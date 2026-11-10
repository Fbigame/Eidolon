"""paths — 缓存根与代/blob 布局（cache_root 全显式；库面不读 env/repo）。

cache_root 由调用方显式构造传入（CLI ``--cache-root`` / 组合层）；库面（warm）只吃
构造传入的根，不做任何解析——上游「容器直属默认根」的 repo 派生**不搬**
（Phase 5 移植定案：``default_cache_root`` 不移植，缺省即参数错误）。

布局（v4 设计 §3）::

    <cache_root>/
      current.json                    # {"game_id","generation",...} 原子切代
      gen-<game_id>/index.sqlite      # 该代自包含索引
      blobs/<sha[:2]>/<sha[2:4]>/<payload_sha256>.<ext>   # ext=png|json|npz|ttf
      lock/                           # 原子 mkdir 锁（route.db.lock 判例）
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

HEALTH_STAMP_VERSION = 1
"""健康 stamp sidecar 的 schema 版（T2 warm-perf；字段面变更即升版）。"""


class SupplyLayout:
    """缓存根布局派生（纯路径计算；不做 IO 语义）。"""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    # ---- 目录 ----

    @property
    def gens_dir(self) -> Path:
        return self.root / "gens"

    def gen_dir(self, game_id: str) -> Path:
        return self.gens_dir / f"gen-{game_id}"

    def gen_db(self, game_id: str) -> Path:
        return self.gen_dir(game_id) / "index.sqlite"

    def gen_db_build(self, game_id: str) -> Path:
        """建库临时位（os.replace 发布前）。"""
        return self.gen_dir(game_id) / "index.sqlite.build"

    # ---- 健康 stamp sidecar（T2 warm-perf：quick_check 结果缓存） ----

    def health_stamp_path(self, game_id: str) -> Path:
        """代库健康 stamp 位：gens/gen-<id>/index.sqlite.health.json。

        记录 (db_size, db_mtime_ns) 身份 + 最近一次全检时间/方式 + locale——
        warm open 据此跳过 PRAGMA quick_check 全扫（小进程产品形态的 open 成本）；
        身份失配/超窗/-wal 残留即失效重检（自愈语义保留，残险账见 warm 模块头）。"""
        return self.gen_dir(game_id) / "index.sqlite.health.json"

    def read_health_stamp(self, game_id: str) -> dict | None:
        """读健康 stamp（缺文件/坏 JSON=None——stamp 是派生物，失效即重检）。"""
        p = self.health_stamp_path(game_id)
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def write_health_stamp(self, game_id: str, *, db_path: Path, locale: str,
                           how: str) -> bool:
        """原子写健康 stamp（tmp+os.replace；best-effort——写失败返回 False，
        下次 open 重检不响亮；DB stat 失败同 False）。"""
        try:
            st = db_path.stat()
        except OSError:
            return False
        doc = {"v": HEALTH_STAMP_VERSION, "db_size": st.st_size,
               "db_mtime_ns": st.st_mtime_ns, "checked_at": int(time.time()),
               "how": how, "locale": locale}
        self.gen_dir(game_id).mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.gen_dir(game_id)),
                                   prefix=".health.", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, sort_keys=True)
            _replace_with_retry(tmp, self.health_stamp_path(game_id))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return False
        return True

    @property
    def blobs_dir(self) -> Path:
        return self.root / "blobs"

    @property
    def current_json(self) -> Path:
        return self.root / "current.json"

    @property
    def lock_dir(self) -> Path:
        return self.root / "lock"

    # ---- blob 内容寻址 ----

    def blob_path(self, payload_sha256: str, ext: str = ".png") -> Path:
        """blob 文件位：blobs/<sha[:2]>/<sha[2:4]>/<sha><ext>。

        ext 按 blobs.codec 派生（png/json/npz/ttf；P1 面=png 缺省不变——现存 blob
        文件名零迁移）。"""
        sha = payload_sha256.lower()
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError(f"非法 payload sha256：{payload_sha256!r}")
        return self.blobs_dir / sha[:2] / sha[2:4] / f"{sha}{ext}"

    # ---- current.json 原子读写 ----

    def read_current(self) -> dict | None:
        """读 current.json（缺文件/坏 JSON=None——缓存是派生物，重建即可，不炸）。"""
        p = self.current_json
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def write_current(self, doc: dict) -> None:
        """原子写 current.json（tmp + os.replace；Windows 共享冲突短重试）。"""
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1)
        fd, tmp = tempfile.mkstemp(dir=str(self.root), prefix=".current.", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            _replace_with_retry(tmp, self.current_json)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _replace_with_retry(src: Path | str, dst: Path, *, attempts: int = 6,
                        delay: float = 0.5) -> None:
    """os.replace + Windows 只读句柄短重试（route.db 判例：6×0.5s 兜短命读者）。"""
    import time

    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)
