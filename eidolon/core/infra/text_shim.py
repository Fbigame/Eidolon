"""text_shim — desc 文本源换轨游戏 CardTextBuilder（pythonnet 无 Unity 进程直调 Assembly-CSharp）。

上游 export-text 实验收口的工程化形态：水合步骤一一对应，不重推导。

一次初始化（进程内单例）：
  load coreclr + Assembly.LoadFrom(Managed/Assembly-CSharp.dll)
    + AppDomain.AssemblyResolve 兜底指向 Managed/（上游 _bootstrap.boot 同法）
  斩日志  Reflection.Emit no-op ILogHandler → UnityEngine.Debug.s_Logger
          （icall 死点②垫片；pythonnet 3.2 对 Unity 程序集接口子类化不可用，必须 IL Emit）
  串表    GameStringTable.Load 读 Strings/<locale>/GAMEPLAY.txt+GLOBAL.txt → GameStrings.s_tables
          （死点④；游戏自家解析器，零解析代码）
  静态    GameDbf.Card 全量水合（FormatterServices.GetUninitializedObject+SetVar 绕真 ctor NRE，
          死点③）+ GameDbfIndex.OnCardAdded 登记——GetCardRecord 供 dispatch 与跨卡名引用
  关键词  KEYWORD_TEXT 全量表（dbf 直读 → SetVar 九键 → GameDbf.KeywordText；
          表=键名表非本地化文本，m_name/m_text=GameStrings 键，译文消费时经 GLOBAL.txt 查；
          NAME/TEXT 存键不预解析，缺译回退=FindSafe 返键名原串=游戏真值。
          上游 keyword-race-tags 立件正典）

per-card 调用（上游实测 ≈0.7ms/卡，记 shim log）：
  build_text(card) 先按 Card.text_builder_type 路由（有效型=tag 782 OVERRIDECARDTEXTBUILDER
  有值覆盖，否则 dbf m_cardTextBuilderType；= EntityDef.cs:EntityDef.GetCardTextBuilder 派发镜像）：
  - 命中 PY_BUILDERS（型 32 BG_QUEST 62 张 / 40 BATTLEGROUNDS_TAVERN_SPELL 61 张 /
    45 BATTLEGROUNDS_DEEP_BLUES 2 张）：不构造 EntityDef、不调 GetCardTextBuilder——Python
    按 Static EntityDef 语义直接实现（40/45 的死点只在游戏 builder 内触发，绕开即不触；
    32 的语义只在 Entity 重载，静态 EntityDef 重载落基类会留 {n}）。info.route="py"。
  - 其余型走 pythonnet 原路：EntityDef（无参 ctor + m_cardId 反射写 + SetTag 注入）
    → ed.GetCardTextBuilder()（分发是游戏自己的代码，铁律 10 合规，本模块零 id 特判）
    → builder.BuildCardTextInHand(ed)。info.route="dll"。

死点①（唯一 native，不可垫片）：ZoneMgr.cctor → ProfilerUnsafeUtility.CreateMarker icall
  （困 builder 型 40/45）。处置（上游裁决 = 本模块架构）：desc 文本源等价「吃进一个 Card 吐出来一个字符串」，按 Card.text_builder_type
  路由；对 pythonnet 无法正确还原的对象不走 pythonnet，Python 自己实现。原「捕获 ECall →
  基类 CardTextBuilder 降级静态文本」的静默错误路径（会残留 {0}/{1} 字面）已删：未路由型
  若 ECall 一律 loud raise（消息含「需补 Python 路由」），fallback=静默分歧，禁。
  离线语义=**静态卡面**（合成 EntityDef：m_controller/m_source=null、非酒馆购物阶段）——
  与 gate 参照（静态卡面截图）同口径，不是任意对局态真值。
  PY_BUILDERS 内仍反射直调纯静态工具（CardTextBuilder.GetRawCardTextInHand /
  TextUtils.TryFormat / TextUtils.TransformCardText）：不触运行态、保真优先。
  32 不触死点：其覆写只在 BuildCardTextInHand(Entity)（BGQuestCardTextBuilder.BuildText），
  静态 EntityDef 调基类不做 TryFormat；Python 路由按 tag 535/1089/2/3 + GameStrings 还原。

消费点：渲染链帧 plan 的 plan["texts"] 汇聚缝（Phase 3 的 ur_frames.prep_plan 对位）——
desc 角色换轨本模块，name/cost/plate 不经 builder 层（游戏里同样不经）。
"""
from __future__ import annotations

import time

from eidolon.core.infra import context   # 契约 D：root/locale/version=ctx 流入
from eidolon.core.infra.errors import GameAssetMissing
from eidolon.core.infra.game_tag import GameTag

_LOG: list[str] = []


def _note(msg: str) -> None:
    _LOG.append(f"[text_shim {time.strftime('%H:%M:%S')}] {msg}")


def boot_log() -> list[str]:
    return list(_LOG)


# 版本来源（原 _product_db_version_str 直读全局 product.db）已随契约 D 解耦：
# ctx.version 由入口边缘层按「root 同装」解析；v1 只记录不判（设计 §1.2/§12.1
# ——版本闸/兼容表/PROVENANCE_VERSION 非目标），本模块消费 ctx 但不校验版本。


class TextShim:
    """进程内单例：装载 + 水合一次，build_text per-card。非线程安全（渲染链单线程假设）。"""

    def __init__(self) -> None:
        self.types: dict = {}
        self.supported_locales: list = []
        self.locale_zhcn = None
        self.cardid_prop = None
        self.set_tag_mi = None
        self._records_built = False
        self._loc_setstring = None  # DbfLocValue.SetString MethodInfo 解析缓存（首触优化，见 make_loc_value）

    # ---------- 装载与类型（export-text _game_env.boot 同法） ----------

    def boot(self) -> "TextShim":
        t0 = time.perf_counter()
        ctx = context.current()
        from pythonnet import load

        load("coreclr")
        from System import AppDomain, ResolveEventHandler
        from System.Reflection import Assembly

        def resolve(sender, args):
            name = args.Name.split(",")[0]
            candidate = ctx.managed / f"{name}.dll"
            if candidate.exists():
                try:
                    return Assembly.LoadFrom(str(candidate))
                except Exception:  # noqa: BLE001
                    return None
            return None

        AppDomain.CurrentDomain.add_AssemblyResolve(ResolveEventHandler(resolve))
        asm = Assembly.LoadFrom(str(ctx.managed / "Assembly-CSharp.dll"))
        _note(f"boot: Assembly-CSharp loaded ({time.perf_counter()-t0:.1f}s)")

        self.types.update({name: asm.GetType(name) for name in (
            "GameDbf", "GameDbfIndex", "CardDbfRecord", "EntityDef", "DbfLocValue",
            "CardTextBuilder", "CardTextBuilderFactory", "TextUtils", "GameStrings",
            "KeywordTextDbfRecord",
        )})
        missing = [k for k, v in self.types.items() if v is None]
        if missing:
            raise RuntimeError(f"text_shim: Assembly-CSharp 类型缺失 {missing}")
        self.types["Localization"] = self.find_type_anywhere("Localization")
        locale_tp = self.find_type_anywhere("Locale")
        self.types["Locale"] = locale_tp
        if locale_tp is not None and bool(locale_tp.IsEnum):
            self.locale_zhcn = locale_tp.GetField("zhCN").GetValue(None)
        sup = self.types["Localization"].GetField("SupportedLocales").GetValue(None)
        self.supported_locales = list(sup)

        # EntityBase.m_cardId（protected）反射写 + EntityDef.SetTag 定位
        from System.Reflection import BindingFlags

        flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static
        prop = None
        base = self.types["EntityDef"]
        while base is not None and prop is None:
            prop = base.GetProperty("m_cardId", BindingFlags.NonPublic | BindingFlags.Instance
                                    | BindingFlags.DeclaredOnly)
            base = base.BaseType
        self.cardid_prop = prop
        mi = None
        base = self.types["EntityDef"]
        while base is not None and mi is None:
            for m in base.GetMethods(flags | BindingFlags.DeclaredOnly):
                if m.Name == "SetTag":
                    mi = m
                    break
            base = base.BaseType
        self.set_tag_mi = mi
        self._flags = flags
        _note(f"boot: types+members ready ({time.perf_counter()-t0:.1f}s)")
        return self

    def find_type_anywhere(self, name: str):
        from System import AppDomain

        for a in AppDomain.CurrentDomain.GetAssemblies():
            try:
                t = a.GetType(name)
            except Exception:  # noqa: BLE001
                t = None
            if t is not None:
                return t
        return None

    # ---------- 调用原语（pythonnet 工程坑：大成员面类型走 MethodInfo.Invoke；int 显式 Int32 装箱） ----------

    @staticmethod
    def csbox(v):
        from System import Boolean, Int32, String

        if isinstance(v, bool):
            return Boolean(v)
        if isinstance(v, int):
            return Int32(v)
        if isinstance(v, str):
            return String(v)
        return v

    def call(self, target, method: str, args: list | None = None, static: bool = False,
             param_type: str | None = None):
        tp = target if static else target.GetType()
        cands = [m for m in tp.GetMethods(self._flags) if m.Name == method]
        if param_type is not None:
            cands = [m for m in cands if m.GetParameters().Length >= 1
                     and m.GetParameters()[0].ParameterType.Name == param_type]
        elif len(cands) > 1 and args is not None:
            by_arity = [m for m in cands if m.GetParameters().Length == len(args)]
            cands = by_arity or cands
        if len(cands) != 1:
            names = [f"({','.join(p.ParameterType.Name for p in m.GetParameters())})" for m in cands]
            raise AttributeError(f"{tp.Name}.{method} ambiguous: {names}")
        return cands[0].Invoke(None if static else target, args or [])

    # ---------- 死点垫片（export-text _game_env.hydrate_logger 同法：Reflection.Emit no-op） ----------

    def hydrate_logger(self) -> None:
        t0 = time.perf_counter()
        from System import Activator
        from System.Reflection import AssemblyName, MethodAttributes, TypeAttributes
        from System.Reflection.Emit import AssemblyBuilder, AssemblyBuilderAccess, OpCodes

        dbg = self.find_type_anywhere("UnityEngine.Debug")
        loghandler_tp = self.find_type_anywhere("UnityEngine.ILogHandler")
        logger_tp = self.find_type_anywhere("UnityEngine.Logger")
        if dbg is None or loghandler_tp is None or logger_tp is None:
            raise RuntimeError("text_shim: UnityEngine logger types missing（斩 Debug.Log icall 失败）")
        ab = AssemblyBuilder.DefineDynamicAssembly(
            AssemblyName("TextShimNoopLog"), AssemblyBuilderAccess.Run)
        mb = ab.DefineDynamicModule("TextShimNoopLog")
        tb = mb.DefineType("NoopLogHandler",
                           TypeAttributes.Class | TypeAttributes.Public | TypeAttributes.BeforeFieldInit,
                           None, [loghandler_tp])
        for m in loghandler_tp.GetMethods():
            params = [p.ParameterType for p in m.GetParameters()]
            dm = tb.DefineMethod(m.Name, MethodAttributes.Public | MethodAttributes.Virtual,
                                 m.ReturnType, params)
            dm.GetILGenerator().Emit(OpCodes.Ret)
        handler = Activator.CreateInstance(tb.CreateType())
        ctor = [c for c in logger_tp.GetConstructors() if c.GetParameters().Length == 1][0]
        logger = ctor.Invoke([handler])
        installed = []
        for fname in ("s_Logger", "s_DefaultLogger"):
            fld = dbg.GetField(fname, self._flags)
            if fld is None:
                continue
            try:
                fld.SetValue(None, logger)
                installed.append(fname)
            except Exception as exc:  # noqa: BLE001
                _note(f"hydrate_logger: {fname} set FAIL {type(exc).__name__}")
        if not installed:
            raise RuntimeError("text_shim: Debug.s_Logger/s_DefaultLogger 均不可写（斩日志失败）")
        _note(f"hydrate_logger: ILogHandler installed via {','.join(installed)}"
              f" ({time.perf_counter()-t0:.1f}s)")

    # ---------- 水合（export-text _game_env 四步同法） ----------

    def hydrate_locale(self) -> None:
        loc = self.types["Localization"].GetMethod("SetLocale")
        if loc is not None and self.locale_zhcn is not None:
            loc.Invoke(None, [self.locale_zhcn])
        _note("hydrate_locale: SetLocale(zhCN) called（探针实证不粘 locale，输出经全列同文解耦）")

    def hydrate_game_strings(self, categories=("GAMEPLAY", "GLOBAL")) -> None:
        """GameStringTable.Load(cat, path, audioPath) 读 Strings/<locale>/*.txt（游戏自家解析器）。"""
        t0 = time.perf_counter()
        strings_dir = context.current().strings_dir
        from System import Activator

        gst_tp = self.find_type_anywhere("GameStringTable")
        cat_tp = self.find_type_anywhere("Global.GameStringCategory")
        if cat_tp is None:
            for a in self._all_assemblies():
                try:
                    for t in a.GetTypes():
                        if t.Name == "GameStringCategory":
                            cat_tp = t
                            break
                except Exception:  # noqa: BLE001
                    pass
                if cat_tp is not None:
                    break
        if gst_tp is None or cat_tp is None:
            raise RuntimeError("text_shim: GameStringTable/GameStringCategory 类型缺失")
        s_tables = self.types["GameStrings"].GetField("s_tables", self._flags).GetValue(None)
        load_mi = [m for m in gst_tp.GetMethods(self._flags)
                   if m.Name == "Load" and m.GetParameters().Length == 3
                   and m.GetParameters()[1].ParameterType.Name == "String"
                   and m.GetParameters()[2].ParameterType.Name == "String"][0]
        map_add = [m for m in s_tables.GetType().GetMethods(self._flags)
                   if m.Name == "Add" and m.GetParameters().Length == 2][0]
        for cat_name in categories:
            cat_val = cat_tp.GetField(cat_name).GetValue(None)
            path = strings_dir / f"{cat_name}.txt"
            if not path.exists():
                cand = sorted(strings_dir.glob(f"{cat_name}*.txt"))
                if not cand:
                    # B4 typed 收口（原裸 RuntimeError）：语料文件缺失=游戏资产类
                    # 缺失（core 发 ENVIRONMENT；preflight 只查 locale 目录存在，
                    # 目录在场但 GAMEPLAY/GLOBAL 缺失在此响亮）。原 RuntimeError
                    # 会被逐卡分类落 render_failed（RENDER 1）——错位：这是环境
                    # 缺语料，不是渲染实现问题。
                    raise GameAssetMissing(
                        path=str(strings_dir),
                        message=f"asset_missing_in_game: Strings/{strings_dir.name} "
                                f"无 {cat_name}*.txt（游戏目录不完整）",
                    )
                path = cand[0]
            tbl = Activator.CreateInstance(gst_tp)
            load_mi.Invoke(tbl, [cat_val, str(path), str(strings_dir / "__no_audio__.txt")])
            entries = self.call(tbl, "GetAll").Count
            map_add.Invoke(s_tables, [cat_val, tbl])
            _note(f"hydrate_game_strings: {cat_name} entries={entries} ({path.name})")
        _note(f"hydrate_game_strings done ({time.perf_counter()-t0:.1f}s)")

    def _all_assemblies(self):
        from System import AppDomain

        return AppDomain.CurrentDomain.GetAssemblies()

    def hydrate_static_dbf(self, field_name: str, records: list) -> None:
        from System import Activator

        fld = self.types["GameDbf"].GetField(field_name, self._flags)
        dbf_tp = fld.FieldType
        dbf_obj = Activator.CreateInstance(dbf_tp, field_name.upper())
        add = [m for m in dbf_tp.GetMethods(self._flags)
               if m.Name == "AddRecord" and m.GetParameters().Length == 1][0]
        for r in records:
            add.Invoke(dbf_obj, [r])
        fld.SetValue(None, dbf_obj)
        _note(f"hydrate_static_dbf: GameDbf.{field_name} <- {len(records)} records")

    def hydrate_keyword_full(self) -> None:
        """KEYWORD_TEXT 全量表水合（dbf 直读 → SetVar 九键 → GameDbf.KeywordText）。

        表=键名表非本地化文本：m_name/m_text 存 GameStrings 键（GLOBAL_KEYWORD_*），
        译文消费时游戏自己经 GameStrings.Get → GLOBAL.txt 解析（漏斗 GetKeywordTextRecord
        GameStrings.cs:GameStrings.GetKeywordTextRecord → GetKeywordName :1566-1573 / GetKeywordText :1590-1597；
        FindSafe miss 回退=返回键名原串，缺译 7 键的回退即游戏真值，零我方特判）。
        **勿用 CARD 表的 zhCN 口径（m_locValues[12]）**——本表无 m_locValues 字段
        （keyword-race-tags p1 证伪在案）。schema=KeywordTextDbfRecord.cs:KeywordTextDbfRecord；
        装载=GameDbf.cs:GameDbf.IsLoaded Load("KEYWORD_TEXT", format)。NOTE_DESC 不装（私有字段、
        无消费；SetVar 十键留一余量，keyword-race-tags A6 同判）。
        849 磁力：dbf 真键=GLOBAL_KEYWORD_MODULAR（GLOBAL_KEYWORD_MAGNETIC 不在
        GLOBAL.txt——已删的最小集硬编码键名失真，全量水合自动修复）。"""
        t0 = time.perf_counter()
        from eidolon.core.infra import dbf

        from System.Runtime.Serialization import FormatterServices

        rows = dbf.default_dbf()._read_records("KEYWORD_TEXT")
        rec_tp = self.types["KeywordTextDbfRecord"]
        records = []
        for u in rows:
            rec = FormatterServices.GetUninitializedObject(rec_tp)
            self.call(rec, "SetVar", ["ID", self.csbox(int(u["m_ID"]))])
            self.call(rec, "SetVar", ["TAG", self.csbox(int(u["m_tagId"]))])
            self.call(rec, "SetVar", ["NAME", u["m_name"] or ""])
            self.call(rec, "SetVar", ["TEXT", u["m_text"] or ""])
            self.call(rec, "SetVar", ["REF_TEXT", u["m_refText"] or ""])
            self.call(rec, "SetVar", ["COLLECTION_TEXT", u["m_collectionText"] or ""])
            self.call(rec, "SetVar", ["IS_COLLECTION_ONLY", self.csbox(bool(u["m_isCollectionOnly"]))])
            self.call(rec, "SetVar", ["AUTO_ADD_SEARCHABLE_TOKEN",
                                      self.csbox(bool(u["m_autoAddSearchableToken"]))])
            self.call(rec, "SetVar", ["TOOLTIP_INIT_ORDER", self.csbox(int(u["m_tooltipInitOrder"]))])
            records.append(rec)
        self.hydrate_static_dbf("KeywordText", records)
        _note(f"hydrate_keyword_full: {len(records)} records（dbf KEYWORD_TEXT 全量表，"
              f"键名表；{time.perf_counter()-t0:.2f}s）")

    # ---------- GameDbf.Card 全量水合（dispatch + 跨卡名引用的数据面） ----------

    def hydrate_card_dbf(self) -> None:
        """36k CARD → CardDbfRecord（GetUninitializedObject+SetVar 五键，probe5 同法）
        → GameDbf.Card 静态 + GameDbfIndex.OnCardAdded 登记。

        2026-11-03 supply-first-touch：SetVar MethodInfo 循环外**解析一次**（原每记录×5
        走 call() 全表 GetMethods 扫描，36,390×5=181,950 次；instance() 全程 call()
        183,843 次 7.9s，cProfile 在案——证据指针见收档 commit body 与实验档 NOTES）。
        解析式与 call() 逐字同构（Name 过滤 → arity 消歧 → 唯一性断言），invoke 的
        方法与实参逐一同前——纯解析缓存，水合产物零变化。"""
        t0 = time.perf_counter()
        from eidolon.core.infra import dbf

        from System.Runtime.Serialization import FormatterServices

        dbf = dbf.default_dbf()
        rec_tp = self.types["CardDbfRecord"]
        cands = [m for m in rec_tp.GetMethods(self._flags) if m.Name == "SetVar"]
        if len(cands) > 1:  # = call() 的 arity 消歧支（args 恒二键 [名, 值]）
            cands = [m for m in cands if m.GetParameters().Length == 2] or cands
        if len(cands) != 1:
            names = [f"({','.join(p.ParameterType.Name for p in m.GetParameters())})" for m in cands]
            raise AttributeError(f"{rec_tp.Name}.SetVar ambiguous: {names}")
        setvar = cands[0]
        records = []
        n_skipped = 0
        for dbf_id, row in dbf.card.items():
            guid = row.get("m_noteMiniGuid") or f"TEXTSHIM_{dbf_id}"
            if not guid:
                n_skipped += 1
                continue
            rec = FormatterServices.GetUninitializedObject(rec_tp)
            setvar.Invoke(rec, ["ID", self.csbox(int(dbf_id))])
            setvar.Invoke(rec, ["NOTE_MINI_GUID", guid])
            setvar.Invoke(rec, ["NAME", self.make_loc_value(row.get("m_name") or "")])
            setvar.Invoke(rec, ["TEXT_IN_HAND", self.make_loc_value(row.get("m_textInHand") or "")])
            setvar.Invoke(rec, ["CARD_TEXT_BUILDER_TYPE",
                                self.csbox(int(row.get("m_cardTextBuilderType") or 0))])
            records.append(rec)
        self.hydrate_static_dbf("Card", records)
        index = self.call(self.types["GameDbf"], "GetIndex", static=True)
        on_added = [m for m in index.GetType().GetMethods(self._flags)
                    if m.Name == "OnCardAdded" and m.GetParameters().Length == 1][0]
        for r in records:
            on_added.Invoke(index, [r])
        self.index = index
        _note(f"hydrate_card_dbf: {len(records)} records (+{n_skipped} no-guid skip)"
              f" ({time.perf_counter()-t0:.1f}s)")

    # ---------- 记录/实体构造与 per-card 直调 ----------

    def make_loc_value(self, text: str):
        from System import Activator

        tp = self.types["DbfLocValue"]
        v = Activator.CreateInstance(tp)
        if self._loc_setstring is None:
            # SetString MethodInfo 解析一次（原每值全表扫描，72,780 值 ~6.4s/进程；
            # 过滤式同前逐字：2 参重载取首个，无唯一性断言——与原码同式）
            self._loc_setstring = [m for m in tp.GetMethods(self._flags)
                                   if m.Name == "SetString"
                                   and m.GetParameters().Length == 2][0]
        for loc in self.supported_locales:
            self._loc_setstring.Invoke(v, [loc, text])
        return v

    def make_entity_def(self, dbf_id: int, card_id: str, tags: dict):
        """EntityDef 无参 ctor + m_cardId 反射写 + SetTag 注入（export-text make_entity_def 同法）。"""
        from System import Activator

        ed = Activator.CreateInstance(self.types["EntityDef"])
        self.cardid_prop.SetValue(ed, card_id)
        for tag, val in tags.items():
            self.set_tag_mi.Invoke(ed, [self.csbox(int(tag)), self.csbox(int(val))])
        return ed

    def build_text(self, card) -> tuple[str, dict]:
        """per-card：Card → (desc_text, info)（唯一文本源入口的实现面）。

        info 键：builder=类名（Python 路由带 "(py)" 后缀）/ builder_type=有效型 /
        route="py"|"dll" / degraded 恒 False（静默降级路径已删，保留键形态）；
        覆盖轴路由（contract C 判据 4，2026-11-06）追加 text_overridden=True。
        card = 渲染链 Card 门面（eidolon/core/infra/card.py）。路由键=card.text_builder_type
        （= EntityDef.cs:EntityDef.GetCardTextBuilder 派发镜像）。未路由型失败一律 raise。"""
        bt = card.text_builder_type
        handler = PY_BUILDERS.get(bt)
        if handler is not None:
            text, info = handler(self, card)
            if card.text_overridden:
                info = {**info, "text_overridden": True}
            return text, info
        ed = self.make_entity_def(card.dbf_id, card.card_id, card.tags)
        if card.text_overridden:
            return self._build_text_overridden(card, ed, bt)
        builder = self.call(ed, "GetCardTextBuilder")
        try:
            built = self.call(builder, "BuildCardTextInHand", [ed], param_type="EntityDef")
        except Exception as exc:  # noqa: BLE001
            if "ECall" in str(exc):
                raise RuntimeError(
                    f"builder_type={bt} EntityDef 路径离线不可用（ECall）；需补 Python 路由"
                ) from exc
            raise
        return str(built), {"builder": builder.GetType().Name, "builder_type": bt,
                            "route": "dll", "degraded": False}

    def _build_text_overridden(self, card, ed, bt) -> tuple[str, dict]:
        """覆盖轴 DLL 路由（contract C 判据 4，2026-11-06）：Card.text 改写 → 水合
        GameDbf.Card 记录的 TEXT_IN_HAND 换成 Card.text（CardDbfRecord.SetTextInHand，
        CardDbfRecord.cs:CardDbfRecord.SetTextInHand——builder 经 GetCardRecordTextInHand
        读的就是这条记录），真 builder 照常跑（类型处理保真——引擎语义=记录文本变了，
        CardTextBuilder.cs:CardTextBuilder.GetRawCardTextInHand），终态还原（finally；
        进程单例全局面，窗口内渲染链单线程）。记录查无=响亮（覆盖无处注入，禁静默丢）。"""
        rec = self.call(self.index, "GetCardRecord", [card.card_id], param_type="String")
        if rec is None:
            raise RuntimeError(
                f"text_shim: dbf={card.dbf_id} card_id={card.card_id!r} 不在水合 "
                "GameDbf.Card 索引——desc 覆盖无处注入（fail loud，禁静默丢覆盖）")
        original = rec.TextInHand
        self.call(rec, "SetTextInHand", [self.make_loc_value(card.text or "")])
        try:
            builder = self.call(ed, "GetCardTextBuilder")
            built = self.call(builder, "BuildCardTextInHand", [ed], param_type="EntityDef")
        except Exception as exc:  # noqa: BLE001
            if "ECall" in str(exc):
                raise RuntimeError(
                    f"builder_type={bt} EntityDef 路径离线不可用（ECall）；需补 Python 路由"
                ) from exc
            raise
        finally:
            self.call(rec, "SetTextInHand", [original])
        return str(built), {"builder": builder.GetType().Name, "builder_type": bt,
                            "route": "dll", "degraded": False, "text_overridden": True}


# ============================================================================
# Python 静态 builder 路由（type 32/40/45；2026-10-19 C 批 + BG_QUEST 批）
# ============================================================================
# 用户裁决 2026-10-19：desc 文本源=「吃进一个 Card 吐出来一个字符串」，按
# Card.text_builder_type 路由；对 pythonnet 无法正确还原的对象不走 pythonnet，直接自己
# 实现。40/45 的 EntityDef 路径共同死点=ZoneMgr.cctor → ProfilerUnsafeUtility.CreateMarker
# icall（native，不可垫片）；32 的语义只覆写了 BuildCardTextInHand(Entity)，静态
# EntityDef 重载落基类 ⇒ 不做 TryFormat、残留 {n}。离线合成 EntityDef 的
# m_controller/m_source=null 且非酒馆购物阶段 ⇒ 游戏侧 alt 切换/增量分支全被 null 跳过，
# Python 转写只需静态部分。**离线语义=静态卡面**（与 gate 参照同口径），非任意对局态。
#
# 型值锚：Assets/Card.cs:Assets.Card.CardTextBuilderType 枚举（BG_QUEST 第 33 项=32、
# BATTLEGROUNDS_TAVERN_SPELL 第 41 项=40、BATTLEGROUNDS_DEEP_BLUES_SPELL 第 46 项=45），
# 与 dbf CARD.m_cardTextBuilderType 同域；路由只按型，零逐卡特判。
PY_BT_BG_QUEST = 32
PY_BT_TAVERN_SPELL = 40
PY_BT_DEEP_BLUES = 45


def _raw_card_text(shim: "TextShim", card) -> str:
    """CardTextBuilder.GetRawCardTextInHand(cardId) 直调（游戏静态函数）。

    decomp 锚：CardTextBuilder.cs:CardTextBuilder.GetRawCardTextInHand =
    TextUtils.GetDefaultTextVariant(GetCardRecordTextInHand(cardId))——dbf TextInHand
    按 '~' 切默认变体；缺记录 → ""。

    文本覆盖轴（contract C 判据 4，2026-11-06）：card.text_overridden → raw 改从
    Card.text 取（`GetDefaultTextVariant(card.text)`——同一函数式第二半边，只是
    「记录里的文本」换成调用方改写值；'~' 变体切分语义照常，TextUtils.cs:
    TextUtils.GetDefaultTextVariant）。"""
    if card.text_overridden:
        return str(shim.call(shim.types["TextUtils"], "GetDefaultTextVariant",
                             [card.text or ""], static=True))
    return str(shim.call(shim.types["CardTextBuilder"], "GetRawCardTextInHand",
                         [card.card_id], static=True))


def _try_format(shim: "TextShim", fmt: str, values) -> str:
    """TextUtils.TryFormat(fmt, params object[]) 直调（string.Format；异常原样返回 fmt）。

    decomp 锚：TextUtils.cs:TextUtils.TryFormat。params object[] 显式
    System.Object[] + 逐值装箱（Int32/String；pythonnet 反射面）。40/45 传 int 元组，
    32 传 int/str 混合（TryFormat 的 4 槽）。"""
    from System import Array, Object

    args = Array[Object]([TextShim.csbox(v) for v in values])
    return str(shim.call(shim.types["TextUtils"], "TryFormat", [fmt, args], static=True))


def _transform_card_text(shim: "TextShim", text: str) -> str:
    """TextUtils.TransformCardText(text, parameters=null) 直调（静态口径）。

    decomp 锚：TextUtils.cs:TextUtils.TransformCardText(string, TransformCardTextParams)
    → DoesStringRequireTransformation? → ParseTextForCraftableSplit →
    GameStrings.ParseLanguageRules →（GameMgr.Get()!=null && !IsBattlegrounds）
    ParseTextForInfinity；离线 GameMgr.Get()=null，末支跳过。
    param_type="String" 消歧（另有同 arity 的 (Entity, string) 重载）。"""
    return str(shim.call(shim.types["TextUtils"], "TransformCardText", [text, None],
                         static=True, param_type="String"))


def _race_name(shim: "TextShim", race: int, total: int) -> str:
    """GameStrings.GetRaceName[Battlegrounds](TAG_RACE) 直调（静态串表；count>1 走 BG 名）。

    decomp 锚：BGQuestCardTextBuilder.cs:BGQuestCardTextBuilder.GetRaceString——count > 1
    → GetRaceNameBattlegrounds(race)，否则 GetRaceName(race)；race=0 时调用方不填槽
    （空串）。TAG_RACE 为枚举入参，经静态方法签名取枚举类型后 Enum.ToObject 装箱
    （pythonnet 反射面）。"""
    if not race:
        return ""
    from System import Enum

    gs = shim.types["GameStrings"]
    name = "GetRaceNameBattlegrounds" if total > 1 else "GetRaceName"
    mi = [m for m in gs.GetMethods(shim._flags) if m.Name == name][0]
    race_tp = mi.GetParameters()[0].ParameterType
    enum_v = Enum.ToObject(race_tp, int(race))
    return str(shim.call(gs, name, [enum_v], static=True))


def _py_tavern_spell(shim: "TextShim", card) -> tuple[str, dict]:
    """type 40：BattlegroundsTavernSpellCardTextBuilder.BuildCardTextInHand(EntityDef) 转写。

    逐句锚（BattlegroundsTavernSpellCardTextBuilder.cs:BattlegroundsTavernSpellCardTextBuilder.
    BuildCardTextInHand(EntityDef)）：
      raw = CardTextBuilder.GetRawCardTextInHand(entityDef.GetCardId())；
      desiredAltTextIndex=0；entity=m_controller=null + 非购物阶段 ⇒ alt 切换分支跳过；
      raw = GetAlternateTextSubstring(raw, 0) = raw.Split('@')[0]（空串→""）；
      num..num4 = entityDef.GetTag(TAG_SCRIPT_DATA_NUM_1..4)（tag 2/3/2889/2919，
      GAME_TAG.cs:GAME_TAG.TAG_SCRIPT_DATA_NUM_*）；m_source=null ⇒
      BACON_EVOLUTION_* 增量跳过；
      return TextUtils.TransformCardText(TextUtils.TryFormat(raw, num, num2, num3, num4))。"""
    raw = _raw_card_text(shim, card)
    raw = raw.split("@")[0] if raw else ""
    nums = (card.tags[GameTag.TAG_SCRIPT_DATA_NUM_1],
            card.tags[GameTag.TAG_SCRIPT_DATA_NUM_2],
            card.tags[GameTag.TAG_SCRIPT_DATA_NUM_3],
            card.tags[GameTag.TAG_SCRIPT_DATA_NUM_4])
    text = _transform_card_text(shim, _try_format(shim, raw, nums))
    return text, {"builder": "BattlegroundsTavernSpellCardTextBuilder(py)",
                  "builder_type": PY_BT_TAVERN_SPELL, "route": "py", "degraded": False}


def _py_deep_blues(shim: "TextShim", card) -> tuple[str, dict]:
    """type 45：BattlegroundsDeepBluesCardTextBuilder.BuildCardTextInHand(EntityDef) 转写。

    逐句锚（BattlegroundsDeepBluesCardTextBuilder.cs:BattlegroundsDeepBluesCardTextBuilder.
    BuildCardTextInHand(EntityDef)）：
      raw = CardTextBuilder.GetRawCardTextInHand(entityDef.GetCardId())（无 alt 切分）；
      entity=m_controller=null + 非购物阶段 ⇒ 不乘 (1+BACON_DEEP_BLUE)；
      num/num2 = entityDef.GetTag(TAG_SCRIPT_DATA_NUM_1..2)（tag 2/3）；
      return TextUtils.TransformCardText(TextUtils.TryFormat(raw, num, num2))。"""
    raw = _raw_card_text(shim, card)
    nums = (card.tags[GameTag.TAG_SCRIPT_DATA_NUM_1],
            card.tags[GameTag.TAG_SCRIPT_DATA_NUM_2])
    text = _transform_card_text(shim, _try_format(shim, raw, nums))
    return text, {"builder": "BattlegroundsDeepBluesCardTextBuilder(py)",
                  "builder_type": PY_BT_DEEP_BLUES, "route": "py", "degraded": False}


def _py_bg_quest(shim: "TextShim", card) -> tuple[str, dict]:
    """type 32：BGQuestCardTextBuilder.BuildText(Entity) 静态转写。

    逐句锚（BGQuestCardTextBuilder.cs:BGQuestCardTextBuilder.BuildText(Entity)）：
      raw = CardTextBuilder.GetRawCardTextInHand(entity.GetCardId())；
      tag = entity.GetTag(QUEST_PROGRESS_TOTAL=535)；
      tag2 = entity.GetTag(QUEST_REWARD_DATABASE_ID=1089)；
      text = tag2!=0 时 GameDbf.Card.GetRecord(tag2).Name（奖励卡名），否则 ""；
      text2/text3 = TAG_SCRIPT_DATA_NUM_1/2 != 0 时
                    GetRaceString((TAG_RACE)tag, tag)（tag>1 → GetRaceNameBattlegrounds，
                    否则 GetRaceName），否则 ""；
      text4 = TextUtils.TryFormat(raw, tag, text, text2, text3)；
      text4 含 '@'：tag2!=0 → Remove('@')（保留两段），否则 Substring(0, '@')；
      return TextUtils.TransformCardText(entity, text4)。
    静态 EntityDef：tag/奖励/种族全读 CARD_TAG + GameStrings 静态串表；无运行态实体引用
    （与 18/20 等 Entity 重载不同）。"""
    from eidolon.core.infra import dbf

    raw = _raw_card_text(shim, card)
    total = card.tags[GameTag.QUEST_PROGRESS_TOTAL]
    reward_id = card.tags[GameTag.QUEST_REWARD_DATABASE_ID]
    reward = ""
    if reward_id:
        rec = dbf.default_dbf().card.get(reward_id) or {}
        reward = str(rec.get("m_name") or "")
    race1 = _race_name(shim, card.tags[GameTag.TAG_SCRIPT_DATA_NUM_1], total)
    race2 = _race_name(shim, card.tags[GameTag.TAG_SCRIPT_DATA_NUM_2], total)
    text = _try_format(shim, raw, (total, reward, race1, race2))
    at = text.find("@")
    if at >= 0:
        text = (text[:at] + text[at + 1:]) if reward_id else text[:at]
    text = _transform_card_text(shim, text)
    return text, {"builder": "BGQuestCardTextBuilder(py)",
                  "builder_type": PY_BT_BG_QUEST, "route": "py", "degraded": False}


PY_BUILDERS = {PY_BT_BG_QUEST: _py_bg_quest,
               PY_BT_TAVERN_SPELL: _py_tavern_spell,
               PY_BT_DEEP_BLUES: _py_deep_blues}


_INSTANCE: TextShim | None = None


def instance() -> TextShim:
    """进程内单例（首调完成装载+水合；一次性成本记 boot_log）。"""
    global _INSTANCE
    if _INSTANCE is None:
        t0 = time.perf_counter()
        shim = TextShim().boot()
        shim.hydrate_logger()
        shim.hydrate_locale()
        shim.hydrate_game_strings(("GAMEPLAY", "GLOBAL"))
        shim.hydrate_card_dbf()
        shim.hydrate_keyword_full()
        _note(f"instance ready, total {time.perf_counter()-t0:.1f}s")
        _INSTANCE = shim
    return _INSTANCE


def desc_text_for(card) -> tuple[str, dict]:
    """prep_plan 缝的薄封装：(desc 文本, 信息)。单例惰性引导。"""
    return instance().build_text(card)
