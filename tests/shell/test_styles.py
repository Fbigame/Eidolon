"""hero_style / bg_style 的 TOML 逐卡语义与 CLI 全局语义。"""

from __future__ import annotations

import unittest

from eidolon.shell.manifest import build_manifest
from eidolon.shell.spec import build_spec
from tests.support import TomlCase, fixture_catalog, toml_with_card


class TomlStyleTests(TomlCase):
    def test_hero_card_hero_style_ok(self) -> None:
        spec = self.build(
            toml_with_card("hero_style = true\n", card_id='"HERO_01"'),
            catalog=fixture_catalog(),
        )
        self.assertTrue(spec.cards[0].hero_style)

    def test_hero_card_bg_style_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card("bg_style = true\n", card_id='"HERO_01"'),
            catalog=fixture_catalog(),
        )
        self.assert_error(errors, code="style", path="cards[0].bg_style")

    def test_non_hero_hero_style_rejected(self) -> None:
        errors = self.spec_errors(
            toml_with_card("hero_style = true\n"), catalog=fixture_catalog()
        )
        self.assert_error(errors, code="style", path="cards[0].hero_style")

    def test_non_hero_bg_style_ok(self) -> None:
        spec = self.build(
            toml_with_card("bg_style = true\n"), catalog=fixture_catalog()
        )
        self.assertTrue(spec.cards[0].bg_style)

    def test_hero_card_both_switches_one_error(self) -> None:
        errors = self.spec_errors(
            toml_with_card(
                "hero_style = true\nbg_style = true\n", card_id='"HERO_01"'
            ),
            catalog=fixture_catalog(),
        )
        self.assert_error(errors, code="style", path="cards[0].bg_style")

    def test_no_catalog_preserves_raw_booleans_and_defers(self) -> None:
        spec = self.build(toml_with_card("hero_style = true\nbg_style = true\n"))
        card = spec.cards[0]
        self.assertTrue(card.hero_style)
        self.assertTrue(card.bg_style)
        self.assertEqual(card.deferred, ("hero_style", "bg_style"))

    def test_no_catalog_explicit_false_not_deferred(self) -> None:
        spec = self.build(
            toml_with_card("hero_style = false\nbg_style = false\n")
        )
        self.assertFalse(spec.cards[0].hero_style)
        self.assertFalse(spec.cards[0].bg_style)
        self.assertEqual(spec.cards[0].deferred, ())

    def test_catalog_unknown_card_defers_style(self) -> None:
        spec = self.build(
            toml_with_card(
                "hero_style = true\n", card_id='"NOT_IN_CATALOG"'
            ),
            catalog=fixture_catalog(),
        )
        card = spec.cards[0]
        self.assertTrue(card.hero_style)
        self.assertEqual(card.deferred, ("hero_style",))

    def test_manifest_carries_effective_flags(self) -> None:
        spec = self.build(
            toml_with_card("bg_style = true\n"), catalog=fixture_catalog()
        )
        manifest = build_manifest(spec)
        self.assertTrue(manifest["cards"][0]["bg_style"])


class CliStyleTests(TomlCase):
    def test_hero_style_applies_only_to_hero_cards(self) -> None:
        spec = build_spec(
            ["HERO_01", "8"], hero_style=True, catalog=fixture_catalog()
        )
        self.assertTrue(spec.cards[0].hero_style)
        self.assertFalse(spec.cards[1].hero_style)

    def test_bg_style_applies_only_to_non_hero_cards(self) -> None:
        spec = build_spec(
            ["HERO_01", "8"], bg_style=True, catalog=fixture_catalog()
        )
        self.assertFalse(spec.cards[0].bg_style)
        self.assertTrue(spec.cards[1].bg_style)

    def test_both_switches_are_orthogonal(self) -> None:
        spec = build_spec(
            ["HERO_01", "8"],
            hero_style=True,
            bg_style=True,
            catalog=fixture_catalog(),
        )
        self.assertEqual(
            [(c.hero_style, c.bg_style) for c in spec.cards],
            [(True, False), (False, True)],
        )

    def test_hero_style_without_hero_card_rejected(self) -> None:
        from eidolon.shell.errors import SpecErrors

        with self.assertRaises(SpecErrors) as caught:
            build_spec(["8"], hero_style=True, catalog=fixture_catalog())
        errors = caught.exception
        self.assert_error(errors, code="style", path="--hero-style")

    def test_bg_style_without_non_hero_card_rejected(self) -> None:
        from eidolon.shell.errors import SpecErrors

        with self.assertRaises(SpecErrors) as caught:
            build_spec(["HERO_01"], bg_style=True, catalog=fixture_catalog())
        errors = caught.exception
        self.assert_error(errors, code="style", path="--bg-style")

    def test_no_catalog_keeps_global_switch_and_defers(self) -> None:
        spec = build_spec(["HERO_01", "8"], hero_style=True)
        self.assertTrue(all(card.hero_style for card in spec.cards))
        self.assertTrue(
            all("hero_style" in card.deferred for card in spec.cards)
        )

    def test_unknown_card_with_catalog_defers_not_errors(self) -> None:
        spec = build_spec(
            ["NOT_IN_CATALOG"], hero_style=True, catalog=fixture_catalog()
        )
        self.assertTrue(spec.cards[0].hero_style)
        self.assertIn("hero_style", spec.cards[0].deferred)

    def test_mixed_known_and_unknown_does_not_false_positive(self) -> None:
        # 已知非 HERO + 未知卡：未知卡可能是 HERO，不能因「无适用卡」报错。
        spec = build_spec(
            ["8", "NOT_IN_CATALOG"],
            hero_style=True,
            catalog=fixture_catalog(),
        )
        self.assertFalse(spec.cards[0].hero_style)
        self.assertTrue(spec.cards[1].hero_style)


class CardtypeOverrideStyleTests(TomlCase):
    """§5.4：style 适用性按「生效 cardtype」（cardtype 覆盖优先于 facts）。"""

    def test_data_hero_cardtype_minion_gets_effective_bg(self) -> None:
        # 数据 HERO + cardtype=MINION + bg_style=true → 生效 bg，不得静默 plain。
        spec = self.build(
            toml_with_card(
                'cardtype = "MINION"\nbg_style = true\n', card_id='"HERO_01"'
            ),
            catalog=fixture_catalog(),
        )
        card = spec.cards[0]
        self.assertTrue(card.bg_style)
        self.assertFalse(card.hero_style)
        self.assertEqual(card.style_requested, (False, True))

    def test_data_minion_cardtype_hero_gets_effective_hero(self) -> None:
        # 数据 MINION + cardtype=HERO + hero_style=true → 生效 hero。
        spec = self.build(
            toml_with_card(
                'cardtype = "HERO"\nhero_style = true\n', card_id='"CS2_182"'
            ),
            catalog=fixture_catalog(),
        )
        card = spec.cards[0]
        self.assertTrue(card.hero_style)
        self.assertFalse(card.bg_style)
        self.assertEqual(card.style_requested, (True, False))

    def test_data_hero_cardtype_minion_global_bg_style(self) -> None:
        # 全局 --bg-style：无覆盖时数据 HERO 不适用（生效 False），但请求
        # 原样保留（style_requested）；混合批避免「本批无适用卡」检查拦截。
        spec = build_spec(
            ["HERO_01", "8"],
            bg_style=True,
            catalog=fixture_catalog(),
        )
        self.assertFalse(spec.cards[0].bg_style)
        self.assertEqual(spec.cards[0].style_requested, (False, True))
        self.assertTrue(spec.cards[1].bg_style)
        self.assertEqual(spec.cards[1].style_requested, (False, True))

    def test_data_hero_cardtype_minion_toml_explicit_hero_style_error(self) -> None:
        # TOML 显式意图错误按生效 cardtype 判：cardtype=MINION 后显式
        # hero_style 仍报错（生效 MINION）。
        errors = self.spec_errors(
            toml_with_card(
                'cardtype = "MINION"\nhero_style = true\n', card_id='"HERO_01"'
            ),
            catalog=fixture_catalog(),
        )
        self.assert_error(errors, code="style", path="cards[0].hero_style")

    def test_data_minion_cardtype_hero_toml_explicit_bg_style_error(self) -> None:
        errors = self.spec_errors(
            toml_with_card(
                'cardtype = "HERO"\nbg_style = true\n', card_id='"CS2_182"'
            ),
            catalog=fixture_catalog(),
        )
        self.assert_error(errors, code="style", path="cards[0].bg_style")

    def test_batch_style_check_uses_effective_cardtype(self) -> None:
        # 批里只有覆盖成 HERO 的卡 + 全局 hero-style → 不误报「无适用卡」。
        # （_check_batch_styles 按「每卡生效 cardtype」判定；数据轴全是
        # MINION，无覆盖时会报 --hero-style 无适用卡。）
        compiled = self._compile_inline(
            ["CS2_182", "RLK_000"],
            cardtype='cardtype = "HERO"\n',
            hero_style=True,
        )
        self.assertTrue(all(card.hero_style for card in compiled.cards))
        self.assertEqual(
            [card.style_requested for card in compiled.cards],
            [(True, False), (True, False)],
        )

    def test_batch_style_check_no_applicable_card_still_rejected(self) -> None:
        # 对照：批里全是数据 MINION 且无覆盖 + 全局 hero-style → 仍报 2。
        from eidolon.shell.errors import SpecErrors

        with self.assertRaises(SpecErrors) as caught:
            self._compile_inline(["CS2_182"], cardtype="", hero_style=True)
        self.assert_error(caught.exception, code="style", path="--hero-style")

    def test_no_override_behavior_unchanged(self) -> None:
        # 回归红线：无覆盖时行为与既有语义一致（生效值按数据轴 + deferred）。
        spec = self.build(
            toml_with_card("bg_style = true\n"), catalog=fixture_catalog()
        )
        card = spec.cards[0]  # CS2_182 数据 MINION：bg 生效
        self.assertTrue(card.bg_style)
        self.assertEqual(card.style_requested, (False, True))
        self.assertEqual(card.deferred, ())
        spec = build_spec(
            ["HERO_01", "8"],
            hero_style=True,
            catalog=fixture_catalog(),
        )
        self.assertTrue(spec.cards[0].hero_style)
        self.assertEqual(spec.cards[0].style_requested, (True, False))
        self.assertFalse(spec.cards[1].hero_style)
        self.assertEqual(spec.cards[1].style_requested, (True, False))
        self.assertEqual(spec.cards[0].deferred, ())

    def _compile_inline(self, ids, *, cardtype: str, hero_style: bool):
        """inline 模式 + 全局开关直通 compile_spec（TOML 模式拒全局开关）。"""
        from dataclasses import replace
        from types import SimpleNamespace

        from eidolon.shell.input import load_input
        from eidolon.shell.spec import compile_spec

        args = SimpleNamespace(
            command="spec",
            ids=list(ids),
            toml=None,
            outdir=str(self.tmp / "out"),
            jobs=None,
            antialias=None,
            hero_style=True if hero_style else None,
            bg_style=None,
            catalog=None,
            game=None,
            locale=None,
            cache_root=None,
        )
        draft = load_input(args, self.tmp)
        if cardtype:
            cards = tuple(
                replace(card, overrides={**card.overrides, "cardtype": "HERO"})
                for card in draft.cards
            )
            draft = replace(draft, cards=cards)
        return compile_spec(draft, _fixture_binding())


def _fixture_binding():
    """fixture catalog 的 CatalogBinding（inline 全局开关组合用）。"""
    from eidolon.contracts import CatalogBinding, CatalogIdentity

    catalog = fixture_catalog()
    return CatalogBinding(
        catalog=catalog,
        game=None,
        identity=CatalogIdentity(kind="json", path="<fixture>", complete=False),
    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
