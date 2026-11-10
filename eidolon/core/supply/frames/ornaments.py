"""frames.ornaments — multiclass 派系饰品（Batch C）。

对照表（旧位 → 本域，预审 2026-10-10）：
  - 8 派系材质全账 ← extract_faction_ornaments 材质段 [mc_extract_assets:539-600 同式
    逐字]：icon×6（probe factionIconMaterials[1..6]）+banner×2（factionBannerMaterials
    [1]/[4]）——v3 probe=color.probe() 平面族表（switcher.data 面已收编）；shader 面
    deref 不可得回落 _shader_bundle_typetree（.badges 同源懒索引）。
  - Faction_Banner walk ← badges 同款累计矩阵逐字（根平移置零 [mc:418]）：
    ref=Faction_Banner.prefab:0a0897af…（guid=badges_report containers 两帧 NestedPrefab
    实测同值——引用直取免名字反查）；节点路径=GO 名路径（根 GO 名起）——**消费端
    （compile_faction_banner nodes_by_rel）按 split("Faction_Banner/",1)[-1] 剥一层定
    rel，路径多垫一层即 Faction_Icon 挂点失配**（asset-supply-fixes 修前实录）；npz 键
    faction|{node_path} [mc:346 逐字]；报告节点**扁平化** [mc:383 平铺口径——嵌套树只剩
    根可被消费，修后首渲仍 assert 的实录根因]。
  - _Ctx/_sanitize ← .ability 同源副本；trs_matrix/_mesh_arrays/_shader_bundle_typetree
    ← .badges（累计矩阵/网格/shader 三件同源逐字，引用不复制）。
产物=OrnamentsKit（faction_report+faction_meshes.npz+textures/ 真内存，落盘随阶段②）。
对拍=duipai_frames.py check_ornaments（report 逐字段+npz 逐键逐位+textures 像素逐位）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from eidolon.core.infra.resolve_asset_ref import PPtrError, Resolver
from eidolon.core.supply._projection import as_pairs, as_rgba
from eidolon.core.supply.frames.ability import _Ctx, _sanitize
from eidolon.core.supply.frames.badges import _mesh_arrays, _shader_bundle_typetree, trs_matrix
from eidolon.core.supply.frames.engine import ptr_dict, subshader_queue
from eidolon.core.supply.machine import core, item

logger = logging.getLogger(__name__)

FACTION_MATERIAL_INDICES = [1, 2, 3, 4, 5, 6]
# 真 ref（badges_report containers 两帧 NestedPrefab 实测同 guid；旧面占位假形常量
# 5bd4e5c9… 已退役——审计 §2 死重定谳，decomp/既档双零命中）
FACTION_BANNER_REF = "Faction_Banner.prefab:0a0897af94ecdcc47b8804c643584320"
FACTION_BANNER_BY_NAME = "Faction_Banner"


@dataclass
class OrnamentsKit:
    """faction ornaments 产物真内存对象（旧 multiclass/ornaments 三布局位内存面）。"""
    report: dict = field(default_factory=dict)   # faction_report.json 内容面
    arrays: dict = field(default_factory=dict)   # faction_meshes.npz 内容面
    textures: dict = field(default_factory=dict)  # textures/ {文件名: PIL}


def _shader_pass_states(stt: dict) -> tuple:
    """[(mc/btf) shader_pass_states 同式] → (name, passes)。

    passes[*].queue（2026-11-01 zbuf-blindspots ②）= SubShader Queue tag 直读
    （engine.subshader_queue 正典单源；supplements kit 面同式）——btf-kit 提取经本函数
    共用同一提取式，注入面 16 材质的 queue 字段由此进报告、进材质态表。缺省 None=
    无 tag（引擎默认 Geometry）。"""
    parsed = stt.get("m_ParsedForm") or {}

    def v(d):
        return (d or {}).get("val")

    passes = []
    for sub in (parsed.get("m_SubShaders") or [])[:4]:
        q = subshader_queue(sub)
        for ps in (sub.get("m_Passes") or [])[:6]:
            state = ps.get("m_State") or {}
            rb = state.get("rtBlend0") or {}
            passes.append({"name": ps.get("m_Name"),
                           "srcBlend": v(rb.get("srcBlend")),
                           "destBlend": v(rb.get("destBlend")),
                           "colMask": v(rb.get("colMask")),
                           "zWrite": v(state.get("zWrite")),
                           "zTest": v(state.get("zTest")),
                           "culling": v(state.get("culling")),
                           "queue": q})
    return parsed.get("m_Name") or stt.get("m_Name"), passes


def _faction_material(r: Resolver, bundle: str, obj, textures: dict) -> dict:
    """单材质全账（icon/banner jobs 共用；落盘 → 内存面）。"""
    mt = obj.read_typetree()
    saved = mt.get("m_SavedProperties") or {}
    sh_ptr = ptr_dict(mt.get("m_Shader") or {})
    sh_name, passes, sh_pid = None, [], sh_ptr.get("m_PathID") or None
    try:
        sobj, _2 = r.resolve_pptr(bundle, sh_ptr, obj)
        sh_name, passes = _shader_pass_states(sobj.read_typetree())
    except Exception:  # noqa: BLE001
        stt_fb = _shader_bundle_typetree(sh_ptr.get("m_PathID"))
        if stt_fb:
            sh_name, passes = _shader_pass_states(stt_fb)
        else:
            sh_pid = None   # shader 序列化不可得：pid 无可证身份，不落假 pid
    texs = {}
    for slot_name, slot in as_pairs(saved.get("m_TexEnvs"), what="m_TexEnvs").items():
        slot = slot or {}
        tp = slot.get("m_Texture") if isinstance(slot, dict) else None
        ent = {"scale": slot.get("m_Scale"), "offset": slot.get("m_Offset")}
        if tp and ptr_dict(tp)["m_PathID"]:
            try:
                tobj, tb = r.resolve_pptr(bundle, ptr_dict(tp), obj)
                tname = tobj.read_typetree().get("m_Name")
                fname = f"{_sanitize(tname)}.png"
                if fname not in textures:
                    textures[fname] = tobj.read().image
                ent["file"] = f"ornaments/textures/{fname}"
            except PPtrError as exc:
                ent["error"] = f"{exc.reason}"
        texs[slot_name] = ent
    return {"name": mt.get("m_Name"), "shader": sh_name, "shader_pid": sh_pid,
            "passes": passes, "textures": texs,
            "colors": {n: as_rgba(v) for n, v in
                       as_pairs(saved.get("m_Colors"), what="m_Colors").items()}}


def _walk_banner(r: Resolver, ctx: _Ctx, froot,
                 arrays: dict, textures: dict, issues: list) -> list[dict]:
    """Faction_Banner prefab walk（badges 同款；根平移置零；报告扁平化）。"""

    def walk(go_obj, parent_acc: np.ndarray, rel: str, depth=0) -> dict:
        if depth > 12:
            return {}
        gt = go_obj.read_typetree()
        name = gt.get("m_Name", "")
        # 节点路径 = GO 名路径（根 GO 名起，无前缀）[mc_extract_assets.py:375-376 逐字]；
        # 消费端按 `split("Faction_Banner/", 1)[-1]` 剥一层前缀定 rel——路径多垫一层即
        # Faction_Icon 挂点失配（asset-supply-fixes 修前实录，findings §根因2）
        my_rel = f"{rel}/{name}" if rel else name
        transform_tt = None
        comps = []
        node: dict = {"path": my_rel, "activeSelf": bool(gt.get("m_IsActive", 1))}
        for pair in gt.get("m_Component") or []:
            cp = pair.get("component") if isinstance(pair, dict) else getattr(pair, "component", None)
            pd = ptr_dict(cp)
            if not pd["m_PathID"]:
                continue
            try:
                cobj, cb = ctx.deref(pd, go_obj)
            except PPtrError:
                continue
            comps.append((cobj.type.name, cobj))
            if cobj.type.name == "Transform":
                transform_tt = cobj.read_typetree()
        own_local = trs_matrix(transform_tt, zero_translation=(depth == 0)) \
            if transform_tt is not None else np.eye(4)
        acc = parent_acc @ own_local
        node["matrix_local_to_root"] = acc.tolist()
        for ctype, cobj in comps:
            ct = cobj.read_typetree()
            if ctype == "MeshFilter":
                mp = ptr_dict(ct.get("m_Mesh") or {})
                if mp.get("m_PathID"):
                    try:
                        mobj, mb = ctx.deref(mp, cobj)
                        arr = _mesh_arrays(mobj)
                        node["mesh_filter"] = {"mesh": {"name": arr["name"]}}
                        # npz 键与节点路径同源 [mc_extract_assets.py:346 逐字]
                        key = f"faction|{my_rel}"
                        arrays[f"{key}/verts"] = arr["verts"]
                        arrays[f"{key}/uv0"] = arr["uv0"]
                        for i, tris in enumerate(arr["submeshes"]):
                            arrays[f"{key}/sub{i}"] = tris
                        arrays[f"{key}/matrix"] = acc.astype(np.float64)
                    except PPtrError:
                        pass
            elif ctype in ("MeshRenderer", "SkinnedMeshRenderer"):
                slots = []
                for i, mp in enumerate(ct.get("m_Materials") or []):
                    pd = ptr_dict(mp)
                    if not pd.get("m_PathID"):
                        continue
                    try:
                        mobj, mb = ctx.deref(pd, cobj)
                        mtt = mobj.read_typetree()
                        mname = mtt.get("m_Name")
                        saved = mtt.get("m_SavedProperties") or {}
                        texs = {}
                        for slot_name, slot in as_pairs(saved.get("m_TexEnvs"),
                                                        what="m_TexEnvs").items():
                            slot = slot or {}
                            tp = slot.get("m_Texture") if isinstance(slot, dict) else None
                            ent = {"scale": slot.get("m_Scale"), "offset": slot.get("m_Offset")}
                            if tp and ptr_dict(tp)["m_PathID"]:
                                try:
                                    tobj, tb = ctx.deref(ptr_dict(tp), mobj)
                                    tname = tobj.read_typetree().get("m_Name")
                                    fname = f"{_sanitize(tname)}.png"
                                    if fname not in textures:
                                        textures[fname] = tobj.read().image
                                    ent["file"] = f"ornaments/textures/{fname}"
                                except PPtrError as exc:
                                    ent["error"] = f"{exc.reason}"
                            texs[slot_name] = ent
                        slots.append({"name": mname, "textures": texs,
                                      "colors": {n: as_rgba(v) for n, v in
                                                 as_pairs(saved.get("m_Colors"),
                                                          what="m_Colors").items()}})
                    except PPtrError:
                        pass
                node["components"] = {"renderer": {"enabled": bool(ct.get("m_Enabled", 1)),
                                                   "material_slots": slots}}
        children = []
        if transform_tt is not None:
            for ch in transform_tt.get("m_Children") or []:
                cpd = ptr_dict(ch)
                if not cpd.get("m_PathID"):
                    continue
                try:
                    tr_obj, _ = ctx.deref(cpd, go_obj)
                    ttt = tr_obj.read_typetree()
                    gop = ptr_dict(ttt.get("m_GameObject") or {})
                    go_child, _2 = ctx.deref(gop, tr_obj)
                    children.append(walk(go_child, acc, my_rel, depth + 1))
                except PPtrError as exc:
                    issues.append(f"{my_rel}: {exc.reason}")
        node["children"] = children
        return node

    roots = [walk(froot, np.eye(4), "")]
    # 扁平化 [mc_extract_assets.py:383 平铺口径]：消费端按顶层一层遍历——嵌套树只剩根
    # 节点可被消费（修后首渲仍 assert 的实录根因）
    flat: list[dict] = []

    def _flatten(n: dict) -> None:
        flat.append(n)
        for ch in n.get("children", []):
            _flatten(ch)

    for _root in roots:
        _flatten(_root)
    return flat


@item("frames", "ornaments_kit")
def ornaments_kit() -> OrnamentsKit:
    """8 派系材质全账 + Faction_Banner walk（report+npz+textures 真内存）。"""
    from eidolon.core.supply import color

    r = core().res
    report: dict = {"prefab": {}, "nodes": [], "faction_materials": {}, "issues": []}
    kit = OrnamentsKit(report=report)

    # ---- 8 派系材质全账 [mc:539-600 同式；v3 probe=平面族表] ----
    probe = color.probe()
    jobs = [("icon", i, probe["factionIconMaterials"][i]) for i in FACTION_MATERIAL_INDICES]
    jobs += [("banner", 1, probe["factionBannerMaterials"][1]),
             ("banner", 4, probe["factionBannerMaterials"][4])]
    for kind, idx, ref in jobs:
        if not ref:
            continue
        res = r.resolve(ref)
        assert res["ok"], (ref, res.get("checks"))
        bundle = res["resolved"]["bundle"]
        obj, _ = r.container_get(bundle, res["resolved"]["guid"])
        report["faction_materials"][f"{kind}_{idx}"] = _faction_material(
            r, bundle, obj, kit.textures)

    # ---- Faction_Banner.prefab walk（badges 同款；guid=containers NestedPrefab 实测）----
    fres = r.resolve(FACTION_BANNER_REF)
    assert fres["ok"], (fres.get("checks"))
    fbundle, fguid = fres["resolved"]["bundle"], fres["resolved"]["guid"]
    ctx = _Ctx(r, fbundle)
    froot, _ = r.container_get(fbundle, fguid)
    report["prefab"] = {"name": FACTION_BANNER_BY_NAME, "ref": f"{FACTION_BANNER_BY_NAME}.prefab:{fguid}",
                        "guid": fguid, "bundle": fbundle}
    report["nodes"] = _walk_banner(r, ctx, froot, kit.arrays, kit.textures, report["issues"])
    logger.debug(f"[faction] nodes={len(report['nodes'])} npz={len(kit.arrays)} "
                 f"mats={len(report['faction_materials'])}")
    return kit
