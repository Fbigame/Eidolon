"""frames.btf — Spell prefab 双件+CARD_RACE 表（Batch C 末件）。

对照表（旧位 → 本域，预审 2026-10-10）：
  - BTF_SPELLS 八件 ← SpellTable 链解（2026-10-10：m_spellTablePrefab→m_Table
    [m_Type].m_SpellPrefabName 完整 ref 运行时实证，零字面量；spell_type 账=表槽位锚
    随件）。唯一例外行=cost_alt_tavern_coin_*：既有 `spell_type`（表查键=305，数据登记
    槽）又有 `engine_spell_type`（303=SpellType.COST_ALT_TAVERN_COIN，引擎实际问的槽）
    ——两代编号混用的显式入账（见该二行注）。
  - walk ← btf_extract_assets 逐字：**根平移保留** [btf:292 LoadSpell 语义]（与 badges/
    ornaments 的根平移置零是两个有意的不同语义）；npz 键 {spell_key}|{rel}（mesh+渲染器
    俱在且非排除名才入）；材质按名全仓去重进 report["materials"]（shader deref 不可得
    回落 .badges 懒索引；blend=multiply 判定 [_btf_blend_mode 同式]）。
  - _MainTex ST 账 [timewarped-tier-icon 2026-10-07 逐字]：序列化字段名=m_Scale/m_Offset
    （无 m_ST 键——首探读错键误判「无 ST」致 Timewarp 盾皮 v 偏移丢失实录）；消费方
    注入期烘焙 uv0。
  - 纹理裸名（消费方拼 textures/ 前缀）；report 树内 _arrays 以 ndarray 字符串化形态
    随 json（既档实证同形态——对拍双侧同走 default=str 逐字可比）。
  - CARD_RACE ← dbf（infra，原 dbf_metadata 改名）直提链 [btf:384-394 同式]。
  - 共享件引用：trs_matrix/_mesh_arrays/_shader_bundle_typetree ← .badges、
    _shader_pass_states ← .ornaments、_sanitize ← .ability（同源单副本）。
产物=BtfKit（spell_prefabs_report+spell_meshes.npz+textures/+card_race_dbf 真内存）。
对拍=duipai_frames.py check_btf（report 逐字段+npz 逐键逐位+textures 像素逐位+race 表
逐行）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from eidolon.core.infra.resolve_asset_ref import Resolver
from eidolon.core.supply._projection import as_pairs, as_rgba
from eidolon.core.supply.frames.ability import _sanitize
from eidolon.core.supply.frames.badges import _mesh_arrays, _shader_bundle_typetree, trs_matrix
from eidolon.core.supply.frames.engine import ptr_dict
from eidolon.core.supply.frames.ornaments import _shader_pass_states
from eidolon.core.supply.machine import core, item

logger = logging.getLogger(__name__)

BTF_SPELLS = {
    # ref 链化（2026-10-10 audit §2 升级账）：四 ref 自 SpellTable 链解——
    # Actor.m_spellTablePrefab（schema 字段，Actor.cs:Actor）→ 共享表 prefab →
    # SpellTable.m_Table[m_Type].m_SpellPrefabName（完整 name:guid 形态，运行时探针
    # 实证；AssignSpells 共享表路径=Actor.cs:Actor.AssignSpells GetComponentInChildren 落空分支；
    # SpellTableEntry.cs m_SpellPrefabName）。链解值与旧四字面量逐字符同源（对拍 report
    # ref 字段双证）；tech_level/timewarped=ally 表、coin×2=ability 表（按消费 actor
    # 类型路由，重叠行两表同值互证）。
    "tech_level_mana_gem": {"slot": "HAND_MINION", "spell_type": 156},
    # Timewarped 盾徽变体件（SpellTable 槽 308）：GetTechLevelSpellType（Actor.cs:Actor.GetTechLevelSpellType）
    # BACON_TIMEWARPED(4503)>0 分岔目标——同 mesh 同 UV 纯换皮（timewarped-frame 诊断 §3
    # 骨架逐位一致账），新纹理仅 Bacon_AllTierGuide_TimewarpTavernTier 1 张。
    "timewarped_tier_icon": {"slot": "HAND_MINION", "spell_type": 308},
    "coin_mana_gem_bacon_spell": {"slot": "HAND_SPELL", "spell_type": 267},
    # 标准金币件（SpellTable 槽 145，仅 Card_Hand_Ability 表有此槽；btf_probe_spelltables
    # 实测映射，tl0-coin-face 2026-10-07）：TL0 法术金币面。采集链 CreateActor bgs 分支
    # `(IsSpell() && !flag2)` leg（AlphaTool.Renderer.cs:AlphaTool.CreateActor GetSpell(SpellType.
    # COIN_MANA_GEM).ActivateState(BIRTH)；SpellType.COIN_MANA_GEM=145 前任 SPELLTYPE 表
    # 钉死）；引擎同区 BigCard.cs:BigCard.ActivateBigCardStateSpells num==0 leg。与 267 变体（根 z−0.643 下移，
    # bacon-tier-frame findings §4）不同，145=标准位。TL>0 法术不出此件（采集链 !flag2
    # 显式排除；65248 参照=盾徽无金币实证）。
    "coin_mana_gem": {"slot": "HAND_SPELL", "spell_type": 145},
    # BG 英雄能力金币件（SpellTable 槽 145，History_HeroPower 表专用行；
    # bacon-hero-power-frames 2026-10-07 hp_table_probe 全表 dump）：TL0-coin-face 的
    # ability 表 145 件外推勘误件——英雄能力 actor（HISTORY_HERO_POWER）的
    # m_spellTablePrefab 指向 History_HeroPower_SpellTable（8 槽），槽 145 →
    # History_HeroPower_CoinManaGem 专用 prefab（b0d925c1…；mesh/材质与 ability 145
    # 件同 pid，仅变换不同）。消费=compile_tier_spell want_coin_hp 腿（mode=bacon ∧
    # CARDTYPE 10，采集链 AlphaTool.Renderer.cs:190-201 IsHeroPower leg）。
    "coin_mana_gem_hero_power": {"slot": "HISTORY_HERO_POWER", "spell_type": 145},
    # 饰品金币件（SpellTable 槽 145，Card_Hand_BG_Trinket 表专用行；bg-ct40-43-44-routing
    # 2026-10-24 链解实证：BIG_CARD_BG_TRINKET 的 m_spellTablePrefab=
    # Card_Hand_BG_Trinket_SpellTable，槽 145 → Card_Hand_Ability_CoinManaGem 1
    # （b3464067…，带空格重定位变体——与 ability 145 件 b 同 pid 异变换，探针实测）。
    # 消费=compile_tier_spell want_coin_trinket 腿（mode=bacon ∧ CARDTYPE 44，
    # 采集链 AlphaTool.Renderer.cs:191-201 IsBattlegroundTrinket leg：
    # HideCoinManaGem→GetSpell(COIN_MANA_GEM).ActivateState(BIRTH)）。
    "coin_mana_gem_trinket": {"slot": "BIG_CARD_BG_TRINKET", "spell_type": 145},
    # 费用底座件（timewarped 替换金币件）：引擎侧槽位=SpellType.COST_ALT_TAVERN_COIN
    # （Blizzard.T5.Game/SpellType.cs = 303，Actor.GetSpellTypeFromAlternateCostType
    # ALT_TAVERN_COIN 腿 → ActivateAlternateCost），**但 37.0 手牌 SpellTable 把它登记在
    # 旧槽 305（=AZURE_ARCANE_SPELL_BUFF 当前枚举值）**——两代 SpellType 编号混用（盘面表
    # 303 正常、手牌两表 303 皆空，2026-10-31 probe_altcoin_tables 实测：
    # HAND_MINION/HAND_SPELL 均有 305 无 303）。表查键因此=305（拿得到 ref 的唯一槽），
    # 而报告里 engine_spell_type 记 303（引擎实际问的槽）——两者同时入账，禁把 305 当
    # 「引擎语义」（消费方 compile_tier_spell 只按 303 的引擎语义挂载）。
    # 素材=底座 Spell prefab（Gem_Coin=Timewarp_Chronum_mesh×Timewarp_Chronum；星芒
    # Coin_Burst/Coin_Persistant 是 Animator 驱动 quad，序列化局部 TRS 全零 → 无数组、
    # 不渲，rest pose 只有 Gem_Coin 一块盘）；手牌 Ally/Ability 两件（随从帧/法术帧）。
    # **树/材质名绑定面**（supply.frames.injectors.btf_tree_mem 的字面 ref 四件）不随之扩
    # ——该表按纪律只收既有双源同值行（新增件写字面 ref = 写死 ref 违例）；本二件消费方
    # `_btf_assets` 取官方树的 material_slots 面（btf 走查已产同形键），渲染链实测可用
    "cost_alt_tavern_coin_ally": {"slot": "HAND_MINION", "spell_type": 305,
                                  "engine_spell_type": 303},
    "cost_alt_tavern_coin_ability": {"slot": "HAND_SPELL", "spell_type": 305,
                                     "engine_spell_type": 303},
}
BTF_EXCLUDE_RULES = {"FX_Plasma", "Gem_Burst", "Health_Burst"}


@dataclass
class BtfKit:
    """btf 产物真内存对象（旧 btf OUT 四布局位内存面）。"""
    report: dict = field(default_factory=dict)    # spell_prefabs_report.json 内容面
    arrays: dict = field(default_factory=dict)    # spell_meshes.npz 内容面
    textures: dict = field(default_factory=dict)  # textures/ {裸文件名: PIL}
    card_race: dict = field(default_factory=dict)  # card_race_dbf.json 内容面


def _btf_blend_mode(passes: list) -> dict | None:
    """[btf:142-157 同式]"""
    for p in passes or []:
        if p.get("srcBlend") == 2.0 and p.get("destBlend") == 0.0:
            return {"mode": "multiply", "override": {"blend": "multiply"}}
    return None


def _spell_refs() -> dict[str, str]:
    """spell prefab ref 链解（见 BTF_SPELLS 注）→ {spell_key: ref}。
    识别谓词=schema 键（Actor 组件 m_cardMesh/m_portraitMesh presence + m_spellTablePrefab
    字段；SpellTable 组件 m_Table presence）——零名字/零 guid 字面量。
    查表键恒取 meta["spell_type"]（表登记槽；cost_alt_tavern_coin_* 的 305 是数据登记槽，
    引擎问的 303 另记 engine_spell_type，**不参与查表**——手牌表 303 为空，查 303 即 KeyError）。"""
    from eidolon.core.infra.dll_reflect import tables

    r = core().res
    out: dict[str, str] = {}
    table_cache: dict[str, dict[int, str]] = {}
    for spell_key, meta in BTF_SPELLS.items():
        slot = meta["slot"]
        if slot not in table_cache:
            actor_ref = tables.actor_slots[slot]
            res = r.resolve(actor_ref)
            assert res["ok"], (slot, res.get("checks"))
            b = res["resolved"]["bundle"]
            root, _ = r.container_get(b, res["resolved"]["guid"])
            tref = None
            for pair in root.read_typetree().get("m_Component", []):
                cobj, _cb = r.resolve_pptr(b, ptr_dict(pair["component"]), root)
                if cobj.type.name != "MonoBehaviour":
                    continue
                mt = cobj.read_typetree()
                if ("m_cardMesh" in mt or "m_portraitMesh" in mt) and mt.get("m_spellTablePrefab"):
                    tref = mt["m_spellTablePrefab"]
                    break
            assert tref, f"{slot}: Actor.m_spellTablePrefab 缺席"
            tres = r.resolve(tref)
            assert tres["ok"], (tref, tres.get("checks"))
            tb = tres["resolved"]["bundle"]
            troot, _2 = r.container_get(tb, tres["resolved"]["guid"])
            env = r.open_bundle(tb)
            objects = {o.path_id: o for o in env.objects}
            rows = None
            for pair in troot.read_typetree().get("m_Component", []):
                co = objects.get(ptr_dict(pair["component"]).get("m_PathID"))
                if co is None or co.type.name != "MonoBehaviour":
                    continue
                mt2 = co.read_typetree()
                if isinstance(mt2, dict) and "m_Table" in mt2:
                    rows = {row["m_Type"]: row["m_SpellPrefabName"] for row in mt2["m_Table"]}
                    break
            assert rows is not None, f"{tref}: SpellTable 组件缺席"
            table_cache[slot] = rows
        ref = table_cache[slot][meta["spell_type"]]   # 表缺行→KeyError=fail loud
        assert isinstance(ref, str) and ".prefab:" in ref, (spell_key, ref)
        out[spell_key] = ref
    return out


def _walk_spell(r: Resolver, spell_key: str, meta: dict,
                report: dict, arrays: dict, textures: dict) -> dict:
    """单 spell prefab 走查 [extract_btf spell 循环体逐字；落盘 → 内存面]。"""
    res = r.resolve(meta["ref"])
    if not res["ok"]:
        # 别名容忍（dk_extract_dk_atlas 先例形；coin_mana_gem_trinket 2026-10-24 实证）：
        # ref=SpellTable.m_SpellPrefabName 链解 verbatim（decomp 忠实数据，GUID 钉死
        # 身份），对象实名可异于文件名 stem——trinket 表 145 行文件名
        # "Card_Hand_Ability_CoinManaGem 1"（Unity 重名拷贝尾缀）vs GO 名
        # "Card_Hand_Trinket_CoinManaGem"。容忍边界=registration/type 两检须过
        # （身份锚），name-consistency 单项豁免；其余失败仍响亮。
        hard = [c for c in res["checks"] if c["check"] != "name-consistency"]
        assert all(c["pass"] in (True, None) for c in hard), \
            (spell_key, meta["ref"], res["checks"])
    bundle = res["resolved"]["bundle"]
    guid = res["resolved"]["guid"]
    root, _ = r.container_get(bundle, guid)
    env = root.assets_file.environment
    by_pid = {o.path_id: o for o in env.objects}

    def deref(ptr: dict, owner):
        if not isinstance(ptr, dict) or not ptr.get("m_PathID"):
            return None
        if ptr.get("m_FileID", 0) == 0:
            return by_pid.get(ptr["m_PathID"])
        try:
            return r.resolve_pptr(bundle, ptr, owner)[0]
        except Exception:  # noqa: BLE001
            return None

    def walk(go_obj, parent_acc: np.ndarray, rel: str):
        tt = go_obj.read_typetree()
        name = tt.get("m_Name", "")
        my_rel = f"{rel}/{name}" if rel else name
        acc = parent_acc
        node: dict = {"rel": my_rel, "name": name, "active_self": tt.get("m_IsActive"),
                      "children": []}
        excluded_here = False
        for comp in tt.get("m_Component", []):
            cpid = comp["component"]["m_PathID"]
            o = by_pid.get(cpid)
            if o is None:
                continue
            if o.type.name == "Transform":
                ttt = o.read_typetree()
                acc = parent_acc @ trs_matrix(ttt)   # 根平移保留（LoadSpell 语义）[btf:292]
                node["matrix"] = acc.tolist()
                for ch in ttt.get("m_Children", []):
                    co = deref(ch, o)
                    if co is not None and co.type.name == "Transform":
                        gpid = co.read_typetree()["m_GameObject"]["m_PathID"]
                        gobj = by_pid.get(gpid)
                        if gobj is not None:
                            node["children"].append(walk(gobj, acc, my_rel))
            elif o.type.name == "MeshFilter":
                mtt = o.read_typetree()
                mo = deref(mtt.get("m_Mesh") or {}, o)
                if mo is not None:
                    arr = _mesh_arrays(mo)
                    node["mesh"] = arr["name"]
                    node["_arrays"] = arr
            elif o.type.name in ("MeshRenderer", "SkinnedMeshRenderer"):
                rtt = o.read_typetree()
                slots = []
                for i, mp in enumerate(rtt.get("m_Materials", [])):
                    mpd = mp if isinstance(mp, dict) else {"m_FileID": mp.m_FileID,
                                                           "m_PathID": mp.m_PathID}
                    mo = deref(mpd, o)
                    if mo is None:
                        continue
                    mtt = mo.read_typetree()
                    mname = mtt.get("m_Name")
                    slots.append({"slot": i, "material": mname})
                    if mname in report["materials"]:
                        continue
                    sh = mtt.get("m_Shader") or {}
                    stt = None
                    sob = deref(sh, mo)
                    if sob is not None:
                        try:
                            stt = sob.read_typetree()
                        except Exception:  # noqa: BLE001
                            stt = None
                    if not stt or not (stt.get("m_ParsedForm") or {}).get("m_SubShaders"):
                        stt = _shader_bundle_typetree(sh.get("m_PathID", 0))
                    sname, passes = ("?", [])
                    if stt:
                        sname, passes = _shader_pass_states(stt)
                    # shader pid（2026-11-01 zbuf-blindspots ②）：材质 m_Shader 引用的
                    # 序列化 path_id（deref 命中与回落 bundle 扫描同键）——引用事实，
                    # 与 shader 体可读与否无关（不可得时 shader 名仍 "?"，pid 照实记）。
                    props = mtt.get("m_SavedProperties", {})
                    tex_entry = None
                    for slot, p2 in as_pairs(props.get("m_TexEnvs"),
                                             what="m_TexEnvs").items():
                        p2 = p2 or {}
                        mp2 = p2.get("m_Texture") or {}
                        if slot == "_MainTex" and mp2.get("m_PathID"):
                            to = deref(mp2, mo)
                            if to is not None:
                                tname = to.read_typetree().get("m_Name")
                                fname = f"{_sanitize(tname)}.png"   # 裸名（消费方拼 textures/ 前缀）
                                if fname not in textures:
                                    textures[fname] = to.read().image
                                # _MainTex ST（timewarped-tier-icon 2026-10-07）：序列化字段名=
                                # m_Scale/m_Offset（无 m_ST 键——首探读错键误判「无 ST」，致
                                # Timewarp 盾皮 v 偏移 0.475 丢失、渲出图集同 UV 区的金冠皮）。
                                # 三件 spell prefab 实测唯一非恒等=Bacon_TechLevelBanner_
                                # Timewarp_Unlit offset(0,0.475)；消费方注入期烘焙 uv0。
                                sc_, of_ = p2.get("m_Scale") or {}, p2.get("m_Offset") or {}
                                tex_entry = {"file": fname, "name": tname,
                                             "st": {"scale": [sc_.get("x", 1.0), sc_.get("y", 1.0)],
                                                    "offset": [of_.get("x", 0.0), of_.get("y", 0.0)]}}
                    colors = {slot: [round(c, 5) for c in as_rgba(col)]
                              for slot, col in as_pairs(props.get("m_Colors"),
                                                        what="m_Colors").items()}
                    report["materials"][mname] = {
                        "shader": sname, "shader_pid": sh.get("m_PathID") or None,
                        "mat_pid": mo.path_id,
                        "passes": passes,
                        "blend": _btf_blend_mode(passes),
                        "_MainTex": tex_entry, "colors": colors,
                    }
                node["renderer_enabled"] = rtt.get("m_Enabled")
                node["material_slots"] = slots
        if name in BTF_EXCLUDE_RULES:
            node["_excluded"] = True
            excluded_here = True
        has_renderer = node.get("material_slots") is not None
        if not excluded_here and node.get("_arrays") is not None and has_renderer:
            prefix = f"{spell_key}|{my_rel}"
            arr = node["_arrays"]
            arrays[f"{prefix}/verts"] = arr["verts"]
            arrays[f"{prefix}/uv0"] = arr["uv0"]
            for i, sub in enumerate(arr["submeshes"]):
                arrays[f"{prefix}/sub{i}"] = sub
            # 顶点色流（网格无该流时不出键）：multiply 链 vColor 首选真顶点色，
            # 缺流时消费方以材质 `_Color` 代偿（见 raster.raster_multiply）。
            if arr.get("colors") is not None:
                arrays[f"{prefix}/colors"] = arr["colors"]
            arrays[f"{prefix}/matrix"] = np.asarray(node["matrix"], dtype=np.float64)
        return node

    tree = walk(root, np.eye(4), "")
    return {**meta, "bundle": bundle, "guid": guid, "tree": tree}


# 进程级 memo（kits._KIT_CACHE / ability._ABILITY_CACHE 同法；2026-11-04）：
# spell prefab 走查+CARD_RACE 表=卡不变游戏结构，此前仅会话 memo——每 bacon 卡
# （compile_tier_spell 激活腿）重走查一遍（暖态实测 ~85-95ms/卡）。消费面只读 kit
# （纹理 np.asarray(convert) 解码新对象、数组算术出新、`rep["spells"][*]["tree"]`
# 注入为幂等等值覆写）——跨会话共享不改消费值。键含资产代/配置三维防跨代污染。
_BTF_CACHE: dict = {}


def _btf_memo_key() -> tuple:
    """进程 memo 键=（资产根, 客户端 locale, 资产代版本串）。三者全部从 GameContext
    流入（契约 D：ctx.data_win / ctx.locale / ctx.version——版本由入口边缘按 root
    同装解析，route.db meta game_build / text_shim 版本闸同源）——进程内客户端
    换代即换键；读不得（None）时 None 照进键（键面显式降级，不做静默共享）。"""
    from eidolon.core.infra.context import current

    ctx = current()
    return (str(ctx.data_win), ctx.locale, ctx.version)


@item("frames", "btf_kit")
def btf_kit() -> BtfKit:
    """spell prefab 走查+CARD_RACE 表（report+npz+textures+card_race 真内存）。
    ref=SpellTable 链解（_spell_refs）。进程 memo 叠会话 memo（_BTF_CACHE 注）。"""
    key = _btf_memo_key()
    cached = _BTF_CACHE.get(key)
    if cached is not None:
        return cached
    r = core().res
    report: dict = {"spells": {}, "materials": {}, "issues": []}
    kit = BtfKit(report=report)
    refs = _spell_refs()
    for spell_key, meta in BTF_SPELLS.items():
        spell_meta = {"ref": refs[spell_key], "spell_type": meta["spell_type"],
                      # 引擎侧槽位（缺省=表槽同值）：cost_alt_tavern_coin_* 二者异号，
                      # 见 BTF_SPELLS 行注（305=数据登记槽 / 303=引擎问的槽）。
                      "engine_spell_type": meta.get("engine_spell_type",
                                                    meta["spell_type"])}
        report["spells"][spell_key] = _walk_spell(r, spell_key, spell_meta,
                                                  report, kit.arrays, kit.textures)

    # CARD_RACE DBF（附加种族 tag 面）[btf:384-394 同式；dbf（infra）直提链]
    from eidolon.core.infra import dbf
    recs = [{"m_ID": u["m_ID"], "m_isRaceTagId": u["m_isRaceTagId"]}
            for u in dbf.default_dbf()._read_records("CARD_RACE")]
    kit.card_race = {"source": "dbf.unity3d CARD_RACE（eidolon.core.infra.dbf 直提链）",
                     "rows": recs}

    report["npz_prefixes"] = sorted({k.rsplit("/", 1)[0] for k in kit.arrays})
    logger.debug(f"[btf] npz={len(kit.arrays)} prefixes={len(report['npz_prefixes'])} "
                 f"mats={len(report['materials'])}")
    _BTF_CACHE[key] = kit
    return kit
