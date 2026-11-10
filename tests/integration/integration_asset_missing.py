"""integration_asset_missing — 设计 §5.3 八边界 GameAssetMissing 负路径（真实游戏）。

覆盖审计返工 Rework C：八个「无对象/无 bundle/无字体」边界逐点验证抛
``GameAssetMissing``（``Problem(ENVIRONMENT, "asset_missing_in_game", ...)``）：
  * ``resolve_asset_ref.resolve``：未知 GUID（catalog 未登记）；
  * ``art.portrait``：cards_map 无该卡（不存在 card id/guid 的卡）；
  * ``watermarks.texture`` / ``named_texture``：未知 watermark ref；
  * ``frames.kits.actor_ref``：actor 活表无该槽位（构造未知 slot）；
  * ``frames.kits._pick_card_id``：CARD 表无该 dbf 行（无 prefab 行的卡，
    Card_Invisible 场景的负例等价构造）；
  * ``color.atlas``：族表注入幽灵 ref（未知 bundle/纹理名）；
  * ``textures``（mip 链直提）：真实 bundle 内无该纹理名；
  * ``text`` 字体链：未知 fontdef 名（显式参数注入未知名）。

负例构造方式（报告在案）：
  - art/watermarks/color 的「resolve 层缺失」走 resolve/container_get 同型 typed
    （未知 GUID 在 catalog 阶段即抛）；color.atlas 用 ``_probe_cache`` 注入幽灵 ref
    （进程级属性读，用后还原），不污染真表。
  - art cards_map / kits actor_ref/_pick_card_id / textures / text 走本域显式 if。

默认 discover（pattern ``test*.py``）**不收集**本文件；显式跑（需游戏 + UnityPy/CLR）：
    EIDOLON_TEST_GAME=<游戏根> [EIDOLON_TEST_CACHE=<缓存根>] \\
        python -m unittest tests.integration.integration_asset_missing -v

初始化纪律（照抄 integration_dbf_catalog / integration_supply_smoke）：
``resolve_context`` → ``context.install``（已装则 adopt，避免同进程全量跑撞
进程单身份不变量）→ ``dbf.install_default(DbfModule(ctx.dbf_path))``；
``install_default`` 同路径幂等，tearDown ``reset_default()``、setUp 重装。

缓存根策略与 integration_supply_smoke 一致（route.db 跨跑复用）：
``EIDOLON_TEST_CACHE`` > ``build/integration_supply_cache``。

import 时序（设计 §6.5）：supply 域 import 全部在 setUpClass install 之后
（frames.kits 顶层 import ``dll_reflect.tables`` 名——活表 cached_property 首访问
才装 coreclr，发生在 install 之后）；模块顶层只 import 纯面。
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from eidolon.contracts import GameRequest
from eidolon.core.infra import context, dbf
from eidolon.core.infra.dbf import DbfModule, install_default, installed_default, reset_default
from eidolon.core.infra.errors import GameAssetMissing
from eidolon.core.infra.game_install import resolve_context

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None

_REPO = Path(__file__).resolve().parents[2]
_cache_env = os.environ.get("EIDOLON_TEST_CACHE", "").strip()
CACHE_ROOT: Path = (Path(_cache_env) if _cache_env
                    else _REPO / "build" / "integration_supply_cache")

_GHOST_GUID = "0" * 32


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class AssetMissingBoundaryTests(unittest.TestCase):
    """八边界负路径（ctx/dbf 装一次；供给调用一律在 session 内）。"""

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
        # install 之后才 import supply 域（machine.core().res 读 current()；
        # frames.kits 的活表访问装 CLR——同样发生在 install 之后）。
        from eidolon.core.supply import art, color, machine, text, textures, watermarks
        from eidolon.core.supply.frames import kits

        cls.machine = machine
        cls.art = art
        cls.color = color
        cls.text = text
        cls.textures = textures
        cls.watermarks = watermarks
        cls.kits = kits

    def setUp(self) -> None:
        if installed_default() is None:
            install_default(DbfModule(self.ctx.dbf_path))

    def tearDown(self) -> None:
        reset_default()

    # ---- 边界：resolve_asset_ref.resolve（infra 层样板，复述钉住）----

    def test_resolve_unknown_guid_raises(self) -> None:
        with self.machine.session():
            with self.assertRaises(GameAssetMissing) as caught:
                self.machine.core().res.resolve(f"Ghost.prefab:{_GHOST_GUID}")
        problem = caught.exception.problem
        self.assertEqual(problem.kind.value, "environment")
        self.assertEqual(problem.code, "asset_missing_in_game")
        self.assertEqual(problem.path, _GHOST_GUID)

    # ---- 边界：art.portrait（cards_map 无该卡）----

    def test_art_portrait_unknown_card_id(self) -> None:
        with self.machine.session():
            with self.assertRaises(GameAssetMissing) as caught:
                self.art.portrait("Ghost_Card_ID")
        problem = caught.exception.problem
        self.assertEqual(problem.code, "asset_missing_in_game")
        self.assertEqual(problem.path, "Ghost_Card_ID")
        self.assertIn("cards_map 无 CardDef", problem.message)

    # ---- 边界：watermarks.texture / named_texture（未知 watermark ref）----

    def test_watermarks_texture_unknown_ref(self) -> None:
        ghost = f"Ghost_Watermark.png:{_GHOST_GUID}"
        with self.machine.session():
            with self.assertRaises(GameAssetMissing) as caught:
                self.watermarks.texture(ghost)
            self.assertEqual(caught.exception.problem.code, "asset_missing_in_game")
            with self.assertRaises(GameAssetMissing) as caught_named:
                self.watermarks.named_texture(ghost)
        self.assertEqual(caught_named.exception.problem.code, "asset_missing_in_game")

    # ---- 边界：frames.kits.actor_ref / _pick_card_id ----

    def test_kits_actor_ref_unknown_slot(self) -> None:
        with self.machine.session():
            with self.assertRaises(GameAssetMissing) as caught:
                self.kits.actor_ref("normal", "GHOST_SLOT")
        problem = caught.exception.problem
        self.assertEqual(problem.code, "asset_missing_in_game")
        self.assertEqual(problem.path, "normal/GHOST_SLOT")
        self.assertIn("actor 活表无 normal/GHOST_SLOT", problem.message)

    def test_kits_pick_card_id_unknown_dbf(self) -> None:
        with self.machine.session():
            with self.assertRaises(GameAssetMissing) as caught:
                self.kits._pick_card_id("999999999")
        problem = caught.exception.problem
        self.assertEqual(problem.code, "asset_missing_in_game")
        self.assertEqual(problem.path, "999999999")
        self.assertIn("CARD 表无 dbf 999999999", problem.message)

    # ---- 边界：color.atlas（族表注入幽灵 ref；_probe_cache 用后还原）----

    def test_color_atlas_unknown_ref(self) -> None:
        saved = self.color._probe_cache
        self.color._probe_cache = {
            "minionCardTextures": [f"Ghost_Color_Atlas.tif:{_GHOST_GUID}"]}
        try:
            with self.machine.session():
                with self.assertRaises(GameAssetMissing) as caught:
                    self.color.atlas("minionCardTextures", 0)
        finally:
            self.color._probe_cache = saved
        problem = caught.exception.problem
        self.assertEqual(problem.code, "asset_missing_in_game")
        # resolve 的 catalog 未登记负例 path=裸 GUID（resolve_asset_ref 正典口径）。
        self.assertEqual(problem.path, _GHOST_GUID)

    # ---- 边界：textures（mip 链直提，真实 bundle 内无该纹理名）----

    def test_textures_chain_unknown_name(self) -> None:
        with self.machine.session():
            bundle = next(iter(self.machine.core().res.catalog.values()))
            with self.assertRaises(GameAssetMissing) as caught:
                self.textures.chain_for_name("Ghost_Texture", (bundle, 12345))
        problem = caught.exception.problem
        self.assertEqual(problem.code, "asset_missing_in_game")
        self.assertTrue(problem.path.endswith("::Ghost_Texture"))
        self.assertIn("bundle 内无纹理", problem.message)

    # ---- 边界：text 字体链（未知 fontdef 名，显式参数注入）----

    def test_text_font_ttf_unknown_fontdef(self) -> None:
        with self.machine.session():
            with self.assertRaises(GameAssetMissing) as caught:
                self.text.font_ttf_bytes("Ghost_FontDef")
        problem = caught.exception.problem
        self.assertEqual(problem.code, "asset_missing_in_game")
        self.assertEqual(problem.path, "Ghost_FontDef")
        self.assertIn("字体定义表无 fontdef", problem.message)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
