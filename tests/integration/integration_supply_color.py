"""integration_supply_color — A4 color 域 e2e（显式跑；需游戏安装 + A4 index）。

判据面（任务单 A4 判据 1/2 + seed 记账）：

  * **判据 1（12 族 probe 对账）**：live ``color.probe()`` vs warm
    ``color_probe()``——键集合全等 + 每键 list 逐槽相等（含空占位槽——
    ColorType 下标对齐语义）+ 键序=落盘序（live 序列化字段声明序）；
  * **判据 2（同 sha 两张）**：normal=EX1_350（1x；live sha 与 A2/A3 冻结值
    对账）+ golden=BG27_822_G（dbf 103592，历史对照 ``manifest_golden.json``
    首行 gate.full=True 的 bacon ally 金卡；form=bg）——live 渲一次冻结 sha →
    seeded 渲一次 → **逐位一致**；
  * **color token 记账**：seeded 会话请求的 color token 全部命中
    （hit/live/unused 贴数打印）——EX1_350 color 面 live 数降到 0（A3 时
    color 仍 live：probe + atlas[7]）。

seeded-first 顺序（A3 e2e 同款）：seeded 在净进程先跑（hit/live/unused 记账
不被 live 渲染的进程级缓存 _SCENES/_KIT_CACHE/_probe_cache 污染）；live 只取
sha 判据。

用法（route 缓存暖；index 先建：``python -m eidolon.core.supply_index build
--game <root> --cache-root build/phase1/index-cache --locale zhcn --jobs 4``）::

    set EIDOLON_TEST_GAME=D:\\game\\Hearthstone
    .venv-release\\Scripts\\python.exe -m unittest discover -s tests/integration -p integration_supply_color.py -t . -v

    # 或直接：
    .venv-release\\Scripts\\python.exe -m tests.integration.integration_supply_color

配置（env，测试驱动专用不进库面）：``EIDOLON_TEST_GAME``（必填）、
``EIDOLON_TEST_ROUTE_CACHE``（选填，缺省 ``%LOCALAPPDATA%\\Eidolon\\cache``）、
``EIDOLON_TEST_INDEX``（选填，缺省 ``<repo>/build/phase1/index-cache``）、
``COLOR_GOLDEN_DBF`` / ``COLOR_GOLDEN_CARD``（选填，缺省 103592 / BG27_822_G）。
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

from eidolon.contracts import CardRef, RenderCard

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "build" / "a4-color"

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT = Path(_game_env) if _game_env else None

_cache_env = os.environ.get("EIDOLON_TEST_ROUTE_CACHE", "").strip()
if _cache_env:
    CACHE_ROOT = Path(_cache_env)
else:
    local = os.environ.get("LOCALAPPDATA", "")
    CACHE_ROOT = Path(local) / "Eidolon" / "cache" if local else Path.home() / ".cache" / "eidolon"

_index_env = os.environ.get("EIDOLON_TEST_INDEX", "").strip()
INDEX_ROOT = Path(_index_env) if _index_env else REPO / "build" / "phase1" / "index-cache"

NORMAL_CARD = "EX1_350"
NORMAL_DBF = 9
# A2/A3 冻结的 EX1_350 live sha（对拍参照；游戏换代则本断言改 informational）
FROZEN_LIVE_SHA = "671e19a2188f7126d0627b5a7b2c647cbe53106c49f9916e384213d88892186e"
# golden（历史对照 golden 卡 首行 BG27_822_G / dbf 103592；bacon ally
# 金卡 gate.full=True；form=bg——历史对照 decode_form("103592_bg_golden.png")="bg"）
GOLDEN_CARD = os.environ.get("COLOR_GOLDEN_CARD", "BG27_822_G").strip()
GOLDEN_DBF = int(os.environ.get("COLOR_GOLDEN_DBF", "103592"))


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class SupplyColorIntegration(unittest.TestCase):
    """A4 color 域判据（probe 对账 / 同 sha / 记账）。"""

    @classmethod
    def setUpClass(cls) -> None:
        # 产品串行分支同序（ctx → dbf → font_dirs）
        from eidolon.core.infra import context, dbf
        from eidolon.core.infra.dbf import DbfModule
        from eidolon.core.infra.game_install import resolve_context
        from eidolon.contracts import GameRequest
        from eidolon.core.render.text import glyph_supply
        from eidolon.shell.paths import default_font_dirs

        ctx = resolve_context(GameRequest(GAME_ROOT, "--game"),
                              cache_root=CACHE_ROOT, locale="zhcn")
        context.install(ctx)
        if dbf.installed_default() is None:
            dbf.install_default(DbfModule(ctx.dbf_path))
        glyph_supply.install_font_dirs(default_font_dirs(),
                                       cache_dir=ctx.cache_root / "fonts")
        cls.ctx = ctx
        from eidolon.core.supply_index.cold import compute_identity

        cls.ident = compute_identity(ctx.data_win, ctx.version,
                                     dll_path=ctx.assembly_csharp)

    # ---- 判据 1：probe 对账 ----

    def test_1_probe_parity_live_vs_warm(self) -> None:
        from eidolon.core.supply import color, machine
        from eidolon.core.supply_index.warm import SupplyIndex

        with machine.session():
            live = color.probe()
        with SupplyIndex(INDEX_ROOT) as idx:
            warm = idx.color_probe()
        self.assertEqual(set(warm), set(live), "12 族键集合全等")
        for fam in live:
            self.assertEqual(warm[fam], live[fam],
                             f"族 {fam} 槽位逐项相等（含空占位槽）")
        self.assertEqual(list(warm), list(live), "键序=落盘序（live 序）")
        # atlas 槽位账：纹理族全槽在库（live probe 有效纹理槽 ⊆ warm slots）
        with SupplyIndex(INDEX_ROOT) as idx:
            slots = set(idx.color_atlas_slots())
        n_tex = sum(1 for fam, refs in live.items()
                    for ref in refs if isinstance(ref, str) and ":" in ref)
        self.assertGreater(len(slots), 100, f"atlas 槽位异常少：{len(slots)}")
        for fam in ("minionCardTextures", "spellCardTextures", "heroCardTextures",
                    "weaponCardTextures", "locationCardTextures"):
            built = sum(1 for (f, _ct) in slots if f == fam)
            expect = sum(1 for ref in live[fam]
                         if isinstance(ref, str) and ":" in ref)
            self.assertEqual(built, expect,
                             f"纹理族 {fam} 槽位未全建（{built}/{expect}）")
        print(f"[a4-color] probe 对账：12 族键集合+槽位全等；纹理槽 {n_tex}，"
              f"built atlas slots={len(slots)}")

    # ---- 判据 2 + 记账：seeded vs live 同 sha ----

    def _seed_and_render(self, name: str, card_id: str, dbf: int,
                         *, bg_style: bool = False):
        """seeded 渲染 + 记账（返回 (sha, ledger, hit/live/unused 清单)）。"""
        import eidolon.core.supply.machine as machine
        from eidolon.core.supply_index.seed import CardSeeder

        seeder = CardSeeder.open(INDEX_ROOT, ctx_locale=self.ctx.locale,
                                 ctx_identity=self.ident["identity"])
        self.assertIsNotNone(seeder, f"index 打不开/身份不同源：{INDEX_ROOT}")
        with seeder:
            t1 = time.perf_counter()
            seeds = seeder.seeds_for_card(card_id)
            t_seeds = time.perf_counter() - t1
            self.assertIsNotNone(seeds, "该卡弃种（严格门/转换失败）——见 WARN")
            ledger = seeder.last_ledger
            print(f"[a4-color] {name} assemble+转换={t_seeds:.3f}s "
                  f"{ledger.summary()}")

            created, orig_session_cls = [], machine.Session

            class RecordingSession(orig_session_cls):
                def __init__(self, memo=None):
                    self.recorder = _RecordingMemo(dict(memo or {}))
                    super().__init__(memo=self.recorder)
                    created.append(self.recorder)

            try:
                machine.Session = RecordingSession
                out = OUT_DIR / f"{name}-seeded.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                rc = RenderCard(ref=CardRef("dbf", dbf), out_path=out,
                                overrides={}, bg_style=bg_style)
                from eidolon.core.render.api import _render_one

                t2 = time.perf_counter()
                outcome = _render_one(rc, antialias=False,
                                      seed_provider=seeder.provider_for_card(card_id))
                self.assertTrue(hasattr(outcome, "sha256"),
                                f"{name} seeded 渲染失败：{getattr(outcome, 'problem', None)}")
                sha_seed = outcome.sha256
                t_seed = time.perf_counter() - t2
            finally:
                machine.Session = orig_session_cls
            self.assertIs(machine.Session, orig_session_cls)

        rec = created[0]
        seeded_keys = set(seeds)
        hit = [t for t in rec.requested if t in seeded_keys]
        live = [t for t in rec.requested if t not in seeded_keys]
        unused = [t for t in seeds if t not in rec.requested]
        ledger.hit, ledger.live, ledger.unused = len(hit), len(live), len(unused)
        color_live = [t for t in live if t[0] == "color"]
        color_hit = [t for t in hit if t[0] == "color"]
        color_unused = [t for t in unused if t[0] == "color"]
        print(f"[a4-color] {name} seeded sha={sha_seed} render={t_seed:.1f}s")
        print(f"[a4-color] {name} 记账 hit={len(hit)}（去重 {len(set(hit))}） "
              f"live={len(live)}（去重 {len(set(live))}） "
              f"unused={len(unused)}（去重 {len(set(unused))}）")
        print(f"[a4-color] {name} color 记账 hit={len(set(color_hit))} "
              f"live={len(set(color_live))} unused={len(set(color_unused))}")
        for t in sorted(set(color_hit), key=repr):
            print(f"[a4-color]   color hit  {t}")
        for t in sorted(set(color_unused), key=repr)[:8]:
            print(f"[a4-color]   color unused {t}（另 "
                  f"{max(0, len(set(color_unused)) - 8)}）")
        for t in sorted(set(color_live), key=repr):
            print(f"[a4-color]   color LIVE {t}")
        return sha_seed, ledger, (color_hit, color_live, color_unused)

    def _render_live(self, name: str, dbf: int, *, bg_style: bool = False) -> str:
        from eidolon.core.render.api import _render_one

        out = OUT_DIR / f"{name}-live.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        rc = RenderCard(ref=CardRef("dbf", dbf), out_path=out,
                        overrides={}, bg_style=bg_style)
        outcome = _render_one(rc, antialias=False)
        self.assertTrue(hasattr(outcome, "sha256"),
                        f"{name} live 渲染失败：{getattr(outcome, 'problem', None)}")
        return outcome.sha256

    def test_2_normal_ex1_350_same_sha(self) -> None:
        sha_seed, _ledger, (color_hit, color_live, _cu) = \
            self._seed_and_render("normal", NORMAL_CARD, NORMAL_DBF)
        sha_live = self._render_live("normal", NORMAL_DBF)
        print(f"[a4-color] normal live  sha={sha_live}")
        self.assertEqual(sha_seed, sha_live, "EX1_350 seeded sha 与 live 逐位一致")
        self.assertTrue(color_hit, "color token 应有命中（probe+类色图集）")
        self.assertEqual(color_live, [],
                         f"color token 不得 live 兜底：{color_live}")
        if sha_live != FROZEN_LIVE_SHA:
            print(f"[a4-color] WARN: live sha 与 A2 冻结值不同（游戏换代/语料漂移）"
                  f"——本判据以同会话 live 为准")

    def test_3_golden_bg27_822_same_sha(self) -> None:
        sha_seed, _ledger, (color_hit, color_live, _cu) = \
            self._seed_and_render("golden", GOLDEN_CARD, GOLDEN_DBF,
                                  bg_style=True)
        sha_live = self._render_live("golden", GOLDEN_DBF, bg_style=True)
        print(f"[a4-color] golden live  sha={sha_live}")
        self.assertEqual(sha_seed, sha_live,
                         f"{GOLDEN_CARD}（历史对照 golden）seeded sha 与 live 逐位一致")
        self.assertEqual(color_live, [],
                         f"color token 不得 live 兜底：{color_live}")


class _RecordingMemo(dict):
    """记账 memo（dict 子类）：请求/写点双账（integration_seed_seam 同款）。"""

    def __init__(self, initial):
        super().__init__(initial)
        self.initial_keys = set(dict.keys(self))
        self.requested = []
        self.overwritten = []

    def __contains__(self, token) -> bool:
        self.requested.append(token)
        return super().__contains__(token)

    def __setitem__(self, token, value) -> None:
        self.overwritten.append(token)
        super().__setitem__(token, value)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
