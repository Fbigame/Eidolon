"""core 的 typed 环境错误（与 ``Problem`` / ``EnvironmentUnavailable`` 同源）。

三类定型（抛出点分别落在 Phase 3 的资产解析、B2 的链解码格式域与渲染写盘）：

- ``GameAssetMissing``：游戏内资产解析「无对象/无 bundle/无字体」八边界
  （art.portrait / watermarks.texture / resolve_asset_ref.resolve / frames/kits
  系 / color.atlas / textures / text 字体链）抛出；code 固定
  ``asset_missing_in_game``。render 端口按类型映射，不再用 ``KeyError`` /
  ``RuntimeError`` 文本猜资产缺失。B4 增补：text_shim 的 locale 语料文件缺失
  （``Strings/<locale>`` 目录在场但无 ``GAMEPLAY*/GLOBAL*.txt``——preflight
  只查目录存在）也归本类（原裸 ``RuntimeError`` 会错归 render_failed 1）。
- ``GameAssetFormatUnsupported``（B2 收口）：游戏资产**在场**但形态在离线解码
  域外（如 BC7 肖像的 mip 链——游戏内可渲染，离线链解码器不可解）抛出；
  code 固定 ``asset_format_unsupported``。与 ``GameAssetMissing``（缺席）分立：
  hint 不指「扫描/修复」（那修不了格式域），指升级 Eidolon。
- ``WriteFailed``：只由渲染输出的 mkstemp / ``os.replace`` / 临时文件写失败抛出；
  code 固定 ``write_failed``。游戏资产读取的 ``PermissionError`` / ``OSError``
  **不**包装成它，按原类型判定。

三者都是 ``EnvironmentUnavailable``（退出码 3），``problem`` 是
:mod:`eidolon.contracts` 的 ``Problem``（kind=ENVIRONMENT）。
"""

from __future__ import annotations

from eidolon.contracts import Problem, ProblemKind, EnvironmentUnavailable

__all__ = ["GameAssetMissing", "GameAssetFormatUnsupported", "WriteFailed"]


class GameAssetMissing(EnvironmentUnavailable):
    """游戏资产缺失（ENV，code=``asset_missing_in_game``，退出码 3）。"""

    def __init__(self, *, path: str, message: str, cause: str = "") -> None:
        super().__init__(Problem(
            ProblemKind.ENVIRONMENT,
            "asset_missing_in_game",
            path,
            message,
            cause=cause,
        ))


class GameAssetFormatUnsupported(EnvironmentUnavailable):
    """游戏资产格式在离线解码域外（ENV，code=``asset_format_unsupported``，退出码 3）。

    B2 收口（原裸 ``ValueError`` 残留面）：资产在游戏内存在且可渲染，但其
    形态不在 Eidolon 离线解码域（首个实证=BC7 肖像 ``DMF_254t5`` 的 mip 链，
    fmt=25 不在链解码器 {10,12,3,4,13} 域——live 渲染本就失败，只从裸
    ValueError 升 typed，渲染语义不变）。``path`` 带资产身份
    （``bundle::纹理名``），``cause`` 带根因（格式/域外账）；卡 id 由
    ``supply.art.portrait_mip`` 的上下文包装回填进 ``message``。
    """

    def __init__(self, *, path: str, message: str, cause: str = "") -> None:
        super().__init__(Problem(
            ProblemKind.ENVIRONMENT,
            "asset_format_unsupported",
            path,
            message,
            cause=cause,
        ))


class WriteFailed(EnvironmentUnavailable):
    """渲染输出写盘失败（ENV，code=``write_failed``，退出码 3）。

    Phase 3 才有抛出点（``_atomic_render``）；类与 code 先定型。
    """

    def __init__(self, *, path: str, message: str, cause: str = "") -> None:
        super().__init__(Problem(
            ProblemKind.ENVIRONMENT,
            "write_failed",
            path,
            message,
            cause=cause,
        ))
