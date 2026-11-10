"""core/render/preflight 单测（§7.7 第 9 步；默认只测无 dbf 会话分支）。

Card 级校验分支（``Card.from_dbf`` + ``live_card_constants`` + form 试算）
函数体内才 import CLR 链——默认 discover 不触，归 integration（§13.3）。
"""

from __future__ import annotations

import contextlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from eidolon.contracts import (
    CardRef,
    EnvironmentUnavailable,
    InputRejected,
    Problem,
    ProblemKind,
    RenderCard,
)
from eidolon.core.render.preflight import problem_of, validate_overrides


def render_card(ref=None, **kwargs) -> RenderCard:
    return RenderCard(ref=ref or CardRef("dbf", 8), out_path=Path("o.png"),
                      **kwargs)


class _FakeSession:
    """「已装会话」的最小替身（duck type：只吃 card_id_to_dbf）。"""

    def __init__(self, mapping: dict[str, int]) -> None:
        self.card_id_to_dbf = mapping


@contextlib.contextmanager
def _dbf_stub(session):
    """``sys.modules`` 注入 dbf 桩（真件顶层 import UnityPy——tests/core 纪律
    禁拖；seams 守卫以 sys.modules 全局断言，桩保证不污染）。

    退场时剥掉 parent 包上被 import 系统缓存的桩属性，防 ``from
    eidolon.core.infra import dbf`` 的 getattr 捷径跨用例漏桩。"""
    import eidolon.core.infra as infra_pkg

    had_attr = hasattr(infra_pkg, "dbf")
    stub = types.ModuleType("eidolon.core.infra.dbf")
    stub.default_dbf = lambda: session
    stub.installed_default = lambda: session
    stub.install_default = lambda module: session
    stub.reset_default = lambda: None
    with mock.patch.dict(sys.modules, {"eidolon.core.infra.dbf": stub}):
        try:
            yield stub
        finally:
            if not had_attr and getattr(infra_pkg, "dbf", None) is stub:
                delattr(infra_pkg, "dbf")


class NoSessionTests(unittest.TestCase):
    """无 dbf 会话 → 空元组（fake provider / 测试注入跳过，不误报）。"""

    def test_empty_cards(self) -> None:
        with _dbf_stub(None):
            self.assertEqual(validate_overrides([]), ())

    def test_invalid_overrides_still_skipped_without_session(self) -> None:
        # 短路语义：非法覆盖在无会话时也返回空——Card 级校验整体跳过。
        cards = [render_card(overrides={"classes": ["BOGUS"], "cost": -5})]
        with _dbf_stub(None):
            self.assertEqual(validate_overrides(cards), ())

    def test_unknown_card_id_skips_card_level_check(self) -> None:
        # 有会话但 ref 查不到 dbf id：Card 级校验无对象 → 跳过（不误报）；
        # 该分支在 import Card（CLR 链）之前返回，默认测试可覆盖。
        cards = [render_card(ref=CardRef("card", "NOPE"),
                             overrides={"classes": ["BOGUS"]})]
        with _dbf_stub(_FakeSession({})):   # 空 card_id_to_dbf
            self.assertEqual(validate_overrides(cards), ())


class SkipInactiveCardsTests(unittest.TestCase):
    """P1-12：无覆盖无 style 请求的卡不进 Card 级校验（零 Card/constants 构造）。

    有会话 + plain 卡 → 快速返回空；``Card.from_dbf`` /
    ``live_card_constants`` 若被触达，经 sys.modules 桩响亮 AssertionError
    （回归可见，不静默）。对照用例证明桩与会话真的在工作（active 卡仍会
    触达 constants 构造——优化只许跳 plain 卡）。
    """

    @staticmethod
    def _guard_stubs() -> dict[str, types.ModuleType]:
        card_stub = types.ModuleType("eidolon.core.infra.card")

        class _Card:
            @staticmethod
            def from_dbf(dbf_id: int) -> None:
                raise AssertionError(
                    f"plain 卡不得构造 Card（dbf_id={dbf_id}，P1-12 快速路径）"
                )

        card_stub.Card = _Card

        from eidolon.core.render.constants import CardConstants

        constants_stub = types.ModuleType("eidolon.core.render.constants")
        constants_stub.CardConstants = CardConstants

        def _no_constants() -> None:
            raise AssertionError("constants 不该在本批构造（P1-12）")

        constants_stub.live_card_constants = _no_constants
        return {
            "eidolon.core.infra.card": card_stub,
            "eidolon.core.render.constants": constants_stub,
        }

    def test_plain_cards_skip_card_level_check(self) -> None:
        # 会话在、ref 可解，但卡无 overrides 无 style → 快速返回，不触 CLR 链。
        cards = [
            render_card(),                                # dbf ref 8
            render_card(ref=CardRef("card", "hero_01")),  # card ref，索引可解
        ]
        with _dbf_stub(_FakeSession({"hero_01": 7})):
            with mock.patch.dict(sys.modules, self._guard_stubs()):
                self.assertEqual(validate_overrides(cards), ())

    def test_active_card_still_reaches_constants(self) -> None:
        # 对照：有 overrides 的卡必须仍进 Card 级校验（constants 构造被触达
        # → 桩 AssertionError），证明上面的跳过不是「会话桩失效」的假绿。
        cards = [render_card(overrides={"cost": 1})]
        with _dbf_stub(_FakeSession({})):
            with mock.patch.dict(sys.modules, self._guard_stubs()):
                with self.assertRaises(AssertionError):
                    validate_overrides(cards)


class ProblemOfTests(unittest.TestCase):
    """Problem 抽取纯函数（不依赖 dbf/CLR）。"""

    def test_input_rejected_yields_problem(self) -> None:
        problem = Problem(ProblemKind.INPUT, "enum", "cost", "m")
        self.assertIs(problem_of(InputRejected(problem)), problem)

    def test_environment_unavailable_yields_problem(self) -> None:
        problem = Problem(ProblemKind.ENVIRONMENT, "dbf_missing", "p", "m")
        self.assertIs(problem_of(EnvironmentUnavailable(problem)), problem)

    def test_other_exception_yields_none(self) -> None:
        self.assertIsNone(problem_of(ValueError("x")))
        self.assertIsNone(problem_of(RuntimeError("x")))
        self.assertIsNone(problem_of(Exception("x")))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
