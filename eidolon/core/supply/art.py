"""art — 原画域（per-card CardDef 链；SMOKE_SENTINELS 最敏感对所属域）。

locale 维度（2026-10-23 portrait-locale）：肖像纹理寻址按**客户端 locale** 走游戏同款
变体解析——`AssetLoader.GetRuntimeAssetVariant`（AssetLoader.cs）+ locale catalog
（`asset_manifest_<locale>.unity3d` 的 `asset_catalog_locale_<locale>.asset`，
baseGuid→变体 guid/bundle）。选择键=locale（GameContext.locale，契约 D 显式流入；
入口边缘解析，语料侧默认 zhcn 与参照语料同侧），**不是** card id/dbf——任何卡都走
同一条解析链：命中变体即消费变体，未命中落 base（引擎 enUS/无覆盖分支同义）。
修正案例=JAM_006（dbf 98390）肖像 `HS28-212_S` 的 zhCN 覆盖件（global 与 zhcn 内容差
mean 3.28/max 219）。
"""
from __future__ import annotations

from PIL import Image

from eidolon.core.infra.context import current   # 契约 D：locale=ctx 流入
from eidolon.core.infra.errors import EnvironmentUnavailable, GameAssetMissing
from eidolon.core.supply.machine import core, item
from eidolon.core.supply.textures import chain_for_name, mip_probe, note_texture_ref


def _portrait_tex(card_id: str) -> dict:
    """CardDef → 肖像 Texture2D（art.portrait / art.portrait_mip / art.portrait_source 单源）。

    [asset_resolver.py:311-350 逐字转写，去 atomic_save 落盘段；根对象无指针时
    走 CardDef 组件扫描（mc_extract_frame:316-331 同式）]。返回
    {"reader","bundle","path_id","tree","source"}——地址与 typetree 供按需 mip 链寻址
    （2026-10-20 portrait-mip-lod：链解码只在 chain_for_name 真被调用时发生）；
    source=资产来源账（locale/base/变体/guid，供 plan 记账与 locale 审计）。

    两次 resolve 都传 ctx.locale：引擎的 prefab 加载（DefLoader.GetCardDef →
    AssetLoader.GetOrInstantiateSharedPrefab）与肖像纹理加载（CardDef.GetPortraitTexture
    → AssetLoader.LoadAsset）走的是**同一个** GetRuntimeAssetVariant，locale 维度对
    两跳同时生效（2026-10-23 同构转写）。

    typed 边界（设计 §5.3）：cards_map 无 CardDef / CardDef 无 portrait 指针
    → ``GameAssetMissing``（一致性检查失败=形态漂移，仍走 assert）。"""
    res = core().res
    locale = current().locale
    ref = res.card_def_ref(card_id)
    if ref is None:
        raise GameAssetMissing(
            path=card_id,
            message=f"asset_missing_in_game: cards_map 无 CardDef {card_id}")
    r = res.resolve(ref, locale=locale)
    assert r.get("ok"), (card_id, r)
    bundle = r["resolved"]["bundle"]
    guid = r["resolved"]["guid"]
    reader, _ = res.container_get(bundle, guid)
    tt = reader.read_typetree()
    pref = tt.get("m_PortraitTexturePath")
    if not pref:
        for comp in tt.get("m_Component", []):
            cr, _cb = res.resolve_pptr(bundle, comp["component"], reader)
            if cr is None or cr.type.name != "MonoBehaviour":
                continue
            t2 = cr.read_typetree()
            if "m_PortraitTexturePath" in t2:
                pref = t2["m_PortraitTexturePath"]
                break
    if not pref:
        raise GameAssetMissing(
            path=card_id,
            message=f"asset_missing_in_game: CardDef {card_id} 无 portrait 指针"
                    "（m_PortraitTexturePath）")
    pr = res.resolve(pref, locale=locale)
    # 纹理位登记别名差容忍（registration/type 须过，name-consistency 仅为别名账；
    # 2026-10-06 案例 TB_Thunderdome_MechaJaraxxus：HERO_07b_H_Recrop vs _RECROPPED）
    pr_resolved = pr.get("resolved") or {}
    if not (pr_resolved.get("bundle") and pr_resolved.get("guid")):
        raise GameAssetMissing(
            path=pref,
            message=f"asset_missing_in_game: portrait ref 无解析结果 {pref}"
                    f"（card_id={card_id}）")
    pr_reader, _ = res.container_get(pr_resolved["bundle"], pr_resolved["guid"])
    assert pr_reader.type.name == "Texture2D", (card_id, pref, pr_reader.type.name)
    return {"reader": pr_reader, "bundle": pr["resolved"]["bundle"],
            "path_id": int(pr_reader.path_id), "tree": pr_reader.read_typetree(),
            "source": {
                "ref": pref,
                "locale": locale,
                "guid": pr["resolved"]["guid"],
                "bundle": pr["resolved"]["bundle"],
                "base_guid": pr["guid"],
                "base_bundle": pr["base"]["bundle"],
                "variant": pr.get("variant"),
                "carddef_ref": ref,
                "carddef_guid": guid,
                "carddef_bundle": bundle,
                "carddef_variant": r.get("variant"),
            }}


@item("art", "portrait")
def portrait(card_id: str) -> Image.Image:
    """原画：cards_map → CardDef → m_PortraitTexturePath → Texture2D.image（locale 变体）。

    消费点顺带登记 mip 地址（m_MipCount>1 时；链解码留给 portrait_mip——肖像层
    mip 开关关闭/无肖像帧时按需链零成本）。"""
    t = _portrait_tex(card_id)
    note_texture_ref(t["tree"], t["bundle"], t["path_id"])
    mip_probe(t["tree"], source=f"art.portrait {card_id}")   # 批24⑤
    return t["reader"].read().image


def _portrait_chain(card_id: str, name: str,
                    addr: tuple[str, int]) -> dict | None:
    """``chain_for_name`` 的卡上下文包装（B2）：链解码 typed 失败回填 card_id。

    链解码域外（``GameAssetFormatUnsupported``，BC7 肖像实证）与缺席
    （``GameAssetMissing``）都由 supply 层带资产身份（bundle::纹理名）抛出；
    本包装只把卡 id 补进 ``message``（类型/code/path/cause 原样保留）——
    Problem 不靠调用方反查 ref 才知道是哪张卡。非 typed 异常不接（原样穿出）。"""
    try:
        return chain_for_name(name, addr)
    except EnvironmentUnavailable as exc:
        p = exc.problem
        raise type(exc)(path=p.path,
                        message=f"{p.message}（card_id={card_id}）",
                        cause=p.cause) from exc


@item("art", "portrait_mip")
def portrait_mip(card_id: str) -> dict | None:
    """肖像纹理真 mip 链（按需）：m_MipCount>1 → {"name","chain","filter","bias"}。

    地址来自与 portrait() 同源的 CardDef 链（_portrait_tex，locale 变体同解析），链
    解码/进程 memo 在 textures.chain_for_name（真 mip 逐层 DXT 解码，box 不取）；
    typed 失败经 ``_portrait_chain`` 回填卡 id（B2）。
    地址显式传入（地址=资产身份）：变体件与 base 同名不同地址，手工链表只认原地址，
    不传会把 base 的 mip 链发给变体件（2026-10-23 防同名劫持）。
    None = 无 mip/无登记 → 调用方落 mip0 直采（逐位等同旧行为）。"""
    t = _portrait_tex(card_id)
    note_texture_ref(t["tree"], t["bundle"], int(t["path_id"]))
    return _portrait_chain(card_id, t["tree"].get("m_Name"),
                           (t["bundle"], int(t["path_id"])))


@item("art", "portrait_source")
def portrait_source(card_id: str) -> dict:
    """肖像资产来源账（盘面/记账用，不产图像）：ref/locale/变体/base 地址。

    消费位=plan.portrait["asset"]（渲染计划可追溯：哪一 locale 的哪一件被消费），
    与 portrait() 同链同 memo，不额外解码图像。"""
    return dict(_portrait_tex(card_id)["source"])


# ============================================================================
# 金肖像族（m_AlwaysRenderGoldenPortrait，2026-10-23 golden-portrait-anim）
# ============================================================================

_GOLDEN_FIELDS = ("m_PortraitTexturePath", "m_GoldenPortraitTexturePath",
                  "m_GoldenPortraitMaterialPath", "m_GoldenUberShaderAnimationPath",
                  "m_AlwaysRenderGoldenPortrait")


def _carddef_golden_fields(card_id: str) -> dict:
    """CardDef → 肖像族字段（含金像三件）。字段缺席即缺席键（不填默认值）。

    与 _portrait_tex 同一解析链（cards_map → CardDef，locale 变体同解析）；字段住在
    CardDef 的 MonoBehaviour 组件里（顶层无该键），故先查顶层再扫组件——与
    _portrait_tex 的 m_PortraitTexturePath 兜底同式。"""
    res = core().res
    ref = res.card_def_ref(card_id)
    assert ref, f"cards_map 无 {card_id}"
    r = res.resolve(ref, locale=current().locale)
    assert r.get("ok"), (card_id, r)
    bundle = r["resolved"]["bundle"]
    guid = r["resolved"]["guid"]
    reader, _ = res.container_get(bundle, guid)
    tt = reader.read_typetree()
    out = {k: tt[k] for k in _GOLDEN_FIELDS if k in tt}
    if not out:
        for comp in tt.get("m_Component", []):
            cr, _cb = res.resolve_pptr(bundle, comp["component"], reader)
            if cr is None or cr.type.name != "MonoBehaviour":
                continue
            t2 = cr.read_typetree()
            if any(k in t2 for k in _GOLDEN_FIELDS):
                out.update({k: t2[k] for k in _GOLDEN_FIELDS if k in t2})
                break
    return out


@item("art", "golden_portrait")
def golden_portrait(card_id: str) -> dict | None:
    """金肖像三件（材质/纹理/动画）——`m_AlwaysRenderGoldenPortrait=1` 才非 None。

    选择键=CardDef 字段组（零 dbf 特判）。依据=Actor.cs:Actor.UpdatePortraitMaterials
    （m_AlwaysRenderGoldenPortrait 覆写 premium=GOLDEN）+ CardDef.GetPortraitTexturePath
    / GetPortraitMaterialPath（GOLDEN 腿）。

    **纹理腿的 premium-1 回退**：m_GoldenPortraitTexturePath 为空时，引擎的
    GetPortraitTexturePath(premium) 递归取 premium-1，落回 m_PortraitTexturePath ——
    即「金材质 + 普通肖像纹理」。实证 HERO_08l（71723）：其肖像像素级动画极弱
    （12 相位扫描 MAE 0.45–0.60 全平），与「纹理未换、只换材质层」自洽。

    返回 None = 未开旗（绝大多数卡；语料 6 张 flag 卡里另 3 张无金资产同理落 None）。"""
    f = _carddef_golden_fields(card_id)
    if not f.get("m_AlwaysRenderGoldenPortrait"):
        return None
    mat_ref = f.get("m_GoldenPortraitMaterialPath") or ""
    if not mat_ref:
        return None
    tex_ref = f.get("m_GoldenPortraitTexturePath") or ""
    fallback = not tex_ref
    return {
        "always_golden": True,
        "material": mat_ref,
        "texture": tex_ref or (f.get("m_PortraitTexturePath") or ""),
        "animation": f.get("m_GoldenUberShaderAnimationPath") or "",
        "texture_fallback": fallback,
        "source": ("CardDef.m_AlwaysRenderGoldenPortrait=1 → "
                   "GetPortraitMaterialPath(GOLDEN) / GetPortraitTexturePath(GOLDEN)"
                   + ("（金纹理空→premium-1 回退普通肖像纹理）" if fallback else "")),
    }

