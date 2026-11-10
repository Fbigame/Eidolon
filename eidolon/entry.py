"""组合根：装配 provider / port / logging，映射退出码。

顶层只 import 标准库、``eidolon.shell``、``eidolon.contracts``；真实 core
的 import 放在默认 factory 函数体内（core 接入轮加入）。入口不做字段
校验、不解析 TOML、不拼 manifest 格式。

退出码：input 2 / environment 3 / render 或 internal 1 / KeyboardInterrupt
130；BrokenPipe 静默退出 0。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Callable

from eidolon.contracts import CatalogProvider, EnvironmentUnavailable, Problem, ProblemKind
from eidolon.shell import cli
from eidolon.shell.errors import (
    EXIT_ENVIRONMENT,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_RENDER_FAILED,
    format_problem,
)
from eidolon.shell.paths import default_cache_root
from eidolon.shell.ports import RenderPort

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[], CatalogProvider]
PortFactory = Callable[[], RenderPort]


def main(
    argv=None,
    *,
    cwd: str | Path | None = None,
    provider_factory: ProviderFactory | None = None,
    port_factory: PortFactory | None = None,
) -> int:
    """组合根入口；factory 参数是 tests/entry 的注入点。

    factory 只在 ``load_input`` 成功后由 ``cli.run`` 调用：``--help``、
    ``spec --catalog``、坏 TOML 都不会触发 provider/port 构造。
    """
    # 先切 UTF-8：argparse 的 --help / usage 在 parse_args 内就会打印，
    # 晚于这一步会让 cp1252 控制台在中文帮助文本上抛 UnicodeEncodeError。
    _reconfigure_streams()
    args = cli.parse_args(argv)
    base = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()

    if provider_factory is None:
        provider_factory = _default_provider_factory(args, base)
    if port_factory is None:
        port_factory = _default_port_factory(args, base)

    handler, old_level = _install_logging(args)
    try:
        try:
            return cli.run(
                args,
                provider_factory=provider_factory,
                port_factory=port_factory,
                cwd=base,
            )
        except EnvironmentUnavailable as exc:
            print(format_problem(exc.problem), file=sys.stderr)
            return EXIT_ENVIRONMENT
        except BrokenPipeError:
            _silence_stdout()
            return EXIT_OK
        except KeyboardInterrupt:
            return EXIT_INTERRUPTED
        except Exception as exc:  # noqa: BLE001  未预期异常统一 internal
            problem = Problem(
                kind=ProblemKind.INTERNAL,
                code="internal",
                path="eidolon",
                message=f"未预期异常: {exc}",
            )
            print(format_problem(problem), file=sys.stderr)
            if getattr(args, "debug", False):
                traceback.print_exc()
            return EXIT_RENDER_FAILED
    finally:
        logger_ = logging.getLogger("eidolon")
        logger_.removeHandler(handler)
        logger_.setLevel(old_level)  # 多次调用 / --debug 后不留 DEBUG level


def _cache_root(args: argparse.Namespace, base: Path) -> Path:
    """``--cache-root`` 相对 ``base`` 解析；缺省用户缓存目录。

    provider 与渲染 port 共用本 helper（port 用 ``spec.game.cache_root``），
    不再各算一份。
    """
    raw = getattr(args, "cache_root", None)
    if raw is None:
        return default_cache_root()
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _default_provider_factory(args: argparse.Namespace, base: Path) -> ProviderFactory:
    """真实默认：core 的 ``DbfCatalogProvider``（lazy import，见设计 §9.2）。

    core 的 import 只在 factory 函数体内：``--help`` / ``spec --catalog`` /
    坏 TOML 不触发 factory，也就不载入 UnityPy；UnityPy 缺失时映射
    ``dependency_missing``（ENV 3）。
    """

    def factory() -> CatalogProvider:
        try:
            from eidolon.core.infra.provider import DbfCatalogProvider
        except ImportError as exc:
            raise EnvironmentUnavailable(Problem(
                ProblemKind.ENVIRONMENT, "dependency_missing", "env:unitypy",
                f"渲染依赖缺失: {exc}")) from exc
        cache_root = _cache_root(args, base)
        locale = getattr(args, "locale", None) or "zhcn"
        logger.debug("cache root: %s; locale: %s", cache_root, locale)
        return DbfCatalogProvider(cache_root=cache_root, locale=locale)

    return factory


def _default_port_factory(args: argparse.Namespace, base: Path) -> PortFactory:
    """真实默认端口：组合层 ``CoreRenderPort``（lazy import，见设计 §9.2）。

    adapters / core 的 import 只在 factory 函数体内（``--help`` / ``spec
    --catalog`` / 坏 TOML 不触发 factory）；pythonnet 装载失败映射
    ``dependency_missing``（ENV 3）。字体目录从 OS 计算点
    ``shell.paths.default_font_dirs()`` 注入（port 构造参数唯一来源）。
    """

    def factory() -> RenderPort:
        try:
            from eidolon.adapters import CoreRenderPort
        except ImportError as exc:
            raise EnvironmentUnavailable(Problem(
                ProblemKind.ENVIRONMENT, "dependency_missing", "env:pythonnet",
                f"渲染依赖缺失: {exc}")) from exc
        from eidolon.shell.paths import default_font_dirs

        font_dirs = default_font_dirs()
        logger.debug("font dirs: %s", font_dirs)
        return CoreRenderPort(font_dirs=font_dirs)

    return factory


def _install_logging(args: argparse.Namespace) -> tuple[logging.Handler, int]:
    """配置 ``eidolon`` logger（不碰 root）。

    返回 handler 与**旧 level**；调用方在 finally 里 removeHandler 并恢复
    level，保证同进程多次调用不累积、不残留 DEBUG。
    """
    if getattr(args, "debug", False):
        level = logging.DEBUG
    elif getattr(args, "verbose", False):
        level = logging.INFO
    else:
        level = logging.WARNING
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.setLevel(level)
    logger_ = logging.getLogger("eidolon")
    old_level = logger_.level
    logger_.setLevel(level)
    logger_.addHandler(handler)
    return handler, old_level


def _reconfigure_streams() -> None:
    """仅当 stdout/stderr 有 ``reconfigure`` 时重配 UTF-8；StringIO 跳过。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):  # 已关闭或不可重配
            pass


def _silence_stdout() -> None:
    """BrokenPipe 后把 fd 1 指向 devnull，避免解释器收尾时再次抛错。"""
    try:
        fileno = sys.stdout.fileno()
        devnull = os.open(os.devnull, os.O_WRONLY)
    except (OSError, ValueError, AttributeError):
        return
    os.dup2(devnull, fileno)
