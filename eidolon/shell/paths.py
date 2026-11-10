"""默认 cache root 与 OS 字体目录的唯一计算点（唯一允许读 OS 目录变量的模块）。

优先级：``--cache-root`` > 默认用户缓存目录；字体目录 = ``WINDIR`` /
``LOCALAPPDATA`` 系统字体位。OS 级目录变量（``LOCALAPPDATA`` /
``XDG_CACHE_HOME`` / ``HOME`` / ``WINDIR``）只允许出现在本模块；
禁止任何 ``HEARTHSTONE_*`` 或其他游戏路径 env（守卫见
tests/architecture/test_env_guards.py）。
"""

from __future__ import annotations

import os
from pathlib import Path


def default_cache_root() -> Path:
    """默认 route 缓存根：Windows ``%LOCALAPPDATA%\\Eidolon\\cache``；
    POSIX ``$XDG_CACHE_HOME/eidolon`` 或 ``~/.cache/eidolon``。"""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Eidolon" / "cache"
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache_home:
        return Path(xdg_cache_home) / "eidolon"
    home = os.environ.get("HOME")
    if home:
        return Path(home) / ".cache" / "eidolon"
    return Path.home() / ".cache" / "eidolon"


def default_font_dirs() -> tuple[Path, ...]:
    """默认 OS 字体目录（glyph_supply.install_font_dirs 的注入源）。

    - ``%WINDIR%\\Fonts``（系统字体）；
    - ``%LOCALAPPDATA%\\Microsoft\\Windows\\Fonts``（按用户安装字体）；
    - 只收实际存在的目录；全无 → 兜底 ``(Path("C:/Windows/Fonts"),)``
      （与 glyph_supply 的政策兜底同值，保证元组非空）。
    """
    dirs: list[Path] = []
    windir = os.environ.get("WINDIR")
    if windir:
        dirs.append(Path(windir) / "Fonts")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        dirs.append(Path(local_app_data) / "Microsoft" / "Windows" / "Fonts")
    existing = tuple(dir for dir in dirs if dir.is_dir())
    if existing:
        return existing
    return (Path("C:/Windows/Fonts"),)
