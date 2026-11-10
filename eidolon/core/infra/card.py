"""card — 渲染链 tag 语义层（Card 模型，2026-10-05 用户提案正典化）。

用户口径：渲染代码调 Card 类，不再散落 `tags.get("476", "0")` 舞蹈。**渲染链消费点已
对接**（2026-10-06 card-integration：render_card/ur_frames/scene_compiler 及五帧模块
compile 全量换轨，CSV 旧轨同日撤除）。

- 属性注册面=渲染链当前实际消费的 tag 集（枚举 id 见各属性 docstring；全集 282 见
  docs/notes/engine-render-tag-inventory.md，消费扩容再补，避免死代码）；
- 构造=整卡元数据门面：`from_dbf(dbf_id)` 组装（CARD 记录全字段+CARD_TAG+离线 set 归属）；
  CSV 旧轨已删（用户裁决 2026-10-06：兼容性无意义）；
- 衍生语义属性=各 compile 散落解释逻辑的收拢预备（decomp 定案随手引）；
- `.raw` 逃生舱=归一化 int dict；攻耐(45/47)原不在注册面（notext 语料连数字都无）——compiler
  统计文本路径现役消费（2026-10-21 gametag-card-merge 收口批入册 attack/health）。

值域=IntEnum/IntFlag 正典：CardType/Rarity/Premium/SpellSchool/CardClass 五枚举**值改活表全镜像**
（上游收口：decomp 手抄值退役，`dll_reflect.enum_table` 逐名供货，缺名/活表
多名导入即响；切换前已一次性对拍全等）；ClassMask 机械派生自 CardClass
（值≥1，位=值−1）；476 掩码 `Card.classes` 逐位扫解码（bit i → TAG_CLASS i+1），未知位
_dec 降级裸 int 忠实入列——IntFlag 迭代只出已命名位、未知位静默丢，禁；未知值 _dec 降级
裸 int（下游等值判式天然不命中、类色消费端必抛，未知不得当缺省）。
"""
from __future__ import annotations

from functools import cached_property
from pathlib import Path

from eidolon.core.infra.game_tag import GameTag   # 渲染消费白名单（值=活表供货，见 game_tag.py）

# ---- 值域枚举（CardType/Rarity/Premium/SpellSchool/CardClass=活表全镜像，值由 _mirror 供货）----
from enum import IntEnum, IntFlag
from functools import lru_cache

from eidolon.core.infra.dll_reflect import enum_table, static_enum_dict
from eidolon.core.infra import il_tables


def _mirror(tag_enum_name: str):
    """活枚举全镜像装载器：返回 (取值函数, 全镜像断言)。

    缺名=成员定义行即响（ImportError 点名）；活表多名=断言响（新成员先判消费语义
    ——族表/宝石/品质链——再入册）。值随活表供货，逐值相等在构造上成立。
    """
    live = enum_table(tag_enum_name)

    def value(name: str) -> int:
        try:
            return live[name]
        except KeyError:
            raise ImportError(
                f"{tag_enum_name}.{name} 不在活枚举（{len(live)} 成员）——值域镜像漂移："
                "客户端升级/改名，先核 Assembly-CSharp 再动成员") from None

    def assert_mirror(enum_cls) -> None:
        extra = sorted(set(live) - {m.name for m in enum_cls})
        assert not extra, (
            f"{tag_enum_name} 活表多出成员 {extra}——值域枚举=活表全镜像（缺名导入即响、"
            "值随活表构造上相等），新成员先判消费语义再入册")

    return value, assert_mirror


_cardtype_v, _assert_cardtype = _mirror("TAG_CARDTYPE")
_rarity_v, _assert_rarity = _mirror("TAG_RARITY")
_premium_v, _assert_premium = _mirror("TAG_PREMIUM")
_school_v, _assert_school = _mirror("TAG_SPELL_SCHOOL")
_class_v, _assert_class = _mirror("TAG_CLASS")


class CardType(IntEnum):
    """TAG_CARDTYPE 全镜像（活表 22 成员；跳号段 12/22/23/24/39/40/42-45=活表原样）。"""

    INVALID = _cardtype_v("INVALID")
    GAME = _cardtype_v("GAME")
    PLAYER = _cardtype_v("PLAYER")
    HERO = _cardtype_v("HERO")
    MINION = _cardtype_v("MINION")
    SPELL = _cardtype_v("SPELL")
    ENCHANTMENT = _cardtype_v("ENCHANTMENT")
    WEAPON = _cardtype_v("WEAPON")
    ITEM = _cardtype_v("ITEM")
    TOKEN = _cardtype_v("TOKEN")
    HERO_POWER = _cardtype_v("HERO_POWER")
    BLANK = _cardtype_v("BLANK")
    GAME_MODE_BUTTON = _cardtype_v("GAME_MODE_BUTTON")
    MOVE_MINION_HOVER_TARGET = _cardtype_v("MOVE_MINION_HOVER_TARGET")
    LETTUCE_ABILITY = _cardtype_v("LETTUCE_ABILITY")
    BATTLEGROUND_HERO_BUDDY = _cardtype_v("BATTLEGROUND_HERO_BUDDY")
    LOCATION = _cardtype_v("LOCATION")
    BATTLEGROUND_QUEST_REWARD = _cardtype_v("BATTLEGROUND_QUEST_REWARD")
    BATTLEGROUND_SPELL = _cardtype_v("BATTLEGROUND_SPELL")
    BATTLEGROUND_ANOMALY = _cardtype_v("BATTLEGROUND_ANOMALY")
    BATTLEGROUND_TRINKET = _cardtype_v("BATTLEGROUND_TRINKET")
    PET = _cardtype_v("PET")


class CardClass(IntEnum):
    """TAG_CLASS 全镜像（活表 15 成员）。

    class 轴活表化（上游收口）：
    decomp 手抄退役，值=`dll_reflect.enum_table` 逐名供货——缺名导入即响、
    活表多名断言响（新职业先判消费语义——类色槽/显示名/476 位掩码——再入册）。
    值域锚=TAG_CLASS（活枚举）；切换前已一次性对拍全等。
    """
    INVALID = _class_v("INVALID")
    DEATHKNIGHT = _class_v("DEATHKNIGHT")
    DRUID = _class_v("DRUID")
    HUNTER = _class_v("HUNTER")
    MAGE = _class_v("MAGE")
    PALADIN = _class_v("PALADIN")
    PRIEST = _class_v("PRIEST")
    ROGUE = _class_v("ROGUE")
    SHAMAN = _class_v("SHAMAN")
    WARLOCK = _class_v("WARLOCK")
    WARRIOR = _class_v("WARRIOR")
    DREAM = _class_v("DREAM")
    NEUTRAL = _class_v("NEUTRAL")
    WHIZBANG = _class_v("WHIZBANG")
    DEMONHUNTER = _class_v("DEMONHUNTER")


class Rarity(IntEnum):
    """TAG_RARITY 全镜像（活表 6 成员）。"""

    INVALID = _rarity_v("INVALID")
    COMMON = _rarity_v("COMMON")
    FREE = _rarity_v("FREE")
    RARE = _rarity_v("RARE")
    EPIC = _rarity_v("EPIC")
    LEGENDARY = _rarity_v("LEGENDARY")


class Premium(IntEnum):
    """TAG_PREMIUM 全镜像（活表 5 成员；MAX=哨兵位镜像——dbf 不携，值域上界）。

    活表多名断言靠 MAX 行成立；真品质档新增（SIGNATURE 先例）→ 断言响 →
    先判宝石/品质链消费再入册。
    """

    NORMAL = _premium_v("NORMAL")
    GOLDEN = _premium_v("GOLDEN")
    DIAMOND = _premium_v("DIAMOND")
    SIGNATURE = _premium_v("SIGNATURE")
    MAX = _premium_v("MAX")   # 哨兵（活表第 5 成员；值域上界镜像，非品质档）


class SpellSchool(IntEnum):
    """TAG_SPELL_SCHOOL 全镜像（活表 14 成员）。"""

    NONE = _school_v("NONE")
    ARCANE = _school_v("ARCANE")
    FIRE = _school_v("FIRE")
    FROST = _school_v("FROST")
    NATURE = _school_v("NATURE")
    HOLY = _school_v("HOLY")
    SHADOW = _school_v("SHADOW")
    FEL = _school_v("FEL")
    PHYSICAL_COMBAT = _school_v("PHYSICAL_COMBAT")
    TAVERN = _school_v("TAVERN")
    SPELLCRAFT = _school_v("SPELLCRAFT")
    LESSER_TRINKET = _school_v("LESSER_TRINKET")
    GREATER_TRINKET = _school_v("GREATER_TRINKET")
    UPGRADE = _school_v("UPGRADE")


# 全镜像断言（活表多名 → 响亮；缺名已在成员行响，值相等由构造保证）
_assert_cardtype(CardType)
_assert_rarity(Rarity)
_assert_premium(Premium)
_assert_school(SpellSchool)
_assert_class(CardClass)


def _dec(enum_cls, v: int):
    """dbf 值→枚举；未定义值（游戏改版新值）降级返回裸 int——忠实转达，不编造不崩溃。"""
    try:
        return enum_cls(v)
    except ValueError:
        return v


def _name(v) -> str:
    """枚举成员→.name；裸 int（降级态）→ ?N。"""
    return v.name if isinstance(v, IntEnum) else f"?{v}"


# 476 位掩码：位位置=CardClass 值−1（引擎解码 bit i → TAG_CLASS i+1，EntityBase.cs:EntityBase.GetClasses
# `int num2 = 1` 起数——上游定案：BG_RLK_833t 476=5 引擎渲 DEATHKNIGHT+HUNTER 帧
# （参照实证），旧「位=值」解码错位成 INVALID+DRUID）。
# 机械派生自 CardClass（值≥1），禁手写第二份。解码=Card.classes 逐位扫
# （IntFlag 迭代静默丢未知位——上游已退役该解码路；本 IntFlag 留作位名账面/构造器）。
ClassMask = IntFlag("ClassMask", [(m.name, 1 << (m.value - 1))
                                  for m in CardClass if m.value >= 1])

def _live_faction_members() -> list[tuple[str, int]]:
    """CardColorSwitcher+FactionColorType 活枚举 → 非 GENERIC 成员（TYPE_ 前缀剥除，
    上游换轨，手抄值退役）。

    引擎语义=FactionColorType 成员序即 VALID_FACTIONS 槽位序（值=banner 六格图集
    下标，SetFactionType 消费真值域）。形状断言=全体成员 TYPE_ 前缀 ∧
    GENERIC=0 在位（引擎改名/加员→红→重锚）。
    """
    fc = enum_table("CardColorSwitcher+FactionColorType")
    assert fc.get("TYPE_GENERIC") == 0, (
        f"FactionColorType 形态漂移（TYPE_GENERIC 缺失/非 0：{fc}）——引擎枚举变更，"
        "先核 Assembly-CSharp 再重锚")
    bad = [k for k in fc if not k.startswith("TYPE_")]
    assert not bad, f"FactionColorType 成员非 TYPE_ 前缀（{bad}）——形态漂移"
    members = [(k[len("TYPE_"):], v) for k, v in fc.items() if k != "TYPE_GENERIC"]
    assert len({n for n, _ in members}) == len(members) and members, (
        f"FactionColorType 剥前缀后重名：{members}")
    return members


Faction = IntEnum("Faction", _live_faction_members())
Faction.__doc__ = """派系（tag id 组，非值域）：值=banner 槽位序（六格图集下标）。

活镜像=CardColorSwitcher+FactionColorType 非 GENERIC 成员（TYPE_ 前缀剥除，
上游换轨，手抄值退役）——成员序=引擎
VALID_FACTIONS 数组序（Actor.cs:Actor）→ SetFactionType 消费真值域
（HearthstoneFactionBanner.cs:HearthstoneFactionBanner.SetFactionType）。
tag id→成员映射=FACTION_TAG_IDS（ctor IL 序+名字连结派生）。"""


class BannerKind(IntEnum):
    """banner 挂件种类（成员值=驱动 tag id，Card.banners 消费）。"""
    FACTION_GRIMY_GOONS = int(GameTag.GRIMY_GOONS)
    FACTION_KABAL = int(GameTag.KABAL)
    FACTION_JADE_LOTUS = int(GameTag.JADE_LOTUS)
    FACTION_ZERG = int(GameTag.ZERG)
    FACTION_TERRAN = int(GameTag.TERRAN)
    FACTION_PROTOSS = int(GameTag.PROTOSS)
    TRADEABLE = int(GameTag.TRADEABLE)
    FORGE = int(GameTag.FORGE)
    PREPARE = int(GameTag.PREPARE)


def _live_faction_tag_ids() -> list[tuple[int, int]]:
    """VALID_FACTIONS ctor 序 × 活枚举名字连结 → (GAME_TAG 值, Faction 槽位) 对
    （上游换轨，手抄值退役）。

    序权威=Actor..ctor VALID_FACTIONS List<GAME_TAG> 初始化 IL
    （`il_tables.ctor_list_const_items`，声明序=引擎判定序）；配对权威=名字连结
    （GAME_TAG 活枚举成员名 == Faction 成员名——两活表同名词连结，改名即响）。
    形状断言=Faction 全成员与 VALID_FACTIONS 名集双射（引擎单边加员→红→先判消费
    语义再重锚）。语义旁证=GetFactionColorTypeForTag 活 Invoke（tag→FactionColorType）
    与本对射全等。
    """
    vf = il_tables.ctor_list_const_items("Actor", "VALID_FACTIONS")
    tag_by_val = {v: k for k, v in enum_table("GAME_TAG").items()}
    fac_by_name = {m.name: int(m) for m in Faction}
    bad = [f"{tag_by_val.get(tv)}@{tv}" for tv in vf
           if tag_by_val.get(tv) not in fac_by_name]
    assert not bad, (
        f"VALID_FACTIONS ctor 序含无 Faction 同名成员的 tag（{bad}）——引擎派系"
        "枚举漂移，先核 Assembly-CSharp 再重锚")
    out = [(tv, fac_by_name[tag_by_val[tv]]) for tv in vf]
    assert {name for name in fac_by_name} == {tag_by_val[tv] for tv, _ in out}, (
        f"VALID_FACTIONS 与 Faction 成员非双射（ctor={vf}）——引擎单边加员/减员")
    return out


FACTION_TAG_IDS = _live_faction_tag_ids()

@lru_cache(maxsize=1)
def _sort_race_order() -> tuple[int, ...]:
    """SortRaceList 固定序（活 IL 直读，进程 memo；上游换轨，手抄序表退役）。

    引擎序表=EntityBase.SortRaceList 方法内 TAG_RACE[13] 常量数组——Release 编译
    收进 `<PrivateImplementationDetails>` RVA 静态数据（Ldtoken+InitializeArray 装
    闭包字段 order），`il_tables.method_rva_arrays` 机械提取（引擎同款机制灌出）。
    引擎排序键=Array.IndexOf（序外种族 -1 排最前，EntityBase.cs:1215-1219）——非
    「未知垫底」。形状断言=13 项互异且全落 TAG_RACE 活值域（引擎加种族入序/换序→
    断言红→重锚；项数=当前引擎形态钉，非手抄值）。
    """
    import struct   # noqa: PLC0415（stdlib，随活读一次性）

    (rva_name, raw), = il_tables.method_rva_arrays("EntityBase", "SortRaceList")
    vals = struct.unpack(f"<{len(raw) // 4}i", raw)
    race_vals = set(enum_table("TAG_RACE").values())
    assert len(vals) == 13 and len(set(vals)) == 13 and set(vals) <= race_vals, (
        f"SortRaceList RVA 序表形态漂移（{rva_name}: {vals}）——引擎序表变更，"
        "先核 Assembly-CSharp 再重锚形状断言")
    return vals


@lru_cache(maxsize=1)
def _trinket_subset_to_race() -> tuple[tuple[int, int], ...]:
    """s_raceSubsetToRaceTable 活反射对（进程 memo；上游换轨，手抄键值对退役）。

    引擎源=EntityBase 静态只读字典（EntityBase.cs:25-79 初始化器；GetRacesForTrinket
    :1146-1165 键值对源，ALL 早退支 :1154-1159 Clear+Add+break）——
    `dll_reflect.static_enum_dict` 直取（纯字典填充型静态构造，GameStrings 先例）。
    迭代序=.NET 插入序（=引擎初始化器序，与旧手抄序同）；语义面=键值映射。
    形状断言=键全落 GAME_TAG 活值域 ∧ 值全落 TAG_RACE 活值域 ∧ ALL 键在位（早退支
    语义成员）。"""
    live = static_enum_dict("EntityBase", "s_raceSubsetToRaceTable")
    tag_vals = set(enum_table("GAME_TAG").values())
    race_vals = set(enum_table("TAG_RACE").values())
    assert set(live) <= tag_vals and set(live.values()) <= race_vals, (
        f"s_raceSubsetToRaceTable 值域漂移（{sorted(live.items())}）——引擎键值变更，"
        "先核 Assembly-CSharp 再重锚")
    assert int(GameTag.BACON_SUBSET_ALL) in live, (
        "s_raceSubsetToRaceTable 缺 BACON_SUBSET_ALL——早退支语义成员缺失，"
        "引擎字典变更，先核 Assembly-CSharp")
    return tuple(live.items())


class _TagDict(dict):
    """GetTag 语义容器（EntityBase：查不到即 0）。读侧默认不插入——tags 保持
    「卡实际有什么」的忠实性（defaultdict 的读时插入会污染枚举面，故用 __missing__）。

    写侧失效语义（contract C 判据 5，2026-11-06）：任何变更操作通知宿主 Card 清
    cached_property 派生缓存——先读后改不再返回旧值（外审探针实证项：patch 后
    classes/races 等曾吃旧值）。读侧零触发（读不失效）。"""

    def __init__(self, mapping=(), *, owner: "Card | None" = None):
        super().__init__(mapping)
        self._owner = owner

    def _fire(self) -> None:
        if self._owner is not None:
            self._owner._invalidate_tag_derived()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._fire()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._fire()

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._fire()

    def setdefault(self, key, default=None):
        v = super().setdefault(key, default)
        self._fire()
        return v

    def pop(self, key, *default):
        v = super().pop(key, *default)
        self._fire()
        return v

    def popitem(self):
        v = super().popitem()
        self._fire()
        return v

    def clear(self):
        super().clear()
        self._fire()

    def __missing__(self, key):
        return 0


class Card:
    """单卡元数据门面：tags（GetTag 语义容器）+ CARD 记录全字段 + 离线 set 归属。
    构造经 from_dbf（dbf.unity3d 直提，元数据裁决 2026-10-05；CSV 旧轨已删）。

    覆盖轴座位（contract C 判据 3 落位 + contract E 消费，2026-11-06）：
    frame_asset/portrait_asset/watermark_asset 显式字段（None=数据轴照旧）；消费
    接缝=契约 E（覆盖落 plan/supply：supply/overrides.py 装载校验单点，frame=类色
    图集写点平面 / portrait=运行时槽 / watermark=V-pass _SecondTex 源）。
    watermark_force=水印强制（契约 E）：忽略 HIDE_WATERMARK(1107) 闸（alpha 三支的
    hide 腿让位）——数据轴 alpha 语义两档（0 / 99/128）保真不变。
    desc 文本覆盖=改写 .text（判据 4，见 text_overridden）。
    races_text_override=种族文本/板数覆盖座位（设计 §7.5；构造后显式设置，非 tag 派生）。"""

    def __init__(self, record: dict, tags: dict, set_id: int | None = None, *,
                 frame_asset: "str | Path | None" = None,
                 portrait_asset: "str | Path | None" = None,
                 watermark_asset: "str | Path | None" = None,
                 watermark_force: bool = False,
                 races_text_override: "tuple[str, ...] | None" = None):
        self.record = record                            # CARD DBF 行全字段（27 列）
        self.tags = _TagDict({int(k): int(v or 0) for k, v in tags.items()},
                             owner=self)                # 写侧失效语义（_TagDict._fire）
        self._desc_account: dict | None = None          # desc 真值账（懒 CLR，见 desc_text_account）
        self._desc_text_source: str | None = None       # desc 账对应的 Card.text 快照（覆盖轴失效检测）
        self.set_id = set_id                            # 离线 GetCardSet 正典（watermark 链）
        self.name = record.get("m_name", "")
        self.text = record.get("m_textInHand", "")
        self.card_id = record.get("m_noteMiniGuid", "")   # =m_NoteMiniGuid 值（全仓既定称呼：
                                                          # manifest 列/card_components 目录键/
                                                          # 报告搜索框）；字段名里的 Guid 与
                                                          # Unity 资产 GUID 无关（后者仅出现于
                                                          # watermark_override 等资产解析串，
                                                          # slug 形制可目辨）
        self.frame_asset = frame_asset                  # 帧覆盖资产座位（契约 E 接缝落位）
        self.portrait_asset = portrait_asset            # 原画覆盖资产座位（契约 E 接缝落位）
        self.watermark_asset = watermark_asset          # 水印覆盖资产座位（契约 E 消费位）
        self.watermark_force = bool(watermark_force)    # 水印强制（契约 E：忽略 HIDE_WATERMARK）
        # 种族文本覆盖座位（设计 §7.5）：显式 tuple=覆盖种族文本与板数（消费点在
        # render 的 compiler/components）；None=数据轴照旧。**不是 tag 派生**——
        # _invalidate_tag_derived 不清它，覆盖轴在构造后显式设置。
        self.races_text_override = races_text_override

    def _invalidate_tag_derived(self) -> None:
        """tags 变更 → 派生缓存清空（contract C 判据 5：cached_property 失效语义，
        由 _TagDict 写侧触发；先读后改不再返回旧值）。_desc_account 同清（desc 管线
        吃 SCRIPT_DATA_NUM 等 tag）——desc 账另有 Card.text 快照检测（_desc_text_account）
        双保险。record 轴不在失效域（数据真值，约定不可变；变更走重建 Card）。

        注（Phase 3c 修正）：``_desc_account`` / ``_desc_text_source`` 是
        ``__init__`` 里的**普通实例属性**（非 cached_property），清空必须
        置 ``None`` 而非 ``pop``——``desc_text_account`` property 直接读它们
        （无类级默认），pop 后再访问即 ``AttributeError``（任何 tag 写覆盖
        （cost/attack/… 共 12 键）+ desc 渲染必炸；产品端口覆盖冒烟实测）。
        置 None = property 的「重建」前置态（``_desc_account is None`` 分支），
        失效语义与 docstring 一致。"""
        d = self.__dict__
        for name in _CARD_TAG_DERIVED:
            d.pop(name, None)
        d["_desc_account"] = None
        d["_desc_text_source"] = None

    @cached_property
    def dbf_id(self) -> int:
        """数字 id 正典称呼（record["m_ID"]；归一同 id 异名：CARD_SET_TIMING/CARD_TAG 的
        m_cardId、CSV 列 dbf_id、gate 报告 id——全仓既有词汇，Card 对齐零翻译层）。"""
        return int(self.record["m_ID"])

    @cached_property
    def text_builder_type(self) -> int:
        """有效 CardTextBuilder 型（desc 文本源路由键；EntityDef.cs:EntityDef.GetCardTextBuilder
        派发镜像）：tag 782 OVERRIDECARDTEXTBUILDER 有值（HasTag=GetTag>0，EntityBase.cs:
        EntityBase.HasTag）则覆盖，否则 dbf CARD.m_cardTextBuilderType。text_shim 以它选
        「Python 静态实现 / pythonnet 直调」路由（消费点=eidolon/core/infra/text_shim.py）。"""
        override = self.tags[GameTag.OVERRIDECARDTEXTBUILDER]
        if override > 0:
            return int(override)
        return int(self.record.get("m_cardTextBuilderType") or 0)

    @property
    def text_overridden(self) -> bool:
        """desc 文本覆盖判定（contract C 判据 4，2026-11-06）：`.text` 与构造记录原文
        （record["m_textInHand"]）不一致 → desc 生成改读 Card.text。引擎对位=
        GetCardRecordTextInHand 的「记录文本」换成了改写值，CardTextBuilder 管线
        （变体切分/占位替换/TransformCardText）语义照常
        （CardTextBuilder.cs:CardTextBuilder.GetRawCardTextInHand）。
        property 非 cached_property——必须随 .text 实时变化，禁缓存。"""
        return (self.text or "") != (self.record.get("m_textInHand") or "")

    @cached_property
    def watermark_ref(self) -> str | None:
        """**考虑过覆盖的水印 ref 裁决**（UpdateWatermark 离线复刻，Actor.cs:Actor.UpdateWatermark）
        → 纹理 ref（"名.ext:GUID"）或 None=无水印。水印唯一门面项——卡级 override
        原始字段是裁决输入明细不单独暴露（record 全字段/dbf.watermark_override
        表可查）。

        四级：卡级 override（EntityDef.cs:EntityDef.GetWatermarkTextureOverride，迷你集族；与 set 活跃性无关）
        → 活跃 set 纹理（set_id=card_set_offline 离线 GetCardSet 正典；CARD_SET 行
        m_cardWatermarkTexture）→ core set **无条件**年标（EntityBase.cs:EntityBase.IsCoreCard；
        ref=DLL 反射直取 SetRotationIcon.CORE_SET_WATERMARK_EVEN，冻结参照裁决=偶数轮，
        78325 圣甲虫实测）→ None。HIDE_WATERMARK（tag 1107）闸在消费侧 alpha 层
        （Actor.cs:Actor.UpdateWatermark）不在此；actor 级 override 手牌默认 INVALID 不涉
        （Actor.cs:Actor.SetWatermarkCardSetOverride）。
        [语义转写自上游 watermark-chain 三级门验收；数据源 dbf 直读]"""
        from eidolon.core.infra.dbf import default_dbf
        from eidolon.core.infra.dll_reflect import tables

        dbf = default_dbf()
        text = dbf.watermark_override.get(self.dbf_id) or ""
        sid = self.set_id
        row = dbf.card_set_dict.get(sid) if sid is not None else None
        if not text:
            text = (row or {}).get("m_cardWatermarkTexture") or ""
        if row and row.get("m_isCoreCardSet"):
            text = tables.year_icon_even
        return text or None

    @classmethod
    def from_dbf(cls, dbf_id: int, dbf=None) -> "Card":
        """权威构造：dbf.unity3d 直提。dbf 可注入共享实例（批量构造免重复装载
        bundle；测试/worker/显式入口用——§6.2 迁移表）。"""
        from eidolon.core.infra.dbf import default_dbf
        dbf = dbf or default_dbf()
        dbf_id = int(dbf_id)
        return cls(dbf.card[dbf_id], dbf.card_tag.get(str(dbf_id), {}),
                   set_id=dbf.card_set_offline.get(dbf_id))

    # ---- 裸 tag（渲染链现消费；注释=GAME_TAG id+首次定案处）----
    @cached_property
    def cost(self) -> int:
        return self.tags[GameTag.COST]

    @cached_property
    def premium(self) -> "Premium":
        return _dec(Premium, self.tags[GameTag.PREMIUM])

    @cached_property
    def cardtype(self) -> "CardType":
        return _dec(CardType, self.tags[GameTag.CARDTYPE])

    @cached_property
    def rarity(self) -> "Rarity":
        return _dec(Rarity, self.tags[GameTag.RARITY])      # 0=INVALID=gemless

    @cached_property
    def elite(self) -> int:
        return self.tags[GameTag.ELITE]

    @cached_property
    def spell_school(self) -> "SpellSchool":
        return _dec(SpellSchool, self.tags[GameTag.SPELL_SCHOOL])

    @cached_property
    def tradeable(self) -> int:
        return self.tags[GameTag.TRADEABLE]

    @cached_property
    def forgeable(self) -> int:
        return self.tags[GameTag.FORGE]

    @cached_property
    def prepareable(self) -> int:
        return self.tags[GameTag.PREPARE]

    @cached_property
    def rune_blood(self) -> int:
        return self.tags[GameTag.COST_BLOOD]

    @cached_property
    def rune_frost(self) -> int:
        return self.tags[GameTag.COST_FROST]

    @cached_property
    def rune_unholy(self) -> int:
        return self.tags[GameTag.COST_UNHOLY]

    @cached_property
    def tech_level(self) -> int:
        return self.tags[GameTag.TECH_LEVEL]

    @cached_property
    def timewarped(self) -> int:
        """BACON_TIMEWARPED(4503)：时空扭曲变体（GAME_TAG.cs:GAME_TAG.BACON_TIMEWARPED）。引擎消费=
        Actor.GetTechLevelSpellType（Actor.cs:Actor.GetTechLevelSpellType）——>0 时酒馆星级盾徽 Spell
        二选一改走 TIME_TAVERN_TIER_ICON(308) 变体件（否则 TECH_LEVEL_MANA_GEM(156)）；
        ally/spell 两链统一入口（ShowTavernTierSpell :7581-7598）。金币件不分岔
        （UseCoinManaGem :6839-6842 无 4503 项，timewarped-frame 诊断 §2 定案）。"""
        return self.tags[GameTag.BACON_TIMEWARPED]

    # ---- 统计值读取与显示谓词（Update*TextMesh 判定链；2026-10-21 gametag-card-merge
    #      收口批入册——render 模块 GameTag 字面量并轨本面）----
    @cached_property
    def attack(self) -> int:
        """GetTag(TAG_ATK)(47) 纯镜像（引擎从不在数据层改写数值，cost 属性同款）。
        引擎消费=UpdateAttackTextMesh :3454 `m_attackTextOverride ?? entityDef.GetTag(GAME_TAG.ATK)`
        （Actor.cs:Actor.UpdateAttackTextMesh）。"""
        return self.tags[GameTag.ATK]

    @cached_property
    def health(self) -> int:
        """GetTag(TAG_HEALTH)(45) 纯镜像。引擎消费=UpdateHealthTextMesh :3519（Actor.cs:Actor.
        UpdateHealthTextMesh）；武器耐久/地标耐久同源（GetAttackOrHealthStringAndDoLargeNumberFormatting）。"""
        return self.tags[GameTag.HEALTH]

    @cached_property
    def armor(self) -> int:
        """GetTag(TAG_ARMOR)(292) 纯镜像。引擎消费=UpdateArmorTextMesh :3531（Actor.cs:Actor.
        UpdateArmorTextMesh）：armor==0 ∨ HasHideStats → m_armorObject 隐。"""
        return self.tags[GameTag.ARMOR]

    @cached_property
    def card_set(self) -> int:
        """GetTag(TAG_CARD_SET)(183) **raw 镜像**——非 GetCardSet 正典（=set_id：EntityBase.cs:
        EntityBase.GetCardSet :1361 tag 优先+CARD_SET_TIMING 活跃回退）。消费点=稀有宝石 MISSIONS
        抑制的转写输入（Actor.cs:Actor.GetRarityTextureOffset :5055 吃 entityDef.GetCardSet()；
        本仓 gems.plan_rarity_gem 既有决策吃 raw tag=转写保真口径，timing 回退差异不在本批合并）。"""
        return self.tags[GameTag.CARD_SET]

    @cached_property
    def has_hide_stats(self) -> bool:
        """Actor.HasHideStats 对位（Actor.cs:Actor.HasHideStats :1208-1219）：HIDE_STATS(402)>0 ∨
        IsDormant（DORMANT(1518)>0，EntityBase.cs:EntityBase.IsDormant :384-387=HasTag）。
        费用/攻/血/护甲显示抑制共用的总闸（UpdateCost/Attack/Health/ArmorTextMesh 四处同调；
        m_ignoreHideStats=actor 级旗，离线静态卡面缺省 false 不入）。"""
        return int(self.tags[GameTag.HIDE_STATS]) > 0 or int(self.tags[GameTag.DORMANT]) > 0

    @cached_property
    def has_trigger_visual(self) -> bool:
        """TRIGGER_VISUAL(32)>0（EntityBase.cs:EntityBase.HasTriggerVisual 逐字=HasTag(TRIGGER_VISUAL)）。
        引擎消费=费用文本 CardButton 腿（Actor.cs:Actor.UpdateCostTextMesh EntityDef 版）：
        IsCardButton ∧ HasTriggerVisual ∧（非 BG ∨ !HAS_ACTIVATE_POWER）→ m_costTextMesh.Text=""，
        **只清数字、水晶不动**（显隐判定单源=render.game.actor.gems.cost_text_semantics）。"""
        return int(self.tags[GameTag.TRIGGER_VISUAL]) > 0

    @cached_property
    def has_activate_power(self) -> bool:
        """HAS_ACTIVATE_POWER(2840)>0（HasTag=GetTag>0，EntityBase.cs:EntityBase.HasTag）。
        消费点=Bacon 语境下 CardButton 费用显隐的例外腿（Actor.cs:Actor.UpdateCostTextMesh：
        BG 里带主动技能的按钮仍显示费用数字）。"""
        return int(self.tags[GameTag.HAS_ACTIVATE_POWER]) > 0

    @cached_property
    def is_card_button(self) -> bool:
        """EntityBase.IsCardButton 对位（EntityBase.cs:EntityBase.IsCardButton）：HERO_POWER(10)/
        LOCATION(39)/GAME_MODE_BUTTON(12)/LETTUCE_ABILITY(23) 四型恒真；第五腿
        IsCoinBasedHeroBuddy 吃对局态 game entity tag（EntityBase.cs:EntityBase.IsCoinBasedHeroBuddy
        ——BACON_USE_COIN_BASED_BUDDY_METER），离线静态卡面不可判，缺省不入（与引擎「非四型且
        非金币伙伴→false」同值）。消费点=费用文本 CardButton 腿。"""
        return int(self.cardtype) in (int(CardType.HERO_POWER), int(CardType.LOCATION),
                                      int(CardType.GAME_MODE_BUTTON),
                                      int(CardType.LETTUCE_ABILITY))

    @cached_property
    def attack_display_hidden(self) -> bool:
        """攻显示抑制（Actor.cs:Actor.UpdateAttackTextMesh :3435）：HasHideStats ∨
        HasTag(HIDE_ATTACK)(683) → 文本空 + GemObject.Hide()（宝石与数字一起没）。"""
        return self.has_hide_stats or int(self.tags[GameTag.HIDE_ATTACK]) > 0

    @cached_property
    def health_display_hidden(self) -> bool:
        """血显示抑制（Actor.cs:Actor.UpdateHealthTextMesh :3496）：HasHideStats ∨
        HasTag(HIDE_HEALTH)(682) → 文本空 + GemObject.Hide()。英雄腿（IsHero ∧
        m_healthDisplayRequiresHeroCard ∧ m_card==null）=对局态条件，离线静态卡面恒不触发，不入。"""
        return self.has_hide_stats or int(self.tags[GameTag.HIDE_HEALTH]) > 0

    @cached_property
    def attack_number_hidden(self) -> bool:
        """攻数字空文本（Actor.cs:Actor.UpdateAttackTextMesh :3470/:3476）：HasTag(
        HIDE_ATTACK_NUMBER)(3472) → Convert.ToString 分支跳过——数字没、宝石留（Show 支路已过）。"""
        return int(self.tags[GameTag.HIDE_ATTACK_NUMBER]) > 0

    @cached_property
    def health_number_hidden(self) -> bool:
        """血数字空文本（Actor.cs:Actor.UpdateHealthTextMesh :3514）：HasTag(
        HIDE_HEALTH_NUMBER)(3471) → Text=string.Empty——数字没、宝石留。"""
        return int(self.tags[GameTag.HIDE_HEALTH_NUMBER]) > 0

    @cached_property
    def watermark_hidden(self) -> bool:
        """HIDE_WATERMARK(1107)>0（HasTag 语义=GetTag>0，EntityBase.cs:EntityBase.HasTag）。
        引擎消费=UpdateWatermark alpha 闸（Actor.cs:Actor.UpdateWatermark :5162）→ 0。
        与 watermark_ref 解耦（引擎同构：text 四级裁决与 alpha 闸两条独立语句——ref 照常解析，
        闸只压 alpha）。"""
        return int(self.tags[GameTag.HIDE_WATERMARK]) > 0

    @cached_property
    def is_bacon_hero(self) -> bool:
        """酒馆可选英雄（play 形态帧族 hero_play_bacon 判据；上游换轨
        CARD_HERO 表查）。

        引擎正典判据 = CARD_HERO 表 HeroType==3（BATTLEGROUNDS_HERO；GameUtils.cs:GameUtils
        → ActorNames.cs:ActorNames.GetPlayActorByTags → Card_Play_Bacon_Hero）——**DBF 列非 GAME_TAG**。本属性
        即表查（dbf.card_hero，default_dbf 进程单例+惰性 import 防环）。原 tag 1491
        （BACON_HERO_CAN_BE_DRAFTED）过渡代理退役：换轨后自动归位 Bacon 帧；
        GUIDE（heroType==4）→
        Card_Play_Bacon_Guide 异 prefab，**仍不入本判据，另案**。"""
        from eidolon.core.infra import dbf   # 惰性：防 import 环（dbf 不依赖本模块，稳起见仍后置）
        return dbf.default_dbf().card_hero.get(self.dbf_id, {}).get("m_heroType") == 3

    # ---- 衍生语义（compile 层散落解释逻辑的收拢预备）----
    @cached_property
    def classes(self) -> tuple:
        """引擎 GetClasses() 语义（EntityBase.cs:EntityBase.GetClasses：bit i → TAG_CLASS i+1；
        Actor.cs:Actor.UpdateMulticlassRibbon 缎带判据即调它）：476 位掩码**逐位扫**解码
        （int(mask) 自低位向高位，bit i → 值 i+1），否则 (199, 0→INVALID)。全无=(INVALID,)。
        未知位（值超出 CardClass 镜像）_dec 降级裸 int **忠实入列**——上游收口：
        旧 ClassMask(mask) IntFlag 迭代只出已命名位、未知位静默丢，退役；消费端
        （get_color_type_for_class 等）对未知值必抛，不在本层编造缺省。
        199/476 裸值不另设属性（防绕过 GetClasses 语义；真需裸值走 tags[GameTag.MULTIPLE_CLASSES]）。
        消费对照：composite=(c_low,c_high) 升序即分割序/缎带=len/类色选图集=[0]。"""
        mask = int(self.tags[GameTag.MULTIPLE_CLASSES])
        if mask:
            out = []
            while mask:
                low = mask & -mask
                out.append(_dec(CardClass, low.bit_length()))
                mask ^= low
            return tuple(out)
        return (_dec(CardClass, self.tags[GameTag.CLASS]),)   # 0=INVALID（引擎 GetTag 缺省；
                                                            # 类色 INVALID→TYPE_GENERIC，
                                                            # Switcher.cs:CardColorSwitcher.GetColorTypeForClass）

    @cached_property
    def is_dualclass(self) -> bool:
        """恰 2 类=分裂双图集帧（Actor.cs:Actor.SetMaterialWithTexture，dualclass 分裂帧判据）。"""
        return len(self.classes) == 2

    @cached_property
    def is_multiclass(self) -> bool:
        """MULTIPLE_CLASSES 本义：至少 2 类（2 类的分裂帧特例=is_dualclass）。"""
        return len(self.classes) >= 2

    @cached_property
    def has_three_or_more_classes(self) -> bool:
        """至少 3 类（引擎原文 GetClasses().Count > 2，Actor.cs:Actor.UpdateMulticlassRibbon）。3+ 类的
        语义面（非单一 UI 件）：右缘缎带（Actor.cs:Actor.UpdateMulticlassRibbon）、GENERIC 帧选择
        （dual-class-color-adjudication 定案 ≥3→GENERIC）等消费方的共同条件。"""
        return len(self.classes) >= 3

    @cached_property
    def banners(self) -> tuple["BannerKind", ...]:
        """tag 驱动的 banner 挂件家族（Actor.cs:Actor.UpdateCardColor 同 pass 四容器：派系旗+三徽章）。
        机制差异：派系旗独立共存（prefab 带 SetFactionType 槽位，槽位见 faction）；三徽章
        DeckActionBanner 赋值互斥（序 tradeable>forge>prepare，容器 SetActive 可并存）。"""
        out = []
        for kind in BannerKind:
            if self.tags[int(kind)] > 0:
                out.append(kind)
        return tuple(out)

    @cached_property
    def has_runes(self) -> bool:
        """CombinedValue>0 → rune banner（CardRuneBanner.cs:CardRuneBanner.Show）。"""
        return (self.rune_blood + self.rune_frost + self.rune_unholy) > 0

    @cached_property
    def races(self) -> tuple[int, ...]:
        """引擎 GetRaces（EntityBase.cs:1233-1239）逐字转写：IsBattlegroundTrinket
        （CARDTYPE==44，:643-645）→ GetRacesForTrinket，否则 GetRacesForNonTrinket。

        trinket 分支（GetRacesForTrinket :1146-1165 逐字）：s_raceSubsetToRaceTable
        （:25-79，BACON_SUBSET_*
        布尔 tag→TAG_RACE，活反射 `_trinket_subset_to_race`）逐对 HasTag 判定；
        BACON_SUBSET_ALL 命中=Clear+Add(ALL)+break（:1154-1159）；>1 时 SortRaceList
        固定序（与常规路同表 _sort_race_order）。

        常规路（GetRacesForNonTrinket :1177-1200）：
        - 主种族=tag 200（CARDRACE）值非 0 即入列；
        - CARDRACE=26(ALL) 早退（:1183-1186，不再扫附加种族）；
        - 附加种族=CARD_RACE 表逐记录 `HasTag(record.IsRaceTag)` 为真则 Add(record.ID)
          （:1187-1193；HasTag=GetTag>0，EntityBase.cs:EntityBase.HasTag；is_race_tag=0 行恒假自然
          跳过——CARD_RACE 直读经 dbf.card_race，数值语义由表承载非 GAME_TAG.cs
          名册，keyword-race-tags B2 定案）；
        - Distinct（保首现）+ >1 时按 SortRaceList 固定序（:1202-1230；序表见
          _sort_race_order，排序键 Array.IndexOf 语义=序外种族 -1 排最前）。

        消费对照：双种族宽板判式=len>1（UpdateRace Actor.cs:Actor.UpdateRace GetRaceCount）；
        种族文本=GetRaceText→BuildRaceText 按本序 "\\n" 连接（trinket 亦入 GetRaceText
        的 IsBattlegroundTrinket 支，EntityBase.cs:1264）。"""
        if self.cardtype == CardType.BATTLEGROUND_TRINKET:      # :1234-1237
            out: list[int] = []
            for tag_id, race_id in _trinket_subset_to_race():
                if self.tags[tag_id] > 0:                       # HasTag（GetTag>0）
                    if tag_id == int(GameTag.BACON_SUBSET_ALL):  # :1154-1159
                        out.clear()
                        out.append(race_id)
                        break
                    out.append(race_id)                         # :1161-1163
            if len(out) > 1:
                order = _sort_race_order()
                out.sort(key=lambda r: order.index(r) if r in order else -1)
            return tuple(out)
        primary = self.tags[GameTag.CARDRACE]
        if primary == 26:
            return (26,)
        races: list[int] = []
        if primary:
            races.append(primary)
        from eidolon.core.infra import dbf
        for race_id, is_race_tag in dbf.default_dbf().card_race.items():
            if not is_race_tag:
                continue
            if race_id in races:
                continue
            if self.tags[is_race_tag] > 0:
                races.append(race_id)
        if len(races) > 1:
            order = _sort_race_order()
            races.sort(key=lambda r: order.index(r) if r in order else -1)
        return tuple(races)

    @cached_property
    def is_dualrace(self) -> bool:
        """GetRaceCount()>1（EntityBase.cs:EntityBase.GetRaceCount = GetRaces().Count）——双种族宽板
        判式正典（UpdateRace Actor.cs:Actor.UpdateRace multi 板 SetActive 门；禁按 id/名猜）。"""
        return len(self.races) > 1

    @cached_property
    def faction(self) -> "Faction | None":
        """VALID_FACTIONS 序首个在场者（Actor.cs:Actor；无则 None）——返回 banner 槽位
        值（Faction 成员 int，SetFactionType 真值域），prefab 注入消费即槽位号。
        （上游起返回裸 int==Faction 成员值——Faction 已
        活镜像化，int(fac) 等值。）"""
        for tid, fac in FACTION_TAG_IDS:
            if self.tags[tid] > 0:
                return fac
        return None

    def __repr__(self) -> str:
        return (f"Card({self.card_id or self.name!r} dbf-tagged "
                f"{_name(self.cardtype)}/{_name(self.rarity)}/{_name(self.premium)})")


_CARD_TAG_DERIVED = frozenset(name for name, v in list(vars(Card).items())
                              if isinstance(v, cached_property))
"""Card 上的 cached_property 名集（tags 派生缓存：cost/classes/races/banners/...
全量；_invalidate_tag_derived 消费）。新加 cached_property 自动入列——失效面与
注册面同源，禁另抄第二份名单。"""


def as_card_or_dbf(card_or_dbf) -> tuple["Card | None", "int | object"]:
    """渲染入口归一（contract C 判据 1，2026-11-06：四入口收 Card）：
    Card 实例 → (card, int(card.dbf_id))（canonical 数字轴）；其余原样 →
    (None, 原值)（dbf 旧路径零变化，内部装载点照旧单点 from_dbf）。
    渲染链传 Card 时整链零 from_dbf（判据 2）——本函数只分流，不装载。"""
    if isinstance(card_or_dbf, Card):
        return card_or_dbf, int(card_or_dbf.dbf_id)
    return None, card_or_dbf


# ---- BG 语义常量（帧编译/计划层共用；2026-10-09 自 ur_frames 上收 infra 单源）----
BG_SPELL_CARDTYPE = int(CardType.BATTLEGROUND_SPELL)   # 42（TAG_CARDTYPE.cs:TAG_CARDTYPE.BATTLEGROUND_SPELL）
BG_MINION_CARDTYPE = int(CardType.MINION)               # 4


# ============================================================================
# 文本真值与显示谓词门面（2026-10-09 L5：Card 唯一消费面收口）
# ============================================================================

def _desc_text_account(self) -> dict:
    """desc 成品文本 + 出处账（text/builder/builder_type/route/degraded/source）。

    懒初始化 CLR（pythonnet + Assembly-CSharp 装载=秒级重活，仅首次 desc 访问支付；
    只查 cost/classes 等元数据访问器的消费者永不付税）。失败语义=text_shim 原样：
    未路由 builder 型失败一律 loud raise（「需补 Python 路由」），无静默 fallback；
    40/45 走 Python 静态路由（route="py"，不构造游戏 builder）。
    DLL 真值边界：以卡牌静态数据为输入的 CardTextBuilder 家族真值（合成实体无对局态），
    非任意对局态真值——语料对拍语义以此为前提（参照=静态卡面截图）。
    覆盖轴（contract C 判据 4，2026-11-06）：账按 `_desc_text_source`（构建时的
    Card.text 快照）检测——.text 被改写后再次访问自动重建（desc 生成改读 Card.text，
    text_shim._raw_card_text/_build_text_override 执行）。"""
    cur_text = self.text or ""
    if self._desc_account is None or self._desc_text_source != cur_text:
        from eidolon.core.infra.text_shim import desc_text_for
        text, info = desc_text_for(self)
        self._desc_account = {**info, "text": text}
        self._desc_text_source = cur_text
    return self._desc_account


def _desc_text(self) -> str:
    """desc 成品字符串（CardTextBuilder 加工终值；占位符 $/#/@/{n} 已替换）。
    像素化不在此层——UberText 排字住渲染链 frames/uber_text。"""
    return _desc_text_account(self)["text"]


def _cost_hidden(self) -> bool:
    """费用显示抑制（数据腿）：HIDE_STATS→HIDE_COST→DORMANT 判定链
    （Actor.cs:Actor.UpdateCostTextMesh + EntityBase.cs:EntityBase.GetRaces/:1222-1226）。
    cost 属性保持纯 GetTag 镜像（引擎从不在数据层改写数值）——本谓词是显示判定。
    语境腿（TL/bacon，吃渲染 mode）住渲染 plan 层。"""
    return _cost_hidden_reason(self) is not None


def _cost_hidden_reason(self) -> str | None:
    if int(self.tags[GameTag.HIDE_STATS]) > 0:
        return "HIDE_STATS(402)>0（HasHideStats，Actor.cs:Actor.UpdateCostTextMesh+EntityBase.cs:EntityBase.GetRaces）"
    if int(self.tags[GameTag.HIDE_COST]) > 0:
        return "HIDE_COST(684)>0（Actor.cs:Actor.UpdateCostTextMesh）"
    if int(self.tags[GameTag.DORMANT]) > 0:
        return "DORMANT(1518)>0（HasHideStats=IsDormant 支路，EntityBase.cs:EntityBase.GetRaces）"
    return None


Card.desc_text_account = property(_desc_text_account)
Card.desc_text = property(_desc_text)
Card.cost_hidden = property(_cost_hidden)
Card.cost_hidden_reason = property(_cost_hidden_reason)
