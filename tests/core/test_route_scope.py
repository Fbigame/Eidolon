"""route scoped 库（B 案）：scoped build / prewarm / 缺行 lazy 补行 单测（2026-11-10）。

零游戏文件：tmp 缓存根 + 任意字节 ``*.unity3d`` + 假 ``_bundle_tables``（每包产一个
cab，不解析 UnityFS）；``test_route_cabs`` / ``test_route_health`` 同风格（惰性
import + tearDownModule 清 UnityPy）。真实语料由集成门覆盖。

覆盖面（B1 任务单判据）：
- scoped build 只建清单内包的行 + meta ``scope``/``scope_bundles`` 如实记账；
  清单缺文件显式计数（``route_scope_bundle_missing``）；
- 全量 build 记 ``scope=full``（旧库无键=full 兼容面）；
- 建库后旧 JSON 清理**只认 ``route*.json``**（cache root 与 supply index 同根
  共存——b1 实测 `*.json` 全量 glob 会删 index 的 current.json）；
- ``prewarm``：无库 → scoped 建；已有有效库（全量/scoped）→ hit 不重建；
  版本换代 → 同 scope 重建（不静默升全量）；off/空清单 → 不建；
- ``ensure`` auto 换代继承 ``scope_bundles``（scoped 库不被静默升级）；
- ``heal_content_mismatch`` 同 scope 重建；scoped 库的 lazy 补行包（不在
  ``scope_bundles``）优先**原位刷新该行**（保留其它补行、不换库），失败/仍失配
  才回退 ``scope_bundles + [bundle]`` 同 scope 重建，仍失配则响亮；
- ``augment_row``：scoped 库缺行补行（bundles/parts/cabs/schemas 并入，
  ``has`` 即真）；全量库拒绝；锁忙/解析失败显式计数不抛；
- ``BundleStore.open_bundle`` 接线：缺行 → augment 调用 + 成功走 route 路 /
  拒绝走惰性兜底（``route_row_missing`` 计数）。

树根跑：``python -m unittest tests.core.test_route_scope``
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# route / resolve_asset_ref 顶层 import 会拖入 UnityPy；默认 discover 的 import
# 守卫（text_atlas / render_import_seams）假设默认测试不载 UnityPy。故本模块
# **惰性 import**，并在 tearDownModule 清掉 UnityPy 模块（同 test_route_health 纪律）。
route = None
R = None


def tearDownModule() -> None:  # noqa: N802 —— unittest 约定钩子
    import sys

    for name in [m for m in sys.modules if m == "UnityPy" or m.startswith("UnityPy.")]:
        sys.modules.pop(name, None)


def _fake_record(path: Path) -> dict:
    """``_bundle_tables`` 替身：每包产一个 cab（cab-<stem>），不解析 UnityFS。"""
    st = path.stat()
    cab = "cab-" + path.stem.lower()
    return {
        "bundle": path.name,
        "file": {"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                 "md5": hashlib.md5(path.read_bytes()).hexdigest()},
        "blocks": [], "nodes": [[0, 0, 0, cab]],
        "cabs": {cab: path.name},
        "objects": {}, "containers": {}, "types": {},
        "externals": {}, "header": {}, "schemas": {},
    }


class _RouteScopeCase(unittest.TestCase):
    def setUp(self) -> None:
        global route, R
        from eidolon.core.infra import resolve_asset_ref as _r
        from eidolon.core.infra import route as _route

        route = _route
        R = _r
        route.STATS.clear()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.cache_root = self.tmp / "cache"
        self.cache_root.mkdir()
        self.data_win = self.tmp / "Data" / "Win"
        self.data_win.mkdir(parents=True)
        self._tables: list[object] = []
        route.STALE.clear()
        self._bundle_patch = mock.patch.object(
            route, "_bundle_tables", side_effect=_fake_record)
        self._bundle_patch.start()
        self.addCleanup(self._bundle_patch.stop)

    def tearDown(self) -> None:
        for tables in self._tables:
            try:
                tables.close()
            except Exception:                          # noqa: BLE001
                pass
        route.STATS.clear()

    # ---- 辅助 ----

    def bundle(self, name: str, content: bytes = b"") -> Path:
        p = self.data_win / name
        p.write_bytes(content)
        return p

    def build(self, *, bundles: list[str] | None = None, version: str | None = None) -> dict:
        return route.build(self.cache_root, data_win=self.data_win,
                           version=version, bundles=bundles)

    def load(self, *, version: str | None = None):
        tables = route._load(self.cache_root, data_win=self.data_win, version=version)
        self._tables.append(tables)
        return tables

    def db_meta(self) -> dict:
        db = self.cache_root / route.DB_NAME
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            return {k: json.loads(v)
                    for k, v in conn.execute("SELECT key, value FROM meta")}
        finally:
            conn.close()

    def track(self, tables) -> None:
        self._tables.append(tables)


class ScopedBuildTests(_RouteScopeCase):
    """``build(bundles=...)``：只建清单行 + scope meta 记账 + 清理 glob 收窄。"""

    def test_scoped_build_only_listed_bundles(self) -> None:
        for name in ("a.unity3d", "b.unity3d", "c.unity3d"):
            self.bundle(name, b"X" * 8)
        meta = self.build(bundles=["b.unity3d", "a.unity3d"])

        self.assertEqual(meta["scope"], "cards")
        self.assertEqual(meta["scope_bundles"], ["a.unity3d", "b.unity3d"])
        self.assertEqual(meta["n_bundles"], 2)
        tables = self.load()
        self.assertEqual(tables.names(), {"a.unity3d", "b.unity3d"})
        self.assertFalse(tables.has("c.unity3d"))          # 清单外未建
        conn = sqlite3.connect(self.cache_root / route.DB_NAME)
        self.addCleanup(conn.close)
        self.assertEqual(dict(conn.execute("SELECT cab,bundle FROM cabs")),
                         {"cab-a": "a.unity3d", "cab-b": "b.unity3d"})
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM parts").fetchone()[0], 2 * len(route.PARTS))

    def test_full_build_records_scope_full(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        meta = self.build()
        self.assertEqual(meta["scope"], "full")
        self.assertNotIn("scope_bundles", meta)

    def test_scoped_build_missing_file_counted(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        meta = self.build(bundles=["a.unity3d", "ghost.unity3d"])
        self.assertEqual(meta["n_bundles"], 1)
        self.assertEqual(route.STATS.get("route_scope_bundle_missing"), 1)

    def test_cleanup_narrowed_to_route_json(self) -> None:
        """cache root 与 supply index 同根：``current.json`` 等外来 JSON 不清理。"""
        self.bundle("a.unity3d", b"A" * 8)
        (self.cache_root / "current.json").write_text("{}", encoding="utf-8")
        (self.cache_root / "other.json").write_text("{}", encoding="utf-8")
        (self.cache_root / "route.json").write_text("{}", encoding="utf-8")
        self.build()
        self.assertTrue((self.cache_root / "current.json").is_file(),
                        "supply index 的 current.json 被清理 glob 误删（b1 实测险情）")
        self.assertTrue((self.cache_root / "other.json").is_file())
        self.assertFalse((self.cache_root / "route.json").is_file(),
                         "v3 时代 route JSON 布局残留应被清理")


class PrewarmTests(_RouteScopeCase):
    """``prewarm``：无库 scoped 建 / 命中不重建 / 换代同 scope / off 不建。"""

    def test_prewarm_builds_scoped_when_missing(self) -> None:
        for name in ("a.unity3d", "b.unity3d", "c.unity3d"):
            self.bundle(name, b"X" * 8)
        tables = route.prewarm(root=self.cache_root, mode="auto",
                               data_win=self.data_win, bundles=["a.unity3d"])
        self.track(tables)
        self.assertIsNotNone(tables)
        self.assertEqual(tables.meta["scope"], "cards")
        self.assertEqual(tables.names(), {"a.unity3d"})
        self.assertEqual(route.STATS.get("route_built"), 1)

    def test_prewarm_hit_skips_rebuild(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        self.build()
        built_before = route.STATS.get("route_built", 0)
        tables = route.prewarm(root=self.cache_root, mode="auto",
                               data_win=self.data_win, bundles=["a.unity3d"])
        self.track(tables)
        self.assertEqual(tables.meta["scope"], "full")     # 命中现有库，不重建
        self.assertEqual(route.STATS.get("route_built"), built_before)
        self.assertEqual(route.STATS.get("route_prewarm_hit"), 1)

    def test_prewarm_version_mismatch_rebuilds_same_scope(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        self.bundle("b.unity3d", b"B" * 8)
        self.build(bundles=["a.unity3d"], version="37.0.0.111")
        tables = route.prewarm(root=self.cache_root, mode="auto",
                               data_win=self.data_win, version="37.0.0.222",
                               bundles=["a.unity3d", "b.unity3d"])
        self.track(tables)
        # 版本换代触发重建（1 次），且按调用方清单（scoped），不升全量
        self.assertEqual(tables.meta["scope"], "cards")
        self.assertEqual(tables.meta["n_bundles"], 2)
        self.assertEqual(route.STATS.get("route_built"), 2)

    def test_prewarm_off_mode_noop(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        self.assertIsNone(route.prewarm(root=self.cache_root, mode="off",
                                        data_win=self.data_win,
                                        bundles=["a.unity3d"]))
        self.assertFalse((self.cache_root / route.DB_NAME).is_file())
        self.assertIsNone(route.prewarm(root=self.cache_root, mode="auto",
                                        data_win=self.data_win, bundles=[]))
        self.assertFalse((self.cache_root / route.DB_NAME).is_file())


class EnsureScopeTests(_RouteScopeCase):
    """``ensure``（auto）换代/自愈：scoped 库同 scope 重建，不静默升全量。"""

    def test_auto_version_mismatch_inherits_scope(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        self.bundle("b.unity3d", b"B" * 8)
        self.build(bundles=["a.unity3d"], version="37.0.0.111")
        tables = route.ensure(root=self.cache_root, mode="auto",
                              data_win=self.data_win, version="37.0.0.222")
        self.track(tables)
        self.assertIsNotNone(tables)
        self.assertEqual(tables.meta["scope"], "cards")
        self.assertEqual(tables.meta["n_bundles"], 1)
        self.assertEqual(route.STATS.get("route_built"), 2)   # 建库 1 + 换代重建 1
        self.assertEqual(tables.meta["scope_bundles"], ["a.unity3d"])

    def test_refresh_rebuilds_full(self) -> None:
        """显式 refresh=全量（scoped → 全量的升级路径）。"""
        self.bundle("a.unity3d", b"A" * 8)
        self.bundle("b.unity3d", b"B" * 8)
        self.build(bundles=["a.unity3d"])
        tables = route.ensure(root=self.cache_root, mode="refresh",
                              data_win=self.data_win, version=None)
        self.track(tables)
        self.assertEqual(tables.meta["scope"], "full")
        self.assertEqual(tables.meta["n_bundles"], 2)

    def test_heal_rebuilds_same_scope(self) -> None:
        """used-hash 失配 heal：按 ``scope_bundles`` 同 scope 重建。"""
        b = self.bundle("a.unity3d", b"A" * 8)
        self.build(bundles=["a.unity3d"])
        tables = self.load()
        b.write_bytes(b"TAMPERED")                         # 蓝屏/bit rot 形态
        self.assertFalse(route.verify_used("a.unity3d", tables, self.data_win))
        fresh = route.heal_content_mismatch("a.unity3d", tables,
                                            root=self.cache_root, mode="auto",
                                            data_win=self.data_win)
        self.track(fresh)
        self.assertEqual(fresh.meta["scope"], "cards")
        self.assertEqual(fresh.meta["scope_bundles"], ["a.unity3d"])
        self.assertTrue(route.verify_used("a.unity3d", fresh, self.data_win))


class HealLazyRowTests(_RouteScopeCase):
    """heal 边界：scoped 库的 lazy 补行包（不在 ``scope_bundles``）也纳入 heal。

    原位刷新优先（保留其它 lazy 行、不换库）；原位失败 → 同 scope 重建，重建
    清单 = ``scope_bundles + [bundle]``（去重保序）；源真坏仍响亮失败。
    """

    def _scoped_with_lazy(self, *names: str):
        self.bundle("a.unity3d", b"A" * 8)
        paths = [self.bundle(name, bytes([66 + i]) * 8)
                 for i, name in enumerate(names)]
        self.build(bundles=["a.unity3d"])
        tables = self.load()
        for path in paths:
            self.assertTrue(route.augment_row(tables, path))
        self.assertEqual(tables.meta["scope_bundles"], ["a.unity3d"])
        return tables, paths

    def test_heal_refreshes_lazy_row_in_place(self) -> None:
        """回归：b 是 augment 补的、不在 scope_bundles——heal 不得假失配。"""
        tables, (b, c) = self._scoped_with_lazy("b.unity3d", "c.unity3d")
        b.write_bytes(b"B" * 16)                        # 正常更新 → used-hash 失配
        self.assertFalse(route.verify_used("b.unity3d", tables, self.data_win))
        c_md5 = tables.fingerprint("c.unity3d")["md5"]
        before_built = route.STATS.get("route_built", 0)

        fresh = route.heal_content_mismatch(
            "b.unity3d", tables, root=self.cache_root, mode="auto",
            data_win=self.data_win)
        self.track(fresh)
        self.assertIs(fresh, tables)                    # 原位刷新：不重建、不换库
        self.assertEqual(route.STATS.get("route_built"), before_built)
        self.assertEqual(route.STATS.get("route_auto_rebuilt", 0), 0)
        self.assertEqual(route.STATS.get("route_heal_inplace"), 1)
        # 其它 lazy 行保留；b 行刷新；used-hash 通过
        self.assertTrue(fresh.has("b.unity3d"))
        self.assertTrue(fresh.has("c.unity3d"))
        self.assertEqual(fresh.fingerprint("c.unity3d")["md5"], c_md5)
        self.assertTrue(route.verify_used("b.unity3d", fresh, self.data_win))
        # 原位刷新不改 scope 身份（同 augment_row：meta 仍记初始工作集）
        self.assertEqual(fresh.meta["scope"], "cards")
        self.assertEqual(fresh.meta["scope_bundles"], ["a.unity3d"])

    def test_heal_inplace_failure_falls_back_to_rebuild_with_lazy_bundle(self) -> None:
        """原位刷新不可用 → 回退重建，重建 scope 并入该 lazy 包（不丢、不升全量）。"""
        tables, (b,) = self._scoped_with_lazy("b.unity3d")
        b.write_bytes(b"B" * 16)
        with mock.patch.object(route, "augment_row", return_value=False):
            fresh = route.heal_content_mismatch(
                "b.unity3d", tables, root=self.cache_root, mode="auto",
                data_win=self.data_win)
        self.track(fresh)
        self.assertIsNot(fresh, tables)
        self.assertEqual(route.STATS.get("route_heal_inplace_declined"), 1)
        self.assertEqual(route.STATS.get("route_auto_rebuilt"), 1)
        self.assertEqual(fresh.meta["scope"], "cards")
        self.assertEqual(fresh.meta["scope_bundles"],
                         ["a.unity3d", "b.unity3d"])    # 初始工作集 + 该 lazy 包
        self.assertTrue(route.verify_used("b.unity3d", fresh, self.data_win))

    def test_heal_inplace_still_mismatch_falls_back_and_is_loud(self) -> None:
        """原位刷新写入的行仍对不上盘上内容 → 回退重建后仍失配 → 响亮，不吞。"""
        tables, (b,) = self._scoped_with_lazy("b.unity3d")
        b.write_bytes(b"B" * 16)
        stale = _fake_record(b)                          # 源真坏：行 md5 是旧内容
        stale["file"]["md5"] = hashlib.md5(b"B" * 8).hexdigest()
        with mock.patch.object(route, "_bundle_tables", return_value=stale):
            with self.assertRaises(Exception) as caught:
                route.heal_content_mismatch(
                    "b.unity3d", tables, root=self.cache_root, mode="auto",
                    data_win=self.data_win)
        self.assertEqual(type(caught.exception).__name__, "BundleContentMismatch")
        self.assertEqual(getattr(caught.exception, "path", None), "b.unity3d")
        self.assertEqual(route.STATS.get("route_heal_inplace_declined"), 1)
        self.assertGreaterEqual(
            route.STATS.get("route_rebuild_still_mismatch", 0), 1)

    def test_heal_lazy_row_source_missing_still_loud(self) -> None:
        """lazy 行源文件缺失：原位刷新/重建都无法入册 → 响亮失败（不是假失配）。"""
        tables, (b,) = self._scoped_with_lazy("b.unity3d")
        b.unlink()
        with self.assertRaises(Exception) as caught:
            route.heal_content_mismatch(
                "b.unity3d", tables, root=self.cache_root, mode="auto",
                data_win=self.data_win)
        self.assertEqual(type(caught.exception).__name__, "BundleContentMismatch")
        self.assertEqual(getattr(caught.exception, "path", None), "b.unity3d")
        self.assertIn("仍失配/未入册", str(caught.exception))
        self.assertGreaterEqual(
            route.STATS.get("route_heal_inplace_declined", 0), 1)
        self.assertGreaterEqual(
            route.STATS.get("route_scope_bundle_missing", 0), 1)
        self.assertGreaterEqual(
            route.STATS.get("route_rebuild_still_mismatch", 0), 1)


class HealthGateMultiMismatchTests(_RouteScopeCase):
    """健康门多失配：逐个修（scoped lazy 原位 / full 单次 rebuild），不假失败。"""

    def _scoped_with_lazy(self, *names: str):
        self.bundle("a.unity3d", b"A" * 8)
        paths = [self.bundle(name, bytes([66 + i]) * 8)
                 for i, name in enumerate(names)]
        self.build(bundles=["a.unity3d"])
        tables = self.load()
        for path in paths:
            self.assertTrue(route.augment_row(tables, path))
        self.assertEqual(tables.meta["scope_bundles"], ["a.unity3d"])
        return tables, paths

    def _gate(self, tables):
        key = route._path_key(self.cache_root)          # noqa: SLF001
        route._HEALTH_CHECKED.discard(key)              # noqa: SLF001
        with mock.patch.object(route, "_health_due", return_value=(True, False)):
            fresh = route._health_gate(
                tables, rt=self.cache_root, root=self.cache_root, mode="auto",
                data_win=self.data_win, version=None, limit=None)
        self.track(fresh)
        return fresh

    def test_gate_heals_all_lazy_mismatches_in_place(self) -> None:
        """回归：b、c 两个 lazy 行同时失配 → 逐个原位刷新，不假失败。"""
        tables, (b, c, d) = self._scoped_with_lazy(
            "b.unity3d", "c.unity3d", "d.unity3d")
        b.write_bytes(b"B" * 16)                        # 正常更新，两个 lazy 包同时失配
        c.write_bytes(b"C" * 16)
        d_md5 = tables.fingerprint("d.unity3d")["md5"]
        before_built = route.STATS.get("route_built", 0)

        fresh = self._gate(tables)

        self.assertIs(fresh, tables)                    # 原位刷新：不重建、不换库
        self.assertEqual(route.STATS.get("route_built", 0), before_built)
        self.assertEqual(route.STATS.get("route_auto_rebuilt", 0), 0)
        self.assertEqual(route.STATS.get("route_heal_inplace"), 2)
        self.assertTrue(route.verify_used("b.unity3d", fresh, self.data_win))
        self.assertTrue(route.verify_used("c.unity3d", fresh, self.data_win))
        # b/c 之外的 lazy 行仍在（原位刷新只动失配行）
        self.assertTrue(fresh.has("d.unity3d"))
        self.assertEqual(fresh.fingerprint("d.unity3d")["md5"], d_md5)
        self.assertEqual(fresh.meta["scope"], "cards")
        self.assertEqual(fresh.meta["scope_bundles"], ["a.unity3d"])

    def test_gate_full_library_multi_mismatch_rebuilds_once(self) -> None:
        """full 库对照：多个失配 → 一次全量 rebuild 修好，行为不变。"""
        for name in ("a", "b", "c", "d"):
            self.bundle(f"{name}.unity3d", name.upper().encode() * 8)
        self.build()                                    # full（scope=full）
        tables = self.load()
        (self.data_win / "b.unity3d").write_bytes(b"B" * 16)
        (self.data_win / "c.unity3d").write_bytes(b"C" * 16)
        before_built = route.STATS.get("route_built", 0)

        fresh = self._gate(tables)

        self.assertIsNot(fresh, tables)                 # 一次 rebuild 换库
        self.assertEqual(route.STATS.get("route_built", 0), before_built + 1)
        self.assertEqual(route.STATS.get("route_auto_rebuilt"), 1)
        self.assertEqual(route.STATS.get("route_heal_inplace", 0), 0)
        self.assertTrue(route.verify_used("b.unity3d", fresh, self.data_win))
        self.assertTrue(route.verify_used("c.unity3d", fresh, self.data_win))
        self.assertEqual(fresh.meta["scope"], "full")

    def test_gate_true_bad_lazy_row_still_loud(self) -> None:
        """真坏：b 源内容对不上 → 原位/rebuild 都修不好 → 响亮，不静默。"""
        tables, (b, c) = self._scoped_with_lazy("b.unity3d", "c.unity3d")
        b.write_bytes(b"B" * 16)
        c.write_bytes(b"C" * 16)
        stale = _fake_record(b)                         # 源真坏：行 md5 是旧内容
        stale["file"]["md5"] = hashlib.md5(b"B" * 8).hexdigest()

        def _fake(path: Path) -> dict:
            return stale if path.name == "b.unity3d" else _fake_record(path)

        with mock.patch.object(route, "_bundle_tables", side_effect=_fake):
            with self.assertRaises(Exception) as caught:
                self._gate(tables)

        self.assertEqual(type(caught.exception).__name__, "BundleContentMismatch")
        self.assertEqual(getattr(caught.exception, "path", None), "b.unity3d")
        self.assertIn("b.unity3d", str(caught.exception))
        self.assertGreaterEqual(route.STATS.get("route_heal_inplace_declined", 0), 1)
        self.assertGreaterEqual(route.STATS.get("route_rebuild_still_mismatch", 0), 1)


class AugmentTests(_RouteScopeCase):
    """``augment_row``：scoped 库缺行 lazy 补行；全量库拒绝；失败显式计数。"""

    def test_augment_adds_missing_row(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        b = self.bundle("b.unity3d", b"B" * 8)
        self.build(bundles=["a.unity3d"])
        tables = self.load()
        self.assertFalse(tables.has("b.unity3d"))

        self.assertTrue(route.augment_row(tables, b))
        self.assertTrue(tables.has("b.unity3d"))
        parts = tables.parts("b.unity3d")
        self.assertIsNotNone(parts)
        self.assertEqual(set(parts), set(route.PARTS))
        self.assertEqual(tables.cab_owner("cab-b"), "b.unity3d")
        self.assertEqual(route.STATS.get("route_augment_built"), 1)
        # 记账面：meta 仍是 scoped（补行不改 scope 身份）
        self.assertEqual(tables.meta["scope"], "cards")

    def test_augment_refused_on_full_scope(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        self.build()                                        # 全量（含所有现有包）
        b = self.bundle("b.unity3d", b"B" * 8)              # 建库后新出现的包=缺行
        tables = self.load()
        self.assertFalse(tables.has("b.unity3d"))
        self.assertFalse(route.augment_row(tables, b))
        self.assertFalse(tables.has("b.unity3d"))
        self.assertEqual(route.STATS.get("route_augment_skip_full"), 1)

    def test_augment_lock_busy_declines(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        b = self.bundle("b.unity3d", b"B" * 8)
        self.build(bundles=["a.unity3d"])
        tables = self.load()
        lock = self.cache_root / route.LOCK_NAME
        lock.mkdir()                                        # 别人持有建库锁
        self.assertFalse(route.augment_row(tables, b))
        self.assertFalse(tables.has("b.unity3d"))
        self.assertEqual(route.STATS.get("route_augment_lock_busy"), 1)

    def test_augment_parse_failure_is_explicit(self) -> None:
        self.bundle("a.unity3d", b"A" * 8)
        self.build(bundles=["a.unity3d"])
        tables = self.load()
        self.assertFalse(route.augment_row(tables, self.data_win / "ghost.unity3d"))
        self.assertEqual(route.STATS.get("route_augment_parse_failed"), 1)
        self.assertEqual(route.STATS.get("route_augment_failed", 0), 0)


class StoreWiringTests(_RouteScopeCase):
    """``BundleStore.open_bundle`` 接线：缺行 → augment → route 路 / 惰性兜底。"""

    def _store(self, fake):
        store = R.BundleStore(self.data_win)
        store._route = fake                                 # noqa: SLF001 —— 同模块单测
        return store

    def test_open_bundle_augments_then_routes(self) -> None:
        b = self.bundle("b.unity3d", b"B" * 8)
        names: set[str] = set()
        fake = SimpleNamespace(has=lambda bundle: bundle in names,
                               meta={"scope": "cards"}, fingerprint=lambda _: None)
        store = self._store(fake)
        env = SimpleNamespace(sentinel="route-env", files={})

        def _augment(tables, path):
            names.add(path.name)
            return True

        with mock.patch.object(route, "augment_row", side_effect=_augment) as m_aug, \
                mock.patch.object(route, "verify_used", return_value=True), \
                mock.patch.object(route, "open_env", return_value=env), \
                mock.patch.object(R.bundle_lazy, "LazyBundle", return_value=object()):
            got = store.open_bundle("b.unity3d")

        self.assertIs(got, env)                             # route 路（非惰性兜底）
        self.assertEqual(route.STATS.get("route_row_missing"), 1)
        self.assertEqual(m_aug.call_count, 1)
        self.assertEqual(store._route_bundles.get("b.unity3d") is not None, True)

    def test_open_bundle_declined_augment_falls_back_lazy(self) -> None:
        b = self.bundle("b.unity3d", b"B" * 8)
        fake = SimpleNamespace(has=lambda _: False,
                               meta={"scope": "full"}, fingerprint=lambda _: None)
        store = self._store(fake)
        lazy_env = SimpleNamespace(sentinel="lazy-env", files={})
        with mock.patch.object(route, "augment_row", return_value=False) as m_aug, \
                mock.patch.object(R.bundle_lazy, "open_env", return_value=lazy_env):
            got = store.open_bundle("b.unity3d")

        self.assertIs(got, lazy_env)                        # 惰性兜底（缺行不假命中）
        self.assertEqual(route.STATS.get("route_row_missing"), 1)
        self.assertEqual(m_aug.call_count, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
