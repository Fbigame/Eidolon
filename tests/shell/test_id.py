"""id 解析 / 归一化 / 重复检测。"""

from __future__ import annotations

import unittest

from eidolon.shell.errors import SpecErrors
from eidolon.shell.spec import CardRef, build_spec, parse_id
from tests.support import TomlCase


class ParseIdTests(unittest.TestCase):
    def test_int_becomes_dbf(self) -> None:
        self.assertEqual(parse_id(8), CardRef("dbf", 8))
        self.assertEqual(parse_id(105108), CardRef("dbf", 105108))

    def test_numeric_string_becomes_dbf(self) -> None:
        self.assertEqual(parse_id("8"), CardRef("dbf", 8))
        self.assertEqual(parse_id("8"), parse_id(8))

    def test_numeric_string_is_canonicalized(self) -> None:
        self.assertEqual(parse_id("008"), CardRef("dbf", 8))
        self.assertEqual(parse_id("000"), CardRef("dbf", 0))

    def test_card_id(self) -> None:
        self.assertEqual(parse_id("CS2_182"), CardRef("card", "CS2_182"))
        # 含数字但并非纯数字：card id。
        self.assertEqual(parse_id("8a"), CardRef("card", "8a"))

    def test_invalid_ids_raise(self) -> None:
        for value in ("", "CS2-182", "CS2 182", "鱼人", None, True, -1, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(SpecErrors) as caught:
                    parse_id(value)
                errors = caught.exception
                self.assertEqual(errors.errors[0].code, "invalid_id")

    def test_parse_id_error_path(self) -> None:
        with self.assertRaises(SpecErrors) as caught:
            parse_id("bad-id", "cards[3].id")
        self.assertEqual(caught.exception.errors[0].path, "cards[3].id")


class DuplicateIdTests(TomlCase):
    def test_inline_int_and_numeric_string_duplicate(self) -> None:
        with self.assertRaises(SpecErrors) as caught:
            build_spec([8, "8"])
        errors = caught.exception
        self.assert_error(errors, code="duplicate_id", path="ids[1]")

    def test_inline_leading_zero_duplicate(self) -> None:
        with self.assertRaises(SpecErrors) as caught:
            build_spec(["008", 8])
        self.assert_error(caught.exception, code="duplicate_id", path="ids[1]")

    def test_inline_card_id_duplicate(self) -> None:
        with self.assertRaises(SpecErrors) as caught:
            build_spec(["CS2_182", "CS2_182"])
        self.assert_error(caught.exception, code="duplicate_id", path="ids[1]")

    def test_toml_numeric_string_id_rejected(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\n\n[[cards]]\nid = "8"\n'
        )
        self.assert_error(errors, code="invalid_id", path="cards[0].id")

    def test_toml_duplicate_int(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\n\n[[cards]]\nid = 8\n\n[[cards]]\nid = 8\n'
        )
        self.assert_error(errors, code="duplicate_id", path="cards[1].id")

    def test_toml_duplicate_card_id(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\n\n[[cards]]\nid = "CS2_182"\n\n'
            '[[cards]]\nid = "CS2_182"\n'
        )
        self.assert_error(errors, code="duplicate_id", path="cards[1].id")

    def test_distinct_ids_ok(self) -> None:
        spec = build_spec(["CS2_182", 8, "HERO_01"])
        self.assertEqual(
            [card.ref.value for card in spec.cards], ["CS2_182", 8, "HERO_01"]
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
