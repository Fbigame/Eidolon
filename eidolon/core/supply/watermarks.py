"""watermarks — 水印域：卡集/迷你集/core 年标水印纹理（ref 链寻址）。

职责切分：**哪张水印**（四级裁决：卡级 override→活跃 set 纹理→core 年标→None）归
infra Card.watermark_ref（decomp 锚随其 docstring）；本域只供纹理字节——ref →
resolve → Texture2D.image（既档 66 张 data/frame_assets/watermarks/ 为对拍 oracle，
随域收编退役为参照语料）。
"""
from __future__ import annotations

from PIL import Image

from eidolon.core.infra.errors import GameAssetMissing
from eidolon.core.supply.machine import core, item


@item("watermarks", "texture")
def texture(ref: str) -> Image.Image:
    """水印纹理（卡集水印/迷你集图标/core 年标皆同形）。

    [旧 get_tex 供给树位/data 既档的链寻址替代；别名差容忍断言随收编带入]
    typed 边界（设计 §5.3）：ref 无解析结果/无对象抛 ``GameAssetMissing``
    （本域显式 if + resolve/container_get 同型；类型不符=形态漂移仍 assert）。"""
    r = core().res
    res = r.resolve(ref)
    resolved = res.get("resolved") or {}
    if not (resolved.get("bundle") and resolved.get("guid")):
        raise GameAssetMissing(
            path=ref,
            message=f"asset_missing_in_game: watermark ref 无解析结果 {ref}")
    got, _ = r.container_get(resolved["bundle"], resolved["guid"])
    assert got.type.name == "Texture2D", res["resolved"]
    return got.read().image


@item("watermarks", "named_texture")
def named_texture(ref: str) -> tuple[str, Image.Image]:
    """水印纹理+对象实名（②壳物化命名={m_Name}_{guid8}.png 实名制，旧落盘同形）。

    typed 边界（设计 §5.3）：ref 无解析结果/无对象抛 ``GameAssetMissing``
    （texture 同款；类型不符=形态漂移仍 assert）。"""
    r = core().res
    res = r.resolve(ref)
    resolved = res.get("resolved") or {}
    if not (resolved.get("bundle") and resolved.get("guid")):
        raise GameAssetMissing(
            path=ref,
            message=f"asset_missing_in_game: watermark ref 无解析结果 {ref}")
    got, _ = r.container_get(resolved["bundle"], resolved["guid"])
    assert got.type.name == "Texture2D", res["resolved"]
    t = got.read()
    return t.m_Name, t.image
