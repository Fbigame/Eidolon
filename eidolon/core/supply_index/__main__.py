"""python -m eidolon.core.supply_index — 供给索引 CLI 入口（Phase 5 内部工具）。"""
from __future__ import annotations

import sys

from .cli import main


def _utf8_streams() -> None:
    """把 stdout/stderr 切到 UTF-8（Windows 非 UTF-8 代码页上 help 含中文会炸）。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    _utf8_streams()
    sys.exit(main())
