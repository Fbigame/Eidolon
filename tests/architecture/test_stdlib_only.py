"""守卫：shell 实现与 contracts 只使用 Python 标准库。

覆盖 ``eidolon/shell/**/*.py``（递归）+ ``eidolon/contracts.py``；文件数
下限防止守卫被搬空后静默通过。组合层（entry / adapters）与 core 允许
第三方依赖，不在本守卫范围。住 ``tests/architecture/``，不随目录搬迁移动。
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

from tests.support import ROOT

PACKAGE_DIR = ROOT / "eidolon"
# 取值日期 2026-11-09：shell 10 个 .py + contracts.py = 实测 11 个
# （旧值 10 是搬迁前骨架面）。下限防止守卫被搬空后静默通过。
MIN_FILES = 11


def _covered_files() -> list[Path]:
    covered = sorted((PACKAGE_DIR / "shell").rglob("*.py"))
    covered.append(PACKAGE_DIR / "contracts.py")
    return covered


def _import_roots(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                roots.append("eidolon")  # 相对 import 还原后根仍是本包
            elif node.module:
                roots.append(node.module.split(".")[0])
    return roots


class StdlibOnlyTests(unittest.TestCase):
    def test_imports_are_stdlib_or_local(self) -> None:
        allowed = set(sys.stdlib_module_names) | {"eidolon"}
        covered = _covered_files()
        self.assertGreaterEqual(
            len(covered), MIN_FILES, "stdlib 守卫覆盖的文件数低于下限"
        )
        offenders: list[str] = []
        for path in covered:
            for root in _import_roots(path):
                if root not in allowed:
                    offenders.append(f"{path.relative_to(ROOT)}:{root}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
