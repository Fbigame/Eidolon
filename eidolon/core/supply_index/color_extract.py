"""color_extract — color 域 UnityPy 面提取（Phase 1 A4；cold 编排、本单点）。

两件：switcher 表直读（probe item 源）+ 类色图集解码 worker（atlas items 源）。
纪律沿 cold/kit_extract/text_extract 同款：container 读取一律 SerializedFile
.container.container 原始 pairs（禁 env.container）；UnityPy 非线程安全→按
bundle 分进程（worker spawn 可 pickle）。

live 对位（eidolon/core/supply/color.py，形状逐字复刻——S1 种子形状契约）：
  - probe ← _probe_build/_families：resolve(_SWITCHER_REF)→container→GO 组件
    直读；list 值族全量（空串占位槽原样保留——ColorType 下标对齐语义），键序=
    序列化字段声明序（drift_probe B3 升版互证面，JSON 落盘保序）；
  - atlas(family, ct) ← probe 族表 ref→resolve→Texture2D.image（1024² RGBA 纹理
    族；faction* 等材质族 reader 非 Texture2D——本域参数域外，cold 记账跳过，
    warm 缺项 fail loud 与 live assert 同响亮面）。
"""
from __future__ import annotations

import time
from pathlib import Path

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index._unity import (
    container_pairs,
    iter_serialized,
    load_bundle,
    path_id_for,
)

# 链根=游戏自己的引导寻址（supply.color._SWITCHER_REF 同源串——**逐字符一致**
# 是链面契约：live 与 cold 必须解析同一对象）；本体识别谓词同理（_SWITCHER_KEYS）。
SWITCHER_REF = "CardColorSwitcher.prefab:b30c8322821f1524d9e08a59e78e2c85"
SWITCHER_KEYS = {"minionCardTextures", "spellCardTextures"}


def read_switcher_probe(win: Path, catalog: dict, variants_by_base: dict) -> dict:
    """switcher 表真内存构建（cold 版 live `_probe_build/_families`）。

    链根 ref→catalog/变体→(guid, bundle)→container pairs→GO 组件直读；组件
    PPtr FileID=0（同文件）按本 sf 对象解，其余跳过（live resolve_pptr 同链——
    switcher 组件与 GO 同包实证）；未命中本体=KeyError 响亮（fail loud，禁静默
    窄扫——live「失效即红」同纪律）。

    返回 {"families": {...}, "bundle": bundle, "cab": cab,
          "path_id": GO path_id, "guid": resolved guid}。"""
    guid, bundle = _resolve_ref(SWITCHER_REF, catalog, variants_by_base)
    if not bundle:
        raise KeyError(f"color probe: 链根 ref 不在 catalog（{SWITCHER_REF}）——"
                       "链根失效属语料级事件，fail loud（live 同响）")
    env = load_bundle(win / bundle)
    sf = next(iter_serialized(env))
    pairs = {k: pid for k, pid in container_pairs(sf)}
    cab = Path(str(getattr(sf, "name", ""))).name.lower()
    pid = path_id_for(pairs, guid)
    if pid is None:
        raise KeyError(f"color probe: 链根 guid {guid} 不在 bundle {bundle} "
                       "container——链根失效 fail loud")
    go = sf.objects[pid]
    tt = go.read_typetree()
    for comp in tt.get("m_Component", []):
        p = comp.get("component") or {}
        cpid = p.get("m_PathID")
        if not cpid or p.get("m_FileID", 0):
            continue          # 同文件组件才算（跨包组件不在 switcher 形态内）
        try:
            tree = sf.objects[cpid].read_typetree()
        except Exception:     # noqa: BLE001  组件级解析缺位→跳过（live 同形）
            continue
        if isinstance(tree, dict) and SWITCHER_KEYS & set(tree):
            return {"families": _families(tree), "bundle": bundle, "cab": cab,
                    "path_id": int(go.path_id), "guid": guid}
    raise KeyError("color probe: switcher 组件未命中（链根可解析但本体缺位）"
                   "——fail loud（live AssertionError 同判）")


def _families(tree: dict) -> dict[str, list[str]]:
    """族表直出（supply/color._families 逐字）：list 值族全量，非串槽位剔除、
    空串占位槽保留（ColorType 下标对齐语义）；键序=typetree 序（落盘保序）。"""
    return {k: [x for x in v if isinstance(x, str)]
            for k, v in tree.items() if isinstance(v, list)}


def _resolve_ref(ref: str, catalog: dict, variants_by_base: dict
                 ) -> tuple[str, str | None]:
    """「名:GUID」→ (resolved_guid, bundle)（cold._resolve_ref 同款变体叠加）。"""
    _, guid = ref.rsplit(":", 1)
    g = guid.lower()
    v = variants_by_base.get(g)
    if v:
        vg, vb = v
        return vg, (catalog.get(vg) or vb)
    return g, catalog.get(g)


def decode_color_atlas_worker(payload):
    """单包 worker：一包一开，解多 (family, ct) 图集 → PNG → blob 落盘。

    形状对位 cold._decode_bundle_worker（返回同构），差异三处：
    - 任务标签=(family, ct)（非 card_id/kind）；
    - guid 去重：同包同 guid 多槽（BG anomaly/trinket 族 45-50 槽同纹理）解一次
      逐槽回填（watermark guid 去重同式）；
    - 类型分类：Texture2D→解码；Material 等非纹理→ok=False + error=
      "material-slot: <type>"（**计划内参数域外**——color.atlas 仅纹理族，
      live assert 同边界；调用方按前缀分类记账，不算解码失败）。
    对象级异常逐任务捕获记账，包级异常整包报错（禁静默吞，portrait worker 判例）。

    A5 mip 账：Texture2D 解码顺带读 typetree 记每槽 mip 判定（m_MipCount/name/
    filter/bias——entry_for_ref 的 seeded 查找数据面；mips=1=「无链」裁决值）；
    mips>1 全级提取落 NPZ（全级含 L0——图集链无派生面，0..n-1 逐级在位）。
    链提取失败≠图集解码失败：mip.error 记账、图集照常出货（调用方把 mip 账
    缺失如实落 manifest，不炸图集）。"""
    win_s, cache_root_s, bundle, tasks = payload
    win = Path(win_s)
    from eidolon.core.supply_index.cold import _encode_png, _write_blob_atomic
    from eidolon.core.supply_index import mip_codec as MC
    from eidolon.core.supply_index import mip_extract as ME

    import numpy as np

    t0 = time.time()
    try:
        env = load_bundle(win / bundle)
    except Exception as exc:  # noqa: BLE001
        return (bundle,
                [{**t, "ok": False, "error": f"bundle-open: {type(exc).__name__}: {exc}"}
                 for t in tasks],
                [], [], time.time() - t0)
    container_rows = []
    sf_indexes = []
    for sf in iter_serialized(env):
        cab = Path(str(getattr(sf, "name", ""))).name.lower()
        pairs = container_pairs(sf)
        for i, (k, pid) in enumerate(pairs):
            container_rows.append((bundle, k, pid, i))
        idx: dict[str, int] = {}
        for k, pid in pairs:
            kl = k.lower()
            idx.setdefault(kl, pid)
            tail = kl.rsplit("/", 1)[-1]
            idx.setdefault(tail, pid)
        sf_indexes.append((cab, sf, idx))

    results: list[dict] = []
    object_rows = []
    root = Path(cache_root_s)
    decoded: dict[str, dict] = {}     # guid → ok 结果（同包去重）
    for t in tasks:
        guid = t["guid"].lower()
        hit = next(((cab, sf, idx) for cab, sf, idx in sf_indexes if guid in idx),
                   None)
        if hit is None:
            results.append({**t, "ok": False, "error": "guid-not-in-container"})
            continue
        cab, sf, idx = hit
        try:
            memo = decoded.get(guid)
            if memo is None:
                obj = sf.objects[idx[guid]]
                if obj.type.name != "Texture2D":
                    memo = {"ok": False,
                            "error": f"material-slot: {obj.type.name}"}
                else:
                    img = obj.read().image
                    pixel_sha = S.sha256_hex(img.tobytes())
                    png = _encode_png(img)
                    payload_sha = S.sha256_hex(png)
                    _rel, fresh = _write_blob_atomic(root, payload_sha, png)
                    object_rows.append((bundle, cab, int(obj.path_id),
                                        int(getattr(obj.type, "value", 0) or 0),
                                        int(obj.byte_start), int(obj.byte_size)))
                    memo = {"ok": True, "bundle": bundle,
                            "path_id": int(obj.path_id), "cab": cab,
                            "width": img.width, "height": img.height,
                            "mode": img.mode, "pixel_sha": pixel_sha,
                            "payload_sha": payload_sha, "payload_size": len(png),
                            "blob_fresh": fresh}
                    memo["mip"] = _atlas_mip_account(obj, bundle, root, MC, ME, np)
                decoded[guid] = memo
            results.append({**t, **memo})
        except Exception as exc:  # noqa: BLE001
            results.append({**t, "ok": False,
                            "error": f"decode: {type(exc).__name__}: {exc}"})
    return (bundle, results, container_rows, object_rows, time.time() - t0)


def _atlas_mip_account(obj, bundle: str, root: Path, MC, ME, np) -> dict:
    """图集纹理的 mip 判定账（A5；Texture2D 在手、图集已解码）。

    mips=1 → {"count":1,"name":...}（「无链」裁决值——seeded 查找面返回 None
    与 live entry_for_ref 同判）；mips>1 → 全级提取（0..n-1，图集链无派生面）
    → NPZ 落盘 + filter/bias 账。失败=mip.error 记账（图集照常出货）。"""
    try:
        tree = obj.read_typetree()
        head = ME.texture_head(tree)
        acc = {"count": head["n"], "name": head["name"],
               "filter": head["filter"], "bias": float(head["bias"]),
               "chain_payload_sha256": "", "chain_payload_size": 0,
               "chain_content_sha": "", "chain_blob_fresh": False, "error": None}
        if head["n"] <= 1:
            return acc
        data = obj.read().get_image_data()
        lods = ME.extract_all_levels(data, fmt=head["fmt"], w=head["w"],
                                     h=head["h"], n=head["n"], name=head["name"])
        payload = MC.encode_chain_npz(
            {MC.level_key(i): lod for i, lod in enumerate(lods)})
        payload_sha = S.sha256_hex(payload)
        _rel, fresh = _atlas_write_blob(root, payload_sha, payload)
        acc.update({"chain_payload_sha256": payload_sha,
                    "chain_payload_size": len(payload),
                    "chain_content_sha": MC.chain_content_sha(lods),
                    "chain_blob_fresh": fresh})
        return acc
    except Exception as exc:  # noqa: BLE001 ——链账失败≠图集失败
        return {"count": None, "name": None, "filter": None, "bias": None,
                "chain_payload_sha256": "", "chain_payload_size": 0,
                "chain_content_sha": "", "chain_blob_fresh": False,
                "error": f"mip-extract: {type(exc).__name__}: {exc}"}


def _atlas_write_blob(root: Path, payload_sha: str, payload: bytes) -> tuple:
    """npz blob 落盘（cold._write_blob_atomic 转发——worker 内函数体 import）。"""
    from eidolon.core.supply_index.cold import _write_blob_atomic

    return _write_blob_atomic(root, payload_sha, payload, ext=".npz")
