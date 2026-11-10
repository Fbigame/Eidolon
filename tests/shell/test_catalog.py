"""CardCatalog：NullCatalog / JsonCatalog（含 complete 语义）。"""

from __future__ import annotations

import unittest

from eidolon.shell.catalog import CardFacts, CatalogError, JsonCatalog, NullCatalog
from eidolon.contracts import CardCatalog, CardRef
from eidolon.shell.spec import parse_id
from tests.support import CATALOG_JSON


def ref(value: int | str) -> CardRef:
    return parse_id(value)


class NullCatalogTests(unittest.TestCase):
    def test_all_known_sets_empty(self) -> None:
        catalog = NullCatalog()
        for name in (
            "known_classes",
            "known_cardtypes",
            "known_rarities",
            "known_spell_schools",
        ):
            with self.subTest(name=name):
                self.assertEqual(getattr(catalog, name), ())

    def test_complete_is_false(self) -> None:
        self.assertIs(NullCatalog().complete, False)

    def test_premiums_and_banners_not_in_protocol(self) -> None:
        # rev4：known_premiums / known_banners 是产品常量，不进 catalog。
        for name in ("known_premiums", "known_banners"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(NullCatalog(), name))

    def test_lookup_always_none(self) -> None:
        self.assertIsNone(NullCatalog().lookup(ref(8)))
        self.assertIsNone(NullCatalog().lookup(ref("CS2_182")))

    def test_satisfies_protocol(self) -> None:
        self.assertIsInstance(NullCatalog(), CardCatalog)


class JsonCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = JsonCatalog.from_path(CATALOG_JSON)

    def test_known_values_loaded(self) -> None:
        self.assertIn("MAGE", self.catalog.known_classes)
        self.assertIn("HERO", self.catalog.known_cardtypes)
        self.assertIn("LEGENDARY", self.catalog.known_rarities)
        self.assertIn("FIRE", self.catalog.known_spell_schools)

    def test_complete_defaults_false(self) -> None:
        self.assertIs(self.catalog.complete, False)

    def test_complete_from_top_level(self) -> None:
        catalog = JsonCatalog.from_dict(
            {
                "complete": True,
                "cards": {"8": {"cardtype": "MINION"}},
            }
        )
        self.assertIs(catalog.complete, True)

    def test_complete_must_be_bool(self) -> None:
        with self.assertRaises(CatalogError):
            JsonCatalog.from_dict({"complete": "yes", "cards": {}})

    def test_lookup_dbf(self) -> None:
        facts = self.catalog.lookup(ref(8))
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertEqual(facts.cardtype, "MINION")

    def test_lookup_card_id(self) -> None:
        facts = self.catalog.lookup(ref("HERO_01"))
        assert facts is not None
        self.assertEqual(facts.cardtype, "HERO")

    def test_lookup_unknown_returns_none(self) -> None:
        self.assertIsNone(self.catalog.lookup(ref("NOT_IN_CATALOG")))

    def test_cards_property_is_copy(self) -> None:
        cards = self.catalog.cards
        cards.clear()
        self.assertIsNotNone(self.catalog.lookup(ref(8)))

    def test_from_dict_defaults(self) -> None:
        catalog = JsonCatalog.from_dict(
            {"cards": {"8": {"cardtype": "MINION"}}}
        )
        self.assertEqual(catalog.known_classes, ())
        self.assertIs(catalog.complete, False)
        assert catalog.lookup(ref(8)) is not None

    def test_unknown_top_level_keys_rejected(self) -> None:
        with self.assertRaises(CatalogError):
            JsonCatalog.from_dict(
                {"cards": {}, "known_premiums": ["NORMAL", "GOLDEN"]}
            )

    def test_invalid_documents_rejected(self) -> None:
        cases = [
            [],
            {"cards": []},
            {"cards": {"8": "MINION"}},
            {"cards": {"8": {}}},
            {"cards": {"8": {"cardtype": ""}}},
            {"cards": {"8": {"cardtype": "MINION", "classes": "MAGE"}}},
            {"cards": {}, "known_classes": "MAGE"},
            {"cards": {}, "known_cardtypes": [1]},
        ]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(CatalogError):
                    JsonCatalog.from_dict(case)

    def test_missing_file_rejected(self) -> None:
        with self.assertRaises(CatalogError):
            JsonCatalog.from_path(CATALOG_JSON.parent / "nope.json")

    def test_invalid_json_rejected(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(CatalogError):
                JsonCatalog.from_path(path)

    def test_card_facts_is_frozen(self) -> None:
        facts = CardFacts(cardtype="MINION")
        with self.assertRaises(Exception):
            facts.cardtype = "SPELL"  # type: ignore[misc]


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
