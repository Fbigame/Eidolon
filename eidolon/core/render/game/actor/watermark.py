"""watermark — Actor.UpdateWatermark 族（段 S8 desc 垫图与卡集水印）。

游戏锚：Actor.UpdateDescriptionMesh→UpdateWatermark（Actor.cs:Actor.UpdateDescriptionMesh→:5108-5169）
——水印恒挂 desc 面两写点：desc 材质 _SecondTex+_SecondTint.a（:5143-5155）+
m_watermarkMesh（:5156-5168，mercenary/BG 专用——Hearthstone.UI/Card.cs:Card.ShowMouseOverSpell
UpdateMercenaryWatermarkVisibility×HideMercenaryWatermark :73；手牌 ability prefab
序列化 null PathID 0 实测）。纹理四级优先（:5112-5138）：actor 级
m_watermarkCardSetOverride（:510/:1216 手牌默认 INVALID）→ CARD
m_watermarkTextureOverride（EntityDef.cs:EntityDef.GetWatermarkTextureOverride→CardDbfRecord.cs:CardDbfRecord.WatermarkTextureOverride，CARD DBF 列，
1016 卡迷你集族，与 set 活跃性无关）→ CardSetDbfRecord.CardWatermarkTexture（按
GetCardSet）→ IsCoreCard（EntityBase.cs:EntityBase.IsCoreCard）无条件覆盖年标
CoreIcon_Even/Odd（SetRotationIcon.cs:SetRotationIcon/:17；GetYearIconWatermark :33——奇偶=
GetActiveSetRotationYear()%2，冻结参照裁决=偶数轮 Even，78325 desc 圣甲虫目检）。
GetCardSet（EntityBase.cs:EntityBase.GetCardSet）：tag 183 恒缺省（CARD_TAG 表 0 行）→
CARD_SET_TIMING 按序首条活跃 timing（活跃性=EventTimingManager.IsEventActive_Impl，
203=ALWAYS 恒真/164=NEVER 恒假/其余服务器窗口离线判假——v3 冻结口径）。
alpha 规则三支（:5139/:5151-5153/:183）：HIDE_WATERMARK(1107)→0；纹理空串→0；
否则 WATERMARK_ALPHA_VALUE=99f/128f（:183）。
OffsetDescriptionTexture（Actor.cs:Actor.OffsetDescriptionTexture，UpdateRace :6255-6256 调）=
(保留序列化 x, withRace ? :601 常量 0 : :599 常量 0.07)；withRace=GetRaceText 非空
（EntityBase.cs:EntityBase.GetRaceText）||IsWeapon||IsLocation（:6254）；IsHero 早退（:6217）。

V-pass=离线发明无游戏对应物（apply_desc_watermark，old_frames/render_card.py:487-522
——V=|full−desc_hidden| 三渲差分；引擎写在 desc 材质上，我方 V-pass 像素等价
结构不同构，属走查档 §0.4 允许的离线等价）。

我方对位：compile_desc_watermark/desc_pass_arrays/apply_watermark_pass
（old_frames/ta_watermark.py:110/:177/:266——PS 公式逐指令；mip 采样版=
old_paint/ms_layers_mip.py:108 make_desc_pass_arrays_mip 同签名勾替位）+
with_race_for/array_prefix/main_tex_for（old_render/registry.py:95/:374/:383——
ta_render_all 同式）。

配方面：水印纹理字节经 recipes.watermarks（texture/named_texture）；desc UV1
补经 recipes.frames.supplements.ta_supplement；四级裁决数据腿=infra.card.
watermark_ref（数据真值恒在 infra——dbf 直读四级，本段消费）。

批17 实现账（2026-10-14，S8 生长；统筹职责切分=Actor 水印判定/装配参数平行——
四级纹理裁决消费/alpha 规则/withRace 推导/desc_pass 键构与 V-pass 编排参数；
PS 公式逐指令执行（desc_pass_arrays/apply_watermark_pass）与 V-pass 三渲差分执行
（apply_desc_watermark）属 engine 侧 S9/S11 段本期不实现，三件立户）：

纪律面前置——本模块 update_watermark 经 recipes.watermarks 域项触供给配方
（@item），**消费须在 supply session 内**（入口层独占纪律，批12-16 同款；未来
门驱动循环开 session 调本段，段内不开）。

职责面六件——
  * desc 面路由（desc_frame_for/_DESC_FRAME）：帧键→desc 帧键（FRAME_DESC
    "desc_frame" 行平行表，本模块自带——FRAME_SPECS 无 desc 列，批15 选型账
    同形）；None=无 desc 面（旧 apply 链 skip 支）。
  * 水印判定/键构（update_watermark）：compile_desc_watermark 对位——wm dict
    十四键逐字（ref/alpha 规则账/offset/tint/st/color/公式参数面），纹理字节经
    recipes.watermarks.texture；数据腿=card.watermark_ref（infra 在役直接用）。
  * withRace 推导（with_race_for）：registry:95 逐字——plan 文本内容推导
    （text 非空判据；notext 口径安全——render 标志在 notext 下恒 False，那是
    前任 12 卡 WITH_RACE 硬编码表的根因，2026-10-04 watermark-chain 通用化）。
  * V-pass 编排参数（array_prefix/main_tex_for）：registry:374/:383 逐字——
    desc 数组前缀（ability 学派网格分叉）+desc 材质 _MainTex 运行时真身。
  * 第二写点绑定（watermark_mesh_binding）：kit report object_refs 直读
    （gem_binding 批16 同式）——m_watermarkMesh 手牌链序列化 null（PathID 0）
    →None=引擎 (bool) 门关离线象（:5156 门；mercenary/BG 专用写点不涉九开放链）。
  * 常量/序列化参数面：WATERMARK_ALPHA/OFF_*/BLEND_INTENSITY/LIGHTING_BLEND
    （decomp :183/:601/:599+desc 材质序列化五帧一致）+DESC_MATERIALS/DESC_PATHS
    （ta_watermark:58/:101 verbatim 沿袭）。

签名修正清单（批11b 立壳→实现，批12/13/15/16 先例同权）——
  * desc_pass_arrays (wm, frame_recon, desc_path)→(wm, frame_recon, desc_path,
    array_prefix, size, project_world, sample_bilinear, main_tex) 返回
    (rgb_out, a_out, cov)：stub 缺五参+「返回 dict」系误推——旧签名继承形
    （ur_core DESC_PASS_ARRAYS_FN 勾替位同签名，mip 变体 ms_layers_mip.py:108
    逐行同构）；返回三元数组面（替换语义像素输出）非报告 dict。
  * apply_watermark_pass (full_img, magenta_img, nodesc_img, wm)→(full_img,
    magenta_img, nodesc_img, rgb_out, a_out, cov, out_png)：stub 第四参 wm 系
    误推（执行面吃 desc_pass_arrays 三数组产物+落盘位，不吃 wm dict）。
  * update_watermark/apply_desc_watermark 签名不动（前者 card-first 即新包
    约定形；后者与旧 render_card:487 逐参吻合）。

decomp 分支的离线边界（记录的缺口，非静默丢弃）——
  * actor 级 m_watermarkCardSetOverride（:510/:1216-1220 SetWatermarkCardSetOverride）：
    对局态 actor 实例字段，手牌默认 INVALID 不涉（infra watermark_ref 同账）——
    离线恒 INVALID=四级裁决自 per-card override 起（:5118 分支不触发）。
  * IsCoreCard 年标奇偶轮（SetRotationIcon GetActiveSetRotationYear()%2）：运行时
    轮换态，冻结参照裁决=偶数轮 CoreIcon_Even（78325 圣甲虫目检；infra
    dll_reflect.tables.year_icon_even 反射直取同值，ODD 变体无消费方不开面）。
  * GetCardSet timing 活跃性（EventTimingManager 服务器窗口）：离线判假口径=
    infra card_set_offline 单实现（v3 冻结；203=ALWAYS 恒真）。
  * m_watermarkMesh 写点（:5156-5168）：mercenary/BG 专用，九开放帧链 prefab
    序列化 null（PathID 0）→ 门关（watermark_mesh_binding 账面）；引擎 SetActive
    链（:4286/:4324）与 HideMercenaryWatermark（Hearthstone.UI/Card.cs:Card.ShowMouseOverSpell）
    对局态不接线。
"""

from __future__ import annotations

from eidolon.core.infra.card import Card
from eidolon.core.recipes.watermarks import texture as _wm_texture
from eidolon.core.supply import overrides as _ovr   # contract E：watermark 覆盖装载域项
from eidolon.core.render.scenes import scenes as _frames
from eidolon.core.render._provenance import fitted, invented  # noqa: F401 （按需）
from eidolon.core.render._provenance import parallel  # noqa: F401 （族默认）

# ============================================================================
# 常量面（decomp 直读 + desc 材质序列化，ta_watermark.py:50-55 沿袭）
# ============================================================================

WATERMARK_ALPHA = 99.0 / 128.0
"""WATERMARK_ALPHA_VALUE=99f/128f（Actor.cs:Actor decomp 直读；对拍转正=duipai 正则
核同——非 HIDE_WATERMARK 且纹理非空的 desc _SecondTint.a/:5151-5153 与 _Color.a
写值）。"""

OFF_WITH_RACE = 0.0
"""descriptionMesh_WithRace_TextureOffset（Actor.cs:Actor；OffsetDescriptionTexture
y 分支 :6186 withRace 真）。"""

OFF_WITHOUT_RACE = 0.07
"""descriptionMesh_WithoutRace_TextureOffset（Actor.cs:Actor；:6186 withRace 假）。"""

BLEND_INTENSITY = 2.0
LIGHTING_BLEND = 0.0
"""desc 材质序列化（desc_mats.json+desc_mats_floats.json，五帧一致——PS 公式参数：
second_t = _SecondTex@UV1 × _SecondTint × _BlendIntensity；VS o2 lighting blend=0
→ out 色=_Color。ta_watermark:54-55 沿袭）。"""

# desc 材质序列化（ta_watermark.py:58-74 verbatim 沿袭；per frame——
# tint=_SecondTint/color=_Color/st=_SecondTex_ST，运行时 _SecondTint.a=UpdateWatermark
# 写点 alpha 覆写）
DESC_MATERIALS = {
    "ability": {"tint": [0.5686274766921997, 0.5616085529327393, 0.5463283658027649, 0.7764706015586853],
                "color": [1.0, 1.0, 1.0, 1.0],
                "st": [1.0, 1.0, -0.03999999910593033, 0.0]},
    "ally": {"tint": [0.5686274766921997, 0.5616085529327393, 0.5463283658027649, 0.7764706015586853],
             "color": [1.0, 1.0, 1.0, 1.0],
             "st": [1.0, 1.0, -0.03999999910593033, 0.0]},
    # 金卡档（mechorse-golden 2026-10-21）：premium desc 材质
    # Card_InHand_BannerAtlasMod2x_Premium 序列化实测（kit prefab dump）——
    # _SecondTint/_Color/_SecondTex_ST 与 ally 逐值相等（金版 BannerAtlas 主图不同，
    # 序列化参数同形）
    "ally_premium": {"tint": [0.5686274766921997, 0.5616085529327393, 0.5463283658027649, 0.7764706015586853],
                     "color": [1.0, 1.0, 1.0, 1.0],
                     "st": [1.0, 1.0, -0.03999999910593033, 0.0]},
    "weapon": {"tint": [0.6705882549285889, 0.6623107194900513, 0.6442906856536865, 0.7764706015586853],
               "color": [1.0, 1.0, 1.0, 1.0],
               "st": [1.0, 1.0, -0.03999999910593033, 0.0]},
    "location": {"tint": [0.5568627715110779, 0.5568627715110779, 0.5568627715110779, 1.0],
                 "color": [0.9063317179679871, 0.9063317179679871, 0.9063317179679871, 1.0],
                 "st": [1.0, 1.0, -0.03999999910593033, 0.0]},
    "hero_hand": {"tint": [0.5686274766921997, 0.5616085529327393, 0.5463283658027649, 0.7764706015586853],
                  "color": [1.0, 1.0, 1.0, 1.0],
                  "st": [5.0, 5.0, -2.009999990463257, -0.5400000214576721]},
}
"""desc 材质序列化参数面（帧键→tint/color/st；ta_watermark DESC_MATERIALS 逐行
沿袭——对拍转正=duipai 逐帧全等；st=desc_mats_floats.json 序列化真值）。"""

DESC_PATHS = {
    "ability": "Card_Hand_Ability/RootObject/NonQuestObjects/Mesh/Description_mesh",
    "ally": "Card_Hand_Ally/RootObject/Mesh/Description_mesh",
    "ally_premium": "Card_Hand_Ally_Premium/RootObject/Mesh/Description_mesh",
    "weapon": "Card_Hand_Weapon/RootObject/Mesh/Description_mesh",
    "location": "Card_Hand_Location/RootObject/Mesh/Description_mesh",
    "hero_hand": "Card_Hand_Hero/RootObject/Mesh/Description_mesh",
}
"""desc 网格节点路径（ta_watermark DESC_PATHS verbatim 沿袭——hierarchy 寻址键，
_find_node 消费）。"""

_DESC_FRAME: dict[str, str | None] = {
    "Card_Hand_Ability": "ability",                  # ability 帧 desc 网格共享（consumer-v2 改键）
    "Card_Hand_Ally": "ally",
    "Card_Hand_Ally_Premium": "ally_premium",        # 金卡档（mechorse-golden）自有 desc 面
    "Card_Hand_Weapon": "weapon",
    "Card_Hand_Hero": "hero_hand",
    "Card_Hand_Location": "location",
    "Card_Play_Hero": None,                          # 打出帧无 desc 面
    "Card_Play_Bacon_Hero": None,
    "History_HeroPower": None,                       # DESC_MATERIALS 无 heropower
    # ct44 饰品（bg-ct40-43-44-routing 2026-10-24）：desc 盘在帧图集
    # Trinket_Hand_BigCard_Player 内（FrameMesh 单材质），无独立 desc 材质
    # （DESC_MATERIALS 无行）→ 垫图 V-pass 无消费位=skip（hero_play 同款）。
    "Card_Hand_BG_Trinket": None,
    # ct43 畸变（bg-ct40-43-44-routing 2026-10-24）：desc 面=Description_mesh slot0
    # Card_InHand_Ability_BannerAtlasMod2x（带 _SecondTex 水印槽，UpdateWatermark
    # 写点在位）——但 ct43 卡集恒 BGS(1453)，watermark_ref 四级裁决恒 None（101954/
    # 132530 实测）→ wm alpha=0 → apply_desc_watermark 首行 skip。None 行=BGS 畸变
    # 语料 V-pass 无消费位的诚实记账（trinket 同款）；若未来畸变卡带卡集水印，
    # 升 own DESC_MATERIALS/DESC_PATHS 行+ta supplement 数组前缀。
    "Card_Hand_BG_Anomaly": None,
    # 金法术帧（capture-determinism 2026-10-30）：98918 首张语料卡。BGS 卡集（1453）
    # watermark_ref 四级裁决恒 None（实测）→ desc 水印 V-pass 无消费位——ct43 同款
    # None 行诚实记账；帧几何/材质走 prefab 实况（specs.py 金法术行=kit ability 不分支）。
    # 若未来金法术卡带卡集水印，升 own DESC_MATERIALS/DESC_PATHS 行。
    "Card_Hand_Ability_Premium": None,
}
"""帧键→desc 帧键（FRAME_DESC "desc_frame" 行平行表，registry.py:167/:200/:233/
:253/:271/:307/:324/:342/:360 九行——本模块自带，批15 _PORTRAIT_PARAMS 选型账
同形；开放位=frames.SCENE_KEYS 九键+trinket/anomaly（2026-10-24 扩十一键），未知键
assert 响亮）。"""


@parallel
def desc_frame_for(key: str) -> str | None:
    """帧键 → desc 帧键（FRAME_DESC[key]["desc_frame"] 对位；None=无 desc 面，
    旧 apply_desc_watermark 首行 skip 支 render_card.py:497）。未知帧键 assert
    响亮（tripwire 纪律，批14 _KIT_SOURCE 同款）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    assert key in _DESC_FRAME, (
        f"未知帧键 {key!r}——_DESC_FRAME 无此键（开放位={sorted(_DESC_FRAME)}）")
    return _DESC_FRAME[key]


# ============================================================================
# withRace 推导（registry.py:95-103 逐字；Actor.cs:Actor.UpdateRace）
# ============================================================================


@parallel
def with_race_for(plan: dict, frame: str) -> bool | None:
    """withRace = 有种族/学派文本 || IsWeapon || IsLocation（Actor.cs:Actor.UpdateRace；
    IsHero 早退 :6217——hero 帧不吃 OffsetDescriptionTexture 改写）。

    frame=desc 帧键。weapon/location 恒真、hero_hand None（早退）由帧型直接
    给出；余从 plan 文本**内容**推导（race/plate 角色 text 非空判据——引擎
    GetRaceText EntityBase.cs:EntityBase.GetRaceText；notext 口径下 text 仍在 plan，render
    标志不可用，前任 12 卡 WITH_RACE 硬编码表存在的根因；2026-10-04
    watermark-chain 通用化删除，12 卡实证与推导全等——唯一差异 dbf 8：表 True/
    推导 False，其 wm alpha=0 offset 不进像素无视觉差）。"""
    if frame in ("weapon", "location"):
        return True
    if frame == "hero_hand":
        return None
    return any(e.get("text") for e in plan["texts"] if e["role"] in ("plate", "race", "race_multi"))


# ============================================================================
# UpdateWatermark 判定/键构（Actor.cs:Actor.UpdateWatermark 离线形；ta_watermark.py:110 对位）
# ============================================================================


@parallel
def update_watermark(card: Card, frame: str,
                     with_race: bool | None = None) -> dict | None:
    """水印判定+desc_pass 参数键构：compile_desc_watermark 对位
    （old_frames/ta_watermark.py:110；引擎=UpdateWatermark :5108-5169 离线形）。

    card=infra.card.Card 语义层（watermark_ref=四级裁决数据腿：per-card override
    →活跃 set 纹理→core 年标→None，infra 在役直接用；HIDE_WATERMARK 闸在消费侧
    alpha 层 :5139 同构）；frame=desc 帧键（DESC_MATERIALS 键；无 desc 面→None
    ——hero_play/hero_play_bacon/heropower，旧同款）；with_race=with_race_for
    产物（None=hero 帧 IsHero 早退不吃改写，offset 保留序列化）。

    水印覆盖/强制轴（contract E，2026-11-06）：Card.watermark_asset 在场=纹理源换
    覆盖图（wm_ref=合成 `override:watermark:<sha16>`——四级裁决数据真值不动，本轴
    只换 _SecondTex 源；无数据水印的卡也可加覆盖水印）；Card.watermark_force=True=
    忽略 HIDE_WATERMARK(1107) 闸（:5139 hide 腿让位）。alpha 两档保真：0（hide）/
    99/128（WATERMARK_ALPHA_VALUE 引擎常量，覆盖轴不发明第三档）。

    alpha 三支（:5139/:5151-5153/:183）：wm_ref 空∨HIDE_WATERMARK>0→0，否则
    99/128。offset（OffsetDescriptionTexture :6173-6189）：with_race None→
    保留序列化 (st[2],st[3])；否则 (st[2], with_race?0:0.07)。返回 wm dict
    十四键（desc_pass_arrays/S11 写点消费面）；tex_img=纹理字节
    （recipes.watermarks.texture，session 内 memo）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    if frame not in DESC_MATERIALS:
        return None
    fov = _ovr.watermark_of(card)   # 覆盖座位（None=数据轴照旧；装载校验 fail loud 在域内）
    hide = False
    tex_img = None
    if fov is not None:
        wm_ref = fov["ref"]
        # 覆盖轴：纹理源=覆盖图；HIDE_WATERMARK 闸按 force 让位（:5139 腿）
        hide = bool(card.watermark_hidden) and not card.watermark_force
        if not hide:
            tex_img = fov["img"]
    else:
        wm_ref = card.watermark_ref
        # GetCardSet=INVALID（无活跃 timing）→ GetCardSet(INVALID)=null → text 空 → a=0（:5139-5153）
        # Actor.cs:Actor.UpdateWatermark HIDE_WATERMARK → 0（tag 1107；与语料/base21 零交集，完备性实现）
        # force（contract E）=HIDE_WATERMARK 腿让位（ref 空腿不动——无纹理无水印可画）
        hide = (not wm_ref) or (card.watermark_hidden and not card.watermark_force)
        if not hide:
            tex_img = _wm_texture(wm_ref)
    mat = DESC_MATERIALS[frame]
    # OffsetDescriptionTexture：offset=(保留序列化 x, 规则 y)；hero 不吃规则
    if with_race is None:
        off = [mat["st"][2], mat["st"][3]]
    else:
        off = [mat["st"][2], OFF_WITH_RACE if with_race else OFF_WITHOUT_RACE]
    wm = {
        "enabled": True, "frame": frame, "dbf_id": str(card.dbf_id),
        "set_id": card.set_id,
        "wm_ref": wm_ref,
        "tex_img": tex_img,
        "alpha": 0.0 if hide else WATERMARK_ALPHA,
        "st_scale": [mat["st"][0], mat["st"][1]],
        "offset_runtime": off,
        "tint_rgba": list(mat["tint"]),
        "blend_intensity": BLEND_INTENSITY,
        "lighting_blend": LIGHTING_BLEND,
        "color_rgba": list(mat["color"]),
        "provenance": {
            "texture": "UpdateWatermark (Actor.cs:Actor.UpdateWatermark) 纹理优先级 = per 卡 override "
                       "（EntityDef.cs:EntityDef.GetWatermarkTextureOverride）→ "
                       "CardSetDbfRecord.CardWatermarkTexture → "
                       "IsCoreCard 年标 CoreIcon_Even（SetRotationIcon.cs:SetRotationIcon.GetYearIconWatermark，偶数轮参照裁决 78325）；"
                       "裁决正典=Card.watermark_ref（dbf 直读；2026-10-11 A 溶解随 ③外迁收编）",
            "alpha": "WATERMARK_ALPHA_VALUE=99f/128f (Actor.cs:Actor)；HIDE_WATERMARK→0 (:5139)；"
                     "空串→0 (:5151-5153)",
            "offset": "OffsetDescriptionTexture (Actor.cs:Actor.OffsetDescriptionTexture) + 常量 :599-601；withRace :6254",
            "formula": "descshader_prog_p4_n1 DX11PixelSM40.asm（PS）+ n0（VS）；材质=desc_mats_floats.json",
            "tint_fix": "PS 不乘 _Color 进 main（min 尾对白/0.906 恒 no-op）——去现离线 _Color tint 偏差",
        },
    }
    if fov is not None:
        wm["override"] = {"ref": fov["ref"], "sha256": fov["sha256"],
                          "path": fov["path"], "force": bool(card.watermark_force)}
    return wm


# ============================================================================
# 第二写点绑定（kit report 直读；gem_binding 批16 同式）
# ============================================================================


@parallel
def watermark_mesh_binding(frame_key: str) -> dict | None:
    """m_watermarkMesh 第二写点绑定：kit report actor_components[0].object_refs
    直读（gem_binding 批16 同式）。

    引擎写点=UpdateWatermark 后半（Actor.cs:Actor.UpdateWatermark——_MainTex+_Color.a，
    mercenary/BG 专用；Hearthstone.UI/Card.cs:Card.ShowMouseOverSpell UpdateMercenaryWatermark
    Visibility×HideMercenaryWatermark）。手牌链 prefab 序列化 null（PathID 0
    实测）→finalize_actor PathID 0 跳过→ref 缺席→None=引擎
    ``if (m_watermarkMesh != null ...)``（:5156）门关离线象（帧相关不可硬编码）。
    非 None 时返回 {"node", "path_id"}（S11 写点消费位）。"""
    refs = (_frames.scene_for(frame_key)["report"]["actor_components"][0]
            .get("object_refs") or {})
    e = refs.get("m_watermarkMesh")
    if not e:
        return None
    return {"node": e.get("node"), "path_id": e.get("path_id")}


# ============================================================================
# V-pass 编排参数（registry.py:374/:383 逐字；ta_render_all 同式）
# ============================================================================

_DESC_ARRAY_PREFIX: dict[str, str] = {
    "ally": "ally_desc", "ally_premium": "ally_premium_desc",
    "weapon": "weapon_desc", "location": "location_desc",
    "hero_hand": "hero_hand",
}
"""desc 帧键→补充提取数组前缀（ability 特源分叉见 array_prefix——学派网格
ability_school/中立 ability_neutral；registry.py:378-380 字面沿袭）。"""


@parallel
def array_prefix(plan: dict, frame: str) -> str:
    """desc 数组前缀：array_prefix 对位（old_render/registry.py:374——
    ta_render_all._array_prefix :265-270 同式）。

    ability 帧按 plan desc 组件网格 runtime 分叉（school_mesh_swap 学派替换
    后真身=ability_school，否则 ability_neutral）；余帧查表
    （_DESC_ARRAY_PREFIX，未知 desc 帧键 KeyError=开放位闭合）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    if frame == "ability":
        comp = next(c for c in plan["components"] if c["path"] == DESC_PATHS["ability"])
        return "ability_school" if (comp.get("mesh") or {}).get("runtime") == "school" else "ability_neutral"
    return _DESC_ARRAY_PREFIX[frame]


@parallel
def main_tex_for(plan: dict, frame: str, recon: dict, kit_textures: dict):
    """desc 材质 _MainTex 运行时真身：main_tex_for 对位（old_render/registry.py:
    383——ta_render_all.main_tex_for :203-224 同式）。

    plan 槽位 BannerAtlas runtime 优先→首槽 runtime→层级序列化 _MainTex
    （kit 名字索引解析：入参 kit_textures 优先，ability kit 兜底——spell 族
    图集落供给镜像的批9b 内存名索引语义）。返回 PIL Image（RGBA）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    from PIL import Image

    comp = next((c for c in plan["components"] if c["path"] == DESC_PATHS.get(frame)), None)
    assert comp is not None, f"{frame}: plan 无 desc 组件"
    rt = None
    for s in comp.get("material_slots", []):
        if "BannerAtlas" in (s.get("material") or ""):
            rt = (s.get("_MainTex_runtime") or {}).get("file")
            break
    if rt is None:
        rt = (comp["material_slots"][0].get("_MainTex_runtime") or {}).get("file")
    if rt:
        # 2026-10-21 render-data-decouple：`_MainTex_runtime.file` → `Image.open(rt)`
        # 直读盘分支**删除**（已退役的 assets_dir 语义）。运行时 desc 主纹理必须走
        # plan 内存面 `image`；**不得**静默落到 node 序列化纹理（那会把路径语义偷换
        # 成「同节点另一槽」的错误资源）。
        raise ValueError(
            f"{frame}: desc 材质 _MainTex_runtime.file={rt!r}——路径直读盘=已退役的"
            " assets_dir 语义（渲染只接受 plan 内存面 image，路径不得直读盘）")
    node = _find_node(recon, DESC_PATHS[frame])
    tex_name = node["renderers"][0]["materials"][0]["tex"]["_MainTex"]["texture"]["file"]
    # 批9b：kit 内存名字索引（目录扫描退役）
    for src in (kit_textures, _frames.kit_for("Card_Hand_Ability").textures):  # consumer-v2 改键
        if tex_name in src:
            return src[tex_name]
    raise KeyError(f"{tex_name} 不在 kit 内存面")


def _find_node(frame_recon: dict, desc_path: str) -> dict:
    """层级走查（ta_watermark._find_node :162-174 逐字——全路径=根名起斜杠链）。"""
    def walk(n, path=""):
        p = f"{path}/{n['name']}" if path else n["name"]
        if p == desc_path:
            return n
        for c in n["children"]:
            r = walk(c, p)
            if r is not None:
                return r
        return None
    n = walk(frame_recon["hierarchy"])
    assert n is not None, f"frame_recon 无 {desc_path}"
    return n


# ============================================================================
# 公式层（PS 逐指令执行与 V-pass 三渲差分执行；批22 兑现——engine/raster 消费面）
# ============================================================================

@parallel
def watermark_submesh_indices(frame_recon: dict, desc_path: str) -> tuple[int, ...]:
    """运行时水印写点覆盖的 submesh 集（=materials[0] 那一个；desc 网格多材质分叉的唯一载体）。

    引擎锚：`Actor.cs:Actor.UpdateWatermark` 的写点取 `Renderer.GetSharedMaterial()`
    （= `Actor.cs:Actor.GetMaterialInstance` → `Renderer.GetMaterial()` → **materials[0]**）
    的 `_SecondTex`/`_SecondTint.a`；`Actor.cs:Actor.OffsetDescriptionTexture` 同取
    该材质实例的 `_SecondTex` offset。**同一 desc 网格的其余 submesh 材质保持序列化态**
    ——运行时水印纹理/alpha 永不写进它们。

    返回下标元组；materials[0] 缺 `_SecondTint`/`_SecondTex` 属性时 assert 响亮
    （=引擎 `HasProperty` 门不成立，V-pass 编排前提被破坏）。"""
    node = _find_node(frame_recon, desc_path)
    mats = node["renderers"][0].get("materials") or []
    assert mats, f"{desc_path}: desc 网格无材质（frame recon renderer.materials 空）"
    m0 = mats[0]
    assert ("_SecondTint" in (m0.get("colors") or {})
            and "_SecondTex" in (m0.get("tex") or {})), (
        f"{desc_path}: materials[0] 缺 _SecondTint/_SecondTex 属性——引擎 "
        f"HasProperty 门不成立（Actor.cs:Actor.UpdateWatermark），V-pass 前提失效")
    return (0,)


@parallel
def desc_submesh_mode(frame_recon: dict, desc_path: str, n_sub: int) -> tuple[str, ...]:
    """desc 网格逐 submesh 的 PS 语义分派：`watermark`（运行时水印载体=materials[0]）
    或 `main_only`（该 submesh 的序列化材质自己的 shader 输出=主纹理）。

    引擎取证（材质级 shader 属性面，`essential_base_global-shader-0.unity3d` 直读）：
      * materials[0]（`*_BannerAtlasMod2x`）shader 属性 =
        `_Color/_MainTex/_SecondTex/_SecondTint/_BlendIntensity/_LightingBlend`
        ⇒ 即 desc PS 公式（本模块 desc_pass_arrays 实现），运行时 `_SecondTex`/
        `_SecondTint.a` 被 Actor.UpdateWatermark 覆写（99/128）。
      * ability 学派/中立网格 materials[1]（`Card_Inhand_Ability_<Class>`）shader 属性 =
        `_MainTex/_EnableDualClass/_SecondTex/_MiddleValue/_LightingBlend`
        ——**没有 `_SecondTint`/`_BlendIntensity`/`_Color`**：双职业拼贴 shader
        （`_EnableDualClass`=0 时输出=_MainTex；=1 时按 UV.x<_MiddleValue 拼两半）。
        该材质不在 UpdateWatermark 写点内 ⇒ 运行时水印与它无关，输出=主纹理。

    纪律：非载体 submesh 若出现「活的」第二纹理（`_SecondTint.a>0` 且有纹理）或
    `_EnableDualClass≠0`（拼贴路径启用）、或其 `_MainTex` 与载体不一致（main_tex 不能
    共用），一律 assert 响亮——本函数只覆盖已取证的冻结资产形态，新形态须另立机制。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    node = _find_node(frame_recon, desc_path)
    mats = node["renderers"][0].get("materials") or []
    assert mats, f"{desc_path}: desc 网格无材质"
    # submesh ↔ material 一一对应（Unity 按 submesh 发 draw、材质槽按序）。不齐=映射假设
    # 失效（可能静默把水印/主纹理路由到错的 submesh），响亮失败而非 min(si, len-1) 兜底。
    assert len(mats) == n_sub, (
        f"{desc_path}: renderer 材质槽 {len(mats)} ≠ submesh 数 {n_sub}"
        f"（材质={[m.get('name') for m in mats]}）——submesh↔material 映射不明确")
    carrier = set(watermark_submesh_indices(frame_recon, desc_path))
    m0_tex = ((mats[0].get("tex") or {}).get("_MainTex") or {}).get("texture") or {}
    modes = []
    for si in range(n_sub):
        m = mats[min(si, len(mats) - 1)]
        if si in carrier:
            modes.append("watermark")
            continue
        colors = m.get("colors") or {}
        tex = (m.get("tex") or {}).get("_SecondTex") or {}
        live_second = (colors.get("_SecondTint") is not None
                       and colors["_SecondTint"][3] > 0
                       and bool((tex.get("texture") or {}).get("file")))
        dual = float((m.get("floats") or {}).get("_EnableDualClass") or 0.0) != 0.0
        assert not live_second and not dual, (
            f"{desc_path}/sub{si} 材质 {m.get('name')!r}: 第二纹理/双职业拼贴态非退化"
            f"（_SecondTint.a>0 或 _EnableDualClass≠0）——main_only 假设失效，须实现该"
            f"材质 PS（desc_submesh_mode 的取证只覆盖冻结资产的退化态）")
        mt = ((m.get("tex") or {}).get("_MainTex") or {}).get("texture") or {}
        assert (mt.get("file") == m0_tex.get("file")
                and mt.get("path_id") == m0_tex.get("path_id")), (
            f"{desc_path}/sub{si} 材质 {m.get('name')!r} _MainTex 与载体不同"
            f"（{mt.get('file')} vs {m0_tex.get('file')}）——main_tex 不能共用")
        modes.append("main_only")
    return tuple(modes)


def _cov_offset() -> tuple[float, float]:
    """当前覆盖样本偏移（单一事实源=raster；0,0=像素中心旧行为）。"""
    from eidolon.core.render.engine import raster as _raster
    return _raster.get_coverage_offset()


def _bary_offsets(gx, gy, xs, ys, d, dx, dy):
    """覆盖样本位置的重心坐标（与 raster._bary 逐字同式；dx=dy=0 退化为中心样本）。"""
    l1 = ((gx + dx - xs[0]) * (ys[2] - ys[0]) - (gy + dy - ys[0]) * (xs[2] - xs[0])) / d
    l2 = ((xs[1] - xs[0]) * (gy + dy - ys[0]) - (ys[1] - ys[0]) * (gx + dx - xs[0])) / d
    return 1.0 - l1 - l2, l1, l2


_MAGENTA = None   # 洋红探针（批4 内存面；懒构——模块导入期不触 PIL 大对象）


def _magenta():
    global _MAGENTA
    if _MAGENTA is None:
        from PIL import Image
        _MAGENTA = Image.new("RGBA", (4, 4), (255, 0, 255, 255))
    return _MAGENTA


@parallel
def desc_pass_arrays(wm: dict, frame_recon: dict, desc_path: str,
                     array_prefix: str, size: tuple[int, int], project_world,
                     sample_bilinear, main_tex, return_z: bool = False):
    """desc 垫图光栅：desc_pass_arrays 对位（old_frames/ta_watermark.py:177 逐字
    转写，批22 兑现；mip 采样变体=engine/raster.set_mip_hooks 勾替位——DESC_PASS_
    ARRAYS_FN 工厂同签名）。

    PS 公式逐指令：VS o1.xy=UV0×_MainTex_ST / o1.zw=UV1×_SecondTex_ST；
    PS second_t=_SecondTex@UV1×_SecondTint×_BlendIntensity、out=st.a×(main×st−main)
    +main、尾 min 恒 no-op 仍逐指令；Clamp+Bilinear 采样、重心光栅与引擎光栅同式。
    main_tex=desc 材质 _MainTex 运行时真身（main_tex_for）。返回 (rgb_out, a_out,
    cov)（替换语义像素输出，apply_watermark_pass 消费）。

    **return_z（vpass-direct 2026-11-03）**：True 时追加返回逐像素 desc 几何 z
    （第 4 元 `z_desc`，H×W float64、覆盖域外 NaN）。z 定义与主光栅 depth 同源：
    世界 Y 重心插值（`z = l0·vw[t_i].y + …`，engine/raster raster_bucket_zbuf_unified
    的 `depth = vw[:, 1]` 同式同顶点源）——gem-zbuf 探针 `_desc_geo` 逐行上正典
    （gem-zbuf 2026-11-02 闭合账：35/35 applied 卡 z_desc==zbuf_final 写域与
    三渲差分写域 W 双向 0）。return_z=False 缺省路径零额外开销（z 分支逐三角跳过）。

    **逐 submesh PS 语义分派（2026-10-20 desc 底缘修）**：`desc_submesh_mode` 取证=引擎
    UpdateWatermark 只写 `Renderer.GetSharedMaterial()`=materials[0]；desc 网格其余
    submesh（ability 网格 sub1=材质 `Card_Inhand_Ability_<Class>`，属性面
    `_MainTex/_EnableDualClass/_SecondTex/_MiddleValue/_LightingBlend`，无
    `_SecondTint/_BlendIntensity/_Color`）输出=主纹理。旧式把运行时水印 PS 套到全部
    submesh，sub1 按 `_SecondTint.a`=99/128 压暗（5 张学派法术 desc 底缘带 y≈553–585
    max 57 级的病灶）。写域仍=整个 desc 面（cov 全 submesh，sub1 写主纹理值）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    import numpy as np

    W, H = size
    node = _find_node(frame_recon, desc_path)
    M = np.array(node["world"], dtype=np.float64)

    from eidolon.core.recipes.frames import supplements as _supp
    sup = _supp.ta_supplement()
    verts = sup[f"{array_prefix}/verts"]
    uv0 = sup[f"{array_prefix}/uv0"]
    uv1 = sup[f"{array_prefix}/uv1"]
    color0 = sup[f"{array_prefix}/color0"]
    n_sub = len([k for k in sup if k.startswith(f"{array_prefix}/sub")])

    vw = (M[:3, :3] @ verts.T).T + M[:3, 3]
    px, py = project_world(vw)

    tex_main = np.asarray(main_tex.convert("RGBA"), dtype=np.float64) / 255.0
    tex_wm = np.asarray(wm["tex_img"].convert("RGBA"), dtype=np.float64) / 255.0
    sx, sy = wm["st_scale"]
    ox, oy = wm["offset_runtime"]
    tint = np.array(wm["tint_rgba"], dtype=np.float64)
    tint = tint.copy()
    tint[3] = wm["alpha"]   # 运行时 _SecondTint.a = UpdateWatermark 写点（99/128 或 0）
    blend = wm["blend_intensity"]
    color = np.array(wm["color_rgba"], dtype=np.float64)
    lb = wm["lighting_blend"]

    rgb_out = np.zeros((H, W, 3), dtype=np.float64)
    a_out = np.zeros((H, W), dtype=np.float64)
    cov = np.zeros((H, W), dtype=bool)
    z_desc = np.full((H, W), np.nan) if return_z else None
    zv = vw[:, 1] if return_z else None

    # 逐 submesh PS 语义分派（desc_submesh_mode）：materials[0]=运行时水印载体走 PS 全式；
    # 其余 submesh（ability 网格 sub1）材质是另一支序列化 shader（双职业拼贴族，无
    # _SecondTint/_Color）⇒ 输出=主纹理，不得套运行时水印（否则按 tint.a=99/128 压暗：
    # 5 张学派法术 desc 底缘带 y≈553–585 max 57 级）。写域仍=整个 desc 面（cov 全 submesh）。
    modes = desc_submesh_mode(frame_recon, desc_path, n_sub)
    for si in range(n_sub):
        wm_like = modes[si] == "watermark"
        tris = sup[f"{array_prefix}/sub{si}"]
        if not wm_like:
            # 非载体 submesh 顶点色契约：PS 里 out=main×v2（v2=顶点色插值）；冻结资产全 1.0。
            # 非 1.0 形态未经引擎取证（拼贴/顶点色调制未验），拒绝而非静默带入。
            _csub = color0[np.unique(tris.reshape(-1))]
            assert np.all(_csub == 1.0), (
                f"{desc_path}/sub{si} 顶点色非常数 1.0（min={_csub.min(axis=0)} "
                f"max={_csub.max(axis=0)}）——main_only 的 out=main×v2 需引擎侧取证后再放开")
        for t in tris:
            xs, ys = px[t], py[t]
            xmin = max(int(np.floor(xs.min())), 0)
            xmax = min(int(np.ceil(xs.max())), W - 1)
            ymin = max(int(np.floor(ys.min())), 0)
            ymax = min(int(np.ceil(ys.max())), H - 1)
            if xmin > xmax or ymin > ymax:
                continue
            gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5,
                                 np.arange(ymin, ymax + 1) + 0.5)
            d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
            if abs(d) < 1e-12:
                continue
            l1 = ((gx - xs[0]) * (ys[2] - ys[0]) - (gy - ys[0]) * (xs[2] - xs[0])) / d
            l2 = ((xs[1] - xs[0]) * (gy - ys[0]) - (ys[1] - ys[0]) * (gx - xs[0])) / d
            l0 = 1.0 - l1 - l2
            # 覆盖超采样（geometry-aa-4x 2026-11-04）：inside/z 用覆盖样本位置，UV/
            # 颜色仍用像素中心（l0/l1/l2）——与 raster 的 desc pass 同式。变量名避开
            # 既有 ox/oy（watermark UV offset；首版同名踩坑账见实验档）。
            cov_x, cov_y = _cov_offset()
            cc0, cc1, cc2 = _bary_offsets(gx, gy, xs, ys, d, cov_x, cov_y)
            inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
            if not inside.any():
                continue
            if return_z:
                # desc 几何 z（世界 Y 重心插值，主光栅 depth 同源定义 vw[:,1]）；
                # gem-zbuf 探针 _desc_geo 逐行同式（后写覆盖=画家序，与 cov 同域）。
                z = cc0 * zv[t[0]] + cc1 * zv[t[1]] + cc2 * zv[t[2]]
            # VS：o1.xy = UV0×_MainTex_ST（ST=单位）；o1.zw = UV1×_SecondTex_ST
            u0 = l0 * uv0[t[0], 0] + l1 * uv0[t[1], 0] + l2 * uv0[t[2], 0]
            v0 = l0 * uv0[t[0], 1] + l1 * uv0[t[1], 1] + l2 * uv0[t[2], 1]
            col0 = u0 * tex_main.shape[1] - 0.5
            row0 = (1.0 - v0) * tex_main.shape[0] - 0.5
            main = sample_bilinear(tex_main, col0, row0)          # clamp 采样（图集 wrap 语义同前）
            if wm_like:
                u1 = (l0 * uv1[t[0], 0] + l1 * uv1[t[1], 0] + l2 * uv1[t[2], 0]) * sx + ox
                v1 = (l0 * uv1[t[0], 1] + l1 * uv1[t[1], 1] + l2 * uv1[t[2], 1]) * sy + oy
                col1 = u1 * tex_wm.shape[1] - 0.5
                row1 = (1.0 - v1) * tex_wm.shape[0] - 0.5
                second = sample_bilinear(tex_wm, col1, row1)      # Clamp+Bilinear（m_WrapU/V=1）
                # PS：second_t = second × _SecondTint × _BlendIntensity
                st = second * tint[None, :] * blend
                # r2 = main×second_t − main；out = second_t.a × r2 + main（rgb/a 同式，PS mad 逐信道）
                out = st[..., 3:4] * (main * st - main) + main
                # 尾 min：v2 = _Color × lerp(color0, γ+ambient, lb)，lb=0 → v2 = _Color×color0
                v2 = color[None, None, :] * color0[t[0]][None, None, :]
                out = np.minimum(out, (out + 0.15) * v2)
            else:
                # 非水印载体 submesh：序列化 shader=双职业拼贴族（PS 逐指令：r2=main×v2、
                # _EnableDualClass=0 ⇒ out=r2）。v2=顶点色**重心插值**（PS 逐像素插值同式）；
                # 冻结资产 desc 网格顶点色全 1.0 ⇒ 与 out=main 逐位同（上方 assert 守门）。
                v2 = (l0[..., None] * color0[t[0]][None, None, :]
                      + l1[..., None] * color0[t[1]][None, None, :]
                      + l2[..., None] * color0[t[2]][None, None, :])
                out = main * v2
            sub_r = rgb_out[ymin:ymax + 1, xmin:xmax + 1]
            sub_a = a_out[ymin:ymax + 1, xmin:xmax + 1]
            sub_c = cov[ymin:ymax + 1, xmin:xmax + 1]
            sub_r[inside] = out[inside, :3]
            sub_a[inside] = out[inside, 3]
            sub_c[inside] = True
            if return_z:
                sub_z = z_desc[ymin:ymax + 1, xmin:xmax + 1]
                sub_z[inside] = z[inside]
    if return_z:
        return rgb_out, a_out, cov, z_desc
    return rgb_out, a_out, cov


@parallel
def apply_watermark_pass(full_img, magenta_img, nodesc_img,
                         rgb_out, a_out, cov, out_png, text_cov=None,
                         w_domain=None) -> dict:
    """写域 W = |magenta − nodesc| ∩ cov：desc 洋红探针变体（desc 材质临时换洋红、
    其余渲染全同）与无 desc 变体之差 = desc 为最终可见层（引擎 One/Zero 顶层写）的
    像素集——对「下层同贴图重合（V 检不见）」「后绘网格/宝石覆盖（full==D_tint 误判）」
    两类边界都严格正确。W 上用 D_out 替换（ta_watermark.apply_watermark_pass :266
    逐字转写，批22 兑现；三图内存 PIL 进出——PNG 往返无损=逐位等价）。

    **w_domain（vpass-direct 2026-11-03）**：直合模式写域显式传入（调用方已算好
    `W′ = cov ∩ (z_desc == zbuf_final)`，深度门控——gem-zbuf 闭合账 W′=W 双向 0），
    跳过 magenta/nodesc 两变体图差分（传 None 占位）。写值式/α 面与三渲模式**同一
    代码路径**（同舍入 `(x·255+0.5).uint8`、同剪影 α 回读）——写域同+写值同+域外
    同保 full ⟹ 与三渲 final 逐位等价。此模式 `v_pixels` 无差分面可算=返回 None。

    **输出保留剪影 α（2026-10-20 α 面修正）**：`out_png` = render_with 在 V-pass 前
    写下的 RGBA 无字底图（与 apply_desc_watermark 的 `full_png` 同一路径）；写回时取其
    α 通道（0/255 剪影）与替换后的 RGB 一起存 RGBA。此前只存 RGB 会把 `putalpha` 的
    剪影 α 冲掉（origin/notext 117 张 24bpp 实证）。

    **`text_cov` 已退役（2026-10-20 文字延后合成）**：V-pass 现在跑在**无字图**上
    （文字层延后到 V-pass 之后最后合成，引擎序），写域即整个 desc 面，无需排除文字
    像素。参数保留仅为旧调用面签名兼容（即使传入也不再参与写域）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    import numpy as np
    from PIL import Image

    C = np.asarray(full_img.convert("RGB"), dtype=np.uint8)
    if w_domain is None:
        Cm = np.asarray(magenta_img.convert("RGB"), dtype=np.uint8)
        Cn = np.asarray(nodesc_img.convert("RGB"), dtype=np.uint8)
        W_dom = (np.any(Cm != Cn, axis=2)) & cov
        v_pixels = int((np.any(C != Cn, axis=2) & cov).sum())
    else:
        W_dom = w_domain
        v_pixels = None
    final = C.copy()
    d_rgb = np.clip(rgb_out, 0.0, 1.0)
    d_a = np.clip(a_out, 0.0, 1.0)
    final[W_dom] = (d_rgb[W_dom] * 255.0 + 0.5).astype(np.uint8)
    # α 面：从 V-pass 前底图（out_png = render_with 写入的 RGBA；与 apply_desc_watermark
    # 的 full_png 同一路径）读剪影 α；输出 RGBA（RGB 不变，α=底图剪影，与引擎
    # SnapshotCamera 的带 α 交付契约一致）。
    alpha = np.asarray(Image.open(out_png).convert("RGBA"), dtype=np.uint8)[..., 3]
    Image.fromarray(np.dstack([final, alpha]), "RGBA").save(out_png)
    return {"w_pixels": int(W_dom.sum()), "cov_pixels": int(cov.sum()),
            "v_pixels": v_pixels,
            "alpha_mean_on_w": float(d_a[W_dom].mean()) if W_dom.any() else None}


def _desc_mutate(plan: dict, frame: str, mode: str) -> dict:
    """V-pass 变体计划（ta_render_all.desc_hidden_plan/desc_magenta_plan 统一体
    :468 逐字）：desc 组件 visible/raster 关（hidden）或材质换洋红探针（magenta）。

    deepcopy 继承 `plan["_defer_text"]` ⇒ 变体渲同为**无字底图**（origin 组合序：
    文字层延后到 V-pass 之后最后合成）。**三变体必须同为无字图**——否则 V-pass 写域
    会重新吃到文字像素（旧 text_cov 排除法的病灶）。"""
    import copy

    plan = copy.deepcopy(plan)
    target = DESC_PATHS.get(frame)
    for c in plan["components"]:
        if c["path"] == target:
            if mode == "hidden":
                c["visible"] = False
                c["raster"] = False
                c["visibility_rule"] = {"rule": "v-pass desc-hidden 变体",
                                        "source": "ur_entry", "tags_used": []}
            elif mode == "magenta":
                for s in c.get("material_slots", []):
                    s["_MainTex_runtime"] = {"image": _magenta(),
                                             "source": "magenta probe (desc 可见域测量)"}
    return plan


@invented(reason="引擎写 desc 材质 _SecondTex，离线进程不可执行该写点——三渲差分/深度门控直合两路达到像素等价（结构不同构）", counterpart="Actor.cs UpdateWatermark")
def apply_desc_watermark(full_png, plan: dict, key: str, dbf: str, cfg,
                         render_fn, card: Card | None = None,
                         full_img=None, zbuf_final=None) -> dict:
    """V-pass 编排执行（old_frames/render_card.py:487-522 逐字转写，批22 兑现）：
    V=|full − desc_hidden|（desc 为最后写入者的像素集），final 在 V 上替换为独立
    重投影的 desc 输出（PS 公式，watermark 本模块=ta_watermark 正典）。

    **直合模式（vpass-direct 2026-11-03，`cfg.vpass_direct`）**：单渲深度门控替代
    三渲差分——跳过 hidden/magenta 两次变体渲（render_fn 不调用），写域改
    `W′ = cov ∩ (z_desc == zbuf_final)`（z_desc=desc_pass_arrays return_z 逐像素
    世界 Y 重心插值、与主光栅 depth 同源；zbuf_final=full 渲终态 zbuf **列表**
    （每覆盖样本一个），render_with 经 update_all_components out_zbuf 捕获）。
    gem-zbuf 闭合账（2026-11-02）：35/35 applied 卡 W′=W 双向 0、门控直合 final
    max|Δ|=0（逐位）——写域同+写值同（apply_watermark_pass 同式）+域外同保 full。
    直合语义前提=宝石深度影子（gem_depth_shadow）：PIL 空间合成的宝石族不写
    zbuf，深度门对其结构性免疫需影子先声明宝石深度。False=三渲差分回退通路。

    **覆盖超采样（geometry-aa-4x 2026-11-04，`cfg.supersample>1`）**：深度门的
    两侧必须**同一样本**——`zbuf` 是逐覆盖样本写入的，desc z/cov 就必须在该样本
    偏移下求值。故 `supersample>1` 时走 `_vpass_supersampled`：逐样本跑 desc pass、
    逐样本门控、写域取样本交、写值取样本平均。只留 pass0 zbuf 会让
    `z_desc == zbuf` 中心 vs 样本错位、写域塌成 0（114363 desc 0.77→1.94 病灶）。

    调用面（2026-10-20 文字延后合成）：`full_img` 与 hidden/magenta 两变体渲均为
    **无字底图**（origin 链 `plan["_defer_text"]`，文字层在 V-pass 之后最后合成，
    引擎序）；故写域=整个 desc 面，不再有文字掩码排除位。

    set 归属/override/年标裁决=update_watermark 数据驱动；withRace 从 plan 文本
    内容推导（with_race_for；text 非空判据，notext 口径安全——规则腿挂接位，批21
    装配账 with_race=None 腿之外的执行面）。V-pass 本体=离线发明无游戏对应物
    （引擎写在 desc 材质上，我方像素等价结构不同构，走查档 §0.4 允许）。"""
    from eidolon.core.render.engine import raster as _raster

    frame = desc_frame_for(key)
    # watermark 覆盖/强制请求面（contract E）：座位在场=显式意图，无 desc 层=无消费位，
    # 响亮拒绝（禁静默 skip——外审「无 desc 层静默 skip」病灶；render_with 主体已有
    # 早响亮，本守卫护直调面）。
    _wm_requested = (card is not None
                     and (getattr(card, "watermark_asset", None) is not None
                          or getattr(card, "watermark_force", False)))
    if frame is None or frame not in DESC_MATERIALS:
        if _wm_requested:
            raise ValueError(
                f"watermark 覆盖/强制无 desc 层（key={key} desc_frame=None）——垫图 "
                "V-pass 无消费位，禁静默 skip（contract E 响亮校验）")
        return {"pass": "skipped (无 desc 面)"}
    wm = update_watermark(card, frame, with_race=with_race_for(plan, frame)) \
        if card is not None else None
    if wm is None or wm.get("alpha", 0.0) == 0.0:
        return {"pass": "skipped (wm None/alpha0)" if wm is None
                else f"skipped (alpha=0, set={wm.get('set_id')})"}
    direct = bool(getattr(cfg, "vpass_direct", False))
    ss = int(getattr(cfg, "supersample", 4))
    zbufs: list = []
    if direct:
        assert zbuf_final is not None, (
            "vpass_direct 直合需要 full 渲终态 zbuf（render_with 经 out_zbuf 捕获）"
            "——缺引用=接线断裂，禁静默回退三渲")
        zbufs = list(zbuf_final) if isinstance(zbuf_final, (list, tuple)) else [zbuf_final]
        assert len(zbufs) == ss, (
            f"supersample={ss} 的直合需要 {ss} 个逐样本 zbuf（实得 {len(zbufs)} 个）"
            "——render_with 的 out_zbuf 接线断裂，禁静默回退三渲")
    else:
        _, img_nodesc, _ = render_fn(_desc_mutate(plan, frame, "hidden"))
        _, img_magenta, _ = render_fn(_desc_mutate(plan, frame, "magenta"))
    prefix = array_prefix(plan, frame)
    recon = _frames.scene_for(key)["meta"]   # scene 缓存 meta（重读退役，批8 同账）
    main_tex = main_tex_for(plan, frame, recon, _frames.kit_for(key).textures)
    pass_fn = _raster.DESC_PASS_ARRAYS_FN or desc_pass_arrays
    if direct and ss > 1:
        rgb_out, a_out, cov, w_prime = _vpass_supersampled(
            pass_fn, wm, recon, frame, prefix, main_tex, zbufs, ss)
        stats = apply_watermark_pass(full_img, None, None, rgb_out, a_out, cov,
                                     full_png, w_domain=w_prime)
        stats["vpass_samples"] = ss
    elif direct:
        import numpy as np

        rgb_out, a_out, cov, z_desc = pass_fn(
            wm, recon, DESC_PATHS[frame], prefix, _raster.SIZE,
            _raster.project_world, _raster.sample_bilinear, main_tex, return_z=True)
        # W′ = cov ∩ (z_desc == zbuf_final)：zbuf 单调 max 语义下「desc 是 zbuf 内
        # 最前」的精确判据（NaN 域=zbuf 空位，errstate 压无效比较告警——gem-zbuf
        # 探针同式）。
        with np.errstate(invalid="ignore"):
            w_prime = cov & (z_desc == zbufs[0])
        stats = apply_watermark_pass(full_img, None, None, rgb_out, a_out, cov,
                                     full_png, w_domain=w_prime)
    else:
        rgb_out, a_out, cov = pass_fn(wm, recon, DESC_PATHS[frame], prefix, _raster.SIZE,
                                      _raster.project_world, _raster.sample_bilinear, main_tex)
        stats = apply_watermark_pass(full_img, _raster_comp(img_magenta),
                                     _raster_comp(img_nodesc), rgb_out, a_out, cov,
                                     full_png)
    stats["pass"] = "applied"
    stats["wm"] = {k: wm[k] for k in ("set_id", "wm_ref", "alpha", "offset_runtime")}
    if "override" in wm:
        stats["wm"]["override"] = wm["override"]   # contract E 证据位（覆盖 sha/路径/force）
    stats["vpass_mode"] = "direct" if direct else "three_render"
    return stats


def _vpass_supersampled(pass_fn, wm, recon, frame, prefix, main_tex, zbufs, ss):
    """4x 直合：**逐覆盖样本**跑 desc pass（inside/z 与 zbuf 同一样本），写域取样本交。

    为什么必须逐样本：深度门的判决是 `z_desc == zbuf` 精确浮点等值，而 `zbuf` 由
    full 渲按覆盖样本（`AA_COVERAGE_OFFSETS`）写入。desc z 若在像素中心求值，
    等值在斜面/曲面上大面积不成立 → 写域塌成 0（2026-11-04 114363 实测
    W'=0 / 1x 40952，desc 区 mae 0.773079→1.938584；水印整块消失、区变亮）。
    逐样本后每侧都同为「第 i 个覆盖样本」，等值前提恢复。

    写值=各样本 desc 输出 RGB 的**算术平均**（不透明替换的样本 resolve）。**不按 α 加权**：
    desc shader 的输出 α 不是覆盖面具——location 类 desc 上存在大片 α=0 而 RGB 非零的
    像素（main 纹理透明区；本卡实测 ~1/3 的 desc 覆盖像素），α 加权批会把它们写成黑
    （2026-11-05 113664 实证：desc 区 mae 0.86→20.96）。写域=`cov ∩ (z_desc == zbuf)` 的
    **样本交**（ss 个样本全判 desc 最前）；取交而非并：`apply_watermark_pass` 是不透明
    替换，部分覆盖像素上替换会抹掉 desc 剪影的 4x 覆盖率 AA；交界像素保留 component 渲的
    desc（无水印）——代价=desc 边界至多 1px 无水印边，见 NOTES 未闭合项。

    族账锚=Actor.cs（模块头注族账）；本件=离线 V-pass 的覆盖超采样形。
    """
    import numpy as np

    from eidolon.core.render.engine import raster as _raster

    W, H = _raster.SIZE
    rgb_acc = np.zeros((H, W, 3), dtype=np.float64)
    a_acc = np.zeros((H, W), dtype=np.float64)
    cov_any = np.zeros((H, W), dtype=bool)
    w_all = np.ones((H, W), dtype=bool)
    for i, (dx, dy) in enumerate(_raster.AA_COVERAGE_OFFSETS[:ss]):
        _raster.set_coverage_offset(dx, dy)
        try:
            rgb_i, a_i, cov_i, z_i = pass_fn(
                wm, recon, DESC_PATHS[frame], prefix, _raster.SIZE,
                _raster.project_world, _raster.sample_bilinear, main_tex, return_z=True)
        finally:
            _raster.set_coverage_offset(0.0, 0.0)
        with np.errstate(invalid="ignore"):
            w_i = cov_i & (z_i == zbufs[i])
        w_all &= w_i
        cov_any |= cov_i
        rgb_acc += rgb_i
        a_acc += a_i
    rgb_out = rgb_acc / ss
    a_out = a_acc / ss
    return rgb_out, a_out, cov_any, w_all


def _raster_comp(img):
    """RGBA → 黑底合成 RGB（ta_render_all.comp_of 同式；消费位=apply_desc_watermark
    三渲差分——S11 components.comp_of 单源晚引避免环）。"""
    from eidolon.core.render.game.actor.components import comp_of
    return comp_of(img)
