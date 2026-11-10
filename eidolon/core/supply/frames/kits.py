"""frames.kits — 五帧族 kit 主流程（Kit 真内存对象）。

[ally_recon.main:371-580 逐字参数化；v3 形态=全内存 Kit（落盘随阶段②适配壳）；
类色图集全槽段复用 color.atlas（同链会话 memo 共享）；actor/卡翻译走 infra 活表]"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from eidolon.core.infra.dll_reflect import tables
from eidolon.core.infra.errors import GameAssetMissing
from eidolon.core.supply.frames.engine import (
    Recon,
    extract_mesh_from_bundle,
    extract_race_strings,
    extract_spell_school_strings,
    global_strings_path,
    mat4_from_trs,
    vec3,
)
from eidolon.core.supply.frames.specs import FRAME_SPECS
from eidolon.core.supply.machine import core, item

logger = logging.getLogger(__name__)


@item("frames", "actor_ref")
def actor_ref(quality: str, slot: str) -> str:
    """品质×槽位 → actor prefab "名.ext:GUID"（ActorNames.GetHandActor/GetPlayActorByTags
    离线等价；批10d：actor_names.csv 退役，背书=dll_reflect actor 三活表——
    s_actorAssets/s_premiumActorAssets/s_diamondActorAssets，与 CSV 逐槽相等实证在案）。

    typed 边界（设计 §5.3）：活表无该槽位 → ``GameAssetMissing``
    （quality 不在三表内=内部取表错误，仍 KeyError）。"""
    tbl = {"normal": tables.actor_slots, "premium": tables.premium_actors,
           "diamond": tables.diamond_actors}[quality]
    try:
        return tbl[slot]
    except KeyError as exc:
        raise GameAssetMissing(
            path=f"{quality}/{slot}",
            message=f"asset_missing_in_game: actor 活表无 {quality}/{slot}",
            cause=f"KeyError: {exc}") from None


@item("frames", "spell_school_names")
def spell_school_names() -> dict[int, str]:
    """TAG_SPELL_SCHOOL 枚举值 → zhCN 学派名（活表键 × GLOBAL_STRINGS 解析；
    批10d：tag_enum.csv 退役）。键缺失=KeyError 响亮（本地化漂移不静默）。"""
    loc = extract_spell_school_strings()
    return {value: loc[key] for value, key in tables.spell_school_names.items()}


@dataclass
class Kit:
    """帧 kit 真内存对象（旧五件布局位的内存面）。"""
    frame_dir: str
    meta: dict                                  # frame_recon.json 内容面
    arrays: dict = field(default_factory=dict)  # mesh_data.npz 内容面 {key: ndarray}
    textures: dict = field(default_factory=dict)  # textures/ {文件名: PIL}
    report: dict = field(default_factory=dict)  # prefab_report_*.json 内容面
    ubertext: dict = field(default_factory=dict)  # prefab_ubertext_*.json 内容面
    races: dict | None = None                   # strings_race_zhcn.json 内容面（ally 族）
    mesh_refs: dict = field(default_factory=dict)  # 网格名→(bundle,pid) 结构引用
    # （MeshFilter PPtr 现场解随走查捕获；派生件链化取用，不进对拍面）


class _ArrayDict(dict):
    """kit 数组面（npz 内容面）：.files 兼容算子——③外迁 2026-10-11 消费方从盘上 npz 换
    内存面，场景 npz 的既有接口面（.files/__getitem__）在此保留（np.load 其余算子无人用）。"""

    @property
    def files(self) -> list[str]:
        return list(self.keys())


# 进程级 kit memo（2026-10-11 ③外迁批6 到期项兑现：kit=卡不变游戏结构，进程 memo 叠加；
# 盘上读穿为底的简陋缓存随 materialize 批落座——worker 池重启后首卡重建，提取事件仍有界）
_KIT_CACHE: dict[str, Kit] = {}


def _pick_actor_ref(slot: str, quality: str = "normal") -> str:
    """[旧 pick_actor_ref 的活表后继]：quality → 三张反射表。"""
    t = {"normal": tables.actor_slots, "premium": tables.premium_actors,
         "diamond": tables.diamond_actors}[quality]
    return t[slot]


def _pick_card_id(dbf_id: str) -> str:
    """[旧 pick_card_id 的活表后继]：CARD.m_noteMiniGuid（大小写账见 infra.dbf）。

    typed 边界（设计 §5.3）：CARD 表无该 dbf 行（无 prefab 行的卡）→
    ``GameAssetMissing``。"""
    from eidolon.core.infra import dbf

    card = dbf.default_dbf().card
    rec = card.get(str(dbf_id)) or card.get(int(dbf_id))
    if rec is None:
        raise GameAssetMissing(
            path=str(dbf_id),
            message=f"asset_missing_in_game: CARD 表无 dbf {dbf_id}")
    return rec["m_noteMiniGuid"]


def _extract_kit(spec: dict, probe: dict, light: bool = False) -> Kit:
    """五帧族 kit：meta（frame_recon）+ arrays（npz）+ textures + report + ubertext
    +（ally）种族串。流程 = ally_recon.main [371-580] 逐字，规格差异走 spec；
    类色图集段扩展为 probe 全槽（superset 安全：渲染查找按名命中，多落不影响逐位）。
    v3 形态：全内存 Kit（落盘随阶段②适配壳）。"""
    actor_ref = spec.get("actor_ref") or _pick_actor_ref(spec["slot"], spec.get("quality", "normal"))
    card_id = _pick_card_id(spec["dbf"])

    rec = Recon(uv1_mode=spec["uv1"], color0=spec["color0"], save_textures=not light)
    res = rec.r.resolve(actor_ref)
    assert res["ok"], f"actor 解析失败: {res['checks']}"
    rec.bundle = res["resolved"]["bundle"]
    guid = res["resolved"]["guid"]
    root_go, _ = rec.r.container_get(rec.bundle, guid)
    rec._root_go = root_go

    hierarchy = rec.walk(root_go, "", "root")
    rec.hierarchy = hierarchy

    # ---- 世界变换自底向上 + 根归零 [ally_recon:394-410 / hero_recon 全恒等增量] ----
    def assign_world(node, parent_m):
        M = mat4_from_trs(**{k: node["local"][k] for k in ("pos", "rot", "scale")}) \
            if node["local"] else np.eye(4)
        node["world"] = (parent_m @ M).tolist()
        for ch in node["children"]:
            assign_world(ch, np.array(node["world"]))

    raw_root = None
    if hierarchy.get("local"):
        raw_root = dict(hierarchy["local"])
        if spec.get("root") == "full":
            # [hero_recon 增量]：根位姿全恒等（pos=0/rot=identity/scale=1）——
            # SnapshotCamera.PrepareObject 无条件覆写根位姿（hero_recon 头注正典）
            hierarchy["local"] = {"pos": [0.0, 0.0, 0.0], "rot": [0.0, 0.0, 0.0, 1.0],
                                  "scale": [1.0, 1.0, 1.0]}
        else:
            hierarchy["local"] = {**hierarchy["local"], "pos": [0.0, 0.0, 0.0]}
    assign_world(hierarchy, np.eye(4))

    # ---- npz [ally_recon:413-429] ----
    arrays: dict[str, np.ndarray] = {}

    def collect(node):
        mesh = node.pop("mesh", None)
        if mesh:
            key = node["npz_key"]
            arrays[f"{key}/verts"] = mesh["verts"]
            arrays[f"{key}/uv0"] = mesh["uv0"]
            if "normals" in mesh:
                arrays[f"{key}/normals"] = mesh["normals"]
            if "uv1" in mesh:
                arrays[f"{key}/uv1"] = mesh["uv1"]
            if "color0" in mesh:
                arrays[f"{key}/color0"] = mesh["color0"]
            for i, tris in enumerate(mesh["submeshes"]):
                arrays[f"{key}/sub{i}"] = tris
            node["mesh_stats"] = {"name": mesh["name"], "verts": len(mesh["verts"]),
                                  "submesh_tris": [len(t) for t in mesh["submeshes"]],
                                  "bbox_min": mesh["bbox_min"], "bbox_max": mesh["bbox_max"]}
        for ch in node["children"]:
            collect(ch)

    collect(hierarchy)

    # ---- Actor 绑定 + extra Mesh [ally_recon:432-449] ----
    actor = rec.finalize_actor(rec.actor_owner)
    # m_alternateCostTextLocalPos（Actor.cs:Actor 序列化 Vector3，费用数字铸币位）：
    # finalize_actor 只收标量/PPtr，Vector3 落空 → 此处显式取。**逐 prefab 不同**
    # （2026-11-04 golden-alt-cost-pos 实测：Card_Hand_Ally=−0.01 / _Premium=+0.025，
    # 金随从帧整字偏 6.15px）——渲染侧禁再按单值常量套全帧族。
    alt_cost = vec3((rec.actor_mt or {}).get("m_alternateCostTextLocalPos"))
    extra = {}
    if spec["extra_meshes"] and not light:
        for field_name, e in actor.get("object_refs", {}).items():
            if e.get("type") != "Mesh" or not e.get("bundle"):
                continue
            mesh = extract_mesh_from_bundle(rec.r, e["bundle"], e["path_id"])
            if mesh is None:
                continue
            key = f"extra/{field_name}"
            arrays[f"{key}/verts"] = mesh["verts"]
            arrays[f"{key}/uv0"] = mesh["uv0"]
            for i, tris in enumerate(mesh["submeshes"]):
                arrays[f"{key}/sub{i}"] = tris
            extra[key] = {"name": mesh["name"], "verts": len(mesh["verts"]),
                          "submesh_tris": [len(t) for t in mesh["submeshes"]],
                          "bundle": e["bundle"], "path_id": e["path_id"]}

    # ---- 饰品章环双外部材质（trinket_level_mats；bg-ct40-43-44-routing 2026-10-24）----
    # Actor 序列化 m_lesserTrinketMaterial/m_greaterTrinketMaterial（外部 bundle 的
    # Material 资产）解引用入 kit 纹理内存面——消费=编译器章环章面换装
    # （UpdateBaconTrinketComponents Actor.cs:5460-5483：SPELL_SCHOOL 11/12 →
    # Trinket_Medallion_Portrait_Mesh materials[0]=m_lesser/greaterTrinketMaterial）。
    # 引擎写的是材质引用（整材质换），我方离线形=章面 _MainTex 运行时写点（两材质
    # 均单槽 Hero/Unlit/Unlit_Texture，_MainTex 唯一视觉面——walk_material 实测）。
    trinket_level_mats: dict[str, dict] = {}
    if spec.get("trinket_level_mats") and not light:
        for field_name in ("m_lesserTrinketMaterial", "m_greaterTrinketMaterial"):
            e = (actor.get("object_refs") or {}).get(field_name)
            assert e and e.get("type") == "Material" and e.get("bundle"), \
                f"{field_name}: Actor 序列化无外部 Material 引用（{e}）——prefab 形态漂移"
            mobj, mb = rec.r.resolve_pptr(
                rec.bundle, {"m_FileID": e["file_id"], "m_PathID": e["path_id"]},
                rec._root_go)
            mat = rec.walk_material(mobj, mb, mobj)
            main = (mat.get("tex") or {}).get("_MainTex", {})
            tex_file = (main.get("texture") or {}).get("file")
            assert tex_file and tex_file in rec.textures, \
                f"{field_name}: 材质 _MainTex 未入 kit 纹理面（{main}）"
            trinket_level_mats[field_name] = {
                "material": mat.get("name"), "main_tex_file": tex_file,
                "main_tex": main.get("texture", {}).get("name"),
                # 整材质换装语义（引擎 materials[0]=新 Material 对象）——新材质
                # _Color 随行（被换槽 BG_Trinket_Meter_Frame_Texture_Lid_Diffuse
                # 序列化 _Color=[0,0,0,1] 黑，不随行会染黑章面——实证坑账）。
                "color": list((mat.get("colors") or {}).get("_Color") or [1.0, 1.0, 1.0, 1.0]),
                "source": f"{field_name}（Actor 序列化外部材质，bundle={e['bundle']}）",
            }

    meta = {"prefab_ref": actor_ref, "bundle": rec.bundle, "guid": guid,
            "dbf_id": spec["dbf"], "card_id": card_id,
            "root_translation_neutralized": {
                "raw_root_pos": (raw_root or {}).get("pos"),
                "reason": "prefab 根位置=场景摆位残留；游戏区域布局覆写根位置；"
                          "canonical 快照位姿=恒等根（Ability 帧原点+E7 实证）",
            },
            "hierarchy": hierarchy, "extra_meshes": extra,
            "actor_alt_cost_pos": alt_cost,
            "trinket_level_mats": trinket_level_mats or None}

    # ---- prefab_report [ally_recon:464-507] ----
    fonts: dict[str, dict] = {}
    for n in rec.iter_nodes(hierarchy):
        if n.get("ubertext"):
            u = n["ubertext"]
            if u.get("font_name"):
                fonts[str(u["font_pptr"]["m_PathID"])] = {
                    "font_name": u["font_name"], "bundle": u.get("font_bundle")}
    rnodes = []
    for n in rec.iter_nodes(hierarchy):
        comp: dict = {}
        rr = n.get("renderers") or []
        if rr:
            slots = []
            for i, mat in enumerate(rr[0]["materials"]):
                if mat is None:
                    slots.append({"slot": i, "empty": True})
                    continue
                texs = {}
                for prop, t in mat["tex"].items():
                    texobj = t.get("texture") or {}
                    if texobj:
                        texs[prop] = {"name": texobj.get("name"), "bundle": texobj.get("bundle")}
                slots.append({"slot": i, "name": mat["name"], "textures": texs})
            comp["renderer"] = {"material_slots": slots}
        if n.get("ubertext"):
            comp["TextComponent"] = {"path_id": n["ubertext"]["path_id"],
                                     "font_name": n["ubertext"].get("font_name"),
                                     "font_pptr": n["ubertext"].get("font_pptr")}
        rnodes.append({"path": n["path"], "go_path_id": n["go_path_id"], "components": comp})
    root_name = actor_ref.split(".")[0]
    report = {
        "prefab": {"name": root_name, "ref": actor_ref, "guid": guid, "bundle": rec.bundle},
        "class_atlas": {"ref": None, "note": "全槽图集由 probe 驱动另落（本字段为采样槽记账）"},
        "nodes": rnodes,
        "actor_components": [actor],
        "fonts": fonts,
        "issues": rec.issues,
        "textures": [dict(v, used_by=["frame"]) for v in rec.tex_saved.values()],
    }

    # ---- prefab_ubertext [ally_recon:509-524] ----
    unodes = []
    for n in rec.iter_nodes(hierarchy):
        if n.get("ubertext"):
            u = n["ubertext"]
            unodes.append({"path": n["path"], "mono_path_id": u["path_id"],
                           "localPosition": (n["local"] or {}).get("pos"),
                           "localScale": (n["local"] or {}).get("scale"),
                           "localRotation": (n["local"] or {}).get("rot"),
                           "fields": u["fields"], "font_name": u.get("font_name")})
    unodes.sort(key=lambda n: n["path"])
    ubertext = {"ref": actor_ref, "bundle": rec.bundle, "n_ubertext": len(unodes),
                "nodes": unodes}

    # ---- 类色图集全槽（probe family 表驱动；命名 = ref stem_guid8，各帧编译器同式）----
    n_atlas = 0
    if spec["family"] and not light:      # 轻走查不进类色图集（1024² 解码大头）
        from eidolon.core.supply import color

        fam = probe[spec["family"]]   # v3 probe=平面族表（旧 json 的 switcher.data 面已收编）
        for ct, ref in enumerate(fam):
            if not (isinstance(ref, str) and ":" in ref):
                continue
            # 登记别名差（引用名 stem ≠ 对象实名，如 Minion_DK vs DeathKnight）非错误：
            # registration/type 检查须过，name-consistency 容忍（dk_extract_dk_atlas 先例）
            stem, _g = ref.rsplit(":", 1)
            atlas_name = f"{Path(stem).stem}_{ref.rsplit(':', 1)[1][:8]}.png"
            rec.textures[atlas_name] = color.atlas(spec["family"], ct)
            n_atlas += 1

    # ---- 种族串（ally）[ally_recon:569-575] ----
    races = None
    if spec["races"] and not light:
        races = {"source": str(global_strings_path()),
                 "provenance": "GameStrings.GetRaceName → s_raceNames[TAG_RACE] → GLOBAL_RACE_*"
                               "（GameStrings.cs:GameStrings/1739）",
                 "strings": extract_race_strings()}

    logger.debug(f"[kit/{spec['frame_dir']}{' LIGHT' if light else ''}] arrays={len(arrays)} "
                 f"atlas={n_atlas} textures={len(rec.textures)} issues={len(rec.issues)}")
    return Kit(frame_dir=spec["frame_dir"], meta=meta, arrays=_ArrayDict(arrays),
               textures=rec.textures, report=report, ubertext=ubertext, races=races,
               mesh_refs={m["mesh"]["name"]: (m["bundle"], m["mesh_obj"].path_id)
                          for m in rec.mesh_jobs})


@item("frames", "kit")
def kit(frame: str) -> Kit:
    """帧 kit（ally/weapon/heropower/location/hero_hand/hero_play）。"""
    from eidolon.core.supply import color

    if frame not in _KIT_CACHE:
        _KIT_CACHE[frame] = _extract_kit(FRAME_SPECS[frame], color.probe())
    return _KIT_CACHE[frame]


_KIT_LIGHT_CACHE: dict[str, Kit] = {}


@item("frames", "kit_light")
def kit_light(frame: str) -> Kit:
    """轻量帧 kit（批2b-1）：只到 hierarchy+report+ubertext——不 deref 纹理
    （Recon.save_textures=False）、不进类色图集/extra meshes/种族串。
    消费者=material_state 级（读 meta["hierarchy"] 的 renderer 材质引用）；
    **textures 为空 dict——渲染链消费者禁用本域项**（空纹理渲空白，门会红）。"""
    return _extract_kit(FRAME_SPECS[frame], None, light=True)
