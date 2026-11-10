"""core/supply_index mip 面单测（A5；默认 discover 收集；零 UnityPy 顶层、零游戏）。

判据面（任务单 A5 + 单测可钉住的部分）：

  * **链表逐字漂移钉住**：``mip_extract.MIP_CHAINS`` == live
    ``supply.textures._MIP_CHAINS``（逐字符——cold 与 live 必须提取同一对象集，
    color_extract.SWITCHER_REF 同款链面契约）；解码件（decode_level/level_dims/
    level_bytes）与 live 同名函数行为全等（样本矩阵对拍）。
  * **mip_codec**：NPZ 往返无损 uint8、确定性（同输入同字节——payload sha 复现
    面）、chain_content_sha 顺序敏感、meta marker 恒定。
  * **warm 两 API 同形**：``mip_registry()``（name → {lods,filter,bias}，uint8
    数组 + 进程缓存）与 ``portrait_mip(card_id)``（{name,chain,filter,bias}，
    WarmChain 协议=len/getitem/peek/shape0 与 live LazyFloatChain 全等；chain
    源 L0=portrait PNG 派生、registry 源=registry lods 同源）；缺项
    SupplyMissingError / blob 篡改 SupplyBlobCorruptError（fail loud 语义不
    弱化）。
  * **expected-vs-built**：portrait_mip role 挂接=期望；哨兵行 expect::
    portrait_mip → plan.missing 点名 + assemble_card 严格门 raise。
  * **entry seed 注入位**（supply.textures 模块级）：covered ref 判定直供
    （None=已裁决无链 / entry=链面）、UNSET 落 live（默认进程无 ctx=解析异常
    →None 同象）、clear 卸载后不再consulted；CardSeeder.open 安装 / close 卸
    （晚开 seeder.close 不误卸新句柄——fn 身份判据）。

WarmChain/LazyFloatChain 协议对拍与 seed 转换形状需要 live 形状类
（``eidolon.core.supply.textures``）——**运行期惰性 import**（拖 texture2ddecoder/
resolver 面），模块出口 ``tearDownModule`` 清 UnityPy 族（test_route_cabs/
test_supply_index_seed 纪律）。
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from eidolon.core.supply_index import mip_codec as MC
from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.paths import SupplyLayout
from eidolon.core.supply_index.warm import (
    SupplyBlobCorruptError,
    SupplyIndex,
    SupplyMissingError,
    WarmChain,
)

# mip_extract=UnityPy 面（_unity 单点）——**惰性 import**（ChainTableParityTests
# setUpClass；模块级 import 会在 discovery 期污染 sys.modules，render_import_seams
# 判例）。

_REPO = Path(__file__).resolve().parents[2]
LOCALE = "zhcn"
NOW = 1700000000

IDENTITY = {"build": "37.0.2-test", "manifest_stamp": "m-stamp", "platform": "pc",
            "dll_stamp": "d-stamp", "constants_stamp": S.sha256_hex(b"[]")}
GAME_ID = S.sha256_hex(S.cjson(IDENTITY).encode("utf-8"))

_REG_CHAINS = {"FakeReg_A_D": (2, 1, 0.0), "FakeReg_B_D": (3, 2, -0.5)}


def _chain_arrays(name: str, n: int, seed: int) -> dict[str, np.ndarray]:
    return {MC.registry_chain_key(name, i):
            np.full((8 >> i, 8 >> i, 4), seed * 10 + i, dtype=np.uint8)
            for i in range(n)}


class _MipFixture:
    """最小代库手造器（registry 全局项 + portrait/portrait_mip 双卡）。"""

    def __init__(self, root: Path):
        self.layout = SupplyLayout(root)
        self.root = Path(root)
        self.db = self.layout.gen_db(GAME_ID)
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = S.connect(self.db)
        self.conn.execute("PRAGMA journal_mode=DELETE")
        S.init_schema(self.conn)
        self.conn.executemany("INSERT INTO meta(key,value) VALUES(?,?)", [
            ("game_id", GAME_ID), ("locale", LOCALE), ("full_build", "1")])
        self._write_registry()
        self._write_card("C_MIP", source="chain")      # 链源（L0 派生 + 2 存储级）
        self._write_card("C_REG", source="registry")   # 注册表源（FakeReg_B_D）
        self._write_sentinel_card("C_GAP_MIP")
        self._write_text()
        self.conn.commit()

    # ---- text 全域段（assemble_card 附带；最小 fontdefs+ttf） ----

    def _write_text(self) -> None:
        fontdefs = {"ZhFont": {"m_Name": "ZhFont", "m_FontDefName": "ZhFont",
                               "m_FontName": "Zhonomy", "base_guid": "guid-zh"}}
        data = json.dumps(fontdefs, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
        payload_sha = S.sha256_hex(data)
        content_sha = S.sha256_hex(data)
        tik = S.fontdefs_item_key(locale=LOCALE,
                                  content_inputs={"fontdefs": content_sha})
        tbk = S.blob_key_generic(domain="text", content_sha=payload_sha,
                                 codec="json")
        self._blob(payload_sha, data, ".json", blob_key=tbk, codec="json")
        self._item(tik, S.DOMAIN_TEXT, S.ITEM_FONTDEFS, S.cjson({}), "json",
                   S.cjson({"payload_sha256": payload_sha}),
                   {"fontdefs": content_sha})
        self.conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                          "VALUES(?,?,?)", (tik, tbk, "fontdefs"))

    def publish_current(self) -> None:
        self.conn.close()
        self.layout.write_current({
            "game_id": GAME_ID, "generation": f"gen-{GAME_ID}",
            "locale": LOCALE, "full_build": True, "updated_at": NOW,
            "identity": IDENTITY})

    # ---- registry 全局项（textures 域） ----

    def _write_registry(self) -> None:
        arrays: dict[str, np.ndarray] = {}
        chains = {}
        for seed_i, (name, (n, filt, bias)) in enumerate(sorted(_REG_CHAINS.items())):
            a = _chain_arrays(name, n, seed_i + 1)
            arrays.update(a)
            chains[name] = {"filter": filt, "bias": bias, "mip_count": n,
                            "bundle": "b1", "path_id": 700 + seed_i}
        payload = MC.encode_chain_npz(arrays)
        payload_sha = S.sha256_hex(payload)
        content = {"chains": MC.chain_content_sha(
                       [arrays[k] for k in sorted(arrays)]),
                   "table": S.sha256_hex(S.cjson(
                       [("FakeReg_A_D", "b1", 700),
                        ("FakeReg_B_D", "b1", 701)]).encode("utf-8"))}
        self.reg_content_inputs = content
        rik = S.mip_registry_item_key(locale=LOCALE, content_inputs=content)
        manifest = {"item": S.ITEM_MIP_REGISTRY, "locale": LOCALE,
                    "chains": chains, "chain_count": len(chains),
                    "array_count": len(arrays),
                    "payload_sha256": payload_sha, "payload_size": len(payload)}
        rbk = S.blob_key_generic(domain="mip", content_sha=payload_sha,
                                 codec="npz")
        self._blob(payload_sha, payload, ".npz", blob_key=rbk, codec="npz")
        self._item(rik, S.DOMAIN_TEXTURES, S.ITEM_MIP_REGISTRY, S.cjson({}),
                   "npz", S.cjson(manifest), content, codec_version=1)
        self.conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                          "VALUES(?,?,?)", (rik, rbk, "registry"))
        self.reg_key = rik
        self.reg_payload_sha = payload_sha

    # ---- per-card portrait + portrait_mip ----

    def _write_card(self, cid: str, *, source: str) -> None:
        conn = self.conn
        conn.execute(
            "INSERT INTO cards(card_id,dbf_id,carddef_ref,carddef_guid,"
            "carddef_bundle,carddef_cab,carddef_path_id,data_sha) "
            "VALUES(?,?,'','','','',0,?)", (cid, 4242, f"ds-{cid}"))
        pk = S.plan_key(card_id=cid, locale=LOCALE, card_data_sha=f"ds-{cid}")
        img = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
        png = _encode_png(img)
        pixel_sha = S.sha256_hex(img.tobytes())
        payload_sha = S.sha256_hex(png)
        content = {"carddef": f"cd-{cid}", "portrait": pixel_sha}
        ik = S.item_key(card_id=cid, kind="portrait", locale=LOCALE, premium="",
                        content_inputs=content)
        manifest = {"card_id": cid, "kind": "portrait", "locale": LOCALE,
                    "ref": f"ref-{cid}", "guid": f"guid-{cid}", "bundle": "b1",
                    "cab": "", "path_id": 11, "width": 8, "height": 8,
                    "mode": "RGBA", "pixel_sha256": pixel_sha,
                    "payload_sha256": payload_sha, "payload_size": len(png)}
        bk = S.blob_key(portrait_content_sha=pixel_sha)
        self._blob(payload_sha, png, ".png", blob_key=bk)
        self._item(ik, S.DOMAIN, S.ITEM_PORTRAIT,
                   S.cjson({"card_id": cid, "kind": "portrait"}), "png",
                   S.cjson(manifest), content)
        conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                     "VALUES(?,?,?)", (ik, bk, "portrait"))
        conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                     "VALUES(?,?,?)", (pk, ik, "portrait"))
        conn.execute(
            "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
            "bundle,cab,path_id,status,source_json) "
            "VALUES((SELECT COALESCE(MAX(id),0)+1 FROM locators),'portrait',"
            "?,?,'','r','g','b1','',11,'ok','{}')", (cid, LOCALE))
        self._write_mip_item(cid, pk, img, pixel_sha, source=source)
        conn.execute(
            "INSERT INTO plans(plan_key,card_id,options_json,status,"
            "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
            (pk, cid, S.cjson({}), "complete", S.PLAN_VERSION, f"ds-{cid}",
             NOW))

    def _write_mip_item(self, cid: str, pk: str, img: Image.Image,
                        pixel_sha: str, *, source: str) -> None:
        name = "FakeReg_B_D" if source == "registry" else "FakeChain_D"
        n = 3 if source == "registry" else 3
        conn = self.conn
        if source == "chain":
            arrays = {MC.level_key(i):
                      np.full((8 >> i, 8 >> i, 4), 40 + i, dtype=np.uint8)
                      for i in range(1, n)}
            payload = MC.encode_chain_npz(arrays)
            chain_sha = MC.chain_content_sha(
                [arrays[MC.level_key(i)] for i in range(1, n)])
            mip_manifest = {"mip_count": n, "l0": "derived", "lods_stored": n - 1}
        else:
            payload = MC.meta_marker_payload()
            chain_sha = ""
            mip_manifest = {"mip_count": n, "l0": "derived", "lods_stored": 0}
        payload_sha = S.sha256_hex(payload)
        meta_sha = S.sha256_hex(S.cjson(
            {"name": name, "filter": 2, "bias": -0.5, "source": source,
             "mip_count": n}).encode("utf-8"))
        content = {"carddef": f"cd-{cid}", "portrait": pixel_sha,
                   "chain": chain_sha, "meta": meta_sha}
        mik = S.portrait_mip_item_key(card_id=cid, locale=LOCALE,
                                      content_inputs=content)
        manifest = {"card_id": cid, "kind": S.ITEM_PORTRAIT_MIP,
                    "locale": LOCALE, "source": source, "name": name,
                    "filter": 2, "bias": -0.5, "width": img.width,
                    "height": img.height, **mip_manifest,
                    "chain_payload_sha256": payload_sha,
                    "chain_payload_size": len(payload),
                    "portrait_pixel_sha256": pixel_sha,
                    "guid": f"guid-{cid}", "bundle": "b1", "cab": "",
                    "path_id": 11}
        mbk = S.blob_key_generic(domain="mip", content_sha=payload_sha,
                                 codec="npz")
        self._blob(payload_sha, payload, ".npz", blob_key=mbk, codec="npz")
        self._item(mik, S.DOMAIN, S.ITEM_PORTRAIT_MIP,
                   S.cjson({"card_id": cid, "kind": S.ITEM_PORTRAIT_MIP}),
                   "npz", S.cjson(manifest), content, codec_version=1)
        conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                     "VALUES(?,?,?)", (mik, mbk, "chain"))
        conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                     "VALUES(?,?,?)", (pk, mik, "portrait_mip"))
        self.mip_keys = getattr(self, "mip_keys", {})
        self.mip_keys[cid] = mik

    def _write_sentinel_card(self, cid: str) -> None:
        """portrait item 在、portrait_mip 缺（哨兵行）——expected-vs-built 缺口。"""
        conn = self.conn
        conn.execute(
            "INSERT INTO cards(card_id,dbf_id,carddef_ref,carddef_guid,"
            "carddef_bundle,carddef_cab,carddef_path_id,data_sha) "
            "VALUES(?,?,'','','','',0,?)", (cid, 4243, f"ds-{cid}"))
        pk = S.plan_key(card_id=cid, locale=LOCALE, card_data_sha=f"ds-{cid}")
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        png = _encode_png(img)
        pixel_sha = S.sha256_hex(img.tobytes())
        payload_sha = S.sha256_hex(png)
        content = {"carddef": f"cd-{cid}", "portrait": pixel_sha}
        ik = S.item_key(card_id=cid, kind="portrait", locale=LOCALE, premium="",
                        content_inputs=content)
        manifest = {"card_id": cid, "kind": "portrait", "locale": LOCALE,
                    "ref": f"ref-{cid}", "guid": f"guid-{cid}", "bundle": "b1",
                    "cab": "", "path_id": 12, "width": 4, "height": 4,
                    "mode": "RGBA", "pixel_sha256": pixel_sha,
                    "payload_sha256": payload_sha, "payload_size": len(png)}
        bk = S.blob_key(portrait_content_sha=pixel_sha)
        self._blob(payload_sha, png, ".png", blob_key=bk)
        self._item(ik, S.DOMAIN, S.ITEM_PORTRAIT,
                   S.cjson({"card_id": cid, "kind": "portrait"}), "png",
                   S.cjson(manifest), content)
        conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                     "VALUES(?,?,?)", (ik, bk, "portrait"))
        conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                     "VALUES(?,?,?)", (pk, ik, "portrait"))
        conn.execute(
            "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
            "bundle,cab,path_id,status,source_json) "
            "VALUES((SELECT COALESCE(MAX(id),0)+1 FROM locators),'portrait',"
            "?,?,'','r','g','b1','',12,'ok','{}')", (cid, LOCALE))
        conn.execute(
            "INSERT INTO plan_items(plan_key,item_key,role) VALUES(?,?,?)",
            (pk, S.expected_item_key("portrait_mip"), "portrait_mip"))
        conn.execute(
            "INSERT INTO plans(plan_key,card_id,options_json,status,"
            "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
            (pk, cid, S.cjson({}), "partial", S.PLAN_VERSION, f"ds-{cid}",
             NOW))

    # ---- 落库小件 ----

    def _blob(self, payload_sha: str, data: bytes, ext: str, *,
              blob_key: str | None = None, codec: str = "png") -> Path:
        bp = self.layout.blob_path(payload_sha, ext=ext)
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_bytes(data)
        self.conn.execute(
            "INSERT OR REPLACE INTO blobs(blob_key,payload_sha256,size,codec,"
            "codec_version,last_used,created_at) VALUES(?,?,?,?,?,?,?)",
            (blob_key or payload_sha, payload_sha, len(data), codec, 1,
             NOW, NOW))
        return bp

    def _item(self, ik: str, domain: str, item: str, params: str, codec: str,
              manifest: str, content: dict, *, codec_version: int = 1) -> None:
        self.conn.execute(
            "INSERT INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (ik, domain, item, params, codec, codec_version, manifest, "ok",
             "asset", S.cjson([]), S.cjson(content), NOW))


def _encode_png(img: Image.Image) -> bytes:
    import io

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class MipCase(unittest.TestCase):
    """公共底座：tmp fixture + SupplyIndex。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.fx = _MipFixture(self.root)
        self.fx.publish_current()
        self.idx = SupplyIndex(self.root)
        self.addCleanup(self.idx.close)


class CodecTests(unittest.TestCase):
    """mip_codec：无损往返 / 确定性 / 内容 sha / meta marker。"""

    def test_roundtrip_lossless_uint8(self) -> None:
        arrays = {"lod/1": np.random.RandomState(3).randint(
            0, 256, (16, 16, 4)).astype(np.uint8),
            "lod/2": np.arange(24, dtype=np.uint8).reshape(2, 3, 4)}
        back = MC.decode_chain_npz(MC.encode_chain_npz(arrays))
        self.assertEqual(set(back), set(arrays))
        for k in arrays:
            self.assertTrue((back[k] == arrays[k]).all(), k)

    def test_deterministic_bytes(self) -> None:
        arrays = {"lod/1": np.arange(64, dtype=np.uint8).reshape(4, 4, 4)}
        b1 = MC.encode_chain_npz(arrays)
        b2 = MC.encode_chain_npz(dict(reversed(list(arrays.items()))))
        self.assertEqual(b1, b2, "条目序=键排序、时间戳固定 → 同输入同字节")

    def test_chain_content_sha_order_sensitive_and_stable(self) -> None:
        a = np.arange(16, dtype=np.uint8).reshape(2, 2, 4)
        b = (a + 1).astype(np.uint8)
        self.assertEqual(MC.chain_content_sha([a, b]),
                         MC.chain_content_sha([a.copy(), b.copy()]))
        self.assertNotEqual(MC.chain_content_sha([a, b]),
                            MC.chain_content_sha([b, a]), "级别序进 sha")
        self.assertEqual(MC.chain_content_sha([]), "")

    def test_meta_marker_constant_and_decodable(self) -> None:
        p1 = MC.meta_marker_payload()
        self.assertEqual(p1, MC.meta_marker_payload())
        self.assertEqual(MC.decode_chain_npz(p1).keys(), {"meta"})

    def test_empty_arrays_encode_empty(self) -> None:
        self.assertEqual(MC.encode_chain_npz({}), b"")


class ChainTableParityTests(unittest.TestCase):
    """mip_extract ↔ live supply.textures 链面契约（逐字漂移钉住）。"""

    @classmethod
    def setUpClass(cls) -> None:
        # UnityPy 面（mip_extract→_unity）+ live 形状类惰性 import（模块级会
        # 在 discovery 期污染 sys.modules——render_import_seams 判例）
        from eidolon.core.supply_index import mip_extract

        cls.ME = mip_extract

    def test_mip_chains_table_identical_to_live(self) -> None:
        from eidolon.core.supply.textures import _MIP_CHAINS

        self.assertEqual(self.ME.MIP_CHAINS, tuple(_MIP_CHAINS),
                         "cold 链表与 live _MIP_CHAINS 逐字符全等"
                         "（提取对象集契约；live 升链须同步 cold）")
        self.assertEqual(self.ME.MIP_CHAIN_ADDR,
                         {e[0]: (e[1], int(e[2])) for e in _MIP_CHAINS})

    def test_decode_helpers_match_live(self) -> None:
        from eidolon.core.supply.textures import (
            _decode_level,
            _level_bytes,
            _level_dims,
        )

        ME = self.ME

        for fmt in (10, 12, 4):
            data = bytes(range(256)) * 256
            for (w, h, lv) in ((64, 64, 0), (33, 17, 2)):
                lw, lh = _level_dims(w, h, lv)
                self.assertEqual(ME.level_dims(w, h, lv), (lw, lh))
                self.assertEqual(ME.level_bytes(fmt, lw, lh),
                                 _level_bytes(fmt, lw, lh))
                lb = _level_bytes(fmt, lw, lh)
                a = ME.decode_level(data[:lb], lw, lh, fmt)
                b = _decode_level(data[:lb], lw, lh, fmt)
                self.assertTrue(np.array_equal(a, b), f"fmt={fmt} {lw}x{lh}")

    def test_extract_all_levels_byte_account_assert(self) -> None:
        # 字节账断言：RGBA32 2×2=16 字节整账；多字节 → AssertionError
        # （live _extract_chain 同判）
        ME = self.ME
        lods = ME.extract_all_levels(bytes(16), fmt=4, w=2, h=2, n=1, name="t")
        self.assertEqual(len(lods), 1)
        with self.assertRaises(AssertionError):
            ME.extract_all_levels(bytes(17), fmt=4, w=2, h=2, n=1, name="t")

    def test_classify_portrait_three_states(self) -> None:
        ME = self.ME
        def tree(name, n):
            return {"m_Name": name, "m_Width": 512, "m_Height": 512,
                    "m_MipCount": n, "m_TextureFormat": 12,
                    "m_TextureSettings": {"m_FilterMode": 2, "m_MipBias": -0.5}}

        live_name, live_bundle, live_pid = ME.MIP_CHAINS[1]
        self.assertEqual(
            ME.classify_portrait(tree(live_name, 10), live_bundle, live_pid),
            (ME.SOURCE_REGISTRY, 10))
        self.assertEqual(
            ME.classify_portrait(tree(live_name, 10), "other-bundle", 1),
            (ME.SOURCE_CHAIN, 10), "同名不同址=变体件（防同名劫持，live 同判）")
        self.assertEqual(
            ME.classify_portrait(tree("Plain_D", 1), "b", 1),
            (ME.SOURCE_PORTRAIT, 1))
        self.assertEqual(
            ME.classify_portrait(tree("Unknown_D", 10), "b", 2),
            (ME.SOURCE_CHAIN, 10))
        # 格式域外（BC7=25）：mips>1 → unsupported（live 链解码 raise 同现状，
        # 缺席可归因——不建 item 不期望）；mips<=1 → portrait（单级链与格式域无关）
        bc7 = tree("BC7_D", 10)
        bc7["m_TextureFormat"] = 25
        self.assertEqual(ME.classify_portrait(bc7, "b", 3),
                         (ME.SOURCE_UNSUPPORTED, 10))
        bc7["m_MipCount"] = 1
        self.assertEqual(ME.classify_portrait(bc7, "b", 3),
                         (ME.SOURCE_PORTRAIT, 1))


class WarmMipTests(MipCase):
    """warm 两 API 同形 + expected-vs-built 门 + fail loud 面。"""

    def test_mip_registry_live_shape_and_cache(self) -> None:
        reg = self.idx.mip_registry()
        self.assertEqual(set(reg), set(_REG_CHAINS))
        for name, (n, filt, bias) in _REG_CHAINS.items():
            ent = reg[name]
            self.assertEqual(set(ent), {"lods", "filter", "bias"})
            self.assertEqual(len(ent["lods"]), n)
            self.assertEqual(ent["filter"], filt)
            self.assertEqual(ent["bias"], bias)
            for i, lod in enumerate(ent["lods"]):
                self.assertEqual(lod.dtype, np.uint8)
                self.assertEqual(lod.shape, (8 >> i, 8 >> i, 4))
        self.assertIs(reg, self.idx.mip_registry(), "进程内缓存一次")

    def test_mip_registry_missing_fails_loud(self) -> None:
        conn = S.connect(self.fx.db)
        try:
            conn.execute("DELETE FROM item_blobs WHERE item_key=?",
                         (self.fx.reg_key,))
            conn.execute("DELETE FROM items WHERE item_key=?",
                         (self.fx.reg_key,))
            conn.commit()
        finally:
            conn.close()
        idx = SupplyIndex(self.root)
        self.addCleanup(idx.close)
        with self.assertRaises(SupplyMissingError):
            idx.mip_registry()

    def test_mip_registry_blob_tamper_corrupt_error(self) -> None:
        bp = self.fx.layout.blob_path(self.fx.reg_payload_sha, ext=".npz")
        bp.write_bytes(bp.read_bytes() + b"x")
        idx = SupplyIndex(self.root)
        self.addCleanup(idx.close)
        with self.assertRaises(SupplyBlobCorruptError):
            idx.mip_registry()

    def test_portrait_mip_chain_source_derived_l0(self) -> None:
        ent = self.idx.portrait_mip("C_MIP")
        self.assertEqual(set(ent), {"name", "chain", "filter", "bias"})
        self.assertEqual(ent["name"], "FakeChain_D")
        self.assertEqual(ent["filter"], 2)
        self.assertEqual(ent["bias"], -0.5)
        chain = ent["chain"]
        self.assertIsInstance(chain, WarmChain)
        self.assertEqual(len(chain), 3)
        # L0=portrait PNG 像素（warm 派生面——fixture 肖像 (10,20,30,255) 实色）
        l0 = chain.peek(0)
        self.assertEqual(l0.shape, (8, 8, 4))
        self.assertEqual(float(l0[0, 0, 0]), 10 / 255.0)
        self.assertEqual(float(l0[0, 0, 3]), 1.0)
        # 存储级=fixture npz 数组（uint8 40+i 实色）
        self.assertTrue((chain.lods[1] == np.full((4, 4, 4), 41,
                                                  dtype=np.uint8)).all())
        self.assertTrue((chain.lods[2] == np.full((2, 2, 4), 42,
                                                  dtype=np.uint8)).all())
        self.assertEqual(chain.shape0(), (8, 8))

    def test_portrait_mip_registry_source_shares_registry_lods(self) -> None:
        ent = self.idx.portrait_mip("C_REG")
        self.assertEqual(ent["name"], "FakeReg_B_D")
        reg = self.idx.mip_registry()
        for a, b in zip(ent["chain"].lods, reg["FakeReg_B_D"]["lods"]):
            self.assertTrue(np.array_equal(a, b), "registry 源=同源单链")

    def test_warm_chain_protocol_matches_live_lazy_float_chain(self) -> None:
        from eidolon.core.supply.textures import LazyFloatChain

        lods = [np.full((8, 8, 4), i, dtype=np.uint8) for i in range(3)]
        warm = WarmChain(lods)
        live = LazyFloatChain(list(lods))
        self.assertEqual(len(warm), len(live))
        self.assertEqual(warm.shape0(), live.shape0())
        for i in range(3):
            self.assertTrue(np.array_equal(warm.peek(i), live.peek(i)),
                            f"peek({i}) 值面逐位一致（同一 astype/255）")
            self.assertTrue(np.array_equal(warm[i], live[i]))

    def test_plan_expected_includes_portrait_mip_and_status_complete(self) -> None:
        plan = self.idx.plan("C_MIP")
        self.assertIsNotNone(plan)
        self.assertIn("portrait_mip", [i.role for i in plan.items])
        self.assertEqual(plan.status, "complete")
        # DB 级 expected-vs-built 账（schema 单源）：portrait_mip role 入期望；
        # 哨兵卡=缺口点名（C_GAP_MIP）
        comp = S.expected_vs_built(self.idx.conn)
        self.assertEqual(comp["by_kind"].get("portrait_mip", {})
                         .get("expected_cards"), 3)
        self.assertEqual(comp["by_kind"].get("portrait_mip", {})
                         .get("missing_cards"), 1)

    def test_sentinel_row_names_portrait_mip_and_gate_raises(self) -> None:
        plan = self.idx.plan("C_GAP_MIP")
        self.assertEqual(plan.status, "partial")
        self.assertTrue(any("portrait_mip" in m for m in plan.missing),
                        plan.missing)
        with self.assertRaises(SupplyMissingError):
            self.idx.assemble_card("C_GAP_MIP")

    def test_portrait_mip_missing_item_fails_loud(self) -> None:
        conn = S.connect(self.fx.db)
        try:
            conn.execute("DELETE FROM item_blobs WHERE item_key=?",
                         (self.fx.mip_keys["C_MIP"],))
            conn.execute("DELETE FROM items WHERE item_key=?",
                         (self.fx.mip_keys["C_MIP"],))
            conn.commit()
        finally:
            conn.close()
        idx = SupplyIndex(self.root)
        self.addCleanup(idx.close)
        with self.assertRaises(SupplyMissingError):
            idx.portrait_mip("C_MIP")

    def test_portrait_mip_unknown_card_fails_loud(self) -> None:
        with self.assertRaises(SupplyMissingError):
            self.idx.portrait_mip("__ghost__")

    def test_assemble_skips_npz_bundle_but_expected_stays_built(self) -> None:
        # npz 项不入通用束（专属访问器装配），期望账不受影响（role 仍 built）
        bundle = self.idx.assemble_card("C_MIP")
        self.assertNotIn("portrait_mip", bundle)
        self.assertIn("portrait", bundle)
        plan = self.idx.plan("C_MIP")
        self.assertEqual(plan.status, "complete")


class SchemaKeyTests(unittest.TestCase):
    """A5 键面：全值输入进键（必须保留 #6）。"""

    def test_portrait_mip_item_key_inputs(self) -> None:
        base = dict(card_id="C1", locale="zhcn",
                    content_inputs={"carddef": "cd", "portrait": "px",
                                    "chain": "ch", "meta": "mt"})
        k1 = S.portrait_mip_item_key(**base)
        self.assertEqual(k1, S.portrait_mip_item_key(**base), "确定性")
        for field, value in (("carddef", "cd2"), ("portrait", "px2"),
                             ("chain", "ch2"), ("meta", "mt2")):
            changed = {**base, "content_inputs":
                       {**base["content_inputs"], field: value}}
            self.assertNotEqual(k1, S.portrait_mip_item_key(**changed),
                                f"content_inputs.{field} 进键")
        self.assertNotEqual(
            k1, S.portrait_mip_item_key(card_id="C2", locale="zhcn",
                                        content_inputs=base["content_inputs"]))
        self.assertNotEqual(
            k1, S.portrait_mip_item_key(card_id="C1", locale="enus",
                                        content_inputs=base["content_inputs"]))

    def test_mip_registry_item_key_inputs(self) -> None:
        base = dict(locale="zhcn",
                    content_inputs={"chains": "agg", "table": "tb"})
        k1 = S.mip_registry_item_key(**base)
        self.assertEqual(k1, S.mip_registry_item_key(**base))
        self.assertNotEqual(k1, S.mip_registry_item_key(
            locale="zhcn", content_inputs={"chains": "agg2", "table": "tb"}))
        self.assertNotEqual(k1, S.mip_registry_item_key(
            locale="zhcn", content_inputs={"chains": "agg", "table": "tb2"}))
        self.assertNotEqual(k1, S.mip_registry_item_key(
            locale="enus", content_inputs=base["content_inputs"]))


class EntrySeedLookupTests(unittest.TestCase):
    """supply.textures entry seed 注入位（模块级；未安装=纯 live）。"""

    def tearDown(self) -> None:
        from eidolon.core.supply.textures import clear_entry_seed_lookup

        clear_entry_seed_lookup()

    def test_covered_ref_served_without_live_resolution(self) -> None:
        from eidolon.core.supply.textures import (
            ENTRY_SEED_UNSET,
            entry_for_ref,
            set_entry_seed_lookup,
        )

        seen = []
        entry = {"name": "T", "chain": WarmChain(
            [np.zeros((4, 4, 4), np.uint8)]), "filter": 2, "bias": 0.0}

        def handle(ref):
            seen.append(ref)
            if ref == "Covered_Mips.tif:g1":
                return dict(entry)
            if ref == "Covered_NoMips.tif:g2":
                return None
            return ENTRY_SEED_UNSET

        set_entry_seed_lookup(handle)
        self.assertEqual(entry_for_ref("Covered_Mips.tif:g1"), entry)
        self.assertIsNone(entry_for_ref("Covered_NoMips.tif:g2"),
                          "已裁决无链=None（live m_MipCount<=1 同判）")
        self.assertEqual(seen, ["Covered_Mips.tif:g1", "Covered_NoMips.tif:g2"])
        # memo 命中不回调（进程 memo 面）
        entry_for_ref("Covered_Mips.tif:g1")
        self.assertEqual(len(seen), 2)

    def test_unset_ref_falls_back_to_live(self) -> None:
        from eidolon.core.supply.textures import (
            ENTRY_SEED_UNSET,
            entry_for_ref,
            set_entry_seed_lookup,
        )

        seen = []

        def handle(ref):
            seen.append(ref)
            return ENTRY_SEED_UNSET

        set_entry_seed_lookup(handle)
        # 默认进程无 ctx 安装 → live 解析异常 → None（与 live fallback 同象；
        # 本测试只钉「UNSET → 落 live 路」的分流，不做真实解析）
        self.assertIsNone(entry_for_ref("Uncovered_Mips.tif:g9"))
        self.assertEqual(seen, ["Uncovered_Mips.tif:g9"])

    def test_clear_uninstalls_and_identity_guard(self) -> None:
        from eidolon.core.supply.textures import (
            clear_entry_seed_lookup,
            entry_for_ref,
            set_entry_seed_lookup,
        )

        calls = []

        def h1(ref):
            calls.append("h1")
            return None

        def h2(ref):
            calls.append("h2")
            return None

        set_entry_seed_lookup(h1)
        set_entry_seed_lookup(h2)                     # 覆盖式安装（后装生效）
        entry_for_ref("Fresh_Mips.tif:g1")
        self.assertEqual(calls, ["h2"])
        clear_entry_seed_lookup(h1)                   # 旧句柄 close 不误卸
        entry_for_ref("Fresh_Mips.tif:g2")
        self.assertEqual(calls, ["h2", "h2"])
        clear_entry_seed_lookup(h2)
        entry_for_ref("Fresh_Mips.tif:g3")
        self.assertEqual(calls, ["h2", "h2"], "卸载后不再 consulted")


class SeederHandleLifecycleTests(MipCase):
    """CardSeeder.open 安装 / close 卸（fn 身份判据；晚开不误卸）。"""

    def _seeder(self):
        from eidolon.core.supply_index.seed import CardSeeder

        seeder = CardSeeder.open(self.root, ctx_locale=LOCALE,
                                 ctx_identity=IDENTITY)
        self.assertIsNotNone(seeder)
        self.addCleanup(seeder.close)
        return seeder

    def test_open_installs_and_close_uninstalls(self) -> None:
        import eidolon.core.supply.textures as TX

        seeder = self._seeder()
        self.assertIs(TX._ENTRY_SEED_LOOKUP, seeder._entry_seed)
        seeder.close()
        self.assertIsNone(TX._ENTRY_SEED_LOOKUP)

    def test_later_seeder_close_does_not_clobber_newer_handle(self) -> None:
        import eidolon.core.supply.textures as TX

        from eidolon.core.supply_index.seed import CardSeeder

        s1 = CardSeeder.open(self.root, ctx_locale=LOCALE,
                             ctx_identity=IDENTITY)
        s2 = CardSeeder.open(self.root, ctx_locale=LOCALE,
                             ctx_identity=IDENTITY)
        self.assertIsNot(s1._entry_seed, s2._entry_seed)
        self.assertIs(TX._ENTRY_SEED_LOOKUP, s2._entry_seed)
        s1.close()                                    # 晚装者优先（身份判据）
        self.assertIs(TX._ENTRY_SEED_LOOKUP, s2._entry_seed)
        s2.close()
        self.assertIsNone(TX._ENTRY_SEED_LOOKUP)

    def test_seeds_include_mip_tokens(self) -> None:
        from eidolon.core.supply_index.seed import CardSeeder

        seeder = CardSeeder.open(self.root, ctx_locale=LOCALE,
                                 ctx_identity=IDENTITY)
        self.addCleanup(seeder.close)
        seeds = seeder.seeds_for_card("C_MIP")
        self.assertIsNotNone(seeds)
        self.assertIn(("textures", "mip_registry", ()), seeds)
        self.assertIn(("art", "portrait_mip", ("C_MIP",)), seeds)
        reg = seeds[("textures", "mip_registry", ())]
        self.assertEqual(set(reg), set(_REG_CHAINS))
        pm = seeds[("art", "portrait_mip", ("C_MIP",))]
        self.assertEqual(set(pm), {"name", "chain", "filter", "bias"})
        self.assertEqual(len(pm["chain"]), 3)
        ledger = seeder.last_ledger
        # fixture 无 kit/watermark/color/supplement 面（合法缺席跳过）；mip 两
        # token 不在跳过面（A6 跳过词面=frames.kit*/bacon/ability/badges/btf/
        # ornaments/ta/material_state/portrait_uv1 + text.font_asset_params）
        self.assertTrue(all(
            t.startswith(("frames.kit", "frames.bacon_kit", "frames.ability_kit",
                          "frames.badges_kit", "frames.btf_kit",
                          "frames.ornaments_kit", "frames.ta_supplement",
                          "frames.material_state", "frames.portrait_uv1",
                          "frames.kit_light", "text.font_asset_params",
                          "watermarks.texture", "color.probe"))
            for t in ledger.skipped), ledger.skipped_reasons)

    def test_sentinel_card_abandons_seeding(self) -> None:
        from eidolon.core.supply_index.seed import CardSeeder

        seeder = CardSeeder.open(self.root, ctx_locale=LOCALE,
                                 ctx_identity=IDENTITY)
        self.addCleanup(seeder.close)
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="WARNING"):
            seeds = seeder.seeds_for_card("C_GAP_MIP")
        self.assertIsNone(seeds, "mip 期望缺口=整卡弃种回 live（严格门同判）")


def tearDownModule() -> None:  # noqa: N802 —— unittest 约定钩子
    """链表对拍/协议对拍的运行期 live import 可能拖入 UnityPy（resolver 面）——
    出口清干净（test_route_cabs/test_supply_index_seed 同纪律），保后续 import
    卫生守卫绿。"""
    import sys

    for name in [m for m in sys.modules
                 if m == "UnityPy" or m.startswith("UnityPy.")]:
        sys.modules.pop(name, None)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
