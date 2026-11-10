"""组合层适配器 CoreRenderPort：to_request 形状转换 + preflight 分支。

默认测试纪律（§13.1）：不触 CLR / UnityPy / 真实 dbf——preflight 到第 10 步
（validate_overrides）时以模块 seam 打桩；``context.install`` 是进程级安装
点，测试用 save/restore ``context._installed`` 隔离。install 后的完整链路
归 ``tests/integration/integration_render_port.py``（真实游戏）。
"""

from __future__ import annotations

import contextlib
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from eidolon import adapters as adapters_mod
from eidolon.adapters import CoreRenderPort
from eidolon.contracts import (
    EnvironmentUnavailable,
    GameContext,
    Problem,
    ProblemKind,
)
from eidolon.shell.errors import SpecErrors
from eidolon.shell.spec import build_spec
from tests.support import fixture_catalog


def _sha_fixture_png(directory: Path, name: str, size: tuple[int, int]) -> Path:
    from PIL import Image

    path = directory / name
    Image.new("RGBA", size, (10, 20, 30, 255)).save(path)
    return path


def _fake_game(tmp: Path, *, complete: bool = True) -> GameContext:
    """含 exe/assembly/dbf/Strings/zhcn 的假安装根（零游戏数据；无 CLR）。"""
    root = tmp / "game"
    (root / "Hearthstone_Data" / "Managed").mkdir(parents=True, exist_ok=True)
    (root / "Data" / "Win").mkdir(parents=True, exist_ok=True)
    (root / "Strings" / "zhcn").mkdir(parents=True, exist_ok=True)
    cache = tmp / "cache"
    cache.mkdir(exist_ok=True)
    if complete:
        (root / "Hearthstone.exe").write_bytes(b"")
        (root / "Hearthstone_Data" / "Managed" / "Assembly-CSharp.dll").write_bytes(b"")
        (root / "Data" / "Win" / "dbf.unity3d").write_bytes(b"")
    return GameContext(root=root, cache_root=cache, locale="zhcn")


@contextlib.contextmanager
def _isolated_render_context():
    """preflight 会 install 进程渲染身份——测试后恢复原状（无卸载 API）。"""
    from eidolon.core.infra import context

    saved = context._installed
    try:
        yield
    finally:
        context._installed = saved


@contextlib.contextmanager
def _no_dbf_session():
    """preflight 第 10 步的 dbf 会话检查打桩（避免 import 真 dbf → UnityPy）。"""
    infra_pkg = __import__("eidolon.core.infra", fromlist=["__dummy__"])
    stub = types.ModuleType("eidolon.core.infra.dbf")
    stub.default_dbf = lambda: None
    stub.installed_default = lambda: None
    stub.install_default = lambda module: None
    stub.reset_default = lambda: None
    had_attr = hasattr(infra_pkg, "dbf")
    saved_attr = getattr(infra_pkg, "dbf", None)
    with mock.patch.dict("sys.modules", {"eidolon.core.infra.dbf": stub}):
        try:
            yield stub
        finally:
            if had_attr:
                infra_pkg.dbf = saved_attr
            elif getattr(infra_pkg, "dbf", None) is stub:
                del infra_pkg.dbf


class AdaptersCase(unittest.TestCase):
    # 默认测试纪律（§13.1 不触 CLR）：preflight 第 3 步后半的 .NET 运行时
    # 真探测打桩；专用探针测试类显式置 False 才走真实探测。
    stub_dotnet_probe = True

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        if self.stub_dotnet_probe:
            patcher = mock.patch.object(
                CoreRenderPort, "_probe_dotnet_runtime", lambda self: None
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_port(self, **kwargs) -> CoreRenderPort:
        font_dirs = kwargs.pop("font_dirs", (Path("C:/Windows/Fonts"),))
        return CoreRenderPort(font_dirs=font_dirs, **kwargs)

    def make_spec(self, *, out_dir: Path | None = None, assets=None, **card_fields):
        out_dir = out_dir or (self.tmp / "out")
        spec = build_spec(
            ["8", "CS2_182"], out_dir=out_dir, cwd=self.tmp, catalog=fixture_catalog()
        )
        fields: dict = {"assets": dict(assets or {})}
        fields.update(card_fields)
        card = replace(spec.cards[0], **fields)
        return replace(spec, cards=(card, spec.cards[1]))

    def spec_with_game(self, **kwargs):
        spec = self.make_spec(**kwargs)
        return replace(spec, game=_fake_game(self.tmp))


class ToRequestTests(AdaptersCase):
    def test_overrides_rebuilt_from_explicit_fields(self) -> None:
        png = _sha_fixture_png(self.tmp, "p.png", (512, 512))
        spec = self.make_spec(
            name="名字",
            desc="描述",
            cost=3,
            attack=4,
            elite=True,
            runes={"BLOOD": 1, "FROST": 2},
            classes=["MAGE"],
            races=["野兽"],
            cardtype="MINION",
            rarity="COMMON",
            premium="GOLDEN",
            spell_school="FIRE",
            cost_banner="KABAL",
            tech_level=3,
            assets={"portrait": png},
        )
        request = self.make_port().to_request(spec)
        self.assertEqual(
            set(request.cards[0].overrides),
            {
                "name",
                "desc",
                "cost",
                "attack",
                "elite",
                "runes",
                "classes",
                "races",
                "cardtype",
                "rarity",
                "premium",
                "spell_school",
                "cost_banner",
                "tech_level",
            },
        )
        self.assertEqual(request.cards[0].overrides["runes"], {"BLOOD": 1, "FROST": 2})
        self.assertEqual(request.cards[1].overrides, {})
        self.assertEqual(request.cards[0].assets, {"portrait": png})
        self.assertIs(request.cards[0].session_t, None)

    def test_runes_is_plain_dict(self) -> None:
        spec = self.make_spec(runes={"BLOOD": 1})
        request = self.make_port().to_request(spec)
        self.assertIs(type(request.cards[0].overrides["runes"]), dict)

    def test_assets_are_copied(self) -> None:
        spec = self.make_spec()
        request = self.make_port().to_request(spec)
        self.assertIsNot(request.cards[0].assets, spec.cards[0].assets)

    def test_style_is_requested_and_effective(self) -> None:
        # §5.4 + README 正交：RenderCard.hero_style/bg_style =
        # style_requested[0/1] and CardSpec 生效值；全局开关只落在适用卡上。
        spec = self.make_spec(hero_style=True, style_requested=(False, False))
        request = self.make_port().to_request(spec)
        self.assertFalse(request.cards[0].hero_style)
        self.assertFalse(request.cards[0].bg_style)
        # 交集钉死：生效 hero_style=True + 双请求（True, True）→ hero 下发、
        # bg 无生效值不下发（HERO 卡 bg 生效值恒 False）。
        spec = self.make_spec(hero_style=True, style_requested=(True, True))
        request = self.make_port().to_request(spec)
        self.assertTrue(request.cards[0].hero_style)
        self.assertFalse(request.cards[0].bg_style)
        # 生效 hero_style=False（默认）+ 请求 hero → 不下发（请求 ∩ 生效）。
        spec = self.make_spec(style_requested=(True, False))
        request = self.make_port().to_request(spec)
        self.assertFalse(request.cards[0].hero_style)
        self.assertFalse(request.cards[0].bg_style)
        spec = self.make_spec(bg_style=True, style_requested=(False, True))
        request = self.make_port().to_request(spec)
        self.assertFalse(request.cards[0].hero_style)
        self.assertTrue(request.cards[0].bg_style)
        # 混合批：HERO 卡带 --bg-style、非 HERO 卡带 --hero-style，均被逐卡 mask。
        spec = self.make_spec(hero_style=True, style_requested=(False, True))
        request = self.make_port().to_request(spec)
        self.assertFalse(request.cards[0].hero_style)
        self.assertFalse(request.cards[0].bg_style)
        spec = self.make_spec(bg_style=True, style_requested=(True, False))
        request = self.make_port().to_request(spec)
        self.assertFalse(request.cards[0].hero_style)
        self.assertFalse(request.cards[0].bg_style)

    def test_mixed_batch_global_style_masks_per_card(self) -> None:
        # 真实 compile_spec + adapter：HERO_01 只吃 hero，8 只吃 bg。
        spec = build_spec(
            ["HERO_01", "8"],
            out_dir=self.tmp / "out",
            bg_style=True,
            catalog=fixture_catalog(),
            cwd=self.tmp,
        )
        request = self.make_port().to_request(spec)
        self.assertFalse(request.cards[0].bg_style)
        self.assertTrue(request.cards[1].bg_style)
        spec = build_spec(
            ["HERO_01", "8"],
            out_dir=self.tmp / "out",
            hero_style=True,
            catalog=fixture_catalog(),
            cwd=self.tmp,
        )
        request = self.make_port().to_request(spec)
        self.assertTrue(request.cards[0].hero_style)
        self.assertFalse(request.cards[1].hero_style)
        spec = build_spec(
            ["HERO_01", "8"],
            out_dir=self.tmp / "out",
            hero_style=True,
            bg_style=True,
            catalog=fixture_catalog(),
            cwd=self.tmp,
        )
        request = self.make_port().to_request(spec)
        self.assertTrue(request.cards[0].hero_style)
        self.assertFalse(request.cards[0].bg_style)
        self.assertFalse(request.cards[1].hero_style)
        self.assertTrue(request.cards[1].bg_style)

    def test_request_shape_fields(self) -> None:
        spec = self.make_spec()
        port = self.make_port(font_dirs=(Path("D:/Fonts"), Path("E:/Fonts")))
        request = port.to_request(spec)
        self.assertEqual(request.out_dir, spec.options.out_dir)
        self.assertEqual(request.jobs, spec.options.jobs)
        self.assertEqual(request.antialias, spec.options.antialias)
        self.assertIs(request.game, spec.game)
        self.assertEqual(request.font_dirs, (Path("D:/Fonts"), Path("E:/Fonts")))
        self.assertEqual(len(request.cards), len(spec.cards))


class PreflightStep1Tests(AdaptersCase):
    def test_game_none_raises_runtime_error(self) -> None:
        spec = self.make_spec()  # game=None（null binding）
        port = self.make_port()
        with self.assertRaises(RuntimeError):
            port.preflight(spec)

    def test_render_game_none_raises_runtime_error(self) -> None:
        spec = self.make_spec()
        with self.assertRaises(RuntimeError):
            self.make_port().render(spec)


class PreflightDependencyTests(AdaptersCase):
    def test_missing_dependency_maps_dependency_missing(self) -> None:
        # 环境已装齐依赖，缺失分支用 find_spec 打桩（§7.7 第 3 步在
        # font/glyph import 前）。
        spec = self.spec_with_game()
        port = self.make_port()
        with _isolated_render_context():
            with mock.patch(
                "importlib.util.find_spec", return_value=None
            ):
                with self.assertRaises(EnvironmentUnavailable) as caught:
                    port.preflight(spec)
        problem = caught.exception.problem
        self.assertEqual(problem.code, "dependency_missing")
        self.assertEqual(problem.kind, ProblemKind.ENVIRONMENT)
        self.assertTrue(problem.path.startswith("env:"))


class DotnetProbeTests(AdaptersCase):
    """preflight 第 3 步后半：.NET 运行时真探测（本类关闭 setUp 打桩）。

    真实 ``load("coreclr")`` 归显式集成（integration_render_port 的
    DOTNET_ROOT 负例子进程用例）；这里用 ``pythonnet.load`` 打桩钉住
    映射与缓存语义。
    """

    stub_dotnet_probe = False

    def setUp(self) -> None:
        super().setUp()
        # 进程级缓存隔离：探针成功会写模块级标记，测试后还原。
        patcher = mock.patch.object(adapters_mod, "_DOTNET_PROBE_OK", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_load_failure_maps_dependency_missing_dotnet(self) -> None:
        # 依赖模块齐全但 CLR 起不来（无 .NET 运行时）→ ENVIRONMENT
        # dependency_missing，path 钉 env:dotnet（§7.7 第 3 步后半）。
        spec = self.spec_with_game()
        port = self.make_port()
        with _isolated_render_context():
            with mock.patch(
                "pythonnet.load", side_effect=RuntimeError("boom: no runtime")
            ):
                with self.assertRaises(EnvironmentUnavailable) as caught:
                    port.preflight(spec)
        problem = caught.exception.problem
        self.assertEqual(problem.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(problem.code, "dependency_missing")
        self.assertEqual(problem.path, "env:dotnet")
        self.assertIn("RuntimeError", problem.cause)

    def test_probe_success_cached_process_wide(self) -> None:
        # 成功结果进程级缓存：同进程两次探测只 load 一次（load 幂等，
        # 缓存只是省重复初始化）。
        port = self.make_port()
        probe = mock.MagicMock(name="load")
        with mock.patch("pythonnet.load", probe):
            port._probe_dotnet_runtime()
            port._probe_dotnet_runtime()
        self.assertEqual(probe.call_count, 1)


class PreflightEnvBranchTests(AdaptersCase):
    """第 4-8 步的 ENV/INPUT 分支（假安装根；不触 CLR）。"""

    def test_cache_root_is_file_maps_cache_unwritable(self) -> None:
        blocker = self.tmp / "not_a_dir"
        blocker.write_bytes(b"")
        spec = self.make_spec()
        game = _fake_game(self.tmp)
        game = replace(game, cache_root=blocker)
        spec = replace(spec, game=game)
        with _isolated_render_context():
            with self.assertRaises(EnvironmentUnavailable) as caught:
                self.make_port().preflight(spec)
        self.assertEqual(caught.exception.problem.code, "cache_unwritable")

    def test_locale_missing_lists_available_dirs(self) -> None:
        game = _fake_game(self.tmp)
        root = game.root
        # 删掉 Strings 子目录（保留 root）→ locale_missing。
        strings = root / "Strings"
        for child in sorted(strings.iterdir(), reverse=True):
            child.rmdir()
        strings.rmdir()
        spec = replace(self.make_spec(), game=game)
        with _isolated_render_context():
            with self.assertRaises(EnvironmentUnavailable) as caught:
                self.make_port().preflight(spec)
        problem = caught.exception.problem
        self.assertEqual(problem.code, "locale_missing")
        self.assertEqual(problem.path, str(root / "Strings" / "zhcn"))
        self.assertIn("无 Strings 目录", problem.message)

    def test_locale_missing_lists_remaining_locale_dirs(self) -> None:
        """B4：请求的 locale 目录缺失但 Strings 下还有别的语言 →
        typed locale_missing（ENV 3），message 点名实际可用的语言目录。"""
        game = _fake_game(self.tmp)
        root = game.root
        (root / "Strings" / "zhcn").rmdir()
        (root / "Strings" / "enUS").mkdir()
        spec = replace(self.make_spec(), game=game)
        with _isolated_render_context():
            with self.assertRaises(EnvironmentUnavailable) as caught:
                self.make_port().preflight(spec)
        problem = caught.exception.problem
        self.assertEqual(problem.code, "locale_missing")
        self.assertEqual(problem.path, str(root / "Strings" / "zhcn"))
        self.assertIn("enUS", problem.message,
                      "locale_missing 应点名 Strings 下实际存在的语言目录")
        self.assertNotIn("无 Strings 目录", problem.message)

    def test_missing_assembly_maps_game_dir_incomplete(self) -> None:
        game = _fake_game(self.tmp)
        (game.root / "Hearthstone_Data" / "Managed" / "Assembly-CSharp.dll").unlink()
        spec = replace(self.make_spec(), game=game)
        with _isolated_render_context():
            with self.assertRaises(EnvironmentUnavailable) as caught:
                self.make_port().preflight(spec)
        problem = caught.exception.problem
        self.assertEqual(problem.code, "game_dir_incomplete")
        self.assertIn("Assembly-CSharp.dll", problem.message)

    def test_missing_dbf_alone_maps_dbf_missing(self) -> None:
        game = _fake_game(self.tmp)
        (game.root / "Data" / "Win" / "dbf.unity3d").unlink()
        spec = replace(self.make_spec(), game=game)
        with _isolated_render_context():
            with self.assertRaises(EnvironmentUnavailable) as caught:
                self.make_port().preflight(spec)
        self.assertEqual(caught.exception.problem.code, "dbf_missing")

    def test_out_dir_shape_error_is_input(self) -> None:
        blocker = self.tmp / "file.png"
        blocker.write_bytes(b"")
        spec = self.make_spec(out_dir=blocker)
        spec = replace(spec, game=_fake_game(self.tmp))
        with _isolated_render_context():
            with self.assertRaises(SpecErrors) as caught:
                self.make_port().preflight(spec)
        self.assertIn("out_dir_invalid", caught.exception.codes)

    def test_out_dir_unwritable_maps_environment(self) -> None:
        # Windows 对目录只读位不拦截建文件（OS 行为，chmod 模拟不可靠）；
        # 以 _probe_writable seam 注入 PermissionError 验证 OSError →
        # out_dir_unwritable（ENV）映射。真实只读盘/权限路径由该分支承接。
        import eidolon.adapters as adapters_module

        out_dir = self.tmp / "out"
        out_dir.mkdir()
        spec = self.make_spec(out_dir=out_dir)
        spec = replace(spec, game=_fake_game(self.tmp))

        real_probe = adapters_module._probe_writable

        def fake_probe(directory):
            if Path(directory).resolve() == out_dir.resolve():
                raise PermissionError(13, "access denied", str(directory))
            return real_probe(directory)

        with _isolated_render_context():
            with mock.patch.object(
                adapters_module, "_probe_writable", side_effect=fake_probe
            ):
                with self.assertRaises(EnvironmentUnavailable) as caught:
                    self.make_port().preflight(spec)
        problem = caught.exception.problem
        self.assertEqual(problem.code, "out_dir_unwritable")
        self.assertEqual(problem.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(problem.path, str(spec.options.out_dir))


class PreflightOverrideTests(AdaptersCase):
    """第 9/10 步：覆盖资产静态规约（真 PIL）+ 语义轻校验（seam 打桩）。"""

    def test_oversized_portrait_maps_asset_dimensions_input(self) -> None:
        bad = _sha_fixture_png(self.tmp, "bad.png", (511, 511))
        spec = self.spec_with_game(assets={"portrait": bad})
        with _isolated_render_context(), _no_dbf_session():
            with self.assertRaises(SpecErrors) as caught:
                self.make_port().preflight(spec)
        self.assertIn("asset_dimensions", caught.exception.codes)
        self.assertEqual(caught.exception.paths[0], "cards[0].asset.portrait")

    def test_valid_portrait_passes_with_stubbed_semantics(self) -> None:
        png = _sha_fixture_png(self.tmp, "ok.png", (512, 512))
        spec = self.spec_with_game(assets={"portrait": png})
        with _isolated_render_context(), _no_dbf_session():
            self.make_port().preflight(spec)  # 不抛即通过

    def test_multiple_asset_errors_collected_once(self) -> None:
        bad = _sha_fixture_png(self.tmp, "bad.png", (511, 511))
        empty = self.tmp / "empty.png"
        empty.write_bytes(b"not a png")
        spec = self.spec_with_game(assets={"portrait": bad, "frame": empty})
        with _isolated_render_context(), _no_dbf_session():
            with self.assertRaises(SpecErrors) as caught:
                self.make_port().preflight(spec)
        # 按 sorted(asset keys) 序收集：frame（坏字节 asset）→ portrait（尺寸）。
        self.assertEqual(caught.exception.codes, ("asset", "asset_dimensions"))
        self.assertEqual(
            caught.exception.paths,
            ("cards[0].asset.frame", "cards[0].asset.portrait"),
        )

    def test_override_semantics_input_routed_to_spec_errors(self) -> None:
        # 第 10 步返回的 INPUT Problem → SpecErrors（path 补卡级索引）。
        png = _sha_fixture_png(self.tmp, "ok.png", (512, 512))
        spec = self.spec_with_game(
            assets={"portrait": png},
            hero_style=True,
            style_requested=(True, True),
        )
        problems = (
            Problem(ProblemKind.INPUT, "style", "cards[0]", "style: 互斥"),
            Problem(ProblemKind.INPUT, "enum", "classes", "未知职业 X"),
        )

        def only_first_card(cards):
            return problems if cards[0].ref.value == 8 else ()

        with _isolated_render_context(), _no_dbf_session():
            with mock.patch(
                "eidolon.core.render.preflight.validate_overrides",
                side_effect=only_first_card,
            ):
                with self.assertRaises(SpecErrors) as caught:
                    self.make_port().preflight(spec)
        self.assertEqual(caught.exception.paths, ("cards[0]", "cards[0].classes"))

    def test_override_semantics_env_not_piled_into_spec_errors(self) -> None:
        # ENV Problem（constants_unavailable）→ EnvironmentUnavailable，
        # 不塞进 SpecErrors；INPUT 优先于 ENV。
        spec = self.spec_with_game()
        env_problem = Problem(
            ProblemKind.ENVIRONMENT,
            "constants_unavailable",
            "eidolon",
            "constants_unavailable: live 枚举缺名",
        )
        with _isolated_render_context(), _no_dbf_session():
            with mock.patch(
                "eidolon.core.render.preflight.validate_overrides",
                return_value=(env_problem,),
            ):
                with self.assertRaises(EnvironmentUnavailable) as caught:
                    self.make_port().preflight(spec)
        self.assertEqual(caught.exception.problem.code, "constants_unavailable")

    def test_input_takes_priority_over_env(self) -> None:
        spec = self.spec_with_game()
        problems = (
            Problem(ProblemKind.INPUT, "enum", "cost", "bad"),
            Problem(
                ProblemKind.ENVIRONMENT,
                "constants_unavailable",
                "eidolon",
                "env-ish",
            ),
        )

        def only_first_card(cards):
            return problems if cards[0].ref.value == 8 else ()

        with _isolated_render_context(), _no_dbf_session():
            with mock.patch(
                "eidolon.core.render.preflight.validate_overrides",
                side_effect=only_first_card,
            ):
                with self.assertRaises(SpecErrors) as caught:
                    self.make_port().preflight(spec)
        self.assertEqual(caught.exception.codes, ("enum",))

    def test_validate_overrides_receives_render_cards(self) -> None:
        # adapter 把 CardSpec → RenderCard（style_requested 语义）后交给 core。
        spec = self.spec_with_game(bg_style=True, style_requested=(False, True))
        seen: list[tuple] = []

        def capture(cards):
            seen.append(tuple(cards))
            return ()

        with _isolated_render_context(), _no_dbf_session():
            with mock.patch(
                "eidolon.core.render.preflight.validate_overrides",
                side_effect=capture,
            ):
                self.make_port().preflight(spec)
        self.assertEqual(len(seen), len(spec.cards))
        self.assertTrue(all(rc.bg_style for rc in seen[0]))
        self.assertFalse(seen[1][0].bg_style)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
