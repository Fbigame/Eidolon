"""bench — 实测收口（设计 §1 预算表逐项对照；预算是设计目标不是承诺，未达如实记）。

测量面：warm 批量（显式卡集）p50/p95 + 吞吐、plan 查询单价、blob 解码单价、
cold 定向单卡 p50/p95、命中率、存储 GB（**纯实测**——D-决策 4：不做任何外推，
partial 代只报实测，全量存储口径以 full 代实跑为准）。设计 §8：
不做运行时预算/告警/自动 GC——本模块只输出数字，一次跑完即收口。

卡集来源（Phase 5 定案）：``cards`` 显式参数；缺省=本代 cards 表抽样 53 张
（种子固定——上游 corpus_meta 语料门不搬）。CLI ``--cards`` 提供、缺省走 DB 抽样。
"""
from __future__ import annotations

import json
import random
import statistics
import time
from pathlib import Path

from eidolon.core.supply_index.paths import SupplyLayout
from eidolon.core.supply_index.warm import SupplyIndex, account_for_cards


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def sample_cards(cache_root: Path | str, *, n: int = 53, seed: int = 42) -> list[str]:
    """bench 缺省卡集：本代 cards 表抽样 N 张（种子固定可复跑）。

    上游 gate=corpus_meta.selected('full') 语料门（Phase 5 定案：corpus_meta
    不搬）——卡集来源改显式参数或本代 DB 抽样，测量轴口径不变。"""
    with SupplyIndex(cache_root) as idx:
        rows = [r["card_id"] for r in idx.conn.execute("SELECT card_id FROM cards")]
    return random.Random(seed).sample(rows, min(n, len(rows)))


def bench_warm_full(cache_root: Path | str, *, locale: str | None = None) -> dict:
    """全卡 warm 吞吐（cards 表全集，repeat=1）：单卡=plan+assemble（全 role 分发
    含 kit 六面重组（共享 LRU）/gems/png/wm；text 全域段一次/进程不计入单卡——
    会话级摊销）。单件解码贴线项另测（bench_decode_lines——assemble 整墙不等于
    单件解码，分桶归属失真判例）。

    缺席归因口径（Phase 5 返工 R2）：**吞吐分母=可装配卡（ok 卡）**——absent
    两类（零期望/locator≠ok，数据缺席）装配是零语义墙钟，不进分母也不算失败，
    单列计数（empty_plan_cards/accounted_absent）；**full 代且 missing_gap==0
    → "partial": false**（缺席可归因 ≠ 失败，与 build 发布门同口径）；gap>0
    或 full_build=0 才 partial。"""
    walls: list[float] = []
    query_walls: list[float] = []
    sections: dict[str, int] = {}
    n_empty = 0
    with SupplyIndex(cache_root, locale=locale) as idx:
        fb = idx.conn.execute(
            "SELECT value FROM meta WHERE key='full_build'").fetchone()
        full_build = bool(fb and fb["value"] == "1")
        cards = idx.card_ids()
        acct = account_for_cards(idx.conn, cards)
        ok_set = set(acct["ok"])
        for cid in cards:
            if cid not in ok_set:
                continue          # absent/gap 卡不进吞吐分母（归因另账）
            t0 = time.perf_counter()
            plan = idx.plan(cid)
            t1 = time.perf_counter()
            bundle = idx.assemble(plan)
            t2 = time.perf_counter()
            if len(bundle) == 0:
                n_empty += 1              # 防御：ok 卡装配空=账面坏，不进分母
                continue
            for role in bundle:
                sections[role] = sections.get(role, 0) + 1
            walls.append((t2 - t0) * 1000)
            query_walls.append((t1 - t0) * 1000)
    counts = acct["counts"]
    n1 = counts["absent_expectationless"]
    n2 = counts["absent_locator_missing"]
    gap = counts["missing_gap"]
    return {
        "cards": len(cards), "n_samples": len(walls),
        "empty_plan_cards": n1 + n2,      # 空 plan=数据缺席合法形态（单列计数）
        "accounted_absent": {"expectationless": n1, "locator_missing": n2},
        "missing_gap": gap,
        "missing_gap_cards": acct["samples"]["missing_gap"],
        "partial": (not full_build) or gap > 0,
        "repeat": 1,
        "wall_ms": {"p50": round(_pct(walls, 0.50), 2),
                    "p95": round(_pct(walls, 0.95), 2),
                    "mean": round(statistics.fmean(walls), 2) if walls else 0},
        "plan_query_ms": {"p50": round(_pct(query_walls, 0.50), 3),
                          "p95": round(_pct(query_walls, 0.95), 3)},
        "throughput_cards_per_s": round(len(walls) / (sum(walls) / 1000), 1)
        if walls else 0,
        "sections": dict(sorted(sections.items())),
    }


def bench_decode_lines(cache_root: Path | str, *, n_portrait: int = 300,
                       n_golden: int = 100, n_wm: int = 200, seed: int = 42,
                       locale: str | None = None) -> dict:
    """单件解码贴线项（<10ms 校准口径；v4 §1「单图片加载+解码」行）：
    blob 读+文件 sha 校验 / PIL 全解 **分段计时**（P3 件3：open 开销占比实测面
    ——pack/raw tier 取舍的数据面），按域分列（随机样本，种子固定）。
    kit 面分冷/热（LRU 首解 vs 缓存命中）；text 面=读+sha（TTF 无解码语义）。"""
    import io as _io
    import random as _random

    from PIL import Image

    from eidolon.core.supply_index import kit_codec as KC
    from eidolon.core.supply_index import schema as S

    out: dict = {}
    with SupplyIndex(cache_root, locale=locale) as idx:
        rng = _random.Random(seed)

        def _png_line(data: bytes) -> tuple[float, float]:
            """(read+sha 后的 PIL 全解 ms)——调用方自计 read 段。"""
            t0 = time.perf_counter()
            img = Image.open(_io.BytesIO(data))
            img.load()
            _ = img.tobytes()
            return (time.perf_counter() - t0) * 1000

        def _account(label: str, read_walls: list[float],
                     decode_walls: list[float]) -> None:
            total = [a + b for a, b in zip(read_walls, decode_walls)]
            rs = statistics.fmean(read_walls) if read_walls else 0.0
            ts = statistics.fmean(total) if total else 0.0
            out[label] = {
                "n": len(total),
                "read_sha_ms": {"p50": round(_pct(read_walls, 0.5), 2),
                                "p95": round(_pct(read_walls, 0.95), 2)},
                "decode_ms": {"p50": round(_pct(decode_walls, 0.5), 2),
                              "p95": round(_pct(decode_walls, 0.95), 2)},
                "total_ms": {"p50": round(_pct(total, 0.5), 2),
                             "p95": round(_pct(total, 0.95), 2)},
                "open_share_pct": round(rs / ts * 100, 1) if ts else 0.0,
            }

        # portrait / golden / wm：抽样单件 png（读+sha 与解码分段计时）
        for label, domain, kind, n in (("portrait", "art", "portrait", n_portrait),
                                       ("portrait_golden", "art", "portrait_golden",
                                        n_golden),
                                       ("watermark", "watermark", "watermark",
                                        n_wm)):
            if kind == "portrait_golden":
                # golden 的 item 词同 portrait，kind 住 params（P1 键面）
                rows = idx.conn.execute(
                    "SELECT item_key FROM items WHERE domain=? AND item=? "
                    "AND params_json LIKE ?",
                    (domain, "portrait", '%"' + kind + '"%')).fetchall()
            else:
                rows = idx.conn.execute(
                    "SELECT item_key FROM items WHERE domain=? AND item=?",
                    (domain, kind)).fetchall()
            rows = rng.sample(rows, min(n, len(rows)))
            read_walls: list[float] = []
            decode_walls: list[float] = []
            for r in rows:
                roles = idx._item_blob_roles(r["item_key"])
                br = next(iter(roles.values()))
                p = idx.layout.blob_path(
                    br["payload_sha256"],
                    ext=KC.BLOB_CODEC_EXT.get(br["codec"] or "png", ".png"))
                t0 = time.perf_counter()
                data = p.read_bytes()
                if S.sha256_hex(data) != br["payload_sha256"]:
                    raise RuntimeError(f"blob sha mismatch {p.name}")
                read_walls.append((time.perf_counter() - t0) * 1000)
                decode_walls.append(_png_line(data))
            _account(label, read_walls, decode_walls)
        # gems：三件（读+sha+解码分段）
        rows = idx.conn.execute(
            "SELECT item_key FROM items WHERE domain='gems'").fetchall()
        read_walls, decode_walls = [], []
        for r in rows:
            br = next(iter(idx._item_blob_roles(r["item_key"]).values()))
            p = idx.layout.blob_path(
                br["payload_sha256"],
                ext=KC.BLOB_CODEC_EXT.get(br["codec"] or "png", ".png"))
            t0 = time.perf_counter()
            data = p.read_bytes()
            assert S.sha256_hex(data) == br["payload_sha256"]
            read_walls.append((time.perf_counter() - t0) * 1000)
            decode_walls.append(_png_line(data))
        _account("gem", read_walls, decode_walls)
        # kit：冷（LRU 清空首解）/热（缓存命中）
        cold_walls, hot_walls = [], []
        for f in sorted(idx.kit_frames()):
            idx._shared.clear()
            t0 = time.perf_counter()
            idx.kit(f)
            cold_walls.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            idx.kit(f)
            hot_walls.append((time.perf_counter() - t0) * 1000)
        out["kit_cold_first"] = {"n": len(cold_walls),
                                 "p50": round(_pct(cold_walls, 0.5), 2),
                                 "max": round(max(cold_walls), 2)}
        out["kit_cached"] = {"n": len(hot_walls),
                             "p50": round(_pct(hot_walls, 0.5), 3),
                             "p95": round(_pct(hot_walls, 0.95), 3)}
        # text：TTF 读+sha（IO 线——文件字节直读无解码语义）+ fontdefs 体量
        t = idx.text()
        ttf_walls = []
        for r in idx.conn.execute(
                "SELECT item_key FROM items WHERE domain='text' AND item='font_ttf'"):
            br = next(iter(idx._item_blob_roles(r["item_key"]).values()))
            p = idx.layout.blob_path(
                br["payload_sha256"],
                ext=KC.BLOB_CODEC_EXT.get(br["codec"] or "ttf", ".ttf"))
            t0 = time.perf_counter()
            data = p.read_bytes()
            assert S.sha256_hex(data) == br["payload_sha256"]
            ttf_walls.append((time.perf_counter() - t0) * 1000)
        out["text"] = {"fonts": sorted(t["fonts"]),
                       "fontdefs_bytes": len(S.cjson(t["fontdefs"])),
                       "ttf_bytes_total": sum(len(v) for v in t["fonts"].values()),
                       "ttf_read_sha_ms": {"n": len(ttf_walls),
                                           "p50": round(_pct(ttf_walls, 0.5), 2),
                                           "max": round(max(ttf_walls), 2)},
                       "note": "TTF=文件字节直读（无解码语义）；文件 sha=内容身份"}
    return out


def bench_warm(cache_root: Path | str, cards: list[str], *, repeat: int = 5,
               locale: str | None = None) -> dict:
    """warm 批量：逐卡 plan+assemble 计时（含 blob sha 校验与 PNG 解码——供给全路径）。"""
    walls, query_walls, decode_walls = [], [], []
    hits = 0
    with SupplyIndex(cache_root, locale=locale) as idx:
        for _ in range(repeat):
            for cid in cards:
                t0 = time.perf_counter()
                plan = idx.plan(cid)
                t1 = time.perf_counter()
                if plan is None or plan.missing:
                    continue  # 缺项不进正态样本（check 面另报命中率）
                imgs = idx.assemble(plan)
                t2 = time.perf_counter()
                if "portrait" in imgs:
                    hits += 1
                walls.append((t2 - t0) * 1000)
                query_walls.append((t1 - t0) * 1000)
                decode_walls.append((t2 - t1) * 1000)
    n = len(walls)
    return {
        "cards": len(cards), "repeat": repeat, "n_samples": n,
        "wall_ms": {"p50": round(_pct(walls, 0.50), 2),
                    "p95": round(_pct(walls, 0.95), 2),
                    "mean": round(statistics.fmean(walls), 2) if walls else 0},
        "plan_query_ms": {"p50": round(_pct(query_walls, 0.50), 3),
                          "p95": round(_pct(query_walls, 0.95), 3),
                          "mean": round(statistics.fmean(query_walls), 3) if query_walls else 0},
        "blob_decode_ms": {"p50": round(_pct(decode_walls, 0.50), 2),
                           "p95": round(_pct(decode_walls, 0.95), 2)},
        "throughput_cards_per_s": round(n / (sum(walls) / 1000), 1) if walls else 0,
        "hits": hits,
    }


def bench_cold_targeted(cache_root: Path | str, *, n: int = 20, jobs: int = 1,
                        game: Path, locale: str) -> dict:
    """cold 定向单卡（catalog+locator 已建、产物未建）：对未建卡逐张定向 build 计时。

    选样（P2 车2 收紧口径）：portrait locator-ok 而无 item 的卡（真「产物未建」）
    ——locator 全无的卡=数据缺席（非可建面，排除防 no-op 污染计时）。
    逐张调 cold.build --cards 单卡形态（锁+DB 开销计入——产品真实路径）。
    game/locale 必填（cold 面=显式身份）。"""
    from eidolon.core.supply_index import cold

    if n <= 0:
        return {"skipped": "n=0"}
    layout = SupplyLayout(cache_root)
    with SupplyIndex(cache_root) as idx:
        built_items = {json.loads(r[0])["card_id"] for r in idx.conn.execute(
            "SELECT params_json FROM items WHERE params_json LIKE '%portrait%'")}
        loc_cards = {r["subject"] for r in idx.conn.execute(
            "SELECT DISTINCT subject FROM locators WHERE kind='portrait' "
            "AND status='ok'")}
        all_cards = [r["card_id"] for r in idx.conn.execute(
            "SELECT card_id FROM cards ORDER BY card_id")]
    unbuilt = [c for c in all_cards
               if c not in built_items and c in loc_cards]
    if not unbuilt:
        return {"skipped": "全代已建（locator-ok 卡全部有产物）；"
                           "冷定向数字=部分代阶段实测"}
    if len(unbuilt) < n:
        n = len(unbuilt)
    rng = random.Random(7)
    sample = rng.sample(unbuilt, n)
    walls = []
    for cid in sample:
        t0 = time.perf_counter()
        cold.build(str(layout.root), game=game, locale=locale, jobs=jobs, cards=[cid])
        walls.append((time.perf_counter() - t0) * 1000)
    return {"n": len(walls), "jobs": jobs,
            "wall_ms": {"p50": round(_pct(walls, 0.50), 1),
                        "p95": round(_pct(walls, 0.95), 1),
                        "mean": round(statistics.fmean(walls), 1)}}


def measure(cache_root: Path | str) -> dict:
    """存储代价实测（一次性；设计 §8 无运行时告警）。**不做外推**（Phase 5 返工
    R1，D-决策 4：旧形 partial 代按 avg×期望 item 数外推的 extrapolated 块已删
    ——外推不是实测，混合在存储报告里误导收口判读；partial 代只报实测 total 与
    分域实测，全量存储以 37k full 代实跑为准）。

    P2 车2 起 blob 面=png/json/npz/ttf 四 codec（kit 六面+gems/wm png+text 域
    json/ttf）——分 ext 计数，PNG 均值口径保持 P1 可比。"""
    layout = SupplyLayout(cache_root)
    blobs_bytes = 0
    blob_files = 0
    sizes = []
    per_ext: dict[str, dict] = {}
    if layout.blobs_dir.is_dir():
        for p in layout.blobs_dir.rglob("*"):
            if not p.is_file() or p.suffix not in (".png", ".json", ".npz", ".ttf"):
                continue
            sz = p.stat().st_size
            blobs_bytes += sz
            blob_files += 1
            e = per_ext.setdefault(p.suffix, {"files": 0, "bytes": 0})
            e["files"] += 1
            e["bytes"] += sz
            if p.suffix == ".png" and len(sizes) < 200000:
                sizes.append(sz)
    cur = layout.read_current() or {}
    db_bytes = 0
    counts = {}
    if cur:
        db = layout.gen_db(cur["game_id"])
        if db.is_file():
            db_bytes = db.stat().st_size
            from eidolon.core.supply_index import schema as S

            conn = S.connect(db, readonly=True)
            for k, v in conn.execute(
                    "SELECT key,value FROM meta WHERE key LIKE 'counts_%' "
                    "OR key LIKE 'full_build%' OR key LIKE 'identity_%' "
                    "OR key LIKE 'selfheal_%'"):
                counts[k] = v
            conn.close()
    total = blobs_bytes + db_bytes
    out = {
        "cache_root": str(layout.root),
        "generation": cur.get("generation"),
        "blob_files": blob_files,
        "blob_bytes": blobs_bytes,
        "blob_gb": round(blobs_bytes / 1e9, 3),
        "blob_per_ext": {k: {"files": v["files"],
                             "mb": round(v["bytes"] / 1e6, 1)}
                         for k, v in sorted(per_ext.items())},
        "db_bytes": db_bytes,
        "db_mb": round(db_bytes / 1e6, 1),
        "total_gb": round(total / 1e9, 3),
        "avg_blob_kb": round(statistics.fmean(sizes) / 1024, 1) if sizes else 0,
        "blob_size_p50_kb": round(_pct(sizes, 0.5) / 1024, 1) if sizes else 0,
        "blob_size_p95_kb": round(_pct(sizes, 0.95) / 1024, 1) if sizes else 0,
        "meta": counts,
    }
    return out


def run(cache_root: Path | str, cards: list[str] | None = None, *, repeat: int = 5,
        cold_sample: int = 20, jobs: int = 4, game: Path, locale: str,
        full: bool = True) -> dict:
    """bench 主入口。cards=None=本代 cards 表抽样 53 张（种子 42——sample_cards，
    上游 corpus 语料门不搬）；输出轴口径（warm/cold p50/p95、命中率、存储 GB）不变。"""
    if cards is None:
        cards = sample_cards(cache_root)
        source = "db-sample"
    else:
        source = "explicit"
    out: dict = {"card_set": {"n": len(cards), "source": source}}
    out["warm"] = bench_warm(cache_root, cards, repeat=repeat, locale=locale)
    if full:
        # 全卡面（P2 车2 判据轴）：cards 表全集吞吐/p50/p95 + 单件解码贴线项
        out["warm_full_corpus"] = bench_warm_full(cache_root, locale=locale)
        out["decode_lines"] = bench_decode_lines(cache_root, locale=locale)
    # 命中率（含缺项口径，正态样本之外如实记）
    with SupplyIndex(cache_root) as idx:
        out["hit_rate"] = idx.check(cards)
    # cold 定向（部分代才有未建卡；全代跳过并注明）
    layout = SupplyLayout(cache_root)
    try:
        out["cold_targeted"] = bench_cold_targeted(cache_root, n=cold_sample,
                                                   jobs=1, game=game, locale=locale)
    except RuntimeError as exc:
        out["cold_targeted"] = {"skipped": str(exc)}
    out["storage"] = measure(cache_root)
    return out
