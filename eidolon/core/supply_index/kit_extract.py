"""kit_extract — cold 侧 frame_kit 提取（六面结构物；全包唯一 kit UnityPy 面）。

从 actor prefab 提取帧 kit 结构，输出对齐 eidolon/core/supply/frames/kits.py kit() 产物
六面（meta/hierarchy/arrays/textures/report/ubertext；hierarchy 自 meta 分立成面）。
**逐配方转写、零 import 参照族**（包边界）：

转写锚（渲染铁律：file:Class 函数位）
- 走查引擎=eidolon/core/supply/frames/engine.py（[ally_recon.py:32-344 逐字]）：Recon.walk
  /walk_material/extract_mesh/save_texture/ubertext_record/finalize_actor、
  mat4_from_trs/ptr_dict/vec3；
- 编排=eidolon/core/supply/frames/kits.py:_extract_kit（[ally_recon.main:371-580 逐字]）：
  根位姿归零（"pos"/"full"）→世界变换自底向上→npz 收集（collect 弹 mesh 存
  mesh_stats）→Actor 绑定（finalize_actor）→extra meshes；
- 形状归一=eidolon/core/supply/_projection.py as_pairs/as_rgba（badge-vcolor 判例：
  只认两已知形态、未知 raise、禁过滤式跳过——纯 stdlib 转写）；
- ActorNames.GetHandActor 槽位分派（ActorNames.cs:ActorNames.GetHandActor :550-575
  表驱动体；值域=TAG_CARDTYPE 活表）→ verify 覆盖面解析。

**container 读取一律 SerializedFile.container.container 原始 pairs（必须保留 #2）**：
PPtr 解析器自写（_KitResolver，转写 eidolon.core.infra.resolve_asset_ref.BundleStore.
_resolve_pptr 的语义——externals CAB 定位+bundle_deps 闭包扫描+PPtrError 分类），
不用 infra Resolver（其 container 面走 route 航线库，供给面禁入）。

车1 排除域（记 kit_codec/manifest 的 excluded 账，禁静默）：
- 类色图集（supply.color.probe/atlas=render 链域，禁 import）；
- trinket_level_mats（trinket 帧不在车1 六族——A6 起该帧=supplement harness
  域（supplement_extract），随 live 提取自带）。

A6 扩展面：**races 种族串**（ally 帧——live spec races=True；GLOBAL.txt 正则
提取，非 UnityPy 面）与 **mesh_refs**（网格名→(bundle, path_id) 结构引用——
walk 期 mesh_jobs 捕获，live kits.py Kit.mesh_refs 同式）两面随 kit item 落库
（kit_codec.KIT_CODEC_VERSION 2；warm kit_races/kit_mesh_refs 访问器供货，
seed 侧组装 live Kit 的 races/mesh_refs 属性——A3 的 live 派生缺口面退役）。
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from UnityPy.helpers.MeshHelper import MeshHandler

logger = logging.getLogger(__name__)

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index import kit_codec as KC
from eidolon.core.supply_index._unity import (
    container_pairs,
    iter_serialized,
    load_bundle,
)

# ---------------------------------------------------------------------------
# 帧规格（FRAME_SPECS 六族转写——eidolon/core/supply/frames/specs.py；只取车1 消费字段）
# ---------------------------------------------------------------------------

FRAME_SPECS_KIT: dict[str, dict] = {
    # key → actor_slot / 采样 dbf / uv1 模式 / color0 / 根归零模式 / extra meshes
    # / races（A6：ally 帧族串面——live FRAME_SPECS races=True 帧族词面；
    # atlas/trinket_level_mats 两列=车1 排除域，不入表——缺席即账）
    "ally":       dict(slot="HAND_MINION", dbf="9", uv1=None, color0=False,
                       root="pos", extra_meshes=True, races=True),
    "weapon":     dict(slot="HAND_WEAPON", dbf="1662", uv1="uv0copy", color0=False,
                       root="pos", extra_meshes=True, races=False),
    "heropower":  dict(slot="HISTORY_HERO_POWER", dbf="229", uv1="uv0copy",
                       color0=True, root="pos", extra_meshes=False, races=False),
    "location":   dict(slot="HAND_LOCATION", dbf="76981", uv1="uv0copy",
                       color0=False, root="pos", extra_meshes=True, races=False),
    # hero 双帧（uv1=zeros/color0/根位姿全恒等归零——SnapshotCamera.PrepareObject
    # 无条件覆写根位姿，hero_recon 头注正典）
    "hero_hand":  dict(slot="HAND_HERO", dbf="7", uv1="zeros", color0=True,
                       root="full", extra_meshes=False, races=False),
    "hero_play":  dict(slot="PLAY_HERO", dbf="7", uv1="zeros", color0=True,
                       root="full", extra_meshes=False, races=False),
}

EXCLUDED_FACES = {
    "atlas": "类色图集（supply.color probe 族表=render 链域，车1 不提）",
    "trinket_level_mats": "饰品章环双外部材质（trinket 帧=A6 supplement harness "
                          "域，随 live 提取自带；车1 六族无此 spec）",
}


def extract_race_strings_from(strings_txt: Path) -> dict:
    """GLOBAL.txt → GLOBAL_RACE_* 键值（A6 kit races 面；engine.extract_race_strings
    逐字转写——正则/编码/strip 三处口径同源，值面=纯文本提取零 UnityPy）。"""
    import re

    out: dict[str, str] = {}
    if strings_txt.is_file():
        text = strings_txt.read_text(encoding="utf-8-sig")
        for m in re.finditer(r"^(GLOBAL_RACE_[A-Z_]+)\t([^\t]*)", text, re.M):
            out[m.group(1)] = m.group(2).strip()
    return out


def races_face(strings_txt: Path) -> dict:
    """kit races 面全形（live kits._extract_kit races 段同形：source/provenance/
    strings 三键——消费点 compiler.GetRaceText 只读 ["strings"]，全形保留对拍面）。"""
    return {"source": str(strings_txt),
            "provenance": "GameStrings.GetRaceName → s_raceNames[TAG_RACE] → GLOBAL_RACE_*"
                          "（GameStrings.cs:GameStrings/1739）",
            "strings": extract_race_strings_from(strings_txt)}


def frame_family_maps() -> tuple[dict[int, str], dict[int, str]]:
    """CARDTYPE 活值 → (HAND 帧族, PLAY 帧族)。

    GetHandActor 表驱动体（ActorNames.cs:ActorNames.GetHandActor :550-575）+
    GetPlayActorByTags HERO 支（:691 PLAY_HERO；BG 分岔 :683-690 活在 kit 域外）
    转写；HAND_SPELL→"ability" 帧族、anomaly/trinket 同帧族名——三族不在车1
    FRAME_SPECS_KIT（verify 覆盖账记 out-of-scope，不炸）。"""
    from eidolon.core.infra.dll_reflect import enum_table

    ct = enum_table("TAG_CARDTYPE")
    spell = "ability"                                  # :554/:557
    hand = {
        ct["MINION"]: "ally",                          # :550-551
        ct["WEAPON"]: "weapon",                        # :552-553
        ct["SPELL"]: spell,
        ct["BATTLEGROUND_QUEST_REWARD"]: spell,        # :555
        ct["BATTLEGROUND_SPELL"]: spell,               # :556
        ct["HERO"]: "hero_hand",                       # :558-559
        ct["HERO_POWER"]: "heropower",                 # :560-561
        ct["BATTLEGROUND_HERO_BUDDY"]: "ally",         # :562-563
        ct["LOCATION"]: "location",                    # :564-565
        ct["BATTLEGROUND_ANOMALY"]: "anomaly",         # :566-567
        ct["BATTLEGROUND_TRINKET"]: "trinket",         # :568-569
    }
    play = {
        ct["HERO"]: "hero_play",                       # :691（非 BG 腿）
        ct["HERO_POWER"]: "heropower",                 # :693-694
        ct["LOCATION"]: "location",                    # :717-718
        ct["MINION"]: None,                            # :673 PLAY_MINION（离线未开帧链）
        ct["WEAPON"]: None,                            # :674-675 同上
        ct["SPELL"]: None,                             # :676-677 CARD_INVISIBLE
    }
    return hand, play


# ---------------------------------------------------------------------------
# 形状归一（eidolon/core/supply/_projection.py 转写；badge-vcolor 判例）
# ---------------------------------------------------------------------------

class ProjectionError(RuntimeError):
    """资产投影失败：形态不认识（响亮，禁过滤式跳过）。"""


def as_pairs(seq, *, what: str = "pairs") -> dict:
    """「键-值对序列」→ {名: 值}（[["_Color", {…}], …] 或 [{"first","second"}, …]；
    未知形态 raise——静默空集比崩溃危险）。"""
    out: dict = {}
    if seq is None:
        return out
    if not isinstance(seq, (list, tuple)):
        raise ProjectionError(
            f"{what}：源形态不是序列（{type(seq).__name__}，{repr(seq)[:120]}）")
    for i, item in enumerate(seq):
        if isinstance(item, dict):
            if "first" not in item or "second" not in item:
                raise ProjectionError(
                    f"{what}[{i}]：dict 形态缺 first/second 键（{repr(item)[:120]}）")
            name, val = item["first"], item["second"]
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            name, val = item[0], item[1]
        else:
            raise ProjectionError(
                f"{what}[{i}]：对形态未知（{type(item).__name__}，{repr(item)[:120]}）")
        if not isinstance(name, str) or not name:
            raise ProjectionError(f"{what}[{i}]：属性名非字符串/为空（{repr(name)[:80]}）")
        out[name] = val
    return out


def as_rgba(v):
    """颜色值 → [r,g,b,a]（不取整；None 原样；未知形态 raise）。"""
    if v is None:
        return None
    if isinstance(v, dict):
        missing = [k for k in ("r", "g", "b", "a") if k not in v]
        if missing:
            raise ProjectionError(f"color：四元 dict 缺键 {missing}")
        vals = [v["r"], v["g"], v["b"], v["a"]]
    elif isinstance(v, (list, tuple)) and len(v) == 4:
        vals = list(v)
    else:
        raise ProjectionError(f"color：形态未知（{type(v).__name__}，{repr(v)[:120]}）")
    return [float(x) for x in vals]


# ---------------------------------------------------------------------------
# 走查基元（engine.py 转写）
# ---------------------------------------------------------------------------

def mat4_from_trs(pos, rot, scale) -> np.ndarray:
    """Unity 四元数(x,y,z,w)+平移+缩放 → 4x4（行主序，右乘列向量）。[ally_recon:42]"""
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
    """PPtr → {"m_FileID","m_PathID"}。[ally_recon:60-63]"""
    if isinstance(p, dict):
        return {"m_FileID": p.get("m_FileID", 0), "m_PathID": p.get("m_PathID", 0)}
    return {"m_FileID": getattr(p, "m_FileID", 0), "m_PathID": getattr(p, "m_PathID", 0)}


def vec3(v):
    """Unity 序列化 Vector3 {"x","y","z"} → [x,y,z]；缺省/异形 → None。"""
    if isinstance(v, dict) and {"x", "y", "z"} <= set(v):
        return [float(v["x"]), float(v["y"]), float(v["z"])]
    return None


class PPtrError(Exception):
    """PPtr 解析失败（分类 reason 同 infra.resolve_asset_ref 口径）。"""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


# ---------------------------------------------------------------------------
# PPtr 解析器（原始 pairs；禁 env.container——必须保留 #2）
# ---------------------------------------------------------------------------

class _KitResolver:
    """kit 提取 PPtr 解析器（一 kit 一实例，bundle env 零驱逐）。

    语义转写自 infra.resolve_asset_ref.BundleStore._resolve_pptr（file_id==0 同
    owner SerializedFile→否则 externals[file_id-1] CAB 名→bundle_deps 闭包扫
    owner 包），container 面全部走原始 pairs。遥测/航线面不进来（supply 边界）。"""

    def __init__(self, win: Path, bundle_deps: dict[str, list[str]]):
        self.win = win
        self.bundle_deps = bundle_deps
        self._envs: dict[str, object] = {}
        self._sfs: dict[str, list] = {}          # bundle → [(cab, sf, {key: pid})]
        self._cabs_owner: dict[str, str] = {}
        self._cab_unreachable: set[str] = set()
        self.object_rows: list[tuple] = []       # 触达对象账（blob 产出物+root）
        self.container_rows: list[tuple] = []    # container 原始 pairs 账（主源包）

    def note_object(self, obj, bundle: str) -> None:
        """触达对象登记（bundle,cab,path_id,class_id,byte_start,byte_size）。"""
        cab = Path(str(getattr(getattr(obj, "assets_file", None), "name", ""))).name.lower()
        self.object_rows.append((bundle, cab, int(obj.path_id),
                                 int(getattr(obj.type, "value", 0) or 0),
                                 int(obj.byte_start), int(obj.byte_size)))

    def record_container(self, bundle: str) -> None:
        """包 container 原始 pairs 登记面（只对 prefab 主源包调——dep 共享包的
        container 归 portrait 域，不重复入账）。"""
        if any(r[0] == bundle for r in self.container_rows):
            return
        self.open_bundle(bundle)
        for cab, sf, _idx in self._sfs[bundle]:
            for i, (k, pid) in enumerate(container_pairs(sf)):
                self.container_rows.append((bundle, k, pid, i))

    def open_bundle(self, bundle: str):
        env = self._envs.get(bundle)
        if env is not None:
            return env
        path = self.win / bundle
        if not path.is_file():
            raise FileNotFoundError(f"bundle 不存在: {path}")
        env = load_bundle(path)
        self._envs[bundle] = env
        sfs = []
        for sf in iter_serialized(env):
            cab = Path(str(getattr(sf, "name", ""))).name.lower()
            idx: dict[str, int] = {}
            for k, pid in container_pairs(sf):
                kl = k.lower()
                idx.setdefault(kl, pid)
                idx.setdefault(kl.rsplit("/", 1)[-1], pid)
            sfs.append((cab, sf, idx))
            if cab:
                self._cabs_owner.setdefault(cab, bundle)
        self._sfs[bundle] = sfs
        return env

    def container_get(self, bundle: str, guid: str):
        """guid → ObjectReader|None（裸 GUID 精确键优先，endswith 退化）。"""
        self.open_bundle(bundle)
        g = guid.lower()
        for _cab, sf, idx in self._sfs[bundle]:
            pid = idx.get(g)
            if pid is not None:
                return sf.objects[pid]
        return None

    def resolve_pptr(self, cur_bundle: str, ptr: dict, owner_obj=None):
        """解 PPtr → (ObjectReader, 所在 bundle)；失败 PPtrError（分类面同款）。"""
        path_id = ptr.get("m_PathID", 0)
        if not path_id:
            raise PPtrError("empty_slot", "m_PathID == 0（空槽位）")
        file_id = ptr.get("m_FileID", 0)
        self.open_bundle(cur_bundle)
        if file_id == 0:                                   # 同 bundle 内引用
            own = getattr(owner_obj, "assets_file", None)
            if own is not None and path_id in own.objects:
                return own.objects[path_id], cur_bundle
            for _cab, sf, _idx in self._sfs[cur_bundle]:
                if path_id in sf.objects:
                    return sf.objects[path_id], cur_bundle
            raise PPtrError("missing_pathid", f"{cur_bundle} 内无 pathID {path_id}")
        # 外部引用：owner 的 SerializedFile externals 给出目标 CAB 名
        own = getattr(owner_obj, "assets_file", None)
        sfs = ([own] if own is not None else []) + \
              [sf for _c, sf, _i in self._sfs[cur_bundle]]
        candidates = []
        for sf in sfs:
            exts = list(getattr(sf, "externals", None) or [])
            if len(exts) >= file_id:
                candidates.append(Path(exts[file_id - 1].path).name.lower())
        target = next((c for c in candidates if c), None)
        if target is None:
            raise PPtrError("no_external", f"externals[{file_id - 1}] 不存在")
        if "unity default resources" in target or "unity_builtin_extra" in target:
            raise PPtrError("builtin", target)
        if target not in self._cabs_owner and target not in self._cab_unreachable:
            for dep in self.bundle_deps.get(cur_bundle, []):
                try:
                    self.open_bundle(dep)
                except Exception:                          # noqa: BLE001（缺包跳过续扫）
                    continue
                if target in self._cabs_owner:
                    break
            else:
                if target not in self._cabs_owner:
                    self._cab_unreachable.add(target)
        owner_bundle = self._cabs_owner.get(target)
        if owner_bundle is None:
            raise PPtrError(
                "missing_cab",
                f"CAB {target} 不在 {cur_bundle} 的依赖包中"
                f"（deps={len(self.bundle_deps.get(cur_bundle, []))}）")
        self.open_bundle(owner_bundle)
        for cab, sf, _idx in self._sfs[owner_bundle]:
            if cab == target and path_id in sf.objects:
                return sf.objects[path_id], owner_bundle
        raise PPtrError("missing_pathid", f"{owner_bundle}/{target} 无 pathID {path_id}")


# ---------------------------------------------------------------------------
# 走查引擎（engine.py Recon 转写；self.r=_KitResolver）
# ---------------------------------------------------------------------------

class KitRecon:
    """五帧族共享走查引擎 [ally_recon:90-317 逐字]；落盘面=内存字典（v3 同形）。"""

    def __init__(self, r: _KitResolver, bundle: str, *, uv1_mode: str | None = None,
                 color0: bool = False):
        self.r = r
        self.bundle = bundle
        self.uv1_mode = uv1_mode        # None | "uv0copy"(weapon/loc) | "zeros"(hero)
        self.color0 = color0            # hp/hero：mesh color0（VS o2 vCOLOR）
        self.mesh_jobs: list[dict] = []
        self.tex_saved: dict[tuple[str, int], dict] = {}
        self.textures: dict[str, object] = {}
        self.issues: list[str] = []
        self.actor_mt: dict | None = None
        self.actor_owner = None
        self.hierarchy: dict | None = None

    # ---------- 纹理（内存面+记录）[ally_recon:102-120] ----------
    def save_texture(self, t_reader, bundle: str) -> dict:
        key = (bundle, t_reader.path_id)
        if key in self.tex_saved:
            return self.tex_saved[key]
        tree = t_reader.read_typetree()
        info = {"name": tree.get("m_Name"), "bundle": bundle,
                "path_id": t_reader.path_id, "width": tree.get("m_Width"),
                "height": tree.get("m_Height"), "format": tree.get("m_TextureFormat")}
        fname = f"{info['name']}.png"
        try:
            self.textures[fname] = t_reader.read().image
            info["file"] = fname
            self.r.note_object(t_reader, bundle)
        except Exception as exc:  # noqa: BLE001
            info["file"] = None
            info["error"] = f"{type(exc).__name__}: {exc}"
        self.tex_saved[key] = info
        return info

    # ---------- 材质 [ally_recon:123-156] ----------
    def _shader_name(self, mt: dict, mbundle: str, owner) -> str | None:
        """材质 → 着色器身份名（m_ParsedForm.m_Name，37.0 序列化直读）。失败静默
        回 None（shader 面只作身份判据，不记 PPtr miss——引擎转写同口径）。"""
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
        info = {"name": mt.get("m_Name"), "bundle": mbundle,
                "path_id": m_reader.path_id, "shader": self._shader_name(mt, mbundle, m_reader),
                "tex": {}, "colors": {}, "floats": {}}
        saved = mt.get("m_SavedProperties", {})
        for first, sec in as_pairs(saved.get("m_TexEnvs"), what="m_TexEnvs").items():
            sec = sec or {}
            tptr = ptr_dict(sec.get("m_Texture") or {})
            sc_, of = sec.get("m_Scale") or {}, sec.get("m_Offset") or {}
            slot = {"scale": [sc_.get("x", 1), sc_.get("y", 1)],
                    "offset": [of.get("x", 0), of.get("y", 0)]}
            if tptr.get("m_PathID"):
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

    # ---------- 网格 [ally_recon:159-174；uv1/color0=weapon/hp/hero 增量] ----------
    def extract_mesh(self, mesh_reader, mbundle: str) -> dict | None:
        try:
            self.r.note_object(mesh_reader, mbundle)
            mesh = mesh_reader.read()
            h = MeshHandler(mesh)
            h.process()
            verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
            uv0 = np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0 \
                else np.zeros((len(verts), 2))
            # 法线：流式网格（m_StreamData）的 m_Normals 访问可能抛错——只降级法线
            # 不丢 verts/uv0（2026-10-23 协调者修；Gem_Attack 流式网格判例）。
            try:
                normals = (np.array(h.m_Normals, dtype=np.float64).reshape(-1, 3)
                           if h.m_Normals else np.zeros((len(verts), 3)))
            except Exception:  # noqa: BLE001
                normals = np.zeros((len(verts), 3))
            if self.uv1_mode == "uv0copy":
                uv1 = np.array(h.m_UV1, dtype=np.float64).reshape(-1, 2) if h.m_UV1 \
                    else uv0.copy()
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
                tris_per_sub.append(np.array([t for t in sub if len(t) == 3],
                                             dtype=np.int32))
            out = {"name": mesh.m_Name, "verts": verts, "uv0": uv0, "normals": normals,
                   "submeshes": tris_per_sub,
                   "bbox_min": verts.min(axis=0).tolist(),
                   "bbox_max": verts.max(axis=0).tolist(),
                   "bundle": mbundle, "path_id": mesh_reader.path_id}
            if uv1 is not None:
                out["uv1"] = uv1
            if color0 is not None:
                out["color0"] = color0
            return out
        except Exception as exc:  # noqa: BLE001
            self.issues.append(f"mesh {getattr(mesh_reader, 'path_id', '?')}: "
                               f"{type(exc).__name__}: {exc}")
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
                self.issues.append(f"{node_path} 组件 {pd['m_PathID']}: {exc.reason}")
                continue
            ctype = cobj.type.name
            ctree = cobj.read_typetree()
            if ctype == "Transform":
                transform = ctree
                transform_obj = cobj
                p, q, s = (ctree["m_LocalPosition"], ctree["m_LocalRotation"],
                           ctree["m_LocalScale"])
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
                    keys = sorted(k for k in ctree.keys() if k.startswith("m_")) \
                        if isinstance(ctree, dict) else []
                    node["mono_unknown"].append({"path_id": cobj.path_id,
                                                 "m_keys": keys[:24]})
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
                        entry.update({"name": t.get("m_Name"), "type": o.type.name,
                                      "bundle": b})
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


# ---------------------------------------------------------------------------
# kit 编排（kits.py:_extract_kit 转写；atlas/races/trinket 三域排除记账）
# ---------------------------------------------------------------------------

def _extract_kit_now(win: Path, *, frame: str, spec: dict, actor_ref: str, guid: str,
                     bundle: str, card_id: str | None, dbf_id: int | None,
                     bundle_deps: dict[str, list[str]],
                     cache_root: Path | None = None,
                     strings_txt: Path | None = None) -> dict:
    """单 kit 全提取→六面编码产物（进程内；worker 与 verify 冷腿共用）。

    cache_root 给了即写 blob（build 面）；None=纯提取（verify 冷腿）。
    A6：strings_txt 给了且 spec races=True → races 面随 kit 落库（GLOBAL.txt
    文本提取，零 UnityPy）；mesh_refs 面恒捕获（walk 期 mesh_jobs 同式）。
    返回 {frame, ok, error?, faces 账（payload/内容 sha+尺寸+纹理像素账）, counts,
    issues, excluded, container_rows, object_rows, root 地址}——全 picklable
    （ndarray/PIL 不出进程，blob 字节 worker 内写盘）。"""
    resolver = _KitResolver(win, bundle_deps)
    root_go = resolver.container_get(bundle, guid)
    if root_go is None:
        return {"frame": frame, "ok": False,
                "error": f"prefab guid {guid} 不在 {bundle} container",
                "faces": {}, "counts": {}, "issues": [],
                "excluded": dict(EXCLUDED_FACES),
                "container_rows": [], "object_rows": []}
    rec = KitRecon(resolver, bundle, uv1_mode=spec["uv1"], color0=spec["color0"])
    hierarchy = rec.walk(root_go, "", "root")
    rec.hierarchy = hierarchy

    # ---- 世界变换自底向上 + 根归零 [ally_recon:394-410] ----
    def assign_world(node, parent_m):
        M = mat4_from_trs(**{k: node["local"][k] for k in ("pos", "rot", "scale")}) \
            if node["local"] else np.eye(4)
        node["world"] = (parent_m @ M).tolist()
        for ch in node["children"]:
            assign_world(ch, np.array(node["world"]))

    raw_root = None
    if hierarchy.get("local"):
        raw_root = dict(hierarchy["local"])
        if spec["root"] == "full":
            hierarchy["local"] = {"pos": [0.0, 0.0, 0.0],
                                  "rot": [0.0, 0.0, 0.0, 1.0],
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
                                  "bbox_min": mesh["bbox_min"],
                                  "bbox_max": mesh["bbox_max"]}
        for ch in node["children"]:
            collect(ch)

    collect(hierarchy)

    # ---- Actor 绑定 + extra Mesh [ally_recon:432-449] ----
    actor = rec.finalize_actor(rec.actor_owner)
    alt_cost = vec3((rec.actor_mt or {}).get("m_alternateCostTextLocalPos"))
    extra = {}
    if spec["extra_meshes"]:
        for field_name, e in actor.get("object_refs", {}).items():
            if e.get("type") != "Mesh" or not e.get("bundle"):
                continue
            mesh = _extract_mesh_from_bundle(resolver, e["bundle"], e["path_id"])
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

    meta = {"prefab_ref": actor_ref, "bundle": bundle, "guid": guid,
            "dbf_id": dbf_id, "card_id": card_id,
            "root_translation_neutralized": {
                "raw_root_pos": (raw_root or {}).get("pos"),
                "reason": "prefab 根位置=场景摆位残留；游戏区域布局覆写根位置；"
                          "canonical 快照位姿=恒等根（Ability 帧原点+E7 实证）",
            },
            "extra_meshes": extra,
            "actor_alt_cost_pos": alt_cost}

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
                        texs[prop] = {"name": texobj.get("name"),
                                      "bundle": texobj.get("bundle")}
                slots.append({"slot": i, "name": mat["name"], "textures": texs})
            comp["renderer"] = {"material_slots": slots}
        if n.get("ubertext"):
            comp["TextComponent"] = {"path_id": n["ubertext"]["path_id"],
                                     "font_name": n["ubertext"].get("font_name"),
                                     "font_pptr": n["ubertext"].get("font_pptr")}
        rnodes.append({"path": n["path"], "go_path_id": n["go_path_id"],
                       "components": comp})
    root_name = actor_ref.split(".")[0]
    report = {
        "prefab": {"name": root_name, "ref": actor_ref, "guid": guid,
                   "bundle": bundle},
        "class_atlas": {"ref": None,
                        "note": "全槽图集由 probe 驱动另落（本字段为采样槽记账）；"
                                "supply kit 面=材质 deref 纹理，类色图集=车1 排除域"},
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
    ubertext = {"ref": actor_ref, "bundle": bundle, "n_ubertext": len(unodes),
                "nodes": unodes}

    return _encode_kit_faces(
        frame=frame, meta=meta, hierarchy=hierarchy, report=report,
        ubertext=ubertext, arrays=arrays, textures=rec.textures,
        tex_saved=rec.tex_saved, prefab_bundle=bundle,
        root_go=root_go,
        issues=rec.issues, resolver=resolver, cache_root=cache_root,
        hierarchy_for_gems=hierarchy, textures_for_gems=rec.textures,
        races=races_face(strings_txt) if (spec.get("races") and strings_txt) else None,
        mesh_refs={m["mesh"]["name"]: (m["bundle"], int(m["mesh_obj"].path_id))
                   for m in rec.mesh_jobs})


def _extract_mesh_from_bundle(r: _KitResolver, bundle: str, path_id: int) -> dict | None:
    """[ally_recon:320-341] extra mesh 提取（bundle+path_id 直取）。"""
    r.open_bundle(bundle)
    for _cab, sf, _idx in r._sfs[bundle]:
        if path_id in sf.objects:
            obj = sf.objects[path_id]
            if obj.type.name != "Mesh":
                return None
            r.note_object(obj, bundle)
            try:
                mesh = obj.read()
                h = MeshHandler(mesh)
                h.process()
                verts = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
                uv0 = np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0 \
                    else np.zeros((len(verts), 2))
                subs = [np.array([t for t in sub if len(t) == 3], dtype=np.int32)
                        for sub in h.get_triangles()]
                return {"name": mesh.m_Name, "verts": verts, "uv0": uv0,
                        "submeshes": subs,
                        "bbox_min": verts.min(axis=0).tolist(),
                        "bbox_max": verts.max(axis=0).tolist(),
                        "bundle": bundle, "path_id": path_id}
            except Exception as exc:  # noqa: BLE001
                logger.warning("[extra mesh fail] %s: %s", path_id, exc)
                return None
    return None


# ---------------------------------------------------------------------------
# 六面编码 + blob 落盘（worker 内完成；内容身份=解析后产物 sha）
# ---------------------------------------------------------------------------

def _encode_kit_faces(*, frame: str, meta: dict, hierarchy: dict, report: dict,
                      ubertext: dict, arrays: dict, textures: dict,
                      tex_saved: dict, prefab_bundle: str, root_go,
                      issues: list, resolver: _KitResolver,
                      cache_root: Path | None = None,
                      hierarchy_for_gems: dict | None = None,
                      textures_for_gems: dict | None = None,
                      races: dict | None = None,
                      mesh_refs: dict | None = None) -> dict:
    """六面编码：JSON 四面 canonical bytes / arrays NPZ / 纹理 PNG；cache_root 给了
    即写 blob（内容寻址）。content sha 全部=解析后产物 sha（m_StreamData 判例）。

    A6 扩展面：races / mesh_refs 两张 JSON 面可选落库（kit_codec.
    EXTRA_JSON_FACES；content sha 并入 kit_content_sha 聚合——缺席=空串进键，
    「无面」与「面内容 X」构造性不同键）。faces 账带 blob rel（worker 直读面）。

    gems 域挂接（P2 车2）：ally 帧（HAND_MINION prefab=gems.py 域配方源）附 gem
    选择+PNG 编码（单走查单源——gem 纹理=本走查 renderers 槽的 file 名查图）；
    account 只出 JSON 可序列化面（PIL 不出进程）。"""
    kit_struct = {"meta": meta, "hierarchy": hierarchy, "report": report,
                  "ubertext": ubertext, "arrays": arrays, "textures": textures}
    from eidolon.core.supply_index.cold import _write_blob_atomic

    faces: dict = {}
    for face, obj in (("meta", meta), ("hierarchy", hierarchy),
                      ("report", report), ("ubertext", ubertext)):
        data = KC.encode_json_face(obj)
        payload_sha = S.sha256_hex(data)
        faces[face] = {"payload_sha256": payload_sha, "size": len(data),
                       "content_sha256": payload_sha}
        if cache_root is not None:
            rel, _fresh = _write_blob_atomic(cache_root, payload_sha, data,
                                             ext=".json")
            faces[face]["blob"] = rel

    # ---- A6 扩展面（races/mesh_refs；可选，缺席不落 faces 键） ----
    for face, obj in (("races", races), ("mesh_refs", mesh_refs)):
        if obj is None:
            continue
        data = KC.encode_json_face(obj)
        payload_sha = S.sha256_hex(data)
        faces[face] = {"payload_sha256": payload_sha, "size": len(data),
                       "content_sha256": payload_sha}
        if cache_root is not None:
            rel, _fresh = _write_blob_atomic(cache_root, payload_sha, data,
                                             ext=".json")
            faces[face]["blob"] = rel

    arr_shas = {k: KC.array_content_sha(k, v) for k, v in arrays.items()}
    arrays_sha = KC.arrays_content_sha(arr_shas)
    npz = KC.encode_npz(arrays) if arrays else b""
    npz_sha = S.sha256_hex(npz) if npz else ""
    faces["arrays"] = {"payload_sha256": npz_sha, "size": len(npz),
                       "content_sha256": arrays_sha, "array_shas": arr_shas,
                       "keys": sorted(arrays)}
    if npz and cache_root is not None:
        rel, _fresh = _write_blob_atomic(cache_root, npz_sha, npz, ext=".npz")
        faces["arrays"]["blob"] = rel

    tex_accounts: dict[str, dict] = {}
    file_info = {info["file"]: info for info in tex_saved.values()
                 if info.get("file")}
    for fname, img in textures.items():
        pixel_sha = S.sha256_hex(img.tobytes())
        png = KC.encode_png(img)
        payload_sha = S.sha256_hex(png)
        src_info = file_info.get(fname) or {}
        acc = {"pixel_sha256": pixel_sha, "payload_sha256": payload_sha,
               "size": len(png), "width": img.width, "height": img.height,
               "mode": img.mode,
               "source": {"bundle": src_info.get("bundle"),
                          "path_id": src_info.get("path_id")}}
        if cache_root is not None:
            rel, _fresh = _write_blob_atomic(cache_root, payload_sha, png,
                                             ext=".png")
            acc["blob"] = rel
        tex_accounts[fname] = acc
    faces["textures"] = tex_accounts

    kit_sha = KC.kit_content_sha(
        meta_sha=faces["meta"]["content_sha256"],
        hierarchy_sha=faces["hierarchy"]["content_sha256"],
        report_sha=faces["report"]["content_sha256"],
        ubertext_sha=faces["ubertext"]["content_sha256"],
        arrays_sha=arrays_sha,
        texture_pixel_shas={k: v["pixel_sha256"] for k, v in tex_accounts.items()},
        races_sha=faces.get("races", {}).get("content_sha256", ""),
        mesh_refs_sha=faces.get("mesh_refs", {}).get("content_sha256", ""))

    n_nodes = sum(1 for _ in _iter_nodes(hierarchy))
    if root_go is not None:
        resolver.note_object(root_go, prefab_bundle)
        resolver.record_container(prefab_bundle)
    out = {"frame": frame, "ok": True, "error": None,
           "prefab_bundle": prefab_bundle,
           "root_path_id": int(root_go.path_id) if root_go is not None else 0,
           "faces": faces, "kit_content_sha": kit_sha,
           "counts": {"nodes": n_nodes, "arrays": len(arrays),
                      "textures": len(tex_accounts),
                      "ubertext": len(ubertext["nodes"]),
                      "issues": len(issues)},
           "issues": issues,
           "excluded": dict(EXCLUDED_FACES),
           "container_rows": resolver.container_rows,
           "object_rows": resolver.object_rows}

    # ---- gems 域挂接（ally 帧=HAND_MINION prefab；gems.py 域配方选择器） ----
    if frame == "ally" and hierarchy_for_gems is not None:
        from eidolon.core.supply_index import gems_codec as GC

        from eidolon.core.supply_index.cold import _write_blob_atomic

        found, gem_issues = GC.select_gems(hierarchy_for_gems, textures_for_gems)
        gem_acc: dict[str, dict] = {}
        for gem, sel in found.items():
            img = sel["img"]
            pixel_sha = S.sha256_hex(img.tobytes())
            png = KC.encode_png(img)
            payload_sha = S.sha256_hex(png)
            acc = GC.gem_accounts({gem: sel})[gem]
            acc.update({"payload_sha256": payload_sha, "size": len(png)})
            if cache_root is not None:
                rel, _fresh = _write_blob_atomic(cache_root, payload_sha, png,
                                                 ext=".png")
                acc["blob"] = rel
            gem_acc[gem] = acc
        out["gems"] = gem_acc
        out["gem_issues"] = gem_issues

    if cache_root is None:
        # verify 冷腿：内存结构随结果带回（比对器输入；build 面不带回——免 pickle
        # 大件，ndarray/PIL 只住 worker）
        out["struct"] = kit_struct
    return out


def _iter_nodes(node):
    yield node
    for c in node["children"]:
        yield from _iter_nodes(c)


def extract_kit_worker(payload):
    """进程池入口：单 kit 提取+编码+blob 落盘（包级异常整 kit 报错——建库禁静默）。
    payload 尾元=strings_txt（A6 races 面；None=不提——verify 冷腿无 strings 面）。"""
    (win_s, cache_root_s, frame, spec, actor_ref, guid, bundle, card_id, dbf_id,
     bundle_deps, strings_txt_s) = payload
    try:
        out = _extract_kit_now(
            Path(win_s), frame=frame, spec=spec, actor_ref=actor_ref, guid=guid,
            bundle=bundle, card_id=card_id, dbf_id=dbf_id, bundle_deps=bundle_deps,
            cache_root=Path(cache_root_s) if cache_root_s else None,
            strings_txt=Path(strings_txt_s) if strings_txt_s else None)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"frame": frame, "ok": False,
                "error": f"{type(exc).__name__}: {exc}", "faces": {},
                "counts": {}, "issues": [], "excluded": dict(EXCLUDED_FACES),
                "container_rows": [], "object_rows": []}


# ---------------------------------------------------------------------------
# 卡→帧族解析（verify 覆盖面用；dbf CARD_TAG × GetHandActor 槽位分派转写）
# ---------------------------------------------------------------------------

def read_card_types_by_dbf(win: Path) -> dict[int, int]:
    """dbf CARD_TAG → {dbf_id: TAG_CARDTYPE 值}（verify 覆盖面解析；
    CARD_TAG=平表 m_cardId×m_tagId×m_tagValue，单遍过滤 CARDTYPE）。"""
    from eidolon.core.infra.game_tag import GameTag

    tag_cardtype = int(GameTag.CARDTYPE)
    env = load_bundle(win / "dbf.unity3d")
    sf = next(iter_serialized(env))
    pairs = {k: pid for k, pid in container_pairs(sf)}
    key = next(k for k in pairs if k.upper().endswith("CARD_TAG.ASSET"))
    recs = sf.objects[pairs[key]].read_typetree()["Records"]
    out: dict[int, int] = {}
    for r in recs:
        if int(r["m_tagId"]) == tag_cardtype:
            cid = r.get("m_cardId")
            if cid is not None:
                out[int(cid)] = int(r["m_tagValue"])
    return out
