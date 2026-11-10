"""lock — 缓存根互斥锁（route.db.lock 判例移植：原子 mkdir 目录锁）。

语义（docs/notes/supply-route-cache.md「版本感知自动重建」节同款）：
- 取锁 = `os.mkdir` 原子占位（Windows/POSIX 均原子）；
- 等待方每 2s 重试抢锁（supply build 无 `_load` 快路可重试——改为重读 current.json，
  锁持有者切代成功后等待方可直接短路退出）；
- 锁龄 > 1h 视为持有者崩溃残留，`os.rename` 抢占清除后重试；
- 总等待超上限（默认 1h）响亮失败（SupplyLockTimeout），**禁静默并发建**。
`finally` 必释放；持锁信息（pid/时刻/意图）落锁内 owner.json 供排障。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


class SupplyLockTimeout(RuntimeError):
    """锁等待超时（响亮失败，不静默并发建）。"""


class CacheLock:
    """原子 mkdir 目录锁。with 语义；持锁期写 owner.json（pid/time purpose）。"""

    def __init__(self, lock_dir: Path | str, *, purpose: str = "build",
                 wait_timeout_s: float = 3600.0, stale_age_s: float = 3600.0,
                 poll_s: float = 2.0):
        self.dir = Path(lock_dir)
        self.purpose = purpose
        self.wait_timeout_s = wait_timeout_s
        self.stale_age_s = stale_age_s
        self.poll_s = poll_s
        self._held = False

    # ---- 探测 ----

    def _owner_file(self) -> Path:
        return self.dir / "owner.json"

    def _lock_age(self) -> float:
        try:
            return max(0.0, time.time() - self.dir.stat().st_mtime)
        except OSError:
            return 0.0

    def _try_acquire(self) -> bool:
        try:
            self.dir.mkdir(parents=True)
        except FileExistsError:
            return False
        try:
            self._owner_file().write_text(json.dumps({
                "pid": os.getpid(), "time": time.time(),
                "purpose": self.purpose}, sort_keys=True), encoding="utf-8")
        except OSError:
            pass
        self._held = True
        return True

    def _takeover_stale(self) -> bool:
        """陈锁 os.rename 抢占（rename 原子挪走旧锁目录 → 空位重抢）。"""
        aged = self._lock_age() >= self.stale_age_s
        if not aged:
            return False
        dead = self.dir.with_name(self.dir.name + f".stale.{int(time.time())}")
        try:
            os.rename(self.dir, dead)
        except OSError:
            return False
        return self._try_acquire()

    # ---- with 语义 ----

    def __enter__(self) -> "CacheLock":
        waited = 0.0
        while not self._try_acquire():
            if self._takeover_stale():
                return self
            if waited >= self.wait_timeout_s:
                raise SupplyLockTimeout(
                    f"supply 缓存锁等待超时（{self.wait_timeout_s:.0f}s）：{self.dir}"
                    f"（owner={self._read_owner() or '未知'}）——不静默并发建，先排障持锁进程")
            time.sleep(self.poll_s)
            waited += self.poll_s
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            owner = self._owner_file()
            if owner.is_file():
                owner.unlink()
        except OSError:
            pass
        try:
            self.dir.rmdir()
        except OSError:
            pass

    def _read_owner(self) -> str | None:
        try:
            return json.loads(self._owner_file().read_text(encoding="utf-8")).get("pid")
        except (OSError, json.JSONDecodeError):
            return None
