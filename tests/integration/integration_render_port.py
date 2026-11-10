"""integration_render_port — Phase 3c 产品端口全链（真实游戏；显式跑；真实 CLI 子进程）。

覆盖面（设计 §7.1 / §7.7 / §7.9 / §12.2 诊断顺序）：
  * 产品端口全链：``python -m eidolon render 8 --game … --antialias``（默认
    factory = DbfCatalogProvider + CoreRenderPort）→ 退出 0、stdout 计划
    manifest（JSON 可解析）、``out_dir/manifest.json`` 结果 manifest、PNG
    512×707、结果 manifest ok 卡 sha256 与 PNG 实际 sha 一致、environment
    game/dbf/catalog 三段完整；
  * worker 等价：``--jobs 4`` 与 ``--jobs 1`` 同 outdir 不同 subdir → PNG
    sha 与结果 manifest sha256 一致（§11.3）；
  * 覆盖冒烟：TOML cost/name 覆盖 + portrait 资产（PIL 造 512×512）→
    结果 manifest overrides / assets_sha256 记录、渲染成功（preflight 第 10
    步真实 validate_overrides 过；不比像素）；
  * 覆盖错误：portrait 511×511 → 退出 2（preflight ``asset_dimensions``，
    stdout 空——诊断顺序第 4 步在 plan manifest 前）；
  * 坏 dbf：tmp 造 1 字节 dbf.unity3d + Hearthstone.exe → spec/render 均
    退出 3（``dbf_unreadable``；provider.bind 期，先于 port）；
  * tag 写 → desc 账重建回归钉子（Phase 3c 对 core/infra/card.py
    `_invalidate_tag_derived` 修正的验收；进程内，adopt-or-install ctx）；
  * adapters 顶层 import 守卫（§7.1.1 的 import 面）：子进程 import
    ``eidolon.adapters`` 后 sys.modules 无 eidolon.core / UnityPy。

产品链测试统一走 ``python -m eidolon`` 子进程：同进程先行的
integration 文件（integration_dbf_catalog）已 install 异 cache_root 的渲染
身份，context 无卸载 API，进程内再走 entry.main 会撞「一个进程一个渲染
身份」；子进程天然干净，且更贴近真实调用面。

默认 discover（pattern ``test*.py``）**不收集**本文件；显式跑（需游戏 +
UnityPy + CLR + pythonnet）：
    EIDOLON_TEST_GAME=<游戏根> python -m unittest discover -s tests/integration -p 'integration_*.py' -t . -v

缓存根策略（与 integration_render_smoke 同款同值）：默认
``build/integration_supply_cache``（route.db 跨跑复用），``EIDOLON_TEST_CACHE``
可覆盖；产品链调用显式 ``--cache-root`` 同值。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eidolon.contracts import GameRequest
from eidolon.core.infra import context
from eidolon.core.infra.game_install import resolve_context

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None

_REPO = Path(__file__).resolve().parents[2]
_cache_env = os.environ.get("EIDOLON_TEST_CACHE", "").strip()
CACHE_ROOT: Path = (Path(_cache_env) if _cache_env
                    else _REPO / "build" / "integration_supply_cache")

_COMMON = ["--game", str(GAME_ROOT), "--cache-root", str(CACHE_ROOT)] if GAME_ROOT else []


def _run_cli(args: list[str], *, env_extra: dict[str, str] | None = None) -> tuple[int, str, str]:
    """真实 CLI 子进程（``python -m eidolon``）。

    产品链经子进程而非进程内 main：同进程先行的 integration 文件
    （integration_dbf_catalog）已 install 异 cache_root 的渲染身份，context
    无卸载 API，进程内再走 entry.main 会撞「一个进程一个渲染身份」；子进程
    天然干净，且更贴近真实调用面。stdout 只含计划 manifest（JSON），日志/
    warning 走 stderr。``env_extra`` 在继承环境上追加变量（如 DOTNET_ROOT
    负环境模拟），不影响其他用例。
    """
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, "-m", "eidolon", *args],
        cwd=_REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=420,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class RenderPortFullChainTests(unittest.TestCase):
    """产品端口全链验收（默认 factory：真实 provider + 真实 port）。"""

    @classmethod
    def setUpClass(cls) -> None:
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmpdir.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def _read_result(self, outdir: Path) -> dict:
        return json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))

    # ---- 产品端口全链 ----

    def test_render_full_chain_plan_and_result_manifest(self) -> None:
        outdir = self.tmp / "full" / "out"
        code, stdout, stderr = _run_cli(
            ["render", "8", *self._common(), "--outdir", str(outdir), "--antialias"]
        )
        self.assertEqual(code, 0, stderr)
        # 计划 manifest（stdout，§12.2 第 5 步）可解析；style_requested 不进 plan。
        plan = json.loads(stdout)
        self.assertEqual(plan["source"], "inline")
        self.assertNotIn("style_requested", plan["cards"][0])
        # 结果 manifest（out_dir/manifest.json，§7.9）。
        result_path = outdir / "manifest.json"
        self.assertTrue(result_path.is_file())
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(
            list(result),
            ["format_version", "source", "options", "environment", "cards", "warnings"],
        )
        self.assertEqual(result["environment"], plan["environment"])
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertEqual(card["input_id"], "8")
        self.assertEqual(card["id"], {"kind": "dbf", "value": 8})
        # PNG 512×707 + sha 一致（结果 manifest 可复算）。
        from PIL import Image

        png = outdir / "8.png"
        self.assertTrue(png.is_file())
        with Image.open(png) as im:
            self.assertEqual(im.size, (512, 707))
        self.assertEqual(card["sha256"], _sha256_of(png))
        self.assertGreaterEqual(card["elapsed_ms"], 0)
        self.assertEqual(card["hero_style"], False)
        self.assertEqual(card["bg_style"], False)
        self.assertEqual(card["style_requested"], [False, False])
        self.assertIn("warnings", card)
        # environment 三段完整。
        env = result["environment"]
        self.assertIsNotNone(env["game"])
        self.assertTrue(env["game"]["root"])
        self.assertIsNotNone(env["dbf"])
        self.assertTrue(Path(env["dbf"]["path"]).is_file())
        self.assertGreater(env["dbf"]["size"], 0)
        self.assertEqual(env["catalog"]["kind"], "dbf")
        self.assertTrue(env["catalog"]["complete"])
        self.assertTrue(env["eidolon"])

    def test_jobs_equivalence(self) -> None:
        # §11.3：worker 与串行同 sha（同 outdir 不同 subdir）。
        out1 = self.tmp / "jobs1" / "out"
        out4 = self.tmp / "jobs4" / "out"
        code1, _, err1 = _run_cli(
            ["render", "8", *self._common(), "--outdir", str(out1), "--jobs", "1",
             "--antialias"]
        )
        self.assertEqual(code1, 0, err1)
        code4, _, err4 = _run_cli(
            ["render", "8", *self._common(), "--outdir", str(out4), "--jobs", "4",
             "--antialias"]
        )
        self.assertEqual(code4, 0, err4)
        sha1 = _sha256_of(out1 / "8.png")
        sha4 = _sha256_of(out4 / "8.png")
        self.assertEqual(sha1, sha4, "--jobs 4 与 --jobs 1 输出 sha 不一致")
        result4 = self._read_result(out4)
        self.assertEqual(result4["cards"][0]["sha256"], sha1)
        self.assertEqual(result4["options"]["jobs"], 4)

    def test_jobs_equivalence_multi(self) -> None:
        # §11.3 真多进程等价：core api 在 len(cards) <= 1 时走串行——旧单卡
        # 用例从未进进程池；2 张卡 --jobs 4 才真进池。1x（--antialias 可省），
        # 两侧同设，逐卡比对 sha。
        out1 = self.tmp / "jobs1_multi" / "out"
        out4 = self.tmp / "jobs4_multi" / "out"
        code1, _, err1 = _run_cli(
            ["render", "8", "CS2_182", *self._common(), "--outdir", str(out1),
             "--jobs", "1"]
        )
        self.assertEqual(code1, 0, err1)
        code4, _, err4 = _run_cli(
            ["render", "8", "CS2_182", *self._common(), "--outdir", str(out4),
             "--jobs", "4"]
        )
        self.assertEqual(code4, 0, err4)
        result1 = self._read_result(out1)
        result4 = self._read_result(out4)
        self.assertEqual(len(result4["cards"]), 2)
        self.assertTrue(all(card["ok"] for card in result4["cards"]))
        self.assertEqual([card["input_id"] for card in result4["cards"]],
                         ["8", "CS2_182"])
        self.assertEqual(result4["options"]["jobs"], 4)
        for card1, card4 in zip(result1["cards"], result4["cards"]):
            self.assertEqual(
                card4["sha256"], card1["sha256"],
                f"card {card4['input_id']}: --jobs 4 与串行 sha 不一致",
            )
        pngs = sorted(p.name for p in out4.glob("*.png"))
        self.assertEqual(pngs, ["8.png", "CS2_182.png"])

    # ---- 覆盖冒烟（§10.0/§10.1；preflight 第 9/10 步真实链）----

    def _write_override_toml(self, outdir: Path, portrait: Path,
                             *, cost: int = 7) -> Path:
        toml = self.tmp / "overrides" / "job.toml"
        toml.parent.mkdir(parents=True, exist_ok=True)
        toml.write_text(
            "format_version = 1\n"
            f'out_dir = "{outdir.as_posix()}"\n\n'
            "[[cards]]\n"
            "id = 8\n"
            "name = \"甲虫占位名\"\n"
            f"cost = {cost}\n"
            "\n[cards.asset]\n"
            f'portrait = "{portrait.as_posix()}"\n',
            encoding="utf-8",
        )
        return toml

    def test_override_smoke_records_overrides_and_assets_sha(self) -> None:
        from PIL import Image

        base = self.tmp / "override"
        base.mkdir(parents=True, exist_ok=True)
        portrait = base / "portrait.png"
        Image.new("RGBA", (512, 512), (120, 40, 200, 255)).save(portrait)
        outdir = base / "out"
        toml = self._write_override_toml(outdir, portrait)
        code, stdout, stderr = _run_cli(
            ["render", "--toml", str(toml), *self._common()]
        )
        self.assertEqual(code, 0, stderr)
        plan = json.loads(stdout)  # 计划 manifest 已打印（§12.2 第 5 步）
        self.assertEqual(plan["cards"][0]["overrides"]["fields"]["cost"], 7)
        result = self._read_result(outdir)
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertEqual(card["overrides"]["name"], "甲虫占位名")
        self.assertEqual(card["overrides"]["fields"]["cost"], 7)
        self.assertEqual(card["overrides"]["assets"]["portrait"], str(portrait))
        self.assertEqual(card["assets_sha256"], {"portrait": _sha256_of(portrait)})
        png = outdir / "8.png"
        self.assertTrue(png.is_file())
        self.assertEqual(card["sha256"], _sha256_of(png))

    def test_override_bad_dimensions_exit_2_with_empty_stdout(self) -> None:
        from PIL import Image

        base = self.tmp / "bad_dim"
        base.mkdir(parents=True, exist_ok=True)
        portrait = base / "portrait.png"
        Image.new("RGBA", (511, 511), (0, 0, 0, 255)).save(portrait)
        outdir = base / "out"
        toml = self._write_override_toml(outdir, portrait)
        code, stdout, stderr = _run_cli(
            ["render", "--toml", str(toml), *self._common()]
        )
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")  # preflight 在 plan manifest 前（§12.2）
        self.assertIn("error[asset_dimensions]", stderr)
        self.assertIn("cards[0].asset.portrait", stderr)
        self.assertFalse((outdir / "manifest.json").exists())

    # ---- core 回归：tag 写 → desc 账重建（Phase 3c 修正的钉子；进程内）----

    def test_tag_write_then_desc_account_rebuilds(self) -> None:
        # _invalidate_tag_derived 曾 pop 普通实例属性 _desc_account →
        # 任何 tag 写覆盖（cost 等 12 键）+ desc 渲染必 AttributeError。
        # 修正后置 None（property 重建前置态）；本测试钉住该语义。
        from eidolon.core.infra import dbf
        from eidolon.core.infra.dbf import DbfModule

        # ctx：adopt-or-install（dbf_catalog 先行时会装异 cache_root 身份；
        # desc 账只用 Managed/CLR 与 dbf 会话，cache_root 不参与）。
        # card.py 是 CLR-at-import（§6.5），import 必须在 install 之后。
        if context.installed() is None:
            ctx = resolve_context(GameRequest(GAME_ROOT, "--game"),
                                  cache_root=CACHE_ROOT, locale="zhcn")
            context.install(ctx)
        from eidolon.core.infra.card import Card

        had_session = dbf.installed_default() is not None
        if not had_session:
            dbf.install_default(DbfModule(GAME_ROOT / "Data" / "Win" / "dbf.unity3d"))
        try:
            card = Card.from_dbf(8)
            first = card.desc_text_account  # 首次访问（懒 CLR；建立账）
            self.assertIsInstance(first, dict)
            card.tags[48] = 7  # COST 写 → _invalidate_tag_derived 触发
            second = card.desc_text_account  # 修正前在此 AttributeError
            self.assertIsInstance(second, dict)
            self.assertIn("text", second)
        finally:
            if not had_session:
                dbf.reset_default()

    # ---- 坏 dbf（provider.bind 期 ENV 3；换根必须走子进程）----

    def test_broken_dbf_spec_and_render_exit_3(self) -> None:
        broken = self.tmp / "broken_game"
        (broken / "Data" / "Win").mkdir(parents=True, exist_ok=True)
        (broken / "Hearthstone.exe").write_bytes(b"")
        (broken / "Data" / "Win" / "dbf.unity3d").write_bytes(b"\x00")
        for command in ("spec", "render"):
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, "-m", "eidolon", command, "8",
                     "--game", str(broken)],
                    cwd=_REPO,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=180,
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn("dbf_unreadable", result.stderr)
                self.assertEqual(result.stdout, "")

    # ---- adapters import 面（§7.1.1）----

    def test_adapters_top_level_import_loads_no_core(self) -> None:
        probe = (
            "import json, sys\n"
            "import eidolon.adapters\n"
            "mods = sorted(\n"
            "    m for m in sys.modules\n"
            "    if m == 'eidolon.core'\n"
            "    or m.startswith('eidolon.core.')\n"
            "    or m.split('.')[0] == 'UnityPy'\n"
            ")\n"
            "print(json.dumps(mods))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=_REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]), [])

    def _common(self) -> list[str]:
        return _COMMON


class DotnetRuntimePreflightTests(unittest.TestCase):
    """preflight 第 3 步后半的 .NET 运行时真探测（显式集成；真实 CLR 语义）。

    单元面（tests/entry/test_adapters.py）用 pythonnet.load 打桩钉映射与
    缓存；这里在真实 CLI 子进程验证产品语义：
      * DOTNET_ROOT 指空目录（模拟无 .NET 运行时）→ render 退出 3
        （ENVIRONMENT dependency_missing / env:dotnet），preflight 在计划
        manifest 前拦截（stdout 空、无结果 manifest）；
      * spec 面不构造渲染端口、不 load CLR：同一负环境下 spec --catalog
        仍可用（无需游戏安装）。
    """

    def setUp(self) -> None:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.tmp = Path(tmpdir.name)

    @unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                         "本机未设 EIDOLON_TEST_GAME 或路径不存在")
    def test_render_without_dotnet_runtime_exit_3(self) -> None:
        empty_dotnet_root = self.tmp / "dotnet_root"
        empty_dotnet_root.mkdir()  # 空目录：hostfxr 缺失 → load("coreclr") 抛
        self.assertTrue(GAME_ROOT)
        outdir = self.tmp / "out"
        code, stdout, stderr = _run_cli(
            ["render", "8", "--game", str(GAME_ROOT),
             "--cache-root", str(CACHE_ROOT), "--outdir", str(outdir)],
            env_extra={"DOTNET_ROOT": str(empty_dotnet_root)},
        )
        self.assertEqual(code, 3, stderr)
        self.assertEqual(stdout, "")  # preflight 在计划 manifest 前（§12.2）
        self.assertIn("error[dependency_missing]", stderr)
        self.assertIn("env:dotnet", stderr)
        self.assertIn(".NET", stderr)
        self.assertFalse((outdir / "manifest.json").exists())

    @unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                         "本机未设 EIDOLON_TEST_GAME 或路径不存在")
    def test_render_with_default_dotnet_succeeds(self) -> None:
        # 正常环境不受影响：不带 env_extra 的同链路渲染成功（探针真跑一次
        # 后缓存，渲染链后续 dll_reflect 的再调不冲突）。
        outdir = self.tmp / "out_ok"
        code, _, stderr = _run_cli(
            ["render", "8", "--game", str(GAME_ROOT),
             "--cache-root", str(CACHE_ROOT), "--outdir", str(outdir)],
        )
        self.assertEqual(code, 0, stderr)
        result = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(result["cards"][0]["ok"])

    def test_spec_does_not_probe_clr(self) -> None:
        # spec 面不探 CLR：负环境（DOTNET_ROOT 指空目录）下 spec 仍可用。
        empty_dotnet_root = self.tmp / "dotnet_root"
        empty_dotnet_root.mkdir()
        code, stdout, stderr = _run_cli(
            ["spec", "--toml", str(_REPO / "tests" / "fixtures" / "batch.toml"),
             "--catalog", str(_REPO / "tests" / "fixtures" / "catalog.json")],
            env_extra={"DOTNET_ROOT": str(empty_dotnet_root)},
        )
        self.assertEqual(code, 0, stderr)
        plan = json.loads(stdout)
        # 批量 fixture 第 2 张卡是 id=8；plan manifest 已含 input_id 定位。
        self.assertEqual(plan["cards"][1]["input_id"], "8")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
