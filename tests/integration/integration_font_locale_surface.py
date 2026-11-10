"""integration_font_locale_surface — B4 判据（字体/locale 失败面；显式跑，需游戏）。

任务单 §10 B4：非 zhcn locale、空字体目录、无中文字体的失败面；判据 =
**响亮或明确回退**——每条路径要么 typed 错误响亮退出，要么有明确文档化的
回退行为，不许静默出坏图。

五条路径的判据（证据落盘 ``build/phase1/b4/``）：

1. **未知 locale**（``--locale nosuch``）：preflight typed
   ``locale_missing``（ENV 3）——stderr ``error[locale_missing]`` 带可用
   语言目录清单，stdout 空（preflight 先于计划 manifest）。
2. **非 zhcn locale 真渲染**（``--locale enus``，游戏 14 locale 之一）：
   渲染成功（exit 0）；卡面文本真值在 dbf（locale 无关——dbf.py 头注
   已知限制），``--locale`` 只影响资产变体与 strings 表消费面；CS2_182
   无 enUS 变体差异 → 逐字节同 zhcn 哨兵 sha（行为可预期的机器证明）。
3. **空字体目录**（产品面无字体目录参数——port 注入，tmp 空目录）：
   - 控制卡 CS2_182：游戏字体覆盖全部字形，OS 回退零参与 → sha 逐字节
     同哨兵（空 OS 字体目录不污染正常渲染）；
   - 缺字卡 EX1_021（name 覆盖含 㐀/㐇——游戏字体 cmap 缺的扩展区汉字，
     缺字回退样本同族）：两级回退（资产名单 → OS 11 族）全空 →
     U+FFFD 无候选 → 零宽 + **响亮缺字事件**：结果 manifest 逐卡
     warnings 含 ``missing_glyphs:㐀:…``（exit 仍 0，不静默 tofu）。
4. **只拉丁字体**（目录只放 arial.ttf）：CJK 缺字的 OS 级回退降级——
   引擎末级 U+FFFD 兜底（Latin 字体常带 U+FFFD）或零宽，两条路都有响亮
   缺字事件；控制卡 sha 仍逐字节同哨兵。
4. **locale 目录在场但语料缺失**（Strings/<loc>/ 空目录）：preflight 只查
   目录存在，渲染期 ``text_shim.hydrate_game_strings`` B4 起抛 typed
   ``GameAssetMissing``（``asset_missing_in_game``，ENV 3）——原裸
   RuntimeError 会错归 render_failed（RENDER 1）。影子安装根（junction
   真游戏 Hearthstone_Data + 空 Strings/enUS）驱动真实 CLR boot 走到抛点。

用法::

    set EIDOLON_TEST_GAME=D:\\game\\Hearthstone
    .venv-release\\Scripts\\python.exe -m unittest discover -s tests/integration -p integration_font_locale_surface.py -t . -v

默认 discover（pattern ``test*.py``）不收集本文件。证据：每判据的
CLI/manifest 实测行写 ``build/phase1/b4/b4-evidence.json``；渲染产物留
``build/phase1/b4/{locale-enus,empty-fonts-run}/``。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None

_cache_env = os.environ.get("EIDOLON_TEST_CACHE", "").strip()
CACHE_ROOT: Path = (Path(_cache_env) if _cache_env
                    else REPO / "build" / "integration_supply_cache")

OUT_DIR = REPO / "build" / "phase1" / "b4"

CS2_182_SENTINEL = "89306531816a36c7ae0423073943f3996dea6d11488b6288b1c9e4427577d0ba"

# 缺字探针字形：U+3400/U+3407（扩展 A 区；缺字回退实验同族样本，
# 游戏字体 cmap 缺、系统盘常见 CJK 字体有——空字体目录下两级全空）。
MISSING_CHARS = ("㐀", "㐇")

EMPTY_FONT_TOML = """format_version = 1
out_dir = "."

[[cards]]
id = "CS2_182"

[[cards]]
id = "EX1_021"
name = "㐀㐇B4"
outname = "EX1_021_missing_glyph.png"
"""


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    """子进程产品路径：``python -m eidolon render …``（独立进程身份）。"""
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, "-m", "eidolon", "render", *args],
        capture_output=True, text=True, cwd=str(REPO), timeout=1200,
    )


def _evidence_write(data: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "b4-evidence.json"
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
    existing.update(data)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=1),
                    encoding="utf-8")


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class FontLocaleSurfaceTests(unittest.TestCase):
    """B4 四条失败路径经真实游戏逐条断言。"""

    # ---- 1) 未知 locale：typed locale_missing（ENV 3） ------------------

    def test_locale_unknown_typed_exit3(self) -> None:
        proc = _run_cli(["CS2_182", "--game", str(GAME_ROOT),
                         "--cache-root", str(CACHE_ROOT), "--locale", "nosuch",
                         "--outdir", str(OUT_DIR / "locale-nosuch")])
        self.assertEqual(proc.returncode, 3,
                         f"未知 locale 应 ENV 3；实得 {proc.returncode}\n"
                         f"stderr={proc.stderr[-2000:]}")
        self.assertEqual(proc.stdout.strip(), "",
                         "preflight 失败先于计划 manifest——stdout 应为空")
        self.assertIn("error[locale_missing]", proc.stderr)
        self.assertIn("Strings\\nosuch", proc.stderr.replace("/", "\\"))
        self.assertIn("enUS", proc.stderr,
                      "locale_missing 应点名游戏实际存在的语言目录")
        self.assertIn("hint:", proc.stderr)
        (OUT_DIR / "locale-nosuch.stderr.log").write_text(proc.stderr,
                                                          encoding="utf-8")
        (OUT_DIR / "locale-nosuch.stdout.log").write_text(proc.stdout,
                                                          encoding="utf-8")
        _evidence_write({"locale_unknown": {
            "exit": proc.returncode,
            "stderr_head": proc.stderr.splitlines()[:2],
            "stdout_empty": proc.stdout.strip() == "",
        }})

    # ---- 2) 非 zhcn locale 真渲染 ---------------------------------------

    def test_locale_enus_true_render(self) -> None:
        out = OUT_DIR / "locale-enus"
        proc = _run_cli(["CS2_182", "--game", str(GAME_ROOT),
                         "--cache-root", str(CACHE_ROOT), "--locale", "enus",
                         "--outdir", str(out)])
        self.assertEqual(proc.returncode, 0,
                         f"enus 真渲染应成功；实得 {proc.returncode}\n"
                         f"stderr={proc.stderr[-2000:]}")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["environment"]["game"]["locale"], "enus")
        rows = {r["input_id"]: r for r in manifest["cards"]}
        row = rows["CS2_182"]
        self.assertTrue(row["ok"])
        self.assertEqual(row["sha256"], CS2_182_SENTINEL,
                         "卡面文本真值在 dbf（locale 无关）、CS2_182 无 enUS "
                         "资产变体差异 → 应逐字节同 zhcn 哨兵")
        self.assertEqual(row["warnings"], [], "enus 语料齐全不应有缺字事件")
        _evidence_write({"locale_enus": {
            "exit": proc.returncode, "locale": "enus",
            "sha256": row["sha256"], "sentinel": CS2_182_SENTINEL,
            "warnings": list(row["warnings"]),
        }})

    # ---- 3) 空字体目录：控制卡 sha 稳定 + 缺字卡响亮警告 -----------------

    def test_empty_font_dirs_control_stable_and_missing_glyph_warned(self) -> None:
        from eidolon.adapters import CoreRenderPort
        from eidolon.entry import main as entry_main

        out = OUT_DIR / "empty-fonts-run"
        out.mkdir(parents=True, exist_ok=True)
        toml = out / "batch.toml"
        toml.write_text(EMPTY_FONT_TOML, encoding="utf-8")
        empty_fonts = OUT_DIR / "empty-fonts"
        empty_fonts.mkdir(parents=True, exist_ok=True)
        # 守卫：注入目录真实存在且为空（空=族索引空表，OS 回退零候选）。
        self.assertEqual(list(empty_fonts.iterdir()), [])

        def port_factory():
            # 产品组合层唯一字体注入口：CoreRenderPort(font_dirs=…)。
            # tmp 空目录（default_font_dirs 会过滤空目录，产品 CLI 无法注入
            # ——本测试走 port 注入 seam，同 adapters 测试纪律）。
            return CoreRenderPort(font_dirs=(empty_fonts,))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = entry_main(
                ["render", "--toml", str(toml), "--game", str(GAME_ROOT),
                 "--cache-root", str(CACHE_ROOT)],
                port_factory=port_factory)
        self.assertEqual(exit_code, 0, f"空字体目录批应成功（缺字=警告不失败）")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        rows = {r["input_id"]: r for r in manifest["cards"]}
        # 控制卡：游戏字体覆盖全部字形 → 空 OS 目录零参与 → 逐字节同哨兵。
        control = rows["CS2_182"]
        self.assertTrue(control["ok"])
        self.assertEqual(control["sha256"], CS2_182_SENTINEL,
                         "空 OS 字体目录不得污染正常渲染（哨兵漂移）")
        self.assertEqual(control["warnings"], [])
        # 缺字卡：两级回退全空 → 零宽 + 响亮缺字事件（ok=True，不静默 tofu）。
        probe = rows["EX1_021"]
        self.assertTrue(probe["ok"], "缺字是警告不是失败")
        self.assertTrue(probe["warnings"],
                        "缺字卡必须有 missing_glyphs 警告（不许静默）")
        joined = "\n".join(probe["warnings"])
        for ch in MISSING_CHARS:
            self.assertIn(f"missing_glyphs:{ch}:", joined,
                          f"缺字事件缺 {ch}：{probe['warnings']}")
        self.assertTrue(any("missing_glyphs" in w for w in manifest["warnings"]),
                        "全局 warnings 也须携带缺字事件")
        _evidence_write({"empty_font_dirs": {
            "exit": exit_code,
            "font_dirs": [str(empty_fonts)],
            "control_sha256": control["sha256"],
            "sentinel": CS2_182_SENTINEL,
            "probe_warnings": list(probe["warnings"]),
        }})

    # ---- 4) 只拉丁字体（缺中文字体）：回退降级仍有响亮缺字事件 ------------

    def test_latin_only_font_dirs_missing_cjk_warned(self) -> None:
        """目录有字体但缺中文字体（只有 Arial）：CJK 缺字的两级回退在 OS 级
        降级——引擎末级 U+FFFD 兜底（Arial 等 Latin 字体常带 U+FFFD）或零宽，
        两条路都有响亮缺字事件；控制卡 sha 仍逐字节同哨兵。"""
        from eidolon.adapters import CoreRenderPort
        from eidolon.entry import main as entry_main

        arial = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"
        if not arial.is_file():
            self.skipTest("本机无 C:/Windows/Fonts/arial.ttf")
        latin_fonts = OUT_DIR / "latin-fonts"
        latin_fonts.mkdir(parents=True, exist_ok=True)
        target = latin_fonts / "arial.ttf"
        if not target.is_file():
            shutil.copyfile(arial, target)

        out = OUT_DIR / "latin-fonts-run"
        out.mkdir(parents=True, exist_ok=True)
        toml = out / "batch.toml"
        toml.write_text(EMPTY_FONT_TOML, encoding="utf-8")

        def port_factory():
            return CoreRenderPort(font_dirs=(latin_fonts,))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = entry_main(
                ["render", "--toml", str(toml), "--game", str(GAME_ROOT),
                 "--cache-root", str(CACHE_ROOT)],
                port_factory=port_factory)
        self.assertEqual(exit_code, 0)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        rows = {r["input_id"]: r for r in manifest["cards"]}
        control = rows["CS2_182"]
        self.assertTrue(control["ok"])
        self.assertEqual(control["sha256"], CS2_182_SENTINEL,
                         "拉丁字体目录下控制卡（游戏字体全覆盖）不得漂移")
        probe = rows["EX1_021"]
        self.assertTrue(probe["ok"])
        joined = "\n".join(probe["warnings"])
        for ch in MISSING_CHARS:
            self.assertIn(f"missing_glyphs:{ch}:", joined,
                          f"拉丁字体目录缺 CJK 仍须响亮：{probe['warnings']}")
        _evidence_write({"latin_only_font_dirs": {
            "exit": exit_code,
            "font_dirs": [str(latin_fonts)],
            "control_sha256": control["sha256"],
            "probe_warnings": list(probe["warnings"]),
        }})

    # ---- 5) locale 目录在场但语料缺失 → GameAssetMissing（ENV 3） --------

    def test_locale_dir_without_corpus_typed(self) -> None:
        from eidolon.contracts import EnvironmentUnavailable, GameContext
        from eidolon.core.infra import context

        shadow = OUT_DIR / "shadow-game"
        shadow.mkdir(parents=True, exist_ok=True)
        managed_link = shadow / "Hearthstone_Data"
        if not managed_link.exists():
            # junction 真游戏 Hearthstone_Data（boot 只读 Managed/Assembly-CSharp）。
            subprocess.run(["cmd", "/c", "mklink", "/J", str(managed_link),
                            str(GAME_ROOT / "Hearthstone_Data")],
                           check=True, capture_output=True)
        (shadow / "Strings" / "enUS").mkdir(parents=True, exist_ok=True)
        if not (shadow / "Hearthstone.exe").exists():
            shutil.copyfile(GAME_ROOT / "Hearthstone.exe",
                            shadow / "Hearthstone.exe")

        saved_ctx = context._installed
        import eidolon.core.infra.text_shim as text_shim

        saved_instance = text_shim._INSTANCE
        try:
            ctx = GameContext(root=shadow, cache_root=OUT_DIR / "shadow-cache",
                              locale="enus")
            # 进程单身份不变量：前序测试（同文件 in-process 渲染）可能已装
            # 真游戏身份——白盒卸载后装影子身份（finally 恢复原身份）。
            context._installed = None
            context.install(ctx)
            text_shim._INSTANCE = None      # 强制本影子身份走完整水合
            with self.assertRaises(EnvironmentUnavailable) as caught:
                text_shim.instance()
            problem = caught.exception.problem
            self.assertEqual(problem.code, "asset_missing_in_game")
            self.assertEqual(str(problem.kind), "environment")
            # path 用 GameContext.locale 的原始值拼（ctx 构造传 "enus"）。
            self.assertEqual(problem.path, str(shadow / "Strings" / ctx.locale))
            self.assertIn("GAMEPLAY", problem.message)
            _evidence_write({"locale_dir_without_corpus": {
                "code": problem.code, "kind": str(problem.kind),
                "path": problem.path, "message": problem.message,
            }})
        finally:
            context._installed = saved_ctx
            text_shim._INSTANCE = saved_instance


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
