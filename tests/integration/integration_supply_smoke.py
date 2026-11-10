"""integration_supply_smoke — Phase 2b supply/recipes/render-text 冒烟（真实游戏；显式跑）。

覆盖任务卡面（每域一个用例，拆薄在先）：
  * ``supply.session()`` 打开（``machine.core().res`` 指向 ``ctx.data_win``）；
  * ``overrides.asset``：PIL 造 512×512 PNG → 装载面正确（img/sha256/ref/path）；
    坏字节 → ``ValueError``（contract E fail loud）；
  * ``art.portrait`` 对已知卡（dbf 8 → CARD.m_noteMiniGuid）resolve 出纹理对象
    （不下载不落 PNG，只断言非 None + 有尺寸）；
  * ``frames.kits``（``kit("ally")``——HAND_MINION 槽、dbf 9 采样 minion 基础卡）
    compile 出 Kit（断言关键键存在；暖 route 后实测 ~4s）；
  * text 字体链：``recipes.text`` 域项 ``font_table`` / ``fontdefs`` /
    ``font_ttf_bytes`` 对 zhCN 侧默认 fontdef 返回非空 bytes。

默认 discover（pattern ``test*.py``）**不收集**本文件；显式跑（需游戏 + UnityPy）：
    EIDOLON_TEST_GAME=<游戏根> python -m unittest discover -s tests/integration \\
        -p 'integration_*.py' -t . -v

初始化纪律（同 Phase 2a 集成测试）：``resolve_context`` → ``context.install`` →
``dbf.install_default(DbfModule(ctx.dbf_path))``；``install_default`` 同路径幂等，
tearDown ``reset_default()``、setUp 重装。本文件**不触 CLR**（不 import card /
game_tag / text_shim；kit 编译经 ``dll_reflect.tables`` 惰性访问活表——
cached_property 首访问才装 coreclr，发生在 install 之后）。

缓存根策略（任务卡「cache_root 用 tmp」的有意偏离，报告在案）：本机游戏
Data/Win 全量 route.db 建库 ~11 分钟（11159 包、~300MB，本机实测），每跑重建
tmp 缓存无法满足「整个文件 ~2-3 分钟」预算——缓存根固定
``build/integration_supply_cache``（gitignored、仓内、可弃；route.db 跨跑复用，
内容键=版本身份，游戏换版自动重建），``EIDOLON_TEST_CACHE`` 可覆盖（测试驱动
env，不入库面）。首跑一次性付建库成本；暖跑实测全文件 ~16s（含进程启动）。

跨文件 ctx 交互（同进程全量跑 ``integration_*.py`` 时）：``context`` 无卸载 API，
``integration_dbf_catalog``（Phase 2a）先装的 ctx（tmp cache_root）会被本文件
setUpClass 采用（同 root/locale、异 cache_root——adopt 而非 raise，避免进程单身份
不变量撞车），本文件于是对**那个 tmp 缓存根**冷建 route.db（~5 分钟）。即：本文件
单独跑 ~16s；全量跑被 Phase 2a 的 tmp ctx 拖到 ~11-12 分钟（其中 ~5 分钟是本文件
在别人 tmp 里的 route 重建）。要快跑请单文件跑本文件；ctx 沙箱隔离（per-file
reset）是 Phase 3 组合层接线时的已知事项。
"""

from __future__ import annotations

import os
import tempfile
import unittest
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
class Phase2bSupplySmokeTests(unittest.TestCase):
    """真实游戏供给链冒烟（ctx/dbf 装一次；会话按用例开关）。"""

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
        # install 之后才 import supply 域（machine.core().res 读 current()）。
        from eidolon.core.supply import art, machine, overrides  # noqa: F401

        cls.machine = machine
        cls.overrides = overrides
        cls.art = art

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        if installed_default() is None:
            install_default(DbfModule(self.ctx.dbf_path))

    def tearDown(self) -> None:
        reset_default()

    # ---- 会话机制（machine）----

    def test_session_opens_res_at_data_win(self) -> None:
        machine = self.machine
        self.assertFalse(machine.in_session())
        with machine.session():
            self.assertTrue(machine.in_session())
            res = machine.core().res
            self.assertEqual(Path(res.win).resolve(), self.ctx.data_win.resolve())
        self.assertFalse(machine.in_session())

    # ---- overrides 域（contract E 装载/校验）----

    def test_overrides_asset_png_and_bad_bytes(self) -> None:
        from PIL import Image

        png = Path(self._tmp.name) / "portrait.png"
        Image.new("RGBA", (512, 512), (10, 20, 30, 255)).save(png)
        with self.machine.session():
            rec = self.overrides.asset(str(png), "portrait")
            self.assertEqual(rec["img"].size, (512, 512))
            self.assertEqual(rec["img"].mode, "RGBA")
            self.assertEqual(len(rec["sha256"]), 64)
            self.assertTrue(rec["ref"].startswith("override:portrait:"))
            self.assertEqual(Path(rec["path"]).resolve(), png.resolve())

            bad = Path(self._tmp.name) / "bad.png"
            bad.write_bytes(b"definitely-not-a-png")
            with self.assertRaises(ValueError):
                self.overrides.asset(str(bad), "portrait")

    # ---- art 域（CardDef → 肖像纹理）----

    def test_art_portrait_resolves_texture(self) -> None:
        # dbf 8 → CARD.m_noteMiniGuid（kit._pick_card_id 同款查法；基础 minion）。
        rec = dbf.default_dbf().card.get("8") or dbf.default_dbf().card.get(8)
        self.assertIsNotNone(rec)
        card_id = rec["m_noteMiniGuid"]
        with self.machine.session():
            img = self.art.portrait(card_id)
            self.assertIsNotNone(img)
            self.assertGreater(img.size[0], 0)
            self.assertGreater(img.size[1], 0)

    # ---- frames 域（kit 编译；冷 kit 重，暖 route 后 ~5-60s）----

    def test_kit_ally_compiles(self) -> None:
        from eidolon.core.supply import frames
        from eidolon.core.supply.frames.kits import Kit

        with self.machine.session():
            kit = frames.kit("ally")
            self.assertIsInstance(kit, Kit)
            self.assertEqual(kit.frame_dir, "ally_frame")
            self.assertGreater(len(kit.arrays), 0)       # mesh npz 内容面
            self.assertGreater(len(kit.textures), 0)     # textures/ 内容面
            self.assertEqual(kit.meta.get("dbf_id"), "9")
            self.assertIn("card_id", kit.meta)
            self.assertIn("prefab", kit.report)

    # ---- text 域（recipes.text 域项链；§6.6 明示的裸 SerializedFile 残留面）----

    def test_text_font_chain(self) -> None:
        from eidolon.core.recipes import text as rtext

        with self.machine.session():
            table = rtext.font_table()
            self.assertGreater(len(table), 0)
            self.assertIn("m_FontDefName", table[0])
            defs = rtext.fontdefs()
            self.assertGreater(len(defs), 0)
            # zhCN 侧有 Font 对象的 def（zhCN 渲染实际消费面）→ 非空 TTF 字节。
            name = next(n for n in sorted(defs)
                        if defs[n].get("zhcn", {}).get("font_object"))
            data = rtext.font_ttf_bytes(name)
            self.assertIsInstance(data, bytes)
            self.assertGreater(len(data), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
