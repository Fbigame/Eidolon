"""selfheal — 三层自愈编排 + 留账（auto 模式专属；require-cache/offline 不 import 本模块）。

三层（todo 2026-11-07-eidolon-supply-selfheal 判据卡）：
- L1 索引：SupplyIndex 构造内建 PRAGMA quick_check（含 DB 打不开形态，warm.py）；
  坏→auto 全量重建（cold.build=锁+重建+原子发布，route.db ensure 判例）；非 auto
  响亮「索引损坏需重建」。
- L2 blob：装配撞 SupplyBlobCorruptError → 沿 recorded source（items.source_json/
  manifest_json）**单次**重推导（integrity.rederive_one=repair 单点形态）→ 重推导
  sha 与行账**全等才算修好** → **单次重试**装配；二次失配=响亮（单次重试铁律：
  循环重试会掩盖介质故障）。
- L3 source：重推导仍≠行账 sha → integrity 诊断分级响亮（版本换代=整库重建判据 /
  同代源坏）。

留账：repair/重建/重推导计数落代库 meta（selfheal_*），integrity/audit/bench 报告
读取；mass-bad 批量口径：坏块 ≥MEDIA_EVENT_MIN_BAD 块或占比 >MEDIA_EVENT_RATIO
=「介质级事件」标记 + 建议人工介入，**禁止静默自愈一行行滚**（L2 单跑重推导到达
同线即停）。

模块纪律：本模块允许 import warm（纯 warm 面）+ 懒 import cold/integrity（UnityPy
面，仅 auto 路径触达）；warm.py 不反向 import 本模块——纯 warm 机器证明
（offline/require-cache + blocker）零退化。
"""
from __future__ import annotations

import time
from pathlib import Path

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.paths import SupplyLayout
from eidolon.core.supply_index.warm import (
    SupplyBlobCorruptError,
    SupplyIndex,
    SupplyIndexCorruptError,
)

# 介质级事件阈值（任务口径「如 >1% 或 >N 块」）：bad≥32 块 或 bad/rows>1%。
MEDIA_EVENT_MIN_BAD = 32
MEDIA_EVENT_RATIO = 0.01

_COUNTER_DELTAS = {
    "selfheal_l1_rebuilds": 0,
    "selfheal_l2_rederives": 0,
    "selfheal_l2_failures": 0,
    "selfheal_repair_items": 0,
}


class SupplyMediaEventError(RuntimeError):
    """介质级事件（mass-bad 超阈值）——停止单跑静默自愈，建议人工介入。"""


def media_event(bad: int, rows: int) -> dict | None:
    """mass-bad 批量口径：超阈值=「介质级事件」标记（None=未超）。

    报告头标记位（integrity 扫描 / L2 单跑限额共用同一判据）。"""
    if bad <= 0 or rows <= 0:
        return None
    ratio = bad / rows
    if bad >= MEDIA_EVENT_MIN_BAD or ratio > MEDIA_EVENT_RATIO:
        return {
            "media_event": True,
            "bad": bad,
            "rows": rows,
            "ratio": round(ratio, 4),
            "verdict": (
                f"介质级事件：坏块 {bad}/{rows}（{ratio:.2%}）超阈值"
                f"（≥{MEDIA_EVENT_MIN_BAD} 块或 >{MEDIA_EVENT_RATIO:.0%}）"
                "——建议人工介入（integrity --repair / 全量重建），"
                "禁止静默自愈一行行滚"),
        }
    return None


# ---------------------------------------------------------------------------
# 留账（代库 meta selfheal_*；integrity/audit/bench 报告读取）
# ---------------------------------------------------------------------------

def read_counters(conn) -> dict[str, str]:
    """代库 meta 里的自愈留账（selfheal_* 键；只读面）。"""
    return {r["key"]: r["value"] for r in conn.execute(
        "SELECT key,value FROM meta WHERE key LIKE 'selfheal_%'")}


def bump_counters(db_path: Path | str, *, l1_rebuilds: int = 0,
                  l2_rederives: int = 0, l2_failures: int = 0,
                  repair_items: int = 0, event: dict | None = None) -> dict:
    """自愈留账落代库 meta（写连接；发布 DB 翻 WAL=已知无害账，P3 记账）。

    返回写后全量留账。调用方责任：只在自愈路径（auto/repair）调——纯 warm 面零写。"""
    conn = S.connect(db_path)
    try:
        cur = {k: v for k, v in read_counters(conn).items()}
        deltas = {"selfheal_l1_rebuilds": l1_rebuilds,
                  "selfheal_l2_rederives": l2_rederives,
                  "selfheal_l2_failures": l2_failures,
                  "selfheal_repair_items": repair_items}
        for k, d in deltas.items():
            if d:
                cur[k] = str(int(cur.get(k, "0") or 0) + d)
        if event:
            cur["selfheal_last_event"] = S.cjson(
                {"time": int(time.time()), **event})
        conn.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                         sorted(cur.items()))
        conn.commit()
        return cur
    finally:
        conn.close()


def _bump_best_effort(idx: SupplyIndex, **kw) -> None:
    """留账尽力而为（留账失败不掩盖响亮失败本身）。"""
    try:
        bump_counters(idx.db_path, **kw)
    except Exception:                                   # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# L1 索引：open 自检（warm 内建）→ auto 全量重建 / 非 auto 响亮
# ---------------------------------------------------------------------------

def _clean_db_sidecars(db_path: Path) -> list[str]:
    """DB sidecar 卫生（P3 蓝屏判例：旧 -wal 按盐值恢复旧帧=毒化新库）。"""
    removed = []
    for suf in ("-wal", "-shm", "-journal"):
        p = Path(str(db_path) + suf)
        try:
            if p.exists():
                p.unlink()
                removed.append(p.name)
        except OSError:
            pass
    return removed


def ensure_index(cache_root: Path | str, *, game: Path, locale: str,
                 auto: bool = False) -> tuple[SupplyIndex, dict]:
    """L1 消费口：SupplyIndex 构造内建 quick_check（含打不开形态）。

    坏 → auto：全量重建（cold.build；锁+重建+原子发布=route.db ensure 判例）后
    重绑句柄；非 auto：SupplyIndexCorruptError 响亮「索引损坏需重建」。
    **无现行代形态（P1-11 返工 R1）**：current.json 缺失 / current 指代库缺失
    （SupplyIndex 构造 FileNotFoundError）——auto 走 L1 全量重建（同一重建编排，
    留账 l1_health 记 no-current）；非 auto 译成干净 SupplyIndexCorruptError
    「先冷建」（CLI 不裸 FileNotFoundError）。
    返回 (idx, L1 留账)。重建前清现行代 sidecar（毒化判例）；重建后留账进新库
    meta（selfheal_l1_rebuilds / selfheal_last_event）。game/locale 必填
    （auto 重建=cold 面，显式身份）。"""
    acct: dict = {"l1_corrupt_detected": False, "l1_health": None,
                  "l1_rebuilt": False, "sidecars_removed": []}
    # health_policy="full"：L1 检测恒 quick_check 全检（T2 决策账）——auto 是自愈
    # 编排入口，检测语义零弱化（含 bit rot 不改 mtime 形态）；产品小进程快路面
    # （stamp 档）才懒检。
    idx: SupplyIndex | None
    try:
        idx = SupplyIndex(cache_root, locale=locale, health_policy="full")
    except FileNotFoundError as exc:
        # 无现行代（current.json 缺失 / 指代库缺失）：auto=走 L1 重建；非 auto=
        # 干净响亮（不裸 traceback）
        if not auto:
            raise SupplyIndexCorruptError(
                f"supply 缓存无现行代（{exc}）——先冷建（cold build 全量）或 "
                "auto 模式自动重建") from exc
        idx = None
        acct.update(l1_corrupt_detected=True,
                    l1_health=f"no-current: {exc}")
    if idx is not None and idx.health_error is None:
        return idx, acct
    if idx is not None:
        acct.update(l1_corrupt_detected=True, l1_health=idx.health_error)
        if not auto:
            raise SupplyIndexCorruptError(
                f"supply 索引损坏需重建（generation={idx.generation}，"
                f"db={idx.db_path}，{idx.health_error}）——require-cache/offline "
                "不自愈：人工重建（cold build 全量）或 auto 模式自动重建")
    # auto：重建（UnityPy 面=合法 auto 路径；warm 主面不触达本分支）
    if idx is not None:
        acct["sidecars_removed"] = _clean_db_sidecars(idx.db_path)
    from eidolon.core.supply_index import cold

    built = cold.build(cache_root, game=game, locale=locale,
                       skip_prebuild_guard=True)
    if idx is None:
        idx = SupplyIndex(cache_root, locale=locale, health_policy="full")
    else:
        idx.close()
        idx.__init__(cache_root, locale=locale, health_policy="full")
    if idx.health_error:
        raise SupplyIndexCorruptError(
            f"L1 重建后 quick_check 仍坏（{idx.health_error}；db={idx.db_path}）"
            "——人工介入（介质/存储层排障优先）")
    acct["l1_rebuilt"] = True
    acct["build"] = {k: built.get(k) for k in
                     ("mode", "game_id", "items", "blobs", "wall_s")}
    try:
        bump_counters(idx.db_path, l1_rebuilds=1, event={
            "kind": "l1_rebuild", "why": acct["l1_health"][:200],
            "generation": idx.generation})
    except Exception:                                   # noqa: BLE001
        pass
    return idx, acct


# ---------------------------------------------------------------------------
# L2 blob：装配撞 SupplyBlobCorruptError → 单次重推导 → 单次重试（铁律）
# ---------------------------------------------------------------------------

def _l2_limit(idx: SupplyIndex) -> int:
    """L2 单跑重推导上限=介质级事件线（≥32 块或 >1% blobs 行）。"""
    row = idx.conn.execute("SELECT COUNT(*) FROM blobs").fetchone()
    return max(MEDIA_EVENT_MIN_BAD, int(row[0] * MEDIA_EVENT_RATIO))


def assemble_with_heal(idx: SupplyIndex, cards: list[str], *, cache_root,
                       game: Path, locale: str,
                       rederive=None) -> tuple[dict, dict]:
    """auto 装配循环（L2 编排）：{role: 计数} + 自愈留账 dict。

    撞 SupplyBlobCorruptError → 单次重推导（rederive 注入口，缺省
    integrity.rederive_one=repair 单点形态）→ 单次重试；二次失配=响亮且**不再
    重推导**；重推导失败（L3 ≠行账）原样上抛（已带诊断分级）。重推导次数到达
    介质级事件线=SupplyMediaEventError 响亮停（禁静默自愈一行行滚）。"""
    if rederive is None:
        from eidolon.core.supply_index.integrity import rederive_one as rederive
    sections: dict[str, int] = {}
    acct: dict = {"l2_rederives": 0, "l2_failures": 0, "healed": [],
                  "limit": _l2_limit(idx)}
    for cid in cards:
        plan = idx.plan(cid)
        if plan is None:
            continue
        try:
            bundle = idx.assemble(plan)
        except SupplyBlobCorruptError as exc:
            if acct["l2_rederives"] >= acct["limit"]:
                acct["l2_failures"] += 1
                _bump_best_effort(idx, l2_failures=1, event={
                    "kind": "l2_media_event", "card": cid,
                    "blob": exc.payload_sha[:12], "heals": acct["l2_rederives"]})
                raise SupplyMediaEventError(
                    f"介质级事件：本次装配重推导 {acct['l2_rederives']} 块已到上限 "
                    f"{acct['limit']}（blobs 占比口径）——禁止静默自愈一行行滚，"
                    f"人工介入：integrity --repair 或全量重建"
                    f"（中断于 {exc.ctx}: {exc.path.name}）") from exc
            acct["l2_rederives"] += 1
            acct["healed"].append(exc.payload_sha[:12])
            rederive(cache_root, exc.payload_sha, game=game, locale=locale)
            try:
                bundle = idx.assemble(plan)          # 单次重试（铁律：仅一次）
            except SupplyBlobCorruptError as exc2:
                acct["l2_failures"] += 1
                _bump_best_effort(idx, l2_failures=1, event={
                    "kind": "l2_retry_fail", "card": cid,
                    "blob": exc2.payload_sha[:12]})
                raise RuntimeError(
                    f"L2 自愈后装配仍失配（{exc2.ctx}: {exc2.path.name}，行账 "
                    f"{exc2.payload_sha[:12]}…）——单次重试铁律：不再重推导"
                    "（循环重试会掩盖介质故障）；人工介入：integrity --repair / "
                    "全量重建") from exc2
        for role in bundle:
            sections[role] = sections.get(role, 0) + 1
    return sections, acct
