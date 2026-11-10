"""frames.bacon — Bacon 英雄对局帧 kit（Batch C 首件）。

对照表（旧位 → 本域，预审 2026-10-10）：
  - BACON_HERO_PLAY_REF ← ActorNames.cs:ActorNames.GetPlayActorByTags 内联字面量（GetHeroType==BATTLEGROUNDS_HERO
    路由；:683 BACON_IS_KEL_THUZAD/BACON_PLAYER_RESULTS_HERO_OVERRIDE tag 同指）——
    方法体内联 ldstr 非字段反射不可达（switcher 链根同类），name:guid 链根 + decomp 锚
    维持（探查点①定案）
  - 帧 rig PPtr ← **撤硬编码 {FileID 28, pid}**：根 Mono m_defaultFrame 字段直读
    （CustomHeroFrameBehaviour.cs:CustomHeroFrameBehaviour 字段、:59 InstantiateFrameMesh(m_defaultFrame)；
    探查点②链化）——脚本类识别走 m_Script→m_ClassName（_ability_portrait 的 CardDef 同式）
  - kit 主体 ← extract_hero_play_bacon_kit [asset_extractors:681-696]：spec 内联（旧形态）
    + Batch A 主流程复用；与标准 PLAY_HERO 四差异账见 asset_extractors:637-644
  - 帧 rig 三件 ← _extract_bacon_hero_frame_rig [asset_extractors:699-818 逐字]：
    ①网格数组 extra/frame_rig/* ②材质 _MainTex 纹理 ③rig 账 meta.frame_rig——并入同一
    Kit（对拍 source.ref_from 归一=链化有意变化）
对拍=duipai_frames.py check_bacon；oracle=既档 hero_root/hero_play_bacon_frame。
"""
from __future__ import annotations

import logging
import numpy as np
from UnityPy.helpers.MeshHelper import MeshHandler

from eidolon.core.supply._projection import as_pairs, as_rgba
from eidolon.core.supply.frames.engine import ptr_dict
from eidolon.core.supply.frames.kits import Kit, _extract_kit
from eidolon.core.supply.machine import core, item

logger = logging.getLogger(__name__)

BACON_HERO_PLAY_REF = "Card_Play_Bacon_Hero.prefab:227eb40f91281fa429c48c8a730c982f"
BACON_HERO_RIG_LOCAL_POS = [0.0, 0.1, 0.0]


def _default_frame_ptr(r, bundle: str, root_reader) -> dict:
    """根 GO 组件 m_Script→CustomHeroFrameBehaviour→m_defaultFrame（链化寻址）。
    [CustomHeroFrameBehaviour.cs:CustomHeroFrameBehaviour/59；m_ClassName 识别 CardDef 同式]"""
    for comp in root_reader.read_typetree().get("m_Component", []):
        cobj, _cb = r.resolve_pptr(bundle, ptr_dict(comp["component"]), root_reader)
        if cobj.type.name != "MonoBehaviour":
            continue
        ctree = cobj.read_typetree()
        sp = ptr_dict(ctree.get("m_Script") or {})
        if not sp["m_PathID"]:
            continue
        sobj, _sb = r.resolve_pptr(bundle, sp, cobj)
        if sobj.read_typetree().get("m_ClassName") != "CustomHeroFrameBehaviour":
            continue
        return ptr_dict(ctree["m_defaultFrame"])
    raise AssertionError("根 GO 无 CustomHeroFrameBehaviour（m_defaultFrame 链断）")


def _append_frame_rig(kit: Kit) -> None:
    """帧 rig 三件并入 Kit（prefab 根 Mono m_defaultFrame 外部引用逐字跟随）：
    ①Hero_Mesh_Frame 网格数组 → arrays extra/frame_rig/*；②BaconGenFX_HeroFrame_Hero
    纹理 → textures；③rig 账 → meta.frame_rig（源/材质/局部位）。
    [asset_extractors:699-818 逐字；落盘 → Kit 内存面]"""
    r = core().res
    res = r.resolve(BACON_HERO_PLAY_REF)
    assert res["ok"], res.get("checks")
    bundle = res["resolved"]["bundle"]
    root_reader, _ = r.container_get(bundle, res["resolved"]["guid"])
    rig_reader, rig_bundle = r.resolve_pptr(bundle, _default_frame_ptr(r, bundle, root_reader),
                                            root_reader)
    assert rig_reader is not None and rig_reader.type.name == "GameObject", rig_reader
    rig_tt = rig_reader.read_typetree()
    rig_name = rig_tt.get("m_Name")

    # rig 子树（根恒等，单子 GenFX_Portrait_Hero 载 MeshFilter/Renderer——根自底向上累计）
    def _trs(t):
        p, q, s = t["m_LocalPosition"], t["m_LocalRotation"], t["m_LocalScale"]
        return {"pos": [p["x"], p["y"], p["z"]], "rot": [q["x"], q["y"], q["z"], q["w"]],
                "scale": [s["x"], s["y"], s["z"]]}

    locals_chain: list[dict] = []
    mesh_info = mat_info = None

    def _walk_rig(go_reader, go_bundle: str, go_tt: dict) -> None:
        transform = None
        nonlocal mesh_info, mat_info
        for comp in go_tt.get("m_Component", []):
            cr, _cb = r.resolve_pptr(go_bundle, ptr_dict(comp["component"]), go_reader)
            ctype = cr.type.name
            ctree = cr.read_typetree()
            if ctype == "Transform":
                transform = (cr, ctree)
                locals_chain.append(_trs(ctree))
            elif ctype == "MeshFilter":
                mp = ptr_dict(ctree.get("m_Mesh") or {})
                mobj, mb = r.resolve_pptr(go_bundle, mp, cr)
                mesh_info = (mobj, mb)
            elif ctype == "MeshRenderer":
                mp = ctree["m_Materials"][0]
                mobj, mb = r.resolve_pptr(go_bundle, mp, cr)
                mat_info = (mobj.read_typetree(), mb, mobj.path_id)
        assert transform is not None, "rig 节点缺 Transform"
        for ch in transform[1].get("m_Children", []):
            tr_obj, _ = r.resolve_pptr(go_bundle, ptr_dict(ch), transform[0])
            tr_tt = tr_obj.read_typetree()
            gop = ptr_dict(tr_tt.get("m_GameObject") or {})
            go_child, child_bundle = r.resolve_pptr(go_bundle, gop, tr_obj)
            _walk_rig(go_child, child_bundle, go_child.read_typetree())

    _walk_rig(rig_reader, rig_bundle, rig_tt)
    assert mesh_info is not None and mat_info is not None, "rig 缺 MeshFilter/Renderer"
    mesh_obj, mesh_bundle = mesh_info

    # ① 网格数组
    h = MeshHandler(mesh_obj.read())
    h.process()
    arrays: dict[str, np.ndarray] = {}
    verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
    uv0 = np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0 else np.zeros((len(verts), 2))
    arrays["extra/frame_rig/verts"] = verts
    arrays["extra/frame_rig/uv0"] = uv0
    if h.m_UV1:
        arrays["extra/frame_rig/uv1"] = np.array(h.m_UV1, dtype=np.float64).reshape(-1, 2)
    for i, tris in enumerate(h.get_triangles()):
        arrays[f"extra/frame_rig/sub{i}"] = np.array([t for t in tris if len(t) == 3], dtype=np.int32)

    # ② 材质 _MainTex 纹理
    mt, mat_bundle, mat_pid = mat_info
    saved = mt.get("m_SavedProperties", {})
    main_tex_slot = None
    for first, sec in as_pairs(saved.get("m_TexEnvs"), what="m_TexEnvs").items():
        if first == "_MainTex":
            main_tex_slot = sec or {}
            break
    tptr = ptr_dict((main_tex_slot or {}).get("m_Texture") or {})
    t_obj, t_bundle = r.resolve_pptr(mat_bundle, tptr, None)
    t_tt = t_obj.read_typetree()
    tex_name = t_tt.get("m_Name")
    fname = f"{tex_name}.png"
    if fname not in kit.textures:
        kit.textures[fname] = t_obj.read().image

    # ③ meta.frame_rig（世界矩阵留 compile 期合成：宿主 Mesh 节点 world × T(0,0.1,0)）
    kit.meta["frame_rig"] = {
        "source": {"go": rig_name, "bundle": rig_bundle, "path_id": rig_reader.path_id,
                   "ref_from": f"{BACON_HERO_PLAY_REF} 根 Mono m_defaultFrame 字段直读"
                               f"（链化：CustomHeroFrameBehaviour.cs:CustomHeroFrameBehaviour.UpdateFrame）",
                   "engine": "CustomHeroFrameBehaviour.UpdateFrame/InstantiateFrameMesh "
                             "(CustomHeroFrameBehaviour.cs:CustomHeroFrameBehaviour)"},
        "host_local_pos": BACON_HERO_RIG_LOCAL_POS,
        "rig_locals": locals_chain,
        "mesh": {"name": mesh_obj.read_typetree().get("m_Name"), "bundle": mesh_bundle,
                 "path_id": mesh_obj.path_id, "verts": len(verts),
                 "submesh_tris": [len(a) for k, a in arrays.items() if k.endswith("/sub0")],
                 "npz_key": "extra/frame_rig"},
        "material": {"name": mt.get("m_Name"), "bundle": mat_bundle, "path_id": mat_pid,
                     "shader_path_id": (mt.get("m_Shader") or {}).get("m_PathID"),
                     "main_tex": {"name": tex_name, "file": fname,
                                  "bundle": t_bundle, "path_id": t_obj.path_id},
                     "shader_semantics": "PS o0=tex(_MainTex@uv0,mipbias)×vCOLOR（bhn_frame_shader_n2.asm）；"
                                         "pass colMask15/One/Zero opaque zWrite1 cullingOff（无 _Color 槽，"
                                         "序列化 _Color 惰性——tint 正典=shader 消费色）；网格无 m_Colors 流"
                                         "→vCOLOR=白=恒等",
                     "floats": as_pairs(saved.get("m_Floats"), what="m_Floats"),
                     "colors": {f: as_rgba(s) for f, s in
                                as_pairs(saved.get("m_Colors"), what="m_Colors").items()}},
    }
    kit.arrays.update(arrays)
    logger.debug(f"[kit/rig] {rig_name}: verts={len(verts)} tex={tex_name} -> {kit.frame_dir}")


@item("frames", "bacon_kit")
def bacon_kit() -> Kit:
    """Bacon 对局帧 kit（五面 + 帧 rig 三件一体；与 hero_play 四差异账见模块 docstring）。"""
    from eidolon.core.supply import color

    spec = dict(slot=None, dbf="132578", uv1="uv0copy", color0=True, root="full",
                extra_meshes=False, races=False, report="prefab_report.json",
                ubertext="prefab_ubertext.json", frame_dir="hero_play_bacon_frame",
                family=None, sample_ct=None, actor_ref=BACON_HERO_PLAY_REF)
    kit = _extract_kit(spec, color.probe())
    _append_frame_rig(kit)
    return kit
