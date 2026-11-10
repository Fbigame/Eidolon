"""integration_dbf — dbf.py / provider.py 全链路（fake container + 真实 dbf 冒烟）。

默认 discover（pattern ``test*.py``）**不收集**本文件；显式跑：
    python -m unittest discover -s tests/integration -p 'integration_*.py' -t . -v

真实游戏冒烟用 ``skipUnless(GAME_ROOT and GAME_ROOT.exists(), ...)`` 保护；
游戏根从 ``EIDOLON_TEST_GAME`` 环境变量取（测试驱动专用，不进库面；设计
§13.3）。未设置时真实冒烟 skip——不违反默认 skip 0（默认 discover 根本不
收集本文件）。fake container 段（DbfModule 模块级 + provider.bind 级）不
依赖游戏安装。
"""

from __future__ import annotations

import gc
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eidolon.contracts import (
    CardRef,
    EnvironmentUnavailable,
    GameRequest,
    ProblemKind,
)
from eidolon.core.infra import dbf
from eidolon.core.infra.dbf import (
    DbfModule,
    default_dbf,
    install_default,
    installed_default,
    reset_default,
)
from eidolon.core.infra.provider import DbfCatalogProvider

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None


# ---------------------------------------------------------------------------
# fake container：最小 DBF 记录（不触游戏文件）
# ---------------------------------------------------------------------------

def _loc(name: str) -> dict:
    # LocalString：m_locValues[12] = zhCN（v1 固定口径）。
    return {"m_locValues": [""] * 12 + [name]}


def _fake_card_rows() -> list[dict]:
    return [
        {
            "m_ID": 8,
            "m_noteMiniGuid": "CS2_182",
            "m_name": _loc("冰风雪人"),
            "m_watermarkTextureOverride": "",
        },
        {
            "m_ID": 1121,
            "m_noteMiniGuid": "cs2_029",  # 大小写混排 → casefold 键
            "m_name": _loc("火球术"),
            "m_watermarkTextureOverride": "mini_set_icon:GUID123",
        },
    ]


def _fake_tables() -> dict[str, dict]:
    return {
        "CARD": {"Records": _fake_card_rows()},
        "CARD_TAG": {
            "Records": [
                # plain 行：cardtype 投影源
                {"m_cardId": 8, "m_tagId": 202, "m_tagValue": 4,
                 "m_isPowerKeywordTag": 0, "m_isReferenceTag": 0},
                {"m_cardId": 1121, "m_tagId": 202, "m_tagValue": 5,
                 "m_isPowerKeywordTag": 0, "m_isReferenceTag": 0},
                # reference 行（非 power keyword）→ 排除口径
                {"m_cardId": 999, "m_tagId": 202, "m_tagValue": 4,
                 "m_isPowerKeywordTag": 0, "m_isReferenceTag": 1},
                # power keyword 行即使 reference=1 也保留
                {"m_cardId": 8, "m_tagId": 9999, "m_tagValue": 7,
                 "m_isPowerKeywordTag": 1, "m_isReferenceTag": 1},
            ]
        },
        "CARD_SET": {
            "Records": [{"m_ID": 2, "m_cardWatermarkTextureOverride": "set_icon:G"}]
        },
        "CARD_SET_TIMING": {
            "Records": [
                # 离线口径：首条 203 判活（表序优先）；204 非窗口事件 → pre 视图收
                {"m_cardId": 8, "m_cardSetId": 2, "m_eventTimingEvent": 203},
                {"m_cardId": 8, "m_cardSetId": 3, "m_eventTimingEvent": 204},
                # pre* 事件 → pre 视图排除
                {"m_cardId": 8, "m_cardSetId": 4, "m_eventTimingEvent": 205},
            ]
        },
        "CARD_RACE": {
            "Records": [{"m_ID": 7, "m_isRaceTagId": 402}]
        },
        "KEYWORD_TEXT": {
            "Records": [{
                "m_tagId": 191,
                "m_name": "GLOBAL_KEYWORD_WINDFURY",
                "m_text": "GLOBAL_KEYWORD_WINDFURY_TEXT",
            }]
        },
        "CARD_HERO": {
            "Records": [{
                "m_ID": 1,
                "m_cardId": 7,
                "m_heroType": 3,
                "m_description": _loc("酒馆英雄"),
            }]
        },
        "EventMap": {"m_Keys": ["launch", "pre_order"], "m_Values": [204, 205]},
    }


class _FakeAsset:
    def __init__(self, data: dict) -> None:
        self._data = data

    def read_typetree(self) -> dict:
        return self._data


class _FakeContainer:
    """按 ``Assets/Game/DBF-Asset/<NAME>.asset`` 键返回假对象（记录访问）。"""

    def __init__(self, tables: dict[str, dict]) -> None:
        self._tables = tables
        self.opened: list[str] = []

    def __getitem__(self, key: str):
        self.opened.append(key)
        name = key.rsplit("/", 1)[-1].removesuffix(".asset")
        try:
            return _FakeAsset(self._tables[name])
        except KeyError:
            raise KeyError(key) from None


class _RaisingContainer:
    def __getitem__(self, key: str):
        raise RuntimeError("boom: 坏盘模拟")


class FakeContainerChainTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_default()

    def tearDown(self) -> None:
        reset_default()

    def _module(self, container) -> DbfModule:
        # 路径不存在：显式 container 在场时惰性装载永不发生（不触盘）。
        return DbfModule(Path("Z:/absent/dbf.unity3d"), container=container)

    def test_card_folds_loc_values_12(self) -> None:
        module = self._module(_FakeContainer(_fake_tables()))
        card = module.card
        self.assertEqual(card[8]["m_name"], "冰风雪人")
        self.assertEqual(card[1121]["m_name"], "火球术")
        self.assertEqual(card[8]["m_noteMiniGuid"], "CS2_182")

    def test_card_tag_reference_exclusion(self) -> None:
        module = self._module(_FakeContainer(_fake_tables()))
        tags = module.card_tag
        self.assertEqual(tags["8"][202], 4)
        self.assertEqual(tags["1121"][202], 5)
        self.assertNotIn("999", tags)          # reference 行被排除
        self.assertEqual(tags["8"][9999], 7)   # power keyword 保留

    def test_card_set_offline_and_pre_views(self) -> None:
        module = self._module(_FakeContainer(_fake_tables()))
        self.assertEqual(module.card_set_offline, {8: 2})   # 首条 203 判活
        self.assertEqual(module.card_set_pre, {8: 3})       # 204=launch 收、205=pre_order 排
        self.assertEqual(module.event_map, {204: "launch", 205: "pre_order"})

    def test_small_tables(self) -> None:
        module = self._module(_FakeContainer(_fake_tables()))
        self.assertEqual(module.card_set_dict, {2: module.card_set_dict[2]})
        self.assertEqual(module.card_set_dict[2]["m_cardWatermarkTextureOverride"], "set_icon:G")
        self.assertEqual(module.watermark_override, {1121: "mini_set_icon:GUID123"})
        self.assertEqual(module.card_race, {7: 402})
        self.assertEqual(module.keyword_text[191]["m_name"], "GLOBAL_KEYWORD_WINDFURY")
        self.assertEqual(module.card_hero[7]["m_heroType"], 3)
        self.assertEqual(module.card_hero[7]["m_description"], "酒馆英雄")

    def test_card_id_to_dbf_casefold_first_wins(self) -> None:
        module = self._module(_FakeContainer(_fake_tables()))
        self.assertEqual(module.card_id_to_dbf, {"cs2_182": 8, "cs2_029": 1121})

    def test_explicit_container_never_loads_file(self) -> None:
        container = _FakeContainer(_fake_tables())
        module = self._module(container)
        module.card
        module.card_tag
        self.assertEqual(
            container.opened,
            [f"Assets/Game/DBF-Asset/{name}.asset"
             for name in ("CARD", "CARD_TAG")],
        )

    def test_unreadable_container_wraps_dbf_unreadable(self) -> None:
        module = self._module(_RaisingContainer())
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            module.card
        problem = ctx.exception.problem
        self.assertEqual(problem.code, "dbf_unreadable")
        self.assertEqual(problem.path, "Z:\\absent\\dbf.unity3d")
        self.assertIn("RuntimeError", problem.cause)
        self.assertIn("boom", problem.cause)


class CorruptFileTests(unittest.TestCase):
    """真实坏文件：load_defended 层 typed error → dbf_unreadable 包装。"""

    def setUp(self) -> None:
        reset_default()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.bad = self.tmp / "dbf.unity3d"
        self.bad.write_bytes(b"x")  # 1 字节：签名解析即炸

    def tearDown(self) -> None:
        # dbf_unreadable 的 cause 链持有 UnityPy reader 的帧（内含打开的文件句柄），
        # 异常图是循环引用——tearDown 先 gc 回收再走 tmp 清理，Windows 才能删文件。
        gc.collect()
        reset_default()

    def test_bad_file_becomes_dbf_unreadable(self) -> None:
        module = DbfModule(self.bad)
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            module.card
        problem = ctx.exception.problem
        self.assertEqual(problem.code, "dbf_unreadable")
        self.assertEqual(problem.path, str(self.bad))
        self.assertTrue(problem.cause)  # 类型+消息账保留


class DefaultSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_default()

    def tearDown(self) -> None:
        reset_default()

    def test_uninstalled_raises(self) -> None:
        self.assertIsNone(installed_default())
        with self.assertRaises(RuntimeError):
            default_dbf()

    def test_install_then_read(self) -> None:
        module = DbfModule(Path("Z:/a.dbf"), container=_FakeContainer(_fake_tables()))
        installed = install_default(module)
        self.assertIs(installed, module)
        self.assertIs(installed_default(), module)
        self.assertIs(default_dbf(), module)

    def test_same_path_is_idempotent_noop(self) -> None:
        first = DbfModule(Path("Z:/a.dbf"), container=_FakeContainer(_fake_tables()))
        install_default(first)
        second = DbfModule(Path("Z:/a.dbf"), container=_FakeContainer(_fake_tables()))
        self.assertIs(install_default(second), first)  # 返回已装实例

    def test_same_path_different_spelling_is_idempotent(self) -> None:
        first = DbfModule(Path("Z:/a.dbf"), container=_FakeContainer(_fake_tables()))
        install_default(first)
        second = DbfModule(Path("Z:/./A.DBF"), container=_FakeContainer(_fake_tables()))
        # normcase + abspath 同装判定（Windows 大小写/分隔符不敏感）。
        self.assertIs(install_default(second), first)

    def test_different_path_raises(self) -> None:
        install_default(DbfModule(Path("Z:/a.dbf"), container=_FakeContainer(_fake_tables())))
        with self.assertRaises(RuntimeError):
            install_default(DbfModule(Path("Z:/b.dbf"), container=_FakeContainer(_fake_tables())))

    def test_reset_clears(self) -> None:
        install_default(DbfModule(Path("Z:/a.dbf"), container=_FakeContainer(_fake_tables())))
        reset_default()
        self.assertIsNone(installed_default())
        with self.assertRaises(RuntimeError):
            default_dbf()


# ---------------------------------------------------------------------------
# provider.bind 的 fake container 段（审计 P1-9：空表守卫 / 重复 guid /
# cardtype 投影此前无正测试）。不触游戏文件。
# ---------------------------------------------------------------------------

class ProviderFakeContainerTests(unittest.TestCase):
    """provider.bind 的 fake container 段（复用 _fake_card_rows 模式）。

    bind 内部自构 ``DbfModule(dbf_path)``——container 注入点是 patch
    provider 模块的 ``DbfModule`` 名（真类 + 显式 container：惰性装载
    不触盘）。假安装根只需要 Hearthstone.exe + Data/Win/dbf.unity3d
    占位文件（后者只进 identity 的 stat 账面）。
    """

    def setUp(self) -> None:
        reset_default()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "game"
        self.root.mkdir()
        (self.root / "Hearthstone.exe").write_bytes(b"")
        (self.root / "Data" / "Win").mkdir(parents=True)
        self.dbf_path = self.root / "Data" / "Win" / "dbf.unity3d"
        self.dbf_path.write_bytes(b"")
        self.provider = DbfCatalogProvider(
            cache_root=self.tmp / "cache", locale="zhcn")

    def tearDown(self) -> None:
        reset_default()

    def _bind(self, tables) -> "object":
        container = _FakeContainer(tables)

        def factory(path, **kwargs):
            return DbfModule(path, container=container, **kwargs)

        with mock.patch(
            "eidolon.core.infra.provider.DbfModule", side_effect=factory
        ):
            return self.provider.bind(GameRequest(self.root, "--game"))

    def test_empty_card_table_maps_dbf_unreadable(self) -> None:
        # 空表守卫：不得让 complete=True 把所有卡误判成 unknown_card。
        tables = _fake_tables()
        tables["CARD"]["Records"] = []
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            self._bind(tables)
        problem = ctx.exception.problem
        self.assertEqual(problem.code, "dbf_unreadable")
        self.assertEqual(problem.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(problem.path, str(self.dbf_path))

    def test_empty_card_tag_table_maps_dbf_unreadable(self) -> None:
        tables = _fake_tables()
        tables["CARD_TAG"]["Records"] = []
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            self._bind(tables)
        problem = ctx.exception.problem
        self.assertEqual(problem.code, "dbf_unreadable")
        self.assertEqual(problem.kind, ProblemKind.ENVIRONMENT)

    def test_duplicate_guid_first_wins_with_warning(self) -> None:
        # 重复 guid：先到先得（guid 键不动），重复者只记账 + warning。
        rows = _fake_card_rows()
        rows.append({
            "m_ID": 9,
            "m_noteMiniGuid": "CS2_182",  # 与 m_ID=8 同 guid、不同 dbf id
            "m_name": _loc("重复冰风雪人"),
            "m_watermarkTextureOverride": "",
        })
        tables = _fake_tables()
        tables["CARD"]["Records"] = rows
        binding = self._bind(tables)
        self.assertEqual(binding.catalog.duplicates, ("CS2_182",))
        self.assertIn("duplicate_card_id", binding.warnings)
        self.assertTrue(binding.catalog.complete)
        # 先到先得：guid 键仍指向首张（8）的 facts（tag 202=4 → MINION）。
        first = binding.catalog.lookup(CardRef("card", "CS2_182"))
        self.assertEqual(first.cardtype, "MINION")
        # 重复者的 dbf id 不丢卡（by_dbf_id 全量在册；无 tag 行 → 事实不全）。
        dup = binding.catalog.lookup(CardRef("dbf", 9))
        self.assertEqual(dup.cardtype, "")

    def test_cardtype_value_not_in_mirror_maps_constants_unavailable(self) -> None:
        # tag 202 的值不在静态镜像（如 9999）→ 响亮 constants_unavailable，
        # 不静默猜（审计 P1-9：镜像缺值分支此前无正测试）。
        tables = _fake_tables()
        for row in tables["CARD_TAG"]["Records"]:
            if row["m_cardId"] == 8 and row["m_tagId"] == 202:
                row["m_tagValue"] = 9999
        with self.assertRaises(EnvironmentUnavailable) as ctx:
            self._bind(tables)
        problem = ctx.exception.problem
        self.assertEqual(problem.code, "constants_unavailable")
        self.assertEqual(problem.kind, ProblemKind.ENVIRONMENT)
        self.assertIn("9999", problem.message)

    def test_missing_cardtype_tag_projects_empty_facts(self) -> None:
        # tag 缺失（卡在、202 行缺）→ CardFacts(cardtype="")：事实不全，
        # compile_spec defer style 检查，不误报 unknown_card。
        tables = _fake_tables()
        tables["CARD_TAG"]["Records"] = [
            row for row in tables["CARD_TAG"]["Records"]
            if not (row["m_cardId"] == 1121 and row["m_tagId"] == 202)
        ]
        binding = self._bind(tables)
        missing = binding.catalog.lookup(CardRef("card", "cs2_029"))
        self.assertEqual(missing.cardtype, "")
        # 对照组：tag 在场的卡正常投影（202=4 → MINION）。
        present = binding.catalog.lookup(CardRef("card", "CS2_182"))
        self.assertEqual(present.cardtype, "MINION")
        self.assertTrue(binding.catalog.complete)
        self.assertNotIn("duplicate_card_id", binding.warnings)


# ---------------------------------------------------------------------------
# 真实 dbf 冒烟（本机游戏安装；游戏缺席机器显式跑时 skip）
# ---------------------------------------------------------------------------

@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(), f"本机未设 EIDOLON_TEST_GAME 或路径不存在")
class RealDbfSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_default()

    def tearDown(self) -> None:
        reset_default()

    def test_dbf_module_real_tables(self) -> None:
        module = DbfModule(GAME_ROOT / "Data" / "Win" / "dbf.unity3d")
        self.assertGreater(len(module.card), 30000)
        self.assertTrue(module.card_tag)
        self.assertIn("cs2_182", module.card_id_to_dbf)

    def test_provider_bind_real(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = DbfCatalogProvider(cache_root=Path(tmp), locale="zhcn")
            binding = provider.bind(GameRequest(GAME_ROOT, "--game"))
        self.assertTrue(binding.catalog.complete)
        self.assertIsNotNone(binding.catalog.lookup(CardRef("dbf", 8)))
        card_facts = binding.catalog.lookup(CardRef("card", "CS2_182"))
        self.assertIsNotNone(card_facts)
        self.assertEqual(binding.identity.kind, "dbf")
        self.assertTrue(binding.identity.size > 0)
        self.assertNotIn("duplicate_card_id", binding.warnings)
        assert binding.game is not None
        self.assertEqual(binding.game.root_source, "--game")
        self.assertEqual(binding.game.locale, "zhcn")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
