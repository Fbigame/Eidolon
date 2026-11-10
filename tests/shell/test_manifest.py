"""manifest 结构、稳定排序、路径与两种输入面的一致性。"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from eidolon.contracts import (
    CardRef,
    CatalogIdentity,
    EnvironmentUnavailable,
    Problem,
    ProblemKind,
    RenderedCard,
    RenderFailure,
    RenderReport,
)
from eidolon.shell.manifest import (
    build_manifest,
    build_result_manifest,
    manifest_json,
    report_exit_code,
    write_result_manifest,
)
from eidolon.shell.spec import build_spec
from tests.support import (
    BATCH_TOML,
    CATALOG_JSON,
    TomlCase,
    fixture_catalog,
    toml_with_card,
)


class BatchManifestTests(TomlCase):
    def setUp(self) -> None:
        super().setUp()
        self.spec = build_spec(
            toml_path=BATCH_TOML, catalog=fixture_catalog(), cwd=self.tmp
        )
        self.manifest = build_manifest(self.spec)

    def test_source_and_options(self) -> None:
        self.assertEqual(self.manifest["format_version"], 1)
        self.assertEqual(self.manifest["source"], "toml")
        options = self.manifest["options"]
        self.assertEqual(options["jobs"], 4)
        self.assertFalse(options["antialias"])
        self.assertTrue(Path(options["out_dir"]).is_absolute())
        self.assertEqual(self.manifest["warnings"], [])

    def test_cards_preserve_input_order(self) -> None:
        self.assertEqual(
            [card["input_id"] for card in self.manifest["cards"]],
            ["HERO_01", "8", "CS2_029", "CS2_112", "105108", "RLK_000"],
        )

    def test_all_outputs_are_absolute(self) -> None:
        for card in self.manifest["cards"]:
            self.assertTrue(Path(card["out"]).is_absolute(), card["out"])
        self.assertEqual(len({card["out"] for card in self.manifest["cards"]}), 6)

    def test_overrides_shape(self) -> None:
        card = self.manifest["cards"][1]
        overrides = card["overrides"]
        self.assertEqual(overrides["name"], "测试名字")
        self.assertEqual(overrides["classes"], ["MAGE"])
        self.assertEqual(overrides["races"], ["鱼人", "野兽"])
        self.assertEqual(overrides["fields"]["cost"], 3)
        self.assertEqual(overrides["fields"]["cost_banner"], "KABAL")
        self.assertTrue(overrides["fields"]["elite"])

    def test_assets_are_absolute_and_exist(self) -> None:
        card = self.manifest["cards"][4]
        self.assertTrue(card["bg_style"])
        assets = card["overrides"]["assets"]
        self.assertEqual(set(assets), {"portrait", "frame", "watermark"})
        for path in assets.values():
            self.assertTrue(Path(path).is_absolute())
            self.assertTrue(Path(path).is_file())

    def test_runes_sorted_in_manifest(self) -> None:
        card = self.manifest["cards"][5]
        self.assertEqual(
            card["overrides"]["fields"]["runes"], {"BLOOD": 1, "FROST": 2}
        )

    def test_manifest_is_json_serializable(self) -> None:
        text = json.dumps(self.manifest, ensure_ascii=False)
        self.assertIn("CS2_029", text)


class StabilityTests(TomlCase):
    def test_same_input_same_json(self) -> None:
        first = build_spec(
            toml_path=BATCH_TOML, catalog=fixture_catalog(), cwd=self.tmp
        )
        second = build_spec(
            toml_path=BATCH_TOML, catalog=fixture_catalog(), cwd=self.tmp
        )
        self.assertEqual(manifest_json(first), manifest_json(second))

    def test_top_level_key_order_is_canonical(self) -> None:
        spec = build_spec(toml_path=BATCH_TOML, catalog=fixture_catalog(), cwd=self.tmp)
        manifest = build_manifest(spec)
        self.assertEqual(
            list(manifest),
            ["format_version", "source", "options", "environment", "cards", "warnings"],
        )

    def test_inline_matches_equivalent_toml_except_source(self) -> None:
        out_dir = self.tmp / "out"
        toml_text = (
            "format_version = 1\n"
            f'out_dir = "{out_dir.as_posix()}"\n\n'
            "[[cards]]\n"
            "id = 8\n"
        )
        toml_spec = self.build(toml_text)
        inline_spec = build_spec(["8"], out_dir=out_dir, cwd=self.tmp)

        toml_manifest = build_manifest(toml_spec)
        inline_manifest = build_manifest(inline_spec)
        self.assertEqual(toml_manifest["source"], "toml")
        self.assertEqual(inline_manifest["source"], "inline")
        toml_manifest.pop("source")
        inline_manifest.pop("source")
        self.assertEqual(toml_manifest, inline_manifest)

    def test_inline_manifest_omits_empty_overrides(self) -> None:
        spec = build_spec(["8"], cwd=self.tmp)
        manifest = build_manifest(spec)
        self.assertNotIn("overrides", manifest["cards"][0])
        self.assertEqual(manifest["cards"][0]["deferred"], [])

    def test_only_given_override_fields_emitted(self) -> None:
        spec = self.build(toml_with_card("cost = 3\n"))
        overrides = build_manifest(spec)["cards"][0]["overrides"]
        self.assertEqual(overrides, {"fields": {"cost": 3}})

    def test_arrays_preserved_order(self) -> None:
        spec = self.build(
            toml_with_card('classes = ["PALADIN", "MAGE"]\nraces = ["野兽", "鱼人"]\n'),
            catalog=fixture_catalog(),
        )
        overrides = build_manifest(spec)["cards"][0]["overrides"]
        self.assertEqual(overrides["classes"], ["PALADIN", "MAGE"])
        self.assertEqual(overrides["races"], ["野兽", "鱼人"])

    def test_input_id_preserved_while_id_normalized(self) -> None:
        # 命令行允许纯数字字符串（TOML 里必须写整数）。
        spec = build_spec(["008"], cwd=self.tmp)
        card = build_manifest(spec)["cards"][0]
        self.assertEqual(card["input_id"], "008")
        self.assertEqual(card["id"], {"kind": "dbf", "value": 8})
        self.assertEqual(Path(card["out"]).name, "8.png")

    def test_deferred_is_deduplicated_and_ordered(self) -> None:
        # rev4：premium 不再 deferred（产品常量，恒直接校验）。
        # §5.4 后拆两态：cardtype 覆盖存在时 style 按生效 cardtype 直接校验
        # （hero_style=true × 生效 MINION → 报 2，不再 deferred）；style 的
        # deferred 只出现在「卡未知且无 cardtype 覆盖」。
        spec = self.build(
            toml_with_card(
                'classes = ["MAGE"]\ncardtype = "MINION"\nrarity = "LEGENDARY"\n'
                'premium = "GOLDEN"\nspell_school = "FIRE"\n'
            )
        )
        deferred = build_manifest(spec)["cards"][0]["deferred"]
        self.assertEqual(
            deferred,
            [
                "classes",
                "cardtype",
                "rarity",
                "spell_school",
            ],
        )
        self.assertEqual(len(deferred), len(set(deferred)))
        # style deferred 态：卡未知（null catalog）且无 cardtype 覆盖。
        style_spec = self.build(
            toml_with_card(
                "hero_style = true\nbg_style = true\n", card_id='"NOT_IN_CATALOG"'
            ),
            catalog=fixture_catalog(),
        )
        style_deferred = build_manifest(style_spec)["cards"][0]["deferred"]
        self.assertEqual(style_deferred, ["hero_style", "bg_style"])
        self.assertEqual(len(style_deferred), len(set(style_deferred)))


class DbfEnvironmentTests(TomlCase):
    """environment.dbf 三态：catalog.kind=="dbf" → 文件账；json / null → None。"""

    def _manifest_with_catalog(self, identity: CatalogIdentity) -> dict:
        spec = build_spec(["8"], cwd=self.tmp)
        return build_manifest(replace(spec, catalog=identity))

    def test_dbf_kind_emits_file_facts(self) -> None:
        manifest = self._manifest_with_catalog(
            CatalogIdentity(
                kind="dbf",
                path="<game-root>/Data/Win/dbf.unity3d",
                size=123,
                mtime_ns=456,
                complete=True,
            )
        )
        self.assertEqual(
            manifest["environment"]["dbf"],
            {"path": "<game-root>/Data/Win/dbf.unity3d", "size": 123, "mtime_ns": 456},
        )

    def test_json_kind_dbf_is_none(self) -> None:
        manifest = self._manifest_with_catalog(
            CatalogIdentity(kind="json", path="c.json", size=1, mtime_ns=2)
        )
        self.assertIsNone(manifest["environment"]["dbf"])

    def test_null_kind_dbf_is_none(self) -> None:
        manifest = self._manifest_with_catalog(CatalogIdentity(kind="null"))
        self.assertIsNone(manifest["environment"]["dbf"])


class FixtureSanityTests(unittest.TestCase):
    def test_fixture_files_exist(self) -> None:
        self.assertTrue(BATCH_TOML.is_file())
        self.assertTrue(CATALOG_JSON.is_file())


# ---------------------------------------------------------------------------
# 结果 manifest（设计 §7.9）
# ---------------------------------------------------------------------------


def _sha256_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


class ResultManifestCase(TomlCase):
    """结果 manifest 测试基座：两卡 spec + 混排 RenderReport。"""

    def setUp(self) -> None:
        super().setUp()
        self.out_dir = self.tmp / "out"
        self.out_dir.mkdir()
        portrait = self.tmp / "portrait.png"
        portrait.write_bytes((Path(__file__).parent.parent / "fixtures" / "art" / "portrait.png").read_bytes())
        spec = build_spec(
            ["8", "CS2_182"], out_dir=self.out_dir, catalog=fixture_catalog(), cwd=self.tmp
        )
        card0 = replace(
            spec.cards[0],
            name="覆盖名",
            cost=3,
            bg_style=True,
            style_requested=(False, True),
            assets={"portrait": portrait},
        )
        self.spec = replace(spec, cards=(card0, spec.cards[1]))
        self.out0 = self.spec.cards[0].out_path
        self.out1 = self.spec.cards[1].out_path
        self.rendered0 = RenderedCard(
            ref=self.spec.cards[0].ref,
            path=self.out0,
            sha256="a" * 64,
            elapsed_ms=812,
            warnings=("missing_glyphs:中:game:Futura",),
        )
        self.failure1 = RenderFailure(
            ref=self.spec.cards[1].ref,
            path=self.out1,
            problem=Problem(
                ProblemKind.ENVIRONMENT,
                "asset_missing_in_game",
                str(self.out1),
                "asset_missing_in_game: 游戏资产缺失",
                cause="FileNotFoundError: x",
            ),
        )
        self.report = RenderReport(
            rendered=(self.rendered0,),
            failures=(self.failure1,),
            # core api.render 的 report.warnings = 逐卡 warnings 汇总去重 + 绑定账。
            warnings=("missing_glyphs:中:game:Futura", "duplicate_card_id"),
        )

    def build_result(self, spec=None, report=None) -> dict:
        return build_result_manifest(
            self.spec if spec is None else spec,
            self.report if report is None else report,
        )


class ResultManifestStructureTests(ResultManifestCase):
    def test_top_level_key_order(self) -> None:
        manifest = self.build_result()
        self.assertEqual(
            list(manifest),
            ["format_version", "source", "options", "environment", "cards", "warnings"],
        )
        self.assertEqual(manifest["format_version"], 1)
        self.assertEqual(manifest["options"]["out_dir"],
                         str(self.spec.options.out_dir))
        self.assertEqual(
            manifest["environment"], build_manifest(self.spec)["environment"]
        )

    def test_cards_preserve_input_order_with_all_entries(self) -> None:
        cards = self.build_result()["cards"]
        self.assertEqual(
            [card["input_id"] for card in cards], ["8", "CS2_182"]
        )

    def test_ok_card_full_fields(self) -> None:
        card = self.build_result()["cards"][0]
        self.assertEqual(
            list(card),
            [
                "input_id",
                "id",
                "out",
                "ok",
                "sha256",
                "elapsed_ms",
                "hero_style",
                "bg_style",
                "style_requested",
                "warnings",
                "overrides",
                "assets_sha256",
            ],
        )
        self.assertTrue(card["ok"])
        self.assertEqual(card["sha256"], "a" * 64)
        self.assertEqual(card["elapsed_ms"], 812)
        self.assertFalse(card["hero_style"])
        self.assertTrue(card["bg_style"])
        self.assertEqual(card["style_requested"], [False, True])
        self.assertEqual(card["warnings"], ["missing_glyphs:中:game:Futura"])
        self.assertEqual(card["overrides"]["name"], "覆盖名")
        self.assertEqual(card["overrides"]["fields"]["cost"], 3)
        self.assertIn("assets", card["overrides"])

    def test_ok_card_assets_sha256_computed_from_file(self) -> None:
        card = self.build_result()["cards"][0]
        self.assertEqual(
            card["assets_sha256"],
            {"portrait": _sha256_of(self.spec.cards[0].assets["portrait"])},
        )

    def test_failed_card_carries_full_error_problem(self) -> None:
        card = self.build_result()["cards"][1]
        self.assertEqual(list(card), ["input_id", "id", "out", "ok", "error"])
        self.assertFalse(card["ok"])
        error = card["error"]
        self.assertEqual(
            list(error), ["kind", "code", "path", "message", "hint", "cause"]
        )
        self.assertEqual(error["kind"], "environment")
        self.assertEqual(error["code"], "asset_missing_in_game")
        self.assertEqual(error["path"], str(self.out1))
        self.assertIn("游戏资产缺失", error["message"])
        self.assertIn("FileNotFoundError", error["cause"])

    def test_style_requested_absent_in_plan_manifest(self) -> None:
        plan_card = build_manifest(self.spec)["cards"][0]
        self.assertNotIn("style_requested", plan_card)
        result_card = self.build_result()["cards"][0]
        self.assertIn("style_requested", result_card)

    def test_global_warnings_dedup_preserving_order(self) -> None:
        # spec.warnings + report.warnings + shell 侧，按出现顺序去重。
        spec = replace(self.spec, warnings=("catalog_incomplete", "duplicate_card_id"))
        manifest = self.build_result(spec=spec)
        self.assertEqual(
            manifest["warnings"],
            [
                "catalog_incomplete",
                "duplicate_card_id",
                "missing_glyphs:中:game:Futura",
            ],
        )

    def test_plain_card_omits_overrides_and_assets_sha256(self) -> None:
        card = self.build_result()["cards"][1]
        # 失败卡只带 error（§7.9 示例形状）；无 assets 字段。
        self.assertNotIn("assets_sha256", card)

    def test_json_serializable(self) -> None:
        import json

        text = json.dumps(self.build_result(), ensure_ascii=False)
        self.assertIn("CS2_182", text)


class ResultManifestAlignmentTests(ResultManifestCase):
    def test_entry_count_mismatch_raises(self) -> None:
        report = RenderReport(rendered=(self.rendered0,), failures=())
        with self.assertRaises(AssertionError):
            build_result_manifest(self.spec, report)

    def test_missing_entry_maps_to_render_failed_with_warning(self) -> None:
        # 条目数守恒但路径对不回：该卡 error=render_failed + report_missing。
        stray = RenderFailure(
            ref=self.spec.cards[1].ref,
            path=self.out_dir / "elsewhere.png",
            problem=Problem(
                ProblemKind.RENDER, "render_failed", str(self.out1), "boom"
            ),
        )
        report = RenderReport(rendered=(self.rendered0,), failures=(stray,))
        manifest = build_result_manifest(self.spec, report)
        card = manifest["cards"][1]
        self.assertFalse(card["ok"])
        self.assertEqual(card["error"]["code"], "render_failed")
        self.assertTrue(
            any(w.startswith("report_missing") for w in manifest["warnings"]),
            manifest["warnings"],
        )

    def test_duplicate_path_entries_raise(self) -> None:
        report = RenderReport(
            rendered=(self.rendered0, self.rendered0), failures=()
        )
        with self.assertRaises(AssertionError):
            build_result_manifest(self.spec, report)

    def test_out_path_matching_is_case_insensitive_on_windows(self) -> None:
        # 渲染 worker 返回的 path 若大小写漂移，规范化后仍能对回。
        drifted = replace(self.rendered0, path=Path(str(self.out0).upper()))
        report = RenderReport(rendered=(drifted,), failures=(self.failure1,))
        manifest = build_result_manifest(self.spec, report)
        self.assertTrue(manifest["cards"][0]["ok"])


class AssetHashUnavailableTests(ResultManifestCase):
    def test_vanished_asset_omits_key_and_warns(self) -> None:
        # 资产在 preflight 后消失 → 该键省略 + asset_hash_unavailable warning
        # （不让整批失败；不是 asset_missing_in_game 3）。
        self.spec.cards[0].assets["portrait"].unlink()
        manifest = self.build_result()
        card = manifest["cards"][0]
        self.assertNotIn("assets_sha256", card)
        self.assertTrue(
            any(
                w.startswith("asset_hash_unavailable") for w in manifest["warnings"]
            ),
            manifest["warnings"],
        )
        self.assertTrue(card["ok"])  # 渲染结果不受影响


class ReportExitCodeTests(unittest.TestCase):
    """退出码三态矩阵：ENV 3 > RENDER/INTERNAL 1 > 0（§9.3 单源）。"""

    _ref = CardRef("dbf", 8)

    def _failure(self, kind: ProblemKind) -> RenderFailure:
        return RenderFailure(
            ref=self._ref,
            path=Path("out.png"),
            problem=Problem(kind, "some_code", "p", "m"),
        )

    def test_empty_report_exit_0(self) -> None:
        self.assertEqual(report_exit_code(RenderReport()), 0)

    def test_render_failure_exit_1(self) -> None:
        self.assertEqual(
            report_exit_code(RenderReport(failures=(self._failure(ProblemKind.RENDER),))), 1
        )

    def test_internal_failure_exit_1(self) -> None:
        self.assertEqual(
            report_exit_code(RenderReport(failures=(self._failure(ProblemKind.INTERNAL),))), 1
        )

    def test_environment_failure_exit_3(self) -> None:
        self.assertEqual(
            report_exit_code(
                RenderReport(failures=(self._failure(ProblemKind.ENVIRONMENT),))
            ),
            3,
        )

    def test_environment_wins_over_render(self) -> None:
        report = RenderReport(
            failures=(
                self._failure(ProblemKind.RENDER),
                self._failure(ProblemKind.ENVIRONMENT),
            )
        )
        self.assertEqual(report_exit_code(report), 3)


class WriteResultManifestTests(ResultManifestCase):
    def test_writes_manifest_json_and_returns_path(self) -> None:
        import json as json_lib

        path = write_result_manifest(self.spec, self.report)
        self.assertEqual(path, self.spec.options.out_dir / "manifest.json")
        self.assertTrue(path.is_file())
        data = json_lib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["format_version"], 1)
        self.assertEqual(len(data["cards"]), 2)
        self.assertTrue(data["cards"][0]["ok"])

    def test_write_failure_maps_write_failed_env(self) -> None:
        # Windows 对目录的只读位不拦截建文件（OS 行为），chmod 模拟不可靠；
        # 改用「out_dir 运行中被删」的确定性 OSError 路径（其他进程占用/
        # 只读盘等最终都收敛到同一 OSError → write_failed 包装）。
        import shutil

        shutil.rmtree(self.out_dir)
        with self.assertRaises(EnvironmentUnavailable) as caught:
            write_result_manifest(self.spec, self.report)
        problem = caught.exception.problem
        self.assertEqual(problem.code, "write_failed")
        self.assertEqual(problem.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(problem.path,
                         str(self.spec.options.out_dir / "manifest.json"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
