"""bundle_guard — 包级读防护（内容哈希 + 好副本整包回退；可选轴，默认关）。

定位（上游坏盘加固判据卡第 3/4 件）：
- **内容哈希**：expected md5（显式传入 > route.db 行账）与盘上文件不符 → 响亮
  （`BundleContentMismatch`，不静默出图）。md5 只在被加载的包上付、单遍顺序读
  （干净数据下每包一次 ~几十 ms 量级）。
- **好副本整包回退**：哈希失配时，若好副本源可用（显式 `good_dir` 参数指向的同名
  文件），校验「size 相等 + block 布局逐项全等 + 好副本 md5==expected」三项**全过**
  才采纳；采纳=留账（计数 + logger.warning），**不静默**。整包回退比跨文件拼块安全
  （拼块要求 block 布局逐项全等且残差面不可控——上游实证：修复只接受逐字节全等）。
- **route.db 信任门**：route 行账 md5 作 expected 前先验「行存在 + md5 是 32 hex +
  行 stat(size, mtime_ns) 与盘上文件一致」；任一不满足 → **不采信**（计数 +
  跳过哈希轴，不静默当它可信）。stat 一致仍可能被"建库后才 rot"骗过——bit rot
  不改 mtime/size 是上游实证判别特征，expected 的价值正在于它来自**建库时刻**的
  独立观测。

坏块 typed error 与单次重试住 `bundle_lazy`（块级读层，自有代码=块号/物理偏移/uc/cs/
flags 的唯一来源），本模块做文件级两件 + `load_defended` 统一收口面（渲染路径直连
`UnityPy.load` 的 UnityFS 调用点走它进惰性层）。
选型裁决（上游）：**wrapper 形态，不 vendor UnityPy**——块级上下文收益已由 bundle_lazy
自有解析持有；vendor 整包需遮蔽 site-packages（import 序敏感 + .pyd 双事实源）。

启用面（无 env 旋钮；上游的 guard 模式/好副本目录环境开关已删除）：
- `load_defended`：块级防护恒开（惰性路优先，不适配退老路并留账）；
- `vetted_path` / `load`：默认零行为零 IO（原样返回/直读）；`expected_md5` 在场即启用
  哈希轴，`tables`（route 行账）在场即走信任门轴；`good_dir` 只收显式参数。

遥测：模块级计数器 `stats()`；警告条目只走 `logger.warning`（诊断面，不进 manifest）。
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import UnityPy

from eidolon.core.infra import bundle_lazy

logger = logging.getLogger(__name__)

_MD5_RE = re.compile(r"^[0-9a-f]{32}$")

STATS: dict[str, int] = {}


def _bump(key: str, n: int = 1) -> None:
    STATS[key] = STATS.get(key, 0) + n


def warn(msg: str) -> None:
    """留账警告（人类可读诊断面；只进 logger，不进任何 manifest/warnings 字段）。"""
    logger.warning("%s", msg)
    _bump("guard_warnings")


def stats() -> dict:
    return dict(STATS)


class BundleContentMismatch(RuntimeError):
    """expected md5 与盘上文件不符（响亮；禁静默出图，禁「能解就算修好」）。

    ``path`` / ``hint`` 是可选结构化定位面：route 内容失配把它设为 bundle 名与
    “战网扫描/修复或显式 refresh”，render 的逐卡映射优先采用（仍归 ENV 3）。
    """

    def __init__(self, message: str, *, path: str | None = None,
                 hint: str | None = None) -> None:
        super().__init__(message)
        self.path = path
        self.hint = hint


# ---------------------------------------------------------------------------
# expected 来源：显式参数 > route.db 行账（信任门）
# ---------------------------------------------------------------------------

def expected_from_route(bundle: str, tables, path: Path) -> tuple[str | None, str]:
    """route.db 行账 md5 作 expected 的信任门。

    返回 `(expected_md5 | None, reason)`：
    - tables 为 None（航线 off/建库失败）→ (None, "no_route")；
    - 行缺失 → (None, "route_row_missing")；
    - md5 非 32 hex → (None, "untrusted_md5_format")；
    - 行 stat (size, mtime_ns) 与盘上不一致 → (None, "untrusted_stat")
      （行账描述的不是当前文件代际——**不得静默采信**，计数后跳过哈希轴）；
    - 全过 → (md5, "trusted")。
    """
    if tables is None:
        return None, "no_route"
    rec = tables.fingerprint(bundle)
    if rec is None:
        _bump("guard_expected_route_row_missing")
        return None, "route_row_missing"
    md5 = str(rec.get("md5") or "")
    if not _MD5_RE.match(md5):
        _bump("guard_expected_untrusted_format")
        warn(f"guard: {bundle} route 行 md5 非法（{md5[:16]!r}…）——不采信，跳过哈希轴")
        return None, "untrusted_md5_format"
    try:
        st = path.stat()
    except OSError:
        _bump("guard_expected_untrusted_stat")
        return None, "untrusted_stat"
    if st.st_size != rec.get("size") or st.st_mtime_ns != rec.get("mtime_ns"):
        _bump("guard_expected_untrusted_stat")
        warn(f"guard: {bundle} route 行 stat 与盘上不符（行 "
             f"size={rec.get('size')}/mtime={rec.get('mtime_ns')}，盘上 "
             f"size={st.st_size}/mtime={st.st_mtime_ns}）——md5 不采信，跳过哈希轴")
        return None, "untrusted_stat"
    return md5, "trusted"


def md5_file(path: Path) -> str:
    """整文件 md5（分块单遍顺序读；独立实现保本模块可独占 import）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _blocks_layout(path: Path) -> tuple[int, list[tuple[int, int, int]]]:
    """(file_size, [(uc, cs, flags)…])——只解析头/blocksInfo（不动数据块）。"""
    br = bundle_lazy.LazyBundle(path)
    try:
        return br.file_bytes, list(br.blocks)
    finally:
        br.close()


# ---------------------------------------------------------------------------
# 防护加载：load_defended（块级两件的统一收口面）
# ---------------------------------------------------------------------------

def load_defended(path: str | Path, *, budget: int | None = None):
    """块级防护加载：惰性路（typed error + 单次重试）优先，不适配显式退老路并留账。

    覆盖面收口：渲染路径直连 ``UnityPy.load`` 的 UnityFS 调用点（dbf 容器装载、
    resolve_asset_ref 的 manifest/locale 包、supply 帧链的 shader/material 包）一律
    走这里——坏块炸在惰性层=BundleBlockCorruptError 全上下文响亮，不会退化成无上下文
    裸异常。非 UnityFS（裸 SerializedFile/assets）/加密/未知压缩 → LazyUnsupported →
    退 ``UnityPy.load``（计数 + logger.warning；裸序列化文件无块层可护，行为=现状）。
    BundleBlockCorruptError **直通不回退**（坏的是数据，老路只会丢上下文再炸一次）。
    """
    path = Path(path)
    try:
        return bundle_lazy.open_env(path, budget=budget)
    except bundle_lazy.BundleBlockCorruptError:
        raise
    except Exception as exc:                            # noqa: BLE001 —— 不适配类统一退老路
        _bump("guard_legacy_fallback")
        warn(f"guard: {path.name} 惰性路不适配，退老路 UnityPy.load "
             f"（{type(exc).__name__}: {exc}）")
        return UnityPy.load(str(path))


# ---------------------------------------------------------------------------
# 门：vetted_path（哈希轴 + 好副本整包回退）
# ---------------------------------------------------------------------------

def vetted_path(path: str | Path, *, tables=None, expected_md5: str | None = None,
                good_dir: str | Path | None = None) -> Path:
    """内容哈希门：返回可用路径（原路径 / 好副本路径）；失配且无好副本 → 响亮。

    默认（无显式 expected 且无 tables 行账）**零行为**：原样返回，零 IO。
    启用：`expected_md5` 在场=显式哈希轴；`tables` 在场=route 行账轴（先过信任门）。
    流量：仅当哈希轴激活时对**本包**付一次单遍 md5（只扫被加载包，禁全量扫盘）。
    """
    path = Path(path)
    explicit = expected_md5 is not None
    if tables is None and not explicit:
        _bump("guard_off_passthrough")
        return path

    # 1) expected：显式参数优先，否则 route 行账（过信任门）
    if explicit:
        expected = expected_md5
        source = "explicit"
    else:
        expected, reason = expected_from_route(path.name, tables, path)
        source = f"route:{reason}"
    if not expected:
        _bump("guard_no_expected")
        return path

    # 2) 单遍哈希比对
    actual = md5_file(path)
    _bump("guard_hash_checked")
    if actual == expected:
        _bump("guard_hash_ok")
        return path
    _bump("guard_hash_mismatch")
    warn(f"guard: {path.name} 内容哈希失配（expected={expected} actual={actual} "
         f"source={source}）——bit rot 不改 mtime/size，响亮处理")

    # 3) 好副本整包回退（三项校验全过才采纳；留账不静默）
    if good_dir is not None:
        good = Path(good_dir) / path.name
        try:
            ok, why = _good_copy_ok(good, path, expected)
        except Exception as exc:                        # noqa: BLE001 —— 头损坏等一律按拒绝响亮
            ok, why = False, f"好副本校验异常: {type(exc).__name__}: {exc}"
        if ok:
            _bump("guard_fallback_used")
            warn(f"guard: {path.name} 回退好副本（size+block 布局+md5 三验全过）"
                 f"→ {good}")
            return good
        _bump("guard_fallback_rejected")
        warn(f"guard: {path.name} 好副本校验未过（{why}）——拒绝回退")
        raise BundleContentMismatch(
            f"{path.name}: 内容哈希失配且好副本不可用（{why}）；"
            f"expected={expected} actual={actual} good={good}")
    raise BundleContentMismatch(
        f"{path.name}: 内容哈希失配（expected={expected} actual={actual} "
        f"source={source}）且未提供好副本源（good_dir）——禁静默出图")


def _good_copy_ok(good: Path, orig: Path, expected: str) -> tuple[bool, str]:
    """好副本三验：size 相等 + block 布局逐项全等 + 好副本 md5==expected。

    （上游判例：同版本判据=同 size / 同 blocks 数；只接受整包回退，不拼块。）
    """
    if not good.is_file():
        return False, f"好副本不存在: {good}"
    orig_size, orig_blocks = _blocks_layout(orig)
    good_size, good_blocks = _blocks_layout(good)
    if orig_size != good_size:
        return False, f"size 不等（原 {orig_size} vs 好 {good_size}）——非同版本"
    if orig_blocks != good_blocks:
        return False, (f"block 布局不等（原 {len(orig_blocks)} 块 vs 好 "
                       f"{len(good_blocks)} 块或逐项不同）——非同版本布局")
    good_md5 = md5_file(good)
    if good_md5 != expected:
        return False, f"好副本 md5 {good_md5} != expected {expected}"
    return True, "ok"


# ---------------------------------------------------------------------------
# 包装加载（可选便捷面：显式 expected 的整包加载，真「快照+同遍 hash」）
# ---------------------------------------------------------------------------

def load(path: str | Path, *, expected_md5: str | None = None,
         good_dir: str | Path | None = None) -> UnityPy.Environment:
    """快照读整包（读的同遍算 md5）→ 校验过 → 从快照字节建 Environment。

    显式 expected 的调用方（非 route 面）用这个可以做到「哈希与读取同遍」——
    只读一次盘。route 面走 `vetted_path`（惰性路不能整包读，md5 独立单遍）。
    好副本回退：校验逻辑同 vetted_path（三验全过），用快照字节建 env。
    默认（无 expected）= 直读，与 legacy 调用逐字节同态（禁白付整包快照）。
    """
    path = Path(path)
    if not expected_md5:
        _bump("guard_off_passthrough")
        return UnityPy.load(str(path))          # 无 expected 无从校验——退直读
    data, actual = _read_and_hash(path)
    _bump("guard_hash_checked")
    if actual == expected_md5:
        _bump("guard_hash_ok")
        return _env_from_bytes(data, path)
    _bump("guard_hash_mismatch")
    warn(f"guard: {path.name} 内容哈希失配（expected={expected_md5} "
         f"actual={actual}）——响亮处理")
    if good_dir is not None:
        good = Path(good_dir) / path.name
        try:
            ok, why = _good_copy_ok(good, path, expected_md5)
        except Exception as exc:                        # noqa: BLE001 —— 头损坏等一律按拒绝响亮
            ok, why = False, f"好副本校验异常: {type(exc).__name__}: {exc}"
        if ok:
            _bump("guard_fallback_used")
            warn(f"guard: {path.name} 回退好副本（size+block 布局+md5 三验全过）"
                 f"→ {good}")
            gdata, _ = _read_and_hash(good)
            return _env_from_bytes(gdata, good)
        _bump("guard_fallback_rejected")
        warn(f"guard: {path.name} 好副本校验未过（{why}）——拒绝回退")
    raise BundleContentMismatch(
        f"{path.name}: 内容哈希失配（expected={expected_md5} actual={actual}）"
        "——禁静默出图")


def _read_and_hash(path: Path) -> tuple[bytes, str]:
    """快照读 + 同遍 md5（单遍，不二次读盘）。"""
    h = hashlib.md5()
    parts: list[bytes] = []
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            parts.append(chunk)
            h.update(chunk)
    return b"".join(parts), h.hexdigest()


def _env_from_bytes(data: bytes, path: Path) -> UnityPy.Environment:
    import io

    env = UnityPy.Environment()
    env.load_file(io.BytesIO(data), name=path.name)
    return env
