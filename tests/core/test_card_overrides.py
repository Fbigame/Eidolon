"""card_overrides 映射表单测（§7.4 全行；fake Card + fake CardConstants，不载 CLR）。

fake 的 tag id 是测试内自洽的任意整数（断言从 fake 常量表推导），
不钉 live GameTag 值——live 构造归 constants 的 live 单测/集成。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from eidolon.contracts import CardRef, EnvironmentUnavailable, InputRejected, RenderCard
from eidolon.core.render.card_overrides import apply
from eidolon.core.render.constants import CardConstants

TAGS = {
    "COST": 48, "ATK": 47, "HEALTH": 45, "ARMOR": 292,
    "CARDTYPE": 202, "RARITY": 203, "PREMIUM": 206, "SPELL_SCHOOL": 1441,
    "ELITE": 1500, "TECH_LEVEL": 1560,
    "CLASS": 199, "MULTIPLE_CLASSES": 476,
    "COST_BLOOD": 1085, "COST_FROST": 2746, "COST_UNHOLY": 2747,
    # 种族 tag（断言 races 覆盖**不写**它们）
    "CARDRACE": 200, "CARD_RACE": 1999,
}
BANNERS = {
    "GRIMY_GOONS": 900, "KABAL": 901, "JADE_LOTUS": 902, "ZERG": 903,
    "TERRAN": 904, "PROTOSS": 905, "TRADEABLE": 906, "FORGE": 907,
    "PREPARE": 908,
}


class FakeCard:
    """§7.4 覆盖座位的最小宿主（tags dict + text/资产/种族座位属性）。"""

    def __init__(self) -> None:
        self.tags: dict[int, int] = {}
        self.name = "orig"
        self.text = "orig text"
        self.races_text_override: tuple[str, ...] | None = None
        self.frame_asset: str | None = None
        self.portrait_asset: str | None = None
        self.watermark_asset: str | None = None
        self.watermark_force = False


def fake_constants() -> CardConstants:
    return CardConstants(
        classes={"INVALID": 0, "DEATHKNIGHT": 1, "HUNTER": 3, "MAGE": 4,
                 "WARRIOR": 10, "DEMONHUNTER": 14},
        cardtypes={"INVALID": 0, "HERO": 3, "MINION": 4, "SPELL": 5},
        rarities={"INVALID": 0, "COMMON": 2, "LEGENDARY": 5},
        schools={"NONE": 0, "FIRE": 2, "FROST": 3},
        premiums={"NORMAL": 0, "GOLDEN": 1},   # 产品政策：只这两档
        banners=BANNERS,
        tags=TAGS,
    )


def render_card(**overrides) -> RenderCard:
    return RenderCard(ref=CardRef("dbf", 8), out_path=Path("o.png"),
                      overrides=overrides)


class ApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.card = FakeCard()
        self.constants = fake_constants()

    def apply(self, **overrides) -> FakeCard:
        apply(self.card, render_card(**overrides), self.constants)
        return self.card

    # ---- name / desc ----

    def test_name_and_desc(self) -> None:
        card = self.apply(name="冰风雪人", desc="新描述")
        self.assertEqual(card.name, "冰风雪人")
        self.assertEqual(card.text, "新描述")

    def test_desc_replaces_text_only(self) -> None:
        # §7.4：desc → card.text；text_overridden 判定（.text != record 原文）
        # 由 Card 契约承担，本层只保证写 .text。
        card = self.apply(desc="改写")
        self.assertEqual(card.text, "改写")
        self.assertEqual(card.name, "orig")

    # ---- classes ----

    def test_classes_single_sets_class_and_zeroes_multi(self) -> None:
        card = self.apply(classes=["MAGE"])
        self.assertEqual(card.tags[TAGS["CLASS"]], 4)
        self.assertEqual(card.tags[TAGS["MULTIPLE_CLASSES"]], 0)

    def test_classes_two_bitmask_or(self) -> None:
        # 位=值−1（引擎 GetClasses：bit i → TAG_CLASS i+1）。
        card = self.apply(classes=["MAGE", "HUNTER"])
        self.assertEqual(card.tags[TAGS["MULTIPLE_CLASSES"]], (1 << 3) | (1 << 2))
        self.assertEqual(card.tags[TAGS["CLASS"]], 0)

    def test_classes_three_bitmask(self) -> None:
        card = self.apply(classes=["MAGE", "HUNTER", "DEATHKNIGHT"])
        self.assertEqual(card.tags[TAGS["MULTIPLE_CLASSES"]],
                         (1 << 3) | (1 << 2) | (1 << 0))
        self.assertEqual(card.tags[TAGS["CLASS"]], 0)

    def test_classes_invalid_value_rejected(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            self.apply(classes=["INVALID"])
        self.assertEqual(ctx.exception.problem.code, "enum")

    def test_classes_unknown_name_rejected(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            self.apply(classes=["BOGUS"])
        self.assertEqual(ctx.exception.problem.code, "enum")

    def test_classes_empty_rejected(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            self.apply(classes=[])
        self.assertEqual(ctx.exception.problem.code, "empty_classes")

    # ---- races（只写文本座位，不写种族 tag）----

    def test_races_write_text_seat_only(self) -> None:
        card = self.apply(races=["野兽", "恶魔"])
        self.assertEqual(card.races_text_override, ("野兽", "恶魔"))
        self.assertNotIn(TAGS["CARDRACE"], card.tags)
        self.assertNotIn(TAGS["CARD_RACE"], card.tags)

    def test_races_empty_tuple_is_legal(self) -> None:
        card = self.apply(races=[])
        self.assertEqual(card.races_text_override, ())

    # ---- 数值 tag ----

    def test_stat_tags(self) -> None:
        card = self.apply(cost=9, attack=7, health=6, armor=3)
        self.assertEqual(card.tags[TAGS["COST"]], 9)
        self.assertEqual(card.tags[TAGS["ATK"]], 7)
        self.assertEqual(card.tags[TAGS["HEALTH"]], 6)
        self.assertEqual(card.tags[TAGS["ARMOR"]], 3)

    def test_stat_tag_non_int_rejected(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            self.apply(cost="9")
        self.assertEqual(ctx.exception.problem.code, "type")

    # ---- 枚举查表 ----

    def test_cardtype_via_constants(self) -> None:
        card = self.apply(cardtype="MINION")
        self.assertEqual(card.tags[TAGS["CARDTYPE"]], 4)

    def test_cardtype_unknown_is_mirror_gap(self) -> None:
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            self.apply(cardtype="WEAPON")
        self.assertEqual(ctx.exception.problem.code, "constants_unavailable")

    def test_rarity_via_constants(self) -> None:
        card = self.apply(rarity="LEGENDARY")
        self.assertEqual(card.tags[TAGS["RARITY"]], 5)

    def test_rarity_unknown_is_mirror_gap(self) -> None:
        with self.assertRaises(EnvironmentUnavailable):
            self.apply(rarity="RARE")

    def test_premium_golden(self) -> None:
        card = self.apply(premium="GOLDEN")
        self.assertEqual(card.tags[TAGS["PREMIUM"]], 1)

    def test_premium_normal_writes_zero(self) -> None:
        card = self.apply(premium="NORMAL")
        self.assertEqual(card.tags[TAGS["PREMIUM"]], 0)

    def test_premium_only_normal_and_golden(self) -> None:
        # 产品政策：premiums 表只 NORMAL/GOLDEN；其他名（DIAMOND…）= INPUT。
        with self.assertRaises(InputRejected) as ctx:
            self.apply(premium="DIAMOND")
        self.assertEqual(ctx.exception.problem.code, "enum")

    def test_spell_school_via_constants(self) -> None:
        card = self.apply(spell_school="FIRE")
        self.assertEqual(card.tags[TAGS["SPELL_SCHOOL"]], 2)

    def test_spell_school_unknown_is_mirror_gap(self) -> None:
        with self.assertRaises(EnvironmentUnavailable):
            self.apply(spell_school="SHADOW")

    # ---- cost_banner ----

    def test_cost_banner_clears_nine_then_sets_one(self) -> None:
        self.card.tags[BANNERS["GRIMY_GOONS"]] = 1   # 预置脏值，验证先清
        card = self.apply(cost_banner="KABAL")
        for name, tag_id in BANNERS.items():
            expected = 1 if name == "KABAL" else 0
            self.assertEqual(card.tags.get(tag_id), expected, name)

    def test_cost_banner_none_only_clears(self) -> None:
        self.card.tags[BANNERS["TRADEABLE"]] = 1
        card = self.apply(cost_banner="NONE")
        for tag_id in BANNERS.values():
            self.assertEqual(card.tags.get(tag_id), 0)

    def test_cost_banner_unknown_name_rejected(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            self.apply(cost_banner="MOONS")
        self.assertEqual(ctx.exception.problem.code, "banner")

    # ---- elite / tech_level ----

    def test_elite_bool_to_0_1(self) -> None:
        card = self.apply(elite=True)
        self.assertEqual(card.tags[TAGS["ELITE"]], 1)
        card = self.apply(elite=False)
        self.assertEqual(card.tags[TAGS["ELITE"]], 0)

    def test_tech_level(self) -> None:
        card = self.apply(tech_level=5)
        self.assertEqual(card.tags[TAGS["TECH_LEVEL"]], 5)

    # ---- runes ----

    def test_runes_clears_then_sets(self) -> None:
        self.card.tags[TAGS["COST_BLOOD"]] = 3       # 预置脏值，验证先清
        card = self.apply(runes={"FROST": 2})
        self.assertEqual(card.tags[TAGS["COST_BLOOD"]], 0)
        self.assertEqual(card.tags[TAGS["COST_FROST"]], 2)
        self.assertEqual(card.tags[TAGS["COST_UNHOLY"]], 0)

    def test_runes_three_keys(self) -> None:
        card = self.apply(runes={"BLOOD": 1, "FROST": 1, "UNHOLY": 1})
        self.assertEqual(card.tags[TAGS["COST_BLOOD"]], 1)
        self.assertEqual(card.tags[TAGS["COST_FROST"]], 1)
        self.assertEqual(card.tags[TAGS["COST_UNHOLY"]], 1)

    def test_runes_invalid_key_rejected(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            self.apply(runes={"SHADOW": 1})
        self.assertEqual(ctx.exception.problem.code, "unknown_rune")

    # ---- assets 三座位 ----

    def test_assets_three_seats(self) -> None:
        apply(self.card,
              RenderCard(ref=CardRef("dbf", 8), out_path=Path("o.png"),
                         assets={"portrait": Path("p.png"), "frame": Path("f.png"),
                                 "watermark": Path("w.png")}),
              self.constants)
        self.assertEqual(self.card.portrait_asset, str(Path("p.png")))
        self.assertEqual(self.card.frame_asset, str(Path("f.png")))
        self.assertEqual(self.card.watermark_asset, str(Path("w.png")))
        self.assertTrue(self.card.watermark_force)   # 显式覆盖即强制显示

    def test_assets_unknown_seat_rejected(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            apply(self.card,
                  RenderCard(ref=CardRef("dbf", 8), out_path=Path("o.png"),
                             assets={"banner": Path("b.png")}),
                  self.constants)
        self.assertEqual(ctx.exception.problem.code, "unknown_key")

    # ---- 未知键 / 空 input ----

    def test_unknown_override_key_rejected(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            self.apply(bogus=1)
        self.assertEqual(ctx.exception.problem.code, "unknown_key")

    def test_no_overrides_writes_nothing(self) -> None:
        apply(self.card, render_card(), self.constants)
        self.assertEqual(self.card.tags, {})
        self.assertEqual(self.card.name, "orig")
        self.assertIsNone(self.card.races_text_override)
        self.assertFalse(self.card.watermark_force)

    # ---- Problem 定位形状（键级 path；cards[i] 由调用方补）----

    def test_problem_path_is_key_scoped(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            self.apply(cost="9")
        self.assertEqual(ctx.exception.problem.path, "cost")
        self.assertIn("cost", ctx.exception.problem.message)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
