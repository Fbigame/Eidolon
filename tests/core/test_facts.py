"""facts：静态枚举镜像（设计 §6.3）——四表逐名逐值钉死。"""

from __future__ import annotations

import unittest

from eidolon.contracts import EnvironmentUnavailable
from eidolon.core.infra.facts import (
    CARD_TYPE_TAG_ID,
    CARDTYPE_NAMES,
    CLASS_NAMES,
    KNOWN_CARDTYPES,
    KNOWN_CLASSES,
    KNOWN_RARITIES,
    KNOWN_SPELL_SCHOOLS,
    RARITY_NAMES,
    SPELL_SCHOOL_NAMES,
    cardtype_name,
)

EXPECTED_CARDTYPE = {
    0: "INVALID",
    1: "GAME",
    2: "PLAYER",
    3: "HERO",
    4: "MINION",
    5: "SPELL",
    6: "ENCHANTMENT",
    7: "WEAPON",
    8: "ITEM",
    9: "TOKEN",
    10: "HERO_POWER",
    11: "BLANK",
    12: "GAME_MODE_BUTTON",
    22: "MOVE_MINION_HOVER_TARGET",
    23: "LETTUCE_ABILITY",
    24: "BATTLEGROUND_HERO_BUDDY",
    39: "LOCATION",
    40: "BATTLEGROUND_QUEST_REWARD",
    42: "BATTLEGROUND_SPELL",
    43: "BATTLEGROUND_ANOMALY",
    44: "BATTLEGROUND_TRINKET",
    45: "PET",
}

EXPECTED_CLASS = {
    0: "INVALID",
    1: "DEATHKNIGHT",
    2: "DRUID",
    3: "HUNTER",
    4: "MAGE",
    5: "PALADIN",
    6: "PRIEST",
    7: "ROGUE",
    8: "SHAMAN",
    9: "WARLOCK",
    10: "WARRIOR",
    11: "DREAM",
    12: "NEUTRAL",
    13: "WHIZBANG",
    14: "DEMONHUNTER",
}

EXPECTED_RARITY = {
    0: "INVALID",
    1: "COMMON",
    2: "FREE",
    3: "RARE",
    4: "EPIC",
    5: "LEGENDARY",
}

EXPECTED_SPELL_SCHOOL = {
    0: "NONE",
    1: "ARCANE",
    2: "FIRE",
    3: "FROST",
    4: "NATURE",
    5: "HOLY",
    6: "SHADOW",
    7: "FEL",
    8: "PHYSICAL_COMBAT",
    9: "TAVERN",
    10: "SPELLCRAFT",
    11: "LESSER_TRINKET",
    12: "GREATER_TRINKET",
    13: "UPGRADE",
}


class FactsTableTests(unittest.TestCase):
    def test_card_type_tag_id(self) -> None:
        # GAME_TAG.CARDTYPE（37.0.2 实测快照；集成测试对活表）。
        self.assertEqual(CARD_TYPE_TAG_ID, 202)

    def test_cardtype_table_pinned(self) -> None:
        self.assertEqual(CARDTYPE_NAMES, EXPECTED_CARDTYPE)
        self.assertEqual(len(CARDTYPE_NAMES), 22)

    def test_class_table_pinned(self) -> None:
        self.assertEqual(CLASS_NAMES, EXPECTED_CLASS)
        self.assertEqual(len(CLASS_NAMES), 15)

    def test_rarity_table_pinned(self) -> None:
        self.assertEqual(RARITY_NAMES, EXPECTED_RARITY)
        self.assertEqual(len(RARITY_NAMES), 6)

    def test_spell_school_table_pinned(self) -> None:
        self.assertEqual(SPELL_SCHOOL_NAMES, EXPECTED_SPELL_SCHOOL)
        self.assertEqual(len(SPELL_SCHOOL_NAMES), 14)

    def test_known_tuples_follow_declaration_order(self) -> None:
        # known_* 按枚举声明序（= 表书写顺序），与 dict 插入序一致。
        self.assertEqual(KNOWN_CARDTYPES, tuple(EXPECTED_CARDTYPE.values()))
        self.assertEqual(KNOWN_CLASSES, tuple(EXPECTED_CLASS.values()))
        self.assertEqual(KNOWN_RARITIES, tuple(EXPECTED_RARITY.values()))
        self.assertEqual(KNOWN_SPELL_SCHOOLS, tuple(EXPECTED_SPELL_SCHOOL.values()))

    def test_known_are_tuples(self) -> None:
        for known in (KNOWN_CARDTYPES, KNOWN_CLASSES, KNOWN_RARITIES, KNOWN_SPELL_SCHOOLS):
            self.assertIsInstance(known, tuple)

    def test_value_domains(self) -> None:
        # CARDTYPE 跳号段（13..21 / 25..38 / 41 不在表内）；其余连续 0 起。
        self.assertEqual(sorted(CARDTYPE_NAMES), sorted(EXPECTED_CARDTYPE))
        self.assertEqual(sorted(CLASS_NAMES), list(range(15)))
        self.assertEqual(sorted(RARITY_NAMES), list(range(6)))
        self.assertEqual(sorted(SPELL_SCHOOL_NAMES), list(range(14)))


class CardtypeNameTests(unittest.TestCase):
    def test_hit(self) -> None:
        self.assertEqual(cardtype_name(4), "MINION")
        self.assertEqual(cardtype_name(39), "LOCATION")
        self.assertEqual(cardtype_name(0), "INVALID")

    def test_miss_raises_environment_unavailable(self) -> None:
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            cardtype_name(99)
        self.assertEqual(ctx.exception.problem.code, "constants_unavailable")
        self.assertEqual(ctx.exception.problem.path, "eidolon")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
