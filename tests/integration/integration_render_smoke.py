"""integration_render_smoke — Phase 3a render 机制冒烟（真实游戏；显式跑；直调 render_with，不走产品端口）。

覆盖任务卡面（Phase 3a 版本；Phase 3c 再扩展 --jobs/--antialias 产品端口版）：
  * 直调链：``Card.from_dbf(8)`` → ``resolve_form(card, "plain")`` →
    ``replace(canonical_cfg(), ...)`` → ``render_with(...)`` 出图（文件存在、
    PIL 可开、尺寸断言、sha256 稳定——同参数渲两次同 sha）；
  * ``races_text_override`` 覆盖座位冒烟（§7.5）：赋 override 后出图成功且
    与无覆盖输出 sha 不同（不验像素，只验不炸 + 有图 + 有差；卡用 dbf 9
    minion——dbf 8 是法术，种族覆盖在其帧型上是机制 no-op）。

默认 discover（pattern ``test*.py``）**不收集**本文件；显式跑（需游戏 + UnityPy + CLR）：
    EIDOLON_TEST_GAME=<游戏根> python -m unittest discover -s tests/integration -p 'integration_*.py' -t . -v

初始化纪律（同 Phase 2a/2b）：``resolve_context`` → ``context.install`` →
``dbf.install_default(...)``；``install_font_dirs`` 在渲染链 import 之前注入
（glyph_supply 族索引首建前的显式口；注入源 = shell/paths 的
``default_font_dirs()``，兜底 ``C:/Windows/Fonts``）。
CLR-at-import 渲染链模块（game.card / components 等，§6.5 清单）在 setUpClass
内 install 之后才 import。

缓存根策略（与 integration_supply_smoke 同款）：默认
``build/integration_supply_cache``（route.db 跨跑复用），``EIDOLON_TEST_CACHE``
可覆盖。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from eidolon.contracts import GameRequest
from eidolon.core.infra import context, dbf
from eidolon.core.infra.dbf import DbfModule, install_default, installed_default, reset_default
from eidolon.core.infra.game_install import resolve_context

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None

_REPO = Path(__file__).resolve().parents[2]
_cache_env = os.environ.get("EIDOLON_TEST_CACHE", "").strip()
CACHE_ROOT: Path = (Path(_cache_env) if _cache_env
                    else _REPO / "build" / "integration_supply_cache")


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class Phase3aRenderSmokeTests(unittest.TestCase):
    """真实游戏渲染机制冒烟（ctx/dbf/字体目录装一次；会话按渲染开）。"""

    @classmethod
    def setUpClass(cls) -> None:
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        cls.ctx = resolve_context(GameRequest(GAME_ROOT, "--game"),
                                  cache_root=CACHE_ROOT, locale="zhcn")
        installed = context.installed()
        if installed is None:
            context.install(cls.ctx)
        else:
            cls.ctx = installed
        if installed_default() is None:
            install_default(DbfModule(cls.ctx.dbf_path))
        # 字体目录注入（渲染链 import 之前；首次 family_index 之前的显式口）。
        # 注入源 = default_font_dirs（WINDIR/用户字体，兜底 C:/Windows/Fonts）
        # ——字体面分叉会直接破坏产出确定性。
        from eidolon.shell.paths import default_font_dirs
        from eidolon.core.render.text import glyph_supply
        glyph_supply.install_font_dirs(default_font_dirs(),
                                       cache_dir=cls.ctx.cache_root / "fonts")
        # install 之后才 import CLR-at-import 渲染链（§6.5 清单）。
        from eidolon.core.infra.card import Card
        from eidolon.core.render.game.actor.components import (
            canonical_cfg,
            render_with,
            resolve_form,
        )
        from eidolon.core.supply import machine

        cls.Card = Card
        cls.canonical_cfg = staticmethod(canonical_cfg)
        cls.render_with = staticmethod(render_with)
        cls.resolve_form = staticmethod(resolve_form)
        cls.machine = machine

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        if installed_default() is None:
            install_default(DbfModule(self.ctx.dbf_path))

    def tearDown(self) -> None:
        reset_default()

    # ---- 直调渲染链 ----

    def _render_png(self, card, *, form: str, t_phase: float, out_png: Path) -> bytes:
        """直调 render_with（Phase 3a 版本：不走产品端口）；返回 PNG 字节。"""
        use_bg_style, zone = self.resolve_form(card, form)
        cfg = replace(self.canonical_cfg(), use_bg_style=use_bg_style,
                      supersample=4, name="eidolon")
        with self.machine.session():
            self.render_with(card, cfg, t_phase=t_phase, zone=zone,
                             notext=False, textonly=False, out_png=out_png,
                             session_time=None)
        self.assertTrue(out_png.is_file(), f"渲染未产出 {out_png}")
        return out_png.read_bytes()

    def test_render_dbf8_smoke_and_determinism(self) -> None:
        from PIL import Image

        card = self.Card.from_dbf(8)
        out = Path(self._tmp.name) / "8.png"
        data1 = self._render_png(card, form="plain", t_phase=0.0, out_png=out)
        self.assertGreater(len(data1), 0)
        with Image.open(out) as im:
            size = im.size
            mode = im.mode
        # dbf 8 实测尺寸（512×707 是卡面规约期望；不符则按实际报告）。
        self.assertEqual(size, (512, 707),
                         f"dbf 8 输出尺寸 {size}（mode={mode}）——按实际报告")
        # sha256 稳定：同卡同参数渲两次同 sha（确定性 §11.2）。
        out2 = Path(self._tmp.name) / "8_again.png"
        data2 = self._render_png(card, form="plain", t_phase=0.0, out_png=out2)
        self.assertEqual(hashlib.sha256(data1).hexdigest(),
                         hashlib.sha256(data2).hexdigest(),
                         "同参数两渲 sha256 不一致（确定性破坏）")

    def test_races_text_override_smoke(self) -> None:
        """§7.5 覆盖座位：override 就地赋值 → 出图成功且与无覆盖 sha 不同。

        卡选 dbf 9（先知维伦，MINION，race 2）而非 dbf 8：dbf 8=精神控制
        （SPELL），法术帧不消费种族文本/板，override 在其上按机制是 no-op
        （实测 sha 相同）——覆盖可见面只在 minion 帧（ally/trinket），冒烟须用
        种族文本在渲染面上的卡。任务卡原文 dbf 8 的偏离，报告在案。"""
        card = self.Card.from_dbf(9)
        baseline = self._render_png(card, form="plain", t_phase=0.0,
                                    out_png=Path(self._tmp.name) / "9_base.png")
        card2 = self.Card.from_dbf(9)
        card2.races_text_override = ("野兽",)
        overridden = self._render_png(card2, form="plain", t_phase=0.0,
                                      out_png=Path(self._tmp.name) / "9_override.png")
        self.assertGreater(len(overridden), 0)
        self.assertNotEqual(hashlib.sha256(baseline).hexdigest(),
                            hashlib.sha256(overridden).hexdigest(),
                            "races_text_override 后输出与无覆盖相同（覆盖未生效）")
        # 空 tuple = 文本/板隐藏（§7.5 空覆盖语义）——同样必有可见差。
        card3 = self.Card.from_dbf(9)
        card3.races_text_override = ()
        empty = self._render_png(card3, form="plain", t_phase=0.0,
                                 out_png=Path(self._tmp.name) / "9_override_empty.png")
        self.assertNotEqual(hashlib.sha256(baseline).hexdigest(),
                            hashlib.sha256(empty).hexdigest(),
                            "空 races_text_override 未隐藏种族文本/板")

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
