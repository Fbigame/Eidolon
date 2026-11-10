"""catalog：DbfCatalog 纯索引（不经 dbf/UnityPy 直接构建）。"""

from __future__ import annotations

import unittest

from eidolon.contracts import CardCatalog, CardFacts, CardRef
from eidolon.core.infra.catalog import DbfCatalog
from eidolon.core.infra.facts import (
    KNOWN_CARDTYPES,
    KNOWN_CLASSES,
    KNOWN_RARITIES,
    KNOWN_SPELL_SCHOOLS,
)

MINION = CardFacts(cardtype="MINION")
SPELL = CardFacts(cardtype="SPELL")


def _catalog() -> DbfCatalog:
    return DbfCatalog(
        by_dbf_id={8: MINION, 1121: SPELL},
        by_card_id={"cs2_182": MINION, "cs2_029": SPELL},
        duplicates=("CS2_201",),
    )


class DbfCatalogTests(unittest.TestCase):
    def test_lookup_by_dbf_id(self) -> None:
        catalog = _catalog()
        self.assertEqual(catalog.lookup(CardRef("dbf", 8)), MINION)
        self.assertEqual(catalog.lookup(CardRef("dbf", 1121)), SPELL)

    def test_lookup_by_card_id_is_case_insensitive(self) -> None:
        catalog = _catalog()
        self.assertEqual(catalog.lookup(CardRef("card", "CS2_182")), MINION)
        self.assertEqual(catalog.lookup(CardRef("card", "cs2_182")), MINION)
        self.assertEqual(catalog.lookup(CardRef("card", "Cs2_029")), SPELL)

    def test_unknown_returns_none(self) -> None:
        catalog = _catalog()
        self.assertIsNone(catalog.lookup(CardRef("dbf", 999999)))
        self.assertIsNone(catalog.lookup(CardRef("card", "NOPE")))

    def test_duplicates_recorded(self) -> None:
        self.assertEqual(_catalog().duplicates, ("CS2_201",))
        self.assertEqual(DbfCatalog(by_dbf_id={}, by_card_id={}).duplicates, ())

    def test_complete_and_known_tables_from_facts(self) -> None:
        catalog = _catalog()
        self.assertIs(catalog.complete, True)
        self.assertEqual(catalog.known_cardtypes, KNOWN_CARDTYPES)
        self.assertEqual(catalog.known_classes, KNOWN_CLASSES)
        self.assertEqual(catalog.known_rarities, KNOWN_RARITIES)
        self.assertEqual(catalog.known_spell_schools, KNOWN_SPELL_SCHOOLS)

    def test_satisfies_card_catalog_protocol(self) -> None:
        self.assertIsInstance(_catalog(), CardCatalog)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
