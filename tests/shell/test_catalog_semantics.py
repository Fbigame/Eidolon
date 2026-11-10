"""catalog complete 语义：unknown_card / catalog_incomplete / manifest environment。"""

from __future__ import annotations

import json
import unittest

from eidolon.version import __version__
from eidolon.shell.catalog import JsonCatalog
from eidolon.shell.errors import SpecErrors
from eidolon.shell.manifest import build_manifest
from eidolon.shell.spec import build_spec
from tests.support import CATALOG_JSON, TomlCase, fixture_catalog, toml_with_card


def complete_catalog(*, without: tuple[str, ...] = ()) -> JsonCatalog:
    """complete=true fixture 的内存版；可从卡索引里挖掉若干 key。"""
    data = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    data["complete"] = True
    for key in without:
        data["cards"].pop(key, None)
    return JsonCatalog.from_dict(data)


class UnknownCardTests(TomlCase):
    def test_complete_catalog_unknown_card_errors(self) -> None:
        catalog = complete_catalog(without=("8",))
        try:
            build_spec(["8"], catalog=catalog, cwd=self.tmp)
        except SpecErrors as exc:
            self.assertIn("unknown_card", exc.codes)
            self.assertEqual(exc.paths, ("ids[0]",))
            self.assertIn("dbf id 8", exc.errors[0].message)
        else:
            raise AssertionError("预期 unknown_card")

    def test_complete_catalog_unknown_card_id_message(self) -> None:
        catalog = complete_catalog(without=("CS2_182",))
        try:
            build_spec(["CS2_182"], catalog=catalog, cwd=self.tmp)
        except SpecErrors as exc:
            self.assertIn("unknown_card", exc.codes)
            self.assertIn("card id CS2_182", exc.errors[0].message)
        else:
            raise AssertionError("预期 unknown_card")

    def test_incomplete_catalog_unknown_card_defers(self) -> None:
        # fixture catalog 未标 complete：查不到只 deferred，不阻塞。
        spec = self.build(
            toml_with_card("hero_style = true\n", card_id='"NOT_IN_CATALOG"'),
            catalog=fixture_catalog(),
        )
        self.assertEqual(spec.cards[0].deferred, ("hero_style",))

    def test_toml_unknown_card_error_path(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\n\n[[cards]]\nid = 8\n',
            catalog=complete_catalog(without=("8",)),
        )
        self.assertIn("unknown_card", errors.codes)
        self.assertIn("cards[0]", errors.paths)

    def test_unknown_card_hint_registered(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\n\n[[cards]]\nid = 8\n',
            catalog=complete_catalog(without=("8",)),
        )
        formatted = "\n".join(e.format() for e in errors.errors)
        self.assertIn("error[unknown_card]", formatted)
        self.assertIn("hint:", formatted)


class CatalogIncompleteTests(TomlCase):
    def test_incomplete_with_deferred_adds_warning(self) -> None:
        spec = self.build(
            toml_with_card("hero_style = true\n", card_id='"NOT_IN_CATALOG"'),
            catalog=fixture_catalog(),
        )
        self.assertEqual(spec.warnings, ("catalog_incomplete",))

    def test_incomplete_without_deferred_no_warning(self) -> None:
        # 查不到的卡没有任何 catalog 依赖覆盖 → 无 deferred → 无 warning。
        spec = self.build(
            toml_with_card("", card_id='"NOT_IN_CATALOG"'),
            catalog=fixture_catalog(),
        )
        self.assertEqual(spec.warnings, ())
        self.assertEqual(spec.cards[0].deferred, ())

    def test_null_catalog_never_adds_warning(self) -> None:
        # §5.4：cardtype 覆盖存在时 style 按生效 cardtype 直接校验
        # （hero_style × 生效 MINION 会报 2），故两者不再同卡出现。
        spec = self.build(
            toml_with_card('classes = ["MAGE"]\ncardtype = "MINION"\n')
        )
        self.assertEqual(spec.warnings, ())
        self.assertIn("classes", spec.cards[0].deferred)
        # hero_style 的 deferred 态（无 cardtype 覆盖 + 卡未知）：同样无警告。
        spec = self.build(
            toml_with_card('classes = ["MAGE"]\nhero_style = true\n')
        )
        self.assertEqual(spec.warnings, ())
        self.assertIn("classes", spec.cards[0].deferred)
        self.assertIn("hero_style", spec.cards[0].deferred)

    def test_complete_catalog_no_warning(self) -> None:
        spec = self.build(
            toml_with_card('classes = ["MAGE"]\ncardtype = "MINION"\n'),
            catalog=complete_catalog(),
        )
        self.assertEqual(spec.warnings, ())
        self.assertEqual(spec.cards[0].deferred, ())

    def test_warning_emitted_once_for_batch(self) -> None:
        spec = self.build(
            'format_version = 1\n\n'
            '[[cards]]\nid = "NOT_IN_CATALOG"\nhero_style = true\n\n'
            '[[cards]]\nid = "ALSO_MISSING"\nhero_style = true\n',
            catalog=fixture_catalog(),
        )
        self.assertEqual(spec.warnings, ("catalog_incomplete",))
        self.assertEqual(len(spec.cards[0].deferred), 1)


class ManifestEnvironmentTests(TomlCase):
    def test_null_catalog_environment(self) -> None:
        manifest = build_manifest(build_spec(["8"], cwd=self.tmp))
        self.assertEqual(
            manifest["environment"],
            {
                "game": None,
                "dbf": None,
                "catalog": {
                    "kind": "null",
                    "path": "",
                    "size": 0,
                    "mtime_ns": 0,
                    "complete": False,
                },
                "eidolon": __version__,
            },
        )

    def test_json_catalog_environment_from_memory(self) -> None:
        manifest = build_manifest(
            build_spec(["8"], catalog=fixture_catalog(), cwd=self.tmp)
        )
        catalog = manifest["environment"]["catalog"]
        self.assertEqual(catalog["kind"], "json")
        self.assertEqual(catalog["path"], "<memory>")
        self.assertFalse(catalog["complete"])

    def test_environment_key_order_canonical(self) -> None:
        manifest = build_manifest(build_spec(["8"], cwd=self.tmp))
        self.assertEqual(
            list(manifest["environment"]), ["game", "dbf", "catalog", "eidolon"]
        )
        self.assertEqual(
            list(manifest),
            ["format_version", "source", "options", "environment", "cards", "warnings"],
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
