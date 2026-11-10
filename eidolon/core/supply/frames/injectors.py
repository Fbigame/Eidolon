"""frames.injectors — 运行时注入器资产域（游戏直提内存面；consumer-arch 批9c）。

四件（badge/faction/tier/BG-rig）的提取在批7 拆座时落座 render/components/*（消费逻辑），
其**资产面**（report/npz/纹理）原为 materialize 落盘镜像文件（BADGE_DIR 等）——本域按
「DLL 拿根、从根访问」规则（todo consumer-arch 纪律，2026-10-12 拍板）补游戏直提内存面：

- 根 = 序列化 ref（roots_walk 调查=injector-roots 实验档，151 项根直取 vs
  既有产物 bitwise 对拍在先）；
- 提取 = prefab GO 树走查（矩阵链口径：badge/faction=NestedPrefabBase.LoadPrefab
  :96-106 根平移置零 rot/scale 保留；btf=AttachAndPreserveLocalTransform 根平移保留）；
- A/B = 消费可见投影等 + 数组/纹理 vs 既有产物位等（本域 tests 语义，evidence 账
  随批次 NOTES）。

@item 域项 + 进程 memo（kits 同法）：解码物会话 memo 之上进程级（提取事件有界）。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from UnityPy.helpers.MeshHelper import MeshHandler

from eidolon.core.infra.resolve_asset_ref import PPtrError, record_pptr_miss
from eidolon.core.supply._projection import as_pairs, as_rgba
from eidolon.core.supply.frames.engine import mat4_from_trs, ptr_dict
from eidolon.core.supply.machine import core, item

# ---- 序列化根（roots_walk 实测 ref 串；gold = injector-roots 实验档 evidence）----
BADGE_PREFABS = {
    "tradeable": "Tradeable_Banner.prefab:2b8ee190319eaf14d906503371f38f5e",
    "forgeable": "Forgeable_Banner.prefab:fca896d80e20b934eb96e7fe83f43a9a",
    "prepareable": "Prepareable_Banner.prefab:fccd1c9e46984864da6f8c37b9975e2d",
}
FACTION_PREFAB = "Faction_Banner.prefab:0a0897af94ecdcc47b8804c643584320"
BTF_SPELLS = {
    "tech_level_mana_gem": ("Card_Hand_Ally_TechLevelManaGem.prefab:fafee4fdb205ce84984f1c7f2147cdab", 156),
    "timewarped_tier_icon": ("Card_Hand_Ally_TierIcon_Timewarped_Tavern.prefab:f72c04600fde42940a8156619c758e9c", 308),
    "coin_mana_gem_bacon_spell": ("Card_Hand_Ability_CoinManaGem_BaconSpell.prefab:6ddefa5a3e359e045b84f737944b8a80", 267),
    "coin_mana_gem": ("Card_Hand_Ability_CoinManaGem.prefab:3416ba18b6faec347a91692f9ecb33eb", 145),
    # BG 英雄能力金币件（History_HeroPower_SpellTable 槽 145 专用行；bacon-hero-power-frames
    # 2026-10-07 hp_table_probe/hp_coin_prefab_probe 定案 ref——mesh/材质与 ability 145 件
    # 同 pid，仅 Gem_Health 变换不同：居中、Y 翻转、Y 压扁）。消费=compile_tier_spell
    # want_coin_hp 腿。字面 ref 与 btf.btf_kit 链解值对拍（audit §2 双源同值）。
    "coin_mana_gem_hero_power": ("History_HeroPower_CoinManaGem.prefab:b0d925c1124201444b626336c386a464", 145),
}


class _ArrayDict(dict):
    """npz 接口兼容 dict（.files 键列表；kits 同法——npz 十消费点接口面）。"""

    @property
    def files(self) -> list[str]:
        return list(self.keys())


def _deref(r, bundle: str, ptr: dict, owner):
    return r.resolve_pptr(bundle, ptr, owner)


def _walk_prefab(r, ref: str, root_tx_zero: bool):
    """prefab GO 树走查（duipai.py walk_prefab 移植）：节点带 path/trs/matrix 链累计/
    mesh reader/材质 typetree。"""
    res = r.resolve(ref)
    assert res["ok"], (ref, res.get("checks"))
    bundle = res["resolved"]["bundle"]
    go, guid = r.container_get(bundle, res["resolved"]["guid"])
    nodes: list[dict] = []

    def rec(go_reader, go_tt, path, parent_m, is_root):
        comps: dict[str, tuple] = {}
        for comp in go_tt.get("m_Component", []):
            p = ptr_dict(comp.get("component") or {})
            if not p.get("m_PathID"):
                continue
            try:
                cobj, cb = r.resolve_pptr(bundle, p, go_reader)
                comps[cobj.type.name] = (cobj, cobj.read_typetree())
            except PPtrError as exc:
                record_pptr_miss(exc, f"{path}: comp")
        tr_name, tr_tt = comps.get("Transform", (None, None))
        p_, q_, s_ = tr_tt["m_LocalPosition"], tr_tt["m_LocalRotation"], tr_tt["m_LocalScale"]
        pos = [p_["x"], p_["y"], p_["z"]]
        if is_root and root_tx_zero:
            pos = [0.0, 0.0, 0.0]   # LoadPrefab :102 根平移强制零
        local = mat4_from_trs(pos, [q_["x"], q_["y"], q_["z"], q_["w"]],
                              [s_["x"], s_["y"], s_["z"]])
        mat = local if parent_m is None else parent_m @ local
        node: dict = {"path": path, "go_path_id": go_reader.path_id,
                      "activeSelf": bool(go_tt.get("m_IsActive", 1)), "matrix": mat,
                      "transform": {"local_position": p_, "local_rotation": q_,
                                    "local_scale": s_},
                      "components": {}}
        if "MeshFilter" in comps:
            mf = comps["MeshFilter"][1].get("m_Mesh") or {}
            mp = ptr_dict(mf)
            if mp.get("m_PathID"):
                try:
                    mobj, mb = r.resolve_pptr(bundle, mp, comps["MeshFilter"][0])
                    node["mesh_obj"] = mobj
                    node["components"]["mesh_filter"] = {
                        "component": "MeshFilter", "enabled": True,
                        "mesh": {"name": mobj.read_typetree().get("m_Name"),
                                 "bundle": mb, "path_id": mobj.path_id}}
                except PPtrError as exc:
                    record_pptr_miss(exc, f"{path}: mesh")
        if "MeshRenderer" in comps:
            mo, mtt = comps["MeshRenderer"]
            slots = []
            for i, mp in enumerate(mtt.get("m_Materials") or []):
                pd = ptr_dict(mp if isinstance(mp, dict) else getattr(mp, "__dict__", mp))
                if not pd.get("m_PathID"):
                    slots.append({"slot": i, "empty": True})
                    continue
                try:
                    mobj, mb = r.resolve_pptr(bundle, pd, mo)
                    mt = mobj.read_typetree()
                    saved = mt.get("m_SavedProperties") or {}
                    shader = "?"
                    sp = ptr_dict(mt.get("m_Shader") or {})
                    if sp.get("m_PathID"):
                        try:
                            sobj, _sb = r.resolve_pptr(bundle, sp, mobj)
                            shader = (sobj.read_typetree().get("m_ParsedForm") or {}).get("m_Name") or "?"
                        except PPtrError as exc:
                            record_pptr_miss(exc, f"{path}: shader")
                    texs = {}
                    for first, sec in as_pairs(saved.get("m_TexEnvs"),
                                               what="m_TexEnvs").items():
                        tp = (sec or {}).get("m_Texture") or {}
                        if not ptr_dict(tp).get("m_PathID"):
                            continue
                        tobj, tb = r.resolve_pptr(bundle, ptr_dict(tp), mobj)
                        texs[first] = {"name": tobj.read_typetree().get("m_Name"),
                                       "bundle": tb, "path_id": tobj.path_id,
                                       "obj": tobj}
                    slots.append({
                        "slot": i, "slot_used_by": path, "name": mt.get("m_Name"),
                        "bundle": mb, "path_id": mobj.path_id,
                        "shader": shader,
                        # m_Colors/m_Floats 的 typetree 形态=**两元素数组对**
                        # `[["_Color", {"r":…}], …]`（不是 {"first","second"} 字典）。
                        # 旧实现按 isinstance(c, dict) 过滤 ⇒ 两表恒空、静默丢数据：
                        # 徽章影件 `_Color`=0.1037736 丢失 → multiply 加性链 vColor=0
                        # （`tex+0`），条带 R 均值 62.97 vs 引擎 70.05（2026-10-31
                        # badge-vcolor；引擎抓帧 cb2[0] 逐值同 0.103774）。
                        # 形态归一/未知形态响亮/基数守恒=eidolon.core.supply._projection
                        # 单一出口（本文件不再自带 pair 解包）。
                        # 颜色落盘形态=raster 消费的 [r,g,b,a]（同式先例 btf.py:276-278）。
                        "colors": {n: as_rgba(c) for n, c in
                                   as_pairs(saved.get("m_Colors"),
                                            what="m_Colors").items()},
                        "floats": {n: float(c) for n, c in
                                   as_pairs(saved.get("m_Floats"),
                                            what="m_Floats").items()},
                        "textures": {k: {kk: vv for kk, vv in v.items() if kk != "obj"}
                                     for k, v in texs.items()},
                        "st": {k: {"scale": v.get("m_Scale") or {}, "offset": v.get("m_Offset") or {}}
                               for k, v in texs.items()},
                        "_tex_objs": texs,   # 纹理解码源（内存面内消费，不出域）
                    })
                except PPtrError as exc:
                    record_pptr_miss(exc, f"{path}: mat")
                    slots.append({"slot": i, "error": f"{exc.reason}: {exc.detail}"})
            node["components"]["renderer"] = {"component": "MeshRenderer",
                                              "enabled": bool(mtt.get("m_Enabled", 1)),
                                              "material_slots": slots}
        nodes.append(node)
        for ch in tr_tt.get("m_Children") or []:
            cp = ptr_dict(ch if isinstance(ch, dict) else getattr(ch, "__dict__", ch))
            if not cp.get("m_PathID"):
                continue
            try:
                tro, tb = r.resolve_pptr(bundle, cp, comps["Transform"][0])
                trtt2 = tro.read_typetree()
                gpp = ptr_dict(trtt2.get("m_GameObject") or {})
                cgo, _cb = r.resolve_pptr(tb, gpp, tro)
                rec(cgo, cgo.read_typetree(), f"{path}/{cgo.read_typetree().get('m_Name')}",
                    mat, False)
            except PPtrError as exc:
                record_pptr_miss(exc, f"{path}: child")

    tt = go.read_typetree()
    rec(go, tt, tt.get("m_Name", "?"), None, True)
    return nodes, bundle, guid


def _mesh_arrays(mesh_obj) -> dict:
    h = MeshHandler(mesh_obj.read())
    h.process()
    verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
    uv0 = (np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0
           else np.zeros((len(verts), 2)))
    out = {"verts": verts, "uv0": uv0,
           "subs": [np.array([t for t in sub if len(t) == 3], dtype=np.int32)
                    for sub in h.get_triangles()]}
    if h.m_UV1:
        out["uv1"] = np.array(h.m_UV1, dtype=np.float64).reshape(-1, 2)
    return out


def _load_tex_obj(r, bundle: str, tobj) -> Image.Image:
    return tobj.read().image


@item("frames", "badge_kit_mem")
def badge_kit_mem() -> dict:
    """徽章三件内存 kit：{"report": {badges:{bkey:{info,nodes,textures}}}, "arrays",
    "textures": {名: PIL}}——形状=消费可见投影（badge_report 旧档同键；shader 态不重建，
    消费位=材质名查表 _badge_blend_mode）。矩阵链=LoadPrefab 根平移置零。"""
    r = core().res
    report: dict = {"badges": {}}
    arrays = _ArrayDict()
    textures: dict[str, Image.Image] = {}
    for bkey, ref in BADGE_PREFABS.items():
        nodes, bundle, guid = _walk_prefab(r, ref, root_tx_zero=True)
        tex_used: dict[str, dict] = {}
        for nd in nodes:
            rr = nd["components"].get("renderer")
            if not rr:
                continue
            node_path = nd["path"]
            for slot in rr["material_slots"]:
                for slot_name, tinfo in slot.get("textures", {}).items():
                    tobj = slot.get("_tex_objs", {}).get(slot_name, {}).get("obj")
                    key = tinfo["name"]
                    if key not in textures and tobj is not None:
                        textures[key] = _load_tex_obj(r, tinfo["bundle"], tobj)
                    ent = tex_used.setdefault(key, {"name": key, "used_by": []})
                    ent["used_by"].append(f"{node_path}:{slot_name}")
            if "mesh_obj" in nd:
                arrs = _mesh_arrays(nd["mesh_obj"])
                pref = f"{bkey}|{node_path}"
                arrays[f"{pref}/verts"] = arrs["verts"]
                arrays[f"{pref}/uv0"] = arrs["uv0"]
                for i, tris in enumerate(arrs["subs"]):
                    arrays[f"{pref}/sub{i}"] = tris
                arrays[f"{pref}/matrix"] = nd["matrix"].astype(np.float64)
        report["badges"][bkey] = {
            "info": {"prefab_ref": ref, "bundle": bundle, "guid": guid,
                     "root_name": nodes[0]["path"],
                     "root_localPosition_forced_zero": True},
            "nodes": [{"path": nd["path"], "go_path_id": nd["go_path_id"],
                       "activeSelf": nd["activeSelf"], "components": nd["components"],
                       "transform": nd["transform"],
                       "matrix_local_to_root": nd["matrix"].tolist()} for nd in nodes],
            "textures": [{"name": v["name"], "used_by": v["used_by"],
                          "file": f"textures/{v['name']}.png"} for v in tex_used.values()],
        }
    return {"report": report, "arrays": arrays, "textures": textures}


def _mat_saved(tt: dict) -> dict:
    """`m_SavedProperties` 三表 → {colors, floats, texenvs}（形态归一走 _projection）。

    旧实现按 `isinstance(c, dict)` 过滤 `m_Colors/m_Floats`，而 typetree 现役形态是
    两元素列表对 ⇒ 两表恒空且不报错（badge-vcolor 同形；本函数当前无生产消费者，
    收编旨在清掉最后一个自带 pair 解包）。"""
    saved = tt.get("m_SavedProperties") or {}
    return {
        "colors": {n: as_rgba(v) for n, v in
                   as_pairs(saved.get("m_Colors"), what="m_Colors").items()},
        "floats": as_pairs(saved.get("m_Floats"), what="m_Floats"),
        "texenvs": as_pairs(saved.get("m_TexEnvs"), what="m_TexEnvs"),
    }


@item("frames", "faction_kit_mem")
def faction_kit_mem() -> dict:
    """派系饰件内存 kit：nodes（matrix_local_to_root/activeSelf/renderer/mesh_filter）
    + faction_materials（icon_1..6/banner_1/banner_4——probe 表 ref 直取，_MainTex
    ST+纹理内存面）+ arrays（faction|Faction_Banner/{rel}/{verts,uv0,subN,matrix}）+
    textures（名→PIL）。矩阵链=LoadPrefab 根平移置零（同 badges）。"""
    r = core().res
    nodes, bundle, guid = _walk_prefab(r, FACTION_PREFAB, root_tx_zero=True)
    arrays = _ArrayDict()
    textures: dict[str, Image.Image] = {}
    for nd in nodes:   # walk 槽纹理全收（shadow 等非 probe 家族件——TradeableBanner_shadow）
        rr = nd["components"].get("renderer")
        for slot in (rr or {}).get("material_slots", []):
            for _k, tv in (slot.get("_tex_objs") or {}).items():
                to = (tv or {}).get("obj") if isinstance(tv, dict) else tv
                tname = (slot.get("textures") or {}).get(_k, {}).get("name")
                if to is not None and tname and tname not in textures:
                    textures[tname] = to.read().image
    for nd in nodes:
        if "mesh_obj" not in nd:
            continue
        arrs = _mesh_arrays(nd["mesh_obj"])
        rel = nd["path"]
        pref = f"faction|{rel}"
        arrays[f"{pref}/verts"] = arrs["verts"]
        arrays[f"{pref}/uv0"] = arrs["uv0"]
        for i, tris in enumerate(arrs["subs"]):
            arrays[f"{pref}/sub{i}"] = tris
        arrays[f"{pref}/matrix"] = nd["matrix"].astype(np.float64)

    def _mat_entry(ref: str) -> dict:
        res = r.resolve(ref)
        assert res["ok"], (ref, res.get("checks"))
        mo, _ck = r.container_get(res["resolved"]["bundle"], res["resolved"]["guid"])
        mt = mo.read_typetree()
        saved = mt.get("m_SavedProperties") or {}
        main = {}
        for first, sec in as_pairs(saved.get("m_TexEnvs"), what="m_TexEnvs").items():
            if first != "_MainTex":
                continue
            sec = sec or {}
            tp = sec.get("m_Texture") or {}
            if not ptr_dict(tp).get("m_PathID"):
                continue
            tobj, tb = r.resolve_pptr(res["resolved"]["bundle"], ptr_dict(tp), mo)
            ttt = tobj.read_typetree()
            tname = ttt.get("m_Name")
            if tname not in textures:
                textures[tname] = tobj.read().image
            main = {"scale": sec.get("m_Scale"), "offset": sec.get("m_Offset"),
                    "tex_name": tname, "tex_bundle": tb, "tex_path_id": tobj.path_id}
        return {"name": mt.get("m_Name"),
                "textures": {"_MainTex": main} if main else {},
                "colors": {n: as_rgba(v) for n, v in
                           as_pairs(saved.get("m_Colors"), what="m_Colors").items()}}

    from eidolon.core.supply import color as _color
    probe = _color.probe()
    faction_materials: dict = {}
    for i in range(1, 7):
        if probe["factionIconMaterials"][i]:
            faction_materials[f"icon_{i}"] = _mat_entry(probe["factionIconMaterials"][i])
        if probe["factionBannerMaterials"][i]:
            faction_materials[f"banner_{i}"] = _mat_entry(probe["factionBannerMaterials"][i])

    report = {
        "prefab": {"name": "Faction_Banner", "ref": FACTION_PREFAB,
                   "guid": FACTION_PREFAB.split(":")[1], "bundle": bundle},
        "nodes": [{"path": nd["path"], "activeSelf": nd["activeSelf"],
                   "matrix_local_to_root": nd["matrix"].tolist(),
                   "components": {k: (v if not isinstance(v, dict) else {
                       kk: ({k2: vv for k2, vv in v2.items()
                             if k2 not in ("_tex_objs", "obj")} if isinstance(v2, dict) else v2)
                       for kk, v2 in v.items()}) for k, v in nd["components"].items()},
                   "children": [c for c in ()]} for nd in nodes],
        "faction_materials": faction_materials,
        "issues": [],
    }
    return {"report": report, "arrays": arrays, "textures": textures}


def btf_tree_mem() -> dict:
    """BG tier 四 Spell 的**树+材质名绑定**内存面（批9c）：walk_prefab 产
    {skey: tree（节点 name/material_slots[{material}]/mesh/children）}——compile_tier_spell
    树查找消费位；数组/材质账/纹理取官方 supply/frames/btf.btf_kit（产品精确集，
    消费方 _btf_assets 组合两源）。矩阵/数组 A/B=duipai 151 项位等在先。"""
    r = core().res
    trees: dict[str, dict] = {}
    for skey, (ref, _stype) in BTF_SPELLS.items():
        nodes, bundle, guid = _walk_prefab(r, ref, root_tx_zero=False)
        tree: dict = {"name": nodes[0]["path"]}
        for nd in nodes:
            segs = nd["path"].split("/")
            cur = tree
            for seg in segs[1:]:
                kids = cur.setdefault("children", [])
                nxt = next((c for c in kids if c.get("name") == seg), None)
                if nxt is None:
                    nxt = {"name": seg}
                    kids.append(nxt)
                cur = nxt
            rr = nd["components"].get("renderer")
            if rr:
                cur["material_slots"] = [{"material": s.get("name")}
                                         for s in rr["material_slots"] if s.get("name")]
            if "mesh_obj" in nd:
                cur["mesh"] = nd["components"].get("mesh_filter", {}).get("mesh", {}).get("name")
        trees[skey] = tree
    return trees
