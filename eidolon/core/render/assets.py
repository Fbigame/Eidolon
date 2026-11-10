"""assets — 覆盖资产的静态规约（设计 §10.0/§10.1；纯 PIL，无 supply session）。

preflight 第 8 步（§7.7）用本模块的纯函数校验覆盖资产，**不得**调
``supply.overrides.asset``（它必须在 ``session()`` 内，preflight 没有
session）。``asset_dimensions`` 只做 INPUT（preflight 静态表拦截；v1 没有
render 期同尺寸分支——§12.1）。未知尺寸/非 2 幂/非表内形状：按表拒绝，
不做缩放、不做 letterbox。
"""
from __future__ import annotations

from pathlib import Path

from eidolon.contracts import Problem, ProblemKind, InputRejected

__all__ = ["ASSET_DIMENSIONS", "read_rgba", "validate_dimensions"]

ASSET_DIMENSIONS: dict[str, tuple[tuple[int, int], ...]] = {
    "portrait": ((512, 512),),
    "frame": ((1024, 1024),),
    "watermark": ((128, 128), (256, 256)),
}
"""三个覆盖座位的合法尺寸表（§10.1；表即全部合法尺寸）。

- ``portrait``：512×512 肖像纹理（运行时肖像槽复写；不是整张卡图）；
- ``frame``：1024×1024 类色图集（写点平面整体替换；不是 512×707 整帧 PNG）；
- ``watermark``：128×128 或 256×256 水印纹理（V-pass ``_SecondTex`` 源；
  两档都有实测——GangsIcon 128² / JAILIcon 256²；v1 不做数据轴同尺寸强制）。
"""


def _asset_rejected(code: str, path: Path, message: str) -> InputRejected:
    return InputRejected(Problem(
        ProblemKind.INPUT,
        code,
        str(path),
        f"{code}: {message}",
    ))


def read_rgba(path: Path) -> "Image":  # noqa: F821 —— 返回 PIL.Image.Image（延迟注解）
    """PIL 打开 → 格式门（只收真 PNG）→ RGBA。

    格式按 PIL 内容嗅探（``im.format``），与扩展名无关：非 PNG（如 JPEG
    字节存 ``.png`` 名）→ ``InputRejected(INPUT, "asset")``；解码/读盘失败
    同归 ``InputRejected(INPUT, "asset")``。不落盘、不缓存；preflight 只做
    「真 PNG 可解码为 RGBA」静态校验，不持有图像。
    """
    from PIL import Image

    try:
        with Image.open(path) as im:
            if im.format != "PNG":
                raise _asset_rejected(
                    "asset", path,
                    f"覆盖资产格式非 PNG（实测 {im.format!r}；按内容嗅探，"
                    "与扩展名无关）")
            return im.convert("RGBA")
    except InputRejected:
        raise
    except Exception as exc:  # noqa: BLE001 —— PIL 解码错误统一归 INPUT asset
        cause = f"{type(exc).__name__}: {exc}"
        raise _asset_rejected(
            "asset", path,
            f"覆盖资产无法解码为 RGBA（{cause}）") from exc


def validate_dimensions(path: Path, kind: str) -> tuple[int, int]:
    """覆盖资产尺寸静态校验（§10.1 表）→ 实际 (width, height)。

    ``kind`` 不在表内 → ``InputRejected``（调用方键级 bug）；读头/解码失败 →
    ``InputRejected(asset)``；尺寸不在表内 → ``InputRejected(asset_dimensions)``
    （message 点名座位与合法尺寸）。
    """
    allowed = ASSET_DIMENSIONS.get(kind)
    if allowed is None:
        raise _asset_rejected(
            "asset", path,
            f"未知资产座位 {kind!r}（只允许 {sorted(ASSET_DIMENSIONS)}）")
    from PIL import Image

    try:
        with Image.open(path) as im:
            # 与 read_rgba 同门：尺寸表只对真 PNG 有意义（JPEG 字节存 .png
            # 名不得因尺寸碰巧合法而通过；preflight 两步都会调，直接调用
            # validate_dimensions 的消费方也不能绕开格式门）。
            if im.format != "PNG":
                raise _asset_rejected(
                    "asset", path,
                    f"覆盖资产格式非 PNG（实测 {im.format!r}；按内容嗅探，"
                    "与扩展名无关）")
            size = (int(im.width), int(im.height))
    except InputRejected:
        raise
    except Exception as exc:  # noqa: BLE001 —— 同 read_rgba：解码失败归 asset
        cause = f"{type(exc).__name__}: {exc}"
        raise _asset_rejected(
            "asset", path,
            f"覆盖资产无法解码（{cause}）") from exc
    if size not in allowed:
        raise _asset_rejected(
            "asset_dimensions", path,
            f"{kind} 覆盖资产尺寸 {size[0]}x{size[1]} 不在合法尺寸表 "
            f"{list(allowed)} 内（不做缩放/letterbox；frame 覆盖=类色图集，"
            "不是整帧 PNG）")
    return size
