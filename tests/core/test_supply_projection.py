"""_projection — 资产投影单一出口（纯 stdlib；默认 discover 收集，不 import UnityPy）。

移植上游 ``scripts/supply/_projection.py`` 的 ``--selftest`` 自测块为单测（§16.1：
``__main__`` 自测块删除、语义要点保留）。覆盖：
  * ``as_pairs`` 两已知形态（两元素列表对 / {"first","second"} 字典）同解；
  * 未知形态响亮 ``ProjectionError``（不做过滤式跳过——badge-vcolor 事故口径）；
  * ``as_rgba`` 双形态同值且**不取整**（与引擎抓帧常量缓冲逐值对位）；
  * ``projection(pairs=True)`` 源-目标基数守恒（源 n 条解出 n 条）；
  * ``projection(require=...)`` 显式已知项非空契约；
  * 域项上下文进报错消息（item_scope 复位正常）。
"""

from __future__ import annotations

import unittest

from eidolon.core.supply._projection import (
    ProjectionError,
    as_pairs,
    as_rgba,
    current_item,
    item_scope,
    projection,
)

DICT_FORM = [
    {"first": "_Color",
     "second": {"r": 0.1037736, "g": 0.1037736, "b": 0.1037736, "a": 1.0}},
    {"first": "_LightingBlend", "second": 0.0},
]
LIST_FORM = [
    ["_Color", {"r": 0.1037736, "g": 0.1037736, "b": 0.1037736, "a": 1.0}],
    ["_LightingBlend", 0.0],
]


class AsPairsTests(unittest.TestCase):
    def test_two_known_shapes_agree(self) -> None:
        a = as_pairs(DICT_FORM, what="m_Colors")
        b = as_pairs(LIST_FORM, what="m_Colors")
        self.assertEqual(len(a), 2)
        self.assertEqual(len(b), 2)
        self.assertEqual(a, b)
        self.assertEqual(list(a), ["_Color", "_LightingBlend"])

    def test_none_yields_empty(self) -> None:
        self.assertEqual(as_pairs(None, what="m_Colors"), {})

    def test_unknown_shape_raises_loudly(self) -> None:
        for bad in ([["_Color", {}], {"first": "_Color"}], ["_Color", {}],
                    [["_Color"], {}]):
            with self.assertRaises(ProjectionError, msg=repr(bad)) as ctx:
                as_pairs(bad, what="m_Colors")
            self.assertIn("m_Colors", str(ctx.exception))

    def test_non_sequence_raises(self) -> None:
        with self.assertRaises(ProjectionError):
            as_pairs({"_Color": {}}, what="m_Colors")


class AsRgbaTests(unittest.TestCase):
    def test_dict_and_quad_agree_without_rounding(self) -> None:
        expected = [0.1037736, 0.1, 0.1, 1.0]
        self.assertEqual(as_rgba({"r": 0.1037736, "g": 0.1, "b": 0.1, "a": 1}),
                         expected)
        self.assertEqual(as_rgba([0.1037736, 0.1, 0.1, 1]), expected)

    def test_none_passes_through(self) -> None:
        self.assertIsNone(as_rgba(None))

    def test_unknown_shapes_raise(self) -> None:
        for bad in ({"r": 1.0, "g": 1.0, "b": 1.0}, [1.0, 2.0, 3.0], "ffff"):
            with self.assertRaises(ProjectionError, msg=repr(bad)):
                as_rgba(bad)


class ProjectionContractTests(unittest.TestCase):
    def test_pairs_contract_enforces_cardinality(self) -> None:
        @projection(name="lossy", pairs=True)
        def lossy(seq):
            # 转换器「过滤」掉一条：覆盖率不变量必须在门里响亮。
            return {k: v for k, v in as_pairs(seq, what="m_Colors").items()
                    if k == "_Color"}

        with self.assertRaises(ProjectionError) as ctx:
            lossy(LIST_FORM)
        msg = str(ctx.exception)
        self.assertIn("基数不守恒", msg)
        self.assertIn("2", msg)
        self.assertIn("1", msg)

    def test_pairs_contract_passes_full_projection(self) -> None:
        @projection(name="full", pairs=True)
        def full(seq):
            return as_pairs(seq, what="m_Colors")

        self.assertEqual(len(full(LIST_FORM)), 2)

    def test_require_contract(self) -> None:
        @projection(name="req", require=("_Color",))
        def req(seq):
            return as_pairs(seq, what="m_Colors")

        with self.assertRaises(ProjectionError) as ctx:
            req([["_Other", 1.0]])
        self.assertIn("_Color", str(ctx.exception))
        self.assertEqual(len(req(LIST_FORM)), 2)

    def test_item_scope_flows_into_error_message_and_resets(self) -> None:
        self.assertIsNone(current_item())
        with item_scope("frames.selftest_item"):
            self.assertEqual(current_item(), "frames.selftest_item")
            with self.assertRaises(ProjectionError) as ctx:
                as_pairs([["_Color"]], what="m_Colors")
            self.assertIn("frames.selftest_item", str(ctx.exception))
        self.assertIsNone(current_item())


if __name__ == "__main__":
    unittest.main()
