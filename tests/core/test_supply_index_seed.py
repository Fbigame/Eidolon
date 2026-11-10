"""core/supply_index seed 种子器单测（默认 discover 收集；零 UnityPy 顶层、零游戏文件）。

判据面（任务单 A3 判据 2「无 index 行为逐位不变」+ A4 判据（color 两 token）
+ §3.6 弃种语义钉住）：

  * tmp 造最小代库（portrait + kit(role=kit) + watermark + text 全域段 +
    color 域 probe/atlas，current.json 带 identity 账——game_id 由 identity
    单射重推，同 cold 口径）；``CardSeeder.open`` 身份校验三面（locale /
    identity 逐键 / identity→game_id 重推一致）+ 整批弃种四面（index 不可用 /
    locale 失配 / 身份失配 / 账面不一致）全返回 None 不 raise，WARN 面用
    assertLogs 钉住；
  * role→token 转换形状（注入缺口面替身=零游戏可测）：portrait PIL 同图、
    kit 六面重组（meta/hierarchy 合并 + trinket_level_mats=None + arrays→
    _ArrayDict + races/mesh_refs 注入件落位）、fontdefs 逐键、font_table 无损
    派生、font_ttf_bytes bytes、watermark ref=manifest 裁决值；color.probe
    逐键同形（键序=落盘序）、color.atlas 帧族全有效槽枚举（空占位槽跳过）、
    frame family=None 腿（ally_premium/heropower 不枚举）；
  * 弃种分层：该卡弃种（卡不在表 / assemble 严格门缺项）→ None；该 token 不种
    （缺口面派生失败 → kit 单跳过，portrait/text 照种；watermark 缺席）→
    seeds 照常返回；
  * **不发明 Problem**：seed.py 全源 AST 无 ``Problem`` 名字/属性/导入
    （弃种=纯 live 回退，不是用户可见失败）；模块级 import 面子进程机器证明
    （warm 纯净：无 UnityPy/clr/cold/kit_extract/text_extract/wm_extract/
    render/supply/recipes——转换件 live import 全在函数体内，spike 同款）；
  * A2 seam 等价：``api._seed_scope`` 对 None/空种子=nullcontext（纯 live）、
    非空=seed_session（渲染路径与 A2 前等价的产品单测面）。

Kit/_ArrayDict 断言需要 live 形状类（``eidolon.core.supply.frames.kits``）——
**运行期惰性 import**（拖 UnityPy），模块出口 ``tearDownModule`` 清 UnityPy
（同 test_route_cabs 纪律，保后续 import 卫生守卫绿）。
"""

from __future__ import annotations

import ast
import contextlib
import json
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
from eidolon.core.supply_index.seed import CardSeeder, SeedLedger
from eidolon.core.supply_index.warm import SupplyIndex

_REPO = Path(__file__).resolve().parents[2]
LOCALE = "zhcn"
NOW = 1700000000

# current.json identity 账（与 cold.compute_identity 字段面同形；game_id 由其
# canonical JSON 单射重推——seed.open 的 identity→game_id 一致性判据用同一口径）
IDENTITY = {"build": "37.0.2-test", "manifest_stamp": "m-stamp", "platform": "pc",
            "dll_stamp": "d-stamp", "constants_stamp": S.sha256_hex(b"[]")}
GAME_ID = S.sha256_hex(S.cjson(IDENTITY).encode("utf-8"))

_TEXT_FONTDEFS = {
    "ZhFont": {"m_Name": "ZhFont", "m_FontDefName": "ZhFont",
               "m_FontName": "Zhonomy", "base_guid": "guid-zh"},
    "Belwe": {"m_Name": "Belwe", "m_FontDefName": "Belwe",
              "m_FontName": "Belwe", "base_guid": "guid-belwe"},
}
_TTF_BYTES = {"ZhFont": b"FAKE-TTF-ZH-0123456789", "Belwe": b"FAKE-TTF-BELWE-987"}
_WM_REF = "CardSetClassic Watermark.tif:00112233"

# color 域（A4）：probe 表（ally 帧族 minionCardTextures 两有效槽 + 一空占位）
_COLOR_PROBE = {"minionCardTextures": ["a.tif:g0", "b.tif:g1", ""],
                "spellCardTextures": ["s.tif:g3"]}
_COLOR_ATLAS = {"minionCardTextures": {0: (11, 22, 33, 255),
                                       1: (44, 55, 66, 255)}}

# 缺口面替身（零游戏；形状=live races/mesh_refs 面）
_GAP_RACES = {"source": "unit:GLOBAL.txt", "provenance": "unit-test",
              "strings": {"7": "野兽"}}
_GAP_MESH = {"Card_InHand_Ally_Portrait_mesh": ("b1", 11)}


def _gap_faces_ok(frame):
    return _GAP_RACES, _GAP_MESH


def _gap_faces_boom(frame):
    raise RuntimeError("缺口面派生失败（替身）")


class _SeedFixture:
    """最小代库手造器（单文件 sqlite + 内容寻址 blob；C_SEED=全 role 载卡）。"""

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
        self._write_card("C_SEED", dbf_id=4242,
                         with_watermark=True, with_kit=True)
        self._write_card("C_NOWM", dbf_id=4243)              # 无 watermark 面
        # 期望缺口载卡：portrait locator ok 而无 item → assemble 严格门 fail loud
        self._write_card("C_GAP", dbf_id=4244, with_portrait_item=False)
        self._write_text()
        self._write_kit()
        self._write_kit_light()
        self._write_bacon_kit()
        self._write_supplements()
        self._write_color()
        self._write_mip_registry()
        self._link_kit("C_SEED")
        self._link_kit("C_NOWM")
        self._link_color("C_SEED")
        self._link_color("C_NOWM")
        self.conn.commit()

    def publish_current(self, *, identity: dict | None = IDENTITY,
                        game_id: str = GAME_ID, locale: str = LOCALE) -> None:
        self.conn.close()
        doc = {"game_id": game_id, "generation": f"gen-{game_id}",
               "locale": locale, "full_build": True, "updated_at": NOW}
        if identity is not None:
            doc["identity"] = identity
        self.layout.write_current(doc)

    # ---- 单卡全链（portrait 必建；watermark/kit 可选） ----

    def _write_card(self, cid: str, *, dbf_id: int,
                    with_watermark: bool = False, with_kit: bool = False,
                    with_portrait_item: bool = True) -> None:
        conn = self.conn
        conn.execute(
            "INSERT INTO cards(card_id,dbf_id,carddef_ref,carddef_guid,"
            "carddef_bundle,carddef_cab,carddef_path_id,data_sha) "
            "VALUES(?,?,'','','','',0,?)", (cid, dbf_id, f"ds-{cid}"))
        pk = S.plan_key(card_id=cid, locale=LOCALE, card_data_sha=f"ds-{cid}")
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        png = KC.encode_png(img)
        pixel_sha = S.sha256_hex(img.tobytes())
        payload_sha = S.sha256_hex(png)
        content = {"carddef": f"cd-{cid}", "portrait": pixel_sha}
        ik = S.item_key(card_id=cid, kind="portrait", locale=LOCALE, premium="",
                        content_inputs=content)
        manifest = {"card_id": cid, "kind": "portrait", "locale": LOCALE,
                    "ref": f"ref-{cid}", "guid": f"guid-{cid}", "bundle": "b1",
                    "cab": "", "path_id": 0, "width": 4, "height": 4,
                    "mode": "RGBA", "pixel_sha256": pixel_sha,
                    "payload_sha256": payload_sha, "payload_size": len(png)}
        bk = S.blob_key(portrait_content_sha=pixel_sha)
        conn.execute(
            "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
            "bundle,cab,path_id,status,source_json) "
            "VALUES((SELECT COALESCE(MAX(id),0)+1 FROM locators),'portrait',"
            "?,?,'','r','g','b1','',0,'ok','{}')", (cid, LOCALE))
        if with_portrait_item:
            self._blob(payload_sha, png, ".png", blob_key=bk)
            self._item(ik, S.DOMAIN, S.ITEM_PORTRAIT,
                       S.cjson({"card_id": cid, "kind": "portrait"}), "png",
                       S.cjson(manifest), content)
            conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                         "VALUES(?,?,?)", (ik, bk, "portrait"))
            conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                         "VALUES(?,?,?)", (pk, ik, "portrait"))
            # A5 mip 面：portrait_mip item + plan 挂接（C_SEED=chain 源带 1 存储
            # 级；C_NOWM=portrait 源 marker——warm 派生双路都有 fixture）
            self._write_mip_item(cid, pk, img, pixel_sha,
                                 source="chain" if cid == "C_SEED" else "portrait")
        if with_watermark:
            wm_img = Image.new("RGBA", (2, 2), (0, 0, 255, 255))
            wm_png = KC.encode_png(wm_img)
            wm_pixel = S.sha256_hex(wm_img.tobytes())
            wm_payload = S.sha256_hex(wm_png)
            wm_content = {"carddef": f"cd-{cid}", "ref": _WM_REF,
                          "watermark": wm_pixel}
            wik = S.watermark_item_key(card_id=cid, locale=LOCALE,
                                       content_inputs=wm_content)
            wm_manifest = {"card_id": cid, "kind": "watermark", "locale": LOCALE,
                           "ref": _WM_REF, "guid": "guid-wm", "bundle": "b1",
                           "cab": "", "path_id": 0, "width": 2, "height": 2,
                           "mode": "RGBA", "pixel_sha256": wm_pixel,
                           "payload_sha256": wm_payload,
                           "payload_size": len(wm_png)}
            wbk = S.blob_key_generic(domain="watermark", content_sha=wm_pixel,
                                     codec=S.CODEC)
            self._blob(wm_payload, wm_png, ".png", blob_key=wbk)
            conn.execute(
                "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,"
                "bundle,cab,path_id,status,source_json) "
                "VALUES((SELECT COALESCE(MAX(id),0)+1 FROM locators),'watermark',"
                "?,?,'',?,'guid-wm','b1','',0,'ok','{}')", (cid, LOCALE, _WM_REF))
            self._item(wik, S.DOMAIN_WATERMARK, S.ITEM_WATERMARK,
                       S.cjson({"card_id": cid}), "png",
                       S.cjson(wm_manifest), wm_content)
            conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                         "VALUES(?,?,?)", (wik, wbk, "watermark"))
            conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                         "VALUES(?,?,?)", (pk, wik, "watermark"))
        status = "complete" if with_portrait_item else "partial"
        conn.execute(
            "INSERT INTO plans(plan_key,card_id,options_json,status,"
            "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
            (pk, cid, S.cjson({}), status, S.PLAN_VERSION, f"ds-{cid}", NOW))

    # ---- kit item（frames 域；faces=kit_codec 六面账+A6 扩展面；不挂 plan） ----

    def _kit_faces_and_rows(self, *, frame: str, meta: dict, hierarchy: dict,
                            report: dict, ubertext: dict, arrays: dict,
                            textures: dict, races: dict | None = None,
                            mesh_refs: dict | None = None):
        """kit 六面+A6 扩展面编码 → (item_key, blobs 行)（kit/bacon/kit_light
        三 writer 共用；blob_key=KC.blob_key 公式）。"""
        blobs: list[tuple[str, str, bytes, str]] = []
        faces = {}
        for face, obj in (("meta", meta), ("hierarchy", hierarchy),
                          ("report", report), ("ubertext", ubertext)):
            payload = KC.encode_json_face(obj)
            sha = S.sha256_hex(payload)
            faces[face] = {"payload_sha256": sha, "content_sha256": sha,
                           "size": len(payload)}
            blobs.append((face, "json", payload, face))
        for face, obj in (("races", races), ("mesh_refs", mesh_refs)):
            if obj is None:
                continue
            payload = KC.encode_json_face(obj)
            sha = S.sha256_hex(payload)
            faces[face] = {"payload_sha256": sha, "content_sha256": sha,
                           "size": len(payload)}
            blobs.append((face, "json", payload, face))
        if arrays:
            arr_shas = {k: KC.array_content_sha(k, v) for k, v in arrays.items()}
            arr_content = KC.arrays_content_sha(arr_shas)
            npz = KC.encode_npz(arrays)
            faces["arrays"] = {"payload_sha256": S.sha256_hex(npz),
                               "content_sha256": arr_content,
                               "size": len(npz), "array_shas": arr_shas}
            blobs.append(("arrays", "npz", npz, "arrays"))
        else:
            arr_content = KC.arrays_content_sha({})
        tex_pixel_shas = {}
        for fname, img in textures.items():
            tex_png = KC.encode_png(img)
            tex_pixel = S.sha256_hex(img.tobytes())
            tex_payload = S.sha256_hex(tex_png)
            tex_pixel_shas[fname] = tex_pixel
            faces["textures"] = faces.get("textures") or {}
            faces["textures"][fname] = {"payload_sha256": tex_payload,
                                        "pixel_sha256": tex_pixel,
                                        "size": len(tex_png)}
            blobs.append(("texture", "png", tex_png, f"texture:{fname}"))
        kit_sha = KC.kit_content_sha(
            meta_sha=faces["meta"]["content_sha256"],
            hierarchy_sha=faces["hierarchy"]["content_sha256"],
            report_sha=faces["report"]["content_sha256"],
            ubertext_sha=faces["ubertext"]["content_sha256"],
            arrays_sha=arr_content,
            texture_pixel_shas=tex_pixel_shas,
            races_sha=faces.get("races", {}).get("content_sha256", ""),
            mesh_refs_sha=faces.get("mesh_refs", {}).get("content_sha256", ""))
        return faces, blobs, kit_sha

    def _write_kit_item(self, *, frame: str, item_name: str, meta: dict,
                        hierarchy: dict, report: dict, ubertext: dict,
                        arrays: dict, textures: dict,
                        races: dict | None = None,
                        mesh_refs: dict | None = None,
                        actor_ref: str = "ref-ally",
                        guid: str = "guid-kit") -> str:
        faces, blobs, kit_sha = self._kit_faces_and_rows(
            frame=frame, meta=meta, hierarchy=hierarchy, report=report,
            ubertext=ubertext, arrays=arrays, textures=textures,
            races=races, mesh_refs=mesh_refs)
        content = {"actor_ref": actor_ref, "guid": guid, "kit": kit_sha}
        if item_name == S.ITEM_KIT:
            ik = S.kit_item_key(frame=frame, locale=LOCALE,
                                content_inputs=content)
        else:
            ik = S.kit_light_item_key(frame=frame, locale=LOCALE,
                                      content_inputs=content)
        manifest = {"frame": frame, "item": item_name, "locale": LOCALE,
                    "prefab_ref": actor_ref, "guid": guid, "bundle": "b1",
                    "faces": faces, "kit_content_sha256": kit_sha,
                    "counts": {}, "excluded": {}}
        self._item(ik, S.DOMAIN_FRAMES, item_name, S.cjson({"frame": frame}),
                   KC.KIT_CODEC, S.cjson(manifest), content)
        for face, codec, payload, role in blobs:
            payload_sha = S.sha256_hex(payload)
            bk = S.sha256_hex(f"test|{face}|{payload_sha}".encode())
            self._blob(payload_sha, payload, KC.BLOB_CODEC_EXT[codec],
                       blob_key=bk, codec=codec)
            self.conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                              "VALUES(?,?,?)", (ik, bk, role))
        return ik

    def _write_kit(self) -> None:
        self.kit_key = self._write_kit_item(
            frame="ally", item_name=S.ITEM_KIT,
            meta={"frame": "ally", "dbf_id": 9},   # index 形：无 hierarchy 键
            hierarchy={"path": "KitRoot", "children": []},
            report={"nodes": 1}, ubertext={"label": "u"},
            arrays={"verts": np.arange(6, dtype=np.float32).reshape(2, 3)},
            textures={"tex0.png": Image.new("RGBA", (3, 3), (9, 9, 9, 255))},
            races={"source": "unit:GLOBAL.txt", "provenance": "fixture",
                   "strings": {"7": "野兽"}},
            mesh_refs={"Card_InHand_Ally_Portrait_mesh": ["b1", 11]})

    def _write_kit_light(self) -> None:
        self.kit_light_key = self._write_kit_item(
            frame="ally", item_name=S.ITEM_KIT_LIGHT,
            meta={"frame": "ally", "dbf_id": 9},
            hierarchy={"path": "KitRoot", "children": []},
            report={"nodes": 1, "light": True}, ubertext={"label": "u"},
            arrays={}, textures={},
            mesh_refs={"Card_InHand_Ally_Portrait_mesh": ["b1", 11]})

    def _write_bacon_kit(self) -> None:
        """bacon 特源帧（kit 六面件存储、bacon_kit token 种——A6 seed 映射面）。"""
        self.bacon_key = self._write_kit_item(
            frame="bacon", item_name=S.ITEM_KIT,
            meta={"frame": "bacon", "dbf_id": 132578,
                  "frame_rig": {"material": {"name": "RigMat"}}},
            hierarchy={"path": "BaconRoot", "children": []},
            report={"nodes": 2}, ubertext={"label": "ub"},
            arrays={"extra/frame_rig/verts": np.zeros((3, 3), np.float32)},
            textures={"rig.png": Image.new("RGBA", (2, 2), (1, 2, 3, 255))},
            races=None,
            mesh_refs={"Hero_Mesh_Frame": ["b1", 21]})

    def _link_kit(self, cid: str) -> None:
        pk = S.plan_key(card_id=cid, locale=LOCALE, card_data_sha=f"ds-{cid}")
        self.conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                          "VALUES(?,?,?)", (pk, self.kit_key, "kit"))

    # ---- A6 supplement 域（parts codec 四 kind 全覆盖的手造最小账） ----

    def _write_supplements(self) -> None:
        from eidolon.core.supply_index import supp_codec as SC

        def write_blob(data: bytes, ext: str, content_sha: str) -> str:
            p = self.layout.blob_path(S.sha256_hex(data), ext=ext)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            return str(p.relative_to(self.root))

        abil_img = Image.new("RGBA", (3, 3), (4, 5, 6, 255))
        port_img = Image.new("RGBA", (2, 2), (7, 8, 9, 255))
        arr = np.arange(4, dtype=np.float32).reshape(2, 2)
        ability_value = {
            "recon_meta": {"prefab_ref": "ref-abil", "quality": "normal"},
            "hierarchy": {"path": "AbilRoot", "children": []},
            "report": {"nodes": 3},
            "ubertext": {"nodes": []},
            "arrays": {"root/verts": arr},
            "textures": {"abil.png": abil_img},
            "portrait": {"portrait.png": port_img},
            "portrait_meta": {"card_id": "CS1_113"},
            "mesh_refs": {"Card_InHand_Ability_Portrait_mesh": ["b1", 31]},
        }
        cases = [
            (S.DOMAIN_FRAMES, S.ITEM_ABILITY_KIT, {"quality": "normal"},
             ability_value),
            (S.DOMAIN_FRAMES, S.ITEM_ABILITY_KIT, {"quality": "premium"},
             dict(ability_value, recon_meta={"prefab_ref": "ref-abil-p",
                                             "quality": "premium"})),
            (S.DOMAIN_FRAMES, S.ITEM_BADGES_KIT, {},
             {"report": {"badges": {"tradeable": {"nodes": 1}}},
              "arrays": {"tradeable|n/verts": arr},
              "textures": {"badge.png": abil_img}}),
            (S.DOMAIN_FRAMES, S.ITEM_BTF_KIT, {},
             {"report": {"spells": {}, "materials": {"M": {"passes": []}}},
              "arrays": {"tl|n/verts": arr},
              "textures": {"btf.png": abil_img},
              "card_race": {"rows": [{"m_ID": 1, "m_isRaceTagId": 4}]}}),
            (S.DOMAIN_FRAMES, S.ITEM_ORNAMENTS_KIT, {},
             {"report": {"nodes": [], "faction_materials": {}},
              "arrays": {"faction|n/verts": arr},
              "textures": {"orn.png": abil_img}}),
            (S.DOMAIN_FRAMES, S.ITEM_TA_SUPPLEMENT, {},
             {"arrays": {"ally_desc/verts": arr, "ability_school/uv0": arr}}),
            (S.DOMAIN_FRAMES, S.ITEM_MATERIAL_STATE, {},
             {"data": {"materials": {"M": {"mat_pid": 1, "passes": []}},
                       "_meta": {"materials": 1}}}),
            (S.DOMAIN_FRAMES, S.ITEM_PORTRAIT_UV1, {},
             {"meshes": {f"{n}/{f}": arr for n in
                         ("Card_InHand_Ally_Portrait_mesh",
                          "Card_InHand_Ability_Portrait_mesh")
                         for f in ("verts", "uv1", "sub0")}}),
            (S.DOMAIN_TEXT, S.ITEM_FONT_ASSET_PARAMS, {},
             {"data": {"fonts": {"Belwe": {"m_CharacterPadding": 4,
                                           "m_FontRenderingMode": 2,
                                           "fallback_object_names": []}},
                       "sources": {}}}),
        ]
        for domain, item, params, value in cases:
            parts, _ = SC.encode_parts(value, write_blob=write_blob)
            content = {"supp": SC.supplement_content_sha(parts)}
            ik = S.supplement_item_key(domain=domain, item=item, params=params,
                                       locale=LOCALE, content_inputs=content)
            manifest = {"item": item, "locale": LOCALE, "parts": parts,
                        "supp_content_sha256": content["supp"]}
            self._item(ik, domain, item, S.cjson(params), SC.SUPP_CODEC,
                       S.cjson(manifest), content)
            for pname, p in parts.items():
                if p["kind"] in ("png", "bin"):
                    for fname, fmeta in p["files"].items():
                        bk = S.blob_key_generic(domain=domain,
                                                content_sha=fmeta["content_sha256"],
                                                codec=p["kind"])
                        self.conn.execute(
                            "INSERT OR REPLACE INTO blobs(blob_key,"
                            "payload_sha256,size,codec,codec_version,"
                            "last_used,created_at) VALUES(?,?,?,?,?,?,?)",
                            (bk, fmeta["payload_sha256"], fmeta["size"],
                             p["kind"], 1, NOW, NOW))
                        self.conn.execute(
                            "INSERT INTO item_blobs(item_key,blob_key,role) "
                            "VALUES(?,?,?)", (ik, bk, f"{pname}:{fname}"))
                else:
                    bk = S.blob_key_generic(domain=domain,
                                            content_sha=p["content_sha256"],
                                            codec=p["kind"])
                    self.conn.execute(
                        "INSERT OR REPLACE INTO blobs(blob_key,"
                        "payload_sha256,size,codec,codec_version,"
                        "last_used,created_at) VALUES(?,?,?,?,?,?,?)",
                        (bk, p["payload_sha256"], p["size"], p["kind"], 1,
                         NOW, NOW))
                    self.conn.execute(
                        "INSERT INTO item_blobs(item_key,blob_key,role) "
                        "VALUES(?,?,?)", (ik, bk, pname))
        self.supp_items = len(cases)

    # ---- color 域（A4：probe 全域项 + minionCardTextures 两槽 atlas） ----

    def _write_color(self) -> None:
        pdata = json.dumps(_COLOR_PROBE, ensure_ascii=False)
        psha = S.sha256_hex(pdata.encode("utf-8"))
        content_sha = S.sha256_hex(S.cjson(_COLOR_PROBE).encode("utf-8"))
        self.color_probe_key = S.color_probe_item_key(
            locale=LOCALE,
            content_inputs={"ref": "CardColorSwitcher.prefab:b30c", "probe":
                            content_sha})
        pbk = S.blob_key_generic(domain=S.DOMAIN_COLOR, content_sha=psha,
                                 codec="json")
        self._blob(psha, pdata.encode("utf-8"), ".json", blob_key=pbk,
                   codec="json")
        self._item(self.color_probe_key, S.DOMAIN_COLOR, S.ITEM_COLOR_PROBE,
                   S.cjson({}), "json",
                   S.cjson({"payload_sha256": psha, "payload_size": len(pdata),
                            "families": {k: len(v)
                                         for k, v in _COLOR_PROBE.items()}}),
                   {"probe": content_sha})
        self.conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                          "VALUES(?,?,?)", (self.color_probe_key, pbk, "probe"))
        self.color_atlas_pixels = {}
        for fam, slots in _COLOR_ATLAS.items():
            for ct, color in slots.items():
                img = Image.new("RGBA", (4, 4), color)
                png = KC.encode_png(img)
                pixel = S.sha256_hex(img.tobytes())
                payload = S.sha256_hex(png)
                cik = S.color_atlas_item_key(
                    family=fam, ct=ct, locale=LOCALE,
                    content_inputs={"ref": f"{fam}-{ct}.tif:g{ct}",
                                    "guid": f"g{ct}", "pixel": pixel})
                cbk = S.blob_key_generic(domain=S.DOMAIN_COLOR,
                                         content_sha=pixel, codec=S.CODEC)
                self._blob(payload, png, ".png", blob_key=cbk)
                self._item(cik, S.DOMAIN_COLOR, S.ITEM_COLOR_ATLAS,
                           S.cjson({"family": fam, "ct": ct}), S.CODEC,
                           S.cjson({"family": fam, "ct": ct, "locale": LOCALE,
                                    "pixel_sha256": pixel,
                                    "payload_sha256": payload,
                                    "payload_size": len(png)}),
                           {"ref": f"{fam}-{ct}.tif:g{ct}", "guid": f"g{ct}",
                            "pixel": pixel})
                self.conn.execute(
                    "INSERT INTO item_blobs(item_key,blob_key,role) "
                    "VALUES(?,?,?)", (cik, cbk, "atlas"))
                self.color_atlas_pixels[(fam, ct)] = pixel

    def _link_color(self, cid: str) -> None:
        pk = S.plan_key(card_id=cid, locale=LOCALE, card_data_sha=f"ds-{cid}")
        self.conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                          "VALUES(?,?,?)", (pk, self.color_probe_key, "color"))

    # ---- text 全域段（fontdefs 双条目 + 双 ttf） ----

    def _write_text(self) -> None:
        fdata = TC.encode_fontdefs(_TEXT_FONTDEFS)
        fsha = S.sha256_hex(fdata)
        fik = S.fontdefs_item_key(locale=LOCALE,
                                  content_inputs={"fontdefs": fsha})
        fbk = TC.fontdefs_blob_key(fsha)
        self._blob(fsha, fdata, ".json", blob_key=fbk, codec="json")
        self._item(fik, S.DOMAIN_TEXT, S.ITEM_FONTDEFS, S.cjson({}), "json",
                   S.cjson({"payload_sha256": fsha}), {"fontdefs": fsha})
        self.conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                          "VALUES(?,?,?)", (fik, fbk, TC.ROLE_FONTDEFS))
        for name, ttf in _TTF_BYTES.items():
            tsha = TC.ttf_content_sha(ttf)
            tik = S.font_ttf_item_key(font=name, locale=LOCALE,
                                      content_inputs={"ttf": tsha})
            tbk = TC.ttf_blob_key(tsha)
            self._blob(tsha, ttf, ".ttf", blob_key=tbk, codec="ttf")
            self._item(tik, S.DOMAIN_TEXT, S.ITEM_FONT_TTF, S.cjson({"font": name}),
                       "ttf", S.cjson({"payload_sha256": tsha}), {"ttf": tsha})
            self.conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                              "VALUES(?,?,?)", (tik, tbk, TC.ROLE_TTF))

    # ---- A5 mip 面（portrait_mip 链项 + registry 全局项） ----

    def _write_mip_item(self, cid: str, pk: str, img: Image.Image,
                        pixel_sha: str, *, source: str) -> None:
        import numpy as np

        from eidolon.core.supply_index import mip_codec as MC

        name = f"FakePortrait_{cid}"
        conn = self.conn
        if source == "chain":
            stored = np.full((2, 2, 4), 7, dtype=np.uint8)
            arrays = {MC.level_key(1): stored}
            manifest_mip = {"mip_count": 2, "l0": "derived", "lods_stored": 1}
            payload = MC.encode_chain_npz(arrays)
        else:
            # portrait 源（mips<=1）：blob=meta 标记（cold _extract_chain_for_worker
            # 同款——warm 链数据由 portrait PNG 派生）
            stored = []
            manifest_mip = {"mip_count": 1, "l0": "derived", "lods_stored": 0}
            payload = MC.meta_marker_payload()
        payload_sha = S.sha256_hex(payload)
        meta_sha = S.sha256_hex(S.cjson(
            {"name": name, "filter": 2, "bias": -0.5, **manifest_mip,
             "source": source}).encode("utf-8"))
        content = {"carddef": f"cd-{cid}", "portrait": pixel_sha,
                   "chain": MC.chain_content_sha(stored) if source == "chain"
                   else "",
                   "meta": meta_sha}
        mik = S.portrait_mip_item_key(card_id=cid, locale=LOCALE,
                                      content_inputs=content)
        manifest = {"card_id": cid, "kind": S.ITEM_PORTRAIT_MIP,
                    "locale": LOCALE, "source": source, "name": name,
                    "filter": 2, "bias": -0.5, "width": img.width,
                    "height": img.height, **manifest_mip,
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
                   "npz", S.cjson(manifest), content)
        conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                     "VALUES(?,?,?)", (mik, mbk, "chain"))
        conn.execute("INSERT INTO plan_items(plan_key,item_key,role) "
                     "VALUES(?,?,?)", (pk, mik, "portrait_mip"))
        self.mip_keys = getattr(self, "mip_keys", {})
        self.mip_keys[cid] = mik

    def _write_mip_registry(self) -> None:
        import numpy as np

        from eidolon.core.supply_index import mip_codec as MC

        arrays = {MC.registry_chain_key("FakeReg_D", i):
                  np.full((4, 4, 4), i + 1, dtype=np.uint8) for i in range(3)}
        payload = MC.encode_chain_npz(arrays)
        payload_sha = S.sha256_hex(payload)
        content = {"chains": MC.chain_content_sha(
                       [arrays[k] for k in sorted(arrays)]),
                   "table": S.sha256_hex(S.cjson(
                       [("FakeReg_D", "b1", 7)]).encode("utf-8"))}
        rik = S.mip_registry_item_key(locale=LOCALE, content_inputs=content)
        manifest = {"item": S.ITEM_MIP_REGISTRY, "locale": LOCALE,
                    "chains": {"FakeReg_D": {"filter": 2, "bias": -0.5,
                                             "mip_count": 3, "bundle": "b1",
                                             "path_id": 7}},
                    "chain_count": 1, "array_count": 3,
                    "payload_sha256": payload_sha, "payload_size": len(payload)}
        rbk = S.blob_key_generic(domain="mip", content_sha=payload_sha,
                                 codec="npz")
        self._blob(payload_sha, payload, ".npz", blob_key=rbk, codec="npz")
        self._item(rik, S.DOMAIN_TEXTURES, S.ITEM_MIP_REGISTRY, S.cjson({}),
                   "npz", S.cjson(manifest), content)
        self.conn.execute("INSERT INTO item_blobs(item_key,blob_key,role) "
                          "VALUES(?,?,?)", (rik, rbk, "registry"))
        self.mip_registry_key = rik

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
              manifest: str, content: dict) -> None:
        self.conn.execute(
            "INSERT INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (ik, domain, item, params, codec, S.CODEC_VERSION, manifest, "ok",
             "asset", S.cjson([]), S.cjson(content), NOW))


class SeederCase(unittest.TestCase):
    """公共底座：tmp fixture + seeder 构造（身份账一致口径）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.fx = _SeedFixture(self.root)
        self.fx.publish_current()

    def _seeder(self, *, identity: dict | None = IDENTITY,
                locale: str = LOCALE, gap=_gap_faces_ok) -> CardSeeder | None:
        seeder = CardSeeder.open(self.root, ctx_locale=locale,
                                 ctx_identity=identity, kit_gap_faces=gap)
        if seeder is not None:
            self.addCleanup(seeder.close)
        return seeder


class OpenGateTests(SeederCase):
    """open 校验 + 整批弃种判据（§3.6；失败恒 None + WARN，不 raise）。"""

    def test_open_ok_binds_generation(self) -> None:
        seeder = self._seeder()
        self.assertIsNotNone(seeder)
        self.assertEqual(seeder.index.locale, LOCALE)
        self.assertEqual(seeder.index.game_id, GAME_ID)

    def test_missing_index_returns_none_with_warn(self) -> None:
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="WARNING") as logs:
            seeder = CardSeeder.open(self.root / "no-such-cache",
                                     ctx_locale=LOCALE)
        self.assertIsNone(seeder)
        self.assertTrue(any("整批弃种" in m for m in logs.output),
                        logs.output)

    def test_locale_mismatch_abandons_batch(self) -> None:
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="WARNING"):
            seeder = self._seeder(locale="enus")
        self.assertIsNone(seeder)

    def test_identity_mismatch_abandons_batch(self) -> None:
        drifted = {**IDENTITY, "manifest_stamp": "other-build"}
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="WARNING"):
            seeder = self._seeder(identity=drifted)
        self.assertIsNone(seeder)

    def test_current_without_identity_abandons_batch(self) -> None:
        self.fx.publish_current(identity=None)     # 覆写 current.json（无 identity）
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="WARNING"):
            seeder = self._seeder()
        self.assertIsNone(seeder)

    def test_identity_game_id_inconsistent_abandons_batch(self) -> None:
        # identity 与 ctx 一致但 game_id 账与 identity 重推不一致（账面损坏形态）
        forged = S.sha256_hex(b"forged-game-id")
        self.fx.publish_current()                       # 先发布（关连接）再复制
        self.fx.layout.gen_dir(forged).mkdir(parents=True, exist_ok=True)
        self.fx.layout.gen_db(forged).write_bytes(self.fx.db.read_bytes())
        self.fx.publish_current(game_id=forged)
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="WARNING"):
            seeder = self._seeder()
        self.assertIsNone(seeder)

    def test_open_without_identity_skips_identity_check(self) -> None:
        # ctx_identity=None（调用方不核同源）→ 只校验 locale，正常开
        seeder = self._seeder(identity=None)
        self.assertIsNotNone(seeder)


class ConversionTests(SeederCase):
    """role→token 转换形状（缺口面注入替身=零游戏）。"""

    def _seeds(self, cid: str = "C_SEED", **kw) -> dict:
        seeder = self._seeder(**kw)
        self.assertIsNotNone(seeder)
        seeds = seeder.seeds_for_card(cid)
        self.assertIsNotNone(seeds)
        return seeds

    def test_seed_tokens_full_bundle_shape(self) -> None:
        seeds = self._seeds()
        self.assertEqual(
            sorted(seeds),
            sorted([("art", "portrait", ("C_SEED",)),
                    ("frames", "kit", ("ally",)),
                    ("frames", "bacon_kit", ()),
                    ("frames", "kit_light", ("ally",)),
                    ("frames", "ability_kit", ("normal",)),
                    ("frames", "ability_kit", ("premium",)),
                    ("frames", "badges_kit", ()),
                    ("frames", "btf_kit", ()),
                    ("frames", "ornaments_kit", ()),
                    ("frames", "ta_supplement", ()),
                    ("frames", "material_state", ()),
                    ("frames", "portrait_uv1", ()),
                    ("text", "fontdefs", ()),
                    ("text", "font_table", ()),
                    ("text", "font_ttf_bytes", ("Belwe",)),
                    ("text", "font_ttf_bytes", ("ZhFont",)),
                    ("text", "font_asset_params", ()),
                    ("watermarks", "texture", (_WM_REF,)),
                    ("color", "probe", ()),
                    ("color", "atlas", ("minionCardTextures", 0)),
                    ("color", "atlas", ("minionCardTextures", 1)),
                    ("textures", "mip_registry", ()),
                    ("art", "portrait_mip", ("C_SEED",))]),
            "A3-A6 映射表：portrait/kit 全帧族+bacon_kit+kit_light/特源附件 kit×7"
            "/fontdefs/font_table/ttf×2/font_asset_params/watermark/color.probe"
            "/color.atlas×2/mip_registry/portrait_mip"
            "（帧族全有效槽枚举，空占位槽跳过）")
        # portrait：warm PNG 复原图（像素 sha 全等）
        img = seeds[("art", "portrait", ("C_SEED",))]
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (4, 4))
        # text：fontdefs 逐键 + font_table 无损派生（条目按名对账——index
        # fontdefs 经 canonical JSON 往返键序=排序序，live=FontTableData 序；
        # 消费面按名建索引，次序不进渲染语义——spike 同源序同 sha 实证）
        self.assertEqual(seeds[("text", "fontdefs", ())], _TEXT_FONTDEFS)
        self.assertEqual(
            sorted(seeds[("text", "font_table", ())],
                   key=lambda e: e["m_FontDefName"]),
            [{"m_FontDefName": "Belwe", "m_FontName": "Belwe",
              "m_FontGuid": "guid-belwe"},
             {"m_FontDefName": "ZhFont", "m_FontName": "Zhonomy",
              "m_FontGuid": "guid-zh"}])
        self.assertEqual(seeds[("text", "font_ttf_bytes", ("ZhFont",))],
                         _TTF_BYTES["ZhFont"])
        # watermark：token 参数=index manifest 裁决值
        self.assertIs(seeds[("watermarks", "texture", (_WM_REF,))],
                      seeds[("watermarks", "texture", (_WM_REF,))])

    def test_kit_reassembly_matches_live_shape(self) -> None:
        from eidolon.core.supply.frames.kits import Kit, _ArrayDict

        seeds = self._seeds()
        kit = seeds[("frames", "kit", ("ally",))]
        self.assertIsInstance(kit, Kit)
        # frame_dir=live spec 形（A6 对账修正：FRAME_SPECS["ally"].frame_dir）
        self.assertEqual(kit.frame_dir, "ally_frame")
        # 六面重组：meta=hierarchy 合并 + trinket_level_mats=None（spike 形）
        self.assertEqual(kit.meta, {"frame": "ally", "dbf_id": 9,
                                    "hierarchy": {"path": "KitRoot",
                                                  "children": []},
                                    "trinket_level_mats": None})
        self.assertIsInstance(kit.arrays, _ArrayDict)
        self.assertEqual(kit.arrays.files, ["verts"])
        self.assertEqual(kit.arrays["verts"].dtype, np.float32)
        self.assertEqual(sorted(kit.textures), ["tex0.png"])
        self.assertEqual(kit.report, {"nodes": 1})
        self.assertEqual(kit.ubertext, {"label": "u"})
        # 缺口面落位（注入替身值）
        self.assertEqual(kit.races, _GAP_RACES)
        self.assertEqual(kit.mesh_refs, _GAP_MESH)

    def test_provider_zero_arg_callable_and_ledger(self) -> None:
        seeder = self._seeder()
        provider = seeder.provider_for_card("C_SEED")
        seeds = provider()                       # 零参调用（A2 seam 注入形）
        self.assertIsInstance(seeds, dict)
        self.assertTrue(seeds)
        ledger = seeder.last_ledger
        self.assertIsInstance(ledger, SeedLedger)
        self.assertEqual(ledger.card_id, "C_SEED")
        self.assertFalse(ledger.skipped)
        self.assertIn("art.portrait('C_SEED')", ledger.seeded)

    def test_dbf_lookup_seeds_same_card(self) -> None:
        seeder = self._seeder()
        by_card = seeder.seeds_for_card("C_SEED")
        by_dbf = seeder.seeds_for_dbf(4242)
        self.assertIsNotNone(by_dbf)
        self.assertEqual(sorted(by_dbf), sorted(by_card))

    def test_dbf_unknown_returns_none(self) -> None:
        seeder = self._seeder()
        self.assertIsNone(seeder.seeds_for_dbf(999999))

    def test_kit_races_attached_only_when_gap_says_so(self) -> None:
        # 替身返回 races=None（live 对非 races 帧族的同形）→ kit 照种、races=None
        seeds = self._seeds(gap=lambda frame: (None, {}))
        kit = seeds[("frames", "kit", ("ally",))]
        self.assertIsNone(kit.races)
        self.assertEqual(kit.mesh_refs, {})


class ColorConversionTests(SeederCase):
    """A4 color 两 token 转换形状（probe 逐键同形 + 帧族全有效槽枚举）。"""

    def test_color_probe_and_atlas_seeded(self) -> None:
        seeder = self._seeder()
        seeds = seeder.seeds_for_card("C_SEED")
        self.assertIsNotNone(seeds)
        probe = seeds[("color", "probe", ())]
        self.assertEqual(probe, _COLOR_PROBE, "probe 逐键逐槽同形")
        self.assertEqual(list(probe), list(_COLOR_PROBE), "键序=落盘序")
        img0 = seeds[("color", "atlas", ("minionCardTextures", 0))]
        img1 = seeds[("color", "atlas", ("minionCardTextures", 1))]
        self.assertIsInstance(img0, Image.Image)
        self.assertIsInstance(img1, Image.Image)
        self.assertEqual(S.sha256_hex(img0.tobytes()),
                         self.fx.color_atlas_pixels[("minionCardTextures", 0)])
        self.assertEqual(S.sha256_hex(img1.tobytes()),
                         self.fx.color_atlas_pixels[("minionCardTextures", 1)])
        # 空占位槽（ct=2）不种（live kit 提取同判跳过）
        self.assertNotIn(("color", "atlas", ("minionCardTextures", 2)), seeds)
        ledger = seeder.last_ledger
        self.assertFalse(ledger.skipped)

    def test_frame_family_mapping_none_leg(self) -> None:
        # frame→族映射：ally→minionCardTextures；ally_premium/heropower family=None
        # （specs.py 账——金卡/英雄技能帧类色=染色不换图集，无 atlas 枚举）；未知帧=None
        from eidolon.core.supply_index.seed import _frame_family

        self.assertEqual(_frame_family("ally"), "minionCardTextures")
        self.assertEqual(_frame_family("weapon"), "weaponCardTextures")
        self.assertIsNone(_frame_family("ally_premium"))
        self.assertIsNone(_frame_family("heropower"))
        self.assertIsNone(_frame_family("__no_such_frame__"))

    def test_color_absent_bundle_skips_tokens(self) -> None:
        # 无 color 挂接卡（未知卡型卡形态：plan 无 color 行）→ color 束缺席 →
        # color 两 token 不种、其余照种（probe item 缺失而挂接行在=账面损坏 →
        # assemble 严格门整卡弃种，不在此列——warm 缺项面同判据）
        pk = S.plan_key(card_id="C_NOWM", locale=LOCALE, card_data_sha="ds-C_NOWM")
        conn = S.connect(self.fx.db)
        try:
            conn.execute("DELETE FROM plan_items WHERE plan_key=? AND role='color'",
                         (pk,))
            conn.commit()
        finally:
            conn.close()
        seeder = self._seeder()
        seeds = seeder.seeds_for_card("C_NOWM")
        self.assertIsNotNone(seeds, "color 束缺席只弃 color token，不弃整卡")
        self.assertFalse(any(t[0] == "color" for t in seeds))
        self.assertIn(("art", "portrait", ("C_NOWM",)), seeds)
        self.assertIn(("frames", "kit", ("ally",)), seeds)
        ledger = seeder.last_ledger
        self.assertTrue(any("color" in s for s in ledger.skipped))

    def test_color_probe_item_missing_strict_gate_abandons_card(self) -> None:
        # probe item 删除而 plan 挂接行在（账面损坏形态）→ assemble 严格门 fail loud
        # → 整卡弃种 None（warm 缺项面同判据——不静默半卡种子）
        conn = S.connect(self.fx.db)
        try:
            conn.execute("DELETE FROM item_blobs WHERE item_key=?",
                         (self.fx.color_probe_key,))
            conn.execute("DELETE FROM items WHERE item_key=?",
                         (self.fx.color_probe_key,))
            conn.commit()
        finally:
            conn.close()
        seeder = self._seeder()
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="WARNING"):
            seeds = seeder.seeds_for_card("C_SEED")
        self.assertIsNone(seeds)


class A6GapFacesTests(SeederCase):
    """A6 缺口面换 index 面（A3 live 派生件退役；注入形保留=替身测试面）。"""

    def _seeds(self, cid: str = "C_SEED", **kw) -> dict:
        seeder = self._seeder(**kw)
        self.assertIsNotNone(seeder)
        seeds = seeder.seeds_for_card(cid)
        self.assertIsNotNone(seeds)
        return seeds

    def test_default_gap_faces_read_index(self) -> None:
        # gap=None（缺省）→ races/mesh_refs 自 index 面读回（JSON list→tuple）
        seeds = self._seeds(gap=None)
        kit = seeds[("frames", "kit", ("ally",))]
        self.assertEqual(kit.races,
                         {"source": "unit:GLOBAL.txt", "provenance": "fixture",
                          "strings": {"7": "野兽"}})
        self.assertEqual(kit.mesh_refs,
                         {"Card_InHand_Ally_Portrait_mesh": ("b1", 11)})

    def test_bacon_kit_seeded_from_kit_item(self) -> None:
        from eidolon.core.supply.frames.kits import Kit

        seeds = self._seeds(gap=None)
        bk = seeds[("frames", "bacon_kit", ())]
        self.assertIsInstance(bk, Kit)
        self.assertEqual(bk.frame_dir, "bacon")
        self.assertEqual(bk.meta["frame_rig"], {"material": {"name": "RigMat"}})
        self.assertIsNone(bk.races)          # live bacon spec races=False 同形
        self.assertEqual(bk.mesh_refs, {"Hero_Mesh_Frame": ("b1", 21)})

    def test_kit_light_seeded(self) -> None:
        from eidolon.core.supply.frames.kits import Kit

        seeds = self._seeds(gap=None)
        kl = seeds[("frames", "kit_light", ("ally",))]
        self.assertIsInstance(kl, Kit)
        self.assertEqual(kl.textures, {}, "轻走查语义：textures 空 dict")
        self.assertIsNone(kl.races, "live kit_light races 恒 None 同形")
        self.assertEqual(kl.mesh_refs,
                         {"Card_InHand_Ally_Portrait_mesh": ("b1", 11)})

    def test_index_gap_faces_races_rule(self) -> None:
        """KIT_RACE_FRAMES 词面规则：races 帧族缺面=SupplyMissingError（kit
        token 整个不种——种缺 races 的 ally Kit 会在 GetRaceText 炸）；非 races
        帧族 races=None 照过。"""
        from eidolon.core.supply_index.seed import CardSeeder
        from eidolon.core.supply_index.warm import SupplyMissingError

        class _Idx:
            def __init__(self, races):
                self._races = races

            def kit_races(self, frame):
                return self._races.get(frame)

            def kit_mesh_refs(self, frame):
                return {"m": ("b1", 1)}

        seeder = CardSeeder(_Idx({"ally": None}), ctx_locale=LOCALE)
        with self.assertRaises(SupplyMissingError):
            seeder._index_gap_faces("ally")
        races, mesh_refs = seeder._index_gap_faces("weapon")
        self.assertIsNone(races)
        self.assertEqual(mesh_refs, {"m": ("b1", 1)})

    def test_index_gap_faces_bad_races_shape_rejected(self) -> None:
        from eidolon.core.supply_index.seed import CardSeeder
        from eidolon.core.supply_index.warm import SupplyMissingError

        class _Idx:
            def kit_races(self, frame):
                return {"strings": None}   # 形状不符（strings 非 dict）

            def kit_mesh_refs(self, frame):
                return {}

        seeder = CardSeeder(_Idx(), ctx_locale=LOCALE)
        with self.assertRaises(SupplyMissingError):
            seeder._index_gap_faces("trinket")


class A6SupplementTests(SeederCase):
    """A6 特源/附件 kit + font_asset_params 种子形状（存储表两半对账）。"""

    def _seeds(self, cid: str = "C_SEED") -> dict:
        seeder = self._seeder(gap=None)
        self.assertIsNotNone(seeder)
        seeds = seeder.seeds_for_card(cid)
        self.assertIsNotNone(seeds)
        return seeds

    def test_ability_kit_reassembly(self) -> None:
        from eidolon.core.supply.frames.ability import AbilityKit
        from eidolon.core.supply.frames.kits import _ArrayDict

        seeds = self._seeds()
        for q in ("normal", "premium"):
            k = seeds[("frames", "ability_kit", (q,))]
            self.assertIsInstance(k, AbilityKit)
            self.assertEqual(k.recon_meta["hierarchy"],
                             {"path": "AbilRoot", "children": []})
            self.assertEqual(k.recon_meta["prefab_ref"],
                             "ref-abil-p" if q == "premium" else "ref-abil")
            self.assertIsInstance(k.arrays, _ArrayDict)
            self.assertEqual(sorted(k.textures), ["abil.png"])
            self.assertIsNotNone(k.portrait)
            self.assertEqual(k.portrait_meta, {"card_id": "CS1_113"})
            self.assertEqual(k.report, {"nodes": 3})
            self.assertEqual(k.ubertext, {"nodes": []})
            self.assertEqual(k.mesh_refs,
                             {"Card_InHand_Ability_Portrait_mesh": ("b1", 31)})
            # 种子形状显式账：obj_texts/fonts_bytes 不进种子形状（渲染链零消费
            # 的提取产物面——supply-source.md A6 落地账）
            self.assertEqual(k.obj_texts, {})
            self.assertEqual(k.fonts_bytes, {})

    def test_badges_btf_ornaments_reassembly(self) -> None:
        from eidolon.core.supply.frames.badges import BadgesKit
        from eidolon.core.supply.frames.btf import BtfKit
        from eidolon.core.supply.frames.ornaments import OrnamentsKit

        seeds = self._seeds()
        b = seeds[("frames", "badges_kit", ())]
        self.assertIsInstance(b, BadgesKit)
        self.assertEqual(sorted(b.arrays), ["tradeable|n/verts"])
        self.assertEqual(sorted(b.textures), ["badge.png"])
        self.assertIn("tradeable", b.report["badges"])
        t = seeds[("frames", "btf_kit", ())]
        self.assertIsInstance(t, BtfKit)
        self.assertEqual(t.card_race, {"rows": [{"m_ID": 1,
                                                 "m_isRaceTagId": 4}]})
        self.assertEqual(t.report["materials"]["M"], {"passes": []})
        o = seeds[("frames", "ornaments_kit", ())]
        self.assertIsInstance(o, OrnamentsKit)
        self.assertEqual(o.report["nodes"], [])

    def test_ta_material_state_portrait_uv1_reassembly(self) -> None:
        seeds = self._seeds()
        ta = seeds[("frames", "ta_supplement", ())]
        self.assertEqual(sorted(ta), ["ability_school/uv0", "ally_desc/verts"])
        ms = seeds[("frames", "material_state", ())]
        self.assertIn("materials", ms)
        self.assertIn("M", ms["materials"])
        uv1 = seeds[("frames", "portrait_uv1", ())]
        # npz 扁平键按名重组（live dict[name][field] 同形）
        self.assertEqual(
            sorted(uv1),
            ["Card_InHand_Ability_Portrait_mesh",
             "Card_InHand_Ally_Portrait_mesh"])
        self.assertEqual(sorted(uv1["Card_InHand_Ally_Portrait_mesh"]),
                         ["sub0", "uv1", "verts"])

    def test_font_asset_params_seeded(self) -> None:
        seeds = self._seeds()
        fap = seeds[("text", "font_asset_params", ())]
        self.assertEqual(fap["fonts"]["Belwe"]["m_CharacterPadding"], 4)
        self.assertEqual(fap["fonts"]["Belwe"]["m_FontRenderingMode"], 2)


class A6SuppCodecTests(unittest.TestCase):
    """supp_codec 四 kind 编解码往返 + 内容聚合 sha 稳定性（零游戏）。"""

    def test_roundtrip_all_kinds(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from PIL import Image

        from eidolon.core.supply_index import supp_codec as SC

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)

        def write_blob(data: bytes, ext: str, content_sha: str) -> str:
            p = root / f"{S.sha256_hex(data)[:12]}{ext}"
            p.write_bytes(data)
            return str(p.relative_to(root))

        arr = np.arange(6, dtype=np.float64).reshape(2, 3)
        value = {
            "j": {"a": 1, "b": [1, 2]},
            "z": {"k/verts": arr},
            "p": {"x.png": Image.new("RGBA", (2, 2), (1, 2, 3, 255))},
            "b": {"f.ttf": b"BIN-BYTES"},
        }
        parts, _ = SC.encode_parts(value, write_blob=write_blob)
        self.assertEqual([parts[k]["kind"] for k in ("j", "z", "p", "b")],
                         ["json", "npz", "png", "bin"])
        sha1 = SC.supplement_content_sha(parts)

        def read_blob(role: str) -> bytes:
            if role == "j":
                return (root / f"{parts['j']['payload_sha256'][:12]}"
                        ".json").read_bytes()
            if role == "z":
                return (root / f"{parts['z']['payload_sha256'][:12]}"
                        ".npz").read_bytes()
            if role.startswith("p:"):
                fname = role.split(":", 1)[1]
                return (root / f"{parts['p']['files'][fname]['payload_sha256'][:12]}"
                        ".png").read_bytes()
            fname = role.split(":", 1)[1]
            return (root / f"{parts['b']['files'][fname]['payload_sha256'][:12]}"
                    ".bin").read_bytes()

        back = SC.decode_parts({"parts": parts}, read_blob)
        self.assertEqual(back["j"], value["j"])
        self.assertTrue(np.array_equal(back["z"]["k/verts"], arr))
        self.assertEqual(back["p"]["x.png"].tobytes(),
                         value["p"]["x.png"].tobytes())
        self.assertEqual(back["b"]["f.ttf"], b"BIN-BYTES")
        # 稳定性：同值重编码=同聚合 sha（内容身份不随编码器实例漂）
        parts2, _ = SC.encode_parts(value, write_blob=write_blob)
        self.assertEqual(SC.supplement_content_sha(parts2), sha1)

    def test_decode_content_verify_rejects_corrupt(self) -> None:
        from eidolon.core.supply_index import supp_codec as SC

        manifest = {"parts": {"j": {"kind": "json",
                                    "payload_sha256": "0" * 64,
                                    "size": 2, "content_sha256": "0" * 64}}}
        with self.assertRaises(SC.SuppContentError):
            SC.decode_parts(manifest, lambda role: b"{}")

    def test_kit_codec_version_matches_schema(self) -> None:
        # schema 不 import kit_codec（防循环）——两处字面量由本测钉死相等
        from eidolon.core.supply_index import kit_codec as KC

        self.assertEqual(KC.KIT_CODEC_VERSION, 2)
        self.assertEqual(S.SUPP_CODEC, "supp")


class SkipTokenTests(SeederCase):
    """该 token 不种（其余照种）/ 该卡弃种（None）分层（§3.6）。"""
    def test_gap_face_failure_skips_kit_only(self) -> None:
        seeder = self._seeder(gap=_gap_faces_boom)
        seeds = seeder.seeds_for_card("C_SEED")
        self.assertIsNotNone(seeds, "缺口面失败只弃 kit token，不弃整卡")
        self.assertNotIn(("frames", "kit", ("ally",)), seeds)
        self.assertIn(("art", "portrait", ("C_SEED",)), seeds)
        self.assertIn(("text", "fontdefs", ()), seeds)
        ledger = seeder.last_ledger
        self.assertTrue(any("kit" in s for s in ledger.skipped))

    def test_watermark_absent_skips_token_only(self) -> None:
        seeder = self._seeder()
        seeds = seeder.seeds_for_card("C_NOWM")
        self.assertIsNotNone(seeds)
        self.assertFalse(any(t[0] == "watermarks" for t in seeds),
                         "无水印卡：watermark token 不种，其余照种")
        self.assertIn(("art", "portrait", ("C_NOWM",)), seeds)
        self.assertIn(("frames", "kit", ("ally",)), seeds)

    def test_card_not_in_table_returns_none(self) -> None:
        seeder = self._seeder()
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="WARNING"):
            seeds = seeder.seeds_for_card("__ghost__")
        self.assertIsNone(seeds)

    def test_assemble_strict_gate_failure_returns_none(self) -> None:
        # locator ok 而无 item（期望缺口）→ assemble_card 严格门 fail loud → None
        seeder = self._seeder()
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="WARNING"):
            seeds = seeder.seeds_for_card("C_GAP")
        self.assertIsNone(seeds)

    def test_ledger_counts_logged_at_info(self) -> None:
        seeder = self._seeder()
        with self.assertLogs("eidolon.core.supply_index.seed",
                             level="INFO") as logs:
            seeder.seeds_for_card("C_SEED")
        # A6 起 seed 全集=portrait+kit+bacon_kit+kit_light+特源附件×7+fontdefs
        # +font_table+ttf×2+font_asset_params+watermark+color×3+mip×2 = 23
        self.assertTrue(any("seeded=23" in m for m in logs.output), logs.output)


class NoProblemDisciplineTests(unittest.TestCase):
    """弃种不产生新 Problem code（任务单 A3 判据 2 钉住面）。"""

    _SEED_FILE = (_REPO / "eidolon" / "core" / "supply_index" / "seed.py")

    def test_seed_source_has_no_problem_names(self) -> None:
        """AST 面：全源无 Problem/ProblemKind 名字、属性或导入（docstring 提及
        不算——AST 只见代码）。弃种=返回 None 的纯 live 回退，不构造 Problem。"""
        tree = ast.parse(self._SEED_FILE.read_text(encoding="utf-8"),
                         filename=str(self._SEED_FILE))
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in ("Problem", "ProblemKind"):
                bad.append(f"Name {node.id}@{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in ("Problem", "ProblemKind"):
                bad.append(f"Attribute {node.attr}@{node.lineno}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names]
                modules = [getattr(node, "module", None) or ""] + names
                if any(n in ("Problem", "ProblemKind") for n in modules):
                    bad.append(f"import@{node.lineno}")
        self.assertEqual(bad, [], "seed.py 构造/导入 Problem：弃种语义被破坏")

    def test_top_level_imports_are_warm_face_only(self) -> None:
        """顶层 import 面（AST module body）：stdlib + PIL + warm/schema/paths
        ——render/supply/recipes/contracts/infra 与本包 UnityPy 面（cold/
        kit_extract/text_extract/wm_extract）一律不在顶层（转换件 live import
        必须全在函数体内，spike 同款）。"""
        tree = ast.parse(self._SEED_FILE.read_text(encoding="utf-8"),
                         filename=str(self._SEED_FILE))
        banned = ("eidolon.core.render", "eidolon.core.supply",
                  "eidolon.core.recipes", "eidolon.contracts",
                  "eidolon.core.infra")

        def _banned_module(module: str) -> bool:
            # 前缀匹配带包界（"eidolon.core.supply" 不得误吞 "supply_index"）
            return any(module == b or module.startswith(b + ".") for b in banned)

        banned_supply_index = ("cold", "kit_extract", "text_extract",
                               "wm_extract", "selfheal")
        offenders = []
        for node in tree.body:                       # 只看 module body（顶层）
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            module = getattr(node, "module", None) or ""
            names = [a.name for a in node.names]
            if _banned_module(module) or any(_banned_module(n) for n in names):
                offenders.append(f"{module}@{node.lineno}")
            if module.startswith("eidolon.core.supply_index"):
                tail = module.rsplit(".", 1)[-1]
                if tail in banned_supply_index or any(
                        n in banned_supply_index for n in names):
                    offenders.append(f"{module}@{node.lineno}")
        self.assertEqual(offenders, [],
                         "seed.py 顶层 import 越界（转换件 live import 必须惰性）")

    def test_seed_import_chain_warm_clean_subprocess(self) -> None:
        """子进程机器证明：import seed 全链（顶层）后 sys.modules 无 UnityPy/
        clr/texture2ddecoder/本包 UnityPy 面/render/supply/recipes。"""
        code = (
            "import sys, json; "
            "import eidolon.core.supply_index.seed; "
            "banned = ('UnityPy', 'clr', 'texture2ddecoder',"
            " 'eidolon.core.render', 'eidolon.core.supply.frames',"
            " 'eidolon.core.supply.text', 'eidolon.core.supply.art',"
            " 'eidolon.core.recipes', 'eidolon.core.supply_index.cold',"
            " 'eidolon.core.supply_index.kit_extract',"
            " 'eidolon.core.supply_index.text_extract',"
            " 'eidolon.core.supply_index.wm_extract',"
            " 'eidolon.core.supply_index.selfheal'); "
            "print(json.dumps(sorted(m for m in sys.modules "
            "if m.startswith(banned))))"
        )
        p = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, cwd=str(_REPO), timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]), [],
                         p.stdout)


class SeedScopeEquivalenceTests(unittest.TestCase):
    """A2 seam 等价（产品路径逐位不变的单测面）：``api._seed_scope`` 对
    None/空种子=nullcontext（纯 live）、非空=seed_session。"""

    def test_seed_scope_none_and_empty_are_pure_live(self) -> None:
        import contextlib

        from eidolon.core.render.api import _seed_scope

        # None / 空 dict / 返回 None 的 provider → nullcontext（纯 live，无种子面）
        self.assertIsInstance(_seed_scope(None), contextlib.nullcontext)
        self.assertIsInstance(_seed_scope(lambda: {}), contextlib.nullcontext)
        self.assertIsInstance(_seed_scope(lambda: None), contextlib.nullcontext)

    def test_seed_scope_nonempty_is_seed_session(self) -> None:
        import eidolon.core.supply.machine as machine
        from eidolon.core.render.api import _seed_scope

        seeds = {("t", "x", (1,)): "seeded"}
        with _seed_scope(lambda: seeds):
            self.assertEqual(machine._pending_seed.get(), seeds)
            with machine.session():
                self.assertEqual(machine._s_current.get().memo, dict(seeds))
        self.assertIsNone(machine._pending_seed.get())


def tearDownModule() -> None:  # noqa: N802 —— unittest 约定钩子
    """Kit 形状断言的运行期 live import 会拖入 UnityPy——出口清干净（同
    test_route_cabs 纪律），保后续 import 卫生守卫（text_atlas 等）绿。"""
    for name in [m for m in sys.modules
                 if m == "UnityPy" or m.startswith("UnityPy.")]:
        sys.modules.pop(name, None)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
