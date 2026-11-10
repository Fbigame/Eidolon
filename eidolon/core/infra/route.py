"""route — 航线库（**批量产出卡图用的派生缓存**）+ 三态（auto / refresh / no-cache），2026-10-17。

## 定位（用户裁决）

航线不是渲染链的常驻设施，而是**批量产出卡图**时才开的东西，因此按 cache 三态管：

| 模式 | 行为 |
|---|---|
| `auto`（默认） | 有有效库 → 直接用；缺/失配 → 建库再用 |
| `refresh` | 重建并**覆盖**（原子：建到 `route.db.build` → `os.replace`） |
| `no-cache` | 缓存根改到**临时目录** ⟹ 天然不命中（每次重建、退出即弃） |
| `off` | 不用航线（退回现行惰性解析） |

## 存储形态：SQLite（v4，2026-10-17 用户裁决）

v3 之前是全量 JSON 大 dict（每 worker 常驻 +1~1.5GB 级）；v4 改成**按包分片**的单文件库：

```
meta(key, value)                               ← format/unitypy/game/fallback +
                                                 game_build/game_manifest/built_at（版本身份）
bundles(name, size, mtime_ns, md5)             ← 失效判据（逐包）
parts(bundle, kind, payload)                   ← kind ∈ blocks/nodes/objects/containers/
                                                  types/externals/header（每包 7 行）
cabs(cab, bundle)                              ← 全局 cab→bundle（v6；按 cab 查归属）
schemas(hash, payload)                         ← 全局共享类型树（1,534 棵）
```

- 冷开一个包 = 1 次主键查询 + `json.loads(payload)`（KB~MB 级，~1ms 级）；
- 失效 = `UPDATE bundles` 一行；重建 = 按包 `INSERT OR REPLACE`；
- 读者只读打开（`mode=ro`），多 worker 并发无碍。

## 全局 cabs 索引（v6，2026-11-09）

`cabs(cab, bundle)` 是**全局表**（cab 主键）：`_bundle_tables` 仍逐包产 `rec["cabs"]`，
`build()` 汇总写入；v5 的 `parts.cabs` 每包一行与 nodes 冗余且无法按 cab 查，v6 起
不再落 parts。消费面：`Tables.cab_owner(cab)`（键=小写 basename 归一，旧库缺表/
读错 → None + 计数，显式不静默）；`resolve_asset_ref._resolve_pptr` 定位跨包依赖
先查它，命中只开 owner 包并校验 `(cab, path_id)`；表 miss → 退回 `bundle_deps`
依赖闭包扫描（不得静默错）。

## scoped 库（v6+，B 案 2026-11-10）

`build(bundles=...)` / `prewarm(...)`：按卡集预热——只建工作集 bundle 的行 +
对应全局 cabs/schemas；meta 记 ``scope``（full/cards）+ ``scope_bundles``（清单，
同 scope 重建的权威面）。消费面不变：`ensure`（auto）照常命中 scoped 库；
工作集外包 ``has()==False`` → :func:`augment_row` lazy 补行（只对 scope=cards
生效；全量库维持既有惰性兜底）。健康机制逐条在 scoped 库上不变：quick_check /
used-hash / dirty / 抽样门 / 单次自动重建——失配 heal 与换代重建都按
``scope_bundles`` **同 scope 重建**（不静默升全量）；显式 refresh 仍全量
（升级路径）。cache root 与 supply index 同根共存：建库后的旧 JSON 清理只认
``route*.json``（B1 实测 `*.json` 全量 glob 会删 index 的 current.json）。

## 键与失效

- 键 = `(format, unitypy)`：表格式与解析语义；游戏版本**不进键**（它是弱证据，会让整表作废）。
- 失效 = **逐包内容哈希** `(size, mtime_ns, md5)`：冷开先 stat 快路，失配才对单包算 md5；
  内容相同则只刷新记录；不同则该包退回惰性，其它包照用（见 verify）。

## 版本感知自动重建（2026-10-19）

逐包 verify 挡得住坏包，却挡不住**版本整体换代**（旧库大面积失效、新包未入册，
首触全耗在 manifest 表解析）。故建库时把版本身份写进
`meta`（库内唯一版本载体，**不另设版本文件**）：

- `game_build` = ctx.version 版本串**末段**（客户端数据 BuildNumber）；
- `game_manifest` = `DATA_WIN/asset_manifest.unity3d` 大小（`game_id()`；版本串不可读时兜底）；
  （契约 D 起：版本与 Data/Win 不再直读全局 product.db/模块常量，改从 GameContext
  显式流入——`ctx.version`（边缘按 root 同装解析）与 `ctx.data_win`，见 `_game_identity`）；
- `built_at` = 建库时刻 epoch 秒（只作重建证据/对账，**不参与判定**）。

`auto` 的 `_load` 在 `_KEY_FIELDS` 校验之后比对身份：不符（含**旧库无版本字段**）→ 视为未命中
并自动重建；当前身份不可读（product.db 与 manifest 都拿不到）→ **不判不符**，退回逐包 verify
（`route_version_unknown`），不误重建。版本**不进** `_KEY_FIELDS`：语义独立、便于计数，
也不让游戏小版本把整库误判成键失配。

重建由 `route.db.lock`（`os.mkdir` 原子目录）串行化：并发 `ensure()` 只有一个进程建库，
其余等待后读新库（绝不并发写 `route.db.build`）。等待方每 2s 重试 `_load`（不必等锁释放）；
锁龄 > 1h 视为残留（持有者崩溃）并清除，单进程总等待上限 1h，超时返回 `None` +
`route_build_lock_timeout`（不静默并发重建）。

## 契约

- `ensure()` 返回 `Tables | None`：`None` = 本进程不用航线（off / 建库失败 / 等锁超时 /
  无游戏目录）。
- `open_env(bundle, tables, br)` → 用航线行重建的 `UnityPy.Environment`（对象字节仍走块级惰性流）。
- 任何"缺行/失配"都**显式**（计数 + 返回 None / 抛错），不猜、不静默降级。
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import shutil
import sqlite3
import time
from collections import namedtuple
from pathlib import Path

import UnityPy
from UnityPy.classes import PPtr
from UnityPy.enums import BuildTarget, ClassIDType
from UnityPy.files.ObjectReader import ObjectReader
from UnityPy.files.SerializedFile import SerializedFile as _RealSerializedFile
from UnityPy.helpers.ContainerHelper import ContainerHelper
from UnityPy.helpers.TypeTreeNode import TypeTreeNode
from UnityPy.helpers.UnityVersion import UnityVersion
from UnityPy.streams import EndianBinaryReader

from eidolon.contracts import EnvironmentUnavailable, Problem, ProblemKind
from eidolon.core.infra import bundle_lazy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.11f1"   # 正典同款（resolve_asset_ref/dbf 同值）

logger = logging.getLogger(__name__)

ROUTE_FORMAT = 6   # v2：header 改存 version_int（引擎版本真值；unity_version 串在本游戏全语料为 "0.0.0"）
                   # v3：meta 增逐包指纹（size/mtime_ns/md5），游戏版本退出键
                   # v4：存储改 SQLite 按包分片（v3 的全量 JSON 载入 → 每 worker 常驻 GB 级）
                   # v5：containers 改存**完整 pairs 列表**（v4 的 dict 丢了同键多条 → 按名扫描
                   #     的消费者找不到对象；实测同一 GUID 在一个 CAB 里有多条）
                   # v6：cabs 改全局表（cab 主键→bundle）；v5 的 parts.cabs 是每包一行、
                   #     与 nodes 冗余且无法按 cab 查（resolve 定位跨包依赖按 cab 查归属，
                   #     命中只开 owner 包；miss 走 bundle_deps 闭包兜底）

DB_NAME = "route.db"

# 缓存健康面（P1）：脏标记 + 上次校验时刻。两个文件都落在**实际航线根**
# （no-cache 时是 pid 临时根，不污染缓存根）。
DIRTY_NAME = "route.dirty"
HEALTH_NAME = "route.health"
HEALTH_SAMPLE_N = 32               # 健康门抽样包数（默认 used-hash 仍覆盖每个被消费包）
HEALTH_MAX_AGE_SECS = 6 * 60 * 60  # 超过则下次 open 抽样一次
HEALTH_FRESH_SECS = 120            # 刚建好的库不需再抽样（建库即读当前盘）
DIRTY_CLAIM_SECS = 5 * 60          # 别人的脏标记超过该年龄且持有者 pid 已死 → 接管（B3）

# 每包一份的部件（blocks/nodes 以 bundle 为键；其余以 cab 为键）
# cabs 不在 PARTS：v6 起它是全局表（cab 主键）。_bundle_tables 仍产 rec["cabs"]
# 供 build 写全局表，但不落 parts（v5 的每包 cabs 行与 nodes 冗余、全仓零消费者）。
PARTS = ("blocks", "nodes", "objects", "containers", "types", "externals", "header")

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE bundles (name TEXT PRIMARY KEY, size INTEGER NOT NULL,
                      mtime_ns INTEGER NOT NULL, md5 TEXT NOT NULL);
CREATE TABLE parts (bundle TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (bundle, kind)) WITHOUT ROWID;
CREATE TABLE schemas (hash TEXT PRIMARY KEY, payload TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE cabs (cab TEXT PRIMARY KEY, bundle TEXT NOT NULL) WITHOUT ROWID;
"""

_AssetInfo = namedtuple("_AssetInfo", "asset")

# 真 SerializedFile 的实例属性全集（UnityPy 1.25.3 实测 25 个，见 2026-10-17 对拍）：
# shim 必须逐个铺上，缺一个就让某个解码分支静默走错（_enable_type_tree/flags 的前科）。
_MIRROR_REQUIRED = frozenset({
    "parent", "cab_file", "name", "is_dependency", "is_changed", "environment",
    "header", "unity_version", "version", "big_id_enabled", "_m_target_platform",
    "target_platform", "externals", "ref_types", "script_types", "_cache",
    "assetbundle", "_container", "reader", "objects", "types",
    "_enable_type_tree", "flags", "unknown", "userInformation",
})

# 运行时计数（随 bundle 遥测落盘）
STATS: dict[str, int] = {}


def _bump(key: str, n: int = 1) -> None:
    STATS[key] = STATS.get(key, 0) + n


def stats() -> dict:
    return dict(STATS)


# ---------------------------------------------------------------- used-hash（P0）
# 进程内已验证结果缓存：键 = (bundle, size, mtime_ns, 行 md5)。同一进程里同包
# 只付一次整文件哈希；rebuild 换了行 md5 自然产生新键，重试不会误命中旧结论。
_VERIFIED: dict[tuple[str, int, int, str], bool] = {}

# 自动重建代际账：同一代只允许一次 mismatch 自动重建（防抖/防循环）。键 =
# (db 路径, db 文件 mtime_ns)——重建会替换 route.db，mtime_ns 即新代身份。
_AUTO_REBUILT: set[tuple[str, int]] = set()


def _generation_key(tables: "Tables") -> tuple[str, int]:
    return _db_generation(Path(tables._db))          # noqa: SLF001 —— 同模块内部身份


def verify_used(bundle: str, tables: "Tables | None", data_win: str | Path) -> bool:
    """**used-hash**：本 bundle 真正被消费时，用航线行 md5 校验盘上内容。

    与 :func:`verify` 的差别：这里**不走** size/mtime 快路——stat 相同也必须
    哈希（蓝屏/bit rot 可以在 size/mtime 不变下改内容）。结果按
    ``(bundle, size, mtime_ns, 行 md5)`` 进程内缓存，同包只哈希一次。
    失配 → 计数 + `STALE.add` + 返回 False（调用方负责单次重建/响亮）。
    """
    if tables is None:
        return False
    rec = tables.fingerprint(bundle)
    if rec is None:
        _bump("route_verify_missing")
        return False
    path = Path(data_win) / bundle
    try:
        st = path.stat()
    except OSError:
        _bump("route_verify_stat_failed")
        STALE.add(bundle)
        return False
    return _used_hash_check(bundle, rec, path, st)


def _used_hash_check(bundle: str, rec: dict, path: Path, st) -> bool:
    key = (bundle, int(st.st_size), int(st.st_mtime_ns), str(rec["md5"]))
    cached = _VERIFIED.get(key)
    if cached is not None:
        _bump("route_used_hash_memo")
        if cached:
            _bump("route_used_hash_ok")
            return True
        _bump("route_used_hash_mismatch")
        STALE.add(bundle)
        return False
    _bump("route_used_hash")
    try:
        same = _md5_file(path) == rec["md5"]
    except OSError:
        _bump("route_verify_stat_failed")
        STALE.add(bundle)
        return False
    _VERIFIED[key] = same
    if same:
        _bump("route_used_hash_ok")
        return True
    _bump("route_used_hash_mismatch")
    _bump("route_stale")
    STALE.add(bundle)
    return False


def verify_sample(tables: "Tables | None", data_win: str | Path,
                  n: int = HEALTH_SAMPLE_N) -> dict:
    """抽样 used-hash（确定性等距抽样；不阻塞正常 render 的默认面之外）。

    返回 ``{"checked", "mismatched", "kind"}``。mismatched 是包名列表；
    调用方决定重建/响亮。``tables=None`` 返回空账。
    """
    if tables is None:
        return {"checked": 0, "mismatched": [], "kind": "sample"}
    names = sorted(tables.names())
    if not names or n <= 0:
        return {"checked": 0, "mismatched": [], "kind": "sample"}
    step = max(1, len(names) // int(n))
    sample = names[::step][:int(n)]
    return _verify_many(tables, data_win, sample, kind="sample")


def verify_all(tables: "Tables | None", data_win: str | Path) -> dict:
    """全量 used-hash（显式/后台调用；不接 render、不新增 CLI）。"""
    if tables is None:
        return {"checked": 0, "mismatched": [], "kind": "full"}
    return _verify_many(tables, data_win, sorted(tables.names()), kind="full")


def _verify_many(tables: "Tables", data_win: str | Path, names: list[str], *,
                 kind: str) -> dict:
    mismatched: list[str] = []
    for name in names:
        if not verify_used(name, tables, data_win):
            mismatched.append(name)
    _bump(f"route_health_{kind}_runs")
    _bump(f"route_health_{kind}_checked", len(names))
    if mismatched:
        _bump(f"route_health_{kind}_mismatched", len(mismatched))
    return {"checked": len(names), "mismatched": mismatched, "kind": kind}


# ---------------------------------------------------------------- 健康文件（P1）

_HEALTH_CHECKED: set[str] = set()          # 本进程已做过健康门的根
_DIRTY_OWNED: dict[str, bool] = {}         # 根 → 脏标记是否由本进程创建
_ATEXIT_REGISTERED = False


def _path_key(rt: Path) -> str:
    try:
        return str(Path(rt).resolve())
    except OSError:
        return str(Path(rt))


def _register_atexit() -> None:
    global _ATEXIT_REGISTERED
    if not _ATEXIT_REGISTERED:
        _ATEXIT_REGISTERED = True
        atexit.register(_clear_owned_dirty)


def _clear_owned_dirty() -> None:
    """正常退出清理本进程创建的脏标记；别人的标记一律不动。"""
    pid = os.getpid()
    for key, owned in list(_DIRTY_OWNED.items()):
        if not owned:
            continue
        marker = Path(key) / DIRTY_NAME
        try:
            text = marker.read_text(encoding="utf-8")
        except OSError:
            continue
        if f"pid={pid}" in text.splitlines():
            try:
                marker.unlink()
            except OSError:
                pass


def _begin_session(rt: Path) -> None:
    """尽力创建“未清洁退出”标记（O_EXCL；已被别人持有则只记观察）。"""
    _register_atexit()
    key = _path_key(rt)
    if key in _DIRTY_OWNED:
        return
    marker = Path(rt) / DIRTY_NAME
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        _DIRTY_OWNED[key] = False
        return
    except OSError:
        _DIRTY_OWNED[key] = False
        _bump("route_dirty_marker_failed")
        return
    try:
        os.write(fd, f"pid={os.getpid()}\nat={time.time():.0f}\n".encode())
    finally:
        os.close(fd)
    _DIRTY_OWNED[key] = True
    _bump("route_dirty_marker_created")


def _read_health(rt: Path) -> dict:
    try:
        data = json.loads((Path(rt) / HEALTH_NAME).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_health(rt: Path, report: dict, *, forced: bool) -> None:
    path = Path(rt) / HEALTH_NAME
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    payload = {
        "last_verify_at": int(time.time()),
        "last_verify_kind": report.get("kind", "sample"),
        "checked": int(report.get("checked", 0)),
        "forced": bool(forced),
    }
    try:
        tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
        _bump("route_health_stamped")
    except OSError:
        _bump("route_health_stamp_failed")
        try:
            tmp.unlink()
        except OSError:
            pass


def _health_due(rt: Path, tables: "Tables") -> tuple[bool, bool]:
    """(是否需要抽样, 是否由别人的脏标记强制)。

    - 本进程刚建的库（built_at 在 HEALTH_FRESH_SECS 内）→ 不需要；
    - 标记不是本进程创建（上次未清洁退出 / 其它 worker）→ 强制；
    - 距上次抽样超过 HEALTH_MAX_AGE_SECS 或从未记录 → 需要。
    """
    dirty = Path(rt) / DIRTY_NAME
    forced = dirty.exists() and not _DIRTY_OWNED.get(_path_key(rt), False)
    age = None
    try:
        age = time.time() - dirty.stat().st_mtime
    except OSError:
        pass
    if forced:
        return True, True
    built_at = int(tables.meta.get("built_at") or 0)
    if built_at and (time.time() - built_at) <= HEALTH_FRESH_SECS:
        return False, False
    last = int(_read_health(rt).get("last_verify_at") or 0)
    if last and (time.time() - last) <= HEALTH_MAX_AGE_SECS:
        return False, False
    return True, False


def _dirty_holder_pid(marker: Path) -> int | None:
    """脏标记的持有者 pid（``pid=`` 行）；旧格式 / 读不到 / 非整数 → None。"""
    try:
        text = marker.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("pid="):
            try:
                return int(line[4:].strip())
            except ValueError:
                return None
    return None


def _pid_alive(pid: int) -> bool:
    """目标 pid 是否仍有存活进程。

    - Windows **不能**用 ``os.kill(pid, 0)``——非 CTRL 信号会直接
      ``TerminateProcess`` 把目标杀掉；改走 ``OpenProcess`` +
      ``GetExitCodeProcess``（查询权限面，不惊动目标）。
    - ``OpenProcess`` 被拒（ERROR_ACCESS_DENIED，如别的用户的会话）→ 视为活
      （保守：宁可晚接管，不误删活人标记）；查不到进程 → 死。
    - POSIX：``kill(pid, 0)`` 探测；进程存在但无权发信号 → 活。
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259                    # GetExitCodeProcess 的"还在跑"哨兵值
        ERROR_ACCESS_DENIED = 5
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = k32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return ctypes.get_last_error() == ERROR_ACCESS_DENIED
        try:
            code = ctypes.wintypes.DWORD()
            if k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True                       # 查询失败 → 保守视为活
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _claim_stale_dirty(rt: Path) -> None:
    """接管陈旧脏标记（B3：年龄 > DIRTY_CLAIM_SECS **且**持有者 pid 已死）。

    标记里的 pid 仍存活（上一个持有者只是慢，>5min 还在跑）→ 只记计数不动
    标记——误删活人的标记会让该会话真崩溃时无人留痕。pid 解析不出（旧格式/
    损坏）→ 按原超时语义接管（向后兼容）；pid 恰为本进程 → 接管（标记自报
    是本进程 pid，出口清理本就会删它）。pid 复用误判（死者 pid 被无关进程
    复用 → 误判"活着"）无法完全消除，后果=陈旧标记滞留、后续新进程多付抽样
    （抽样照跑，内容正确性不受影响），记已知限制。
    """
    marker = Path(rt) / DIRTY_NAME
    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        age = 0.0
    if age <= DIRTY_CLAIM_SECS:
        return
    holder = _dirty_holder_pid(marker)
    if (holder is not None and holder != os.getpid()
            and _pid_alive(holder)):
        _bump("route_dirty_holder_alive")
        return
    try:
        marker.unlink()
    except OSError:
        return
    _bump("route_dirty_marker_claimed")
    _DIRTY_OWNED.pop(_path_key(rt), None)
    _begin_session(rt)


def _heal_sampled_bundle(bundle: str, tables: "Tables", *, root: Path, mode: str,
                         data_win: str | Path, version: str | None,
                         limit: int | None) -> "Tables":
    """健康门处理单个失配包（多失配时逐个调用，不是“只修第一个”）。

    - scoped 库且 bundle 不在 ``scope_bundles``（渲染期 lazy 补行）：优先
      ``augment_row`` + ``verify_used`` **原位刷新该行**——只动这一包，库里其它
      lazy 行保留；成功即返回同一 ``tables``；
    - 原位刷新失败（锁忙/解析失败/写入失败/刷新后仍失配）→ 回退
      :func:`heal_content_mismatch`（同 scope rebuild = ``scope_bundles + [bundle]``）；
    - full 库 / scope 内包：直接交给 :func:`heal_content_mismatch` 的“单代一次
      rebuild”语义（``_AUTO_REBUILT`` 守卫不变）。
    """
    scope_bundles = tables.meta.get("scope_bundles")
    lazy_row = (tables.meta.get("scope") == "cards"
                and isinstance(scope_bundles, list)
                and bundle not in scope_bundles)
    if not lazy_row:
        return heal_content_mismatch(
            bundle, tables, root=root, mode=mode, data_win=data_win,
            version=version, limit=limit)
    if (augment_row(tables, Path(data_win) / bundle)
            and verify_used(bundle, tables, data_win)):
        _bump("route_generation_stale")                 # 与 heal 路径同口径：每失配包记一次
        _bump("route_heal_inplace")
        logger.warning("route: scoped 库失配行已原位刷新（bundle=%s）", bundle)
        return tables
    _bump("route_heal_inplace_declined")
    logger.warning(
        "route: scoped 库失配行原位刷新失败（bundle=%s）——回退同 scope 单次重建",
        bundle)
    return heal_content_mismatch(
        bundle, tables, root=root, mode=mode, data_win=data_win,
        version=version, limit=limit)


def _health_gate(tables: "Tables", *, rt: Path, root: Path, mode: str,
                 data_win: str | Path, version: str | None,
                 limit: int | None) -> "Tables":
    """打开库后的健康门：未清洁退出/久未校验 → 抽样 used-hash。

    一次游戏更新可能让**多个**包同时失配，因此对 ``report["mismatched"]``
    **逐个**处理（不是只处理第一个）：

    - scoped 库且 bundle 不在 ``scope_bundles``（lazy 补行）：优先
      ``augment_row`` + ``verify_used`` 原位刷新，成功继续下一个（所有 lazy
      行保留）；
    - full 库 / scope 内包：``heal_content_mismatch`` 单代一次 rebuild；前一个
      包 rebuild 后已自洽的后续包（``verify_used`` 通过）直接跳过，不再对同一代
      重复 heal（``_AUTO_REBUILT`` 守卫）；
    - 任一包原位/rebuild 后仍失配 → ``BundleContentMismatch``（带实际 bundle
      名，响亮，不循环）。

    全部处理后再抽样一次；仍失配才用首个仍是失配的 bundle 名响亮。
    """
    key = _path_key(rt)
    if key in _HEALTH_CHECKED:
        return tables
    due, forced = _health_due(rt, tables)
    if not due:
        _HEALTH_CHECKED.add(key)
        return tables
    _bump("route_health_forced" if forced else "route_health_due")
    report = verify_sample(tables, data_win, n=HEALTH_SAMPLE_N)
    if report["mismatched"]:
        logger.warning(
            "route: 健康抽样发现 %d 个包内容失配（%s）——逐个修复"
            "（scoped lazy 行原位刷新，其余单次自动重建）",
            len(report["mismatched"]), ", ".join(report["mismatched"][:5]))
        _bump("route_health_mismatch")
        for bundle in report["mismatched"]:
            # 上一次 rebuild 可能已一并修好后续包（同一代不重复 heal）。
            if verify_used(bundle, tables, data_win):
                continue
            tables = _heal_sampled_bundle(
                bundle, tables, root=root, mode=mode, data_win=data_win,
                version=version, limit=limit)
        retry = verify_sample(tables, data_win, n=HEALTH_SAMPLE_N)
        if retry["mismatched"]:
            raise content_mismatch(retry["mismatched"][0],
                                   "健康抽样逐个修复后仍失配")
    _write_health(rt, report, forced=forced)
    if forced:
        _claim_stale_dirty(rt)
    _HEALTH_CHECKED.add(key)
    return tables


# ---------------------------------------------------------------- 单次自动重建（P0）

def _cache_unavailable(path: Path | str, message: str, *, cause: str = "") -> EnvironmentUnavailable:
    return EnvironmentUnavailable(Problem(
        ProblemKind.ENVIRONMENT, "route_cache_unreadable", str(path), message,
        hint="删除缓存根下的 route.db（派生缓存）后重试；或在战网里扫描/修复游戏文件",
        cause=cause))


def content_mismatch(bundle: str, detail: str = "") -> Exception:
    """route 内容失配的响亮出口（BundleContentMismatch；render 映射 ENV 3）。

    延迟 import bundle_guard：避免把 UnityPy 链在模块导入顺序上提前，同时保持
    typed error 的唯一类（render 的现有类名/类型映射不变）。path=bundle。
    """
    from eidolon.core.infra.bundle_guard import BundleContentMismatch

    return BundleContentMismatch(
        f"{bundle}: route 行内容哈希失配，自动重建后仍不自洽"
        + (f"（{detail}）" if detail else "")
        + "——航线缓存是派生缓存；请战网扫描/修复游戏文件，或删除缓存后显式 refresh",
        path=bundle,
        hint="在战网里扫描/修复游戏文件；或删除缓存根下的 route.db 后重跑以显式 refresh")


def rebuild(*, root: Path, data_win: str | Path, version: str | None = None,
            mode: str = "auto", limit: int | None = None,
            bundles: list[str] | None = None) -> "Tables | None":
    """显式全量重建（refresh 语义；锁内串行）。失败返回 None 或抛原始异常。

    ``bundles``（B 案）：给定清单 → 同 scope 重建（heal 用）；None → 全语料。"""
    rt = _tmp_root(root) if str(mode).strip().lower() == "no-cache" else Path(root)
    return _rebuild_locked(rt, limit=limit, always=True, bundles=bundles,
                           data_win=data_win, version=version)


def _existing_scope_bundles(root: Path) -> list[str] | None:
    """旧库 meta 的 ``scope_bundles``（best-effort；读不到 → None=全量）。

    auto 换代/坏库自动重建时据此**同 scope 重建**：scoped 库不被静默升级成
    全量（全量 = 数百秒级，正是 B 案要避免的首跑形态）；全量库 / 读不出
    （真坏库/旧库无该键）→ None → 全量重建（升级路径保留：显式 refresh）。
    """
    db = Path(root) / DB_NAME
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key='scope_bundles'").fetchone()
            if row is None:
                return None
            val = json.loads(row[0])
            return [str(x) for x in val] if isinstance(val, list) else None
        finally:
            conn.close()
    except (sqlite3.Error, ValueError, TypeError, OSError):
        return None


def heal_content_mismatch(bundle: str, tables: "Tables", *, root: Path, mode: str,
                          data_win: str | Path, version: str | None = None,
                          limit: int | None = None) -> "Tables":
    """内容失配 → stale 留账 → 锁内重建一次 → 重试该包。

    同一代（db 路径 + 文件 mtime_ns）只允许一次自动重建；第二次失配不再重建，
    直接抛 ``BundleContentMismatch``（不循环）。重建失败同样响亮。
    scoped 库（B 案）按 ``scope_bundles`` **同 scope 重建**，不静默升全量；
    但重建 scope 还要纳入 **lazy 补行**：渲染期 ``augment_row`` 补进来的包不在
    初始 ``scope_bundles`` 里，直接按初始清单重建会把它丢掉 → ``fresh.has`` 假
    失配（文件可能只是正常更新）。这类包的处置：

    1. 优先**原位刷新该行**（``augment_row`` 本身就是单包解析 + 锁内
       ``INSERT OR REPLACE``，只动这一包）→ ``verify_used`` 通过即返回，库里
       其它 lazy 补行全部保留（不触发全库重扫/逐包重补）；
    2. 原位刷新失败（锁忙/解析失败/写入失败）或刷新后仍失配 → 回退同 scope
       重建，重建清单 = ``scope_bundles + [bundle]``（去重保序）——只补这一个
       包，不全量升级；重建后仍失配 → ``BundleContentMismatch``（响亮）。
    """
    gen = _generation_key(tables)
    scope_bundles = tables.meta.get("scope_bundles")
    if not isinstance(scope_bundles, list):
        scope_bundles = None
    # 失配包不在初始工作集 ⟹ 它是渲染期 lazy 补进来的行（scoped 库特有边界）。
    lazy_row = scope_bundles is not None and bundle not in scope_bundles
    _bump("route_generation_stale")
    if lazy_row:
        logger.warning(
            "route: %s 内容哈希失配（scoped 库 lazy 补行）——先原位刷新该行，"
            "失败再同 scope 重建", bundle)
    else:
        logger.warning("route: %s 内容哈希失配——标记当前代 stale 并重建一次", bundle)
    if gen in _AUTO_REBUILT:
        raise content_mismatch(bundle, "本代已自动重建过一次，拒绝循环")
    if lazy_row:
        if (augment_row(tables, Path(data_win) / bundle)
                and verify_used(bundle, tables, data_win)):
            _bump("route_heal_inplace")
            logger.warning("route: scoped 库失配行已原位刷新（bundle=%s）", bundle)
            return tables
        _bump("route_heal_inplace_declined")
    rebuild_bundles = scope_bundles
    if lazy_row:
        rebuild_bundles = list(dict.fromkeys([*scope_bundles, bundle]))
    try:
        tables.close()                                 # Windows：旧只读句柄会挡 os.replace
    except Exception:                                  # noqa: BLE001
        pass
    try:
        fresh = rebuild(root=root, mode=mode, data_win=data_win,
                        version=version, limit=limit, bundles=rebuild_bundles)
    except Exception as exc:                           # noqa: BLE001 —— 重建失败必须响亮
        _bump("route_rebuild_failed")
        raise content_mismatch(
            bundle, f"重建失败 {type(exc).__name__}: {exc}") from exc
    if fresh is None:
        _bump("route_rebuild_failed")
        raise content_mismatch(bundle, "重建未取得新库（锁超时/建库失败）")
    _AUTO_REBUILT.add(_generation_key(fresh))
    _bump("route_auto_rebuilt")
    logger.warning("route: 已自动重建航线缓存（bundle=%s）", bundle)
    if not fresh.has(bundle) or not verify_used(bundle, fresh, data_win):
        _bump("route_rebuild_still_mismatch")
        try:
            fresh.close()
        except Exception:                              # noqa: BLE001
            pass
        raise content_mismatch(bundle, "重建后该包仍失配/未入册")
    return fresh


# ---------------------------------------------------------------- 三态（参数化；契约 D）
# route 三态/缓存根的 env 消费已随契约 D 搬到入口边缘层，三态值与缓存根经 GameContext
# （ctx.route_mode / ctx.route_cache）由调用方显式传入——本模块是纯库：只收参数，不读 env、
# 不定位容器。

def _tmp_root(root: Path) -> Path:
    """no-cache 用的临时根（cache_root 树内、按 pid 隔离；不落系统 temp）。

    上游用 repo/output 下的 mkdtemp；产品无 repo 容器——root（=ctx.cache_root）
    由 ensure 的调用方显式传入（设计 §8/§11.1）。"""
    return Path(root) / f"_no_cache_route_{os.getpid()}"


def game_id(data_win: str | Path) -> str:
    """游戏版本**信息**（非键）：manifest 目录名 + 文件大小，只作人类可读线索。"""
    man = Path(data_win) / "asset_manifest.unity3d"
    try:
        st = man.stat()
        return f"{man.parent.name}:{st.st_size}"
    except OSError:
        return str(Path(data_win).name)


def _game_identity(data_win: str | Path, version: str | None) -> dict:
    """当前客户端数据版本身份：`game_build` + `game_manifest`（写库与校验共用）。

    - `game_build` = ctx.version 版本串**末段**（客户端数据 BuildNumber；37.0 = `254477`；
      契约 D：来源=入口边缘已按 root 同装解析的 GameContext.version，不再直读全局
      product.db——拷贝安装/显式指根时全局 product.db 说的可能是别的安装）。
    - `game_manifest` = `game_id(data_win)`（manifest 目录名:大小）——版本串不可读时的兜底。

    **不**用仓内钉版：航线库跟的是本机游戏装。任何失败都吞掉并
    留空串（空 = 不可读，`_load` 据此不判不符）——身份探测绝不让 `ensure()` 崩。
    """
    ident = {"game_build": "", "game_manifest": ""}
    try:
        ver = version or ""
        if ver:
            ident["game_build"] = ver.split(".")[-1].strip()
    except Exception:                                  # noqa: BLE001
        _bump("route_identity_build_unreadable")
    try:
        ident["game_manifest"] = game_id(data_win)
    except Exception:                                  # noqa: BLE001
        _bump("route_identity_manifest_unreadable")
    return ident


_KEY_FIELDS = ("format", "unitypy")


def _fallback_str() -> str:
    try:
        return UnityPy.config.get_fallback_version()
    except Exception:                                  # noqa: BLE001
        return ""


def _keys() -> dict:
    """库有效性键（**不含游戏版本、也不含 fallback**）。

    - `format`：表格式；
    - `unitypy`：解析语义（含 `SerializedFile.__init__` 的版本分支）——升级即重建。

    fallback 只影响建库（已烘进 `version_int`），读路径只认库里的值；它还会随 import 顺序
    在常量间摆动，进键等于自找整库重建。游戏内容变化由逐包内容哈希判定（见 verify）。
    """
    return {"format": ROUTE_FORMAT, "unitypy": UnityPy.__version__}


# ---------------------------------------------------------------- 建库

def _flat_nodes(root) -> list[dict]:
    """TypeTreeNode 树 → 扁平 dict 列表（DFS 序；= `from_list` 的输入格式）。"""
    out = []
    for n in root.traverse():
        d = {"m_Level": n.m_Level, "m_Type": n.m_Type, "m_Name": n.m_Name}
        for k in ("m_ByteSize", "m_Version", "m_TypeFlags", "m_VariableCount",
                  "m_Index", "m_MetaFlag", "m_RefTypeHash"):
            v = getattr(n, k, None)
            if v is not None:
                d[k] = v
        out.append(d)
    return out


def _md5_file(path: Path) -> str:
    """整文件 md5（分块读；35GB 全语料实测 ≈50s，只在建库与 stat 失配时付）。"""
    import hashlib

    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _bundle_tables(path: Path) -> dict:
    """单包 → 航线片段（blocks/nodes/objects/containers/types/externals/header/schemas）。

    `rec["cabs"]`（cab→bundle）只供 build 写**全局** cabs 表；v6 起不落 parts
    （与 nodes 的 path 冗余，且每包一行无法按 cab 查）。

    建库用**现行惰性解析**跑一遍（每个包一次），所以建库成本 ≈ 一次全量首触；
    这正是"auto 命中即跳过"要保的东西。另记**本包内容指纹**（失效判据，见 verify）。
    """
    import hashlib

    br = bundle_lazy.LazyBundle(path)
    env = bundle_lazy.open_env(path)
    st = path.stat()
    rec = {"bundle": path.name,
           "file": {"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                    "md5": _md5_file(path)},
           "blocks": [[uc, cs, fl] for (uc, cs, fl) in br.blocks],
           "nodes": [[off, size, fl, name] for (off, size, fl, name) in br.nodes],
           "cabs": {}, "objects": {}, "containers": {}, "types": {},
           "externals": {}, "header": {}, "schemas": {}}
    for node_name, f in env.files.items():
        if not hasattr(f, "objects"):                   # .resS 等非 SerializedFile
            continue
        cab = Path(node_name).name.lower()
        rec["cabs"][cab] = path.name
        rec["header"][cab] = {
            "version": int(getattr(f.header, "version", 0)),
            # 生效引擎版本 = SerializedFile.version（UnityVersion，bit-packed int）。
            # 不能用 f.unity_version：本游戏全语料它是 "0.0.0"，真值来自 fallback。
            "version_int": int(getattr(f, "version", 0) or 0),
            "version_engine": str(getattr(br, "version_engine", "") or ""),
            "unity_version": str(getattr(f, "unity_version", "") or ""),
            "target_platform": int(getattr(f, "_m_target_platform", 0) or 0),
            "big_id": int(getattr(f, "big_id_enabled", 0) or 0),
            "endian": str(getattr(f.header, "endian", "<") or "<"),
            "enable_type_tree": bool(getattr(f, "_enable_type_tree", True)),
            "flags": int(getattr(f, "flags", 0) or 0),
            "unknown": int(getattr(f, "unknown", 0) or 0),
            "user_information": str(getattr(f, "userInformation", "") or ""),
        }
        rec["externals"][cab] = [str(getattr(e, "path", "")) for e in (f.externals or [])]
        tref = {}
        for ti, t in enumerate(getattr(f, "types", None) or []):
            node = getattr(t, "node", None)
            if node is None:
                continue
            flat = _flat_nodes(node)
            th = hashlib.sha1(json.dumps(flat, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()[:16]
            rec["schemas"][th] = flat
            tref[str(ti)] = {"class_id": int(getattr(t, "class_id", -1)), "tree": th,
                             "old_hash": (getattr(t, "old_type_hash", b"") or b"").hex(),
                             "script_idx": getattr(t, "script_type_index", None)}
        rec["types"][cab] = tref
        rec["objects"][cab] = {str(pid): [int(o.type_id), int(o.byte_start),
                                          int(o.byte_size), int(o.class_id)]
                               for pid, o in (f.objects or {}).items()}
        try:
            # 存**完整 pairs 列表**而不是 dict：AssetBundle 的 m_Container 允许同键多条
            # （实测某 CAB 同一 GUID 多条、path_id 各不相同）；dict 会塌成最后
            # 一条，按名扫描 container 的消费者（ability._school_extra）就找不到目标对象。
            # 注意 pairs 的值是 AssetInfo（不是 PPtr）——path_id 要经 .asset 取。
            rec["containers"][cab] = [[k, int(v.asset.m_PathID)] for k, v in f.container.container]
        except Exception:                              # noqa: BLE001
            _bump("route_build_containers_failed")
            rec["containers"][cab] = []
    br.close()
    bundle_lazy.close_env(env)
    return rec


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _replace_with_retry(tmp: Path, dst: Path, *, attempts: int = 6,
                        delay: float = 0.5) -> None:
    """`os.replace` + Windows 共享冲突重试。

    SQLite 在 Windows 上以 FILE_SHARE_READ|WRITE 打开库（**不共享删除**），所以只要还有
    进程持有旧库只读句柄，`os.replace` 就 WinError 5。短命读者（同时 `_load` 的并发
    worker）毫秒~秒级就会关句柄，重试足够；长命读者挡住时仍然响亮失败（与旧实现同）——
    auto 的版本门保证"命中者"不会同时触发重建，正常负载下碰撞窗口仅在 `_load` 那一瞬。
    """
    for i in range(attempts):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            _bump("route_build_replace_retry")
            time.sleep(delay)


def build(root: Path, *, data_win: str | Path, version: str | None,
          limit: int | None = None,
          bundles: list[str] | None = None) -> dict:
    """建库并原子替换（`route.db.build` → `os.replace`）。返回 meta。

    `bundles=None` → 全语料（既有语义）；给定清单 → **scoped build（B 案）**：
    只建清单内包的行 + 对应全局 cabs/schemas 行，meta 如实记账
    ``scope="cards"`` + ``scope_bundles``（覆盖面清单，rebuild 供同 scope 重建）。
    清单里不存在的包计数跳过（``route_scope_bundle_missing``），不响亮失败——
    scoped 库的覆盖面本来就是"工作集尽力覆盖 + 缺行 lazy 补行"。
    """
    if bundles is None:
        files = sorted(Path(data_win).glob("*.unity3d"), key=lambda p: p.stat().st_size)
        if limit:
            step = max(1, len(files) // limit)
            files = files[::step][:limit]
    else:
        files = []
        for name in dict.fromkeys(bundles):            # 去重保序
            p = Path(data_win) / name
            if p.is_file():
                files.append(p)
            else:
                _bump("route_scope_bundle_missing")
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / (DB_NAME + ".build")
    for old in (tmp, tmp.with_name(tmp.name + "-journal")):
        if old.exists():
            old.unlink()
    conn = sqlite3.connect(tmp)
    replaced = False
    try:
        conn.executescript(_SCHEMA)
        schemas: dict[str, list] = {}
        cabs_map: dict[str, str] = {}
        n_ok = 0
        for p in files:
            try:
                rec = _bundle_tables(p)
            except Exception:                          # noqa: BLE001
                _bump("route_build_bundle_failed")
                continue
            n_ok += 1
            fp = rec["file"]
            conn.execute("INSERT OR REPLACE INTO bundles(name,size,mtime_ns,md5) VALUES(?,?,?,?)",
                         (p.name, fp["size"], fp["mtime_ns"], fp["md5"]))
            for kind in PARTS:
                conn.execute("INSERT OR REPLACE INTO parts(bundle,kind,payload) VALUES(?,?,?)",
                             (p.name, kind, _dump(rec[kind])))
            cabs_map.update(rec["cabs"])
            for h, flat in rec["schemas"].items():
                schemas.setdefault(h, flat)
        conn.executemany("INSERT OR REPLACE INTO cabs(cab,bundle) VALUES(?,?)",
                         list(cabs_map.items()))
        conn.executemany("INSERT OR REPLACE INTO schemas(hash,payload) VALUES(?,?)",
                         [(h, _dump(v)) for h, v in schemas.items()])
        ident = _game_identity(data_win, version)
        meta = {**_keys(), "game": game_id(data_win), "fallback": _fallback_str(), "n_bundles": n_ok,
                "n_cabs": len(cabs_map),
                "game_build": ident["game_build"],
                "game_manifest": ident["game_manifest"],
                # scope 如实记账（B 案）：full=全语料；cards=scoped 工作集，附带
                # scope_bundles 清单供 heal/版本换代时**同 scope 重建**（不静默升全量）。
                "scope": "cards" if bundles else "full",
                # built_at 用 **epoch 秒**：无需解析时区/格式，可直接比大小证明"又建了一次"；
                # 人类可读时间需要时现算（time.strftime）。
                "built_at": int(time.time())}
        if bundles:
            meta["scope_bundles"] = sorted(set(bundles))
        conn.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                         [(k, _dump(v)) for k, v in meta.items()])
        conn.commit()
        conn.close()
        _replace_with_retry(tmp, root / DB_NAME)       # 原子替换（读者要么旧库要么新库）
        replaced = True
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        if not replaced:                               # 建库失败不留 route.db.build（锁的同一纪律）
            for old in (tmp, tmp.with_name(tmp.name + "-journal")):
                try:
                    old.unlink()
                except OSError:
                    pass
    for old in root.glob("route*.json"):               # v3 及以前的 route JSON 布局，清掉
        # B1 收窄（原 `*.json`）：cache root 现与 supply index 同根共存
        #（current.json 在根上），全量 glob 会在建库后把 index 的代账删掉
        #（b1 实验 2026-11-10 实测复现：seeded 渲染下一批整批弃种）。
        try:
            old.unlink()
        except OSError:
            pass
    _bump("route_built")
    return meta


# ---------------------------------------------------------------- 读句柄

class Tables:
    """SQLite 航线库的只读句柄（进程级，一条连接）。

    只加载 `bundles.name` 集合（~1MB，用于 O(1) `has`）；其它一切**按包按需**查询，
    故每 worker 的常驻只随打开过的包增长，而不是全语料。
    """

    def __init__(self, conn: sqlite3.Connection, meta: dict, db_path: Path):
        self._conn = conn
        self._db = db_path
        self._wconn: sqlite3.Connection | None = None
        self.meta = meta
        self._names = {row[0] for row in conn.execute("SELECT name FROM bundles")}
        try:
            self._has_cabs = bool(conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cabs'").fetchone())
        except sqlite3.Error:
            self._has_cabs = False
        self._parts_cache: dict[str, dict] = {}

    # ---- 查询 ----
    def has(self, bundle: str) -> bool:
        return bundle in self._names

    def names(self) -> set[str]:
        return set(self._names)

    def cab_owner(self, cab: str) -> str | None:
        """全局 cab→bundle（v6）；键=小写 basename（`archive:/cab/cab` 也可）。

        旧 v5 库无 cabs 表 / 查询失败 → None + 计数（显式，不静默）；调用方据此
        回退 `bundle_deps` 依赖闭包扫描。
        """
        c = str(cab or "").strip().lower().replace("\\", "/")
        if "/" in c:
            c = c.rsplit("/", 1)[-1]
        if not c:
            _bump("route_cab_owner_empty")
            return None
        if not self._has_cabs:
            _bump("route_cab_table_missing")
            return None
        try:
            row = self._conn.execute("SELECT bundle FROM cabs WHERE cab=?", (c,)).fetchone()
        except sqlite3.Error:
            _bump("route_cab_lookup_failed")
            return None
        if row is None:
            _bump("route_cab_owner_miss")
            return None
        _bump("route_cab_owner_hit")
        return str(row[0])

    def fingerprint(self, bundle: str) -> dict | None:
        row = self._conn.execute(
            "SELECT size, mtime_ns, md5 FROM bundles WHERE name=?", (bundle,)).fetchone()
        if row is None:
            return None
        return {"size": row[0], "mtime_ns": row[1], "md5": row[2]}

    def touch(self, bundle: str, size: int, mtime_ns: int) -> None:
        """stat 变了但内容相同：把这个包的 stat 写回库（免得下个进程再算一次 md5）。

        只读连接不能写 → 懒开一个可写连接；库在只读介质上时静默降级（只多付 md5）。
        """
        try:
            if self._wconn is None:
                self._wconn = sqlite3.connect(self._db, timeout=5)
            self._wconn.execute("UPDATE bundles SET size=?, mtime_ns=? WHERE name=?",
                                (size, mtime_ns, bundle))
            self._wconn.commit()
            _bump("route_stat_refreshed")
        except sqlite3.Error:
            _bump("route_stat_refresh_failed")

    def parts(self, bundle: str) -> dict | None:
        got = self._parts_cache.get(bundle)
        if got is not None:
            return got
        rows = self._conn.execute(
            "SELECT kind, payload FROM parts WHERE bundle=?", (bundle,)).fetchall()
        if not rows:
            return None
        got = {k: json.loads(v) for k, v in rows}
        self._parts_cache[bundle] = got
        return got

    def schema(self, tree_hash: str) -> list | None:
        row = self._conn.execute("SELECT payload FROM schemas WHERE hash=?", (tree_hash,)).fetchone()
        return json.loads(row[0]) if row else None

    def close(self) -> None:
        for c in (self._wconn, self._conn):
            try:
                if c is not None:
                    c.close()
            except Exception:                          # noqa: BLE001
                pass


def _version_verdict(meta: dict, ident: dict) -> str:
    """版本判定：`hit`（一致）/ `mismatch`（自动重建）/ `unknown`（不可判，沿用逐包 verify）。

    优先级（任务卡 §2）：
    - 旧库**两个版本键都没有** + 当前身份可读 → 不符（首跑自动重建升级旧库）；
    - 当前 `game_build` 可读 → 只比 build（build 是数据 BuildNumber，精确到数据版本）；
    - 当前 build 不可读 → 用 `game_manifest` 兜底比；
    - 两者都不可读 → `unknown`，**绝不**据此判不符（否则版本探测失败会每次都重建）。
    """
    stored_build = meta.get("game_build")
    stored_manifest = meta.get("game_manifest")
    cur_build = str(ident.get("game_build") or "").strip()
    cur_manifest = str(ident.get("game_manifest") or "").strip()
    if stored_build is None and stored_manifest is None:
        return "mismatch" if (cur_build or cur_manifest) else "unknown"
    if not (cur_build or cur_manifest):
        return "unknown"
    if cur_build:
        if stored_build is not None:
            return "hit" if stored_build == cur_build else "mismatch"
        # 半旧库（有 manifest 无 build）：落到 manifest 兜底
    if stored_manifest and cur_manifest:
        return "hit" if stored_manifest == cur_manifest else "mismatch"
    return "unknown"


class _DbCorrupt(Exception):
    """航线库自身损坏（打不开 / PRAGMA quick_check 失败 / meta 读不出）。

    内部信号：`ensure` 捕获后在锁内删除并重建一次；重建失败 → ENV。
    绝不让“坏缓存”静默退化成正常惰性路径（那会掩盖环境问题）。
    """

    def __init__(self, path: Path, detail: str):
        super().__init__(f"{path}: {detail}")
        self.path = Path(path)
        self.detail = detail


def _quick_check(conn: sqlite3.Connection) -> str:
    """`PRAGMA quick_check` → "ok" 或失败原因。异常由调用方归一为 _DbCorrupt。"""
    row = conn.execute("PRAGMA quick_check").fetchone()
    return str(row[0]) if row else "quick_check 无返回"


# 进程内 quick_check 通过缓存：键 = (db 路径, db mtime_ns)。同进程反复打开同一
# 代（manifest/locale 多次 peek）不再重扫 300MB 级库；换文件（原子替换）即新键。
# 跨进程/蓝屏后的内容漂移仍是新进程空缓存 → 必扫。
_QUICK_CHECK_OK: set[tuple[str, int]] = set()


def _db_generation(db: Path) -> tuple[str, int]:
    try:
        return (str(db), db.stat().st_mtime_ns)
    except OSError:
        return (str(db), 0)


def _discard_db(root: Path) -> None:
    """删除损坏的航线库与 SQLite 边车文件（重建前的清场；锁持有者调用）。"""
    for name in (DB_NAME, DB_NAME + "-journal", DB_NAME + "-wal", DB_NAME + "-shm"):
        try:
            (Path(root) / name).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            _bump("route_db_discard_failed")


def _load(root: Path, *, data_win: str | Path, version: str | None) -> Tables | None:
    db = root / DB_NAME
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        _bump("route_db_unopenable")
        raise _DbCorrupt(db, f"打不开: {exc}") from exc
    try:
        gen = _db_generation(db)
        if gen not in _QUICK_CHECK_OK:
            check = _quick_check(conn)
            if check != "ok":
                _bump("route_db_quick_check_failed")
                raise _DbCorrupt(db, f"quick_check: {check}")
            _QUICK_CHECK_OK.add(gen)
        meta = {k: json.loads(v) for k, v in conn.execute("SELECT key, value FROM meta")}
    except _DbCorrupt:
        conn.close()
        raise
    except (sqlite3.Error, ValueError, TypeError) as exc:
        conn.close()
        _bump("route_db_quick_check_failed")
        raise _DbCorrupt(db, f"读数失败: {type(exc).__name__}: {exc}") from exc
    for k in _KEY_FIELDS:
        if meta.get(k) != _keys()[k]:
            conn.close()
            _bump(f"route_key_mismatch_{k}")
            return None
    verdict = _version_verdict(meta, _game_identity(data_win, version))
    if verdict == "mismatch":
        conn.close()
        _bump("route_version_mismatch")
        return None
    _bump("route_version_unknown" if verdict == "unknown" else "route_version_hit")
    return Tables(conn, meta, db)


# ---------------------------------------------------------------- 失效（逐包内容指纹）

STALE: set[str] = set()          # 本进程判定为失效的 bundle（供报告/下次 refresh）


def verify(bundle: str, tables: Tables | None, data_win: str | Path) -> bool:
    """本 bundle 的航线行是否仍对应当前文件内容（**used-hash**；P0）。

    - stat 相同**不再直接信任**：仍走进程内缓存的整文件 md5（蓝屏/bit rot 可在
      size/mtime_ns 不变下改内容）；同包同代只哈希一次。
    - stat 失配但内容相同 → 刷新库内 stat 记录（`route_verify_md5_same`）。
    - 内容不同 → 该包失效（`route_stale` + `STALE`），调用方做单次自动重建或
      响亮退出；**绝不整库作废**。
    **绝不整库作废**：每包独立判定。`data_win` 由调用方显式传入（契约 D）。
    """
    if tables is None:
        return False
    rec = tables.fingerprint(bundle)
    if rec is None:
        _bump("route_verify_missing")
        return False
    path = Path(data_win) / bundle
    try:
        st = path.stat()
    except OSError:
        _bump("route_verify_stat_failed")
        STALE.add(bundle)
        return False
    stat_match = (st.st_size == rec["size"] and st.st_mtime_ns == rec["mtime_ns"])
    if stat_match:
        _bump("route_verify_fast")
    else:
        _bump("route_verify_md5")
    same = _used_hash_check(bundle, rec, path, st)
    if same and not stat_match:
        _bump("route_verify_md5_same")
        tables.touch(bundle, st.st_size, st.st_mtime_ns)
    return same


# ---------------------------------------------------------------- 建库串行化（并发 ensure 只重建一次）

LOCK_NAME = DB_NAME + ".lock"          # 原子目录锁（os.mkdir）；与 route.db 同目录，不新增版本文件
_LOCK_STALE_SECS = 60 * 60             # 锁龄 > 1h = 持有者已死（建库分钟级，余量充足）
_LOCK_WAIT_SECS = 60 * 60              # 单进程总等待上限；超时返回 None（禁止静默并发重建）
_LOCK_POLL_SECS = 2.0


def _lock_path(root: Path) -> Path:
    return root / LOCK_NAME


def _clear_stale_lock(lock: Path) -> None:
    """用 rename 抢占式清理陈旧锁：rename 原子，多个等待者只有一个能清。"""
    grave = lock.with_name(f"{lock.name}.stale.{os.getpid()}")
    try:
        os.rename(lock, grave)
    except OSError:
        return
    shutil.rmtree(grave, ignore_errors=True)
    _bump("route_build_lock_stale_cleared")


def _try_acquire_lock(root: Path) -> Path | None:
    """**非阻塞**抢锁：拿到返回锁路径；被别人持有返回 None（不等待）。

    `os.mkdir` 的其它 OSError（权限/介质）向上抛，由调用方响亮降级。
    """
    lock = _lock_path(root)
    try:
        os.mkdir(lock)                                 # 原子：并发只有一个进程成功
    except FileExistsError:
        return None
    try:
        (lock / "owner").write_text(
            f"pid={os.getpid()}\n"
            f"at={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n",
            encoding="utf-8")
    except OSError:
        pass
    _bump("route_build_lock_acquired")
    return lock


def _lock_age(lock: Path) -> float | None:
    """锁龄（秒）；锁已不存在返回 None。"""
    try:
        return time.time() - lock.stat().st_mtime
    except OSError:
        return None


def _release_lock(lock: Path) -> None:
    shutil.rmtree(lock, ignore_errors=True)


def _ensure_root(root: Path) -> None:
    """缓存根就绪（并发建根容忍；mkdir 幂等）。

    冷缓存根（非 git 安装首跑落用户缓存）+ j4 并发首建时，多 worker 同帧
    `mkdir(parents=True)` 同一条父链是 Windows 理论竞态面（CreateDirectory 瞬时
    ERROR_ACCESS_DENIED；exist_ok 只吞 FileExistsError）。处置：瞬时
    PermissionError 且路径已在 → 竞态输者视为成功；仍在 → 退避重试；重试耗尽照抛
    （fail loud 不静默）。渲染语义零触碰。
    """
    for i in range(8):
        try:
            root.mkdir(parents=True, exist_ok=True)
            return
        except PermissionError:
            if root.is_dir():
                return
            time.sleep(0.25 * (i + 1))
    root.mkdir(parents=True, exist_ok=True)


def _rebuild_locked(root: Path, *, limit: int | None, always: bool,
                    data_win: str | Path, version: str | None,
                    corrupt: bool = False,
                    bundles: list[str] | None = None) -> "Tables | None":
    """抢锁建库；等锁期间每 `_LOCK_POLL_SECS` 重试 `_load`（auto）。

    - 抢到锁：auto 再 `_load` 一次（等锁期间别人可能刚建好），仍无则 `build`；`always`
      则无条件 `build`；`finally` 必删锁。
    - `corrupt=True`（调用方已发现库自损坏）：锁内删除库与边车、重建一次；重建失败
      → `route_cache_unreadable`（ENV），不无限重试。
    - 等锁：陈旧锁（锁龄 > 1h，持有者崩溃）用 `os.rename` 抢占清除；总等待超
      `_LOCK_WAIT_SECS` 返回 None + `route_build_lock_timeout`（**不**静默并发重建，
      也**不**动别人仍在持有的锁）。
    - scope（B 案）：给定 `bundles` → 按清单建；未给定且非 `always`（auto 换代/坏库
      自愈）→ 继承旧库 `scope_bundles`（scoped 库不被静默升全量）；`always`
      （显式 refresh）→ 全语料（升级路径）。
    """
    if bundles is None and not always:
        bundles = _existing_scope_bundles(root)
    _ensure_root(root)
    lock = _lock_path(root)
    deadline = time.monotonic() + _LOCK_WAIT_SECS
    got: Path | None = None
    while got is None:
        try:
            got = _try_acquire_lock(root)
        except OSError:
            _bump("route_build_lock_failed")
            return None
        if got is not None:
            break
        if not always and not corrupt:
            try:
                tbl = _load(root, data_win=data_win, version=version)   # 别人可能刚建好
            except _DbCorrupt:
                tbl = None
            if tbl is not None:
                _bump("route_cache_hit")
                return tbl
        age = _lock_age(lock)
        if age is None:
            continue                                   # 锁刚被释放 → 立即再抢
        if age > _LOCK_STALE_SECS:
            _clear_stale_lock(lock)
            continue
        if time.monotonic() >= deadline:
            _bump("route_build_lock_timeout")
            if corrupt:
                raise _cache_unavailable(root / DB_NAME, "航线库损坏且等待重建锁超时")
            return None
        _bump("route_build_lock_wait")
        time.sleep(_LOCK_POLL_SECS)
    try:
        if not always and not corrupt:
            try:
                tbl = _load(root, data_win=data_win, version=version)   # 抢到锁后再确认一次
            except _DbCorrupt:
                corrupt = True
                tbl = None
            if tbl is not None:
                _bump("route_cache_hit")
                return tbl
        elif corrupt:
            try:                                       # 等锁期间别人可能已重建好
                tbl = _load(root, data_win=data_win, version=version)
            except _DbCorrupt:
                tbl = None
            if tbl is not None:
                _bump("route_cache_hit")
                return tbl
        if corrupt:
            _bump("route_db_discarded")
            _discard_db(root)
        try:
            build(root, limit=limit, data_win=data_win, version=version,
                  bundles=bundles)
        except Exception as exc:                       # noqa: BLE001 —— 损坏库重建失败必须 ENV
            if corrupt:
                _bump("route_db_rebuild_failed")
                raise _cache_unavailable(
                    root / DB_NAME,
                    f"航线库损坏且自动重建失败（{type(exc).__name__}: {exc}）",
                    cause=f"{type(exc).__name__}: {exc}") from exc
            raise
        try:
            return _load(root, data_win=data_win, version=version)
        except _DbCorrupt as exc:
            _bump("route_db_rebuild_failed")
            raise _cache_unavailable(root / DB_NAME,
                                     f"航线库重建后仍不可读（{exc.detail}）") from exc
    finally:
        _release_lock(got)


def ensure(*, root: Path, mode: str, data_win: str | Path,
           version: str | None = None, limit: int | None = None) -> Tables | None:
    """按三态取库；返回 None = 本进程不用航线（off/建库失败/等锁超时/无游戏目录）。

    契约 D：`root`（缓存根）与 `mode`（三态）显式传入（来源=GameContext.route_cache /
    route_mode，入口边缘解析），`data_win`/`version` 同显式（BundleStore 调用点自
    ctx 取）。`auto`：命中即用（版本不符视为未命中）；未命中 → 取锁 → 再 `_load`
    一次 → 仍无则建库。`refresh`/`no-cache`：取锁后**无条件**重建，语义同旧版（只是
    串行化）。建库一律由锁持有者执行 ⟹ 永不并发写 `route.db.build`。

    **缓存健康（P0）**：打开库先 `PRAGMA quick_check`；坏库/打不开 → 锁内删库重建
    一次；重建失败 → `route_cache_unreadable`（ENV），不无限重试。命中后用
    `route.dirty` / `route.health` 做未清洁退出加速检测（P1：脏标记或久未校验 →
    抽样 used-hash；失配走同一单次自动重建）。
    """
    m = str(mode).strip().lower()
    if m == "off":
        return None
    rt = _tmp_root(root) if m == "no-cache" else Path(root)
    always = m in ("refresh", "no-cache")
    _ensure_root(rt)
    _begin_session(rt)
    corrupt = False
    if not always:
        try:
            tbl = _load(rt, data_win=data_win, version=version)         # auto
        except _DbCorrupt:
            corrupt = True
            tbl = None
        if tbl is not None:
            _bump("route_cache_hit")
            return _health_gate(tbl, rt=rt, root=root, mode=m,
                                data_win=data_win, version=version, limit=limit)
    tbl = _rebuild_locked(rt, limit=limit, always=always,
                          data_win=data_win, version=version, corrupt=corrupt)
    if tbl is not None:
        tbl = _health_gate(tbl, rt=rt, root=root, mode=m,
                           data_win=data_win, version=version, limit=limit)
    return tbl


def peek_existing(*, root: Path, mode: str, data_win: str | Path,
                  version: str | None = None) -> Tables | None:
    """只读打开**已存在**的航线库（不建库、不触发全语料重建）。

    manifest/locale 包不是 `route.open_env` 的消费点，但若缓存库里已有它们的
    行，消费这些文件时同样要做 used-hash（P0：resolve 的 manifest/locale 同路）。
    这里只“看”现有库，避免一次 manifest 读取就触发全量建库；坏库返回 None
    （后续 BundleStore 的 ensure 会走 quick_check 重建一次）。
    """
    m = str(mode).strip().lower()
    if m == "off":
        return None
    rt = _tmp_root(root) if m == "no-cache" else Path(root)
    try:
        return _load(rt, data_win=data_win, version=version)
    except _DbCorrupt:
        return None


def prewarm(*, root: Path, mode: str, data_win: str | Path,
            version: str | None = None,
            bundles: list[str]) -> "Tables | None":
    """B 案按卡集预热：scoped 建库（只建 ``bundles`` 工作集的行），已命中不重建。

    B1 条件实验（2026-11-10，build/phase1/b1/）：新机器（有 supply index、无
    route.db）首跑 seeded 渲染，首个 `open_bundle` 即触发全量建库——11,159 包 /
    ~350s。渲染前按卡集算 bundle 工作集（``ManifestIndex.card_working_set``，
    定位半程不开包）→ 本入口锁内只建这些包。语义：

    - `mode=off` / 空清单 → None（不建）；
    - 已有有效库（全量或 scoped，键与版本命中）→ 直接用，不重建
      （``route_prewarm_hit``）；
    - 无库 / 版本不符 → 锁内按清单建 scoped 库（并发与 `ensure` 同一锁纪律；
      等锁期间别人建好即直接用）；
    - 建成后 `ensure`（auto）即命中该 scoped 库（meta.scope=cards 如实记账）；
      工作集外的包行缺失 → 渲染时 :func:`augment_row` lazy 补行（或惰性兜底），
      绝不假命中；scoped 库后续可被显式 refresh（全量 build）升级。
    """
    m = str(mode).strip().lower()
    if m == "off" or not bundles:
        return None
    rt = _tmp_root(root) if m == "no-cache" else Path(root)
    _ensure_root(rt)
    _begin_session(rt)
    try:
        tbl = _load(rt, data_win=data_win, version=version)
        if tbl is not None:
            _bump("route_prewarm_hit")
            return tbl
    except _DbCorrupt:
        tbl = None                                     # 坏库交给 _rebuild_locked 清场
    tbl = _rebuild_locked(rt, limit=None, always=False, bundles=list(bundles),
                          data_win=data_win, version=version)
    if tbl is not None:
        tbl = _health_gate(tbl, rt=rt, root=root, mode=m,
                           data_win=data_win, version=version, limit=None)
    return tbl


def augment_row(tables: "Tables", path: Path) -> bool:
    """scoped 库缺行 lazy 补行（B 案）：解析单包 → 锁内 ``INSERT OR REPLACE``。

    渲染遇到工作集外的包（``Tables.has`` False）时调用；只对 ``meta.scope ==
    "cards"`` 的库生效——全量库缺行=游戏更新面，维持既有惰性兜底语义
    （``route_augment_skip_full``）。语义：

    - 锁忙（别人在重建/补行）→ 本轮不补（False），调用方惰性兜底（正确，只是慢）；
    - 行内容 = :func:`_bundle_tables`（单包 md5 + 解析，一次成本）→ 写入走
      ``Tables._wconn``（``touch`` 同款可写连接），提交后 ``Tables.has`` 即真
      （只读连接 autocommit 下次查询可见新行）；cabs/schemas 同并入（同 cab
      多包时后写覆盖——``_resolve_pptr`` 命中会校验 ``(cab, path_id)``，错主
      落 ``cab_owner_bad`` 回依赖闭包扫描，不静默错）；
    - 解析/写入失败 → 回滚 + 计数（``route_augment_parse_failed`` /
      ``route_augment_failed``），**绝不抛**（调用方惰性兜底）；补行成功
      ``route_augment_built``，该包此后走正常 route 路（含 used-hash）。
    """
    if tables.meta.get("scope") != "cards":
        _bump("route_augment_skip_full")
        return False
    root = tables._db.parent                           # noqa: SLF001 —— 同模块内部面
    try:
        got = _try_acquire_lock(root)
    except OSError:
        _bump("route_augment_lock_failed")
        return False
    if got is None:
        _bump("route_augment_lock_busy")
        return False
    rec = None
    try:
        try:
            rec = _bundle_tables(Path(path))
        except Exception:                              # noqa: BLE001 —— 单包失败不致命
            _bump("route_augment_parse_failed")
            return False
        if tables._wconn is None:                      # noqa: SLF001
            tables._wconn = sqlite3.connect(tables._db, timeout=5)
        conn = tables._wconn
        try:
            fp = rec["file"]
            conn.execute(
                "INSERT OR REPLACE INTO bundles(name,size,mtime_ns,md5) VALUES(?,?,?,?)",
                (rec["bundle"], fp["size"], fp["mtime_ns"], fp["md5"]))
            for kind in PARTS:
                conn.execute(
                    "INSERT OR REPLACE INTO parts(bundle,kind,payload) VALUES(?,?,?)",
                    (rec["bundle"], kind, _dump(rec[kind])))
            conn.executemany("INSERT OR REPLACE INTO cabs(cab,bundle) VALUES(?,?)",
                             list(rec["cabs"].items()))
            conn.executemany("INSERT OR REPLACE INTO schemas(hash,payload) VALUES(?,?)",
                             [(h, _dump(v)) for h, v in rec["schemas"].items()])
            conn.commit()
        except sqlite3.Error:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            _bump("route_augment_failed")
            return False
    finally:
        _release_lock(got)
    tables._names.add(rec["bundle"])                   # noqa: SLF001 —— has() 即真
    _bump("route_augment_built")
    logger.info("route: scoped 库缺行补行 %s（lazy augment）", rec["bundle"])
    return True


# ---------------------------------------------------------------- 重建（shim）

class _Ext:
    __slots__ = ("path",)

    def __init__(self, path: str):
        self.path = path


class _Header:
    __slots__ = ("version", "data_offset", "endian", "metadata_size", "file_size", "reserved")

    def __init__(self, version: int, endian: str = "<"):
        self.version = int(version)
        self.data_offset = 0
        self.metadata_size = 0
        self.file_size = 0
        self.reserved = b""
        self.endian = endian


class _SerType:
    __slots__ = ("class_id", "node", "is_stripped_type", "script_type_index",
                 "old_type_hash", "m_ClassName", "m_NameSpace", "m_AssemblyName",
                 "type_dependencies", "m_Flags", "m_TreeHash")

    def __init__(self, class_id: int, node, script_idx=None, old_hash: bytes = b""):
        self.class_id = int(class_id)
        self.node = node
        self.is_stripped_type = False
        self.script_type_index = script_idx
        self.old_type_hash = old_hash
        self.m_ClassName = ""
        self.m_NameSpace = ""
        self.m_AssemblyName = ""
        self.type_dependencies = []
        self.m_Flags = 0


class SerializedFileShim(_RealSerializedFile):
    """航线重建的 SerializedFile 替身：不读元数据区，对象字节仍按需从块流读。

    必须是**真子类**：`Environment.container` 用 `isinstance(f, SerializedFile)` 过滤 cab，
    非子类会让 container 表整个变空（实测同包 1,911 键全丢 → `container_get` 恒 None）。
    不调 `super().__init__`（那会读元数据区）；所有属性由本类自行铺满。
    """

    # 进程级 schema→TypeTreeNode 缓存：58,891 次类型引用只对应 1,534 棵树，
    # 按实例重建等于把 parse 又做一遍（实测 j1 +6.2%/j4 +19% 的直接原因）。
    _TREE_CACHE: dict[str, object] = {}

    @classmethod
    def _tree(cls, tree_hash: str, tables: Tables):
        node = cls._TREE_CACHE.get(tree_hash)
        if node is None:
            flat = tables.schema(tree_hash)
            if flat is None:
                raise KeyError(f"schemas 缺 {tree_hash}")
            node = TypeTreeNode.from_list(flat)
            cls._TREE_CACHE[tree_hash] = node
            _bump("route_tree_built")
        else:
            _bump("route_tree_reused")
        return node

    def __init__(self, cab: str, bundle: str, parts: dict, tables: Tables, br, env):
        # 注意：不调用父类 __init__（它读元数据区）；下面铺满父类方法会用到的属性
        self.parent = None
        self.cab_file = "CAB-UnityPy_Mod.resS"
        self.name = cab
        self.is_dependency = False
        self.is_changed = False
        self.environment = env
        hdr = parts["header"][cab]
        self.header = _Header(hdr["version"])
        self.header.endian = str(hdr.get("endian") or "<")
        self.unity_version = str(hdr.get("unity_version") or "")
        # 生效引擎版本：只认 version_int（UnityVersion 的 bit-packed int）。
        # 缺/零 = 库不可信，响亮失败——**禁止**回退到 unity_version 或全局 fallback：
        # 那正是 v1 的 bug 形态（全语料 "0.0.0" → 解码器走 Unity<4 分支）。
        version_int = int(hdr.get("version_int") or 0)
        if not version_int:
            raise ValueError(
                f"{bundle}/{cab}: header 无有效 version_int（旧格式库？需 refresh）")
        self.version = UnityVersion(version_int)
        self._enable_type_tree = bool(hdr.get("enable_type_tree", True))
        self.flags = int(hdr.get("flags") or 0)
        self.unknown = int(hdr.get("unknown") or 0)
        self.userInformation = str(hdr.get("user_information") or "")
        self.big_id_enabled = int(hdr.get("big_id") or 0)
        self._m_target_platform = int(hdr.get("target_platform") or 0)
        try:
            self.target_platform = BuildTarget(self._m_target_platform)
        except Exception:                              # noqa: BLE001
            self.target_platform = self._m_target_platform
        self.externals = [_Ext(p) for p in parts["externals"][cab]]
        self.ref_types = []
        self.script_types = []
        self._cache = {}
        self.assetbundle = None
        by_id: dict[int, _SerType] = {}
        for ti_s, t in parts["types"][cab].items():
            node = self._tree(t["tree"], tables)
            by_id[int(ti_s)] = _SerType(t["class_id"], node, script_idx=t.get("script_idx"),
                                        old_hash=bytes.fromhex(t.get("old_hash") or ""))
        self._types_by_id = by_id
        self.types = [by_id[k] for k in sorted(by_id)]
        off = size = None
        for (n_off, n_size, _flags, n_path) in parts["nodes"]:
            if Path(n_path).name.lower() == cab:
                off, size = int(n_off), int(n_size)
                break
        if off is None:
            raise KeyError(f"nodes 无 {bundle} → {cab}")
        self.reader = EndianBinaryReader(bundle_lazy.BlockStream(br, off, size))
        self.reader.endian = str(hdr.get("endian") or "<")   # 字节序必须跟随 CAB 头
        self.objects: dict[int, ObjectReader] = {}
        for pid_s, (type_id, byte_start, byte_size, class_id) in parts["objects"][cab].items():
            pid = int(pid_s)
            self.objects[pid] = ObjectReader(
                assets_file=self, reader=self.reader, path_id=pid,
                type_id=int(type_id), serialized_type=by_id.get(int(type_id)),
                class_id=int(class_id), type=ClassIDType(int(class_id)),
                byte_start=int(byte_start), byte_size=int(byte_size),
                is_destroyed=None, is_stripped=None)
        pairs = [(k, _AssetInfo(PPtr(m_FileID=0, m_PathID=int(pid), assetsfile=self)))
                 for k, pid in parts["containers"][cab]]
        self._container = ContainerHelper(pairs)
        # 镜像完备性断言：shim 必须铺满真 SerializedFile 的实例属性全集。
        missing = _MIRROR_REQUIRED - set(vars(self))
        if missing:
            raise RuntimeError(f"{bundle}/{cab}: shim 缺属性 {sorted(missing)}"
                               f"（UnityPy 升级后需同步镜像面）")

    @property
    def container(self):
        return self._container

    @property
    def files(self):
        return self.objects


def open_env(bundle: str, tables: Tables, br) -> UnityPy.Environment:
    """用航线行重建一个包的 Environment（调用方持有 `br` = bundle_lazy.LazyBundle）。

    **消费前置**：调用方必须先对该 bundle 做 :func:`verify_used`（BundleStore
    在 open_env 前调用；失配走单次自动重建/响亮）。本函数只管用行重建，不做
    内容校验（它没有 data_win/缓存根上下文）。
    """
    parts = tables.parts(bundle)
    if parts is None:
        raise KeyError(f"航线库无 {bundle} 的 parts")
    env = UnityPy.Environment()
    for (n_off, n_size, _flags, n_path) in parts["nodes"]:
        cab = Path(n_path).name
        cab_l = cab.lower()
        if cab_l not in parts["header"]:
            # 资源节点（.resS 等）：**必须注册成 reader cab**——纹理的 m_StreamData 靠
            # cab 名向 Environment 要流数据（ResourceReader.get_cab）。漏注册即
            # FileNotFoundError: Resource file CAB-….resS not found（实测）。
            rd = EndianBinaryReader(bundle_lazy.BlockStream(br, int(n_off), int(n_size)))
            env.register_cab(cab, rd)
            env.files[cab] = rd
            _bump("route_resource_nodes")
            continue
        shim = SerializedFileShim(cab_l, bundle, parts, tables, br, env)
        env.register_cab(cab, shim)
        env.files[cab] = shim
    if not env.container.container_dict:
        raise RuntimeError(f"{bundle}: 航线重建后 container 为空（shim 未被认作 SerializedFile？）")
    _bump("route_env_rebuilt")
    return env
