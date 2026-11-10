"""kit_codec — frame_kit 六面 codec + 非纹理内容身份原则（本包 UnityPy-free 面）。

六面（对齐本仓 eidolon/core/supply/frames/kits.py kit() 产物；hierarchy 自 meta 分立成面）::

    meta / hierarchy / report / ubertext  → canonical JSON（S.cjson：sort_keys+紧凑分隔）
    arrays                                → NPZ 一件（全 ndarray；确定性 zip：ZipInfo 1980）
    textures                              → PNG 一件/纹理（复用 P1 blob 面，payload_sha 寻址）

**非纹理内容身份原则（P2 车1 核心判据；m_StreamData 判例）**：一切 content sha=
**解析后产物 sha**，禁 raw 序列化字节 sha——
  - JSON 面：canonical 字节 sha（canonical 形即解析产物的规范序列化）；
  - arrays：逐数组内容 sha=sha256(f"{key}|{dtype}|{shape}|{C-contig tobytes}")，
    面内容=聚合 sha（canonical JSON of {key: arr_sha}）；NPZ 容器字节只是存储
    形态（mesh 顶点住 .resS 流，序列化对象字节只有 ~208B 头——raw sha 是假身份）；
  - 纹理：解码像素 sha（img.tobytes()；Texture2D 像素在 .resS，raw 字节是头）。

item_key 的 content_inputs.kit=六面内容聚合 sha（kit_content_sha）——任何面内容变化
即换键（必须保留 #6 的结构物实现）。

warm 重组（decode_kit）：JSON+NPZ+PNG→kit dict（dict/ndarray/PIL），零 UnityPy、
零游戏文件——本模块 import 面=stdlib+numpy+PIL+本包 schema（audit blocker 机器
证明的通过面）。
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Callable

import numpy as np
from PIL import Image

from eidolon.core.supply_index import schema as S

KIT_CODEC = "kit"
# KIT_CODEC_VERSION 2（Phase 1 A6）：kit faces 扩 races/mesh_refs 两张 JSON 面
# （kit 内容聚合 sha 并入——任何一面内容变化即换 item 键）。decode 形不变
# （decode_kit 仍只重组 JSON_FACES 六面 + arrays/textures；races/mesh_refs 由
# warm 专属访问器 kit_races/kit_mesh_refs 供货——seed 侧组装 live Kit 的
# races/mesh_refs 属性）。schema.kit_item_key 的 codec_version 字面量与本值
# 同步（schema 不 import 本模块防循环；单测钉死两处相等）。
KIT_CODEC_VERSION = 2
NPZ_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
"""确定性 zip 时间戳（np.savez 依赖 numpy 的 ZipFile 默认值——显式自写不随实现漂）。"""

JSON_FACES = ("meta", "hierarchy", "report", "ubertext")
# A6 扩展面（JSON）：races=种族串账（ally/ally_premium/trinket——live spec
# races=True 帧族）、mesh_refs=网格名→(bundle, path_id) 结构引用账（全帧族）。
# 两面可选（缺席=None/{} 语义随帧族）；blob role 同名，blob_key 公式复用。
EXTRA_JSON_FACES = ("races", "mesh_refs")
# blob codec → 文件 ext（包级映射；P2 车2 增 ttf——字体文件字节即产物；
# A6 supp 域增 bin——任意字节面（fonts_bytes 等，按文件 sha 寻址））
BLOB_CODEC_EXT = {"png": ".png", "json": ".json", "npz": ".npz", "ttf": ".ttf",
                  "bin": ".bin"}


# ---------------------------------------------------------------------------
# 内容身份（解析后产物 sha；单测回归面=tests/test_content_identity.py）
# ---------------------------------------------------------------------------

def json_face_sha(obj) -> str:
    """JSON 面 content sha=canonical 字节 sha。"""
    return S.sha256_hex(cjson_bytes(obj))


def cjson_bytes(obj) -> bytes:
    return S.cjson(obj).encode("utf-8")


def array_content_sha(key: str, arr: np.ndarray) -> str:
    """单数组内容 sha：键|dtype|shape|C-contig 字节——raw 序列化字节（m_StreamData
    判例）与容器编码（NPZ zip 字节）都不进来。"""
    a = np.ascontiguousarray(arr)
    h = hashlib.sha256()
    h.update(f"{key}|{a.dtype.str}|{a.shape}".encode("utf-8"))
    h.update(a.tobytes())
    return h.hexdigest()


def arrays_content_sha(arr_shas: dict[str, str]) -> str:
    """arrays 面聚合内容 sha=canonical JSON of {key: arr_sha}。"""
    return S.sha256_hex(cjson_bytes(dict(sorted(arr_shas.items()))))


def kit_content_sha(*, meta_sha: str, hierarchy_sha: str, report_sha: str,
                    ubertext_sha: str, arrays_sha: str,
                    texture_pixel_shas: dict[str, str],
                    races_sha: str = "", mesh_refs_sha: str = "") -> str:
    """六面内容聚合 sha（item content_inputs.kit；任何面变化即换键）。

    A6：races/mesh_refs 两扩展面并入聚合（缺面=空串——缺席也是身份输入，
    「该帧族无 races 面」与「races 内容 X」是不同键）。"""
    return S.sha256_hex(cjson_bytes({
        "meta": meta_sha, "hierarchy": hierarchy_sha, "report": report_sha,
        "ubertext": ubertext_sha, "arrays": arrays_sha,
        "textures": dict(sorted(texture_pixel_shas.items())),
        "races": races_sha, "mesh_refs": mesh_refs_sha,
    }))


def blob_key(*, face: str, content_sha: str, blob_codec: str) -> str:
    """kit 面 blob_key=sha256(kit/<face>|content_sha|blob_codec|<KIT_CODEC_VERSION>|)。

    texture 面的 content_sha=像素 sha→跨 kit 同内容同 blob 行（内容寻址去重）；
    JSON 面 content=canonical bytes sha（=payload）；arrays 面 content=聚合数组 sha；
    races/mesh_refs 面 content=canonical bytes sha（A6 扩展面同公式）。"""
    return S.sha256_hex(
        f"kit/{face}|{content_sha}|{blob_codec}|{KIT_CODEC_VERSION}|".encode("utf-8"))


# ---------------------------------------------------------------------------
# encode（cold 调用）：六面 → 落盘字节
# ---------------------------------------------------------------------------

def encode_json_face(obj) -> bytes:
    """JSON 面落盘字节=canonical 形（content=整字节 sha，读回 json.loads 即还原）。"""
    return cjson_bytes(obj)


def encode_npz(arrays: dict[str, np.ndarray]) -> bytes:
    """全数组 → 单 NPZ（确定性 zip：条目序=键排序、时间戳固定、ZIP_STORED）。
    空数组面 → b""（无 blob——无 mesh 的 kit 合法，faces.arrays.payload 为空串）。"""
    if not arrays:
        return b""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_STORED) as zf:
        for name in sorted(arrays):
            zi = zipfile.ZipInfo(name + ".npy", date_time=NPZ_ZIP_DATE)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = 0o644 << 16
            abuf = io.BytesIO()
            np.lib.format.write_array(abuf, np.ascontiguousarray(arrays[name]),
                                      allow_pickle=False)
            zf.writestr(zi, abuf.getvalue())
    return bio.getvalue()


def decode_npz(data: bytes) -> dict[str, np.ndarray]:
    """NPZ → {key: ndarray}（np.load 面；键序=zip 条目序）。"""
    with np.load(io.BytesIO(data), allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def encode_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# decode（warm 调用）：blobs → kit dict（六面；零 UnityPy）
# ---------------------------------------------------------------------------

def decode_kit(manifest: dict, blob_bytes: Callable[[str], bytes],
               *, verify_content: bool = True, decode_threads: int = 1) -> dict:
    """kit item → 六面内存 kit（meta/hierarchy/report/ubertext=dict、arrays={key:
    ndarray}、textures={fname: PIL}）。

    blob_bytes(role)→该 role 的 blob 字节（warm 面 blob 文件读取由调用方注入——
    本函数零 IO 语义、零游戏面）。verify_content=True 逐面核内容 sha（JSON 面
    payload sha、arrays 逐数组内容 sha、纹理逐像素 sha）——mismatch 响亮
    （KitContentError）：派生物可删重建但不许坏。

    decode_threads>1：纹理面（读 blob+PNG 解码）走线程池并行——PIL 解码在 C 层
    放 GIL，实测 28 纹理 68→22ms@4 线程（T3 warm-perf：首 kit 装配大头=PNG 解码
    逐张串行）；结果序=输入序（ex.map 保序），逐字段一致面不变。verify/单测缺省
    1=串行（行为与历史逐位一致）。"""
    faces = manifest["faces"]
    out: dict = {}
    for face in JSON_FACES:
        data = blob_bytes(face)
        if verify_content and S.sha256_hex(data) != faces[face]["payload_sha256"]:
            raise KitContentError(f"{face}: canonical bytes sha 失配")
        out[face] = json.loads(data.decode("utf-8"))
    fa = faces.get("arrays") or {}
    arr_data = blob_bytes("arrays") if fa.get("payload_sha256") else b""
    if arr_data and verify_content and \
            S.sha256_hex(arr_data) != fa["payload_sha256"]:
        raise KitContentError("arrays: NPZ payload sha 失配")
    arrays = decode_npz(arr_data) if arr_data else {}
    if verify_content:
        want = faces["arrays"]["array_shas"]
        if set(arrays) != set(want):
            raise KitContentError(
                f"arrays: 键面失配（缺 {sorted(set(want)-set(arrays))[:4]}"
                f" 多 {sorted(set(arrays)-set(want))[:4]}）")
        for k, arr in arrays.items():
            if array_content_sha(k, arr) != want[k]:
                raise KitContentError(f"arrays[{k}]: 数组内容 sha 失配（假内容身份面）")
    out["arrays"] = arrays

    def _decode_texture(item: tuple[str, dict]) -> tuple[str, Image.Image]:
        fname, finfo = item
        data = blob_bytes(f"texture:{fname}")
        if verify_content and S.sha256_hex(data) != finfo["payload_sha256"]:
            raise KitContentError(f"texture {fname}: PNG payload sha 失配")
        img = Image.open(io.BytesIO(data))
        img.load()
        if verify_content and S.sha256_hex(img.tobytes()) != finfo["pixel_sha256"]:
            raise KitContentError(f"texture {fname}: 解码像素 sha 失配")
        return fname, img

    tex_items = list((faces.get("textures") or {}).items())
    textures: dict[str, Image.Image] = {}
    if decode_threads > 1 and len(tex_items) > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=decode_threads) as ex:
            for fname, img in ex.map(_decode_texture, tex_items):
                textures[fname] = img
    else:
        for item in tex_items:
            fname, img = _decode_texture(item)
            textures[fname] = img
    out["textures"] = textures
    return out


class KitContentError(RuntimeError):
    """kit blob 内容失配（fail loud；派生物可删重建但不许坏）。"""


# ---------------------------------------------------------------------------
# 比对器（verify 冷暖一致）：逐字段、逐节点、逐数组、逐 sha
# ---------------------------------------------------------------------------

def _walk_nodes(node, path: str = ""):
    """hierarchy 先序遍历 → [(path, node)]（比对计数轴；与 extract 侧 iter_nodes 同序）。"""
    p = node.get("path", path)
    yield p, node
    for ch in node.get("children", []):
        yield from _walk_nodes(ch, p)


def compare_kit(cold: dict, warm: dict) -> dict:
    """cold 提取六面 vs warm 重组六面 逐字段比对。

    返回 {ok, mismatches[], counts:{json_faces, nodes, arrays, textures}}：
    - hierarchy 逐节点：path/name/go_path_id/local/world/mesh_stats/ubertext 存在性/
      renderers（材质名+shader+槽纹理名）逐字段相等；
    - arrays 逐数组：键集+dtype+shape+内容 sha；
    - textures 逐 sha：文件名集+像素 sha；
    - JSON 面（meta/report/ubertext/hierarchy 整树）：canonical 字节 sha 相等
      （canonical 序列化对 dict 内容单射——整面 sha 相等=逐字段相等）。"""
    bad: list[str] = []
    counts = {"json_faces": 0, "nodes": 0, "arrays": 0, "textures": 0}

    for face in JSON_FACES:
        counts["json_faces"] += 1
        if json_face_sha(cold[face]) != json_face_sha(warm[face]):
            bad.append(f"{face}: canonical sha mismatch")

    cn, wn = list(_walk_nodes(cold["hierarchy"])), list(_walk_nodes(warm["hierarchy"]))
    if len(cn) != len(wn):
        bad.append(f"hierarchy: 节点数失配 cold={len(cn)} warm={len(wn)}")
    for (cp, c), (_wp, w) in zip(cn, wn):
        counts["nodes"] += 1
        for f in ("name", "go_path_id", "path", "local", "world", "mesh_stats",
                  "ubertext", "active_self", "active_in_hierarchy"):
            if c.get(f) != w.get(f):
                bad.append(f"node {cp}: {f} mismatch")
        cr = [(m or {}).get("name") if m else None
              for r in c.get("renderers", []) for m in r.get("materials", [])]
        wr = [(m or {}).get("name") if m else None
              for r in w.get("renderers", []) for m in r.get("materials", [])]
        if cr != wr:
            bad.append(f"node {cp}: renderer material names mismatch")

    ca, wa = cold["arrays"], warm["arrays"]
    if set(ca) != set(wa):
        bad.append(f"arrays: 键集失配（cold-only {sorted(set(ca)-set(wa))[:4]} "
                   f"warm-only {sorted(set(wa)-set(ca))[:4]}）")
    for k in sorted(set(ca) & set(wa)):
        counts["arrays"] += 1
        if array_content_sha(k, ca[k]) != array_content_sha(k, wa[k]):
            bad.append(f"arrays[{k}]: 内容 sha mismatch")

    ct = cold["textures"]
    wt = warm["textures"]
    if set(ct) != set(wt):
        bad.append(f"textures: 文件名集失配（cold-only {sorted(set(ct)-set(wt))[:4]} "
                   f"warm-only {sorted(set(wt)-set(ct))[:4]}）")
    for fname in sorted(set(ct) & set(wt)):
        counts["textures"] += 1
        if S.sha256_hex(ct[fname].tobytes()) != S.sha256_hex(wt[fname].tobytes()):
            bad.append(f"texture {fname}: 像素 sha mismatch")

    return {"ok": not bad, "mismatches": bad[:20], "counts": counts}
