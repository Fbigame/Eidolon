"""supplement_extract — cold 侧 supplement 域捕获（A6；live 提取链 harness）。

**包边界修订（设计账，supply-source.md §5 同步）**：cold 侧原「零 import 参照族」
纪律针对的是**转写域**（kit_extract/text_extract/wm_extract/mip_extract——五帧族
kit/fontdefs/watermark/mip 的走查引擎逐字转写，_KitResolver 免 route）。A6 的
特源/附件 kit 面（ability_kit/bacon/badges/btf/ornaments/ta_supplement/
material_state/portrait_uv1/font_asset_params）值面=live 域函数的内存产物对象，
转写=数千行且形状漂移风险面大——本域改走 **live 提取 harness**：独立子进程
install ctx（**route_mode="off"**——cold 不进 route 航线库，原纪律的实质边界
保持）+ session，逐字调用 live 提取器，产物编码为 content 寻址 blob。值面因此
**构造性=live 值**（零转写漂移）；container/object 证据账不入（harness 无
_KitResolver——item source_json 记 harness 来路）。

标准六帧族 kit 仍走 kit_extract 转写域（byte 级已由 A3 e2e 逐位对拍钉死）；
ally_premium/trinket/anomaly/bacon 四 kit + kit_light×9 走 harness（同 kit
六面 codec 落库——kit_extract._encode_kit_faces 编码复用），races 面随 kit
自带（live spec races=True 帧族：ally_premium/trinket）。

worker 内存形：单子进程顺序捕获（live 提取器自带进程 memo——kit_light×9 被
material_state 复用、六帧族 kit 由 ta/portrait_uv1 复用；注入面=KitRecon 已建
kit 的 faces 读回，免重走查）。ndarray/PIL 不出进程（blob 字节 worker 内写盘），
返回账面全 picklable。单项失败=该项 error 记账（item 缺建 → warm 缺项响亮 →
seed 该 token 不种回 live），不炸整批。

值形状契约：``_supp_value`` 的 parts 形与 ``seed._convert_supplements`` 的
重组形是一张表的两半（两处必须同步改；单测钉死）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

logger = logging.getLogger(__name__)

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index import supp_codec as SC

# harness 域捕获清单（A6 任务单 §7；kit 六面件与 supp parts 件两类）
HARNESS_KIT_FRAMES = ("ally_premium", "trinket", "anomaly", "bacon")
HARNESS_KIT_LIGHT_FRAMES = ("ally", "ally_premium", "weapon", "heropower",
                            "location", "hero_hand", "hero_play", "trinket",
                            "anomaly")
SUPP_ITEMS = ("badges_kit", "btf_kit", "ornaments_kit", "ta_supplement",
              "material_state", "portrait_uv1")


class _NullResolver:
    """harness 编码的证据账替位（_encode_kit_faces 的 resolver 参数形；
    container/object 证据账=空列表——harness 无 _KitResolver 走查面）。"""

    def __init__(self) -> None:
        self.object_rows: list[tuple] = []
        self.container_rows: list[tuple] = []

    def note_object(self, obj, bundle: str) -> None:  # noqa: D102
        return

    def record_container(self, bundle: str) -> None:  # noqa: D102
        return


# ---------------------------------------------------------------------------
# worker（单进程顺序捕获；ProcessPoolExecutor max_workers=1 或直调）
# ---------------------------------------------------------------------------

def capture_worker(payload: dict) -> dict:
    """harness 捕获进程入口：install ctx（route off）→ session → 顺序捕获 →
    编码落 blob → 账面返回。

    payload["win"]=**游戏安装根**（resolve_context 语义——非 data_win；cold
    侧传 ctx.root）。"""
    win = Path(payload["win"])
    cache_root = Path(payload["cache_root"])
    loc = payload["locale"]
    kit_manifests: dict[str, str] = payload.get("kit_manifests") or {}
    out: dict = {"kits": [], "kit_light": [], "supp": [], "errors": [],
                 "injected": sorted(kit_manifests)}
    try:
        _setup_ctx(win, cache_root, loc)
    except Exception as exc:  # noqa: BLE001
        out["errors"].append({"item": "__ctx__",
                              "error": f"{type(exc).__name__}: {exc}"})
        return out

    import eidolon.core.supply.frames.kits as kits_mod
    from eidolon.core.supply import machine

    injected: dict[str, int] = {}
    for frame, mjson in kit_manifests.items():
        try:
            kits_mod._KIT_CACHE.setdefault(
                frame, _kit_from_manifest(json.loads(mjson), cache_root))
            injected[frame] = 1
        except Exception as exc:  # noqa: BLE001
            out["errors"].append({"item": f"inject:{frame}",
                                  "error": f"{type(exc).__name__}: {exc}"})
    out["injected"] = sorted(injected)

    with machine.session():
        # ---- kit 六面件（特源四帧 + kit_light×9） ----
        for frame in HARNESS_KIT_FRAMES:
            try:
                if frame == "bacon":
                    from eidolon.core.supply.frames.bacon import bacon_kit
                    kit = bacon_kit()
                else:
                    kit = kits_mod.kit(frame)
                out["kits"].append(_kit_account(frame, kit, cache_root,
                                                light=False))
            except Exception as exc:  # noqa: BLE001
                out["errors"].append({"item": f"kit:{frame}",
                                      "error": f"{type(exc).__name__}: {exc}"})
        for frame in HARNESS_KIT_LIGHT_FRAMES:
            try:
                kit = kits_mod.kit_light(frame)
                out["kit_light"].append(_kit_account(frame, kit, cache_root,
                                                     light=True))
            except Exception as exc:  # noqa: BLE001
                out["errors"].append({"item": f"kit_light:{frame}",
                                      "error": f"{type(exc).__name__}: {exc}"})

        # ---- supp parts 件（ability_kit quality 分片在前——material_state/
        #      portrait_uv1 的进程 memo 依赖面） ----
        for q in ("normal", "premium"):
            try:
                value, source = _ability_value(q)
                out["supp"].append(_supp_account(
                    S.ITEM_ABILITY_KIT, {"quality": q}, value, source,
                    cache_root))
            except Exception as exc:  # noqa: BLE001
                out["errors"].append({"item": f"{S.ITEM_ABILITY_KIT}:{q}",
                                      "error": f"{type(exc).__name__}: {exc}"})
        for item in SUPP_ITEMS:
            try:
                value, source = _supp_value(item)
                out["supp"].append(_supp_account(item, {}, value, source,
                                                 cache_root))
            except Exception as exc:  # noqa: BLE001
                out["errors"].append({"item": item,
                                      "error": f"{type(exc).__name__}: {exc}"})
        try:
            from eidolon.core.supply.text import font_asset_params as _fap

            out["supp"].append(_supp_account(
                S.ITEM_FONT_ASSET_PARAMS, {}, {"data": _fap()},
                {"source": "text.font_asset_params（harness live 域函数）"},
                cache_root, domain=S.DOMAIN_TEXT))
        except Exception as exc:  # noqa: BLE001
            out["errors"].append({"item": S.ITEM_FONT_ASSET_PARAMS,
                                  "error": f"{type(exc).__name__}: {exc}"})
    out["errors"].extend(_drain_unknown_misses())
    return out


def _setup_ctx(win: Path, cache_root: Path, loc: str) -> None:
    """worker 进程身份安装（route_mode="off"——cold 不进 route 航线库）+ dbf。"""
    from eidolon.contracts import GameRequest
    from eidolon.core.infra import context, dbf
    from eidolon.core.infra.game_install import resolve_context

    ctx = resolve_context(GameRequest(win, "--game"),
                          cache_root=cache_root, locale=loc)
    ctx = replace(ctx, route_mode="off")
    context.install(ctx)
    if dbf.installed_default() is None:
        from eidolon.core.infra.dbf import DbfModule

        dbf.install_default(DbfModule(ctx.dbf_path))


def _drain_unknown_misses() -> list[dict]:
    """live 提取器的未知 PPtr miss 台账排干（证据性；builtin 不入账）。"""
    try:
        from eidolon.core.infra.resolve_asset_ref import unknown_misses_since

        return [{"item": "pptr_unknown_miss", "error": n}
                for n in unknown_misses_since(0)]
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# kit 六面件编码（kit_extract worker 结果同形——_write_kit_items 直吃）
# ---------------------------------------------------------------------------

def _kit_account(frame: str, kit, cache_root: Path, *, light: bool) -> dict:
    """live Kit → kit_extract worker 结果同形账（_encode_kit_faces 编码复用）。"""
    from eidolon.core.supply_index.cold import _write_blob_atomic
    from eidolon.core.supply_index.kit_extract import (
        EXCLUDED_FACES,
        _encode_kit_faces,
    )

    meta_face = {k: v for k, v in kit.meta.items() if k != "hierarchy"}
    hierarchy = kit.meta["hierarchy"]
    arrays = dict(kit.arrays)
    textures = dict(kit.textures)
    # tex_saved 账自 report.textures 读回（live rec.tex_saved 的 used_by 已并入
    # report 条目；_encode_kit_faces 只用 file→info 映射补 faces.textures.source）
    tex_saved = {e["file"]: e for e in (kit.report.get("textures") or [])
                 if isinstance(e, dict) and e.get("file")}
    result = _encode_kit_faces(
        frame=frame, meta=meta_face, hierarchy=hierarchy, report=kit.report,
        ubertext=kit.ubertext, arrays=arrays, textures=textures,
        tex_saved=tex_saved, prefab_bundle=str(kit.meta.get("bundle") or ""),
        root_go=None, issues=list(kit.report.get("issues") or []),
        resolver=_NullResolver(), cache_root=cache_root,
        races=kit.races if isinstance(kit.races, dict) else None,
        mesh_refs={k: (v[0], int(v[1])) for k, v in kit.mesh_refs.items()})
    result["capture"] = "supplement-harness" + (" light" if light else "")
    result["identity"] = {
        "actor_ref": kit.meta.get("prefab_ref"),
        "guid": kit.meta.get("guid"),
        "bundle": kit.meta.get("bundle"),
        "card_id": kit.meta.get("card_id"),
        "dbf_id": kit.meta.get("dbf_id"),
    }
    n_nodes = sum(1 for _ in _iter_nodes(hierarchy))
    result["counts"] = {"nodes": n_nodes, "arrays": len(arrays),
                        "textures": len(textures),
                        "ubertext": len((kit.ubertext or {}).get("nodes") or []),
                        "issues": len(result["issues"])}
    result["excluded"] = dict(EXCLUDED_FACES)
    result["container_rows"] = []
    result["object_rows"] = []
    return result


def _iter_nodes(node):
    yield node
    for c in node.get("children") or []:
        yield from _iter_nodes(c)


def _kit_from_manifest(manifest: dict, cache_root: Path):
    """KitRecon kit item faces → live Kit 对象（ta/portrait_uv1 的 memo 注入形）。

    blob 读=manifest faces 的 rel 直读（build_kits 已落盘；worker 免 DB 依赖——
    build DB 事务未提交，子进程连接不可见）；faces payload sha 逐面校验。"""
    from eidolon.core.supply.frames.kits import Kit, _ArrayDict
    from eidolon.core.supply_index import kit_codec as KC

    def blob_bytes(role: str) -> bytes:
        # role 三形：JSON 面/arrays=faces 顶层键；texture:fname=faces["textures"]
        # 嵌套键（_encode_kit_faces 账形——注入读回同构）
        if role.startswith("texture:"):
            face = (manifest["faces"].get("textures") or {}).get(
                role.split(":", 1)[1])
        else:
            face = manifest["faces"].get(role)
        if face is None or not face.get("blob"):
            raise KeyError(f"kit {manifest.get('frame')}: faces 无 {role} blob")
        p = cache_root / face["blob"]
        data = p.read_bytes()
        if S.sha256_hex(data) != face["payload_sha256"]:
            raise ValueError(f"kit {manifest.get('frame')}: {role} blob sha 失配")
        return data

    six = KC.decode_kit(manifest, blob_bytes, verify_content=False)
    extra: dict = {}
    for face in KC.EXTRA_JSON_FACES:
        if face in manifest["faces"]:
            extra[face] = json.loads(blob_bytes(face).decode("utf-8"))
    meta = {**six["meta"], "hierarchy": six["hierarchy"]}
    meta.setdefault("trinket_level_mats", None)
    return Kit(frame_dir=manifest["frame"], meta=meta,
               arrays=_ArrayDict(six["arrays"]), textures=six["textures"],
               report=six["report"], ubertext=six["ubertext"],
               races=extra.get("races"), mesh_refs=extra.get("mesh_refs") or {})


# ---------------------------------------------------------------------------
# supp parts 件（ability/badges/btf/ornaments/ta/material_state/portrait_uv1/fap）
# ---------------------------------------------------------------------------

def _ability_value(quality: str) -> tuple[dict, dict]:
    """frames.ability_kit(quality) → (parts 值, source 账)。

    形状契约（seed._convert_supplements 同表）：recon_meta 拆 hierarchy 分面、
    arrays/textures 平面、portrait 单件 png、mesh_refs (bundle,pid) 二元组。
    obj_texts/fonts_bytes 不进种子形状（渲染链零消费的提取产物面——对拍契约
    显式记账）。"""
    from eidolon.core.supply.frames.ability import ability_kit

    k = ability_kit(quality)
    value = {
        "recon_meta": {kk: vv for kk, vv in k.recon_meta.items()
                       if kk != "hierarchy"},
        "hierarchy": k.recon_meta["hierarchy"],
        "report": k.report,
        "ubertext": k.ubertext,
        "arrays": dict(k.arrays),
        "textures": dict(k.textures),
        "portrait": ({"portrait.png": k.portrait}
                     if k.portrait is not None else {}),
        "portrait_meta": dict(k.portrait_meta or {}),
        "mesh_refs": {kk: (vv[0], int(vv[1])) for kk, vv in k.mesh_refs.items()},
    }
    return value, {"source": f"frames.ability_kit({quality!r})"
                             "（harness live 域函数）"}


def _supp_value(item: str) -> tuple[dict, dict]:
    """live 域函数 → (parts 值, source 账)。形状=seed._convert_supplements 同表。"""
    if item == "badges_kit":
        from eidolon.core.supply.frames.badges import badges_kit

        k = badges_kit()
        return ({"report": k.report, "arrays": dict(k.arrays),
                 "textures": dict(k.textures)},
                {"source": "frames.badges_kit（harness live 域函数）"})
    if item == "btf_kit":
        from eidolon.core.supply.frames.btf import btf_kit

        k = btf_kit()
        return ({"report": k.report, "arrays": dict(k.arrays),
                 "textures": dict(k.textures), "card_race": k.card_race},
                {"source": "frames.btf_kit（harness live 域函数）"})
    if item == "ornaments_kit":
        from eidolon.core.supply.frames.ornaments import ornaments_kit

        k = ornaments_kit()
        return ({"report": k.report, "arrays": dict(k.arrays),
                 "textures": dict(k.textures)},
                {"source": "frames.ornaments_kit（harness live 域函数）"})
    if item == "ta_supplement":
        from eidolon.core.supply.frames.supplements import ta_supplement

        return ({"arrays": dict(ta_supplement())},
                {"source": "frames.ta_supplement（harness live 域函数）"})
    if item == "material_state":
        from eidolon.core.supply.frames.supplements import material_state

        return ({"data": material_state()},
                {"source": "frames.material_state（harness live 域函数）"})
    if item == "portrait_uv1":
        from eidolon.core.supply.frames.supplements import portrait_uv1

        meshes = {}
        for name, ch in portrait_uv1().items():
            for field, arr in ch.items():
                meshes[f"{name}/{field}"] = arr
        return ({"meshes": meshes},
                {"source": "frames.portrait_uv1（harness live 域函数）"})
    raise KeyError(f"supplement harness 未收录 item {item!r}")


def _supp_account(item: str, params: dict, value: dict, source: dict,
                  cache_root: Path, *, domain: str = S.DOMAIN_FRAMES) -> dict:
    """parts 值 → items 账（单 item 单行；content 聚合 sha=键面身份）。"""
    from eidolon.core.supply_index.cold import _write_blob_atomic

    def write_blob(data: bytes, ext: str, content_sha: str) -> str:
        rel, _fresh = _write_blob_atomic(cache_root, S.sha256_hex(data), data,
                                         ext=ext)
        return rel

    parts, _payload_shas = SC.encode_parts(value, write_blob=write_blob)
    content_sha = SC.supplement_content_sha(parts)
    return {"item": item, "domain": domain, "params": params, "parts": parts,
            "content_sha": content_sha, "source": source, "ok": True}
