"""TOML 顶层 / 卡级 / asset 级未知键与类型检查。"""

from __future__ import annotations

import unittest

from eidolon.shell.errors import MAX_ERRORS
from tests.support import TomlCase, toml_with_card


class TopLevelTomlTests(TomlCase):
    def test_minimal_valid(self) -> None:
        spec = self.build('format_version = 1\n\n[[cards]]\nid = 8\n')
        self.assertEqual(spec.source, "toml")
        self.assertEqual(spec.options.jobs, 1)
        self.assertFalse(spec.options.antialias)

    def test_missing_format_version(self) -> None:
        errors = self.spec_errors('[[cards]]\nid = 8\n')
        self.assert_error(errors, code="missing", path="format_version")

    def test_format_version_must_be_one(self) -> None:
        errors = self.spec_errors('format_version = 2\n\n[[cards]]\nid = 8\n')
        self.assert_error(errors, code="format_version", path="format_version")

    def test_format_version_type(self) -> None:
        for value in ('"1"', "true", "1.0"):
            with self.subTest(value=value):
                errors = self.spec_errors(
                    f"format_version = {value}\n\n[[cards]]\nid = 8\n"
                )
                self.assert_error(errors, code="type", path="format_version")

    def test_unknown_top_level_key(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\nschema = 1\n\n[[cards]]\nid = 8\n'
        )
        self.assert_error(errors, code="unknown_key", path="schema")

    def test_empty_cards(self) -> None:
        errors = self.spec_errors("format_version = 1\ncards = []\n")
        self.assert_error(errors, code="empty_cards", path="cards")

    def test_missing_cards(self) -> None:
        errors = self.spec_errors("format_version = 1\n")
        self.assert_error(errors, code="missing", path="cards")

    def test_cards_wrong_type(self) -> None:
        errors = self.spec_errors('format_version = 1\ncards = "nope"\n')
        self.assert_error(errors, code="type", path="cards")

    def test_jobs_type_and_range(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\njobs = "4"\n\n[[cards]]\nid = 8\n'
        )
        self.assert_error(errors, code="type", path="jobs")

        errors = self.spec_errors(
            "format_version = 1\njobs = 0\n\n[[cards]]\nid = 8\n"
        )
        self.assert_error(errors, code="range", path="jobs")

    def test_out_dir_and_antialias_types(self) -> None:
        errors = self.spec_errors(
            "format_version = 1\nout_dir = 3\nantialias = 1\n\n[[cards]]\nid = 8\n"
        )
        self.assert_error(errors, code="type", path="out_dir")
        self.assert_error(errors, code="type", path="antialias")

    def test_toml_syntax_error(self) -> None:
        errors = self.spec_errors("format_version = \n")
        self.assert_error(errors, code="toml_syntax")

    def test_missing_toml_file(self) -> None:
        from eidolon.shell.errors import SpecErrors
        from eidolon.shell.spec import build_spec

        with self.assertRaises(SpecErrors) as caught:
            build_spec(toml_path=self.tmp / "nope.toml")
        self.assert_error(caught.exception, code="io")


class CardTomlTests(TomlCase):
    def test_unknown_card_key(self) -> None:
        errors = self.spec_errors(toml_with_card("foo = 1\n"))
        self.assert_error(errors, code="unknown_key", path="cards[0].foo")

    def test_unknown_key_second_card(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\n\n[[cards]]\nid = 8\n\n'
            '[[cards]]\nid = "CS2_182"\nfoo = 1\n'
        )
        self.assert_error(errors, code="unknown_key", path="cards[1].foo")

    def test_unknown_asset_key(self) -> None:
        errors = self.spec_errors(
            toml_with_card('[cards.asset]\nfoo = "x.png"\n')
        )
        self.assert_error(errors, code="unknown_key", path="cards[0].asset.foo")

    def test_card_must_be_table(self) -> None:
        errors = self.spec_errors("format_version = 1\ncards = [1]\n")
        self.assert_error(errors, code="type", path="cards[0]")

    def test_id_types(self) -> None:
        errors = self.spec_errors(
            "format_version = 1\n\n[[cards]]\nid = true\n"
        )
        self.assert_error(errors, code="type", path="cards[0].id")

        errors = self.spec_errors(
            "format_version = 1\n\n[[cards]]\nid = 1.5\n"
        )
        self.assert_error(errors, code="type", path="cards[0].id")

    def test_missing_id(self) -> None:
        errors = self.spec_errors(
            "format_version = 1\n\n[[cards]]\nname = \"x\"\n"
        )
        self.assert_error(errors, code="missing", path="cards[0].id")

    def test_string_fields_type(self) -> None:
        for field in ("name", "desc", "outname", "cardtype", "rarity", "premium", "spell_school", "cost_banner"):
            with self.subTest(field=field):
                errors = self.spec_errors(toml_with_card(f"{field} = 1\n"))
                self.assert_error(errors, code="type", path=f"cards[0].{field}")

    def test_int_fields_type(self) -> None:
        for field in ("cost", "attack", "health", "armor", "tech_level"):
            for value in ("1.5", '"3"', "true"):
                with self.subTest(field=field, value=value):
                    errors = self.spec_errors(
                        toml_with_card(f"{field} = {value}\n")
                    )
                    self.assert_error(errors, code="type", path=f"cards[0].{field}")

    def test_bool_fields_type(self) -> None:
        for field in ("elite", "hero_style", "bg_style"):
            with self.subTest(field=field):
                errors = self.spec_errors(toml_with_card(f"{field} = 1\n"))
                self.assert_error(errors, code="type", path=f"cards[0].{field}")

    def test_classes_type(self) -> None:
        errors = self.spec_errors(toml_with_card('classes = "MAGE"\n'))
        self.assert_error(errors, code="type", path="cards[0].classes")

        errors = self.spec_errors(toml_with_card("classes = [1]\n"))
        self.assert_error(errors, code="type", path="cards[0].classes[0]")

    def test_races_type(self) -> None:
        errors = self.spec_errors(toml_with_card('races = "鱼人"\n'))
        self.assert_error(errors, code="type", path="cards[0].races")
        errors = self.spec_errors(toml_with_card("races = [1]\n"))
        self.assert_error(errors, code="type", path="cards[0].races[0]")

    def test_runes_type(self) -> None:
        errors = self.spec_errors(toml_with_card('runes = { BLOOD = "1" }\n'))
        self.assert_error(errors, code="type", path="cards[0].runes.BLOOD")

        errors = self.spec_errors(toml_with_card('runes = "BLOOD"\n'))
        self.assert_error(errors, code="type", path="cards[0].runes")

    def test_asset_type(self) -> None:
        errors = self.spec_errors(toml_with_card('asset = "art"\n'))
        self.assert_error(errors, code="type", path="cards[0].asset")

        errors = self.spec_errors(toml_with_card("[cards.asset]\nportrait = 1\n"))
        self.assert_error(errors, code="type", path="cards[0].asset.portrait")

    def test_multiple_errors_are_collected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('foo = 1\ncost = "3"\nclasses = "MAGE"\n')
        )
        self.assertGreaterEqual(len(errors.errors), 3)
        self.assert_error(errors, code="unknown_key", path="cards[0].foo")
        self.assert_error(errors, code="type", path="cards[0].cost")
        self.assert_error(errors, code="type", path="cards[0].classes")

    def test_error_cap(self) -> None:
        lines = ["format_version = 1"]
        for index in range(MAX_ERRORS + 10):
            lines += ["[[cards]]", f'id = "CARD_{index}"', "bogus = 1"]
        errors = self.spec_errors("\n".join(lines) + "\n")
        self.assertEqual(len(errors.errors), MAX_ERRORS)
        self.assertTrue(errors.truncated)
        self.assertIn("仅显示前", str(errors))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
