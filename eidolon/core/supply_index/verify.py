"""verify — 冷暖逐字节一致验证（正确性判据的执行面）。

判据：warm 供 portrait 与 cold 解码**逐字节一致**——
- payload 级：blob 文件 sha == cold 现算 PNG sha（warm 供的字节=cold 产的字节）；
- 像素级（53 全查加做）：warm PIL 解码像素 tobytes == cold UnityPy 解码 tobytes
  （PNG 无损往返的构造性推论，实测钉死）。

P2 车1 kit 面：**kit 冷暖逐字段一致**——六族 kit 全查（cold 重提取 vs warm 重组：
hierarchy 逐节点/arrays 逐数组（内容 sha）/纹理逐 sha（像素）/JSON 面逐面
（canonical sha），比对器=kit_codec.compare_kit）+ 卡→帧族覆盖解析（53 gate 全查
+ N≥500 抽样；CARDTYPE→GetHandActor 槽位分派转写，C# 锚
ActorNames.cs:ActorNames.GetHandActor :550-575）。

抽样：gate 卡集全查 + N 随机（含 portrait_golden/portpremium 变体抽样）。cold 现算
走 _decode_bundle_worker 同一 worker（与 build 产 blob 同源代码，防「验证器另写一份
解码」漂移）；kit 冷腿同源（kit_extract._extract_kit_now=build worker 本体）。
"""
from __future__ import annotations

import json
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.paths import SupplyLayout
from eidolon.core.supply_index.warm import SupplyIndex, account_for_cards


def _sample_gate_cards(conn, *, n: int = 53, seed: int = 42) -> list[str]:
    """gate 卡集缺省源：本代 cards 表抽样 N 张（种子固定可复跑）。

    上游 gate=corpus_meta.selected('full') 语料门（Phase 5 定案：corpus_meta
    不搬）——卡集来源改显式参数或本代 DB 抽样，报告轴口径不变（全查+像素级）。"""
    rows = [r["card_id"] for r in conn.execute("SELECT card_id FROM cards")]
    return random.Random(seed).sample(rows, min(n, len(rows)))


def _sample_items(conn, n_portrait: int, n_golden: int, seed: int,
                  *, all_items: bool = False) -> list[dict]:
    """items 表抽样：portrait n1 + golden n2（种子固定可复跑；P2 车1 起 domain 过滤
    ——kit item params 无 kind，不入 portrait 抽样面）。

    ``all_items=True``（CLI ``--all``，Phase 5 审计 P2 全量档）时不做随机抽样，
    两种 kind 的全集都入列（排序后返回，可复跑）。默认抽样行为不变。"""
    rng = random.Random(seed)
    out = []
    for kind, n in (("portrait", n_portrait), ("portrait_golden", n_golden)):
        rows = []
        for r in conn.execute(
                "SELECT i.item_key, i.params_json, i.manifest_json, i.content_inputs_json "
                "FROM items i WHERE i.domain='art' AND i.params_json LIKE ?",
                (f'%"{kind}"%',)):
            params = json.loads(r["params_json"])
            if params["kind"] != kind:
                continue
            rows.append({"item_key": r["item_key"], "params": params,
                         "manifest": json.loads(r["manifest_json"]),
                         "content": json.loads(r["content_inputs_json"])})
        if all_items:
            out.extend(rows)
        else:
            out.extend(rng.sample(rows, min(n, len(rows))))
    return out


def _cold_rederive(payload):
    """cold 现算单包：返回 {(card_id, kind): {pixel_sha, payload_sha}}。"""
    (win_s, bundle, tasks) = payload
    win = Path(win_s)
    from eidolon.core.supply_index._unity import container_pairs, iter_serialized, load_bundle
    from eidolon.core.supply_index.cold import _encode_png

    try:
        env = load_bundle(win / bundle)
    except Exception as exc:  # noqa: BLE001
        return (bundle, {tuple(t["key"]): {"error": f"bundle-open: {exc}"}
                         for t in tasks})
    out = {}
    sfs = [(sf, {k.lower(): pid for k, pid in container_pairs(sf)})
           for sf in iter_serialized(env)]
    for t in tasks:
        guid = t["guid"].lower()
        hit = next(((sf, idx) for sf, idx in sfs if guid in idx), None)
        if hit is None:
            out[tuple(t["key"])] = {"error": "guid-not-in-container"}
            continue
        sf, idx = hit
        try:
            obj = sf.objects[idx[guid]]
            img = obj.read().image
            png = _encode_png(img)
            out[tuple(t["key"])] = {"pixel_sha": S.sha256_hex(img.tobytes()),
                                    "payload_sha": S.sha256_hex(png)}
        except Exception as exc:  # noqa: BLE001
            out[tuple(t["key"])] = {"error": f"decode: {type(exc).__name__}: {exc}"}
    return (bundle, out)


def verify(cache_root: Path | str, *, n_sample: int = 500, n_golden: int = 100,
           gate_cards: list[str] | None = None, seed: int = 42, jobs: int = 4,
           game: Path, locale: str,
           kits: bool = True, all_items: bool = False) -> dict:
    """逐字节一致验证（P2 车1 起=portrait + kit 两面）。mismatch≠0 → exit 1（CLI 层）。

    两档抽样（Phase 5 审计 P2）：
    - 默认（``all_items=False``）：portrait 抽 ``n_sample`` + golden 抽 ``n_golden``
      + watermark 抽 200（``verify_watermarks`` 缺省）——秒级收口；
    - ``all_items=True``（CLI ``--all``）：art 两种 kind **全集** + watermark 全集
      入 cold 现算对拍——37k 级全量档，耗时按语料规模线性增长（文档写明）。
    gate 卡集轴（像素级全查）两档一致。

    game/locale 必填（cold 现算=显式身份；resolve_context + context.install，与
    build 同规）。gate_cards=None=本代 cards 表抽样 53 张（种子 seed——上游
    corpus_meta 语料门不搬）；[]=跳过 gate 轴。"""
    from eidolon.core.infra import context
    from eidolon.core.infra.game_install import resolve_context
    from eidolon.contracts import GameRequest

    ctx = resolve_context(GameRequest(Path(game), "--game"),
                          cache_root=Path(cache_root), locale=locale or "zhcn")
    context.install(ctx)            # cold 面入口（同身份幂等；异身份 raise）
    win = ctx.data_win
    layout = SupplyLayout(cache_root)

    # warm 面：gate 全查 + 抽样（--all=art 全集）
    with SupplyIndex(cache_root) as idx:
        conn = idx.conn
        fb = conn.execute(
            "SELECT value FROM meta WHERE key='full_build'").fetchone()
        full_build = bool(fb and fb["value"] == "1")
        if gate_cards is None:
            gate_cards = _sample_gate_cards(conn, seed=seed)
        samples = _sample_items(conn, n_sample, n_golden, seed,
                                all_items=all_items)
        targets = []
        for s in samples:
            m = s["manifest"]
            targets.append({"key": (m["card_id"], m["kind"]), "guid": m["guid"],
                            "bundle": m["bundle"], "pixel_sha": m["pixel_sha256"],
                            "payload_sha": m["payload_sha256"], "warm": True})
        # gate 全查的 item 也入 cold 现算集（去重按 (card,kind)）
        for cid in gate_cards:
            plan = idx.plan(cid)
            if plan is None or plan.missing:
                continue
            for it in plan.items:
                if it.role == "portrait":
                    m = it.manifest
                    if not any(t["key"] == (m["card_id"], m["kind"]) for t in targets):
                        targets.append({"key": (m["card_id"], m["kind"]),
                                        "guid": m["guid"], "bundle": m["bundle"],
                                        "pixel_sha": m["pixel_sha256"],
                                        "payload_sha": m["payload_sha256"],
                                        "warm": False})

    # warm 像素级（gate 全查）：PIL 解码 tobytes vs 账面 pixel sha
    # （verify 管「在库的等不等」，缺项归 audit/warm 的 fail-loud 面——未建卡
    #   按 R2 缺席归因分道：not_built_gap（有期望未建，真红）vs not_built_absent
    #   （零期望/locator≠ok，数据缺席合法单列）——判据=warm.account_for_cards
    #   同一单源；portrait 无 item 而 locator 非 ok 的 ok 卡（golden-only 卡）
    #   同归 absent）
    pixel_checks = []
    nb_gap: list[str] = []
    nb_absent: list[str] = []
    with SupplyIndex(cache_root) as idx:
        if gate_cards:
            acct = account_for_cards(idx.conn, gate_cards)
            verdict: dict[str, str] = {}
            for cat in ("ok", "missing_gap", "absent_expectationless",
                        "absent_locator_missing"):
                for cid in acct[cat]:
                    verdict[cid] = cat
            for reason, cards_ in acct["anomaly"].items():
                for cid in cards_:
                    verdict[cid] = f"anomaly:{reason}"
            ph = ",".join("?" * len(gate_cards))
            loc_portrait = {r["subject"]: r["status"] for r in idx.conn.execute(
                "SELECT subject, status FROM locators WHERE kind='portrait' "
                f"AND subject IN ({ph})", gate_cards)}
            for cid in gate_cards:
                plan = idx.plan(cid)
                if plan is not None and not plan.missing and any(
                        i.role == "portrait" for i in plan.items):
                    img = idx.assemble_portrait(cid)
                    m = next(i.manifest for i in plan.items
                             if i.role == "portrait")
                    ok = S.sha256_hex(img.tobytes()) == m["pixel_sha256"]
                    pixel_checks.append(
                        {"card_id": cid, "ok": ok,
                         "why": None if ok else "pixel-sha-mismatch"})
                    continue
                v = verdict.get(cid, "missing_gap")   # 未入账=红侧保守缺省
                if v in ("absent_expectationless",
                         "absent_locator_missing") or \
                        (v == "ok" and loc_portrait.get(cid) != "ok"):
                    nb_absent.append(cid)
                    pixel_checks.append({"card_id": cid, "ok": None,
                                         "why": f"absent:{v}"})
                else:
                    nb_gap.append(cid)
                    pixel_checks.append({"card_id": cid, "ok": None,
                                         "why": "not-built-gap"})

    # cold 现算（按 bundle 分组分进程，与 build 同 worker 语义）
    by_bundle: dict[str, list[dict]] = {}
    for t in targets:
        by_bundle.setdefault(t["bundle"], []).append(t)
    payload = [(str(win), b, ts) for b, ts in sorted(by_bundle.items())]
    got = {}
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for bundle, res in ex.map(_cold_rederive, payload):
            got.update(res)

    ok = bad = 0
    mismatches = []
    for t in targets:
        r = got.get(t["key"], {"error": "no-result"})
        if r.get("error"):
            bad += 1
            mismatches.append({"card_id": t["key"][0], "kind": t["key"][1],
                               "why": r["error"]})
            continue
        same_payload = r["payload_sha"] == t["payload_sha"]
        same_pixel = r["pixel_sha"] == t["pixel_sha"]
        if same_payload and same_pixel:
            ok += 1
        else:
            bad += 1
            mismatches.append({"card_id": t["key"][0], "kind": t["key"][1],
                               "why": "payload/pixel sha mismatch"})
    out = {"sample": len(targets), "ok": ok, "bad": bad,
           "mismatches": mismatches[:20],
           "full_build": full_build,
           # partial 代显式标注（Phase 5 返工 R1，P0-2）：full_build=0 的代
           # gate 像素全查会大面积 not_built（scope 外未建是 partial 代定义），
           # 输出必须显式标 partial，门语义归 CLI（full 代 not_built_gap>0 →
           # exit 1；partial 代不按 not_built 门禁，其余 bad 条件照常）。
           # R2 缺席归因：not_built 拆分 not_built_gap（有期望未建，真红）/
           # not_built_absent（零期望/locator≠ok，数据缺席合法单列）；
           # not_built 保留为两者总账（兼容旧消费面）。
           "partial": not full_build,
           "gate_pixel_checks": {"n": len(pixel_checks),
                                   "ok": sum(1 for c in pixel_checks if c["ok"] is True),
                                   "not_built": len(nb_gap) + len(nb_absent),
                                   "not_built_gap": len(nb_gap),
                                   "not_built_absent": len(nb_absent),
                                   "not_built_gap_cards": nb_gap[:10],
                                   "not_built_absent_cards": nb_absent[:10],
                                   "bad": [c for c in pixel_checks if c["ok"] is False][:10]}}
    if kits:
        out["kit"] = verify_kits(cache_root, n_sample=n_sample, seed=seed,
                                 win=win, gate_cards=gate_cards,
                                 game=game, locale=locale)
    out["gems"] = verify_gems(cache_root, win=win)
    out["text"] = verify_text(cache_root, win=win, game=game, locale=locale)
    out["watermark"] = verify_watermarks(cache_root, win=win, n_sample=n_sample,
                                         seed=seed, all_items=all_items)
    return out


# ---------------------------------------------------------------------------
# P2 车1：kit 冷暖逐字段一致 + 卡→帧族覆盖解析
# ---------------------------------------------------------------------------

def _kit_cold_warm(cache_root: Path | str, win: Path) -> dict:
    """六族 kit 全查：warm 重组 vs cold 重提取（build worker 本体内联——结构不出
    进程免 pickle 大件）。比对=kit_codec.compare_kit（逐节点/逐数组/逐 sha）。"""
    from eidolon.core.supply_index import cold as cold_mod
    from eidolon.core.supply_index import kit_codec as KC
    from eidolon.core.supply_index.kit_extract import (
        FRAME_SPECS_KIT,
        _extract_kit_now,
    )

    with SupplyIndex(cache_root) as idx:
        frames = sorted(idx.kit_frames())
        warm_kits = {}
        metas = {}
        missing = []
        for f in frames:
            try:
                warm_kits[f] = idx.kit(f)
                metas[f] = warm_kits[f]["meta"]
            except Exception as exc:  # noqa: BLE001
                missing.append({"frame": f, "why": str(exc)[:200]})
    deps = cold_mod.read_bundle_deps(win)

    comparisons = []
    counts = {"nodes": 0, "arrays": 0, "textures": 0, "json_faces": 0}
    for f in frames:
        if f not in warm_kits:
            continue
        m = metas[f]
        cold = _extract_kit_now(win, frame=f, spec=FRAME_SPECS_KIT[f],
                                actor_ref=m["prefab_ref"], guid=m["guid"],
                                bundle=m["bundle"], card_id=m.get("card_id"),
                                dbf_id=m.get("dbf_id"), bundle_deps=deps,
                                strings_txt=cold_mod.ctx_strings_path(
                                    win, m.get("locale") or "zhcn"))
        if not cold.get("ok"):
            comparisons.append({"frame": f, "ok": False, "why": cold.get("error")})
            continue
        comp = KC.compare_kit(cold["struct"], warm_kits[f])
        for k in counts:
            counts[k] += comp["counts"].get(k, 0)
        comp["frame"] = f
        comparisons.append(comp)
    bad = [c for c in comparisons if not c["ok"]]
    return {"frames_in_index": frames, "compared": len(comparisons),
            "ok": not bad and not missing, "mismatches": bad[:10],
            "warm_missing": missing,
            "element_counts": counts}


def _kit_frame_coverage(cache_root: Path | str, win: Path, gate_cards: list[str],
                        n_sample: int, seed: int) -> dict:
    """卡→帧族覆盖解析：53 gate 全查 + N 抽样。

    解析链（GetHandActor 表驱动体转写，ActorNames.cs:ActorNames.GetHandActor
    :550-575；值域=TAG_CARDTYPE 活表）：dbf CARD_TAG CARDTYPE → 槽位 → 帧族。
    hero 卡另查 PLAY 腿（GetPlayActorByTags :691 → hero_play）。判定：
    - family ∈ 车1 六族 → kit item 必须在库（缺=bad）；
    - family ∉ 六族（ability/anomaly/trinket/CARD_HIDDEN）→ 记 out_of_scope
      （车2/later 域，不算失败）。"""
    from eidolon.core.supply_index import cold as cold_mod
    from eidolon.core.supply_index.kit_extract import (
        FRAME_SPECS_KIT,
        frame_family_maps,
        read_card_types_by_dbf,
    )

    dbf_ids, _dup = cold_mod.read_dbf_card_ids(win)
    card_types = read_card_types_by_dbf(win)
    hand_map, play_map = frame_family_maps()
    with SupplyIndex(cache_root) as idx:
        have = set(idx.kit_frames())

    pool = sorted(gate_cards)
    if n_sample > 0:
        with SupplyIndex(cache_root) as idx:
            all_cards = [r["card_id"] for r in idx.conn.execute(
                "SELECT card_id FROM cards")]
        # 抽样池=本代 cards 表全集−gate（gate 全查独立计数，抽样不重叠）
        rest = [c for c in all_cards if c not in set(pool)]
        rng = random.Random(seed)
        pool = pool + rng.sample(rest, min(n_sample, len(rest)))

    fam_counts: dict[str, int] = {}
    out_of_scope: dict[str, int] = {}
    bad = []
    play_leg = {"checked": 0, "ok": 0, "bad": []}
    for cid in pool:
        dbf = dbf_ids.get(cid)
        ct = card_types.get(dbf) if dbf is not None else None
        if ct is None:
            bad.append({"card_id": cid, "why": "cardtype-unknown"})
            continue
        fam = hand_map.get(ct)
        if fam is None:
            out_of_scope["CARD_HIDDEN"] = out_of_scope.get("CARD_HIDDEN", 0) + 1
            continue
        if fam not in FRAME_SPECS_KIT:
            # 车1 帧域外（ability/anomaly/trinket——ability 帧=车2 后续 codec 域）
            out_of_scope[fam] = out_of_scope.get(fam, 0) + 1
            continue
        fam_counts[fam] = fam_counts.get(fam, 0) + 1
        if fam not in have:
            bad.append({"card_id": cid, "why": f"kit-missing:{fam}"})
        if ct in play_map and play_map[ct] is not None:
            pfam = play_map[ct]
            play_leg["checked"] += 1
            if pfam in FRAME_SPECS_KIT and pfam in have:
                play_leg["ok"] += 1
            elif pfam in FRAME_SPECS_KIT:
                play_leg["bad"].append({"card_id": cid, "why": f"kit-missing:{pfam}"})
                bad.append(play_leg["bad"][-1])
    uncovered = {f: n for f, n in fam_counts.items()
                 if f in FRAME_SPECS_KIT and f not in have}
    return {"cards_resolved": len(pool), "gate": len(gate_cards),
            "sampled": max(0, len(pool) - len(gate_cards)),
            "family_card_counts": dict(sorted(fam_counts.items())),
            "out_of_scope": dict(sorted(out_of_scope.items())),
            "play_leg": {**play_leg, "bad": play_leg["bad"][:5]},
            "kit_missing_for_covered": uncovered,
            "ok": not bad and not uncovered, "bad": bad[:10]}


def verify_kits(cache_root: Path | str, *, n_sample: int = 500, seed: int = 42,
                win: Path | None = None, gate_cards: list[str] | None = None,
                game: Path, locale: str) -> dict:
    """kit 冷暖一致验证（verify() 组合面调；win/gate_cards 已解析时免重装 ctx）。

    gate_cards=None=本代 cards 表抽样（同 verify 主面口径）。"""
    from eidolon.core.infra import context
    from eidolon.core.infra.game_install import resolve_context
    from eidolon.contracts import GameRequest

    if win is None:
        ctx = resolve_context(GameRequest(Path(game), "--game"),
                              cache_root=Path(cache_root), locale=locale or "zhcn")
        context.install(ctx)
        win = ctx.data_win
    if gate_cards is None:
        with SupplyIndex(cache_root) as idx:
            gate_cards = _sample_gate_cards(idx.conn, seed=seed)
    cw = _kit_cold_warm(cache_root, win)
    cov = _kit_frame_coverage(cache_root, win, gate_cards, n_sample, seed)
    return {"cold_warm": cw, "coverage": cov,
            "ok": bool(cw["ok"] and cov["ok"])}


# ---------------------------------------------------------------------------
# P2 车2：gems / text / watermark 冷暖一致
# ---------------------------------------------------------------------------

def verify_gems(cache_root: Path | str, *, win: Path | None = None) -> dict:
    """gems 冷暖一致（全查 3 件）：cold=ally kit 重提取的 gems 账（build worker
    本体）；warm=gems items blob 解码像素 sha。比对器=gems_codec.compare_gems。"""
    import io as _io

    from PIL import Image

    from eidolon.core.supply_index import cold as cold_mod
    from eidolon.core.supply_index import gems_codec as GC
    from eidolon.core.supply_index import kit_codec as _KC
    from eidolon.core.supply_index.kit_extract import FRAME_SPECS_KIT, _extract_kit_now

    if win is None:
        from eidolon.core.infra import context

        win = context.current().data_win      # 库面禁默认解析——ctx 未装即响亮

    with SupplyIndex(cache_root) as idx:
        warm_shas: dict[str, str] = {}
        missing: list[str] = []
        for r in idx.conn.execute(
                "SELECT item, item_key FROM items WHERE domain=?",
                (S.DOMAIN_GEMS,)):
            blobs = idx._item_blob_roles(r["item_key"])
            br = blobs.get(f"gem:{r['item']}")
            if br is None:
                missing.append(f"{r['item']}: blob 行缺失")
                continue
            p = idx.layout.blob_path(
                br["payload_sha256"],
                ext=_KC.BLOB_CODEC_EXT.get(br["codec"] or "png", ".png"))
            if not p.is_file():
                missing.append(f"{r['item']}: blob 文件缺失")
                continue
            img = Image.open(_io.BytesIO(p.read_bytes()))
            img.load()
            warm_shas[r["item"]] = S.sha256_hex(img.tobytes())
        ally_row = idx.conn.execute(
            "SELECT manifest_json FROM items WHERE domain=? AND item=? "
            "AND params_json=?", (S.DOMAIN_FRAMES, "kit",
                                  S.cjson({"frame": "ally"}))).fetchone()
        ally_meta = json.loads(ally_row["manifest_json"]) if ally_row else None

    if ally_meta is None:
        return {"ok": False, "why": "ally kit item 缺失（gems 提取源）",
                "missing": missing}
    deps = cold_mod.read_bundle_deps(win)
    cold = _extract_kit_now(
        win, frame="ally", spec=FRAME_SPECS_KIT["ally"],
        actor_ref=ally_meta["prefab_ref"], guid=ally_meta["guid"],
        bundle=ally_meta["bundle"], card_id=ally_meta.get("card_id"),
        dbf_id=ally_meta.get("dbf_id"), bundle_deps=deps)
    if not cold.get("ok"):
        return {"ok": False, "why": f"cold 重提取失败: {cold.get('error')}",
                "missing": missing}
    comp = GC.compare_gems(cold.get("gems") or {}, warm_shas)
    comp["warm_missing"] = missing
    comp["ok"] = bool(comp["ok"] and not missing)
    return comp


def verify_text(cache_root: Path | str, *, win: Path | None = None,
                game: Path, locale: str) -> dict:
    """text 冷暖一致（全查）：cold=extract_fonts 重提取；warm=idx.text()。
    fontdefs=canonical sha 面、TTF=文件 sha 面（text_codec.compare_text）。"""
    from eidolon.core.infra import context
    from eidolon.core.infra.game_install import resolve_context
    from eidolon.contracts import GameRequest
    from eidolon.core.supply_index import cold as cold_mod
    from eidolon.core.supply_index import text_codec as TC
    from eidolon.core.supply_index.text_extract import extract_fonts

    if win is None:
        ctx = resolve_context(GameRequest(Path(game), "--game"),
                              cache_root=Path(cache_root), locale=locale or "zhcn")
        context.install(ctx)
        win = ctx.data_win
    ctx = context.current()
    loc = ctx.locale

    tables = cold_mod.read_manifest_tables(win, loc)
    zhcat = {base: (guid, bundle) for base, _layer, l, guid, bundle
             in tables["variant_rows"] if l == "zhcn"}
    cold = extract_fonts(win, catalog=tables["catalog"], zhcat=zhcat,
                         bundle_deps=tables["bundle_deps"])
    with SupplyIndex(cache_root) as idx:
        try:
            warm = idx.text()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "why": f"warm text 缺项: {exc}"}
    comp = TC.compare_text(cold["fontdefs"], warm["fontdefs"],
                           cold["ttfs"],
                           {k: S.sha256_hex(v) for k, v in warm["fonts"].items()})
    comp["cold_errors"] = cold["errors"]
    comp["ok"] = bool(comp["ok"] and not cold["errors"])
    return comp


def verify_watermarks(cache_root: Path | str, *, win: Path | None = None,
                      n_sample: int = 200, seed: int = 42,
                      all_items: bool = False) -> dict:
    """watermark 冷暖一致：gate 全查（域全查抽样=items 全集抽样）+ N 抽样（cold
    现算走 _cold_rederive 同 worker——与 build 产 blob 同源代码）。
    ``all_items=True``（verify --all）时抽全集，不做随机截取。"""
    import random

    from eidolon.core.infra import context

    if win is None:
        win = context.current().data_win      # 库面禁默认解析——ctx 未装即响亮

    rng = random.Random(seed)
    with SupplyIndex(cache_root) as idx:
        rows = idx.conn.execute(
            "SELECT item_key, manifest_json FROM items WHERE domain=?",
            (S.DOMAIN_WATERMARK,)).fetchall()
        n_total = len(rows)
        pick = rows if all_items else rng.sample(rows, min(n_sample, n_total))
        targets = []
        for r in pick:
            m = json.loads(r["manifest_json"])
            targets.append({"key": ("wm", m["card_id"]), "guid": m["guid"],
                            "bundle": m["bundle"], "pixel_sha": m["pixel_sha256"],
                            "payload_sha": m["payload_sha256"]})
    by_bundle: dict[str, list[dict]] = {}
    for t in targets:
        by_bundle.setdefault(t["bundle"], []).append(t)
    got = {}
    if by_bundle:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=2) as ex:
            for _b, res in ex.map(_cold_rederive,
                                  [(str(win), b, ts)
                                   for b, ts in sorted(by_bundle.items())]):
                got.update(res)
    ok = bad = 0
    mismatches = []
    for t in targets:
        r = got.get(t["key"], {"error": "no-result"})
        if r.get("error"):
            bad += 1
            mismatches.append({"card_id": t["key"][1], "why": r["error"]})
            continue
        if r["payload_sha"] == t["payload_sha"] and r["pixel_sha"] == t["pixel_sha"]:
            ok += 1
        else:
            bad += 1
            mismatches.append({"card_id": t["key"][1], "why": "sha mismatch"})
    return {"items_total": n_total, "sampled": len(targets), "ok_count": ok,
            "bad": bad, "mismatches": mismatches[:10],
            "ok": bad == 0 and n_total > 0}
