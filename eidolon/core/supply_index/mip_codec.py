"""mip_codec — mip 链 NPZ 编解码（Phase 1 A5；cold 落盘 / warm 读回共用单点）。

与 kit_codec.encode_npz（ZIP_STORED）的差异：mip 链是**纯像素噪声**（DXT 解码
产物），STORED 不压缩会让 ~16.8k 条 512² 肖像链落 ~6GB；本模块用 ZIP_DEFLATED
（确定性：zlib 同输入同层输出确定，条目序=键排序、时间戳固定——与 kit_codec
同一确定性纪律，payload sha 复现面成立）。往返=无损 uint8 数组（np.lib.format
write/read，allow_pickle=False）。

数组键面（cold 写、warm 读、audit 对账三方同一词面）：
- portrait_mip 项 blob：``lod/<i>``（i=1..n-1 存储级；L0 缺位=由 portrait PNG
  派生——manifest "l0" 字段裁决 derived/explicit，explicit 时 ``lod/0`` 在位）；
- mip_registry 项 blob：``chain/<name>/<i>``（i=0..n-1 全级——注册表无派生面）；
- color atlas 项 mip_chain blob：``lod/<i>``（0..n-1 全级——图集链无派生面）。

warm import 面纪律：本模块只 import numpy/zipfile/io——零 UnityPy、零游戏面
（audit import blocker 过闸件，test_supply_index_mip 有机器证明）。
"""
from __future__ import annotations

import io
import zipfile

import numpy as np

from eidolon.core.supply_index import schema as S

MIP_CODEC = "npz"
MIP_CODEC_VERSION = 1
NPZ_ZIP_DATE = (2026, 11, 10, 0, 0, 0)   # 固定时间戳（确定性 zip）


def encode_chain_npz(arrays: dict[str, "np.ndarray"]) -> bytes:
    """链数组 → 单 NPZ（确定性 deflate：条目序=键排序、时间戳固定）。"""
    if not arrays:
        return b""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(arrays):
            zi = zipfile.ZipInfo(name + ".npy", date_time=NPZ_ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            abuf = io.BytesIO()
            np.lib.format.write_array(abuf, np.ascontiguousarray(arrays[name]),
                                      allow_pickle=False)
            zf.writestr(zi, abuf.getvalue())
    return bio.getvalue()


def decode_chain_npz(data: bytes) -> dict[str, "np.ndarray"]:
    """NPZ → {key: ndarray}（uint8 链级数组；键序=zip 条目序）。"""
    with np.load(io.BytesIO(data), allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def level_key(i: int) -> str:
    """portrait/atlas 链 blob 内第 i 级的数组键。"""
    return f"lod/{int(i)}"


def meta_marker_payload() -> bytes:
    """meta-only 项（source=registry/portrait——无自有链数据）的 blob 占位字节。

    expected-vs-built 的 built 判据=items 行 + ≥1 item_blobs 行，故 mip item
    一律带 blob 行；此类项的链数据由 warm 派生（registry 项 / portrait PNG），
    blob 只落 1 字节标记数组（内容恒定 → payload sha 恒定 → 跨卡 blob 去重）。
    warm 读回：无 ``lod/*`` 键 → 按 manifest source 走派生面。"""
    return encode_chain_npz({"meta": np.zeros(1, dtype=np.uint8)})


def registry_chain_key(name: str, i: int) -> str:
    """mip_registry blob 内 (链名, 第 i 级) 的数组键。"""
    return f"chain/{name}/{int(i)}"


def chain_content_sha(lods) -> str:
    """链数组内容聚合 sha（值身份——键面/对账/repair 判据共用；级别序=存储序）。

    公式=sha256(每级 sha256(level.tobytes()) 顺次拼接的 hex 串)——逐级内容
    sha 链聚合（kit_codec.arrays_content_sha 同构），空链=空串。"""
    import hashlib

    parts = []
    for arr in lods:
        parts.append(hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest())
    if not parts:
        return ""
    return S.sha256_hex("".join(parts).encode("utf-8"))
