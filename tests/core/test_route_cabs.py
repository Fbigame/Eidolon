"""route v6 全局 cabs 表 + ``_resolve_pptr`` 接线单测（2026-11-09）。

参考实现同族用例改写成 Eidolon 风格；
零游戏文件：临时 SQLite / 假 ``_bundle_tables`` / 假 env，真实语料由集成门覆盖。

上游 8 例的映射：
- cab_owner 命中/miss/归一、旧 v5 缺表 → 本文件同款（Eidolon 计数名 ``route_cab_*``）；
- build 写全局 cabs、parts 无 cabs 行 → 同款（并入多包汇总断言）；
- ``_lookup_cab_owner`` 计数、``_resolve_pptr`` 只开 owner 包、miss 回 dep 扫描 →
  同款（Eidolon 无 cabmap：查表只有 route 一源，``_route=None`` 也算 miss）；
- 上游 2 例 cabmap（``build_cab_index`` header-only / cabmap 与 full build 集合对拍）
  **不搬**——产品没有 cabmap/CLI，miss 走 ``bundle_deps`` 兜底；
- 补 Eidolon 显式计数面：cab_owner 空键 / 读错误（``route_cab_owner_empty`` /
  ``route_cab_lookup_failed``）。

树根跑：``python -m unittest tests.core.test_route_cabs``
"""

from __future__ import annotations

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


def _route_db(path: Path, *, with_cabs: bool = True) -> sqlite3.Connection:
    """临时航线库：``with_cabs=False`` 模拟旧 v5 布局（无全局 cabs 表）。"""
    conn = sqlite3.connect(path)
    if with_cabs:
        conn.executescript(route._SCHEMA)              # noqa: SLF001 —— 同模块单测
    else:
        conn.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE bundles (name TEXT PRIMARY KEY, size INTEGER NOT NULL,
                                  mtime_ns INTEGER NOT NULL, md5 TEXT NOT NULL);
            CREATE TABLE parts (bundle TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
                                PRIMARY KEY (bundle, kind)) WITHOUT ROWID;
            CREATE TABLE schemas (hash TEXT PRIMARY KEY, payload TEXT NOT NULL) WITHOUT ROWID;
        """)
    return conn


class _RouteCabsCase(unittest.TestCase):
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

    def tearDown(self) -> None:
        route.STATS.clear()


class CabOwnerTests(_RouteCabsCase):
    """``Tables.cab_owner``：v6 全局表的读面（归一 / miss / 缺表 / 读错）。"""

    def test_hit_miss_and_normalization(self) -> None:
        db = self.tmp / "route.db"
        conn = _route_db(db)
        conn.execute("INSERT INTO cabs(cab,bundle) VALUES(?,?)", ("cab-aaa", "b1.unity3d"))
        conn.commit()
        tables = route.Tables(conn, {}, db)
        self.addCleanup(tables.close)

        self.assertEqual(tables.cab_owner("cab-aaa"), "b1.unity3d")
        self.assertEqual(tables.cab_owner("CAB-AAA"), "b1.unity3d")
        self.assertEqual(tables.cab_owner("archive:/CAB-AAA/CAB-AAA"), "b1.unity3d")
        self.assertIsNone(tables.cab_owner("cab-missing"))
        self.assertEqual(route.STATS.get("route_cab_owner_hit"), 3)
        self.assertEqual(route.STATS.get("route_cab_owner_miss"), 1)

    def test_old_v5_missing_table(self) -> None:
        db = self.tmp / "route.db"
        conn = _route_db(db, with_cabs=False)
        tables = route.Tables(conn, {}, db)
        self.addCleanup(tables.close)

        self.assertFalse(tables._has_cabs)             # noqa: SLF001 —— 同模块单测
        self.assertIsNone(tables.cab_owner("cab-aaa"))
        self.assertEqual(route.STATS.get("route_cab_table_missing"), 1)

    def test_empty_key_and_lookup_failure_are_explicit(self) -> None:
        db = self.tmp / "route.db"
        conn = _route_db(db)
        tables = route.Tables(conn, {}, db)
        self.addCleanup(tables.close)

        self.assertIsNone(tables.cab_owner(""))
        self.assertIsNone(tables.cab_owner("archive:///"))
        self.assertEqual(route.STATS.get("route_cab_owner_empty"), 2)
        tables._conn.close()                           # noqa: SLF001 —— 模拟读错误
        self.assertIsNone(tables.cab_owner("cab-aaa"))
        self.assertEqual(route.STATS.get("route_cab_lookup_failed"), 1)


class BuildGlobalCabsTests(_RouteCabsCase):
    """build：rec["cabs"] 汇总写全局表；parts 不再有 cabs 行。"""

    @staticmethod
    def _fake_tables(path: Path) -> dict:
        """``_bundle_tables`` 替身：每包产一个 cab（cab-<stem>），不解析 UnityFS。"""
        cab = "cab-" + path.stem.lower()
        return {
            "bundle": path.name,
            "file": {"size": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns,
                     "md5": "0" * 32},
            "blocks": [], "nodes": [[0, 0, 0, cab]],
            "cabs": {cab: path.name},
            "objects": {}, "containers": {}, "types": {},
            "externals": {}, "header": {}, "schemas": {},
        }

    def test_build_writes_global_cabs_not_parts(self) -> None:
        for name in ("b1.unity3d", "b2.unity3d"):
            (self.tmp / name).write_bytes(b"")
        with mock.patch.object(route, "_bundle_tables",
                               side_effect=self._fake_tables):
            meta = route.build(self.tmp, data_win=self.tmp, version=None)

        self.assertEqual(meta["format"], route.ROUTE_FORMAT)
        self.assertEqual(meta["n_cabs"], 2)
        conn = sqlite3.connect(self.tmp / route.DB_NAME)
        self.addCleanup(conn.close)
        self.assertEqual(dict(conn.execute("SELECT cab,bundle FROM cabs")),
                         {"cab-b1": "b1.unity3d", "cab-b2": "b2.unity3d"})
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM parts WHERE kind='cabs'").fetchone()[0], 0)
        # 2 包 × 7 部件（v6：PARTS 去掉 cabs，8→7）
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0], 14)


class ResolvePptrTests(_RouteCabsCase):
    """``_resolve_pptr`` 查询序：route cabs → 命中只开 owner 包 → miss 回 dep 扫描。"""

    def _store(self, *, owner_bundle: str | None, deps: dict | None = None):
        store = R.BundleStore(Path("."))
        store._route = SimpleNamespace(cab_owner=lambda _cab: owner_bundle)
        store._index = SimpleNamespace(bundle_deps=deps or {})
        return store

    def test_lookup_uses_route_table_only(self) -> None:
        store = self._store(owner_bundle="b1.unity3d")
        self.assertEqual(store._lookup_cab_owner("cab-a"), "b1.unity3d")  # noqa: SLF001
        self.assertEqual(route.STATS.get("cab_owner_hit"), 1)

        store2 = self._store(owner_bundle=None)
        self.assertIsNone(store2._lookup_cab_owner("cab-z"))              # noqa: SLF001
        self.assertEqual(route.STATS.get("cab_owner_miss"), 1)
        # route off（_route=None）没有第二兜底源：同样 miss 计数，调用方走 deps
        store3 = self._store(owner_bundle="b1.unity3d")
        store3._route = None
        self.assertIsNone(store3._lookup_cab_owner("cab-a"))              # noqa: SLF001
        self.assertEqual(route.STATS.get("cab_owner_miss"), 2)

    def test_resolve_pptr_opens_owner_only(self) -> None:
        store = self._store(owner_bundle="owner.unity3d")
        ext = SimpleNamespace(path="archive:/CAB-X/CAB-X")
        own_sf = SimpleNamespace(name="CAB-CUR", externals=[ext], objects={})
        owner_sf = SimpleNamespace(name="CAB-X", externals=[], objects={123: "obj"})
        cur_env = SimpleNamespace(sfs=[own_sf])
        owner_env = SimpleNamespace(sfs=[owner_sf])

        def _open(bundle):
            return {"cur.unity3d": cur_env, "owner.unity3d": owner_env}[bundle]

        with mock.patch.object(store, "open_bundle", side_effect=_open), \
                mock.patch.object(R, "_iter_serialized", lambda env: iter(env.sfs)):
            res, bundle = store._resolve_pptr(
                "cur.unity3d", {"m_FileID": 1, "m_PathID": 123},
                owner_obj=SimpleNamespace(assets_file=own_sf))

        self.assertEqual((res, bundle), ("obj", "owner.unity3d"))
        self.assertEqual(route.STATS.get("cab_owner_hit"), 1)
        self.assertEqual(route.STATS.get("cab_owner_open"), 1)
        self.assertNotIn("dep_scan_opens", route.STATS)

    def test_resolve_pptr_miss_falls_back_to_dep_scan(self) -> None:
        store = self._store(owner_bundle=None, deps={"cur.unity3d": ["dep.unity3d"]})
        ext = SimpleNamespace(path="archive:/CAB-X/CAB-X")
        own_sf = SimpleNamespace(name="CAB-CUR", externals=[ext], objects={})
        cur_env = SimpleNamespace(sfs=[own_sf])
        dep_sf = SimpleNamespace(name="CAB-X", externals=[], objects={123: "obj2"})
        dep_env = SimpleNamespace(sfs=[dep_sf])

        def _open(bundle):
            if bundle == "dep.unity3d":
                # 真 open_bundle 会在驻留时登记 CAB 归属；这里同形模拟
                store._cabs_owner.setdefault("cab-x", "dep.unity3d")
                return dep_env
            return cur_env

        with mock.patch.object(store, "open_bundle", side_effect=_open), \
                mock.patch.object(R, "_iter_serialized", lambda env: iter(env.sfs)):
            res, bundle = store._resolve_pptr(
                "cur.unity3d", {"m_FileID": 1, "m_PathID": 123},
                owner_obj=SimpleNamespace(assets_file=own_sf))

        self.assertEqual((res, bundle), ("obj2", "dep.unity3d"))
        self.assertEqual(route.STATS.get("cab_owner_miss"), 1)
        self.assertEqual(route.STATS.get("dep_scan_opens"), 1)
        self.assertEqual(route.STATS.get("dep_scan_depth"), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
