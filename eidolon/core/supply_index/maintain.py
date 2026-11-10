"""maintain — 旧代清理维护（列代/删旧代/保留策略；设计 §3「删除是维护动作，
不是产品功能」+ §11 P4「旧代清理作为维护脚本」的前置落位）。

命令面（cli maintain）：默认列代（只读）；`--prune --keep N [--dry-run]` 删旧代。

列代：gens/gen-* 全目录逐一登记——
- valid    有 index.sqlite 的代（读 meta：game_id/full_build/built_at/counts）；
- current  current.json 指代的代（恒保留）；
- synthetic 目录名 gen-synth*（五态演练副本；resolve_gens 已把它们排除在 diff
  自动选代外）；
- leftover 无 index.sqlite 的残目录（演练焚副本的 WAL/SHM sidecar 残留判例——
  2026-11-07 真实缓存 gens/ 下四个 gen-synth* 残目录；_burn 已源头修复，存量由
  本脚本收口）。

删旧代（prune）保留策略：**current 恒留** + 其余 valid 代按 built_at 新→旧留
keep-1 个；synthetic/leftover 一律清（非代，不占保留名额）。安全语义：
- 删代前 **integrity 前置**（介质事故账 2026-11-07：现行代全量 blob 扫，
  bad>0 响亮不删——先 `integrity --repair` 自愈；坏账上删代可能烧掉修复所需的
  行账参照）；
- 锁=CacheLock（本包 lock.py 判例：原子 mkdir + 陈锁抢占 + 超时响亮——与 build
  互斥，禁边建边删）；
- 删除=逐代整目录 rmtree（gen 目录自包含：DB+sidecar；blobs/ 共享内容寻址面
  **不随代删**——设计 §0 非目标「无 GC 子系统」，孤儿 blob 回收不做）；
- current.json 缺失时 fail-safe：valid 代全不删（只清 synthetic/leftover）；
- keep<1 拒绝；逐代删除错误收集、响亮回报（不静默半删）。
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.lock import CacheLock
from eidolon.core.supply_index.paths import SupplyLayout

_SYNTH_PREFIX = "gen-synth"


def _gen_meta(db_path: Path) -> dict:
    """代 DB meta 摘要（缺表/缺键如实容忍——残代也可能被列）。"""
    out: dict = {}
    if not db_path.is_file():
        return out
    try:
        conn = S.connect(db_path, readonly=True)
    except sqlite3.Error:
        return out
    try:
        for k in ("game_id", "full_build", "built_at", "locale", "code_version"):
            row = conn.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
            if row is not None:
                out[k] = row["value"]
        for k in ("counts_cards", "counts_items", "counts_blobs"):
            row = conn.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
            if row is not None:
                out[k] = int(row["value"])
    except Exception:  # noqa: BLE001  残代 meta 读不动=如实返回部分账
        pass
    finally:
        conn.close()
    return out


def _as_layout(root) -> SupplyLayout:
    """入口归一（prune 内部/测试传 layout 复用；字符串/Path 走构造）。"""
    return root if isinstance(root, SupplyLayout) else SupplyLayout(root)


def list_generations(cache_root) -> dict:
    """列代：gens/ 下全部 gen-* 目录 + current 绑定 + 残目录识别（只读）。"""
    layout = _as_layout(cache_root)
    cur = layout.read_current()
    cur_gen = (cur or {}).get("generation")
    entries = []
    if layout.gens_dir.is_dir():
        for d in sorted(layout.gens_dir.glob("gen-*")):
            if not d.is_dir():
                continue
            db = d / "index.sqlite"
            meta = _gen_meta(db)
            if not db.is_file():
                state = "leftover"
            elif cur_gen == f"gen-{meta.get('game_id')}" and meta.get("game_id"):
                state = "current"
            elif d.name.startswith(_SYNTH_PREFIX):
                state = "synthetic"
            else:
                state = "valid"
            entries.append({
                "dir": d.name, "state": state, "db": bool(db.is_file()),
                "db_mb": round(db.stat().st_size / 1e6, 1) if db.is_file() else 0,
                **meta,
            })
    return {"cache_root": str(layout.root),
            "current": cur_gen,
            "keep_policy": "current 恒留 + valid 按 built_at 新→旧（prune --keep N）",
            "generations": entries,
            "counts": {
                "valid": sum(1 for e in entries if e["state"] == "valid"),
                "synthetic": sum(1 for e in entries if e["state"] == "synthetic"),
                "leftover": sum(1 for e in entries if e["state"] == "leftover"),
            }}


def _prunable(layout: SupplyLayout, keep: int) -> tuple[list[dict], dict]:
    """保留策略裁决：返回 (待删清单, 账面)。current 恒留；valid 按 built_at
    新→旧留 keep-1；synthetic/leftover 一律删。current.json 缺失=valid 全留
    （fail-safe：没有 current 绑定就不裁 valid 代）。"""
    listing = list_generations(layout)
    cur_gen = listing["current"]
    valid = [e for e in listing["generations"] if e["state"] == "valid"]
    trash: list[dict] = []
    if cur_gen is None:
        # fail-safe：无 current 绑定（代序不可靠）——valid 全留
        pass
    else:
        keepers = {e["dir"] for e in valid
                   if f"gen-{e.get('game_id')}" == cur_gen}
        ranked = sorted((e for e in valid
                         if f"gen-{e.get('game_id')}" != cur_gen),
                        key=lambda e: (int(e.get("built_at") or 0), e["dir"]),
                        reverse=True)
        keepers |= {e["dir"] for e in ranked[:max(0, keep - 1)]}
        for e in valid:
            if e["dir"] not in keepers:
                e = {**e, "why": "beyond-keep"}
                trash.append(e)
    for e in listing["generations"]:
        if e["state"] in ("synthetic", "leftover"):
            trash.append({**e, "why": e["state"]})
    return trash, {"keep": keep, "current": cur_gen,
                   "valid_total": len(valid),
                   "prunable": len(trash),
                   "prunable_dirs": [e["dir"] for e in trash]}


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def prune(cache_root, *, keep: int = 2, dry_run: bool = False) -> dict:
    """删旧代（保留策略见模块头）。删代前 integrity 前置（现行代全量扫；
    bad>0 响亮不删）。dry_run=只出账不删除（免 14s integrity——账面标注）。"""
    if keep < 1:
        raise ValueError(f"--keep须≥1（current 恒留），得到 {keep}")
    layout = _as_layout(cache_root)
    trash, plan_acc = _prunable(layout, keep)
    out: dict = {"cache_root": str(layout.root), "mode": "dry-run" if dry_run
                 else "prune", "keep": keep, "plan": plan_acc}
    if not trash:
        out["ok"] = True
        out["note"] = "无可删代（保留策略内全留）"
        return out
    if dry_run:
        out["ok"] = True
        out["would_delete"] = [{**e, "dir_mb": round(
            _dir_size(layout.gens_dir / e["dir"]) / 1e6, 1)} for e in trash]
        out["note"] = ("dry-run 只走账不删除（integrity 前置在真删时执行；"
                       "blobs 共享面不随代删——设计 §0 非目标）")
        return out

    # 删代前 integrity 前置（介质判例：坏账上删代=烧修复参照；现行代存在才扫）
    cur = layout.read_current()
    if cur is not None and layout.gen_db(cur.get("game_id", "")).is_file():
        from eidolon.core.supply_index.integrity import scan as _integrity_scan

        conn = S.connect(layout.gen_db(cur["game_id"]), readonly=True)
        try:
            findings = _integrity_scan(conn, layout)
        finally:
            conn.close()
        if findings["bad"]:
            raise RuntimeError(
                f"删代前 integrity 前置：现行代 bad={findings['bad']}"
                f"（missing={len(findings['missing'])} "
                f"mismatch={len(findings['mismatch'])}）——先 `integrity --repair` "
                "自愈到 0 bad 再删（介质事故账 2026-11-07）")
        out["integrity_precheck"] = {"rows": findings["rows"],
                                     "ok": findings["ok"]}

    deleted, errors = [], []
    with CacheLock(layout.lock_dir, purpose="maintain-prune"):
        # 锁内重裁决（build 可能刚切了 current——删前账必须新鲜）
        trash, plan_acc = _prunable(layout, keep)
        out["plan"] = plan_acc
        cur_gen = (layout.read_current() or {}).get("generation")
        for e in trash:
            d = layout.gens_dir / e["dir"]
            if not d.is_dir():
                continue
            if cur_gen and e["dir"] == cur_gen:
                errors.append({"dir": e["dir"], "why": "refuse-current"})
                continue
            try:
                size = _dir_size(d)
                shutil.rmtree(d)
                deleted.append({"dir": e["dir"], "why": e.get("why"),
                                "mb": round(size / 1e6, 1)})
            except OSError as exc:
                errors.append({"dir": e["dir"],
                               "why": f"{type(exc).__name__}: {exc}"})
    out["deleted"] = deleted
    out["errors"] = errors
    out["ok"] = not errors
    return out


def run(cache_root, *, do_prune: bool = False, keep: int = 2,
        dry_run: bool = False) -> dict:
    """CLI 组合面：默认列代；--prune 走删代。"""
    if not do_prune:
        return list_generations(cache_root)
    return prune(cache_root, keep=keep, dry_run=dry_run)
