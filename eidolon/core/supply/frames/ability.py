"""frames.ability — ability（spell）帧三件套真内存收编（Batch B）。

对照表（旧位 → 本域，预审 2026-10-10）：
  - HAND_SPELL_REF ← tables.actor_slots["HAND_SPELL"]（反射表逐字符等值实证；
    顺带账：HAND_GAME_MODE_BUTTON 同指一 prefab——actor 表比旧硬编码 richer）
  - ABILITY_CLASS_ATLAS_REF ← color.probe()["spellCardTextures"][7]（probe 槽 7
    逐字符等值实证；mc_render 时代"槽 7=牧师"记账获反射面印证）
  - school_desc 附加网格 ← **豁免行**：bundle+名字双谓词扫描保留为正形（证据=
    Card_Hand_Ability 全层级 50+ mesh 引用走查零命中——Description_mesh 挂
    Neutral 变体，学校变体=运行时换装件不进序列化；与类色换装同机制族）；
    premium 帧（2026-11-04 金法术 98918 网格错配修复）不走名字谓词——report
    actor 组件 m_spellDescriptionMeshSchool 序列化 PPtr 现场解，键
    extra/school_desc_premium（见 _school_extra quality 分派）
旧落盘形态（非原子 savez/img.save/meshes obj 目录/fonts 字节）→ 内存面；
阶段②适配壳物化。三件独立实现（recon walk=by_path 快查；report=_Ctx 反向索引；
ubertext=deref cache）——**互不合并**（转写纪律：三者本就三套走法）。
"""
from __future__ import annotations

import logging
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from UnityPy.helpers.MeshHelper import MeshHandler

from eidolon.core.infra.dll_reflect import tables
from eidolon.core.infra.resolve_asset_ref import PPtrError, Resolver, record_pptr_miss
from eidolon.core.supply._projection import as_pairs, as_rgba
from eidolon.core.supply.frames.engine import vec3
from eidolon.core.supply.frames.kits import _ArrayDict, actor_ref
from eidolon.core.supply.machine import core, item

logger = logging.getLogger(__name__)

ABILITY_CARD_ID = "CS1_113"          # [mc_extract_frame:28]


@dataclass
class AbilityKit:
    """ability 帧三件套真内存对象（旧 ability_frame+data 镜像布局位的内存面）。"""
    recon_meta: dict = field(default_factory=dict)   # frame_recon.json 内容面
    arrays: dict = field(default_factory=dict)       # mesh_data.npz 内容面
    textures: dict = field(default_factory=dict)     # textures/（recon+report 合流）{文件名: PIL}
    portrait: Image.Image | None = None              # portrait_CS1_113.png
    portrait_meta: dict = field(default_factory=dict)  # portrait_recon.json 内容面
    report: dict = field(default_factory=dict)       # prefab_report.json 内容面
    obj_texts: dict = field(default_factory=dict)    # meshes/*.obj {文件名: obj 文本}
    fonts_bytes: dict = field(default_factory=dict)  # fonts/* {文件名: 字节}
    ubertext: dict = field(default_factory=dict)     # prefab_ubertext_ability.json 内容面
    mesh_refs: dict = field(default_factory=dict)    # 网格名→(bundle,pid) 结构引用
    # （MeshFilter PPtr 现场解随走查捕获；派生件链化取用，不进对拍面）


# ============================================================================
# 件一：extract_ability_recon [mc_extract_frame.py:98-346 逐字；OUT → 参数]
# ============================================================================

def _hand_spell_ref(quality: str = "normal") -> str:
    # 品质×槽位活表（kits.actor_ref 三活表贯穿；premium=Card_Hand_Ability_Premium，
    # ActorNames.cs s_premiumActorAssets[HAND_SPELL] 镜像——capture-determinism 2026-10-30）
    return actor_ref(quality, "HAND_SPELL")


def _mat4(pos, rot, scale) -> np.ndarray:
    """[mc_extract_frame 同构 mat4；与 engine.mat4_from_trs 同式——独立保留防串线]"""
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


def _walk_sf(env):
    from UnityPy.files import SerializedFile

    def walk(f):
        if isinstance(f, SerializedFile):
            yield f
            return
        subs = getattr(f, "files", None)
        if isinstance(subs, dict):
            for s in subs.values():
                yield from walk(s)

    yield from walk(list(env.files.values())[0])


def _recon_walk(r, bundle, root_reader, textures: dict) -> dict:
    """[mc_extract_frame.py:114-280 逐字：by_path 同-file 快查 + read_pptr_obj]"""
    root_tree = root_reader.read_typetree()
    env = r.open_bundle(bundle)
    mesh_refs: dict[str, tuple[str, int]] = {}   # 网格名→(bundle,pid)（结构引用随走查捕获）

    def find_sf():
        for sf in _walk_sf(env):
            if root_reader.path_id in sf.objects:
                return sf
        return None

    sf = find_sf()

    def by_path(pid: int):
        return sf.objects.get(pid) if pid in sf.objects else None

    def components_of(go_tree):
        out = []
        for comp in go_tree.get("m_Component", []):
            rr = by_path(comp["component"]["m_PathID"])
            if rr is not None:
                out.append((comp, rr))
        return out

    def read_pptr_obj(cur_bundle: str, ptr: dict, owner=None):
        if not ptr or not ptr.get("m_PathID"):
            return None, None
        try:
            return r.resolve_pptr(cur_bundle, ptr, owner_obj=owner)
        except PPtrError as e:  # 批9a：分类上账（builtin 静默容忍，未知台账+打印）
            record_pptr_miss(e)
            if e.reason != "builtin":
                logger.warning(f"[pptr miss][UNKNOWN] {ptr} -> {e}")
            return None, None

    def texture_info(tex_reader, bundle_: str) -> dict:
        tree = tex_reader.read_typetree()
        return {"name": tree.get("m_Name"), "type": "Texture2D", "bundle": bundle_,
                "path_id": tex_reader.path_id, "width": tree.get("m_Width"),
                "height": tree.get("m_Height"), "format": tree.get("m_TextureFormat")}

    def extract_mesh(mesh_reader, bundle_: str) -> dict | None:
        try:
            mesh = mesh_reader.read()
            h = MeshHandler(mesh)
            h.process()
            verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
            uv0 = np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0 else np.zeros((len(verts), 2))
            tris_per_sub = []
            for sub in h.get_triangles():
                tris = np.array([t for t in sub if len(t) == 3], dtype=np.int32)
                tris_per_sub.append(tris)
            result = {"name": mesh.m_Name, "verts": verts, "uv0": uv0,
                      "submeshes": tris_per_sub,
                      "bbox_min": verts.min(axis=0).tolist(), "bbox_max": verts.max(axis=0).tolist(),
                      "bundle": bundle_, "path_id": mesh_reader.path_id}
            mesh_refs[result["name"]] = (bundle_, mesh_reader.path_id)
            return result
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[mesh fail] {getattr(mesh_reader, 'path_id', '?')}: {type(e).__name__}: {e}")
            return None

    def walk(go_reader, depth=0, parent_active=True):
        tree = go_reader.read_typetree()
        name = tree["m_Name"]
        node = {"name": name, "go_path_id": go_reader.path_id, "transform_path_id": None,
                "local": None, "world": None, "children": [], "renderers": [],
                "active_self": bool(tree.get("m_IsActive", 1)),
                "active_in_hierarchy": bool(parent_active and tree.get("m_IsActive", 1))}
        transform = None
        for comp, rr in components_of(tree):
            ctype = rr.type.name
            ctree = rr.read_typetree()
            if ctype == "Transform":
                transform = ctree
                node["transform_path_id"] = rr.path_id
                p = ctree["m_LocalPosition"]
                q = ctree["m_LocalRotation"]
                s = ctree["m_LocalScale"]
                node["local"] = {"pos": [p["x"], p["y"], p["z"]],
                                 "rot": [q["x"], q["y"], q["z"], q["w"]],
                                 "scale": [s["x"], s["y"], s["z"]]}
            elif ctype in ("MeshFilter",):
                mesh_reader, mb = read_pptr_obj(bundle, ctree.get("m_Mesh"), rr)
                if mesh_reader is not None:
                    mesh = extract_mesh(mesh_reader, mb)
                    if mesh is not None:
                        node.setdefault("mesh", mesh)
            elif ctype == "MeshRenderer":
                mats = []
                for mp in ctree.get("m_Materials", []):
                    m_reader, mb = read_pptr_obj(bundle, mp, rr)
                    if m_reader is None:
                        mats.append(None)
                        continue
                    mt = m_reader.read_typetree()
                    minfo = {"name": mt.get("m_Name"), "bundle": mb, "path_id": m_reader.path_id,
                             "shader": None, "tex": {}, "colors": {}, "floats": {}}
                    saved = mt.get("m_SavedProperties", {})

                    for first, sec in as_pairs(saved.get("m_TexEnvs"),
                                               what="m_TexEnvs").items():
                        prop = first
                        sec = sec or {}
                        tptr = sec.get("m_Texture") or {}
                        sc_, of = sec.get("m_Scale") or {}, sec.get("m_Offset") or {}
                        info = {"scale": [sc_.get("x", 1), sc_.get("y", 1)],
                                "offset": [of.get("x", 0), of.get("y", 0)]}
                        if tptr.get("m_PathID"):
                            t_reader, tb = read_pptr_obj(mb or bundle, tptr, m_reader)
                            if t_reader is not None and t_reader.type.name == "Texture2D":
                                tinfo = texture_info(t_reader, tb)
                                info["texture"] = tinfo
                                fname = f"{tinfo['name']}.png"
                                if fname not in textures:
                                    textures[fname] = t_reader.read().image
                                info["texture"]["file"] = fname
                        minfo["tex"][prop] = info
                    for first, sec in as_pairs(saved.get("m_Colors"),
                                               what="m_Colors").items():
                        minfo["colors"][first] = as_rgba(sec)
                    for first, sec in as_pairs(saved.get("m_Floats"),
                                               what="m_Floats").items():
                        minfo["floats"][first] = sec
                    mats.append(minfo)
                node["renderers"].append({"enabled": ctree.get("m_Enabled"), "materials": mats,
                                          "renderer_path_id": rr.path_id})
        node["_transform_tree"] = transform
        for child_ptr in transform.get("m_Children", []):
            child_pid = child_ptr.get("m_PathID")
            child_tr = by_path(child_pid)
            if child_tr is None:
                continue
            child_tr_tree = child_tr.read_typetree()
            go_ptr = child_tr_tree.get("m_GameObject", {}).get("m_PathID")
            child_go = by_path(go_ptr)
            if child_go is None:
                continue
            child_node = walk(child_go, depth + 1, node["active_in_hierarchy"])
            node["children"].append(child_node)
        return node

    root_node = walk(root_reader)

    def assign_world(node, parent_m):
        M = _mat4(**{k: node["local"][k] for k in ("pos", "rot", "scale")}) if node["local"] else np.eye(4)
        node["world"] = (parent_m @ M).tolist()
        for ch in node["children"]:
            assign_world(ch, np.array(node["world"]))
        node.pop("_transform_tree", None)

    assign_world(root_node, np.eye(4))

    arrays: dict[str, np.ndarray] = {}

    def collect(node, path: str):
        mesh = node.get("mesh")
        if mesh:
            key = path
            arrays[f"{key}/verts"] = mesh["verts"]
            arrays[f"{key}/uv0"] = mesh["uv0"]
            for i, tris in enumerate(mesh["submeshes"]):
                arrays[f"{key}/sub{i}"] = tris
            node["mesh_stats"] = {"name": mesh["name"], "verts": len(mesh["verts"]),
                                  "submesh_tris": [len(t) for t in mesh["submeshes"]],
                                  "bbox_min": mesh["bbox_min"], "bbox_max": mesh["bbox_max"]}
            del node["mesh"]
        for i, ch in enumerate(node["children"]):
            collect(ch, f"{path}.{i}" if path else str(i))

    collect(root_node, "root")
    return {"root_node": root_node, "arrays": arrays, "mesh_refs": mesh_refs}


def _school_extra(r, quality: str = "normal", report: dict | None = None) -> tuple[dict, dict]:
    """学校描述附加网格。**豁免行**（见模块 docstring）：bundle+名字双谓词扫描——
    prefab 序列化不引用该网格（层级走查零命中实证），运行时换装件。
    名字账（2026-10-10）：现名=Card_In**H**and_Ability_Description_School_mesh；
    旧代码字面量为 Inhand 小写 h——**E0「对象名跨版本稳定」首例反例**（游戏内容
    更新改大小写，guid 不变；名字谓词从此挂对拍监视）。
    [mc_extract_frame:283-303 同构；名字谓词按现文件更新]
    quality 分派（2026-11-04 金法术 98918 网格错配修复）：normal 走上述豁免行
    原形逐字不动；premium 学派网格=prefab 序列化引用**现场解**——report actor
    组件 m_spellDescriptionMeshSchool PPtr（UpdateRace 运行时写
    meshFilter.sharedMesh 的同一引用面；bundle+path_id 直取，实取名与 PPtr 名
    一致断言=漂移 tripwire，E0 教训下 premium 不设名字谓词），键
    =extra/school_desc_premium。两品质网格实证：A=Card_InHand_Ability_Description_
    School_mesh（essential_base_global-mesh-0）、B=Card_InHand_Ability_Premium_
    Description_School_mesh（initial_base_global-910a3655-mesh-0），A 对 B 整体
    local z −0.0126≈屏幕 2.3px 整板错位——premium 帧吃 A 即错配根源。"""
    def extract_mesh(mesh_reader, bundle_: str) -> dict | None:
        mesh = mesh_reader.read()
        h = MeshHandler(mesh)
        h.process()
        verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
        uv0 = np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0 else np.zeros((len(verts), 2))
        tris_per_sub = [np.array([t for t in sub if len(t) == 3], dtype=np.int32)
                        for sub in h.get_triangles()]
        return {"name": mesh.m_Name, "verts": verts, "uv0": uv0, "submeshes": tris_per_sub,
                "bbox_min": verts.min(axis=0).tolist(), "bbox_max": verts.max(axis=0).tolist(),
                "bundle": bundle_, "path_id": mesh_reader.path_id}

    school_extra: dict = {}
    arrays: dict[str, np.ndarray] = {}

    if quality == "premium":
        # premium 分派：PPtr 现场解（解法=frames.supplements 对账行同式——open_bundle
        # 后 objects 按 type+path_id 直取），禁名字谓词（E0 名字漂移反例）。
        ref = ((report or {}).get("actor_components") or [{}])[0].get(
            "object_refs", {}).get("m_spellDescriptionMeshSchool")
        assert ref and ref.get("type") == "Mesh" and ref.get("bundle") \
            and ref.get("path_id"), f"premium 学派网格 PPtr 未解析: {ref}"
        env_b = r.open_bundle(ref["bundle"])
        found = None
        for o in env_b.objects:
            if o.type.name != "Mesh" or o.path_id != ref["path_id"]:
                continue
            found = extract_mesh(o, ref["bundle"])
            break
        assert found is not None, \
            f"premium 学派网格 pid {ref['path_id']} 未找到（{ref['bundle']}）"
        assert found["name"] == ref.get("name"), \
            f"学派网格名字漂移: PPtr 实名={ref.get('name')} 实取={found['name']}"
        key = "extra/school_desc_premium"
        school_extra[key] = {"name": found["name"], "verts": len(found["verts"]),
                             "submesh_tris": [len(t) for t in found["submeshes"]],
                             "bbox_min": found["bbox_min"], "bbox_max": found["bbox_max"]}
        arrays[f"{key}/verts"] = found["verts"]
        arrays[f"{key}/uv0"] = found["uv0"]
        for i, tris in enumerate(found["submeshes"]):
            arrays[f"{key}/sub{i}"] = tris
        return school_extra, arrays

    for mesh_name, key in [("Card_InHand_Ability_Description_School_mesh", "extra/school_desc")]:
        found = None
        for b in ("essential_base_global-mesh-0.unity3d",):
            try:
                # 走 resolver（航线/惰性路）而**不是** UnityPy.load：
                # 后者给 env 带上游戏目录 path，container 的 preload 表一 deref 外部引用就
                # find_file 未命中 → fs.walk 全目录（11k 文件）→ 单次 ~5ms，
                # 实测 5,415 次 ≈ 30s（2026-10-17 首触画像的头号项）。
                env_b = r.open_bundle(b)
            except Exception:                          # noqa: BLE001
                continue
            for _ckey, o in env_b.container.items():
                if o.type.name != "Mesh":              # 先按类型筛，再读 typetree（省 8k 次解码）
                    continue
                t = o.read_typetree()
                if t.get("m_Name") == mesh_name:
                    found = extract_mesh(o, b)
                    break
            if found:
                break
        if found:
            school_extra[key] = {"name": found["name"], "verts": len(found["verts"]),
                                 "submesh_tris": [len(t) for t in found["submeshes"]],
                                 "bbox_min": found["bbox_min"], "bbox_max": found["bbox_max"]}
            arrays[f"{key}/verts"] = found["verts"]
            arrays[f"{key}/uv0"] = found["uv0"]
            for i, tris in enumerate(found["submeshes"]):
                arrays[f"{key}/sub{i}"] = tris
    return school_extra, arrays


def _ability_portrait(r) -> tuple[Image.Image | None, dict]:
    """CardDef 原画自提 [mc_extract_frame:306-345 逐字]。"""
    card_ref = r.card_def_ref(ABILITY_CARD_ID)
    if not card_ref:
        return None, {}
    cd = r.resolve(card_ref)
    if not cd["ok"]:
        return None, {}
    cb = cd["resolved"]["bundle"]
    cd_reader, _ = r.container_get(cb, cd["resolved"]["guid"])
    ct = cd_reader.read_typetree()
    portrait_ref = None
    if "m_PortraitTexturePath" in ct:
        portrait_ref = ct.get("m_PortraitTexturePath")
    else:
        for comp in ct.get("m_Component", []):
            cr, cb2 = r.resolve_pptr(cb, comp["component"], cd_reader)
            if cr is None or cr.type.name != "MonoBehaviour":
                continue
            try:
                sr, _ = r.resolve_pptr(cb2, cr.read_typetree().get("m_Script", {}), cr)
                cls = sr.read_typetree().get("m_ClassName", "")
            except Exception:  # noqa: BLE001
                cls = "?"
            if cls == "CardDef":
                portrait_ref = cr.read_typetree().get("m_PortraitTexturePath")
                break
    if not portrait_ref:
        return None, {}
    pr = r.resolve(portrait_ref)
    if not pr["ok"]:
        return None, {}
    pb = pr["resolved"]["bundle"]
    p_reader, _ = r.container_get(pb, pr["resolved"]["guid"])
    img = p_reader.read().image
    meta = {"card_id": ABILITY_CARD_ID, "portrait_ref": portrait_ref,
            "bundle": pb, "file": f"portrait_{ABILITY_CARD_ID}.png", "size": list(img.size)}
    return img, meta


# ============================================================================
# 件二：prefab_report [_mc_asset_frame_extract → _McExtractor 逐字；落盘→内存面]
# ============================================================================

def _sanitize(name: str) -> str:
    """[mc_asset_frame_extract:39-40]"""
    return re.sub(r"[^A-Za-z0-9_.\-]+", "_", name) or "root"


def _cab_of(obj) -> str:
    """[mc_asset_frame_extract:50-51]"""
    return Path(str(getattr(obj.assets_file, "name", ""))).name.lower()


class _Ctx:
    """[mc_asset_frame_extract:54-84 逐字]"""

    def __init__(self, r: Resolver, bundle: str):
        self.r = r
        self.bundle = bundle
        self.rev: dict[tuple[str, int], str] = {}
        env = r.open_bundle(bundle)
        for key, pptr in env.container.container_dict.items():
            try:
                o = pptr.deref()
            except Exception:  # noqa: BLE001
                continue
            self.rev[(_cab_of(o), o.path_id)] = key

    def guid_of(self, obj) -> str | None:
        return self.rev.get((_cab_of(obj), obj.path_id))

    def deref(self, ptr: dict, owner):
        return self.r.resolve_pptr(self.bundle, ptr, owner)

    def asset_info(self, obj, bundle: str) -> dict:
        info: dict = {"type": obj.type.name, "path_id": obj.path_id, "bundle": bundle,
                      "guid": self.guid_of(obj) if bundle == self.bundle else None}
        try:
            t = obj.read_typetree()
            info["name"] = t.get("m_Name")
        except Exception as exc:  # noqa: BLE001
            info["name"] = None
            info["error"] = f"{type(exc).__name__}: {exc}"
        return info


class _McExtractor:
    """[mc_asset_frame_extract:87-513 逐字；OUT_DIR → 内存面（textures/fonts_bytes/obj_texts）]"""

    def __init__(self, r: Resolver, actor_ref: str, atlas_ref: str,
                 textures: dict, fonts_bytes: dict, obj_texts: dict):
        self.r = r
        self.OUT_DIR = None
        self.actor_ref = actor_ref
        self.atlas_ref = atlas_ref
        self.textures_out = textures
        self.fonts_bytes = fonts_bytes
        self.obj_texts = obj_texts
        self.ctx: _Ctx | None = None
        self._foreign_rev: dict[str, dict[int, str]] = {}   # 跨包 bundle → path_id→container 键
        self.nodes: list[dict] = []
        self.mesh_jobs: list[dict] = []
        self.texture_jobs: list[dict] = []
        self.fonts: dict[str, dict] = {}
        self.issues: list[str] = []

    def _guid_of(self, bundle: str, obj) -> str | None:
        """对象 guid：同包走 ctx 反向索引；跨包按其所属 bundle container 反查（**v3 改进**：
        旧代码跨包 guid=None → 文件名退化为进程随机 hash——非确定性命名，两轮运行文件名
        必不同=旧 cache 垃圾积累根因；v3 guid 稳定名）。"""
        if bundle == self.ctx.bundle:
            return self.ctx.guid_of(obj)
        rev = self._foreign_rev.get(bundle)
        if rev is None:
            env = self.r.open_bundle(bundle)
            rev = {}
            for _key, pptr in env.container.container_dict.items():
                try:
                    o = pptr.deref()
                except Exception:  # noqa: BLE001
                    continue
                rev[o.path_id] = _key
            self._foreign_rev[bundle] = rev
        return rev.get(obj.path_id)

    def queue_texture(self, obj, bundle: str, used_by: str, slot: str) -> dict | None:
        for job in self.texture_jobs:
            if job["bundle"] == bundle and job["tex_obj"].path_id == obj.path_id:
                job["used_by"].append(f"{used_by}:{slot}")
                return job["info"]
        info = self.ctx.asset_info(obj, bundle) if bundle == self.ctx.bundle else self._foreign_info(obj, bundle)
        self.texture_jobs.append({"tex_obj": obj, "info": info, "bundle": bundle,
                                  "used_by": [f"{used_by}:{slot}"]})
        return info

    def _foreign_info(self, obj, bundle: str) -> dict:
        info = {"type": obj.type.name, "path_id": obj.path_id, "bundle": bundle}
        try:
            t = obj.read_typetree()
            info["name"] = t.get("m_Name")
        except Exception as exc:  # noqa: BLE001
            info["name"], info["error"] = None, f"{type(exc).__name__}: {exc}"
        return info

    def save_textures(self) -> list[dict]:
        saved = []
        for job in self.texture_jobs:
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
            g = info.get("guid") or self._guid_of(job["bundle"], obj) or ""
            fname = f"{_sanitize(name)}_{g[:8] or abs(hash((job['bundle'], obj.path_id))) % 10**8}.png"
            try:
                self.textures_out[fname] = obj.read().image
                info["file"] = f"textures/{fname}"
            except Exception as exc:  # noqa: BLE001
                info["file"] = None
                info["error"] = f"decode {type(exc).__name__}: {exc}"
            saved.append(info)
        return saved

    def probe_font(self, font_ptr: dict, owner) -> dict | None:
        key = f"{font_ptr['m_FileID']}:{font_ptr['m_PathID']}"
        if not font_ptr["m_PathID"]:
            return None
        if key in self.fonts:
            return {"ref": key, "already_recorded": True}
        try:
            fobj, fbundle = self.ctx.deref(font_ptr, owner)
        except PPtrError as exc:
            record_pptr_miss(exc)
            self.fonts[key] = {"ref": key, "error": f"{exc.reason}: {exc.detail}"}
            return self.fonts[key]
        rec: dict = {"ref": key, "bundle": fbundle, "path_id": fobj.path_id,
                     "type": fobj.type.name}
        try:
            ft = fobj.read_typetree()
            rec["font_name"] = ft.get("m_Name")
            data = ft.get("m_FontData")
            if isinstance(data, list) and len(data) > 4:
                data = bytes(data)
            if isinstance(data, (bytes, bytearray)) and len(data) > 4:
                head = bytes(data[:4])
                ext = ".otf" if head == b"OTTO" else ".ttf"
                out = f"{_sanitize(str(rec['font_name']))}{ext}"
                self.fonts_bytes[out] = bytes(data)
                rec["m_FontData_bytes"] = len(data)
                rec["file"] = f"fonts/{out}"
                rec["sniff"] = head.hex()
            else:
                rec["m_FontData_bytes"] = len(data) if data else 0
                rec["file"] = None
                rec["note"] = ("动态字体/引用型：无内嵌 TTF 字节（m_FontData 空），"
                               "字形由运行时按 FontTable/OS 光栅化——H2 用替代字体")
                rec["structure_keys"] = sorted(k for k in ft.keys() if k.startswith("m_"))
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"
        self.fonts[key] = rec
        return {"ref": key, "font_name": rec.get("font_name"), "bundle": fbundle}

    def walk_material(self, mat_obj, bundle: str, used_by: str) -> dict:
        rec: dict = {"slot_used_by": used_by}
        try:
            mt = mat_obj.read_typetree()
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"
            return rec
        rec["name"] = mt.get("m_Name")
        rec["guid"] = self.ctx.guid_of(mat_obj) if bundle == self.ctx.bundle else None
        rec["bundle"] = bundle
        texenvs = as_pairs((mt.get("m_SavedProperties") or {}).get("m_TexEnvs"),
                           what="m_TexEnvs")
        texs = {}
        for slot_name, slot in texenvs.items():
            tp = slot.get("m_Texture") if isinstance(slot, dict) else None
            if not tp or not (tp.get("m_PathID")):
                continue
            try:
                tobj, tbundle = self.ctx.deref(tp, mat_obj)
            except PPtrError as exc:
                record_pptr_miss(exc)
                texs[slot_name] = {"error": f"{exc.reason}: {exc.detail}"}
                continue
            info = self.queue_texture(tobj, tbundle, used_by, slot_name)
            texs[slot_name] = {"name": info.get("name"), "guid": info.get("guid"),
                               "bundle": tbundle, "path_id": tobj.path_id}
        rec["textures"] = texs
        return rec

    def walk_renderer(self, comp_obj, comp_type: str, node_path: str) -> dict:
        try:
            ct = comp_obj.read_typetree()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}
        rec: dict = {"component": comp_type}
        mesh_ptr = ct.get("m_Mesh")
        if mesh_ptr and mesh_ptr.get("m_PathID"):
            try:
                mobj, mbundle = self.ctx.deref(mesh_ptr, comp_obj)
            except PPtrError as exc:
                record_pptr_miss(exc)
                rec["mesh"] = {"error": f"{exc.reason}: {exc.detail}"}
                mobj = mbundle = None
            if mobj is not None:
                minfo = self.ctx.asset_info(mobj, mbundle) if mbundle == self.ctx.bundle \
                    else self._foreign_info(mobj, mbundle)
                try:
                    mt = mobj.read_typetree()
                    minfo["submesh_count"] = len(mt.get("m_SubMeshes") or [])
                    minfo["vertex_count"] = mt.get("m_VertexCount")
                except Exception:  # noqa: BLE001
                    pass
                rec["mesh"] = minfo
                self.mesh_jobs.append({"node_path": node_path, "mesh_obj": mobj,
                                       "bundle": mbundle, "info": minfo})
        mats = ct.get("m_Materials") or []
        slots = []
        for i, mp in enumerate(mats):
            pd = mp if isinstance(mp, dict) else {}
            if not pd.get("m_PathID"):
                slots.append({"slot": i, "empty": True})
                continue
            try:
                mobj, mbundle = self.ctx.deref(pd, comp_obj)
            except PPtrError as exc:
                record_pptr_miss(exc)
                slots.append({"slot": i, "error": f"{exc.reason}: {exc.detail}"})
                continue
            slots.append({"slot": i, **self.walk_material(mobj, mbundle, node_path)})
        rec["material_slots"] = slots
        return rec

    def walk_go(self, go_obj, parent_path: str, depth: int = 0) -> None:
        if depth > 12:
            return
        try:
            gt = go_obj.read_typetree()
        except Exception as exc:  # noqa: BLE001
            self.issues.append(f"GameObject {go_obj.path_id} 读取失败: {exc}")
            return
        name = gt.get("m_Name") or f"go_{go_obj.path_id}"
        node_path = f"{parent_path}/{name}" if parent_path else name
        node: dict = {"path": node_path, "go_path_id": go_obj.path_id, "components": {}}
        transform_ptr = None
        for pair in gt.get("m_Component") or []:
            comp_ptr = pair.get("component") if isinstance(pair, dict) else getattr(pair, "component", None)
            pd = {"m_FileID": (comp_ptr or {}).get("m_FileID", 0),
                  "m_PathID": (comp_ptr or {}).get("m_PathID", 0)}
            if not pd["m_PathID"]:
                continue
            try:
                cobj, cbundle = self.ctx.deref(pd, go_obj)
            except PPtrError as exc:
                record_pptr_miss(exc)
                node["components"][f"pathid_{pd['m_PathID']}"] = {"error": f"{exc.reason}"}
                continue
            ctype = cobj.type.name
            if ctype == "Transform":
                transform_ptr = pd
                tt = cobj.read_typetree()
                node["transform"] = {
                    "local_position": tt.get("m_LocalPosition"),
                    "local_rotation": tt.get("m_LocalRotation"),
                    "local_scale": tt.get("m_LocalScale"),
                }
                continue
            if ctype in ("MeshFilter", "MeshRenderer", "SkinnedMeshRenderer"):
                rec = self.walk_renderer(cobj, ctype, node_path)
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
                if not isinstance(mt, dict):
                    continue
                if "m_cardMesh" in mt or "m_portraitMesh" in mt:
                    node["components"]["Actor"] = self.actor_record(mt, cobj)
                elif "m_Text" in mt and "m_Font" in mt:
                    node["components"]["TextComponent"] = self.text_record(mt, cobj, node_path)
                elif "m_PortraitTexturePath" in mt:
                    node["components"]["CardDef"] = {
                        "path_id": cobj.path_id,
                        "m_PortraitTexturePath": mt.get("m_PortraitTexturePath"),
                    }
                continue
        self.nodes.append(node)
        if transform_ptr:
            try:
                tobj, _ = self.ctx.deref(transform_ptr, go_obj)
                tt = tobj.read_typetree()
                for ch in tt.get("m_Children") or []:
                    cpd = ch if isinstance(ch, dict) else {}
                    if not cpd.get("m_PathID"):
                        continue
                    try:
                        cobj, _2 = self.ctx.deref(cpd, tobj)
                        cgt = cobj.read_typetree()
                        gop = cgt.get("m_GameObject")
                        child_go, _3 = self.ctx.deref(gop, cobj)
                        self.walk_go(child_go, node_path, depth + 1)
                    except PPtrError as exc:
                        record_pptr_miss(exc)
                        self.issues.append(f"{node_path} 子节点解析失败: {exc.reason}")
            except PPtrError as exc:
                record_pptr_miss(exc)
                self.issues.append(f"{node_path} Transform 解析失败: {exc.reason}")

    def actor_record(self, mt: dict, cobj) -> dict:
        rec: dict = {"path_id": cobj.path_id}
        # m_alternateCostTextLocalPos：Actor 序列化 Vector3（费用数字铸币位，逐 prefab
        # 不同——金随从帧 +0.025 vs 普通 −0.01，2026-11-04 golden-alt-cost-pos 实证）。
        # 白名单显式收，消费方经 recon_meta["actor_alt_cost_pos"] 读。
        for k in ("m_cardFrontMatIdx", "m_portraitMatIdx", "m_portraitFrameMatIdx",
                  "m_cardBackMatIdx", "m_premiumRibbon", "m_portraitMatIdxActor",
                  "m_alternateCostTextLocalPos"):
            if k in mt:
                rec[k] = mt[k]
        rec["_pptr_fields"] = {}
        for k, v in mt.items():
            if k.startswith("m_") and isinstance(v, dict) and "m_PathID" in v:
                rec["_pptr_fields"][k] = {"m_FileID": v.get("m_FileID", 0),
                                          "m_PathID": v.get("m_PathID", 0)}
        return rec

    def finalize_actor(self, actor_rec: dict, root_owner) -> dict:
        out = {k: v for k, v in actor_rec.items() if k != "_pptr_fields"}
        by_pid = {n["go_path_id"]: n["path"] for n in self.nodes}
        refs = {}
        for k, pd in actor_rec.get("_pptr_fields", {}).items():
            if not pd["m_PathID"]:
                continue
            entry: dict = {"file_id": pd["m_FileID"], "path_id": pd["m_PathID"]}
            hit = by_pid.get(pd["m_PathID"])
            if hit:
                entry["node"] = hit
            else:
                try:
                    o, b = self.ctx.deref(pd, root_owner)
                    info = self.ctx.asset_info(o, b) if b == self.ctx.bundle else self._foreign_info(o, b)
                    entry.update({"name": info.get("name"), "type": info.get("type"),
                                  "bundle": b, "guid": info.get("guid")})
                except PPtrError as exc:
                    entry["error"] = exc.reason
            refs[k] = entry
        out["object_refs"] = refs
        return out

    def text_record(self, mt: dict, cobj, node_path: str) -> dict:
        rec: dict = {"path_id": cobj.path_id, "text": (mt.get("m_Text") or "")[:80],
                     "font_size": mt.get("m_FontSize")}
        for k in ("m_Color", "m_Alignment", "m_Anchor", "m_UseEllipsis", "m_WordWrap",
                  "m_RenderMode", "m_CurveModifier"):
            if k in mt:
                rec[k] = mt[k]
        keys = sorted(k for k in mt.keys() if k.startswith("m_"))
        rec["suspected_class"] = "UberText" if "m_FontSize" in mt else "CurvedText/other"
        rec["all_m_keys"] = keys
        fp = mt.get("m_Font")
        if fp:
            pd = {"m_FileID": fp.get("m_FileID", 0), "m_PathID": fp.get("m_PathID", 0)}
            rec["font_pptr"] = pd
            res = self.probe_font(pd, cobj)
            if res:
                rec["font_resolved"] = res
        return rec

    def run(self) -> dict:
        res = self.r.resolve(self.actor_ref)
        assert res["ok"], f"actor ref 解析失败: {res['checks']}"
        bundle = res["resolved"]["bundle"]
        guid = res["resolved"]["guid"]
        self.ctx = _Ctx(self.r, bundle)
        root_obj, _ = self.ctx.r.container_get(bundle, guid)
        self.walk_go(root_obj, "", 0)

        actor_recs = [n["components"]["Actor"] for n in self.nodes if "Actor" in n["components"]]
        actor_final = [self.finalize_actor(rec, root_obj) for rec in actor_recs]

        dumped_keys = {(j["bundle"], j["mesh_obj"].path_id) for j in self.mesh_jobs}
        for rec in actor_final:
            for field, v in rec.get("object_refs", {}).items():
                if v.get("type") != "Mesh" or not v.get("bundle"):
                    continue
                key = (v["bundle"], v["path_id"])
                if key in dumped_keys:
                    continue
                try:
                    mobj, mbundle = self.ctx.deref(
                        {"m_FileID": v.get("file_id", 0), "m_PathID": v["path_id"]}, root_obj)
                except PPtrError as exc:
                    record_pptr_miss(exc)
                    self.issues.append(f"actor mesh {field}: {exc.reason}")
                    continue
                minfo = self.ctx.asset_info(mobj, mbundle) if mbundle == self.ctx.bundle \
                    else self._foreign_info(mobj, mbundle)
                try:
                    mt = mobj.read_typetree()
                    minfo["submesh_count"] = len(mt.get("m_SubMeshes") or [])
                except Exception:  # noqa: BLE001
                    pass
                minfo["via_actor_field"] = field
                self.mesh_jobs.append({"node_path": field, "mesh_obj": mobj,
                                       "bundle": mbundle, "info": minfo})
                dumped_keys.add(key)

        atlas_res = self.r.resolve(self.atlas_ref)
        atlas_bundle = atlas_res["resolved"]["bundle"]
        aobj, _ = self.r.container_get(atlas_bundle, atlas_res["resolved"]["guid"])
        atlas_info = None
        if aobj is not None:
            info = {"type": aobj.type.name, "path_id": aobj.path_id, "bundle": atlas_bundle,
                    "guid": atlas_res["resolved"]["guid"]}
            t = aobj.read_typetree()
            info["name"], info["width"], info["height"] = t.get("m_Name"), t.get("m_Width"), t.get("m_Height")
            info["texture_format"] = t.get("m_TextureFormat")
            atlas_info = info
            self.texture_jobs.append({"tex_obj": aobj, "info": info, "bundle": atlas_bundle,
                                      "used_by": ["CardColorSwitcher.spellCardTextures[7]:_MainTex"]})

        textures = self.save_textures()

        from UnityPy.export import MeshExporter

        meshes_report = []
        seen_mesh_files: dict[tuple[str, int], str] = {}
        seen_mesh_nodes: dict[tuple[str, int], str] = {}
        for job in self.mesh_jobs:
            node_path, mobj, mbundle, minfo = job["node_path"], job["mesh_obj"], job["bundle"], job["info"]
            key = (mbundle, mobj.path_id)
            fname = f"{_sanitize(node_path)}.obj"
            entry = {"node": node_path, "mesh_name": minfo.get("name"),
                     "guid": minfo.get("guid"), "bundle": mbundle,
                     "path_id": mobj.path_id, "submesh_count": minfo.get("submesh_count")}
            if key in seen_mesh_files:
                entry["file"] = seen_mesh_files[key]
                entry["shared_with_node"] = seen_mesh_nodes[key]
            else:
                try:
                    obj_text = MeshExporter.export_mesh_obj(mobj.read())
                    header = (f"# node: {node_path}\n# mesh: {minfo.get('name')} "
                              f"bundle={mbundle} path_id={mobj.path_id} guid={minfo.get('guid')}\n"
                              f"# UnityPy 导出约定：X 坐标取反（Unity 左手系→obj 右手系）\n")
                    self.obj_texts[fname] = header + obj_text
                    entry["file"] = f"meshes/{fname}"
                    seen_mesh_files[key] = entry["file"]
                    seen_mesh_nodes[key] = node_path
                except Exception as exc:  # noqa: BLE001
                    entry["file"] = None
                    entry["error"] = f"{type(exc).__name__}: {exc}"
            meshes_report.append(entry)

        report = {
            "prefab": {"name": "Card_Hand_Ability", "ref": self.actor_ref, "guid": guid, "bundle": bundle},
            "class_atlas": {"ref": self.atlas_ref, "colorType_index": 7, "colorType": "TYPE_PRIEST",
                            "resolved": atlas_info,
                            "apply": "SetMaterialWithTexture: cardMesh 材质[m_cardFrontMatIdx]._MainTex "
                                     "+ portraitMesh 材质[m_portraitFrameMatIdx]._MainTex"},
            "nodes": self.nodes,
            "actor_components": actor_final,
            "meshes": meshes_report,
            "textures": textures,
            "fonts": list(self.fonts.values()),
            "issues": self.issues,
        }
        logger.debug(f"[prefab_report] nodes={len(self.nodes)} meshes={len(meshes_report)} "
                     f"textures={len(textures)} issues={len(self.issues)}")
        return report


# ============================================================================
# 件三：prefab_ubertext_ability [tp1_dump_prefab_ubertext.py:24-168 逐字；OUT → 参数]
# ============================================================================

def _build_ubertext(r: Resolver, actor_ref: str) -> dict:
    res = r.resolve(actor_ref)
    bundle = res["resolved"]["bundle"]
    guid = res["resolved"]["guid"]
    env = r.open_bundle(bundle)
    obj, _key = r.container_get(bundle, guid)

    cache: dict[tuple, object] = {}

    def deref(pptr, owner_obj, expect: str | None = None):
        fid = pptr.get("m_FileID", 0)
        pid = pptr.get("m_PathID", 0)
        if not pid:
            return None
        ck = (fid, pid, id(expect))
        if ck in cache:
            return cache[ck]
        if fid == 0:
            o = owner_obj.assets_file.objects.get(pid)
        else:
            ext = list(getattr(owner_obj.assets_file, "externals", []))
            cab = Path(ext[fid - 1].path).name.lower() if len(ext) >= fid else ""
            o = None
            for f in _walk_sf(env):
                fname = Path(str(getattr(f, "name", ""))).name.lower()
                if fname == cab and pid in f.objects:
                    cand = f.objects[pid]
                    if expect is None or cand.type.name == expect:
                        o = cand
                        break
        cache[ck] = o
        return o

    def tt(o):
        return o.read_typetree() if o is not None else None

    def comps_of(go_tt, owner_obj):
        out = []
        for c in go_tt.get("m_Component", []):
            co = deref(c["component"], owner_obj, expect=None)
            if co is None:
                out.append(None)
                continue
            t = co.type.name
            d = tt(co)
            out.append({"kind": t, "path_id": co.path_id, "obj": co, "d": d})
        return out

    _paths: dict[int, str] = {}

    def path_of(go_obj, gtt, trc) -> str:
        pid = go_obj.path_id
        if pid in _paths:
            return _paths[pid]
        name = gtt["m_Name"]
        trd = (trc or {}).get("d", {})
        fptr = trd.get("m_Father")
        pp = ""
        if fptr and fptr.get("m_PathID") and trc is not None:
            ftr = deref(fptr, trc["obj"], expect="Transform")
            if ftr is not None:
                ftrd = tt(ftr) or {}
                fgo = deref(ftrd.get("m_GameObject", {"m_PathID": 0}), ftr, expect="GameObject")
                if fgo is not None:
                    ftt = tt(fgo) or {}
                    ftrc = {"kind": "Transform", "obj": ftr, "d": ftrd, "path_id": ftr.path_id}
                    pp = path_of(fgo, ftt, ftrc) + "/"
        _paths[pid] = pp + name
        return _paths[pid]

    nodes, extras = [], []
    want = {
        "NameBanner_mesh", "Card_InHand_Ally_CurvedText", "NameUberText",
        "Description_mesh", "PowersUberText", "RaceUberText",
        "CostObject", "CostUberText", "RacePlate_mesh",
    }

    def visit(go_obj, owner_obj) -> None:
        gtt = tt(go_obj)
        if gtt is None:
            return
        comps = comps_of(gtt, go_obj)
        trc = next((c for c in comps if c and c["kind"] == "Transform"), None)
        trd = (trc or {}).get("d", {})
        path = path_of(go_obj, gtt, trc)
        rec_base = {
            "path": path,
            "localPosition": trd.get("m_LocalPosition"),
            "localScale": trd.get("m_LocalScale"),
            "localRotation": trd.get("m_LocalRotation"),
        }
        for c in comps:
            if not c:
                continue
            d = c.get("d") or {}
            if c["kind"] == "MonoBehaviour" and "m_CharacterSize" in d and "m_FontSize" in d:
                nodes.append({**rec_base, "mono_path_id": c["path_id"], "fields": d})
        if gtt["m_Name"] in want:
            extras.append({**rec_base, "name": gtt["m_Name"], "gameobject_path_id": go_obj.path_id,
                           "components": [{k: v for k, v in c.items() if k != "obj"} for c in comps]})
        if trc:
            for ch in trd.get("m_Children", []):
                child_tr = deref(ch, trc["obj"], expect="Transform")
                if child_tr is None:
                    continue
                ctrd = tt(child_tr) or {}
                cgo = deref(ctrd.get("m_GameObject", {"m_FileID": 0, "m_PathID": 0}), child_tr,
                            expect="GameObject")
                visit(cgo, child_tr)

    visit(obj, None)
    nodes.sort(key=lambda n: n["path"])
    return {"ref": actor_ref, "bundle": bundle, "n_ubertext": len(nodes),
            "nodes": nodes, "extras": extras}


# ============================================================================
# 组装与域面
# ============================================================================

# 进程级 memo（同 kits._KIT_CACHE：ability kit=卡不变游戏结构；③外迁批6 2026-10-11）
_ABILITY_CACHE: dict = {}


@item("frames", "ability_kit")
def ability_kit(quality: str = "normal") -> AbilityKit:
    """ability 帧三件套（recon/report/ubertext 真内存）。

    quality="premium"=Card_Hand_Ability_Premium（金法术帧，capture-determinism
    2026-10-30，98918 首例）：同管线换 prefab ref（s_premiumActorAssets[HAND_SPELL]），
    结构镜像由 recon 走查自证（层级/网格/ubertext 全自 prefab 实况）。
    学派 desc 网格按 quality 分派（2026-11-04 网格错配修复）：normal=豁免行
    名字谓词（extra/school_desc），premium=prefab m_spellDescriptionMeshSchool
    序列化 PPtr 现场解（extra/school_desc_premium）——见 _school_extra。
    """
    from eidolon.core.supply import color

    if quality in _ABILITY_CACHE:
        return _ABILITY_CACHE[quality]
    r = core().res
    actor_ref = _hand_spell_ref(quality)
    atlas_ref = color.probe()["spellCardTextures"][7]   # 槽 7=牧师（对照表行 2）

    textures: dict[str, Image.Image] = {}

    # 件一 recon
    res = r.resolve(actor_ref)
    assert res["ok"], res.get("checks")
    bundle = res["resolved"]["bundle"]
    guid = res["resolved"]["guid"]
    root_reader, _ = r.container_get(bundle, guid)
    walk_res = _recon_walk(r, bundle, root_reader, textures)
    # 件二 report（先于 school_extra：premium 学派网格走 report actor 组件
    # m_spellDescriptionMeshSchool 序列化 PPtr 现场解——_school_extra quality 分派；
    # report 不读 school 数组，序前移=零行为差）
    extractor = _McExtractor(r, actor_ref, atlas_ref, textures, {}, {})
    report = extractor.run()
    school_extra, school_arrays = _school_extra(r, quality, report)
    arrays = {**walk_res["arrays"], **school_arrays}
    # 费用数字铸币位（Actor 序列化 Vector3，逐 prefab 不同）：消费=渲染侧
    # m_costTextMesh 位移（UpdateManaGemOffset）。缺字段→None（渲染侧回退代码默认，
    # 见 gems._COST_ALT_LOCAL_POS 的失效条件）。
    actor0 = (report.get("actor_components") or [{}])[0]
    recon_meta = {"prefab_ref": actor_ref, "bundle": bundle, "guid": guid,
                  "hierarchy": walk_res["root_node"], "extra_meshes": school_extra,
                  "actor_alt_cost_pos": vec3(actor0.get("m_alternateCostTextLocalPos")),
                  "quality": quality}
    portrait, portrait_meta = _ability_portrait(r)

    # 件三 ubertext
    ubertext = _build_ubertext(r, actor_ref)

    kit = AbilityKit(recon_meta=recon_meta, arrays=_ArrayDict(arrays), textures=textures,
                     portrait=portrait, portrait_meta=portrait_meta, report=report,
                     obj_texts=extractor.obj_texts, fonts_bytes=extractor.fonts_bytes,
                     ubertext=ubertext, mesh_refs=walk_res["mesh_refs"])
    _ABILITY_CACHE[quality] = kit
    return kit
