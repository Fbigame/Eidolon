"""core/supply_index schema/paths/diff 判定面单测（默认 discover 收集；零 UnityPy）。

覆盖（任务 A1）：
  * SupplyLayout 纯路径派生：current.json / gen_dir / gen_db / gen_db_build /
    blobs / health stamp 相对 cache_root 的关系；blob 内容寻址分片与非法 sha 拒绝；
  * schema DDL：tmp DB 建表断言表/列/唯一约束存在；cjson 稳定性；sha256_hex；
  * 五态判定（reused/revalidate/stale/missing/orphan）：diff() 的 cheap 判定是
    纯 DB 函数（零游戏访问）——tmp 造 from/to 两代行集直测五态 + bundle 三态；
  * revalidate --exact 转移记账核心 ``diff._apply_exact_transitions``（纯函数面：
    reused+carryover / stale / revalidate 保持带因）；
  * import 卫生：子进程 import schema + warm 后 sys.modules 无 UnityPy/clr/
    texture2ddecoder（warm 的 numpy/PIL 合法，不入断言）。

本文件禁触游戏文件与真实缓存根：所有 DB/路径都在 tempfile 里。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.paths import HEALTH_STAMP_VERSION, SupplyLayout

_REPO = Path(__file__).resolve().parents[2]

# 五态域词（diff.py 判定面输出；此处钉死词汇——五态语义的契约面）
FIVE_STATES = ("reused", "revalidate", "stale", "missing", "orphan")


class _TmpCase(unittest.TestCase):
    """每个用例一个临时目录。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)


class SupplyLayoutPathTests(_TmpCase):
    """SupplyLayout 纯路径派生（不触 IO 的部分）。"""

    def test_layout_paths_relative_to_root(self) -> None:
        lay = SupplyLayout(self.root / "cache")
        base = self.root / "cache"
        self.assertEqual(lay.root, base)
        self.assertEqual(lay.current_json, base / "current.json")
        self.assertEqual(lay.blobs_dir, base / "blobs")
        self.assertEqual(lay.lock_dir, base / "lock")
        self.assertEqual(lay.gens_dir, base / "gens")
        self.assertEqual(lay.gen_dir("g1"), base / "gens" / "gen-g1")
        self.assertEqual(lay.gen_db("g1"), base / "gens" / "gen-g1" / "index.sqlite")
        self.assertEqual(lay.gen_db_build("g1"),
                         base / "gens" / "gen-g1" / "index.sqlite.build")
        self.assertEqual(lay.health_stamp_path("g1"),
                         base / "gens" / "gen-g1" / "index.sqlite.health.json")
        # gen_db_build 是建库临时位：与正式 DB 同目录、不同名（os.replace 发布）
        self.assertNotEqual(lay.gen_db_build("g1"), lay.gen_db("g1"))
        self.assertEqual(lay.gen_db_build("g1").parent, lay.gen_db("g1").parent)

    def test_layout_accepts_str_root(self) -> None:
        lay = SupplyLayout(str(self.root / "cache"))
        self.assertEqual(lay.root, self.root / "cache")

    def test_blob_path_sharding(self) -> None:
        lay = SupplyLayout(self.root)
        sha = "ab" * 32
        p = lay.blob_path(sha)
        self.assertEqual(p, self.root / "blobs" / "ab" / "ab" / f"{sha}.png")
        self.assertEqual(lay.blob_path(sha.upper()), p)          # 大写归一小写
        self.assertEqual(lay.blob_path(sha, ext=".json"),
                         self.root / "blobs" / "ab" / "ab" / f"{sha}.json")

    def test_blob_path_rejects_bad_sha(self) -> None:
        lay = SupplyLayout(self.root)
        for bad in ("", "zz" * 32, "abc", "ab" * 31 + "g"):
            with self.assertRaises(ValueError):
                lay.blob_path(bad)


class SupplyLayoutIOTests(_TmpCase):
    """current.json / 健康 stamp 的原子读写与容错（坏 JSON=None 不炸）。"""

    def test_current_json_roundtrip_and_corruption(self) -> None:
        lay = SupplyLayout(self.root)
        self.assertIsNone(lay.read_current())                 # 缺文件=None
        doc = {"game_id": "g1", "generation": "gen-g1", "locale": "zhcn"}
        lay.write_current(doc)
        self.assertEqual(lay.read_current(), doc)
        lay.current_json.write_text("{not json", encoding="utf-8")
        self.assertIsNone(lay.read_current())                 # 坏 JSON=None
        # tmp 残留不留在 root（原子写：mkstemp + os.replace）
        strays = [p.name for p in self.root.iterdir()
                  if p.name.startswith(".current.")]
        self.assertEqual(strays, [])

    def test_health_stamp_roundtrip_and_corruption(self) -> None:
        lay = SupplyLayout(self.root)
        self.assertIsNone(lay.read_health_stamp("g1"))
        db = self.root / "gens" / "gen-g1" / "index.sqlite"
        db.parent.mkdir(parents=True, exist_ok=True)
        db.write_bytes(b"x" * 8)
        self.assertTrue(lay.write_health_stamp("g1", db_path=db, locale="zhcn",
                                               how="quick_check"))
        doc = lay.read_health_stamp("g1")
        self.assertIsNotNone(doc)
        self.assertEqual(doc["v"], HEALTH_STAMP_VERSION)
        self.assertEqual(doc["db_size"], db.stat().st_size)
        self.assertEqual(doc["db_mtime_ns"], db.stat().st_mtime_ns)
        self.assertEqual(doc["locale"], "zhcn")
        self.assertEqual(doc["how"], "quick_check")
        lay.health_stamp_path("g1").write_text("{not json", encoding="utf-8")
        self.assertIsNone(lay.read_health_stamp("g1"))        # 坏 JSON=None

    def test_burn_removes_health_stamp_and_generation_dir(self) -> None:
        # P1-1：five_state 的 synth 代会写 health stamp；_burn 必须一并清掉，
        # 否则 gen-synth* 残目录留在 gens/ 下。
        from eidolon.core.supply_index import diff as D

        lay = SupplyLayout(self.root)
        gen_dir = lay.gen_dir("synthto-test")
        gen_dir.mkdir(parents=True)
        db = lay.gen_db("synthto-test")
        db.write_bytes(b"x" * 8)
        lay.write_health_stamp("synthto-test", db_path=db, locale="zhcn",
                               how="quick_check")
        self.assertTrue(lay.health_stamp_path("synthto-test").is_file())
        D._burn(db)
        self.assertFalse(gen_dir.exists())


class SchemaDdlTests(_TmpCase):
    """DDL：tmp DB 建表断言表/列/约束。"""

    def _conn(self) -> sqlite3.Connection:
        conn = S.connect(self.root / "index.sqlite")
        self.addCleanup(conn.close)
        S.init_schema(conn)
        return conn

    def test_connect_readonly_missing_db(self) -> None:
        with self.assertRaises(sqlite3.OperationalError):
            S.connect(self.root / "nope.sqlite", readonly=True)

    def test_all_tables_created(self) -> None:
        conn = self._conn()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for want in ("meta", "asset_catalog", "asset_variants", "cards", "bundles",
                     "containers", "objects", "locators", "locator_inputs",
                     "plans", "plan_items", "items", "item_blobs", "blobs",
                     "migration_report"):
            self.assertIn(want, tables)

    def test_key_columns_present(self) -> None:
        conn = self._conn()
        want = {
            "cards": ["card_id", "dbf_id", "carddef_ref", "carddef_guid",
                      "carddef_bundle", "carddef_cab", "carddef_path_id",
                      "data_sha"],
            "locators": ["id", "kind", "subject", "locale", "premium", "ref",
                         "guid", "bundle", "cab", "path_id", "status",
                         "source_json"],
            "plans": ["plan_key", "card_id", "options_json", "status",
                      "plan_version", "card_data_sha", "created_at"],
            "plan_items": ["plan_key", "item_key", "role"],
            "items": ["item_key", "domain", "item", "params_json", "codec",
                      "codec_version", "manifest_json", "status", "source_kind",
                      "source_json", "content_inputs_json", "created_at"],
            "item_blobs": ["item_key", "blob_key", "role"],
            "blobs": ["blob_key", "payload_sha256", "size", "codec",
                      "codec_version", "last_used", "created_at"],
            "migration_report": ["game_id", "kind", "key", "status", "reason",
                                 "detail_json"],
        }
        for table, cols in want.items():
            got = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            for c in cols:
                self.assertIn(c, got, f"{table}.{c} 缺列")

    def test_locator_unique_and_without_rowid(self) -> None:
        conn = self._conn()
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='locators'"
        ).fetchone()[0]
        self.assertIn("UNIQUE (kind, subject, locale, premium)", sql)
        rows = [(1, "portrait", "C1", "", "", "r", "g", "b", "", 0, "ok", "{}"),
                (2, "portrait", "C2", "", "", "r2", "g2", "b", "", 0, "ok", "{}")]
        conn.executemany(
            "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,bundle,"
            "cab,path_id,status,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            rows)
        # 同 (kind, subject, locale, premium) 即撞 UNIQUE（不同 id 不豁免）
        dup = (3, "portrait", "C2", "", "", "r3", "g3", "b", "", 0, "ok", "{}")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
                "bundle,cab,path_id,status,source_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", dup)
        # 键面表 WITHOUT ROWID（v4「必须保留」条款的物理形态）
        for table in ("cards", "plans", "items", "blobs"):
            tsql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,)).fetchone()[0]
            self.assertIn("WITHOUT ROWID", tsql, table)


class CanonicalJsonTests(_TmpCase):
    """cjson 稳定性 + sha256_hex。"""

    def test_cjson_key_order_insensitive_and_compact(self) -> None:
        a = S.cjson({"b": 1, "a": {"y": [1, 2], "x": None}})
        b = S.cjson({"a": {"x": None, "y": [1, 2]}, "b": 1})
        self.assertEqual(a, b)
        self.assertEqual(a, '{"a":{"x":null,"y":[1,2]},"b":1}')   # 紧凑分隔符
        self.assertNotEqual(S.cjson({"a": 1}), S.cjson({"a": 2}))

    def test_sha256_hex_known_vector(self) -> None:
        self.assertEqual(S.sha256_hex(b"abc"),
                         hashlib.sha256(b"abc").hexdigest())
        self.assertEqual(len(S.sha256_hex(b"")), 64)


class KeyDerivationTests(_TmpCase):
    """键派生单源：内容维度缺一即换键（必须保留 #6 的键面形态）。"""

    CI = {"carddef": "cd", "portrait": "px"}

    def test_item_key_dimensions(self) -> None:
        base = S.item_key(card_id="C1", kind="portrait", locale="zhcn",
                          premium="", content_inputs=self.CI)
        self.assertEqual(len(base), 64)
        self.assertEqual(base, S.item_key(card_id="C1", kind="portrait",
                                          locale="zhcn", premium="",
                                          content_inputs=dict(self.CI)))
        for overrides in (
                {"card_id": "C2"}, {"kind": "portrait_golden"},
                {"locale": "enus"}, {"premium": "gold"},
                {"content_inputs": {"carddef": "cd", "portrait": "px2"}}):
            with self.subTest(**overrides):
                args = {"card_id": "C1", "kind": "portrait", "locale": "zhcn",
                        "premium": "", "content_inputs": self.CI}
                args.update(overrides)
                self.assertNotEqual(base, S.item_key(**args))

    def test_plan_key_dimensions(self) -> None:
        base = S.plan_key(card_id="C1", locale="zhcn", card_data_sha="ds1")
        self.assertEqual(base, S.plan_key(card_id="C1", locale="zhcn",
                                          card_data_sha="ds1"))
        self.assertNotEqual(base, S.plan_key(card_id="C1", locale="zhcn",
                                             card_data_sha="ds1", options={"a": 1}))
        self.assertNotEqual(base, S.plan_key(card_id="C1", locale="zhcn",
                                             card_data_sha="ds2"))
        self.assertNotEqual(base, S.plan_key(card_id="C1", locale="enus",
                                             card_data_sha="ds1"))
        self.assertNotEqual(base, S.plan_key(card_id="C2", locale="zhcn",
                                             card_data_sha="ds1"))
        # options=None 与 {} 同键（options or {} 归一）
        self.assertEqual(S.plan_key(card_id="C1", locale="zhcn", card_data_sha="d"),
                         S.plan_key(card_id="C1", locale="zhcn", card_data_sha="d",
                                    options={}))

    def test_blob_key_domains_and_inputs(self) -> None:
        p1 = S.blob_key(portrait_content_sha="px1")
        self.assertEqual(p1, S.blob_key(portrait_content_sha="px1"))
        self.assertNotEqual(p1, S.blob_key(portrait_content_sha="px2"))
        # 泛化形：域词进键——同内容跨域不共行（文件层仍按 payload 去重）
        g1 = S.blob_key_generic(domain="portrait", content_sha="px1", codec="png")
        self.assertEqual(p1, g1)                    # portrait 域专用形=泛化形同参
        self.assertNotEqual(g1, S.blob_key_generic(domain="text/ttf",
                                                   content_sha="px1",
                                                   codec="png"))
        self.assertNotEqual(g1, S.blob_key_generic(domain="portrait",
                                                   content_sha="px1",
                                                   codec="json"))
        self.assertNotEqual(g1, S.blob_key_generic(domain="portrait",
                                                   content_sha="px1", codec="png",
                                                   codec_version=2))

    def test_domain_key_functions(self) -> None:
        kit1 = S.kit_item_key(frame="ally", locale="zhcn",
                              content_inputs={"guid": "g", "kit": "k"})
        self.assertNotEqual(kit1, S.kit_item_key(frame="ally", locale="zhcn",
                                                 content_inputs={"guid": "g",
                                                                 "kit": "k2"}))
        self.assertNotEqual(kit1, S.kit_item_key(frame="enemy", locale="zhcn",
                                                 content_inputs={"guid": "g",
                                                                 "kit": "k"}))
        gem1 = S.gem_item_key(gem="mana_albedo", locale="zhcn",
                              content_inputs={"kit": "k", "pixel": "p"})
        self.assertNotEqual(gem1, S.gem_item_key(gem="clouds", locale="zhcn",
                                                 content_inputs={"kit": "k",
                                                                 "pixel": "p"}))
        wm1 = S.watermark_item_key(card_id="C1", locale="zhcn",
                                   content_inputs={"carddef": "c", "ref": "r",
                                                   "watermark": "w"})
        self.assertNotEqual(wm1, S.watermark_item_key(card_id="C2", locale="zhcn",
                                                      content_inputs={"carddef": "c",
                                                                      "ref": "r",
                                                                      "watermark": "w"}))
        fd1 = S.fontdefs_item_key(locale="zhcn", content_inputs={"fontdefs": "f"})
        self.assertNotEqual(fd1, S.fontdefs_item_key(locale="enus",
                                                     content_inputs={"fontdefs": "f"}))
        ft1 = S.font_ttf_item_key(font="ZhFont", locale="zhcn",
                                  content_inputs={"ttf": "t"})
        self.assertNotEqual(ft1, S.font_ttf_item_key(font="EnFont", locale="zhcn",
                                                     content_inputs={"ttf": "t"}))
        cp1 = S.color_probe_item_key(locale="zhcn",
                                     content_inputs={"probe": "p", "ref": "r"})
        self.assertNotEqual(cp1, S.color_probe_item_key(
            locale="enus", content_inputs={"probe": "p", "ref": "r"}))
        self.assertNotEqual(cp1, S.color_probe_item_key(
            locale="zhcn", content_inputs={"probe": "p2", "ref": "r"}))
        ca1 = S.color_atlas_item_key(family="minionCardTextures", ct=7,
                                     locale="zhcn",
                                     content_inputs={"ref": "r", "guid": "g",
                                                     "pixel": "px"})
        self.assertNotEqual(ca1, S.color_atlas_item_key(
            family="minionCardTextures", ct=8, locale="zhcn",
            content_inputs={"ref": "r", "guid": "g", "pixel": "px"}))
        self.assertNotEqual(ca1, S.color_atlas_item_key(
            family="spellCardTextures", ct=7, locale="zhcn",
            content_inputs={"ref": "r", "guid": "g", "pixel": "px"}))
        self.assertNotEqual(ca1, S.color_atlas_item_key(
            family="minionCardTextures", ct=7, locale="zhcn",
            content_inputs={"ref": "r", "guid": "g", "pixel": "px2"}))
        # 跨域键互异（kit/gems/watermark/text/color 同 content 也不共键）
        self.assertEqual(len({kit1, gem1, wm1, fd1, ft1, cp1, ca1}), 7)

    def test_schema_constants(self) -> None:
        self.assertEqual(S.SCHEMA_VERSION, "1")
        self.assertEqual(S.PLAN_VERSION, 5)   # A6：kit races/mesh_refs 换键 + supplement 域
        self.assertEqual(S.CODEC, "png")
        self.assertEqual(S.CODEC_VERSION, 1)
        self.assertEqual(HEALTH_STAMP_VERSION, 1)
        self.assertEqual(S.DOMAIN, "art")
        self.assertEqual(S.ITEM_PORTRAIT, "portrait")
        self.assertEqual((S.DOMAIN_FRAMES, S.ITEM_KIT), ("frames", "kit"))
        self.assertEqual(S.ITEM_KIT_LIGHT, "kit_light")   # A6 域词面
        self.assertEqual(S.SUPP_CODEC, "supp")
        self.assertEqual(S.SUPP_CODEC_VERSION, 1)
        self.assertEqual(S.KIT_RACE_FRAMES, ("ally", "ally_premium", "trinket"))
        self.assertEqual(S.DOMAIN_GEMS, "gems")
        self.assertEqual((S.DOMAIN_WATERMARK, S.ITEM_WATERMARK),
                         ("watermark", "watermark"))
        self.assertEqual((S.DOMAIN_TEXT, S.ITEM_FONTDEFS, S.ITEM_FONT_TTF),
                         ("text", "fontdefs", "font_ttf"))
        self.assertEqual((S.DOMAIN_COLOR, S.ITEM_COLOR_PROBE, S.ITEM_COLOR_ATLAS),
                         ("color", "probe", "atlas"))   # A4 域词面
        self.assertEqual(S.ITEM_FONT_ASSET_PARAMS, "font_asset_params")


# ---------------------------------------------------------------------------
# 五态判定（diff 的 cheap 判定=纯 DB 函数；tmp 造行直测）
# ---------------------------------------------------------------------------

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


def _write_gen(layout: SupplyLayout, gid: str, *,
               cards: list[tuple[str, str]],
               bundles: dict[str, str],
               catalog: list[str],
               items: list[dict]) -> Path:
    """最小代库行集（diff 判定面所需子集：meta/cards/bundles/asset_catalog/items）。"""
    db = layout.gen_db(gid)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = S.connect(db)
    try:
        S.init_schema(conn)
        conn.execute("INSERT INTO meta(key,value) VALUES('game_id',?)", (gid,))
        conn.execute("INSERT INTO meta(key,value) VALUES('locale',?)", ("zhcn",))
        conn.executemany(
            "INSERT INTO cards(card_id,dbf_id,carddef_ref,carddef_guid,"
            "carddef_bundle,carddef_cab,carddef_path_id,data_sha) "
            "VALUES(?,NULL,'','', '', '',0,?)", cards)
        conn.executemany(
            "INSERT INTO bundles(name,size,mtime_ns,sha256) VALUES(?,0,0,?)",
            sorted(bundles.items()))
        conn.executemany("INSERT INTO asset_catalog(guid,bundle) VALUES(?,?)",
                         [(g, "") for g in catalog])
        for it in items:
            conn.execute(
                "INSERT INTO items(item_key,domain,item,params_json,codec,"
                "codec_version,manifest_json,status,source_kind,source_json,"
                "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (it["item_key"], "art", "portrait",
                 S.cjson({"card_id": it["card_id"], "kind": it["kind"]}),
                 it.get("codec", "png"), it.get("codec_version", 1),
                 S.cjson({"card_id": it["card_id"], "kind": it["kind"],
                          "locale": ""}),
                 "ok", "asset",
                 S.cjson([{"bundle": it["bundle"], "guid": it["guid"],
                           "bundle_sha256": it.get("bundle_sha256", "")}]),
                 S.cjson({"carddef": "cd", "portrait": it["portrait"]}), 0))
        conn.commit()
    finally:
        conn.close()
    return db


def _item(card_id: str, *, bundle: str, guid: str, portrait: str = SHA_A,
          kind: str = "portrait", bundle_sha256: str = "", codec: str = "png",
          codec_version: int = 1) -> dict:
    return {"item_key": f"ik-{card_id}-{kind}", "card_id": card_id, "kind": kind,
            "bundle": bundle, "guid": guid, "portrait": portrait,
            "bundle_sha256": bundle_sha256, "codec": codec,
            "codec_version": codec_version}


class DiffFiveStateTests(_TmpCase):
    """diff() cheap 判定五态 + bundle 三态（纯 DB；from/to 显式点名）。"""

    def setUp(self) -> None:
        super().setUp()
        self.lay = SupplyLayout(self.root)
        # from 代：c1 reused / c2 内容变 / c3 codec 变 / c4 包 sha 变（revalidate）
        #         / c5 guid 消失（missing）/ c6 卡消失（orphan）
        self.lay.gen_db("gf").parent.mkdir(parents=True, exist_ok=True)
        _write_gen(
            self.lay, "gf",
            cards=[("c1", "d1"), ("c2", "d2"), ("c3", "d3"), ("c4", "d4"),
                   ("c5", "d5"), ("c6", "d6")],
            bundles={"b1": SHA_A, "b3": SHA_C, "b4": SHA_E, "b5": ""},
            catalog=["g1", "g2", "g3", "g4", "g5", "g6"],
            items=[
                _item("c1", bundle="b1", guid="g1", bundle_sha256=SHA_A),
                _item("c2", bundle="b1", guid="g2", portrait=SHA_B,
                      bundle_sha256=SHA_A),
                _item("c3", bundle="b1", guid="g3", bundle_sha256=SHA_A),
                _item("c4", bundle="b3", guid="g4", bundle_sha256=SHA_C),
                _item("c5", bundle="b1", guid="g5", bundle_sha256=SHA_A),
                _item("c6", bundle="b1", guid="g6", bundle_sha256=SHA_A),
            ])
        # to 代：c2 内容变、c3 codec 变、c4/c5 删 item、c6 删卡；b3 sha 变、b4 消失；
        # g5 的 guid 从 catalog 删（c5 的 missing 判据）
        _write_gen(
            self.lay, "gt",
            cards=[("c1", "d1"), ("c2", "d2"), ("c3", "d3"), ("c4", "d4"),
                   ("c5", "d5")],
            bundles={"b1": SHA_A, "b3": SHA_D, "b5": ""},
            catalog=["g1", "g2", "g3", "g4"],
            items=[
                _item("c1", bundle="b1", guid="g1", bundle_sha256=SHA_A),
                _item("c2", bundle="b1", guid="g2", portrait=SHA_D,
                      bundle_sha256=SHA_A),
                _item("c3", bundle="b1", guid="g3", codec="webp",
                      bundle_sha256=SHA_A),
            ])

    def test_five_state_counts_and_reasons(self) -> None:
        from eidolon.core.supply_index.diff import diff

        rep = diff(self.root, from_gen="gen-gf", to_gen="gen-gt")
        self.assertEqual(rep["from"], "gen-gf")
        self.assertEqual(rep["to"], "gen-gt")
        self.assertEqual(rep["counts"], {"reused": 1, "revalidate": 1,
                                         "stale": 2, "missing": 1, "orphan": 1})
        for state in FIVE_STATES:
            self.assertIn(state, rep["samples"])
        # 逐槽位 reason（migration_report 落 to 代）
        tconn = S.connect(self.lay.gen_db("gt"), readonly=True)
        try:
            rows = {r["key"]: (r["status"], r["reason"]) for r in tconn.execute(
                "SELECT key,status,reason FROM migration_report "
                "WHERE kind='item' AND game_id='gf'")}
        finally:
            tconn.close()
        self.assertEqual(rows["c1|portrait|"], ("reused", "content-sha-equal"))
        self.assertEqual(rows["c2|portrait|"], ("stale", "object-content-changed"))
        self.assertEqual(rows["c3|portrait|"], ("stale", "codec-changed"))
        self.assertEqual(rows["c4|portrait|"], ("revalidate",
                                                "source-bundle-sha-changed"))
        self.assertEqual(rows["c5|portrait|"], ("missing",
                                                "source-bundle-or-guid-gone"))
        self.assertEqual(rows["c6|portrait|"], ("orphan", "card-absent-in-to-gen"))

    def test_bundle_three_states(self) -> None:
        from eidolon.core.supply_index.diff import diff

        diff(self.root, from_gen="gen-gf", to_gen="gen-gt")
        tconn = S.connect(self.lay.gen_db("gt"), readonly=True)
        try:
            rows = {r["key"]: (r["status"], r["reason"]) for r in tconn.execute(
                "SELECT key,status,reason FROM migration_report "
                "WHERE kind='bundle' AND game_id='gf'")}
        finally:
            tconn.close()
        self.assertEqual(rows["b1"], ("reused", "sha-equal"))
        self.assertEqual(rows["b3"], ("revalidate", "sha-changed"))
        self.assertEqual(rows["b4"], ("missing", "bundle-absent-in-to-gen"))
        self.assertEqual(rows["b5"], ("revalidate", "sha-unrecorded"))


class DiffAllDomainsTests(_TmpCase):
    """五态判定覆盖全供给域（Phase 5 审计 P2：kit/gems/watermark/text 不再范围外）。

    卡不变域（frames/gems/text）无 orphan；gems 的 source 无 bundle 地址时
    revalidate（不冒充 missing）；watermark 是 per-card 域（卡删=orphan）。"""

    def _add_item(self, conn, *, item_key: str, domain: str, item: str,
                  params: dict, content: dict, source: list[dict],
                  locale: str = "zhcn", codec: str = "png") -> None:
        conn.execute(
            "INSERT INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (item_key, domain, item, S.cjson(params), codec, 1,
             S.cjson({"locale": locale, **params}), "ok", "asset",
             S.cjson(source), S.cjson(content), 0))

    def _gen(self, gid: str, *, cards: list[tuple[str, str]],
             bundles: dict[str, str], catalog: list[str],
             art: list[dict], domains: list[dict]) -> None:
        db = _write_gen(self.lay if hasattr(self, "lay") else SupplyLayout(self.root),
                        gid, cards=cards, bundles=bundles, catalog=catalog,
                        items=art)
        conn = S.connect(db)
        try:
            for d in domains:
                self._add_item(conn, **d)
            conn.commit()
        finally:
            conn.close()

    def setUp(self) -> None:
        super().setUp()
        self.lay = SupplyLayout(self.root)
        art = lambda cid, sha: _item(cid, bundle="b1", guid="g1", portrait=sha)  # noqa: E731
        self._gen(
            "gf",
            cards=[("c1", "d1"), ("c2", "d2")], bundles={"b1": SHA_A},
            catalog=["g1"],
            art=[art("c1", SHA_A), art("c2", SHA_A)],
            domains=[
                {"item_key": "wm1", "domain": S.DOMAIN_WATERMARK,
                 "item": S.ITEM_WATERMARK, "params": {"card_id": "c1"},
                 "content": {"watermark": SHA_A},
                 "source": [{"bundle": "b1", "guid": "g1"}]},
                {"item_key": "kit-ally", "domain": S.DOMAIN_FRAMES,
                 "item": S.ITEM_KIT, "params": {"frame": "ally"},
                 "content": {"kit": SHA_A},
                 "source": [{"bundle": "b1", "guid": "g1"}], "codec": "kit"},
                {"item_key": "kit-violet", "domain": S.DOMAIN_FRAMES,
                 "item": S.ITEM_KIT, "params": {"frame": "violet"},
                 "content": {"kit": SHA_A},
                 "source": [{"bundle": "gone", "guid": "g1"}], "codec": "kit"},
                {"item_key": "gem-clouds", "domain": S.DOMAIN_GEMS,
                 "item": "clouds", "params": {},
                 "content": {"pixel": SHA_A, "kit": SHA_A},
                 "source": [{"bundle": None, "guid": None}]},
                {"item_key": "gem-fire", "domain": S.DOMAIN_GEMS,
                 "item": "fire", "params": {},
                 "content": {"pixel": SHA_B, "kit": SHA_A},
                 "source": [{"bundle": None, "guid": None}]},
                {"item_key": "text-fd", "domain": S.DOMAIN_TEXT,
                 "item": S.ITEM_FONTDEFS, "params": {},
                 "content": {"fontdefs": SHA_A},
                 "source": [{"bundle": "b1", "guid": "g1"}], "codec": "json"},
                {"item_key": "text-belwe", "domain": S.DOMAIN_TEXT,
                 "item": S.ITEM_FONT_TTF, "params": {"font": "Belwe"},
                 "content": {"ttf": SHA_A},
                 "source": [{"bundle": "b1", "guid": "g1"}], "codec": "ttf"},
            ],
        )
        self._gen(
            "gt",
            cards=[("c1", "d1")], bundles={"b1": SHA_A}, catalog=["g1"],
            art=[art("c1", SHA_A)],
            domains=[
                {"item_key": "wm1b", "domain": S.DOMAIN_WATERMARK,
                 "item": S.ITEM_WATERMARK, "params": {"card_id": "c1"},
                 "content": {"watermark": SHA_A},
                 "source": [{"bundle": "b1", "guid": "g1"}]},
                {"item_key": "kit-ally-b", "domain": S.DOMAIN_FRAMES,
                 "item": S.ITEM_KIT, "params": {"frame": "ally"},
                 "content": {"kit": SHA_A},
                 "source": [{"bundle": "b1", "guid": "g1"}], "codec": "kit"},
                {"item_key": "gem-clouds-b", "domain": S.DOMAIN_GEMS,
                 "item": "clouds", "params": {},
                 "content": {"pixel": SHA_B, "kit": SHA_A},
                 "source": [{"bundle": None, "guid": None}]},
                {"item_key": "text-fd-b", "domain": S.DOMAIN_TEXT,
                 "item": S.ITEM_FONTDEFS, "params": {},
                 "content": {"fontdefs": SHA_B},
                 "source": [{"bundle": "b1", "guid": "g1"}], "codec": "json"},
                {"item_key": "text-belwe-b", "domain": S.DOMAIN_TEXT,
                 "item": S.ITEM_FONT_TTF, "params": {"font": "Belwe"},
                 "content": {"ttf": SHA_A},
                 "source": [{"bundle": "b1", "guid": "g1"}], "codec": "ttf"},
            ],
        )

    def test_all_domain_item_states_and_reasons(self) -> None:
        from eidolon.core.supply_index.diff import diff

        diff(self.root, from_gen="gen-gf", to_gen="gen-gt")
        tconn = S.connect(self.lay.gen_db("gt"), readonly=True)
        try:
            rows = {r["key"]: (r["status"], r["reason"]) for r in tconn.execute(
                "SELECT key,status,reason FROM migration_report "
                "WHERE kind='item' AND game_id='gf'")}
        finally:
            tconn.close()
        # art + watermark + kit + text：内容相等=reused
        self.assertEqual(rows["c1|portrait|"], ("reused", "content-sha-equal"))
        self.assertEqual(rows["c1|watermark|zhcn"],
                         ("reused", "content-sha-equal"))
        self.assertEqual(rows["frame:ally"], ("reused", "content-sha-equal"))
        self.assertEqual(rows["text:font_ttf:Belwe"],
                         ("reused", "content-sha-equal"))
        # 内容变=stale（gems/text 域同判）
        self.assertEqual(rows["gem:clouds"], ("stale", "object-content-changed"))
        self.assertEqual(rows["text:fontdefs:fontdefs"],
                         ("stale", "object-content-changed"))
        # 来源包消失=missing（卡不变域照判，非 orphan）
        self.assertEqual(rows["frame:violet"],
                         ("missing", "source-bundle-or-guid-gone"))
        # gems 无 bundle 地址：保守 revalidate（不冒充 missing）
        self.assertEqual(rows["gem:fire"],
                         ("revalidate", "item-absent-in-to-gen-no-source"))
        # 卡删：art/watermark 均 orphan；卡不变域无 orphan
        self.assertEqual(rows["c2|portrait|"], ("orphan", "card-absent-in-to-gen"))
        self.assertNotIn("frame:ally", [k for k, v in rows.items()
                                        if v[0] == "orphan"])

    def test_exercise_selfcheck_pins_injected_counts(self) -> None:
        from eidolon.core.supply_index.diff import _exercise_mismatches

        injected = {"stale": 2, "revalidate": 3, "missing": 2, "orphan": 1}
        exact_ok = {"checked": 3, "reused": 2, "stale": 1}
        self.assertEqual(_exercise_mismatches(
            injected, dict(injected), exact_ok, {"hit": 3}), [])
        bad = _exercise_mismatches(
            injected, {**injected, "stale": 1},
            {"checked": 2, "reused": 1, "stale": 0}, {"hit": 1})
        joined = "; ".join(bad)
        self.assertIn("stale: injected=2 diff=1", joined)
        self.assertIn("exact.checked=2", joined)
        self.assertIn("transferred=1", joined)
        self.assertIn("warm 闭环 hit=1", joined)
        # 转移账不足也要被点名
        bad2 = _exercise_mismatches(injected, dict(injected),
                                    {"checked": 3, "reused": 1, "stale": 1},
                                    {"hit": 3})
        self.assertTrue(any("transferred=2" in m for m in bad2), bad2)
        # warm 复验本身 error=不判红（失败已由 exact/selfcheck 面记录）
        self.assertEqual(_exercise_mismatches(
            injected, dict(injected), exact_ok, {"error": "boom"}), [])


class VerifyAllItemsModeTests(_TmpCase):
    """verify --all（P2 审计）：全量档取 art 两种 kind 全集；默认档保持抽样。"""

    def test_sample_items_all_returns_whole_art_set(self) -> None:
        from eidolon.core.supply_index.verify import _sample_items

        lay = SupplyLayout(self.root)
        items = [
            _item("c1", bundle="b1", guid="g1"),
            _item("c2", bundle="b1", guid="g2"),
            _item("c3", bundle="b1", guid="g3", kind="portrait_golden"),
        ]
        db = _write_gen(lay, "g1", cards=[("c1", "d1"), ("c2", "d2"),
                                           ("c3", "d3")],
                        bundles={"b1": SHA_A}, catalog=["g1", "g2", "g3"],
                        items=items)
        conn = S.connect(db, readonly=True)
        try:
            all_rows = _sample_items(conn, 1, 1, 42, all_items=True)
            self.assertEqual(len(all_rows), 3)
            self.assertEqual(
                {r["params"]["kind"] for r in all_rows},
                {"portrait", "portrait_golden"})
            sampled = _sample_items(conn, 1, 1, 42)
            self.assertEqual(len(sampled), 2)      # 每种 kind 各 1（默认档）
        finally:
            conn.close()


class PlanItemBlobChainTests(_TmpCase):
    """P2 审计：items 行在而 item_blobs 链断 → expected_vs_built/归因均判缺口。"""

    def test_expected_vs_built_counts_missing_blob_row(self) -> None:
        lay = SupplyLayout(self.root)
        db = _write_gen(lay, "g1", cards=[("cA", "dsA")], bundles={},
                        catalog=[], items=[])
        conn = S.connect(db)
        try:
            pk = S.plan_key(card_id="cA", locale="zhcn", card_data_sha="dsA")
            conn.execute(
                "INSERT INTO plans(plan_key,card_id,options_json,status,"
                "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,0)",
                (pk, "cA", "{}", "complete", S.PLAN_VERSION, "dsA"))
            self._add_item_without_blobs(conn, "ik-cA", pk, "cA")
            conn.commit()
            comp = S.expected_vs_built(conn)
            self.assertEqual(comp["missing_total"], 1)
            self.assertEqual(comp["missing_sample"][0]["role"], "portrait")
            rec = S.recompute_plan_status(conn, [pk])
            self.assertEqual(rec, {"complete": 0, "partial": 1})
            self.assertEqual(conn.execute(
                "SELECT status FROM plans WHERE plan_key=?", (pk,)).fetchone()[0],
                "partial")
        finally:
            conn.close()

    def _add_item_without_blobs(self, conn, ik: str, pk: str, cid: str) -> None:
        conn.execute(
            "INSERT INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
            (ik, "art", "portrait", S.cjson({"card_id": cid, "kind": "portrait"}),
             "png", 1, S.cjson({"locale": "zhcn"}), "ok", "asset", "[]",
             S.cjson({"portrait": SHA_A})))
        conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                     "VALUES(?,?,?)", (pk, ik, "portrait"))


class ResolveGensTests(_TmpCase):
    """resolve_gens 默认面：to=current；from=唯一其它代自动。"""

    def test_default_resolution_with_single_other_gen(self) -> None:
        from eidolon.core.supply_index.diff import resolve_gens

        lay = SupplyLayout(self.root)
        lay.gen_db("g1").parent.mkdir(parents=True, exist_ok=True)
        _write_gen(lay, "g1", cards=[], bundles={}, catalog=[], items=[])
        _write_gen(lay, "g2", cards=[], bundles={}, catalog=[], items=[])
        lay.write_current({"game_id": "g2", "generation": "gen-g2",
                           "locale": "zhcn"})
        self.assertEqual(resolve_gens(lay, None, None), ("gen-g1", "gen-g2"))

    def test_explicit_names_pass_through(self) -> None:
        from eidolon.core.supply_index.diff import resolve_gens

        lay = SupplyLayout(self.root)
        self.assertEqual(resolve_gens(lay, "gen-a", "gen-b"), ("gen-a", "gen-b"))

    def test_no_current_requires_explicit_to(self) -> None:
        from eidolon.core.supply_index.diff import resolve_gens

        with self.assertRaises(FileNotFoundError):
            resolve_gens(SupplyLayout(self.root), None, None)


class ApplyExactTransitionsTests(_TmpCase):
    """revalidate --exact 转移记账核心（纯函数：got/got_err 注入，零游戏访问）。"""

    def setUp(self) -> None:
        super().setUp()
        self.lay = SupplyLayout(self.root)
        # from 代：item+blob+plan_items 齐备（carryover 复制源）
        _write_gen(self.lay, "gf",
                   cards=[("cA", "dsA")], bundles={"b1": SHA_A},
                   catalog=["gA"],
                   items=[_item("cA", bundle="b1", guid="gA", portrait=SHA_A,
                                bundle_sha256=SHA_A)])
        fconn = S.connect(self.lay.gen_db("gf"))
        try:
            ik = "ik-cA-portrait"
            bk = S.blob_key(portrait_content_sha=SHA_A)
            pk = S.plan_key(card_id="cA", locale="", card_data_sha="dsA")
            fconn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                          "VALUES(?,?,?)", (ik, bk, "portrait"))
            fconn.execute(
                "INSERT INTO blobs(blob_key,payload_sha256,size,codec,"
                "codec_version,last_used,created_at) VALUES(?,?,?,?,?,?,?)",
                (bk, SHA_B, 10, "png", 1, 0, 0))
            fconn.execute("INSERT INTO plans(plan_key,card_id,options_json,"
                          "status,plan_version,card_data_sha,created_at) "
                          "VALUES(?,?,?,?,?,?,?)",
                          (pk, "cA", "{}", "partial", S.PLAN_VERSION, "dsA", 0))
            fconn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                          "VALUES(?,?,?)", (pk, ik, "portrait"))
            fconn.commit()
        finally:
            fconn.close()
        # to 代：同卡、无 item；migration_report 预置 revalidate 行
        _write_gen(self.lay, "gt", cards=[("cA", "dsA")], bundles={"b1": SHA_A},
                   catalog=["gA"], items=[])
        self.wconn = S.connect(self.lay.gen_db("gt"))
        self.wconn.execute(
            "INSERT INTO migration_report(game_id,kind,key,status,reason,"
            "detail_json) VALUES('gf','item','cA|portrait|','revalidate','x',NULL)")
        self.wconn.commit()
        self.fconn = S.connect(self.lay.gen_db("gf"), readonly=True)
        self.addCleanup(self.fconn.close)
        self.addCleanup(self.wconn.close)

    def _target(self) -> dict:
        return {"card_id": "cA", "kind": "portrait", "locale": "",
                "item_key": "ik-cA-portrait", "source": [], "content":
                    {"portrait": SHA_A}}

    def _report_row(self) -> tuple[str, str]:
        r = self.wconn.execute(
            "SELECT status,reason FROM migration_report WHERE kind='item' "
            "AND key='cA|portrait|'").fetchone()
        return r["status"], r["reason"]

    def test_reused_transfers_and_carries_item_into_to_gen(self) -> None:
        from eidolon.core.supply_index.diff import _apply_exact_transitions

        acct = _apply_exact_transitions(self.fconn, self.wconn, [self._target()],
                                        {("cA", "portrait"): SHA_A}, {})
        self.assertEqual(acct["checked"], 1)
        self.assertEqual(acct["reused"], 1)
        self.assertEqual(acct["stale"], 0)
        self.assertEqual(acct["carryover"]["slots"], 1)
        # item 面复制进 to 代（设计 §7.1：reused=直接复制 item 行；blob 复用）
        self.assertEqual(self.wconn.execute(
            "SELECT COUNT(*) FROM items WHERE item_key='ik-cA-portrait'"
        ).fetchone()[0], 1)
        self.assertEqual(self.wconn.execute("SELECT COUNT(*) FROM item_blobs"
                                            ).fetchone()[0], 1)
        self.assertEqual(self.wconn.execute(
            "SELECT COUNT(*) FROM blobs WHERE blob_key=?",
            (S.blob_key(portrait_content_sha=SHA_A),)).fetchone()[0], 1)
        self.assertEqual(self.wconn.execute(
            "SELECT status FROM plans WHERE card_id='cA'").fetchone()[0],
            "complete")
        self.assertEqual(self._report_row(), ("reused", "exact-object-sha-equal"))

    def test_stale_records_redecoded_sha(self) -> None:
        from eidolon.core.supply_index.diff import _apply_exact_transitions

        acct = _apply_exact_transitions(self.fconn, self.wconn, [self._target()],
                                        {("cA", "portrait"): "f" * 64}, {})
        self.assertEqual(acct["reused"], 0)
        self.assertEqual(acct["stale"], 1)
        self.assertEqual(self.wconn.execute(
            "SELECT COUNT(*) FROM items").fetchone()[0], 0)     # 不 carryover
        status, reason = self._report_row()
        self.assertEqual(status, "stale")
        self.assertEqual(reason, "exact-object-sha-differs")
        detail = json.loads(self.wconn.execute(
            "SELECT detail_json FROM migration_report WHERE kind='item' "
            "AND key='cA|portrait|'").fetchone()["detail_json"])
        self.assertEqual(detail["redecoded_sha"], "f" * 64)

    def test_redecode_failure_keeps_revalidate_with_reason(self) -> None:
        from eidolon.core.supply_index.diff import _apply_exact_transitions

        acct = _apply_exact_transitions(self.fconn, self.wconn, [self._target()],
                                        {}, {("cA", "portrait"): "boom"})
        self.assertEqual(acct["unresolved"], 1)
        self.assertEqual(self._report_row(),
                         ("revalidate", "exact-redecode-failed:boom"))

    def test_no_source_keeps_revalidate(self) -> None:
        from eidolon.core.supply_index.diff import _apply_exact_transitions

        acct = _apply_exact_transitions(self.fconn, self.wconn, [self._target()],
                                        {}, {})
        self.assertEqual(acct["unresolved"], 1)
        self.assertEqual(self._report_row(), ("revalidate", "exact-no-source"))


class ImportCleanlinessTests(unittest.TestCase):
    """import 卫生：schema（纯 stdlib）与 warm（numpy/PIL 合法）无 UnityPy 族。"""

    def _banned_in_modules(self, stmt: str) -> list[str]:
        code = ("import sys, json; " + stmt + "; "
                "print(json.dumps(sorted(m for m in sys.modules "
                "if m.split('.')[0] in ('UnityPy', 'clr', 'texture2ddecoder'))))")
        p = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, cwd=str(_REPO), timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def test_schema_import_has_no_unitypy(self) -> None:
        self.assertEqual(
            self._banned_in_modules("import eidolon.core.supply_index.schema"), [])

    def test_warm_import_has_no_unitypy(self) -> None:
        self.assertEqual(
            self._banned_in_modules(
                "import eidolon.core.supply_index.warm"
                "; import eidolon.core.supply_index.diff"
                "; import eidolon.core.supply_index.paths"), [])


# ---------------------------------------------------------------------------
# expected-vs-built 完整性账（Phase 5 返工 R1，P0-1/P0-2 单源纯函数）
# ---------------------------------------------------------------------------

def _completeness_fixture(root: Path) -> Path:
    """完整性账 fixture 代库：
    - cA：locator ok（portrait+portrait_golden）、portrait item 在、golden 缺
      （decode 缺口形态）、kit 哨兵行（期望未建）；
    - cB：locator ok portrait、item 在（全齐）；
    - cC：locator ok portrait、无 item（partial 代 scope 外缺项形态）；
    - cD：cards 表在、零期望（数据缺席）。"""
    db = SupplyLayout(root).gen_db("cg")
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = S.connect(db)
    try:
        S.init_schema(conn)
        conn.executemany("INSERT INTO meta(key,value) VALUES(?,?)",
                         [("game_id", "cg"), ("locale", "zhcn"),
                          ("full_build", "1")])
        for cid in ("cA", "cB", "cC", "cD"):
            conn.execute(
                "INSERT INTO cards(card_id,dbf_id,carddef_ref,carddef_guid,"
                "carddef_bundle,carddef_cab,carddef_path_id,data_sha) "
                "VALUES(?,NULL,'','','','',0,?)", (cid, f"ds-{cid}"))
        locs = [("portrait", "cA", "ok"), ("portrait_golden", "cA", "ok"),
                ("portrait", "cB", "ok"), ("portrait", "cC", "ok")]
        for i, (kind, cid, status) in enumerate(locs, 1):
            conn.execute(
                "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
                "bundle,cab,path_id,status,source_json) VALUES(?,?,?,?"
                ",'','r','g','b1','',0,?,'{}')", (i, kind, cid, "zhcn", status))
        items = []
        for cid in ("cA", "cB"):
            ik = f"ik-{cid}-portrait"
            content = {"carddef": f"cd-{cid}", "portrait": SHA_A}
            conn.execute(
                "INSERT INTO items(item_key,domain,item,params_json,codec,"
                "codec_version,manifest_json,status,source_kind,source_json,"
                "content_inputs_json,created_at) VALUES(?, 'art','portrait',?,"
                "'png',1,'{}','ok','asset','{}',?,0)",
                (ik, S.cjson({"card_id": cid, "kind": "portrait"}),
                 S.cjson(content)))
            items.append((ik, cid))
        # items 行必须有 item_blobs 链才算 built（P2 完整性口径：只查 items 行
        # 会漏「item 在而 blob 链断」的不可装配坏账）
        for ik, _cid in items:
            conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                         "VALUES(?,?,?)", (ik, f"bk-{ik}", "portrait"))
        for ik, cid in items:
            pk = S.plan_key(card_id=cid, locale="zhcn", card_data_sha=f"ds-{cid}")
            conn.execute(
                "INSERT OR IGNORE INTO plans(plan_key,card_id,options_json,"
                "status,plan_version,card_data_sha,created_at) "
                "VALUES(?,?,'{}','complete',?,?,0)",
                (pk, cid, S.PLAN_VERSION, f"ds-{cid}"))
            conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                         "VALUES(?,?,?)", (pk, ik, "portrait"))
        # cA：kit 哨兵行（期望未建形态）
        pk_a = S.plan_key(card_id="cA", locale="zhcn", card_data_sha="ds-cA")
        conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                     "VALUES(?,?,?)", (pk_a, S.expected_item_key("kit:violet"),
                                       "kit"))
        # cC：有 plan 无 plan_items（scope 外缺项形态）
        pk_c = S.plan_key(card_id="cC", locale="zhcn", card_data_sha="ds-cC")
        conn.execute(
            "INSERT INTO plans(plan_key,card_id,options_json,status,"
            "plan_version,card_data_sha,created_at) VALUES(?,?,'{}',"
            "'partial',?,?,0)", (pk_c, "cC", S.PLAN_VERSION, "ds-cC"))
        # cD：零期望 plan
        pk_d = S.plan_key(card_id="cD", locale="zhcn", card_data_sha="ds-cD")
        conn.execute(
            "INSERT INTO plans(plan_key,card_id,options_json,status,"
            "plan_version,card_data_sha,created_at) VALUES(?,?,'{}',"
            "'complete',?,?,0)", (pk_d, "cD", S.PLAN_VERSION, "ds-cD"))
        conn.commit()
    finally:
        conn.close()
    return db


class ExpectedVsBuiltTests(_TmpCase):
    """schema.expected_vs_built / recompute_plan_status（纯 DB 函数）+ cold 尾部
    发布门（_tail_completeness_guard——full/partial 两模式语义；cold import 触
    UnityPy 面，无 UnityPy 环境该两例 skip，纯函数例不触 cold 照跑）。"""

    def setUp(self) -> None:
        super().setUp()
        self.db = _completeness_fixture(self.root)

    def _conn(self):
        conn = S.connect(self.db, readonly=True)
        self.addCleanup(conn.close)
        return conn

    def test_expected_vs_built_full_scope(self) -> None:
        comp = S.expected_vs_built(self._conn())
        # 缺项对：cA×portrait_golden（locator ok 无产物）、cA×kit（哨兵）、
        # cC×portrait（locator ok 无 item）
        self.assertEqual(comp["missing_total"], 3)
        self.assertEqual(comp["missing_in_scope"], 3)
        self.assertEqual(comp["missing_out_scope"], 0)
        pairs = {(m["card_id"], m["role"]) for m in comp["missing_sample"]}
        self.assertIn(("cA", "portrait_golden"), pairs)
        self.assertIn(("cA", "kit"), pairs)
        self.assertIn(("cC", "portrait"), pairs)
        self.assertEqual(comp["expectationless_cards"], 1)   # cD
        by = comp["by_kind"]
        self.assertEqual(by["portrait"]["missing_cards"], 1)   # cC
        self.assertEqual(by["portrait"]["expected_cards"], 3)  # cA/cB/cC
        self.assertEqual(by["portrait_golden"]["missing_cards"], 1)
        self.assertEqual(by["kit"]["missing_roles_total"], 1)

    def test_expected_vs_built_scope_split(self) -> None:
        comp = S.expected_vs_built(self._conn(), scope_cards={"cA"})
        # partial 代 scope={cA}：cA 的两缺项在 scope 内（阻断面），cC 在外（列账）
        self.assertEqual(comp["missing_in_scope"], 2)
        self.assertEqual(comp["missing_out_scope"], 1)

    def test_recompute_plan_status(self) -> None:
        conn = S.connect(self.db)
        try:
            counts = S.recompute_plan_status(conn)
            conn.commit()        # 写面由调用方提交（build 尾部统一 commit 同形）
        finally:
            conn.close()
        self.assertEqual(counts, {"complete": 2, "partial": 2})
        conn = S.connect(self.db, readonly=True)
        try:
            status = {r["card_id"]: r["status"] for r in conn.execute(
                "SELECT card_id, status FROM plans")}
        finally:
            conn.close()
        self.assertEqual(status["cA"], "partial")   # golden+kit 缺
        self.assertEqual(status["cB"], "complete")  # 全齐
        self.assertEqual(status["cC"], "partial")   # portrait 缺
        self.assertEqual(status["cD"], "complete")  # 零期望=complete（数据缺席合法）

    def _set_full(self, v: str) -> None:
        conn = S.connect(self.db)
        try:
            conn.execute("INSERT OR REPLACE INTO meta(key,value) "
                         "VALUES('full_build',?)", (v,))
            conn.commit()
        finally:
            conn.close()

    def test_cold_tail_completeness_gate_full_blocks(self) -> None:
        """P0-2 发布门（小型合成代）：full 代 expected>built → 拒绝发布（响亮）。

        子进程跑（cold import 触 UnityPy——不污染本测试进程 sys.modules，
        test_text_atlas 的进程级 import 卫生断言会抓）。"""
        rc, out, err = self._run_gate_child()
        self.assertEqual(rc, 0, f"gate 子进程失败：\n{err[-800:]}")
        self.assertIn("GATE_FULL_BLOCKS", out)
        self.assertIn("缺预期产物 3 项", out)
        self.assertIn("不发布", out)

    def test_cold_tail_completeness_gate_scope_semantics(self) -> None:
        """partial 代门语义：scope 内缺项阻断；scope 外缺项列账不阻断（子进程）。"""
        rc, out, err = self._run_gate_child()
        self.assertEqual(rc, 0, f"gate 子进程失败：\n{err[-800:]}")
        self.assertIn("GATE_SCOPE_OK", out)

    def _run_gate_child(self) -> tuple[int, str, str]:
        """完整性门子进程：fixture 代库 + cold._tail_completeness_guard 两场景。"""
        code = (
            "import sys, json;"
            f"sys.path.insert(0, {str(_REPO)!r});"
            "import tempfile;"
            "from pathlib import Path;"
            "from tests.core.test_supply_index_schema import _completeness_fixture;"
            "tmp = tempfile.TemporaryDirectory();"
            "db = _completeness_fixture(Path(tmp.name));"
            "from eidolon.core.supply_index import schema as S;"
            "from eidolon.core.supply_index.cold import _tail_completeness_guard;"
            "conn = S.connect(db, readonly=True);"
            "# full 代：expected>built → 响亮拒绝发布\n"
            "try:\n"
            "    _tail_completeness_guard(conn, full=True, scope_cards=None)\n"
            "    raise SystemExit('full 门未阻断（应为红）')\n"
            "except RuntimeError as exc:\n"
            "    assert '缺预期产物 3 项' in str(exc) and '不发布' in str(exc), exc\n"
            "    print('GATE_FULL_BLOCKS ok:', exc)\n"
            "# partial 代：scope 内缺项阻断\n"
            "try:\n"
            "    _tail_completeness_guard(conn, full=False, scope_cards={'cC'})\n"
            "    raise SystemExit('partial scope 门未阻断（应为红）')\n"
            "except RuntimeError:\n"
            "    print('GATE_SCOPE_BLOCK ok')\n"
            "# partial 代：scope 卡全齐——缺项全在 scope 外，列账不阻断\n"
            "comp = _tail_completeness_guard(conn, full=False, scope_cards={'cB'});"
            "assert comp['gate'] == 'partial-scope', comp;"
            "assert comp['blocking_missing'] == 0, comp;"
            "assert comp['missing_out_scope'] == 3, comp;"
            "print('GATE_SCOPE_OK ok')"
        )
        import os

        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        # 不用 -I：UnityPy 装在用户 site（-I 跳过）；子进程代码自洽，无不可信输入
        p = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, cwd=str(_REPO),
                           encoding="utf-8", errors="replace", env=env,
                           timeout=120)
        return p.returncode, p.stdout, p.stderr


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
