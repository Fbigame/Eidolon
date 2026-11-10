"""compiler — 渲染计划编译（段 S11 execute 第 2/3 步：compile_plan* 收敛+prep 换轨）。

游戏锚（walk-skeleton §11 表第 2/3 行）：Step4 CardDef+组件可见性判定（tag 驱动
编译期）→ 我方 desc["compile"](dbf, card)（old_frames/render_card.py:627）；
UpdateCostTextMesh/UpdateManaGemOffset 判定+文本源 → prep_plan
（old_plan/prep_plan.py:91）。七份旧编译器（scene_compiler/scene_compiler_ally/
wf_render/hero_render/hero_render_bacon/hp_render/location_render 的 compile_plan*）
= consumer-arch 卡第 1 类「共享编译引擎收敛」的最后一块副本网——本模块统一形收敛：
帧差异全走帧差异表（_FAMILY 组件可见性/文字角色/绑定面 per 帧键），判定面消费
九段已对拍函数（S4 family_for_card_type/get_texture、S5 plan_portrait/
plan_portrait_render、S6 plan_rarity_gem/plan_gem/cost_text_semantics、S7
spell_school_names 经 recipes、stat 收集=actor/gems.collect_stat_gems）。

批22 实现账（2026-10-14，S11 组装段生长；**立壳补充件**——批14 frames.py/批20
injectors.py 先例同形，NOTES 记一笔）。转写来源=七编译器 compile_plan*+_frame_*
组件段+prep_plan（行为面逐字保真——像素等价的编译半边）；账面串差异记账（见
偏差账）。两源=骨架 §11 第 2/3 行×旧实现还原，判定面以 decomp 为准、组件可见性
以旧实现为准（旧编译器自身即 decomp 逐条注出处件）。

纪律面前置——本模块经 recipes（color/frames/art 间接）/gems 判定触供给配方
（@item），**消费须在 supply session 内**（入口层独占纪律，批12-21 同款；未来
门驱动循环开 session 调本段，段内不开）。

偏差账（行为面零差为判据，账面串不保真——duipai C 账只对行为键）——
  * plan.meta/input/tags/actor 账面：旧编译器 meta.generator/compiled_at/来源串
    逐帧异形（行为零消费），统一形记账不保真；plan.tags 白名单=各编译器自有子集
    （行为零消费，记账统一白名单）。
  * class_color 账面：atlas_table/apply 出处串随统一形（行为消费=atlas_ref/
    atlas_img/color_type）；compile 期图集占位=GetClasses[0] pick 语义（sc:266
    逐字——引擎 compile 期写点与 IsMultiClass 覆写块 :6465-6477〔组件段复指时点
    =render_with 接线序〕两时点不可混同，S4 segment 全分支判定面对应后者）。
  * kit report 形态真差异归一读取（sc 平面 scalars 直键 vs Kit 嵌套 scalars——
    frames._kit_meta/portrait.portrait_binding 先例同款）。
  * compile 期 stat_gems 收集：ally/weapon/hero/heropower/location 编译期自带、
    spell/spell_dk 编译期不收（execute 期 gem==stat ∧ "stat_gems" not in plan
    补收，render_card.py:400 同判）——帧差异表 _COMPILE_COLLECTS。
离线边界：承袭各编译器头注（hero 手牌合成 (HERO,0) 选择、play m_cardFrontMatIdx=-1
不换装、bacon 文字恒隐藏等，逐条在位注）。
"""

from __future__ import annotations

import datetime as _dt

from eidolon.core.infra.card import BG_SPELL_CARDTYPE, Card, CardType, GameTag, SpellSchool
from eidolon.core.infra import il_tables
from eidolon.core.infra.dll_reflect import enum_table
from eidolon.core.recipes import color as _color
from eidolon.core.supply import overrides as _ovr   # contract E：frame 覆盖装载域项
from eidolon.core.recipes.frames import actor_ref, bacon_kit, kit, spell_school_names
from eidolon.core.recipes.frames import ability_kit
from eidolon.core.render.game import card_color_switcher as _switcher
from eidolon.core.render.game.actor import gems as _gems
from eidolon.core.render.game.actor import portrait as _portrait
# compile 期 plan.gem.t 占位（text-default-phase 2026-10-22：plan_gem 的 t 必填）：
# 正典渲染链在 prep_plan 恒覆写为逐卡 t_phase；直接消费 compile_plan 而不跑 prep 的
# 诊断面视同「无参考卡」，故取正典缺省常量。
from eidolon.core.render.params import DEFAULT_SESSION_T
from eidolon.core.render._provenance import fitted, invented  # noqa: F401 （按需）
from eidolon.core.render._provenance import parallel  # noqa: F401 （族默认）

CAMERA_PROVENANCE = {
    "model": "orthographic_natural",
    "px_per_unit": 707.0 / 4.0,
    "px_per_unit_source": "orthographicSize=2(半高) → 全高4单位 × 707px 出图"
                          "（tools/alphatool/SnapshotCamera.cs:SnapshotCamera.MakeSnapshotCamera,"
                          " tools/alphatool/AlphaTool.cs:AlphaTool）",
    "half_w": 2.0 * 512.0 / 707.0,
    "half_h": 2.0,
    "half_pixel_offset": 0.0,
}

def _live_cardtype_to_slot() -> dict[int, str]:
    """GetHandActor 分派臂表活读（hand-table-residuals 2026-11-06 换轨，手抄
    10 行退役）。

    引擎源=ActorNames.GetHandActor（ActorNames.cs:ActorNames.GetHandActor）——
    `il_tables.dispatch_call_consts` 提取「case TAG_CARDTYPE → call
    GetNameWithPremiumType 前装载的 ACTOR_ASSET 常量」，槽位名=ACTOR_ASSET 活枚举
    值名（==三活表 s_actorAssets 等的键名域）。形状断言=13 臂（当前引擎分派形态）
    ∧ default 腿=Card_Hidden 字面量（actor_names.CARD_HIDDEN 同串，decomp :574-575
    行为本体）。臂集=引擎全分派（含 BG_QUEST_REWARD/BG_SPELL/HERO_BUDDY/ANOMALY/
    TRINKET/GAME_MODE_BUTTON/PET）；开放位纪律不在本表（consumer-v2 起帧链开放位=
    resolve_prefab.open_prefab tripwire/_BUILDERS，本表仅 plan["actor"] 记账面）。
    改轨前对拍=evidence/probe_hand_tables.json（手抄 10 行全等子集+差异=12/24/45
    三开放位政策行）。锚 file:il_tables.dispatch_call_consts。
    """
    arms, dfn = il_tables.dispatch_call_consts(
        "ActorNames", "GetHandActor", "GetNameWithPremiumType", param_count=3)
    assert len(arms) == 13, (
        f"GetHandActor 臂数漂移（{len(arms)}，期 13）——引擎分派形态变更，"
        "先核 Assembly-CSharp 再重锚")
    assert dfn["ldstr"] and all(s.startswith("Card_Hidden") for s in dfn["ldstr"]), (
        f"GetHandActor default 腿形态漂移（{dfn['ldstr']}）——Card_Hidden 行为本体变更")
    asset_by_val = {v: k for k, v in enum_table("ActorNames+ACTOR_ASSET").items()}
    assert set(arms.values()) <= set(asset_by_val), (
        f"GetHandActor 臂常量越 ACTOR_ASSET 值域（{sorted(set(arms.values()) - set(asset_by_val))}）")
    return {ct: asset_by_val[v] for ct, v in arms.items()}


# 账面镜像（行为零消费：真分发=actor_names.resolve_prefab；本表仅写 plan["actor"] 记账。consumer-v2 起与 PREFAB_SPECS 无耦）
CARDTYPE_TO_SLOT = _live_cardtype_to_slot()

# 行 3=已账离线策略（批12 4c9294bb 偏差账：「SIGNATURE 过渡钻石」scene_compiler 旧
# 决策 vs decomp :886-895 SIGNATURE 走 DBF 后贯穿金表——SIGNATURE 无 card_id 落金表）。
# 2026-11-06 hand-table-residuals 活 Invoke 实证同 decomp（premium=3 链首表=premium，
# evidence/probe_hand_tables.json）；行 0/1/2=引擎转写（活链首表全等，drift_probe F 面
# 常驻逐值对）；本表保留手抄+行 3 钉账=族5 二选一的 F 面路线（表保留，值非纯转写）。
PREMIUM_TO_QUALITY = {0: "normal", 1: "premium", 2: "diamond", 3: "diamond"}

_PLAN_TAGS = (GameTag.COST, GameTag.PREMIUM, GameTag.CLASS, GameTag.CARDTYPE,
              GameTag.RARITY, GameTag.ELITE, GameTag.SPELL_SCHOOL, GameTag.CARD_SET,
              GameTag.CARDRACE, GameTag.ATK, GameTag.HEALTH, GameTag.ARMOR,
              GameTag.FACTION)

_TEXT_APPLY = ("Actor.Update*TextMesh → UberText（render-pipeline Step5）；"
               "排版 = uber_text 模块（FontDef 链 + prefab 序列化字段）")

NON_RASTER_MATERIALS: frozenset[str] = frozenset({"GenFX_Card_Back_Default_D"})
"""本渲染链支持的展示态里**永不参与光栅**的材质（2026-10-16 用户裁决）。

判据（用户口谕 + 实测）：卡背壳 = `Mesh` submesh1 / 材质 `GenFX_Card_Back_Default_D`；
引擎侧该材质主色 pass `culling=2.0`（Cull Back，材质状态表实测），正对手牌姿态下 18/48 个
三角全部背向 → 引擎恒不画；而**我方离线链不渲染翻面/牌库预览态**（grep 实证：render 面
无 flip/FaceDown/CardBack 渲染路径）⟹ 该几何在本链**没有可渲染态**，属"该不该进清单"问题
（用户裁决：不该进），不是"剔除状态"问题。

与剔除的分工（两件事，互不替代）：本集合=**几何级**从清单里排除（省掉投影+光栅化探索）；
`raster.primary_cull`（材质表 CullMode）=**执行级**兜底，负责其余链（武器剑/盾 823 三角、
英雄技能框 317、护甲 42）那些"靠正面遮挡兜底"的背向几何。两者都留着，判据各自独立。

取证要点：卡背壳先画、卡面后画 ⟹ 壳写入 z 后卡面在同 z 上被 LEqual 判不通过，那些轮廓外像素
只剩壳的金色（清单级排除单独做=像素零变化，执行级剔除才修画面；正典账见
docs/notes/scene-compiler-mvp.md §渲染正典）。"""


def _plan_tags(card: Card) -> dict[str, str]:
    return {str(int(t)): str(card.tags[t]) for t in _PLAN_TAGS if t in card.tags}


def _actor_selection(cardtype, premium) -> dict:
    """Step2：ActorNames.GetHandActor（ActorNames.cs:ActorNames.GetHandActor, 838-908）离线等价。"""
    slot = CARDTYPE_TO_SLOT.get(int(cardtype))
    quality = PREMIUM_TO_QUALITY.get(int(premium))
    assert slot and quality, f"卡型/品质不在 MVP（CARDTYPE={cardtype}, PREMIUM={premium}）"
    return {"actor_slot": slot, "quality": quality,
            "asset": actor_ref(quality, slot),
            "selection_rule": "ActorNames.GetHandActor (ActorNames.cs:ActorNames.GetHandActor) + "
                              "GetNameWithPremiumType (:838-908)"}


def _class_color(card: Card, family: str | None, *, applied: bool = True,
                 apply_note: str | None = None) -> dict:
    """compile 期类色账：GetClasses[0] pick 语义（sc:266 逐字；S4 family/atlas_ref
    判定面消费——family_for_card_type/get_texture）；family=None=无写点卡型
    （HERO_POWER break :6709-6725 / bacon play m_cardFrontMatIdx=-1 守卫跳过）。

    image/ref 同族断言（residual-silent-fallbacks 2026-11-05 收口）：图集像素族=
    调用方字面量（`_color.atlas(family, ct)`），ref 族=`family_for_card_type`
    （`get_texture` 内部）——两路分叉=像素与 ref 身份错位（canonical 复指按
    atlas_ref 判写点、mip 链按 ref 寻址，错族即静默失配），断言响亮。

    frame 覆盖轴（contract E，2026-11-06）：Card.frame_asset 在场=图集平面整体换
    覆盖图（ref=合成 `override:frame:<sha16>`，_REF_ENTRY 对其恒 miss→mip0 直采）；
    family=None 腿不在此响——覆盖在场时由 render_with 接缝步对 applied=False 响亮
    （无写点面禁静默 no-op），本函数保持「无写点=记账腿」单一职责。"""
    cls = card.classes[0]
    ct = _switcher.get_color_type_for_class(int(cls))
    if family is None:
        return {"tag_class": int(cls), "color_type": ct, "atlas_ref": None,
                "atlas_img": None, "applied": False,
                "apply": apply_note or "无类色写点卡型（SetMaterialNormal break 组）"}
    ref_family = _switcher.family_for_card_type(int(card.cardtype))
    assert family == ref_family, (
        f"类色 image/ref 族分叉：调用方字面族 {family!r} != "
        f"family_for_card_type({int(card.cardtype)})={ref_family!r}——图集像素与 ref "
        "必须同族（residual-silent-fallbacks 2026-11-05 收口）")
    fov = _ovr.frame_of(card)   # 会话 memo（session 内；路径/格式校验 fail loud 在域内）
    if fov is not None:
        atlas_ref, atlas_img = fov["ref"], fov["img"]
    else:
        atlas_ref = _switcher.get_texture(int(card.cardtype), ct)
        atlas_img = _color.atlas(family, ct)
    out = {"tag_class": int(cls), "color_type": ct, "atlas_ref": atlas_ref,
           "atlas_img": atlas_img, "applied": applied,
           "apply": apply_note
           or "SetMaterialWithTexture (Actor.cs:Actor.SetMaterialWithTexture) 写点全集（组件段槽位）"}
    if fov is not None:
        out["frame_override"] = {"ref": fov["ref"], "sha256": fov["sha256"],
                                 "path": fov["path"]}
    return out


def _binding(report: dict, extra_refs: tuple[str, ...] = (), *,
             scalars_flat: bool = False) -> dict:
    """Actor 序列化绑定面（kit report actor_components[0] 直读；形态真差异归一——
    ability kit 平面直键 / frames kit 嵌套 scalars，portrait.portrait_binding 先例）。"""
    ac = report["actor_components"][0]
    refs = ac.get("object_refs") or {}
    scalars = ac if scalars_flat else (ac.get("scalars") or {})
    b = {
        "card_mesh_node": (refs.get("m_cardMesh") or {}).get("node"),
        "portrait_mesh_node": (refs.get("m_portraitMesh") or {}).get("node"),
        "name_banner_mesh_node": (refs.get("m_nameBannerMesh") or {}).get("node"),
        "description_mesh_node": (refs.get("m_descriptionMesh") or {}).get("node"),
        "rarity_frame_mesh_node": (refs.get("m_rarityFrameMesh") or {}).get("node"),
        "rarity_gem_mesh_node": (refs.get("m_rarityGemMesh") or {}).get("node"),
        "mana_gem_node": (refs.get("m_manaObject") or {}).get("node"),
        "elite_object_node": (refs.get("m_eliteObject") or {}).get("node"),
        "card_front_mat_idx": scalars.get("m_cardFrontMatIdx"),
        "portrait_mat_idx": scalars.get("m_portraitMatIdx"),
        "portrait_frame_mat_idx": scalars.get("m_portraitFrameMatIdx"),
        "card_back_mat_idx": scalars.get("m_cardBackMatIdx"),
        "premium_ribbon": scalars.get("m_premiumRibbon"),
    }
    for key in extra_refs:
        b[key] = (refs.get(key) or {}).get("node")
    return b


def _frame_active_flags(hierarchy: dict) -> dict[str, bool]:
    """prefab activeInHierarchy（含父链传播；各编译器 _frame_active_flags* 同式）。"""
    out: dict[str, bool] = {}

    def walk(n, path=""):
        p = f"{path}/{n['name']}" if path else n["name"]
        out[p] = bool(n.get("active_in_hierarchy", True))
        for c in n["children"]:
            walk(c, p)

    walk(hierarchy)
    return out


def _renderer_enabled_map(hierarchy: dict) -> dict[str, bool]:
    """路径 → 序列化 renderer.enabled（prefab 真值；缺 renderer 的节点不登记）。

    2026-10-23 hero-play-frame：接触阴影 `Shadow`/`ShadowUnique` 的展示态**不能**
    按 `m_shadowVisible` 缺省值推——那是 Actor 运行时状态机（`ContactShadow(bool)`
    才置位），不是 prefab 序列化态；本仓渲染链对位的是**参照采集态**
    （tools/alphatool `CreateActor` → `UpdateAllComponents(true)`，全链无
    `ContactShadow(...)` 调用 ⇒ `m_contactShadows == null` ⇒
    `Actor.UpdateContactShadow` 首行早退 ⇒ renderer 保持序列化 enabled）。
    故判据一律取序列化 enabled（hero 双 prefab 实测：Card_Play_Hero/Shadow
    enabled=true / Card_Hand_Hero/Shadow+ShadowUnique enabled=false）。"""
    out: dict[str, bool] = {}

    def walk(n, path=""):
        p = f"{path}/{n['name']}" if path else n["name"]
        rr = n.get("renderers") or []
        if rr:
            out[p] = bool(rr[0].get("enabled", True))
        for c in n.get("children", []):
            walk(c, p)

    walk(hierarchy)
    return out


def _walk_with_key(node, key="root", path=""):
    """层级走查（yield (node, npz_key, path)；sc._walk_with_key :501 同式）。"""
    p = f"{path}/{node['name']}" if path else node["name"]
    yield node, key, p
    for i, c in enumerate(node.get("children", [])):
        yield from _walk_with_key(c, f"{key}.{i}", p)


def _slot_write(class_color: dict, portrait: dict, binding: dict,
                m: dict, path: str, *, spell_like: bool = False) -> dict | None:
    """材质槽运行时写点（_frame_components 材质段公共形）：cardMesh[cardFront]（恒写）
    → portraitFrame 槽（SPELL 专属 :6767 或共享资产连带帧）→ portrait 槽。返回槽
    增补或 None。各帧差异（共享 pid 连带/占位纹理跟随/LOCATION 六节点）在位覆写。"""
    tex = (m.get("textures", {}).get("_MainTex") or {})
    slot = {"slot": m["slot"], "material": m.get("name"),
            "_MainTex": {"name": tex.get("name"), "bundle": tex.get("bundle")}}
    if m["slot"] == binding["card_front_mat_idx"] and path == binding["card_mesh_node"] \
            and class_color["applied"]:
        slot["_MainTex_runtime"] = {"image": class_color["atlas_img"],
                                    "atlas_ref": class_color["atlas_ref"],
                                    "source": "SetMaterialWithTexture cardMesh[cardFrontMatIdx]"}
        return slot
    if m["slot"] == binding["portrait_frame_mat_idx"] and path == binding["portrait_mesh_node"] \
            and class_color["applied"] and spell_like:
        slot["_MainTex_runtime"] = {"image": class_color["atlas_img"],
                                    "atlas_ref": class_color["atlas_ref"],
                                    "source": "SetMaterialWithTexture SPELL 分支 "
                                              "portraitMesh[portraitFrameMatIdx]（Actor.cs:Actor.SetMaterialWithTexture）"}
        return slot
    if m["slot"] == binding["portrait_mat_idx"] and path == binding["portrait_mesh_node"]:
        slot["_MainTex_runtime"] = {"image": portrait["img"],
                                    "source": "CardDef.m_PortraitTexturePath（Actor.cs:Actor.UpdatePortraitTexture）"}
        return slot
    return slot


def _components_base(report: dict, frame_active: dict[str, bool]) -> list[dict]:
    """组件清单基底（各编译器公共形）：renderer 节点×序列化失活面。"""
    comps = []
    for n in report["nodes"]:
        path = n["path"]
        comp = n.get("components", {})
        renderer = comp.get("renderer")
        if not renderer or not renderer.get("material_slots"):
            continue
        name = path.rsplit("/", 1)[-1]
        entry = {"node": name, "path": path, "visible": True, "raster": True}
        if not frame_active.get(path, True):
            entry["visible"] = False
            entry["raster"] = False
            entry["visibility_rule"] = {
                "rule": "prefab activeInHierarchy=false（序列化失活，运行时按状态机激活的变体子树）",
                "source": "kit meta active_in_hierarchy（prefab dump 实测）",
                "tags_used": [],
            }
        comps.append(entry)
    return comps


def _vis(entry: dict, visible, rule: dict, *, raster=None) -> None:
    entry["visible"] = visible
    if raster is not None:
        entry["raster"] = raster
    entry["visibility_rule"] = rule


_RARITY_RULE_KEYS = ("rule", "source", "tags_used")


def _rarity_rule(rarity: dict, source_extra: str = "") -> dict:
    rule = {k: rarity[k] for k in _RARITY_RULE_KEYS}
    if source_extra:
        rule = {**rule, "source": rarity["source"] + source_extra}
    return rule


def _school_plate(schools: dict[int, str], school_id: int) -> str:
    """学派板文本（TAG_SPELL_SCHOOL 值→zhCN 名；residual-silent-fallbacks
    2026-11-05 收口——旧 `schools.get(school_id, "")` 静默落「无学派板」退役）。

    三态：0（GetTag 缺省=无学派 tag）→ 显式无板（引擎 UpdateRace 文本空同象）；
    活表已名值（s_spellSchoolNames 1-13 全员，probe 实测）→ 文本；其余（活表外
    裸 int=新学派未入册 / 活成员缺键=本地化面漂移）→ KeyError 响亮——未知学派
    不得静默渲成无学派卡（fail-closed；新学派先入册 TAG_SPELL_SCHOOL+
    GLOBAL_SPELL_SCHOOL_* 再渲）。语料普查 36,390 卡 SPELL_SCHOOL 值全落已名
    1-13（evidence/corpus_tag_hist.json）——本响亮面对现行语料零扰动。"""
    if not school_id:
        return ""
    try:
        return schools[school_id]
    except KeyError:
        raise KeyError(
            f"未知学派 id {school_id}——s_spellSchoolNames 活表无此键"
            f"（已名 {sorted(schools)}）：新学派先入册 TAG_SPELL_SCHOOL+"
            "GLOBAL_SPELL_SCHOOL_* 本地化再渲，禁静默落「无学派板」"
            "（residual-silent-fallbacks 2026-11-05 收口）") from None


def _race_display_name(strings: dict[str, str], race_id: int) -> str:
    """种族显示名（race id→GLOBAL_RACE_* 键→zhCN；residual-silent-fallbacks
    2026-11-05 收口——旧 `strings.get(race_names[r], "UNKNOWN")` 渲字面 UNKNOWN
    退役）。

    两腿响亮：race id 不在 race_names（TAG_RACE/s_raceNames 活表外=未知种族）；
    键不在 kit 串表（GLOBAL_RACE_* 本地化漂移）。两态都不得渲字面 UNKNOWN
    （fail-closed）。语料普查 CARDRACE 值全落 race_names 43 键
    （evidence/corpus_tag_hist.json）——本响亮面对现行语料零扰动。"""
    from eidolon.core.infra.game_strings import race_names
    try:
        key = race_names[race_id]
    except KeyError:
        raise KeyError(
            f"未知种族 id {race_id}——race_names 无此键（TAG_RACE 活表 "
            f"{len(race_names)} 键）：新种族先入册 TAG_RACE+s_raceNames 再渲，"
            "禁渲字面 UNKNOWN（residual-silent-fallbacks 2026-11-05 收口）") from None
    try:
        return strings[key]
    except KeyError:
        raise KeyError(
            f"种族 {race_id} 本地化键 {key} 不在 kit 串表——GLOBAL_RACE_* 面漂移，"
            "禁渲字面 UNKNOWN（residual-silent-fallbacks 2026-11-05 收口）") from None


# ============================================================================
# ability 帧（spell/spell_dk；sc.compile_plan :228 行为面）
# ============================================================================

def _compile_ability(dbf_id: str, card: Card, premium: bool = False) -> dict:
    # premium=True=金法术帧（capture-determinism 2026-10-30，98918 首例）：
    # 独立 premium kit（自身 report/hierarchy/ubertext，层级少 NonQuestObjects 层），
    # plan 组件路径自 premium report——与 ally/ally_premium 先例同构。
    pk = "Card_Hand_Ability_Premium" if premium else "Card_Hand_Ability"
    schools = spell_school_names()
    school_id = int(card.spell_school)
    texts = {"name": card.name, "desc": card.text,
             "cost": str(card.cost),
             "plate": _school_plate(schools, school_id)}
    card_id = card.card_id
    k = ability_kit("premium" if premium else "normal")
    report, hierarchy = k.report, k.recon_meta["hierarchy"]
    binding = _binding(report, scalars_flat=True,
                       extra_refs=("m_attackObject", "m_healthObject",
                                   "m_racePlateObject", "m_multiRacePlateObject"))
    binding["spell_desc_mesh_neutral"] = (
        report["actor_components"][0]["object_refs"]
        .get("m_spellDescriptionMeshNeutral", {}).get("name"))
    binding["spell_desc_mesh_school"] = (
        report["actor_components"][0]["object_refs"]
        .get("m_spellDescriptionMeshSchool", {}).get("name"))
    binding["rune_banner"] = "Actor.cs:Actor.UpdateCardRuneBannerComponent UpdateCardRuneBannerComponent 默认 Hide()"

    cardtype_ = int(card.cardtype)
    if cardtype_ == int(CardType.BATTLEGROUND_QUEST_REWARD):
        # ct40 类色 null 写点（bg-ct40-43-44-routing 2026-10-24）：
        # CardColorSwitcher.GetTexture :259-261 BATTLEGROUND_QUEST_REWARD 直返 null →
        # Actor.SetMaterialWithTexture :6801-6812 texture==null 早退——cardFront/
        # portraitFrame 两槽均不写，帧保持序列化材质（NEUTRAL 序列化面与
        # spellCardTextures[GENERIC] 写后同象，参照 89449 vs 89011 逐位同帧实证）。
        family = None
        apply_note = ("GetTexture null 腿（CardColorSwitcher.cs:259-261）→ "
                      "SetMaterialWithTexture null 早退（Actor.cs:6801-6812）："
                      "帧保持序列化材质，无类色写点（ct40）")
    else:
        family = ("battlegroundsSpellCardTextures"
                  if cardtype_ == BG_SPELL_CARDTYPE else "spellCardTextures")
        apply_note = ("SetMaterialWithTexture (Actor.cs:Actor.SetMaterialWithTexture)：cardMesh 材质"
                      "[m_cardFrontMatIdx]._MainTex；SPELL 再写 portraitMesh 材质"
                      "[m_portraitFrameMatIdx]（Actor.cs:Actor.SetMaterialWithTexture）")
    class_color = (_premium_class_color(card, binding) if premium
                   else _class_color(card, family, apply_note=apply_note))
    # 金卡类色=SetMaterialPremium 染色（不换图集，SetMaterial :6609 GOLDEN 分岔——
    # UpdateCardColor 尾 switch 实证：premium≠NORMAL 永不进 SetMaterialNormal/
    # SetMaterialWithTexture），帧保持序列化金贴图——ally/ally_premium 先例同构。
    portrait = _portrait.plan_portrait(card_id, pk)

    rarity = _gems.plan_rarity_gem(card)
    frame_active = _frame_active_flags(hierarchy)
    comps = _components_base(report, frame_active)
    by_path = {c["path"]: c for c in comps}
    is_elite = bool(card.elite)
    is_spell = int(card.cardtype) == int(CardType.SPELL)
    has_school = bool(texts["plate"])
    for c in comps:
        name = c["node"]
        path = c["path"]
        if name in ("RarityFrame_mesh", "RarityGem"):
            _vis(c, rarity["visible"], _rarity_rule(rarity))
            if name == "RarityGem" and rarity["visible"]:
                c["material_override"] = {
                    "_MainTex.offset": rarity["atlas_offset"],
                    "_tint_rgb": rarity["tint_rgb"],
                    "source": "GetRarityTextureOffset → material.mainTextureOffset/_tint"
                              "（Actor.cs:Actor.GetRarityTextureOffset, 常量 :101-115）",
                }
        elif name in ("InHand_Ability_Unique_Dragon", "InHand_Ability_Unique_Dragon_shadow"):
            _vis(c, is_elite, {
                "rule": "该节点 = m_eliteObject。UpdateEliteComponent (Actor.cs:Actor.UpdateEliteComponent)："
                        "EnableRenderers(m_eliteObject, IsElite())，IsElite=TAG_ELITE(114)",
                "source": "Actor.cs:Actor.UpdateEliteComponent + :1365-1384 (IsElite)",
                "tags_used": [int(GameTag.ELITE)],
            })
            # m_eliteObject 子树展示态=IsElite() 运行时覆写（RenderUtils.EnableRenderers
            # includeInactive:true 对子树每个 renderer 无条件写 enabled=enable）——prefab
            # 序列化 enabled 不是展示态（影节点序列化 enabled=False，ELITE 卡引擎实画；
            # elite-dragon-shadow 2026-10-24 RenderDoc 117341 实证）。执行层两过滤按本
            # 标记豁免：components._suppress_disabled / build_render_list 的 list_enabled_skip。
            c["enabled_override"] = "Actor.UpdateEliteComponent"
        elif name in ("RuneHolder_Mesh", "RuneHolder_Shadow_Mesh"):
            _vis(c, False, {
                "rule": "UpdateCardRuneBannerComponent 默认 m_cardRuneBanner.Hide()，"
                        "仅 HasRuneCost（DK 符文费）才 Show",
                "source": "Actor.cs:Actor.UpdateCardRuneBannerComponent",
                "tags_used": ["HasRuneCost(符文费 tag 族，非 DK 恒缺)"],
            })
        elif name in ("Shadow", "ShadowUnique"):
            _vis(c, False, {
                "rule": "接触阴影：m_shadowVisible 默认 false，仅 ContactShadow(true)才显；"
                        "AlphaTool 静态快照不调 → renderer.enabled=false",
                "source": "Actor.cs:Actor.ContactShadow + :4852-4866；字段默认 :430",
                "tags_used": [],
            })
        elif name == "FX_Ghost_Quad":
            _vis(c, False, {
                "rule": "幽灵卡特效：m_ghostCard 默认 NONE → DisableGhost",
                "source": "Actor.cs:Actor.UpdateGhostCardEffect (UpdateGhostCardEffect)",
                "tags_used": [],
            })
        elif name == "Highlight_Card_Plane":
            _vis(c, False, {
                "rule": "高亮盖板：HighlightState 组件运行时状态机控制",
                "source": "Actor.cs:Actor.UpdateHighlights (UpdateHighlights → HighlightState)",
                "tags_used": [],
            })
        elif name == "Card_InHand_Ally_CurvedText":
            c["raster"] = False
            c["role"] = ("name 文字 RTT 载体网格（AbilityCardCurvedText）：m_RenderToTexture "
                         "路径由 uber_text 模块按网格 UV 贴回；无自身材质故不参与帧光栅")
            c["visibility_rule"] = {
                "rule": "NameUberText.m_RenderToTexture=1 → 文字渲进 RT、按本网格 UV 贴回卡面"
                        "（UberText.cs:UberText.SetupRenderToTexture）",
                "source": "text-rendering-pipeline.md §弧面；uber_text._render_rtt",
                "tags_used": [],
            }
        slots = []
        for m in next(n for n in report["nodes"] if n["path"] == path)\
                .get("components", {}).get("renderer", {}).get("material_slots", []):
            slot = _slot_write(class_color, portrait, binding, m, path,
                               spell_like=True)
            if premium and m["slot"] == class_color["premium_ribbon_slot"] \
                    and path == binding["card_mesh_node"]:
                # SetMaterialPremium 染色写点（Actor.cs:6762-6770 GetMaterial(
                # m_premiumRibbon).color=cardColor）——与 _compile_ally premium 支
                # 同构（mechorse-golden 先例）；金法术帧 2026-10-30 接线时漏移植，
                # 序列化类材质 _Color（_Warlock 紫等）未被类色覆写 → 顶带/学派横幅/
                # desc 中柱（ribbon submesh 覆盖域）被序列化紫染色。单 tint=
                # GetClassColor(colors[0])；双职业账=_compile_ally 同款
                # _dual_class_tint（本卡族暂单色，账面留位与 ally 同形）。
                slot["material_override"] = {
                    "_tint_rgb": list(class_color["premium_ribbon_color"]),
                    "source": "Actor.cs:Actor.SetMaterialPremium :6757-6779（金法术补移植 2026-11-04）",
                }
            slots.append(slot)
        c["material_slots"] = slots
        if name == "InHand_Ability_Unique_Dragon_shadow":
            # 影子件=乘性影通路（elite-dragon-shadow 2026-10-24）：材质
            # Card_Inhand_Ability_Warlock_Shadow 束内序列化 shader_pid=−870869104636564592
            # （与 Card_Inhand_Weapon_Drake_shadow 同 pid，后者 kit 记录实名
            # Hero/Multiply/Multiply——PS `add o0.xyz,r0,v2`，vColor=_Color 序列化 0 →
            # src=tex+0=tex，out=dst×tex）。spell 链 blend 消费=mo.blend
            # （blend_from_override 谱系），无本 override 会按 over 画；显式 add 式
            # 防止 multiply_form 回落旧 tint（tex×_Color=0 → 纯黑）。纹理=序列化
            # 职业图集原样（_slot_write 不给龙/影槽写 atlas_ref——SetMaterialWithTexture
            # 只写 cardMesh/portraitMesh，RenderDoc 实证龙/影不随类色换图集）。
            for s in c["material_slots"]:
                s["material_override"] = {
                    "blend": "multiply", "_multiply_form": "add_vcolor",
                    "source": "Card_Inhand_Ability_Warlock_Shadow（Hero/Multiply/Multiply，"
                              "DstColor·Zero pass+zWrite0；材质束序列化直读）",
                }
        if path == binding["description_mesh_node"]:
            c["mesh"] = {
                "neutral": binding["spell_desc_mesh_neutral"],
                "school": binding["spell_desc_mesh_school"],
                "runtime": "school" if is_spell and has_school else "neutral",
                "source": "UpdateRace (Actor.cs:Actor.UpdateRace)：SPELL 且学派文本非空 → "
                          "meshFilter.sharedMesh = m_spellDescriptionMeshSchool",
                "tags_used": [int(GameTag.CARDTYPE), int(GameTag.SPELL_SCHOOL)],
            }
    del by_path

    texts_plan = []
    sources = {"name": "Card m_name zhCN", "desc": "Card m_textinhand zhCN",
               "cost": "TAG_COST(48)",
               "plate": "TAG_SPELL_SCHOOL(1635) → s_spellSchoolNames zhCN"}
    for role in ("cost", "name", "desc", "plate"):
        if not texts[role]:
            texts_plan.append({"role": role, "render": False,
                               "reason": "文本为空（cost 缺省/无派系）"})
            continue
        texts_plan.append({"role": role, "render": True, "text": texts[role],
                           "source": sources[role], "apply": _TEXT_APPLY})

    return {
        "meta": {"generator": "eidolon/core/render/game/compiler.py",
                 "frame": "Card_Hand_Ability（spell/spell_dk 共链）" if not premium
                          else "Card_Hand_Ability_Premium（金法术，capture-determinism 2026-10-30）",
                 "compiled_at": _dt.datetime.now().isoformat(timespec="seconds")},
        "input": {"dbf_id": str(dbf_id), "card_id": card_id, "locale": "zhCN", "zone": "HAND"},
        "tags": _plan_tags(card),
        "actor": _actor_selection(card.cardtype, card.premium),
        "actor_binding": binding,
        "camera": CAMERA_PROVENANCE,
        "class_color": class_color,
        "portrait": portrait,
        "components": comps,
        "rarity_gem": rarity,
        "texts": texts_plan,
        "gem": _gems.plan_gem(pk, t=DEFAULT_SESSION_T),
    }


# ============================================================================
# ally 帧（sca.compile_plan_ally :211 行为面）
# ============================================================================

def _race_text_and_count(card: Card) -> tuple[str, int, dict]:
    """GetRaceText（EntityBase.cs:EntityBase.GetRaceText）+ Card.races 正典查询（批16 dual-race
    缺口闭合形态）。文本 = SortRaceList 序 GetRaceName 逐种族 "\\n" 连接。
    race id→GLOBAL_RACE_* 键=数据面（infra.game_strings，decomp 直读；
    race-names-data 2026-11-01 去 hosted 反射）；解析响亮面=_race_display_name
    （residual-silent-fallbacks 2026-11-05——未知 id/缺本地化禁渲 UNKNOWN）。

    Eidolon 覆盖座位（core-integration §7.5）：card.races_text_override 非 None
    时整段短路——文本="\n".join(override)，计数=len(override)；空 tuple →
    ("", 0)，种族文本/板自然隐藏（消费点 1/3）。"""
    if getattr(card, "races_text_override", None) is not None:
        text = "\n".join(card.races_text_override)
        return text, len(card.races_text_override), {"source": "eidolon.races_override"}
    strings = kit("ally").races["strings"]
    races = list(card.races)
    names = [_race_display_name(strings, r) for r in races]
    text = "\n".join(names)
    rule = {"rule": "随从：races=GetRaces 正典；plate 显隐 = 文本非空且 GetRaceCount()==1"
                    "（单板）/ >1（宽板）",
            "source": "Actor.cs:Actor.UpdateRace (UpdateRace); EntityBase.cs:EntityBase",
            "tags_used": ["TAG_CARDRACE(200)", "CARD_RACE.IsRaceTag 布尔行"],
            "races": races}
    return text, len(races), rule


def _premium_class_color(card: Card, binding: dict) -> dict:
    """金卡类色账：SetMaterialPremium 转写（Actor.cs:Actor.SetMaterialPremium :6757-6779
    ——GOLDEN/DIAMOND/SIGNATURE 经 SetMaterial :6609 分岔进入；**不换图集**，唯一写点
    =premiumRibbon 槽材质染色）。

    单职业支（colors.Count==1）_Color=GetClassColor(colorType)+_EnableDualClass=0；
    双职业支（Count==2）_EnableDualClass=1+_Color=left/_SecondColor=right——左右两色
    **同经 GetDualClassColor 反查**（Actor.cs:Actor.GetDualClassColors :6704-6712 →
    Actor.cs:Actor.GetDualClassColor switch 体，dual_class_color_rgb 对位）。
    ≥3 类/空类=GetCardColorTypeForClasses 的 [GENERIC] 单色形
    （CardColorSwitcher.cs:125-143）。执行形=cardMesh[premiumRibbon] 槽级
    material_override（raster tint 消费口）：单职业 _tint_rgb；双职业追加
    _dual_class_tint（_Color/_SecondColor/_EnableDualClass，raster 逐像素判式消费——
    shader Custom/Card/UnlitDualClassTextureTint：判轴=对象空间 POSITION.x、双 margin
    白缝带、_Color 高 x 侧；判式常量 _MiddleValue/_FirstColorRightMargin/
    _SecondColorLeftMargin 由 raster 自材质序列化直读，不抄第二份事实源）。

    修正账（premium-dualclass-color 2026-11-01）：双职业 left 现行实现
    class_color_rgb(cts[0]) 曾落 GENERIC 灰（旧手抄类色表无 DUALCLASS 键域，缺键缺省
    同象）——与引擎 GetDualClassColors 两色同经 GetDualClassColor 不符，随本卡
    接线按 decomp 修正（单职业支计算不变，98918 零扰动）。2026-11-05 class-axis
    收口：dual_class_color_rgb 改 IL 直读（臂表/值域活面），算术反查退役。"""
    classes = list(card.classes)
    cts = _switcher.get_card_color_type_for_classes(classes or None)
    ribbon = int(binding.get("premium_ribbon", -1))
    dual = len(cts) == 2
    if dual:
        left = _switcher.dual_class_color_rgb(cts[0])
        right = _switcher.dual_class_color_rgb(cts[1])
    else:
        left = _switcher.class_color_rgb(cts[0])
        right = None
    account = {
        "tag_class": int(classes[0]) if classes else 0,
        "color_type": int(cts[0]),
        "color_types": [int(c) for c in cts],
        "atlas_ref": None, "atlas_img": None, "applied": False,
        "premium_ribbon_slot": ribbon,
        "premium_ribbon_color": list(left),
        "enable_dual_class": 1 if dual else 0,
        "second_color": list(right) if right else None,
        "apply": "SetMaterialPremium（Actor.cs:Actor.SetMaterialPremium :6757-6779）："
                 "premiumRibbon 槽染色，无图集写点（SetMaterial :6609 GOLDEN 分岔）",
    }
    if dual:
        account["apply"] += ("；双职业支 _Color=GetDualClassColor(colors[0]) 落高 POSITION.x 侧、"
                             "_SecondColor=colors[1] 落低侧（shader UnlitDualClassTextureTint "
                             "PS 直读，premium-dualclass-color 2026-11-01）")
    return account


def _compile_ally(dbf_id: str, card: Card, *, premium: bool = False) -> dict:
    """ally 帧（Card_Hand_Ally）；premium=True=金卡档（Card_Hand_Ally_Premium，
    resolve_frame_key GOLDEN 分叉同入——帧差异全在 kit/类色账两处，组件名两 prefab
    全同构〔mechorse-golden 2026-10-21 prefab 走查〕）。"""
    card_id = card.card_id
    k = kit("ally_premium") if premium else kit("ally")
    report, hierarchy = k.report, k.meta["hierarchy"]
    binding = _binding(report, extra_refs=("m_attackObject", "m_healthObject",
                                           "m_racePlateObject", "m_multiRacePlateObject"))
    if premium:
        class_color = _premium_class_color(card, binding)
        portrait = _portrait.plan_portrait(card_id, "Card_Hand_Ally_Premium")
    else:
        class_color = _class_color(
            card, "minionCardTextures",
            apply_note="SetMaterialWithTexture（Actor.cs:Actor.SetMaterialWithTexture）：cardMesh._MainTex；"
                       "Ally prefab PortraitFrame_mesh[m_portraitFrameMatIdx] 与 cardMesh[slot0] "
                       "绑同一 Material 资产 → 单写点双面生效")
        portrait = _portrait.plan_portrait(card_id, "Card_Hand_Ally")
    rarity = _gems.plan_rarity_gem(card)
    attack_text = "" if (card.attack_display_hidden or card.attack_number_hidden) \
        else str(card.attack)
    health_text = "" if (card.health_display_hidden or card.health_number_hidden) \
        else str(card.health)
    race_text, race_count, race_rule = _race_text_and_count(card)
    frame_active = _frame_active_flags(hierarchy)
    comps = _components_base(report, frame_active)
    is_elite = bool(card.elite)
    for c in comps:
        name, path = c["node"], c["path"]
        if name in ("RarityGem", "RarityGemFrame"):
            _vis(c, rarity["visible"], _rarity_rule(
                rarity, "；NORMAL 卡不走 SetRarityGemMesh 网格切换（:5004-5022 仅 SIGNATURE）"))
            if name == "RarityGem" and rarity["visible"]:
                c["material_override"] = {
                    "_MainTex.offset": rarity["atlas_offset"],
                    "_tint_rgb": rarity["tint_rgb"],
                    "source": "GetRarityTextureOffset → mainTextureOffset/_tint"
                              "（Actor.cs:Actor.UpdateRarityComponent, 常量 :101-115）",
                }
        elif name in ("Unique_Ally_Dragon", "Unique_Ally_Dragon_Shadow"):
            # Shadow 子节点=premium prefab 独有（mechorse-golden prefab 走查；普通
            # prefab 无此节点不命中）——UpdateEliteComponent EnableRenderers 递归子树
            # （Actor.cs:5174-5181 + RenderUtils.cs:98-109 GetComponentsInChildren），
            # 影子随本体 IsElite() 显隐（e10 golden 龙影漏隐藏正典修点同锚）
            _vis(c, is_elite, {
                "rule": "该节点 = m_eliteObject 子树。UpdateEliteComponent "
                        "(Actor.cs:Actor.UpdateEliteComponent)：EnableRenderers(m_eliteObject, "
                        "IsElite())，IsElite=TAG_ELITE(114)，递归子树",
                "source": "Actor.cs:Actor.UpdateEliteComponent + :1365-1384 (IsElite) + "
                          "RenderUtils.cs:98-109",
                "tags_used": [int(GameTag.ELITE)],
            })
        elif name == "Gem_Attack":
            _vis(c, not card.attack_display_hidden, {
                "rule": "UpdateAttackTextMesh (Actor.cs:Actor.UpdateAttackTextMesh :3435)："
                        "HasHideStats(HIDE_STATS∨DORMANT)/HIDE_ATTACK → "
                        "GemObject.Hide()，否则 Show()",
                "source": "Actor.cs:Actor.UpdateAttackTextMesh",
                "tags_used": ["HIDE_STATS", "HIDE_ATTACK"],
            })
        elif name == "Gem_Health":
            _vis(c, not card.health_display_hidden, {
                "rule": "UpdateHealthTextMesh (Actor.cs:Actor.UpdateHealthTextMesh :3496)："
                        "HasHideStats(HIDE_STATS∨DORMANT)/HIDE_HEALTH → "
                        "GemObject.Hide()，否则 Show()",
                "source": "Actor.cs:Actor.UpdateHealthTextMesh",
                "tags_used": ["HIDE_STATS", "HIDE_HEALTH"],
            })
        elif name == "RacePlate_mesh":
            _vis(c, bool(race_text) and race_count == 1, race_rule)
        elif name == "Multi_RacePlate_mesh":
            _vis(c, bool(race_text) and race_count > 1, {
                "rule": "UpdateRace：多 race（GetRaceCount()>1）才显 multi 板与 m_multiRaceTextMesh",
                "source": race_rule["source"],
                "tags_used": ["TAG_CARDRACE(200)+附加种族 tag"],
            })
        elif name in ("RuneHolder_Mesh", "RuneHolder_Shadow_Mesh", "HolderGlow_Tutorial"):
            _vis(c, False, {
                "rule": "UpdateCardRuneBannerComponent 默认 m_cardRuneBanner.Hide()",
                "source": "Actor.cs:Actor.UpdateCardRuneBannerComponent",
                "tags_used": ["HasRuneCost"],
            })
        elif name in ("Shadow", "ShadowUnique"):
            _vis(c, False, {
                "rule": "接触阴影：m_shadowVisible 默认 false；AlphaTool 静态快照不调",
                "source": "Actor.cs:Actor.ContactShadow + :4852-4866",
                "tags_used": [],
            })
        elif name.startswith("FX_Ghost_Quad"):
            _vis(c, False, {
                "rule": "幽灵卡特效：m_ghostCard 默认 NONE → DisableGhost",
                "source": "Actor.cs:Actor.UpdateGhostCardEffect (UpdateGhostCardEffect)",
                "tags_used": [],
            })
        elif name == "Highlight_Card_Plane":
            _vis(c, False, {
                "rule": "高亮盖板：HighlightState 状态机，无高亮不可见",
                "source": "Actor.cs:Actor.UpdateHighlights (UpdateHighlights)",
                "tags_used": [],
            })
        elif name == "Card_InHand_Ally_CurvedText":
            c["raster"] = False
            c["role"] = ("name 文字 RTT 载体网格（CardAllyCurvedText）："
                         "m_RenderToTexture 路径由 uber_text 按网格 UV 贴回")
            c["visibility_rule"] = {
                "rule": "NameUberText.m_RenderToTexture=1 → 文字渲进 RT、按本网格 UV 贴回卡面",
                "source": "text-rendering-pipeline.md §弧面；uber_text._render_rtt",
                "tags_used": [],
            }
        slots = []
        for m in next(n for n in report["nodes"] if n["path"] == path)\
                .get("components", {}).get("renderer", {}).get("material_slots", []):
            slot = _slot_write(class_color, portrait, binding, m, path)
            if name == "Unique_Ally_Dragon_Shadow":
                # 龙影压暗件混合态（golden-base-alignment 2026-11-04）：材质
                # GenFX_Card_InHand_DragonShadow_Premium（shader Hero/Particle/
                # Particle Multiply，pass0=Blend Zero SrcColor → out=dst×src.rgb，
                # 与 (DstColor,Zero) 乘性恒等；pass1=加法辉光 _GlowIntensity=0 不出
                # 像素）。ally 链 blend_from_table=False → 无 override 回落 alpha-over
                # =白环带被龙影纹理加亮（隔离实证：full 129.11 vs 去件 99.48，
                # only 件黑底 74.79=opaque 画法）。override 按材质实名经
                # multiply_form 解析=tint 形（_Color=1）；ability 帧同名影子
                # （Hero/Multiply/Multiply=add_vcolor 形）先例同位。
                slot["material_override"] = {
                    "blend": "multiply",
                    "source": "GenFX_Card_InHand_DragonShadow_Premium pass0 Blend "
                              "Zero SrcColor（材质态表 passes 直读；"
                              "Hero/Particle/Particle Multiply）",
                }
            if premium and m["slot"] == class_color["premium_ribbon_slot"] \
                    and path == binding["card_mesh_node"]:
                # SetMaterialPremium 染色写点（Actor.cs:6762-6770 GetMaterial(m_premiumRibbon)
                # .color）——槽级 material_override._tint_rgb（raster tint 消费口）；
                # 单 tint=colors[0] 类色。双职业（Count==2）追加 _dual_class_tint=
                # 引擎运行时三写点（_Color=GetDualClassColor(colors[0])/_SecondColor=
                # colors[1]/_EnableDualClass=1，GetDualClassColors :6704-6712）——
                # raster 逐像素判式消费（shader UnlitDualClassTextureTint：判轴=对象空间
                # POSITION.x、[M−m2,M+m1) 白缝带、_Color 高 x 侧）；判式常量
                # （_MiddleValue 等三件）raster 自材质序列化直读。单职业卡无此键
                # → 旧单 tint 路径逐位不变（neutral 零扰动锚）。
                slot["material_override"] = {
                    "_tint_rgb": list(class_color["premium_ribbon_color"]),
                    "source": "Actor.cs:Actor.SetMaterialPremium :6757-6779（mechorse-golden）",
                }
                if class_color.get("second_color"):
                    slot["material_override"]["_dual_class_tint"] = {
                        "_Color": list(class_color["premium_ribbon_color"]),
                        "_SecondColor": list(class_color["second_color"]),
                        "_EnableDualClass": 1.0,
                        "source": "Actor.cs:Actor.SetMaterialPremium 双职业支 :6771-6777 + "
                                  "Actor.cs:Actor.GetDualClassColors（shader Custom/Card/"
                                  "UnlitDualClassTextureTint PS 直读判式；"
                                  "premium-dualclass-color 2026-11-01）",
                    }
            if slot.get("slot") == binding["portrait_frame_mat_idx"] \
                    and path == binding["portrait_mesh_node"] \
                    and "_MainTex_runtime" in slot and slot["_MainTex_runtime"].get("atlas_ref"):
                slot["_MainTex_runtime"]["source"] = (
                    "与 cardMesh[slot0] 同一 Material 资产（path_id 相同）→ 类色写点连带生效")
            slots.append(slot)
        c["material_slots"] = slots

    from eidolon.core.render.game.actor.components import walk_with_key  # 环避让（S11 执行面单源）
    stat_gems = _gems.collect_stat_gems(hierarchy, {"components": comps}, walk_with_key)

    race_role = "race_multi" if race_count > 1 else "race"
    bodies = {"cost": str(card.cost), "name": card.name, "desc": card.text,
              "race": race_text, "attack": attack_text, "health": health_text}
    sources = {
        "name": "Card m_name zhCN", "desc": "Card m_textinhand zhCN", "cost": "TAG_COST(48)",
        "attack": "TAG_ATK(47)；HIDE_ATTACK_NUMBER 缺省 → Convert.ToString（Actor.cs:Actor.UpdateAttackTextMesh）",
        "health": "TAG_HEALTH(45)；HIDE_HEALTH_NUMBER 缺省 → Convert.ToString",
        "race": "GetRaces 正典 → GetRaceName → GLOBAL_RACE_* zhCN（BuildRaceText :1273-1279）",
        "race_multi": "同 race 文本（引擎同一 text 写宽板 UberText，Actor.cs:Actor.UpdateRace）",
    }
    texts_plan = []
    for role in ("cost", "name", "desc", "race", "attack", "health"):
        body = bodies[role]
        if not body:
            texts_plan.append({"role": role, "render": False, "reason": "文本为空（缺省/规则隐藏）"})
            continue
        entry_role = race_role if role == "race" else role
        texts_plan.append({"role": entry_role, "render": True, "text": body,
                           "source": sources[entry_role], "apply": _TEXT_APPLY})

    return {
        "meta": {"generator": "eidolon/core/render/game/compiler.py",
                 "frame": "Card_Hand_Ally_Premium（金卡随从手牌帧）" if premium
                          else "Card_Hand_Ally（随从手牌帧）",
                 "compiled_at": _dt.datetime.now().isoformat(timespec="seconds")},
        "input": {"dbf_id": str(dbf_id), "card_id": card_id, "locale": "zhCN", "zone": "HAND"},
        "tags": _plan_tags(card),
        "actor": _actor_selection(card.cardtype, card.premium),
        "actor_binding": binding,
        "camera": CAMERA_PROVENANCE,
        "class_color": class_color,
        "portrait": portrait,
        "components": comps,
        "rarity_gem": rarity,
        "texts": texts_plan,
        "gem": _gems.plan_gem("Card_Hand_Ally_Premium" if premium else "Card_Hand_Ally",
                              t=DEFAULT_SESSION_T),
        "stat_gems": stat_gems,
    }


# ============================================================================
# weapon 帧（wf.compile_plan_weapon :151 行为面）
# ============================================================================

def _compile_weapon(dbf_id: str, card: Card) -> dict:
    assert int(card.cardtype) == int(CardType.WEAPON), \
        f"dbf {dbf_id} 非 WEAPON（CARDTYPE={card.cardtype}）"
    card_id = card.card_id
    k = kit("weapon")
    report, hierarchy = k.report, k.meta["hierarchy"]
    binding = _binding(report, extra_refs=("m_attackObject", "m_healthObject",
                                           "m_descriptionTrimMesh"))
    binding["description_trim_mesh_node"] = (
        (report["actor_components"][0].get("object_refs") or {})
        .get("m_descriptionTrimMesh", {}).get("node"))
    class_color = _class_color(
        card, "weaponCardTextures",
        apply_note="SetMaterialNormal(WEAPON)→SetMaterialWeapon（Actor.cs:Actor.SetMaterialNormal/"
                   "6800-6808）：HasTexture=true → 写 cardMesh[0]._MainTex；"
                   "PortraitFrame/RarityGemFrame 同 Material 资产连带染色")
    portrait = _portrait.plan_portrait(card_id, "Card_Hand_Weapon")
    rarity = _gems.plan_rarity_gem(card)
    attack_text = "" if (card.attack_display_hidden or card.attack_number_hidden) \
        else str(card.attack)
    durability_text = "" if (card.health_display_hidden or card.health_number_hidden) \
        else str(card.health)
    frame_active = _frame_active_flags(hierarchy)
    comps = _components_base(report, frame_active)
    is_elite = bool(card.elite)
    for c in comps:
        name, path = c["node"], c["path"]
        if name in ("RarityGem", "RarityGemFrame"):
            _vis(c, rarity["visible"], _rarity_rule(
                rarity, "；NORMAL 卡不走 SetRarityGemMesh（:4992-5022 仅 SIGNATURE）"))
            if name == "RarityGem" and rarity["visible"]:
                c["material_override"] = {
                    "_MainTex.offset": rarity["atlas_offset"],
                    "_tint_rgb": rarity["tint_rgb"],
                    "source": "UpdateRarityComponent（Actor.cs:Actor.UpdateRarityComponent）：GetRarityTextureOffset",
                }
        elif name == "Unique_Weapon_Dragon":
            _vis(c, is_elite, {
                "rule": "该节点 = m_eliteObject。UpdateEliteComponent (Actor.cs:Actor.UpdateEliteComponent)："
                        "EnableRenderers(m_eliteObject, IsElite())",
                "source": "Actor.cs:Actor.UpdateEliteComponent",
                "tags_used": [int(GameTag.ELITE)],
            })
            # 同 spell 侧语义（elite-dragon-shadow 2026-10-24）：序列化 enabled=False 不是
            # 展示态。本帧 list_enabled_skip=False（plan visible 直渲）+suppress 不适用，
            # 标记今日惰性——留给过滤面演化的护位，防未来策略翻转丢件。
            c["enabled_override"] = "Actor.UpdateEliteComponent"
        elif name == "Wep_Swords":
            _vis(c, not card.attack_display_hidden, {
                "rule": "该节点 = m_attackObject。UpdateAttackTextMesh (Actor.cs:Actor.UpdateAttackTextMesh :3435)："
                        "HasHideStats(HIDE_STATS∨DORMANT)/HIDE_ATTACK → GemObject.Hide()",
                "source": "Actor.cs:Actor.UpdateAttackTextMesh",
                "tags_used": ["HIDE_STATS", "HIDE_ATTACK"],
            })
        elif name == "Wep_SheildBroken":
            _vis(c, not card.health_display_hidden, {
                "rule": "该节点 = m_healthObject。UpdateHealthTextMesh (Actor.cs:Actor.UpdateHealthTextMesh :3496)："
                        "HasHideStats(HIDE_STATS∨DORMANT)/HIDE_HEALTH → GemObject.Hide()",
                "source": "Actor.cs:Actor.UpdateHealthTextMesh",
                "tags_used": ["HIDE_STATS", "HIDE_HEALTH"],
            })
        elif name in ("RuneHolder_Mesh", "RuneHolder_Shadow_Mesh", "HolderGlow_Tutorial"):
            _vis(c, False, {
                "rule": "UpdateCardRuneBannerComponent 默认 m_cardRuneBanner.Hide()",
                "source": "Actor.cs:Actor.UpdateCardRuneBannerComponent",
                "tags_used": ["HasRuneCost"],
            })
        elif name in ("Shadow", "ShadowUnique"):
            _vis(c, False, {
                "rule": "接触阴影：m_shadowVisible 默认 false（本帧 renderer.enabled=false 序列化即证）",
                "source": "Actor.cs:Actor.UpdateContactShadow",
                "tags_used": [],
            })
        elif name.startswith("FX_Ghost_Quad"):
            _vis(c, False, {
                "rule": "幽灵卡特效（本帧 renderer.enabled=false 序列化即证）",
                "source": "Actor.cs:Actor.UpdateGhostCardEffect (UpdateGhostCardEffect)",
                "tags_used": [],
            })
        elif name == "Highlight_Card_Plane":
            _vis(c, False, {
                "rule": "高亮盖板：HighlightState 状态机，无高亮不可见",
                "source": "Actor.cs:Actor.UpdateHighlights (UpdateHighlights)",
                "tags_used": [],
            })
        elif name in ("Multiclass_Ribbon_mesh", "Multiclass_Ribbon_Shadow_mesh",
                      "Multiclass_Ribbon_Signature_mesh", "Multiclass_Ribbon_Signature_Shadow_mesh"):
            _vis(c, False, {
                "rule": "多职业缎带：prefab 序列化失活（UpdateMulticlassRibbonComponent 仅多职业卡 Show）",
                "source": "kit meta active_in_hierarchy 实测",
                "tags_used": ["多职业 tag 族（本卡缺省）"],
            })
        slots = []
        for m in next(n for n in report["nodes"] if n["path"] == path)\
                .get("components", {}).get("renderer", {}).get("material_slots", []):
            slot = _slot_write(class_color, portrait, binding, m, path)
            if slot.get("slot") == binding["portrait_frame_mat_idx"] \
                    and path == binding["portrait_mesh_node"] \
                    and "_MainTex_runtime" in slot and slot["_MainTex_runtime"].get("atlas_ref"):
                slot["_MainTex_runtime"]["source"] = (
                    "与 cardMesh[slot0] 同一 Material 资产 → 共享实例连带类色（RarityGemFrame 同）")
            if (class_color["applied"]
                    and class_color["color_type"] == _switcher.ColorType.TYPE_DEATHKNIGHT
                    and not card.is_dualclass
                    and slot.get("slot") == binding["portrait_frame_mat_idx"]
                    and path == binding["portrait_mesh_node"]):
                # WEAPON 单色 DK 特支（Actor.cs:Actor.SetMaterialWithTexture）：portraitMesh[
                # portraitFrameMatIdx] 追加写 _MainTex=colors[0] 图集——Count==1
                # 守卫=引擎逐字（双职业 DK 武器 Count==2 不走；≥3 类落 GENERIC
                # 亦不走）；flag=false → _EnableDualClass=0、无 _SecondTex。
                # 批25 补写点（批22 记账缺口兑现）：语料 weapon 2 卡（42700
                # Warrior/68354 Rogue）判定恒假=语料零行为，合成探针自证。
                slot["_MainTex_runtime"] = {
                    "image": class_color["atlas_img"],
                    "atlas_ref": class_color["atlas_ref"],
                    "source": "SetMaterialWithTexture WEAPON 单色 DK 特支 "
                              "portraitMesh[portraitFrameMatIdx]（Actor.cs:Actor.SetMaterialWithTexture）"}
            slots.append(slot)
        c["material_slots"] = slots
        if name == "Unique_Weapon_Dragon":
            # 龙影=同节点槽 1 材质 Card_Inhand_Weapon_Drake_shadow（elite-dragon-shadow
            # 2026-10-24）：mesh polySurface1 束内序列化**单 submesh**（264 tri）×双材质槽
            # ——Unity MeshRenderer 语义=材质多于 submesh 时末 submesh 逐多余材质重画，
            # 引擎把龙几何再用影材质（Hero/Multiply/Multiply，_Color=0.5 灰 → src=tex+0.5）
            # 乘性叠画（raster 桶 n_draw=max(n_sub,len(mats)) 消费）。weapon 链
            # blend_from_table/override 双 False——影槽 blend 须槽级 override 显式给。
            for s in c["material_slots"]:
                if s.get("slot") == 1:
                    s["material_override"] = {
                        "blend": "multiply", "_multiply_form": "add_vcolor",
                        "source": "Card_Inhand_Weapon_Drake_shadow（Hero/Multiply/Multiply，"
                                  "DstColor·Zero pass+zWrite0；kit 材质记录实名+束内同 pid）",
                    }
        if path == binding["portrait_mesh_node"]:
            c["portrait_submesh"] = {
                "sub": binding["portrait_mat_idx"],
                "source": "八角画像窗 = PortraitFrame sub1（22 三角，slot1=portrait 材质）",
            }
        if path == binding["description_trim_mesh_node"]:
            c["material_override"] = {
                "_Color": "保持序列化（Card_InHand_Weapon_TrimWarlock 紫）",
                "source": "SetMaterialWeapon（Actor.cs:Actor.SetMaterialWeapon）：HasTexture=true → "
                          "SetColor _Color 的 else-if 分支不触发",
            }

    from eidolon.core.render.game.actor.components import walk_with_key
    stat_gems = _gems.collect_stat_gems(hierarchy, {"components": comps}, walk_with_key)

    bodies = {"cost": str(card.cost), "name": card.name,
              "desc": card.desc_text or "", "attack": attack_text,
              "durability": durability_text}
    sources = {
        "cost": "TAG_COST(48)", "name": "Card m_name zhCN",
        "desc": "CardTextBuilder DLL 直调（infra/text_shim；静态卡面真值）",
        "attack": "TAG_ATK(47)；HIDE_ATTACK_NUMBER 缺省 → Convert.ToString",
        "durability": "TAG_HEALTH(45)=武器耐久；GetAttackOrHealthStringAndDoLargeNumberFormatting",
    }
    texts_plan = []
    for role in ("cost", "name", "desc", "attack", "durability"):
        body = bodies[role]
        if not body:
            texts_plan.append({"role": role, "render": False, "reason": "文本为空（缺省/规则隐藏）"})
            continue
        texts_plan.append({"role": role, "render": True, "text": body,
                           "source": sources[role], "apply": _TEXT_APPLY})

    return {
        "meta": {"generator": "eidolon/core/render/game/compiler.py",
                 "frame": "Card_Hand_Weapon（武器手牌帧）",
                 "compiled_at": _dt.datetime.now().isoformat(timespec="seconds")},
        "input": {"dbf_id": str(dbf_id), "card_id": card_id, "locale": "zhCN", "zone": "HAND"},
        "tags": _plan_tags(card),
        "actor": _actor_selection(card.cardtype, card.premium),
        "actor_binding": binding,
        "camera": CAMERA_PROVENANCE,
        "class_color": class_color,
        "portrait": portrait,
        "components": comps,
        "rarity_gem": rarity,
        "texts": texts_plan,
        "gem": _gems.plan_gem("Card_Hand_Weapon", t=DEFAULT_SESSION_T),
        "stat_gems": stat_gems,
    }


# ============================================================================
# hero 双帧（hero.compile_plan_hero :181 行为面）
# ============================================================================

def _compile_hero(mode: str, dbf_id: str, card: Card) -> dict:
    assert int(card.cardtype) == int(CardType.HERO), \
        f"dbf {dbf_id} 非 HERO（CARDTYPE={card.cardtype}）"
    kit_key = "hero_hand" if mode == "hand" else "hero_play"   # supply kit 命名空间
    pk = "Card_Hand_Hero" if mode == "hand" else "Card_Play_Hero"  # prefab 命名空间（consumer-v2）
    card_id = card.card_id
    k = kit(kit_key)
    report, hierarchy = k.report, k.meta["hierarchy"]
    binding = _binding(report, extra_refs=("m_attackObject", "m_healthObject", "m_armorObject"))
    class_color = _class_color(
        card, "heroCardTextures", applied=(mode == "hand"),
        apply_note=("SetMaterialNormal(HERO)→SetMaterialHero（Actor.cs:Actor.SetMaterialNormal/6794-6797）"
                    "→ SetMaterialWithTexture 写 cardMesh[m_cardFrontMatIdx=0]._MainTex"
                    if mode == "hand" else
                    "m_cardFrontMatIdx=-1 → SetMaterialWithTexture 守卫"
                    "（Actor.cs:Actor.SetMaterialWithTexture `if (m_cardFrontMatIdx > -1)`）跳过 → 帧不换装"))
    portrait = _portrait.plan_portrait(card_id, pk)
    rarity = _gems.plan_rarity_gem(card)
    if binding["rarity_gem_mesh_node"] is None:
        # 帧 prefab 无 m_rarityGemMesh（hero play 双链 object_refs 实测为空）⇒
        # Actor.UpdateRarityComponent 的 `(bool)m_rarityGemMesh` 门关（:4960）——
        # 与 plan_gem 的 `enabled = m_manaObject 在位` 同族判据（帧绑定数据驱动，
        # 非卡/前缀特判）。此前 play 帧传说英雄（112815/104637）会走进
        # composite_rarity_gem 取 hero_play kit 里不存在的 GenFX_RarityGems.png 而崩。
        rarity = dict(rarity, visible=False,
                      rule="帧 prefab 无 m_rarityGemMesh → Actor.UpdateRarityComponent "
                           "`(bool)m_rarityGemMesh` 门关（play 双链 prefab object_refs 无"
                           "稀有度宝石对象）",
                      source="Actor.cs:Actor.UpdateRarityComponent (UpdateRarityComponent)")
    armor = card.armor
    frame_active = _frame_active_flags(hierarchy)
    renderer_enabled = _renderer_enabled_map(hierarchy)
    comps = _components_base(report, frame_active)
    is_elite = bool(card.elite)
    for c in comps:
        name, path = c["node"], c["path"]
        if name in ("RarityGem", "RarityGemFrame"):
            _vis(c, rarity["visible"], _rarity_rule(
                rarity, "；NORMAL 不走 SetRarityGemMesh"))
            if name == "RarityGem" and rarity["visible"]:
                c["material_override"] = {
                    "_MainTex.offset": rarity["atlas_offset"],
                    "_tint_rgb": rarity["tint_rgb"],
                    "source": "UpdateRarityComponent（Actor.cs:Actor.UpdateRarityComponent）",
                }
        elif name == "HeroCard_InHand_EliteDragon":
            _vis(c, is_elite, {
                "rule": "该节点 = m_eliteObject。UpdateEliteComponent (Actor.cs:Actor.UpdateEliteComponent)："
                        "EnableRenderers(m_eliteObject, IsElite())",
                "source": "Actor.cs:Actor.UpdateEliteComponent",
                "tags_used": [int(GameTag.ELITE)],
            })
        elif name == "Gem_Attack":
            _vis(c, False, {
                "rule": "UpdateAttackTextMesh 英雄分支（Actor.cs:Actor.UpdateAttackTextMesh）：IsHero 且 ATK==0 → "
                        "m_attackObject.SetActive(false)",
                "source": "Actor.cs:Actor.UpdateAttackTextMesh",
                "tags_used": ["TAG_ATK(47)"],
            })
        elif name == "Gem_Health":
            _vis(c, False, {
                "rule": "UpdateHealthTextMesh（Actor.cs:Actor.UpdateHealthTextMesh）：IsHero && "
                        "m_healthDisplayRequiresHeroCard（默认 true）&& m_card==null → Hide",
                "source": "Actor.cs:Actor.UpdateHealthTextMesh",
                "tags_used": [],
            })
        elif name in ("Armor_whole", "Armor_Whole_mesh"):
            _vis(c, armor != 0 and not card.has_hide_stats, {
                "rule": "UpdateArmorTextMesh（Actor.cs:Actor.UpdateArmorTextMesh :3532）：ARMOR==0 ∨ "
                        "HasHideStats(HIDE_STATS∨DORMANT) → m_armorObject.SetActive(false)",
                "source": "Actor.cs:Actor.UpdateArmorTextMesh",
                "tags_used": ["TAG_ARMOR(292)", "HasHideStats(HIDE_STATS/DORMANT)"],
            })
        elif name in ("Shadow", "ShadowUnique"):
            enabled = renderer_enabled.get(path, True)
            _vis(c, enabled, {
                "rule": "接触阴影（tag FakeShadow/FakeShadowUnique）：展示态=prefab 序列化 "
                        "renderer.enabled（本帧=%s）——参照采集链不调 Actor.ContactShadow(bool)，"
                        "m_contactShadows 恒 null ⇒ UpdateContactShadow 首行早退 ⇒ 序列化态即展示态"
                        "（hero 双 prefab 对照：Play/Shadow enabled=true、Hand/Shadow 与 ShadowUnique "
                        "enabled=false）" % enabled,
                "source": "prefab 序列化 renderer.enabled（Actor.cs:Actor.UpdateContactShadow 早退语义；"
                          "参照链=tools/alphatool Renderer.CreateActor→UpdateAllComponents 无 ContactShadow 调用）",
                "tags_used": [],
            })
        elif name == "Highlight_Card_Plane":
            _vis(c, False, {
                "rule": "高亮盖板：HighlightState 状态机，无高亮不可见",
                "source": "Actor.cs:Actor.UpdateHighlights (UpdateHighlights)",
                "tags_used": [],
            })
        slots = []
        for m in next(n for n in report["nodes"] if n["path"] == path)\
                .get("components", {}).get("renderer", {}).get("material_slots", []):
            if mode == "hand" and class_color["applied"]:
                tex = (m.get("textures", {}).get("_MainTex") or {})
                slot = {"slot": m["slot"], "material": m.get("name"),
                        "_MainTex": {"name": tex.get("name"), "bundle": tex.get("bundle")}}
                if m["slot"] == binding["card_front_mat_idx"] and path == binding["card_mesh_node"]:
                    slot["_MainTex_runtime"] = {"image": class_color["atlas_img"],
                                                "atlas_ref": class_color["atlas_ref"],
                                                "source": "SetMaterialWithTexture cardMesh[0]"}
                elif m.get("name") == "Card_Inhand_Hero_Druid":
                    slot["_MainTex_runtime"] = {"image": class_color["atlas_img"],
                                                "atlas_ref": class_color["atlas_ref"],
                                                "source": "与 cardMesh[0] 同一 Material 资产 → 共享实例连带类色"}
                elif tex.get("name") == "Card_Inhand_Hero_Druid":
                    slot["_MainTex_runtime"] = {"image": class_color["atlas_img"],
                                                "atlas_ref": class_color["atlas_ref"],
                                                "source": "占位 _MainTex 同名纹理 → 跟随类色图集"
                                                          "（BannerAtlasMod2x 独立资产）"}
                if path == binding["portrait_mesh_node"] and m["slot"] == binding["portrait_mat_idx"]:
                    slot["_MainTex_runtime"] = {"image": portrait["img"],
                                                "source": "CardDef.m_PortraitTexturePath；本 sub 走肖像公式层"}
                slots.append(slot)
            else:
                slot = {"slot": m["slot"], "material": m.get("name"),
                        "_MainTex": {"name": (m.get("textures", {}).get("_MainTex") or {}).get("name"),
                                     "bundle": (m.get("textures", {}).get("_MainTex") or {}).get("bundle")}}
                if path == binding["portrait_mesh_node"] and m["slot"] == binding["portrait_mat_idx"]:
                    slot["_MainTex_runtime"] = {"image": portrait["img"],
                                                "source": "CardDef.m_PortraitTexturePath；本 sub 走肖像公式层"}
                slots.append(slot)
        c["material_slots"] = slots
        if path == binding["portrait_mesh_node"]:
            c["portrait_submesh"] = {
                "sub": binding["portrait_mat_idx"],
                "source": ("肖像窗 = PortraitFrame sub1（29 tri，slot1）" if mode == "hand"
                           else "肖像 = Mesh sub1（18 tri，slot1=GenFX_Card_Hero-HeroPortrait）"),
            }

    from eidolon.core.render.game.actor.components import walk_with_key
    stat_gems = _gems.collect_stat_gems(hierarchy, {"components": comps}, walk_with_key)

    if mode == "hand":
        bodies = {"cost": "" if card.cost_hidden else str(card.cost),
                  "name": card.name, "desc": card.text, "attack": "",
                  "armor": str(armor) if armor != 0 else ""}
        sources = {"cost": "TAG_COST(48) → Convert.ToString(entity.GetCost())；cost_hidden 链"
                           "（HIDE_STATS/HIDE_COST/DORMANT）→ 空文本（Actor.cs:Actor.UpdateCostTextMesh"
                           " :3293 + Actor.cs:Actor.ShouldHideCost :4023）",
                   "name": "Card m_name zhCN", "desc": "Card m_textinhand zhCN",
                   "attack": "英雄分支 ATK==0 → m_attackObject 隐藏（Actor.cs:Actor.UpdateAttackTextMesh）",
                   "armor": "TAG_ARMOR(292)；缺省 0 → 隐藏（Actor.cs:Actor.UpdateArmorTextMesh）"}
    else:
        bodies = {"attack": "", "health": ""}
        sources = {"attack": "英雄分支 ATK==0 → m_attackObject 隐藏（Actor.cs:Actor.UpdateAttackTextMesh）",
                   "health": "IsHero && m_healthDisplayRequiresHeroCard(默认 true :403) && "
                             "m_card==null → 隐藏（Actor.cs:Actor.UpdateHealthTextMesh）"}
    texts_plan = []
    for role in bodies:
        body = bodies[role]
        if not body:
            texts_plan.append({"role": role, "render": False, "reason": "文本为空（缺省/规则隐藏）"})
            continue
        texts_plan.append({"role": role, "render": True, "text": body,
                           "source": sources[role], "apply": _TEXT_APPLY})

    slot_sel = "HAND_HERO" if mode == "hand" else "PLAY_HERO"
    if mode == "hand":
        actor = _actor_selection(int(CardType.HERO), 0)   # hero 手牌合成 (HERO, 0) 选择语义（旧轨同）
    else:
        actor = {"actor_slot": "PLAY_HERO", "quality": "normal",
                 "asset": actor_ref("normal", "PLAY_HERO"),
                 "selection_rule": "ActorNames.GetPlayActorByTags (ActorNames.cs:ActorNames.GetPlayActorByTags+) HERO case"}

    return {
        "meta": {"generator": "eidolon/core/render/game/compiler.py",
                 "frame": f"{k.meta.get('root', 'Card_Hand_Hero')}（英雄{mode}帧）",
                 "compiled_at": _dt.datetime.now().isoformat(timespec="seconds")},
        "input": {"dbf_id": str(dbf_id), "card_id": card_id, "locale": "zhCN",
                  "zone": "HAND" if mode == "hand" else "PLAY"},
        "tags": _plan_tags(card),
        "actor": {**actor, "actor_slot": slot_sel},
        "actor_binding": binding,
        "camera": CAMERA_PROVENANCE,
        "class_color": class_color,
        "portrait": portrait,
        "components": comps,
        "rarity_gem": rarity,
        "texts": texts_plan,
        "gem": _gems.plan_gem(pk, t=DEFAULT_SESSION_T),
        "stat_gems": stat_gems,
        "portrait_render": _portrait.plan_portrait_render(pk),
    }


# ============================================================================
# heropower 帧（hp.compile_plan_hp :179 行为面）
# ============================================================================

def _compile_heropower(dbf_id: str, card: Card) -> dict:
    assert int(card.cardtype) == int(CardType.HERO_POWER), \
        f"dbf {dbf_id} 非 HERO_POWER（CARDTYPE={card.cardtype}）"
    card_id = card.card_id
    k = kit("heropower")
    report, hierarchy = k.report, k.meta["hierarchy"]
    binding = _binding(report)
    binding["card_mesh_node"] = None
    binding["unbound_fields"] = ("m_cardMesh/m_eliteObject/m_nameBannerMesh/m_descriptionMesh/"
                                 "m_rarityGemMesh 等未绑定（dump object_refs 无此键或空）")
    class_color = _class_color(
        card, None,
        apply_note="SetMaterialNormal（Actor.cs:Actor.SetMaterialNormal）HERO_POWER → break：帧保持 "
                   "prefab 序列化材质，无类色写点")
    portrait = _portrait.plan_portrait(card_id, "History_HeroPower")
    rarity = _gems.plan_rarity_gem(card)
    frame_active = _frame_active_flags(hierarchy)
    comps = _components_base(report, frame_active)
    for c in comps:
        name, path = c["node"], c["path"]
        if name == "Highlight_Card_Plane":
            _vis(c, False, {
                "rule": "高亮盖板：renderer.enabled=false（序列化即证）+ HighlightState 无高亮不可见",
                "source": "Actor.cs:Actor.UpdateHighlights (UpdateHighlights)",
                "tags_used": [],
            }, raster=False)
        elif name == "FX_Ghost_Quad":
            _vis(c, False, {
                "rule": "幽灵卡特效：renderer.enabled=false（序列化即证）",
                "source": "Actor.cs:Actor.UpdateGhostCardEffect (UpdateGhostCardEffect)",
                "tags_used": [],
            }, raster=False)
        slots = []
        for m in next(n for n in report["nodes"] if n["path"] == path)\
                .get("components", {}).get("renderer", {}).get("material_slots", []):
            slots.append(_slot_write({"applied": False}, portrait, binding, m, path))
        c["material_slots"] = slots
        if path == binding["portrait_mesh_node"]:
            c["portrait_submesh"] = {
                "sub": binding["portrait_mat_idx"],
                "source": "圆窗 = HeroPowerV2 sub1（6 三角，slot1=_InPlayPortraitV2 肖像材质）",
            }

    from eidolon.core.render.game.actor.components import walk_with_key
    stat_gems = _gems.collect_stat_gems(hierarchy, {"components": comps}, walk_with_key)

    bodies = {"cost": str(card.cost), "name": card.name,
              "desc": card.desc_text or ""}
    sources = {"cost": "TAG_COST(48)", "name": "Card m_name zhCN",
               "desc": "CardTextBuilder DLL 直调；<b>英雄技能</b> 加粗行由 uber_text Bold 语义处理"}
    texts_plan = []
    for role in ("cost", "name", "desc"):
        body = bodies[role]
        if not body:
            texts_plan.append({"role": role, "render": False, "reason": "文本为空（缺省/规则隐藏）"})
            continue
        texts_plan.append({"role": role, "render": True, "text": body,
                           "source": sources[role], "apply": _TEXT_APPLY})

    return {
        "meta": {"generator": "eidolon/core/render/game/compiler.py",
                 "frame": "History_HeroPower（英雄技能帧）",
                 "compiled_at": _dt.datetime.now().isoformat(timespec="seconds")},
        "input": {"dbf_id": str(dbf_id), "card_id": card_id, "locale": "zhCN", "zone": "HAND"},
        "tags": _plan_tags(card),
        "actor": {"actor_slot": "HISTORY_HERO_POWER",
                  "quality": PREMIUM_TO_QUALITY[int(card.premium)],
                  "asset": actor_ref(PREMIUM_TO_QUALITY[int(card.premium)], "HISTORY_HERO_POWER"),
                  "selection_rule": "ActorNames.GetHandActor HERO_POWER 分支 (ActorNames.cs:ActorNames.GetHandActor)"},
        "actor_binding": binding,
        "camera": CAMERA_PROVENANCE,
        "class_color": class_color,
        "portrait": portrait,
        "components": comps,
        "rarity_gem": rarity,
        "texts": texts_plan,
        "gem": _gems.plan_gem("History_HeroPower", t=DEFAULT_SESSION_T),
        "stat_gems": stat_gems,
    }


# ============================================================================
# location 帧（loc.compile_plan_location :168 行为面）
# ============================================================================

_LOCATION_SHARED_NODES = ("Mesh", "NameBanner_mesh", "PortraitFrame_mesh",
                          "No_Gem_Mesh", "Unique_Ally_Dragon", "RacePlate_mesh")


def _compile_location(dbf_id: str, card: Card) -> dict:
    assert int(card.cardtype) == int(CardType.LOCATION), \
        f"dbf {dbf_id} 非 LOCATION（CARDTYPE={card.cardtype}）"
    card_id = card.card_id
    k = kit("location")
    report, hierarchy = k.report, k.meta["hierarchy"]
    binding = _binding(report, extra_refs=("m_rarityNoGemMesh", "m_healthObject",
                                           "m_racePlateObject"))
    class_color = _class_color(
        card, "locationCardTextures",
        apply_note="SetMaterialNormal(LOCATION)→default→SetMaterialWithTexture：写 cardMesh[0]；"
                   "共享 pid 六节点连带；LOCATION 尾段（:6782-6786）显式写 m_rarityNoGemMesh")
    portrait = _portrait.plan_portrait(card_id, "Card_Hand_Location")
    rarity = _gems.plan_rarity_gem(card)
    durability_text = "" if (card.health_display_hidden or card.health_number_hidden) \
        else str(card.health)
    frame_active = _frame_active_flags(hierarchy)
    comps = _components_base(report, frame_active)
    is_elite = bool(card.elite)
    for c in comps:
        name, path = c["node"], c["path"]
        if name == "RarityGem":
            _vis(c, rarity["visible"], _rarity_rule(rarity))
            if rarity["visible"]:
                c["material_override"] = {
                    "_MainTex.offset": rarity["atlas_offset"],
                    "_tint_rgb": rarity["tint_rgb"],
                    "source": "UpdateRarityComponent（Actor.cs:Actor.UpdateRarityComponent）",
                }
        elif name == "No_Gem_Mesh":
            # 运行时规则胜过序列化 inactive（序列化失活分支已被上面置 false，此处按规则翻回）
            _vis(c, not rarity["visible"], {
                "rule": "UpdateRarityComponent 地标专属分支（Actor.cs:Actor.UpdateRarityComponent）：IsLocation 且 "
                        "m_rarityNoGemMesh 非空 → SetActive(!rarityTextureOffset)",
                "source": "Actor.cs:Actor.UpdateRarityComponent",
                "tags_used": [int(GameTag.RARITY), int(GameTag.CARDTYPE)],
            }, raster=not rarity["visible"])
            if c["visible"]:
                c["material_override"] = {
                    "_MainTex_runtime": {"image": class_color["atlas_img"],
                                         "atlas_ref": class_color["atlas_ref"]},
                    "source": "SetMaterialWithTexture LOCATION 尾段（Actor.cs:Actor.SetMaterialWithTexture）："
                              "No_Gem_Mesh 材质 mainTexture=类色图集（显式写点）",
                }
        elif name == "Unique_Ally_Dragon":
            _vis(c, is_elite, {
                "rule": "该节点 = m_eliteObject。UpdateEliteComponent (Actor.cs:Actor.UpdateEliteComponent)",
                "source": "Actor.cs:Actor.UpdateEliteComponent",
                "tags_used": [int(GameTag.ELITE)],
            })
        elif name == "Wep_SheildBroken":
            _vis(c, not card.health_display_hidden, {
                "rule": "该节点 = m_healthObject。UpdateHealthTextMesh (Actor.cs:Actor.UpdateHealthTextMesh :3496)："
                        "HasHideStats(HIDE_STATS∨DORMANT)/HIDE_HEALTH → GemObject.Hide()",
                "source": "Actor.cs:Actor.UpdateHealthTextMesh",
                "tags_used": ["HIDE_STATS", "HIDE_HEALTH"],
            })
        elif name == "RacePlate_mesh":
            _vis(c, False, {
                "rule": "UpdateRace（Actor.cs:Actor.UpdateRace）flag7=IsLocation 分支：地标无种族 → 隐藏",
                "source": "Actor.cs:Actor.UpdateRace",
                "tags_used": [int(GameTag.CARDTYPE), "TAG_RACE"],
            })
        elif name in ("RuneHolder_Mesh", "RuneHolder_Shadow_Mesh", "HolderGlow_Tutorial"):
            _vis(c, False, {
                "rule": "UpdateCardRuneBannerComponent 默认 m_cardRuneBanner.Hide()",
                "source": "Actor.cs:Actor.UpdateCardRuneBannerComponent",
                "tags_used": ["HasRuneCost"],
            })
        elif name in ("Shadow", "ShadowUnique"):
            _vis(c, False, {
                "rule": "接触阴影：m_shadowVisible 默认 false（renderer.enabled=false 序列化即证）",
                "source": "Actor.cs:Actor.UpdateContactShadow",
                "tags_used": [],
            })
        elif name.startswith("FX_Ghost_Quad"):
            _vis(c, False, {
                "rule": "幽灵卡特效（renderer.enabled=false 序列化即证）",
                "source": "Actor.cs:Actor.UpdateGhostCardEffect (UpdateGhostCardEffect)",
                "tags_used": [],
            })
        elif name == "Highlight_Card_Plane":
            _vis(c, False, {
                "rule": "高亮盖板：HighlightState 状态机，无高亮不可见",
                "source": "Actor.cs:Actor.UpdateHighlights (UpdateHighlights)",
                "tags_used": [],
            })
        elif name in ("Multiclass_Ribbon_mesh", "Multiclass_Ribbon_Shadow_mesh",
                      "Multiclass_Ribbon_Signature_mesh", "Multiclass_Ribbon_Signature_Shadow_mesh"):
            _vis(c, False, {
                "rule": "多职业缎带：prefab 序列化失活",
                "source": "kit meta active_in_hierarchy 实测",
                "tags_used": ["多职业 tag 族（本卡缺省）"],
            })
        elif name == "Speed_Wing":
            _vis(c, False, {
                "rule": "佣兵战纪速度翼：prefab 序列化失活",
                "source": "kit meta active_in_hierarchy 实测",
                "tags_used": [],
            })
        slots = []
        for m in next(n for n in report["nodes"] if n["path"] == path)\
                .get("components", {}).get("renderer", {}).get("material_slots", []):
            slot = _slot_write(class_color, portrait, binding, m, path)
            if class_color["applied"] and "_MainTex_runtime" not in slot \
                    and path == binding["name_banner_mesh_node"] \
                    and m.get("name") == "Card_Location_InHand_Mat":
                slot["_MainTex_runtime"] = {"image": class_color["atlas_img"],
                                            "atlas_ref": class_color["atlas_ref"],
                                            "source": "与 cardMesh[slot0] 同一 Material 资产 → 共享实例连带类色"}
            if slot.get("slot") == binding["portrait_frame_mat_idx"] \
                    and path == binding["portrait_mesh_node"] \
                    and "_MainTex_runtime" in slot and slot["_MainTex_runtime"].get("atlas_ref"):
                slot["_MainTex_runtime"]["source"] = (
                    "与 cardMesh[slot0] 同一 Material 资产 → 共享实例连带类色")
            slots.append(slot)
        c["material_slots"] = slots
        if path == binding["portrait_mesh_node"]:
            c["portrait_submesh"] = {
                "sub": binding["portrait_mat_idx"],
                "source": "画像窗 = PortraitFrame sub0（11 三角，slot0=portrait 材质）",
            }

    # 共享框体材质 tint 正典化（2026-10-04 landmark-frame-anomaly 定案：shader 无 _Color 槽，
    # 序列化 0.9063 灰系美编遗留——合并式写入，保留组件既有 override 键）
    for c in comps:
        if c.get("node") in _LOCATION_SHARED_NODES:
            c.setdefault("material_override", {})["_tint_rgb"] = [1.0, 1.0, 1.0]

    from eidolon.core.render.game.actor.components import walk_with_key
    stat_gems = _gems.collect_stat_gems(hierarchy, {"components": comps}, walk_with_key)

    bodies = {"cost": str(card.cost), "name": card.name,
              "desc": card.desc_text or "", "durability": durability_text}
    sources = {"cost": "TAG_COST(48)", "name": "Card m_name zhCN",
               "desc": "CardTextBuilder DLL 直调",
               "durability": "TAG_HEALTH(45)=地标耐久（m_healthTextMesh 绑定 "
                             "Wep_SheildBroken/HealthUberText）"}
    texts_plan = []
    for role in ("cost", "name", "desc", "durability"):
        body = bodies[role]
        if not body:
            texts_plan.append({"role": role, "render": False, "reason": "文本为空（缺省/规则隐藏）"})
            continue
        texts_plan.append({"role": role, "render": True, "text": body,
                           "source": sources[role], "apply": _TEXT_APPLY})

    return {
        "meta": {"generator": "eidolon/core/render/game/compiler.py",
                 "frame": "Card_Hand_Location（地标手牌帧）",
                 "compiled_at": _dt.datetime.now().isoformat(timespec="seconds")},
        "input": {"dbf_id": str(dbf_id), "card_id": card_id, "locale": "zhCN", "zone": "HAND"},
        "tags": _plan_tags(card),
        "actor": {"actor_slot": "HAND_LOCATION", "quality": "normal",
                  "asset": actor_ref("normal", "HAND_LOCATION"),
                  "selection_rule": "ActorNames.GetHandActor + TAG_CARDTYPE.cs:TAG_CARDTYPE.LOCATION（LOCATION=39）"},
        "actor_binding": binding,
        "camera": CAMERA_PROVENANCE,
        "class_color": class_color,
        "portrait": portrait,
        "components": comps,
        "rarity_gem": rarity,
        "texts": texts_plan,
        "gem": _gems.plan_gem("Card_Hand_Location", t=DEFAULT_SESSION_T),
        "stat_gems": stat_gems,
    }


# ============================================================================
# hero_play_bacon 帧（hero_render_bacon.compile_plan :78 行为面）
# ============================================================================

def _compile_hero_play_bacon(dbf_id: str, card: Card) -> dict:
    assert int(card.cardtype) == int(CardType.HERO), \
        f"dbf {dbf_id} 非 HERO（CARDTYPE={card.cardtype}）"
    card_id = card.card_id
    k = bacon_kit()
    report, recon = k.report, k.meta
    hierarchy = recon["hierarchy"]
    binding = _binding(report, extra_refs=("m_attackObject", "m_healthObject", "m_armorObject"))
    class_color = _class_color(
        card, None, applied=False,
        apply_note="m_cardFrontMatIdx=-1 → SetMaterialWithTexture 守卫跳过 → 帧不换装"
                   "（BG 英雄全 CLASS=12 NEUTRAL 亦无类色面）")
    portrait = _portrait.plan_portrait(card_id, "Card_Play_Bacon_Hero")
    rarity = _gems.plan_rarity_gem(card)
    frame_active = _frame_active_flags(hierarchy)
    renderer_enabled = _renderer_enabled_map(hierarchy)
    comps = _components_base(report, frame_active)
    for c in comps:
        name, path = c["node"], c["path"]
        if name == "Gem_Attack":
            _vis(c, False, {
                "rule": "UpdateAttackTextMesh 英雄分支（Actor.cs:Actor.UpdateAttackTextMesh）：IsHero 且 ATK==0 → 隐藏",
                "source": "Actor.cs:Actor.UpdateAttackTextMesh",
                "tags_used": ["TAG_ATK(47)"],
            })
        elif name == "Gem_Health":
            _vis(c, False, {
                "rule": "UpdateHealthTextMesh（Actor.cs:Actor.UpdateHealthTextMesh）：IsHero && requires_hero_card && "
                        "m_card==null → Hide",
                "source": "Actor.cs:Actor.UpdateHealthTextMesh",
                "tags_used": [],
            })
        elif name in ("Shadow", "ShadowUnique"):
            enabled = renderer_enabled.get(path, True)
            _vis(c, enabled, {
                "rule": "接触阴影（tag FakeShadow/FakeShadowUnique）：展示态=prefab 序列化 "
                        "renderer.enabled（本帧=%s；Card_Play_Bacon_Hero 与标准 play 帧同款 "
                        "ShadowRenderPlane360/GenFX_CardShadow_Hero）——参照采集链不调 "
                        "Actor.ContactShadow(bool) ⇒ UpdateContactShadow 首行早退 ⇒ 序列化态即展示态"
                        % enabled,
                "source": "prefab 序列化 renderer.enabled（Actor.cs:Actor.UpdateContactShadow 早退语义；"
                          "参照链=tools/alphatool Renderer.CreateActor→UpdateAllComponents 无 ContactShadow 调用）",
                "tags_used": [],
            })
        elif name == "Highlight_Card_Plane":
            _vis(c, False, {
                "rule": "高亮盖板：HighlightState 状态机（序列化 enabled=0 同证）",
                "source": "Actor.cs:Actor.UpdateHighlights (UpdateHighlights)",
                "tags_used": [],
            })
        elif name == "Graveyard_Cracks":
            _vis(c, False, {
                "rule": "renderer.enabled=false（序列化；裂纹层不进光栅）",
                "source": "kit meta renderer enabled 实测",
                "tags_used": [],
            })
        slots = []
        for m in next(n for n in report["nodes"] if n["path"] == path)\
                .get("components", {}).get("renderer", {}).get("material_slots", []):
            slot = {"slot": m["slot"], "material": m.get("name"),
                    "_MainTex": {"name": (m.get("textures", {}).get("_MainTex") or {}).get("name"),
                                 "bundle": (m.get("textures", {}).get("_MainTex") or {}).get("bundle")}}
            if path == binding["portrait_mesh_node"] and m["slot"] == binding["portrait_mat_idx"]:
                slot["_MainTex_runtime"] = {"image": portrait["img"],
                                            "source": "CardDef.m_PortraitTexturePath；本 sub 走肖像公式层"}
            slots.append(slot)
        c["material_slots"] = slots
        if path == binding["portrait_mesh_node"]:
            c["portrait_submesh"] = {
                "sub": binding["portrait_mat_idx"],
                "source": "肖像/帧合成面 = Mesh sub0（Hero_Mesh_Portrait 18 tri 单材质）",
            }

    # 肖像公式层参数（kit 层级 Mesh slot0 材质序列化直读——plan_portrait_render 承担）
    texts_plan = [
        {"role": "attack", "render": False,
         "reason": "英雄分支 ATK==0 → m_attackObject 隐藏（Actor.cs:Actor.UpdateAttackTextMesh）"},
        {"role": "health", "render": False,
         "reason": "IsHero && m_healthDisplayRequiresHeroCard(默认 true :403) && m_card==null → 隐藏"},
    ]
    return {
        "meta": {"generator": "eidolon/core/render/game/compiler.py",
                 "frame": "Card_Play_Bacon_Hero（BG 英雄对局帧）+ Bacon_HeroFrame_Default rig",
                 "compiled_at": _dt.datetime.now().isoformat(timespec="seconds")},
        "input": {"dbf_id": str(dbf_id), "card_id": card_id, "locale": "zhCN", "zone": "PLAY"},
        "tags": _plan_tags(card),
        "actor": {"actor_slot": "PLAY_HERO", "quality": "normal",
                  "asset": "Card_Play_Bacon_Hero.prefab（ActorNames.cs:ActorNames.GetPlayActorByTags 字面 prefab 引用）",
                  "selection_rule": "ActorNames.GetPlayActorByTags BATTLEGROUNDS_HERO leg"},
        "actor_binding": binding,
        "camera": CAMERA_PROVENANCE,
        "class_color": class_color,
        "portrait": portrait,
        "components": comps,
        "rarity_gem": rarity,
        "texts": texts_plan,
        "gem": _gems.plan_gem("Card_Play_Bacon_Hero", t=DEFAULT_SESSION_T),
        "portrait_render": _portrait.plan_portrait_render("Card_Play_Bacon_Hero"),
        "frame_rig": {"source": recon.get("frame_rig", {}),
                      "note": "rig 渲染注入 = actor.injectors.apply_injections 接线段"
                              "（宿主=portrait_mesh_node，localPos=(0,0.1,0) 引擎逐字）"},
    }


# ============================================================================
# trinket 帧（Card_Hand_BG_Trinket；bg-ct40-43-44-routing 2026-10-24）
# ============================================================================

def _trinket_race_text(card: Card) -> tuple[str, int, dict]:
    """GetRaceText trinket 路（EntityBase.cs:1264 IsBattlegroundTrinket 支→BuildRaceText）
    + UpdateRace 族板判式（Actor.cs:Actor.UpdateRace flag6→flag7 支）。

    races=Card.races trinket 分支（GetRacesForTrinket EntityBase.cs:1146-1165 正典，
    infra 单实现）；文本=GetRaceName 逐种族 "\\n" 连接（与 ally 同串表）。
    race id→GLOBAL_RACE_* 键=数据面（infra.game_strings，decomp 直读；
    race-names-data 2026-11-01 去 hosted 反射）；解析响亮面=_race_display_name
    （residual-silent-fallbacks 2026-11-05——未知 id/缺本地化禁渲 UNKNOWN）。

    Eidolon 覆盖座位（core-integration §7.5）：与 _race_text_and_count 同构
    （消费点 2/3）。"""
    if getattr(card, "races_text_override", None) is not None:
        text = "\n".join(card.races_text_override)
        return text, len(card.races_text_override), {"source": "eidolon.races_override"}
    strings = kit("trinket").races["strings"]
    races = list(card.races)
    names = [_race_display_name(strings, r) for r in races]
    text = "\n".join(names)
    rule = {"rule": "饰品：races=GetRacesForTrinket 正典（BACON_SUBSET_* 布尔 tag→"
                    "TAG_RACE，ALL 早退）；plate 显隐 = 文本非空且 GetRaceCount()==1"
                    "（单板）/ >1（宽板）——UpdateRace flag6=IsBattlegroundTrinket 支",
            "source": "Actor.cs:Actor.UpdateRace (UpdateRace); EntityBase.cs:EntityBase"
                      " GetRacesForTrinket/:1264 GetRaceText",
            "tags_used": ["BACON_SUBSET_*（1591-1596/1688/1845/2272/2347/2630/3436/4757）"],
            "races": races}
    return text, len(races), rule


def _compile_trinket(dbf_id: str, card: Card) -> dict:
    """trinket 帧（Card_Hand_BG_Trinket；ct44 手牌大卡帧，ActorNames.cs:568-569）。

    帧形（prefab probe 实测）：主网格=NonQuestObjects/Mesh 双槽（slot0=
    BG_Trinket_BigCard_FramePortrait_Mat 肖像窗 Unlit_Portrait 白占位、slot1=
    Battlegrounds_Trinket_Frame 紫幡帧底）；FrameMesh=框饰环；文字区四矩形
    （feature-corpus TRINKET_MASK 定案）=硬币费用/名牌/desc/族学牌；章环
    （TrinketLevelIndicatorRing 子树）=大小饰品章面换装；金币件=btf 表 145 专用件
    （injectors want_coin_trinket 腿，采集链 AlphaTool.Renderer.cs:191-201）。
    """
    assert int(card.cardtype) == int(CardType.BATTLEGROUND_TRINKET), \
        f"dbf {dbf_id} 非 BATTLEGROUND_TRINKET（CARDTYPE={card.cardtype}）"
    card_id = card.card_id
    k = kit("trinket")
    report, hierarchy = k.report, k.meta["hierarchy"]
    binding = _binding(report, extra_refs=("m_racePlateObject", "m_multiRacePlateObject",
                                           "m_trinketLevelIndicator",
                                           "m_trinketLevelPortraitMesh"))
    # 肖像绑定修正（界外回退腿落地）：_binding 直读序列化标量（m_portraitMesh=
    # FrameMesh / m_portraitMatIdx=1——FrameMesh 单材质，主腿越界）；引擎
    # GetPortraitMaterial（Actor.cs:3197-3215）回退 m_legacyPortraitMaterialIndex=
    # Mesh slot0（AssignMaterials "Portrait" 材质名扫描，portrait_binding 回退腿
    # 已转写）。_binding 为十编译器公共形不动，本编译器按回退腿覆写两键。
    _pb = _portrait.portrait_binding("Card_Hand_BG_Trinket")
    binding["portrait_mesh_node"] = _pb["node"]
    binding["portrait_mat_idx"] = _pb["sub"]
    binding["portrait_binding_source"] = _pb.get("binding_source")
    # 类色账：UpdateCardColor ct44→TYPE_BATTLEGROUNDS_TRINKET_FRIENDLY（FRIENDLY 侧，
    # Actor.cs:6530）→ GetTexture(ct44,43)=Trinket_Hand_BigCard_Player（CardColorSwitcher
    # 族表 idx44，probe/color 实测）——写 m_cardMesh[0]._MainTex（SetMaterialWithTexture
    # :6822-6830）与该槽序列化 _MainTex 同名同资产 ⇒ 写点幂等，帧保持序列化纹理
    # （离线不落图集写点；NEUTRAL 类色的 GetColorTypeForClass=GENERIC 轴不适用 ct44）。
    class_color = _class_color(
        card, None,
        apply_note="SetMaterialWithTexture（Actor.cs:Actor.SetMaterialWithTexture）ct44："
                   "GetTexture(BATTLEGROUND_TRINKET, TYPE_BATTLEGROUNDS_TRINKET_FRIENDLY)"
                   "=Trinket_Hand_BigCard_Player == cardMesh[0] 序列化 _MainTex（幂等写点，"
                   "帧保持序列化纹理；CardColorSwitcher.cs:253-255 族表 idx44）")
    portrait = _portrait.plan_portrait(card_id, "Card_Hand_BG_Trinket")
    rarity = _gems.plan_rarity_gem(card)
    race_text, race_count, race_rule = _trinket_race_text(card)

    # 章环（UpdateBaconTrinketComponents Actor.cs:5460-5483；调用位 UpdateAllComponents
    # 流 :2043）：isBaconTrinket = IsBattlegroundTrinket ∧ SPELL_SCHOOL∈{LESSER_TRINKET(11),
    # GREATER_TRINKET(12)}（GetTrinketLevel :5425-5449）→ m_trinketLevelIndicator
    # SetActive + m_trinketLevelPortraitMesh materials[0] = m_lesser/greaterTrinketMaterial
    # （PickTrinketMaterial :5452-5458）。
    school = int(card.spell_school)
    level_field = {int(SpellSchool.LESSER_TRINKET): "m_lesserTrinketMaterial",
                   int(SpellSchool.GREATER_TRINKET): "m_greaterTrinketMaterial"}.get(school)
    level_mats = k.meta.get("trinket_level_mats") or {}
    level_mat = level_mats.get(level_field) if level_field else None
    if level_field and not level_mat:
        raise KeyError(f"kit meta 无 {level_field} 章面材质账（trinket_level_mats="
                       f"{sorted(level_mats)}）——kit 提取账漂移")

    frame_active = _frame_active_flags(hierarchy)
    renderer_enabled = _renderer_enabled_map(hierarchy)
    comps = _components_base(report, frame_active)
    is_elite = bool(card.elite)
    medallion_comp = None
    for c in comps:
        name, path = c["node"], c["path"]
        if name == "Mesh" and path == binding["portrait_mesh_node"]:
            # 肖像窗 = Mesh slot0（BG_Trinket_BigCard_FramePortrait_Mat，Unlit_Portrait
            # 白占位 6 tri）——绑定=portrait_binding 界外回退腿（GetPortraitMaterial
            # legacy 槽，Actor.cs:3197-3215 × AssignMaterials :7945-7968）。
            c["portrait_submesh"] = {
                "sub": binding["portrait_mat_idx"],
                "source": "肖像窗 = Mesh slot0（Unlit_Portrait 白占位；m_portraitMesh="
                          "FrameMesh/m_portraitMatIdx=1 界外 → GetPortraitMaterial "
                          "m_legacyPortraitMaterialIndex 回退）",
            }
        elif name == "Trinket_Medallion_Portrait_Mesh":
            _vis(c, level_mat is not None, {
                "rule": "该节点 = m_trinketLevelPortraitMesh。UpdateBaconTrinketComponents"
                        "（Actor.cs:Actor.UpdateBaconTrinketComponents）：isBaconTrinket="
                        "IsBattlegroundTrinket ∧ SPELL_SCHOOL∈{11,12} → m_trinketLevelIndicator"
                        " SetActive + 本节点 materials[0]=PickTrinketMaterial（lesser/greater）",
                "source": "Actor.cs:Actor.UpdateBaconTrinketComponents + GetTrinketLevel"
                          " :5425-5449 + PickTrinketMaterial :5452-5458",
                "tags_used": [int(GameTag.CARDTYPE), int(GameTag.SPELL_SCHOOL)],
            })
            medallion_comp = c if c["visible"] and level_mat else None
        elif name == "Trinket_Medallion_Shadow_Mesh":
            # 章环影（multiply）随父 GO SetActive 同步显隐（UpdateBaconTrinketComponents
            # 只 SetActive m_trinketLevelIndicator 根 GO，子树整体跟随）
            _vis(c, level_mat is not None, {
                "rule": "章环影：TrinketLevelIndicatorRing 根 GO SetActive（UpdateBaconTrinket"
                        "Components）子树跟随——显隐与章面同判（SPELL_SCHOOL 11/12）",
                "source": "Actor.cs:Actor.UpdateBaconTrinketComponents（根 GO SetActive 语义）",
                "tags_used": [int(GameTag.CARDTYPE), int(GameTag.SPELL_SCHOOL)],
            })
        elif name == "RacePlate_mesh":
            _vis(c, bool(race_text) and race_count == 1, race_rule)
        elif name == "Multi_RacePlate_mesh":
            _vis(c, bool(race_text) and race_count > 1, {
                "rule": "UpdateRace：多 race（GetRaceCount()>1）才 SetActive 宽板与"
                        " m_multiRaceTextMesh（trinket flag7 支同构）",
                "source": race_rule["source"],
                "tags_used": ["BACON_SUBSET_*"],
            })
        elif name == "Shadow":
            enabled = renderer_enabled.get(path, True)
            _vis(c, enabled, {
                "rule": "接触阴影（tag FakeShadow）：展示态=prefab 序列化 renderer.enabled"
                        "（本帧=%s）——参照采集链不调 Actor.ContactShadow(bool) ⇒ "
                        "UpdateContactShadow 首行早退 ⇒ 序列化态即展示态（hero-play-frame 先例）"
                        % enabled,
                "source": "prefab 序列化 renderer.enabled（Actor.cs:Actor.UpdateContactShadow"
                          " 早退语义；参照链=AlphaTool.Renderer.CreateActor→UpdateAllComponents"
                          " 无 ContactShadow 调用）",
                "tags_used": [],
            })
        elif name == "ShadowUnique":
            _vis(c, False, {
                "rule": "接触阴影变体：renderer.enabled=false（序列化即证）",
                "source": "kit meta renderer enabled 实测",
                "tags_used": [],
            })
        elif name == "InHand_Ability_Unique_Dragon":
            # m_eliteObject（"Mesh Old" 失活子树内）——UpdateEliteComponent 门存在但
            # 该 prefab 置于序列化失活子树（prefab probe 实测），Elite trinket 语料零
            # 命中；双保险=IsElite 判定 ∧ 序列化失活态。
            _vis(c, is_elite and frame_active.get(path, True), {
                "rule": "该节点 = m_eliteObject。UpdateEliteComponent "
                        "(Actor.cs:Actor.UpdateEliteComponent)：EnableRenderers(m_eliteObject, "
                        "IsElite())；本 prefab 该节点在序列化失活子树（Mesh Old）内",
                "source": "Actor.cs:Actor.UpdateEliteComponent + kit meta active_in_hierarchy",
                "tags_used": [int(GameTag.ELITE)],
            })
        elif name == "Highlight_Card_Plane":
            _vis(c, False, {
                "rule": "高亮盖板：HighlightState 状态机（序列化 enabled=0 同证）",
                "source": "Actor.cs:Actor.UpdateHighlights (UpdateHighlights)",
                "tags_used": [],
            })
        elif name.startswith("FX_Ghost_Quad"):
            _vis(c, False, {
                "rule": "幽灵卡特效：m_ghostCard 默认 NONE → DisableGhost（序列化 enabled=0 同证）",
                "source": "Actor.cs:Actor.UpdateGhostCardEffect (UpdateGhostCardEffect)",
                "tags_used": [],
            })
        elif name == "Speed_Wing":
            _vis(c, False, {
                "rule": "佣兵战纪速度翼：prefab 序列化失活",
                "source": "kit meta active_in_hierarchy 实测",
                "tags_used": [],
            })
        slots = []
        for m in next(n for n in report["nodes"] if n["path"] == path)\
                .get("components", {}).get("renderer", {}).get("material_slots", []):
            slots.append(_slot_write(class_color, portrait, binding, m, path))
        c["material_slots"] = slots

    # 章面换装写点（slots 装配后落位——UpdateBaconTrinketComponents materials[0] 替换；
    # 引擎写的是整材质引用，我方离线形=章面槽 _MainTex 运行时写点 + 新材质 _Color 随行
    # （slot material_override._tint_rgb）——被换槽序列化 _Color=[0,0,0,1] 黑，不随行
    # 会染黑章面；两材质均单槽 Hero/Unlit/Unlit_Texture、_MainTex 唯一视觉面）。
    if medallion_comp is not None and level_mat:
        slot0 = next((s for s in medallion_comp.get("material_slots", [])
                      if s.get("slot") == 0), None)
        assert slot0 is not None, "章盘节点无 slot0 材质账（kit report 形态漂移）"
        slot0["_MainTex_runtime"] = {
            "image": k.textures[level_mat["main_tex_file"]],
            "source": f"UpdateBaconTrinketComponents 章面换装（{level_field}="
                      f"{level_mat['material']}，kit 外部材质解引用）",
        }
        slot0["material_override"] = {
            "_tint_rgb": list(level_mat["color"][:3]),
            "source": "整材质换装随行色（BaconTrinket*Material _Color；被换槽序列化"
                      " _Color=[0,0,0,1] 黑）",
        }

    from eidolon.core.render.game.actor.components import walk_with_key  # 环避让（S11 执行面单源）
    stat_gems = _gems.collect_stat_gems(hierarchy, {"components": comps}, walk_with_key)

    race_role = "race_multi" if race_count > 1 else "race"
    bodies = {"cost": str(card.cost), "name": card.name, "desc": card.desc_text or "",
              "race": race_text}
    sources = {
        "cost": "TAG_COST(48)（硬币语境数字面；金币件=SpellTable 槽 145 注入，"
                "AlphaTool.Renderer.cs:191-201 trinket leg）",
        "name": "Card m_name zhCN", "desc": "CardTextBuilder DLL 直调",
        "race": "GetRacesForTrinket 正典 → GetRaceName → GLOBAL_RACE_* zhCN"
                "（EntityBase.cs:1146-1165/:1264）",
        "race_multi": "同 race 文本（引擎同一 text 写宽板 UberText，Actor.cs:Actor.UpdateRace）",
    }
    texts_plan = []
    for role in ("cost", "name", "desc", "race"):
        body = bodies[role]
        if not body:
            texts_plan.append({"role": role, "render": False,
                               "reason": "文本为空（GetRacesForTrinket 空=无 BACON_SUBSET_* "
                                         "tag → 族板隐藏，UpdateRace flag8=false）"
                               if role == "race" else "文本为空（缺省/规则隐藏）"})
            continue
        entry_role = race_role if role == "race" else role
        texts_plan.append({"role": entry_role, "render": True, "text": body,
                           "source": sources[entry_role], "apply": _TEXT_APPLY})

    return {
        "meta": {"generator": "eidolon/core/render/game/compiler.py",
                 "frame": "Card_Hand_BG_Trinket（BG 饰品手牌帧）",
                 "compiled_at": _dt.datetime.now().isoformat(timespec="seconds")},
        "input": {"dbf_id": str(dbf_id), "card_id": card_id, "locale": "zhCN", "zone": "HAND"},
        "tags": _plan_tags(card),
        "actor": _actor_selection(card.cardtype, card.premium),
        "actor_binding": binding,
        "camera": CAMERA_PROVENANCE,
        "class_color": class_color,
        "portrait": portrait,
        "components": comps,
        "rarity_gem": rarity,
        "texts": texts_plan,
        "gem": _gems.plan_gem("Card_Hand_BG_Trinket", t=DEFAULT_SESSION_T),
        "stat_gems": stat_gems,
    }


# ============================================================================
# anomaly 帧（Card_Hand_BG_Anomaly；bg-ct40-43-44-routing 2026-10-24 ct43 轮）
# ============================================================================

def _compile_anomaly(dbf_id: str, card: Card) -> dict:
    """anomaly 帧（Card_Hand_BG_Anomaly；ct43 手牌大卡帧，ActorNames.cs:570-571）。

    帧形（prefab probe 实测）=Card_Hand_Ability 族变体：主网格 Mesh 双槽（slot0=
    Card_Inhand_Ability_Anomaly 紫幡帧底、slot1=GenFX_Card_Back_Default_D 卡背壳
    〔几何级排除，NON_RASTER_MATERIALS〕）；Description_mesh 序列化网格=
    Card_InHand_Ability_Description_Neutral_mesh（ct43 非 SPELL/BaconSpell/Lettuce
    →UpdateRace flag2/flag5 false 无学派网格替换，保持序列化，Actor.cs:UpdateRace
    :6326-6333）；PortraitFrame_mesh=ability 同资产（肖像窗=slot1 主腿）。文字区
    两矩形（feature-corpus ANOMALY_MASK 定案）=名牌+desc 板；**费用无数字位**
    （CostObject 子树序列化失活=展示态——UpdateManaGemComponent 只 SetActive(false)
    从不激活，Actor.cs:5217-5231；采集链金币腿四判式不含 ct43，
    AlphaTool.Renderer.cs:190-201）；金币件/盾徽零注入（want_* 判式结构性排除）。
    卡体外光环带（Card_Play_BG_Anomaly_Highlight：Mesh_Glow_Backer builtin mesh+
    PS_Shards 粒子）=氛围动画——feature-corpus p2c 批畸变豁免（REF_WAIVERS
    101954/132530，NOTES 99 行附近）登记不追保真，卡体内（帧/文字）仍对拍。
    """
    assert int(card.cardtype) == int(CardType.BATTLEGROUND_ANOMALY), \
        f"dbf {dbf_id} 非 BATTLEGROUND_ANOMALY（CARDTYPE={card.cardtype}）"
    card_id = card.card_id
    k = kit("anomaly")
    report, hierarchy = k.report, k.meta["hierarchy"]
    binding = _binding(report)
    # 类色账：UpdateCardColor ct43 缺省腿 GetColorTypeForClass(NEUTRAL)=GENERIC(0)
    # → GetTexture(43, 0)=battlegroundsAnomalyCardTextures[0]=Card_Inhand_Ability_
    # Anomaly.tif（color probe 实测全 45 槽同纹理）——与 cardMesh[0] 序列化 _MainTex
    # 同资产 ⇒ SetMaterialWithTexture（Actor.cs:6792-6836）写点幂等，帧保持序列化
    # 纹理（trinket ct44 同款；NEUTRAL 类色轴不适用 ct43）。
    class_color = _class_color(
        card, None,
        apply_note="SetMaterialWithTexture（Actor.cs:Actor.SetMaterialWithTexture）ct43："
                   "GetTexture(BATTLEGROUND_ANOMALY, TYPE_GENERIC)=Card_Inhand_Ability_"
                   "Anomaly.tif == cardMesh[0] 序列化 _MainTex（幂等写点——族表全 45 槽"
                   "同纹理，probe 实测；帧保持序列化纹理）")
    portrait = _portrait.plan_portrait(card_id, "Card_Hand_BG_Anomaly")
    rarity = _gems.plan_rarity_gem(card)
    frame_active = _frame_active_flags(hierarchy)
    renderer_enabled = _renderer_enabled_map(hierarchy)
    comps = _components_base(report, frame_active)
    is_elite = bool(card.elite)
    for c in comps:
        name, path = c["node"], c["path"]
        if name in ("RarityFrame_mesh", "RarityGem"):
            # UpdateRarityComponent（Actor.cs:4961-5010）：GetRarityTextureOffset
            # rarity=0 返 false → EnableRenderers(m_rarityGem/FrameMesh, false)——
            # 稀有度件随 rarity 数据驱动显隐（101954 rarity=0 双隐）。
            _vis(c, rarity["visible"], _rarity_rule(rarity))
            if name == "RarityGem" and rarity["visible"]:
                c["material_override"] = {
                    "_MainTex.offset": rarity["atlas_offset"],
                    "_tint_rgb": rarity["tint_rgb"],
                    "source": "GetRarityTextureOffset → material.mainTextureOffset/_tint"
                              "（Actor.cs:Actor.GetRarityTextureOffset, 常量 :101-115）",
                }
        elif name in ("InHand_Ability_Unique_Dragon", "InHand_Ability_Unique_Dragon_shadow"):
            # UpdateEliteComponent（Actor.cs:5192-5198）EnableRenderers(m_eliteObject,
            # IsElite(), includeInactive: true)——含失活扫描，精英卡会开序列化
            # enabled=false 的渲染器（ability 链 suppress 语义同源）；本批 rarity 语料
            # elite=0 隐藏。龙影子节点随父 m_eliteObject 同门（includeInactive 扫描面）。
            _vis(c, is_elite, {
                "rule": "该节点 = m_eliteObject 子树。UpdateEliteComponent "
                        "(Actor.cs:Actor.UpdateEliteComponent)：EnableRenderers"
                        "(m_eliteObject, IsElite(), includeInactive: true)",
                "source": "Actor.cs:Actor.UpdateEliteComponent + :1365-1384 (IsElite)",
                "tags_used": [int(GameTag.ELITE)],
            })
        elif name in ("RuneHolder_Mesh", "RuneHolder_Shadow_Mesh"):
            _vis(c, False, {
                "rule": "UpdateCardRuneBannerComponent 默认 m_cardRuneBanner.Hide()，"
                        "仅 HasRuneCost（DK 符文费）才 Show（prefab 序列化失活子树同证）",
                "source": "Actor.cs:Actor.UpdateCardRuneBannerComponent",
                "tags_used": ["HasRuneCost(符文费 tag 族，非 DK 恒缺)"],
            })
        elif name in ("Shadow", "ShadowUnique"):
            _vis(c, False, {
                "rule": "接触阴影：m_shadowVisible 默认 false，仅 ContactShadow(true)才显；"
                        "AlphaTool 静态快照不调 → renderer.enabled=false（序列化同证）",
                "source": "Actor.cs:Actor.ContactShadow + :4852-4866；字段默认 :430",
                "tags_used": [],
            })
        elif name == "FX_Ghost_Quad":
            _vis(c, False, {
                "rule": "幽灵卡特效：m_ghostCard 默认 NONE → DisableGhost",
                "source": "Actor.cs:Actor.UpdateGhostCardEffect (UpdateGhostCardEffect)",
                "tags_used": [],
            })
        elif name == "Highlight_Card_Plane":
            _vis(c, False, {
                "rule": "高亮盖板：HighlightState 组件运行时状态机控制（序列化 enabled=0 同证）",
                "source": "Actor.cs:Actor.UpdateHighlights (UpdateHighlights → HighlightState)",
                "tags_used": [],
            })
        elif name == "Card_InHand_Ally_CurvedText":
            c["raster"] = False
            c["role"] = ("name 文字 RTT 载体网格（AbilityCardCurvedText 资产，与 ability 帧"
                         "同）：m_RenderToTexture 路径由 uber_text 模块按网格 UV 贴回；"
                         "无自身材质故不参与帧光栅")
            c["visibility_rule"] = {
                "rule": "NameUberText.m_RenderToTexture=1 → 文字渲进 RT、按本网格 UV 贴回卡面"
                        "（UberText.cs:UberText.SetupRenderToTexture）",
                "source": "text-rendering-pipeline.md §弧面；uber_text._render_rtt",
                "tags_used": [],
            }
        elif name == "Mesh_Glow_Backer":
            # 光环衬板（Card_Play_BG_Anomaly_Highlight 子树，序列化 active+enabled=
            # 展示态）：mesh=Unity builtin（probe issues——无离线提取面），伴生
            # PS_Shards 粒子（无 mesh 组件）。=卡体外氛围动画带，按 feature-corpus
            # p2c 批畸变豁免（REF_WAIVERS 101954/132530）登记不追保真：热图实证
            # 差异全在卡体外光环带，卡体内（帧/文字）不受影响。
            c["raster"] = False
            c["visible"] = False
            c["visibility_rule"] = {
                "rule": "畸变卡光环带（紫色光环+漂浮碎片=氛围动画）：Mesh_Glow_Backer "
                        "mesh=builtin（离线无提取面）+PS_Shards 粒子不可冻结复刻——"
                        "既有豁免先例登记（feature-corpus p2c 批 REF_WAIVERS 101954/"
                        "132530），卡体外光环带差异不追保真",
                "source": "feature-corpus p2c 批畸变豁免登记（REF_WAIVERS 101954/132530；"
                          "NOTES 分批进度账 p2c 行）+ anomaly_prefab_probe.json issues"
                          "（builtin mesh）",
                "tags_used": [int(GameTag.CARDTYPE)],
            }
        slots = []
        for m in next(n for n in report["nodes"] if n["path"] == path)\
                .get("components", {}).get("renderer", {}).get("material_slots", []):
            slots.append(_slot_write(class_color, portrait, binding, m, path))
        c["material_slots"] = slots
        if path == binding["description_mesh_node"]:
            # ct43 无学派网格替换（UpdateRace flag2/flag5 false）——与 ability 的
            # neutral/school 换装分叉不同，运行时恒=序列化网格（neutral 资产）。
            c["mesh"] = {
                "serialized": "Card_InHand_Ability_Description_Neutral_mesh",
                "runtime": "serialized",
                "source": "UpdateRace（Actor.cs:Actor.UpdateRace）flag2=IsSpell∨IsBaconSpell"
                          " ∧ flag5=IsLettuceAbility 均 false（ct43）→ 无学派网格替换，"
                          "保持序列化 neutral 网格",
                "tags_used": [int(GameTag.CARDTYPE), int(GameTag.SPELL_SCHOOL)],
            }
    # 金币/水晶面（ct43 双无）：CostObject 子树序列化失活（CostUberText/Gem_Mana
    # 均在内，_components_base 已标隐）=展示态——引擎 UpdateManaGemComponent
    # （Actor.cs:5217-5231）对 m_manaObject 只 SetActive(false) 从不激活；采集链
    # 金币腿四判式（IsSpell/IsHeroPower/IsBattlegroundTrinket/IsBattlegroundQuestReward，
    # AlphaTool.Renderer.cs:190-201）不含 ct43 → 无金币件注入。gem 键 enabled=False
    # 关水晶公式层（plan_gem 主腿按 m_manaObject 在位给 True——此处按展示态覆写）。
    gem = _gems.plan_gem("Card_Hand_BG_Anomaly", t=DEFAULT_SESSION_T)
    gem["enabled"] = False
    gem["visibility_rule"] = (
        "CostObject 子树序列化失活=展示态（费用无数字位；ANOMALY_MASK 无 cost 矩形）——"
        "UpdateManaGemComponent 只 SetActive(false) 从不激活（Actor.cs:5217-5231）；"
        "金币件不注入（采集链 AlphaTool.Renderer.cs:190-201 金币腿不含 ct43）")

    texts_plan = [
        {"role": "cost", "render": False,
         "reason": "CostObject 序列化失活（费用无数字位）——cost 文本不展示"},
        {"role": "name", "render": True, "text": card.name,
         "source": "Card m_name zhCN", "apply": _TEXT_APPLY},
        {"role": "desc", "render": True, "text": card.text,
         "source": "Card m_textinhand zhCN（prep 换轨 CardTextBuilder）", "apply": _TEXT_APPLY},
        {"role": "plate", "render": False,
         "reason": "UpdateRace（Actor.cs:Actor.UpdateRace）：ct43 无种族/学派文本"
                   "（GetRaceText 空 → flag8 false → m_raceTextMesh SetActive(false)）"},
    ]

    return {
        "meta": {"generator": "eidolon/core/render/game/compiler.py",
                 "frame": "Card_Hand_BG_Anomaly（BG 畸变手牌大卡帧）",
                 "compiled_at": _dt.datetime.now().isoformat(timespec="seconds")},
        "input": {"dbf_id": str(dbf_id), "card_id": card_id, "locale": "zhCN", "zone": "HAND"},
        "tags": _plan_tags(card),
        "actor": _actor_selection(card.cardtype, card.premium),
        "actor_binding": binding,
        "camera": CAMERA_PROVENANCE,
        "class_color": class_color,
        "portrait": portrait,
        "components": comps,
        "rarity_gem": rarity,
        "texts": texts_plan,
        "gem": gem,
    }


_BUILDERS = {  # consumer-v2 改键=prefab 名（spell_dk 行消亡）；kit() 参数=supply 命名空间不动
    "Card_Hand_Ability": _compile_ability,
    "Card_Hand_Ability_Premium": lambda dbf, card: _compile_ability(dbf, card, premium=True),
    "Card_Hand_Ally": _compile_ally,
    "Card_Hand_Ally_Premium": lambda dbf, card: _compile_ally(dbf, card, premium=True),
    "Card_Hand_Weapon": _compile_weapon,
    "Card_Hand_Hero": lambda dbf, card: _compile_hero("hand", dbf, card),
    "Card_Play_Hero": lambda dbf, card: _compile_hero("play", dbf, card),
    "History_HeroPower": _compile_heropower, "Card_Hand_Location": _compile_location,
    "Card_Play_Bacon_Hero": _compile_hero_play_bacon,
    "Card_Hand_BG_Trinket": _compile_trinket,
    "Card_Hand_BG_Anomaly": _compile_anomaly,
}


def _exclude_non_raster_components(plan: dict) -> list[dict]:
    """按材质名从组件清单里排除**永不参与本链展示态**的几何（2026-10-16）。

    逐组件看 `material_slots[].material`：槽材质全属 `NON_RASTER_MATERIALS` ⟹ 整件标
    `visible/raster=False`（构形记来源）；混合槽（如 `Mesh` = slot0 卡面 + slot1 卡背壳）
    ⟹ 记入 `plan["_raster_skip_materials"]`，由 `build_render_list` 的 submesh 级过滤
    与 `raster.raster_bucket_zbuf_unified(skip_materials=)` 各自消费（同一集合，计划级单源）。

    返回被排除的组件账（`node`/`path`/`materials`），供 `render_with` 落 log 复核。
    """
    excluded: list[dict] = []
    skip: set[str] = set()
    for c in plan.get("components") or []:
        slots = c.get("material_slots") or []
        names = {s.get("material") for s in slots if s.get("material")}
        hit = names & NON_RASTER_MATERIALS
        if not hit:
            continue
        whole = bool(slots) and names <= NON_RASTER_MATERIALS
        if whole:
            c["visible"] = False
            c["raster"] = False
            c["visibility_rule"] = {
                "rule": f"材质 {sorted(hit)} 在本链支持的展示态下恒不可见（卡背壳："
                        "引擎 Cull Back 恒剔 + 我方不渲染翻面态）→ 整件不进清单",
                "source": "用户裁决 2026-10-16 + 材质状态表 primary_cull=2.0 + 三态语料 133 卡"
                          "零劣化验证（账见 docs/notes/scene-compiler-mvp.md §渲染正典）",
                "tags_used": [],
            }
        else:
            skip |= hit
        excluded.append({"node": c.get("node"), "path": c.get("path"),
                         "materials": sorted(hit),
                         "mode": "whole-node" if whole else "submesh"})
    if skip:
        plan["_raster_skip_materials"] = sorted(skip)
    return excluded


@invented(reason="七编译器统一形+计划级注入编排（组件生命周期不复刻，形态边界 §0.4）", counterpart="Actor.cs UpdateAllComponents 判定序")
def compile_plan(key: str, dbf_id, card: Card | None = None) -> dict:
    """统一编译入口：desc["compile"](dbf, card) 对位（old_frames/render_card.py:627）——
    帧键分派七编译器统一形（spell/spell_dk 同链同函数，old :351 同构）。

    消费须在 supply session 内（头注纪律）。未知帧键 assert 响亮（tripwire 纪律）。
    末段统一挂 `_exclude_non_raster_components`（九链同一处生效，免逐链改）。"""
    builder = _BUILDERS.get(key)
    assert builder is not None, (
        f"未知帧键 {key!r}——compile_plan 无此键（开放位={sorted(_BUILDERS)}）")
    card = card if card is not None else Card.from_dbf(int(dbf_id))
    plan = builder(str(dbf_id), card)
    excluded = _exclude_non_raster_components(plan)
    if excluded:
        plan["non_raster_excluded"] = excluded
    return plan


# ============================================================================
# prep（old_plan/prep_plan.py:91 换轨；S6 相位/费用语义注入）
# ============================================================================

def _shim_desc_texts(plan: dict, card: Card) -> None:
    """desc 文本源换轨 Card 门面（prep_plan._shim_desc_texts :17 同构）。

    文本源按 Card.text_builder_type 路由（吃进 Card 吐字符串）：route="py" = builder
    40/45 的 Python EntityDef 静态实现（不构造游戏 builder）；route="dll" = pythonnet
    直调游戏 CardTextBuilder。text_degraded 恒 False（静默降级路径已删，键形态保留）。"""
    for e in plan["texts"]:
        if e.get("role") != "desc":
            continue
        acc = card.desc_text_account
        e["source_pre_shim"] = e.get("source")
        e["text"] = acc["text"]
        e["text_builder"] = acc["builder"]
        e["text_builder_type"] = acc["builder_type"]
        e["text_degraded"] = acc["degraded"]
        if acc.get("route") == "py":
            e["source"] = ("CardTextBuilder Python EntityDef 静态路由（infra/text_shim.py；"
                           f"builder={acc['builder']} type={acc['builder_type']}）")
        else:
            e["source"] = ("CardTextBuilder DLL 直调（infra/text_shim.py；builder="
                           f"{acc['builder']} type={acc['builder_type']}）")


@invented(reason="prep 换轨编排（相位/费用语义 compile 期化）", counterpart="UpdateCostTextMesh/UpdateManaGemOffset 判定")
def prep_plan(plan: dict, *, t_phase: float, notext: bool, frame_key: str,
              textonly: bool = False, card: Card | None = None,
              session_time: float | None = None) -> dict:
    """渲染前的正典准备（prep_plan :91 逐支换轨）：宝石相位注入 → desc 文本源换轨
    → 费用文本语义（S6 gems.cost_text_semantics 判定面消费+计划写点）→ 无字口径
    → 只渲字口径。顺序有义：隐藏判定须在三态过滤前（隐藏在三态全一致）；
    t=语料时刻（_Time.x 冻结值）。

    session_time（2026-10-25 tz 代实测修正）：宝石云纹相位=引擎 **C# 冻结时刻**
    （UberShaderController 族 m_time 是 C# 侧时间累计，shader 全局钉不到它，freeze 停
    在 frozen_p/20）。缺省 None → 降级 t_phase（旧行为逐位）。实证=tz 代 full
    128/131 红全系 z_rarity_gem 8-16：cand t=0.0 云纹相位离引擎 0.55 冻结态，
    ours t=0.15285 反贴（慢速云纹下 0.15≈0.55 无感、0.0 差半幅）。

    **负结果记账（2026-10-25 第五轮）**：ally_premium 帧曾试 gem 相位=t_phase 派发
    （分区手测 0 相位优：z_race 9.08/16.97），但门管线 cand 未复现收益（z_race
    17.155→17.274 反微劣——门渲染路径与手测尚有配置差未对齐，RD 取证待做）→
    撤特例，3 红归 BG27 种子（premium 金件扫光/宝石时间源 RD 取证一并）。
    constructed 链 session_time 修复维持（full 128→3 的实证不变）。"""
    card = card or plan.get("_card_runtime")
    assert card is not None, "prep_plan: 缺 Card——desc 换轨/费用语义需 Card 门面"
    plan["gem"]["t"] = float(session_time if session_time is not None else t_phase)
    _shim_desc_texts(plan, card)
    cost_entry = next((e for e in plan["texts"] if e.get("role") == "cost"), None)
    cost_sem = _gems.cost_text_semantics(card, bg_style=plan.get("_bg_style")) \
        if cost_entry is not None else None
    if cost_sem is not None:
        if cost_sem.get("hide"):
            cost_entry["render"] = False
            cost_entry["skip"] = f"cost hide: {cost_sem['hide']}"
        if cost_sem.get("alt_pos"):
            plan["_cost_alt_pos"] = {
                # local=代码默认值（C# 字段初值），仅作回退；有效值=帧 kit meta
                # actor_alt_cost_pos（逐 prefab 序列化，见 gems._COST_ALT_LOCAL_POS 注与
                # uber_text._cost_alt_node_settings 取值面）。
                "local": list(cost_sem["alt_pos"]),
                "parent_suffix": "NonQuestObjects/CostObject",
                "rule": ("UpdateManaGemOffset（Actor.cs:Actor.UpdateManaGemOffset）× IsBaconSpell"
                         "（EntityBase.cs:EntityBase.IsBaconSpell）：cost 文本铸币位"
                         " m_alternateCostTextLocalPos（逐 prefab 序列化值；本地 local=代码默认回退）"),
                "source": "BigCard.cs:BigCard.SetupActor + 采集链 AlphaTool.Renderer.cs:AlphaTool.CreateActor",
            }
        plan["_cost_text_semantics"] = cost_sem
    if notext:
        for e in plan["texts"]:
            e["render"] = False
            e["skip"] = "notext (textless-ref)"
    if textonly:
        for c in plan["components"]:
            c["visible"] = False
            c["raster"] = False
            c["skip"] = "textonly (triple-report)"
        rg = plan.get("rarity_gem")
        if isinstance(rg, dict):
            rg["visible"] = False
        plan["stat_gems"] = []   # 预置空 → execute 期 collect 短路且渲染空转
        plan["_textonly"] = True
    return plan
