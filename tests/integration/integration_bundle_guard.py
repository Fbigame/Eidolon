"""integration_bundle_guard — bundle_lazy / bundle_guard 坏盘读防护矩阵。

合成 UnityFS 包矩阵（2026-11-08 判据卡 4 件的
离线面，27 例）：lz4 真压缩流 + 动态必炸点定位，零游戏
文件、零真实语料 + 注入坏字节 + mock 注入瞬时读故障。

默认 discover（pattern ``test*.py``）**不收集**本文件（UnityPy / lz4 依赖）；
显式跑：
    python -m unittest discover -s tests/integration -p 'integration_bundle_guard.py' -t . -v

**纯合成面：不依赖游戏安装（不设 EIDOLON_TEST_GAME）**。

移植映射（上游 27 例 → 产品 27 例；编号对应上游类.用例）：

- BlockCorruptTests 5 例全移植（typed error 全上下文 / 瞬时读恰 1 次重试 /
  二次坏响亮禁循环 / open_env typed 直通 / 干净零重试）；
- GuardHashTests：off 零 IO 直通、显式 expected 过/响亮、route 信任门
  （可信行激活哈希轴 / stat 不符不采信 / md5 非法 / 行缺失）5 例移植，
  ``no_route`` 期望值并入 off 直通用例；
- GuardFallbackTests 6 例全移植（三验全过采纳留账 / md5 不过拒 / 缺失拒 /
  布局不等拒 / 无好副本源响亮 / route 行账 + 显式 good_dir 回退）；
- GuardLoadTests 4 例全移植（load 快照+同遍 hash：off 直读 / 过 / 响亮 /
  好副本回退）；
- LoadDefendedTests 3 例全移植（惰性优先 / 坏块 typed 直通不退老路 /
  LazyUnsupported 退老路留账）；
- **设计性删除 2 例**：上游 ``ModeKnobTests.test_modes`` 与
  ``GuardHashTests.test_mode_invalid_loud``——Eidolon 产品面删除了 guard
  模式 / 好副本目录的 env 旋钮（bundle_guard docstring「启用面」节），上游
  经 ``os.environ[KNOB]`` 启用的用例改写成显式参数等价（见各用例注记），
  ``mode()`` 解析器本身已不存在，无对象可测；
- **产品新增 2 例**（budget 面，任务 P1-8 要求）：单包解压块 LRU 预算
  （``LazyBundle(budget=)`` 显式参数）淘汰最旧块后重读仍正确 / budget=0
  不限全缓存。
"""

from __future__ import annotations

import gc
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lz4.block as lz4block

from eidolon.core.infra import bundle_guard as BG
from eidolon.core.infra import bundle_lazy as BL

_LZ4_FLAG = 2          # CompressionFlags.LZ4
_PLAIN = b"A" * 4 + b"B" * 4 + b"A" * 40        # 有重复面 → 压缩流含 match（必炸点存在）
_PAYLOAD = lz4block.compress(_PLAIN, store_size=False)


def _raising_offset() -> int:
    """最小必炸偏移：翻坏该字节后 lz4 拒解（match offset/token 等结构位）。

    LZ4 注记（上游实测入账）：单字节翻坏**不必然**炸解码——字面量区的翻坏
    会静默出错字节；必炸点=结构位。lz4 行为随版本漂移，故动态定位而非写死。
    """
    for k in range(len(_PAYLOAD)):
        bad = bytearray(_PAYLOAD)
        bad[k] ^= 0x01
        try:
            lz4block.decompress(bytes(bad), uncompressed_size=len(_PLAIN))
        except Exception:
            return k
    raise AssertionError("压缩流内无必炸偏移？!（lz4 行为漂移）")


_RAISE_OFF = _raising_offset()


def _write_bundle(path: Path, blocks, nodes) -> None:
    """blocks=[(payload, uc, flags)]; nodes=[(off, size, flags, path)]。

    blocksInfo 不压缩（flags=0）、文件头 version=6（无对齐）、info 在头后。
    """
    info = bytearray()
    info += b"\x00" * 16                                   # uncompressedDataHash（实测全零面）
    info += struct.pack(">I", len(blocks))
    for payload, uc, flags in blocks:
        info += struct.pack(">IIH", uc, len(payload), flags)
    info += struct.pack(">I", len(nodes))
    for off, size, nflags, npath in nodes:
        info += struct.pack(">qqI", off, size, nflags) + npath.encode() + b"\x00"
    data = b"".join(p for p, _uc, _f in blocks)
    head = (b"UnityFS\x00" + struct.pack(">I", 6) + b"0.0.0\x00" + b"6000.3.11f1\x00")
    size = len(head) + 8 + 12 + len(info) + len(data)
    head += struct.pack(">q", size) + struct.pack(">III", len(info), len(info), 0)
    path.write_bytes(bytes(head) + bytes(info) + data)


def _make_bundle(path: Path, *, corrupt_at: int | None = None,
                 nblocks: int = 1) -> Path:
    """合成包；corrupt_at 给定时注入块内坏字节（必炸点）。

    nblocks=2 是 budget 用例的双块变体（内容可区分：X*64 / Y*64）。
    """
    if nblocks == 1:
        payload = bytearray(_PAYLOAD)
        if corrupt_at is not None:
            payload[corrupt_at] ^= 0x01
        _write_bundle(path,
                      blocks=[(bytes(payload), len(_PLAIN), _LZ4_FLAG)],
                      nodes=[(0, len(_PLAIN), 0, "CAB-test")])
        return path
    assert corrupt_at is None and nblocks == 2
    _write_bundle(path,
                  blocks=[(lz4block.compress(b"X" * 64, store_size=False), 64, _LZ4_FLAG),
                          (lz4block.compress(b"Y" * 64, store_size=False), 64, _LZ4_FLAG)],
                  nodes=[(0, 128, 0, "CAB-test")])
    return path


def _bl_delta(key: str, fn) -> int:
    """bundle_lazy 计数器增量（诊断遥测面是模块级 Counter）。"""
    before = BL.stats().get(key, 0)
    fn()
    return BL.stats().get(key, 0) - before


def _bg_delta(key: str, fn) -> int:
    """bundle_guard 计数器增量。"""
    before = BG.STATS.get(key, 0)
    fn()
    return BG.STATS.get(key, 0) - before


class _FakeTables:
    """route.Tables 鸭子替身（fingerprint 行账可编）。"""

    def __init__(self, row):
        self._row = row

    def fingerprint(self, bundle):
        return self._row


def _md5(p: Path) -> str:
    return BG.md5_file(p)


class _GuardCase(unittest.TestCase):
    """公共夹具：每例独立 tmp + bundle_guard 计数清零 + mmap/env 收口。

    Windows 文件锁：LazyBundle 持 mmap，env（open_env / load_defended 路）
    经 ``_lazy_bundles`` 持 mmap——tearDown 显式收口后才允许 tmp 清理。
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        BG.STATS.clear()
        self._bundles: list = []
        self._envs: list = []

    def tearDown(self) -> None:
        for br in self._bundles:
            try:
                br.close()
            except Exception:                              # noqa: BLE001 —— 已关/重复关容忍
                pass
        for env in self._envs:
            BL.close_env(env)
        self._bundles.clear()
        self._envs.clear()
        gc.collect()

    def track(self, lazy_bundle):
        self._bundles.append(lazy_bundle)
        return lazy_bundle

    def track_env(self, env):
        self._envs.append(env)
        return env

    def make_bundle(self, name: str, **kwargs) -> Path:
        return _make_bundle(self.tmp / name, **kwargs)

    def loud(self):
        """guard 警告捕获上下文（「留账不静默」：警告必须真发 logger）。"""
        return self.assertLogs("eidolon.core.infra.bundle_guard", level="WARNING")


# ---------------------------------------------------------------------------
# bundle_lazy：坏块 typed error + 单次重试（判据卡第 1/2 件）
# ---------------------------------------------------------------------------

class BlockCorruptTests(_GuardCase):
    def setUp(self) -> None:
        super().setUp()
        self.clean = self.make_bundle("clean.unity3d")
        self.br = self.track(BL.LazyBundle(self.clean))

    def test_clean_roundtrip_no_retry(self) -> None:
        """干净数据零行为：块解压结果正确、零重试、零 typed error。"""
        self.assertEqual(self.br.read(0, len(_PLAIN)), _PLAIN)
        self.assertEqual(self.br._block(0), _PLAIN)        # noqa: SLF001
        self.assertEqual(_bl_delta("block_retry_recovered", lambda: None), 0)
        self.assertEqual(_bl_delta("block_corrupt", lambda: None), 0)

    def test_injection_typed_error_full_context(self) -> None:
        """注入必红：单字节翻坏（结构位）→ typed error 含 bundle/块号/物理偏移/uc/cs/flags。"""
        self.br.close()
        bad = self.make_bundle("inject_bad.unity3d", corrupt_at=_RAISE_OFF)
        br = self.track(BL.LazyBundle(bad))
        with self.assertRaises(BL.BundleBlockCorruptError) as cm:
            br._block(0)                                   # noqa: SLF001
        msg = str(cm.exception)
        self.assertIn(str(bad), msg)                       # bundle 路径
        self.assertIn("block=0", msg)                      # 块号
        self.assertIn(f"phys={br.blocks_start}", msg)      # 物理偏移
        self.assertIn(f"uc={len(_PLAIN)}", msg)
        self.assertIn(f"cs={len(_PAYLOAD)}", msg)
        self.assertIn("flags=0x2", msg)                    # LZ4
        self.assertIn("LZ4BlockError", msg)                # 原始异常
        self.assertEqual(_bl_delta("block_retry_recovered", lambda: None), 0)

    def test_transient_read_retried_once(self) -> None:
        """瞬时读：首坏次好 → 恰 1 次重试成功，计数 +1，总读恰 2 次。"""
        orig = BL.LazyBundle._read_raw
        calls = {"n": 0}

        def flaky(self_br, phys, cs):
            calls["n"] += 1
            raw = orig(self_br, phys, cs)
            if calls["n"] == 1:
                bad = bytearray(raw)
                bad[_RAISE_OFF] ^= 0x01
                return bytes(bad)
            return raw

        with mock.patch.object(BL.LazyBundle, "_read_raw", flaky):
            out = _bl_delta(
                "block_retry_recovered",
                lambda: self.assertEqual(self.br.read(0, len(_PLAIN)), _PLAIN))
        self.assertEqual(out, 1)                       # 计数器 +1
        self.assertEqual(calls["n"], 2)                # 恰一次重试（两读）

    def test_second_failure_loud_no_loop(self) -> None:
        """二次仍坏 → 响亮（typed error），恰 2 次读，禁循环。"""
        orig = BL.LazyBundle._read_raw
        calls = {"n": 0}

        def always_bad(self_br, phys, cs):
            calls["n"] += 1
            raw = bytearray(orig(self_br, phys, cs))
            raw[_RAISE_OFF] ^= 0x01
            return bytes(raw)

        with mock.patch.object(BL.LazyBundle, "_read_raw", always_bad):
            with self.assertRaises(BL.BundleBlockCorruptError):
                self.br._block(0)                      # noqa: SLF001
        self.assertEqual(calls["n"], 2)                # 恰两读——无第三读（禁循环）
        self.assertEqual(_bl_delta("block_retry_recovered", lambda: None), 0)

    def test_open_env_raises_typed(self) -> None:
        """加载路（open_env）撞坏块同样 typed 响亮——禁静默出图、禁退化成 LazyUnsupported。"""
        self.br.close()
        bad = self.make_bundle("inject_env.unity3d", corrupt_at=_RAISE_OFF)
        with self.assertRaises(BL.BundleBlockCorruptError):
            BL.open_env(bad)


# ---------------------------------------------------------------------------
# bundle_lazy：单包解压块 LRU 预算（显式参数面；上游 27 例之外的产品补充）
# ---------------------------------------------------------------------------

class BudgetTests(_GuardCase):
    def test_small_budget_evicts_oldest_and_rereads(self) -> None:
        """预算 1B：读块 1 后最旧的块 0 被淘汰；重读块 0 再解压仍逐字节正确。"""
        two = self.make_bundle("two.unity3d", nblocks=2)
        br = self.track(BL.LazyBundle(two, budget=1))
        self.assertEqual(br.read(0, 64), b"X" * 64)
        self.assertEqual(br.read(64, 64), b"Y" * 64)
        self.assertEqual(list(br._cache.keys()), [1])      # noqa: SLF001 —— 块 0 已淘汰（最旧先出）
        self.assertGreaterEqual(
            _bl_delta("blocks_evicted", lambda: br.read(0, 64)), 1)
        self.assertEqual(br.read(0, 64), b"X" * 64)        # 淘汰后重读仍正确
        self.assertEqual(br.read(64, 64), b"Y" * 64)

    def test_zero_budget_keeps_all_blocks(self) -> None:
        """budget=0 = 不限：两块都在缓存，零淘汰。"""
        two = self.make_bundle("two0.unity3d", nblocks=2)
        br = self.track(BL.LazyBundle(two, budget=0))
        br.read(0, 64)
        br.read(64, 64)
        self.assertEqual(sorted(br._cache.keys()), [0, 1])  # noqa: SLF001
        self.assertEqual(_bl_delta("blocks_evicted", lambda: None), 0)


# ---------------------------------------------------------------------------
# bundle_guard：内容哈希 + route 信任门（判据卡第 3 件）
# ---------------------------------------------------------------------------

class GuardHashTests(_GuardCase):
    def setUp(self) -> None:
        super().setUp()
        self.good = self.make_bundle("hash.unity3d")
        self.bad = self.make_bundle("hash_bad.unity3d", corrupt_at=_RAISE_OFF)

    def test_off_passthrough_zero_io(self) -> None:
        """默认关闭零行为：直通原路径，且不读文件（零 IO）。

        上游经 tables=_FakeTables(None) 驱动 off；Eidolon 无旋钮，缺省即 off，
        ``expected_from_route`` 同输入返回 (None, "no_route") 一并钉死。
        """
        with mock.patch.object(
            BG, "md5_file", side_effect=AssertionError("off 不得读盘")
        ):
            out = BG.vetted_path(self.good)
        self.assertEqual(out, self.good)
        expected, reason = BG.expected_from_route(self.good.name, None, self.good)
        self.assertIsNone(expected)
        self.assertEqual(reason, "no_route")

    def test_explicit_expected_ok(self) -> None:
        out = BG.vetted_path(self.good, expected_md5=_md5(self.good))
        self.assertEqual(out, self.good)

    def test_explicit_mismatch_loud(self) -> None:
        """expected 与盘上不符 → 响亮（默认关也被显式 expected 激活）。"""
        with self.loud():
            with self.assertRaises(BG.BundleContentMismatch) as cm:
                BG.vetted_path(self.bad, expected_md5=_md5(self.good))
        msg = str(cm.exception)
        self.assertIn(self.bad.name, msg)
        self.assertIn(_md5(self.good), msg)

    def test_route_trusted_row_activates_hash_axis(self) -> None:
        """route 可信行账（stat/md5 都对得上**当前文件**）→ 哈希轴生效。

        上游 ``test_mode_md5_with_route_row`` 的改写：原例先置
        ``os.environ[KNOB] = "md5"`` 再走 route 轴——Eidolon 删除模式旋钮，
        route 行账在场即走信任门轴，语义等价。
        """
        st = self.good.stat()
        trusted = _FakeTables({"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                               "md5": _md5(self.good)})
        self.assertEqual(BG.vetted_path(self.good, tables=trusted), self.good)
        st_bad = self.bad.stat()
        stale_md5 = _FakeTables({"size": st_bad.st_size, "mtime_ns": st_bad.st_mtime_ns,
                                 "md5": _md5(self.good)})   # 行账=好内容 md5，盘上=坏文件
        with self.loud():
            with self.assertRaises(BG.BundleContentMismatch):
                BG.vetted_path(self.bad, tables=stale_md5)

    def test_route_untrusted_stat_not_silently_trusted(self) -> None:
        """route 行 stat 与盘上不符 → 不采信（跳过哈希轴 + 留账），不响亮也不假绿。"""
        tables = _FakeTables({"size": 1, "mtime_ns": 2, "md5": _md5(self.good)})
        with mock.patch.object(
            BG, "md5_file", side_effect=AssertionError("不得用未采信 md5")
        ):
            with self.assertLogs("eidolon.core.infra.bundle_guard",
                                 level="WARNING") as logs:
                out = BG.vetted_path(self.good, tables=tables)
        self.assertEqual(out, self.good)               # 不拦也不假绿（哈希轴未启用）
        expected, reason = BG.expected_from_route(self.good.name, tables, self.good)
        self.assertIsNone(expected)
        self.assertEqual(reason, "untrusted_stat")
        self.assertTrue(any("不采信" in line for line in logs.output))

    def test_route_untrusted_md5_format(self) -> None:
        st = self.good.stat()
        tables = _FakeTables({"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                              "md5": "not-a-hash"})
        expected, reason = BG.expected_from_route(self.good.name, tables, self.good)
        self.assertIsNone(expected)
        self.assertEqual(reason, "untrusted_md5_format")

    def test_route_row_missing(self) -> None:
        expected, reason = BG.expected_from_route(
            self.good.name, _FakeTables(None), self.good)
        self.assertIsNone(expected)
        self.assertEqual(reason, "route_row_missing")


# ---------------------------------------------------------------------------
# bundle_guard：好副本整包回退（判据卡第 4 件）
# ---------------------------------------------------------------------------

class GuardFallbackTests(_GuardCase):
    def setUp(self) -> None:
        super().setUp()
        self.good_dir = self.tmp / "good_copy"
        self.good_dir.mkdir()
        self.orig = self.make_bundle("fall.unity3d", corrupt_at=_RAISE_OFF)
        self.good = _make_bundle(self.good_dir / "fall.unity3d")
        self.expected = _md5(self.good)

    def test_fallback_success_with_accounting(self) -> None:
        """三验全过 → 回退成功 + 留账（计数 + 警告），不静默。"""
        with self.assertLogs("eidolon.core.infra.bundle_guard", level="WARNING"):
            out = BG.vetted_path(self.orig, expected_md5=self.expected,
                                 good_dir=self.good_dir)
        self.assertEqual(out, self.good_dir / "fall.unity3d")
        self.assertEqual(out.read_bytes(), self.good.read_bytes())
        self.assertGreaterEqual(BG.STATS.get("guard_fallback_used", 0), 1)
        self.assertGreaterEqual(_bg_delta(
            "guard_fallback_used", lambda: None), 0)
        self.assertGreaterEqual(BG.STATS.get("guard_warnings", 0), 1)

    def test_fallback_via_route_row_and_explicit_good_dir(self) -> None:
        """route 可信行账 + 显式 good_dir → 同样回退。

        上游 ``test_fallback_via_full_mode_env_and_route`` 的改写：原例经
        ``os.environ[KNOB]="full"`` + ``GOOD_DIR_ENV`` 启用——两个 env 旋钮
        在 Eidolon 均已删除，好副本源只收显式 ``good_dir`` 参数，route 行账
        在场即走信任门轴，语义等价。
        """
        st = self.orig.stat()
        tables = _FakeTables({"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                              "md5": self.expected})     # 行账 md5=好副本内容
        out = BG.vetted_path(self.orig, tables=tables, good_dir=self.good_dir)
        self.assertEqual(out, self.good_dir / "fall.unity3d")

    def test_fallback_rejected_bad_md5_loud(self) -> None:
        """好副本 md5 != expected → 拒绝回退并响亮。"""
        other = _make_bundle(self.good_dir / "other.unity3d", corrupt_at=_RAISE_OFF)
        (self.good_dir / "fall.unity3d").write_bytes(other.read_bytes())
        with self.assertLogs("eidolon.core.infra.bundle_guard", level="WARNING"):
            with self.assertRaises(BG.BundleContentMismatch):
                BG.vetted_path(self.orig, expected_md5=self.expected,
                               good_dir=self.good_dir)
        self.assertGreaterEqual(BG.STATS.get("guard_fallback_rejected", 0), 1)

    def test_fallback_rejected_missing_good(self) -> None:
        """好副本缺失 → 拒绝并响亮。"""
        empty = self.tmp / "empty_dir"
        empty.mkdir()
        with self.loud():
            with self.assertRaises(BG.BundleContentMismatch):
                BG.vetted_path(self.orig, expected_md5=self.expected,
                               good_dir=empty)

    def test_fallback_rejected_layout_mismatch(self) -> None:
        """block 布局不等 → 拒绝（md5 之前先挡）。"""
        orig_size, orig_blocks = BG._blocks_layout(self.orig)   # noqa: SLF001
        with mock.patch.object(
            BG, "_blocks_layout",
            side_effect=lambda p: (123, [(9, 9, 9)]) if p == self.good
            else (orig_size, orig_blocks),
        ):
            with self.loud():
                with self.assertRaises(BG.BundleContentMismatch):
                    BG.vetted_path(self.orig, expected_md5=self.expected,
                                   good_dir=self.good_dir)

    def test_no_good_source_loud(self) -> None:
        """失配且无好副本源 → 响亮（禁静默出图）。"""
        with self.loud():
            with self.assertRaises(BG.BundleContentMismatch):
                BG.vetted_path(self.orig, expected_md5=self.expected)


# ---------------------------------------------------------------------------
# bundle_guard.load：快照 + 同遍 hash 的整包加载便捷面
# ---------------------------------------------------------------------------

class GuardLoadTests(_GuardCase):
    def setUp(self) -> None:
        super().setUp()
        self.good = self.make_bundle("load.unity3d")
        self.bad = self.make_bundle("load_bad.unity3d", corrupt_at=_RAISE_OFF)

    def test_off_delegates_to_unitypy(self) -> None:
        with mock.patch.object(
            BG, "_read_and_hash", side_effect=AssertionError("off 不得快照")
        ):
            env = self.track_env(BG.load(self.good))
        self.assertIn("cab-test", env.cabs)

    def test_load_hash_ok(self) -> None:
        env = self.track_env(BG.load(self.good, expected_md5=_md5(self.good)))
        self.assertIn("cab-test", env.cabs)

    def test_load_mismatch_loud(self) -> None:
        with self.loud():
            with self.assertRaises(BG.BundleContentMismatch):
                BG.load(self.bad, expected_md5=_md5(self.good))

    def test_load_fallback(self) -> None:
        gd = self.tmp / "gd"
        gd.mkdir()
        (gd / "load_bad.unity3d").write_bytes(self.good.read_bytes())
        env = self.track_env(
            BG.load(self.bad, expected_md5=_md5(self.good), good_dir=gd))
        self.assertIn("cab-test", env.cabs)


# ---------------------------------------------------------------------------
# bundle_guard.load_defended：块级两件的统一收口面
# ---------------------------------------------------------------------------

class LoadDefendedTests(_GuardCase):
    def test_defended_load_clean(self) -> None:
        """干净包：惰性路加载成功，env 语义与老路同形（cabs 可见、惰性层在场）。"""
        good = self.make_bundle("ld.unity3d")
        env = self.track_env(BG.load_defended(good))
        self.assertIn("cab-test", env.cabs)
        self.assertTrue(BL.is_lazy_env(env))

    def test_corrupt_propagates_typed_not_fallback(self) -> None:
        """坏块 typed 直通——禁退化成老路重读丢上下文。"""
        bad = self.make_bundle("ld_bad.unity3d", corrupt_at=_RAISE_OFF)
        with mock.patch.object(BG, "UnityPy") as upy:
            upy.load.side_effect = AssertionError("typed error 不得退老路")
            with self.assertRaises(BL.BundleBlockCorruptError):
                BG.load_defended(bad)

    def test_unsupported_falls_back_to_legacy(self) -> None:
        """非 UnityFS → LazyUnsupported → 显式退老路（计数 + 警告留账）。"""
        junk = self.tmp / "junk.bin"
        junk.write_bytes(b"not a bundle at all........")
        sentinel = object()
        with mock.patch.object(BG, "UnityPy") as upy:
            upy.load.return_value = sentinel
            with self.assertLogs("eidolon.core.infra.bundle_guard",
                                 level="WARNING") as logs:
                out = BG.load_defended(junk)
        self.assertIs(out, sentinel)
        self.assertGreaterEqual(BG.STATS.get("guard_legacy_fallback", 0), 1)
        self.assertTrue(any("退老路" in line for line in logs.output))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
