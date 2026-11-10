"""守卫：Phase 2b 分层约束（§4.2 供给禁 paint + render/text 的 import 面）。

- ``core/supply/**``（含 frames）**任何位置**（顶层或函数体）不得 import
  ``eidolon.core.render``——供给禁 paint（§4.2；badges/btf/supplements 等经
  函数体惰性 import infra，同样在扫描面内）；
- ``core/recipes/**`` 同禁（recipes 是 supply 的别名转发面，实现时若别名导致
  循环保留直接 import，但不得反向依赖 render）；
- ``core/render/text/{ft_unhinted,glyph_supply,text_atlas}.py`` 允许 import
  ``infra`` / ``supply`` / ``recipes`` 与 ``core.render`` 的 ``_provenance`` /
  ``text`` 子树（本包内件），**不得** import ``core.render`` 的 game / engine /
  scenes / batch / params 等渲染主链件（Phase 3 才落地；text 层是它们的地基，
  方向不可倒置）。
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests.support import ROOT

CORE = ROOT / "eidolon" / "core"


def _import_names(path: Path) -> list[str]:
    """文件内**全部** import 名（含函数体惰性 import；§4.2 不分层级）。

    ``from X import y`` 同时记录 ``X`` 与 ``X.y``。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def resolve(node: ast.ImportFrom) -> str:
        if node.level == 0:
            return node.module or ""
        return ""  # 相对 import：本仓 core 内不用（出现即守卫对象外的形状漂移）

    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve(node)
            for alias in node.names:
                if alias.name != "*":
                    names.append(f"{base}.{alias.name}" if base else alias.name)
            if base:
                names.append(base)
    return names


def _under(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def _files(rel: str) -> list[Path]:
    files = sorted((CORE / rel).rglob("*.py"))
    assert files, f"{rel} 不存在"
    return files


class SupplyNoPaintTests(unittest.TestCase):
    def test_supply_never_imports_render(self) -> None:
        offenders: list[str] = []
        for path in _files("supply"):
            for name in _import_names(path):
                if _under(name, "eidolon.core.render"):
                    offenders.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual(offenders, [])

    def test_recipes_never_import_render(self) -> None:
        offenders: list[str] = []
        for path in _files("recipes"):
            for name in _import_names(path):
                if _under(name, "eidolon.core.render"):
                    offenders.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual(offenders, [])


class RenderTextImportFaceTests(unittest.TestCase):
    TEXT_FILES = (
        "render/text/ft_unhinted.py",
        "render/text/glyph_supply.py",
        "render/text/text_atlas.py",
    )

    def test_text_files_import_face_is_bounded(self) -> None:
        """render/text 三件不得 import 渲染主链（game/engine/scenes/batch/params）。

        允许面 = infra / supply / recipes / render._provenance / render.text.*。"""
        offenders: list[str] = []
        for rel in self.TEXT_FILES:
            path = CORE / rel
            for name in _import_names(path):
                if not _under(name, "eidolon.core.render"):
                    continue
                if (_under(name, "eidolon.core.render._provenance")
                        or _under(name, "eidolon.core.render.text")):
                    continue
                offenders.append(f"{rel}: {name}")
        self.assertEqual(offenders, [])

    def test_text_files_exist(self) -> None:
        for rel in self.TEXT_FILES:
            self.assertTrue((CORE / rel).is_file(), f"缺 {rel}")


if __name__ == "__main__":
    unittest.main()
