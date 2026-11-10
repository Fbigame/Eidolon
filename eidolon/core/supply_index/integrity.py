"""integrity — 全量 blob 完整性扫 + 定点修复（--repair；事故账 2026-11-07 的机器面）。

扫描（只读）：blobs 表全行 → 盘上文件逐个 hash → ok/missing/mismatch 三态 +
属主归因（item_blobs→items→domain/params/manifest→卡/字体/帧；**预载归属映射**
OwnerIndex——mass-bad 不再每坏行全表扫，P3 病态账修复）。audit 的装配 sha 校验
只覆盖被装配触达的 blob；本命令=全库逐行机器检查（22,678 行 ~14s）。

修复（--repair；cold 面=合法 UnityPy 唯一模式）：坏 blob 的属主 item 逐域
**重推导并要求字节全等**（确定性解码+编码；漂移=响亮——item 陈旧须全量重建，
禁静默改行）：
- art/watermark：source_json[0] 的 bundle+guid → _decode_bundle_worker 同款
  解码（写面=_write_blob_atomic：复用 hash 验+写后读回复验）→ payload sha ==
  行账；
- frames（kit）：_extract_kit_now 整 kit 重提取（六面 blob 带验证重写），逐
  face payload sha 对行账；
- gems：ally kit 重提取随走查重写 gem blob；
- text：extract_fonts 重提取（fontdefs/ttf 重写），逐件对行账。
修复后重扫；仍有坏 → exit 1（CLI 层）。

自愈车（2026-11-07）新增：rederive_one（L2 单点重推导=repair 单点形态，auto 模式
warm 撞 SupplyBlobCorruptError 的自愈入口）+ diagnose_source（L3 诊断分级：重推导
≠行账→版本换代/同代源坏）+ 报告留账（selfheal_* 计数 + media_event 介质级事件
报告头标记）+ open 自检（quick_check，损坏响亮「索引损坏需重建」）。

背景（必须保留 #1 的姊妹条）：warm 面不 import 本模块（UnityPy 面，同 cold/
kit_extract/text_extract/wm_extract——audit blocker 已拦）。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from eidolon.core.supply_index import kit_codec as KC
from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.paths import SupplyLayout


def _ext(codec: str) -> str:
    return KC.BLOB_CODEC_EXT.get(codec or "png", ".png")


class OwnerIndex:
    """归属映射预载（归因提速，2026-11-07 自愈车；零 schema 变更）。

    病态账（docs/notes/supply-index-p3.md）：attribute() 每坏行对 blobs.payload_sha256
    （无索引）+ item_blobs.blob_key（PK 前缀=item_key）+ plan_items.item_key 三重
    全表扫，mass-bad 退化 O(缺失×行数)=227s+ 实测。修法=一趟全表建内存映射：
    {payload_sha: [blob_key]} + {blob_key: [(item_key, role)]} + plan_items item 集
    （38k+38k+111k 行 <1s），归因退化 O(1) 字典查 + 每属主 items PK 点查。"""

    def __init__(self, conn: sqlite3.Connection):
        self.blob_by_sha: dict[str, list[str]] = {}
        for r in conn.execute("SELECT blob_key, payload_sha256 FROM blobs"):
            self.blob_by_sha.setdefault(r["payload_sha256"], []).append(
                r["blob_key"])
        self.owners_by_blob: dict[str, list[tuple[str, str]]] = {}
        for r in conn.execute("SELECT item_key, blob_key, role FROM item_blobs"):
            self.owners_by_blob.setdefault(r["blob_key"], []).append(
                (r["item_key"], r["role"]))
        self.plan_items: set[str] = {
            r[0] for r in conn.execute("SELECT item_key FROM plan_items")}


def scan(conn: sqlite3.Connection, layout: SupplyLayout) -> dict:
    """全量 blob 完整性扫（只读）：ok/missing/mismatch + 每坏行属主归因。

    归因走预载归属映射（OwnerIndex 一次；0 坏=零预载成本）。"""
    from eidolon.core.supply_index._unity import sha256_file

    rows = list(conn.execute(
        "SELECT blob_key, payload_sha256, size, codec FROM blobs"))
    ok, missing, mismatch = 0, [], []
    for r in rows:
        sha = r["payload_sha256"]
        p = layout.blob_path(sha, ext=_ext(r["codec"]))
        try:
            if not p.is_file():
                missing.append({"payload_sha256": sha, "size": r["size"],
                                "codec": r["codec"], "why": "file-missing"})
                continue
            if sha256_file(p) != sha:
                mismatch.append({"payload_sha256": sha, "size": r["size"],
                                 "codec": r["codec"], "why": "content-sha-mismatch",
                                 "file_size": p.stat().st_size})
                continue
            ok += 1
        except OSError as exc:
            missing.append({"payload_sha256": sha, "size": r["size"],
                            "codec": r["codec"],
                            "why": f"read-error: {type(exc).__name__}"})
    if missing or mismatch:
        index = OwnerIndex(conn)
        enrich: dict[str, dict] = {}     # item 级归一面缓存（同 item 多坏块共享）
        for bad in (*missing, *mismatch):
            bad["owners"] = attribute(conn, layout, bad["payload_sha256"],
                                      index=index, _enrich=enrich)
    return {"rows": len(rows), "ok": ok, "missing": missing,
            "mismatch": mismatch,
            "bad": len(missing) + len(mismatch)}


def _owner_pairs(conn: sqlite3.Connection, payload_sha: str,
                 index: OwnerIndex | None) -> list[tuple[str, str]]:
    """payload sha → [(item_key, role)]（预载映射直查；单查回退 SQL）。"""
    if index is not None:
        pairs: list[tuple[str, str]] = []
        for bk in index.blob_by_sha.get(payload_sha, ()):
            pairs.extend(index.owners_by_blob.get(bk, ()))
        return pairs
    return [(r[0], r[1]) for r in conn.execute(
        "SELECT ib.item_key, ib.role FROM item_blobs ib WHERE ib.blob_key IN "
        "(SELECT blob_key FROM blobs WHERE payload_sha256=?)", (payload_sha,))]


def _enrich_item(conn: sqlite3.Connection, item_key: str,
                 index: OwnerIndex | None) -> dict:
    """item 级归一面（domain/params/manifest 摘要+plan 链存在性；plan_linked 用
    预载集，退回单查 LIMIT 1——per-owner 全表扫禁复发）。"""
    r = conn.execute(
        "SELECT domain, params_json, manifest_json FROM items WHERE item_key=?",
        (item_key,)).fetchone()
    if r is None:
        return {"item_key": item_key, "role": None, "domain": None,
                "params": {}, "card": None, "kind": None, "gem": None,
                "font": None, "frame": None, "plan_linked": False,
                "bundle": None, "guid": None, "item_row_missing": True}
    m = json.loads(r["manifest_json"])
    params = json.loads(r["params_json"])
    if index is not None:
        linked = item_key in index.plan_items
    else:
        linked = conn.execute(
            "SELECT 1 FROM plan_items WHERE item_key=? LIMIT 1",
            (item_key,)).fetchone() is not None
    return {
        "item_key": item_key, "role": None, "domain": r["domain"],
        "item": r["item"], "params": params,
        "card": m.get("card_id") or params.get("card_id"),
        "kind": m.get("kind"), "gem": m.get("gem"), "font": m.get("font"),
        "frame": m.get("frame"), "plan_linked": bool(linked),
        "bundle": m.get("bundle"), "guid": m.get("guid"),
    }


def attribute(conn: sqlite3.Connection, layout: SupplyLayout, payload_sha: str,
              *, index: OwnerIndex | None = None,
              _enrich: dict | None = None) -> list[dict]:
    """blob → 属主 item 面（domain/params/manifest 摘要+plan 链存在性）。

    index=预载归属映射（mass-bad 面；scan 传入共享）；缺省=单查 SQL（零星坏行
    等价）。_enrich=item 级归一缓存（同 item 多坏块零重复查询）。"""
    out = []
    for ik, role in _owner_pairs(conn, payload_sha, index):
        base = None
        if _enrich is not None:
            base = _enrich.get(ik)
        if base is None:
            base = _enrich_item(conn, ik, index)
            if _enrich is not None:
                _enrich[ik] = base
        out.append({**base, "role": role})
    return out


# ---------------------------------------------------------------------------
# 修复（--repair）：逐域重推导，字节全等或响亮
# ---------------------------------------------------------------------------

def _assert_payload_unchanged(conn: sqlite3.Connection, payload_sha: str) -> None:
    """重推导后行账必须不变（确定性产物）；变=响应亮（item 陈旧须全量重建）。"""
    row = conn.execute("SELECT payload_sha256 FROM blobs WHERE payload_sha256=?",
                       (payload_sha,)).fetchone()
    if row is None:
        raise RuntimeError(
            f"repair 后行账消失 {payload_sha[:12]}…（item 陈旧？）——须全量重建")


def _repair_asset(conn: sqlite3.Connection, layout: SupplyLayout, win: Path,
                  owner: dict) -> dict:
    """art/watermark 项：source_json 的 (bundle,guid) 定点重解码（build worker
    本体=写面带验证）。payload sha 漂移=响亮。"""
    from eidolon.core.supply_index.cold import _decode_bundle_worker

    ik = owner["item_key"]
    src_row = conn.execute("SELECT source_json FROM items WHERE item_key=?",
                           (ik,)).fetchone()
    src = json.loads(src_row["source_json"])
    if not src or not src[0].get("guid"):
        raise RuntimeError(f"repair {ik[:12]}…: source_json 无 (bundle,guid)——"
                           "须全量重建")
    bundle, guid = src[0]["bundle"], src[0]["guid"]
    kind = owner["kind"] or "portrait"
    key = f"repair::{ik[:16]}"
    _bundle, results, _c, _o, _w = _decode_bundle_worker(
        (str(win), str(layout.root), bundle,
         [{"card_id": key, "kind": kind, "guid": guid}]))
    r = results[0]
    if not r.get("ok"):
        raise RuntimeError(f"repair {ik[:12]}…: 重解码失败 {r.get('error')}")
    row = conn.execute(
        "SELECT b.payload_sha256 FROM item_blobs ib JOIN blobs b "
        "ON b.blob_key=ib.blob_key WHERE ib.item_key=? AND ib.role=?",
        (ik, owner["role"])).fetchone()
    if r["payload_sha"] != row["payload_sha256"]:
        raise RuntimeError(
            f"repair {ik[:12]}…: 重解码 payload {r['payload_sha'][:12]}… ≠ 行账 "
            f"{row['payload_sha256'][:12]}…（确定性解码被破坏）——须全量重建")
    return {"item": ik, "mode": "asset-redecode", "payload": r["payload_sha"]}


def _repair_kit(conn: sqlite3.Connection, layout: SupplyLayout, win: Path,
                owner: dict) -> dict:
    """frames/gems 项：整 kit 重提取（六面+gem blob 带验证重写），逐 face 对行账。
    （gems 坏块由 repair() 归一到 ally kit item——frame 恒有值。）"""
    from eidolon.core.supply_index.cold import read_bundle_deps
    from eidolon.core.supply_index.kit_extract import (
        FRAME_SPECS_KIT,
        _extract_kit_now,
    )

    frame = owner["frame"]
    if frame not in FRAME_SPECS_KIT:
        # A6：harness 帧族（ally_premium/trinket/anomaly/bacon）=live 提取
        # 产物，kit_extract 转写域无此 spec——响亮指全量重建
        raise RuntimeError(
            f"repair kit {frame}: harness 域帧（A6 supplement_extract）坏块"
            "须全量重建（live 提取非单 blob 重推导面）")
    mrow = conn.execute(
        "SELECT manifest_json FROM items WHERE domain=? AND item=? AND params_json=?",
        (S.DOMAIN_FRAMES, owner.get("item") or S.ITEM_KIT,
         S.cjson({"frame": frame}))).fetchone()
    if mrow is None:
        raise RuntimeError(f"repair kit {frame}: kit item 缺失——须全量重建")
    m = json.loads(mrow["manifest_json"])
    deps = read_bundle_deps(win)
    out = _extract_kit_now(
        win, frame=frame, spec=FRAME_SPECS_KIT[frame], actor_ref=m["prefab_ref"],
        guid=m["guid"], bundle=m["bundle"], card_id=m.get("card_id"),
        dbf_id=m.get("dbf_id"), bundle_deps=deps, cache_root=layout.root)
    if not out.get("ok"):
        raise RuntimeError(f"repair kit {frame}: 重提取失败 {out.get('error')}")
    # 行账逐 face 对齐（kit 聚合 sha 变=响应亮）
    rows = {r["role"]: r["payload_sha256"] for r in conn.execute(
        "SELECT ib.role, b.payload_sha256 FROM item_blobs ib JOIN blobs b "
        "ON b.blob_key=ib.blob_key WHERE ib.item_key=?",
        (owner["item_key"],))}
    _verify_kit_faces(out["faces"], rows, frame)
    return {"item": owner["item_key"], "mode": "kit-reextract",
            "frame": frame}


def _verify_kit_faces(faces: dict, row_payloads: dict, frame: str) -> None:
    """重提取产物 payload sha vs 行账逐 face 相等（漂移=响亮）。"""
    expect = {}
    for face in KC.JSON_FACES:
        expect[face] = faces[face]["payload_sha256"]
    if faces["arrays"]["payload_sha256"]:
        expect["arrays"] = faces["arrays"]["payload_sha256"]
    for fname, facc in faces["textures"].items():
        expect[f"texture:{fname}"] = facc["payload_sha256"]
    for role, sha in expect.items():
        want = row_payloads.get(role)
        if want is None:
            continue      # 重提取新面（excluded 域回归等）——不在此扩账，扫面盯
        if want != sha:
            raise RuntimeError(
                f"repair kit {frame}: face {role} payload {sha[:12]}… ≠ 行账 "
                f"{want[:12]}…——须全量重建")


def _repair_text(conn: sqlite3.Connection, layout: SupplyLayout, win: Path,
                 owner: dict) -> dict:
    """text 项：extract_fonts 重提取，fontdefs/ttf 重写（写面带验证），对行账。"""
    from eidolon.core.supply_index import text_codec as TC
    from eidolon.core.supply_index.cold import _write_blob_atomic, read_manifest_tables
    from eidolon.core.supply_index.text_extract import extract_fonts

    mrow = conn.execute(
        "SELECT manifest_json FROM items WHERE item_key=?",
        (owner["item_key"],)).fetchone()
    m = json.loads(mrow["manifest_json"])
    ctx_locale = m.get("locale", "zhcn")
    tables = read_manifest_tables(win, ctx_locale)
    zhcat = {base: (guid, bundle) for base, _l, loc, guid, bundle
             in tables["variant_rows"] if loc == "zhcn"}
    fonts = extract_fonts(win, catalog=tables["catalog"], zhcat=zhcat,
                          bundle_deps=tables["bundle_deps"])
    if m.get("font") is None:
        # fontdefs 全表项
        data = TC.encode_fontdefs(fonts["fontdefs"])
        payload = S.sha256_hex(data)
        row = conn.execute(
            "SELECT b.payload_sha256 FROM item_blobs ib JOIN blobs b "
            "ON b.blob_key=ib.blob_key WHERE ib.item_key=? AND ib.role=?",
            (owner["item_key"], TC.ROLE_FONTDEFS)).fetchone()
        if payload != row["payload_sha256"]:
            raise RuntimeError("repair fontdefs: 重提取 canonical sha ≠ 行账——须全量重建")
        _write_blob_atomic(layout.root, payload, data, ext=".json")
        return {"item": owner["item_key"], "mode": "text-reextract",
                "what": "fontdefs"}
    name = m["font"]
    raw = fonts["ttfs"].get(name)
    if raw is None:
        raise RuntimeError(f"repair ttf {name}: 重提取无字节——须全量重建")
    payload = TC.ttf_content_sha(raw)
    row = conn.execute(
        "SELECT b.payload_sha256 FROM item_blobs ib JOIN blobs b "
        "ON b.blob_key=ib.blob_key WHERE ib.item_key=? AND ib.role=?",
        (owner["item_key"], TC.ROLE_TTF)).fetchone()
    if payload != row["payload_sha256"]:
        raise RuntimeError(f"repair ttf {name}: 文件 sha ≠ 行账——须全量重建")
    _write_blob_atomic(layout.root, payload, raw, ext=".ttf")
    return {"item": owner["item_key"], "mode": "text-reextract", "what": name}


def repair(conn: sqlite3.Connection, layout: SupplyLayout, win: Path,
           findings: dict) -> dict:
    """坏 blob 逐域定点重推导（gem 归一到 ally kit；同 item 多坏只修一次）。"""
    seen_items: dict[str, dict] = {}
    plan: list[tuple[str, dict]] = []
    for bad in (*findings["missing"], *findings["mismatch"]):
        for owner in bad["owners"]:
            if owner["item_key"] in seen_items:
                continue
            seen_items[owner["item_key"]] = owner
            dom = owner["domain"]
            if dom == S.DOMAIN and (owner.get("params") or {}).get("kind") \
                    == S.ITEM_PORTRAIT_MIP:
                plan.append(("mip", owner))         # A5：portrait_mip 链 blob
            elif dom == S.DOMAIN_TEXTURES:
                plan.append(("mip", owner))         # A5：mip_registry 全局项
            elif dom == S.DOMAIN_COLOR and owner.get("role") == "mip_chain":
                plan.append(("mip", owner))         # A5：atlas mip_chain blob
            elif dom in (S.DOMAIN, S.DOMAIN_WATERMARK):
                plan.append(("asset", owner))
            elif dom == S.DOMAIN_COLOR:
                # color：atlas=纹理项，(bundle,guid) 定点重解码（asset 同路）；
                # probe=switcher 表 typetree 直读（非纹理）——重解码不可达，响亮
                if (owner.get("params") or {}).get("family") is None:
                    raise RuntimeError(
                        "repair color probe: switcher 表项须全量重建（表读取非"
                        "单 blob 重推导面）")
                plan.append(("asset", owner))
            elif dom == S.DOMAIN_FRAMES:
                if owner.get("item") != S.ITEM_KIT:
                    # A6：kit_light（轻走查面无独立重提取形）+ supplement 域
                    # （ability/badges/btf/ornaments/ta/material_state/
                    # portrait_uv1）=live 提取 harness 产物，单 blob 重推导面
                    # 不存在——响亮指全量重建
                    raise RuntimeError(
                        f"repair: frames 域 item {owner.get('item')} 坏块"
                        "须全量重建（live harness 提取非单 blob 重推导面）")
                plan.append(("kit", owner))
            elif dom == S.DOMAIN_GEMS:
                # gems 源=ally kit 走查——归一到 ally kit item 重提取
                ally = conn.execute(
                    "SELECT item_key FROM items WHERE domain=? AND item=? "
                    "AND params_json=?", (S.DOMAIN_FRAMES, S.ITEM_KIT,
                                          S.cjson({"frame": "ally"}))).fetchone()
                if ally is None:
                    raise RuntimeError("repair gems: ally kit item 缺失——须全量重建")
                if ally["item_key"] in seen_items:
                    continue
                seen_items[ally["item_key"]] = {
                    "item_key": ally["item_key"], "role": "kit",
                    "domain": S.DOMAIN_FRAMES, "frame": "ally",
                    "gem": owner.get("gem")}
                plan.append(("kit", seen_items[ally["item_key"]]))
            elif dom == S.DOMAIN_TEXT:
                plan.append(("text", owner))
            else:
                raise RuntimeError(f"repair: 未知域 {dom}——须全量重建")

    results = []
    for kind, owner in plan:
        if kind == "asset":
            results.append(_repair_asset(conn, layout, win, owner))
        elif kind == "kit":
            results.append(_repair_kit(conn, layout, win, owner))
        elif kind == "mip":
            results.append(_repair_mip(conn, layout, win, owner))
        else:
            results.append(_repair_text(conn, layout, win, owner))
    return {"planned": len(plan), "repaired": results}


def _repair_mip(conn: sqlite3.Connection, layout: SupplyLayout, win: Path,
                owner: dict) -> dict:
    """mip 面（A5）：链 NPZ 定点重提取（同一解码器确定性产物），payload 对
    行账全等或响亮。三类：portrait_mip 项（source 裁决链级/marker）、
    mip_registry 全局项（23 链全量重提取）、color atlas 的 mip_chain role
    blob（全级 0..n-1）。"""
    from eidolon.core.supply_index import mip_codec as MC
    from eidolon.core.supply_index import mip_extract as ME
    from eidolon.core.supply_index._unity import iter_serialized, load_bundle
    from eidolon.core.supply_index.cold import _write_blob_atomic

    ik = owner["item_key"]
    role = owner.get("role") or "chain"
    row = conn.execute(
        "SELECT b.payload_sha256, b.size FROM item_blobs ib JOIN blobs b "
        "ON b.blob_key=ib.blob_key WHERE ib.item_key=? AND ib.role=?",
        (ik, role)).fetchone()
    if row is None:
        raise RuntimeError(
            f"repair mip {ik[:12]}…: blob 行缺失 role={role}——须全量重建")

    def _payload_for(manifest: dict) -> bytes:
        if owner.get("domain") == S.DOMAIN_TEXTURES:
            # registry：23 链全量重提取（注册表=单一 blob）
            arrays = {}
            for r_name, r_bundle, r_pid in ME.MIP_CHAINS:
                _b, results, _w = ME.extract_registry_worker(
                    (str(win), r_bundle, [(r_name, r_bundle, r_pid)]))
                r = results[0]
                if r.get("error"):
                    raise RuntimeError(
                        f"repair mip registry: {r_name} 重提取失败 {r['error']}")
                for i, lod in enumerate(r["lods"]):
                    arrays[MC.registry_chain_key(r_name, i)] = lod
            return MC.encode_chain_npz(arrays)
        if owner.get("role") == "mip_chain":
            # color atlas 链：全级 0..n-1（图集链无派生面）
            obj = _find_mip_texture(win, manifest)
            head = ME.texture_head(obj.read_typetree())
            lods = ME.extract_all_levels(obj.read().get_image_data(),
                                         fmt=head["fmt"], w=head["w"],
                                         h=head["h"], n=head["n"],
                                         name=head["name"])
            return MC.encode_chain_npz(
                {MC.level_key(i): lod for i, lod in enumerate(lods)})
        source = manifest.get("source")
        if source in ("registry", "portrait"):
            return MC.meta_marker_payload()
        # portrait_mip 链源：manifest l0 裁决链级（1..n-1 / explicit 0..n-1）
        obj = _find_mip_texture(win, manifest)
        head = ME.texture_head(obj.read_typetree())
        lods = ME.extract_all_levels(obj.read().get_image_data(),
                                     fmt=head["fmt"], w=head["w"],
                                     h=head["h"], n=head["n"], name=head["name"])
        if manifest.get("l0") == "explicit":
            return MC.encode_chain_npz(
                {MC.level_key(i): lod for i, lod in enumerate(lods)})
        return MC.encode_chain_npz(
            {MC.level_key(i): lod for i, lod in enumerate(lods[1:])})

    mrow = conn.execute("SELECT manifest_json FROM items WHERE item_key=?",
                        (ik,)).fetchone()
    if mrow is None:
        raise RuntimeError(f"repair mip {ik[:12]}…: item 行缺失——须全量重建")
    manifest = json.loads(mrow["manifest_json"])
    payload = _payload_for(manifest)
    payload_sha = S.sha256_hex(payload)
    if payload_sha != row["payload_sha256"]:
        raise RuntimeError(
            f"repair mip {ik[:12]}…: 重提取 payload {payload_sha[:12]}… ≠ 行账 "
            f"{row['payload_sha256'][:12]}…（确定性解码被破坏）——须全量重建")
    _write_blob_atomic(layout.root, payload_sha, payload, ext=".npz")
    return {"item": ik, "mode": "mip-reextract", "role": role}


def _find_mip_texture(win: Path, manifest: dict):
    """mip 项 manifest (bundle, path_id, name) → Texture2D 对象（重提取寻址）。

    name 面两形态：portrait_mip manifest.name 直在；atlas manifest 名在
    manifest["mip"]["name"]（mip 账段——A5 落库形）。"""
    from eidolon.core.supply_index import mip_extract as ME
    from eidolon.core.supply_index._unity import iter_serialized, load_bundle

    bundle = manifest.get("bundle")
    path_id = int(manifest.get("path_id") or 0)
    mip_seg = manifest.get("mip") or {}
    name = manifest.get("name") or mip_seg.get("name")
    env = load_bundle(win / bundle)
    for sf in iter_serialized(env):
        obj = ME._find_texture(sf, name, path_id)
        if obj is not None and obj.read_typetree().get("m_Name") == name:
            return obj
    raise RuntimeError(
        f"repair mip: bundle {bundle} 内无纹理 {name!r}（path_id={path_id}）"
        "——须全量重建")


def integrity(cache_root: Path | str, *, game: Path, locale: str,
              do_repair: bool = False) -> dict:
    """完整性扫（+可选修复）。返回账面；bad>0 由 CLI 退出面报 1。

    工具面 open 自检（quick_check 一次，含打不开形态——SupplyIndex 同判据）；
    报告头=media_event 介质级事件标记（mass-bad 批量口径）；留账=selfheal_*
    计数（--repair 成功修复计 repair_items）。game/locale 必填（--repair 重推导
    =cold 面，显式身份；纯扫描不触）。"""
    from eidolon.core.infra import context
    from eidolon.core.infra.game_install import assert_game_root, resolve_context
    from eidolon.contracts import GameRequest
    from eidolon.core.supply_index.selfheal import (
        bump_counters,
        media_event,
        read_counters,
    )
    from eidolon.core.supply_index.warm import SupplyIndexCorruptError

    layout = SupplyLayout(cache_root)
    cur = layout.read_current()
    if cur is None:
        raise FileNotFoundError(f"supply 缓存无 current.json：{layout.root}")
    db = layout.gen_db(cur["game_id"])
    _open_checked(db)
    conn = S.connect(db)
    try:
        findings = scan(conn, layout)
        out: dict = {"cache_root": str(layout.root),
                     "generation": cur.get("generation"),
                     "media_event": media_event(findings["bad"],
                                                findings["rows"]),
                     "scan": {k: findings[k] for k in
                              ("rows", "ok", "bad")},
                     "missing": findings["missing"],
                     "mismatch": findings["mismatch"]}
        out["selfheal"] = read_counters(conn)
        if do_repair and findings["bad"]:
            ctx = resolve_context(GameRequest(Path(game), "--game"),
                                  cache_root=Path(cache_root), locale=locale or "zhcn")
            context.install(ctx)        # 同身份幂等；异身份 raise（进程单渲染身份）
            assert_game_root(ctx.root)
            rep = repair(conn, layout, ctx.data_win, findings)
            out["repair"] = rep
            findings2 = scan(conn, layout)
            out["rescan"] = {"rows": findings2["rows"], "ok": findings2["ok"],
                             "bad": findings2["bad"],
                             "missing": findings2["missing"],
                             "mismatch": findings2["mismatch"]}
            out["bad"] = findings2["bad"]
            try:
                out["selfheal"] = bump_counters(
                    db, repair_items=len(rep.get("repaired", [])), event={
                        "kind": "integrity_repair",
                        "bad_before": findings["bad"],
                        "bad_after": findings2["bad"]})
            except Exception:                           # noqa: BLE001
                pass        # 留账失败不掩盖修复结果本身
        else:
            out["bad"] = findings["bad"]
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# L2/L3：单点重推导（auto 自愈）+ 源坏/换代诊断分级
# ---------------------------------------------------------------------------

class RederiveMismatchError(RuntimeError):
    """L3：重推导 sha ≠ 行账（源坏或版本换代）——诊断分级消息（diagnose_source）。"""


def _open_checked(db: Path) -> None:
    """integrity/repair 工具面 open 自检（quick_check 一次；含打不开形态）。

    损坏=SupplyIndexCorruptError 响亮「索引损坏需重建」（SupplyIndex 同判据；
    本命令不自动重建——重建=cold build 全量，交 auto/人工）。"""
    from eidolon.core.supply_index.warm import SupplyIndexCorruptError

    try:
        conn = S.connect(db)
    except sqlite3.Error as exc:
        raise SupplyIndexCorruptError(
            f"supply 索引损坏需重建（DB 打不开：{type(exc).__name__}: {exc}；"
            f"db={db}）——cold build 全量重建") from exc
    try:
        qc = conn.execute("PRAGMA quick_check(8)").fetchall()
        if not (len(qc) == 1 and qc[0][0] == "ok"):
            raise SupplyIndexCorruptError(
                "supply 索引损坏需重建（quick_check: "
                + "; ".join(r[0] for r in qc[:8])
                + f"；db={db}）——cold build 全量重建（本命令不自动重建）")
    finally:
        conn.close()


def diagnose_source(layout: SupplyLayout, db_game_id: str, *,
                    game: Path, locale: str,
                    ident: dict | None = None) -> str:
    """L3 诊断分级：重推导 sha ≠ 行账 时判「版本换代 vs 同代源坏」。

    game_id 变更本来就该整库重建（判据写进错误信息）；同代=源内容漂移/确定性
    破坏。ident=预计算身份（测试缝；缺省现算——触游戏身份面，game/locale 必填）。"""
    if ident is None:
        try:
            from eidolon.core.infra import context
            from eidolon.core.infra.game_install import assert_game_root, resolve_context
            from eidolon.contracts import GameRequest
            from eidolon.core.supply_index import cold as _cold

            ctx = resolve_context(GameRequest(Path(game), "--game"),
                                  cache_root=Path(layout.root),
                                  locale=locale or "zhcn")
            context.install(ctx)
            assert_game_root(ctx.root)
            ident = _cold.compute_identity(ctx.data_win, ctx.version,
                                           dll_path=ctx.assembly_csharp)
        except Exception as exc:                        # noqa: BLE001
            return (f"诊断不可用（{type(exc).__name__}: {exc}）——保守判据："
                    "整库重建（cold build 全量）")
    cur_gid = ident.get("game_id", "")
    if cur_gid != db_game_id:
        return (f"版本换代：当前 game_id {cur_gid[:12]}… ≠ 建库 "
                f"{db_game_id[:12]}…——game_id 变更本来就该整库重建"
                "（cold build 全量），逐块自愈无意义")
    return (f"同代源坏：游戏身份未变（game_id {cur_gid[:12]}…）而重推导 sha ≠ "
            "行账（源内容漂移/确定性解码破坏）——整库重建（cold build 全量）"
            "并人工复查该源")


def rederive_one(cache_root: Path | str, payload_sha: str, *,
                 game: Path, locale: str,
                 ident: dict | None = None) -> dict:
    """L2 单点重推导（auto 自愈面；=repair 单点形态）。

    沿 recorded source（items.source_json/manifest_json 的 bundle+guid 等账面
    地址）重推导**单个**坏 blob：重推导 sha 与行账**全等才算修好**（写面
    _write_blob_atomic 带验证重写），修好后复验盘上字节并留账；不等=L3
    RederiveMismatchError（诊断分级：版本换代/同代源坏）。单次语义由编排层
    （selfheal.assemble_with_heal）执行——本函数不重试。game/locale 必填。"""
    from eidolon.core.infra import context
    from eidolon.core.infra.game_install import assert_game_root, resolve_context
    from eidolon.contracts import GameRequest
    from eidolon.core.supply_index._unity import sha256_file
    from eidolon.core.supply_index.selfheal import bump_counters

    layout = SupplyLayout(cache_root)
    cur = layout.read_current()
    if cur is None:
        raise FileNotFoundError(f"supply 缓存无 current.json：{layout.root}")
    db = layout.gen_db(cur["game_id"])
    conn = S.connect(db)
    try:
        owners = attribute(conn, layout, payload_sha)
        if not owners:
            raise RederiveMismatchError(
                f"L2 rederive {payload_sha[:12]}…: 无属主 item 行（blob 行账孤儿/"
                f"item 缺）——须全量重建（db={db}）")
        findings = {"missing": [{"payload_sha256": payload_sha,
                                 "owners": owners}],
                    "mismatch": [], "bad": 1}
        ctx = resolve_context(GameRequest(Path(game), "--game"),
                              cache_root=Path(cache_root), locale=locale or "zhcn")
        context.install(ctx)            # 同身份幂等；异身份 raise（进程单渲染身份）
        assert_game_root(ctx.root)
        try:
            rep = repair(conn, layout, ctx.data_win, findings)
        except RuntimeError as exc:
            diag = diagnose_source(layout, cur["game_id"], game=game,
                                   locale=locale, ident=ident)
            try:
                bump_counters(db, l2_failures=1, event={
                    "kind": "l2_rederive_fail",
                    "blob": payload_sha[:12], "why": str(exc)[:200]})
            except Exception:                       # noqa: BLE001
                pass
            raise RederiveMismatchError(
                f"L2 重推导失败：{exc}——L3 诊断分级：{diag}") from exc
        # 修好判定（双证）：repair 逐域已对行账 sha；此处复验盘上文件字节。
        row = conn.execute(
            "SELECT payload_sha256, size, codec FROM blobs WHERE payload_sha256=?",
            (payload_sha,)).fetchone()
        if row is None:
            raise RederiveMismatchError(
                f"L2 rederive {payload_sha[:12]}…: 修后行账消失——须全量重建")
        p = layout.blob_path(row["payload_sha256"], ext=_ext(row["codec"]))
        if not p.is_file() or sha256_file(p) != row["payload_sha256"]:
            raise RederiveMismatchError(
                f"L2 rederive {payload_sha[:12]}…: 重推导后盘上文件仍≠行账"
                f"（{p.name}）——单次重试铁律交编排层；人工介入 integrity --repair")
        try:
            bump_counters(db, l2_rederives=1, event={
                "kind": "l2_rederive", "blob": payload_sha[:12],
                "mode": (rep.get("repaired") or [{}])[0].get("mode", "")})
        except Exception:                           # noqa: BLE001
            pass
        return {"payload_sha256": payload_sha, "owners": len(owners),
                "repair": rep}
    finally:
        conn.close()
