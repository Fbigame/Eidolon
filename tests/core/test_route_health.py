"""route 缓存健康（P0/P1）：used-hash、quick_check、单次自动重建、dirty 门。

纯合成面：tmp 航线库 + 任意字节 ``*.unity3d``；``route._bundle_tables`` 用 fake
record 替换，**不需要游戏安装**（也不解码 UnityFS；只验证 hash/DB 健康语义）。

覆盖验收点：
- stat（size/mtime_ns）不变、内容翻转 → used-hash 必须发现；
- 失配 → stale 计数/日志 + 锁内自动重建一次 → 重试通过；
- 重建后仍失配 → ``BundleContentMismatch``（响亮、不循环）；
- ``PRAGMA quick_check`` 坏库 → 删/重建一次；重建失败 → ENV
  ``route_cache_unreadable``；
- dirty 接管 = 超时**且**持有者 pid 已死（B3：活人标记不误删；旧格式回退超时
  语义；活人标记仍强制抽样）；
- ``route.stats()`` 可见 mismatch/rebuild 计数；
- 无 env / 无新 CLI（route 模块不读 ``os.environ``，无 console script）。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from eidolon.contracts import EnvironmentUnavailable

# route 顶层 import 会拖入 UnityPy；默认 discover 的 import 守卫（text_atlas /
# render_import_seams）假设默认测试不载 UnityPy。故本模块**惰性 import**，并在
# tearDownModule 清掉 UnityPy 模块，保证跑在守卫前后都不污染 sys.modules。
route = None


def tearDownModule() -> None:  # noqa: N802 —— unittest 约定钩子
    import sys

    for name in [m for m in sys.modules if m == "UnityPy" or m.startswith("UnityPy.")]:
        sys.modules.pop(name, None)


def _fake_record(path: Path) -> dict:
    """``_bundle_tables`` 的替身：只提供 build 需要的键（不解析包）。"""
    st = path.stat()
    return {
        "bundle": path.name,
        "file": {"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                 "md5": hashlib.md5(path.read_bytes()).hexdigest()},
        "blocks": [], "nodes": [],
        "cabs": {}, "objects": {}, "containers": {}, "types": {},
        "externals": {}, "header": {}, "schemas": {},
    }


class _RouteHealthCase(unittest.TestCase):
    def setUp(self) -> None:
        global route
        from eidolon.core.infra import route as _route

        route = _route
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.cache_root = self.tmp / "cache"
        self.cache_root.mkdir()
        self.data_win = self.tmp / "Data" / "Win"
        self.data_win.mkdir(parents=True)
        self.bundle = self.data_win / "a.unity3d"
        self.bundle.write_bytes(b"A" * 64)
        self._tables: list[route.Tables] = []
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
        self._tables.clear()
        route.STALE.clear()

    def _ensure(self, **override):
        tables = route.ensure(
            root=override.pop("root", self.cache_root),
            mode=override.pop("mode", "auto"),
            data_win=override.pop("data_win", self.data_win),
            version=override.pop("version", "test"),
            **override)
        if tables is not None:
            self._tables.append(tables)
        return tables

    def _flip_preserving_stat(self) -> None:
        st = self.bundle.stat()
        self.bundle.write_bytes(b"B" * len(b"A" * 64))
        os.utime(self.bundle, ns=(st.st_atime_ns, st.st_mtime_ns))
        now = self.bundle.stat()
        self.assertEqual((now.st_size, now.st_mtime_ns),
                         (st.st_size, st.st_mtime_ns))


class UsedHashTests(_RouteHealthCase):
    def test_stat_unchanged_content_flip_detected(self) -> None:
        tables = self._ensure()
        self.assertIsNotNone(tables)
        self._flip_preserving_stat()          # 首次消费前翻转（进程内已验证过则按 memo 信任）
        before = route.STATS.get("route_used_hash_mismatch", 0)
        self.assertFalse(route.verify_used("a.unity3d", tables, self.data_win))
        self.assertEqual(route.STATS.get("route_used_hash_mismatch", 0), before + 1)
        self.assertIn("a.unity3d", route.STALE)

    def test_memo_avoids_repeat_hash(self) -> None:
        tables = self._ensure()
        self.assertTrue(route.verify_used("a.unity3d", tables, self.data_win))
        before = route.STATS.get("route_used_hash_memo", 0)
        with mock.patch.object(route, "_md5_file",
                               side_effect=AssertionError("不得重复哈希")):
            self.assertTrue(route.verify_used("a.unity3d", tables, self.data_win))
        self.assertEqual(route.STATS.get("route_used_hash_memo", 0), before + 1)


class AutoRebuildTests(_RouteHealthCase):
    def test_mismatch_rebuilds_once_then_passes(self) -> None:
        tables = self._ensure()
        self._flip_preserving_stat()
        self.assertFalse(route.verify_used("a.unity3d", tables, self.data_win))
        before_stale = route.STATS.get("route_generation_stale", 0)
        before_rebuilt = route.STATS.get("route_auto_rebuilt", 0)
        with self.assertLogs("eidolon.core.infra.route", level="WARNING") as logs:
            fresh = route.heal_content_mismatch(
                "a.unity3d", tables, root=self.cache_root, mode="auto",
                data_win=self.data_win, version="test")
        self.assertTrue(any("自动重建" in line for line in logs.output))
        self._tables.append(fresh)
        self.assertIsNot(fresh, tables)
        self.assertEqual(route.STATS.get("route_generation_stale", 0), before_stale + 1)
        self.assertEqual(route.STATS.get("route_auto_rebuilt", 0), before_rebuilt + 1)
        self.assertTrue(route.verify_used("a.unity3d", fresh, self.data_win))
        counts = route.stats()
        self.assertGreaterEqual(counts.get("route_used_hash_mismatch", 0), 1)
        self.assertGreaterEqual(counts.get("route_auto_rebuilt", 0), 1)

    def test_second_heal_on_same_generation_is_loud_no_loop(self) -> None:
        tables = self._ensure()
        self._flip_preserving_stat()
        fresh = route.heal_content_mismatch(
            "a.unity3d", tables, root=self.cache_root, mode="auto",
            data_win=self.data_win, version="test")
        self._tables.append(fresh)
        with mock.patch.object(route, "build",
                               side_effect=AssertionError("不得再次重建")):
            with self.assertRaises(Exception) as caught:
                route.heal_content_mismatch(
                    "a.unity3d", fresh, root=self.cache_root, mode="auto",
                    data_win=self.data_win, version="test")
        self.assertEqual(type(caught.exception).__name__, "BundleContentMismatch")
        self.assertIn("已自动重建过一次", str(caught.exception))

    def test_rebuild_still_mismatch_loud(self) -> None:
        tables = self._ensure()
        self._flip_preserving_stat()
        stale = _fake_record(self.bundle)
        stale["file"]["md5"] = hashlib.md5(b"A" * 64).hexdigest()   # 重建写回旧内容 md5
        with mock.patch.object(route, "_bundle_tables", side_effect=lambda _p: stale):
            with self.assertRaises(Exception) as caught:
                route.heal_content_mismatch(
                    "a.unity3d", tables, root=self.cache_root, mode="auto",
                    data_win=self.data_win, version="test")
        self.assertEqual(type(caught.exception).__name__, "BundleContentMismatch")
        self.assertEqual(getattr(caught.exception, "path", None), "a.unity3d")
        self.assertIn("扫描/修复", getattr(caught.exception, "hint", ""))
        self.assertGreaterEqual(route.STATS.get("route_rebuild_still_mismatch", 0), 1)


class DbQuickCheckTests(_RouteHealthCase):
    def test_corrupt_db_rebuilt_once(self) -> None:
        (self.cache_root / route.DB_NAME).write_bytes(b"not a sqlite database")
        before_qc = route.STATS.get("route_db_quick_check_failed", 0)
        before_discard = route.STATS.get("route_db_discarded", 0)
        tables = self._ensure()
        self.assertIsNotNone(tables)
        self.assertTrue(tables.has("a.unity3d"))
        self.assertGreaterEqual(
            route.STATS.get("route_db_quick_check_failed", 0), before_qc + 1)
        self.assertGreaterEqual(
            route.STATS.get("route_db_discarded", 0), before_discard + 1)

    def test_corrupt_db_rebuild_failure_is_env(self) -> None:
        (self.cache_root / route.DB_NAME).write_bytes(b"not a sqlite database")
        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise OSError("disk on fire")

        with mock.patch.object(route, "build", side_effect=boom):
            with self.assertRaises(EnvironmentUnavailable) as caught:
                route.ensure(root=self.cache_root, mode="auto",
                             data_win=self.data_win, version="test")
        self.assertEqual(caught.exception.problem.code, "route_cache_unreadable")
        self.assertEqual(calls["n"], 1)                   # 单次，不无限重试


class DirtyMarkerTests(_RouteHealthCase):
    def test_dirty_from_other_process_forces_sample_and_is_not_cleared(self) -> None:
        tables = self._ensure()
        self.assertIsNotNone(tables)
        # Windows：旧只读 sqlite 句柄会挡重建的 os.replace；生产中同一 store 只持一个句柄。
        self._tables.remove(tables)
        tables.close()
        key = route._path_key(self.cache_root)           # noqa: SLF001
        route._DIRTY_OWNED[key] = False                  # 模拟“标记来自别人”  # noqa: SLF001
        route._HEALTH_CHECKED.discard(key)               # noqa: SLF001
        self._flip_preserving_stat()
        # 旧的健康戳会很新；但“未清洁退出”标记强制抽样，内容失配 → 单次重建
        # （标记 pid=本进程 → 接管守卫放行：自报本进程 pid 的标记出口清理本就会删）
        with mock.patch.object(route, "heal_content_mismatch",
                               wraps=route.heal_content_mismatch) as heal:
            fresh = self._ensure()
        self.assertIsNotNone(fresh)
        heal.assert_called_once()
        self.assertTrue(route.verify_used("a.unity3d", fresh, self.data_win))
        self.assertTrue((self.cache_root / route.DIRTY_NAME).exists())  # 别人的标记不删

    def test_clean_session_skips_sample(self) -> None:
        tables = self._ensure()
        self.assertIsNotNone(tables)
        key = route._path_key(self.cache_root)           # noqa: SLF001
        route._HEALTH_CHECKED.discard(key)               # noqa: SLF001
        with mock.patch.object(route, "verify_sample",
                               side_effect=AssertionError("干净会话不得抽样")):
            self.assertIsNotNone(self._ensure())


def _kill_later(proc: "subprocess.Popen[bytes]") -> None:
    """测试清理：杀掉探活用的子进程并收尸（防 pid 复用污染后续用例）。"""
    try:
        proc.kill()
    except OSError:
        pass
    proc.wait()


class DirtyClaimTests(_RouteHealthCase):
    """B3：接管判定 = 超时 **且** 持有者 pid 不存活（活人标记不误删）。

    pid 复用（死者 pid 被无关进程复用 → 误判活 → 晚接管）无法在单测里消除，
    属已知限制（见 architecture §6 已知限制；保守方向，正确性不受影响）。
    """

    def _write_marker(self, holder_pid: int | None, *, age_secs: float) -> Path:
        """伪造持有者脏标记（backdate mtime 控制年龄，不真等 5 分钟）。"""
        marker = self.cache_root / route.DIRTY_NAME
        lines = [] if holder_pid is None else [f"pid={holder_pid}"]
        lines.append(f"at={time.time():.0f}")
        marker.write_text("\n".join(lines) + "\n", encoding="utf-8")
        past = time.time() - age_secs
        os.utime(marker, (past, past))
        return marker

    def test_live_holder_not_claimed(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(_kill_later, proc)
        marker = self._write_marker(
            proc.pid, age_secs=route.DIRTY_CLAIM_SECS + 120)
        before = route.STATS.get("route_dirty_holder_alive", 0)
        route._claim_stale_dirty(self.cache_root)        # noqa: SLF001
        self.assertTrue(marker.exists())
        self.assertEqual(route.STATS.get("route_dirty_holder_alive"), before + 1)
        self.assertEqual(route._dirty_holder_pid(marker), proc.pid)   # noqa: SLF001
        # 未接管 → 本进程未占标记
        self.assertIsNone(route._DIRTY_OWNED.get(route._path_key(self.cache_root)))  # noqa: SLF001

    def test_dead_holder_claimed_and_recreated(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_pid = proc.pid
        proc.wait()
        marker = self._write_marker(
            dead_pid, age_secs=route.DIRTY_CLAIM_SECS + 120)
        before = route.STATS.get("route_dirty_marker_claimed", 0)
        route._claim_stale_dirty(self.cache_root)        # noqa: SLF001
        self.assertGreaterEqual(
            route.STATS.get("route_dirty_marker_claimed"), before + 1)
        # 接管者删旧并重建自己的标记（同路径，持有者换人）
        self.assertTrue(marker.exists())
        self.assertEqual(route._dirty_holder_pid(marker), os.getpid())  # noqa: SLF001
        self.assertNotEqual(route._dirty_holder_pid(marker), dead_pid)
        self.assertTrue(route._DIRTY_OWNED[route._path_key(self.cache_root)])  # noqa: SLF001

    def test_unparseable_pid_falls_back_to_age_semantics(self) -> None:
        # 旧格式标记（无 pid 行 / pid 行损坏）→ 按原超时语义接管（向后兼容）
        for text in ("at=1700000000\n", "pid=not-a-number\n", ""):
            with self.subTest(text=text):
                marker = self.cache_root / route.DIRTY_NAME
                marker.write_text(text, encoding="utf-8")
                past = time.time() - (route.DIRTY_CLAIM_SECS + 120)
                os.utime(marker, (past, past))
                before = route.STATS.get("route_dirty_marker_claimed", 0)
                route._claim_stale_dirty(self.cache_root)   # noqa: SLF001
                self.assertGreaterEqual(
                    route.STATS.get("route_dirty_marker_claimed"), before + 1)
                # 接管成功：同路径标记已是本进程的
                self.assertEqual(route._dirty_holder_pid(marker), os.getpid())  # noqa: SLF001
                marker.unlink(missing_ok=True)

    def test_fresh_marker_not_claimed_even_if_holder_dead(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_pid = proc.pid
        proc.wait()
        marker = self._write_marker(dead_pid, age_secs=1.0)   # 未超时
        before = route.STATS.get("route_dirty_marker_claimed", 0)
        route._claim_stale_dirty(self.cache_root)             # noqa: SLF001
        self.assertTrue(marker.exists())
        self.assertEqual(route.STATS.get("route_dirty_marker_claimed"), before)

    def test_gate_samples_but_spares_live_holder_marker(self) -> None:
        """门级接线：活人标记仍强制抽样（崩溃检测不放松），但不接管删除。"""
        tables = self._ensure()
        self.assertIsNotNone(tables)
        self._tables.remove(tables)
        tables.close()
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(_kill_later, proc)
        marker = self.cache_root / route.DIRTY_NAME
        marker.write_text(f"pid={proc.pid}\nat={time.time():.0f}\n", encoding="utf-8")
        past = time.time() - (route.DIRTY_CLAIM_SECS + 120)
        os.utime(marker, (past, past))
        key = route._path_key(self.cache_root)            # noqa: SLF001
        route._DIRTY_OWNED[key] = False                   # noqa: SLF001
        route._HEALTH_CHECKED.discard(key)                # noqa: SLF001
        with mock.patch.object(route, "verify_sample",
                               wraps=route.verify_sample) as vs:
            fresh = self._ensure()
        self.assertIsNotNone(fresh)
        vs.assert_called_once()                           # 强制抽样仍发生
        self.assertTrue(marker.exists())                  # 活人标记未被接管
        self.assertEqual(route._dirty_holder_pid(marker), proc.pid)   # noqa: SLF001


class ManifestLocaleUsedHashTests(_RouteHealthCase):
    """resolve 的 manifest/locale 包：库里有行就同路 used-hash（P0）。"""

    def _ctx(self):
        return types.SimpleNamespace(route_cache=self.cache_root, route_mode="auto",
                                     version="test")

    def test_manifest_row_mismatch_auto_rebuilds(self) -> None:
        from eidolon.core.infra import resolve_asset_ref

        manifest = self.data_win / "asset_manifest.unity3d"
        manifest.write_bytes(b"M" * 32)
        tables = self._ensure()
        self.assertIsNotNone(tables)
        self._tables.remove(tables)
        tables.close()
        st = manifest.stat()
        manifest.write_bytes(b"N" * 32)
        os.utime(manifest, ns=(st.st_atime_ns, st.st_mtime_ns))
        before = route.STATS.get("route_auto_rebuilt", 0)
        with mock.patch.object(resolve_asset_ref.context, "installed",
                               return_value=self._ctx()):
            index = resolve_asset_ref.ManifestIndex(self.data_win)
            index._route_used_hash(manifest)     # noqa: SLF001
        self.assertEqual(route.STATS.get("route_auto_rebuilt", 0), before + 1)


class HealthSampleApiTests(_RouteHealthCase):
    """P1：内部 verify_sample / verify_all 支持抽样与全量（不接 render/CLI）。"""

    def test_sample_and_full_report(self) -> None:
        tables = self._ensure()
        sample = route.verify_sample(tables, self.data_win, n=1)
        self.assertEqual(sample["checked"], 1)
        self.assertEqual(sample["mismatched"], [])
        self._flip_preserving_stat()
        route._VERIFIED.clear()             # 模拟新进程（进程内 memo 按 stat 键信任）  # noqa: SLF001
        sample2 = route.verify_sample(tables, self.data_win, n=1)
        self.assertEqual(sample2["mismatched"], ["a.unity3d"])
        full = route.verify_all(tables, self.data_win)
        self.assertEqual(full["kind"], "full")
        self.assertIn("a.unity3d", full["mismatched"])
        self.assertGreaterEqual(route.stats().get("route_health_sample_runs", 0), 1)
        self.assertGreaterEqual(route.stats().get("route_health_full_runs", 0), 1)


class RefreshModeTests(_RouteHealthCase):
    """P1：显式 refresh 仍是全量重建（不被 health 门短路）。"""

    def test_refresh_always_rebuilds(self) -> None:
        first = self._ensure(mode="auto")
        self.assertIsNotNone(first)
        self._tables.remove(first)
        first.close()
        before = route.STATS.get("route_built", 0)
        second = self._ensure(mode="refresh")
        self.assertIsNotNone(second)
        self.assertEqual(route.STATS.get("route_built", 0), before + 1)


class NoEnvNoCliTests(unittest.TestCase):
    def test_route_module_has_no_env_access(self) -> None:
        from eidolon.core.infra import route as route_mod

        src = Path(route_mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("os.environ", src)
        self.assertNotIn("os.getenv", src)

    def test_no_route_console_script(self) -> None:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if not pyproject.is_file():                       # pragma: no cover
            self.skipTest("pyproject.toml 不在仓内")
        text = pyproject.read_text(encoding="utf-8")
        self.assertNotIn("eidolon-route", text)
        self.assertNotIn("route =", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
