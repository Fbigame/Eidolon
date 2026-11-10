"""portrait — Actor 肖像族（段 S5 原画与肖像公式层）。

游戏锚：Actor.UpdatePortraitTexture（Actor.cs:Actor.UpdatePortraitTexture——override > LegendaryHeroPortrait
> cardDef.GetPortraitTexture(premium, fallbackToLowerPremium) 链；初始材质态读数降
NORMAL :2892-2894）· Actor.SetPortraitTexture（:2908-2920——写点=肖像材质 mainTexture；
写门四腿 :2911 usingInitial/premium<GOLDEN∧非恒金/品质材质路径双空）·
Actor.UpdatePortraitMaterials（:2956-3035——SIGNATURE 直入品质材质腿；GOLDEN/DIAMOND
经 IsPremiumPortraitEnabled(:3207-3223，对局态 tag+m_LegendaryModel+图形设置链) 门；
DIAMOND→GetPortraitMaterial(GOLDEN) 改写 :2976-2978；else 支→初始材质
m_usingInitialPortraitMaterial :3010-3011；BaconSpell 换装腿 :3000-3002）·
CardDef.GetPortraitTexturePath / GetPortraitMaterialPath（CardDef.cs:CardDef.GetPortraitTexturePath/:436-452
——NORMAL/GOLDEN/DIAMOND/SIGNATURE 路径 switch+逐级回退 premium-1；材质路径仅
GOLDEN/SIGNATURE 有值，NORMAL 腿 `_ => null`）· LoadCustomFrame（Actor.cs:Actor.LoadCustomFrame
——m_CustomHeroFramePrefab 自定义帧换装，登记缺口不接线）。
肖像 shader（不透明，main.alpha 不参与）：PS 逐指令直译
out.rgb = main.rgb · lerp(1, second.rgb·tint·BI, second.a·tint.a·BI)
（portrait-secondtex findings §2-3）；_SecondTex 序列化槽=GenFX_Card_InHand_BannerAtlas
暗角带，运行时只换 _MainTex（findings §1）。uv1=TEXCOORD1（mesh UV1 通道）；
uv1 暗角 F=1.003/0.676 与 G3 uv0 定理=alphatool-render-recipe 守则正典。

我方对位：render_portrait_pass（old_paint/ur_core.py:845——同 canvas/zbuf 公式层；
uv1 消费链 :919-928=npz 优先→补充提取→uv0 兜底）+ render_portrait_submesh
（old_paint/dz_portrait_layer.py:64——全局 zbuf 版）；attach_portrait_component
（old_render/components/portrait.py:31——submesh↔材质槽帧相关 actor_binding 结构化
补标，spell/ally 执行期补/wf·hero·hp·loc 编译期自带）；FRAME_DESC 各行 "portrait"
策略（old_render/registry.py——second/wrap_tile/from_plan 帧差异）；plan.portrait
六编译器同构段（old_frames/scene_compiler.py:294-297 等六份）；plan.portrait_render
（hero_render.py:348/hero_render_bacon.py:217——from_plan 形态 st/bi 参数面）；
portrait_uv1（ur_core.py:925，正典=supply/frames/supplements.portrait_uv1）。

配方面：原画经 recipes.art.portrait（per-card 最敏感域；card id=m_noteMiniGuid 寻址，
批12 异名账）；UV1 补经 recipes.frames.supplements（portrait_uv1）；帧 kit/report/
FRAME_SPECS 经 recipes.frames（批14 增补导出面）。

批15 实现账（2026-10-14，S5 生长；统筹职责切分=判定/绑定/装配参数平行——像素合成
（shader PS 直译）属 engine 侧 S9/S11 段本期不实现，update_portrait_texture 立户；
两源=骨架 §5 走查×旧实现还原，判定/材质判定以 decomp 为准、装配面以旧实现为准）：

纪律面前置——本模块函数族经 recipes.art.portrait / recipes.frames 域项触供给配方
（@item），**消费须在 supply session 内**（入口层独占纪律，批12/13/14 同款；未来门
驱动循环开 session 调本段，段内不开）。

职责面四件——
  * override 链判定（set_portrait_texture）：UpdatePortraitTexture 三腿判定+取数，
    结构化 record 产物（branch/premium/image）——写点（SetPortraitTexture mainTexture
    赋值 :2913-2917）属 S11 组装段。
  * 品质材质判定（update_portrait_materials）：UpdatePortraitMaterials 离线形——
    分支结构（品质材质腿/初始材质腿/DIAMOND→GOLDEN 改写）判定产物，材质路径解析
    需 CardDef 品质路径配方（扩展位记账，语料全 NORMAL 零行为）。
  * submesh↔材质槽绑定（portrait_binding）：kit report actor_components[0] 直读
    （m_portraitMesh 节点+m_portraitMatIdx/m_portraitFrameMatIdx）——帧相关不可
    硬编码（secondtex findings §6：ability=slot1/sub1、ally=slot0/sub0）。
  * 装配参数（portrait_params/plan_portrait/plan_portrait_render/portrait_uv1）：
    FRAME_DESC "portrait" 行平行表+second=None 链材质序列化 _SecondTex 槽解析+
    from_plan 三链 st/bi 参数面+uv1 模式逐帧链+UV1 补充提取消费。

六编译器同构 portrait 段差异账（plan.portrait 键构；行为面=card_id/img 两键）——
  * 公共形六份全同：{"card_id", "source", "apply", "img"} 四键；img=recipes.art.
    portrait(card_id) 内存面（批6 2026-10-12 六份同批换轨）。
  * source/apply=出处串（非行为）：source 两形（sc/sca 带 CardDef.cs:CardDef 尾注、
    wf/hp/loc/bacon 无）；apply 逐帧自述（portraitMesh/PortraitFrame_mesh/Mesh ×
    各帧窗几何注）。统一形取 sc/sca source 全形+自述位留帧键参数。
  * bacon 差外一笔：材质槽 _MainTex_runtime 的 source 注带 plan.portrait_render
    指认（hero_render_bacon.py:306-308）——from_plan 链的公式层参数挂注形态。

签名修正清单（批11b 立壳→实现，批12/13 先例同权）——
  * set_portrait_texture (card_id, override=None)→(card_id, override=None,
    legendary_texture=None, premium=NORMAL, using_initial_material=False)：
    decomp :2881-2899 链需要 LegendaryHeroPortrait 腿与 premium 轴（:2892-2894，
    初始材质态读数降 NORMAL）；stub 缺两腿系形态误推。返回 裸图→结构化 record
    （判定链可见+S11 写点消费，class_color_segment 先例）。
  * update_portrait_materials (plan, premium: str)→(premium: int, *,
    always_golden=False, premium_portrait_enabled=False)：stub 首参 plan 系误推
    （材质策略 dict 是产物非入参）；premium 轴=TAG_PREMIUM int 值（批12 premium
    轴先例）非串；两旗=CardDef.m_AlwaysRenderGoldenPortrait/IsPremiumPortraitEnabled
    离线参数化面（真值链=对局态/图形设置，不入离线形）。
  * update_portrait_texture 签名不动（render_portrait_pass 公式层继承形；S9/S11
    生长时自本段装配参数取数）。

decomp 分支的离线边界（记录的缺口，非静默丢弃）——
  * IsPremiumPortraitEnabled（:3207-3223）：GameEntity tag+m_LegendaryModel+图形
    设置链=对局态/配置态，离线恒 False 参数化——GOLDEN/DIAMOND 品质材质腿随之
    关闭（SIGNATURE 腿不受门控，:2974 首析独支）。
  * m_shadowform 早退（:2961-2963）/BaconSpell 换装腿（:3000-3002）：对局态，
    不接线（语料零命中）。
  * GetPortraitTexturePath 品质>NORMAL 回退链（CardDef.cs:CardDef.GetPortraitTexturePath premium-1 递归）与
    GetPortraitMaterialPath：需 CardDef 品质路径字段配方（现役 recipes 只揭
    m_PortraitTexturePath=NORMAL 腿；扩展位）——premium>NORMAL 判定产物记账
    used_premium 链语义，解析面待配方。
  * LegendaryHeroPortrait 腿（LegendaryHero skin 系统）：语料零命中，参数位 None。
  * LoadCustomFrame（:7983）：自定义帧换装（m_CustomHeroFramePrefab→运行时
    prefab 实例化）登记缺口不接线（回调驱动形态边界 §0.4.1 同族）。

locale 维度（2026-10-23 portrait-locale）：引擎在 GetPortraitTexturePath 之下还有一层
**资产变体解析**——AssetLoader.GetRuntimeAssetVariant 按
`Localization.GetLocale()`（CN 账号强制 zhCN）查 `asset_manifest_<locale>.unity3d` 的
locale catalog（baseGuid→变体 guid/bundle），命中即消费本地化覆盖件，未命中落 base。
该层对 prefab 与纹理两跳同样生效，故对位实现下沉 supply（`supply/art.py::_portrait_tex`
两次 resolve 均传 GameContext.locale（契约 D）），本段只透传来源账
（plan.portrait["asset"]→渲染日志），判定/组装语义不变。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from eidolon.core.infra.card import Premium
from eidolon.core.recipes.art import portrait as _art_portrait
from eidolon.core.recipes.art import portrait_mip as _art_portrait_mip
from eidolon.core.recipes.art import portrait_source as _art_portrait_source
from eidolon.core.recipes.frames import FRAME_SPECS, supplements
from eidolon.core.render.engine import raster as _raster
from eidolon.core.render.scenes import scenes as _frames
from eidolon.core.render._provenance import parallel  # noqa: F401 （族默认）

# ============================================================================
# UpdatePortraitMaterials 判定（Actor.cs:Actor.UpdatePortraitMaterials 离线形）
# ============================================================================


@parallel
def update_portrait_materials(premium: int, *, always_golden: bool = False,
                              premium_portrait_enabled: bool = False) -> dict:
    """品质材质判定：UpdatePortraitMaterials 对位（Actor.cs:Actor.UpdatePortraitMaterials 离线形）。

    premium=TAG_PREMIUM 值（0 NORMAL/1 GOLDEN/2 DIAMOND/3 SIGNATURE）；
    always_golden=CardDef.m_AlwaysRenderGoldenPortrait（:2969-2971 覆写 GOLDEN）；
    premium_portrait_enabled=IsPremiumPortraitEnabled()（:3207-3223 对局态/图形
    设置链，离线恒 False——参数化位）。

    分支（引擎序）：品质材质腿（:2974——SIGNATURE 直入；GOLDEN/DIAMOND 须门开）→
    DIAMOND 改写取金材质（:2976-2978）→ 写门+贴图补挂（TryApplyPremiumPortraitTexture
    :3037-3050，初始材质态回退 :2987-2990）‖ else 支→初始材质
    （:2999-3011，m_usingInitialPortraitMaterial=true；BaconSpell 腿不接线记账）。
    返回材质策略 dict（材质腿/贴图品质/边界注，供 S11 写点消费）；材质路径解析
    （GetPortraitMaterialPath CardDef.cs:CardDef.GetPortraitMaterialPath，仅 GOLDEN/SIGNATURE 有值）=CardDef
    品质路径配方扩展位（模块 docstring 边界账）。
    """
    premium = int(premium)
    effective = int(Premium.GOLDEN) if always_golden else premium      # :2969-2971
    out: dict = {
        "premium_in": premium, "effective_premium": effective,
        "premium_portrait_enabled": premium_portrait_enabled,
        "source": "Actor.cs:Actor.UpdatePortraitMaterials UpdatePortraitMaterials（离线判定形；"
                  "材质路径解析=CardDef 品质路径配方扩展位）",
    }
    if effective == int(Premium.SIGNATURE) or (
            effective in (int(Premium.GOLDEN), int(Premium.DIAMOND))
            and premium_portrait_enabled):                              # :2974
        # DIAMOND→GOLDEN 材质改写（:2976-2978）；SIGNATURE/GOLDEN 直取
        material_premium = int(Premium.GOLDEN) if effective == int(Premium.DIAMOND) \
            else effective
        out.update({
            "branch": "premium_material",
            "material_premium": material_premium,
            "material_path_leg": {int(Premium.GOLDEN): "m_GoldenPortraitMaterialPath",
                                  int(Premium.SIGNATURE): "m_SignaturePortraitMaterialPath",
                                  }[material_premium],                  # CardDef.cs:CardDef.GetPortraitMaterialPath
            "texture_premium": effective,   # TryApplyPremiumPortraitTexture(cardDef, eff)
                                            # 贴图品质=原轴（fallbackToLowerPremium 链）
            "diamond_rewrites_golden": effective == int(Premium.DIAMOND),
        })
    else:
        out.update({
            "branch": "initial",                                        # :2999-3011
            "material_premium": None,
            "material_path_leg": None,   # GetPortraitMaterialPath `_ => null`（NORMAL 腿）
            "texture_premium": effective,
            "using_initial_material": True,
            "bacon_spell_leg": "Actor.cs:Actor.UpdatePortraitMaterials BaconSpell 换装腿不接线"
                               "（对局态 m_entity.IsBaconSpell；语料零命中）",
        })
    return out


# ============================================================================
# UpdatePortraitTexture 判定链（Actor.cs:Actor.UpdatePortraitTexture）+ 取数
# ============================================================================


@parallel
def set_portrait_texture(card_id: str, override=None, legendary_texture=None,
                         premium: int = int(Premium.NORMAL),
                         using_initial_material: bool = False) -> dict:
    """原画取数与 override 链判定：UpdatePortraitTexture 对位（Actor.cs:Actor.UpdatePortraitTexture）。

    card_id=引擎串 id（CardDef 寻址键；我方=Card.card_id=m_noteMiniGuid，批12 异名
    账）；override=m_portraitTextureOverride（优先级首位）；legendary_texture=
    LegendaryHeroPortrait.PortraitTexture（次位）；premium=m_premiumType；
    using_initial_material=m_usingInitialMaterial 态（真值由 update_portrait_materials
    判定——初始材质态贴图读数降 NORMAL，:2892-2894）。

    链序（引擎逐字）：override 腿（:2882-2885）→ LegendaryHeroPortrait 腿
    （:2886-2890）→ cardDef 腿（:2891-2896，GetPortraitTexture(premium,
    fallbackToLowerPremium=true)；品质回退链=CardDef.cs:CardDef.GetPortraitTexturePath 递归，解析面=品质路径
    配方扩展位）。返回结构化 record：{"branch", "premium", "card_id", "image"}
    （image=内存面，经 recipes.art.portrait）；写点（SetPortraitTexture mainTexture
    :2913-2917）属 S11 组装段。override/legendary 腿语料零命中（参数位缺省即不
    触发）。
    """
    if override is not None:                                            # :2882-2885
        return {"branch": "override", "premium": None, "card_id": card_id,
                "image": override}
    if legendary_texture is not None:                                   # :2886-2890
        return {"branch": "legendary_hero_portrait", "premium": None,
                "card_id": card_id, "image": legendary_texture}
    # cardDef 腿：初始材质态读数降 NORMAL（:2892-2894）
    used = int(Premium.NORMAL) if using_initial_material else int(premium)
    return {"branch": "carddef", "premium": used, "card_id": card_id,
            "image": _art_portrait(card_id)}                            # :2895-2896


# ============================================================================
# submesh↔材质槽绑定（attach_portrait_component 对位；帧相关不可硬编码）
# ============================================================================

_RUNTIME_KEY = "_MainTex_runtime"
"""肖像槽运行时贴图标记键（六编译器+attach 同款；消费位 ur_core.py:903）。"""


@parallel
def portrait_binding(frame_key: str) -> dict:
    """肖像 submesh↔材质槽绑定：attach_portrait_component 对位
    （old_render/components/portrait.py:31；wf_render.py:447-449/hp_render.py:374-378/
    location_render.py:511-515/hero_render.py:499-509 编译期写同构）。

    kit report actor_components[0] 直读（m_portraitMesh 节点路径+m_portraitMatIdx
    +m_portraitFrameMatIdx——旧八编译器 binding 同源，scene_compiler.py:243-257 形）；
    帧相关不可硬编码（secondtex findings §6：ability=slot1/sub1(10 tris)、
    ally=slot0/sub0(19 tris)、weapon=slot1/sub1(22 tris)、heropower=slot1/sub1
    (6 tris)、location=slot0/sub0(11 tris)、hero=slot1/sub1、bacon=slot0/sub0
    单材质）。返回 {"node", "sub", "frame_sub", "runtime_key"}。

    界外回退腿（2026-10-24 ct44 帧链批；trinket 实测 m_portraitMesh=FrameMesh 单材质
    而 m_portraitMatIdx=1 越界）：GetPortraitMaterial（Actor.cs:3197-3215）主腿界外
    （`m_portraitMatIdx < GetSharedMaterials().Count` 不成立）→ m_legacyPortraitMaterialIndex
    回退——AssignMeshRenderers（:7897-7913）m_meshRenderer=名 "Mesh"（OrdinalIgnoreCase
    Equals）GO 的 renderer，AssignMaterials（:7945-7968）对其 GetComponentsInChildren
    （含自体，:7917）逐材质名 LastIndexOf("Portrait", OrdinalIgnoreCase)>=0 末次命中
    登记槽号。缺 m_portraitMesh 引用 assert 响亮（旧 attach 空腿=十开放帧链不存在的
    形态，tripwire 批12 纪律）；主腿有效帧零行为变化（回退腿仅在越界时触达）。
    """
    ac = _frames.scene_for(frame_key)["report"]["actor_components"][0]
    refs = ac.get("object_refs") or {}
    scalars = ac.get("scalars") or ac   # report 形态真差异归一读取（同 frames._kit_meta
    # 先例，供给面不动）：ability kit 平面（ac["m_portraitMatIdx"] 直键，
    # scene_compiler.py:256 消费形）vs frames kit 嵌套 scalars 面（sca:226-239 等）
    node = refs.get("m_portraitMesh", {}).get("node")
    sub = scalars.get("m_portraitMatIdx")
    if node is not None and sub is not None:
        # 主腿界外核查（GetPortraitMaterial :3200-3206 同判）：m_portraitMesh 节点
        # 材质数内=主腿成立；越界=legacy 回退（下支）。
        n_mats = _portrait_mesh_mat_count(frame_key, node)
        if n_mats is not None and int(sub) < n_mats:
            return {"node": node, "sub": int(sub),
                    "frame_sub": scalars.get("m_portraitFrameMatIdx"),
                    "runtime_key": _RUNTIME_KEY}
    assert node is not None, (
        f"{frame_key} 帧 kit report 无 m_portraitMesh 绑定"
        f"（node={node!r} sub={sub!r}）——旧 attach 空腿形态不在十开放帧链"
        "（tripwire 纪律）")
    # ---- legacy 回退（AssignMaterials 材质名扫描；仅主腿界外帧触达）----
    fb = _legacy_portrait_slot(frame_key)
    assert fb is not None, (
        f"{frame_key} 肖像绑定主腿界外（node={node!r} sub={sub!r}）且 legacy 扫描"
        "（AssignMaterials \"Mesh\" 子树材质名 Portrait 命中）无命中——prefab 形态漂移")
    fnode, fsub = fb
    return {"node": fnode, "sub": int(fsub),
            "frame_sub": scalars.get("m_portraitFrameMatIdx"),
            "runtime_key": _RUNTIME_KEY,
            "binding_source": ("GetPortraitMaterial 界外回退：m_legacyPortraitMaterialIndex"
                               "（Actor.cs:3197-3215 × AssignMeshRenderers/AssignMaterials"
                               " :7897-7913/:7945-7968）")}


def _portrait_mesh_mat_count(frame_key: str, node_path: str) -> int | None:
    """m_portraitMesh 节点的序列化材质数（界外核查用；节点无 renderer/查无→None）。"""
    hierarchy = _frames.scene_for(frame_key)["hierarchy"]
    for n, _key, path in _walk_with_key(hierarchy):
        if path == node_path:
            rr = n.get("renderers") or []
            return len(rr[0].get("materials") or []) if rr else None
    return None


def _legacy_portrait_slot(frame_key: str) -> tuple[str, int] | None:
    """AssignMaterials 扫描（:7897-7913 m_meshRenderer=名 "Mesh" GO；:7945-7968 逐
    材质名 LastIndexOf("Portrait", OrdinalIgnoreCase)>=0 末次命中；GetComponents-
    InChildren 含自体——扫描序=自体先、子树 DFS，末次命中即最后命中槽）。"""
    hierarchy = _frames.scene_for(frame_key)["hierarchy"]
    mesh_root = None
    for n, _key, path in _walk_with_key(hierarchy):
        if n["name"].lower() == "mesh":   # OrdinalIgnoreCase Equals（:7908）
            mesh_root = (n, path)
            break
    if mesh_root is None:
        return None
    hit: tuple[str, int] | None = None
    n0, p0 = mesh_root

    def scan(n, path):
        nonlocal hit
        rr = n.get("renderers") or []
        if rr:
            for i, m in enumerate(rr[0].get("materials") or []):
                if m and "portrait" in str(m.get("name") or "").lower():
                    hit = (path, i)
        for c in n.get("children", []):
            scan(c, f"{path}/{c['name']}")

    scan(n0, p0)
    return hit


@parallel
def plan_portrait(card_id: str, frame_key: str | None = None) -> dict:
    """plan.portrait 键构：六编译器同构段统一形
    （old_frames/scene_compiler.py:294-297 等六份；行为面=card_id/img）。

    img=recipes.art.portrait(card_id) 内存面（m_noteMiniGuid 寻址，批6 换轨）；
    source=全形出处串（sc/sca 形）；apply=写点自述（frame_key 给定时带绑定槽位，
    旧为逐帧字面注——模块 docstring 差异账）。
    asset=recipes.art.portrait_source(card_id)——实际消费的纹理地址账（locale/base/
    变体 guid+bundle；2026-10-23 portrait-locale：寻址按客户端 locale 解析，此键让
    「消费了哪一件」可复核，不再只有一张内存图）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    apply = "portraitMesh 材质（SetPortraitTexture Actor.cs:Actor.SetPortraitTexture 只写 mainTexture）"
    if frame_key is not None:
        b = portrait_binding(frame_key)
        apply = f"{b['node']} 材质[m_portraitMatIdx={b['sub']}]（Actor.cs:Actor.UpdatePortraitTexture）"
    return {"card_id": card_id,
            "source": "cards_map → CardDef prefab → m_PortraitTexturePath"
                      "（DefLoader.cs:DefLoader.GetCardDef, CardDef.cs:CardDef）",
            "apply": apply,
            "asset": _art_portrait_source(card_id),
            "img": _art_portrait(card_id)}


# ============================================================================
# 装配参数（FRAME_DESC "portrait" 行平行 + from_plan 参数面 + uv1 模式）
# ============================================================================

_PORTRAIT_PARAMS: dict[str, dict] = {
    # FRAME_DESC 各行 "portrait" 策略平行表（old_render/registry.py；second=None=
    # 材质序列化 _SecondTex 槽，运行时只换 _MainTex——ps findings §1）
    "Card_Hand_Ability": {"second": None, "wrap_tile": False},         # registry:172（consumer-v2 改键）
    # 金法术档（capture-determinism 2026-10-30）：同 ability 形（second=None=
    # 材质序列化 _SecondTex 槽；premium 肖像材质随金 prefab 序列化实况，与
    # ally_premium 同款「premium 材质槽=金 BannerAtlas」口径）
    "Card_Hand_Ability_Premium": {"second": None, "wrap_tile": False},
    "Card_Hand_Ally": {"second": None, "wrap_tile": False},            # :203
    # 金卡档同 ally 形（mechorse-golden 2026-10-21：second=None=序列化 _SecondTex 槽
    # ——premium 肖像材质 Card_InHand_AllyPortrait_Premium 槽=金 BannerAtlas，§6 采集
    # 口径反转下 ps 层照同链）
    "Card_Hand_Ally_Premium": {"second": None, "wrap_tile": False},
    "Card_Hand_Weapon": {"second": "GenFX_Card_InHand_BannerAtlas.png", "wrap_tile": False},  # :223
    "Card_Hand_Hero": {"second": "GenFX_HeroFrame.png", "wrap_tile": False, "from_plan": True},  # :246
    "Card_Play_Hero": {"second": "GenFX_HeroFrame.png", "wrap_tile": False, "from_plan": True},  # :266
    "Card_Play_Bacon_Hero": {"second": "GenFX_HeroFrame.png", "wrap_tile": False,
                        "from_plan": True},                            # :302
    "History_HeroPower": {"second": None, "wrap_tile": True},          # :319（3×3 tile/Repeat）
    "Card_Hand_Location": {"second": None, "wrap_tile": False},        # :337（=类色图集）
    # ct44 饰品（bg-ct40-43-44-routing 2026-10-24）：肖像窗=Mesh slot0
    # （BG_Trinket_BigCard_FramePortrait_Mat，Unlit_Portrait 白占位）——绑定经
    # portrait_binding 界外回退腿（GetPortraitMaterial legacy 槽，见该函数注）。
    # second=None=材质序列化 _SecondTex 槽（Lettuce_MercMinionAbility_InPlayFramePortait）。
    # 键=canonical prefab 键（与 _UV1_MODE/portrait_binding 同键空间；kit 命名空间
    # 'trinket' 只活在 FRAME_SPECS 映射表左列）。
    "Card_Hand_BG_Trinket": {"second": None, "wrap_tile": False},
    # ct43 畸变（bg-ct40-43-44-routing 2026-10-24）：肖像窗=PortraitFrame_mesh
    # slot1（m_portraitMatIdx=1 主腿成立，材质 Card_InHand_Ability-portrait——与
    # spell 同资产同约定，probe 实测）；second=None=材质序列化 _SecondTex 槽
    # （GenFX_Card_InHand_BannerAtlas，spell 行同象）。
    "Card_Hand_BG_Anomaly": {"second": None, "wrap_tile": False},
}
"""肖像装配策略表（帧键→second/wrap_tile/from_plan；旧 FRAME_DESC "portrait" 行
平行——本模块自带表，S11 新 registry 收口时自此处取数，批13 选型账同形）。"""

_UV1_MODE: dict[str, str] = {
    # uv1 装配模式（帧键→通道来源）：FRAME_SPECS uv1 列派生+ability/bacon 特源显式
    # consumer-v2 改键：FRAME_SPECS 键=supply kit 命名空间，映射到 prefab 键
    **{{"ally": "Card_Hand_Ally", "ally_premium": "Card_Hand_Ally_Premium",
        "weapon": "Card_Hand_Weapon", "hero_hand": "Card_Hand_Hero",
        "hero_play": "Card_Play_Hero", "heropower": "History_HeroPower",
        "location": "Card_Hand_Location", "trinket": "Card_Hand_BG_Trinket",
        "anomaly": "Card_Hand_BG_Anomaly"}[key]: (spec["uv1"] or "supplement")
       for key, spec in FRAME_SPECS.items()},
    "Card_Hand_Ability": "supplement",                 # ability 帧无 spec 行：帧 npz
    # 无 uv1 通道→supplements.portrait_uv1 补充提取（正典面，双网格 recon_map）
    "Card_Hand_Ability_Premium": "supplement",         # 金法术同构（2026-10-30，ability 特源显式同款）
    # bacon：键=prefab 键（consumer-v2 键空间，2026-10-30 改；旧链名行已删——该行漏改致
    # portrait_params 查表 KeyError）。prefab 身份锚=ActorNames.cs:ActorNames.
    # GetPlayActorByTags BATTLEGROUNDS_HERO 支→Card_Play_Bacon_Hero.prefab:
    # 227eb40f91281fa429c48c8a730c982f（=frames.bacon.BACON_HERO_PLAY_REF）。
    # 值锚=frames.bacon.bacon_kit 内联 spec uv1 列="uv0copy"（bacon 无 FRAME_SPECS
    # 行→上面的派生式覆盖不到，须显式列出）。
    "Card_Play_Bacon_Hero": "uv0copy",
}
"""uv1 通道来源逐帧链（supplement=补充提取 / uv0copy / zeros；运行时消费链
ur_core.py:919-928=npz 优先→补充提取→uv0 兜底，模式=正典落点预判）。"""

from_plan = "Card_Hand_Hero", "Card_Play_Hero", "Card_Play_Bacon_Hero"  # consumer-v2 改键
"""from_plan 链（FRAME_DESC 行带 from_plan=True：st/bi 自 plan.portrait_render）。"""


@parallel
def portrait_params(frame_key: str) -> dict:
    """肖像装配参数：FRAME_DESC "portrait" 行对位（old_render/registry.py）。

    返回行拷贝+派生面：second=None 链解析材质序列化 _SecondTex 槽名（_second_tex_
    serialized，消费形=ur_core.py:905-909——hierarchy 直读 Path.name）+uv1 模式+
    uv1 补充提取网格键（supplement 链）。未知帧键 assert 响亮（tripwire，批14
    _KIT_SOURCE 同纪律）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    row = _PORTRAIT_PARAMS.get(frame_key)
    assert row is not None, (
        f"未知帧键 {frame_key!r}——_PORTRAIT_PARAMS 无此行"
        f"（开放位={sorted(_PORTRAIT_PARAMS)}）")
    out = dict(row)
    out["from_plan"] = bool(row.get("from_plan"))
    if out["second"] is None:
        out["second_source"] = "material_serialization"
        out["second_serialized"] = _second_tex_serialized(frame_key)
    else:
        out["second_source"] = "policy_row"
    mode = _UV1_MODE[frame_key]
    out["uv1_mode"] = mode
    out["uv1_supplement_mesh"] = _SUPPLEMENT_MESH.get(frame_key) if mode == "supplement" else None
    return out


_SUPPLEMENT_MESH: dict[str, str] = {
    "Card_Hand_Ability": "Card_InHand_Ability_Portrait_mesh",
    # 金法术（2026-11-04，golden 98918）：supplements recon_map 同键——缺行=uv1 走
    # uv0 兜底，_SecondTex（BannerAtlas 网格图集）被肖像 uv0 采样印格子鬼影。
    "Card_Hand_Ability_Premium": "Card_InHand_Ability_Premium_Portrait_Mesh",
    "Card_Hand_Ally": "Card_InHand_Ally_Portrait_mesh",
    "Card_Hand_Ally_Premium": "Card_InHand_Ally_Portrait_Premium_mesh",   # 金卡档（mechorse-golden；
                                                                # supplements recon_map 同键）
}
"""uv1 补充提取网格键（supplements.portrait_uv1 recon_map 同构——全网格全通道，
extract_portrait_uv1 正典）。"""


def _second_tex_serialized(frame_key: str) -> str:
    """材质序列化 _SecondTex 槽名解析（ur_core.py:905-909 消费形——肖像节点
    renderers[materials[sub]] 的 tex._SecondTex.texture.file 取 Path.name）。
    hierarchy=kit 场景面（frames.scene_for）；无槽 assert 响亮（second=None 链的
    序列化槽必在——spell/ally=BannerAtlas、heropower=Hero_Power_D、location=类色
    图集，ps findings §1/§6）。"""
    b = portrait_binding(frame_key)
    hierarchy = _frames.scene_for(frame_key)["hierarchy"]
    for n, _key, path in _walk_with_key(hierarchy):
        if n.get("mesh_stats") and path == b["node"]:
            pmat = n["renderers"][0]["materials"][b["sub"]]
            entry = (pmat.get("tex", {}).get("_SecondTex", {}).get("texture") or {})
            name = entry.get("file")
            assert name, f"{frame_key} 肖像材质无序列化 _SecondTex（pmat={pmat}）"
            return Path(name).name
    raise AssertionError(f"{frame_key} 层级未找到肖像节点 {b['node']!r}")


def _walk_with_key(node, key: str = "root", path: str = ""):
    """层级走查器（ur_core.walk_with_key 同式 :1012-1016——全路径=根名起斜杠链）。"""
    p = f"{path}/{node['name']}" if path else node["name"]
    yield node, key, p
    for i, c in enumerate(node.get("children", [])):
        yield from _walk_with_key(c, f"{key}.{i}", p)


@parallel
def plan_portrait_render(frame_key: str) -> dict:
    """from_plan 链公式层参数：plan.portrait_render 对位
    （hero_render.py:348-362 hand/play 常量 + hero_render_bacon.py:164-178 材质
    序列化直读）。行为面=second_tex/second_tint/blend_intensity（消费位
    render_card.py:430-433 st/bi 直取）；hero hand/play=反汇编定值常量（旧面字面
    迁移）；bacon=kit 层级 Mesh slot0 材质序列化直读（_SecondTint/_BlendIntensity，
    desat 支恒等——bhn_formula_adjudication 数值裁决）。非 from_plan 链 assert
    响亮。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    assert frame_key in from_plan, (
        f"{frame_key!r} 非 from_plan 链（开放位={list(from_plan)}）")
    if frame_key == "Card_Hand_Hero":
        st = [0.501960813999176, 0.501960813999176, 0.501960813999176,
              0.38823530077934265]
        bi, sub = 2.0, 1
    elif frame_key == "Card_Play_Hero":
        st, bi, sub = [1.0, 1.0, 1.0, 1.0], 1.0, 1
    else:   # hero_play_bacon：材质序列化直读（旧 _find_node(recon, "Mesh") 同源——
        # kit 层级即该 hierarchy，场景面直读免副本）
        b = portrait_binding(frame_key)
        hierarchy = _frames.scene_for(frame_key)["hierarchy"]
        st = bi = sub = None
        for n, _key, path in _walk_with_key(hierarchy):
            if n.get("mesh_stats") and path == b["node"]:
                pmat = n["renderers"][0]["materials"][b["sub"]]
                st = list(pmat["colors"]["_SecondTint"])
                bi = float(pmat["floats"]["_BlendIntensity"])
                sub = b["sub"]
                break
        assert st is not None, f"{frame_key} 层级未找到肖像节点 {b['node']!r}"
    return {"second_tex": "GenFX_HeroFrame@uv1", "second_tint": st,
            "blend_intensity": bi, "sub": sub}


# ============================================================================
# uv1 补充提取消费（supplements 正典）
# ============================================================================


@parallel
def portrait_uv1(mesh_name: str):
    """肖像网格 TEXCOORD1 补充提取消费（ur_core.py:925 portrait_uv1 对位；
    正典=supply/frames/supplements.portrait_uv1 双网格全通道）。

    mesh_name 不在补充面→None（调用方 uv0 兜底支的记账位——开放帧链中 spell/ally
    恒命中，其余链 uv1_mode 非 supplement 不走此函数）。供给 dict=@item 进程
    memo（旧 _UV1_SUP 局部 memo 的上移等价，无重复提取）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    entry = supplements.portrait_uv1().get(mesh_name)
    return entry["uv1"] if entry else None


# ============================================================================
# 公式层（像素合成=shader PS 直译；批22 兑现——engine/raster 消费面）
# ============================================================================

BRIGHTNESS_LIFT = 0.15   # PS l(0.15,0.15,0.15)；min 支在 o2=白时恒不命中
ALPHA_LIFT = 1.15        # PS l(1.15)
UV_WRAP = False          # hp 帧 Repeat 语义（ur_core.render_portrait_pass 按帧置位；
                         # uservisual 725 案：texel mod 后 clamp；单渲单帧序每渲无条件置位
                         # 防跨帧残留）


@parallel
def portrait_mip_entry(card_id: str) -> dict | None:
    """肖像纹理真 mip 链条目（按需直提；None=纯 mip0 路径）。

    地址=(bundle, path_id) 消费点登记（supply.art.portrait/portrait_mip 同链单源），
    链=序列化真 mip 逐层（真/box MAE 3.16 结构性差异，box 不取）；LOD=log2(ρ)+纹理
    序列化 MipBias（肖像语料实测恒 FilterMode=2 Trilinear / MipBias=−0.5）。
    阴性对照 raster.MIP_ENABLE=False 时恒 None（与 mip 采样族同一总闸）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    if not _raster.mip_enabled():
        return None
    return _art_portrait_mip(card_id)


_MIP_L0_TOL = 1.0 / 255.0 + 1e-12


def _entry_matches(entry: dict, rgba: np.ndarray) -> bool:
    """内容校验派发：采样数组与链 L0 同源（mip0 双解码器位等已证；容忍 1 级解码抖动）。

    安全网：运行时 `_MainTex` 可能被材质级写点覆写（类色图集/材质 override 同族），
    此时 CardDef 肖像链与实采数组不同源——链分辨率与数组不同会让 `_sample_level` 的
    shape 换算按错比例缩放（错色）。语料 127 卡实测 0 命中（`mip_skip` 恒 None），
    故本检查只作未来帧型/写点变化的响亮降级位。"""
    l0 = entry["chain"][0]
    if l0.shape != rgba.shape:
        return False
    return bool(np.abs(l0 - rgba).max() <= _MIP_L0_TOL)


@parallel
def portrait_factor(second_rgba: np.ndarray, second_tint, blend_intensity) -> np.ndarray:
    """F = lerp(1, second.rgb*t.rgb, second.a*t.a)，t=_SecondTint*_BlendIntensity
    （dz_portrait_layer.portrait_factor :57 逐字——engine 侧 mip 工厂消费位）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    t = np.asarray(second_tint, dtype=np.float64) * float(blend_intensity)
    w = second_rgba[..., 3:4] * t[3]
    return (1.0 - w) + second_rgba[..., :3] * t[None, None, :3] * w


def _sample_bilinear_uv(arr: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """UV(0..1, v 向上) 双线性采样，边缘 clamp；UV_WRAP=True 先 texel mod
    （dz_portrait_layer.sample_bilinear :37 逐字）。"""
    h, w = arr.shape[:2]
    x = u * w - 0.5
    y = (1.0 - v) * h - 0.5
    if UV_WRAP:
        x = np.mod(x, w)
        y = np.mod(y, h)
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = x0 + 1
    y1 = y0 + 1
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    return (arr[y0, x0] * (1 - fx) * (1 - fy) + arr[y0, x1] * fx * (1 - fy)
            + arr[y1, x0] * (1 - fx) * fy + arr[y1, x1] * fx * fy)


@parallel
def render_portrait_submesh(canvas: np.ndarray, zbuf: np.ndarray, depth, px, py, uv0, uv1,
                            tris, main_rgba: np.ndarray, second_rgba: np.ndarray,
                            second_tint, blend_intensity,
                            color=(1.0, 1.0, 1.0, 1.0), vcolor=(1.0, 1.0, 1.0, 1.0),
                            mip_entry=None) -> None:
    """肖像窗 PS 直译（dz_portrait_layer.render_portrait_submesh :64 逐字；z 序根修
    版——深度=全局 zbuf 世界 Y 轴，tri_z >= zbuf 才写〔引擎 ZTest LEqual〕，写色同时
    写深；不透明 One/Zero）。公式：out.rgb = main.rgb · F，min 尾支 (o2=白) 恒不命中
    仍逐指令。

    `mip_entry` 给定 = _MainTex 走真 mip 链三线性（LOD=log2(ρ)+MipBias，ρ=D3D11.3
    §7.18.11 屏幕轴各向同性式；正交投影+仿射 UV → 三角形内 ∇ 恒定=逐像素导数闭式，见
    raster.tri_lambda）；None = 纯 mip0 双线性（逐位等同旧行为）。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    color = np.asarray(color, dtype=np.float64)
    vcol = np.asarray(vcolor, dtype=np.float64) * color
    order = sorted(range(len(tris)), key=lambda i: float(py[tris[i]].mean()))
    for i in order:
        tri = tris[i]
        xs, ys = px[tri], py[tri]
        xmin = max(int(np.floor(xs.min())), 0)
        xmax = min(int(np.ceil(xs.max())), canvas.shape[1] - 1)
        ymin = max(int(np.floor(ys.min())), 0)
        ymax = min(int(np.ceil(ys.max())), canvas.shape[0] - 1)
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
        # 逐像素深度（世界 Y 插值）与 LEqual 测试（>=；引擎 ZTest LEqual 同语义）
        # 深度用覆盖样本位置（c*）；UV/颜色仍用像素中心（l*）——geometry-aa-4x。
        zs = depth[tri]
        zpix = cc0 * zs[0] + cc1 * zs[1] + cc2 * zs[2]
        zb = zbuf[ymin:ymax + 1, xmin:xmax + 1]
        inside = inside & (zpix >= zb)
        if not inside.any():
            continue
        u0 = l0 * uv0[tri[0], 0] + l1 * uv0[tri[1], 0] + l2 * uv0[tri[2], 0]
        v0 = l0 * uv0[tri[0], 1] + l1 * uv0[tri[1], 1] + l2 * uv0[tri[2], 1]
        u1 = l0 * uv1[tri[0], 0] + l1 * uv1[tri[1], 0] + l2 * uv1[tri[2], 0]
        v1 = l0 * uv1[tri[0], 1] + l1 * uv1[tri[1], 1] + l2 * uv1[tri[2], 1]
        if mip_entry is not None:
            # Repeat 语义先落到 UV（texel 换算后 mod 等价：mod(u*w-0.5,w) ≡ mod(u,1)*w-0.5）
            if UV_WRAP:
                u0, v0 = np.mod(u0, 1.0), np.mod(v0, 1.0)
            tri2d = np.stack([xs, ys], axis=1)
            main = _raster.sample_mip_rgba(
                main_rgba, u0 * main_rgba.shape[1] - 0.5, (1.0 - v0) * main_rgba.shape[0] - 0.5,
                _raster.tri_lambda(tri2d, uv0[tri], main_rgba), mip_entry,
                _raster.sample_texel_bilinear)
        else:
            main = _sample_bilinear_uv(main_rgba, u0, v0)
        sec = _sample_bilinear_uv(second_rgba, u1, v1)
        F = portrait_factor(sec, second_tint, blend_intensity)
        blend = main[..., :3] * F
        # PS min 支：out = min((blend,1), ((blend+0.15)*o2.rgb, 1.15*o2.rgb))
        cand1 = np.concatenate([blend, np.full(blend.shape[:2] + (1,), 1.0)], axis=-1)
        cand2_rgb = (blend + BRIGHTNESS_LIFT) * vcol[None, None, :3]
        cand2_a = ALPHA_LIFT * vcol[3]
        cand2 = np.concatenate([cand2_rgb, np.full(blend.shape[:2] + (1,), cand2_a)], axis=-1)
        out = np.minimum(cand1, cand2)
        sub = canvas[ymin:ymax + 1, xmin:xmax + 1]
        sub[inside] = out[inside]
        zb[inside] = zpix[inside]     # 不透明：写色同时写深


@parallel
def update_portrait_texture(canvas, zbuf, hierarchy, npz, comp, get_tex, walk, *,
                            second_tex_name: str | None = None,
                            second_tint=None, blend_intensity=None,
                            wrap_tile: bool = False, mip_entry: dict | None = None,
                            asset: dict | None = None):
    """肖像窗公式层统一挂接：render_portrait_pass 对位（old_paint/ur_core.py:845
    逐字转写，批22 兑现；out.rgb = main·lerp(1, second·t, second.a)，不透明）。

    帧型策略：second=None 链=材质序列化 _SecondTex 槽（portrait_params
    second_serialized）、from_plan 链=plan.portrait_render（st/bi 调用方传）、
    hp wrap_tile=True（Repeat 仿真→UV_WRAP 每渲无条件置位防跨帧残留）；
    uv1 消费链=npz 优先→补充提取（supplements.portrait_uv1）→uv0 兜底。
    mip_entry=肖像 _MainTex 真 mip 链（plan.portrait.card_id → portrait_mip_entry；
    None=纯 mip0，逐位等同旧行为）；_SecondTex 不参与（desc 族纹理 mips=1 无链）。
    asset=plan.portrait["asset"] 来源账（locale/变体地址），原样回传供渲染日志记账。
    返回 dict 含 uv1_source/mip 供记账。

    族账锚=Actor.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    from pathlib import Path as _P

    pkey = pnode = None
    for n, key, path in walk(hierarchy):
        if n.get("mesh_stats") and path == comp["path"]:
            pkey, pnode = key, n
            break
    psub = comp["portrait_submesh"]["sub"]
    prt = next(s for s in comp["material_slots"] if s["slot"] == psub)["_MainTex_runtime"]
    _pimg = prt.get("image")
    if _pimg is None:
        # 2026-10-21 render-data-decouple：`prt["file"]` → `Image.open(Path(...))` 兜底
        # **删除**（已退役的 assets_dir 语义）。plan 肖像纹理必须为内存面；缺 image
        # 响亮失败（带 plan 路径上下文），不读盘。
        raise KeyError(
            f"肖像槽 {comp['path']!r}[slot={psub}] 无 _MainTex_runtime.image"
            f"（file={prt.get('file')!r}）——路径直读盘=已退役的 assets_dir 语义"
            "（plan 肖像纹理必须为内存面 image）")
    main_rgba = np.asarray(_pimg.convert("RGBA"), dtype=np.float64) / 255.0
    mip_skip = None
    if mip_entry is not None and not _entry_matches(mip_entry, main_rgba):
        # 运行时 _MainTex 与 CardDef 肖像链不同源（材质级覆写帧型）→ 弃链落 mip0
        # （内容校验派发；语料 127 卡 0 命中，属未来写点变化的响亮降级位）
        mip_skip, mip_entry = "content-mismatch", None
    pmat = pnode["renderers"][0]["materials"][psub]
    if second_tex_name is None:
        second_name = (pmat["tex"].get("_SecondTex", {}).get("texture") or {}).get("file")
        second_name = Path(second_name).name
    else:
        second_name = second_tex_name
    second_rgba = np.asarray(get_tex(second_name), dtype=np.float64) / 255.0
    st = np.array(second_tint) if second_tint is not None \
        else np.array(pmat["colors"]["_SecondTint"])
    bi = float(blend_intensity) if blend_intensity is not None \
        else float(pmat["floats"]["_BlendIntensity"])
    verts = npz[f"{pkey}/verts"]
    uv0 = npz[f"{pkey}/uv0"]
    uv1 = npz[f"{pkey}/uv1"] if f"{pkey}/uv1" in npz.files else None
    uv1_src = "npz" if uv1 is not None else None
    if uv1 is None:
        sup = portrait_uv1((pnode.get("mesh_stats") or {}).get("name", ""))
        if sup is not None:
            assert sup.shape == uv0.shape, \
                f"uv1 补充提取形状不符：{sup.shape} vs uv0 {uv0.shape}"
            uv1, uv1_src = sup, "data-supplement"
    if uv1 is None:
        uv1, uv1_src = uv0, "uv0-fallback"   # 基线兼容位；并链帧型（ally/spell）不走此支
    # hp 帧 Repeat 语义：不落平铺数组（平铺致 mip 注册表按 shape 派发恒 mip0 直采），
    # Repeat 下沉采样器。UV_WRAP 旗**每渲无条件置位**（跨渲残留防护）：Repeat 是 hp 帧
    # **该帧材质**的采样语义，只能在本帧生效——旧实现只在 wrap_tile 支置 True、从无复位，
    # 同进程任一 hp 卡之后所有卡的肖像 UV 都被 `np.mod(u,1)`（实例：116510/116614 在
    # 「hp 在前」的 43 卡单进程与 chunk 进程池两上下文差 71 px；hp 卡=229/74786）。
    global UV_WRAP
    UV_WRAP = bool(wrap_tile)
    M = np.array(pnode["world"])
    vw = (M[:3, :3] @ verts.T).T + M[:3, 3]
    px, py = _raster.project_world(vw)
    depth = vw[:, 1]
    tris = npz[f"{pkey}/sub{psub}"]
    fn = _raster.PORTRAIT_FN or render_portrait_submesh
    fn(canvas, zbuf, depth, px, py, uv0, uv1, tris,
       main_rgba, second_rgba, st, bi, mip_entry=mip_entry)
    return {"file": (prt.get("file") and _P(prt["file"]).name) or "内存面 art.portrait",
            "second_tex": second_name,
            "second_tint": st.tolist(), "blend_intensity": bi,
            "uv1_source": uv1_src,
            "asset": asset,
            "mip": (None if mip_entry is None else
                    {"name": mip_entry["name"], "levels": len(mip_entry["chain"]),
                     "filter": mip_entry["filter"], "bias": mip_entry["bias"]}),
            "mip_skip": mip_skip}
