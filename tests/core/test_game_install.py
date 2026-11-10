"""game_install：显式/探测两路解析（无 env）、product.db 合成 walk、版本回落。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eidolon.contracts import EnvironmentUnavailable, GameRequest, ProblemKind
from eidolon.core.infra.game_install import (
    PRODUCT_DB_PATH,
    assert_game_root,
    resolve_context,
    resolve_game_root,
    resolve_version,
)


# ---------------------------------------------------------------------------
# 合成 product.db（按上游 protobuf walk 格式手写最小二进制；全走 tmp 注入）
# ---------------------------------------------------------------------------

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _field(field: int, payload: bytes) -> bytes:
    """length-delimited 字段（wire type 2）。"""
    return _varint((field << 3) | 2) + _varint(len(payload)) + payload


def _write_product_db(
    path: Path,
    *,
    product: bytes = b"hs_beta",
    alias: bytes | None = None,
    install_path: str | None = None,
    version: str | None = None,
) -> Path:
    entry = _field(1, product)
    if alias is not None:
        entry += _field(2, alias)
    if install_path is not None:
        # (3,1) = install_path
        entry += _field(3, _field(1, install_path.encode("utf-8")))
    if version is not None:
        # (4,1,7) = 版本串（末段=数据 BuildNumber）
        entry += _field(4, _field(1, _field(7, version.encode("utf-8"))))
    path.write_bytes(_field(1, entry))
    return path


def _make_game_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Hearthstone.exe").write_bytes(b"MZ")
    return root


class GameInstallCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.product_db = self.tmp / "product.db"
        self.db = self.tmp / "game"


class ProductDbPathTests(GameInstallCase):
    def test_default_constant(self) -> None:
        self.assertEqual(
            PRODUCT_DB_PATH, Path("C:/ProgramData/Battle.net/Agent/product.db")
        )


class ResolveGameRootTests(GameInstallCase):
    def test_explicit_uses_given_source(self) -> None:
        root = self.tmp / "anywhere"  # 显式路不判安装根
        resolved, source = resolve_game_root(root, source="--game")
        self.assertEqual(resolved, root)
        self.assertEqual(source, "--game")

    def test_explicit_empty_source_falls_to_explicit(self) -> None:
        root = self.tmp / "anywhere"
        resolved, source = resolve_game_root(root, source="")
        self.assertEqual((resolved, source), (root, "explicit"))

    def test_missing_product_db_raises_game_not_found(self) -> None:
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            resolve_game_root(None, source="", product_db_path=self.product_db)
        problem = ctx.exception.problem
        self.assertIs(problem.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(problem.code, "game_not_found")
        self.assertEqual(problem.path, str(self.product_db))

    def test_entry_without_install_path_raises_game_not_found(self) -> None:
        _write_product_db(self.product_db)  # 只有 product 名，无 (3,1)
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            resolve_game_root(None, source="", product_db_path=self.product_db)
        self.assertEqual(ctx.exception.problem.code, "game_not_found")
        self.assertIn("install_path", ctx.exception.problem.message)

    def test_no_hs_entry_raises_game_not_found(self) -> None:
        _write_product_db(self.product_db, product=b"wow")
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            resolve_game_root(None, source="", product_db_path=self.product_db)
        self.assertEqual(ctx.exception.problem.code, "game_not_found")
        self.assertIn("hs_beta", ctx.exception.problem.message)

    def test_install_path_dir_missing_raises_game_not_found(self) -> None:
        _write_product_db(
            self.product_db, install_path=str(self.tmp / "gone"))
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            resolve_game_root(None, source="", product_db_path=self.product_db)
        self.assertEqual(ctx.exception.problem.code, "game_not_found")
        self.assertEqual(ctx.exception.problem.path, str(self.product_db))
        self.assertIn("目录不存在", ctx.exception.problem.message)

    def test_dir_without_exe_raises_game_dir_incomplete(self) -> None:
        stale = self.tmp / "stale"
        stale.mkdir()
        _write_product_db(self.product_db, install_path=str(stale))
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            resolve_game_root(None, source="", product_db_path=self.product_db)
        problem = ctx.exception.problem
        self.assertEqual(problem.code, "game_dir_incomplete")
        self.assertEqual(problem.path, str(stale))

    def test_probe_success_returns_product_db_source(self) -> None:
        root = _make_game_root(self.db)
        _write_product_db(self.product_db, install_path=str(root))
        resolved, source = resolve_game_root(
            None, source="", product_db_path=self.product_db)
        self.assertEqual(resolved, root)
        self.assertEqual(source, "product.db")

    def test_probe_walks_past_decoy_entries_and_hsb_alias(self) -> None:
        root = _make_game_root(self.db)
        # 前置 decoy 条目（非炉石产品）+ 主条目走 hsb 别名（field 2）。
        decoy = _field(1, _field(1, b"wow"))
        main_entry = _field(2, b"hsb") + _field(
            3, _field(1, str(root).encode("utf-8")))
        self.product_db.write_bytes(decoy + _field(1, main_entry))
        resolved, source = resolve_game_root(
            None, source="", product_db_path=self.product_db)
        self.assertEqual(resolved, root)
        self.assertEqual(source, "product.db")


class AssertGameRootTests(GameInstallCase):
    def test_missing_dir_raises_game_not_found(self) -> None:
        missing = self.tmp / "missing"
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            assert_game_root(missing)
        problem = ctx.exception.problem
        self.assertEqual(problem.code, "game_not_found")
        self.assertEqual(problem.path, str(missing))

    def test_dir_without_exe_raises_game_dir_incomplete(self) -> None:
        bare = self.tmp / "bare"
        bare.mkdir()
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            assert_game_root(bare)
        problem = ctx.exception.problem
        self.assertEqual(problem.code, "game_dir_incomplete")
        self.assertEqual(problem.path, str(bare))

    def test_complete_root_passes(self) -> None:
        root = _make_game_root(self.db)
        self.assertIsNone(assert_game_root(root))


class ResolveVersionTests(GameInstallCase):
    def test_same_install_trusts_product_db_version(self) -> None:
        root = _make_game_root(self.db)
        _write_product_db(
            self.product_db,
            install_path=str(root),
            version="37.0.2.256589.255790",
        )
        version, source = resolve_version(
            root, product_db_path=self.product_db)
        self.assertEqual(version, "37.0.2.256589.255790")
        self.assertEqual(source, "product.db")

    def test_different_install_falls_to_power_log(self) -> None:
        root = _make_game_root(self.db)
        other = _make_game_root(self.tmp / "other")
        _write_product_db(
            self.product_db,
            install_path=str(other),  # 与 root 不同装 → 不采信
            version="37.0.2.256589.255790",
        )
        log_dir = root / "Logs" / "Hearthstone_2026_11_08_10_00_00"
        log_dir.mkdir(parents=True)
        (log_dir / "Power-1.log").write_text(
            "D 11:00:00.0000000 GameState.DebugPrintPower() - "
            "BuildNumber=256589\n",
            encoding="utf-8",
        )
        version, source = resolve_version(root, product_db_path=self.product_db)
        self.assertEqual(version, "256589")
        self.assertTrue(source.startswith("power.log:"))
        self.assertIn("Power-1.log", source)

    def test_root_level_power_log_is_fallback(self) -> None:
        root = _make_game_root(self.db)
        _write_product_db(self.product_db, product=b"wow")  # 无条目
        (root / "Power.log").write_text("BuildNumber= 253216\n", encoding="utf-8")
        version, source = resolve_version(root, product_db_path=self.product_db)
        self.assertEqual(version, "253216")
        self.assertTrue(source.startswith("power.log:"))

    def test_nothing_available_returns_none_empty(self) -> None:
        root = _make_game_root(self.db)
        _write_product_db(
            self.product_db,
            install_path=str(self.tmp / "elsewhere"),
            version="37.0.2.256589.255790",
        )
        self.assertEqual(resolve_version(root, product_db_path=self.product_db), (None, ""))


class ResolveContextTests(GameInstallCase):
    def test_root_source_explicit_cli(self) -> None:
        root = self.tmp / "root_a"
        ctx = resolve_context(
            GameRequest(root, "--game"),
            cache_root=self.tmp / "cache",
            locale="zhcn",
        )
        self.assertEqual(ctx.root, root)
        self.assertEqual(ctx.root_source, "--game")

    def test_root_source_toml(self) -> None:
        root = self.tmp / "root_b"
        ctx = resolve_context(
            GameRequest(root, "toml game_dir"),
            cache_root=self.tmp / "cache",
            locale="zhcn",
        )
        self.assertEqual(ctx.root_source, "toml game_dir")

    def test_root_source_probe(self) -> None:
        root = _make_game_root(self.db)
        _write_product_db(self.product_db, install_path=str(root))
        ctx = resolve_context(
            GameRequest(None, ""),
            cache_root=self.tmp / "cache",
            locale="zhcn",
            product_db_path=self.product_db,
        )
        self.assertEqual(ctx.root, root)
        self.assertEqual(ctx.root_source, "product.db")

    def test_probe_failure_raises_environment(self) -> None:
        with self.assertRaises(EnvironmentUnavailable) as ctx_exc:
            resolve_context(
                GameRequest(None, ""),
                cache_root=self.tmp / "cache",
                locale="zhcn",
                product_db_path=self.tmp / "absent.db",
            )
        self.assertEqual(ctx_exc.exception.problem.code, "game_not_found")

    def test_locale_normalization(self) -> None:
        root = self.tmp / "root_c"
        ctx = resolve_context(
            GameRequest(root, "--game"),
            cache_root=self.tmp / "cache",
            locale=" zhCN ",
        )
        self.assertEqual(ctx.locale, "zhcn")
        empty = resolve_context(
            GameRequest(root, "--game"),
            cache_root=self.tmp / "cache",
            locale="",
        )
        self.assertEqual(empty.locale, "zhcn")
        self.assertEqual(empty.strings_dir, root / "Strings" / "zhcn")

    def test_fixed_switches_and_derived_paths(self) -> None:
        root = self.tmp / "root_d"
        cache = self.tmp / "cache_d"
        ctx = resolve_context(
            GameRequest(root, "--game"),
            cache_root=cache,
            locale="zhcn",
        )
        self.assertEqual(ctx.route_mode, "auto")
        self.assertIs(ctx.version_strict, False)
        self.assertIsNone(ctx.version)
        self.assertEqual(ctx.cache_root, cache)
        self.assertEqual(ctx.data_win, root / "Data" / "Win")
        self.assertEqual(ctx.dbf_path, root / "Data" / "Win" / "dbf.unity3d")
        self.assertEqual(ctx.game_exe, root / "Hearthstone.exe")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
