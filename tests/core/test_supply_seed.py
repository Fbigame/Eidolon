"""core/supply/machine pending seed（A2 S1 seam）单测——零游戏、零会话产物。

判据面（任务单 A2「pending seed 不泄漏」）：嵌套 ``seed_session``、重复
``session()`` 调用、异常路径下 pending 均被消费/清除，不跨会话泄漏；
``in_session`` 语义不变；无 seed 路径逐位不变。机制证明用 ``machine.item``
包计数函数：命中种子 memo 的 token 直接返回种子值、域函数体零执行
（served 的查键点即 memo 命中；未命中 token 照旧 live）。

setUp/tearDown 双向断言 pending/会话为 None：前例泄漏在此响亮（防串台，
兼作跨用例泄漏守卫）。
"""

from __future__ import annotations

import unittest


def _machine():
    """惰性装载 machine。

    本模块 collection 期不得拖 UnityPy（machine→resolve_asset_ref 顶层
    ``import UnityPy``）：``test_render_import_seams`` 的轻 import 断言依赖
    discover 全量收集后 ``sys.modules`` 干净——顶层 import 会在收集期污染，
    故 machine 只在用例执行期（setUp/方法体）装载。"""
    import eidolon.core.supply.machine as m

    return m


class SeedHygieneCase(unittest.TestCase):
    """公共底座：setUp 装载 machine；每例前后 pending / 会话必须为 None
    （前例泄漏在此响亮）。"""

    def setUp(self) -> None:
        self.m = _machine()
        self.assertIsNone(self.m._pending_seed.get())
        self.assertIsNone(self.m._s_current.get())

    def tearDown(self) -> None:
        self.assertIsNone(self.m._pending_seed.get())
        self.assertIsNone(self.m._s_current.get())


class PendingSeedLeakTests(SeedHygieneCase):
    """pending seed 消费/清除纪律（任务单 A2 泄漏判据）。"""

    def test_no_seed_session_unchanged(self) -> None:
        """无 seed：逐位不变——空 memo、in_session 正常进出。"""
        with self.m.session():
            self.assertTrue(self.m.in_session())
            self.assertEqual(self.m._s_current.get().memo, {})
        self.assertFalse(self.m.in_session())

    def test_first_session_consumes_pending(self) -> None:
        """进入 session() 即消费 pending：memo 预填、pending 清零。"""
        seeds = {("t", "x", (1,)): "seeded"}
        with self.m.seed_session(seeds):
            self.assertEqual(self.m._pending_seed.get(), seeds)
            with self.m.session():
                self.assertIsNone(self.m._pending_seed.get())   # 消费即清
                self.assertEqual(self.m._s_current.get().memo, dict(seeds))
        self.assertIsNone(self.m._pending_seed.get())

    def test_repeated_session_no_reseed(self) -> None:
        """同一 seed_session 内重复 session()：只种首个，后续空 memo。"""
        seeds = {("t", "x", (1,)): "seeded"}
        with self.m.seed_session(seeds):
            with self.m.session():
                self.assertEqual(self.m._s_current.get().memo, dict(seeds))
            with self.m.session():
                self.assertEqual(self.m._s_current.get().memo, {})   # 不重种
        self.assertIsNone(self.m._pending_seed.get())

    def test_nested_seed_innermost_wins_outer_restored(self) -> None:
        """嵌套：内层遮蔽外层（首个 session 消费内层）；内层出口后外层恢复
        可见（栈式遮蔽，seed_session docstring 契约）；全出口后无残留。"""
        a = {("t", "a", ()): "A"}
        b = {("t", "b", ()): "B"}
        with self.m.seed_session(a):
            with self.m.seed_session(b):
                with self.m.session():
                    self.assertEqual(self.m._s_current.get().memo, dict(b))
            self.assertEqual(self.m._pending_seed.get(), a)   # 外层恢复
            with self.m.session():
                self.assertEqual(self.m._s_current.get().memo, dict(a))
        self.assertIsNone(self.m._pending_seed.get())

    def test_exception_inside_session_consumed_and_cleared(self) -> None:
        """会话体内异常：pending 已消费不复活，后续会话空 memo。"""
        seeds = {("t", "x", (1,)): "seeded"}
        with self.m.seed_session(seeds):
            with self.assertRaises(RuntimeError):
                with self.m.session():
                    raise RuntimeError("boom")
            self.assertIsNone(self.m._pending_seed.get())    # 已消费
            with self.m.session():
                self.assertEqual(self.m._s_current.get().memo, {})   # 不重种
        self.assertIsNone(self.m._pending_seed.get())

    def test_exception_in_seed_session_clears_pending(self) -> None:
        """seed_session 体内异常：出口复位，无残留进后续会话。"""
        seeds = {("t", "x", (1,)): "seeded"}
        with self.assertRaises(RuntimeError):
            with self.m.seed_session(seeds):
                raise RuntimeError("boom")
        self.assertIsNone(self.m._pending_seed.get())
        with self.m.session():
            self.assertEqual(self.m._s_current.get().memo, {})   # 无泄漏

    def test_unconsumed_seed_no_residue(self) -> None:
        """作用域内无 session：出口复位，无残留。"""
        with self.m.seed_session({("t", "x", (1,)): "seeded"}):
            self.assertFalse(self.m.in_session())   # seed_session 不开会话
        with self.m.session():
            self.assertEqual(self.m._s_current.get().memo, {})

    def test_seed_session_does_not_activate_in_session(self) -> None:
        """``in_session`` 语义不变：只认 ``_s_current``，不认 pending。"""
        self.assertFalse(self.m.in_session())
        with self.m.seed_session({}):
            self.assertFalse(self.m.in_session())
        with self.m.session():
            self.assertTrue(self.m.in_session())

    def test_memo_is_copy_not_alias(self) -> None:
        """会话 memo=种子 dict 的浅拷贝：会话写面不回流种子。"""
        seeds = {("t", "x", (1,)): "seeded"}
        with self.m.seed_session(seeds):
            with self.m.session():
                memo = self.m._s_current.get().memo
                self.assertIsNot(memo, seeds)
                self.assertEqual(memo, seeds)
                memo["injected"] = 1
        self.assertEqual(seeds, {("t", "x", (1,)): "seeded"})


class SeedServedMechanismTests(SeedHygieneCase):
    """机制证明：@item served 命中种子 memo → 域函数体不执行（计数器观测）。"""

    def setUp(self) -> None:
        super().setUp()
        calls: list[int] = []

        @self.m.item("test", "probe")
        def probe(x: int) -> str:
            calls.append(x)
            return f"live:{x}"

        self.probe = probe
        self.calls = calls

    def test_seeded_token_served_from_memo(self) -> None:
        """命中 token：返回种子值、域函数零执行；未命中 token 照旧 live。"""
        seeds = {("test", "probe", (7,)): "seeded-7"}
        with self.m.seed_session(seeds):
            with self.m.session():
                self.assertEqual(self.probe(7), "seeded-7")
                self.assertEqual(self.calls, [])             # 域函数体零执行
                self.assertEqual(self.probe(8), "live:8")    # 未命中→live
                self.assertEqual(self.calls, [8])

    def test_unseeded_token_live(self) -> None:
        """无种子：token 走 live 域函数（无 seed 路径逐位不变）。"""
        with self.m.session():
            self.assertEqual(self.probe(7), "live:7")
            self.assertEqual(self.calls, [7])

    def test_seed_is_one_shot_across_sessions(self) -> None:
        """消费后同 token 再查：第二会话重新解码（不重种）。"""
        seeds = {("test", "probe", (7,)): "seeded-7"}
        with self.m.seed_session(seeds):
            with self.m.session():
                self.assertEqual(self.probe(7), "seeded-7")
            with self.m.session():
                self.assertEqual(self.probe(7), "live:7")    # 第二会话不命中
                self.assertEqual(self.calls, [7])


if __name__ == "__main__":
    unittest.main()
