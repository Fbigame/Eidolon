"""frames.supplements — kit 派生件三配方（ta 补 npz/portrait uv1/material state，Batch C）。

对照表（旧位 → 本域，预审 2026-10-10）：
  - ta_supplement ← extract_ta_supplement [asset_extractors:2387-2448 逐字]：五帧 desc
    网格全通道重提（_find_desc_components 结构路径寻节点）+ kit npz 对齐断言 +
    ability school 变体（mesh pid 走 kit report actor refs——v3=AbilityKit.report 同形）。
    消费前缀表（ability_neutral/ally_desc/weapon_desc/location_desc/hero_hand/
    ability_school）=ur_frames array_prefix 消费端映射，逐字保留。
    prefab ref=tables.actor_slots 活表直取（2026-10-10 audit 升级账，_DM_SLOTS 路由）。
  - portrait_uv1 ← extract_portrait_uv1 [asset_extractors:2571-2625 逐字]：双目标网格
    + UV1_TARGETS submesh 数断言 + PortraitFrame_mesh 对齐断言；**uv1 缺通道 zeros
    填充**（本配方语义）。v3 链化（2026-10-10）：网格取用=Kit.mesh_refs 结构引用，
    bundle 名+网格名双名字扫描退役（audit §3.4#1）。
  - material_state ← extract_material_state [asset_extractors:2749-2855 逐字]：8 kit
    renderers[0] 材质收集→shader m_ParsedForm passes 全量→按材质名合并（零冲突断言）
    + badges 材质并表（colMask=15 pass 断言）〔7→8：ally_premium 帧入表，mechorse-golden
    2026-10-21——premium 材质 cull/blend 真值位〕。
  - 共享帮手：_key_walk/_mesh_channels/_find_desc_components/DM_PREFABS/DESC_PATHS_TA
    [ta_extract_watermarks 同源逐字]；**_mesh_channels uv1 缺通道=uv0 回填**
    （sc-hero-furniture 正典：引擎缺 UV1 网格有效 TEXCOORD1=uv0；与 uv1 配方的 zeros
    填充是两个有意的不同语义，互不合并）。_SHADER_BUNDLES 自 .badges 引用（同源常量）。
  - kit 输入：旧=七 kit 目录落盘读（_kits_map），v3=Kit/AbilityKit 内存面（同会话 memo
    单实例）；material_state 徽章输入=badges_kit().report。
对拍=duipai_frames.py check_supplements（ta/uv1 npz 逐键逐位；material_state 逐字段，
_meta.extraction 归一=收编账）。
"""
from __future__ import annotations

import logging
import numpy as np

from eidolon.core.infra.context import current   # 契约 D：Data/Win=ctx 流入
from eidolon.core.infra.resolve_asset_ref import Resolver
from eidolon.core.supply._projection import as_pairs
from eidolon.core.supply.frames.badges import _SHADER_BUNDLES
from eidolon.core.supply.frames.engine import _iter_sf, ptr_dict, subshader_queue as _subshader_queue
from eidolon.core.supply.machine import core, item

logger = logging.getLogger(__name__)

_DM_SLOTS = {                         # 活表槽路由（decomp 锚：ActorNames.cs:ActorNames/52/56/60/68）
    "ability": "HAND_SPELL",
    "ally": "HAND_MINION",
    "ally_premium": "HAND_MINION",    # 金卡档走 premium 表（mechorse-golden 2026-10-21）
    "weapon": "HAND_WEAPON",
    "hero_hand": "HAND_HERO",
    "location": "HAND_LOCATION",
}
DESC_PATHS_TA = {
    "ability": "Card_Hand_Ability/RootObject/NonQuestObjects/Mesh/Description_mesh",
    "ally": "Card_Hand_Ally/RootObject/Mesh/Description_mesh",
    "ally_premium": "Card_Hand_Ally_Premium/RootObject/Mesh/Description_mesh",
    "weapon": "Card_Hand_Weapon/RootObject/Mesh/Description_mesh",
    "location": "Card_Hand_Location/RootObject/Mesh/Description_mesh",
    "hero_hand": "Card_Hand_Hero/RootObject/Mesh/Description_mesh",
}
UV1_TARGETS = {
    "Card_InHand_Ally_Portrait_mesh": [19, 389],      # [pc:37-40]
    "Card_InHand_Ability_Portrait_mesh": [132, 10],
    # 金法术（golden 98918 2026-11-04）：premium 肖像网格（prefab dump 实测
    # subs=[132,10]——与 ability 同形：sub0 肖像 quad 132 tri + sub1 框缘 10 tri；
    # 序列化 uv1≠uv0，sub0 uv1∈[0.21,0.78]×[0.45,0.91] 指 BannerAtlas 单元内。
    # 缺行=uv1 走 uv0 兜底 → _SecondTex 跨格采样印格子鬼影（z_art 71.7 主因）。
    "Card_InHand_Ability_Premium_Portrait_Mesh": [132, 10],
    # 金卡档（mechorse-golden 2026-10-21）：premium 肖像网格（prefab dump 实测
    # subs=[19,1258]——sub0 肖像 quad 与 ally 同 19 tri，sub1 金框 1258 tri）。
    "Card_InHand_Ally_Portrait_Premium_mesh": [19, 1258],
}

# 材质态表（material_state）遍历的帧族 kit 集合。**新增帧族 kit 必须入表**——
# 不入表 = 该族材质没有状态行，门内 `zbuf_no_row` 红（fail loud，禁缺省猜）。
MATERIAL_STATE_KITS: tuple[str, ...] = (
    "ability", "ability_premium", "ally", "ally_premium", "weapon",
    "heropower", "location",
    "hero_hand", "hero_play",
    # bacon 英雄 play 帧：`Card_Play_Bacon_Hero`（render/scenes/specs 里 kit="bacon"）。
    # 该 kit 的 spec 内联在 bacon.py、未入 FRAME_SPECS，故走 bacon_kit() 特源；
    # 其帧 rig 材质（Bacon_HeroFrame_Default 经 CustomHeroFrameBehaviour.m_defaultFrame
    # 的 nested prefab）不进 hierarchy 走查面，由 _append_frame_rig 的 meta.frame_rig 直读。
    "bacon",
    # ct44 饰品帧（bg-ct40-43-44-routing 2026-10-24）：trinket kit 材质入表——
    # 章环影 Anomalies_Atlas_Shadow_Mat（Hero/Multiply/Multiply）等缺行材质的
    # blend/cull/zWrite 真值面（缺行→opaque 缺省会画错影盘）。
    "trinket",
    # ct43 畸变帧（bg-ct40-43-44-routing 2026-10-24）：anomaly kit 材质入表——帧主体=
    # ability 族同 pid 材质（ability 行已覆盖），增量=Card_Inhand_Ability_Anomaly 主纹理/
    # Card_Hand_BG_Quest_Text_Tray_Mat/BaconFX_Anomaly_CardGlow_Backer 等。
    "anomaly",
)


def _dm_prefabs() -> dict[str, str]:
    """ta 派生件五 prefab ref：tables.actor_slots 活表直取（audit §2 升级账 2026-10-10；
    旧 DM_PREFABS 字面量与活表槽值逐字符同源——decomp ActorNames.cs:ActorNames 实证+
    ta 对拍 kit npz 对齐断言运行时双证）。ally_premium=premium 表直取
    （s_premiumActorAssets HAND_MINION，mechorse-golden 2026-10-21）。"""
    from eidolon.core.infra.dll_reflect import tables

    out = {}
    for f, s in _DM_SLOTS.items():
        tbl = tables.premium_actors if f == "ally_premium" else tables.actor_slots
        out[f] = tbl[s]
    return out


def _kit(frame: str, light: bool = False):
    """派生件的 kit 输入（ability/ability_premium=AbilityKit，余=Kit；同会话 memo 单实例）。
    light=True 走 kit_light 域项（批2b-1：只到 hierarchy，不 deref 纹理）。"""
    if frame in ("ability", "ability_premium"):
        from eidolon.core.supply.frames.ability import ability_kit
        return ability_kit("premium" if frame == "ability_premium" else "normal")
    from eidolon.core.supply.frames import kits
    return kits.kit_light(frame) if light else kits.kit(frame)


def _kit_hierarchy(frame: str, light: bool = False) -> dict:
    k = _kit(frame, light=light)
    return k.recon_meta["hierarchy"] if frame in ("ability", "ability_premium") \
        else k.meta["hierarchy"]


def _key_walk(node, key="root", path=""):
    """[ta_extract_watermarks.key_walk 逐字]"""
    p = f"{path}/{node['name']}" if path else node["name"]
    yield node, key, p
    for i, c in enumerate(node["children"]):
        yield from _key_walk(c, f"{key}.{i}", p)


def _npz_key_for_path(frame: str, desc_path: str) -> str | None:
    """[ta_extract_watermarks.npz_key_for_path；recon_dir 读 → kit 内存面]"""
    for n, key, p in _key_walk(_kit_hierarchy(frame)):
        if p == desc_path:
            return key
    return None


def _mesh_channels(mesh_obj) -> dict:
    """[ta_extract_watermarks.mesh_channels 逐字]
    2026-10-07 sc-hero-furniture：网格缺 UV1 通道时 uv1:=uv0 回填（原 np.zeros）——
    引擎（Unity 6000.3.11f1）对缺 UV1 网格的有效 TEXCOORD1=uv0（经验判式非序列化语义，
    hero desc 网格 HeroCard_InHand_Description 实证；49 张英雄参照零反例）。零填充使
    采样 clamp 到纹理透明角=水印整层视觉 no-op（毒数据，112815 SC 戳记缺失案）。"""
    from UnityPy.helpers.MeshHelper import MeshHandler
    h = MeshHandler(mesh_obj)
    h.process()
    verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
    uv0 = (np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2)
           if h.m_UV0 else np.zeros((len(verts), 2)))
    uv1 = (np.array(h.m_UV1, dtype=np.float64).reshape(-1, 2)
           if h.m_UV1 else uv0.copy())
    color0 = (np.array(h.m_Colors, dtype=np.float64).reshape(-1, 4)
              if h.m_Colors else np.ones((len(verts), 4)))
    subs = [np.array([t for t in sub if len(t) == 3], dtype=np.int64)
            for sub in h.get_triangles()]
    return {"verts": verts, "uv0": uv0, "uv1": uv1, "color0": color0, "subs": subs,
            "name": mesh_obj.m_Name}


def _find_desc_components(r: Resolver, prefab_ref: str, desc_path: str) -> dict:
    """[ta_extract_watermarks.find_desc_components 逐字]"""
    res = r.resolve(prefab_ref)
    assert res["ok"], f"prefab 解析失败 {prefab_ref}"
    bundle = res["resolved"]["bundle"]
    obj, _ = r.container_get(bundle, res["resolved"]["guid"])
    go = obj.read_typetree()
    found = {}

    def comps_of(go_tree):
        out = []
        for e in go_tree.get("m_Component") or []:
            c = e.get("component") if isinstance(e, dict) and "component" in e else e
            pd = {"m_PathID": c.get("m_PathID") if isinstance(c, dict) else c.path_id,
                  "m_FileID": c.get("m_FileID", 0) if isinstance(c, dict) else 0}
            out.append(pd)
        return out

    def walk(go_reader, path, depth=0):
        if depth > 16 or "mesh_filter" in found:
            return
        g = go_reader.read_typetree()
        name = g.get("m_Name", "")
        p = f"{path}/{name}" if path else name
        tf_reader, mf_ptr, mats = None, None, []
        for pd in comps_of(g):
            try:
                cr, _cb = r.resolve_pptr(bundle, pd, go_reader)
            except Exception:  # noqa: BLE001
                continue
            if cr.type.name == "Transform":
                tf_reader = cr
            elif cr.type.name == "MeshFilter" and p == desc_path:
                mf_ptr = cr.read_typetree().get("m_Mesh")
            elif cr.type.name == "MeshRenderer" and p == desc_path:
                for mptr in cr.read_typetree().get("m_Materials", []):
                    try:
                        mr, mb = r.resolve_pptr(bundle, mptr, cr)
                    except Exception as exc:  # noqa: BLE001
                        mats.append({"error": str(exc)})
                        continue
                    mt = mr.read_typetree()
                    mats.append({
                        "material": mt.get("m_Name"),
                        "shader_pid": (mt.get("m_Shader") or {}).get("m_PathID"),
                        "m_Floats": mt.get("m_SavedProperties", {}).get("m_Floats"),
                        # 形态解包走唯一出口（2026-11-03 G2 收编：旧 (e[0], e[1]) 只认列表对，
                        # typetree 字典形态 KeyError 炸提取期——as_pairs 两形态都收、未知 raise）
                        "m_Colors": as_pairs(
                            mt.get("m_SavedProperties", {}).get("m_Colors"),
                            what="desc_components m_Colors"),
                    })
        if p == desc_path:
            found["mesh_filter"] = mf_ptr
            found["materials"] = mats
            found["bundle"] = bundle
        if tf_reader is not None:
            tf = tf_reader.read_typetree()
            for cp in comps_of({"m_Component": tf.get("m_Children")}):
                try:
                    cr, _cb = r.resolve_pptr(bundle, cp, tf_reader)
                except Exception:  # noqa: BLE001
                    continue
                if cr.type.name != "Transform":
                    continue
                try:
                    cgo_tree = cr.read_typetree()
                    gop = cgo_tree.get("m_GameObject") or {}
                    cgo, _cb2 = r.resolve_pptr(bundle, {"m_PathID": gop.get("m_PathID"),
                                                        "m_FileID": 0}, cr)
                except Exception:  # noqa: BLE001
                    continue
                if cgo.type.name == "GameObject":
                    walk(cgo, p, depth + 1)

    walk(obj, "")
    assert found.get("mesh_filter"), f"{prefab_ref}: desc 节点 {desc_path} 未找到 MeshFilter"
    return found


@item("frames", "ta_supplement")
def ta_supplement() -> dict[str, np.ndarray]:
    """mesh_uv1_supplement 内容面 [extract_ta_supplement 逐字；五帧 desc 全通道+
    ability school 变体]。"""
    r = core().res
    npz_out: dict[str, np.ndarray] = {}
    dm = _dm_prefabs()
    for frame in ("ability", "ally", "ally_premium", "weapon", "location", "hero_hand"):
        node = _find_desc_components(r, dm[frame], DESC_PATHS_TA[frame])
        mf = node["mesh_filter"]
        m_reader, m_bundle = r.resolve_pptr(node["bundle"], mf, None)
        assert m_reader.type.name == "Mesh", f"{frame}: MeshFilter → {m_reader.type.name}"
        ch = _mesh_channels(m_reader.read())
        k = _kit(frame)
        key = _npz_key_for_path(frame, DESC_PATHS_TA[frame])
        assert key, f"{frame}: kit npz 无 {DESC_PATHS_TA[frame]}"
        z = k.arrays
        assert np.allclose(z[f"{key}/verts"], ch["verts"]) and np.allclose(z[f"{key}/uv0"], ch["uv0"]), \
            f"{frame}: 顶点序与 kit npz 不对齐"
        pre = {"ability": "ability_neutral", "ally": "ally_desc",
               "ally_premium": "ally_premium_desc", "weapon": "weapon_desc",
               "location": "location_desc", "hero_hand": "hero_hand"}[frame]
        npz_out[f"{pre}/verts"] = ch["verts"]
        npz_out[f"{pre}/uv0"] = ch["uv0"]
        npz_out[f"{pre}/uv1"] = ch["uv1"]
        npz_out[f"{pre}/color0"] = ch["color0"]
        for i, s in enumerate(ch["subs"]):
            npz_out[f"{pre}/sub{i}"] = s

    # ability school 变体（pid 来自 kit report actor refs——v3=AbilityKit.report 同形）
    ak = _kit("ability")
    school_ref = ak.report["actor_components"][0]["object_refs"]["m_spellDescriptionMeshSchool"]
    env = r.open_bundle(school_ref["bundle"])
    mobj = None
    for o in env.objects:
        if o.type.name == "Mesh" and o.path_id == school_ref["path_id"]:
            mobj = o
            break
    assert mobj is not None, f"school mesh pid {school_ref['path_id']} 未找到"
    chs = _mesh_channels(mobj.read())
    z = ak.arrays
    key_ok = None
    if "extra/school_desc/verts" in z:
        key_ok = bool(np.allclose(z["extra/school_desc/verts"], chs["verts"]))
    assert key_ok, "school mesh 顶点序与 kit extra/school_desc 不对齐"
    npz_out.update({"ability_school/verts": chs["verts"], "ability_school/uv0": chs["uv0"],
                    "ability_school/uv1": chs["uv1"], "ability_school/color0": chs["color0"]})
    for i, s in enumerate(chs["subs"]):
        npz_out[f"ability_school/sub{i}"] = s
    logger.debug(f"[ta] npz {len(npz_out)} arrays（内存面）")
    return npz_out


def _mesh_by_ref(r: Resolver, bundle: str, path_id: int) -> dict:
    """(bundle,pid) 结构引用取网格全通道（uv1 缺通道 zeros 填充=本配方语义，与
    _mesh_channels 的 uv0 回填有意不同）。[原 _extract_uv1_mesh 通道段逐字]"""
    from UnityPy.helpers.MeshHelper import MeshHandler

    obj = None
    for sf in _iter_sf(r.open_bundle(bundle)):
        if path_id in sf.objects:
            obj = sf.objects[path_id]
            break
    assert obj is not None and obj.type.name == "Mesh", (bundle, path_id)
    t = obj.read()
    h = MeshHandler(t)
    h.process()
    verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
    uv0 = (np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2)
           if h.m_UV0 else np.zeros((len(verts), 2)))
    uv1 = (np.array(h.m_UV1, dtype=np.float64).reshape(-1, 2)
           if h.m_UV1 else np.zeros((len(verts), 2)))
    color0 = (np.array(h.m_Colors, dtype=np.float64).reshape(-1, 4)
              if h.m_Colors else np.ones((len(verts), 4)))
    subs = [np.array([x for x in sub if len(x) == 3], dtype=np.int64)
            for sub in h.get_triangles()]
    return {"path_id": obj.path_id, "verts": verts, "uv0": uv0, "uv1": uv1,
            "color0": color0, "subs": subs}


@item("frames", "portrait_uv1")
def portrait_uv1() -> dict[str, dict[str, np.ndarray]]:
    """portrait_uv1 双网格全通道 [extract_portrait_uv1 逐字；锚=kit 内存面]。
    v3 链化（2026-10-10 audit §3.4#1）：网格取用=kit 层级走查的结构引用
    （Kit.mesh_refs：MeshFilter PPtr 现场解的 bundle+pid）——UV1_MESH_BUNDLE bundle 名
    +网格名双名字扫描退役；名字仅存 refs 键与断言链（漂移→KeyError/StopIteration=
    fail loud），对齐断言保留为监视。"""
    r = core().res
    recon_map = {"Card_InHand_Ability_Portrait_mesh": "ability",
                 "Card_InHand_Ability_Premium_Portrait_Mesh": "ability_premium",
                 "Card_InHand_Ally_Portrait_mesh": "ally",
                 "Card_InHand_Ally_Portrait_Premium_mesh": "ally_premium"}
    out: dict[str, dict[str, np.ndarray]] = {}
    for name, want_subs in UV1_TARGETS.items():
        frame = recon_map[name]
        k = _kit(frame)
        bundle, pid = k.mesh_refs[name]   # 名字漂移→KeyError=fail loud
        m = _mesh_by_ref(r, bundle, pid)
        assert len(m["subs"]) == len(want_subs), (name, [len(s) for s in m["subs"]])
        got_subs = [len(s) for s in m["subs"]]
        stats = next(n["mesh_stats"] for n, _, _ in _key_walk(_kit_hierarchy(frame))
                     if n.get("mesh_stats") and n["mesh_stats"].get("name") == name)
        assert stats["verts"] == len(m["verts"]), (name, stats["verts"], len(m["verts"]))
        assert stats["submesh_tris"] == got_subs, (name, stats["submesh_tris"], got_subs)
        pf_key = next(key for n, key, _ in _key_walk(_kit_hierarchy(frame))
                      if n.get("name") == "PortraitFrame_mesh")
        z = k.arrays
        assert np.allclose(z[f"{pf_key}/uv0"], m["uv0"]), f"{name} uv0 与帧 npz 不一致"
        assert np.allclose(z[f"{pf_key}/verts"], m["verts"]), f"{name} verts 与帧 npz 不一致"
        out[name] = {"verts": m["verts"], "uv0": m["uv0"], "uv1": m["uv1"],
                     "color0": m["color0"], "sub0": m["subs"][0],
                     "sub1": m["subs"][1] if len(m["subs"]) > 1 else np.zeros((0, 3), np.int64)}
    logger.debug(f"[uv1] {len(UV1_TARGETS)} meshes（内存面，refs 链化）")
    return out


@item("frames", "material_state")
def material_state() -> dict:
    """material_state_merged 内容面 [extract_material_state 逐字；kit 清单 + badge 报告并入，
    共享键零冲突校验沿用五源合并纪律]。

    `passes[*].queue`（2026-10-31 zbuf-table-driven）= SubShader Queue tag 直读，透明队列
    件的直接判据；徽章来源行无该字段（None），消费方回落 zWrite 判据。

    帧族范围=模块常量 `MATERIAL_STATE_KITS`（新增帧族 kit 必须入表，否则该族材质无
    状态行，门 `zbuf_no_row` 红）。"""
    mats_by_pid: dict = {}
    for frame in MATERIAL_STATE_KITS:
        rig_mats: list[dict] = []
        if frame == "bacon":
            # bacon 特源：spec 内联在 bacon.py:163（未入 FRAME_SPECS，scenes 侧同注），
            # 故不走 _kit_hierarchy 的 FRAME_SPECS 分派，直接调 bacon_kit()。
            from eidolon.core.supply.frames.bacon import bacon_kit
            bk = bacon_kit()
            hier = bk.meta["hierarchy"]
            # 帧 rig 材质是 **nested prefab**（Bacon_HeroFrame_Default，走
            # CustomHeroFrameBehaviour.m_defaultFrame 外部引用）——不进 hierarchy 走查，
            # 只有 meta.frame_rig.material 直读面（bacon.py:_append_frame_rig 已解）。
            rm = (bk.meta.get("frame_rig") or {}).get("material") or {}
            if rm.get("path_id") is not None:
                rig_mats.append({"name": rm.get("name"), "bundle": rm.get("bundle"),
                                 "path_id": rm["path_id"]})
        else:
            hier = _kit_hierarchy(frame, light=(frame != "ability"))   # 批2b-1：Kit 帧走轻量（ability 无轻路，本就 ~5s）

        def walk(n):
            rr = n.get("renderers") or []
            if rr:
                for m in rr[0].get("materials", []):
                    if m and m.get("path_id") is not None:
                        mats_by_pid.setdefault(m["path_id"], {"name": m["name"], "bundle": m["bundle"]})
            for c in n.get("children", []):
                walk(c)

        walk(hier)
        for m in rig_mats:
            mats_by_pid.setdefault(m["path_id"], {"name": m["name"], "bundle": m["bundle"]})
    by_bundle: dict = {}
    for pid, m in mats_by_pid.items():
        by_bundle.setdefault(m["bundle"], []).append(pid)
    shader_of = {}
    data_win = current().data_win
    from eidolon.core.infra import bundle_guard
    for bundle, pids in by_bundle.items():
        env = bundle_guard.load_defended(data_win / bundle)   # 坏盘读防护收口（2026-11-08）
        for obj in env.objects:
            if obj.path_id in pids:
                tt = obj.read_typetree()
                sh = tt.get("m_Shader", {}) or {}
                shader_of[obj.path_id] = {"shader_pid": sh.get("m_PathID"),
                                          "mat_name": tt.get("m_Name")}
    shaders = {}
    shader_envs = [bundle_guard.load_defended(data_win / p)    # 双包合扫（原 UnityPy.load 多路
                   for p in _SHADER_BUNDLES]                   # 单 env 等价拆分：逐 env 链式遍历）
    want = {v["shader_pid"] for v in shader_of.values() if v.get("shader_pid")}
    for obj in [o for e in shader_envs for o in e.objects]:
        if obj.type.name != "Shader" or obj.path_id not in want:
            continue
        tt = obj.read_typetree()
        tt = obj.read_typetree()
        parsed = tt.get("m_ParsedForm") or {}
        passes = []
        for si, sub in enumerate(parsed.get("m_SubShaders", [])):
            # 渲染队列 tag（2026-10-31 zbuf-table-driven）：ShaderLab Queue 的序列化位
            # = m_SubShaders[i].m_Tags.tags 里键名大写 "QUEUE" 的二元组（"Transparent"/
            # "Geometry"/数值串）。缺省无 tag=引擎默认 Geometry。此字段是「透明队列件」
            # 的直接判据（优先于 zWrite 推导）；badge 来源行无此字段（None=未知，消费方
            # 回落 zWrite 判据，见 raster.primary_queue）。
            q = _subshader_queue(sub)
            for pi, ps in enumerate(sub.get("m_Passes", [])):
                st = ps.get("m_State", {})
                rb0 = (st.get("rtBlend0") or {})
                passes.append({
                    "subshader": si, "pass": pi,
                    "culling": (st.get("culling") or {}).get("val"),
                    "zWrite": (st.get("zWrite") or {}).get("val"),
                    "zTest": (st.get("zTest") or {}).get("val"),
                    "srcBlend": (rb0.get("srcBlend") or {}).get("val"),
                    "destBlend": (rb0.get("destBlend") or {}).get("val"),
                    "colMask": (rb0.get("colMask") or {}).get("val"),
                    "queue": q,
                    "tags": ps.get("m_Tags"),
                })
        # shader 身份名（2026-11-01 material-state-shader-name）：m_ParsedForm.m_Name
        # 优先、顶层 m_Name 回落（engine.Recon._shader_name 同式）——部分 shader 序列化
        # 顶层名为空串（真名只在 m_ParsedForm，如 Hero/Multiply/Multiply 族），只取顶层
        # 会让这些行的 shader_name 空串、multiply_form 第二路判据失明。
        shaders[obj.path_id] = {
            "m_Name": ((tt.get("m_ParsedForm") or {}).get("m_Name")
                       or tt.get("m_Name") or None),
            "passes": passes}

    table_mats: dict = {}
    prov: dict = {}
    for pid, info in shader_of.items():
        spid = info.get("shader_pid")
        sh = shaders.get(spid)
        nm = info["mat_name"]
        row = {"mat_pid": pid, "shader_pid": spid,
               "shader_name": (sh or {}).get("m_Name"),
               "passes": (sh or {}).get("passes")}
        if nm in table_mats and table_mats[nm]["passes"] != row["passes"]:
            raise AssertionError(f"材质态共享键冲突 {nm}")
        table_mats[nm] = row
        prov[nm] = "kit-recon shader dump（ef_dump_cull_all 同式）"

    from eidolon.core.supply.frames.badges import badges_kit
    report = badges_kit().report
    for bk, b in report["badges"].items():
        for n in b["nodes"]:
            rr = n["components"].get("renderer")
            if not rr:
                continue
            for m in rr.get("material_slots", []):
                name, sh = m.get("name"), m.get("shader") or {}
                if not name or sh.get("error") or not sh.get("passes"):
                    continue
                st = None
                for p in sh["passes"]:
                    if p.get("colMask") == 15.0:
                        st = {k: p.get(k) for k in ("culling", "zWrite", "srcBlend", "destBlend", "colMask")}
                        break
                assert st is not None, (bk, name, "无 colMask=15 pass")
                if name in table_mats:
                    continue
                # shader_pid（2026-11-01 zbuf-blindspots ③）：badge 报告 shader_info
                # 增补的 pid 直通——badge 族行自此有 shader 身份，queue 经 passes 进表
                # （此前 badge 行 shader_pid=None、queue 恒缺，延期判据只能靠 zWrite 兜底）。
                table_mats[name] = {"mat_pid": m.get("path_id"), "shader_pid": sh.get("pid"),
                                    "shader_name": sh.get("name"), "passes": sh["passes"]}
                prov[name] = "badge-trio(bt_extract_badges 同式)"

    # ---- 注入面报告并入（2026-11-01 zbuf-blindspots ②，通用形态）----
    # btf-kit / faction-ornaments 两报告的材质账**通用读入**（此前这 16 件在
    # raster.ZBUF_STATE_KNOWN_GAPS 逐名冻结——「缺口已记账待补」态）。行构造与 kit
    # 面同构（passes 直读报告；queue 字段随 ornaments._shader_pass_states/
    # engine.subshader_queue 进报告），共享键冲突校验沿用五源合并纪律。
    # **culling/srcBlend/destBlend 三列暂缓并入**（A/B 归因 2026-11-01）：
    #   * culling——cull=True 链消费注入面行的 CullMode=Back 后，5 张 BG/任务卡
    #     盾徽/金币区对 oracle 全面变差（上轮「+0.001~+0.009 微退」同成因；
    #     changed=228~245 → 剥离后 changed=0 bit-identical）；
    #   * srcBlend/destBlend——blend_from_table 链（trinket）消费注入面行的
    #     (1,0)=opaque 后，Gem_Mana_Coin 软边 167 px 变差（116510/116614_bg
    #     z_cost +0.0033 门红）；剥离后 blend_mode_of 回落 "alpha"=并表前同象。
    #   注入面网格的剔除/混合消费与引擎实测不符，归因（widing/双向壳/负缩放翻转、
    #   AlphaMaskScroller 软边）另立卡。行内缺键=对应 primary_* 返 None/回落，
    #   与并表前行为逐位同。zWrite/queue 列正常并入（icon 延期 6 卡 6/6 改善，
    #   5 张 BG/任务卡 bit-identical）。
    # **无主色 pass 的材质不并**（如 GenFX_FlareStarGold：shader 序列化不可得 "?"）
    # ——表契约=主色 pass 决定源，无数据行只会产出 no_primary_pass 缺口；该件留
    # KNOWN_GAPS 记账（冻结集只许缩）。
    from eidolon.core.supply.frames.btf import btf_kit as _btf_kit
    from eidolon.core.supply.frames.ornaments import ornaments_kit as _orn_kit

    _QUARANTINE = ("culling", "srcBlend", "destBlend")

    def _strip_quarantined(ps: list) -> list:
        return [{k: v for k, v in p.items() if k not in _QUARANTINE} for p in ps]

    def _merge_report_mat(name: str, ent: dict, prov_tag: str) -> bool:
        passes = ent.get("passes") or []
        if not name or not any(p.get("colMask") == 15.0 for p in passes):
            return False
        row = {"mat_pid": ent.get("mat_pid"), "shader_pid": ent.get("shader_pid"),
               "shader_name": ent.get("shader"),
               "passes": _strip_quarantined(passes)}
        if name in table_mats:
            if _strip_quarantined(table_mats[name]["passes"]) != row["passes"]:
                raise AssertionError(f"材质态共享键冲突 {name}（{prov_tag}）")
            return False   # 既有行（kit/badge 源）优先，不重复记账
        table_mats[name] = row
        prov[name] = prov_tag
        return True

    _n_inj = 0
    for _mn, _ent in _btf_kit().report["materials"].items():
        _n_inj += _merge_report_mat(_mn, _ent, "btf-kit 注入面报告直读")
    for _rec in _orn_kit().report["faction_materials"].values():
        _n_inj += _merge_report_mat(_rec.get("name") or "", _rec,
                                    "faction-ornaments 注入面报告直读")
    logger.debug(f"[material_state] 注入面报告并入 {len(table_mats)} ← btf/ornaments（+{_n_inj}）")

    out = {
        "_meta": {
            "source": ("游戏 shader bundle m_ParsedForm（36.6.0.253216）× 供给树 kit recon "
                       "+ badge 报告 + btf/ornaments 注入面报告（2026-11-01 ②并入）"),
            "extraction": "eidolon/core/supply/frames/supplements.material_state（ef_dump_cull_all 同式合并）",
            "materials": len(table_mats),
        },
        "sources": {"kits": sorted(MATERIAL_STATE_KITS), "badge-trio": "badges_report.json",
                    "injected-surfaces": ["spell_prefabs_report.json（btf-kit）",
                                          "faction_report.json（faction-ornaments）"]},
        "per_material_provenance": prov,
        "materials": table_mats,
    }
    logger.debug(f"[material_state] {len(table_mats)} materials（内存面）")
    return out
