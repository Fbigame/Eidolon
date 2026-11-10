"""integration_supply_seed_one — A3 种子器 e2e（显式跑；需游戏安装 + 真 index）。

判据面（任务单 A3 判据 1）：EX1_350（A2 已冻结其 live sha）live vs seeded
同卡对拍——

  * seed_provider = ``CardSeeder.open(index_root, ctx_locale, ctx_identity)``
    的 ``provider_for_card(card_id)``（A3 库 API；identity 由
    ``cold.compute_identity`` 从 ctx 游戏安装现算——generation 身份同源校验）；
  * seeded 渲染经 **产品 seam**：``api._render_one(seed_provider=...)``（A2
    零参可调用形态直接可用，本文件不改 api）；
  * 断言 seeded PNG sha 与 live **逐位一致**（role→token 转换形状对拍收口——
    A3 硬停点判据）；
  * hit/live/unused 记账（memo 观测件双账：token 被请求/未被 live 重写），
    计数原样打印进报告；
  * ``CardSeeder.open`` 对不存在的 index 根返回 None 不 raise（无 index 行为
    逐位不变的 e2e 面；单测细账在 ``tests/core/test_supply_index_seed.py``）。

用法（route 缓存暖；index 先建：``python -m eidolon.core.supply_index build
--game <root> --cache-root build/phase1/index-cache --locale zhcn``）::

    set EIDOLON_TEST_GAME=D:\\game\\Hearthstone
    .venv-release\\Scripts\\python.exe -m unittest discover -s tests/integration -p integration_supply_seed_one.py -t . -v

    # 或直接：
    .venv-release\\Scripts\\python.exe -m tests.integration.integration_supply_seed_one

配置（env，测试驱动专用不进库面）：``EIDOLON_TEST_GAME``（必填）、
``EIDOLON_TEST_ROUTE_CACHE``（选填，缺省 ``%LOCALAPPDATA%\\Eidolon\\cache``）、
``EIDOLON_TEST_INDEX``（选填，缺省 ``<repo>/build/phase1/index-cache``）、
``SEED_ONE_CARD`` / ``SEED_ONE_DBF``（选填，缺省 EX1_350 / 9）。
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

OUT_DIR = REPO / "build" / "a3-seed-one"

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

CARD_ID = os.environ.get("SEED_ONE_CARD", "EX1_350").strip() or "EX1_350"
DBF = int(os.environ.get("SEED_ONE_DBF", "9"))
# A2 冻结的 EX1_350 live sha（对拍参照；游戏换代则本断言改 informational）
FROZEN_LIVE_SHA = "671e19a2188f7126d0627b5a7b2c647cbe53106c49f9916e384213d88892186e"


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class SeedOneCardTests(unittest.TestCase):
    """live vs seeded 同卡对拍（同一进程内两渲 + index 弃种面）。"""

    @classmethod
    def setUpClass(cls) -> None:
        # 产品串行分支同序（ctx → dbf → font_dirs）；ctx 经 resolve_context
        # 构造（version 解析链与 cold build 同源——identity 校验的前提）。
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
        # generation 身份（组合层注入面）：cold.compute_identity 从 ctx 现算
        from eidolon.core.supply_index.cold import compute_identity

        cls.ident = compute_identity(ctx.data_win, ctx.version,
                                     dll_path=ctx.assembly_csharp)

    def _render(self, name: str, *, seed_provider=None):
        from eidolon.core.render.api import _render_one

        out = OUT_DIR / f"{name}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        rc = RenderCard(ref=CardRef("dbf", DBF), out_path=out, overrides={})
        outcome = _render_one(rc, antialias=False, seed_provider=seed_provider)
        self.assertTrue(hasattr(outcome, "sha256"),
                        f"{name} 渲染失败：{getattr(outcome, 'problem', None)}")
        return outcome

    def test_open_missing_index_returns_none(self) -> None:
        """无 index：open 返回 None 不 raise（调用方拿 None 即纯 live）。"""
        from eidolon.core.supply_index.seed import CardSeeder

        seeder = CardSeeder.open(REPO / "build" / "phase1" / "no-such-index",
                                 ctx_locale=self.ctx.locale,
                                 ctx_identity=self.ident["identity"])
        self.assertIsNone(seeder)

    def test_seeded_render_sha_matches_live(self) -> None:
        import eidolon.core.supply.machine as machine
        from eidolon.core.supply_index.seed import CardSeeder

        # 防呆：card_id ↔ dbf 配对（phase0 spike 同款）
        from eidolon.core.infra.dbf import default_dbf

        self.assertEqual(default_dbf().card_id_to_dbf.get(CARD_ID.casefold()), DBF,
                         f"SEED_ONE_CARD/{CARD_ID} 与 SEED_ONE_DBF={DBF} 不配对")

        # 先 seeded 后 live：seeded 在净进程跑（hit/live/unused 记账不被
        # live 渲染的进程级缓存（_SCENES/_KIT_CACHE 等）污染——spike 对拍
        # 顺序同款；live 只取 sha 判据，不记账）。
        seeder = CardSeeder.open(INDEX_ROOT, ctx_locale=self.ctx.locale,
                                 ctx_identity=self.ident["identity"])
        self.assertIsNotNone(
            seeder, f"index 打不开/身份不同源：{INDEX_ROOT}"
                    f"（identity={self.ident['identity']}）")
        with seeder:
            t1 = time.perf_counter()
            seeds = seeder.seeds_for_card(CARD_ID)
            t_seeds = time.perf_counter() - t1
            self.assertIsNotNone(seeds, "该卡弃种（严格门/转换失败）——见 WARN 日志")
            ledger = seeder.last_ledger
            print(f"[seed-one] assemble+转换={t_seeds:.3f}s {ledger.summary()}")
            for reason in ledger.skipped_reasons:
                print(f"[seed-one] {reason}")

            created, orig_session_cls = [], machine.Session

            class RecordingSession(orig_session_cls):
                """观测用 Session：memo 换 RecordingMemo（Session 形不变）。"""

                def __init__(self, memo=None):
                    self.recorder = _RecordingMemo(dict(memo or {}))
                    super().__init__(memo=self.recorder)
                    created.append(self.recorder)

            try:
                machine.Session = RecordingSession
                t2 = time.perf_counter()
                outcome = self._render("seeded",
                                       seed_provider=seeder.provider_for_card(CARD_ID))
                sha_seed = outcome.sha256
                t_seed_render = time.perf_counter() - t2
            finally:
                machine.Session = orig_session_cls
            self.assertIs(machine.Session, orig_session_cls)   # 观测件零残留

        t0 = time.perf_counter()
        sha_live = self._render("live").sha256
        t_live = time.perf_counter() - t0

        self.assertEqual(len(created), 1, "一次 _render_one 恰开一个会话")
        rec = created[0]
        seeded_keys = set(seeds)
        hit = [t for t in rec.requested if t in seeded_keys]
        live = [t for t in rec.requested if t not in seeded_keys]
        unused = [t for t in seeds if t not in rec.requested]
        ledger.hit, ledger.live, ledger.unused = len(hit), len(live), len(unused)
        print(f"[seed-one] {CARD_ID} live sha={sha_live} render={t_live:.1f}s")
        print(f"[seed-one] {CARD_ID} seeded sha={sha_seed} "
              f"render={t_seed_render:.1f}s")
        print(f"[seed-one] 记账 hit={len(hit)}（去重 {len(set(hit))} token） "
              f"live={len(live)}（去重 {len(set(live))} token） "
              f"unused={len(unused)}（去重 {len(set(unused))} token）"
              f"——查询总账 {len(rec.requested)}（memo 查键可重复计）")
        for t in sorted(set(hit), key=repr):
            print(f"[seed-one]   hit  {t}")
        for t in sorted(set(unused), key=repr):
            print(f"[seed-one]   unused {t}")
        for t in sorted(set(live), key=repr):
            print(f"[seed-one]   live {t}")
        self.assertGreaterEqual(len(hit), 5,
                                f"种子命中过少（hit={hit}）——转换面有缺口")
        self.assertEqual(sha_seed, sha_live, "seeded 渲染 sha 与 live 逐位一致")
        if sha_live != FROZEN_LIVE_SHA:
            print(f"[seed-one] WARN: live sha 与 A2 冻结值不同（游戏换代/语料漂移）"
                  f"——本判据以同会话 live 为准")


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
