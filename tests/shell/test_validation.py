"""字段语义校验：classes / races / 枚举 / banner / runes / 数值 / outname / asset。"""

from __future__ import annotations

import unittest

from eidolon.shell.manifest import build_manifest
from eidolon.shell.spec import BANNERS
from tests.support import TomlCase, fixture_catalog, toml_with_card


class ClassesTests(TomlCase):
    def test_known_classes_ok(self) -> None:
        spec = self.build(
            toml_with_card('classes = ["MAGE", "PALADIN"]\n'),
            catalog=fixture_catalog(),
        )
        self.assertEqual(spec.cards[0].classes, ["MAGE", "PALADIN"])

    def test_empty_classes_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card("classes = []\n"), catalog=fixture_catalog()
        )
        self.assert_error(errors, code="empty_classes", path="cards[0].classes")

    def test_unknown_class_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('classes = ["MAGE", "BANANA"]\n'),
            catalog=fixture_catalog(),
        )
        self.assert_error(
            errors, code="unknown_class", path="cards[0].classes[1]"
        )

    def test_duplicate_class_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('classes = ["MAGE", "MAGE"]\n'),
            catalog=fixture_catalog(),
        )
        self.assert_error(
            errors, code="duplicate_class", path="cards[0].classes[1]"
        )

    def test_order_preserved(self) -> None:
        spec = self.build(
            toml_with_card('classes = ["PALADIN", "MAGE"]\n'),
            catalog=fixture_catalog(),
        )
        self.assertEqual(spec.cards[0].classes, ["PALADIN", "MAGE"])


class RacesTests(TomlCase):
    def test_empty_races_allowed(self) -> None:
        spec = self.build(toml_with_card("races = []\n"))
        manifest = build_manifest(spec)
        self.assertEqual(manifest["cards"][0]["overrides"]["races"], [])

    def test_races_order_preserved(self) -> None:
        spec = self.build(toml_with_card('races = ["鱼人", "野兽"]\n'))
        self.assertEqual(spec.cards[0].races, ["鱼人", "野兽"])

    def test_duplicate_race_rejected(self) -> None:
        errors = self.spec_errors(toml_with_card('races = ["鱼人", "鱼人"]\n'))
        self.assert_error(errors, code="duplicate_race", path="cards[0].races[1]")

    def test_empty_race_rejected(self) -> None:
        errors = self.spec_errors(toml_with_card('races = [""]\n'))
        self.assert_error(errors, code="empty_race", path="cards[0].races[0]")


class EnumTests(TomlCase):
    def test_known_enum_values_ok(self) -> None:
        spec = self.build(
            toml_with_card(
                'cardtype = "MINION"\nrarity = "LEGENDARY"\npremium = "GOLDEN"\n'
                'spell_school = "FIRE"\ncost_banner = "KABAL"\n'
            ),
            catalog=fixture_catalog(),
        )
        card = spec.cards[0]
        self.assertEqual(card.cardtype, "MINION")
        self.assertEqual(card.rarity, "LEGENDARY")
        self.assertEqual(card.premium, "GOLDEN")
        self.assertEqual(card.spell_school, "FIRE")
        self.assertEqual(card.cost_banner, "KABAL")

    def test_unknown_cardtype_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('cardtype = "BANANA"\n'), catalog=fixture_catalog()
        )
        self.assert_error(errors, code="enum", path="cards[0].cardtype")

    def test_unknown_rarity_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('rarity = "MYTHIC"\n'), catalog=fixture_catalog()
        )
        self.assert_error(errors, code="enum", path="cards[0].rarity")

    def test_unknown_spell_school_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('spell_school = "BLOOD"\n'), catalog=fixture_catalog()
        )
        self.assert_error(errors, code="enum", path="cards[0].spell_school")

    def test_premium_only_normal_or_golden(self) -> None:
        errors = self.spec_errors(
            toml_with_card('premium = "SIGNATURE"\n'), catalog=fixture_catalog()
        )
        self.assert_error(errors, code="enum", path="cards[0].premium")

    def test_premium_normal_ok(self) -> None:
        spec = self.build(
            toml_with_card('premium = "NORMAL"\n'), catalog=fixture_catalog()
        )
        self.assertEqual(spec.cards[0].premium, "NORMAL")

    def test_empty_enum_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('cardtype = ""\n'), catalog=fixture_catalog()
        )
        self.assert_error(errors, code="enum", path="cards[0].cardtype")

    def test_all_banners_accepted(self) -> None:
        for banner in BANNERS:
            with self.subTest(banner=banner):
                spec = self.build(
                    toml_with_card(f'cost_banner = "{banner}"\n'),
                    catalog=fixture_catalog(),
                )
                self.assertEqual(spec.cards[0].cost_banner, banner)

    def test_unknown_banner_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('cost_banner = "KABALX"\n'), catalog=fixture_catalog()
        )
        self.assert_error(errors, code="banner", path="cards[0].cost_banner")


class NumericTests(TomlCase):
    def test_numbers_and_elite(self) -> None:
        spec = self.build(
            toml_with_card(
                "cost = 3\nattack = 4\nhealth = 5\narmor = 0\nelite = true\n"
            )
        )
        card = spec.cards[0]
        self.assertEqual((card.cost, card.attack, card.health, card.armor), (3, 4, 5, 0))
        self.assertTrue(card.elite)

    def test_negative_numbers_allowed_by_shell(self) -> None:
        # 外壳只要求 int；取值范围/语义由渲染层负责。
        spec = self.build(toml_with_card("cost = -1\n"))
        self.assertEqual(spec.cards[0].cost, -1)

    def test_tech_level_range(self) -> None:
        spec = self.build(toml_with_card("tech_level = 0\n"))
        self.assertEqual(spec.cards[0].tech_level, 0)
        spec = self.build(toml_with_card("tech_level = 7\n"))
        self.assertEqual(spec.cards[0].tech_level, 7)
        for value in (-1, 8):
            with self.subTest(value=value):
                errors = self.spec_errors(
                    toml_with_card(f"tech_level = {value}\n")
                )
                self.assert_error(
                    errors, code="range", path="cards[0].tech_level"
                )

    def test_runes_valid(self) -> None:
        spec = self.build(
            toml_with_card("runes = { BLOOD = 1, FROST = 2 }\n")
        )
        self.assertEqual(spec.cards[0].runes, {"BLOOD": 1, "FROST": 2})

    def test_runes_empty_table_clears(self) -> None:
        spec = self.build(toml_with_card("runes = {}\n"))
        manifest = build_manifest(spec)
        self.assertEqual(
            manifest["cards"][0]["overrides"]["fields"]["runes"], {}
        )

    def test_rune_key_whitelist_all_valid(self) -> None:
        # §12.1：键名白名单 BLOOD/FROST/UNHOLY；三个都合法（计数各 1）。
        spec = self.build(
            toml_with_card("runes = { BLOOD = 1, FROST = 1, UNHOLY = 1 }\n")
        )
        self.assertEqual(
            spec.cards[0].runes, {"BLOOD": 1, "FROST": 1, "UNHOLY": 1}
        )

    def test_unknown_rune_rejected(self) -> None:
        for rune in ("BLAH", "blood", "BLOODS"):
            with self.subTest(rune=rune):
                errors = self.spec_errors(
                    toml_with_card(f'runes = {{ {rune} = 1 }}\n')
                )
                self.assert_error(
                    errors, code="unknown_rune", path=f"cards[0].runes.{rune}"
                )

    def test_unknown_rune_message_lists_allowed_names(self) -> None:
        errors = self.spec_errors(toml_with_card("runes = { BLAH = 1 }\n"))
        error = errors.errors[0]
        self.assertIn("BLOOD/FROST/UNHOLY", error.message)

    def test_rune_value_range(self) -> None:
        for value in (-1, 4):
            with self.subTest(value=value):
                errors = self.spec_errors(
                    toml_with_card(f"runes = {{ BLOOD = {value} }}\n")
                )
                self.assert_error(
                    errors, code="range", path="cards[0].runes.BLOOD"
                )

    def test_runes_total_limit(self) -> None:
        errors = self.spec_errors(
            toml_with_card("runes = { BLOOD = 2, FROST = 2 }\n")
        )
        self.assert_error(errors, code="runes_total", path="cards[0].runes")


class OutnameTests(TomlCase):
    def test_default_outname(self) -> None:
        spec = self.build(toml_with_card("", card_id="8"))
        self.assertEqual(spec.cards[0].outname, "8.png")
        self.assertEqual(spec.cards[0].out_path.name, "8.png")

    def test_auto_png_suffix(self) -> None:
        spec = self.build(toml_with_card('outname = "yeti"\n'))
        self.assertEqual(spec.cards[0].outname, "yeti.png")

    def test_explicit_png_preserved(self) -> None:
        spec = self.build(toml_with_card('outname = "x.png"\n'))
        self.assertEqual(spec.cards[0].outname, "x.png")

    def test_path_separators_rejected(self) -> None:
        for outname in ("a/b.png", r"a\b.png"):
            with self.subTest(outname=outname):
                errors = self.spec_errors(
                    toml_with_card(f'outname = {outname!r}\n'.replace("'", '"'))
                )
                self.assert_error(errors, code="outname", path="cards[0].outname")

    def test_dotdot_rejected(self) -> None:
        errors = self.spec_errors(toml_with_card('outname = "../x.png"\n'))
        self.assert_error(errors, code="outname", path="cards[0].outname")

    def test_empty_outname_rejected(self) -> None:
        errors = self.spec_errors(toml_with_card('outname = ""\n'))
        self.assert_error(errors, code="outname", path="cards[0].outname")

    def test_duplicate_outname_rejected(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\n\n'
            '[[cards]]\nid = "CS2_182"\noutname = "same.png"\n\n'
            '[[cards]]\nid = "CS2_029"\noutname = "same.png"\n'
        )
        self.assert_error(
            errors, code="duplicate_outname", path="cards[1].outname"
        )

    def test_duplicate_outname_case_insensitive(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\n\n'
            '[[cards]]\nid = "CS2_182"\noutname = "Same.png"\n\n'
            '[[cards]]\nid = "CS2_029"\noutname = "same.png"\n'
        )
        self.assert_error(
            errors, code="duplicate_outname", path="cards[1].outname"
        )


class AssetTests(TomlCase):
    def _png(self, name: str = "art.png") -> None:
        (self.tmp / name).write_bytes(b"\x89PNG\r\n\x1a\n")

    def test_relative_asset_resolves_against_toml_dir(self) -> None:
        self._png("art.png")
        spec = self.build(
            toml_with_card('[cards.asset]\nportrait = "art.png"\n')
        )
        path = spec.cards[0].assets["portrait"]
        self.assertTrue(path.is_absolute())
        self.assertEqual(path, (self.tmp / "art.png").resolve())

    def test_missing_asset_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('[cards.asset]\nportrait = "missing.png"\n')
        )
        self.assert_error(
            errors, code="asset_missing", path="cards[0].asset.portrait"
        )

    def test_wrong_extension_rejected(self) -> None:
        (self.tmp / "art.jpg").write_bytes(b"jpg")
        errors = self.spec_errors(
            toml_with_card('[cards.asset]\nframe = "art.jpg"\n')
        )
        self.assert_error(
            errors, code="asset_ext", path="cards[0].asset.frame"
        )

    def test_empty_asset_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card('[cards.asset]\nwatermark = ""\n')
        )
        self.assert_error(
            errors, code="asset", path="cards[0].asset.watermark"
        )


class DeferredTests(TomlCase):
    def test_no_catalog_defers_card_checks(self) -> None:
        # rev4：premium 是产品常量（NORMAL/GOLDEN），恒直接校验，不 deferred。
        spec = self.build(
            toml_with_card(
                'classes = ["MAGE"]\ncardtype = "MINION"\nrarity = "LEGENDARY"\n'
                'premium = "GOLDEN"\nspell_school = "FIRE"\n'
            )
        )
        self.assertEqual(
            spec.cards[0].deferred,
            ("classes", "cardtype", "rarity", "spell_school"),
        )

    def test_no_catalog_no_overrides_has_no_deferred(self) -> None:
        spec = self.build(toml_with_card(""))
        self.assertEqual(spec.cards[0].deferred, ())

    def test_catalog_resolves_deferred(self) -> None:
        spec = self.build(
            toml_with_card(
                'classes = ["MAGE"]\ncardtype = "MINION"\nrarity = "LEGENDARY"\n'
                'premium = "GOLDEN"\nspell_school = "FIRE"\ncost_banner = "KABAL"\n'
            ),
            catalog=fixture_catalog(),
        )
        self.assertEqual(spec.cards[0].deferred, ())


class ErrorPathTests(TomlCase):
    def test_error_path_points_at_second_card_cost(self) -> None:
        errors = self.spec_errors(
            'format_version = 1\n\n'
            '[[cards]]\nid = "CS2_182"\ncost = 1\n\n'
            '[[cards]]\nid = "CS2_029"\ncost = "three"\n'
        )
        self.assertIn("cards[1].cost", errors.paths)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

class TextTests(TomlCase):
    def test_multiline_desc_strips_trailing_newlines(self) -> None:
        spec = self.build(
            toml_with_card('desc = """\n第一行。\n第二行。\n"""\n'),
            catalog=fixture_catalog(),
        )
        self.assertEqual(spec.cards[0].desc, "第一行。\n第二行。")

    def test_inline_desc_unchanged(self) -> None:
        spec = self.build(
            toml_with_card('desc = "单行"\n'),
            catalog=fixture_catalog(),
        )
        self.assertEqual(spec.cards[0].desc, "单行")
