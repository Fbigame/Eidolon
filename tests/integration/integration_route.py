"""integration_route — route.py 三态/布局/指纹（显式跑；只依赖 UnityPy，不依赖游戏）。

默认 discover（pattern ``test*.py``）**不收集**本文件；显式跑：
    python -m unittest discover -s tests/integration -p 'integration_*.py' -t . -v

fake data_win（垃圾字节 ``*.unity3d``，与 cache_root 分离）+ tmp cache_root：
``build`` 对单包解析失败按包跳过（计数留账）但 meta 照写——正好隔离出
「布局/三态/版本身份/指纹」的纯库面。``Tables`` 持有 sqlite 连接（Windows 文件
锁），tearDown 统一 close 后才允许 tmp 清理。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import eidolon.core.infra.route as route
from eidolon.core.infra.route import DB_NAME, ensure


def _fake_data_win(root: Path) -> tuple[Path, Path, bytes]:
    """fake Data/Win：一个非 UnityFS 的 ``*.unity3d``（build 逐包跳过、meta 照写）。"""
    data_win = root / "Data" / "Win"
    data_win.mkdir(parents=True)
    payload = b"NOT-UNITYFS-" + os.urandom(64)
    bundle = data_win / "fake.unity3d"
    bundle.write_bytes(payload)
    return data_win, bundle, payload


class _RouteCase(unittest.TestCase):
    """公共夹具：cache_root 与 data_win 同属一个 tmp 但互相分离；Tables 收口 close。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.cache_root = root / "cache"
        self.cache_root.mkdir()
        self.data_win, self.bundle, self.payload = _fake_data_win(root / "data")
        self._open_tables: list[route.Tables] = []
        route.STALE.clear()

    def tearDown(self) -> None:
        for tables in self._open_tables:
            tables.close()
        self._open_tables.clear()
        route.STALE.clear()

    def _ensure(self, **override):
        tables = ensure(root=override.pop("root", self.cache_root),
                        data_win=override.pop("data_win", self.data_win),
                        version=override.pop("version", "test"),
                        **override)
        if tables is not None:
            self._open_tables.append(tables)
        return tables


class RouteThreeStateTests(_RouteCase):
    """三态语义 + route.db 布局（每测试独立 tmp，互不串缓存）。"""

    def test_off_builds_nothing(self) -> None:
        self.assertIsNone(self._ensure(mode="off"))
        self.assertEqual(list(self.cache_root.iterdir()), [])   # 无库、无锁、无目录

    def test_auto_builds_route_db_at_cache_root(self) -> None:
        tables = self._ensure(mode="auto")
        self.assertIsNotNone(tables)
        db = self.cache_root / DB_NAME
        self.assertTrue(db.is_file())                            # 建立位置=缓存根
        self.assertFalse((self.cache_root / (DB_NAME + ".build")).exists())
        # meta：键 + 版本身份（version="test" → game_build="test"）
        self.assertEqual(tables.meta["format"], route.ROUTE_FORMAT)
        self.assertEqual(tables.meta["unitypy"], route.UnityPy.__version__)
        self.assertEqual(tables.meta["game_build"], "test")
        self.assertEqual(tables.meta["game_manifest"], route.game_id(self.data_win))
        self.assertEqual(tables.meta["n_bundles"], 0)            # 垃圾包被逐包跳过
        self.assertGreaterEqual(tables.meta["built_at"], 1)      # epoch 秒
        self.assertGreaterEqual(route.stats().get("route_build_bundle_failed", 0), 1)
        self.assertFalse((self.cache_root / route.LOCK_NAME).exists())   # 锁清理干净

    def test_auto_second_call_hits_without_rebuild(self) -> None:
        first = self._ensure(mode="auto")
        built_before = route.stats().get("route_built", 0)
        second = self._ensure(mode="auto")
        self.assertIsNotNone(second)
        self.assertEqual(route.stats().get("route_built", 0), built_before)  # 命中不重建
        self.assertEqual(second.meta["built_at"], first.meta["built_at"])

    def test_version_mismatch_triggers_rebuild(self) -> None:
        first = self._ensure(mode="auto")
        first_built_at = first.meta["built_at"]
        # 旧读者先关（Windows sqlite 句柄挡 os.replace；生产里版本身份每进程固定，
        # 重建只发生在无旧读者或新进程——测试内同构：先关再重建）。
        self._open_tables.remove(first)
        first.close()
        built_before = route.stats().get("route_built", 0)
        second = self._ensure(mode="auto", version="other")      # 身份不符 → 重建
        self.assertIsNotNone(second)
        self.assertEqual(route.stats().get("route_built", 0), built_before + 1)
        self.assertEqual(second.meta["game_build"], "other")
        self.assertGreaterEqual(second.meta["built_at"], first_built_at)  # epoch 秒粒度

    def test_version_verdict_matrix(self) -> None:
        """版本身份判定（纯函数面）：hit / mismatch / unknown 三态全矩阵。

        `unknown` 语义=当前身份不可读**绝不**判不符（否则版本探测失败会每次重建）。
        """
        verdict = route._version_verdict
        # 旧库无版本键 + 当前可读 → 不符（首跑自动重建升级旧库）
        self.assertEqual(verdict({}, {"game_build": "x", "game_manifest": "y"}), "mismatch")
        # 旧库无版本键 + 当前不可读 → unknown（不判不符）
        self.assertEqual(verdict({}, {"game_build": "", "game_manifest": ""}), "unknown")
        # build 精确比对
        self.assertEqual(verdict({"game_build": "x"},
                                 {"game_build": "x", "game_manifest": ""}), "hit")
        self.assertEqual(verdict({"game_build": "x"},
                                 {"game_build": "y", "game_manifest": ""}), "mismatch")
        # 半旧库（有 manifest 无 build）→ manifest 兜底
        self.assertEqual(verdict({"game_build": None, "game_manifest": "m"},
                                 {"game_build": "", "game_manifest": "m"}), "hit")
        self.assertEqual(verdict({"game_build": None, "game_manifest": "m"},
                                 {"game_build": "", "game_manifest": "n"}), "mismatch")
        # 当前身份完全不可读 → unknown，绝不误重建
        self.assertEqual(verdict({"game_build": "x"},
                                 {"game_build": "", "game_manifest": ""}), "unknown")
        self.assertEqual(verdict({"game_build": "x", "game_manifest": "m"},
                                 {"game_build": "", "game_manifest": ""}), "unknown")

    def test_no_cache_uses_pid_dir_not_cache_root(self) -> None:
        expected_tmp = self.cache_root / f"_no_cache_route_{os.getpid()}"
        self.assertEqual(route._tmp_root(self.cache_root), expected_tmp)     # 命名含 pid
        tables = self._ensure(mode="no-cache")
        self.assertIsNotNone(tables)
        self.assertTrue((expected_tmp / DB_NAME).is_file())                  # 库落在 pid 目录
        self.assertFalse((self.cache_root / DB_NAME).exists())               # 缓存根不落 route.db
        self.assertEqual([p.name for p in self.cache_root.iterdir()],
                         [expected_tmp.name])                                # 根下只有 pid 目录
        # no-cache 恒重建（天然不命中语义）；旧读者先关（同 test_version_mismatch 的锁账）
        self._open_tables.remove(tables)
        tables.close()
        built_before = route.stats().get("route_built", 0)
        self._ensure(mode="no-cache")
        self.assertGreaterEqual(route.stats().get("route_built", 0), built_before + 1)


class FingerprintRoundtripTests(_RouteCase):
    """指纹记账面：fingerprint / verify（stat 快路 + md5 路）/ touch roundtrip。

    build 逐包跳过垃圾包 ⟹ 库里无 bundles 行；这里按真实 API 面手工入一行
    （stat + md5 用同一文件真值），再走 ensure(auto) → Tables 的公开查询面。
    """

    def setUp(self) -> None:
        super().setUp()
        self._ensure(mode="auto")
        st = self.bundle.stat()
        self.row = {"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                    "md5": hashlib.md5(self.payload).hexdigest()}
        conn = sqlite3.connect(self.cache_root / DB_NAME)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO bundles(name,size,mtime_ns,md5) VALUES(?,?,?,?)",
                ("fake.unity3d", self.row["size"], self.row["mtime_ns"], self.row["md5"]))
            conn.commit()
        finally:
            conn.close()

    def _fresh_tables(self) -> route.Tables:
        tables = self._ensure(mode="auto")
        self.assertIsNotNone(tables)
        return tables

    def test_fingerprint_read(self) -> None:
        tables = self._fresh_tables()
        self.assertTrue(tables.has("fake.unity3d"))
        self.assertIn("fake.unity3d", tables.names())
        self.assertEqual(tables.fingerprint("fake.unity3d"), self.row)
        self.assertIsNone(tables.fingerprint("absent.unity3d"))   # 缺行 → None

    def test_verify_stat_fast_path(self) -> None:
        tables = self._fresh_tables()
        before = route.stats().get("route_verify_fast", 0)
        self.assertTrue(route.verify("fake.unity3d", tables, self.data_win))
        self.assertEqual(route.stats().get("route_verify_fast", 0), before + 1)
        self.assertNotIn("fake.unity3d", route.STALE)

    def test_verify_md5_same_touches_row(self) -> None:
        tables = self._fresh_tables()
        # 内容相同、只动 mtime → stat 快路失配 → md5 路 → 相同 → touch 写回
        new_mtime = self.row["mtime_ns"] + 1_000
        os.utime(self.bundle, ns=(new_mtime, new_mtime))
        before = route.stats().get("route_verify_md5_same", 0)
        self.assertTrue(route.verify("fake.unity3d", tables, self.data_win))
        self.assertEqual(route.stats().get("route_verify_md5_same", 0), before + 1)
        self.assertEqual(tables.fingerprint("fake.unity3d")["mtime_ns"], new_mtime)
        self.assertNotIn("fake.unity3d", route.STALE)

    def test_verify_md5_diff_marks_stale(self) -> None:
        tables = self._fresh_tables()
        # 内容不同（同 size）→ md5 失配 → 该包失效，调用方退回惰性
        os.utime(self.bundle, ns=(self.row["mtime_ns"] + 5_000,) * 2)
        self.bundle.write_bytes(b"x" * self.row["size"])
        before = route.stats().get("route_stale", 0)
        self.assertFalse(route.verify("fake.unity3d", tables, self.data_win))
        self.assertEqual(route.stats().get("route_stale", 0), before + 1)
        self.assertIn("fake.unity3d", route.STALE)

    def test_verify_missing_row_fails_loud_counted(self) -> None:
        tables = self._fresh_tables()
        before = route.stats().get("route_verify_missing", 0)
        self.assertFalse(route.verify("absent.unity3d", tables, self.data_win))
        self.assertEqual(route.stats().get("route_verify_missing", 0), before + 1)
        self.assertNotIn("absent.unity3d", route.STALE)           # 缺行≠内容失配，不进 STALE
        # off 语义：tables=None → False（调用方不走航线）
        self.assertFalse(route.verify("absent.unity3d", None, self.data_win))

    def test_touch_writes_back_without_md5(self) -> None:
        tables = self._fresh_tables()
        tables.touch("fake.unity3d", self.row["size"], self.row["mtime_ns"] + 42)
        self.assertEqual(tables.fingerprint("fake.unity3d")["mtime_ns"],
                         self.row["mtime_ns"] + 42)


class RouteHealthIntegrationTests(_RouteCase):
    """缓存健康（真实 sqlite/ensure 面，不 mock）：坏库 quick_check → 重建一次。"""

    def test_corrupt_db_quick_check_rebuilt_once(self) -> None:
        first = self._ensure(mode="auto")
        self.assertIsNotNone(first)
        self._open_tables.remove(first)
        first.close()
        db = self.cache_root / DB_NAME
        db.write_bytes(b"this is not a sqlite route database")
        before_qc = route.stats().get("route_db_quick_check_failed", 0)
        before_discard = route.stats().get("route_db_discarded", 0)
        rebuilt = self._ensure(mode="auto")
        self.assertIsNotNone(rebuilt)
        self.assertTrue(db.is_file())
        self.assertGreaterEqual(
            route.stats().get("route_db_quick_check_failed", 0), before_qc + 1)
        self.assertGreaterEqual(
            route.stats().get("route_db_discarded", 0), before_discard + 1)
        self.assertFalse((self.cache_root / route.LOCK_NAME).exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
