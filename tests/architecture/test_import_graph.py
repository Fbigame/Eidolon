"""守卫：依赖方向。

- ``eidolon/shell/`` 不得出现 ``eidolon.core``；import 只允许标准库 +
  ``eidolon.contracts`` / ``eidolon.version`` / ``eidolon.shell.*``。
- ``eidolon/core/``（存在时）不得 import ``eidolon.shell``。
- ``eidolon/__init__.py`` 不 import ``eidolon.core``。
- 相对 import 还原成绝对名后按上述规则判定；``from X import y`` 的
  alias 展开（``from eidolon import core`` → ``eidolon.core``，审计
  P1-7：只记 module 名可被顶层别名绕过）。
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

from tests.support import ROOT

PACKAGE_DIR = ROOT / "eidolon"
SHELL_DIR = PACKAGE_DIR / "shell"
CORE_DIR = PACKAGE_DIR / "core"
TESTS_DIR = ROOT / "tests"

_SHELL_ALLOWED_SUBMODULES = frozenset({"contracts", "version", "shell"})


def _package_of(path: Path) -> str:
    parts = path.relative_to(ROOT).with_suffix("").parts[:-1]
    return ".".join(parts)


def _resolve(module: str | None, level: int, package: str) -> str:
    """相对 import 还原成绝对名（level=1 即当前包）。"""
    if level == 0:
        return module or ""
    parts = package.split(".") if package else []
    base = parts[: len(parts) - (level - 1)] if level > 0 else parts
    if module:
        return ".".join(base + [module]) if base else module
    return ".".join(base)


def _imported_names(path: Path) -> list[str]:
    """import 的绝对名；``from X import y`` 同时记录 ``X`` 与 ``X.y``。

    审计 P1-7：只记 module 名时 ``from eidolon import core``（module=
    "eidolon"、alias.name="core"）记录的是 ``eidolon``，core 守卫可被绕过
    ——alias 必须展开成 ``eidolon.core`` 再判定。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_of(path)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve(node.module, node.level, package)
            if base:
                names.append(base)
            for alias in node.names:
                if alias.name != "*" and base:
                    names.append(f"{base}.{alias.name}")
    return names


def _is_stdlib(name: str) -> bool:
    return name.split(".")[0] in sys.stdlib_module_names


class ImportGraphTests(unittest.TestCase):
    def test_shell_imports_are_scoped(self) -> None:
        covered = sorted(SHELL_DIR.rglob("*.py"))
        self.assertGreaterEqual(len(covered), 8, "shell 文件数低于下限")
        offenders: list[str] = []
        for path in covered:
            for name in _imported_names(path):
                if _is_stdlib(name):
                    continue
                parts = name.split(".")
                if parts[0] == "eidolon" and (
                    len(parts) == 1 or parts[1] in _SHELL_ALLOWED_SUBMODULES
                ):
                    continue
                offenders.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual(offenders, [])

    def test_shell_never_imports_core(self) -> None:
        offenders: list[str] = []
        for path in sorted(SHELL_DIR.rglob("*.py")):
            for name in _imported_names(path):
                if name == "eidolon.core" or name.startswith("eidolon.core."):
                    offenders.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual(offenders, [])

    def test_core_never_imports_shell(self) -> None:
        if not CORE_DIR.is_dir():
            return  # core 尚未建立；建仓后守卫自动生效
        offenders: list[str] = []
        for path in sorted(CORE_DIR.rglob("*.py")):
            for name in _imported_names(path):
                if name == "eidolon.shell" or name.startswith("eidolon.shell."):
                    offenders.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual(offenders, [])

    def test_package_init_never_imports_core(self) -> None:
        names = _imported_names(PACKAGE_DIR / "__init__.py")
        offenders = [
            name
            for name in names
            if name == "eidolon.core" or name.startswith("eidolon.core.")
        ]
        self.assertEqual(offenders, [])

    def test_from_import_alias_expansion_canary(self) -> None:
        # 审计 P1-7 回归：``from eidolon import core`` 必须展开成
        # eidolon.core（旧扫描只记 module 名 ``eidolon``，core 混层可借
        # 顶层别名绕过）。canary 只被 AST 解析、永不执行。
        canary = TESTS_DIR / "_alias_canary.py"
        canary.write_text(
            "from eidolon import core\n"
            "from eidolon.shell import cli as c\n",
            encoding="utf-8",
        )
        self.addCleanup(canary.unlink)
        names = _imported_names(canary)
        self.assertIn("eidolon.core", names)
        self.assertIn("eidolon.shell.cli", names)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
