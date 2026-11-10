"""integration_overrides — Phase 4 覆盖语义矩阵（真实游戏；显式跑；真实 CLI 子进程）。

覆盖面（设计 §7.4 / §10.0-§10.2 / §5.4 / §1.2；§13.5 审计清单覆盖行）：

* **生效面**：``assets.frame``（1024² 类色图集）/ ``assets.portrait``（512² 肖像
  纹理）/ ``assets.watermark``（128² 水印纹理）覆盖渲染成功、输出 sha 与无覆盖
  基线互异、结果 manifest 记录 ``overrides.assets.<seat>`` + ``assets_sha256``
  （watermark 覆盖生效点=``update_watermark``/V-pass——渲染成功即证消费链通）、
  像素区域 MAE 断言（P1-11，PIL+numpy：portrait 中心 200×200 / frame 全图 /
  watermark 底部 1/4 与 plain 同区域可见差；阈值=实测标定值的 1/3 写死）；
* **尺寸错**：portrait 511² / frame 512×707（整帧图误用）/ watermark 300² →
  退出 2 ``asset_dimensions``（preflight 静态表，stdout 空）；
* **响亮失败（RENDER 1）**：frame 覆盖到无写点帧（HERO_POWER）→ 1
  ``render_failed``；watermark 覆盖到无 desc 层卡（数据 HERO + ``hero_style``
  → ``Card_Play_Hero``，desc_frame=None）→ 1；GOLDEN 武器（数据 WEAPON +
  ``premium=GOLDEN`` 覆盖 → ``Card_Hand_Weapon_Premium`` 未开放）→ 1 message
  点名 prefab（§1.2：spec 接受、render 逐卡报）；
* **watermark 语义钉**：无 desc **文本** minion + watermark 覆盖 → 渲染成功
  （desc **层**（ally 帧 Description_mesh）仍在；「无 desc 层」指帧无 desc 面
  ——设计 §10.2 的响亮失败判据是层不是文本；覆盖轴=无数据水印卡也可加水印）；
* **races 覆盖**：BG 双种族 minion（数据轴 2 种族）无覆盖（双板基线）→ 覆盖
  1 种族（单板+单文本）→ 覆盖空 tuple（板隐藏）→ 三次输出 sha 互异且渲染成功
  （像素级板正确性归 历史对照语料 既有行）；
* **style 矩阵（core 侧，§5.4）**：数据 HERO + ``cardtype=MINION`` 覆盖 +
  ``bg_style=true`` → bg 生效（sha 与同覆盖 plain 互异）；数据 MINION +
  ``cardtype=HERO`` 覆盖 + ``hero_style=true`` → hero 生效；CLI
  ``--hero-style --bg-style`` 同卡 → 退出 2（preflight style）；
* **runes 覆盖**：死亡骑士 minion + ``{BLOOD:1,FROST:1}`` → 渲染成功；
  ``{BLAH:1}`` → 退出 2 ``unknown_rune``；
* **premium 覆盖**：普通 minion + ``premium=GOLDEN`` → 渲染成功、sha 与 plain
  互异（``Card_Hand_Ally_Premium`` 已开放）；``SIGNATURE`` → spec 期 2（shell
  常量拦，§1.2）。

产品链统一走 ``python -m eidolon`` 子进程（与 integration_render_port 同款
理由：子进程天然干净、贴近真实调用面）。默认 discover 不收集本文件；显式跑：

    EIDOLON_TEST_GAME=<游戏根> python -m unittest discover -s tests/integration \\
      -p 'integration_*.py' -t . -v

测试卡 id（2026-11-08 本机 dbf CARD_TAG 直筛探针；guid 注释防漂移）：
8=杂鱼 minion、229=HERO_05bp（HERO_POWER）、7=HERO_01（数据 HERO）、
76=EX1_598（desc 文本空 minion）、304=CS2_112（武器）、60122=BGS_028
（BG minion，数据轴种族 [17,20] 双种族）、77510=TB_BaconShop_HERO_25_Buddy
（DEATHKNIGHT minion）。id 失配会在断言消息里显形。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None

_REPO = Path(__file__).resolve().parents[2]
_cache_env = os.environ.get("EIDOLON_TEST_CACHE", "").strip()
CACHE_ROOT: Path = (Path(_cache_env) if _cache_env
                    else _REPO / "build" / "integration_supply_cache")

_COMMON = ["--game", str(GAME_ROOT), "--cache-root", str(CACHE_ROOT)] if GAME_ROOT else []

# ---- 像素区域断言阈值（P1-11；实测标定，取实测 MAE 的 1/3 作下限写死）----
# 标定口径：2026-11-08 本机真实游戏 + 暖缓存，产品 CLI 渲染（512×707），对照 =
# 同批 plain_8 无覆盖基线；实测：portrait 中心 200×200 = 25.4294、frame 全图 =
# 10.0092、watermark 底部 1/4 = 5.5215（PIXEL-MAE 打印可复现标定）。
PORTRAIT_MAE_MIN = 8.47   # 实测 25.4294 / 3
FRAME_MAE_MIN = 3.33      # 实测 10.0092 / 3
WATERMARK_MAE_MIN = 1.84  # 实测 5.5215 / 3


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-m", "eidolon", *args],
        cwd=_REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=420,
    )
    return result.returncode, result.stdout, result.stderr


def _sha256_of(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mae_region(png_a: Path, png_b: Path,
                box: tuple[int, int, int, int] | None) -> float:
    """两 PNG 的 RGB MAE（P1-11 像素区域断言的度量）。

    ``box=(left, top, right, bottom)`` 时取两图同区域（numpy 切片，半开
    区间）；None=全图。尺寸不等直接 AssertionError（覆盖渲染输出尺寸须与
    基线一致，这本身就是断言面）。numpy 函数体内引入（同 harness 口）。"""
    import numpy as np

    with Image.open(png_a) as a, Image.open(png_b) as b:
        if a.size != b.size:
            raise AssertionError(
                f"尺寸不等：{png_a} {a.size} vs {png_b} {b.size}")
        arr_a = np.asarray(a.convert("RGB"), dtype=np.float64)
        arr_b = np.asarray(b.convert("RGB"), dtype=np.float64)
    if box is not None:
        left, top, right, bottom = box
        arr_a = arr_a[top:bottom, left:right]
        arr_b = arr_b[top:bottom, left:right]
    return float(np.abs(arr_a - arr_b).mean())


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class OverrideMatrixTests(unittest.TestCase):
    """覆盖语义矩阵（真实 dbf + 真实渲染链）。"""

    # 数据 HERO（HERO_01）；watermark 响亮失败用它（hero_style → Card_Play_Hero
    # 无 desc 面）与 style 矩阵 cardtype 覆盖共用。
    HERO_ID = "7"

    @classmethod
    def setUpClass(cls) -> None:
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmpdir.name)
        cls.base_png = cls._render_plain("8")   # 无覆盖基线（sha 比较锚）

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    # ---- 工具 ----

    def _write_toml(self, name: str, card_id: str, body: str,
                    outdir: Path) -> Path:
        toml = self.tmp / name / "job.toml"
        toml.parent.mkdir(parents=True, exist_ok=True)
        toml.write_text(
            "format_version = 1\n"
            f'out_dir = "{outdir.as_posix()}"\n\n'
            "[[cards]]\n"
            f"id = {card_id}\n"
            + body,
            encoding="utf-8",
        )
        return toml

    def _make_png(self, name: str, size: tuple[int, int],
                  color: tuple[int, int, int, int]) -> Path:
        png = self.tmp / name / f"{name}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", size, color).save(png)
        return png

    def _render(self, toml: Path) -> tuple[int, str, str, dict | None]:
        code, stdout, stderr = _run_cli(["render", "--toml", str(toml), *self._common()])
        manifest_path = toml.parent / "out" / "manifest.json"
        result = (json.loads(manifest_path.read_text(encoding="utf-8"))
                  if manifest_path.is_file() else None)
        return code, stdout, stderr, result

    @classmethod
    def _render_plain(cls, card_id: str) -> str:
        outdir = cls.tmp / f"plain_{card_id}" / "out"
        toml = cls.tmp / f"plain_{card_id}" / "job.toml"
        toml.parent.mkdir(parents=True, exist_ok=True)
        toml.write_text(
            "format_version = 1\n"
            f'out_dir = "{outdir.as_posix()}"\n\n'
            "[[cards]]\n"
            f"id = {card_id}\n",
            encoding="utf-8",
        )
        code, _, stderr = _run_cli(["render", "--toml", str(toml), *_COMMON])
        if code != 0:
            raise AssertionError(f"plain {card_id} 基线渲染失败：{stderr}")
        return _sha256_of(outdir / f"{card_id}.png")

    def _plain_png(self) -> Path:
        """无覆盖基线 PNG（setUpClass 已渲 plain_8；像素断言的对照面）。"""
        png = self.tmp / "plain_8" / "out" / "8.png"
        self.assertTrue(png.is_file(), f"plain 基线 PNG 缺失：{png}")
        return png

    def _common(self) -> list[str]:
        return _COMMON

    # ---- 生效面（§10.0 三座位）----

    def test_frame_override_effective(self) -> None:
        frame = self._make_png("frame_ok", (1024, 1024), (30, 90, 200, 255))
        outdir = self.tmp / "frame_ok" / "out"
        toml = self._write_toml("frame_ok", "8", "\n[cards.asset]\n"
                                f'frame = "{frame.as_posix()}"\n', outdir)
        code, stdout, stderr, result = self._render(toml)
        self.assertEqual(code, 0, stderr)
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertEqual(card["overrides"]["assets"]["frame"], str(frame))
        self.assertEqual(card["assets_sha256"], {"frame": _sha256_of(frame)})
        self.assertNotEqual(card["sha256"], self.base_png,
                            "frame 覆盖后输出应与无覆盖基线互异")
        # P1-11 像素断言：整图集替换 → 全图 MAE 必须可见差（不只 sha 互异）。
        mae = _mae_region(outdir / "8.png", self._plain_png(), None)
        print(f"PIXEL-MAE frame full-image = {mae:.4f} (min {FRAME_MAE_MIN})")
        self.assertGreater(
            mae, FRAME_MAE_MIN,
            f"frame 覆盖后全图 MAE {mae:.4f} 未超阈值 {FRAME_MAE_MIN}"
            "（整图集替换应全图可见差）")

    def test_portrait_override_effective(self) -> None:
        portrait = self._make_png("portrait_ok", (512, 512), (120, 40, 200, 255))
        outdir = self.tmp / "portrait_ok" / "out"
        toml = self._write_toml("portrait_ok", "8", "\n[cards.asset]\n"
                                f'portrait = "{portrait.as_posix()}"\n', outdir)
        code, _, stderr, result = self._render(toml)
        self.assertEqual(code, 0, stderr)
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertEqual(card["overrides"]["assets"]["portrait"], str(portrait))
        self.assertEqual(card["assets_sha256"], {"portrait": _sha256_of(portrait)})
        self.assertNotEqual(card["sha256"], self.base_png)
        # P1-11 像素断言：输出中心 200×200（肖像座位所在）与 plain 同区域 MAE。
        plain_png = self._plain_png()
        with Image.open(plain_png) as im:
            width, height = im.size
        box = ((width - 200) // 2, (height - 200) // 2,
               (width - 200) // 2 + 200, (height - 200) // 2 + 200)
        mae = _mae_region(outdir / "8.png", plain_png, box)
        print(f"PIXEL-MAE portrait center-200x200 = {mae:.4f} "
              f"(min {PORTRAIT_MAE_MIN})")
        self.assertGreater(
            mae, PORTRAIT_MAE_MIN,
            f"portrait 覆盖后中心 200×200 MAE {mae:.4f} 未超阈值 "
            f"{PORTRAIT_MAE_MIN}（肖像座位替换应中心区域可见差）")

    def test_watermark_override_effective(self) -> None:
        # 生效点=update_watermark/V-pass（§10.1）；渲染成功 + sha 互异即证链通。
        wm = self._make_png("wm_ok", (128, 128), (250, 200, 30, 255))
        outdir = self.tmp / "wm_ok" / "out"
        toml = self._write_toml("wm_ok", "8", "\n[cards.asset]\n"
                                f'watermark = "{wm.as_posix()}"\n', outdir)
        code, _, stderr, result = self._render(toml)
        self.assertEqual(code, 0, stderr)
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertEqual(card["overrides"]["assets"]["watermark"], str(wm))
        self.assertEqual(card["assets_sha256"], {"watermark": _sha256_of(wm)})
        self.assertNotEqual(card["sha256"], self.base_png,
                            "watermark 覆盖（watermark_force=True）应改变输出")
        # P1-11 像素断言：底部 1/4 区域（水印座位所在）与 plain 同区域 MAE。
        plain_png = self._plain_png()
        with Image.open(plain_png) as im:
            width, height = im.size
        box = (0, height - height // 4, width, height)
        mae = _mae_region(outdir / "8.png", plain_png, box)
        print(f"PIXEL-MAE watermark bottom-quarter = {mae:.4f} "
              f"(min {WATERMARK_MAE_MIN})")
        self.assertGreater(
            mae, WATERMARK_MAE_MIN,
            f"watermark 覆盖后底部 1/4 MAE {mae:.4f} 未超阈值 "
            f"{WATERMARK_MAE_MIN}（水印座位替换应底部区域可见差）")

    # ---- 尺寸错（preflight 静态表；§10.1）----

    def test_dimension_rejections_exit_2(self) -> None:
        cases = [
            ("dim_portrait", "portrait", (511, 511)),
            ("dim_frame", "frame", (512, 707)),       # 整帧图误用
            ("dim_watermark", "watermark", (300, 300)),
        ]
        for name, seat, size in cases:
            with self.subTest(seat=seat):
                png = self._make_png(name, size, (10, 10, 10, 255))
                outdir = self.tmp / name / "out"
                toml = self._write_toml(name, "8", "\n[cards.asset]\n"
                                        f'{seat} = "{png.as_posix()}"\n', outdir)
                code, stdout, stderr, result = self._render(toml)
                self.assertEqual(code, 2, stderr)
                self.assertEqual(stdout, "")   # preflight 在 plan manifest 前
                self.assertIn("error[asset_dimensions]", stderr)
                self.assertIn(f"cards[0].asset.{seat}", stderr)
                self.assertIsNone(result)      # 结果 manifest 未落

    # ---- 响亮失败（§10.2 RENDER 1，不静默出图）----

    def test_frame_override_no_write_point_hero_power_loud(self) -> None:
        # HERO_POWER（229=HERO_05bp）走 History_HeroPower 帧——类色图集无写点
        # （class_color.applied=False）→ frame 覆盖无消费位 → ValueError 响亮。
        frame = self._make_png("frame_hp", (1024, 1024), (30, 90, 200, 255))
        outdir = self.tmp / "frame_hp" / "out"
        toml = self._write_toml("frame_hp", "229", "\n[cards.asset]\n"
                                f'frame = "{frame.as_posix()}"\n', outdir)
        code, stdout, stderr, result = self._render(toml)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(result["cards"][0]["ok"], False)
        error = result["cards"][0]["error"]
        self.assertEqual(error["code"], "render_failed")
        self.assertEqual(error["kind"], "render")
        self.assertIn("frame", error["message"])
        self.assertIn("写点", error["message"])   # message 点名机制（类色写点面）

    def test_watermark_no_desc_layer_loud(self) -> None:
        # 数据 HERO（7=HERO_01）+ hero_style → Card_Play_Hero：desc_frame=None
        # → watermark 覆盖无 V-pass 消费位 → render_with 早响亮（§10.2）。
        wm = self._make_png("wm_hero", (128, 128), (250, 200, 30, 255))
        outdir = self.tmp / "wm_hero" / "out"
        toml = self._write_toml(
            "wm_hero", self.HERO_ID,
            "hero_style = true\n\n[cards.asset]\n"
            f'watermark = "{wm.as_posix()}"\n', outdir)
        code, stdout, stderr, result = self._render(toml)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(result["cards"][0]["ok"], False)
        error = result["cards"][0]["error"]
        self.assertEqual(error["code"], "render_failed")
        self.assertIn("watermark", error["message"])
        self.assertIn("desc", error["message"])

    def test_watermark_on_desc_text_free_minion_renders(self) -> None:
        # 语义钉（§10.2 判据是 desc **层**不是文本）：76=EX1_598 desc 文本空，
        # 但 ally 帧 Description_mesh 仍在 → 覆盖加水印合法（覆盖轴=无数据水印
        # 卡也可加水印）→ 渲染成功、sha 互异。响亮失败只对帧级无 desc 面。
        wm = self._make_png("wm_nodesc", (128, 128), (90, 250, 60, 255))
        outdir = self.tmp / "wm_nodesc" / "out"
        toml = self._write_toml("wm_nodesc", "76", "\n[cards.asset]\n"
                                f'watermark = "{wm.as_posix()}"\n', outdir)
        code, _, stderr, result = self._render(toml)
        self.assertEqual(code, 0, stderr)
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertNotEqual(card["sha256"], self._render_plain("76"))

    def test_unsupported_golden_weapon_prefab_loud(self) -> None:
        # §1.2：GOLDEN 武器未开放（Card_Hand_Weapon_Premium 无 _SLOT_FOR_KEY 行）
        # → spec 接受（302=CS2_112 数据 WEAPON + premium=GOLDEN 覆盖），render
        # 逐卡 RENDER 1，message 点名 prefab。
        outdir = self.tmp / "golden_weapon" / "out"
        toml = self._write_toml("golden_weapon", "304",
                                'premium = "GOLDEN"\n', outdir)
        code, stdout, stderr, result = self._render(toml)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(result["cards"][0]["ok"], False)
        error = result["cards"][0]["error"]
        self.assertEqual(error["code"], "render_failed")
        self.assertIn("Card_Hand_Weapon_Premium", error["message"])

    # ---- races 覆盖（§7.4 显示覆盖；板/文本三态）----

    def test_races_override_board_and_text_triplet(self) -> None:
        # 60122=BGS_028：BG minion 数据轴种族 [17,20]（双种族宽板）。
        base_png = self._render_plain("60122")
        shas = {"plain": base_png}
        for label, races_toml in (
            ("one", 'races = ["鱼人"]\n'),          # 单板+单文本
            ("empty", "races = []\n"),              # 空 tuple=板隐藏
        ):
            outdir = self.tmp / f"races_{label}" / "out"
            toml = self._write_toml(f"races_{label}", "60122", races_toml, outdir)
            code, _, stderr, result = self._render(toml)
            self.assertEqual(code, 0, stderr)
            card = result["cards"][0]
            self.assertTrue(card["ok"])
            self.assertEqual(card["overrides"]["races"],
                             ["鱼人"] if label == "one" else [])
            shas[label] = card["sha256"]
        self.assertEqual(len(set(shas.values())), 3,
                         f"三态输出 sha 必须互异：{shas}")

    # ---- style 矩阵（§5.4 core 侧两行 + 互斥行）----

    def test_style_matrix_data_hero_cardtype_minion_bg(self) -> None:
        # 数据 HERO + cardtype=MINION 覆盖 + bg_style=true → bg 请求不被数据轴
        # 压掉（§5.4）。像素可观测面：无 BG 组件（无 tech_level/badge）的卡，
        # bacon 与 constructed **同字节**（同输入交叉验证同态，2026-11-08 归因）。字节可观测
        # 对 = 追加 tech_level（bacon 模式渲染酒馆科技宝石，constructed 不渲染）。
        base = self._render_cardtype_minion_hero7_plain()
        outdir = self.tmp / "style_hero7_bg" / "out"
        toml = self._write_toml("style_hero7_bg", self.HERO_ID,
                                'cardtype = "MINION"\nbg_style = true\n', outdir)
        code, _, stderr, result = self._render(toml)
        self.assertEqual(code, 0, stderr)
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertTrue(card["bg_style"])
        self.assertEqual(card["style_requested"], [False, True])

        # 字节可观测对：同卡 + tech_level=6，±bg_style → bacon 加科技宝石。
        shas: dict[str, str] = {}
        for label, body in (
            ("bg_tech", 'cardtype = "MINION"\nbg_style = true\ntech_level = 6\n'),
            ("constructed_tech", 'cardtype = "MINION"\ntech_level = 6\n'),
        ):
            outdir = self.tmp / f"style_hero7_{label}" / "out"
            toml = self._write_toml(f"style_hero7_{label}", self.HERO_ID, body, outdir)
            code, _, stderr, result = self._render(toml)
            self.assertEqual(code, 0, stderr)
            self.assertTrue(result["cards"][0]["ok"])
            self.assertEqual(result["cards"][0]["style_requested"],
                             [False, True] if label == "bg_tech" else [False, False])
            shas[label] = result["cards"][0]["sha256"]
        self.assertNotEqual(shas["bg_tech"], shas["constructed_tech"],
                            "bg_style 请求必须到达引擎（bacon 科技宝石可观测，§5.4）")

    def _render_cardtype_minion_hero7_plain(self) -> str:
        outdir = self.tmp / "style_hero7_plain" / "out"
        toml = self._write_toml("style_hero7_plain", self.HERO_ID,
                                'cardtype = "MINION"\n', outdir)
        code, _, stderr, result = self._render(toml)
        self.assertEqual(code, 0, stderr)
        self.assertTrue(result["cards"][0]["ok"])
        self.assertFalse(result["cards"][0]["bg_style"])
        return result["cards"][0]["sha256"]

    def test_style_matrix_data_minion_cardtype_hero(self) -> None:
        # 数据 MINION + cardtype=HERO 覆盖 + hero_style=true → hero 生效。
        base = self._render_plain("8")
        outdir = self.tmp / "style_minion8_hero" / "out"
        toml = self._write_toml("style_minion8_hero", "8",
                                'cardtype = "HERO"\nhero_style = true\n', outdir)
        code, _, stderr, result = self._render(toml)
        self.assertEqual(code, 0, stderr)
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertTrue(card["hero_style"])
        self.assertEqual(card["style_requested"], [True, False])
        self.assertNotEqual(card["sha256"], base)

    def test_style_both_global_flags_exit_2(self) -> None:
        # CLI 全局 --hero-style --bg-style（位置 id 模式——两旗标不与 --toml
        # 同用，option_not_allowed）：批内无适用卡 → compile_spec style → 2
        # （stdout 空）。dbf 8 是 SPELL：--hero-style 无适用卡即报。
        code, stdout, stderr = _run_cli(
            ["render", "8", *self._common(), "--hero-style", "--bg-style"])
        self.assertEqual(code, 2, stderr)
        self.assertEqual(stdout, "")
        self.assertIn("error[style]", stderr)

    # ---- runes 覆盖 ----

    def test_runes_override_effective_and_unknown_key(self) -> None:
        # 77510=TB_BaconShop_HERO_25_Buddy（DEATHKNIGHT minion）。
        base = self._render_plain("77510")
        outdir = self.tmp / "runes_ok" / "out"
        toml = self._write_toml("runes_ok", "77510",
                                "runes = { BLOOD = 1, FROST = 1 }\n", outdir)
        code, _, stderr, result = self._render(toml)
        self.assertEqual(code, 0, stderr)
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertEqual(card["overrides"]["fields"]["runes"],
                         {"BLOOD": 1, "FROST": 1})
        self.assertNotEqual(card["sha256"], base)

        bad = self._write_toml("runes_bad", "77510", 'runes = { BLAH = 1 }\n',
                               self.tmp / "runes_bad" / "out")
        code, stdout, stderr, result = self._render(bad)
        self.assertEqual(code, 2, stderr)
        self.assertEqual(stdout, "")
        self.assertIn("error[unknown_rune]", stderr)
        self.assertIsNone(result)

    # ---- premium 覆盖 ----

    def test_premium_golden_override_effective(self) -> None:
        # 普通 minion + GOLDEN → Card_Hand_Ally_Premium（已开放）渲染成功。
        outdir = self.tmp / "prem_golden" / "out"
        toml = self._write_toml("prem_golden", "8", 'premium = "GOLDEN"\n', outdir)
        code, _, stderr, result = self._render(toml)
        self.assertEqual(code, 0, stderr)
        card = result["cards"][0]
        self.assertTrue(card["ok"])
        self.assertEqual(card["overrides"]["fields"]["premium"], "GOLDEN")
        self.assertNotEqual(card["sha256"], self.base_png)

    def test_premium_signature_rejected_at_spec(self) -> None:
        # SIGNATURE/DIAMOND 是 shell 常量外词汇 → spec 期 2（§1.2 常量拦）。
        outdir = self.tmp / "prem_signature" / "out"
        toml = self._write_toml("prem_signature", "8", 'premium = "SIGNATURE"\n',
                                outdir)
        code, stdout, stderr, result = self._render(toml)
        self.assertEqual(code, 2, stderr)
        self.assertEqual(stdout, "")
        self.assertIsNone(result)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
