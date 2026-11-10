"""_unity — 冷侧 UnityPy 原始访问单点（仅 cold/verify/revalidate-worker 可 import）。

判据（必须保留 #2）：container 读取一律 `SerializedFile.container.container` 原始
pairs——**禁 env.container**（`parse_preload_table` 大包首触 225s 判例，
docs/notes/supply-route-cache.md）。本模块是全包唯一 UnityPy 触点，warm 面零 import
（audit.import_blocker 的机器证明边界即「warm 进程拦不到本模块被 import」）。

version fallback：本机客户端 6000.3.11f1（2026-10-17 用户裁决，dbf_metadata 同值）；
bundle 自带版本缺失时 fallback 兜底（route 判例：生效引擎版本看 SerializedFile.version，
本语料 f.unity_version 恒 "0.0.0"）。
"""
from __future__ import annotations

from pathlib import Path

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.11f1"

from UnityPy.files import SerializedFile  # noqa: E402

FALLBACK_UNITY_VERSION = "6000.3.11f1"


def iter_serialized(env):
    """深度优先枚举 env 内全部 SerializedFile（bundle 内多 CAB）。"""

    def walk(file):
        if isinstance(file, SerializedFile):
            yield file
            return
        subs = getattr(file, "files", None)
        if isinstance(subs, dict):
            for sub in subs.values():
                yield from walk(sub)

    for f in env.files.values():
        yield from walk(f)


def container_pairs(sf: SerializedFile) -> list[tuple[str, int]]:
    """原始 container pairs（键, path_id）——**唯一合法读法**（必须保留 #2）。

    同键可多条（route 判例：实测同 GUID 单 CAB 17 条 path_id 各异），保序不折叠。"""
    return [(k, int(v.asset.m_PathID)) for k, v in sf.container.container]


def path_id_for(pairs: list[tuple[str, int]] | dict, guid: str) -> int | None:
    """guid → path_id：裸小写 GUID 精确键优先，退化 endswith（带路径键的包）。"""
    items = pairs.items() if isinstance(pairs, dict) else pairs
    g = guid.lower()
    for key, pid in items:
        if key.lower() == g or key.lower().endswith(g):
            return pid
    return None


def load_bundle(path: Path):
    """单包打开（冷侧专用；返回 env，调用方负责生命周期）。"""
    return UnityPy.load(str(path))


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
