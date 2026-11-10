"""组合根：factory 注入、退出码映射、日志 handler 生命周期、pipe/help。

Phase 3c：render 命令走真实端口链（fake port 必须返回
``RenderReport``——cli 会写结果 manifest）；默认 port factory 是组合层
``CoreRenderPort``（lazy import，测试见 DefaultPortFactoryTests）。
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import logging
import tempfile
import unittest
from pathlib import Path

from eidolon.contracts import (
    CatalogBinding,
    CatalogIdentity,
    EnvironmentUnavailable,
    Problem,
    ProblemKind,
    RenderReport,
)
from eidolon.entry import main
from eidolon.shell.catalog import NullCatalog
from eidolon.shell.spec import RenderSpec


def run_main(args: list[str], **kwargs) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(args, **kwargs)
    return code, stdout.getvalue(), stderr.getvalue()


class _RecordingProvider:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[Problem | None] = []
        self.error = error

    def bind(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return CatalogBinding(
            catalog=NullCatalog(), game=None, identity=CatalogIdentity(kind="null")
        )


def _report_for(spec) -> RenderReport:
    """与 spec 卡数对齐的成功报告（结果 manifest 的条目数守卫要求）。"""
    from eidolon.contracts import RenderedCard

    return RenderReport(
        rendered=tuple(
            RenderedCard(ref=card.ref, path=card.out_path, sha256="0" * 64, elapsed_ms=1)
            for card in spec.cards
        )
    )


class _FakePort:
    def __init__(self, *, behavior=None, preflight_behavior=None) -> None:
        self.specs: list[RenderSpec] = []
        self._behavior = behavior
        self._preflight_behavior = preflight_behavior

    def preflight(self, spec) -> None:
        if self._preflight_behavior is not None:
            self._preflight_behavior(spec)
        return None

    def render(self, spec) -> RenderReport:
        self.specs.append(spec)
        if self._behavior is not None:
            outcome = self._behavior(spec)
            if outcome is not None:
                return outcome
        return _report_for(spec)


class _TmpCaseMixin(unittest.TestCase):
    """render 写结果 manifest 的测试需要独立 cwd（out_dir 默认 = cwd）。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)


class FactoryInjectionTests(_TmpCaseMixin, unittest.TestCase):
    def test_injected_provider_used_for_spec(self) -> None:
        provider = _RecordingProvider()
        code, out, err = run_main(["spec", "8"], provider_factory=lambda: provider)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(provider.calls), 1)
        self.assertIn('"source": "inline"', out)

    def test_provider_not_called_on_bad_toml(self) -> None:
        provider = _RecordingProvider()
        code, out, err = run_main(
            ["spec", "--toml", "does-not-exist.toml"],
            provider_factory=lambda: provider,
        )
        self.assertEqual(code, 2)
        self.assertEqual(provider.calls, [])

    def test_provider_not_called_with_catalog(self) -> None:
        from tests.support import CATALOG_JSON

        provider = _RecordingProvider()
        code, out, err = run_main(
            ["spec", "8", "--catalog", str(CATALOG_JSON)],
            provider_factory=lambda: provider,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(provider.calls, [])

    def test_injected_port_used_for_render(self) -> None:
        port = _FakePort()
        code, out, err = run_main(
            ["render", "8"],
            cwd=self.tmp,
            provider_factory=lambda: _RecordingProvider(),
            port_factory=lambda: port,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(port.specs), 1)
        self.assertIsInstance(port.specs[0], RenderSpec)
        self.assertEqual(len(port.specs[0].cards), 1)
        # 结果 manifest 已写盘（out_dir 默认 = cwd）。
        self.assertTrue((self.tmp / "manifest.json").is_file())


class DefaultPortFactoryTests(_TmpCaseMixin, unittest.TestCase):
    """默认 port factory（§9.2）：lazy import 组合层 CoreRenderPort。"""

    def test_factory_constructs_core_render_port_with_font_dirs(self) -> None:
        import argparse

        from eidolon.adapters import CoreRenderPort
        from eidolon.entry import _default_port_factory
        from eidolon.shell.paths import default_font_dirs

        args = argparse.Namespace(cache_root=None)
        factory = _default_port_factory(args, self.tmp)
        port = factory()
        self.assertIsInstance(port, CoreRenderPort)
        self.assertEqual(port.font_dirs, default_font_dirs())
        self.assertGreaterEqual(len(port.font_dirs), 1)
        self.assertTrue(all(isinstance(d, Path) for d in port.font_dirs))

    def test_factory_import_error_maps_dependency_missing(self) -> None:
        # adapters 装载失败（pythonnet 间接依赖缺失等）→ dependency_missing
        # env:pythonnet（ENV 3）——entry 统一映射，factory 只抛。
        import argparse
        from unittest import mock

        from eidolon.entry import _default_port_factory

        args = argparse.Namespace(cache_root=None)
        factory = _default_port_factory(args, self.tmp)
        with mock.patch.dict("sys.modules", {"eidolon.adapters": None}):
            with self.assertRaises(EnvironmentUnavailable) as caught:
                factory()
        problem = caught.exception.problem
        self.assertEqual(problem.code, "dependency_missing")
        self.assertEqual(problem.path, "env:pythonnet")
        self.assertEqual(problem.kind, ProblemKind.ENVIRONMENT)

    def test_portfactory_type_face(self) -> None:
        # PortFactory = Callable[[], RenderPort]；StubRenderPort 不再存在。
        import eidolon.entry as entry_module
        from eidolon.shell.ports import RenderPort

        self.assertTrue(hasattr(entry_module, "PortFactory"))
        self.assertFalse(hasattr(entry_module, "StubRenderPort"))
        # RenderPort 协议可在注入点做 runtime 判定（fake 满足形状）。
        self.assertTrue(isinstance(_FakePort(), RenderPort))


class ExitCodeMappingTests(_TmpCaseMixin, unittest.TestCase):
    def test_environment_unavailable_maps_3(self) -> None:
        problem = Problem(
            ProblemKind.ENVIRONMENT, "game_not_found", "D:/x/product.db", "找不到游戏"
        )
        provider = _RecordingProvider(error=EnvironmentUnavailable(problem))
        code, out, err = run_main(
            ["spec", "8"], provider_factory=lambda: provider
        )
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertIn("error[game_not_found]", err)
        self.assertIn("hint:", err)

    def test_unexpected_exception_maps_internal_1(self) -> None:
        provider = _RecordingProvider(error=RuntimeError("boom"))
        code, out, err = run_main(
            ["spec", "8"], provider_factory=lambda: provider
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("error[internal]", err)
        self.assertIn("boom", err)
        self.assertNotIn("Traceback", err)

    def test_debug_prints_traceback(self) -> None:
        provider = _RecordingProvider(error=RuntimeError("boom"))
        code, out, err = run_main(
            ["spec", "8", "--debug"], provider_factory=lambda: provider
        )
        self.assertEqual(code, 1)
        self.assertIn("Traceback", err)

    def test_keyboard_interrupt_maps_130(self) -> None:
        def interrupt(spec) -> None:
            raise KeyboardInterrupt()

        code, out, err = run_main(
            ["render", "8"],
            provider_factory=lambda: _RecordingProvider(),
            port_factory=lambda: _FakePort(behavior=interrupt),
        )
        self.assertEqual(code, 130)

    def test_broken_pipe_maps_0_silently(self) -> None:
        class _Broken:
            def write(self, text):
                raise BrokenPipeError()

            def flush(self):
                pass

        stderr = io.StringIO()
        with redirect_stdout(_Broken()), redirect_stderr(stderr):
            # Phase 1b：默认 provider 是真实 DbfCatalogProvider；此处注入
            # fake provider 保持断言不依赖游戏安装。
            code = main(["spec", "8"], provider_factory=lambda: _RecordingProvider())
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")

    def test_render_failure_report_maps_1(self) -> None:
        # Phase 3c：逐卡失败经 RenderReport 返回（不再有 stub 异常路径）；
        # RENDER 类 failure → 退出 1，结果 manifest 仍写。
        from eidolon.contracts import CardRef, RenderFailure

        def failing_render(spec):
            return RenderReport(
                failures=(
                    RenderFailure(
                        ref=CardRef("dbf", 8),
                        path=spec.cards[0].out_path,
                        problem=Problem(
                            ProblemKind.RENDER,
                            "render_failed",
                            str(spec.cards[0].out_path),
                            "render_failed: 覆盖无写点",
                        ),
                    ),
                )
            )

        code, out, err = run_main(
            ["render", "8"],
            cwd=self.tmp,
            provider_factory=lambda: _RecordingProvider(),
            port_factory=lambda: _FakePort(behavior=failing_render),
        )
        self.assertEqual(code, 1)
        self.assertIn('"cards"', out)  # 计划 manifest 先于失败打印
        result_manifest = (self.tmp / "manifest.json").read_text(encoding="utf-8")
        self.assertIn('"ok": false', result_manifest)

    def test_environment_failure_report_maps_3(self) -> None:
        from eidolon.contracts import CardRef, RenderFailure

        def env_failing_render(spec):
            return RenderReport(
                failures=(
                    RenderFailure(
                        ref=CardRef("dbf", 8),
                        path=spec.cards[0].out_path,
                        problem=Problem(
                            ProblemKind.ENVIRONMENT,
                            "write_failed",
                            str(spec.cards[0].out_path),
                            "write_failed: 磁盘不可写",
                        ),
                    ),
                )
            )

        code, out, err = run_main(
            ["render", "8"],
            cwd=self.tmp,
            provider_factory=lambda: _RecordingProvider(),
            port_factory=lambda: _FakePort(behavior=env_failing_render),
        )
        self.assertEqual(code, 3)

    def test_preflight_input_error_maps_2_with_empty_stdout(self) -> None:
        from eidolon.shell.errors import SpecErrors

        def bad_preflight(spec) -> None:
            errors = SpecErrors()
            errors.add("out_dir_invalid", "--outdir", "输出目录形状非法")
            raise errors

        port = _FakePort(preflight_behavior=bad_preflight)
        code, out, err = run_main(
            ["render", "8"],
            provider_factory=lambda: _RecordingProvider(),
            port_factory=lambda: port,
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("error[out_dir_invalid]", err)
        self.assertIn("hint:", err)

    def test_preflight_environment_error_maps_3_with_empty_stdout(self) -> None:
        problem = Problem(
            ProblemKind.ENVIRONMENT, "out_dir_unwritable", "out", "输出目录不可写"
        )

        def bad_preflight(spec) -> None:
            raise EnvironmentUnavailable(problem)

        port = _FakePort(preflight_behavior=bad_preflight)
        code, out, err = run_main(
            ["render", "8"],
            provider_factory=lambda: _RecordingProvider(),
            port_factory=lambda: port,
        )
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertIn("error[out_dir_unwritable]", err)

    def test_preflight_runs_before_manifest_print(self) -> None:
        # preflight 在打印计划 manifest 之前：失败时 stdout 恒空。
        seen: list[int] = []

        class _OrderingPort:
            def preflight(self, spec) -> None:
                seen.append(1)

            def render(self, spec) -> RenderReport:
                seen.append(2)
                return _report_for(spec)

        code, out, err = run_main(
            ["render", "8"],
            cwd=self.tmp,
            provider_factory=lambda: _RecordingProvider(),
            port_factory=lambda: _OrderingPort(),
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(seen, [1, 2])
        self.assertIn('"cards"', out)


class ParserBoundaryTests(unittest.TestCase):
    def test_help_exits_0(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as caught:
                main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("usage:", stdout.getvalue())

    def test_unknown_argument_systemexit_2_with_usage_problem(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                main(["spec", "--nope"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("error[usage]", stderr.getvalue())


class LoggingLifecycleTests(_TmpCaseMixin, unittest.TestCase):
    def test_handler_removed_after_main(self) -> None:
        logger = logging.getLogger("eidolon")
        before = list(logger.handlers)
        code, out, err = run_main(["spec", "bad-id"])
        self.assertEqual(code, 2)
        self.assertEqual(list(logger.handlers), before)

    def test_repeated_calls_do_not_accumulate_handlers(self) -> None:
        logger = logging.getLogger("eidolon")
        before = len(logger.handlers)
        # Phase 1b：注入 fake provider；默认 factory 会真实 bind（依赖游戏）。
        run_main(["spec", "8"], provider_factory=lambda: _RecordingProvider())
        run_main(["spec", "8"], provider_factory=lambda: _RecordingProvider())
        run_main(
            ["render", "8"],
            cwd=self.tmp,
            provider_factory=lambda: _RecordingProvider(),
            port_factory=lambda: _FakePort(),
        )
        self.assertEqual(len(logger.handlers), before)

    def test_debug_does_not_leave_level_debug(self) -> None:
        logger = logging.getLogger("eidolon")
        old = logger.level
        try:
            code, out, err = run_main(["spec", "bad-id", "--debug"])
            self.assertEqual(code, 2)
            self.assertEqual(logger.level, old)
        finally:
            logger.setLevel(old)  # 失败也不污染其他测试

    def test_handler_present_during_run(self) -> None:
        logger = logging.getLogger("eidolon")
        observed: list[int] = []

        class _Port:
            def preflight(self, spec) -> None:
                return None

            def render(self, spec) -> RenderReport:
                observed.append(len(logger.handlers))
                return RenderReport()

        run_main(
            ["render", "8"],
            cwd=self.tmp,
            provider_factory=lambda: _RecordingProvider(),
            port_factory=lambda: _Port(),
        )
        self.assertEqual(observed, [len(logging.getLogger("eidolon").handlers) + 1])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
