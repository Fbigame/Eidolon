"""integration_dbf_catalog — Phase 2a 渲染依赖链冒烟（真实游戏 + CLR；显式跑）。

覆盖任务卡面：Card 双入口（default_dbf / 显式 dbf 注入）、card_id_to_dbf casefold
查询（resolve_dbf_id 语义预演）、§6.3 维护纪律的 live 对拍（四表 × facts 镜像 +
GAME_TAG.CARDTYPE id）、game_strings.race_names、resolve_asset_ref 负路径
（GameAssetMissing）、text_shim 冒烟。

默认 discover（pattern ``test*.py``）**不收集**本文件；显式跑（需游戏 + CLR）：
    EIDOLON_TEST_GAME=<游戏根> python -m unittest discover -s tests/integration \\
        -p 'integration_*.py' -t . -v

初始化纪律（任务卡）：``resolve_context`` → ``context.install`` →
``dbf.install_default(DbfModule(ctx.dbf_path))``。同进程重复 install 异身份会
raise——cache_root 用类级共享 tmp；``install_default`` 同路径幂等，setUp 用
``installed_default()`` 判断，tearDown ``reset_default()``。

CLR-at-import 清单（设计 §6.5）：card / game_tag / game_strings / text_shim 在
import 期即装载 coreclr——本文件全部在 setUpClass（install 完成后）才 import，
模块顶层只 import 纯面（route/facts/dbf/context/dll_reflect/resolve_asset_ref）。
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from eidolon.contracts import GameRequest
from eidolon.core.infra import context, dbf, dll_reflect, facts
from eidolon.core.infra.dbf import DbfModule, install_default, installed_default, reset_default
from eidolon.core.infra.game_install import resolve_context
from eidolon.core.infra import resolve_asset_ref
from eidolon.core.infra.errors import GameAssetMissing

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class Phase2aRenderingDepsTests(unittest.TestCase):
    """真实游戏渲染依赖链（ctx/dbf 装一次，测试间只重置 dbf 会话）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.ctx = resolve_context(GameRequest(GAME_ROOT, "--game"),
                                  cache_root=Path(cls._tmp.name), locale="zhcn")
        # context.install：同进程只装一次；异身份（理论上不会出现——本类是唯一
        # install 者）直接复用已装实例。
        installed = context.installed()
        if installed is None:
            context.install(cls.ctx)
        else:
            cls.ctx = installed
        if installed_default() is None:
            install_default(DbfModule(cls.ctx.dbf_path))
        # install 之后才 import CLR-at-import 清单内的模块（§6.5）。
        from eidolon.core.infra import card, game_strings, game_tag, text_shim

        cls.card = card
        cls.game_strings = game_strings
        cls.game_tag = game_tag
        cls.text_shim = text_shim
        cls.module = installed_default()

    def setUp(self) -> None:
        # 同类内前一测试 reset_default 后这里重装（同路径幂等；异路径必 raise——
        # 同进程一个 dbf 会话的不变量由 install_default 自守）。
        if installed_default() is None:
            install_default(DbfModule(self.ctx.dbf_path))

    def tearDown(self) -> None:
        reset_default()

    # ---- Card 双入口（§6.2 迁移表）----

    def test_card_from_dbf_double_entry(self) -> None:
        via_default = self.card.Card.from_dbf(8)
        via_explicit = self.card.Card.from_dbf(8, dbf=self.module)
        self.assertEqual(via_default.dbf_id, 8)
        self.assertEqual(via_explicit.dbf_id, 8)
        self.assertEqual(via_default.card_id, via_explicit.card_id)
        self.assertTrue(via_default.card_id)                     # 有效 noteMiniGuid
        self.assertEqual(via_default.name, via_explicit.name)
        self.assertEqual(int(via_default.cardtype), int(via_explicit.cardtype))
        self.assertEqual(via_default.set_id, via_explicit.set_id)

    def test_card_id_to_dbf_casefold_query(self) -> None:
        # resolve_dbf_id 语义预演：查询侧 casefold 后进 casefold 键索引，且反查闭环。
        # 实测客户端：cs2_182（冰风雪人）→ dbf 90；断言走索引闭环不钉具体值。
        dbf_id = self.module.card_id_to_dbf["cs2_182"]
        self.assertEqual(self.module.card_id_to_dbf["CS2_182".casefold()], dbf_id)
        self.assertEqual(
            str(self.module.card[dbf_id]["m_noteMiniGuid"]).casefold(), "cs2_182")
        card = self.card.Card.from_dbf(dbf_id)
        self.assertEqual(card.card_id, self.module.card[dbf_id]["m_noteMiniGuid"])
        self.assertEqual(card.dbf_id, dbf_id)

    def test_races_text_override_seat(self) -> None:
        # §7.5 座位：构造可带 override；非 tag 派生（设置后不被 _invalidate 清）
        c = self.card.Card.from_dbf(8, dbf=self.module)
        self.assertIsNone(c.races_text_override)
        c.races_text_override = ("兽人",)
        self.assertEqual(c.races_text_override, ("兽人",))
        c.tags[self.game_tag.GameTag.COST] = 9     # 写侧失效触发
        self.assertEqual(c.races_text_override, ("兽人",))   # 座位不在失效域

    # ---- live 对拍（§6.3 维护纪律：漂移即红）----

    def test_live_enum_tables_match_facts_mirror(self) -> None:
        for enum_name, names, known in (
            ("TAG_CARDTYPE", facts.CARDTYPE_NAMES, facts.KNOWN_CARDTYPES),
            ("TAG_CLASS", facts.CLASS_NAMES, facts.KNOWN_CLASSES),
            ("TAG_RARITY", facts.RARITY_NAMES, facts.KNOWN_RARITIES),
            ("TAG_SPELL_SCHOOL", facts.SPELL_SCHOOL_NAMES, facts.KNOWN_SPELL_SCHOOLS),
        ):
            with self.subTest(enum=enum_name):
                live = dll_reflect.enum_table(enum_name)
                # 值全等（name→value 与镜像互为反转）
                self.assertEqual(live, {v: k for k, v in names.items()})
                # 声明序全等（known_* 是声明序名称集合，集成对拍钉死）
                self.assertEqual(tuple(live), known)

    def test_game_tag_cardtype_id_matches_facts(self) -> None:
        self.assertEqual(int(self.game_tag.GameTag.CARDTYPE), facts.CARD_TYPE_TAG_ID)
        self.assertEqual(facts.CARD_TYPE_TAG_ID, 202)

    def test_race_names_nonempty(self) -> None:
        self.assertTrue(self.game_strings.race_names)
        for key in self.game_strings.race_names.values():
            self.assertTrue(key.startswith("GLOBAL_RACE_"))

    # ---- resolve_asset_ref 负路径（GameAssetMissing，§5.3 边界）----

    def test_resolve_unknown_guid_raises_game_asset_missing(self) -> None:
        resolver = resolve_asset_ref.Resolver(self.ctx.data_win)
        ghost_guid = "0" * 32
        with self.assertRaises(GameAssetMissing) as caught:
            resolver.resolve(f"Ghost.prefab:{ghost_guid}")
        problem = caught.exception.problem
        self.assertEqual(problem.code, "asset_missing_in_game")
        self.assertEqual(problem.path, ghost_guid)

    def test_container_get_unknown_object_raises(self) -> None:
        # 先借 catalog 拿一个真实 bundle，再对其中不存在的 guid 取对象 → 响亮
        resolver = resolve_asset_ref.Resolver(self.ctx.data_win)
        guid = next(iter(resolver.catalog))
        bundle = resolver.catalog[guid]
        real = resolver.container_get(bundle, guid)           # 正路径可用
        self.assertIsNotNone(real[0])
        with self.assertRaises(GameAssetMissing) as caught:
            resolver.container_get(bundle, "f" * 32)
        self.assertEqual(caught.exception.problem.code, "asset_missing_in_game")

    # ---- text_shim 冒烟（PY_BUILDERS 路由 / dll 路由都不炸；§6.2 迁移表）----

    def test_text_shim_smoke(self) -> None:
        card = self.card.Card.from_dbf(8)
        text, info = self.text_shim.desc_text_for(card)
        self.assertIsInstance(text, str)
        self.assertIn(info["route"], ("py", "dll"))
        self.assertIn("builder_type", info)
        self.assertFalse(info["degraded"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
