"""entry 默认 provider factory：DbfCatalogProvider 构造面 + ImportError 映射。

本文件只测 factory 的构造（lazy import + cache_root / locale），不调
``bind``——默认测试不得依赖本机游戏安装。载入 UnityPy（经 lazy import）
在 tests/entry 允许。
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest import mock

from eidolon.contracts import EnvironmentUnavailable, Problem, ProblemKind
from eidolon.entry import _cache_root, _default_provider_factory, main
from eidolon.shell.paths import default_cache_root


def _args(**kw) -> SimpleNamespace:
    base = dict(cache_root=None, locale=None)
    base.update(kw)
    return SimpleNamespace(**base)


class CacheRootHelperTests(unittest.TestCase):
    def test_none_falls_back_to_default_cache_root(self) -> None:
        base = Path("D:/base").resolve()
        self.assertEqual(_cache_root(_args(), base), default_cache_root())

    def test_relative_resolved_against_base(self) -> None:
        base = Path("D:/base").resolve()
        got = _cache_root(_args(cache_root="cache/sub"), base)
        self.assertEqual(got, (base / "cache/sub").resolve())
        self.assertTrue(got.is_absolute())

    def test_absolute_kept(self) -> None:
        absolute = Path("D:/elsewhere/cache").resolve()
        self.assertEqual(
            _cache_root(_args(cache_root=str(absolute)), Path("D:/base")), absolute
        )


class DefaultProviderFactoryTests(unittest.TestCase):
    def test_factory_builds_dbf_provider_with_defaults(self) -> None:
        from eidolon.core.infra.provider import DbfCatalogProvider

        factory = _default_provider_factory(_args(), Path("D:/base").resolve())
        provider = factory()
        self.assertIsInstance(provider, DbfCatalogProvider)
        self.assertEqual(provider.cache_root, default_cache_root())
        self.assertEqual(provider.locale, "zhcn")

    def test_factory_relative_cache_root_resolved_against_base(self) -> None:
        base = Path("D:/base").resolve()
        factory = _default_provider_factory(_args(cache_root="cache"), base)
        provider = factory()
        self.assertEqual(provider.cache_root, (base / "cache").resolve())

    def test_factory_locale_passthrough(self) -> None:
        factory = _default_provider_factory(_args(locale="enus"), Path.cwd())
        self.assertEqual(factory().locale, "enus")

    def test_factory_import_error_maps_dependency_missing(self) -> None:
        # sys.modules 注入缺 DbfCatalogProvider 的假模块 → from-import 抛
        # ImportError → factory 必须转 EnvironmentUnavailable(dependency_missing)。
        fake = ModuleType("eidolon.core.infra.provider")
        factory = _default_provider_factory(_args(), Path.cwd())
        with mock.patch.dict(sys.modules, {"eidolon.core.infra.provider": fake}):
            with self.assertRaises(EnvironmentUnavailable) as caught:
                factory()
        problem = caught.exception.problem
        self.assertEqual(problem.code, "dependency_missing")
        self.assertEqual(problem.path, "env:unitypy")

    def test_main_maps_factory_environment_error_to_3(self) -> None:
        # factory 抛 EnvironmentUnavailable 与 bind 抛同路映射：exit 3。
        problem = Problem(
            ProblemKind.ENVIRONMENT,
            "dependency_missing",
            "env:unitypy",
            "渲染依赖缺失: boom",
        )

        def bad_factory():
            raise EnvironmentUnavailable(problem)

        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["spec", "8"], provider_factory=bad_factory)
        self.assertEqual(code, 3)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("error[dependency_missing]", stderr.getvalue())
        self.assertIn("env:unitypy", stderr.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
