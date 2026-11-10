"""frames.badges — 三徽章 prefab 走查 + 容器坐标（Batch C）。

对照表（旧位 → 本域，预审 2026-10-10）：
  - BADGES 三 ref ← name:guid 链根维持（资产身份档位；bt_extract_badges 同形）
  - 走查 ← bt_extract_badges.py:44-544 逐字（walk_go 累计世界矩阵，根平移置零=
    LoadPrefab 根平移语义；OBJ 证据件段省略——report.meshes 非渲染消费面，
    compile_badges 只读 info/textures/nodes）
  - shader 面 ← 材质 m_Shader deref，typetree 不可得回落双 shader bundle 扫描
    （模块级懒索引=进程 memo，dll_reflect.tables 同形态；_u64=typetree 溢出形态双键）
  - 容器坐标 ← Card_Hand_Ally/Card_Hand_Ability 两帧 BannerContainer 节点
    （name:guid 链根，与 DM_PREFABS 同形）
  - _Ctx/_cab_of/_sanitize ← .ability 引用（mc_asset_frame_extract:39-84 同源逐字件，
    v3 共用一副本）；quat_to_mat3/trs_matrix=badges 特有（累计矩阵语义）独立保留防串线
产物=BadgesKit（report+arrays+textures 真内存；旧落盘 badges_report.json/
badges_meshes.npz/textures/ 的内存面，落盘随阶段②适配壳）。
对拍=duipai_frames.py check_badges（report 逐字段+npz 逐键逐位+textures 像素逐位）。
"""
from __future__ import annotations

import logging
import zlib
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from UnityPy.helpers.MeshHelper import MeshHandler

from eidolon.core.infra.dll_reflect import tables
from eidolon.core.infra.context import current   # 契约 D：Data/Win=ctx 流入
from eidolon.core.infra.resolve_asset_ref import PPtrError, Resolver
from eidolon.core.supply._projection import as_pairs, as_rgba
from eidolon.core.supply.frames.ability import _Ctx, _sanitize
from eidolon.core.supply.frames.engine import ptr_dict, subshader_queue
from eidolon.core.supply.machine import core, item

logger = logging.getLogger(__name__)

BADGES = {
    "tradeable": "Tradeable_Banner.prefab:2b8ee190319eaf14d906503371f38f5e",
    "forgeable": "Forgeable_Banner.prefab:fca896d80e20b934eb96e7fe83f43a9a",
    "prepareable": "Prepareable_Banner.prefab:fccd1c9e46984864da6f8c37b9975e2d",
}
_SHADER_BUNDLES = ("essential_base_global-shader-0.unity3d",
                   "essential_base_global-shader-1.unity3d")
_shader_index: dict[int, dict] | None = None


@dataclass
class BadgesKit:
    """badges 产物真内存对象（旧 badges OUT 三布局位的内存面）。"""
    report: dict = field(default_factory=dict)   # badges_report.json 内容面
    arrays: dict = field(default_factory=dict)   # badges_meshes.npz 内容面
    textures: dict = field(default_factory=dict)  # textures/ {文件名: PIL}


def _u64(pid: int) -> int:
    """int64 负 pid → uint64（typetree 溢出形态双侧对齐）。[bt:58-60]"""
    return pid if pid >= 0 else pid + (1 << 64)


def _shader_bundle_typetree(pid: int) -> dict | None:
    """[bt:63-77]"""
    global _shader_index
    if _shader_index is None:
        from eidolon.core.infra import bundle_guard

        _shader_index = {}
        data_win = current().data_win
        for b in _SHADER_BUNDLES:
            env = bundle_guard.load_defended(data_win / b)   # 坏盘读防护收口（2026-11-08）
            for obj in env.objects:
                if obj.type.name != "Shader":
                    continue
                try:
                    _shader_index[obj.path_id] = obj.read_typetree()
                    _shader_index[_u64(obj.path_id)] = _shader_index[obj.path_id]
                except Exception:  # noqa: BLE001
                    continue
    return _shader_index.get(pid) or _shader_index.get(_u64(pid))


def quat_to_mat3(q: dict) -> np.ndarray:
    """[bt:94-100]"""
    x, y, z, w = (float(q.get(k, 0.0)) for k in ("x", "y", "z", "w"))
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def trs_matrix(tt: dict, zero_translation: bool = False) -> np.ndarray:
    """[bt:103-113]"""
    M = np.eye(4)
    p = tt.get("m_LocalPosition") or {}
    s = tt.get("m_LocalScale") or {"x": 1.0, "y": 1.0, "z": 1.0}
    M[:3, :3] = quat_to_mat3(tt.get("m_LocalRotation") or {"w": 1.0}) \
        @ np.diag([float(s.get("x", 1)), float(s.get("y", 1)), float(s.get("z", 1))])
    M[:3, 3] = [float(p.get(k, 0.0)) for k in ("x", "y", "z")]
    if zero_translation:
        M[:3, 3] = 0.0
    return M


def _mesh_arrays(mesh_obj) -> dict:
    """[bt:116-124]
    + `colors`（m_Colors 顶点色流，4 通道；网格无该流时**不出键**）：multiply 链的
    `Hero/Multiply/Multiply` PS 是 `dst *= tex + vColor`，vColor 优先取真顶点色；
    当前语料 multiply 网格（btf 两影/徽章 ShadowQuad/符文影）序列化均无 m_Colors 流
    （材质色在运行时影网格里烘入），故消费方以材质 `_Color` 代偿——见
    raster.raster_multiply 的前提/弃用条件。"""
    mesh = mesh_obj.read()
    h = MeshHandler(mesh)
    h.process()
    verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
    uv0 = np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0 else np.zeros((len(verts), 2))
    subs = [np.array([t for t in sub if len(t) == 3], dtype=np.int32) for sub in h.get_triangles()]
    out = {"name": mesh.m_Name, "verts": verts, "uv0": uv0, "submeshes": subs}
    if h.m_Colors:
        out["colors"] = np.array(h.m_Colors, dtype=np.float64).reshape(-1, 4)
    return out


def _walk_badge(r: Resolver, badge_key: str, asset_ref: str,
                arrays: dict, textures: dict, issues: list) -> dict:
    """单徽章走查 [bt Extractor.run 徽章循环体逐字；落盘 → 内存面]。"""
    res = r.resolve(asset_ref)
    assert res["ok"], (badge_key, res["checks"])
    bundle = res["resolved"]["bundle"]
    guid = res["resolved"]["guid"]
    ctx = _Ctx(r, bundle)
    root, _ = r.container_get(bundle, guid)
    nodes: list[dict] = []
    texture_jobs: list[dict] = []
    mono_records: list[dict] = []
    badge_textures: list[dict] = []

    def foreign_info(obj, b) -> dict:
        info = {"type": obj.type.name, "path_id": obj.path_id, "bundle": b,
                "guid": ctx.guid_of(obj) if b == bundle else None}
        try:
            t = obj.read_typetree()
            info["name"] = t.get("m_Name")
        except Exception as exc:  # noqa: BLE001
            info["name"], info["error"] = None, f"{type(exc).__name__}: {exc}"
        return info

    def queue_texture(obj, b, used_by, slot) -> dict | None:
        for job in texture_jobs:
            if job["bundle"] == b and job["tex_obj"].path_id == obj.path_id:
                job["used_by"].append(f"{used_by}:{slot}")
                return job["info"]
        info = foreign_info(obj, b)
        texture_jobs.append({"tex_obj": obj, "info": info, "bundle": b,
                             "used_by": [f"{used_by}:{slot}"]})
        return info

    def shader_info(mat_obj, mt: dict) -> dict:
        """[bt:185-223 逐字；2026-11-01 zbuf-blindspots ③ 增补 pid+queue 两字段]

        `pid`：shader 序列化 path_id（成功/回落两路都记；此前只在错误腿出现）——
        材质态表 badge 行 `shader_pid` 的来路，让 badge 族 15 件能按 shader 身份取
        Queue tag（此前 badge 行无 shader pid，queue 恒缺、延期判据只能靠 zWrite 兜底）。
        `passes[*].queue`：SubShader Queue tag 直读（engine.subshader_queue 正典单源；
        kit 面 supplements.material_state 同式）。缺省 None=无 tag（引擎默认 Geometry）。"""
        sh = mt.get("m_Shader")
        pd = ptr_dict(sh) if sh else {"m_PathID": 0}
        if not pd["m_PathID"]:
            return {"error": "no shader ref", "pid": 0}
        stt = None
        try:
            sobj, sb = ctx.deref(pd, mat_obj)
            stt = sobj.read_typetree()
        except Exception:  # noqa: BLE001
            stt = None
        if not stt or not (stt.get("m_ParsedForm") or {}).get("m_SubShaders"):
            stt = _shader_bundle_typetree(pd["m_PathID"])
            sb = "essential_base_global-shader-bundle-scan"
        if not stt:
            return {"error": "shader typetree 不可得", "pid": pd["m_PathID"]}
        parsed = stt.get("m_ParsedForm") or {}

        def v(d):
            return (d or {}).get("val")

        passes = []
        for sub in (parsed.get("m_SubShaders") or [])[:4]:
            q = subshader_queue(sub)
            for ps in (sub.get("m_Passes") or [])[:6]:
                state = ps.get("m_State") or {}
                rb = state.get("rtBlend0") or {}
                passes.append({
                    "name": ps.get("m_Name"),
                    "srcBlend": v(rb.get("srcBlend")), "destBlend": v(rb.get("destBlend")),
                    "colMask": v(rb.get("colMask")),
                    "zWrite": v(state.get("zWrite")), "zTest": v(state.get("zTest")),
                    "culling": v(state.get("culling")),
                    "queue": q,
                })
        return {"name": parsed.get("m_Name") or stt.get("m_Name"),
                "pid": pd["m_PathID"],
                "bundle": sb, "passes": passes}

    def walk_material(mat_obj, b, used_by) -> dict:
        """[bt:225-259 逐字]"""
        rec: dict = {"slot_used_by": used_by}
        try:
            mt = mat_obj.read_typetree()
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"
            return rec
        rec["name"] = mt.get("m_Name")
        rec["guid"] = ctx.guid_of(mat_obj) if b == bundle else None
        rec["bundle"] = b
        rec["path_id"] = mat_obj.path_id
        rec["shader"] = shader_info(mat_obj, mt)
        saved = mt.get("m_SavedProperties") or {}
        texenvs = as_pairs(saved.get("m_TexEnvs"), what="m_TexEnvs")
        texs = {}
        for slot_name, slot in texenvs.items():
            tp = (slot or {}).get("m_Texture") if isinstance(slot, dict) else None
            if not tp or not ptr_dict(tp)["m_PathID"]:
                continue
            try:
                tobj, tb = ctx.deref(ptr_dict(tp), mat_obj)
            except PPtrError as exc:
                texs[slot_name] = {"error": f"{exc.reason}: {exc.detail}"}
                continue
            info = queue_texture(tobj, tb, used_by, slot_name)
            texs[slot_name] = {"name": info.get("name"), "guid": info.get("guid"),
                               "bundle": tb, "path_id": tobj.path_id}
        rec["colors"] = {n: as_rgba(v) for n, v in
                         as_pairs(saved.get("m_Colors"), what="m_Colors").items()}
        rec["floats"] = as_pairs(saved.get("m_Floats"), what="m_Floats")
        rec["textures"] = texs
        return rec

    def walk_renderer(comp_obj, ctype, node_path, acc: np.ndarray) -> dict:
        """[bt:261-305 逐字]"""
        try:
            ct = comp_obj.read_typetree()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}
        rec: dict = {"component": ctype, "enabled": bool(ct.get("m_Enabled", 1))}
        mesh_ptr = ct.get("m_Mesh")
        if mesh_ptr and ptr_dict(mesh_ptr)["m_PathID"]:
            try:
                mobj, mb = ctx.deref(ptr_dict(mesh_ptr), comp_obj)
            except PPtrError as exc:
                rec["mesh"] = {"error": f"{exc.reason}: {exc.detail}"}
                mobj = None
            if mobj is not None:
                minfo = foreign_info(mobj, mb)
                try:
                    arrs = _mesh_arrays(mobj)
                    minfo["submesh_count"] = len(arrs["submeshes"])
                    minfo["vertex_count"] = len(arrs["verts"])
                    key = f"{badge_key}|{node_path}"
                    arrays[f"{key}/verts"] = arrs["verts"]
                    arrays[f"{key}/uv0"] = arrs["uv0"]
                    for i, tris in enumerate(arrs["submeshes"]):
                        arrays[f"{key}/sub{i}"] = tris
                    if arrs.get("colors") is not None:
                        arrays[f"{key}/colors"] = arrs["colors"]
                    arrays[f"{key}/matrix"] = acc.astype(np.float64)
                    minfo["npz_key"] = key
                except Exception as exc:  # noqa: BLE001
                    minfo["npz_error"] = f"{type(exc).__name__}: {exc}"[:160]
                rec["mesh"] = minfo
        slots = []
        for i, mp in enumerate(ct.get("m_Materials") or []):
            pd = ptr_dict(mp)
            if not pd["m_PathID"]:
                slots.append({"slot": i, "empty": True})
                continue
            try:
                mobj, mb = ctx.deref(pd, comp_obj)
            except PPtrError as exc:
                slots.append({"slot": i, "error": f"{exc.reason}: {exc.detail}"})
                continue
            slots.append({"slot": i, **walk_material(mobj, mb, node_path)})
        rec["material_slots"] = slots
        return rec

    def walk_go(go_obj, parent_path, parent_acc: np.ndarray, depth=0):
        """[bt:307-379 逐字（LoadPrefab 根平移置零语义）]"""
        if depth > 12:
            return
        gt = go_obj.read_typetree()
        name = gt.get("m_Name") or f"go_{go_obj.path_id}"
        node_path = f"{parent_path}/{name}" if parent_path else name
        node: dict = {"path": node_path, "go_path_id": go_obj.path_id,
                      "activeSelf": bool(gt.get("m_IsActive", 1)),
                      "components": {}}
        transform_tt = None
        comps: list[tuple[str, object, str]] = []
        for pair in gt.get("m_Component") or []:
            cp = pair.get("component") if isinstance(pair, dict) else getattr(pair, "component", None)
            pd = ptr_dict(cp)
            if not pd["m_PathID"]:
                continue
            try:
                cobj, cb = ctx.deref(pd, go_obj)
            except PPtrError as exc:
                node["components"][f"pathid_{pd['m_PathID']}"] = {"error": exc.reason}
                continue
            comps.append((cobj.type.name, cobj, node_path))
            if cobj.type.name == "Transform":
                transform_tt = cobj.read_typetree()
                node["transform"] = {
                    "local_position": transform_tt.get("m_LocalPosition"),
                    "local_rotation": transform_tt.get("m_LocalRotation"),
                    "local_scale": transform_tt.get("m_LocalScale"),
                }
        own_local = trs_matrix(transform_tt, zero_translation=(depth == 0)) \
            if transform_tt is not None else np.eye(4)
        acc = parent_acc @ own_local
        node["matrix_local_to_root"] = acc.tolist()
        for ctype, cobj, _np in comps:
            if ctype == "Transform":
                continue
            if ctype in ("MeshFilter", "MeshRenderer", "SkinnedMeshRenderer"):
                rec = walk_renderer(cobj, ctype, node_path, acc)
                key = "mesh_filter" if ctype == "MeshFilter" else "renderer"
                if key in node["components"]:
                    node["components"][key] = {**node["components"][key], **rec}
                else:
                    node["components"][key] = rec
                continue
            if ctype == "MonoBehaviour":
                try:
                    mt = cobj.read_typetree()
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(mt, dict) and "m_Prefab" in mt:
                    mono_records.append({"node": node_path, "path_id": cobj.path_id,
                                         "m_Prefab": mt.get("m_Prefab"),
                                         "m_Enabled": mt.get("m_Enabled"),
                                         "fields": sorted(k for k in mt if k.startswith("m_"))})
        nodes.append(node)
        if transform_tt is not None:
            for ch in transform_tt.get("m_Children") or []:
                cpd = ptr_dict(ch)
                if not cpd["m_PathID"]:
                    continue
                try:
                    cobj2, _2 = ctx.deref(cpd, go_obj)
                    cgt = cobj2.read_typetree()
                    gop = cgt.get("m_GameObject")
                    child_go, _3 = ctx.deref(ptr_dict(gop), cobj2)
                    walk_go(child_go, node_path, acc, depth + 1)
                except PPtrError as exc:
                    issues.append(f"{node_path} 子节点: {exc.reason}")

    root_gt = root.read_typetree()
    root_info = {
        "prefab_ref": asset_ref, "bundle": bundle, "guid": guid,
        "root_name": root_gt.get("m_Name"),
        "root_localPosition_forced_zero": True,
        "root_activeSelf": bool(root_gt.get("m_IsActive", 1)),
    }
    walk_go(root, "", np.eye(4))
    for job in texture_jobs:
        info = dict(job["info"])
        info["used_by"] = job["used_by"]
        obj = job["tex_obj"]
        try:
            t = obj.read_typetree()
            info["width"], info["height"] = t.get("m_Width"), t.get("m_Height")
            info["texture_format"] = t.get("m_TextureFormat")
        except Exception:  # noqa: BLE001
            pass
        name = info.get("name") or f"tex_{obj.path_id}"
        crc = zlib.crc32(f'{job["bundle"]}:{obj.path_id}'.encode()) % 10**8
        fname = f"{_sanitize(name)}_{(info.get('guid') or '')[:8] or f'{crc:08d}'}.png"
        try:
            textures[fname] = obj.read().image
            info["file"] = f"textures/{fname}"
        except Exception as exc:  # noqa: BLE001
            info["file"] = None
            info["error"] = f"decode {type(exc).__name__}: {exc}"
        badge_textures.append(info)

    return {"info": root_info, "nodes": nodes, "textures": badge_textures,
            "monos": mono_records}


def _container_transforms(r: Resolver, actor_ref: str) -> dict:
    """容器节点坐标（两帧）[bt container_transforms 逐字]。
    ref=tables.actor_slots 活表直取（2026-10-10 audit 升级账：Card_Hand_Ally=
    HAND_MINION、Card_Hand_Ability=HAND_SPELL，槽值与旧字面量逐字符同源
    ActorNames.cs:ActorNames/52）。"""
    res = r.resolve(actor_ref)
    assert res["ok"], (frame_name, res["checks"])
    fbundle = res["resolved"]["bundle"]
    env = r.open_bundle(fbundle)
    objects = {o.path_id: o for o in env.objects}
    froot, _ = r.container_get(fbundle, res["resolved"]["guid"])
    out: dict = {}

    def walk(go_obj, path):
        gt = go_obj.read_typetree()
        name = gt.get("m_Name") or f"go_{go_obj.path_id}"
        node_path = f"{path}/{name}" if path else name
        if name.endswith("BannerContainer"):
            rec: dict = {"path": node_path, "components": {}}
            for pair in gt.get("m_Component") or []:
                cp = pair.get("component") if isinstance(pair, dict) else getattr(pair, "component", None)
                pd = ptr_dict(cp)
                if not pd["m_PathID"]:
                    continue
                cobj = objects.get(pd["m_PathID"])
                if cobj is None:
                    continue
                if cobj.type.name == "Transform":
                    tt = cobj.read_typetree()
                    rec["transform"] = {
                        "local_position": tt.get("m_LocalPosition"),
                        "local_rotation": tt.get("m_LocalRotation"),
                        "local_scale": tt.get("m_LocalScale"),
                    }
                elif cobj.type.name == "MonoBehaviour":
                    try:
                        mt = cobj.read_typetree()
                    except Exception:  # noqa: BLE001
                        continue
                    if isinstance(mt, dict) and "m_Prefab" in mt:
                        rec["components"]["NestedPrefab"] = {
                            "m_Prefab": mt["m_Prefab"], "m_Enabled": mt.get("m_Enabled")}
                        rec["activeSelf"] = bool(gt.get("m_IsActive", 1))
            out[node_path] = rec
        for pair in gt.get("m_Component") or []:
            cp = pair.get("component") if isinstance(pair, dict) else getattr(pair, "component", None)
            pd = ptr_dict(cp)
            if not pd["m_PathID"]:
                continue
            cobj = objects.get(pd["m_PathID"])
            if cobj is None or cobj.type.name != "Transform":
                continue
            tt = cobj.read_typetree()
            for ch in tt.get("m_Children") or []:
                chd = ptr_dict(ch)
                if not chd["m_PathID"]:
                    continue
                ch_t = objects.get(chd["m_PathID"])
                if ch_t is None:
                    continue
                cgt = ch_t.read_typetree()
                gop = cgt.get("m_GameObject")
                gpid = ptr_dict(gop)["m_PathID"]
                child_go = objects.get(gpid)
                if child_go is not None:
                    walk(child_go, node_path)

    walk(froot, "")
    return out


@item("frames", "badges_kit")
def badges_kit() -> BadgesKit:
    """三徽章走查+容器坐标（badges_report+badges_meshes.npz+textures 真内存）。"""
    r = core().res
    issues: list[str] = []
    arrays: dict[str, np.ndarray] = {}
    textures: dict[str, Image.Image] = {}
    report: dict = {"badges": {}, "containers": {}, "issues": issues}
    kit = BadgesKit(report=report, arrays=arrays, textures=textures)

    for badge_key, asset_ref in BADGES.items():
        report["badges"][badge_key] = _walk_badge(r, badge_key, asset_ref,
                                                  arrays, textures, issues)
    report["containers"]["Card_Hand_Ally"] = _container_transforms(
        r, tables.actor_slots["HAND_MINION"])
    report["containers"]["Card_Hand_Ability"] = _container_transforms(
        r, tables.actor_slots["HAND_SPELL"])
    n_nodes = sum(len(b["nodes"]) for b in report["badges"].values())
    logger.debug(f"[badges] nodes={n_nodes} npz={len(arrays)} textures={len(textures)}")
    return kit
