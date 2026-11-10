"""integration_style_matrix — CLI 全局 style 旗标 × 混合批三态（真实游戏；显式跑；真实 CLI 子进程）。

审计返工 P0-1（2026-11-08，裁决 A，设计 §5.4）：全局 ``--hero-style`` /
``--bg-style`` 是**批级请求**，adapter 逐卡按「请求 ∧ 生效适用」下发
（``style_requested[i] and CardSpec.hero_style/bg_style``）；raw
``style_requested`` 原样只进结果 manifest。本文件钉混合批的产品行为：

* ``render HERO_01 8 --bg-style`` → 退出 0；HERO_01（数据 HERO）plain
  （hero_style 生效 False）、8（数据非 HERO）bg（bg_style 生效 True）——
  修复前 raw 透传把 HERO_01 当 bg，preflight form 守卫 → 退出 2；
* ``--hero-style`` → 退出 0；HERO_01 hero、8 plain——修复前 8 被 raw
  hero_style 打到 Card_Invisible（逐卡 render_failed 1）；
* 双旗标 ``--hero-style --bg-style`` → 退出 0；HERO_01 hero、8 bg——
  修复前双卡同时 raw 双真，both-true 互斥报错。

逐卡断言结果 manifest（``out_dir/manifest.json``）的 ``hero_style`` /
``bg_style`` / ``style_requested`` 与 ``ok``（三态都须真实渲染出图）。

只测 CLI 全局旗标 × 混合批面；卡级 style 与 ``cardtype`` 覆盖组合归
``integration_overrides.py`` 的 style 矩阵（两文件互补，不重复）。
``_render_one`` / preflight 的 both-true 守卫保留为直调 core 的防御面，
adapter 路径不可达——双旗标用例即钉「不可达」这件事。

产品链统一走 ``python -m eidolon`` 子进程（与 integration_overrides /
integration_render_port 同款理由：子进程天然干净、贴近真实调用面）。
默认 discover（pattern ``test*.py``）**不收集**本文件；显式跑（需游戏 +
UnityPy + CLR）：

    EIDOLON_TEST_GAME=<游戏根> EIDOLON_TEST_CACHE=<缓存根> \\
      python -m unittest tests.integration.integration_style_matrix -v

测试卡（2026-11-08 本机 dbf CARD_TAG 直筛探针；guid 注释防漂移）：
7=HERO_01（数据 HERO）、8（数据 SPELL——非 HERO 即适用 ``--bg-style``，
其 cardtype 具体值不参与 bg 适用性判定，§5.4）。id 失配会在断言消息里显形。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None

_REPO = Path(__file__).resolve().parents[2]
_cache_env = os.environ.get("EIDOLON_TEST_CACHE", "").strip()
CACHE_ROOT: Path = (Path(_cache_env) if _cache_env
                    else _REPO / "build" / "integration_supply_cache")

_COMMON = ["--game", str(GAME_ROOT), "--cache-root", str(CACHE_ROOT)] if GAME_ROOT else []


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


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class MixedBatchGlobalStyleTests(unittest.TestCase):
    """混合批（HERO + 非 HERO）三态：全局旗标只落适用卡，三态全 exit 0。"""

    HERO_ID = "HERO_01"          # dbf 7（数据 HERO）
    NON_HERO_ID = "8"            # dbf 8（数据 SPELL；§5.4 bg 适用 = 非 HERO）

    @classmethod
    def setUpClass(cls) -> None:
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmpdir.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    # ---- 工具 ----

    def _render_mixed(self, name: str, *flags: str) -> tuple[int, str, str, list[dict]]:
        """位置 id 模式渲染混合批（HERO_01 + 8），读回结果 manifest 卡列表。"""
        outdir = self.tmp / name
        code, stdout, stderr = _run_cli([
            "render", self.HERO_ID, self.NON_HERO_ID,
            "--outdir", str(outdir), *flags, *_COMMON,
        ])
        manifest_path = outdir / "manifest.json"
        result = (json.loads(manifest_path.read_text(encoding="utf-8"))
                  if manifest_path.is_file() else None)
        cards = result["cards"] if result is not None else []
        return code, stdout, stderr, cards

    def _assert_card(
        self, card: dict, *, input_id: str, ref: dict, hero: bool, bg: bool,
        requested: list[bool],
    ) -> None:
        """逐卡钉结果 manifest 的 style 三字段与渲染成功。"""
        self.assertEqual(card["input_id"], input_id)
        self.assertEqual(card["id"], ref)
        self.assertTrue(card["ok"],
                        f"{input_id} 须渲染成功；error={card.get('error')}")
        self.assertEqual(card["hero_style"], hero,
                         f"{input_id} hero_style 生效值不符")
        self.assertEqual(card["bg_style"], bg,
                         f"{input_id} bg_style 生效值不符")
        self.assertEqual(card["style_requested"], requested,
                         f"{input_id} style_requested raw 账面不符")

    def _assert_mixed_batch(
        self, cards: list[dict], *, hero_card: tuple[bool, bool],
        non_hero_card: tuple[bool, bool], requested: list[bool],
    ) -> None:
        self.assertEqual(len(cards), 2, f"结果 manifest 须两卡：{cards}")
        self._assert_card(
            cards[0],
            input_id=self.HERO_ID,
            ref={"kind": "card", "value": self.HERO_ID},
            hero=hero_card[0], bg=hero_card[1], requested=requested,
        )
        self._assert_card(
            cards[1],
            input_id=self.NON_HERO_ID,
            ref={"kind": "dbf", "value": int(self.NON_HERO_ID)},
            hero=non_hero_card[0], bg=non_hero_card[1], requested=requested,
        )

    # ---- 三态 ----

    def test_bg_style_mixed_batch_hero_stays_plain(self) -> None:
        # 修复前：HERO_01 吃到 raw bg_style → preflight form 守卫退出 2。
        code, stdout, stderr, cards = self._render_mixed("bg", "--bg-style")
        self.assertEqual(code, 0, stderr)
        self._assert_mixed_batch(
            cards,
            hero_card=(False, False),      # HERO_01 plain：hero_style 生效 False
            non_hero_card=(False, True),   # 8 bg：bg_style 生效 True
            requested=[False, True],
        )

    def test_hero_style_mixed_batch_non_hero_stays_plain(self) -> None:
        # 修复前：8 吃到 raw hero_style → Card_Invisible（逐卡 render_failed 1）。
        code, _, stderr, cards = self._render_mixed("hero", "--hero-style")
        self.assertEqual(code, 0, stderr)
        self._assert_mixed_batch(
            cards,
            hero_card=(True, False),       # HERO_01 hero
            non_hero_card=(False, False),  # 8 plain
            requested=[True, False],
        )

    def test_both_flags_mixed_batch_orthogonal(self) -> None:
        # 修复前：双卡同时 raw 双真 → both-true 互斥；守卫保留为防御面，
        # adapter 路径（请求 ∩ 生效）不可达 → 退出 0、各落各的 form。
        code, _, stderr, cards = self._render_mixed(
            "both", "--hero-style", "--bg-style")
        self.assertEqual(code, 0, stderr)
        self._assert_mixed_batch(
            cards,
            hero_card=(True, False),       # HERO_01 hero（不吃 bg）
            non_hero_card=(False, True),   # 8 bg（不吃 hero）
            requested=[True, True],
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
