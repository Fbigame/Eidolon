"""core/supply_index warm 面单测（默认 discover 收集；零 UnityPy、零游戏文件）。

覆盖（任务 A2）：
  * tmp 造最小代库（init_schema + 手工 INSERT cards/locators/plans/plan_items/
    items/item_blobs/blobs + text 域 fontdefs/ttf + frames 域 kit）+ 内容寻址
    blobs（真实 PNG 字节，按 paths 布局落盘）；
  * ``SupplyIndex(cache_root)`` plan / assemble / assemble_card / assemble_portrait
    命中路径出 PIL Image（与写入 blob 同图、像素 sha 全等）；kit 六面重组 + 进程内
    LRU（同对象按引用返回）；text 全域段（json→dict、ttf→bytes）；
  * 缺项 fail loud：卡不在表 / item 缺 / blob 行缺 / blob 文件缺 / 未知 codec →
    SupplyMissingError（类型与 message 点名）；blob 字节篡改 →
    SupplyBlobCorruptError（SupplyMissingError 子类，payload_sha 定位）；
  * check / fillable_missing 批量审计账（hit / absent_portrait / missing 分拣）；
  * expected-vs-built 门（Phase 5 返工 R1，P0-1；审计 CAP_000 场景固化）：golden
    locator 在、golden item 删 → plan.missing 点名 golden、check miss、
    assemble_card 严格门抛 SupplyMissingError、allow_partial=True 显式豁免可过
    （缺省 False 断言）；kit 期望哨兵行（expect::*）点名 role；blob 篡改负例在
    新门下保持响亮；
  * bench_warm_full 缺席归因口径（R2：partial 标注 + 吞吐分母=可装配卡、
    absent 两类单列不算失败、gap>0 才 partial）；
  * 缺席归因四分类 account_for_cards（R2：ok/missing_gap/absent 两类/anomaly
    判据与期望面同源）+ 期望为零卡 plan/assemble 零 raise 钉死；
  * health_policy 三档 stamp 语义（miss→quick_check→hit / 身份失配 / skip / 非法值）
    与 gen= 绑代演练面；
  * import 卫生（子进程机器面）：import warm 全链后 sys.modules 无 UnityPy/clr/
    texture2ddecoder/本包 UnityPy 面（cold/kit_extract/text_extract/wm_extract）。

warm 的 numpy/PIL import 是合法面（kit_codec 重组）；本文件自身也不 import UnityPy。
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from eidolon.core.supply_index import kit_codec as KC
from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index import text_codec as TC
from eidolon.core.supply_index.paths import SupplyLayout
from eidolon.core.supply_index.warm import (
    SupplyBlobCorruptError,
    SupplyIndex,
    SupplyIndexCorruptError,
    SupplyMissingError,
)

_REPO = Path(__file__).resolve().parents[2]
LOCALE = "zhcn"
GID = "testgen"
NOW = 1700000000

_TEXT_FONTDEFS = {"ZhFont": {"m_Name": "ZhFont", "m_LineSpaceModifier": 1.0}}
_TTF_BYTES = b"FAKE-TTF-BYTES-0123456789"

# color 域（A4）：probe 表（含空占位槽——ColorType 下标对齐语义）+ 两张 atlas
_COLOR_PROBE = {"minionCardTextures": ["a.tif:g0", "b.tif:g1", "", "c.tif:g2"],
                "spellCardTextures": ["s.tif:g3"]}
_COLOR_ATLAS = {"minionCardTextures": {0: (10, 20, 30, 255),
                                       7: (40, 50, 60, 255)}}
_SWITCHER_REF = "CardColorSwitcher.prefab:b30c8322821f1524d9e08a59e78e2c85"


def _encode_png(img: Image.Image) -> bytes:
    return KC.encode_png(img)


class _Fixture:
    """最小代库手造器（单文件 sqlite + 内容寻址 blob 文件）。"""

    def __init__(self, root: Path):
        self.layout = SupplyLayout(root)
        self.root = Path(root)
        self.db = self.layout.gen_db(GID)
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.blob_files: dict[str, Path] = {}      # card_id -> portrait blob 路径
        self.pixel_shas: dict[str, str] = {}
        self.payload_shas: dict[str, str] = {}
        self.portrait_keys: dict[str, str] = {}
        self.golden_keys: dict[str, str] = {}
        conn = S.connect(self.db)
        try:
            S.init_schema(conn)
            conn.executemany("INSERT INTO meta(key,value) VALUES(?,?)",
                             [("game_id", GID), ("locale", LOCALE),
                              ("full_build", "0")])
            self._write_card(conn, "C_BUILT", (255, 0, 0, 255))
            self._write_card(conn, "C_BUILT_2", (0, 255, 0, 255))
            self._write_card(conn, "C_BADCODEC", (0, 0, 255, 255))
            # C_GOLD：portrait + portrait_golden 双 kind 全链（期望落账正面件）
            self._write_card(conn, "C_GOLD", (255, 255, 0, 255),
                             kinds=("portrait", "portrait_golden"))
            # C_GAP：locator ok 而无 item/plan（期望缺口 → fillable 面）
            self._write_card(conn, "C_GAP", None, kinds=())
            conn.execute(
                "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
                "bundle,cab,path_id,status,source_json) "
                "VALUES((SELECT COALESCE(MAX(id),0)+1 FROM locators),'portrait',"
                "?,?,'','r','g','b1','',0,'ok','{}')", ("C_GAP", LOCALE))
            # C_ABSENT：在 cards 表、无 locator 无 plan（数据缺席=合法）
            self._write_card(conn, "C_ABSENT", None, kinds=())
            # C_LOCMISS：locator status='missing'（ref 不可解）而无 item
            #（不可补面——check 缺项账，非 expected）
            self._write_card(conn, "C_LOCMISS", None, kinds=())
            conn.execute(
                "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
                "bundle,cab,path_id,status,source_json) "
                "VALUES((SELECT COALESCE(MAX(id),0)+1 FROM locators),'portrait',"
                "?,?,'','r','g','','',0,'missing','{}')", ("C_LOCMISS", LOCALE))
            # C_NOITEM：plan+plan_items 指向不存在的 item（LEFT JOIN status NULL）
            self._write_card(conn, "C_NOITEM", None, kinds=())
            pk = S.plan_key(card_id="C_NOITEM", locale=LOCALE,
                            card_data_sha="ds-C_NOITEM")
            conn.execute(
                "INSERT INTO plans(plan_key,card_id,options_json,status,"
                "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
                (pk, "C_NOITEM", S.cjson({}), "partial", S.PLAN_VERSION,
                 "ds-C_NOITEM", NOW))
            conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                         "VALUES(?,?,?)", (pk, "ik-ghost-0000000000", "portrait"))
            # C_SENT：期望哨兵行（kit 期望未建——D-决策 2 落账形态）
            self._write_card(conn, "C_SENT", None, kinds=())
            pk = S.plan_key(card_id="C_SENT", locale=LOCALE,
                            card_data_sha="ds-C_SENT")
            conn.execute(
                "INSERT INTO plans(plan_key,card_id,options_json,status,"
                "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
                (pk, "C_SENT", S.cjson({}), "partial", S.PLAN_VERSION,
                 "ds-C_SENT", NOW))
            conn.execute(
                "INSERT INTO plan_items(plan_key,item_key,role) VALUES(?,?,?)",
                (pk, S.expected_item_key("kit:ally"), "kit"))
            self._write_text(conn)
            self._write_kit(conn)
            self._write_color(conn)
            conn.commit()
        finally:
            conn.close()
        self.layout.write_current({
            "game_id": GID, "generation": f"gen-{GID}", "locale": LOCALE,
            "full_build": False, "updated_at": NOW,
        })

    # ---- 单卡 portrait 面（locator+item+blob+plan 全链；kinds 缺省=仅 portrait，
    #      color=None=只建卡行不建产物） ----

    def _write_card(self, conn: sqlite3.Connection, cid: str,
                    color: tuple[int, int, int, int] | None,
                    kinds: tuple[str, ...] = ("portrait",)) -> None:
        conn.execute(
            "INSERT INTO cards(card_id,dbf_id,carddef_ref,carddef_guid,"
            "carddef_bundle,carddef_cab,carddef_path_id,data_sha) "
            "VALUES(?,NULL,'','','','',0,?)", (cid, f"ds-{cid}"))
        if color is None:
            return
        pk = S.plan_key(card_id=cid, locale=LOCALE, card_data_sha=f"ds-{cid}")
        codec = "webp" if cid == "C_BADCODEC" else S.CODEC
        roles = []
        for kind in kinds:
            premium = "gold" if kind == "portrait_golden" else ""
            # golden 面独立像素（真 cold 里 golden 是另一张纹理——blob_key 依
            # 像素 sha 派生，同图会撞 blob 行 PK）
            kcolor = color if kind == "portrait" else \
                (max(0, color[0] - 40), color[1], color[2], color[3])
            img = Image.new("RGBA", (4, 4), kcolor)
            png = _encode_png(img)
            pixel_sha = S.sha256_hex(img.tobytes())
            payload_sha = S.sha256_hex(png)
            content = {"carddef": f"cd-{cid}", "portrait": pixel_sha}
            ik = S.item_key(card_id=cid, kind=kind, locale=LOCALE, premium=premium,
                            content_inputs=content)
            manifest = {"card_id": cid, "kind": kind, "locale": LOCALE,
                        "ref": f"ref-{cid}", "guid": f"guid-{cid}", "bundle": "b1",
                        "cab": "", "path_id": 0, "width": 4, "height": 4,
                        "mode": "RGBA", "pixel_sha256": pixel_sha,
                        "payload_sha256": payload_sha, "payload_size": len(png),
                        "carddef": {"sha256": f"cd-{cid}"}}
            bk = S.blob_key(portrait_content_sha=pixel_sha)
            bp = self.layout.blob_path(payload_sha)
            bp.parent.mkdir(parents=True, exist_ok=True)
            bp.write_bytes(png)
            conn.execute(
                "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
                "bundle,cab,path_id,status,source_json) "
                "VALUES((SELECT COALESCE(MAX(id),0)+1 FROM locators),?,?"
                ",?,?,'r','g','b1','',0,'ok','{}')", (kind, cid, LOCALE, premium))
            conn.execute(
                "INSERT INTO items(item_key,domain,item,params_json,codec,"
                "codec_version,manifest_json,status,source_kind,source_json,"
                "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (ik, S.DOMAIN, S.ITEM_PORTRAIT,
                 S.cjson({"card_id": cid, "kind": kind}), codec,
                 S.CODEC_VERSION, S.cjson(manifest), "ok", "asset",
                 S.cjson([{"bundle": "b1", "guid": f"guid-{cid}",
                           "bundle_sha256": ""}]),
                 S.cjson(content), NOW))
            conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                         "VALUES(?,?,?)", (ik, bk, kind))
            conn.execute(
                "INSERT INTO blobs(blob_key,payload_sha256,size,codec,codec_version,"
                "last_used,created_at) VALUES(?,?,?,?,?,?,?)",
                (bk, payload_sha, len(png), S.CODEC, S.CODEC_VERSION, NOW, NOW))
            conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                         "VALUES(?,?,?)", (pk, ik, kind))
            roles.append(kind)
            if kind == "portrait":
                self.blob_files[cid] = bp
                self.pixel_shas[cid] = pixel_sha
                self.payload_shas[cid] = payload_sha
                self.portrait_keys[cid] = ik
            else:
                self.golden_keys[cid] = ik
        status = "complete" if "portrait" in roles else "partial"
        conn.execute(
            "INSERT INTO plans(plan_key,card_id,options_json,status,"
            "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
            (pk, cid, S.cjson({}), status, S.PLAN_VERSION, f"ds-{cid}", NOW))

    # ---- text 全域段（fontdefs json + ttf 文件字节身份） ----

    def _write_text(self, conn: sqlite3.Connection) -> None:
        fdata = TC.encode_fontdefs(_TEXT_FONTDEFS)
        fsha = S.sha256_hex(fdata)
        fik = S.fontdefs_item_key(locale=LOCALE,
                                  content_inputs={"fontdefs": fsha})
        fbk = TC.fontdefs_blob_key(fsha)
        fbp = self.layout.blob_path(fsha, ext=".json")
        fbp.parent.mkdir(parents=True, exist_ok=True)
        fbp.write_bytes(fdata)
        conn.execute(
            "INSERT INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (fik, S.DOMAIN_TEXT, S.ITEM_FONTDEFS, S.cjson({}), "json",
             S.CODEC_VERSION, S.cjson({"payload_sha256": fsha}), "ok", "asset",
             S.cjson([]), S.cjson({"fontdefs": fsha}), NOW))
        conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                     "VALUES(?,?,?)", (fik, fbk, TC.ROLE_FONTDEFS))
        conn.execute(
            "INSERT INTO blobs(blob_key,payload_sha256,size,codec,codec_version,"
            "last_used,created_at) VALUES(?,?,?,?,?,?,?)",
            (fbk, fsha, len(fdata), "json", S.CODEC_VERSION, NOW, NOW))

        tsha = TC.ttf_content_sha(_TTF_BYTES)
        tik = S.font_ttf_item_key(font="ZhFont", locale=LOCALE,
                                  content_inputs={"ttf": tsha})
        tbk = TC.ttf_blob_key(tsha)
        tbp = self.layout.blob_path(tsha, ext=".ttf")
        tbp.parent.mkdir(parents=True, exist_ok=True)
        tbp.write_bytes(_TTF_BYTES)
        conn.execute(
            "INSERT INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (tik, S.DOMAIN_TEXT, S.ITEM_FONT_TTF, S.cjson({"font": "ZhFont"}),
             "ttf", S.CODEC_VERSION, S.cjson({"payload_sha256": tsha}), "ok",
             "asset", S.cjson([]), S.cjson({"ttf": tsha}), NOW))
        conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                     "VALUES(?,?,?)", (tik, tbk, TC.ROLE_TTF))
        conn.execute(
            "INSERT INTO blobs(blob_key,payload_sha256,size,codec,codec_version,"
            "last_used,created_at) VALUES(?,?,?,?,?,?,?)",
            (tbk, tsha, len(_TTF_BYTES), "ttf", S.CODEC_VERSION, NOW, NOW))

    # ---- kit（frames 域；faces 结构=kit_codec 面约定） ----

    def _write_kit(self, conn: sqlite3.Connection) -> None:
        meta = {"frame": "ally", "dbf_id": 9}
        hierarchy = {"path": "KitRoot", "children": []}
        report = {"nodes": 1}
        ubertext = {"label": "u"}
        arr = np.arange(6, dtype=np.float32).reshape(2, 3)
        npz = KC.encode_npz({"verts": arr})
        tex_img = Image.new("RGBA", (3, 3), (9, 9, 9, 255))
        tex_png = _encode_png(tex_img)
        tex_pixel = S.sha256_hex(tex_img.tobytes())
        tex_payload = S.sha256_hex(tex_png)
        arr_shas = {"verts": KC.array_content_sha("verts", arr)}
        # faces 账先算齐（blob 落库需要 ik，ik 依赖六面聚合 sha）
        blobs: list[tuple[str, str, bytes, str]] = []   # (face, codec, payload, role)
        faces = {}
        for face, obj in (("meta", meta), ("hierarchy", hierarchy),
                          ("report", report), ("ubertext", ubertext)):
            payload = KC.encode_json_face(obj)
            sha = S.sha256_hex(payload)
            faces[face] = {"payload_sha256": sha, "content_sha256": sha,
                           "size": len(payload)}
            blobs.append((face, "json", payload, face))
        arr_content = KC.arrays_content_sha(arr_shas)
        faces["arrays"] = {"payload_sha256": S.sha256_hex(npz),
                           "content_sha256": arr_content,
                           "size": len(npz), "array_shas": arr_shas}
        blobs.append(("arrays", "npz", npz, "arrays"))
        faces["textures"] = {"tex0.png": {
            "payload_sha256": tex_payload, "pixel_sha256": tex_pixel,
            "size": len(tex_png)}}
        blobs.append(("texture", "png", tex_png, "texture:tex0.png"))
        kit_sha = KC.kit_content_sha(
            meta_sha=faces["meta"]["content_sha256"],
            hierarchy_sha=faces["hierarchy"]["content_sha256"],
            report_sha=faces["report"]["content_sha256"],
            ubertext_sha=faces["ubertext"]["content_sha256"],
            arrays_sha=arr_content, texture_pixel_shas={"tex0.png": tex_pixel})
        content = {"actor_ref": "ref-ally", "guid": "guid-kit", "kit": kit_sha}
        ik = S.kit_item_key(frame="ally", locale=LOCALE, content_inputs=content)
        manifest = {"frame": "ally", "locale": LOCALE, "prefab_ref": "ref-ally",
                    "guid": "guid-kit", "bundle": "b1", "faces": faces,
                    "kit_content_sha256": kit_sha}
        conn.execute(
            "INSERT INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (ik, S.DOMAIN_FRAMES, S.ITEM_KIT, S.cjson({"frame": "ally"}),
             KC.KIT_CODEC, KC.KIT_CODEC_VERSION, S.cjson(manifest), "ok",
             "asset", S.cjson([{"bundle": "b1", "guid": "guid-kit",
                                "bundle_sha256": ""}]),
             S.cjson(content), NOW))
        for face, codec, payload, role in blobs:
            payload_sha = S.sha256_hex(payload)
            # blob_key 无需与 cold 完全同形（warm 只吃行账）；但 role 必须对齐
            bk = S.sha256_hex(f"test|{face}|{payload_sha}".encode())
            ext = KC.BLOB_CODEC_EXT[codec]
            bp = self.layout.blob_path(payload_sha, ext=ext)
            bp.parent.mkdir(parents=True, exist_ok=True)
            bp.write_bytes(payload)
            conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                         "VALUES(?,?,?)", (ik, bk, role))
            conn.execute(
                "INSERT INTO blobs(blob_key,payload_sha256,size,codec,"
                "codec_version,last_used,created_at) VALUES(?,?,?,?,?,?,?)",
                (bk, payload_sha, len(payload), codec, 1, NOW, NOW))

    # ---- color 域（A4：probe 全域项 + 两张 atlas；C_BUILT/C_GOLD 挂 role='color'） ----

    def _write_color(self, conn: sqlite3.Connection) -> None:
        # probe：json 落盘**保序**（live 键序语义——warm json.loads 复原同序）
        pdata = json.dumps(_COLOR_PROBE, ensure_ascii=False)
        psha = S.sha256_hex(pdata.encode("utf-8"))
        content_sha = S.sha256_hex(S.cjson(_COLOR_PROBE).encode("utf-8"))
        pik = S.color_probe_item_key(locale=LOCALE,
                                     content_inputs={"ref": _SWITCHER_REF,
                                                     "probe": content_sha})
        pbk = S.blob_key_generic(domain=S.DOMAIN_COLOR, content_sha=psha,
                                 codec="json")
        self.color_probe_key = pik
        self._write_blob_file(conn, pik, S.DOMAIN_COLOR, S.ITEM_COLOR_PROBE,
                              S.cjson({}), "json", psha, pdata.encode("utf-8"),
                              pbk, "probe",
                              {"payload_sha256": psha, "payload_size": len(pdata),
                               "families": {k: len(v)
                                            for k, v in _COLOR_PROBE.items()}})
        # atlas：两槽真 PNG（4×4 同形小图——像素 sha 对账用）
        self.color_atlas_files: dict[int, Path] = {}
        self.color_atlas_pixels: dict[int, str] = {}
        for fam, slots in _COLOR_ATLAS.items():
            for ct, color in slots.items():
                img = Image.new("RGBA", (4, 4), color)
                png = _encode_png(img)
                pixel = S.sha256_hex(img.tobytes())
                payload = S.sha256_hex(png)
                cik = S.color_atlas_item_key(
                    family=fam, ct=ct, locale=LOCALE,
                    content_inputs={"ref": f"{fam}-{ct}.tif:g{ct}",
                                    "guid": f"g{ct}", "pixel": pixel})
                cbk = S.blob_key_generic(domain=S.DOMAIN_COLOR,
                                         content_sha=pixel, codec=S.CODEC)
                self._write_blob_file(
                    conn, cik, S.DOMAIN_COLOR, S.ITEM_COLOR_ATLAS,
                    S.cjson({"family": fam, "ct": ct}), S.CODEC, payload, png,
                    cbk, "atlas",
                    {"family": fam, "ct": ct, "locale": LOCALE,
                     "ref": f"{fam}-{ct}.tif:g{ct}", "guid": f"g{ct}",
                     "bundle": "b1", "width": 4, "height": 4, "mode": "RGBA",
                     "pixel_sha256": pixel, "payload_sha256": payload,
                     "payload_size": len(png)})
                self.color_atlas_files[ct] = self.layout.blob_path(payload)
                self.color_atlas_pixels[ct] = pixel
        # per-card 挂接（已知卡型卡人口——单测里挂 C_BUILT/C_GOLD 两载卡）
        for cid in ("C_BUILT", "C_GOLD"):
            pk = S.plan_key(card_id=cid, locale=LOCALE, card_data_sha=f"ds-{cid}")
            conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                         "VALUES(?,?,?)", (pk, pik, "color"))

    def _write_blob_file(self, conn: sqlite3.Connection, ik: str, domain: str,
                         item: str, params: str, codec: str, payload_sha: str,
                         payload: bytes, blob_key: str, role: str,
                         manifest: dict) -> None:
        bp = self.layout.blob_path(
            payload_sha, ext=KC.BLOB_CODEC_EXT.get(codec, ".png"))
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_bytes(payload)
        conn.execute(
            "INSERT INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (ik, domain, item, params, codec, S.CODEC_VERSION,
             S.cjson(manifest), "ok", "asset", S.cjson([]),
             S.cjson({"fixture": ik[:16]}), NOW))
        conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                     "VALUES(?,?,?)", (ik, blob_key, role))
        conn.execute(
            "INSERT INTO blobs(blob_key,payload_sha256,size,codec,codec_version,"
            "last_used,created_at) VALUES(?,?,?,?,?,?,?)",
            (blob_key, payload_sha, len(payload), codec, S.CODEC_VERSION,
             NOW, NOW))


class WarmCase(unittest.TestCase):
    """每用例独立 fixture（tmp 目录 + 最小代库）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.fx = _Fixture(self.root)
        self.layout = self.fx.layout

    def _idx(self, **kw) -> SupplyIndex:
        idx = SupplyIndex(self.root, **kw)
        self.addCleanup(idx.close)
        return idx


class WarmHitPathTests(WarmCase):
    """plan/assemble 命中路径：PIL 产物与写入 blob 同图。"""

    def test_open_binds_generation_and_locale(self) -> None:
        idx = self._idx()
        self.assertEqual(idx.game_id, GID)
        self.assertEqual(idx.generation, f"gen-{GID}")
        self.assertEqual(idx.locale, LOCALE)
        self.assertIsNone(idx.health_error)
        self.assertEqual(idx.probe["quick_check"], "ok")
        self.assertEqual(sorted(idx.card_ids()), sorted(
            ["C_BUILT", "C_BUILT_2", "C_BADCODEC", "C_GOLD", "C_GAP",
             "C_ABSENT", "C_LOCMISS", "C_NOITEM", "C_SENT"]))

    def test_assemble_portrait_returns_written_image(self) -> None:
        idx = self._idx()
        img = idx.assemble_portrait("C_BUILT")
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (4, 4))
        self.assertEqual(img.mode, "RGBA")
        # 与写入 blob 同图：像素 sha 全等
        self.assertEqual(S.sha256_hex(img.tobytes()),
                         self.fx.pixel_shas["C_BUILT"])
        # plan 面：portrait item 命中、blob 账对齐
        plan = idx.plan("C_BUILT")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.status, "complete")
        self.assertEqual(plan.missing, [])
        it = next(i for i in plan.items if i.role == "portrait")
        self.assertEqual(it.payload_sha256, self.fx.payload_shas["C_BUILT"])
        self.assertEqual(it.blob_path, self.fx.blob_files["C_BUILT"])

    def test_assemble_card_bundle_includes_text(self) -> None:
        idx = self._idx()
        bundle = idx.assemble_card("C_BUILT")
        self.assertIn("portrait", bundle)
        self.assertIn("text", bundle)
        self.assertIsInstance(bundle["portrait"], Image.Image)
        self.assertEqual(bundle["text"]["fontdefs"], _TEXT_FONTDEFS)
        self.assertEqual(bundle["text"]["fonts"], {"ZhFont": _TTF_BYTES})
        # text 全域段进程内缓存一次（同对象）
        self.assertIs(bundle["text"], idx.text())

    def test_kit_six_faces_roundtrip_and_lru(self) -> None:
        idx = self._idx()
        self.assertEqual(idx.kit_frames(), ["ally"])
        kit = idx.kit("ally")
        self.assertEqual(sorted(kit), ["arrays", "hierarchy", "meta", "report",
                                       "textures", "ubertext"])
        self.assertEqual(kit["meta"]["frame"], "ally")
        self.assertEqual(kit["arrays"]["verts"].dtype, np.float32)
        self.assertEqual(kit["arrays"]["verts"].shape, (2, 3))
        self.assertEqual(sorted(kit["textures"]), ["tex0.png"])
        self.assertEqual(S.sha256_hex(kit["textures"]["tex0.png"].tobytes()),
                         S.sha256_hex(Image.new("RGBA", (3, 3),
                                                (9, 9, 9, 255)).tobytes()))
        # 卡不变项：进程内 LRU 按引用返回（同对象，非重解码）
        self.assertIs(idx.kit("ally"), kit)

    def test_kit_missing_frame_fails_loud(self) -> None:
        idx = self._idx()
        with self.assertRaises(SupplyMissingError) as cm:
            idx.kit("nope")
        self.assertIn("kit nope: item 缺失", str(cm.exception))


class WarmColorTests(WarmCase):
    """A4 color 域 warm 面：probe 同形（含键序）+ atlas LRU + 缺项 fail loud。"""

    def test_color_probe_shape_order_and_cache(self) -> None:
        idx = self._idx()
        probe = idx.color_probe()
        self.assertEqual(probe, _COLOR_PROBE, "probe 逐键逐槽相等（判据 1 面）")
        self.assertEqual(list(probe), list(_COLOR_PROBE),
                         "键序=落盘序（live 键序语义）")
        self.assertEqual(probe["minionCardTextures"][2], "",
                         "空占位槽原样保留（ColorType 下标对齐）")
        self.assertIs(idx.color_probe(), probe, "进程内缓存一次（同对象）")

    def test_color_probe_in_assemble_card_bundle(self) -> None:
        idx = self._idx()
        bundle = idx.assemble_card("C_BUILT")
        self.assertEqual(bundle["color"], _COLOR_PROBE,
                         "probe per-card 挂接→assemble 束随卡带 color")
        # 无 color 挂接卡（C_ABSENT 零期望形态）：束无 color 键
        self.assertNotIn("color", idx.assemble_card("C_ABSENT"))

    def test_color_atlas_roundtrip_lru_and_slots(self) -> None:
        idx = self._idx()
        img = idx.color_atlas("minionCardTextures", 0)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(S.sha256_hex(img.tobytes()),
                         self.fx.color_atlas_pixels[0])
        self.assertIs(idx.color_atlas("minionCardTextures", 0), img,
                      "共享域 LRU 按引用返回（color 入池）")
        self.assertEqual(idx.color_atlas_slots(),
                         [("minionCardTextures", 0), ("minionCardTextures", 7)])

    def test_color_atlas_missing_slots_fail_loud(self) -> None:
        idx = self._idx()
        with self.assertRaises(SupplyMissingError) as cm:
            idx.color_atlas("minionCardTextures", 3)     # 未建槽（cold 无行）
        self.assertIn("color.atlas minionCardTextures[3]", str(cm.exception))
        with self.assertRaises(SupplyMissingError):
            idx.color_atlas("factionIconMaterials", 0)   # 材质族（参数域外）

    def test_color_atlas_blob_tamper_corrupt_error(self) -> None:
        bp = self.fx.color_atlas_files[7]
        raw = bp.read_bytes()
        bp.write_bytes(raw[:-4] + b"XXXX")
        self.addCleanup(bp.write_bytes, raw)             # 还原（tmp 清理前）
        idx = self._idx()
        with self.assertRaises(SupplyBlobCorruptError):
            idx.color_atlas("minionCardTextures", 7)

    def test_color_probe_item_missing_fails_loud(self) -> None:
        conn = S.connect(self.fx.db)
        try:
            # 只删 items/item_blobs（plan_items 挂接行保留=plan 引用缺失 item 形态）
            conn.execute("DELETE FROM item_blobs WHERE item_key=?",
                         (self.fx.color_probe_key,))
            conn.execute("DELETE FROM items WHERE item_key=?",
                         (self.fx.color_probe_key,))
            conn.commit()
        finally:
            conn.close()
        idx = self._idx()
        with self.assertRaises(SupplyMissingError) as cm:
            idx.color_probe()
        self.assertIn("先跑全量 cold build", str(cm.exception))
        # 严格门同面：plan 引用缺失 item → assemble_card raise（不静默）
        with self.assertRaises(SupplyMissingError):
            idx.assemble_card("C_BUILT")


class WarmMissingTests(WarmCase):
    """缺项 fail loud 家族（类型 + message 点名）。"""

    def test_ghost_card_not_in_cards_table(self) -> None:
        idx = self._idx()
        with self.assertRaises(SupplyMissingError) as cm:
            idx.assemble_portrait("GHOST")
        self.assertIn("GHOST: 卡不在 cards 表", str(cm.exception))
        self.assertIn(cm.exception.missing[0], str(cm.exception))
        self.assertIsNone(idx.plan("GHOST"))

    def test_item_missing_in_plan_join(self) -> None:
        idx = self._idx()
        plan = idx.plan("C_NOITEM")
        self.assertEqual(plan.status, "partial")
        self.assertTrue(any("item 缺失" in m for m in plan.missing))
        with self.assertRaises(SupplyMissingError) as cm:
            idx.assemble_portrait("C_NOITEM")
        self.assertIn("item 缺失", str(cm.exception))

    def test_blob_file_missing(self) -> None:
        bp = self.fx.blob_files["C_BUILT"]
        saved = bp.read_bytes()
        self.addCleanup(lambda: (bp.parent.mkdir(parents=True, exist_ok=True),
                                 bp.write_bytes(saved)))
        bp.unlink()
        idx = self._idx()
        plan = idx.plan("C_BUILT")
        self.assertTrue(any("blob 文件缺失" in m for m in plan.missing))
        with self.assertRaises(SupplyMissingError) as cm:
            idx.assemble_portrait("C_BUILT")
        self.assertIn("blob 文件缺失", str(cm.exception))

    def test_unknown_codec_fails_loud(self) -> None:
        idx = self._idx()
        with self.assertRaises(SupplyMissingError) as cm:
            idx.assemble_portrait("C_BADCODEC")
        self.assertIn("未知 blob codec 'webp'", str(cm.exception))

    def test_blob_byte_tamper_corrupt_error(self) -> None:
        bp = self.fx.blob_files["C_BUILT"]
        saved = bp.read_bytes()
        self.addCleanup(bp.write_bytes, saved)
        bp.write_bytes(saved[:-1] + bytes([saved[-1] ^ 0xFF]))   # 翻转末字节
        idx = self._idx()
        with self.assertRaises(SupplyBlobCorruptError) as cm:
            idx.assemble_portrait("C_BUILT")
        exc = cm.exception
        # is-a SupplyMissingError（审计/CLI 同一响亮语义）
        self.assertIsInstance(exc, SupplyMissingError)
        self.assertEqual(exc.payload_sha, self.fx.payload_shas["C_BUILT"])
        self.assertEqual(exc.path, bp)
        self.assertIn("blob sha 不匹配", str(exc))
        self.assertIn(self.fx.payload_shas["C_BUILT"][:12], str(exc))

    def test_corrupt_db_health_error_is_loud(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            fx2 = _Fixture(Path(other))
            fx2.db.write_bytes(b"definitely not a sqlite database")
            idx = SupplyIndex(other, health_policy="full")
            self.addCleanup(idx.close)
            self.assertIsNotNone(idx.health_error)
            with self.assertRaises(SupplyIndexCorruptError):
                idx.conn


class WarmCheckAccountingTests(WarmCase):
    """check / fillable_missing 批量审计账。"""

    def test_check_hit_missing_absent(self) -> None:
        idx = self._idx()
        rep = idx.check(["C_BUILT", "C_GAP", "C_ABSENT", "GHOST"])
        self.assertEqual(rep["total"], 4)
        self.assertEqual(rep["hit"], 2)          # C_BUILT + C_ABSENT（数据缺席）
        self.assertEqual(rep["absent_portrait"], 1)
        self.assertEqual(rep["miss"], 2)
        self.assertEqual(rep["missing_cards"], ["GHOST: 卡不在 cards 表"])
        self.assertEqual(len(rep["missing_items"]), 1)
        # expected-vs-built 语义（返工 R1）：locator-ok 期望无产物点名 kind
        self.assertIn("C_GAP: 缺预期产物: portrait", rep["missing_items"][0])

    def test_check_golden_missing_counts(self) -> None:
        """golden 缺失与 portrait 同权入缺项账（P0-1 返工 R1；审计 CAP_000 固化）。"""
        self._delete_golden("C_GOLD")
        idx = self._idx()
        rep = idx.check(["C_GOLD"])
        self.assertEqual(rep["miss"], 1)
        self.assertEqual(len(rep["missing_items"]), 1)
        self.assertIn("C_GOLD: 缺预期产物: portrait_golden",
                      rep["missing_items"][0])

    def test_check_locator_missing_is_loud(self) -> None:
        """locator status=missing（ref 不可解）而无产物=locator 缺口（响亮清单）。"""
        idx = self._idx()
        rep = idx.check(["C_LOCMISS"])
        self.assertEqual(rep["miss"], 1)
        self.assertIn("C_LOCMISS: portrait locator 无产物（status=missing",
                      rep["missing_items"][0])

    def test_plan_expected_field_and_sentinel_role(self) -> None:
        """plan.expected 记期望集；哨兵行（expect::*）期望未建点名 role 入 missing。"""
        idx = self._idx()
        plan = idx.plan("C_GOLD")
        self.assertEqual(plan.expected, ["portrait", "portrait_golden"])
        self.assertEqual(plan.missing, [])
        self.assertEqual(plan.status, "complete")
        plan = idx.plan("C_SENT")
        self.assertIn("kit", plan.expected)
        self.assertTrue(any("C_SENT: 缺预期产物: kit" in m for m in plan.missing))
        self.assertEqual(plan.status, "partial")   # complete 降级（缺预期产物）

    def test_fillable_missing_sorting(self) -> None:
        idx = self._idx()
        rep = idx.fillable_missing(["C_GAP", "GHOST"])
        self.assertEqual(rep["fillable"], ["C_GAP"])      # locator ok → 可定向冷补
        self.assertEqual(rep["unfillable"], ["GHOST"])    # 无 locator → 不可补

    def _delete_golden(self, cid: str) -> None:
        """删某卡 golden 面（plan_items/items/item_blobs）——CAP_000 场景构造。"""
        ik = self.fx.golden_keys[cid]
        conn = S.connect(self.layout.gen_db(GID))
        try:
            conn.execute("DELETE FROM plan_items WHERE item_key=?", (ik,))
            conn.execute("DELETE FROM item_blobs WHERE item_key=?", (ik,))
            conn.execute("DELETE FROM items WHERE item_key=?", (ik,))
            conn.commit()
        finally:
            conn.close()


class WarmExpectedVsBuiltGateTests(WarmCase):
    """expected-vs-built 装配门（P0-1 返工 R1；审计 CAP_000 场景固化）。"""

    def _delete_golden(self, cid: str) -> None:
        ik = self.fx.golden_keys[cid]
        conn = S.connect(self.layout.gen_db(GID))
        try:
            conn.execute("DELETE FROM plan_items WHERE item_key=?", (ik,))
            conn.execute("DELETE FROM item_blobs WHERE item_key=?", (ik,))
            conn.execute("DELETE FROM items WHERE item_key=?", (ik,))
            conn.commit()
        finally:
            conn.close()

    def test_golden_locator_in_item_deleted_assemble_card_raises(self) -> None:
        """golden locator 在、golden item 删 → assemble_card 严格门点名缺 role。"""
        self._delete_golden("C_GOLD")
        idx = self._idx()
        plan = idx.plan("C_GOLD")
        self.assertTrue(any("portrait_golden" in m for m in plan.missing))
        with self.assertRaises(SupplyMissingError) as cm:
            idx.assemble_card("C_GOLD")
        self.assertIn("portrait_golden", str(cm.exception))
        self.assertEqual(idx.plan("C_GOLD").status, "partial")

    def test_allow_partial_true_passes_with_built_subset(self) -> None:
        """allow_partial=True 显式豁免：已建子集 + text 段照常出货。"""
        self._delete_golden("C_GOLD")
        idx = self._idx()
        bundle = idx.assemble_card("C_GOLD", allow_partial=True)
        self.assertIsInstance(bundle["portrait"], Image.Image)
        self.assertNotIn("portrait_golden", bundle)
        self.assertEqual(bundle["text"]["fonts"], {"ZhFont": _TTF_BYTES})

    def test_allow_partial_defaults_false(self) -> None:
        """allow_partial 缺省 False：缺预期产物必 fail loud（产品语义）。"""
        import inspect

        self.assertEqual(
            inspect.signature(SupplyIndex.assemble_card)
            .parameters["allow_partial"].default, False)
        idx = self._idx()
        with self.assertRaises(SupplyMissingError):
            idx.assemble_card("C_SENT")     # kit 哨兵期望未建 → 缺省即抛

    def test_blob_tamper_still_loud_under_partial_gate(self) -> None:
        """blob 篡改负例保持（allow_partial 门不弱化介质损坏响亮面）。"""
        bp = self.fx.blob_files["C_BUILT"]
        saved = bp.read_bytes()
        self.addCleanup(bp.write_bytes, saved)
        bp.write_bytes(saved[:-1] + bytes([saved[-1] ^ 0xFF]))
        idx = self._idx()
        with self.assertRaises(SupplyBlobCorruptError):
            idx.assemble_card("C_BUILT")
        with self.assertRaises(SupplyBlobCorruptError):
            idx.assemble_card("C_BUILT", allow_partial=True)


class WarmAbsentAttributionTests(WarmCase):
    """缺席归因四分类（Phase 5 返工 R2）：account_for_cards 判据与期望面同源
    （真机 37k full 代缺席账=7,161 expectationless + 12 locator_missing 同构）+
    期望为零卡 plan/assemble 语义钉死（complete 可达、零 raise——缺席合法形态
    是 R2 门语义的事实基础）。"""

    def test_four_category_attribution(self) -> None:
        from eidolon.core.supply_index.warm import account_for_cards

        idx = self._idx()
        acct = account_for_cards(idx.conn, idx.card_ids() + ["GHOST"])
        # ok=C_BUILT/C_BUILT_2/C_GOLD/C_BADCODEC（DB 面期望全 built；BADCODEC
        # 的解码红在 warm assemble 面，归因账只看期望账——integrity/verify 域）
        self.assertEqual(acct["counts"]["ok"], 4)
        self.assertIn("C_BUILT", acct["ok"])
        self.assertIn("C_GOLD", acct["ok"])
        # gap：C_GAP（locator ok 无 item）/ C_SENT（kit 哨兵）/ C_NOITEM（坏引用）
        self.assertEqual(acct["missing_gap"], ["C_GAP", "C_NOITEM", "C_SENT"])
        # absent 两类（可归因数据缺席）：无任何 locator / locator status≠ok
        self.assertEqual(acct["absent_expectationless"], ["C_ABSENT"])
        self.assertEqual(acct["absent_locator_missing"], ["C_LOCMISS"])
        # anomaly 单列（not_in_cards）
        self.assertEqual(acct["anomaly"], {"not_in_cards": ["GHOST"]})
        self.assertEqual(acct["counts"]["missing_gap"], 3)
        self.assertEqual(acct["counts"]["anomaly_total"], 1)
        self.assertEqual(acct["samples"]["absent_locator_missing"], ["C_LOCMISS"])

    def test_expectationless_plan_status_complete(self) -> None:
        """期望为零卡 status=complete（P2 明确语义：expected ∅ ⊆ built 恒真）。"""
        conn = S.connect(self.layout.gen_db(GID))
        try:
            for cid in ("C_ABSENT", "C_LOCMISS"):
                pk = S.plan_key(card_id=cid, locale=LOCALE,
                                card_data_sha=f"ds-{cid}")
                conn.execute(
                    "INSERT INTO plans(plan_key,card_id,options_json,status,"
                    "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
                    (pk, cid, "{}", "complete", S.PLAN_VERSION, f"ds-{cid}", NOW))
            conn.commit()
        finally:
            conn.close()
        idx = self._idx()
        for cid in ("C_ABSENT", "C_LOCMISS"):
            self.assertEqual(idx.plan(cid).status, "complete", cid)

    def test_item_without_blob_row_is_gap(self) -> None:
        """P2 审计：items 行在而 item_blobs 链断=不可装配缺口（不静默通过）。"""
        from eidolon.core.supply_index.warm import account_for_cards

        conn = S.connect(self.layout.gen_db(GID))
        try:
            pk = S.plan_key(card_id="C_BLOBGAP", locale=LOCALE,
                            card_data_sha="ds-C_BLOBGAP")
            conn.execute(
                "INSERT INTO cards(card_id,dbf_id,carddef_ref,carddef_guid,"
                "carddef_bundle,carddef_cab,carddef_path_id,data_sha) "
                "VALUES('C_BLOBGAP',NULL,'','','','',0,'ds-C_BLOBGAP')")
            conn.execute(
                "INSERT INTO plans(plan_key,card_id,options_json,status,"
                "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
                (pk, "C_BLOBGAP", "{}", "complete", S.PLAN_VERSION,
                 "ds-C_BLOBGAP", NOW))
            conn.execute(
                "INSERT INTO items(item_key,domain,item,params_json,codec,"
                "codec_version,manifest_json,status,source_kind,source_json,"
                "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ("ik-blobgap", S.DOMAIN, S.ITEM_PORTRAIT,
                 S.cjson({"card_id": "C_BLOBGAP", "kind": "portrait"}),
                 S.CODEC, S.CODEC_VERSION,
                 S.cjson({"card_id": "C_BLOBGAP", "kind": "portrait",
                          "locale": LOCALE}),
                 "ok", "asset", "[]", S.cjson({"portrait": "f" * 64}), NOW))
            conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                         "VALUES(?,?,?)", (pk, "ik-blobgap", "portrait"))
            conn.commit()
            acct = account_for_cards(conn, ["C_BLOBGAP"])
            self.assertEqual(acct["missing_gap"], ["C_BLOBGAP"])
            comp = S.expected_vs_built(conn)
            self.assertIn({"card_id": "C_BLOBGAP", "role": "portrait"},
                          comp["missing_sample"])
        finally:
            conn.close()
        idx = self._idx()
        plan = idx.plan("C_BLOBGAP")
        self.assertTrue(plan.missing)          # warm 侧同判（blob 行缺失点名）
        with self.assertRaises(SupplyMissingError):
            idx.assemble_card("C_BLOBGAP")

    def test_expectationless_plan_assemble_no_raise(self) -> None:
        """期望为零卡：plan.expected==∅、plan.missing==∅、assemble_card 不 raise
        （产物=零 items + text 段——缺席合法形态）。"""
        idx = self._idx()
        for cid in ("C_ABSENT", "C_LOCMISS"):
            plan = idx.plan(cid)
            self.assertEqual(plan.expected, [], cid)
            self.assertEqual(plan.missing, [], cid)
            bundle = idx.assemble_card(cid)
            self.assertEqual(sorted(bundle), ["text"], cid)
            self.assertEqual(bundle["text"]["fonts"], {"ZhFont": _TTF_BYTES})


class SelfhealEnsureIndexTests(unittest.TestCase):
    """selfheal.ensure_index 无现行代端到端（Phase 5 审计 P2）。

    - 非 auto：current.json 缺失 / 指代库缺失 → 干净 SupplyIndexCorruptError
      「先冷建」（不裸 FileNotFoundError）；
    - auto：同一形态走 L1 全量重建编排（cold.build 打桩落一个合法代），返回
      重建后句柄 + l1_health 记 no-current。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _fake_build(self, cache_root, **kw):
        lay = SupplyLayout(cache_root)
        gid = "autogen"
        db = lay.gen_db(gid)
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = S.connect(db)
        try:
            S.init_schema(conn)
            conn.executemany("INSERT INTO meta(key,value) VALUES(?,?)",
                             [("game_id", gid), ("locale", LOCALE)])
            conn.commit()
        finally:
            conn.close()
        lay.write_current({"game_id": gid, "generation": f"gen-{gid}",
                           "locale": LOCALE, "full_build": True})
        return {"mode": "full", "game_id": gid, "items": 0, "blobs": 0,
                "wall_s": 0.0}

    def test_no_current_non_auto_is_clean_corrupt_error(self) -> None:
        from eidolon.core.supply_index.selfheal import ensure_index

        with self.assertRaises(SupplyIndexCorruptError) as cm:
            ensure_index(self.root, game=Path("game-root"), locale=LOCALE,
                         auto=False)
        self.assertIn("无现行代", str(cm.exception))
        self.assertIn("先冷建", str(cm.exception))

    def test_no_current_auto_rebuilds(self) -> None:
        from unittest import mock

        from eidolon.core.supply_index.selfheal import ensure_index

        fake_cold = mock.Mock(build=self._fake_build)
        with mock.patch.dict(
                "sys.modules",
                {"eidolon.core.supply_index.cold": fake_cold}):
            idx, acct = ensure_index(self.root, game=Path("game-root"),
                                     locale=LOCALE, auto=True)
        self.addCleanup(idx.close)
        self.assertTrue(acct["l1_corrupt_detected"])
        self.assertTrue(acct["l1_rebuilt"])
        self.assertIn("no-current", acct["l1_health"])
        self.assertEqual(idx.generation, "gen-autogen")
        self.assertEqual(idx.locale, LOCALE)
        self.assertEqual(idx.conn.execute(
            "SELECT COUNT(*) FROM cards").fetchone()[0], 0)

    def test_current_points_missing_db_auto_rebuilds(self) -> None:
        from unittest import mock

        from eidolon.core.supply_index.selfheal import ensure_index

        layout = SupplyLayout(self.root)
        layout.write_current({"game_id": "gone", "generation": "gen-gone",
                              "locale": LOCALE})
        fake_cold = mock.Mock(build=self._fake_build)
        with mock.patch.dict(
                "sys.modules",
                {"eidolon.core.supply_index.cold": fake_cold}):
            idx, acct = ensure_index(self.root, game=Path("game-root"),
                                     locale=LOCALE, auto=True)
        self.addCleanup(idx.close)
        self.assertTrue(acct["l1_rebuilt"])
        self.assertIn("no-current", acct["l1_health"])
        self.assertEqual(idx.generation, "gen-autogen")


class WarmHealthStampTests(WarmCase):
    """health_policy 三档与 stamp 语义。"""

    def test_stamp_miss_then_hit(self) -> None:
        idx1 = SupplyIndex(self.root)
        self.addCleanup(idx1.close)
        self.assertEqual(idx1.probe["stamp"], "miss")
        self.assertEqual(idx1.probe["quick_check"], "ok")
        idx1.close()
        idx2 = SupplyIndex(self.root)
        self.addCleanup(idx2.close)
        self.assertEqual(idx2.probe["stamp"], "hit")
        self.assertEqual(idx2.probe["quick_check"], "skipped_stamp")

    def test_stamp_identity_mismatch_on_mtime_change(self) -> None:
        SupplyIndex(self.root).close()               # 先写 stamp
        db = self.layout.gen_db(GID)
        st = db.stat()
        os.utime(db, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        idx = SupplyIndex(self.root)
        self.addCleanup(idx.close)
        self.assertEqual(idx.probe["stamp"], "identity_mismatch")
        self.assertEqual(idx.probe["quick_check"], "ok")   # 重检通过

    def test_stamp_bad_version(self) -> None:
        SupplyIndex(self.root).close()
        p = self.layout.health_stamp_path(GID)
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["v"] = 99
        p.write_text(json.dumps(doc), encoding="utf-8")
        idx = SupplyIndex(self.root)
        self.addCleanup(idx.close)
        self.assertEqual(idx.probe["stamp"], "bad_version")
        self.assertEqual(idx.probe["quick_check"], "ok")

    def test_stamp_wal_frames_forces_recheck(self) -> None:
        idx0 = SupplyIndex(self.root)
        self.addCleanup(idx0.close)
        db = self.layout.gen_db(GID)
        wal = Path(str(db) + "-wal")
        wal.write_bytes(b"\x00" * 32)
        self.addCleanup(wal.unlink)
        self.assertEqual(idx0._stamp_probe(db.stat()), ("wal_frames", ""))

    def test_skip_policy_and_invalid_policy(self) -> None:
        idx = self._idx(health_policy="skip")
        self.assertEqual(idx.probe["quick_check"], "skipped_policy")
        with self.assertRaises(ValueError):
            SupplyIndex(self.root, health_policy="nope")


class WarmGenBindingTests(WarmCase):
    """gen= 绑代演练面 + current.json 缺失语义。"""

    def test_gen_binding_skips_current_json(self) -> None:
        self.layout.current_json.unlink()
        for gen in (GID, f"gen-{GID}"):
            with self.subTest(gen=gen):
                idx = SupplyIndex(self.root, gen=gen)
                self.addCleanup(idx.close)
                self.assertEqual(idx.game_id, GID)
                self.assertEqual(idx.locale, LOCALE)      # 缺省从代库 meta 读
                self.assertEqual(idx.assemble_portrait("C_BUILT").size, (4, 4))

    def test_missing_current_json_is_loud(self) -> None:
        self.layout.current_json.unlink()
        with self.assertRaises(FileNotFoundError) as cm:
            SupplyIndex(self.root)
        self.assertIn("无 current.json", str(cm.exception))

    def test_gen_db_missing_is_loud(self) -> None:
        with self.assertRaises(FileNotFoundError) as cm:
            SupplyIndex(self.root, gen="no-such-gen")
        self.assertIn("gen 代库缺失", str(cm.exception))


def _bench_fixture(root: Path) -> SupplyLayout:
    """bench 专用最小代库（无坏 codec 面）：C1=有产物、C2=期望缺口（locator ok
    无 item）、C3=数据缺席（零期望，装配空）。"""
    layout = SupplyLayout(root)
    db = layout.gen_db(GID)
    db.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (4, 4), (1, 2, 3, 255))
    png = _encode_png(img)
    pixel_sha = S.sha256_hex(img.tobytes())
    payload_sha = S.sha256_hex(png)
    content = {"carddef": "cd-C1", "portrait": pixel_sha}
    ik = S.item_key(card_id="C1", kind="portrait", locale=LOCALE, premium="",
                    content_inputs=content)
    bk = S.blob_key(portrait_content_sha=pixel_sha)
    bp = layout.blob_path(payload_sha)
    bp.parent.mkdir(parents=True, exist_ok=True)
    bp.write_bytes(png)
    pk1 = S.plan_key(card_id="C1", locale=LOCALE, card_data_sha="ds-C1")
    pk2 = S.plan_key(card_id="C2", locale=LOCALE, card_data_sha="ds-C2")
    conn = S.connect(db)
    try:
        S.init_schema(conn)
        conn.executemany("INSERT INTO meta(key,value) VALUES(?,?)",
                         [("game_id", GID), ("locale", LOCALE),
                          ("full_build", "0")])
        for cid in ("C1", "C2", "C3"):
            conn.execute(
                "INSERT INTO cards(card_id,dbf_id,carddef_ref,carddef_guid,"
                "carddef_bundle,carddef_cab,carddef_path_id,data_sha) "
                "VALUES(?,NULL,'','','','',0,?)", (cid, f"ds-{cid}"))
        for cid in ("C1", "C2"):
            conn.execute(
                "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
                "bundle,cab,path_id,status,source_json) VALUES(?,"
                "'portrait',?,?,'','r','g','b1','',0,'ok','{}')",
                (1 if cid == "C1" else 2, cid, LOCALE))
        conn.execute(
            "INSERT INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (ik, S.DOMAIN, S.ITEM_PORTRAIT,
             S.cjson({"card_id": "C1", "kind": "portrait"}), S.CODEC,
             S.CODEC_VERSION, S.cjson({"payload_sha256": payload_sha}), "ok",
             "asset", S.cjson([]), S.cjson(content), NOW))
        conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                     "VALUES(?,?,?)", (ik, bk, "portrait"))
        conn.execute(
            "INSERT INTO blobs(blob_key,payload_sha256,size,codec,codec_version,"
            "last_used,created_at) VALUES(?,?,?,?,?,?,?)",
            (bk, payload_sha, len(png), S.CODEC, S.CODEC_VERSION, NOW, NOW))
        conn.execute(
            "INSERT INTO plans(plan_key,card_id,options_json,status,"
            "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
            (pk1, "C1", S.cjson({}), "complete", S.PLAN_VERSION, "ds-C1", NOW))
        conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                     "VALUES(?,?,?)", (pk1, ik, "portrait"))
        conn.execute(
            "INSERT INTO plans(plan_key,card_id,options_json,status,"
            "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
            (pk2, "C2", S.cjson({}), "partial", S.PLAN_VERSION, "ds-C2", NOW))
        conn.commit()
    finally:
        conn.close()
    layout.write_current({"game_id": GID, "generation": f"gen-{GID}",
                          "locale": LOCALE, "full_build": False,
                          "updated_at": NOW})
    return layout


class BenchWarmFullPartialTests(unittest.TestCase):
    """bench_warm_full 缺席归因口径（P1-4 返工 R1 + R2 对齐）：partial 显式标注 +
    吞吐分母=可装配卡（ok 卡）；absent 两类单列计数不算失败——full 代且
    gap==0 → partial=false。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.layout = _bench_fixture(self.root)

    def _set_full(self, v: str) -> None:
        conn = S.connect(self.layout.gen_db(GID))
        try:
            conn.execute("INSERT OR REPLACE INTO meta(key,value) "
                         "VALUES('full_build',?)", (v,))
            conn.commit()
        finally:
            conn.close()

    def test_partial_annotation_and_denominator(self) -> None:
        from eidolon.core.supply_index.bench import bench_warm_full

        out = bench_warm_full(self.root)
        # full_build=0 → partial；吞吐分母=可装配卡（仅 C1；C2 期望缺口、
        # C3 零期望数据缺席——都不进分母）
        self.assertTrue(out["partial"])
        self.assertEqual(out["n_samples"], 1)
        self.assertEqual(out["empty_plan_cards"], 1)      # C3（缺席合法单列）
        self.assertEqual(out["accounted_absent"],
                         {"expectationless": 1, "locator_missing": 0})
        self.assertEqual(out["missing_gap"], 1)           # C2（缺口另账）
        self.assertGreater(out["throughput_cards_per_s"], 0)

    def test_full_absent_cards_not_partial(self) -> None:
        """full 代 + 缺席可归因（C2 locator 删→无美术形态、C3 零期望）→
        partial=false（R2：缺席 ≠ 失败，吞吐分母=ok 卡）。"""
        from eidolon.core.supply_index.bench import bench_warm_full

        self._set_full("1")
        conn = S.connect(self.layout.gen_db(GID))
        try:
            conn.execute("DELETE FROM locators WHERE subject='C2'")
            conn.commit()
        finally:
            conn.close()
        out = bench_warm_full(self.root)
        self.assertFalse(out["partial"])
        self.assertEqual(out["missing_gap"], 0)
        self.assertEqual(out["empty_plan_cards"], 2)
        self.assertEqual(out["accounted_absent"],
                         {"expectationless": 2, "locator_missing": 0})
        self.assertEqual(out["n_samples"], 1)

    def test_full_gap_forces_partial(self) -> None:
        """full 代 + 期望缺口（C2 locator ok 无 item）→ partial=true（不可归因
        缺口才红）。"""
        from eidolon.core.supply_index.bench import bench_warm_full

        self._set_full("1")
        out = bench_warm_full(self.root)
        self.assertTrue(out["partial"])
        self.assertEqual(out["missing_gap"], 1)
        self.assertEqual(out["missing_gap_cards"], ["C2"])
        self.assertEqual(out["empty_plan_cards"], 1)      # C3 缺席单列


class WarmImportCleanlinessTests(unittest.TestCase):
    """import 卫生（子进程机器面）：warm 全链不触 UnityPy 族与本包 UnityPy 面。"""

    def test_warm_import_chain_has_no_unitypy(self) -> None:
        code = (
            "import sys, json; "
            "import eidolon.core.supply_index.warm; "
            "import eidolon.core.supply_index.kit_codec; "
            "import eidolon.core.supply_index.text_codec; "
            "import eidolon.core.supply_index.gems_codec; "
            "banned_prefix = ('UnityPy', 'clr', 'texture2ddecoder',"
            " 'eidolon.core.supply_index.cold',"
            " 'eidolon.core.supply_index.kit_extract',"
            " 'eidolon.core.supply_index.text_extract',"
            " 'eidolon.core.supply_index.wm_extract',"
            " 'eidolon.core.supply_index.selfheal'); "
            "print(json.dumps(sorted(m for m in sys.modules "
            "if m.startswith(banned_prefix))))"
        )
        p = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, cwd=str(_REPO), timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
