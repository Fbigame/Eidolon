"""game_install — 游戏安装**边缘解析链**（契约 D 产品化：全显式、无 env）。

解析链（两路，无环境变量、无硬编码默认）：

- root：显式 ``game_dir`` > 战网 ``product.db`` install_path 自动发现 > 响亮报错
  （``EnvironmentUnavailable(game_not_found)``）。显式路径不在这里判安装根
  （shell 的 ``load_input`` 已判；provider 侧用 ``GameContext.game_exe`` 再验）。
- version：product.db 版本串（**仅当其 install_path 与 root 同装**——拷贝安装与
  全局 product.db 打架的解耦判据）> root 下 ``Logs/*/Power*.log`` + ``Power*.log``
  的 ``BuildNumber=``（新→旧）> ``(None, "")``（v1 只记录不闸）。
- ``cache_root`` / ``locale`` 由 provider 构造参数传入；locale 归一化
  ``strip().lower()``，空串回落 ``"zhcn"``。

protobuf walk 私有段：hs_beta 条目 ``(3,1)``=install_path、``(4,1,7)``=
版本串（末段=数据 BuildNumber，机器常驻不随游戏日志轮转）。唯一语义偏离：
字段号命中但 wire_type≠2 的标量字段照常跳过（不跳会致后续失配）。

版本只记录不闸（v1 非目标）：客户端自动更新会使数据偏离采集态，v1 不做
兼容表/严格闸；``GameContext.version`` 只进 manifest 账面。

测试可注入 ``product_db_path=``（合成 product.db 走 tmp 文件，不 monkeypatch
模块常量）。
"""
from __future__ import annotations

import os
from pathlib import Path

from eidolon.contracts import (
    EnvironmentUnavailable,
    GameContext,
    GameRequest,
    Problem,
    ProblemKind,
)

PRODUCT_DB_PATH = Path("C:/ProgramData/Battle.net/Agent/product.db")

_GAME_NOT_FOUND = "game_not_found"
_GAME_DIR_INCOMPLETE = "game_dir_incomplete"


# ============================================================================
# product.db protobuf walk（共享私有段：hs_beta 条目定位 + install_path/版本串）
# ============================================================================

def _pb_read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            break
    return value, pos


def _pb_skip(data: bytes, pos: int, wire_type: int) -> int:
    if wire_type == 0:
        _, pos = _pb_read_varint(data, pos)
    elif wire_type == 1:
        pos += 8
    elif wire_type == 2:
        length, pos = _pb_read_varint(data, pos)
        pos += length
    elif wire_type == 5:
        pos += 4
    return pos


def _pb_walk(data: bytes, path: tuple[int, ...]) -> list[bytes]:
    if not path:
        return []
    target = path[0]
    remaining = path[1:]
    results: list[bytes] = []

    pos = 0
    while pos < len(data):
        tag, pos = _pb_read_varint(data, pos)
        field_number = tag >> 3
        wire_type = tag & 0x07

        if field_number == target and wire_type == 2:
            # length-delimited: read content
            length, pos = _pb_read_varint(data, pos)
            content = data[pos:pos + length]
            pos += length
            if remaining:
                results.extend(_pb_walk(content, remaining))
            else:
                results.append(content)
        else:
            pos = _pb_skip(data, pos, wire_type)

    return results


def _pb_walk_one(data: bytes, path: tuple[int, ...]) -> bytes | None:
    results = _pb_walk(data, path)
    return results[0] if results else None


def _product_db_hs_entry(product_db_path: Path) -> tuple[bytes | None, str | None]:
    """读 product.db 定位 hs_beta（或别名 hsb）产品条目；返回 (条目字节, 失败原因)。"""
    if not product_db_path.exists():
        return None, f"product.db 不存在：{product_db_path}"
    try:
        data = product_db_path.read_bytes()
    except OSError as e:
        return None, f"product.db 读取失败：{e}"
    try:
        for entry_bytes in _pb_walk(data, (1,)):
            f1 = _pb_walk_one(entry_bytes, (1,))
            f2 = _pb_walk_one(entry_bytes, (2,))
            try:
                if (f1 and f1.decode("utf-8") == "hs_beta") or \
                        (f2 and f2.decode("utf-8") == "hsb"):
                    return entry_bytes, None
            except UnicodeDecodeError:
                continue
    except Exception as e:  # noqa: BLE001  protobuf 坏数据兜底（共享原型同判）
        return None, f"product.db protobuf 解析异常：{e}"
    return None, "product.db 无 hs_beta/hsb 条目"


def _entry_utf8_field(entry: bytes, path: tuple[int, ...]) -> str | None:
    """取条目内路径字段的 UTF-8 串；字段缺失或非 UTF-8 → None。"""
    field = _pb_walk_one(entry, path)
    if field is None:
        return None
    try:
        return field.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _product_db_install_path(product_db_path: Path) -> tuple[str | None, str | None]:
    """hs_beta 条目 (3,1) 字段 = install_path。"""
    entry, err = _product_db_hs_entry(product_db_path)
    if entry is None:
        return None, err
    value = _entry_utf8_field(entry, (3, 1))
    if value is None:
        return None, "hs_beta 条目无 (3,1) install_path 字段（或非 UTF-8）"
    return value, None


def _product_db_version_str(product_db_path: Path) -> str | None:
    """hs_beta 条目 (4,1,7) 字段 = 版本串（末段=数据 BuildNumber）。

    机器常驻、不随游戏日志轮转。任何失败返回 None，不 raise。**注意**：这是
    product.db 所记安装的串；采信前必须先过 `resolve_version` 的同装一致性闸
    （install_path==root），不得绕过直接当 root 的版本用。
    """
    entry, _err = _product_db_hs_entry(product_db_path)
    if entry is None:
        return None
    return _entry_utf8_field(entry, (4, 1, 7))


# ============================================================================
# 边缘解析链（显式 > product.db 探测；失败一律 typed EnvironmentUnavailable）
# ============================================================================

def resolve_game_root(explicit: Path | None, *, source: str,
                      product_db_path: Path = PRODUCT_DB_PATH) -> tuple[Path, str]:
    """root 解析：显式 > product.db 自动发现 > 响亮报错。

    explicit 非 None → ``(path, source or "explicit")``，不在这里判安装根
    （shell ``load_input`` 已判；provider 侧 ``game_exe`` 再验）。
    探测路：product.db 文件不存在 / 读取失败 / 无 hs_beta|hsb 条目 / 无
    install_path / 目录不存在 → ``EnvironmentUnavailable(game_not_found，
    path=product.db，message=具体原因)``；install_path 目录存在但缺
    Hearthstone.exe → ``game_dir_incomplete``（path=目录）。
    **无硬编码默认**：product.db 不可用且无显式值=raise（拷贝安装/无战网机器
    必须显式传 --game / game_dir）。
    """
    if explicit is not None:
        return Path(explicit), source or "explicit"
    install_path, err = _product_db_install_path(product_db_path)
    if install_path is not None:
        candidate = Path(install_path)
        if not candidate.is_dir():
            raise EnvironmentUnavailable(Problem(
                ProblemKind.ENVIRONMENT, _GAME_NOT_FOUND,
                str(product_db_path),
                f"game_not_found: product.db install_path={install_path} 目录不存在"))
        if not (candidate / "Hearthstone.exe").is_file():
            raise EnvironmentUnavailable(Problem(
                ProblemKind.ENVIRONMENT, _GAME_DIR_INCOMPLETE,
                str(candidate),
                f"game_dir_incomplete: install_path={install_path} 下无 Hearthstone.exe"
                "（stale 条目）"))
        return candidate, "product.db"
    raise EnvironmentUnavailable(Problem(
        ProblemKind.ENVIRONMENT, _GAME_NOT_FOUND,
        str(product_db_path),
        f"game_not_found: product.db 自动发现失败（{err or '未知原因'}）"))


def assert_game_root(path: Path) -> None:
    """安装根自检（core 自检/测试用；不参与 load_input 的输入校验）。

    目录不存在 → ``EnvironmentUnavailable(game_not_found, path=str(path))``；
    目录在但缺 Hearthstone.exe → ``game_dir_incomplete``（path=str(path)）。
    """
    path = Path(path)
    if not path.is_dir():
        raise EnvironmentUnavailable(Problem(
            ProblemKind.ENVIRONMENT, _GAME_NOT_FOUND,
            str(path), f"game_not_found: 游戏目录不存在：{path}"))
    if not (path / "Hearthstone.exe").is_file():
        raise EnvironmentUnavailable(Problem(
            ProblemKind.ENVIRONMENT, _GAME_DIR_INCOMPLETE,
            str(path), f"game_dir_incomplete: {path} 下无 Hearthstone.exe"))


def _power_log_version(root: Path) -> tuple[str | None, str]:
    """回落源：root 下 Logs/*/Power*.log（新→旧）+ 旧式 root/Power*.log 找
    `BuildNumber=<n>`（GameState.DebugPrintGame 打印）。返回 (build 串, 日志路径)。"""
    try:
        candidates = sorted(root.glob("Logs/*/Power*.log"),
                            key=lambda p: p.stat().st_mtime, reverse=True) \
            + sorted(root.glob("Power*.log"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None, ""
    for log in candidates:
        try:
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                if "BuildNumber=" in line:
                    got = line.split("BuildNumber=", 1)[1].strip().split()[0].rstrip("\r")
                    return got, str(log)
        except OSError:
            continue
    return None, ""


def _same_install(a: str | Path, b: str | Path) -> bool:
    """路径同装判定（normcase+abspath 同口径）。"""
    na = os.path.normcase(os.path.abspath(os.fspath(a)))
    nb = os.path.normcase(os.path.abspath(os.fspath(b)))
    return na == nb


def resolve_version(root: str | Path, *,
                    product_db_path: Path = PRODUCT_DB_PATH) -> tuple[str | None, str]:
    """root 同装的客户端数据版本串解析。返回 (版本串, 来路账)。

    ① product.db 版本串——**仅当其 install_path 与 root 同装**才采信
    （拷贝安装/显式指根时，product.db 说的可能是别的安装）；
    ② root 下 Power.log 扫描（见 _power_log_version；返回裸 BuildNumber 串）；
    ③ (None, "")——v1 只记录不闸。
    """
    root = Path(root)
    try:
        install_path, _err = _product_db_install_path(product_db_path)
        vs = _product_db_version_str(product_db_path)
    except Exception:                                  # noqa: BLE001 —— 探测失败=走回落
        install_path, vs = None, None
    if vs and install_path and _same_install(install_path, root):
        return vs.strip(), "product.db"
    got, src = _power_log_version(root)
    if got:
        return got, f"power.log:{src}"
    return None, ""


def resolve_context(request: GameRequest, *, cache_root: Path, locale: str,
                    product_db_path: Path = PRODUCT_DB_PATH) -> GameContext:
    """边缘总入口：解析链 → GameContext（provider.bind 用）。

    - locale 归一化 ``strip().lower()``，空串回落 ``"zhcn"``；
    - ``route_mode="auto"`` / ``version_strict=False``（v1 固定，不开开关）；
    - ``root_source``：``"--game"`` → ``"--game"``；``"toml game_dir"`` →
      ``"toml game_dir"``；探测成功 → ``"product.db"``（显式给值但未记来路时
      落 ``"explicit"``）；
    - ``version_source``：``"product.db"`` / ``"power.log:<path>"`` / ``""``。
    """
    norm_locale = (locale or "").strip().lower() or "zhcn"
    root, root_source = resolve_game_root(
        request.game_dir, source=request.source, product_db_path=product_db_path)
    version, version_source = resolve_version(root, product_db_path=product_db_path)
    return GameContext(
        root=root,
        cache_root=Path(cache_root),
        locale=norm_locale,
        version=version,
        version_source=version_source,
        root_source=root_source,
        route_mode="auto",
        version_strict=False,
    )
