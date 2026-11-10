"""frames.engine — 共享走查引擎（五帧族逐字转写；v3 形态适配唯二：save_texture 落盘→
Recon.textures 内存字典、npz 落盘→Kit.arrays 内存字典，落盘随阶段②适配壳恢复）。

[ally_recon.py:32-344 逐字；uv1/color0 = weapon/hp/hero 的参数化增量]
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image
from UnityPy.helpers.MeshHelper import MeshHandler

from eidolon.core.infra.context import current   # 契约 D：Strings 路径=ctx 流入
from eidolon.core.infra.resolve_asset_ref import PPtrError, Resolver, record_pptr_miss
from eidolon.core.supply._projection import as_pairs, as_rgba
from eidolon.core.supply.machine import core

logger = logging.getLogger(__name__)


def global_strings_path() -> Path:
    """游戏 Strings/<locale>/GLOBAL.txt（契约 D：ctx.strings_dir；旧模块常量
    GLOBAL_STRINGS 的活源形态——import 期钉死改调用期解析，locale 随 ctx）。"""
    return current().strings_dir / "GLOBAL.txt"


def mat4_from_trs(pos, rot, scale) -> np.ndarray:
    """Unity 四元数(x,y,z,w) + 平移 + 缩放 → 4x4（行主序，右乘列向量）。[ally_recon:42]"""
    x, y, z, w = rot
    R = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)
    M = np.eye(4)
    M[:3, :3] = R @ np.diag(scale)
    M[:3, 3] = pos
    return M


def ptr_dict(p) -> dict:
    """[ally_recon:60-63]"""
    if isinstance(p, dict):
        return {"m_FileID": p.get("m_FileID", 0), "m_PathID": p.get("m_PathID", 0)}
    return {"m_FileID": getattr(p, "m_FileID", 0), "m_PathID": getattr(p, "m_PathID", 0)}


def vec3(v) -> list[float] | None:
    """Unity 序列化 Vector3（typetree 形 {"x","y","z"}）→ [x,y,z]；缺省/异形 → None。

    走查引擎的两条 Actor 记录（kits.finalize_actor / ability.finalize_actor）只收标量与
    PPtr，Vector3 字段会整个落空——需要向量字段的消费方（如 m_alternateCostTextLocalPos）
    经由本函数显式取值，禁把「拿不到」读成「等于代码默认」。
    """
    if isinstance(v, dict) and {"x", "y", "z"} <= set(v):
        return [float(v["x"]), float(v["y"]), float(v["z"])]
    return None


def subshader_queue(sub: dict) -> str | None:
    """SubShader 的 ShaderLab Queue tag（序列化 m_Tags.tags 二元组，键名大写 "QUEUE"）。

    返回原值字符串（如 "Transparent"）或 None（无 tag=引擎默认 Geometry）。**不做数值
    归一化**——数值队列（"2450"）原样透传，消费方按需比较。

    正典单源（2026-11-01 zbuf-blindspots ②③ 自 supplements._subshader_queue 上移）：
    同一提取式三处消费（supplements.material_state kit 面 / badges.shader_info /
    ornaments._shader_pass_states），共置本模块防三份漂移。"""
    tags = sub.get("m_Tags") or {}
    pairs = tags.get("tags") if isinstance(tags, dict) else None
    for kv in pairs or []:
        if isinstance(kv, (list, tuple)) and len(kv) == 2 and str(kv[0]).upper() == "QUEUE":
            return kv[1]
    return None


def _iter_sf(env):
    """[ally_recon:344-357]"""
    from UnityPy.files import SerializedFile

    def walk(file):
        if isinstance(file, SerializedFile):
            yield file
            return
        subs = getattr(file, "files", None)
        if isinstance(subs, dict):
            for sub in subs.values():
                yield from walk(sub)

    for f in env.files.values():
        yield from walk(f)


def extract_mesh_from_bundle(r: Resolver, bundle: str, path_id: int) -> dict | None:
    """[ally_recon:320-341]"""
    env = r.open_bundle(bundle)
    for sf in _iter_sf(env):
        if path_id in sf.objects:
            obj = sf.objects[path_id]
            if obj.type.name != "Mesh":
                return None
            try:
                mesh = obj.read()
                h = MeshHandler(mesh)
                h.process()
                verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
                uv0 = np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0 else np.zeros((len(verts), 2))
                subs = [np.array([t for t in sub if len(t) == 3], dtype=np.int32)
                        for sub in h.get_triangles()]
                return {"name": mesh.m_Name, "verts": verts, "uv0": uv0, "submeshes": subs,
                        "bbox_min": verts.min(axis=0).tolist(), "bbox_max": verts.max(axis=0).tolist(),
                        "bundle": bundle, "path_id": path_id}
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[extra mesh fail] {path_id}: {exc}")
                return None
    return None


def extract_race_strings() -> dict:
    """游戏 Strings/<locale>/GLOBAL.txt → GLOBAL_RACE_* 键值。[ally_recon:360-368]"""
    import re

    out: dict[str, str] = {}
    gs = global_strings_path()
    if gs.is_file():
        text = gs.read_text(encoding="utf-8-sig")
        for m in re.finditer(r"^(GLOBAL_RACE_[A-Z_]+)\t([^\t]*)", text, re.M):
            out[m.group(1)] = m.group(2).strip()
    return out


def extract_spell_school_strings() -> dict:
    """游戏 Strings/<locale>/GLOBAL.txt → GLOBAL_SPELL_SCHOOL_* 键值（批10d：tag_enum
    CSV 退役——法术学派 zhCN 显示名的游戏本体源）。"""
    import re

    out: dict[str, str] = {}
    gs = global_strings_path()
    if gs.is_file():
        text = gs.read_text(encoding="utf-8-sig")
        for m in re.finditer(r"^(GLOBAL_SPELL_SCHOOL_[A-Z_]+)\t([^\t]*)", text, re.M):
            out[m.group(1)] = m.group(2).strip()
    return out


class Recon:
    """五帧族共享走查引擎 [ally_recon:90-317 逐字]；v3 形态适配：save_texture 落盘→
    textures 内存字典（其余逐字）。"""

    def __init__(self, uv1_mode: str | None = None, color0: bool = False,
                 save_textures: bool = True):
        self.r = core().res
        self.bundle = None
        self.uv1_mode = uv1_mode        # None | "uv0copy"(weapon/loc) | "zeros"(hero)
        self.color0 = color0            # hp/hero：mesh color0（VS o2 vCOLOR）
        self.save_textures = save_textures   # 轻走查旗（批2b-1）：False=材质槽不 deref 纹理
                                             # （省纹理包读+PIL 解码；material_state 级消费者用）
        self.nodes: list[dict] = []
        self.mesh_jobs: list[dict] = []
        self.tex_saved: dict[tuple[str, int], dict] = {}
        self.textures: dict[str, Image.Image] = {}
        self.issues: list[str] = []
        self.actor_mt: dict | None = None
        self.actor_owner = None
        self._root_go = None
        self.hierarchy: dict | None = None

    # ---------- 纹理（内存面 + 记录）[ally_recon:102-120] ----------
    def save_texture(self, t_reader, bundle: str) -> dict:
        key = (bundle, t_reader.path_id)
        if key in self.tex_saved:
            return self.tex_saved[key]
        tree = t_reader.read_typetree()
        info = {"name": tree.get("m_Name"), "bundle": bundle, "path_id": t_reader.path_id,
                "width": tree.get("m_Width"), "height": tree.get("m_Height"),
                "format": tree.get("m_TextureFormat")}
        fname = f"{info['name']}.png"
        try:
            self.textures[fname] = t_reader.read().image
            info["file"] = fname
        except Exception as exc:  # noqa: BLE001
            info["file"] = None
            info["error"] = f"{type(exc).__name__}: {exc}"
        self.tex_saved[key] = info
        return info

    # ---------- 材质 [ally_recon:123-156] ----------
    def _shader_name(self, mt: dict, mbundle: str, owner) -> str | None:
        """材质 → 着色器身份名（m_ParsedForm.m_Name，37.0 序列化直读）。

        2026-10-23 hero-play-frame：`"shader"` 键自本批起实名（此前恒 None）——
        消费方=raster 的**着色器身份**分派（`Effects/FX_Transparent_ColorAsAlpha`
        的 ColorAsAlpha 合成式；先例=`multiply_form` 按 shader 名分族）。
        失败静默回 None（shader 面只作身份判据，缺则回落旧语义；**不记 PPtr miss**
        ——门内 unknown_misses 是硬判据，shader 引用缺不得把整卡判红）。"""
        ptr = ptr_dict(mt.get("m_Shader") or {})
        if not ptr.get("m_PathID"):
            return None
        try:
            s_obj, _ = self.r.resolve_pptr(mbundle or self.bundle, ptr, owner)
            s_tt = s_obj.read_typetree()
        except Exception:  # noqa: BLE001
            return None
        pf = s_tt.get("m_ParsedForm") or {}
        return pf.get("m_Name") or s_tt.get("m_Name") or None

    def walk_material(self, m_reader, mbundle: str, owner) -> dict | None:
        try:
            mt = m_reader.read_typetree()
        except Exception as exc:  # noqa: BLE001
            self.issues.append(f"material {m_reader.path_id}: {exc}")
            return None
        info = {"name": mt.get("m_Name"), "bundle": mbundle, "path_id": m_reader.path_id,
                "shader": self._shader_name(mt, mbundle, m_reader),
                "tex": {}, "colors": {}, "floats": {}}
        saved = mt.get("m_SavedProperties", {})

        for first, sec in as_pairs(saved.get("m_TexEnvs"), what="m_TexEnvs").items():
            sec = sec or {}
            tptr = ptr_dict(sec.get("m_Texture") or {})
            sc_, of = sec.get("m_Scale") or {}, sec.get("m_Offset") or {}
            slot = {"scale": [sc_.get("x", 1), sc_.get("y", 1)],
                    "offset": [of.get("x", 0), of.get("y", 0)]}
            if tptr.get("m_PathID") and self.save_textures:
                try:
                    t_reader, tb = self.r.resolve_pptr(mbundle or self.bundle, tptr, owner)
                except PPtrError as exc:
                    slot["error"] = f"{exc.reason}: {exc.detail}"
                else:
                    if t_reader.type.name == "Texture2D":
                        tinfo = self.save_texture(t_reader, tb)
                        slot["texture"] = {"name": tinfo["name"], "bundle": tb,
                                           "file": tinfo.get("file")}
            info["tex"][first] = slot
        for first, sec in as_pairs(saved.get("m_Colors"), what="m_Colors").items():
            info["colors"][first] = as_rgba(sec)
        for first, sec in as_pairs(saved.get("m_Floats"), what="m_Floats").items():
            info["floats"][first] = sec
        return info

    # ---------- 网格 [ally_recon:159-174；uv1/color0 = weapon/hp/hero 增量] ----------
    def extract_mesh(self, mesh_reader, mbundle: str) -> dict | None:
        try:
            mesh = mesh_reader.read()
            h = MeshHandler(mesh)
            h.process()
            verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
            uv0 = np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0 else np.zeros((len(verts), 2))
            # 法线（2026-10-23 gold-frame-phase）：UnlitTextureReflection 反射 UV 的
            # 世界法线扰动项 `-uv0.x·0.3·(R·n).xz` 唯一数据来源（VS asm `mul r0.zw,
            # v1.yyyy, cb1[1].xxxz` 链）；无流网格回退零（扰动项随之为零）。
            # 流式网格（m_StreamData）的 m_Normals 访问可能抛错——只降级法线，不能
            # 连 verts/uv0 一起丢（2026-10-23 协调者修：Gem_Attack 等流式网格曾因此
            # 整节点 mesh_stats=None，z_attack +30；法线缺失只影响金框反射扰动）。
            try:
                normals = (np.array(h.m_Normals, dtype=np.float64).reshape(-1, 3)
                           if h.m_Normals else np.zeros((len(verts), 3)))
            except Exception:  # noqa: BLE001
                normals = np.zeros((len(verts), 3))
            if self.uv1_mode == "uv0copy":
                uv1 = np.array(h.m_UV1, dtype=np.float64).reshape(-1, 2) if h.m_UV1 else uv0.copy()
            elif self.uv1_mode == "zeros":
                uv1 = np.array(h.m_UV1, dtype=np.float64).reshape(-1, 2) if h.m_UV1 \
                    else np.zeros((len(verts), 2))
            else:
                uv1 = None
            color0 = None
            if self.color0:
                color0 = (np.array(h.m_Colors, dtype=np.float64).reshape(-1, 4)
                          if h.m_Colors else np.ones((len(verts), 4)))
            tris_per_sub = []
            for sub in h.get_triangles():
                tris_per_sub.append(np.array([t for t in sub if len(t) == 3], dtype=np.int32))
            out = {"name": mesh.m_Name, "verts": verts, "uv0": uv0, "normals": normals,
                   "submeshes": tris_per_sub,
                   "bbox_min": verts.min(axis=0).tolist(), "bbox_max": verts.max(axis=0).tolist(),
                   "bundle": mbundle, "path_id": mesh_reader.path_id}
            if uv1 is not None:
                out["uv1"] = uv1
            if color0 is not None:
                out["color0"] = color0
            return out
        except Exception as exc:  # noqa: BLE001
            self.issues.append(f"mesh {getattr(mesh_reader, 'path_id', '?')}: {type(exc).__name__}: {exc}")
            return None

    # ---------- 层级 [ally_recon:177-265] ----------
    def walk(self, go_reader, path: str, key: str, depth: int = 0,
             parent_active: bool = True) -> dict:
        if depth > 14:
            raise RuntimeError(f"{path}: 超深层级")
        tree = go_reader.read_typetree()
        name = tree["m_Name"]
        node_path = f"{path}/{name}" if path else name
        node = {"name": name, "go_path_id": go_reader.path_id, "path": node_path,
                "npz_key": key, "local": None, "world": None, "children": [],
                "renderers": [], "ubertext": None, "mono_unknown": [],
                "active_self": bool(tree.get("m_IsActive", 1)),
                "active_in_hierarchy": bool(parent_active and tree.get("m_IsActive", 1))}
        transform = None
        transform_obj = None
        for comp in tree.get("m_Component", []):
            pd = ptr_dict(comp["component"])
            if not pd["m_PathID"]:
                continue
            try:
                cobj, _cb = self.r.resolve_pptr(self.bundle, pd, go_reader)
            except PPtrError as exc:
                record_pptr_miss(exc)
                self.issues.append(f"{node_path} 组件 {pd['m_PathID']}: {exc.reason}")
                continue
            ctype = cobj.type.name
            ctree = cobj.read_typetree()
            if ctype == "Transform":
                transform = ctree
                transform_obj = cobj
                p, q, s = ctree["m_LocalPosition"], ctree["m_LocalRotation"], ctree["m_LocalScale"]
                node["local"] = {"pos": [p["x"], p["y"], p["z"]],
                                 "rot": [q["x"], q["y"], q["z"], q["w"]],
                                 "scale": [s["x"], s["y"], s["z"]]}
            elif ctype in ("MeshFilter", "MeshRenderer", "SkinnedMeshRenderer"):
                if ctype == "MeshFilter":
                    mp = ptr_dict(ctree.get("m_Mesh") or {})
                    if mp.get("m_PathID"):
                        try:
                            mobj, mb = self.r.resolve_pptr(self.bundle, mp, cobj)
                            mesh = self.extract_mesh(mobj, mb)
                            if mesh is not None:
                                node["mesh"] = mesh
                                self.mesh_jobs.append({"key": key, "mesh_obj": mobj,
                                                       "bundle": mb, "mesh": mesh})
                        except PPtrError as exc:
                            record_pptr_miss(exc)
                            self.issues.append(f"{node_path} mesh: {exc.reason}")
                else:
                    mats = []
                    for mp in ctree.get("m_Materials", []):
                        pdm = ptr_dict(mp)
                        if not pdm.get("m_PathID"):
                            mats.append(None)
                            continue
                        try:
                            mobj, mb = self.r.resolve_pptr(self.bundle, pdm, cobj)
                            mats.append(self.walk_material(mobj, mb, mobj))
                        except PPtrError as exc:
                            mats.append(None)
                            self.issues.append(f"{node_path} mat: {exc.reason}")
                    node["renderers"].append({"enabled": ctree.get("m_Enabled"),
                                              "materials": mats,
                                              "renderer_path_id": cobj.path_id})
            elif ctype == "MonoBehaviour":
                if "m_CharacterSize" in ctree and "m_FontSize" in ctree:
                    node["ubertext"] = self.ubertext_record(ctree, cobj)
                elif "m_cardMesh" in ctree or "m_portraitMesh" in ctree:
                    if self.actor_mt is None:
                        self.actor_mt = ctree
                        self.actor_owner = cobj
                else:
                    keys = sorted(k for k in ctree.keys() if k.startswith("m_")) if isinstance(ctree, dict) else []
                    node["mono_unknown"].append({"path_id": cobj.path_id, "m_keys": keys[:24]})
        if transform is not None:
            for ch in transform.get("m_Children", []):
                cpd = ptr_dict(ch)
                if not cpd["m_PathID"]:
                    continue
                try:
                    tr_obj, _ = self.r.resolve_pptr(self.bundle, cpd, transform_obj)
                    tr_tree = tr_obj.read_typetree()
                    gop = ptr_dict(tr_tree.get("m_GameObject") or {})
                    go_child, _ = self.r.resolve_pptr(self.bundle, gop, tr_obj)
                except PPtrError as exc:
                    record_pptr_miss(exc)
                    self.issues.append(f"{node_path} 子解析: {exc.reason}")
                    continue
                child = self.walk(go_child, node_path, f"{key}.{len(node['children'])}",
                                  depth + 1, node["active_in_hierarchy"])
                node["children"].append(child)
        return node

    def ubertext_record(self, mt: dict, cobj) -> dict:
        """[ally_recon:271-284]"""
        rec = {"path_id": cobj.path_id}
        rec["fields"] = mt
        fp = ptr_dict(mt.get("m_Font") or {})
        rec["font_pptr"] = fp
        if fp.get("m_PathID"):
            try:
                fobj, fb = self.r.resolve_pptr(self.bundle, fp, cobj)
                ftree = fobj.read_typetree()
                rec["font_name"] = ftree.get("m_Name")
                rec["font_bundle"] = fb
            except PPtrError as exc:
                rec["font_error"] = f"{exc.reason}: {exc.detail}"
        return rec

    # ---------- Actor 绑定 [ally_recon:287-317] ----------
    def finalize_actor(self, root_owner) -> dict:
        mt = self.actor_mt
        by_pid = {n["go_path_id"]: n["path"] for n in self.iter_nodes(self.hierarchy)}
        rec: dict = {}
        for k, v in mt.items():
            if not k.startswith("m_"):
                continue
            if isinstance(v, dict) and "m_PathID" in v:
                pd = ptr_dict(v)
                if not pd["m_PathID"]:
                    continue
                entry: dict = {"file_id": pd["m_FileID"], "path_id": pd["m_PathID"]}
                hit = by_pid.get(pd["m_PathID"])
                if hit:
                    entry["node"] = hit
                else:
                    try:
                        o, b = self.r.resolve_pptr(self.bundle, pd, root_owner)
                        t = o.read_typetree()
                        entry.update({"name": t.get("m_Name"), "type": o.type.name, "bundle": b})
                    except PPtrError as exc:
                        entry["error"] = exc.reason
                rec.setdefault("object_refs", {})[k] = entry
            elif isinstance(v, (int, float, str, bool)) or v is None:
                rec.setdefault("scalars", {})[k] = v
        return rec

    def iter_nodes(self, node):
        yield node
        for c in node["children"]:
            yield from self.iter_nodes(c)
