"""render 移植缝（Phase 3a）——轻 import 面 + §7.5 消费点文本守卫（默认 discover 收集；不 import UnityPy / 不触 CLR）。

断言面（core-integration §6.5 / §7.5 / §16.1）：

  * ``core/render/params.py`` 可轻 import；``PRODUCT_SESSION_T == 0.0``（产品
    tzero，§7.6）且 ``DEFAULT_SESSION_T == 0.15285``（legacy 保留值）；
  * ``core/render/__init__.py`` 保持轻——AST 断言无任何 import 语句（§6.5：CLR-at-import
    模块只能 install 后 import，包顶层不得拖入）；
  * 轻面 import 链后 ``sys.modules`` 无 UnityPy / clr / System 模块；
  * §7.5 三个 ``races_text_override`` 消费点的文本级守卫（compiler 两处 +
    components 板选择一处；真行为归 integration 冒烟）；
  * ``canonical_cfg()`` 逐字段文本守卫（§7.6：按 components 函数体对拍，防静默改字段）；
  * §4.3 不搬清单防回归：``eidolon/core/render/`` 全域无 ``find_data`` /
    ``load_atlas`` / ``atlas_glyph`` 引用。
"""

from __future__ import annotations

import ast
import sys
import unittest

from tests.support import ROOT

RENDER_DIR = ROOT / "eidolon" / "core" / "render"
PARAMS_FILE = RENDER_DIR / "params.py"
RENDER_INIT_FILE = RENDER_DIR / "__init__.py"
COMPILER_FILE = RENDER_DIR / "game" / "compiler.py"
COMPONENTS_FILE = RENDER_DIR / "game" / "actor" / "components.py"

BANNED_ATLAS_REFS = ("find_data", "load_atlas", "atlas_glyph")


def _read(path) -> str:
    return path.read_text(encoding="utf-8")


class ParamsConstantsTests(unittest.TestCase):
    def test_params_imports_light_with_product_tzero(self) -> None:
        import eidolon.core.render.params as params

        self.assertEqual(params.PRODUCT_SESSION_T, 0.0)
        self.assertEqual(params.DEFAULT_SESSION_T, 0.15285)

    def test_product_tzero_docstates_legacy_split(self) -> None:
        text = _read(PARAMS_FILE)
        self.assertIn("PRODUCT_SESSION_T", text)
        self.assertIn("DEFAULT_SESSION_T", text)
        # §7.6：产品固定相位 tzero；DEFAULT_SESSION_T 只给 legacy t=null 行
        self.assertIn("legacy", text)


class RenderInitLightTests(unittest.TestCase):
    def test_render_init_has_no_imports(self) -> None:
        tree = ast.parse(_read(RENDER_INIT_FILE), filename=str(RENDER_INIT_FILE))
        imports = [n for n in ast.walk(tree)
                   if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertEqual(imports, [],
                         "core/render/__init__.py 必须零 import（轻面纪律 §6.5）")

    def test_render_init_import_leaves_sysmodules_clean(self) -> None:
        import eidolon.core.render  # noqa: F401

        bad = sorted(m for m in sys.modules
                     if m.split(".")[0] in ("UnityPy", "clr", "System"))
        self.assertEqual(bad, [], f"轻 import 链不得拖入 UnityPy/CLR：{bad}")

    def test_scenes_specs_imports_light(self) -> None:
        import eidolon.core.render.scenes.specs as specs

        self.assertTrue(specs.PREFAB_SPECS)
        bad = sorted(m for m in sys.modules
                     if m.split(".")[0] in ("UnityPy", "clr", "System"))
        self.assertEqual(bad, [], f"scenes.specs 是纯数据表，不得拖 UnityPy：{bad}")


class RacesTextOverrideSeamsTests(unittest.TestCase):
    """§7.5 三个消费点的文本级守卫（AST 文本断言；真行为归 integration）。"""

    def test_compiler_race_text_override_consumed(self) -> None:
        text = _read(COMPILER_FILE)
        # 消费点 1/3：_race_text_and_count 开头短路
        self.assertGreaterEqual(text.count("races_text_override"), 2,
                                "compiler.py 缺 races_text_override 消费")
        self.assertIn('{"source": "eidolon.races_override"}', text)
        # 两个函数体（_race_text_and_count / _trinket_race_text）都要有 getattr 短路
        for fn_name in ("_race_text_and_count", "_trinket_race_text"):
            tree = ast.parse(text, filename=str(COMPILER_FILE))
            fns = [n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == fn_name]
            self.assertEqual(len(fns), 1, f"{fn_name} 应恰一份")
            body_src = ast.dump(fns[0])
            self.assertIn("races_text_override", body_src,
                          f"{fn_name} 缺 §7.5 覆盖短路（消费点）")

    def test_components_bacon_race_count_consumed(self) -> None:
        text = _read(COMPONENTS_FILE)
        self.assertIn("races_text_override", text,
                      "components.py 缺 §7.5 板选择消费（race_count）")
        tree = ast.parse(text, filename=str(COMPONENTS_FILE))
        fns = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_bacon_plan_patch"]
        self.assertEqual(len(fns), 1)
        src = ast.dump(fns[0])
        self.assertIn("races_text_override", src)
        self.assertIn("race_count", src)

    def test_card_seat_exists(self) -> None:
        # 座位本体在 Phase 2a（infra/card.py）；这里防消费面引用悬空
        card_src = _read(ROOT / "eidolon" / "core" / "infra" / "card.py")
        self.assertIn("races_text_override", card_src)


class CanonicalCfgGuardTests(unittest.TestCase):
    """§7.6：canonical_cfg 正典字段逐字段守卫（文本级；字段值改动必须过设计轮）。"""

    CANONICAL_FIELDS = (
        "mip=True", "portrait_mip=True", 'class_color="canonical"',
        "watermark=True", 'rarity_gem_mode="lineage"', "use_bg_style=None",
        "supersample=4",
    )

    def test_canonical_cfg_fields_intact(self) -> None:
        text = _read(COMPONENTS_FILE)
        for field in self.CANONICAL_FIELDS:
            self.assertIn(field, text, f"canonical_cfg 正典字段漂移：缺 {field}")


class NoAtlasSnapshotRefsTests(unittest.TestCase):
    """§4.3 不搬清单防回归：render 全域禁图集快照链引用（docstring 提及也算）。"""

    def test_no_banned_refs_in_render_tree(self) -> None:
        offenders: list[str] = []
        for path in sorted(RENDER_DIR.rglob("*.py")):
            text = _read(path)
            for ref in BANNED_ATLAS_REFS:
                if ref in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {ref}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
