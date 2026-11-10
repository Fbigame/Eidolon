"""integration_seed_seam — A2 S1 生产 seam e2e（显式跑；需游戏安装 + 暖 route 缓存）。

判据面（任务单 A2）：手工种一个 ``art.portrait`` token——

  * token 数据先经 **live 路径**取得（手动 ``session()`` 内直调 @item served，
    与渲染链同一条解码路）；
  * 构造 seeds 走 **产品 seam**：``api._render_one(seed_provider=...)`` 渲染
    同卡（seed_session 预置 pending → ``_in_session`` 内首个 ``session()``
    一次性消费为初始 memo——不改 components/render_with，零 monkeypatch
    session 本体）；
  * 断言该 token **命中会话 memo**：RecordingMemo 双账观测——token 被请求
    （``__contains__``）且未被 live 重写（``__setitem__``）、memo 终值 is 种子
    对象。served 查键命中即返回种子值 ⇒ ``art.portrait`` 域函数体零执行 ⇒
    该 token 的 Resolver 解码路径零触达（机制级证明另见
    ``tests/core/test_supply_seed.py`` 的计数器用例）；
  * 输出 PNG sha 与 live 渲染**逐位一致**（只种 1/67 token，其余 token 照旧
    live=fallback 天然的同卡实证）；
  * provider 给 None/空 → 纯 live（seam 关闭路径同 sha）。

用法（route 缓存暖；冷建 ~300s 归 route v6 判据，不在本脚本重付）::

    set EIDOLON_TEST_GAME=D:\\game\\Hearthstone
    .venv-release\\Scripts\\python.exe -m unittest discover -s tests/integration -p integration_seed_seam.py -t . -v

    # 或直接：
    .venv-release\\Scripts\\python.exe -m tests.integration.integration_seed_seam

配置（env，测试驱动专用不进库面）：``EIDOLON_TEST_GAME``（必填）、
``EIDOLON_TEST_ROUTE_CACHE``（选填，缺省 ``%LOCALAPPDATA%\\Eidolon\\cache``
暖缓存）、``SEED_SEAM_CARD`` / ``SEED_SEAM_DBF``（选填，缺省 EX1_350 / 9——
phase0 spike 已证配对）。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from eidolon.contracts import CardRef, GameContext, RenderCard

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "build" / "a2-seed-seam"

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT = Path(_game_env) if _game_env else None

_cache_env = os.environ.get("EIDOLON_TEST_ROUTE_CACHE", "").strip()
if _cache_env:
    CACHE_ROOT = Path(_cache_env)
else:
    local = os.environ.get("LOCALAPPDATA", "")
    CACHE_ROOT = Path(local) / "Eidolon" / "cache" if local else Path.home() / ".cache" / "eidolon"

CARD_ID = os.environ.get("SEED_SEAM_CARD", "EX1_350").strip() or "EX1_350"
DBF = int(os.environ.get("SEED_SEAM_DBF", "9"))


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class SeedSeamTests(unittest.TestCase):
    """live vs seeded 同卡对拍（同一进程内三渲：live / seeded / provider-None）。"""

    @classmethod
    def setUpClass(cls) -> None:
        # 产品串行分支同序（ctx → dbf → font_dirs；_render_one 全参缺省）
        from eidolon.core.infra import context, dbf
        from eidolon.core.infra.dbf import DbfModule
        from eidolon.core.render.text import glyph_supply
        from eidolon.shell.paths import default_font_dirs

        ctx = GameContext(root=GAME_ROOT, cache_root=CACHE_ROOT,
                          locale="zhcn", root_source="integration-seed-seam")
        context.install(ctx)
        if dbf.installed_default() is None:
            dbf.install_default(DbfModule(ctx.dbf_path))
        glyph_supply.install_font_dirs(default_font_dirs(),
                                       cache_dir=ctx.cache_root / "fonts")

    def _render(self, name: str, *, seed_provider=None):
        from eidolon.core.render.api import _render_one

        out = OUT_DIR / f"{name}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        rc = RenderCard(ref=CardRef("dbf", DBF), out_path=out, overrides={})
        outcome = _render_one(rc, antialias=False, seed_provider=seed_provider)
        self.assertTrue(hasattr(outcome, "sha256"),
                        f"{name} 渲染失败：{getattr(outcome, 'problem', None)}")
        return outcome

    def _live_portrait_token(self):
        """live 路径取 ``art.portrait`` token 数据（与渲染链同一条解码路）。"""
        import eidolon.core.supply.machine as machine
        from eidolon.core.supply.art import portrait as art_portrait

        with machine.session():
            return art_portrait(CARD_ID)

    def test_seeded_portrait_token_hits_memo_and_sha_matches(self) -> None:
        import eidolon.core.supply.machine as machine

        # 防呆：card_id ↔ dbf 配对（phase0 spike 同款）
        from eidolon.core.infra.dbf import default_dbf

        self.assertEqual(default_dbf().card_id_to_dbf.get(CARD_ID.casefold()), DBF,
                         f"SEED_SEAM_CARD/{CARD_ID} 与 SEED_SEAM_DBF={DBF} 不配对")

        sha_live = self._render("live").sha256

        seed_img = self._live_portrait_token()
        token = ("art", "portrait", (CARD_ID,))
        seeds = {token: seed_img.copy()}   # 防共享可变态：种子持有独立副本

        created, orig_session_cls = [], machine.Session

        class RecordingSession(orig_session_cls):
            """观测用 Session：memo 换 RecordingMemo（Session 形不变）。"""

            def __init__(self, memo=None):
                self.recorder = _RecordingMemo(dict(memo or {}))
                super().__init__(memo=self.recorder)
                created.append(self.recorder)

        try:
            machine.Session = RecordingSession
            sha_seed = self._render("seeded", seed_provider=lambda: seeds).sha256
        finally:
            machine.Session = orig_session_cls
        self.assertIs(machine.Session, orig_session_cls)   # 观测件零残留

        # 1) memo 命中证据：token 被渲染链请求、未被 live 重写、终值 is 种子对象
        self.assertEqual(len(created), 1, "一次 _render_one 恰开一个会话")
        rec = created[0]
        self.assertEqual(rec.initial_keys, {token}, "pending 消费=memo 预填种子面")
        self.assertIn(token, rec.requested, "渲染链请求了 art.portrait token")
        self.assertNotIn(token, rec.overwritten,
                         "token 未被 live 重写=served 查键命中种子 memo 直接返回"
                         "（域函数体零执行 → Resolver 解码路径对该 token 零触达）")
        self.assertIs(rec.get(token), seeds[token], "memo 终值 is 种子对象")

        # 2) pending/会话卫生：seam 消费后无残留
        self.assertIsNone(machine._pending_seed.get())

        # 3) 输出逐位一致（只种 1 token，其余 token 照旧 live=fallback 天然）
        self.assertEqual(sha_seed, sha_live, "seeded 渲染 sha 与 live 逐位一致")
        print(f"[seed-seam] {CARD_ID} live sha={sha_live}")
        print(f"[seed-seam] {CARD_ID} seeded sha={sha_seed}（token {token} 命中 memo）")

    def test_provider_none_or_empty_is_pure_live(self) -> None:
        """seam 关闭路径：provider 给 None/空 dict → 纯 live，同卡同 sha。"""
        sha_live = self._render("live-pure").sha256
        sha_none = self._render("seed-none", seed_provider=lambda: None).sha256
        sha_empty = self._render("seed-empty", seed_provider=lambda: {}).sha256
        self.assertEqual(sha_none, sha_live)
        self.assertEqual(sha_empty, sha_live)


class _RecordingMemo(dict):
    """记账 memo（dict 子类）：请求/写点双账。

    served 的查键点=``token not in memo``：被请求（requested）且未被重写
    （overwritten）⇔ 命中种子 memo 直接返回（live 解码会先 ``__setitem__``
    再返回，两账必然同时出现）。"""

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


if __name__ == "__main__":
    unittest.main()
