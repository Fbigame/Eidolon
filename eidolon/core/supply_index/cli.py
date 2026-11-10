"""cli — 供给索引 CLI（python -m eidolon.core.supply_index <cmd>）。

入口边缘职责：cache_root/game/locale 全显式（Phase 5 定案：产品无 env/默认解析
链——``--cache-root``/``--game``/``--locale`` 缺省即参数错误，不读 env 不算默认；
core 内部工具禁 import shell 的默认根派生）。库面零 env 旋钮。

命令：build / warm（--mode require-cache|auto|offline）/ diff / revalidate /
verify / bench / bench-process / audit（--auto） / measure / integrity（--repair） /
maintain（--prune --keep N）。

--game/--locale 必填面：build/revalidate/verify/bench 恒必填（代码路径恒触 ctx）；
warm（--mode auto）/diff（--synthetic）/audit（--auto）按消费路径校验（纯 warm/
diff 面不触游戏身份，不必强填）。stdout 输出只住本层（库面 logger——core 无
print 的守卫口径）。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def _emit(doc: dict) -> None:
    sys.stdout.write(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n")


def _stderr(msg: str) -> None:
    sys.stderr.write(msg.rstrip("\n") + "\n")


def _need_identity(args, why: str) -> tuple[Path, str]:
    """消费 ctx 的路径校验 --game/--locale（缺省=参数错误退出 2——产品无 env 链）。"""
    if not getattr(args, "game", None) or not getattr(args, "locale", None):
        _stderr(f"参数错误：{why}需要 --game 与 --locale 显式给"
                "（产品无 env/默认解析链；core 内部工具不 import shell 默认根派生）")
        raise SystemExit(2)
    return Path(args.game), args.locale


def cmd_build(args) -> int:
    from eidolon.core.supply_index.cold import build

    try:
        out = build(args.cache_root, game=Path(args.game), locale=args.locale,
                    jobs=args.jobs, cards=args.cards, sample=args.sample,
                    skip_bundle_hash=args.skip_bundle_hash)
    except RuntimeError as exc:
        # build 响亮失败（身份门/完整性发布门/integrity 门——消息已带判据与
        # 恢复路径）走干净 stderr + exit 1，不裸 traceback
        _stderr(f"BUILD FAIL: {exc}")
        return 1
    _emit(out)
    return 0


def cmd_warm(args) -> int:
    from eidolon.core.supply_index.integrity import RederiveMismatchError
    from eidolon.core.supply_index.selfheal import SupplyMediaEventError
    from eidolon.core.supply_index.warm import (
        SupplyBlobCorruptError,
        SupplyIndex,
        SupplyIndexCorruptError,
    )

    mode = args.mode
    if mode == "auto":
        game, locale = _need_identity(args, "warm --mode auto（缺项自动冷补=cold 面）")
    else:
        game, locale = None, None
    idx = None
    l1_acct: dict | None = None
    l2_acct: dict | None = None
    try:
        if mode == "auto":
            # L1：open 自检（quick_check 内建）坏→自动重建（非 auto 响亮在 except 面）
            from eidolon.core.supply_index import selfheal

            idx, l1_acct = selfheal.ensure_index(
                args.cache_root, game=game, locale=locale, auto=True)
            if l1_acct["l1_corrupt_detected"]:
                _stderr(f"[warm:auto] L1 索引损坏（{l1_acct['l1_health']}）→ "
                        f"{'已自动重建（全量）' if l1_acct['l1_rebuilt'] else '重建失败'}")
        else:
            idx = SupplyIndex(args.cache_root, locale=args.locale)
            if idx.health_error is not None:
                raise SupplyIndexCorruptError(
                    f"supply 索引损坏需重建（generation={idx.generation}，db="
                    f"{idx.db_path}，{idx.health_error}）——{mode} 不自愈："
                    "人工重建（cold build 全量）或 auto 模式自动重建")
        if args.cards:
            cards = args.cards
        else:
            from eidolon.core.supply_index.bench import sample_cards

            cards = sample_cards(args.cache_root)
        rep = idx.check(cards)
        if rep["miss"] and mode == "auto":
            # auto：缺项自动冷补（全包唯一合法 UnityPy 路径=定向 cold decode）。
            # 只补 portrait 面（locator-ok 而无 item）；域级项缺失/不可补=响应亮。
            from eidolon.core.supply_index import cold

            rep = idx.fillable_missing(cards)
            if rep["fillable"]:
                _stderr(f"[warm:auto] 冷补 {len(rep['fillable'])} 卡（定向 decode）")
                cold.build(args.cache_root, game=game, locale=locale,
                           cards=rep["fillable"])
                # gen 可能已被定向 build 更新：句柄重绑（close→re-init，连接/缓存
                # 全新）
                idx.close()
                idx.__init__(args.cache_root, locale=args.locale)
                rep = idx.check(cards)
        if rep["miss"]:
            sys.stdout.write(json.dumps(rep, ensure_ascii=False, indent=1) + "\n")
            tag = {"require-cache": "require-cache", "offline": "offline",
                   "auto": "auto 冷补后仍缺"}[mode]
            _stderr(f"WARM MISS({mode}): {rep['miss']} 项（fail loud；"
                    f"{tag}——先跑 cold build）")
            return 1
        if args.save_png:
            from PIL import Image

            out_dir = Path(args.save_png)
            out_dir.mkdir(parents=True, exist_ok=True)
            for cid in cards:
                plan = idx.plan(cid)
                if plan is None:
                    continue
                for it in plan.items:
                    if it.codec != "png" or it.blob_path is None:
                        continue
                    img = Image.open(it.blob_path)
                    img.load()
                    img.save(out_dir / f"{cid}.{it.role}.png")
        # 全卡装配计数（供给出口演练；bundle 不落盘——内存对象契约）。
        # auto=L2 编排（blob sha 失配→单次重推导→单次重试）；require-cache/
        # offline=原样装配（失配 SupplyBlobCorruptError 响亮不自愈）。
        if mode == "auto":
            from eidolon.core.supply_index import selfheal

            sections, l2_acct = selfheal.assemble_with_heal(
                idx, cards, cache_root=args.cache_root, game=game, locale=locale)
        else:
            sections: dict[str, int] = {}
            for cid in cards:
                plan = idx.plan(cid)
                if plan is None:
                    continue
                for role in idx.assemble(plan):
                    sections[role] = sections.get(role, 0) + 1
        out = {"ok": True, "mode": mode, "check": rep,
               "assembled_sections": sections, "saved_png": args.save_png}
        if l1_acct is not None or l2_acct is not None:
            out["selfheal"] = {"l1": l1_acct, "l2": l2_acct}
        _emit(out)
    except FileNotFoundError as exc:
        # current.json 缺失 / current 指代库缺失（P1-11：不裸 traceback——
        # require-cache/offline 干净响亮「先冷建」；auto 的重建编排在
        # selfheal.ensure_index 内处理同形态）
        _stderr(f"WARM({mode}): {exc}——先跑 cold build 全量建代"
                f"{'（或用 --mode auto 自动重建）' if mode != 'auto' else ''}")
        return 1
    except SupplyIndexCorruptError as exc:
        _stderr(f"WARM({mode}): {exc}")
        return 1
    except sqlite3.DatabaseError as exc:
        # 读错误兜底（T2 残险账：bit rot 无 mtime 时 stamp 档 open 不检，坏页在
        # 查询触达时抛 DatabaseError）——响亮不静默；auto 模式此处不打断（重建
        # 编排在 ensure_index 的 full 档 quick_check 已先行）。
        _stderr(f"WARM({mode}): 读错误（索引可能损坏——先 integrity/quick_check "
                f"排查）：{type(exc).__name__}: {exc}")
        return 1
    except (SupplyMediaEventError, RederiveMismatchError) as exc:
        # L2 介质级事件停机 / L3 源坏-换代分级——已带判据的响亮面
        _stderr(f"WARM({mode}): {exc}")
        return 1
    except SupplyBlobCorruptError as exc:
        _stderr(f"WARM({mode}): {exc}")
        _stderr(f"提示：{mode} 不自愈——先 integrity --repair（auto 模式才有单次"
                "重推导自愈）")
        return 1
    finally:
        if idx is not None:
            idx.close()
    return 0


def cmd_diff(args) -> int:
    from eidolon.core.supply_index.diff import diff, five_state_exercise

    if args.synthetic:
        game, locale = _need_identity(
            args, "diff --synthetic（五态演练 exact 重读=cold 面）")
        try:
            out = five_state_exercise(args.cache_root, game=game, locale=locale)
        except RuntimeError as exc:
            # P1-12 返工 R1：演练自校验失败（注入账 vs 结果账不一致）响亮 exit 1
            # （不裸 traceback，也不静默绿）
            _stderr(f"DIFF(synthetic): 五态演练自校验失败：{exc}")
            return 1
    else:
        out = diff(args.cache_root, from_gen=args.from_gen, to_gen=args.to_gen)
    _emit(out)
    return 0


def cmd_revalidate(args) -> int:
    from eidolon.core.supply_index.diff import revalidate_exact

    if not args.exact:
        _stderr("revalidate 默认=cheap（即 diff）；--exact 才开包重读")
        return 2
    game, locale = _need_identity(args, "revalidate --exact（开包重读=cold 面）")
    out = revalidate_exact(args.cache_root, from_gen=args.from_gen,
                           to_gen=args.to_gen, limit=args.limit,
                           game=game, locale=locale, jobs=args.jobs)
    _emit(out)
    return 0


def cmd_verify(args) -> int:
    from eidolon.core.supply_index.verify import verify

    game, locale = _need_identity(args, "verify（cold 现算对拍=cold 面）")
    out = verify(args.cache_root, n_sample=args.sample, n_golden=args.golden_sample,
                 gate_cards=args.gate_cards, seed=args.seed, jobs=args.jobs,
                 game=game, locale=locale, kits=not args.no_kits,
                 all_items=args.all_items)
    # 退出面：bad 计数（int）非零 ∨ gate 像素失配清单（list）非空 ∨ kit/gems/
    # text/watermark 段红（P1 潜坑修复：旧形 `list != 0` 恒真——verify 全绿也恒
    # exit 1）。not_built 门禁（R1 P0-2 / R2 缺席归因口径）：full 代 gate 全查
    # 出现 **not_built_gap>0**（该卡有期望却未建——不可归因缺口）→ exit 1；
    # not_built_absent（零期望/locator≠ok——数据缺席）不判红只计数。partial 代
    # （out["partial"]=true 显式标注）不按 not_built 门禁——scope 外未建是
    # partial 代定义，其余 bad 条件照常。
    bad = out["bad"] != 0 or bool(out["gate_pixel_checks"]["bad"])
    if out.get("full_build") and \
            out["gate_pixel_checks"].get("not_built_gap", 0) > 0:
        bad = True
    for section in ("kit", "gems", "text", "watermark"):
        if out.get(section) is not None and not out[section].get("ok", True):
            bad = True
    _emit(out)
    if bad:
        if out.get("partial"):
            _stderr("VERIFY: partial 代（full_build=0）——not_built 不作门禁，"
                    "红项见报告 bad/mismatch/分段")
        return 1
    return 0


def cmd_bench(args) -> int:
    from eidolon.core.supply_index.bench import run

    game, locale = _need_identity(args, "bench（cold 定向段=cold 面）")
    out = run(args.cache_root, cards=args.cards or None, repeat=args.repeat,
              cold_sample=args.cold_sample, jobs=args.jobs, game=game, locale=locale)
    _emit(out)
    return 0


def cmd_bench_process(args) -> int:
    """bench-process：进程级 warm 墙钟（T1 warm-perf 车）。

    --child=内部子进程形态（单卡分段 JSON 一行；父进程编排消费）；
    非 child=父进程编排（样本集×轮次串行 spawn，聚合 JSON 输出）。"""
    from eidolon.core.supply_index.bench_process import child_measure, run_subprocess

    if args.child:
        seg = child_measure(args.cache_root, args.card)
        sys.stdout.write(json.dumps(seg, ensure_ascii=False) + "\n")
        return 0
    out = run_subprocess(args.cache_root, cards=args.cards or None,
                         rounds=args.rounds, random_n=args.random_n,
                         single_repeat=args.single_repeat, seed=args.seed)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    _emit(out)
    return 0


def cmd_audit(args) -> int:
    from eidolon.core.supply_index.audit import audit, audit_auto

    out = audit(args.cache_root, game_arg=args.fake_game)
    if args.auto:
        game, locale = _need_identity(
            args, "audit --auto（行为审计含 cold 建库=cold 面）")
        out["auto_mode"] = audit_auto(args.cache_root, game=game, locale=locale,
                                      scratch_root=args.auto_scratch)
        out["pass"] = bool(out["pass"] and out["auto_mode"]["pass"])
    _emit(out)
    return 0 if out["pass"] else 1


def cmd_measure(args) -> int:
    from eidolon.core.supply_index.bench import measure

    _emit(measure(args.cache_root))
    return 0


def cmd_integrity(args) -> int:
    from eidolon.core.supply_index.integrity import integrity
    from eidolon.core.supply_index.warm import SupplyIndexCorruptError

    game, locale = _need_identity(
        args, "integrity（--repair 重推导=cold 面；纯扫描同面显式给）")
    try:
        out = integrity(args.cache_root, game=game, locale=locale,
                        do_repair=args.repair)
    except SupplyIndexCorruptError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 1
    _emit(out)
    return 1 if out.get("bad") else 0


def cmd_maintain(args) -> int:
    from eidolon.core.supply_index import maintain

    out = maintain.run(args.cache_root, do_prune=args.prune, keep=args.keep,
                       dry_run=args.dry_run)
    _emit(out)
    return 0 if out.get("ok", True) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="eidolon.core.supply_index",
                                 description="Eidolon 供给落盘索引"
                                             "（Phase 5 内部工具；不进产品 CLI）")
    ap.add_argument("--cache-root", default=None,
                    help="缓存根（必填——产品无 env/默认解析链，显式给；"
                         "顶层或子命令任一位置给出即可）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _add_sub(name, fn, help_, *, identity: str = "none"):
        """identity：required=--game/--locale 必填；optional=按消费路径校验；
        none=命令不消费游戏身份（不给参数面）。"""
        p = sub.add_parser(name, help=help_)
        if identity != "none":
            p.add_argument("--game", required=(identity == "required"),
                           help="游戏安装根（显式；产品无 env 解析链）")
            p.add_argument("--locale", required=(identity == "required"),
                           help="locale（显式；语料缺省值不在此隐式补）")
        p.add_argument("--cache-root", default=argparse.SUPPRESS,
                       help="覆写顶层 --cache-root（SUPPRESS 防子解析器默认值回填"
                            "覆盖顶层已解析值）")
        p.set_defaults(fn=fn)
        return p

    p = _add_sub("build", cmd_build, "冷侧建库（全量；--cards/--sample 定向增量）",
            identity="required")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--cards", nargs="*", default=None)
    p.add_argument("--sample", type=int, default=None,
                   help="随机抽 N 卡定向 build（种子 42）")
    p.add_argument("--skip-bundle-hash", action="store_true",
                   help="诊断用：跳过全语料 sha（bundles.sha256 记空串）")

    p = _add_sub("warm", cmd_warm, "暖侧供给（无 UnityPy；三态 --mode，缺项语义见 help）",
            identity="optional")
    p.add_argument("--cards", nargs="*", default=None,
                   help="卡集（缺省=本代 cards 表抽样 53 张，种子 42）")
    p.add_argument("--mode", choices=["require-cache", "auto", "offline"],
                   default="require-cache",
                   help="require-cache=缺项 fail loud 列清单（缺省，P1 语义）；"
                        "auto=缺项自动冷补（定向 cold decode，全包唯一合法 "
                        "UnityPy 模式）+三层自愈（L1 索引坏自动重建/L2 blob 失配"
                        "单次重推导/L3 源坏诊断分级）后转 warm，仍缺响应亮；"
                        "offline=require-cache + 零游戏访问审计形态")
    p.add_argument("--save-png", default=None,
                   help="调试：装配结果中 png 项落 PNG 目录")

    p = _add_sub("diff", cmd_diff, "版本 cheap diff（五态迁移报告；默认 from=另一代）",
            identity="optional")
    p.add_argument("--from-gen", dest="from_gen", default=None)
    p.add_argument("--to-gen", dest="to_gen", default=None)
    p.add_argument("--synthetic", action="store_true",
                   help="合成旧代副本演练五态（注入 bundle sha/guid/卡变化；不碰真代）")

    p = _add_sub("revalidate", cmd_revalidate,
            "exact 重读（须 --exact；处理 revalidate 槽位）", identity="required")
    p.add_argument("--exact", action="store_true")
    p.add_argument("--from-gen", dest="from_gen", default=None)
    p.add_argument("--to-gen", dest="to_gen", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=2)

    p = _add_sub("verify", cmd_verify, "冷暖逐字节一致验证（payload+像素级+kit 逐字段）",
            identity="required")
    p.add_argument("--sample", type=int, default=500)
    p.add_argument("--golden-sample", dest="golden_sample", type=int, default=100)
    p.add_argument("--all", dest="all_items", action="store_true",
                   help="全量档（Phase 5 审计 P2）：art 的 portrait/portrait_golden "
                        "两种 kind 全集 + watermark 全集入 cold 现算对拍（默认只抽样："
                        "--sample/--golden-sample/200 wm——37k 级全量耗时随语料线性"
                        "增长，收口前显式选择）")
    p.add_argument("--gate-cards", dest="gate_cards", nargs="*", default=None,
                   help="gate 卡集（像素级全查轴；缺省=本代 cards 表抽样 53 张，"
                        "种子 --seed；空列表=跳过 gate 轴）")
    p.add_argument("--no-kits", dest="no_kits", action="store_true",
                   help="跳过 kit 冷暖一致段（默认全查）")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--jobs", type=int, default=4)

    p = _add_sub("bench", cmd_bench, "实测收口（warm/cold p50/p95、命中率、存储）",
            identity="required")
    p.add_argument("--cards", nargs="*", default=None,
                   help="卡集（缺省=本代 cards 表抽样 53 张，种子 42）")
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--cold-sample", dest="cold_sample", type=int, default=20)
    p.add_argument("--jobs", type=int, default=4)

    p = _add_sub("bench-process", cmd_bench_process,
            "进程级 warm 墙钟 bench（单卡全新 Python 子进程分段：interpreter/"
            "imports/open/plan/assemble；基准集+随机+单卡重复，OS 暖两轮+冷态"
            "首触标注；JSON 输出）", identity="none")
    p.add_argument("--child", action="store_true",
                   help="内部：单卡子进程形态（打印分段 JSON 供父进程聚合）")
    p.add_argument("--card", default=None, help="child 形态：单卡 card_id")
    p.add_argument("--cards", nargs="*", default=None,
                   help="基准卡集（缺省=本代 cards 表抽样 53 张，种子 42）")
    p.add_argument("--rounds", type=int, default=2, help="OS 暖轮数（缺省 2）")
    p.add_argument("--random-n", dest="random_n", type=int, default=10,
                   help="随机卡样本数（种子 --seed；排除基准集重叠）")
    p.add_argument("--single-repeat", dest="single_repeat", type=int, default=8,
                   help="单卡重复进程数（卡内分布）")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=None, help="JSON 落盘路径（stdout 恒输出）")

    p = _add_sub("audit", cmd_audit, "warm 隔离机器证明（全卡装配；坏 game + "
                                "import blocker + open 拦 + require-cache 负探针）",
            identity="optional")
    p.add_argument("--fake-game", dest="fake_game", default=None,
                   help="offline 审计用的不存在游戏根")
    p.add_argument("--auto", action="store_true",
                   help="加跑 auto 模式行为审计（一次性缓存根部分建库→冷补→复验；"
                        "合法用 UnityPy 的唯一模式）")
    p.add_argument("--auto-scratch", dest="auto_scratch", default=None,
                   help="auto 审计一次性缓存根（缺省=系统临时目录，用完即焚）")

    p = _add_sub("measure", cmd_measure, "存储代价实测（一次性输出）", identity="none")

    p = _add_sub("integrity", cmd_integrity,
            "全量 blob 完整性扫（blobs 行 vs 盘上文件逐个 hash；bad=exit 1）",
            identity="required")
    p.add_argument("--repair", action="store_true",
                   help="定点修复：坏 blob 属主 item 逐域重推导（字节全等或响亮），"
                        "修复后重扫")

    p = _add_sub("maintain", cmd_maintain,
            "旧代维护（默认列代只读；--prune 删旧代——保留策略/锁/integrity 前置"
            "见 maintain 模块头）", identity="none")
    p.add_argument("--prune", action="store_true",
                   help="执行删旧代（缺省=仅列代；synthetic/leftover 残目录一律清）")
    p.add_argument("--keep", type=int, default=2,
                   help="保留代数（current 恒在内；缺省 2=Current+上一代）")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="只走保留策略账不删除（integrity 前置在真删时执行）")

    args = ap.parse_args(argv)
    # --cache-root 缺省校验（解析后统一裁决：顶层/子命令任一位置可给；都不给=
    # 参数错误退出 2——产品无 env/默认解析链，不读 env 不算默认）
    if getattr(args, "cache_root", None) is None:
        _stderr("参数错误：--cache-root 必填（supply 缓存根；产品无 env/默认解析链"
                "——core 内部工具不 import shell 默认根派生，显式给）")
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
