"""object_cache — 默认零 IO + 显式开启路径（纯 stdlib 模块；默认 discover 收集）。

设计 §8：三处 env 旋钮全删——`_ENABLED` 固定 False（默认零 IO 零目录）、预算固定
256 MB、kinds 固定 `("container", "typetree", "pptr")`；API 面与上游一致（模块无
显式 enable 参数，本测试直接 patch 模块常量模拟「未来显式开启」）。

本文件不得 import UnityPy（分层测试纪律：tests/core 纯单测）——被缓存对象用
fake reader，只测缓存面本身。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eidolon.core.infra import object_cache as oc


class _FakeReader:
    """最小 reader：read_typetree 每次调用计数并返回新 dict（缓存命中则不计数）。"""

    def __init__(self, payload: dict | None = None) -> None:
        self.calls = 0
        self.payload = payload if payload is not None else {"m_Name": "fake"}

    def read_typetree(self, nodes=None, wrap=False, check_read=True) -> dict:
        self.calls += 1
        return dict(self.payload)


def _hits() -> dict:
    return oc.stats()["hits"]


class DefaultDisabledTests(unittest.TestCase):
    """默认态：enabled=False，store/get 不落盘、不建目录、不驻留。"""

    def test_enabled_default_false(self) -> None:
        self.assertFalse(oc.enabled())
        for kind in ("container", "typetree", "pptr"):
            self.assertFalse(oc.kind_on(kind))
        self.assertFalse(oc.stats()["enabled"])
        self.assertEqual(oc.stats()["kinds"], ["container", "pptr", "typetree"])
        self.assertEqual(oc.stats()["budget_mb"], 256.0)

    def test_default_no_io_no_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            builds: list[str] = []

            def build():
                builds.append("container")
                return object(), "key"

            obj, ckey = oc.memo_container("b.unity3d", "ABC", build)
            self.assertEqual(builds, ["container"])   # 直接走 build，无缓存层
            self.assertEqual(ckey, "key")
            handle = oc.ObjectHandle(oc.Addr.guid("b.unity3d", "ABC"), _FakeReader())
            tree = handle.read_typetree()             # 默认关 → 直通 reader
            self.assertEqual(tree["m_Name"], "fake")
            self.assertEqual(handle.reader.calls, 1)  # 第二次读也直通（再 +1）
            handle.read_typetree()
            self.assertEqual(handle.reader.calls, 2)
            pptr_obj, pptr_pid = oc.memo_pptr("b.unity3d", "cab", 1, 7,
                                              lambda: ("obj", 7))
            self.assertEqual((pptr_obj, pptr_pid), ("obj", 7))  # 直通语义（返回 build 结果）
            self.assertEqual(oc.stats()["entries"], {"typetree": 0, "pptr": 0, "container": 0})
            # 不落盘、不建目录
            self.assertEqual(list(tmp_path.iterdir()), [])


class ExplicitEnabledTests(unittest.TestCase):
    """显式开启（patch 模块常量模拟未来显式参数）：命中 / kinds 过滤 / 容量淘汰。"""

    def setUp(self) -> None:
        oc.clear()

    def tearDown(self) -> None:
        oc.clear()

    def test_container_same_key_hits(self) -> None:
        with mock.patch.object(oc, "_ENABLED", True), \
                mock.patch.object(oc, "_KINDS", {"container", "typetree", "pptr"}):
            builds: list[str] = []

            def build():
                builds.append("x")
                return self, "guid-key"

            first = oc.memo_container("b.unity3d", "ABC", build)
            second = oc.memo_container("b.unity3d", "abc", build)   # guid 键 lower 归一
            self.assertEqual(builds, ["x"])                          # 只 build 一次
            self.assertIs(first, second)                             # 同一 handle 返回
            self.assertIsInstance(first[0], oc.ObjectHandle)
            self.assertEqual(first[1], "guid-key")                   # 实际 container 键带回

    def test_kinds_filter_excludes_disabled_kind(self) -> None:
        with mock.patch.object(oc, "_ENABLED", True), \
                mock.patch.object(oc, "_KINDS", {"typetree"}):
            builds: list[str] = []

            def build():
                builds.append("x")
                return object(), "k"

            oc.memo_container("b.unity3d", "ABC", build)
            oc.memo_container("b.unity3d", "ABC", build)
            self.assertEqual(builds, ["x", "x"])       # container 不在 kinds → 恒直通
            self.assertFalse(oc.kind_on("container"))
            self.assertTrue(oc.kind_on("typetree"))

    def test_typetree_cache_by_addr(self) -> None:
        with mock.patch.object(oc, "_ENABLED", True), \
                mock.patch.object(oc, "_KINDS", {"typetree"}):
            reader = _FakeReader()
            handle = oc.ObjectHandle(oc.Addr.guid("b.unity3d", "ABC"), reader)
            t1 = handle.read_typetree()
            t2 = handle.read_typetree()
            self.assertEqual(reader.calls, 1)          # 第二次命中缓存
            self.assertIs(t1, t2)
            # 带 nodes/wrap 参数 → 直通不缓存
            handle.read_typetree(nodes=[])
            self.assertEqual(reader.calls, 2)
            # 不同地址 → 不同键，不串
            other = oc.ObjectHandle(oc.Addr.guid("b.unity3d", "DEF"), _FakeReader())
            other.read_typetree()
            self.assertEqual(oc.stats()["entries"]["typetree"], 2)
            self.assertEqual(_hits().get("hit_typetree", 0), 1)

    def test_budget_eviction_lru(self) -> None:
        """容量淘汰：预算压到 16 KB，连塞 12 × ~4KB 条目 → LRU 逐出、预算守住。"""
        big = {"pad": "x" * 4096}
        budget = 16 * 1024
        with mock.patch.object(oc, "_ENABLED", True), \
                mock.patch.object(oc, "_KINDS", {"typetree"}), \
                mock.patch.object(oc, "_BUDGET_BYTES", budget):
            before_evict = oc.stats()["evicted"].get("evict_typetree", 0)
            for i in range(12):
                handle = oc.ObjectHandle(oc.Addr.guid("b.unity3d", f"G{i:02d}"),
                                         _FakeReader(payload=big))
                handle.read_typetree()                 # 每次入账 ~4KB 新条目
            total_bytes = oc.stats()["bytes_mb"]["typetree"] * 2**20
            self.assertLessEqual(total_bytes, budget + 8192)   # 预算守住（估算法有粒度）
            self.assertGreater(oc.stats()["evicted"].get("evict_typetree", 0), before_evict)
            self.assertLess(oc.stats()["entries"]["typetree"], 12)  # 淘汰发生过

    def test_pptr_no_cab_skips_cache_counted(self) -> None:
        with mock.patch.object(oc, "_ENABLED", True), \
                mock.patch.object(oc, "_KINDS", {"pptr"}):
            builds: list[str] = []

            def build():
                builds.append("x")
                return object(), None

            oc.memo_pptr("b.unity3d", None, 1, 7, build)   # cab 缺失：不缓存、计数
            oc.memo_pptr("b.unity3d", None, 1, 7, build)
            self.assertEqual(builds, ["x", "x"])
            self.assertEqual(oc.stats()["skip"].get("skip_pptr_no_cab", 0), 2)
            self.assertEqual(oc.stats()["entries"]["pptr"], 0)

    def test_pptr_same_cab_key_hits(self) -> None:
        with mock.patch.object(oc, "_ENABLED", True), \
                mock.patch.object(oc, "_KINDS", {"pptr"}):
            builds: list[str] = []

            def build():
                builds.append("x")
                return object(), None

            oc.memo_pptr("b.unity3d", "cab-a", 1, 7, build)
            oc.memo_pptr("b.unity3d", "CAB-A", 1, 7, build)   # cab lower 归一
            self.assertEqual(builds, ["x"])
            self.assertEqual(oc.stats()["entries"]["pptr"], 1)

    def test_clear_empties_everything(self) -> None:
        with mock.patch.object(oc, "_ENABLED", True), \
                mock.patch.object(oc, "_KINDS", {"container", "typetree", "pptr"}):
            oc.memo_container("b.unity3d", "ABC", lambda: (object(), "k"))
            oc.ObjectHandle(oc.Addr.guid("b.unity3d", "DEF"),
                            _FakeReader()).read_typetree()
            self.assertGreater(sum(oc.stats()["entries"].values()), 0)
            oc.clear()
            self.assertEqual(oc.stats()["entries"],
                             {"typetree": 0, "pptr": 0, "container": 0})


class AddrTests(unittest.TestCase):
    """带标签地址：两族键隔离 + 无默认值纪律（缺分量=响亮）。"""

    def test_guid_normalizes_and_validates(self) -> None:
        a = oc.Addr.guid("B.unity3d", "ABCDEF")
        self.assertEqual(a.kind, "guid")
        self.assertEqual(a.bundle, "B.unity3d")
        self.assertEqual(a.guid_value, "abcdef")
        with self.assertRaises(oc.MissingAddress):
            oc.Addr.guid("", "ABC")
        with self.assertRaises(oc.MissingAddress):
            oc.Addr.guid("b", "")

    def test_path_requires_cab(self) -> None:
        a = oc.Addr.path("b.unity3d", "CAB-1", 7)
        self.assertEqual(a.path_value, ("cab-1", 7))
        with self.assertRaises(oc.MissingAddress):
            oc.Addr.path("b.unity3d", "", 7)       # bundle 名不能冒充 cab

    def test_wrong_family_access_is_loud(self) -> None:
        g = oc.Addr.guid("b", "abc")
        p = oc.Addr.path("b", "cab", 1)
        with self.assertRaises(oc.MissingAddress):
            g.path_value
        with self.assertRaises(oc.MissingAddress):
            p.guid_value
        with self.assertRaises(oc.MissingAddress):
            oc.Addr("other", "b", "x")             # 未知地址族

    def test_unknown_kind_rejected(self) -> None:
        with self.assertRaises(oc.MissingAddress):
            oc.Addr("bogus", "b", "ref")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
