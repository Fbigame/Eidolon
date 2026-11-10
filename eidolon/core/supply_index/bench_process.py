"""bench_process — 进程级 warm 墙钟 bench（T1 warm-perf 车；任务书 §3.T1）。

测量命题：P2 账面 per-card 6ms p50 是「open 之后、kit LRU 已暖」的进程内数字；
产品=多次小进程调用，每次调用要付 interpreter 启动+import+SupplyIndex open（含
quick_check）+首卡首 kit 装配。本模块把**单卡全新 Python 子进程**走真实入口
（import → SupplyIndex → plan → assemble）的分段墙钟测出来：

    interpreter_start / imports / index_open / plan / assemble / supply_total /
    wall_total

分段口径：
- interpreter_start（spawn→entry）：父进程 perf_counter 基准减子进程入口
  perf_counter——Windows QPC/Linux CLOCK_MONOTONIC 均为系统级单调钟，跨进程可比；
  含 Python 启动+-m 机制+包 init+argparse（--cache-root 显式传参，子进程免默认根
  解析——该项计入产品但属入口边缘，单测另记）。
- imports（entry→import 完）：warm 模块链（PIL+numpy+本包 schema/paths/kit_codec/
  text_codec）——进程级大头之一。
- index_open：SupplyIndex 构造（current.json+代库探测；T2 前含 PRAGMA quick_check）。
- plan / assemble：与 bench.bench_warm 同口径（plan+assemble，text 全域段不计入）。
- supply_total = imports+open+plan+assemble（验收「不含 interpreter」口径）。
- wall_total：父进程 spawn→exit 全墙钟（验收「含 interpreter」口径）。

样本（任务书）：基准卡集 + 10 随机（种子 42，排除基准集重叠）+ 单卡重复
（--single-repeat，缺省 8）；OS 暖两轮（round1/round2），round1 首样本单独标注
first_touch=冷态口径（Windows 无用户态 cache-drop API——冷态=进程级首触 DB/blob
页的诚实近似，如实标注不冒充全冷）。另有 bare `python -c pass` 对照（纯解释器
启动+退出，给 interpreter_start 定标）。基准卡集=显式 --cards 或本代 DB 抽样 53
（Phase 5 定案：上游 corpus 语料门不搬）。

输出 JSON（stdout；--out 落盘可选）。串行跑（并行 spawn 争 CPU 污染计时）。
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time


# ---------------------------------------------------------------------------
# 子进程测量（child 模式：print 单份分段 JSON 到 stdout）
# ---------------------------------------------------------------------------

def child_measure(cache_root: str, card_id: str) -> dict:
    """单卡全新进程分段测量：entry→imports→open→plan→assemble。

    本函数在**全新 Python 子进程**里跑（CLI `bench-process --child`）；返回分段
    秒数 dict（单调钟绝对值，父进程做差出 interpreter_start）。"""
    t_entry = time.perf_counter()
    from eidolon.core.supply_index.warm import SupplyIndex, SupplyMissingError

    t_imports = time.perf_counter()
    idx = SupplyIndex(cache_root)
    t_open = time.perf_counter()
    plan = idx.plan(card_id)
    t_plan = time.perf_counter()
    error = None
    roles: dict[str, int] = {}
    if plan is None:
        error = "card-not-in-cards"
    elif plan.missing:
        error = f"missing:{plan.missing[0][:120]}"
    else:
        bundle = idx.assemble(plan)
        roles = {r: 1 for r in bundle}
    t_assemble = time.perf_counter()
    idx.close()
    t_close = time.perf_counter()
    probe = dict(getattr(idx, "probe", {}) or {})
    return {
        "card": card_id,
        "t_entry": t_entry, "t_imports": t_imports, "t_open": t_open,
        "t_plan": t_plan, "t_assemble": t_assemble, "t_close": t_close,
        "error": error, "roles": roles, "probe": probe,
    }


# ---------------------------------------------------------------------------
# 父进程编排（样本集 × 轮次；串行 spawn）
# ---------------------------------------------------------------------------

def _spawn_child(card_id: str, cache_root: str) -> tuple[dict, float, float]:
    """spawn 单卡子进程：返回 (child segments, t_spawn_before, t_after)。

    perf_counter 跨进程可比（QPC 系统级单调钟）——interpreter_start=子 t_entry
    −父 t_spawn_before（含 Popen 创建开销，如实计入）。"""
    t_spawn = time.perf_counter()
    p = subprocess.run(
        [sys.executable, "-m", "eidolon.core.supply_index", "bench-process",
         "--child", "--card", card_id, "--cache-root", cache_root],
        capture_output=True, text=True, timeout=600)
    t_after = time.perf_counter()
    if p.returncode != 0:
        raise RuntimeError(
            f"bench-process 子进程失败 rc={p.returncode} card={card_id}: "
            f"{p.stderr.strip()[-400:]}")
    seg = json.loads(p.stdout)
    return seg, t_spawn, t_after


def _spawn_bare_interpreter() -> float:
    """bare `python -c pass` 全墙钟（纯解释器启动+退出对照；单样本）。"""
    t0 = time.perf_counter()
    subprocess.run([sys.executable, "-c", "pass"], capture_output=True,
                   timeout=120)
    return (time.perf_counter() - t0) * 1000


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def _agg(samples: list[dict], key: str) -> dict:
    vals = [s[key] for s in samples if s.get(key) is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals),
            "p50": round(_pct(vals, 0.5), 2), "p95": round(_pct(vals, 0.95), 2),
            "mean": round(statistics.fmean(vals), 2),
            "min": round(min(vals), 2), "max": round(max(vals), 2)}


def _finalize_sample(seg: dict, t_spawn: float, t_after: float,
                     *, first_touch: bool, kind: str) -> dict:
    """子进程分段 → 样本行（ms；supply_total 与 wall_total 合成）。"""
    supply_total = (seg["t_assemble"] - seg["t_entry"]) * 1000
    return {
        "kind": kind, "card": seg["card"], "first_touch": first_touch,
        "error": seg["error"], "roles_n": len(seg["roles"]),
        "probe": seg["probe"],
        "interpreter_start_ms": round((seg["t_entry"] - t_spawn) * 1000, 2),
        "imports_ms": round((seg["t_imports"] - seg["t_entry"]) * 1000, 2),
        "index_open_ms": round((seg["t_open"] - seg["t_imports"]) * 1000, 2),
        "plan_ms": round((seg["t_plan"] - seg["t_open"]) * 1000, 2),
        "assemble_ms": round((seg["t_assemble"] - seg["t_plan"]) * 1000, 2),
        "close_ms": round((seg["t_close"] - seg["t_assemble"]) * 1000, 2),
        "supply_total_ms": round(supply_total, 2),
        "wall_total_ms": round((t_after - t_spawn) * 1000, 2),
    }


def _round_stats(samples: list[dict]) -> dict:
    seg_keys = ("interpreter_start_ms", "imports_ms", "index_open_ms",
                "plan_ms", "assemble_ms", "supply_total_ms", "wall_total_ms")
    ok = [s for s in samples if not s["error"]]
    stats = {k: _agg(ok, k) for k in seg_keys}
    sup = [s["supply_total_ms"] for s in ok if s["supply_total_ms"]]
    stats["segment_share_pct"] = {
        k: round(statistics.fmean([s[k] for s in ok]) /
                 statistics.fmean(sup) * 100, 1)
        for k in ("imports_ms", "index_open_ms", "plan_ms", "assemble_ms")
        if sup}
    return {"n_samples": len(samples), "n_ok": len(ok),
            "n_error": len(samples) - len(ok),
            "errors": [f"{s['card']}: {s['error']}" for s in samples
                       if s["error"]][:10],
            "segments_ms": stats}


def _sample_cards(cache_root: str, *, cards: list[str] | None, random_n: int,
                  seed: int) -> tuple[list[str], list[str]]:
    """(基准卡集, random N)——random 从 cards 表全集抽（排除基准集重叠，种子固定）。

    基准卡集=显式 cards（Phase 5 定案）；缺省=bench.sample_cards（本代 DB 抽样 53，
    种子 42——上游 corpus 语料门不搬）。"""
    from eidolon.core.supply_index.bench import sample_cards
    from eidolon.core.supply_index.warm import SupplyIndex

    if cards is None:
        cards = sample_cards(cache_root)
    with SupplyIndex(cache_root) as idx:
        all_cards = idx.card_ids()
    base = set(cards)
    pool = [c for c in all_cards if c not in base]
    import random as _random
    rng = _random.Random(seed)
    rand = rng.sample(pool, min(random_n, len(pool))) if random_n > 0 else []
    return list(cards), rand


def run_subprocess(cache_root: str, *, cards: list[str] | None = None,
                   rounds: int = 2, random_n: int = 10,
                   single_repeat: int = 8, seed: int = 42,
                   bare_n: int = 3) -> dict:
    """进程级 bench 主入口（父进程编排；串行 spawn；JSON 可序列化返回）。

    cards=None=本代 DB 抽样 53 张（sample_cards 口径）。"""
    t0 = time.perf_counter()
    base_cards, rand = _sample_cards(cache_root, cards=cards, random_n=random_n,
                                     seed=seed)
    single_card = base_cards[0] if base_cards else (rand[0] if rand else None)
    bare_ms = sorted(_spawn_bare_interpreter() for _ in range(max(bare_n, 1)))
    rounds_out = []
    for r in range(1, max(rounds, 1) + 1):
        samples: list[dict] = []
        seq = ([(c, "base") for c in base_cards] + [(c, "random") for c in rand]
               + [(single_card, "single_repeat")] * max(single_repeat, 0))
        first = True
        for card_id, kind in seq:
            seg, t_spawn, t_after = _spawn_child(card_id, cache_root)
            samples.append(_finalize_sample(seg, t_spawn, t_after,
                                            first_touch=first, kind=kind))
            first = False
        # 冷态单独标注：round1 首触样本（进程级首触口径，见模块头）
        cold = [s for s in samples if s["first_touch"]]
        body = _round_stats(samples)
        body["round"] = r
        body["cold_first_touch"] = cold[0] if cold else None
        body["warm_base_only"] = _round_stats(
            [s for s in samples if s["kind"] == "base" and not s["first_touch"]]
        )["segments_ms"]
        body["single_repeat"] = _round_stats(
            [s for s in samples if s["kind"] == "single_repeat"])
        body["single_card"] = single_card
        rounds_out.append(body)
    warm = rounds_out[-1] if rounds_out else None
    return {
        "bench": "process-level-warm",
        "cache_root": cache_root,
        "sample": {"base_cards": len(base_cards), "random": len(rand),
                   "single_repeat": single_repeat, "single_card": single_card,
                   "seed": seed, "rounds": rounds},
        "bare_interpreter_ms": {"n": len(bare_ms), "min": round(min(bare_ms), 2),
                                "median": round(bare_ms[len(bare_ms) // 2], 2)},
        "rounds": rounds_out,
        "warm_summary_round": warm["round"] if warm else None,
        "acceptance_warm": None if warm is None else {
            "supply_only_excl_interp": {
                "p50": warm["segments_ms"]["supply_total_ms"]["p50"],
                "p95": warm["segments_ms"]["supply_total_ms"]["p95"],
                "target": "p50<=200 p95<=400（OS 暖，不含 interpreter start）"},
            "total_incl_interp": {
                "p50": warm["segments_ms"]["wall_total_ms"]["p50"],
                "p95": warm["segments_ms"]["wall_total_ms"]["p95"],
                "target": "p50<=500（含 interpreter start）"},
        },
        "wall_s": round(time.perf_counter() - t0, 1),
    }
