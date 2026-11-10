"""injectors — 注入件：Spell/NestedPrefab 运行时组件的离线等价（段 S10）。

游戏锚（walk-skeleton §10 逐件表）：
  badges          Actor.cs:Actor.UpdateCardColor 容器 SetActive（m_hearthstoneFactionBannerContainer/
                  m_tradeableBannerContainer/m_forgeBannerContainer/
                  m_prepareBannerContainer 四容器按 tag 独立，无互斥）+
                  EntityBase.cs:EntityBase tag 判定（IsTradeable/IsForgeable/
                  IsPrepareable = HasTag(TRADEABLE 1720/FORGE 2785/PREPARE 4354)，
                  HasTag=GetTag>0）+ NestedPrefabBase.cs:NestedPrefabBase.LoadPrefab LoadPrefab 实例化
                  （localPosition 强制零、rot/scale 保留——提取 npz matrix 已按
                  「根平移置零 × 局部链」累计，节点 world = 容器 world × matrix）。
  faction_banner  VALID_FACTIONS（Actor.cs:Actor 数组序）→ GetHearthstoneFaction
                  首中 → FactionBannerContainer SetActive（:6489）+
                  HearthstoneFactionBanner.SetFactionType（HearthstoneFactionBanner.cs:HearthstoneFactionBanner.SetFactionType：icon 材质←GetMaterialIcon(premium, faction)、banner 材质←
                  GetMaterialBanner(faction)；premium 判定 :17——语料 NORMAL 走
                  factionIconMaterials；m_shadowRef 不在 SetFactionType 链，永持
                  序列化 TradeableBanner_shadow）。合成正典=标准 alpha-over
                  （badge-trio FactionBanner 节，批11c 晋升；SC_019 拟合 k=1.000）。
  tier_spell      ShowTavernTierSpell（Actor.cs:Actor.ShowTavernTierSpell：FSM "TechLevel"=
                  GetTechLevel → ActivateState(BIRTH)；Lv1-Lv7 星组按等级累计激活）+
                  UseTechLevelManaGem（:6812-6837，S6 gems.use_tech_level_mana_gem
                  已立引用）+ UpdateManaGemComponent（:5217-5231 flag4=
                  UseTechLevelManaGem ∨ UseCoinManaGem 两 gem 门）。
  bacon rig       CustomHeroFrameBehaviour.UpdateFrame→InstantiateFrameMesh
                  （CustomHeroFrameBehaviour.cs:CustomHeroFrameBehaviour，正典 bacon-hero-frames §2：
                  m_defaultFrame=Bacon_HeroFrame_Default 实例化到 m_portraitMesh 下
                  localPosition=(0,0.1,0)；Awake→UpdateFrame 恒跑无 tag 门）。
  rune_banner     UpdateCardRuneBannerComponent（Actor.cs:Actor.UpdateCardRuneBannerComponent：默认 Hide()，
                  HasRuneCost → RunePattern.SetCostsFromEntity + Show）+ HasRuneCost
                  （EntityBase.cs:EntityBase.GetBloodCost = COST_BLOOD+FROST+UNHOLY > 0，无 CLASS/CARDTYPE
                  门——全手牌帧族无差别）+ GetRuneMaterial（Rune.cs:Rune.SetState switch
                  RuneState→m_runeAssetTable[type].m_runeMaterial；渲染语义正典
                  dk-runes.md：底座纯 unlit 纹理×顶点色、holder 阴影 final=dst×tex.rgb、
                  固定三槽扇形从左往右填）。

正典文：badge-trio.md（FactionBanner 合成=alpha-over 节）/ bacon-hero-frames.md /
dk-runes.md / scene-compiler-mvp.md 守则。

我方对位（旧实现参照，两源=decomp 转写×旧实现还原，冲突以 decomp 为准）：
old_render/components/{badges,faction_banner,tier_spell,bacon,rune_banner}.py
compile_* + 注入四件段（old_frames/render_card.py:357-388：compile_badges→
compile_faction_banner→compile_tier_spell→compile_bacon_hero_frame）+接线段
（:632-650，S11）。前段已转正判定面（本段引用不重做）：multiclass 三支路=
card_color_switcher.multiclass_segments（批13）、portrait=actor/portrait.py（批15）、
class_color=card_color_switcher.class_color_segment（批13）；语境 mode 轴判式=
gems.use_tech_level_mana_gem/cost_text_semantics（批16）。

配方面：badge_kit_mem/faction_kit_mem/btf_tree_mem 经 recipes.frames.injectors；
btf_kit/bacon_kit 经 recipes.frames；rune 图集经 recipes.frames.dk.rune_atlas
（mip_registry CardRunes_DeathKnight_sm L0）；blend/zwrite 材质态判定经
engine/raster（recipes.frames.supplements.material_state 92 材质内存面）。

批20 实现账（2026-10-14，S10 生长；**立壳补充件**——批11b 壳外新件，批14
frames.py 先例同形，NOTES 记一笔）。统筹职责切分=**本段产出 compile 产物与挂接
清单结构**：hierarchy copy-on-write 变异+MergedNpz 合并+plan["components"] 挂接
=接线段归 S11（apply_injections 立户）；本段 compile_* 返回结构化注入清单——
  {"applied", "nodes": {全路径: 节点记录（path/world/renderers 材质账/mesh_stats/
   source 账）}, "components": [计划组件记录（visibility_rule/material_override，
   与旧 comp_log 同构）], "npz_sources": {全路径: {"kind","prefix"|quad 载荷}},
   "log": {plan 键构面（S11 写 plan["badges"]/["faction_banner"]/["tier_spell"]/
   ["frame_rig"]["applied"]/["rune_banner"]）}}
无激活判定 → None（旧 (hierarchy, npz, None) 同象）。节点 world 合成三式：
容器 world × npz matrix（NestedPrefab，badges/faction）· 帧根 world × matrix
（Spell 挂载 AttachAndPreserveLocalTransform——spell 根局部变换**保留**，与
NestedPrefab 根平移置零相反；btf 提取 matrix 已含根平移，Actor.cs:Actor.LoadSpell）·
宿主 world × T(0,0.1,0)（rig）。icon quad=引擎公开常量几何（_BUILTIN_QUAD_*），
ST 选格 compile 期烘 uv0。

签名（新形即新定，非修正——批14 先例：本模块非批11b 立壳件）：compile 家族吃
Card+帧键（card-first，批15/16 同款），不吃 plan/hierarchy/npz（三样=S11 执行面
入参）；语境 mode 轴 bg_style 显式参数（derive_bg_mode 兜底=旧 plan["_bg_style"]
缺省推导同象）。账面串（visibility_rule/log source）verbatim 沿袭旧面（批16
DESC_MATERIALS/批17 _DESC_FRAME 先例：对拍表逐行全等的账面基础）。

纪律面前置——本模块函数族经 recipes.frames 触供给配方（@item），**消费须在
supply session 内**（入口层独占纪律，批12-17 同款；未来门驱动循环开 session 调
本段，段内不开）。

decomp 分支的离线边界（记录的缺口，非静默丢弃）——
  * m_deckActionBanner else-if 链（Actor.cs:Actor.UpdateCardColor：三徽章互斥夺高亮组件归属）
    ——hover 高亮件（DeckActionBanner 两个默认关闭 MeshRenderer），静态挂坠不消费；
    Glow/Selection/Highlight 序列化 enabled=false 不建计划组件（badge-trio 正典，
    旧 compile_badges 同账）。
  * faction 容器缺帧（FACTION_CONTAINER_BY_KEY 无行，如 heropower/play 双链）→
    None 透传（引擎 m_hearthstoneFactionBannerContainer 空引用 SetActive 同象）；
    旧返回 log{"applied": False, "reason"} 的容器缺节点腿同语义（applied=False 账）。
  * hero_hand 无徽章容器（BADGE_CONTAINER_BASE 缺行）=引擎同构（injector-roots
    调查：hero_hand prefab 无徽章容器）——KeyError 响亮非静默（旧同款）。
  * Timewarped 盾徽二选一（GetTechLevelSpellType Actor.cs:Actor.GetTechLevelSpellType，4503 分岔
    156/308）：判定已判 Timewarped 而供给账无 308 前缀 → RuntimeError 响亮
    （禁静默回落 156，旧同款）。
  * 金币件 FSM 演示态 Ability_Cost_Shadow_Mesh 排除（运行时演示态非 rest pose，
    参照三联 A/B 实证；npz 数据保留）。
  * LoadCustomFrame（Actor.cs:Actor.LoadCustomFrame 自定义帧换装）登记缺口不接线（批15 portrait
    段在册——本段非其宿位，CustomHeroFrameBehaviour 是 BG 帧族 rig 非 m_Custom
    HeroFramePrefab 链）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from eidolon.core.infra.card import (BG_MINION_CARDTYPE, BG_SPELL_CARDTYPE, BannerKind,
                                Card, CardType, FACTION_TAG_IDS, Faction, GameTag)
from eidolon.core.recipes.frames import bacon_kit, btf_kit, dk
from eidolon.core.recipes.frames import injectors as _inj
from eidolon.core.render.engine import raster as _raster
from eidolon.core.render.scenes import scenes as _frames
from eidolon.core.render.game.actor.portrait import portrait_binding
from eidolon.core.render._provenance import parallel  # noqa: F401 （族默认）

# ============================================================================
# badges — 卡牌徽章三件（Actor.cs:Actor.UpdateCardColor + EntityBase.cs:EntityBase）
# ============================================================================

BADGE_KIND_TO_KEY = {BannerKind.TRADEABLE: "tradeable", BannerKind.FORGE: "forgeable",
                     BannerKind.PREPARE: "prepareable"}
"""BannerKind（成员值=驱动 tag id）→ 徽章键；EntityBase.cs:EntityBase 判定三件。"""

BADGE_KIND_BY_KEY = {v: k for k, v in BADGE_KIND_TO_KEY.items()}

BADGE_CONTAINER_BASE = {  # consumer-v2 改键（spell_dk 行消亡）
    "Card_Hand_Ally": "Card_Hand_Ally/RootObject",
    "Card_Hand_Ally_Premium": "Card_Hand_Ally_Premium/RootObject",
    "Card_Hand_Ability": "Card_Hand_Ability/RootObject/NonQuestObjects",
}
"""帧键 → 容器基径（actor prefab 序列化容器位实测；hero_hand 无徽章容器=引擎同构，
play 双链同）。location 容器名=ForgeBannerContainer（无 "able"，injector-roots 勘误）
——location 不在开放位（徽章三件 prefab 序列化字段仅 ally/ability 帧挂）。"""

_BADGE_CONTAINER_NODE = {"tradeable": "TradableBannerContainer",
                         "forgeable": "ForgeableBannerContainer",
                         "prepareable": "PrepareableBannerContainer"}


@parallel
def compile_badges(card: Card, frame_key: str) -> dict | None:
    """tag 驱动的徽章三件挂载清单（数据驱动，禁逐卡表）——compile 产物+
    挂接清单结构（S11 消费面）；无激活 tag → None（旧原样透传同象）。

    判定=EntityBase.cs:EntityBase 三 tag 独立（card.banners 已按 tag 在场收集，
    HasTag=GetTag>0）；容器=BADGE_CONTAINER_BASE[frame_key] 容器基径下
    {Tradable,Forgeable,Prepareable}BannerContainer（容器 world=层级序列化真值）。
    节点 world = 容器 world × npz matrix（LoadPrefab 语义：根平移置零、rot/scale
    保留、局部链累计——NestedPrefabBase.cs:NestedPrefabBase.LoadPrefab）。Glow 高亮 MeshRenderer
    序列化关闭 → 不建计划组件。ShadowQuad 材质 multiply 走 material_override
    （材质态表 Hero/Multiply/Multiply badge-trio 源）；ally 画家链无 multiply
    语义（lineage 镜像，Mesh/Shadow 等透明件同桶 over）。"""
    active = [bkey for kind, bkey in BADGE_KIND_TO_KEY.items() if kind in card.banners]
    if not active:
        return None
    container_base = BADGE_CONTAINER_BASE.get(frame_key)
    if container_base is None:
        raise KeyError(f"帧 {frame_key} 无徽章容器基径（BADGE_CONTAINER_BASE 缺行）")
    k = _inj.badge_kit_mem()
    report, bnpz, badge_tex = k["report"], k["arrays"], k["textures"]
    hierarchy = _frames.scene_for(frame_key)["hierarchy"]

    # 纹理解析表：report textures[].used_by "节点路径:_MainTex" → 内存 PIL
    tex_by_node: dict[tuple[str, str], object] = {}
    for bkey in active:
        for t in report["badges"][bkey]["textures"]:
            f = t.get("file")
            if not f:
                continue
            for ub in t.get("used_by") or []:
                node_path, _, slot = ub.rpartition(":")
                if slot == "_MainTex":
                    tex_by_node[(bkey, node_path)] = badge_tex[Path(f).stem]

    nodes: dict[str, dict] = {}
    comp_log: list[dict] = []
    npz_sources: dict[str, dict] = {}
    containers: dict[str, str] = {}
    for bkey in active:
        container_path = f"{container_base}/{_BADGE_CONTAINER_NODE[bkey]}"
        containers[bkey] = container_path
        cont_node = _node_at(hierarchy, container_path)
        assert cont_node is not None, \
            f"{frame_key}: 帧层级无 {container_path}（recon 口径不符）"
        cont_world = np.array(cont_node["world"], dtype=np.float64)
        nodes_by_path = {n["path"]: n for n in report["badges"][bkey]["nodes"]}
        prefixes = sorted({key[:-len("/verts")] for key in bnpz
                           if key.startswith(f"{bkey}|") and key.endswith("/verts")})
        for prefix in prefixes:   # 渲染载荷写叶（链成形=S11，rel 全链自带结构）
            rel = prefix.split("|", 1)[1]
            parts = tuple(rel.split("/"))
            full_path = f"{container_path}/{rel}"
            npz_sources[full_path] = {"kind": "npz", "prefix": prefix}
            src = nodes_by_path.get(rel) or {}
            src_rr = src.get("components", {}).get("renderer") or {}
            enabled = bool(src_rr.get("enabled", True))
            mats = []
            for slot_rec in src_rr.get("material_slots", []):
                mname = slot_rec.get("name")
                if not mname:
                    continue
                tex_img = tex_by_node.get((bkey, rel))
                # `_Color` 的消费面**只有加性 multiply**（`Hero/Multiply/Multiply`：
                # PS `add o0.xyz,r0,v2`，tint 槽即 vColor）——与 btf 侧
                # `_multiply_color_props` 同判据（shader 身份，不是材质名）。
                # 其余 shader 一律不透传：徽章材质的 `m_SavedProperties` 混着**前代
                # shader 的陈旧槽**（影件留 `_ColorIntensity/_FlareIntensity`、横幅
                # `Tradeable_Banner` 的 `_Color` 仍是弃用的 [1,0,0,1]），而 raster 的
                # `colors._Color` 是 tint 乘法因子——错透传会把横幅染红。
                # 序列化面实测（2026-10-31 badge-vcolor，脚本 dump_badge_materials.py）：
                # 三件影件 `_Color`=(0.10377,0.10377,0.10377,1)、`_LightingBlend`=0。
                _sh = slot_rec.get("shader")
                _sh_name = _sh.get("name") if isinstance(_sh, dict) else (_sh or None)
                _col = (slot_rec.get("colors") or {}).get("_Color") \
                    if _raster.multiply_form(mname, _sh_name) \
                    == _raster.MULTIPLY_FORM_ADD_VCOLOR else None
                mats.append({
                    "name": mname,
                    "tex": {"_MainTex": {"texture": {"image": tex_img}}
                            if tex_img else {}},
                    "colors": {"_Color": list(_col)} if _col else {},
                })
            world = cont_world @ np.asarray(bnpz[f"{prefix}/matrix"], dtype=np.float64)
            nodes[full_path] = {
                "name": parts[-1],
                "path": full_path,
                "world": world.tolist(),
                "renderers": [{"enabled": enabled, "materials": mats}],
                "mesh_stats": {"name": (src.get("components", {})
                                        .get("mesh_filter", {})
                                        .get("mesh", {}) or {}).get("name")
                               or parts[-1]},
                "badge_source": {"prefab": report["badges"][bkey]["info"]["prefab_ref"],
                                 "npz_prefix": prefix},
            }   # 叶链节点即渲染节点（children 结构=S11 链成形面）
            if not enabled:
                continue   # Glow 高亮：序列化关闭，不建计划组件（不进光栅）
            slots = [{"slot": i, "material": m["name"],
                      "_MainTex_runtime": {"image": m["tex"]["_MainTex"]["texture"]["image"],
                                           "source": "injectors.badge_kit_mem 材质 _MainTex 直提"
                                                     "（批9c 内存面）"}}
                     for i, m in enumerate(mats) if m["tex"]["_MainTex"]["texture"].get("image")]
            comp: dict = {"path": full_path, "node": parts[-1],
                          "visible": True, "raster": True,
                          "material_slots": slots,
                          "visibility_rule": {
                              "rule": f"HasTag({int(BADGE_KIND_BY_KEY[bkey])}) → 容器 SetActive",
                              "source": "Actor.cs:Actor.UpdateCardColor + EntityBase.cs:EntityBase"
                                        "（badge-trio NOTES §1.1/§1.2）",
                              "tags_used": [int(BADGE_KIND_BY_KEY[bkey])]},
                          }
            if mats and (mname_state := _badge_blend_mode(mats[0]["name"])):
                comp["material_override"] = mname_state
            comp_log.append(comp)

    log = {"active": active,
           "containers": containers,
           "n_components": len(comp_log),
           "n_npz_nodes": _npz_node_count(npz_sources, bnpz)}
    return {"applied": True, "frame_key": frame_key,
            "nodes": nodes, "components": comp_log, "npz_sources": npz_sources,
            "log": {**log, "source": "ur_frames.compile_badges（badge-trio 2026-10-04）"}}


def _badge_blend_mode(mat_name: str) -> dict | None:
    """材质态表主色 pass → material_override（zbuf 链消费；painter 链忽略）。
    multiply（DstColor/Zero）走既有 multiply 通路（rune shadow 同式）；opaque
    （Unlit_Texture One/Zero）链内 over≡opaque 不写 override；zWrite=0 的 alpha 件
    记 _zwrite_off（2026-10-31 zbuf-table-driven 起材质态表 zWrite/Queue 全局直读，该键
    仅作注入期记账；光栅层不再消费链级开关）。"""
    mode = _raster.blend_mode_of(mat_name)
    zw = _raster.primary_zwrite(mat_name)
    if mode == "multiply":
        return {"blend": "multiply",
                "source": f"材质态表 {mat_name} 主色 pass（Hero/Multiply/Multiply，"
                          "badge-trio 提取入 material_state_merged.json）"}
    if zw == 0.0 and mode == "alpha":
        return {"blend": "over", "_zwrite_off": True,
                "source": f"材质态表 {mat_name} 主色 pass zWrite=0（透明队列件）"}
    return None


# ============================================================================
# faction_banner — 派系饰件（Actor.cs:Actor/:6489 + HearthstoneFactionBanner.cs:HearthstoneFactionBanner.SetFactionType）
# ============================================================================

VALID_FACTIONS = [int(tid) for tid, _ in FACTION_TAG_IDS]
"""VALID_FACTIONS 数组序（Actor.cs:Actor）——tag id 列（派系饰件判定域）。"""

FACTION_TAG_TO_INDEX = {int(tid): int(fac) for tid, fac in FACTION_TAG_IDS}
FACTION_TAG_BY_MEMBER = {int(fac): int(tid) for tid, fac in FACTION_TAG_IDS}
"""tag id ↔ Faction 槽位序（infra FACTION_TAG_IDS 机械派生——Faction 槽位值即
CardColorSwitcher.GetFactionColorTypeForTag 色型下标，2026-10-06 换轨正典）。"""

FACTION_NAMES = {int(f): f.name.split("_")[-1].lower() for f in Faction}
"""槽位→日志词（hand-table-residuals 2026-11-06 换轨：手抄六词退役）——派生规则=
Faction 活成员名末段小写（GRIMY_GOONS→goons / JADE_LOTUS→lotus / KABAL→kabal /
ZERG→zerg / TERRAN→terran / PROTOSS→protoss，与引擎成员词汇同源）。纯 log 面
（compile_faction_banner log.faction），零渲染消费。"""

FACTION_CONTAINER_BY_KEY = {  # consumer-v2 改键（spell_dk 行消亡）
    "Card_Hand_Ally": "Card_Hand_Ally/RootObject/FactionBannerContainer",
    "Card_Hand_Ally_Premium": "Card_Hand_Ally_Premium/RootObject/FactionBannerContainer",
    "Card_Hand_Ability": "Card_Hand_Ability/RootObject/NonQuestObjects/FactionBannerContainer",
    "Card_Hand_Weapon": "Card_Hand_Weapon/RootObject/FactionBannerContainer",
    "Card_Hand_Location": "Card_Hand_Location/RootObject/FactionBannerContainer",
    "Card_Hand_Hero": "Card_Hand_Hero/RootObject/FactionBannerContainer",
}

# Unity 内置 Quad（Faction_Icon 节点 MeshFilter 引用 unity default resources builtin；
# 游戏目录无该文件可提——引擎公开常量几何：XY 平面 1×1 中心对称、uv 0-1、
# 三角顺时针正面 +Z）。ST 选格在 compile 期烘进 uv0（对 uv_scale 双态策略无依赖）。
_BUILTIN_QUAD_VERTS = np.array([[-0.5, -0.5, 0.0], [0.5, -0.5, 0.0],
                                [-0.5, 0.5, 0.0], [0.5, 0.5, 0.0]], dtype=np.float64)
_BUILTIN_QUAD_UV0 = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], dtype=np.float64)
_BUILTIN_QUAD_TRIS = np.array([[0, 3, 1], [0, 2, 3]], dtype=np.int32)


@parallel
def compile_faction_banner(card: Card, frame_key: str) -> dict | None:
    """派系饰件挂载清单（compile_badges 同族，数据驱动禁逐卡表）；无派系 tag →
    None；容器缺帧 → None（引擎空引用门同象）。

    判定=VALID_FACTIONS（Actor.cs:Actor）按数组序首个 HasTag 命中
    （GetHearthstoneFaction :1439-1461，infra Card.faction 同序单实现）→
    FactionBannerContainer SetActive（UpdateCardColor :6489）→
    HearthstoneFactionBanner.SetFactionType（HearthstoneFactionBanner.cs:HearthstoneFactionBanner.SetFactionType）：
    icon 材质←m_factionIconRef 槽换装 factionIconMaterials[idx]、banner 材质←
    m_factionBannerRef 槽换装 factionBannerMaterials（idx1-3 共用 banner_1/
    idx4-6 共用 banner_4）；shadow 永持序列化 TradeableBanner_shadow。注入链只含
    activeSelf=True 且 renderer.enabled=True 的 mesh 节点（Faction_Banner_mesh
    序列化 activeSelf=false 整树不注入）。icon=引擎内置 Quad 常量几何+ST 选格烘
    uv0；合成正典=alpha-over（badge-trio 节，SC_019 拟合裁决，blend add→over）。"""
    faction = card.faction   # VALID_FACTIONS 序首中（Actor.cs:Actor）
    container_path = FACTION_CONTAINER_BY_KEY.get(frame_key)
    if faction is None or container_path is None:
        return None
    idx = int(faction)
    faction_tag = FACTION_TAG_BY_MEMBER[idx]   # 账面用驱动 tag id
    k = _inj.faction_kit_mem()
    report, fnpz, faction_tex = k["report"], k["arrays"], k["textures"]
    hierarchy = _frames.scene_for(frame_key)["hierarchy"]

    cont_node = _node_at(hierarchy, container_path)
    if cont_node is None:
        return {"applied": False, "frame_key": frame_key, "nodes": {},
                "components": [], "npz_sources": {},
                "log": {"applied": False,
                        "reason": f"帧层级无 {container_path}（recon 口径不符）"}}
    cont_world = np.array(cont_node["world"], dtype=np.float64)

    nodes_by_rel = {n["path"].split("Faction_Banner/", 1)[-1]: n
                    for n in report["nodes"] if "/" in n["path"]}
    banner_mat = report["faction_materials"][f"banner_{1 if idx <= 3 else 4}"]
    icon_mat = report["faction_materials"][f"icon_{idx}"]

    def _active(rel: str) -> bool:
        nd = nodes_by_rel.get(rel)
        return bool(nd and nd.get("activeSelf", True))

    def _raster_enabled(rel: str) -> bool:
        nd = nodes_by_rel.get(rel)
        return bool((nd.get("components", {}).get("renderer") or {}).get("enabled", True))

    prefixes = sorted({key.split("|", 1)[1][:-len("/verts")].split("Faction_Banner/", 1)[-1]
                       for key in fnpz
                       if key.startswith("faction|") and key.endswith("/verts")})
    icon_rel = "Banner_Root/Faction_Icon"
    assert icon_rel in nodes_by_rel, "Faction_Banner.prefab 无 Faction_Icon 节点（提取口径漂移）"

    def _want(rel: str) -> bool:
        if not _active(rel) or not _raster_enabled(rel):
            return False
        parts = rel.split("/")
        return all(_active("/".join(parts[:i])) for i in range(1, len(parts)))

    rels = sorted({p for p in prefixes if _want(p)} | {icon_rel})

    nodes: dict[str, dict] = {}
    comp_log: list[dict] = []
    npz_sources: dict[str, dict] = {}
    for rel in rels:
        nd = nodes_by_rel[rel]
        full_path = f"{container_path}/{rel}"   # 预制件根 GO 折入矩阵（LoadPrefab 语义），不占层级段
        world = cont_world @ np.asarray(nd["matrix_local_to_root"], dtype=np.float64)
        nodes[full_path] = {
            "name": rel.split("/")[-1],
            "path": full_path,
            "world": world.tolist(),
            "renderers": [{"enabled": True,
                           "materials": [_faction_runtime_mat(rel, banner_mat, icon_mat)]}],
            "mesh_stats": {"name": (nd.get("components", {}).get("mesh_filter", {})
                                    .get("mesh", {}) or {}).get("name") or rel.split("/")[-1]},
            "faction_banner_source": {"prefab": report["prefab"]["ref"], "rel": rel},
        }
        if rel == icon_rel:
            npz_sources[full_path] = {"kind": "quad",
                                      "verts": _BUILTIN_QUAD_VERTS,
                                      "uv0": _icon_uv0(icon_mat),
                                      "sub0": _BUILTIN_QUAD_TRIS}
        else:
            npz_sources[full_path] = {"kind": "npz",
                                      "prefix": f"faction|Faction_Banner/{rel}"}
        comp_log.append(_faction_component(full_path, rel, banner_mat, icon_mat,
                                           idx, faction_tag))

    log = {"applied": True, "faction_index": idx, "faction": FACTION_NAMES[idx],
           "tag": faction_tag, "container": container_path,
           "n_components": len(comp_log), "n_npz_nodes": _faction_npz_count(npz_sources, fnpz)}
    return {"applied": True, "frame_key": frame_key,
            "nodes": nodes, "components": comp_log, "npz_sources": npz_sources,
            "log": {**log,
                    "source": "ur_frames.compile_faction_banner（multiclass-render "
                              "2026-10-05；Actor.cs:Actor.UpdateCardColor + "
                              "HearthstoneFactionBanner.cs:HearthstoneFactionBanner.SetFactionType）"}}


def _icon_uv0(icon_mat: dict) -> np.ndarray:
    """icon quad uv0 = builtin quad uv × _MainTex ST（六派系共用 Faction_Icons 图集选格；
    ST 来源 = faction_materials 序列化 m_TexEnvs 实测）。"""
    st = (icon_mat.get("textures", {}).get("_MainTex") or {})
    sc = st.get("scale") or {"x": 1.0, "y": 1.0}
    of = st.get("offset") or {"x": 0.0, "y": 0.0}
    return _BUILTIN_QUAD_UV0 * np.array([float(sc["x"]), float(sc["y"])]) \
        + np.array([float(of["x"]), float(of["y"])])


def _faction_runtime_mat(rel: str, banner_mat: dict, icon_mat: dict) -> dict:
    """注入节点 renderer 的运行时材质账（SetFactionType swap 后态；shadow 永持序列化）。"""
    if rel.endswith("Faction_Icon"):
        return {"name": icon_mat["name"],
                "tex": {"_MainTex": {"texture": {"image": _ornament_tex(icon_mat)}}},
                "colors": {"_Color": [1.0, 1.0, 1.0, 1.0]}}
    if rel.endswith("ShadowQuad"):
        # `colors` 透传序列化 `_Color`（2026-10-31 silent-loss-guard 缺陷修）：旧注释
        # 「serialized material 无 `_Color` 属性」是空颜色表 bug 时代的假前提——该材质
        # 实有 `_Color`=0.1037736、`_LightingBlend`=0（badge-vcolor 正典 ⇒ vColor=_Color）。
        # 旧 `colors={}` 使加性 multiply 落 IA 缺省 vColor=0（tex+0），影子压暗过深：
        # 7 张派系卡 A/B 变化像素距 oracle 6.2–7.6 → 1.0–1.3 灰阶、门口径零回归全改善。
        # 只在 shader 身份=加性 multiply 时透传（其余 shader 的 `_Color` 是 tint 因子）。
        _shadow = _shadow_slot()
        _col = ((_shadow.get("colors") or {}).get("_Color")
                if _shadow.get("shader") == _raster.MULTIPLY_ADD_SHADER else None)
        return {"name": "TradeableBanner_shadow",
                "tex": {"_MainTex": {"texture": {"image": _shadow_tex()}}},
                "colors": {"_Color": list(_col)} if _col else {}}
    return {"name": banner_mat["name"],
            "tex": {"_MainTex": {"texture": {"image": _ornament_tex(banner_mat)}}},
            "colors": {"_Color": [1.0, 1.0, 1.0, 1.0]}}


def _ornament_tex(mat: dict):
    """材质 _MainTex 内存 PIL（域 kit textures；旧 ornaments 文件路径退役）。"""
    tname = (mat.get("textures", {}).get("_MainTex") or {}).get("tex_name")
    assert tname, f"faction 材质 {mat.get('name')} 缺 _MainTex 纹理"
    return _inj.faction_kit_mem()["textures"][tname]


def _shadow_tex():
    """TradeableBanner_shadow 序列化 _MainTex（Faction_Banner.prefab ShadowQuad 槽）。"""
    k = _inj.faction_kit_mem()
    report, tex = k["report"], k["textures"]
    for n in report["nodes"]:
        rr = n.get("components", {}).get("renderer")
        if rr and n["path"].endswith("Faction_Banner/ShadowQuad"):
            m = (rr.get("material_slots") or [{}])[0]
            tname = (m.get("textures", {}).get("_MainTex") or {}).get("name")
            if tname:
                return tex[tname]
    raise FileNotFoundError("Faction_Banner.prefab ShadowQuad 材质纹理缺失（提取账漂移）")


def _shadow_slot() -> dict:
    """Faction_Banner.prefab ShadowQuad 槽材质记录（`_shadow_tex` 同式；`_Color` 来路）。"""
    for n in _inj.faction_kit_mem()["report"]["nodes"]:
        rr = n.get("components", {}).get("renderer")
        if not rr or not n["path"].endswith("Faction_Banner/ShadowQuad"):
            continue
        for m in rr.get("material_slots") or []:
            if m.get("colors"):
                return m
    return {}


def _faction_component(full_path: str, rel: str, banner_mat: dict,
                       icon_mat: dict, idx: int, faction_tag: int) -> dict:
    comp: dict = {"path": full_path, "node": rel.split("/")[-1],
                  "visible": True, "raster": True,
                  "material_slots": [], "visibility_rule": {
                      "rule": f"HasTag({faction_tag}) → FactionBannerContainer SetActive + "
                              "HearthstoneFactionBanner.SetFactionType",
                      "source": "Actor.cs:Actor.UpdateCardColor + HearthstoneFactionBanner.cs:HearthstoneFactionBanner.SetFactionType"
                                "（NOTES §3.1；HasTag=GetTag>0）",
                      "tags_used": [faction_tag]}}
    if rel.endswith("Faction_Icon"):
        comp["material_slots"] = [{"slot": 0, "material": icon_mat["name"],
                                   "_MainTex_runtime": {"image": _ornament_tex(icon_mat),
                                                        "source": "injectors.faction_kit_mem "
                                                                  "Faction_Icons 图集（ST 已烘 uv0）"}}]
        comp["material_override"] = {
            # SC_019 案：参照 icon 合成=标准 alpha-over（逐像素拟合 k=1.000/R²=0.999），
            # SrcAlpha/One 多加 dst·α 项→icon 过亮偏白；blend add→over（badge-trio
            # FactionBanner 正典节，批11c 晋升）。shader pass 字面 destBlend=10（Unity
            # 枚举无 10；D3D11=INV_DEST_COLOR）与观测 alpha-over 不符=映射疑点，登记
            # findings 待定。zwrite 维持 0。
            "blend": "over",
            "source": f"{icon_mat['name']} shader Hero/Unlit_Transparent 主色 pass "
                      "(srcBlend=5 SrcAlpha / destBlend=10 字面值, zWrite=0)——faction_report.json "
                      "faction_materials 实测；blend 语义经 SC_019 拟合裁决=alpha-over"}
    elif rel.endswith("ShadowQuad"):
        comp["material_slots"] = [{"slot": 0, "material": "TradeableBanner_shadow"}]
        comp["material_override"] = {
            "blend": "multiply",
            "source": "TradeableBanner_shadow shader Hero/Multiply/Multiply（材质态表 badge-trio "
                      "源既有行；blend_from_table 链同名表查命中同值，显式 mo 优先级同值）"}
    else:
        comp["material_slots"] = [{"slot": 0, "material": banner_mat["name"],
                                   "_MainTex_runtime": {
                                       "image": _ornament_tex(banner_mat),
                                       "source": "injectors.faction_kit_mem faction_materials "
                                                 "(factionBannerMaterials 表槽 _MainTex 直提；"
                                                 "ST 恒等)"}}]
    return comp


# ============================================================================
# tier_spell — BG tier 盾徽+金币件（ShowTavernTierSpell :7581-7598 两跳 SpellTable）
# ============================================================================

TIER_FRAME_ROOTS = {  # consumer-v2 改键（spell_dk 行消亡）
    "Card_Hand_Ally": "Card_Hand_Ally", "Card_Hand_Ally_Premium": "Card_Hand_Ally_Premium",
    "Card_Hand_Ability": "Card_Hand_Ability",
    "Card_Hand_Ability_Premium": "Card_Hand_Ability_Premium",   # 金法术（2026-10-30）：独立 premium kit，根=自身层级根
    "History_HeroPower": "History_HeroPower",
    "Card_Hand_BG_Trinket": "Card_Hand_BG_Trinket"}
"""帧键 → actor 根名（GetSpellParent Actor.cs:Actor.GetSpellParent "Spells" GO local 零；
帧根 world 恒等——注入节点 world = spell npz matrix，根平移已含。heropower 行=
bacon-hero-power-frames 2026-10-07：frame_recon.json root world=I 已核；GetHandActor
HERO_POWER → HISTORY_HERO_POWER 与 spell 链同挂载语义（GetSpellParent/AttachAndPreserveLocalTransform
不分支于卡型）。"""


def _btf_assets():
    """btf 双源组合（旧 _btf_assets 同构，配方面经 recipes）：官方 btf_kit
    （arrays/材质账/纹理=产品精确集）+ injectors.btf_tree_mem（树+材质名绑定——
    官方树为工具域形无 material_slots 消费字段）。返回 (report, arrays, textures)。"""
    k = btf_kit()
    rep = dict(k.report)
    trees = _inj.btf_tree_mem()
    for skey, tree in trees.items():
        if skey in rep["spells"]:
            rep["spells"][skey]["tree"] = tree
    return rep, k.arrays, k.textures


@parallel
def compile_tier_spell(card: Card, frame_key: str, *, bg_style: str | None = None) -> dict | None:
    """盾徽（TECH_LEVEL_MANA_GEM 156/TIME_TAVERN_TIER_ICON 308 变体）+ BG 法术金币件
    （COIN_MANA_GEM_BACON_SPELL 267/标准件 145）+ BG 英雄能力金币件（槽 145 专用件）
    + timewarped 费用底座件（COST_ALT_TAVERN_COIN 303）
    挂载清单——非 BG 语境原样 None。

    激活判据（mode 轴+tag 数据驱动，禁逐卡表；离线以 bg_style=bacon 显式替代
    游戏实体 TECH_LEVEL_MANA_GEM/COIN_MANA_GEM tag 门，Actor.cs:Actor.UseTechLevelManaGem/:6839-6841）：
      - 盾徽：mode=bacon ∧ TECH_LEVEL(1440)>0 ∧ cardtype∈{42,4,5}（UseTechLevelManaGem：
        随从手牌域恒真 :6819-6829，法术需 TECH_LEVEL tag ∧ IsBaconSpell∨IsSpell
        :6831-6835——S6 use_tech_level_mana_gem 已立，此处判式同源复述）；
        spell_key 二选一（GetTechLevelSpellType :7542-7550 同构语义）：4503>0 → 308
        变体件（timewarped_tier_icon|*，同 mesh 同 UV 纯换皮），否则 156 标准件；
        渲染面=盾徽+shadow+Lv{tier} 星组（ShowTavernTierSpell :7581-7598 置 FSM
        "TechLevel"=GetTechLevel 后 BIRTH，组=1..7 星累计）。
      - 金币：mode=bacon ∧ cardtype==42（IsBaconSpell :5236 flag7——ct5 不出金币件）；
        不分岔（UseCoinManaGem :6839-6842 无 4503 项）。
      - 金币·TL0 腿：mode=bacon ∧ TL 缺省/0 ∧ cardtype==5 → 标准金币件 145
        （Card_Hand_Ability_CoinManaGem；SpellTable 槽 145 仅 ability 表有）。
      - 金币·任务奖励腿（bg-ct40-43-44-routing 2026-10-24）：mode=bacon ∧
        cardtype==40 → 标准金币件 145（与 TL0 腿同件同表）；采集链
        AlphaTool.Renderer.cs:190-201 标准金币腿 `(IsSpell()&&!flag2)||IsHeroPower()
        ||IsBattlegroundTrinket()||IsBattlegroundQuestReward()` 显式含 ct40——
        无 TL 门（ct40 不在 flag2=IsBaconSpell∨IsSpell 盾徽面内，UseTechLevelManaGem
        Actor.cs:6884-6910 结构性排除）。
      - 金币·英雄能力腿：mode=bacon ∧ cardtype==10 → 英雄能力金币件
        coin_mana_gem_hero_power（History_HeroPower SpellTable 槽 145 专用件，
        bacon-hero-power-frames 2026-10-07 hp_table_probe 定案；采集链 IsHeroPower
        leg AlphaTool.Renderer.cs:190-201；无盾徽腿——UseTechLevelManaGem flag2
        结构性排除 ct10 且 heropower 表无 156/308 槽）。
      - 费用底座腿（timewarped-cost-base 2026-10-31）：mode=bacon ∧ BACON_TIMEWARPED
        (4503)>0 ∧（cardtype==42 ∨ (TL>0 ∧ cardtype∈{4,5})）→ 底座件 303（数据登记槽
        305，见 supply.frames.btf 行注）：随从帧挂 Ally 件、法术帧挂 Ability 件；
        **同卡 267 金币件不再画**（303 顶替，采集链 :219-227 同形）。
    挂载语义（Actor.cs:Actor.LoadSpell LoadSpell）：AttachAndPreserveLocalTransform——
    spell 根局部变换**保留**（与 NestedPrefab 根平移置零相反）；帧根 world 恒等 →
    注入节点 world = root world × npz matrix（根平移已含）。"""
    mode = bg_style if bg_style is not None else derive_bg_mode(card)
    cardtype = int(card.cardtype)
    tech_level = int(card.tech_level)
    is_timewarped = int(card.timewarped) > 0   # BACON_TIMEWARPED(4503)——数据驱动，禁逐卡表
    is_bg_spell = cardtype == BG_SPELL_CARDTYPE
    in_bacon = mode == "bacon"
    # 费用底座件（SpellType.COST_ALT_TAVERN_COIN=303）：timewarped 卡的「替换金币件」——
    # 引擎侧=tag 驱动（CARD_ALTERNATE_COST==ALT_TAVERN_COIN(5) → Actor.ActivateAlternateCost
    # :7391 → GetSpellTypeFromAlternateCostType :7384 → COST_ALT_TAVERN_COIN →
    # LoadSpell(303) :7026）；离线无对局实体 tag 面 → 代理=mode=bacon ∧ BACON_TIMEWARPED
    # (4503)>0（数据驱动，禁逐卡表）。两条激活腿与采集链 AlphaTool.Renderer.cs
    # CreateActor bgs 分支同形（:165-233，oracle 三态即该链产出）：
    #   * flag2 腿（(IsSpell()||IsMinion()) ∧ TL>0）→ 303 底座；
    #   * IsBaconSpell 腿（CARDTYPE 42，采集链无 TL 门）→ 303 顶替 267 金币件。
    # 数据侧登记槽=305（手牌两表 303 皆空，见 supply.frames.btf row 注）；此处只按引擎
    # 语义（303）判定并挂件，取 ref 由供给行负责。
    is_alt_coin = bool(in_bacon and is_timewarped and (
        cardtype == BG_SPELL_CARDTYPE
        or (tech_level > 0 and cardtype in (BG_MINION_CARDTYPE, int(CardType.SPELL)))))
    want_shield = (in_bacon and tech_level > 0 and cardtype in (
        BG_SPELL_CARDTYPE, BG_MINION_CARDTYPE, int(CardType.SPELL)))
    # 267 金币件：303 底座生效时不再画（采集链 IsBaconSpell 腿 `spell3` 被 303 顶替，
    # AlphaTool.Renderer.cs:219-227；37.0 引擎同区=ActivateAlternateCost 的 death/birth
    # 两态切换，Actor.cs:7397-7402）→ timewarped 酒馆法术只剩底座、非 timewarped 照旧 267。
    want_coin = in_bacon and is_bg_spell and not is_alt_coin
    # premium 门（golden 98918 2026-11-04）：premium>0 的 ct5 TL0 法术不注金币件。
    # 依据：①游戏自身常驻金币链 m_baconCoinObject.SetActive 仅 IsBaconSpell
    # （ct42 严格，EntityBase.cs:566-568）——ct5 无常驻金币，手牌静态=序列化
    # Gem_Mana（UpdateManaGemComponent gem 显隐只吃 DISABLE_SPELL_MANA_GEM 选项）；
    # ②采集腿（AlphaTool.Renderer.cs:190-201）对 145 只 ActivateState(BIRTH)
    # （267/303 腿均 DEATH+BIRTH 成对）=瞬态动画触发，98918_golden 的 oracle
    # 冻结快照上金币不可见（蓝 Gem_Mana 在）=该腿对 premium actor 的采集结果
    # 即「无金币」；③对照 89449（ct40，同腿）oracle 金币可见——判别变量
    # （冻结时点金币 FSM 态）离线不可得，补采项记过程账 NOTES（带金币态日志单卡
    # 重采）。故 premium 域先收口为「不注」；非 premium ct5 TL0 行为不变
    # （语料无例，零扰动）。
    want_coin_std = (in_bacon and tech_level == 0
                     and cardtype == int(CardType.SPELL)
                     and not card.premium)
    # BG 英雄能力金币件（bacon-hero-power-frames 2026-10-07 patch 提案 P2）：mode=bacon
    # ∧ CARDTYPE(202)=10 → History_HeroPower_SpellTable 槽 145 专用件（采集链 IsHeroPower
    # leg AlphaTool.Renderer.cs:190-201 `(IsSpell()&&!flag2) || IsHeroPower() || …` leg，
    # SpellType 同 145=各 actor 经自己的表解析成各自 prefab）。无盾徽腿：引擎
    # UseTechLevelManaGem flag2 结构性排除 ct10 且 heropower 表无 156/308 槽（8 槽
    # 全 dump）。
    want_coin_hp = in_bacon and cardtype == int(CardType.HERO_POWER)
    # 饰品金币件（bg-ct40-43-44-routing 2026-10-24）：mode=bacon ∧ CARDTYPE(202)=44 →
    # Card_Hand_BG_Trinket_SpellTable 槽 145 专用件（采集链 IsBattlegroundTrinket leg
    # AlphaTool.Renderer.cs:191-201 HideCoinManaGem→GetSpell(COIN_MANA_GEM).
    # ActivateState(BIRTH)；SpellType 145=各 actor 经自己的表解析成各自 prefab）。
    # 无盾徽腿：UseTechLevelManaGem 随从/法术两腿结构性排除 ct44（Actor.cs:6816-6836）。
    want_coin_trinket = in_bacon and cardtype == int(CardType.BATTLEGROUND_TRINKET)
    # 任务奖励金币件（bg-ct40-43-44-routing 2026-10-24）：mode=bacon ∧ ct40 →
    # 标准金币件 145（采集链 AlphaTool.Renderer.cs:190-201 标准金币腿显式含
    # IsBattlegroundQuestReward()，与 ct5 TL0 腿同件同表；无盾徽腿——
    # UseTechLevelManaGem flag2 结构性排除 ct40，Actor.cs:6884-6910）。
    want_coin_quest_reward = (in_bacon
                              and cardtype == int(CardType.BATTLEGROUND_QUEST_REWARD))
    if not (want_shield or want_coin or want_coin_std or want_coin_hp
            or want_coin_trinket or want_coin_quest_reward or is_alt_coin):
        return None
    rep, bnpz, btf_tex = _btf_assets()
    if frame_key not in TIER_FRAME_ROOTS:
        raise KeyError(f"帧 {frame_key} 无 BG spell 挂载面（actor 根基径缺失）")
    frame_root = TIER_FRAME_ROOTS[frame_key]
    hierarchy = _frames.scene_for(frame_key)["hierarchy"]
    root_world = _node_world(hierarchy, frame_root)
    assert root_world is not None, f"{frame_key}: 帧层级无根 {frame_root}"

    spells = rep["spells"]
    wanted: list[str] = []
    # 盾徽件二选一（GetTechLevelSpellType Actor.cs:Actor.GetTechLevelSpellType）：4503>0 → 308 变体件，
    # 否则 156 标准件。盾 renderer 名单两件并存于同一 endswith 元组安全：节点名各自
    # 独有（156=…_Unlit / 308=…_Timewarped；shadow 同名），且前缀已按 spell_key 过滤。
    shield_spell_key = "timewarped_tier_icon" if is_timewarped else "tech_level_mana_gem"
    if want_shield:
        star_group = f"/Stars/Lv{max(1, min(7, tech_level))}/"
        for pref in rep["npz_prefixes"]:
            if not pref.startswith(f"{shield_spell_key}|"):
                continue
            rel = pref.split("|", 1)[1]
            if rel.endswith(("Bacon_TechLevel_Shield_Unlit", "Bacon_TechLevel_Shield_Timewarped",
                             "Bacon_TechLevel_Shield_shadow")) \
                    or star_group in rel:
                wanted.append(pref)
        if is_timewarped and not any(p.startswith("timewarped_tier_icon|") for p in wanted):
            # 静默空结果=先疑 schema 假设：判定已判 Timewarped 而供给账无 308 前缀 →
            # btf 供给陈旧，响亮失败禁静默回落 156（旧同款）。
            raise RuntimeError(
                f"timewarped 盾徽前缀缺失（dbf={card.dbf_id}）：btf 供给无 timewarped_tier_icon|* "
                f"——供给缓存陈旧，需重建")
    if want_coin:
        # 267 件全集注入（含 `Gem_Health/Ability_Cost_Shadow_Mesh` 42tri 币阴盘）：
        # RenderDoc 104027/104601 真渲染帧逐 draw 实证该盘**每帧都画**（order18/19，
        # 晚于肖像；PS `add o0.xyz,r0,v2`/DstColor-Zero ⇒ dst*=tex+vColor；vColor=材质
        # `_Color` 0.11321）。旧「参照无此盘、FSM 演示态、排除+记账」归因被反证——
        # 排除项删除（正典勘误见 docs/notes/bacon-frame-furniture.md）。
        wanted += [p for p in rep["npz_prefixes"]
                   if p.startswith("coin_mana_gem_bacon_spell|")]
    if want_coin_std or want_coin_quest_reward:
        # 145 件：唯一 npz 渲染节点 Root/Gem_Health（Coin_Mana_mesh×Gem_Mana_Coin）。
        # FX_Plasma/Health_Burst 无 npz 前缀自动落空；本 prefab 无影盘（267 那件的
        # `Ability_Cost_Shadow_Mesh` 只挂 CoinManaGem_BaconSpell）。响亮守卫（308 先例）：
        # 判定已判 TL0 法术/任务奖励而供给账无前缀=btf 供给陈旧，禁静默空注。
        wanted += [p for p in rep["npz_prefixes"] if p.startswith("coin_mana_gem|")]
        if not any(p.startswith("coin_mana_gem|") for p in wanted):
            raise RuntimeError(
                f"标准金币件前缀缺失（dbf={card.dbf_id}）：btf 供给无 coin_mana_gem|* "
                f"——供给缓存陈旧，需重建")
    if want_coin_hp:
        # heropower 表 145 专用件：唯一 npz 渲染节点 History_HeroPower_CoinManaGem/
        # Gem_Health（同 Coin_Mana_mesh×Gem_Mana_Coin pid，仅变换不同——hp_coin_prefab
        # 探针逐 pid 定案）。响亮守卫同上两先例：判定已判 bacon 英雄能力而供给账无
        # 前缀=btf 供给陈旧，禁静默空注。
        wanted += [p for p in rep["npz_prefixes"]
                   if p.startswith("coin_mana_gem_hero_power|")]
        if not any(p.startswith("coin_mana_gem_hero_power|") for p in wanted):
            raise RuntimeError(
                f"英雄能力金币件前缀缺失（dbf={card.dbf_id}）：btf 供给无 "
                f"coin_mana_gem_hero_power|* ——供给缓存陈旧，需重建")
    if want_coin_trinket:
        # trinket 表 145 专用件（bg-ct40-43-44-routing 2026-10-24）：唯一 npz 渲染节点
        # Card_Hand_Trinket_CoinManaGem/Gem_Health（链解实证，见 btf.py BTF_SPELLS 行注）。
        # 响亮守卫同上三先例：判定已判 bacon 饰品而供给账无前缀=btf 供给陈旧，禁静默空注。
        wanted += [p for p in rep["npz_prefixes"]
                   if p.startswith("coin_mana_gem_trinket|")]
        if not any(p.startswith("coin_mana_gem_trinket|") for p in wanted):
            raise RuntimeError(
                f"饰品金币件前缀缺失（dbf={card.dbf_id}）：btf 供给无 "
                f"coin_mana_gem_trinket|* ——供给缓存陈旧，需重建")
    alt_coin_key = None
    if is_alt_coin:
        # 底座件二选一按 **actor 帧族**（spell 挂到 GetSpellParent 下，件身份随帧）：
        # 随从帧=Ally 件、法术帧（ct5 普通法术 / ct42 酒馆法术）=Ability 件
        # （SpellTable 链解行：HAND_MINION 表 305→Ally 件、HAND_SPELL 表 305→Ability 件）。
        # 响亮守卫（308/145 先例）：判定已判 timewarped 底座而供给账无该前缀=
        # btf 供给陈旧，禁静默空注。
        alt_coin_key = ("cost_alt_tavern_coin_ally"
                        if cardtype == BG_MINION_CARDTYPE
                        else "cost_alt_tavern_coin_ability")
        wanted += [p for p in rep["npz_prefixes"]
                   if p.startswith(f"{alt_coin_key}|")]
        if not any(p.startswith(f"{alt_coin_key}|") for p in wanted):
            raise RuntimeError(
                f"费用底座件前缀缺失（dbf={card.dbf_id}）：btf 供给无 {alt_coin_key}|* "
                f"——供给缓存陈旧，需重建")
    if not wanted:
        return None

    # 纹理解析表：report materials[名]._MainTex.file → 域 textures 内存 PIL
    tex_by_mat: dict[str, object] = {}
    for mname, m in rep.get("materials", {}).items():
        t = (m.get("_MainTex") or {}).get("file")
        if t:
            tex_by_mat[mname] = btf_tex[t]

    nodes: dict[str, dict] = {}
    npz_sources: dict[str, dict] = {}
    comp_log: list[dict] = []
    for pref in wanted:
        spell_key, rel = pref.split("|", 1)
        parts = tuple(rel.split("/"))
        # report 树按 rel 找（parts[0]=spell 根名=树根本体，匹配自 parts[1:] 起）
        cur = rep["spells"][spell_key]["tree"]
        for seg in parts[1:]:
            nxt = next((c for c in cur.get("children", []) if c.get("name") == seg), None)
            if nxt is None:
                cur = None
                break
            cur = nxt
        src = cur or {}
        mats = []
        for slot_rec in src.get("material_slots") or []:
            mname = slot_rec.get("material")
            tex_img = tex_by_mat.get(mname)
            ment = rep.get("materials", {}).get(mname) or {}
            mats.append({"name": mname,
                         "tex": {"_MainTex": {"texture": {"image": tex_img} if tex_img else {}}},
                         "colors": _multiply_color_props(ment)})
        if not mats:
            continue   # 无 renderer/材质账的链节点（理论不含——npz 只收 renderer 节点）
        # _MainTex ST（timewarped-tier-icon 账）：非恒等 ST 的材质在注入期烘焙进
        # uv0（S11 合并面消费；引擎 Repeat wrap 语义 %1）。三件 prefab 实测唯一非恒等=
        # 308 盾皮 Bacon_TechLevelBanner_Timewarp_Unlit offset(0,0.475)。
        st = None
        for slot_rec in src.get("material_slots") or []:
            ment = rep.get("materials", {}).get(slot_rec.get("material")) or {}
            s = (ment.get("_MainTex") or {}).get("st")
            if s and (tuple(s["scale"]) != (1.0, 1.0) or tuple(s["offset"]) != (0.0, 0.0)):
                st = s
                break
        world = root_world @ np.asarray(bnpz[f"{pref}/matrix"], dtype=np.float64)
        full_path = f"{frame_root}/{rel}"
        nodes[full_path] = {
            "name": parts[-1],
            "path": full_path,
            "world": world.tolist(),
            "renderers": [{"enabled": True, "materials": mats}],
            "mesh_stats": {"name": src.get("mesh") or parts[-1]},
            "btf_source": {"spell": spell_key, "spell_type": rep["spells"][spell_key]["spell_type"],
                           "prefab": rep["spells"][spell_key]["ref"], "npz_prefix": pref,
                           **({"_MainTex_st": st} if st else {})},
        }
        npz_sources[full_path] = {"kind": "npz", "prefix": pref,
                                  **({"uv0_baked": (np.asarray(bnpz[f"{pref}/uv0"], dtype=np.float64)
                                                    * np.asarray(st["scale"], dtype=np.float64)
                                                    + np.asarray(st["offset"], dtype=np.float64)) % 1.0}
                                     if st is not None else {})}
        slots = [{"slot": i, "material": m["name"],
                  "_MainTex_runtime": {"image": m["tex"]["_MainTex"]["texture"]["image"],
                                       "source": "btf_extract_assets 材质 _MainTex 直提"
                                                 "（spell_prefabs_report.json）"}}
                 for i, m in enumerate(mats) if m["tex"]["_MainTex"]["texture"].get("image")]
        is_coin = spell_key == "coin_mana_gem_bacon_spell"
        is_coin_std = spell_key == "coin_mana_gem"
        is_coin_hp = spell_key == "coin_mana_gem_hero_power"
        is_coin_trinket = spell_key == "coin_mana_gem_trinket"
        is_alt_coin_node = spell_key.startswith("cost_alt_tavern_coin")
        if is_alt_coin_node:
            # 费用底座面（timewarped-cost-base 2026-10-31 账面）：引擎侧槽位 303
            # （SPELLS 表登记在 305=旧编号，见 supply.frames.btf 行注），消费=tag 驱动的
            # ActivateAlternateCost 链；离线代理=4503。
            vr_rule = ("费用底座件 SpellType.COST_ALT_TAVERN_COIN(303) ∧ "
                       "BACON_TIMEWARPED(4503)=1 ∧ mode=bacon（语境旗）——"
                       + ("随从帧 Ally 件" if cardtype == BG_MINION_CARDTYPE
                          else "法术帧 Ability 件"))
            vr_source = ("Actor.cs:Actor.ActivateAlternateCost :7391 + "
                         "GetSpellTypeFromAlternateCostType :7384（CARD_ALTERNATE_COST=="
                         "ALT_TAVERN_COIN → COST_ALT_TAVERN_COIN）+ LoadSpell :7026；"
                         "数据登记槽=305（手牌两表 303 皆空，37.0 两代编号混用），"
                         "采集链 AlphaTool.Renderer.cs:165-233 flag2/IsBaconSpell 两腿同源")
            vr_tags = [4503, 2837]   # 4503=代理 tag；2837=GAME_TAG.CARD_ALTERNATE_COST（值 5=ALT_TAVERN_COIN，引擎真腿）
        elif is_coin_trinket:
            # 饰品金币面（bg-ct40-43-44-routing 2026-10-24 账面）
            vr_rule = ("饰品金币件 CARDTYPE(202)=44 ∧ mode=bacon（语境旗）——"
                       "Card_Hand_BG_Trinket_SpellTable 槽 145 专用 prefab")
            vr_source = ("采集链 IsBattlegroundTrinket leg（AlphaTool.Renderer.cs:191-201 "
                         "HideCoinManaGem→GetSpell(COIN_MANA_GEM).ActivateState(BIRTH)，"
                         "SpellType 145 各 actor 经自己的表解析成各自 prefab）；表槽映射="
                         "trinket SpellTable 链解（本批 btf.py BTF_SPELLS 行注）")
            vr_tags = [202]
        elif is_coin_hp:
            # BG 英雄能力金币面（bacon-hero-power-frames 2026-10-07 patch 提案 P2 账面）
            vr_rule = ("英雄能力金币件 CARDTYPE(202)=10 ∧ mode=bacon（语境旗）——"
                       "History_HeroPower_SpellTable 槽 145 专用 prefab")
            vr_source = ("采集链 IsHeroPower leg（AlphaTool.Renderer.cs:190-201 "
                         "ActivateState(BIRTH)，SpellType 145 各 actor 经自己的表解析成"
                         "各自 prefab）+ 藏水晶 UseCoinManaGem flag4（Actor.cs:"
                         "5217-5231/:6839-6841）卡侧无条件；表槽映射=hp_table_probe"
                         "（bacon-hero-power-frames 2026-10-07）")
            vr_tags = [202]
        else:
            rule = ("金币件" if is_coin else "标准金币件" if is_coin_std else "盾徽") + (
                f"（Lv{tech_level} 组）" if not (is_coin or is_coin_std) else "")
            if is_coin_std and cardtype == int(CardType.BATTLEGROUND_QUEST_REWARD):
                # ct40 与 ct5 TL0 同件（coin_mana_gem| 前缀）——账面按卡型分述
                vr_rule = ("标准金币件 CARDTYPE(202)=40（任务奖励金币面，mode=bacon "
                           "语境旗；无 TL 门）")
            else:
                vr_rule = (f"金币件 TECH_LEVEL(1440)={tech_level} / IsBaconSpell"
                           if not is_coin_std else
                           f"{rule} CARDTYPE(202)=5 ∧ TECH_LEVEL(1440) 缺省/0"
                           "（TL0 法术金币面，mode=bacon 语境旗）") + (
                    " / BACON_TIMEWARPED(4503)=1→308 变体件"
                    if not is_coin and not is_coin_std and is_timewarped else "")
            vr_source = ("ShowTavernTierSpell Actor.cs:Actor.ShowTavernTierSpell + UseTechLevelManaGem"
                         " :6812-6837 + GetTechLevelSpellType :7542-7550（4503 分岔 "
                         "156/308）+ SpellTable 映射（采集链 AlphaTool."
                         "Renderer.cs bgs 分支同源）"
                         if not (is_coin or is_coin_std) else
                         "Actor.cs:Actor.UpdateManaGemComponent flag7 + 采集链 267 ActivateState"
                         "（AlphaTool.Renderer.cs CreateActor bgs 分支；无 4503 "
                         "分岔，UseCoinManaGem :6839-6842）"
                         if is_coin else
                         "采集链 IsBattlegroundQuestReward() leg 145 ActivateState(BIRTH)"
                         "（AlphaTool.Renderer.cs:AlphaTool.CreateActor 标准金币腿；"
                         "SpellTable 槽 145 映射）"
                         if is_coin_std and cardtype == int(CardType.BATTLEGROUND_QUEST_REWARD)
                         else
                         "采集链 (IsSpell()&&!flag2) leg 145 ActivateState(BIRTH)"
                         "（AlphaTool.Renderer.cs:AlphaTool.CreateActor；引擎同区 BigCard.cs:"
                         "1430-1431 num==0 leg；SpellTable 槽 145 映射）")
            vr_tags = ([1440] + ([4503] if is_timewarped else [])) \
                if not (is_coin or is_coin_std) else [202]
        comp: dict = {"path": full_path, "node": parts[-1],
                      "visible": True, "raster": True,
                      "material_slots": slots,
                      "visibility_rule": {
                          "rule": vr_rule,
                          "source": vr_source,
                          "tags_used": vr_tags},
                      }
        ov = _btf_blend_override(mats[0]["name"], rep)
        if ov is not None:
            comp["material_override"] = ov
        comp_log.append(comp)

    log = {"shield": want_shield, "coin": want_coin, "coin_std": want_coin_std,
           "coin_hp": want_coin_hp, "coin_trinket": want_coin_trinket,
           "coin_quest_reward": want_coin_quest_reward,
           "alt_coin": is_alt_coin, "alt_coin_spell": alt_coin_key,
           "tech_level": tech_level,
           "timewarped": is_timewarped, "bg_style_mode": mode,
           "n_components": len(comp_log), "n_npz_nodes": _npz_node_count(npz_sources, bnpz),
           "st_baked_nodes": sum(1 for v in npz_sources.values() if "uv0_baked" in v)}
    return {"applied": True, "frame_key": frame_key,
            "nodes": nodes, "components": comp_log, "npz_sources": npz_sources,
            "log": {**log,
            "source": "ur_frames.compile_tier_spell（bacon-tier-frame 2026-10-06"
                      "+tl0-coin-face 2026-10-07 coin_std 腿"
                      "+bacon-hero-power-coin 2026-10-21 coin_hp 腿"
                      "+timewarped-cost-base 2026-10-31 alt_coin 腿）"}}


def _btf_blend_override(mat_name: str, rep: dict) -> dict | None:
    """提取报告 blend 面 → material_override（_badge_blend_mode 同判，数据源=btf
    提取账 spell_prefabs_report.json materials[名].blend，非共享材质态表）。multiply
    （DstColor/Zero）走既有 multiply 通路；opaque 不写 override；unknown 记账不拦。

    合成式随材质 **shader 身份**透传（`_multiply_form`）：`Hero/Multiply/Multiply` 的
    PS 是 `dst *= tex + vColor`（RenderDoc PS `add o0.xyz,r0,v2`、DstColor/Zero），
    非 `tex × tint`——btf 供给材质不在材质态表内（`raster.multiply_form` 查不到行），
    故由提取账 `materials[名].shader` 在注入期随 override 指定。"""
    ment = rep.get("materials", {}).get(mat_name) or {}
    blend = ment.get("blend") or {}
    mode = blend.get("mode")
    if mode == "multiply":
        ov = {"blend": "multiply",
              "source": (f"材质态（btf 提取）{mat_name} 主色 pass "
                         f"{(rep['materials'][mat_name].get('shader'))}（Hero/Multiply/Multiply）"
                         "→ spell_prefabs_report.json materials")}
        if ment.get("shader") == _raster.MULTIPLY_ADD_SHADER:
            ov["_multiply_form"] = _raster.MULTIPLY_FORM_ADD_VCOLOR
        return ov
    return None


def _multiply_color_props(ment: dict) -> dict:
    """btf 材质账 color 面 → 组件材质 `colors`（raster tint/vColor 供给）。

    **只对加性 multiply shader（`Hero/Multiply/Multiply`）透传 `_Color`**：该 shader 的
    真 tint 通道是顶点色（材质 `_Color` 烘进运行时影网格色流；序列化 prefab 网格无
    m_Colors），`_Color` 是序列化侧唯一等价物（币影 0.11321 / 盾影 0 逐值实证）。
    其余 shader 一律不透传——`_Color` 不进它们的 PS（如 Gem_Mana_Coin 的
    DiffuseAlphaMaskScroller），而 `raster` 的 `colors._Color` 是 tint 乘法因子，错透传
    会把币面压暗。前提与弃用条件见 raster.raster_multiply。"""
    if ment.get("shader") != _raster.MULTIPLY_ADD_SHADER:
        return {}
    col = (ment.get("colors") or {}).get("_Color")
    return {"_Color": list(col)} if col else {}


# ============================================================================
# bacon rig — BG 英雄帧 rig（CustomHeroFrameBehaviour，正典 bacon-hero-frames §2）
# ============================================================================

_BACON_RIG_NPZ_KEY = "extra/frame_rig"
_BACON_RIG_FRAME_KEY = "Card_Play_Bacon_Hero"  # consumer-v2 改键


@parallel
def compile_bacon_hero_frame(frame_key: str) -> dict | None:
    """BG 英雄帧 rig 挂载清单（hero_play_bacon 专用；非 bacon 键 → None 原样透传）。

    引擎语义：Card_Play_Bacon_Hero 根 CustomHeroFrameBehaviour（RequireComponent
    (Actor)）UpdateFrame→InstantiateFrameMesh（CustomHeroFrameBehaviour.cs:CustomHeroFrameBehaviour）
    ——m_defaultFrame（Bacon_HeroFrame_Default，prefab 根 Mono 外部引用）实例化到
    m_portraitMesh 下 localPosition=(0,0.1,0)、rot/scale 保留（rig 根恒等）。渲染面
    =rig 子 GenFX_Portrait_Hero：Hero_Mesh_Frame（200v/287tri 环带，无窗）×
    BaconHeroFrame_Hero（_MainTex=BaconGenFX_HeroFrame_Hero 银拱+紫带+暗晕整画纹理；
    PS o0=tex×vCOLOR、One/Zero opaque、无 _Color 槽——tint=白恒等）。序列化 prefab
    不含 rig（运行时实例化件）；世界 = 宿主 Mesh 节点 world × T(0,0.1,0)（+0.1
    世界 y=深度轴前置 → zbuf 后画覆盖原网格外带，参照银环位置实证）。rig 账=
    bacon kit meta.frame_rig（供给三件套：数组/纹理/账，批9c 内存面）。"""
    if frame_key != _BACON_RIG_FRAME_KEY:
        return None
    scene = _frames.scene_for(frame_key)
    # rig 账层级：旧 plan["frame_rig"]["source"]=hero_render_bacon 由 kit.meta
    # ["frame_rig"] 整体充任（内含 source/material/mesh/host_local_pos）——本模块
    # 直读 kit meta 同一层（读取别名归一，供给面不动）。
    rig_meta = scene["meta"].get("frame_rig") or {}
    mat_meta = rig_meta.get("material") or {}
    if not rig_meta:
        raise RuntimeError("hero_play_bacon: kit meta 缺 frame_rig 账（供给缓存陈旧？"
                           "重建 kit）")
    host_path = portrait_binding(frame_key)["node"]
    host_world = _node_world(scene["hierarchy"], host_path)
    assert host_world is not None, f"帧层级无宿主 {host_path}"

    k = _frames.kit_for(frame_key)
    rig_tex = mat_meta.get("main_tex", {}).get("file")
    assert rig_tex, "frame_rig 材质账缺 _MainTex file"
    _bt = k.textures
    _key = rig_tex if rig_tex in _bt else f"{rig_tex}.png"
    tex_img = _bt[_key]

    local_pos = rig_meta.get("host_local_pos") or [0.0, 0.1, 0.0]
    t_mat = np.eye(4)
    t_mat[0, 3], t_mat[1, 3], t_mat[2, 3] = local_pos
    rig_world = host_world @ t_mat

    full_path = f"{host_path}/Custom Frame"
    rig_mat_name = mat_meta.get("name") or "BaconHeroFrame_Hero"
    arrays = k.arrays
    tails = [t for t in ("verts", "uv0", "uv1") if f"{_BACON_RIG_NPZ_KEY}/{t}" in arrays]
    n_subs = 0
    si = 0
    while f"{_BACON_RIG_NPZ_KEY}/sub{si}" in arrays:
        tails.append(f"sub{si}")
        n_subs += 1
        si += 1
    nodes = {full_path: {
        "name": "Custom Frame",
        "path": full_path,
        "world": rig_world.tolist(),
        "renderers": [{"enabled": True,
                       "materials": [{"name": rig_mat_name,
                                      "tex": {"_MainTex": {"texture": {"image": tex_img}}},
                                      "colors": {"_Color": [1.0, 1.0, 1.0, 1.0]}}]}],
        "mesh_stats": {"name": (rig_meta.get("mesh") or {}).get("name") or "Hero_Mesh_Frame",
                       "verts": (rig_meta.get("mesh") or {}).get("verts"),
                       "submesh_tris": (rig_meta.get("mesh") or {}).get("submesh_tris")},
        "frame_rig_source": {"go": rig_meta.get("source", {}).get("go"),
                             "bundle": rig_meta.get("source", {}).get("bundle"),
                             "host_local_pos": local_pos},
    }}
    comp = {"path": full_path, "node": "Custom Frame",
            "visible": True, "raster": True,
            "material_slots": [{"slot": 0, "material": rig_mat_name,
                                "_MainTex_runtime": {
                                    "image": tex_img,
                                    "source": "BaconHeroFrame_Hero._MainTex 直提"
                                              "（BaconGenFX_HeroFrame_Hero，kit rig 账）"}}],
            "visibility_rule": {
                "rule": "CustomHeroFrameBehaviour 实例化 rig（引擎恒跑，无 tag 门）",
                "source": "CustomHeroFrameBehaviour.cs:CustomHeroFrameBehaviour（UpdateFrame/LoadFrameMesh/"
                          "InstantiateFrameMesh）+ CardDef.m_FrameMeshOverride null 实测",
                "tags_used": [],
                "note": "无 tag 门（CustomHeroFrameBehaviour.Awake→UpdateFrame 恒跑；"
                        "m_FrameMeshOverride 优先，本族 null）",
            }}
    npz_sources = {full_path: {"kind": "kit_arrays", "prefix": _BACON_RIG_NPZ_KEY,
                               "tails": tails}}
    log = {"applied": True, "host": host_path, "node": full_path,
           "mesh": (rig_meta.get("mesh") or {}).get("name"),
           "tex": rig_tex, "n_npz_nodes": (2 + (1 if "uv1" in tails else 0) + n_subs) // 2}
    return {"applied": True, "frame_key": frame_key,
            "nodes": nodes, "components": [comp], "npz_sources": npz_sources,
            "log": log}


# ============================================================================
# rune_banner — DK 符文横幅（UpdateCardRuneBannerComponent :6116-6133 三链）
# ============================================================================

LAYOUT_SLOTS = {
    "OneRune": ["Resource_Rune"],
    "TwoRunes": ["Resource_Rune (1)", "Resource_Rune (2)"],
    "ThreeRunes": ["Resource_Rune (3)", "Resource_Rune (4)", "Resource_Rune (5)"],
}
RUNE_BANNER_ROOTS: dict[str, str] = {   # prefab → 符文横幅根名（consumer-v2 改键；spell_dk 行消亡）
    "Card_Hand_Ability": "Card_Hand_Ability",
    "Card_Hand_Ally": "Card_Hand_Ally",           # bacon ally kit 同 prefab（Card_Hand_Ally）
    "Card_Hand_Ally_Premium": "Card_Hand_Ally_Premium",   # 金卡档（mechorse-golden 2026-10-21）
    "Card_Hand_Weapon": "Card_Hand_Weapon",
    "Card_Hand_Hero": "Card_Hand_Hero",
    "Card_Hand_Location": "Card_Hand_Location",
}
RUNE_BASE = "Card_Hand_Ability/RootObject/RuneBanner"   # spell 族正典路径（兼容旧引用）
PATH_HOLDER = f"{RUNE_BASE}/Card_Hand_Deathknight_Banner/RuneHolder_Mesh"
PATH_SHADOW = f"{RUNE_BASE}/Card_Hand_Deathknight_Banner/RuneHolder_Shadow_Mesh"

RUNE_ATLAS_OFFSET = {"BLOOD": (0.0, 0.5), "FROST": (0.5, 0.5), "UNHOLY": (0.0, 0.0)}
RUNE_ATLAS_SCALE = (0.5, 0.5)
"""Rune.cs:Rune.GetRuneMaterial GetRuneMaterial → Rune_Blood_sm/Rune_Frost_sm/Rune_Unholy_sm
（prefab 实测，_MainTex 图集偏移；CardRunes_DeathKnight 256² 四象限）——dk_render
常量存根 verbatim 沿袭（图集真身经 recipes.frames.dk.rune_atlas 内存面）。"""

TINT_FIX_PROVENANCE = (
    "PS 反汇编 o0=tex×v2(COLOR)（rd_rune_shader_prog_p4_n1_DX11PixelSM40.asm:23-24）；"
    "VS o2=(1+cb2[1].x·(sRGB(cb1[27..29].w)+cb0[6].rgb−1))×COLOR_vs（_n0 asm:23-44），"
    "常量槽只读 cb2[0]=_MainTex_ST / cb2[1].x / cb0[4].x=MipBias——材质 _Color 未被引用；"
    "dk-runes 逐像素拟合（findings §阴影，corr 0.89、ratio/tex.rgb 中位 1.028）同结论："
    "final = dst.rgb × tex.rgb，_Color=(0,0,0,1) 黑不进 rgb 因子")


@parallel
def compile_rune_banner(card: Card, frame_key: str, *, shadow_fix: bool = True) -> dict:
    """DK 符文横幅挂载清单（frame_key 查表定挂点根名 RUNE_BANNER_ROOTS；判定纯 tag
    数据驱动 EntityBase.cs:EntityBase.GetBloodCost 无 CLASS 门，非符文卡终点=Hide（只记账零组件变更））。

    返回 plan["rune_banner"] 键构+逐节点挂接记录（nodes：{path: {visible/raster/
    material_override/main_tex_runtime/visibility_rule}}，S11 对 plan["components"]
    同路径组件原位应用——旧 compile 内 assert 节点在位+材质名对号随 S11 消费 plan
    时执行）。运行时激活路径翻 raster=True：hero_hand 帧整棵 RuneBanner 子树序列化
    inactive → 帧编译置 raster=False，引擎同构 CardRuneBanner.Show →
    m_runeBannerBackground.SetActive(true)（dk-runes findings §5.2）。"""
    root = RUNE_BANNER_ROOTS.get(frame_key)
    assert root is not None, \
        f"帧 {frame_key} 无 RuneBanner 挂点（play/heropower actor prefab 实测无此子树）"
    rune_base = f"{root}/RootObject/RuneBanner"
    path_holder = f"{rune_base}/Card_Hand_Deathknight_Banner/RuneHolder_Mesh"
    path_shadow = f"{rune_base}/Card_Hand_Deathknight_Banner/RuneHolder_Shadow_Mesh"
    blood = int(card.rune_blood)
    frost = int(card.rune_frost)
    unholy = int(card.rune_unholy)
    combined = blood + frost + unholy
    rule = {"has_rune_cost": combined > 0,
            "tags_used": [int(GameTag.COST_BLOOD), int(GameTag.COST_FROST), int(GameTag.COST_UNHOLY)],
            "pattern": {"blood": blood, "frost": frost, "unholy": unholy, "combined": combined}}
    if combined <= 0:
        return {**rule, "visible": False,
                "source": "Actor.cs:Actor.UpdateCardRuneBannerComponent（非符文卡路径）"}
    assert combined <= 3, combined
    layout = ["OneRune", "TwoRunes", "ThreeRunes"][combined - 1]  # CardRuneBanner.cs:CardRuneBanner.Show
    seq = (["BLOOD"] * blood) + (["FROST"] * frost) + (["UNHOLY"] * unholy)  # RunePattern.cs:RunePattern

    runes = []
    nodes: dict[str, dict] = {}
    atlas_img = dk.rune_atlas()
    for i, rt in enumerate(seq):
        p = f"{rune_base}/RuneLayouts/{layout}/{LAYOUT_SLOTS[layout][i]}/Rune"
        nodes[p] = {
            "visible": True,
            "raster": True,  # 运行时激活路径须翻回（dk-runes findings §5.2）
            "material_override": {
                "_MainTex.offset": list(RUNE_ATLAS_OFFSET[rt]),
                "_MainTex.scale": list(RUNE_ATLAS_SCALE),
                # 组件级 ST 消费口：weapon/hero/ally/location 链 zbuf_policy uv_scale=False
                # （符文字形 quad UV 0..1 全幅，引擎侧 _MainTex_ST 恒被 shader 消费
                # ——cb2[0]，TINT_FIX_PROVENANCE asm 账）；spell 族链 uv_scale=True 本就消费，
                # 键存在与否不影响其结果（非符文卡无此 mo → 行为逐位不变）。
                "_uv_transform": True,
                "source": f"Rune.cs:Rune.GetRuneMaterial GetRuneMaterial(Default) → Rune_{rt.capitalize()}_sm 偏移"},
            "main_tex_runtime": {
                "image": atlas_img,   # 内存面（mip_registry CardRunes L0）
                # 纹理身份（2026-10-23 weapon-dk-frame）：CardRunes_DeathKnight_sm 是带
                # mip 的纹理（m_MipCount=9 / filter=1 / bias=−0.5），引擎采样器按 LOD 点选层；
                # 本键让光栅走真 mip 链（raster._slot_mip_entry 名字通道，L0 逐位校验）。
                "mip_name": "CardRunes_DeathKnight_sm",
                "source": "Rune_*_sm._MainTex → CardRunes_DeathKnight_sm（mip_registry "
                          "CardRunes_DeathKnight_sm L0，批9c 内存面）"},
            "visibility_rule": {
                "rule": f"CombinedValue={combined} → {layout}[{i}]={LAYOUT_SLOTS[layout][i]}",
                "source": "CardRuneBanner.cs:CardRuneBanner.Show + RuneSlotVisual.cs:RuneSlotVisual.UpdateRuneSlots + prefab 计划实测"
                          "（rune-samples；槽 GO 名表）",
                "tags_used": [int(GameTag.COST_BLOOD), int(GameTag.COST_FROST), int(GameTag.COST_UNHOLY)]},
        }
        runes.append({"slot": i, "go": LAYOUT_SLOTS[layout][i], "rune_type": rt, "path": p})

    shadow_mo = {
        "blend": "multiply",
        "source": "RuneBanner_Card_Shadow_Mat shader pass（dk-runes findings §阴影）+ "
                  "PS 反汇编（rd_extract_rune_shader.py → output/rd_rune_shader_*.asm）",
    }
    if shadow_fix:
        shadow_mo["_tint_rgb"] = [1.0, 1.0, 1.0]
        shadow_mo["tint_rule"] = TINT_FIX_PROVENANCE
    for p, mat in ((path_holder, "RuneBanner_Card"), (path_shadow, "RuneBanner_Card_Shadow_Mat")):
        rec: dict = {"visible": True, "material": mat,
                     # 运行时激活路径翻回 raster（同字形 quads 理由）：hero_hand 帧整棵
                     # RuneBanner 子树序列化 inactive → 帧编译置 raster=False。引擎同构：
                     # CardRuneBanner.Show → m_runeBannerBackground.SetActive(true)。
                     "raster": True,
                     "visibility_rule": {
                         "rule": "CardRuneBanner.cs:CardRuneBanner.Show CombinedValue>0 → m_runeBannerBackground SetActive(true)",
                         "source": "Actor.cs:Actor.UpdateCardRuneBannerComponent + prefab MB dump（dk-runes）",
                         "tags_used": [int(GameTag.COST_BLOOD), int(GameTag.COST_FROST), int(GameTag.COST_UNHOLY)]}}
        if p == path_shadow:
            rec["material_override"] = shadow_mo
        nodes[p] = rec

    return {**rule, "visible": True, "layout": layout, "runes": runes,
            "shadow_fix": shadow_fix, "frame_key": frame_key, "nodes": nodes}


# ============================================================================
# 语境 mode 轴（bg_mode 判定面：AlphaTool.Pipeline.cs:AlphaTool.ImportJsonSelectAndRun useBattlegroundsStyle）
# ============================================================================

BGS_SET_ID = 1453
"""set==BGS 数值锚（离线 GetCardSet 正典 card_set_offline 的 set_id 值域）。卡牌 id
字符串前缀≠set（BGS_Treasures_010 set 确为 1453；BG_OG_145 set=21——「id 不承载
语义」实证对）。"""


@parallel
def derive_bg_mode(card: Card) -> str | None:
    """缺省 mode 推导（数据驱动）：set==BGS(1453) → "bacon"（仅酒馆形态，单身份）；
    set!=BGS ∧ TECH_LEVEL>0 → "constructed"（双身份卡缺省构筑形态）；其余 → None
    （非 TECH_LEVEL 卡 mode 无语义，渲染零影响）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    if card.set_id == BGS_SET_ID:   # set_id 可为 None（card_set_offline 缺位）——直比较同旧面
        return "bacon"
    if int(card.tech_level) > 0:
        return "constructed"
    return None


@parallel
def resolve_bg_mode(card: Card, use_bg_style) -> str | None:
    """mode 三态消费：cfg 显式 True/False（对齐注入器 useBattlegroundsStyle bool 开关，
    AlphaTool.Pipeline.cs:AlphaTool.ImportJsonSelectAndRun）优先，None=数据推导（derive_bg_mode）。"""
    if use_bg_style is not None:
        return "bacon" if use_bg_style else "constructed"
    return derive_bg_mode(card)


# ============================================================================
# 接线段（批22 兑现：hierarchy copy-on-write 变异+MergedNpz 合并+plan 挂接）
# ============================================================================

_BADGE_ARRAY_HEADS = ("tradeable", "forgeable", "prepareable")
_TIER_ARRAY_HEADS = ("tech_level_mana_gem", "timewarped_tier_icon",
                     "coin_mana_gem_bacon_spell", "coin_mana_gem",
                     "coin_mana_gem_hero_power", "coin_mana_gem_trinket",
                     "cost_alt_tavern_coin_ally", "cost_alt_tavern_coin_ability")
"""btf npz 前缀头白名单（注入数组源分派——新 spell_key 进供给配方必须同步入表，
新前缀=域形状变化；assert 缺行=响亮，禁静默回落。schema 取号语义（旧 CACHE_SCHEMA
5→6闸）随三态缓存退役（consumer-arch 批11d）由本表+响亮供给守卫承位：供给=每会话
游戏直提内存面，无盘上陈旧面可陈；前缀缺席在 compile 期 RuntimeError。）"""


def _arrays_for(source: dict):
    """npz_sources 条目 → 数组源（kind 分派：quad=内联载荷 / kit_arrays=帧 kit /
    npz=按 prefix 头段查注入域 kit——badges 三头/faction 头/btf 四头）。"""
    kind = source.get("kind")
    if kind == "quad":
        return None
    if kind == "kit_arrays":
        return _frames.kit_for(source.get("frame_key", _BACON_RIG_FRAME_KEY)).arrays
    head = source["prefix"].split("|", 1)[0]
    if head in _BADGE_ARRAY_HEADS:
        return _inj.badge_kit_mem()["arrays"]
    if head == "faction":
        return _inj.faction_kit_mem()["arrays"]
    assert head in _TIER_ARRAY_HEADS, f"未知注入 npz 前缀头 {head!r}（数组源分派表外）"
    return _btf_assets()[1]


def _place_node(hierarchy: dict, path: str, node: dict) -> dict:
    """copy-on-write 放置：从根到父链浅拷贝（dict+children list），节点挂入父
    children（既有同名子=替换〔载荷保留既有 children——裸链成形节点被后至同路径
    载荷覆盖时链结构不丢〕，否则追加）；中间段缺=裸链节点成形（_copy_path_to/
    _append_under/_chain_node 三件合并形，ur_frames 注入族同语义——badges 中间段
    不在 nodes 清单，调用方以 sorted(path) 序保证父先于子）。路径首段=根名
    （walk 路径以根名开头，_copy_path_to :29 同款跳过）。返回新根；场景缓存的
    层级对象不被原位变异。"""
    segs = path.split("/")
    new_root = dict(hierarchy)
    new_root["children"] = list(hierarchy.get("children") or [])
    cur = new_root
    prefix = ""
    for i, seg in enumerate(segs[:-1]):
        if i == 0 and seg == hierarchy.get("name"):
            continue   # 首段=根名：起点即根（_copy_path_to 同款）
        prefix = f"{prefix}/{seg}" if prefix else seg
        children = cur.setdefault("children", [])
        idx = next((j for j, ch in enumerate(children) if ch["name"] == seg), None)
        if idx is None:
            nxt = {"name": seg, "children": []}
            children.append(nxt)
        else:
            nxt = dict(children[idx])
            nxt["children"] = list(nxt.get("children") or [])
            children[idx] = nxt
        cur = nxt
    node = {**node, "children": list(node.get("children") or [])}
    children = cur.setdefault("children", [])
    tail = segs[-1]
    idx = next((j for j, ch in enumerate(children) if ch["name"] == tail), None)
    if idx is None:
        children.append(node)
    else:
        # 载荷覆盖既有节点（裸链成形/重复放置）：children 以在场者为准（链结构不丢）
        node["children"] = list(children[idx].get("children") or []) or node["children"]
        children[idx] = node
    return new_root


def _placement_order(paths) -> list[str]:
    """放置序（old chain_roots sorted append 同构）：按「帧根后首段」（=old rel
    parts[0]=chain_roots 键）分组，组间字典序（old tier_spell :352
    `sorted(chain_roots.items())`——267 金币链先于 156/308 盾徽链的序列化依据），
    组内保持产物插入序（badges/faction 单组=纯插入序）。"""
    groups: dict[str, list[str]] = {}
    for p in paths:
        parts = p.split("/")
        head = parts[1] if len(parts) > 1 else parts[0]
        groups.setdefault(head, []).append(p)
    out: list[str] = []
    for head in sorted(groups):
        out.extend(groups[head])
    return out


@parallel
def apply_injections(plan: dict, frame_key: str, products: list, hierarchy: dict, npz,
                     walk=None):
    """注入件接线段：compile 产物（挂接清单）→ hierarchy copy-on-write 变异+
    MergedNpz 合并+plan["components"] 挂接+plan 键写位——旧注入四件段
    （old_frames/render_card.py:357-388）的执行面对位（批22 兑现）。

    products=:357-388 执行序的 compile 产物列（badges→faction_banner→tier_spell→
    frame_rig；None 项跳过——无激活=原样透传）。每件：
      * nodes 全路径 copy-on-write 注入（_place_node；中间段裸链成形）；
      * npz_sources 合并进 MergedNpz（键=walk key/尾段；quad=内联几何、
        kit_arrays=帧 kit 数组、npz=注入域 kit 前缀）；
      * components 计划挂接（路径去重 append——重复挂载守卫）；
      * log 键写位：plan["badges"]/["faction_banner"]/["tier_spell"]/
        ["frame_rig"]["applied"]（账面串=批20 compile 产物 verbatim）。
    textonly 整段跳过由调用方执行（triple-report 账——:361 同判）。
    符文原位应用不在本函数（products 形态不含 rune 产物——apply_rune_banner
    独立腿，:644-645 对位）。walk=None 时用包内 walk_with_key（S11 单源晚引）。
    返回 (hierarchy_r, npz_final, logs dict)。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    from eidolon.core.render.game.actor.components import MergedNpz, walk_with_key
    walk = walk or walk_with_key
    hierarchy_r = hierarchy
    npz_final = npz
    logs: dict = {}
    for product in products:
        if not product or not product.get("applied"):
            continue
        log = product.get("log") or {}
        sources = product.get("npz_sources") or {}
        # 数组源按件 memo（同件多前缀共享一 kit arrays）
        arrays_memo: dict[int, object] = {}
        for full_path, source in sources.items():
            arrays_memo[id(source)] = _arrays_for(source)
        # hierarchy copy-on-write 注入（nodes 全路径——放置序=_placement_order）
        for full_path in _placement_order(product.get("nodes") or {}):
            hierarchy_r = _place_node(hierarchy_r, full_path,
                                      product["nodes"][full_path])
        # npz 合并（键=注入后实现树 walk key/尾段）
        extra: dict = {}
        for n, wk, p in walk(hierarchy_r):
            source = sources.get(p)
            if source is None:
                continue
            arrays = arrays_memo[id(source)]
            kind = source.get("kind")
            if kind == "quad":
                for tail in ("verts", "uv0", "sub0"):
                    if tail in source:
                        extra[f"{wk}/{tail}"] = source[tail]
            elif kind == "kit_arrays":
                prefix, tails = source["prefix"], source["tails"]
                for tail in tails:
                    baked = source.get("uv0_baked")
                    extra[f"{wk}/{tail}"] = (baked if tail == "uv0" and baked is not None
                                             else arrays[f"{prefix}/{tail}"])
            else:
                prefix = source["prefix"]
                for tail in ("verts", "uv0"):
                    baked = source.get("uv0_baked")
                    extra[f"{wk}/{tail}"] = (baked if tail == "uv0" and baked is not None
                                             else arrays[f"{prefix}/{tail}"])
                si = 0
                while f"{prefix}/sub{si}" in arrays:   # NpzFile/dict 双形（in 即成员判）
                    extra[f"{wk}/sub{si}"] = arrays[f"{prefix}/sub{si}"]
                    si += 1
        if extra:
            npz_final = MergedNpz(npz_final, extra)
        # 计划组件挂接（路径去重）+ plan 键写位（log 键构分派件型）
        have = {c["path"] for c in plan["components"]}
        plan["components"].extend(
            [c for c in product.get("components") or [] if c["path"] not in have])
        if "containers" in log:
            plan["badges"] = log
        elif "faction_index" in log:
            plan["faction_banner"] = log
        elif "shield" in log:
            plan["tier_spell"] = log
        elif "host" in log:
            plan.setdefault("frame_rig", {})["applied"] = log
        else:
            raise AssertionError(f"注入产物件型不可辨（log 键构={sorted(log)}）")
        logs[product.get("frame_key", frame_key) + f"#{len(logs)}"] = log
    return hierarchy_r, npz_final, logs


@parallel
def apply_rune_banner(plan: dict, product: dict | None) -> dict | None:
    """符文横幅原位应用（old render_with :644-645 compile_rune_banner 的接线半边；
    批22 兑现——批20 职责切分：compile 产物=批20 compile_rune_banner，原位应用=
    本函数）。

    对 plan["components"] 同路径组件原位应用（visible/raster 翻回+材质名对号
    assert+材质 override/_MainTex_runtime/visibility_rule 写入）；非符文卡终点=
    Hide（compile 产物 visible=False——只记账零组件变更，像素逐位不变）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    if product is None:
        return None
    if not product.get("visible"):
        plan["rune_banner"] = product
        return product
    for p, rec in product["nodes"].items():
        ent = next((c for c in plan["components"] if c["path"] == p), None)
        assert ent is not None, f"计划缺符文节点 {p}"
        ent["visible"] = rec["visible"]
        ent["raster"] = rec["raster"]   # 运行时激活路径翻回（dk-runes findings §5.2）
        if rec.get("material_override") is not None:
            ent["material_override"] = rec["material_override"]
        if rec.get("main_tex_runtime") is not None:
            ent["material_slots"][0]["_MainTex_runtime"] = rec["main_tex_runtime"]
        if rec.get("visibility_rule") is not None:
            ent["visibility_rule"] = rec["visibility_rule"]
        if rec.get("material") is not None:
            assert any(s["material"] == rec["material"] for s in ent["material_slots"]), p
    plan["rune_banner"] = product
    return product


# ============================================================================
# 私有面（层级定位/npz 计数）
# ============================================================================


def _node_at(hierarchy: dict, path: str) -> dict | None:
    """层级内按 path 定位节点（容器/根定位——world 来源；帧 recon 容器节点自带
    world）。路径首段=根名（walk 路径以根名开头）。"""

    def _walk(node: dict, prefix: str) -> dict | None:
        p = f"{prefix}/{node['name']}" if prefix else node["name"]
        if p == path:
            return node
        for ch in node.get("children") or ():
            hit = _walk(ch, p)
            if hit is not None:
                return hit
        return None

    return _walk(hierarchy, "")


def _node_world(hierarchy: dict, path: str) -> np.ndarray | None:
    nd = _node_at(hierarchy, path)
    return np.array(nd["world"], dtype=np.float64) if nd is not None else None


def _npz_tail_count(prefix: str, arrays) -> int:
    n = 2   # verts + uv0
    si = 0
    while f"{prefix}/sub{si}" in arrays:
        n += 1
        si += 1
    return n


def _npz_node_count(npz_sources: dict, arrays) -> int:
    """旧 n_npz_nodes=len(extra)//2 同构计算（extra 每 npz 叶=verts+uv0+subN；
    quad 载荷不在此账——faction 用 _faction_npz_count）。"""
    total = sum(_npz_tail_count(v["prefix"], arrays)
                for v in npz_sources.values() if v.get("kind") == "npz")
    return total // 2


def _faction_npz_count(npz_sources: dict, arrays) -> int:
    """旧 faction n_npz_nodes=len(npz_extra)//3 同构（quad 叶=verts/uv0/sub0 三键，
    npz 叶=verts+uv0+subN）。"""
    total = 0
    for v in npz_sources.values():
        if v.get("kind") == "quad":
            total += 3
        else:
            total += _npz_tail_count(v["prefix"], arrays)
    return total // 3
