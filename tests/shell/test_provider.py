"""provider 与 catalog 绑定：NullCatalogProvider / bind_json_catalog / build_spec 身份。

Phase 1b：``game_unresolved`` 警告随真实 provider 接入删除（设计性删除，
设计文档 §9.6）——provider 解析不出 GameContext 时
直接 ``EnvironmentUnavailable``（退出 3），不再产出带警告的 spec。
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import unittest

from eidolon.contracts import (
    CatalogBinding,
    CatalogIdentity,
    GameContext,
    GameRequest,
)
from eidolon.entry import main
from eidolon.shell.catalog import JsonCatalog, NullCatalog, NullCatalogProvider, bind_json_catalog
from eidolon.shell.spec import build_spec
from tests.shell.test_input import make_game_root
from tests.support import CATALOG_JSON, TomlCase, fixture_catalog


class NullCatalogProviderTests(unittest.TestCase):
    def test_bind_returns_null_binding(self) -> None:
        provider = NullCatalogProvider(cache_root=Path("C:/cache"), locale="zhcn")
        binding = provider.bind(GameRequest(game_dir=None, source=""))
        self.assertIsInstance(binding.catalog, NullCatalog)
        self.assertIsNone(binding.game)
        self.assertEqual(binding.identity, CatalogIdentity(kind="null"))
        self.assertEqual(binding.warnings, ())

    def test_bind_ignores_explicit_game_request(self) -> None:
        # 真实 provider（core）才消费 GameRequest；dev provider 恒 null。
        provider = NullCatalogProvider()
        binding = provider.bind(
            GameRequest(game_dir=Path("D:/Games/Hearthstone"), source="--game")
        )
        self.assertIsNone(binding.game)


class BindJsonCatalogTests(TomlCase):
    def test_identity_carries_file_facts(self) -> None:
        binding = bind_json_catalog(CATALOG_JSON)
        stat = CATALOG_JSON.stat()
        self.assertEqual(binding.identity.kind, "json")
        self.assertEqual(binding.identity.path, str(CATALOG_JSON.resolve()))
        self.assertEqual(binding.identity.size, stat.st_size)
        self.assertEqual(binding.identity.mtime_ns, stat.st_mtime_ns)
        self.assertFalse(binding.identity.complete)
        self.assertIsNone(binding.game)

    def test_complete_flag_copied_from_catalog(self) -> None:
        path = self.tmp / "complete.json"
        path.write_text(
            '{"complete": true, "cards": {"8": {"cardtype": "MINION"}}}',
            encoding="utf-8",
        )
        binding = bind_json_catalog(path)
        self.assertTrue(binding.identity.complete)
        self.assertIsNotNone(binding.catalog.lookup(_ref(8)))

    def test_missing_catalog_raises_catalog_error(self) -> None:
        from eidolon.shell.catalog import CatalogError

        with self.assertRaises(CatalogError):
            bind_json_catalog(self.tmp / "nope.json")


def _ref(value):
    from eidolon.shell.spec import parse_id

    return parse_id(value)


class _FakeDbfProvider:
    """fake provider：恒返回带 GameContext + dbf 身份的 binding（不触盘）。

    替代 Phase 1b 删除的 game_unresolved 断言：真实 provider 的 bind 形状
    （game 非 None、identity kind="dbf"）经注入面进入 spec / manifest。
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def bind(self, request: GameRequest) -> CatalogBinding:
        ctx = GameContext(
            root=self.root,
            cache_root=Path("C:/cache"),
            locale="zhcn",
            version="37.0.2-test",
            version_source="test",
            root_source="--game",
        )
        return CatalogBinding(
            catalog=JsonCatalog.from_dict(
                {"complete": True, "cards": {"8": {"cardtype": "MINION"}}}
            ),
            game=ctx,
            identity=CatalogIdentity(
                kind="dbf",
                path=str(self.root / "Data" / "Win" / "dbf.unity3d"),
                size=12345,
                mtime_ns=67890,
                complete=True,
            ),
        )


class FakeProviderBindingTests(TomlCase):
    """binding.game 非 None + identity kind="dbf" → manifest 三段 environment。"""

    def test_manifest_environment_game_and_dbf(self) -> None:
        root = make_game_root(self.tmp)
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                ["spec", "8", "--game", str(root)],
                provider_factory=lambda: _FakeDbfProvider(root.resolve()),
            )
        self.assertEqual(code, 0, stderr.getvalue())
        manifest = json.loads(stdout.getvalue())

        game = manifest["environment"]["game"]
        self.assertIsNotNone(game)
        self.assertEqual(game["root"], str(root.resolve()))
        self.assertEqual(game["locale"], "zhcn")
        self.assertEqual(game["version"], "37.0.2-test")
        self.assertEqual(game["root_source"], "--game")

        dbf = manifest["environment"]["dbf"]
        self.assertEqual(
            dbf,
            {
                "path": str(root.resolve() / "Data" / "Win" / "dbf.unity3d"),
                "size": 12345,
                "mtime_ns": 67890,
            },
        )
        self.assertTrue(manifest["environment"]["catalog"]["complete"])
        self.assertEqual(manifest["warnings"], [])

    def test_manifest_game_none_when_provider_gives_no_game(self) -> None:
        root = make_game_root(self.tmp)
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                ["spec", "8", "--game", str(root)],
                provider_factory=NullCatalogProvider,
            )
        self.assertEqual(code, 0, stderr.getvalue())
        manifest = json.loads(stdout.getvalue())
        self.assertIsNone(manifest["environment"]["game"])
        self.assertIsNone(manifest["environment"]["dbf"])


class BuildSpecBindingTests(TomlCase):
    """兼容包装的 binding 形状：catalog=None → null；传 catalog → json/<memory>。"""

    def test_null_catalog_identity(self) -> None:
        spec = build_spec(["8"], cwd=self.tmp)
        self.assertEqual(spec.catalog.kind, "null")
        self.assertEqual(spec.catalog.path, "")
        self.assertFalse(spec.catalog.complete)
        self.assertIsNone(spec.game)

    def test_json_catalog_identity(self) -> None:
        spec = build_spec(["8"], catalog=fixture_catalog(), cwd=self.tmp)
        self.assertEqual(spec.catalog.kind, "json")
        self.assertEqual(spec.catalog.path, "<memory>")
        self.assertFalse(spec.catalog.complete)

    def test_render_spec_has_game_and_catalog_fields(self) -> None:
        spec = build_spec(["8"], cwd=self.tmp)
        self.assertIsNone(spec.game)
        self.assertEqual(spec.warnings, ())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
