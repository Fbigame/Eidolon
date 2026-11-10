"""gems — Actor 宝石族（段 S6 费用/攻血/稀有度判定与装配参数）。

游戏锚：Actor.UpdateRarityComponent（Actor.cs:Actor.UpdateRarityComponent——四子物体 SetActive，
SIGNATURE 特判 :4939-4959）· Actor.SetRarityGemShape（:4992）·
Actor.GetRarityTextureOffset（:4964 起，:5024-5070 区段——图集偏移+tint，常量
GEM_TEXTURE_OFFSET_*/GEM_COLOR_* Actor.cs:Actor）· UpdateCostTextMesh/
UpdateAttackTextMesh/UpdateHealthTextMesh（Actor.cs:Actor.UpdateCostTextMesh/:4107/:4148，EntityDef
版 :3278/:3418/:3478）· Actor.UpdateManaGemOffset（37.0 :6593-6599——cost 文本铸币
位移 m_alternateCostTextLocalPos :566 代码默认）· Actor.UseTechLevelManaGem
（:6812-6837——BG 盾徽门，随从恒真/法术需 TECH_LEVEL）· UpdateManaGemComponent
（:5183-5210——game option 三旗门，NORMAL 手牌恒显）。
宝石 shader：DXBC 10 指令直译 rgb = albedo.rgb + cloud.x·_tint.rgb·albedo.a
·1.5·_Intensity，相位 t=(P/20)%0.2（_Time.x；textless-ref §7.5 冻结采集裁定）；
云层=裸 uv+T·speed，_MainTex 图集 offset 只进主纹采样（E8 VS 字节码 o1.zw，
gem-and-flat-card-assets 云层语义节）。

我方对位：collect_stat_gems/render_stat_gems（old_paint/ur_core.py:667/:698——
Gem_Mana 网格投影+序列化参数，E9 归一单实现）· composite_rarity_gem_canonical
（:780——云层采样修正，E8 VS 字节码 o1.zw）· COST_PHASE
（old_frames/render_card.py:253-279——费用亚像素相位表；2026-11-01 cost-phase-closure
起相位由 uber_text._numeric_phase_y 引擎锚公式闭算，2026-11-02 cost-phase-untested
起闭算为缺省路由+延旧集显式守卫，本表降级为验算账、cost_phase_for 退役）·
_rarity_visible（old_frames/scene_compiler.py:207-226，七编译器共引）+
_frame_components rarity 段（:402-410）· prep 宝石相位 t=_Time.x
（old_plan/prep_plan.py:92）+ cost_text_semantics（:54-88）·
_cost_alt_node_settings（render_card.py:282——世界平移覆写，S11 消费形）。

配方面：宝石槽清单/mana_albedo/clouds/rarity_atlas 经 recipes.gems；
Gem_Mana 网格经 recipes.frames.ability_kit；帧 kit report 经 recipes.frames
（gem_binding 消费）。

批16 实现账（2026-10-14，S6 生长；统筹职责切分=Actor 宝石判定/装配参数平行——
像素合成（shader DXBC 直译/云层采样）属 engine 侧 S9/S11 段本期不实现，
collect_stat_gems/render_stat_gems/composite_rarity_gem 三件立户）：

纪律面前置——gem_binding 经 recipes.frames 域项（frames.scene_for→kit @item）
触供给配方，**消费须在 supply session 内**（入口层独占纪律，批12/13/14/15 同款；
未来门驱动循环开 session 调本段，段内不开）。

职责面六件——
  * rarity visible 判定（get_rarity_texture_offset/update_rarity_component）：
    GetRarityTextureOffset 逐字（MISSIONS 腿/SIGNATURE 特判腿/rarity switch，
    缺省 offset/tint=COMMON 值直返）+UpdateRarityComponent 四子物体 SetActive 面
    （gem/frame EnableRenderers+地标 m_rarityNoGemMesh 反相+材质写点参数面）。
  * 形状切换（set_rarity_gem_shape）：SetRarityGemShape 四 mesh SetActive+
    SetRarityGemMesh switch（COMMON/FREE 同槽）。
  * 绑定（gem_binding）：kit report actor_components[0].object_refs 直读
    （portrait_binding 批15 同式）——play 双链 prefab 无宝石族对象→None 位=
    decomp (bool)m_rarityGemMesh 门关（帧相关不可硬编码）。
  * 费用显隐判定链（cost_text_semantics/use_tech_level_mana_gem）：数据腿
    （Card.cost_hidden_reason 三锚链）+语境腿（mode=bacon 盾徽门替代）+
    alt_pos 腿（IsBaconSpell→EnableAlternateCostTextPosition）。
  * 铸币位移（update_mana_gem_offset）：UpdateManaGemOffset 三条件门离线形+
    m_alternateCostTextLocalPos 策略面（S11 _cost_alt_node_settings 消费形）。
  * 相位与 plan 键构（plan_rarity_gem/plan_gem）：COST_PHASE 验算账（数字角色相位
    闭算缺省=uber_text._numeric_phase_y，2026-11-01 cost-phase-closure；2026-11-02
    cost-phase-untested 起闭算路由反转+延旧集显式守卫、cost_phase_for 旧表路径
    退役）+plan.rarity_gem 七编译器同构段统一形+plan.gem 统一形（enabled=
    m_manaObject 在位推导）。

签名修正清单（批11b 立壳→实现，批12/13/15 先例同权）——
  * update_mana_gem_offset (plan, card)→(card, *, bg_style=None, mana_object=True,
    cost_text_mesh=True)：stub 首参 plan 系误推（offset 策略 dict 是产物非入参）；
    判定链吃 Card+渲染语境（bacon），不吃 plan。
  * cost_phase_for (plan, card)→(key, *, bg_style=None)：stub 双参系误推——旧实现
    (key: str, plan: dict)（render_card.py:276），plan 只为读 _bg_style 语境；
    相位表键=帧键。返回 tuple（旧同形；stub「返回相位 float」系误推——COST_PHASE
    值为 (φu,φv) 二维）。
  * collect_stat_gems/render_stat_gems/composite_rarity_gem 签名不动（ur_core
    公式层继承形；S9/S11 生长时自本段装配参数取数）。

decomp 分支的离线边界（记录的缺口，非静默丢弃）——
  * SIGNATURE 特判腿（:4939-4959 特判+:5038-5049 GetRarityTextureOffset 内）：
    GetSignatureFrameId（ActorNames.cs:ActorNames.GetSignatureFrameId=GameDbf.SignatureFrame DBF 映射，
    批12 get_signature_actor 立户同族）离线缺位→signature_frame_id 参数位
    （None=特判腿不触发记账，落 rarity switch；非 None 逐字判 !=1，命中时
    offset/tint=COMMON 缺省值直返——decomp :5027-5028 缺省不被 switch 覆写）。
  * CARD_SET=MISSIONS 腿（:5031-5036）：TAG_CARD_SET.MISSIONS=5 直判（GetTag
    缺省 0≠5）。旧 _rarity_visible 只照录规则不实判（tag 183 在 CARD_TAG 0 行
    缺省账）——新按 decomp 实判，语料 127 张 CARD_SET 全 0 零行为（duipai 探针
    实证），规则面 decomp 更正记账。
  * ShouldHideCost 对局态腿（:4006-4030——BG shop phase/CARD_ALTERNATE_COST/
    showCostOverride/BaconSpell friendly-side）：对局态，不接线。EntityDef 版 :3282 的
    **IsCardButton 腿已接线**（2026-10-23 heropower-hidden-cost：IsCardButton 对
    HERO_POWER/LOCATION/GAME_MODE_BUTTON/LETTUCE_ABILITY 恒真，配 TRIGGER_VISUAL 即
    「被动英雄技能」→ 费用文本空、水晶保留；74786 实证。BG 例外 HAS_ACTIVATE_POWER
    同式入判）；showCostOverride 仍为选项态不接线。数据腿=HIDE_STATS→HIDE_COST→
    DORMANT 三锚链，infra Card.cost_hidden_reason 单实现。
  * UseTechLevelManaGem 游戏实体门（GetGameEntityIfAllowed().HasTag
    TECH_LEVEL_MANA_GEM :6813-6815）与 checkInPlay 区链（:6819-6824 ZoneMgr
    对局态）：离线 gate 参数位默认 False=门关；mode=bacon 显式替代（prep 语境
    腿同账）。随从恒真腿 decomp 不查 TECH_LEVEL、旧合并式要求 tech_level>0
    （BG 随从恒带 TECH_LEVEL——语料等价，记账）。
  * UpdateManaGemComponent（:5183-5210 game option 三旗+TL/Coin gem 门）：
    NORMAL 手牌恒显（旧 visibility_rule 同账），game option 腿不接线。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from eidolon.core.render.engine import raster as _raster

from eidolon.core.infra.card import (BG_MINION_CARDTYPE, BG_SPELL_CARDTYPE, Card,
                                CardType, GameTag, Premium, Rarity)
from eidolon.core.infra import il_tables
from eidolon.core.render.scenes import scenes as _frames
from eidolon.core.render._provenance import invented  # noqa: F401 （按需；fitted 随
# cost_phase_for 退役离场——2026-11-02 cost-phase-untested，本模块零拟合件）
from eidolon.core.render._provenance import parallel  # noqa: F401 （族默认）

# ============================================================================
# 常量面（Actor.cs:Actor decomp 直读；对拍转正=duipai 正则直读核同，批12 三表先例）
# ============================================================================

def _live_gem_tables() -> tuple[dict[str, tuple[float, ...]],
                                dict[str, tuple[float, ...]]]:
    """Actor..ctor GEM_TEXTURE_OFFSET_*/GEM_COLOR_* readonly 字段活读
    （hand-table-residuals 2026-11-06 换轨，手抄两表退役）。

    提取=il_tables.ctor_object_fields（Vector2 n=2 / Color n=3；实证=Actor.cs:Actor
    ctor 字段族 :101-115）。键=字段名后缀（==Rarity 活镜像成员名，名字连结）。
    形状断言=两表四臂同集 ∧ 后缀全落 Rarity 成员名 ∧ offset ∈ {0.0,0.5}²（GenFX_
    RarityGems 四象限底账，gem-and-flat-card-assets）∧ rgb∈[0,1]³。引擎加稀有度
    臂/改象限→红→重锚。改轨前对拍=evidence/probe_hand_tables.json（4+4 臂 f32
    容差 1e-5 全等）。锚 file:il_tables.ctor_object_fields。
    """
    colors = il_tables.ctor_object_fields("Actor", "Color", const_count=3)
    offsets = il_tables.ctor_object_fields("Actor", "Vector2", const_count=2)
    gem_c = {k[len("GEM_COLOR_"):]: tuple(v) for k, v in colors.items()
             if k.startswith("GEM_COLOR_")}
    gem_o = {k[len("GEM_TEXTURE_OFFSET_"):]: tuple(v) for k, v in offsets.items()
             if k.startswith("GEM_TEXTURE_OFFSET_")}
    rarity_names = {m.name for m in Rarity}
    assert len(gem_c) == len(gem_o) == 4 and set(gem_c) == set(gem_o), (
        f"GEM 字段臂漂移（color={sorted(gem_c)} offset={sorted(gem_o)}）——"
        "引擎四臂形态变更，先核 Assembly-CSharp 再重锚")
    bad = sorted((set(gem_c) | set(gem_o)) - rarity_names)
    assert not bad, f"GEM 字段后缀非 Rarity 成员名（{bad}）——名字连结漂移"
    assert all(v in (0.0, 0.5) for t in gem_o.values() for v in t), (
        f"GEM_TEXTURE_OFFSET 越象限域（{gem_o}）——四象限底账变更")
    assert all(0.0 <= v <= 1.0 for t in gem_c.values() for v in t), (
        f"GEM_COLOR 越色域（{gem_c}）")
    return gem_o, gem_c


_GEM_OFFSET_BY_NAME, _GEM_COLOR_BY_NAME = _live_gem_tables()

GEM_TEXTURE_OFFSET: dict[int, tuple[float, float]] = {
    int(Rarity[name]): v for name, v in _GEM_OFFSET_BY_NAME.items()}
"""稀有度宝石图集偏移（活读 Actor..ctor GEM_TEXTURE_OFFSET_*，f32 真值；键=
TAG_RARITY 活镜像值。GenFX_RarityGems 四象限 TL 灰/TR 蓝/BL 紫/BR 橙——
gem-and-flat-card-assets 象限底账；Repeat wrap 采样落位，ally_recon wrap 注）。

换轨注（hand-table-residuals 2026-11-06）：手抄十进值（0.549/0.1529…）退役——
活值=f32 解码真值（0.5490000247955322…），与手抄差 ~1e-8（f32 表示误差）；下游
uniform f32 化后逐位同（6 卡 4x sha256 逐位比对账=本实验 evidence）。"""

GEM_COLOR: dict[int, tuple[float, float, float]] = {
    int(Rarity[name]): v for name, v in _GEM_COLOR_BY_NAME.items()}
"""稀有度宝石 _tint 着色（活读 Actor..ctor GEM_COLOR_*，f32 真值；蓝色宝石=
云层染色+tint 双面，shader 正典 gem-shader-recon）。换轨注同 GEM_TEXTURE_OFFSET。"""

_GEM_RARITIES = (int(Rarity.COMMON), int(Rarity.RARE), int(Rarity.EPIC),
                 int(Rarity.LEGENDARY))
"""GetRarityTextureOffset switch 开放位（:5051-5069；FREE/INVALID=default→false）。"""

_GEM_DEFAULT_LEG = (int(Rarity.FREE), int(Rarity.INVALID))
"""引擎 default 腿语义成员（decomp switch default→false）——合法无宝石档，
显式记账非静默回落（residual-silent-fallbacks 2026-11-05 收口）。"""

_CARD_SET_MISSIONS = 5
"""TAG_CARD_SET.MISSIONS（TAG_CARD_SET.cs:TAG_CARD_SET.MISSIONS；GetTag 缺省 0=INVALID≠MISSIONS）。"""


@parallel
def rarity_display(rarity: int) -> str:
    """Rarity → tag_enum s_rarityNames 显示串（scene_compiler.RARITY_DISPLAY
    :126-127 平行——枚举成员单源派生：INVALID 全大写特例，余首字母大写）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    name = Rarity(int(rarity)).name
    return name if name == "INVALID" else name.capitalize()


# ============================================================================
# GetRarityTextureOffset 判定（Actor.cs:Actor.GetRarityTextureOffset 离线形）
# ============================================================================


@parallel
def get_rarity_texture_offset(rarity: int, *, premium: int = int(Premium.NORMAL),
                              card_set: int = 0,
                              signature_frame_id: int | None = None) -> dict:
    """稀有度宝石可见性+图集偏移+tint：GetRarityTextureOffset 对位
    （Actor.cs:Actor.GetRarityTextureOffset 离线形）。

    rarity=TAG_RARITY（Card.rarity，dbf tag 203）；premium=m_premiumType；
    card_set=TAG_CARD_SET（GetCardSet tag 183 缺省 0）；signature_frame_id=
    GetSignatureFrameId(cardId)（ActorNames.cs:ActorNames.GetSignatureFrameId DBF 映射）离线参数位
    （None=缺位，特判腿不触发记账）。

    链序（引擎逐字）：缺省 offset/tint=COMMON 值（:5027-5028）→ MISSIONS 腿
    （:5031-5036 false）→ SIGNATURE 特判腿（:5038-5049，frameId!=1→true 且
    缺省 COMMON 值直返——switch 未及）→ rarity switch（:5051-5069，开放位
    COMMON/RARE/EPIC/LEGENDARY；FREE/INVALID=default→false）。返回
    {"visible", "branch", "offset", "tint", ...}；写点（mainTextureOffset/
    SetColor("_tint") :4979-4977）属 S11 组装段。"""
    rarity = int(rarity)
    if rarity not in _GEM_RARITIES and rarity not in _GEM_DEFAULT_LEG:
        # 响亮面（residual-silent-fallbacks 2026-11-05 收口）：旧形未知值混落
        # gemless 缺省——活镜像外裸 int 与无臂新成员两态都不得静默 gemless
        # （fail-closed；语料 RARITY 值 1-5 全落已臂/default 腿，零扰动）。
        try:
            name = Rarity(rarity).name
        except ValueError:
            raise ValueError(
                f"未知稀有度 {rarity}——TAG_RARITY 活镜像（{len(Rarity)} 成员）外值："
                "宝石判定 fail-closed，禁静默 gemless"
                "（residual-silent-fallbacks 2026-11-05 收口）") from None
        raise ValueError(
            f"稀有度 {name}({rarity}) 无宝石臂且非 default 腿语义成员（FREE/INVALID）——"
            "新品质档先判宝石消费语义再入册（gems 收口 residual-silent-fallbacks "
            "2026-11-05），禁静默 gemless")
    offset = GEM_TEXTURE_OFFSET[int(Rarity.COMMON)]      # :5027-5028 缺省=COMMON
    tint = GEM_COLOR[int(Rarity.COMMON)]
    out: dict = {"rarity": rarity, "rarity_display": rarity_display(rarity),
                 "premium": int(premium), "card_set": int(card_set),
                 "source": "Actor.cs:Actor.GetRarityTextureOffset GetRarityTextureOffset + 常量 :101-115"
                           "（离线判定形）"}
    if int(card_set) == _CARD_SET_MISSIONS:                            # :5031-5036
        out.update({"visible": False, "branch": "card_set_missions",
                    "offset": None, "tint": None})
        return out
    if (int(premium) == int(Premium.SIGNATURE)
            and signature_frame_id is not None
            and int(signature_frame_id) != 1):                         # :5038-5049
        out.update({"visible": True, "branch": "signature_frame",
                    "offset": list(offset), "tint": list(tint),
                    "boundary": "SIGNATURE 特判腿命中：offset/tint=COMMON 缺省值直返"
                                "（switch 未及，decomp :5027-5028×:5044-5048）"})
        return out
    if int(premium) == int(Premium.SIGNATURE) and signature_frame_id is None:
        out["boundary"] = ("GetSignatureFrameId（ActorNames.cs:ActorNames.GetSignatureFrameId，GameDbf."
                           "SignatureFrame DBF 映射）离线缺位——SIGNATURE 特判腿不触发"
                           "记账（批12 get_signature_actor 立户同族），落 rarity switch")
    if rarity in _GEM_RARITIES:                                        # :5051-5069 switch
        out.update({"visible": True, "branch": "rarity",
                    "offset": list(GEM_TEXTURE_OFFSET[rarity]),
                    "tint": list(GEM_COLOR[rarity])})
    else:                                                              # FREE/INVALID
        out.update({"visible": False, "branch": "gemless",
                    "offset": None, "tint": None,
                    "boundary": "FREE/INVALID=引擎 GetRarityTextureOffset default 臂"
                                "语义成员（decomp default→false）——合法无宝石档显式"
                                "记账（residual-silent-fallbacks 2026-11-05；活镜像外/"
                                "无臂新成员已在函数头响亮，不经此腿）"})
    return out


# ============================================================================
# SetRarityGemShape（Actor.cs:Actor.SetRarityGemShape）——SIGNATURE 特判四子物体切换
# ============================================================================


@parallel
def set_rarity_gem_shape(rarity: int, *, signature_frame_id: int | None = None,
                         meshes_present: bool = True) -> dict:
    """稀有度宝石形状切换：SetRarityGemShape 对位（Actor.cs:Actor.SetRarityGemShape）。

    门（:4993）=GetSignatureFrameId(cardId)!=1 ∧ 四 mesh 非空——cardId 仅经
    GetSignatureFrameId 消费，离线=DBF 缺位参数（signature_frame_id）。四腿
    SetActive（:4994-4997：COMMON∨FREE→common；余按等值）+SetRarityGemMesh
    switch（:4999-5009，m_rarityGemMesh 重绑；COMMON/FREE 同槽）。门关（非
    SIGNATURE 特判路径/缺位）返回 gated=True 记账面（四腿 None=不触达）。"""
    rarity = int(rarity)
    if not (signature_frame_id is not None and int(signature_frame_id) != 1
            and meshes_present):
        return {"gated": True, "common": None, "rare": None, "epic": None,
                "legendary": None, "gem_mesh": None,
                "gate": "GetSignatureFrameId!=1 ∧ 四 mesh 非空（:4993）不满足"
                        "（离线=DBF 缺位参数或语料非 SIGNATURE 特判路径）",
                "source": "Actor.cs:Actor.SetRarityGemShape SetRarityGemShape + :5012-5022 "
                          "SetRarityGemMesh"}
    gem_mesh = {int(Rarity.COMMON): "Common", int(Rarity.FREE): "Common",
                int(Rarity.RARE): "Rare", int(Rarity.EPIC): "Epic",
                int(Rarity.LEGENDARY): "Legendary"}[rarity]            # :5012-5022
    return {"gated": False,
            "common": rarity in (int(Rarity.COMMON), int(Rarity.FREE)),  # :4994
            "rare": rarity == int(Rarity.RARE),                        # :4995
            "epic": rarity == int(Rarity.EPIC),                        # :4996
            "legendary": rarity == int(Rarity.LEGENDARY),              # :4997
            "gem_mesh": gem_mesh,
            "source": "Actor.cs:Actor.SetRarityGemShape SetRarityGemShape + :5012-5022 "
                      "SetRarityGemMesh"}


# ============================================================================
# UpdateRarityComponent（Actor.cs:Actor.UpdateRarityComponent 离线形）——四子物体 SetActive 面
# ============================================================================


@parallel
def update_rarity_component(rarity: int, *, premium: int = int(Premium.NORMAL),
                            card_set: int = 0,
                            signature_frame_id: int | None = None,
                            is_location: bool = False,
                            has_rarity_gem_mesh: bool = True,
                            has_rarity_frame_mesh: bool = True,
                            has_rarity_no_gem_mesh: bool = False) -> dict:
    """稀有度组件更新：UpdateRarityComponent 对位（Actor.cs:Actor.UpdateRarityComponent 离线形）。

    链序（引擎逐字）：SIGNATURE 特判（:4939-4959，premium==SIGNATURE 且
    GetSignatureFrameId!=1→SetRarityGemShape）→ (bool)m_rarityGemMesh 门
    （:4960）→ GetRarityTextureOffset 裁决 → EnableRenderers(gem[, frame], v)
    （:4964-4968）→ 地标腿（:4969-4977，IsLocation=EntityBase.cs:EntityBase.IsLocation
    CARDTYPE==39；m_rarityNoGemMesh.SetActive(!v)）→ 材质写点（:4979-4977，
    mainTextureOffset/_tint——S11 组装段，此处只产参数面）。

    has_* 三参=prefab 绑定在局面（gem_binding 缺席 ref=None 同象；heropower
    prefab 无稀有度宝石对象=门关实例）。返回判定+四子物体产物 dict。"""
    face = get_rarity_texture_offset(rarity, premium=premium, card_set=card_set,
                                     signature_frame_id=signature_frame_id)
    shape = None
    if int(premium) == int(Premium.SIGNATURE):                          # :4939-4959
        shape = set_rarity_gem_shape(rarity, signature_frame_id=signature_frame_id)
    visible = bool(has_rarity_gem_mesh) and face["visible"]             # :4960-4963
    return {"premium": int(premium), "rarity": face["rarity"],
            "rarity_display": face["rarity_display"],
            "visible": visible,
            "rarity_gem_enabled": visible,        # EnableRenderers(gem, v) :4964-4965
            "rarity_frame_enabled": visible if has_rarity_frame_mesh else None,  # :4966-4968
            "no_gem_active": (not face["visible"])                        # :4969-4977
            if (is_location and has_rarity_no_gem_mesh) else None,
            "material_override": ({"_MainTex.offset": face["offset"],    # :4979-4977
                                   "_tint_rgb": face["tint"]}
                                  if visible else None),
            "shape": shape,
            "boundary": face.get("boundary"),
            "source": "Actor.cs:Actor.UpdateRarityComponent UpdateRarityComponent（离线判定形；"
                      "材质实例写点属 S11 组装段）"}


# ============================================================================
# 宝石族绑定面（kit report 直读；portrait_binding 批15 同式）
# ============================================================================


@parallel
def gem_binding(frame_key: str) -> dict:
    """宝石族对象绑定：kit report actor_components[0].object_refs 直读
    （旧编译器 binding 的 gem 行平行——scene_compiler.py:248-252 直键/
    hero_render.py:207-213 防御式 get，两形归一读取）。

    返回 {"rarity_gem_node", "rarity_frame_node", "rarity_no_gem_node",
    "mana_node", "elite_node"}（缺席 ref=None——play 双链 prefab 无宝石族对象=
    decomp (bool)m_rarityGemMesh 门关；location 独有 m_rarityNoGemMesh）。
    帧相关不可硬编码（走链零硬编码 pid 同纪律）；未知帧键由 frames.kit_for
    assert 响亮（批14 tripwire）。消费须在 supply session 内（模块 docstring
    纪律面前置）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    refs = (_frames.scene_for(frame_key)["report"]["actor_components"][0]
            .get("object_refs") or {})
    return {
        "rarity_gem_node": (refs.get("m_rarityGemMesh") or {}).get("node"),
        "rarity_frame_node": (refs.get("m_rarityFrameMesh") or {}).get("node"),
        "rarity_no_gem_node": (refs.get("m_rarityNoGemMesh") or {}).get("node"),
        "mana_node": (refs.get("m_manaObject") or {}).get("node"),
        "elite_node": (refs.get("m_eliteObject") or {}).get("node"),
    }


# ============================================================================
# plan 键构（plan.rarity_gem / plan.gem——七编译器同构段统一形）
# ============================================================================


@parallel
def plan_rarity_gem(card: Card, *, signature_frame_id: int | None = None) -> dict:
    """plan.rarity_gem 键构：七编译器同构段统一形（scene_compiler.py:207-226/:328
    ——ally:275/hp:231/hero:255/bacon:128/location:237/wf:221 全部共引
    sc._rarity_visible）。键位逐字保真（visible/rule/source/tags_used/rarity/
    atlas_offset/tint_rgb）；判定面=get_rarity_texture_offset（MISSIONS 腿新按
    decomp 实判——语料零行为，模块 docstring 偏差账）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    face = get_rarity_texture_offset(card.rarity, premium=int(card.premium),
                                     card_set=int(card.card_set),
                                     signature_frame_id=signature_frame_id)
    return {"visible": face["visible"],
            "rule": "GetRarityTextureOffset (Actor.cs:Actor.GetRarityTextureOffset)：RARITY∈{Common,"
                    "Rare,Epic,Legendary} → true+图集偏移/着色；FREE/INVALID → false；"
                    "CARD_SET=MISSIONS → false",
            "source": "Actor.cs:Actor.UpdateRarityComponent (UpdateRarityComponent), :5024-5070 "
                      "(GetRarityTextureOffset), 常量 :101-115",
            "tags_used": [int(GameTag.RARITY), int(GameTag.CARD_SET)],
            "rarity": face["rarity_display"],
            "atlas_offset": face["offset"],
            "tint_rgb": face["tint"]}


@parallel
def plan_gem(frame_key: str, *, t: float) -> dict:
    """plan.gem 键构：七编译器 gem 段统一形（scene_compiler.py:330-337/
    ally:364-371/hp:295-300/wf:301-306/location:322-327/hero:341-346/
    bacon:211-216）。行为面=enabled/t/mesh_node：enabled=m_manaObject 在位推导
    （手牌七链 prefab 有→True；hero_play/hero_play_bacon 无→False，旧
    enabled=(mode=='hand')/False 同象）；t=语料捕获时刻（prep 注入
    plan["gem"]["t"]）。**t 必填**（text-default-phase 2026-10-22：会话相位逐卡
    参考量，本层不设缺省；编译期占位/诊断面由调用方显式传
    eidolon.core.render.params.DEFAULT_SESSION_T）。material/render 等编译器自注串=
    差异记账（统一形不保真，批15 plan_portrait source/apply 同款）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    b = gem_binding(frame_key)
    return {"enabled": b["mana_node"] is not None,
            "t": float(t),
            "t_note": "参照帧相位标定值（cb0[15].x，云层动画未定态；gem-shader-recon "
                      "§6）——prep 注入语料时刻 t（t=(P/20)%0.2，textless-ref §7.5）",
            "mesh_node": b["mana_node"],
            "visibility_rule": "UpdateManaGemComponent (Actor.cs:Actor.UpdateManaGemComponent)：仅 game "
                               "option/bgs 分支隐藏，NORMAL 手牌恒显",
            "source": "Gem_Mana 材质序列化+帧 kit（recipes.gems/frames；shader 公式"
                      "=gem-shader-recon DXBC 直译，像素合成属 S9/S11）"}


# ============================================================================
# 费用显隐判定链（UpdateCostTextMesh :3278/:4006 离线数据腿+语境腿）
# ============================================================================

_COST_ALT_LOCAL_POS = (-0.01, 0.003, -0.58)
"""m_alternateCostTextLocalPos **C# 字段默认值**（Actor.cs:Actor `m_alternateCostTextLocalPos
= new Vector3(-0.01f, 0.003f, -0.58f)`），不是全帧族有效值。

引擎真值=**逐 prefab 序列化**（Unity 反序列化覆盖字段默认）：Card_Hand_Ally / Card_Hand_Ability
= −0.01，**Card_Hand_Ally_Premium = +0.025**（2026-11-04 golden-alt-cost-pos 实测；Δ0.035
× 176.75 px/unit = 6.19px，金随从帧费用数字整字偏左 6.15px 的根因）。故渲染侧取值=帧 kit
meta `actor_alt_cost_pos`（supply/kits.py、supply/ability.py 自 prefab 读），本常量只作
**缺字段回退**。

失效条件：prefab 无 m_alternateCostTextLocalPos（形态漂移）或帧链未携 actor_alt_cost_pos
（新帧型未接线）时回退到本值——此时金/异帧可能再次整字偏移，判据=该帧 z_cost_timewarped
（普通帧 1.8–2.1；偏一帧即 30+）。"""

_COST_ALT_PARENT_SUFFIX = "NonQuestObjects/CostObject"
"""CostUberText 父节点路径后缀（prep _COST_ALT_PARENT_SUFFIX；S11 世界平移覆写
定位形，render_card._cost_alt_node_settings :282 消费）。"""


@parallel
def cost_text_semantics(card: Card, *, bg_style: str | None = None) -> dict | None:
    """费用文本显隐+铸币位移判定链：prep_plan.cost_text_semantics 对位
    （old_plan/prep_plan.py:54-88 离线形；引擎=UpdateCostTextMesh EntityDef 版
    Actor.cs:Actor.UpdateCostTextMesh + ShouldHideCost Entity 版 :4006-4030）。

    显隐=数据腿（Card.cost_hidden_reason：HIDE_STATS→HIDE_COST→DORMANT 三锚链，
    Actor.cs:Actor.UpdateCostTextMesh+EntityBase.cs:EntityBase.GetRaces/:384-387——infra 单实现）
    + CardButton 腿（IsCardButton∧HasTriggerVisual∧(非 BG∨!HAS_ACTIVATE_POWER)→文本空、水晶保留，
    Actor.cs:Actor.UpdateCostTextMesh EntityDef 版 :3293；74786 血色异术 = 英雄技能+TRIGGER_VISUAL，
    DBF 无 HIDE_COST 而引擎仍清数字的唯一支路）
    + 语境腿（mode=bacon 盾徽门显式替代游戏实体 TECH_LEVEL_MANA_GEM tag 门，
    UseTechLevelManaGem :6812-6837×:3282；4503 timewarped 例外=数字不藏，见函数内注释）。
    位移腿=IsBaconSpell（EntityBase.cs:EntityBase.IsBaconSpell CARDTYPE==42）
    → EnableAlternateCostTextPosition（BigCard.cs:BigCard.LoadSecondaryBigCardIfNeeded/:1980）
    + timewarped 底座腿（4503 ∧ ct∈{4,5,42}——底座蓝宝石中心即数字位，见函数内注释）。

    返回 {"hide": 原因串|None, "alt_pos": [x,y,z]|bacon 咒语}；两者皆无→None
    （旧同款）。cost 条目 render=False 与 plan["_cost_alt_pos"] 写点=消费侧
    （S11 装配，batch15 判定/写点切分同款）。"""
    cardtype = int(card.cardtype)
    hide = card.cost_hidden_reason
    if hide is None and card.is_card_button and card.has_trigger_visual \
            and not (bg_style == "bacon" and card.has_activate_power):
        hide = ("CardButton 腿（IsCardButton∧HasTriggerVisual(32)，BG 下例外 HAS_ACTIVATE_POWER(2840)>0；"
                "Actor.cs:Actor.UpdateCostTextMesh EntityDef 版）→ 费用文本空、水晶保留"
                "（EntityDef 版只清 Text；对照 Entity 版 ShouldHideCost 连水晶一起 ScaleToZero）")
    # timewarped 例外（timewarped-cost-base 2026-10-31）：4503 卡的费用数字不藏。三源同指——
    # ①引擎 unhide 腿 Actor.cs:Actor.ShouldHideCost :4022 `flag2 = CARD_ALTERNATE_COST==
    #   ALT_TAVERN_COIN(5) ∧ zone≠HAND → return false（显示）`：替费卡（timewarped 在酒馆
    #   即 ALT_TAVERN_COIN 语境）不藏数字；②同函数之后的 :4069 `BACON_TIMEWARPED(4503)`
    #   分支给数字上色（BACON_OVERRIDE_COST_COLOR）——藏了就不必上色，反证数字可见；
    #   ③采集链（oracle 生成方）AlphaTool.Renderer.cs:187 `if (!flag)` 才藏、
    #   flag=4408∨4503 → timewarped 不藏；新 oracle 10 卡（底座区）与 36.6 参照
    #   （128044/126286 白数字 vs 99579 无数字）逐像素同证。离线无 CARD_ALTERNATE_COST/
    #   zone 轴 → 代理=4503（数据驱动，禁逐卡表；非 timewarped BG 卡 65248/99579 仍藏）。
    if hide is None and bg_style == "bacon" and cardtype != BG_SPELL_CARDTYPE \
            and int(card.tech_level) > 0 \
            and cardtype in (BG_MINION_CARDTYPE, int(CardType.SPELL)) \
            and not int(card.timewarped) > 0:
        hide = ("UseTechLevelManaGem 语境腿（mode=bacon 显式替代游戏实体 tag 门，"
                "Actor.cs:Actor.GetGameEntityIfAllowed/:6812-6837×:3285；65248 参照=盾徽无数字；"
                "timewarped(4503) 例外见上条注释）")
    account: dict = {"hide": hide}
    # 位移腿（UpdateManaGemOffset Actor.cs:6595 三条件门 → m_costTextMesh.localPosition=
    # m_alternateCostTextLocalPos；旗=EnableAlternateCostTextPosition :1203）：
    #   * bacon 法术（ct42）恒开——decomp 直锚 BigCard.cs:457/1980 `EnableAlternate…
    #     (entity.IsBaconSpell())`，数字落 267/底座币心；
    #   * timewarped 随从/法术（4503 ∧ (ct42 ∨ (TL>0 ∧ ct∈{4,5}))）同开——底座件
    #     （COST_ALT_TAVERN_COIN 303，injectors alt_coin 腿同式）的蓝宝石中心就是数字位，
    #     不开位移则数字停在普通费用位（屏幕 y≈131）而 oracle 在底座中心（y≈250）。
    #     偏离记账：decomp 全程序集只 BigCard 两处调此旗（无手牌 Actor 调用点），采集链
    #     则对 flag2 腿（(IsSpell()||IsMinion())∧TL>0）**全体**开位移
    #     （AlphaTool.Renderer.cs:169-172）——本链取采集链形，但只在该位移有像素后果
    #     （数字可见=timewarped 底座腿）时开，非 timewarped 卡逐位不变；判据=新 oracle。
    if bg_style == "bacon" and (
            cardtype == BG_SPELL_CARDTYPE                                   # :556-559
            or (int(card.timewarped) > 0 and int(card.tech_level) > 0
                and cardtype in (BG_MINION_CARDTYPE, int(CardType.SPELL)))):
        account["alt_pos"] = list(_COST_ALT_LOCAL_POS)
    return account if (hide or account.get("alt_pos")) else None


@parallel
def use_tech_level_mana_gem(card: Card, *, tech_level_mana_gem_gate: bool = False,
                            check_in_play: bool = False, zone_play: bool = False,
                            controlled_by_friendly_side: bool = True,
                            bg_battle_phase: bool = False) -> bool:
    """BG 盾徽门：UseTechLevelManaGem 对位（Actor.cs:Actor.UseTechLevelManaGem 逐字离线形）。

    门序：游戏实体 TECH_LEVEL_MANA_GEM tag 门（GetGameEntityIfAllowed().HasTag
    :6813-6815——对局态，离线参数位默认 False=门关；mode=bacon 显式替代，prep
    语境腿同账）→ 随从恒真腿（:6816-6826；checkInPlay 时 ZonePlay∧(友方侧∨
    战斗阶段) 反旋——ZoneMgr 对局态参数位）→ 法术腿（TECH_LEVEL tag∧(IsBaconSpell
    ∨IsSpell) :6827-6836；HasTag=GetTag>0 EntityBase.cs:EntityBase.HasTag）。decomp 随从腿
    不查 TECH_LEVEL（恒真）；cost_text_semantics 语境腿要求 tech_level>0=旧合并
    式（BG 随从恒带 TECH_LEVEL，语料等价——模块 docstring 边界账）。"""
    if not tech_level_mana_gem_gate:                                    # :6813-6815
        return False
    ct = int(card.cardtype)
    if ct == int(CardType.MINION):                                      # :6816-6818
        if check_in_play and zone_play and (controlled_by_friendly_side
                                            or bg_battle_phase):        # :6819-6824
            return False
        return True                                                    # :6826
    if ct in (BG_SPELL_CARDTYPE, int(CardType.SPELL)) \
            and int(card.tech_level) > 0:                              # :6827-6836
        return True
    return False                                                       # :6836-6837


# ============================================================================
# 铸币位移（Actor.cs:Actor.UpdateManaGemOffset，37.0 :6593-6599 离线形）
# ============================================================================


@parallel
def update_mana_gem_offset(card: Card, *, bg_style: str | None = None,
                           mana_object: bool = True,
                           cost_text_mesh: bool = True) -> dict:
    """cost 文本铸币位移：UpdateManaGemOffset 对位（Actor.cs:Actor.UpdateManaGemOffset 离线形）。

    引擎三条件门（m_manaObject ∧ m_costTextMesh ∧ m_useAlternateCostTextPos）
    → cost 文本 localPosition 强制 m_alternateCostTextLocalPos（**逐 prefab 序列化**：
    Ally/Ability=−0.01，Ally_Premium=+0.025；本模块 `local_pos` 返回 C# 默认值，仅记账/
    回退，渲染取值面=帧 meta actor_alt_cost_pos，见 _COST_ALT_LOCAL_POS 注）。
    m_useAlternateCostTextPos 离线推导=IsBaconSpell
    （EntityBase.cs:EntityBase.IsBaconSpell；EnableAlternateCostTextPosition 调用位
    BigCard.cs:BigCard.LoadSecondaryBigCardIfNeeded/:1980）+ **timewarped 底座腿**
    （4503 ∧ (ct42 ∨ (TL>0 ∧ ct∈{4,5}))——底座件蓝宝石中心即数字位；
    cost_text_semantics 同式，两实现保持同判）。

    返回 {"applied", "local_pos", "alt_pos", "source"}：alt_pos=plan
    ["_cost_alt_pos"] 键构面（local/parent_suffix/rule/source——S11
    _cost_alt_node_settings 世界平移覆写消费形，render_card.py:282）；
    applied=False 时 local_pos/alt_pos 均 None。"""
    ct = int(card.cardtype)
    enabled = bg_style == "bacon" and (
        ct == BG_SPELL_CARDTYPE
        or (int(card.timewarped) > 0 and int(card.tech_level) > 0
            and ct in (BG_MINION_CARDTYPE, int(CardType.SPELL))))
    applied = bool(mana_object and cost_text_mesh and enabled)          # :6595
    alt = None
    if enabled:
        alt = {"local": list(_COST_ALT_LOCAL_POS),
               "parent_suffix": _COST_ALT_PARENT_SUFFIX,
               "rule": ("UpdateManaGemOffset（Actor.cs:Actor.UpdateManaGemOffset）× "
                        "IsBaconSpell（EntityBase.cs:EntityBase.IsBaconSpell）/ timewarped "
                        "底座腿（4503，底座蓝宝石中心即数字位）：cost 文本铸币位"
                        " m_alternateCostTextLocalPos（逐 prefab 序列化；此处 local=代码默认回退）"),
               "source": ("BigCard.cs:BigCard.SetupActor + 采集链 AlphaTool.Renderer.cs:"
                          "AlphaTool.CreateActor（flag2 腿）"
                          "；probe=evidence/actor_alt_pos_ability.json"
                          "（bg-cost-anchor 实验档）+ 本批 probe_alt_cost_pos")}
    return {"applied": applied,
            "local_pos": list(_COST_ALT_LOCAL_POS) if applied else None,
            "alt_pos": alt,
            "source": "Actor.cs:Actor.UpdateManaGemOffset UpdateManaGemOffset + "
                      "EnableAlternateCostTextPosition :1194-1196（离线形）"}


# ============================================================================
# 费用亚像素相位表（render_card.py:253-279 实测标定沿袭；2026-11-01
# cost-phase-closure 闭算关闭「明标未闭」账；2026-11-02 cost-phase-untested 起
# 闭算路由反转为缺省（uber_text._numeric_phase_y 接管），同日 ability-premium-phase
# 98918 锐扫 argmin=闭算值后延旧集守卫清零（uber_text 延旧常量已删）——本表=纯验算账
# （历史 1/64 网格快照，零消费位）；cost_phase_for/COST_PHASE_BACON 旧表路径退役
# ============================================================================
COST_PHASE: dict[str, tuple[float, float]] = {
    "Card_Hand_Ability": (0.0, -0.25),          # 诊断 4 锁：126616/68307/8/117544（ability 帧 CostUberText）
    "Card_Hand_Ally": (0.0, -0.25),           # 诊断 56806（ally 帧 CostUberText）
    "Card_Hand_Ally_Premium": (0.0, -0.25),   # 金卡档沿 ally 值（mechorse-golden 2026-10-21；
                                    # BG 语境 cost 不渲，非 BG 金卡进渲染集时按
                                    # cost-glyph-impl 标定制实测复核）
    "History_HeroPower": (0.0, -0.203125),  # 诊断 82523 锐锁；s4 扫描 229 独立同值确认
    "Card_Hand_Weapon": (0.0, -0.25),         # s4 扫描 42700（锐锁）
    "Card_Hand_Location": (0.0, -0.25),       # s4 扫描 76981（锐锁）
    "Card_Hand_Hero": (0.0, -0.25),      # 112815 英雄手牌 textonly 1/64 锐扫：dy 0→3.333、
                                    # dy −0.25→0.441、两侧单调回升（与 spell/ally 同值）；
                                    # 67048 同帧同值改善（z_cost 2.628→1.053，z_health
                                    # 2.421→0.646）；7 无 cost 墨迹、零变化。
    "Card_Hand_BG_Trinket": (0.0, -0.25),        # ct44 trinket textonly 三卡实测（116510/116614/133060；
                                    # 116510/133060 锐谷同值：dy 0→max 77/87、−0.25→max 2/3）；
                                    # 与 spell/ally/weapon 同常量，非新拟合
}
"""cost 节点亚像素相位 φ 的历史验算账（帧族常数，2026-10-08 cost-glyph-impl P3
实测标定制——诊断 cg_phase_render sharp lock ±1/64px 劣化即真锁）。

**2026-11-01 cost-phase-closure 闭算（「明标未闭」账关闭）**：UB
SetupTextMeshAlignment（UberText.cs:UberText.SetupTextMeshAlignment）Center/Middle
臂确实恒零 C# 偏移，但锚定语义落 TextMesh 原生垂直锚（UberTextRendering.
SetTextAnchor→TextMesh.anchor）＝单行 MiddleCenter 行盒（metrics.height，含 hhea
lineGap）盒心对 pivot、基线=盒顶+浮点 ascent：
  baseline_img = pivot + ((hhea.asc+hhea.desc−hhea.gap)/2)·fs/upem·K
（Belwe_Outline 74：385×74/1024=27.822266 字体 px；K=k·local_scale·s）。与我方现链
（整型 ascent+asc−desc 盒）之差=**闭算式**
  phase_y = [(asc_f−asc_round)−gap_f/2]·K（Belwe 74 C=−0.177734 字体 px），
消费位=uber_text._numeric_phase_y（text_layer_plan；2026-11-02 cost-phase-untested
起闭算路由反转为缺省，本表不再作为路由键集——纯验算账）。
逐值验算：7 帧族 13 实例+ally_premium 3 实例全部 ≤1/64px 判等（下值=本式 1/64
网格快照；−0.25 vs −0.234375 之差=节点 lossyScale 1.0 vs 1.1261–1.16，非角色类
机制；heropower −0.203125=characterSize k=0.0065）。证据=本任务实验档 evidence/
（d1 反解 json/d2 d3 逐值 json/对比 CSV/decomp 摘录）。
未测帧族显式不设（=零相位，hero_hand 已由 112815 补入 2026-10-19）。2026-11-02
cost-phase-untested 取证：其余未测键全部零数字墨（anomaly cost=CostObject 序列化
失活 plan 恒 render=False、hero 双链整层 any(render)=False 不触达 text_layer_plan）
或延旧集显式守卫（Card_Hand_Ability_Premium，golden 98918 欠账——同日
ability-premium-phase 锐扫 argmin=闭算值后守卫清零，闭算路由唯一）——旧表路径
（cost_phase_for/COST_PHASE_BACON）退役，closed=False 清零。扫描 JSON=锚
（output/phi_scan_*.json）。
consumer-v2 改键=prefab 名；spell_dk 行消亡（与 ability 帧同构，97532 走 spell 行）。

**COST_PHASE_BACON 退役（2026-11-02 随旧表路径删除）**：bacon 语境覆写表
（bg-cost-anchor 2026-10-08 复测值 (0,−0.25)=spell 帧同相位；2026-11-01 退役为
验算账——闭算式接管后 bacon 与否同值，铸币位移只动 world_pos 不动 k/local_scale）。
唯一读位 cost_phase_for 同批退役；值=闭算式 1/64 网格快照（−0.25 vs −0.2513，
≤1/64 判等）。历史扫描锚=bg-cost-anchor 实验档 phi_scan_bacon_*.json。
"""


# ============================================================================
# 公式层立户（像素合成=engine 侧 S9/S11 段）
# ============================================================================


@parallel
def collect_stat_gems(hierarchy, plan: dict, walk) -> list[dict]:
    """stat 宝石收集：collect_stat_gems 对位（old_paint/ur_core.py:667 逐字转写，
    批22 兑现；walk=节点遍历生成器 (node, key, path)）。

    攻/血/费用晶体渲染参数（Gem_Attack/Gem_Health/Gem_Mana 网格×材质序列化；
    Gem_Mana 恒收——bacon 滤 Gem_Mana 走 bacon_plan_patch 计划面，此处照旧）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    vis = {c["path"]: c for c in plan["components"] if c.get("visible")}
    gems_out = []
    for n, key, path in walk(hierarchy):
        if n["name"] not in ("Gem_Attack", "Gem_Health", "Gem_Mana") or not n.get("mesh_stats"):
            continue
        if n["name"] != "Gem_Mana":
            comp = vis.get(path)
            if comp is None or not comp.get("visible"):
                continue
        rr = (n.get("renderers") or [{}])[0]
        mat = (rr.get("materials") or [None])[0]
        if not mat:
            continue
        tex_file = (mat["tex"].get("_MainTex", {}).get("texture") or {}).get("file")
        f = mat.get("floats", {})
        gems_out.append({
            "node": n["name"], "path": path, "npz_key": key,
            "main_tex_file": tex_file,
            "tint_rgb": mat["colors"]["_tint"][:3],
            "intensity": f.get("_Intensity", 1.0),
            "speed_xy": [f.get("_XSpeed", 5.0), f.get("_YSpeed", 0.2)],
            "scale_xy": [f.get("_ScaleX", 1.0), f.get("_ScaleY", 1.0)],
            "source": "材质序列化值（kit renderer materials；shader=宝石族 pid "
                      "9099378368919310605，公式字节级验证见 gem-shader-recon 正典）",
        })
    return gems_out


@parallel
def render_stat_gems(base, plan: dict, hierarchy, npz, get_tex, walk):
    """stat 宝石渲染：render_stat_gems 对位（old_paint/ur_core.py:698 逐字转写，
    批22 兑现）。rgb = clouds(uv·Scale + t·Speed).x · _tint · main.a · 1.5 ·
    _Intensity + main.rgb，不透明贴片（gem-shader-recon DXBC 10 指令直译）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    from PIL import Image

    from eidolon.core.render.engine.raster import project_world, sample_wrap
    if not plan["gem"]["enabled"] or not plan.get("stat_gems"):
        return base
    rgba_out = np.asarray(base.convert("RGBA"), dtype=np.float64) / 255.0
    rgb_out = rgba_out[..., :3]          # 三通道视图：宝石写点仍按 RGB 语义
    t = plan["gem"]["t"]
    clouds = np.asarray(get_tex("GenFX_clouds03.png"), dtype=np.float64) / 255.0
    tex_cache_local: dict[str, np.ndarray] = {}
    for g in plan["stat_gems"]:
        fname = Path(g["main_tex_file"]).name
        if fname not in tex_cache_local:
            tex_cache_local[fname] = np.asarray(get_tex(fname), dtype=np.float64) / 255.0
        main = tex_cache_local[fname]
        tint = np.array(g["tint_rgb"])
        du, dv = (t * g["speed_xy"][0]) % 1.0, (t * g["speed_xy"][1]) % 1.0
        for n, key, path in walk(hierarchy):
            if not n.get("mesh_stats") or path != g["path"]:
                continue
            verts = npz[f"{key}/verts"]
            uv0 = npz[f"{key}/uv0"]
            M = np.array(n["world"])
            vw = (M[:3, :3] @ verts.T).T + M[:3, 3]
            px, py = project_world(vw)
            tris = npz[f"{key}/sub0"]
            order = sorted(range(len(tris)),
                           key=lambda i: float(vw[tris[i], 1].mean()))
            for i in order:
                tri = tris[i]
                xs, ys = px[tri], py[tri]
                xmin = max(int(np.floor(xs.min())), 0)
                xmax = min(int(np.ceil(xs.max())), rgb_out.shape[1] - 1)
                ymin = max(int(np.floor(ys.min())), 0)
                ymax = min(int(np.ceil(ys.max())), rgb_out.shape[0] - 1)
                if xmin > xmax or ymin > ymax:
                    continue
                gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5,
                                     np.arange(ymin, ymax + 1) + 0.5)
                d = ((xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0]))
                if abs(d) < 1e-12:
                    continue
                l0, l1, l2 = _raster._bary(gx, gy, xs, ys, d)
                cov_x, cov_y = _raster.get_coverage_offset()
                cc0, cc1, cc2 = _raster._bary(gx + cov_x, gy + cov_y, xs, ys, d)
                inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
                if not inside.any():
                    continue
                u = l0 * uv0[tri[0], 0] + l1 * uv0[tri[1], 0] + l2 * uv0[tri[2], 0]
                v = l0 * uv0[tri[0], 1] + l1 * uv0[tri[1], 1] + l2 * uv0[tri[2], 1]
                mn = _sample_generic(main, u, v, clamp=True)
                cl = _sample_generic(clouds, u * g["scale_xy"][0] + du,
                                     v * g["scale_xy"][1] + dv, clamp=False)
                c_ = cl[..., :1] * tint[None, None, :] * mn[..., 3:4] * 1.5 * g["intensity"]
                rgb = np.clip(c_ + mn[..., :3], 0.0, 1.0)
                sub = rgb_out[ymin:ymax + 1, xmin:xmax + 1]
                sub[inside] = rgb[inside]
                rgba_out[ymin:ymax + 1, xmin:xmax + 1, 3][inside] = 1.0   # 宝石=不透明贴片
    # 末级量化 round 化（quant-ab 2026-11-05）：宝石层出口 trunc→round-to-nearest。
    return Image.fromarray(np.rint(np.clip(rgba_out, 0, 1) * 255).astype(np.uint8), "RGBA")


def _sample_generic(arr, u, v, clamp: bool):
    """render_gem._sample 等价：clamp=True 边缘夹取 / False wrap（ur_core:757 逐字）。"""
    if clamp:
        return _sample_clamp_rg(arr, arr.shape[1], arr.shape[0], u, v)
    from eidolon.core.render.engine.raster import sample_wrap
    return sample_wrap(arr, u, v)


def _sample_clamp_rg(arr: np.ndarray, w: int, h: int, u, v_):
    """render_gem._sample clamp 支逐字（上界是 w-1/h-1 本身，非 -1.001——fx 边缘带
    数值敏感；ur_core:765 逐字）。"""
    x = np.clip(u * w - 0.5, 0, w - 1)
    y = np.clip((1.0 - v_) * h - 0.5, 0, h - 1)
    x1 = np.minimum(np.floor(x).astype(int) + 1, w - 1)
    y1 = np.minimum(np.floor(y).astype(int) + 1, h - 1)
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    return (arr[y0, x0] * (1 - fx) * (1 - fy) + arr[y0, x1] * fx * (1 - fy)
            + arr[y1, x0] * (1 - fx) * fy + arr[y1, x1] * fx * fy)


@parallel
def composite_rarity_gem(base, plan: dict, npz, hierarchy, get_tex, *,
                         mode: str = "canonical"):
    """稀有度宝石合成：composite_rarity_gem_canonical 对位（old_paint/ur_core.py:780
    逐字转写，批22 兑现；签名修正=walk 收内部化〔S11 walk_with_key 单源晚引〕+
    clouds_with_atlas_offset 参数化为本模块 mode 轴——lineage=云层带图集 offset 的
    sca 漂移镜像、canonical=E8 VS 字节码 o1.zw 修正〔云=裸 UV+滚动〕，批16 mode
    轴既定）。

    main=uv+offset wrap 采样+云层滚动；SPEED_XY=(5.0, 0.2)（render_gem.py:54 正典）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    from PIL import Image

    from eidolon.core.render.engine.raster import project_world, sample_wrap
    rgba_out = np.asarray(base.convert("RGBA"), dtype=np.float64) / 255.0
    rgb_out = rgba_out[..., :3]          # 三通道视图：宝石写点仍按 RGB 语义
    main = np.asarray(get_tex("GenFX_RarityGems.png"), dtype=np.float64) / 255.0
    clouds = np.asarray(get_tex("GenFX_clouds03.png"), dtype=np.float64) / 255.0
    tint = np.array(list(plan["rarity_gem"]["tint_rgb"]) + [1.0])
    off_u, off_v = plan["rarity_gem"]["atlas_offset"]
    t = plan["gem"]["t"]
    du, dv = (t * 5.0) % 1.0, (t * 0.2) % 1.0   # SPEED_XY（render_gem.py:54）

    comp = next(c for c in plan["components"] if c["node"] == "RarityGem" and c.get("visible"))
    gem_path = comp["path"]
    clouds_with_atlas_offset = mode == "lineage"
    from eidolon.core.render.game.actor.components import walk_with_key  # 环避让（S11 执行面单源）
    for n, key, path in walk_with_key(hierarchy):
        if n.get("mesh_stats") and path == gem_path:
            verts = npz[f"{key}/verts"]
            uv0 = npz[f"{key}/uv0"]
            M = np.array(n["world"])
            vw = (M[:3, :3] @ verts.T).T + M[:3, 3]
            px, py = project_world(vw)
            tris = npz[f"{key}/sub0"]
            for tri in tris:
                xs, ys = px[tri], py[tri]
                xmin = max(int(np.floor(xs.min())), 0)
                xmax = min(int(np.ceil(xs.max())), rgb_out.shape[1] - 1)
                ymin = max(int(np.floor(ys.min())), 0)
                ymax = min(int(np.ceil(ys.max())), rgb_out.shape[0] - 1)
                if xmin > xmax or ymin > ymax:
                    continue
                gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5,
                                     np.arange(ymin, ymax + 1) + 0.5)
                d = ((xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0]))
                if abs(d) < 1e-12:
                    continue
                l0, l1, l2 = _raster._bary(gx, gy, xs, ys, d)
                cov_x, cov_y = _raster.get_coverage_offset()
                cc0, cc1, cc2 = _raster._bary(gx + cov_x, gy + cov_y, xs, ys, d)
                inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
                if not inside.any():
                    continue
                u_raw = l0 * uv0[tri[0], 0] + l1 * uv0[tri[1], 0] + l2 * uv0[tri[2], 0]
                v_raw = l0 * uv0[tri[0], 1] + l1 * uv0[tri[1], 1] + l2 * uv0[tri[2], 1]
                mn = sample_wrap(main, u_raw + off_u, v_raw + off_v)   # main：ST 生效
                if clouds_with_atlas_offset:
                    cl = sample_wrap(clouds, u_raw + off_u + du, v_raw + off_v + dv)
                else:
                    cl = sample_wrap(clouds, u_raw + du, v_raw + dv)   # clouds：裸 UV+滚动（E8 修正点）
                c_ = cl[..., :1] * tint[None, None, :3] * mn[..., 3:4] * 1.5 * 1.0
                rgb = np.clip(c_ + mn[..., :3], 0.0, 1.0)
                sub = rgb_out[ymin:ymax + 1, xmin:xmax + 1]
                sub[inside] = rgb[inside]
                rgba_out[ymin:ymax + 1, xmin:xmax + 1, 3][inside] = 1.0   # 宝石=不透明贴片
    # 末级量化 round 化（quant-ab 2026-11-05）：宝石层出口 trunc→round-to-nearest。
    return Image.fromarray(np.rint(np.clip(rgba_out, 0, 1) * 255).astype(np.uint8), "RGBA")


@invented(reason="宝石族 depth-only 预光栅（gem-zbuf 路线 A 深度影子）：stat 宝石 RGB "
                 "走 PIL 覆盖不写 zbuf，desc 直接合成的深度门控结构性看不见宝石（G 探针 "
                 "W′∖W=45,707 px 唯一缺口）；引擎侧宝石是不透明几何、遮挡序内建",
          counterpart="Unity 不透明几何 ZWrite/ZTest（遮挡序内建）")
def gem_depth_shadow(zbuf, plan: dict, hierarchy, npz, walk) -> int:
    """stat 宝石深度影子：把 render_stat_gems 的同一三角集（同门控同迭代序）
    以 depth-only 写进 zbuf（gem-zbuf 2026-11-02，路线 A；判据=RGB 逐位不变 +
    重开 vpass-elimination-probe 后 W′∖W gem 类→0）。

    **路线 A 契约=镜像 RGB 覆盖，非建模引擎**：门控与三角面集逐点镜像
    render_stat_gems（plan["gem"]["enabled"]+plan["stat_gems"]×walk×sub0×
    同投影×全体三角不剔除），保证深度面与 PIL 覆盖像素共延——直合深度门控
    恰在「RGB 输出有宝石」处看见遮挡。两轮实测负结果各留账：①cull=Back 变体
    W′∖W 残 289 px（RGB 画家序写背面 sliver、引擎深度无）；②纯 z-test 变体
    残 25 px（40407：宝石几何在 desc 平面之后，PIL 覆盖仍无条件画上去——
    画家空间 vs 深度空间的分歧，差分法天然免疫、深度门结构性盲）。故本件
    **声明式语义**：宝石深度先accum进 scratch 缓冲（自身 frontmost=max，无
    z-test），再整体覆写 zbuf 的宝石覆盖域——覆盖域内 RGB 恒示宝石（覆盖
    即画家序终像），desc 门控在域内必须读不到「desc 可见」；引擎遮挡序的
    真值深度归路线 B（宝石真网格化，RGB 面重锚时再议）。宝石深度先在 scratch
    缓冲 accum（自身 frontmost=max，无 z-test），再整体覆写 zbuf 覆盖域。
    调用时点=透明延期队补画之后（zbuf 此后无色彩消费者——RGB 逐位不变的
    结构性保证）。返回写入像素的三角数（记账）。

    族账锚=Actor.cs（模块头注族账；本件离线机制，网格/材质/深度语义 dump 账=
    gem-zbuf 实验档 evidence，slug 可 git 检索）。
    """
    from eidolon.core.render.engine.raster import project_world, raster_depth_only
    if not plan["gem"]["enabled"] or not plan.get("stat_gems"):
        return 0
    gem_z = np.full(np.shape(zbuf), -np.inf)
    n_tris = 0
    for g in plan["stat_gems"]:
        for n, key, path in walk(hierarchy):
            if not n.get("mesh_stats") or path != g["path"]:
                continue
            verts = npz[f"{key}/verts"]
            M = np.array(n["world"])
            vw = (M[:3, :3] @ verts.T).T + M[:3, 3]
            px, py = project_world(vw)
            depth = vw[:, 1]
            for tri in npz[f"{key}/sub0"]:
                if raster_depth_only(gem_z, np.stack([px[tri], py[tri]], axis=1),
                                     depth[tri]):
                    n_tris += 1
    mask = gem_z > -np.inf
    zbuf[mask] = gem_z[mask]
    return n_tris
