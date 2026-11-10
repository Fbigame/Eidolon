"""context — 游戏安装身份的进程安装点（render 路径专用）。

进程不变量：**一个进程一个渲染身份**。``install()`` 首装生效；重装相同身份
=no-op；重装不同身份=raise（防同进程跨根渲染串缓存：进程级 memo 都以
「ctx 不变」为隐含前提）。同异判定 = ``GameContext.identity()`` 六元组
（root / cache_root / locale / version / route_mode / version_strict）；
``root_source`` / ``version_source`` 只是**来路账**，不参与——同根不同来路
（如探测与显式指根）= 同一渲染身份。

调用面（设计 §6.5）：只在 render 路径调用（``port.preflight`` 前一次；
worker initializer 各自一次）。``spec`` 路径**不**调用 ``install``——
provider 只构造 ctx，dbf 会话显式（``dbf.install_default``）。
``core/infra/card`` / ``supply.machine`` / ``resolve_asset_ref`` 等渲染链
经 ``current()`` 读身份；它们只在 render 路径被 import/调用。

纯内存安装点：无 I/O、不读 env、无默认值；未安装就读 = fail loud。
"""
from __future__ import annotations

from eidolon.contracts import GameContext

__all__ = ["install", "current", "installed"]

_installed: GameContext | None = None


def install(ctx: GameContext) -> GameContext:
    """安装进程渲染身份。首装生效；重装同身份 no-op（返回已装实例）；
    重装异身份 raise（进程单身份不变量）。"""
    global _installed
    if _installed is not None:
        if _installed.identity() != ctx.identity():
            raise RuntimeError(
                f"GameContext 重复安装且身份不同：已装 root={_installed.root} "
                f"locale={_installed.locale} cache_root={_installed.cache_root} "
                f"version={_installed.version}，"
                f"新值 root={ctx.root} locale={ctx.locale} "
                f"cache_root={ctx.cache_root} version={ctx.version}"
                "——一个进程只许一个渲染身份（跨根渲染请开新进程；"
                "进程级缓存以 ctx 不变为前提）")
        return _installed
    _installed = ctx
    return ctx


def current() -> GameContext:
    """读当前渲染身份。未安装=raise（库面禁自行解析 env/默认——契约 D 的机械保障）。"""
    if _installed is None:
        raise RuntimeError(
            "GameContext 未安装：render 路径必须先 "
            "`context.install(ctx)` 再触渲染/解析链；"
            "库面不读环境变量、无硬编码默认（契约 D）")
    return _installed


def installed() -> GameContext | None:
    """已装身份或 None（入口/诊断用；库面一律 current()）。"""
    return _installed
