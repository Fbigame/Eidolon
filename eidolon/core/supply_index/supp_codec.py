"""supp_codec — supplement 域 parts codec（A6；本包 UnityPy-free 面）。

supplement item 的值面=live 域函数产物内存对象（AbilityKit/BadgesKit/BtfKit/
OrnamentsKit/ndarray dict/JSON dict——见 supplement_extract）。存储形=**命名
parts 束**，四 kind：

    json  → 单 canonical JSON blob（dict；content=payload 字节 sha）
    npz   → 单确定性 NPZ blob（{key: ndarray}；content=聚合数组 sha，kit_codec 同式）
    png   → 多 PNG blob（{fname: PIL}；content=逐文件像素 sha 聚合）
    bin   → 多裸字节 blob（{fname: bytes}；content=逐文件字节 sha 聚合）

manifest.parts 账::

    {"<part>": {"kind": "json"|"npz", "payload_sha256": …, "size": …,
                "content_sha256": …}
     | {"kind": "png"|"bin", "files": {fname: {"payload_sha256": …,
        "size": …, "content_sha256": …}}}}

blob role：json/npz=part 名；png/bin=f"{part}:{fname}"。item content_inputs 的
聚合 sha=canonical JSON of {part: 内容身份}（encode_parts 产、supplement_
content_sha 复推）——任何 part 内容变化即换键（必须保留 #6）。

本模块 import 面=stdlib+numpy+PIL+schema+kit_codec（blob ext 表复用）——warm/
seed 侧可安全 import（audit blocker 通过面）。decode 只做字节→内存产物复原，
不重组 live 对象（Kit/AbilityKit 等形状重组归 seed 转换件——warm 面禁 import
supply 包）。
"""
from __future__ import annotations

import io
import json
from typing import Callable

import numpy as np
from PIL import Image

from eidolon.core.supply_index import kit_codec as KC
from eidolon.core.supply_index import schema as S

SUPP_CODEC = "supp"
SUPP_CODEC_VERSION = 1
PART_KINDS = ("json", "npz", "png", "bin")


# ---------------------------------------------------------------------------
# encode（cold worker 调用）：内存产物 → parts 账 + 落盘字节
# ---------------------------------------------------------------------------

def encode_parts(value: dict, *, write_blob: Callable[[bytes, str, str], str]
                 ) -> tuple[dict, dict[str, str]]:
    """内存 parts 值 → (parts 账, {role: payload_sha})。

    write_blob(payload_bytes, ext, content_sha) → blob rel（cold 侧内容寻址落盘
    注入——本函数零 IO 语义）。value 形见模块 docstring 四 kind；空 dict part
    （textures={} 等）照常落账（png/bin 零文件=合法缺席形态）。"""
    parts: dict = {}
    payload_shas: dict[str, str] = {}
    for name, val in value.items():
        if isinstance(val, dict) and val and \
                all(isinstance(v, Image.Image) for v in val.values()):
            files: dict = {}
            for fname, img in val.items():
                png = KC.encode_png(img)
                psha = S.sha256_hex(png)
                csha = S.sha256_hex(img.tobytes())
                rel = write_blob(png, ".png", csha)
                files[fname] = {"payload_sha256": psha, "size": len(png),
                                "content_sha256": csha, "blob": rel}
                payload_shas[f"{name}:{fname}"] = psha
            parts[name] = {"kind": "png", "files": files}
        elif isinstance(val, dict) and val and \
                all(isinstance(v, (bytes, bytearray)) for v in val.values()):
            files = {}
            for fname, raw in val.items():
                psha = S.sha256_hex(raw)
                rel = write_blob(bytes(raw), KC.BLOB_CODEC_EXT["bin"], psha)
                files[fname] = {"payload_sha256": psha, "size": len(raw),
                                "content_sha256": psha, "blob": rel}
                payload_shas[f"{name}:{fname}"] = psha
            parts[name] = {"kind": "bin", "files": files}
        elif isinstance(val, dict) and val and \
                all(isinstance(v, np.ndarray) for v in val.values()):
            arr_shas = {k: KC.array_content_sha(k, v) for k, v in val.items()}
            csha = KC.arrays_content_sha(arr_shas)
            npz = KC.encode_npz(val)
            psha = S.sha256_hex(npz)
            rel = write_blob(npz, ".npz", csha)
            parts[name] = {"kind": "npz", "payload_sha256": psha,
                           "size": len(npz), "content_sha256": csha,
                           "array_shas": arr_shas, "blob": rel}
            payload_shas[name] = psha
        else:
            # default=str：非 JSON 原生对象（ndarray 等——btf report 树内
            # _arrays 面）按既档 dump 形态字符串化（json.dump default=str
            # 同口径——对拍双侧同走；消费面不读该字段）
            data = json.dumps(val, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), default=str).encode("utf-8")
            psha = S.sha256_hex(data)
            rel = write_blob(data, ".json", psha)
            parts[name] = {"kind": "json", "payload_sha256": psha,
                           "size": len(data), "content_sha256": psha, "blob": rel}
            payload_shas[name] = psha
    return parts, payload_shas


def supplement_content_sha(parts: dict) -> str:
    """parts 内容聚合 sha（item content_inputs.supp；任何 part 内容变化即换键）。

    内容身份面：json/npz=content_sha256；png/bin=逐文件 content_sha256 聚合。"""
    identity: dict = {}
    for name, p in parts.items():
        if p["kind"] in ("png", "bin"):
            identity[name] = {f: meta["content_sha256"]
                              for f, meta in sorted(p["files"].items())}
        else:
            identity[name] = p["content_sha256"]
    return S.sha256_hex(S.cjson(identity).encode("utf-8"))


# ---------------------------------------------------------------------------
# decode（warm/seed 调用）：blobs → 内存 parts（零 UnityPy、零游戏文件）
# ---------------------------------------------------------------------------

def decode_parts(manifest: dict, blob_bytes: Callable[[str], bytes], *,
                 verify_content: bool = True) -> dict:
    """manifest.parts + blob_bytes(role) → {part: 内存产物}。

    blob_bytes(role)→该 role 的 blob 字节（warm 面读取由调用方注入——blob 文件
    字节 sha 逐次校验在调用方（L2 介质面）；verify_content=True 逐 part 核内容
    sha（JSON payload/npz 逐数组/png 逐像素/bin 逐文件）——mismatch 响亮）。"""
    out: dict = {}
    for name, p in manifest["parts"].items():
        kind = p["kind"]
        if kind == "json":
            data = blob_bytes(name)
            if verify_content and S.sha256_hex(data) != p["payload_sha256"]:
                raise SuppContentError(f"{name}: canonical bytes sha 失配")
            out[name] = json.loads(data.decode("utf-8"))
        elif kind == "npz":
            data = blob_bytes(name)
            if verify_content and S.sha256_hex(data) != p["payload_sha256"]:
                raise SuppContentError(f"{name}: NPZ payload sha 失配")
            arrays = KC.decode_npz(data)
            if verify_content:
                want = p["array_shas"]
                if set(arrays) != set(want):
                    raise SuppContentError(
                        f"{name}: 数组键面失配（缺 {sorted(set(want)-set(arrays))[:4]}"
                        f" 多 {sorted(set(arrays)-set(want))[:4]}）")
                for k, arr in arrays.items():
                    if KC.array_content_sha(k, arr) != want[k]:
                        raise SuppContentError(f"{name}[{k}]: 数组内容 sha 失配")
            out[name] = arrays
        elif kind in ("png", "bin"):
            files: dict = {}
            for fname, meta in p["files"].items():
                data = blob_bytes(f"{name}:{fname}")
                if verify_content and S.sha256_hex(data) != meta["payload_sha256"]:
                    raise SuppContentError(f"{name}:{fname}: payload sha 失配")
                if kind == "png":
                    img = Image.open(io.BytesIO(data))
                    img.load()
                    if verify_content and \
                            S.sha256_hex(img.tobytes()) != meta["content_sha256"]:
                        raise SuppContentError(f"{name}:{fname}: 解码像素 sha 失配")
                    files[fname] = img
                else:
                    files[fname] = data
            out[name] = files
        else:
            raise SuppContentError(f"{name}: 未知 part kind {kind!r}")
    return out


class SuppContentError(RuntimeError):
    """supplement part 内容失配（fail loud；派生物可删重建但不许坏）。"""


def part_blob_role(part: str, fname: str | None = None) -> str:
    """part → blob role（json/npz=part 名；png/bin=part:fname）。"""
    return part if fname is None else f"{part}:{fname}"
