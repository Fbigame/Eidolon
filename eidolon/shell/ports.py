"""渲染端口协议（只放协议；适配器在组合层，Card 构造留在 core）。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from eidolon.contracts import RenderReport

from .spec import RenderSpec


@runtime_checkable
class RenderPort(Protocol):
    """``render`` 命令的输出端口。

    ``preflight`` 在打印计划 manifest 前运行（locale / cache / out_dir /
    依赖检查）：INPUT 类抛 ``SpecErrors``（壳捕获 → 2），ENVIRONMENT 类抛
    ``EnvironmentUnavailable``（entry → 3）；``render`` 接收已校验 spec，
    返回 :class:`~eidolon.contracts.RenderReport`。
    """

    def preflight(self, spec: RenderSpec) -> None:
        ...

    def render(self, spec: RenderSpec) -> RenderReport:
        ...
