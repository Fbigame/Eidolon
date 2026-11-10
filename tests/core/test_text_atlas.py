"""text_atlas — §4.3 精确切口守卫（默认 discover 收集；不 import UnityPy / 不触 CLR）。

设计 §4.3：``render/text/text_atlas.py`` 只删 ``load_atlas`` / ``atlas_glyph`` 与旧的
容器取数函数 ``find_data``（快照回归锚依赖 fonts 语料，产品无此素材）；
保留 ``glyph_quad`` / ``render_atlas_text`` / ``render_rt_content`` /
``_render_atlas_text_center`` / ``_taps`` 等现役函数（Phase 3 的 ``uber_text`` 会调用）。

断言两面：
  * 模块可 import（numpy/PIL/scipy 链，无 UnityPy）；
  * 文件源码无 ``find_data`` / ``load_atlas`` / ``atlas_glyph`` 引用（文本断言，
    docstring 提及也算引用——§4.3「文件内无引用」口径）。
"""

from __future__ import annotations

import unittest

from tests.support import ROOT

MODULE_FILE = ROOT / "eidolon" / "core" / "render" / "text" / "text_atlas.py"

KEPT_SYMBOLS = (
    "glyph_quad",
    "render_atlas_text",
    "render_rt_content",
    "_render_atlas_text_center",
    "_taps",
    "_vs_f32_quad",
    "_composite",
)

BANNED_REFS = ("find_data", "load_atlas", "atlas_glyph")


class TextAtlasCutTests(unittest.TestCase):
    def test_module_imports_without_unitypy(self) -> None:
        import sys

        import eidolon.core.render.text.text_atlas as ta  # noqa: F401

        self.assertNotIn("UnityPy", sys.modules)

    def test_kept_functions_present(self) -> None:
        import eidolon.core.render.text.text_atlas as ta

        for name in KEPT_SYMBOLS:
            self.assertTrue(callable(getattr(ta, name, None)), f"缺现役函数 {name}")

    def test_taps_shape_is_engine_order(self) -> None:
        import eidolon.core.render.text.text_atlas as ta

        taps = ta._taps(2.0)
        self.assertEqual(len(taps), 8)
        # 引擎常量序：4 轴向在前（±r），4 对角在后（±0.6r）；不可换序。
        self.assertEqual(taps[0], (2.0, 0.0))
        self.assertEqual(taps[3], (0.0, -2.0))
        self.assertEqual(taps[4], (1.2, 1.2))

    def test_source_has_no_snapshot_path_references(self) -> None:
        text = MODULE_FILE.read_text(encoding="utf-8")
        offenders = [ref for ref in BANNED_REFS if ref in text]
        self.assertEqual(offenders, [], f"text_atlas 残留快照路径引用：{offenders}")

    def test_source_has_no_repo_or_unused_imports(self) -> None:
        text = MODULE_FILE.read_text(encoding="utf-8")
        # find_data 的来源与快照解码的 json/Path 都随切口退役（AST 层面确认不再 import）。
        import ast

        tree = ast.parse(text)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertNotIn("json", imported)
        self.assertNotIn("eidolon.core.infra", imported)


if __name__ == "__main__":
    unittest.main()
