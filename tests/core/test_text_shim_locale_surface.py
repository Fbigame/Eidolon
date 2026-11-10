"""text_shim — locale 语料缺失面 typed 收口守卫（B4；零游戏零 CLR，只读源码）。

任务单 §10 B4：游戏 locale 语料缺失是**资产类缺失**（core 发
``environment``）；``hydrate_game_strings`` 的「Strings/<locale> 无
GAMEPLAY/GLOBAL*.txt」原为裸 ``RuntimeError``——逐卡分类落
``render_failed``（RENDER 1），错误归类。B4 改抛
``GameAssetMissing``（``asset_missing_in_game``，ENV 3）。

行为验证（真实 CLR boot + 影子安装根）在显式集成
``tests/integration/integration_font_locale_surface.py``；本守卫只钉源码
形状（text_shim 顶层 import game_tag 装 CLR，零游戏测试不得 import 本体，
文本断言是唯一零游戏面——tests/architecture 文本守卫同法）。
"""

from __future__ import annotations
import unittest
from pathlib import Path

from tests.support import ROOT

TEXT_SHIM = ROOT / "eidolon" / "core" / "infra" / "text_shim.py"


class TextShimLocaleSurfaceTests(unittest.TestCase):
    def test_corpus_miss_raises_game_asset_missing(self) -> None:
        text = TEXT_SHIM.read_text(encoding="utf-8")
        self.assertIn("GameAssetMissing", text,
                      "text_shim 未引入 GameAssetMissing（B4 typed 收口回退？）")
        self.assertIn("raise GameAssetMissing(", text,
                      "语料缺失抛出点不再是 GameAssetMissing")
        self.assertIn("asset_missing_in_game: Strings/", text,
                      "语料缺失 message 缺 asset_missing_in_game 前缀")

    def test_corpus_miss_site_has_no_bare_runtime_error(self) -> None:
        """原裸 RuntimeError 形状不得回归（游戏目录不完整=ENV 资产缺失）。"""
        text = TEXT_SHIM.read_text(encoding="utf-8")
        self.assertNotIn("RuntimeError(f\"text_shim: Strings/", text)
        self.assertNotIn("RuntimeError(f'text_shim: Strings/", text)

    def test_other_internal_raises_untouched(self) -> None:
        """CLR 类型缺失等**内部**失败仍走 RuntimeError（逐卡 render_failed /
        internal 域），B4 只收口语料文件缺失这一条资产类路径。"""
        text = TEXT_SHIM.read_text(encoding="utf-8")
        self.assertIn('RuntimeError("text_shim: GameStringTable/GameStringCategory 类型缺失")',
                      text)
        self.assertIn("RuntimeError(f\"text_shim: Assembly-CSharp 类型缺失 {missing}\")",
                      text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
