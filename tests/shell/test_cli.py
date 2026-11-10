"""CLI：退出码、stdout/stderr、互斥模式、render 真实端口返回路径（经 entry.main）。

Phase 3c：``render`` 不再有 stub——fake port 返回 ``RenderReport`` 后
cli 写结果 manifest（``out_dir/manifest.json``）并按 report 汇总退出码。
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from eidolon.contracts import (
    InputRejected,
    EnvironmentUnavailable,
    Problem,
    ProblemKind,
    RenderReport,
    RenderedCard,
)
from eidolon.entry import main
from eidolon.shell.catalog import NullCatalogProvider
from tests.support import BATCH_TOML, CATALOG_JSON, ROOT


def run_cli(args: list[str], cwd: str | Path | None = None, **kwargs) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(args, cwd=cwd, **kwargs)
    return code, stdout.getvalue(), stderr.getvalue()


class _FakeRenderPort:
    """render 命令的确定性 fake：preflight 可注入异常，render 返回与
    spec 卡数对齐的 ``RenderReport``（cli 会写结果 manifest）。"""

    def __init__(self, *, preflight_error: Exception | None = None,
                 render_error: Exception | None = None) -> None:
        self.preflight_calls: int = 0
        self.render_calls: int = 0
        self._preflight_error = preflight_error
        self._render_error = render_error

    def preflight(self, spec) -> None:
        self.preflight_calls += 1
        if self._preflight_error is not None:
            raise self._preflight_error
        # 真实 preflight 的契约之一：确保 out_dir 存在且可写（§7.7 第 8 步）。
        from pathlib import Path as _P

        _P(spec.options.out_dir).mkdir(parents=True, exist_ok=True)

    def render(self, spec) -> RenderReport:
        self.render_calls += 1
        if self._render_error is not None:
            raise self._render_error
        return RenderReport(
            rendered=tuple(
                RenderedCard(ref=card.ref, path=card.out_path, sha256="0" * 64,
                             elapsed_ms=1)
                for card in spec.cards
            )
        )


class SpecCommandTests(unittest.TestCase):
    def test_spec_toml_with_catalog(self) -> None:
        code, out, err = run_cli(
            ["spec", "--toml", str(BATCH_TOML), "--catalog", str(CATALOG_JSON)]
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        manifest = json.loads(out)
        self.assertEqual(manifest["source"], "toml")
        self.assertEqual(len(manifest["cards"]), 6)
        self.assertTrue(Path(manifest["cards"][0]["out"]).is_absolute())

    def test_spec_inline(self) -> None:
        code, out, err = run_cli(
            ["spec", "8", "--catalog", str(CATALOG_JSON)]
        )
        self.assertEqual(code, 0, err)
        manifest = json.loads(out)
        self.assertEqual(manifest["source"], "inline")
        self.assertEqual(manifest["cards"][0]["id"], {"kind": "dbf", "value": 8})

    def test_spec_inline_without_catalog_defers(self) -> None:
        # Phase 1b：默认 provider 是真实 DbfCatalogProvider（依赖游戏安装）；
        # dev 断言注入 NullCatalogProvider 保持原语义（null binding → deferred）。
        code, out, err = run_cli(["spec", "8"], provider_factory=NullCatalogProvider)
        self.assertEqual(code, 0, err)
        manifest = json.loads(out)
        self.assertEqual(manifest["cards"][0]["deferred"], [])
        self.assertEqual(manifest["environment"]["game"], None)

    def test_spec_global_styles(self) -> None:
        code, out, err = run_cli(
            [
                "spec",
                "HERO_01",
                "8",
                "--hero-style",
                "--bg-style",
                "--catalog",
                str(CATALOG_JSON),
            ]
        )
        self.assertEqual(code, 0, err)
        cards = json.loads(out)["cards"]
        self.assertEqual(
            [(card["hero_style"], card["bg_style"]) for card in cards],
            [(True, False), (False, True)],
        )

    def test_spec_antialias_and_jobs(self) -> None:
        code, out, err = run_cli(
            ["spec", "8", "--jobs", "4", "--antialias", "--outdir", "out"],
            provider_factory=NullCatalogProvider,
        )
        self.assertEqual(code, 0, err)
        options = json.loads(out)["options"]
        self.assertEqual(options["jobs"], 4)
        self.assertTrue(options["antialias"])
        self.assertTrue(Path(options["out_dir"]).is_absolute())


class CliErrorTests(unittest.TestCase):
    def test_invalid_id_exit_2(self) -> None:
        code, out, err = run_cli(["spec", "bad-id"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("invalid_id", err)
        self.assertIn("ids[0]", err)

    def test_both_input_modes_exit_2(self) -> None:
        code, out, err = run_cli(
            ["spec", "8", "--toml", str(BATCH_TOML)]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("互斥", err)

    def test_no_input_exit_2(self) -> None:
        code, out, err = run_cli(["spec"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("至少需要一个", err)

    def test_toml_conflicts_with_global_flags(self) -> None:
        cases = [
            ["--hero-style"],
            ["--bg-style"],
            ["--antialias"],
            ["--jobs", "2"],
            ["--outdir", "out"],
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                code, out, err = run_cli(
                    ["spec", "--toml", str(BATCH_TOML), *extra]
                )
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("option_not_allowed", err)

    def test_jobs_zero_exit_2(self) -> None:
        code, out, err = run_cli(["spec", "8", "--jobs", "0"])
        self.assertEqual(code, 2)
        self.assertIn("--jobs", err)

    def test_spec_dbf_missing_exit_3_subprocess(self) -> None:
        # Phase 1b 验收：spec 默认路径走真实 provider → resolve_context → dbf
        # 检查。显式 --game（含 exe、缺 Data/Win/dbf.unity3d）是确定性退出 3
        # 路径，不依赖本机真实游戏安装与否。
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "Hearthstone.exe").write_bytes(b"")
        result = subprocess.run(
            [sys.executable, "-m", "eidolon", "spec", "8", "--game", str(tmp)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("dbf_missing", result.stderr)
        self.assertIn("hint:", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_complete_catalog_unknown_card_exit_2(self) -> None:
        complete = CATALOG_JSON.parent / "catalog_complete.json"
        code, out, err = run_cli(["spec", "8", "--catalog", str(complete)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("error[unknown_card]", err)

    def test_missing_catalog_exit_2(self) -> None:
        code, out, err = run_cli(
            ["spec", "8", "--catalog", str(BATCH_TOML.parent / "nope.json")]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("catalog", err)

    def test_unknown_argument_exits_2(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main(["spec", "--nope"])
        self.assertEqual(caught.exception.code, 2)

    def test_non_int_jobs_exits_2(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main(["spec", "8", "--jobs", "many"])
        self.assertEqual(caught.exception.code, 2)


class RenderCommandTests(unittest.TestCase):
    """render 真实返回路径（fake port；结果 manifest + 退出码矩阵）。"""

    def _tmp(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_render_fake_port_success_writes_result_manifest(self) -> None:
        tmp = self._tmp()
        outdir = tmp / "out"
        port = _FakeRenderPort()
        code, out, err = run_cli(
            ["render", "8", "--outdir", str(outdir)],
            cwd=tmp,
            provider_factory=NullCatalogProvider,
            port_factory=lambda: port,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(port.render_calls, 1)
        # 计划 manifest 仍写 stdout；结果 manifest 写 out_dir/manifest.json。
        plan = json.loads(out)
        self.assertEqual(len(plan["cards"]), 1)
        result = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(result["format_version"], 1)
        self.assertEqual(len(result["cards"]), 1)
        self.assertTrue(result["cards"][0]["ok"])
        self.assertEqual(result["warnings"], [])

    def test_render_preflight_input_error_exit_2_empty_stdout(self) -> None:
        from eidolon.shell.errors import SpecErrors

        errors = SpecErrors()
        errors.add("out_dir_invalid", "--outdir", "输出目录形状非法")
        tmp = self._tmp()
        code, out, err = run_cli(
            ["render", "8", "--outdir", str(tmp / "out")],
            cwd=tmp,
            provider_factory=NullCatalogProvider,
            port_factory=lambda: _FakeRenderPort(preflight_error=errors),
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")  # preflight 在打印计划 manifest 前
        self.assertIn("error[out_dir_invalid]", err)

    def test_render_preflight_env_error_exit_3_empty_stdout(self) -> None:
        problem = Problem(
            ProblemKind.ENVIRONMENT, "out_dir_unwritable", "out", "输出目录不可写"
        )
        tmp = self._tmp()
        code, out, err = run_cli(
            ["render", "8", "--outdir", str(tmp / "out")],
            cwd=tmp,
            provider_factory=NullCatalogProvider,
            port_factory=lambda: _FakeRenderPort(
                preflight_error=EnvironmentUnavailable(problem)
            ),
        )
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertIn("error[out_dir_unwritable]", err)

    def test_render_input_rejected_from_port_maps_2(self) -> None:
        # InputRejected（core 输入类，防 core 直调路径）→ 打印 Problem、退出 2。
        problem = Problem(
            ProblemKind.INPUT, "unknown_rune", "cards[0].runes.X", "未知 rune"
        )
        tmp = self._tmp()
        code, out, err = run_cli(
            ["render", "8", "--outdir", str(tmp / "out")],
            cwd=tmp,
            provider_factory=NullCatalogProvider,
            port_factory=lambda: _FakeRenderPort(
                render_error=InputRejected(problem)
            ),
        )
        self.assertEqual(code, 2)
        self.assertIn("error[unknown_rune]", err)

    def test_render_with_catalog_exit_2(self) -> None:
        # --catalog 仅 spec：render + --catalog → usage（2），stdout 为空。
        code, out, err = run_cli(
            ["render", "--toml", str(BATCH_TOML), "--catalog", str(CATALOG_JSON)]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("usage", err)
        self.assertIn("--catalog", err)

    def test_render_invalid_input_exit_2(self) -> None:
        code, out, err = run_cli(["render", "bad-id"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("invalid_id", err)


class CatalogExclusiveTests(unittest.TestCase):
    """--catalog 仅 spec，且与 --game / TOML game_dir 互斥。"""

    def test_catalog_with_game_exit_2(self) -> None:
        code, out, err = run_cli(
            [
                "spec",
                "8",
                "--catalog",
                str(CATALOG_JSON),
                "--game",
                str(ROOT / "fixtures-game"),
            ]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("usage", err)

    def test_catalog_with_toml_game_dir_exit_2(self) -> None:
        toml = self._write_toml_with_game_dir()
        code, out, err = run_cli(
            ["spec", "--toml", str(toml), "--catalog", str(CATALOG_JSON)]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("usage", err)
        self.assertIn("game_dir", err)

    def _write_toml_with_game_dir(self) -> Path:
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(_rmtree, tmp)
        path = tmp / "job.toml"
        path.write_text(
            'format_version = 1\n'
            f'game_dir = "{(tmp / "game").as_posix()}"\n\n'
            "[[cards]]\nid = 8\n",
            encoding="utf-8",
        )
        (tmp / "game").mkdir()
        (tmp / "game" / "Hearthstone.exe").write_bytes(b"")
        return path


def _rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


class ModuleEntryTests(unittest.TestCase):
    def _tmp(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_python_m_eidolon_spec(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "eidolon",
                "spec",
                "8",
                "--catalog",
                str(CATALOG_JSON),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["source"], "inline")

    def test_python_m_eidolon_render_fake_port(self) -> None:
        # 子进程探针：注入 dev provider + fake port（返回对齐 RenderReport），
        # 验证整条 render 编排（计划 manifest → 结果 manifest → 退出 0）。
        import json as json_lib

        tmp = self._tmp()
        outdir = tmp / "out"
        probe = (
            "import sys\n"
            "from pathlib import Path\n"
            "from eidolon.contracts import RenderReport, RenderedCard\n"
            "from eidolon.entry import main\n"
            "from eidolon.shell.catalog import NullCatalogProvider\n"
            "class FakePort:\n"
            "    def preflight(self, spec):\n"
            "        spec.options.out_dir.mkdir(parents=True, exist_ok=True)\n"
            "    def render(self, spec):\n"
            "        return RenderReport(rendered=tuple(\n"
            "            RenderedCard(ref=c.ref, path=c.out_path, sha256='0'*64,\n"
            "                         elapsed_ms=1) for c in spec.cards))\n"
            f"outdir = Path(r'{outdir}')\n"
            "code = main(['render', '8', '--outdir', str(outdir)],\n"
            "            provider_factory=NullCatalogProvider,\n"
            "            port_factory=FakePort)\n"
            "print(outdir.joinpath('manifest.json').is_file())\n"
            "sys.exit(code)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "True")
        data = json_lib.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(data["cards"][0]["ok"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
