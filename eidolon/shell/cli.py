"""壳命令行：``parse_args`` + ``run``（编排由组合根 eidolon.entry.main 做）。

两阶段输入在此汇合：

* ``spec``   load_input → bind（provider 或 --catalog 直读）→ compile_spec
  → 打印 manifest，退出码 0；
* ``render`` 同上，然后构造 port（只在输入合法后）→ preflight → 打印计划
  manifest → port.render → 写结果 manifest → 退出码 0/1/3。

run 捕获 ``SpecErrors`` / ``CatalogError`` / ``InputRejected`` → stderr /
2；``EnvironmentUnavailable``→3 与未预期→internal(1) 由 entry 映射。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable, Sequence

from eidolon.contracts import (
    CatalogProvider,
    EnvironmentUnavailable,
    InputRejected,
    Problem,
    ProblemKind,
)

from .catalog import CatalogError, bind_json_catalog
from .errors import (
    EXIT_INVALID_INPUT,
    EXIT_OK,
    MAX_ERRORS,
    SpecErrors,
    format_problem,
)
from .input import load_input
from .manifest import manifest_json, report_exit_code, write_result_manifest
from .spec import compile_spec

ProviderFactory = Callable[[], CatalogProvider]
PortFactory = Callable[[], object]


class _UsageErrorParser(argparse.ArgumentParser):
    """usage 错误格式化为 ``Problem(usage)`` 后 ``SystemExit(2)``。

    ``--help`` 仍走 argparse 原生 ``SystemExit(0)``。
    """

    def error(self, message: str) -> None:
        problem = Problem(
            kind=ProblemKind.INPUT, code="usage", path="argv", message=message
        )
        print(format_problem(problem), file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = _UsageErrorParser(
        prog="eidolon",
        description="Eidolon 外壳：归一化并校验卡牌渲染输入，调用渲染端口输出 PNG。",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="{spec,render}",
        parser_class=_UsageErrorParser,
    )

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "ids",
            nargs="*",
            metavar="id",
            help="位置 id（纯数字 = dbf id，其余 = card id）；与 --toml 互斥",
        )
        sub.add_argument(
            "--toml",
            metavar="FILE",
            default=None,
            help="批量输入 TOML 文件；与位置 id 互斥",
        )
        sub.add_argument(
            "--outdir",
            metavar="DIR",
            default=None,
            help="输出目录（仅命令行模式；默认 .）",
        )
        sub.add_argument(
            "--jobs",
            metavar="N",
            type=int,
            default=None,
            help="并行工作数（仅命令行模式；默认 1）",
        )
        sub.add_argument(
            "--hero-style",
            action="store_true",
            default=None,
            help="全局开关：HERO 卡使用 PLAY 形态（仅命令行模式）",
        )
        sub.add_argument(
            "--bg-style",
            action="store_true",
            default=None,
            help="全局开关：非 HERO 卡使用酒馆战棋装饰（仅命令行模式）",
        )
        sub.add_argument(
            "--antialias",
            action="store_true",
            default=None,
            help="开启 4x 覆盖超采样；缺省 false（仅命令行模式）",
        )
        sub.add_argument(
            "--catalog",
            metavar="PATH",
            default=None,
            help="JSON catalog；仅 spec 可用（与 --game / TOML game_dir 互斥）",
        )
        sub.add_argument(
            "--game",
            metavar="DIR",
            default=None,
            help="游戏安装根（含 Hearthstone.exe）；缺省时由 provider 探测",
        )
        sub.add_argument(
            "--locale",
            metavar="LOC",
            default=None,
            help="游戏数据语言（默认 zhcn）",
        )
        sub.add_argument(
            "--cache-root",
            dest="cache_root",
            metavar="DIR",
            default=None,
            help="route/supply 缓存根（默认用户缓存目录；相对 cwd）",
        )
        sub.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="INFO 日志",
        )
        sub.add_argument(
            "--debug",
            action="store_true",
            help="DEBUG 日志；未预期异常打印完整 traceback",
        )

    add_common(
        subparsers.add_parser(
            "spec", help="解析并校验输入，输出 manifest（不渲染）"
        )
    )
    add_common(
        subparsers.add_parser(
            "render",
            help="解析并校验输入，调用渲染端口出图并写结果 manifest",
        )
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    provider_factory: ProviderFactory,
    port_factory: PortFactory,
    cwd: str | Path,
) -> int:
    """两阶段编排：load_input → bind → compile_spec → 输出 / 渲染。"""
    try:
        return _run(
            args,
            provider_factory=provider_factory,
            port_factory=port_factory,
            cwd=cwd,
        )
    except InputRejected as exc:
        # core 输入类错误（防 core 直调路径；spec / 产品 render 路径理论上
        # 不会到这里——preflight 已把 INPUT 类收进 SpecErrors，逐卡期归
        # RenderFailure）：按输入错误处理，打印其 Problem、退出 2。
        print(format_problem(exc.problem), file=sys.stderr)
        return EXIT_INVALID_INPUT


def _run(
    args: argparse.Namespace,
    *,
    provider_factory: ProviderFactory,
    port_factory: PortFactory,
    cwd: str | Path,
) -> int:
    try:
        draft = load_input(args, cwd)
    except SpecErrors as exc:
        _print_errors(exc)
        return EXIT_INVALID_INPUT

    try:
        if draft.catalog_path is not None:
            binding = bind_json_catalog(draft.catalog_path)
        else:
            binding = provider_factory().bind(draft.game)
    except CatalogError as exc:
        problem = Problem(
            kind=ProblemKind.INPUT,
            code="catalog_invalid",
            path=str(draft.catalog_path or "<root>"),
            message=str(exc),
        )
        print(format_problem(problem), file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        spec = compile_spec(draft, binding)
    except SpecErrors as exc:
        _print_errors(exc)
        return EXIT_INVALID_INPUT

    port = None
    if draft.command == "render":
        # port 只在输入合法后才构造；--catalog 已在 load_input 拒绝。
        # preflight 在打印计划 manifest 前：INPUT 类 → 2（stdout 空），
        # ENVIRONMENT 类抛 EnvironmentUnavailable 由 entry 映射 3。
        port = port_factory()
        try:
            port.preflight(spec)
        except SpecErrors as exc:
            _print_errors(exc)
            return EXIT_INVALID_INPUT

    print(manifest_json(spec))

    if port is not None:
        report = port.render(spec)
        try:
            write_result_manifest(spec, report)
        except EnvironmentUnavailable:
            raise  # manifest 写盘失败（write_failed，ENV 3）；已渲染 PNG 保留
        return report_exit_code(report)
    return EXIT_OK


def _print_errors(errors: SpecErrors) -> None:
    for error in errors.errors:
        print(error.format(), file=sys.stderr)
    if errors.truncated:
        print(f"... 错误过多，仅显示前 {MAX_ERRORS} 条", file=sys.stderr)
