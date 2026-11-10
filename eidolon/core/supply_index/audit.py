"""audit — warm 隔离机器证明 + 双模式行为审计（P2 车2；Phase 5 返工 R1 P0-2）。

四个子证明（1-3 全过=隔离 PASS；4=auto 行为审计随 --auto）：
1. 全卡 offline：子进程带 `--game <不存在目录>` 跑 **全卡装配走查**（cards 表
   全集按缺席归因分道：ok 卡（期望全 built）严格 assemble_card 全 role 出货 +
   全部 kit 六面重组 + text 全域段；absent 两类（数据缺席）跳过装配显式计账
   ——R2 缺席归因）——warm 供给不触游戏身份，坏 --game 必须无感通过；
   同时 = 「第二次跑全卡零 UnityPy」验收面。**full 代 assemble_card 严格门**
   （expected-vs-built：ok 卡缺产物即 raise——P0-2）；partial 代 allow_partial
   显式豁免 + 报告 "partial": true 标注（partial 代定义=scope 外可缺，不按全卡
   严格门）。走查尾汇总 raise **只对 full 代的 missing_gap/anomaly（不可归因
   缺口）抛**——可归因缺席不抛、partial 代 scope 外可缺不抛（R2）。
2. import blocker：同子进程 sys.meta_path 拦 UnityPy/texture2ddecoder/
   eidolon.core.render/eidolon.core.supply/eidolon.core.recipes/cold/kit_extract/
   text_extract/wm_extract/mip_extract——全卡装配跑通=隔离机器面（kit_codec/
   gems_codec/text_codec/mip_codec 过闸——UnityPy-free 面）。**A4 扩面**：
   color 域全查同窗（probe 表 + 全 atlas 槽 warm 解码 + manifest 像素 sha 对账
   ——warm color 读取零游戏文件的机器证明；缺 color 域的旧代列账
   color_missing 不炸——color 完整性门在 build 发布门/expected-vs-built，
   audit 只证隔离）。**A5 扩面**：mip 域全查同窗（mip_registry 全链解码+
   聚合 sha/链数/级数/filter-bias 对账 + portrait_mip 样本走查——warm mip
   读取零游戏文件；缺 mip 域旧代列账 mip_missing 不炸）。
3. open 拦截：子进程内建 open 对游戏文件族 raise（`*.unity3d` +
   `globalgamemanagers*` + `resources.assets*` + `*.dll`——P1-7 返工 R1 扩面，
   见 _OPEN_BLOCK_GAME_FILES）——装配跑通=零游戏文件读取。
4. 负探针（require-cache 行为审计）：子进程对不存在卡跑 check→SupplyMissingError
   必须响亮（fail-loud 语义存续证明）。
5. auto 行为审计（--auto；合法用 UnityPy 的唯一模式）：一次性缓存根部分建库
   （全表+子集 decode）→ require-cache 对未建卡 fail loud → auto 冷补 → 复验
   全绿 → 不可补卡（无 locator）保持 fail loud 列清单。scratch 用完即焚。
6. 完整性门（P0-2 返工 R1；R2 缺席归因口径）：meta.full_build=1 的代——
   缺席归因账（warm.account_for_cards，DB 面单源）**missing_gap==0 且
   anomaly==0** → pass；可归因数据缺席（absent_expectationless +
   absent_locator_missing，如 dbf 无卡面纹理行 / locator status≠ok）显式计数
   进报告（accounted_absent）不判红——与 build 尾部发布门 expected-vs-built
   同口径：不可归因缺口才红。child（走查报告）在窗时加自洽断言
   assembled+absent+gap==cards 且 child absent==DB 归因 absent。full_build=0
   的代显式 partial 标注、不按全卡严格门（scope 外缺项是 partial 代定义）。

子进程代码经 -c 注入（用完即焚，无临时文件）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.paths import SupplyLayout

_BLOCKED = ("UnityPy", "texture2ddecoder", "eidolon.core.render",
            "eidolon.core.supply", "eidolon.core.recipes",
            "eidolon.core.supply_index.cold",
            "eidolon.core.supply_index.kit_extract",
            "eidolon.core.supply_index.text_extract",
            "eidolon.core.supply_index.wm_extract",
            "eidolon.core.supply_index.mip_extract")

# open 拦截游戏文件族（P1-7 返工 R1 扩面：basename 形态 fnmatch；warm 面
# 合法读取只有自身缓存 blob/index——命中即 raise）
_OPEN_BLOCK_GAME_FILES = ("*.unity3d", "globalgamemanagers*",
                          "resources.assets*", "*.dll")

_WARM_CHILD = r'''
import json, sys, os, builtins
from fnmatch import fnmatch

# ---- import blocker（机器证明面：warm 进程内任何被禁 import 即 raise）----
class Blocker:
    _BANNED = ''' + repr(list(_BLOCKED)) + r'''
    def find_module(self, name, path=None):
        return self.find_spec(name, path)
    def find_spec(self, name, path=None, target=None):
        for b in self._BANNED:
            if name == b or name.startswith(b + "."):
                raise ImportError(f"audit import blocker: {name} 在 warm 面被禁"
                                  "（设计必须保留 #1）")
        return None

sys.meta_path.insert(0, Blocker())

# ---- open 拦截（游戏文件族全禁：warm 不开游戏文件；P1-7 扩面账）----
_OPEN_BLOCK_GAME_FILES = ''' + repr(list(_OPEN_BLOCK_GAME_FILES)) + r'''
_real_open = builtins.open
def guarded_open(file, *a, **kw):
    name = os.path.basename(str(file)).lower()
    for pat in _OPEN_BLOCK_GAME_FILES:
        if fnmatch(name, pat):
            raise PermissionError(f"audit open-blocker: warm 面禁开游戏文件 {file}"
                                  f"（命中 {pat}）")
    return _real_open(file, *a, **kw)
builtins.open = guarded_open

# ---- 入口参数：--game 指向不存在的目录（warm 必须无感）----
fake_game = sys.argv[1]
assert not os.path.exists(fake_game), f"审计前提失效：{fake_game} 竟存在"

from eidolon.core.supply_index.warm import (
    SupplyIndex,
    SupplyMissingError,
    account_for_cards,
)
cache_root = sys.argv[2]
with SupplyIndex(cache_root) as idx:
    cards = idx.card_ids()          # 全卡轴（cards 表全集——「第二次跑全卡」）
    # full/partial 门形态（P0-2）：ok 卡 assemble_card 严格门（缺预期产物即
    # raise）；partial 代 allow_partial 显式豁免（scope 外可缺）
    fb = idx.conn.execute("SELECT value FROM meta WHERE key='full_build'"
                          ).fetchone()
    full_build = bool(fb and fb[0] == "1")
    # R2 缺席归因分道：只有 ok 卡（期望全 built）进严格装配走查；absent 两类
    # （数据缺席，零期望）跳过装配显式计账——空 plan 是合法形态不是缺口
    acct = account_for_cards(idx.conn, cards)
    counts = acct["counts"]
    n_empty = 0
    sections = {}
    for i, cid in enumerate(acct["ok"]):
        bundle = idx.assemble_card(cid, allow_partial=not full_build)
        if len(bundle) <= 1:              # 只带 text 段=plan 零 items（ok 卡不该空）
            n_empty += 1
        for role in bundle:
            sections[role] = sections.get(role, 0) + 1
        if (i + 1) % 5000 == 0:
            print(f"[audit-full {i+1}/{len(acct['ok'])}]", file=sys.stderr)
    # kit 域全查 + text 全域段（共享缓存面同窗）
    kits = {f: isinstance(idx.kit(f), dict) for f in idx.kit_frames()}
    text = idx.text()
    # color 域全查（Phase 1 A4）：probe 表 + 全 atlas 槽解码（open/import blocker
    # 同窗=warm color 读取零游戏文件的机器证明面）；缺 color 域（旧代）列账不炸
    color = None
    color_missing = None
    try:
        from eidolon.core.supply_index import schema as _S
        from hashlib import sha256 as _sha
        probe = idx.color_probe()
        atlas_bad = []
        n_atlas = 0
        rows = idx.conn.execute(
            "SELECT item_key, params_json, manifest_json FROM items "
            "WHERE domain=? AND item=? ORDER BY params_json",
            (_S.DOMAIN_COLOR, _S.ITEM_COLOR_ATLAS)).fetchall()
        for r in rows:
            p = json.loads(r["params_json"])
            m = json.loads(r["manifest_json"])
            img = idx.color_atlas(p["family"], p["ct"])
            n_atlas += 1
            if _sha(img.tobytes()).hexdigest() != m["pixel_sha256"]:
                atlas_bad.append(f"{p['family']}[{p['ct']}]")
        color = {"probe_families": {k: len(v) for k, v in probe.items()},
                 "atlas_items": n_atlas, "atlas_bad": atlas_bad}
    except Exception as exc:                      # noqa: BLE001 —— 旧代无 color 域
        color_missing = f"{type(exc).__name__}: {exc}"
    # mip 域全查（Phase 1 A5）：registry 全链解码对账（payload sha 由读面校验 +
    # 聚合内容 sha/链数/级数/filter-bias 对 manifest）+ portrait_mip 样本走查
    # （open/import blocker 同窗=warm mip 读取零游戏文件的机器证明面）；缺 mip
    # 域（旧代）列账 mip_missing 不炸（mip 完整性门在 expected-vs-built）
    mip = None
    mip_missing = None
    try:
        from eidolon.core.supply_index import mip_codec as _MC
        mrow = idx.conn.execute(
            "SELECT item_key, manifest_json, content_inputs_json FROM items "
            "WHERE domain=? AND item=?",
            (_S.DOMAIN_TEXTURES, _S.ITEM_MIP_REGISTRY)).fetchone()
        reg_bad = []
        if mrow is None:
            raise SupplyMissingError(["textures: mip_registry item 缺失"])
        reg = idx.mip_registry()
        mm = json.loads(mrow["manifest_json"])
        ci = json.loads(mrow["content_inputs_json"])
        arrays = _MC.decode_chain_npz(idx._read_role_blob(
            mrow["item_key"], "registry", "audit mip"))
        agg = _MC.chain_content_sha([arrays[k] for k in sorted(arrays)])
        if agg != ci.get("chains"):
            reg_bad.append("chains 聚合 sha 失配")
        if len(reg) != mm.get("chain_count"):
            reg_bad.append(f"链数失配 {len(reg)} != {mm.get('chain_count')}")
        for name, m in mm.get("chains", {}).items():
            ent = reg.get(name)
            if ent is None:
                reg_bad.append(f"缺链 {name}")
            elif len(ent["lods"]) != m["mip_count"]:
                reg_bad.append(f"{name} 级数失配")
            elif ent["filter"] != m["filter"] or ent["bias"] != m["bias"]:
                reg_bad.append(f"{name} filter/bias 失配")
        pm_ok, pm_bad = 0, []
        for cid in acct["ok"][:64]:
            # 期望人口过滤：无 portrait_mip role 的 ok 卡（kit/color-only 卡=
            # 合法无肖像面；unsupported 卡=缺席可归因不期望）不计 bad
            has_mip = idx.conn.execute(
                "SELECT 1 FROM plan_items pi JOIN plans p ON p.plan_key="
                "pi.plan_key WHERE p.card_id=? AND pi.role=? LIMIT 1",
                (cid, _S.ITEM_PORTRAIT_MIP)).fetchone() is not None
            if not has_mip:
                continue
            try:
                ent = idx.portrait_mip(cid)
                if len(ent["chain"]) < 1:
                    pm_bad.append(f"{cid}: 空链")
                else:
                    pm_ok += 1
            except Exception as exc:  # noqa: BLE001 —— 缺项即账
                pm_bad.append(f"{cid}: {type(exc).__name__}: {exc}")
        mip = {"registry_chains": len(reg), "registry_bad": reg_bad[:8],
               "registry_bad_total": len(reg_bad),
               "portrait_mip_sample": pm_ok, "portrait_mip_bad": pm_bad[:8],
               "portrait_mip_bad_total": len(pm_bad)}
    except Exception as exc:                      # noqa: BLE001 —— 旧代无 mip 域
        mip_missing = f"{type(exc).__name__}: {exc}"
    # supplement 域全查（Phase 1 A6）：kit 扩展面（races/mesh_refs）+ kit_light
    # 全帧 + supp 全 item 解码（open/import blocker 同窗=warm A6 域读取零游戏
    # 文件的机器证明面）；缺 A6 域（旧代）列账 supp_missing 不炸（A6 域无期望
    # 账——卡不变全局项，完整性面=本段 + build 发布门）
    supp = None
    supp_missing = None
    try:
        from eidolon.core.supply_index import schema as _S6
        supp_bad = []
        # kit 扩展面：races 帧族须有面（strings dict）+ mesh_refs 全帧须有面
        for f in idx.kit_frames():
            mr = idx.kit_mesh_refs(f)
            if not isinstance(mr, dict):
                supp_bad.append(f"kit {f}: mesh_refs 面缺席")
            if f in _S6.KIT_RACE_FRAMES:
                rc = idx.kit_races(f)
                if not (isinstance(rc, dict)
                        and isinstance(rc.get("strings"), dict)):
                    supp_bad.append(f"kit {f}: races 面缺席（races 帧族）")
        n_light = 0
        for f in idx.kit_light_frames():
            k = idx.kit_light(f)
            n_light += 1
            if not isinstance(k, dict) or not isinstance(k.get("meta"), dict):
                supp_bad.append(f"kit_light {f}: 六面形状不符")
        supp_items = 0
        for r in idx.conn.execute(
                "SELECT item_key, domain, item, params_json, manifest_json "
                "FROM items WHERE codec='supp'").fetchall():
            params = json.loads(r["params_json"])
            parts = idx.supplement_parts(r["domain"], r["item"], params)
            supp_items += 1
            m = json.loads(r["manifest_json"])
            for pname, p in m["parts"].items():
                v = parts.get(pname)
                if p["kind"] in ("png", "bin"):
                    if len(v or {}) != len(p["files"]):
                        supp_bad.append(f"{r['item']}.{pname}: 文件数失配")
                elif v is None:
                    supp_bad.append(f"{r['item']}.{pname}: part 缺席")
        supp = {"kit_frames": len(idx.kit_frames()), "kit_light_frames": n_light,
                "supp_items": supp_items, "bad": supp_bad[:8],
                "bad_total": len(supp_bad)}
    except Exception as exc:                      # noqa: BLE001 —— 旧代无 A6 域
        supp_missing = f"{type(exc).__name__}: {exc}"
    print(json.dumps({
        "cards": len(cards), "assembled": len(acct["ok"]),
        "empty_plan_cards": counts["absent_expectationless"]
                            + counts["absent_locator_missing"],
        "absent_expectationless": counts["absent_expectationless"],
        "absent_locator_missing": counts["absent_locator_missing"],
        "missing_gap": counts["missing_gap"],
        "missing_gap_cards": acct["samples"]["missing_gap"],
        "anomaly_total": counts.get("anomaly_total", 0),
        "ok_empty_bundles": n_empty,
        "full_build": full_build,
        "partial": not full_build,
        "sections": dict(sorted(sections.items())),
        "kits_ok": sum(1 for v in kits.values() if v), "kits_total": len(kits),
        "text_fontdefs": len(text["fontdefs"]),
        "text_fonts": sorted(text["fonts"]),
        # color 段放尾部（父报告 stdout 截断窗 1200 字符——game_root 两字段须
        # 留在窗内供断言；color 全文经父端 json.loads(child) 提取，不受截断影响）
        "game_root_arg": fake_game,
        "game_root_exists": os.path.exists(fake_game),
        "color": color, "color_missing": color_missing,
        "mip": mip, "mip_missing": mip_missing,
        "supp": supp, "supp_missing": supp_missing,
    }))
    # 走查尾汇总 raise：只对 missing_gap/anomaly（不可归因缺口）抛，且只对
    # full 代抛（partial 代 scope 外可缺=partial 定义）；可归因缺席（absent
    # 两类）不抛（R2 门语义——doc 已先行 print 供门消费）
    red = list(acct["missing_gap"]) + [c for lst in acct["anomaly"].values()
                                       for c in lst]
    if red and full_build:
        raise SupplyMissingError(red)
'''

_NEGATIVE_CHILD = r'''
import sys
from eidolon.core.supply_index.warm import SupplyIndex, SupplyMissingError
cache_root, ghost = sys.argv[1], sys.argv[2]
with SupplyIndex(cache_root) as idx:
    rep = idx.check([ghost])
    if not rep["miss"]:
        raise SystemExit("负探针失效：不存在卡未被报缺")
    raise SupplyMissingError(rep["missing_cards"] + rep["missing_items"])
'''


def _read_meta_full_build(layout: SupplyLayout) -> bool:
    """现行代 meta.full_build（无代/缺键=False——partial 门语义）。"""
    try:
        cur = layout.read_current()
        if not cur:
            return False
        conn = S.connect(layout.gen_db(cur["game_id"]), readonly=True)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key='full_build'").fetchone()
            return bool(row and row["value"] == "1")
        finally:
            conn.close()
    except Exception:                                   # noqa: BLE001
        return False


def completeness_gate(cache_root: Path | str, *,
                      child: dict | None = None) -> dict:
    """expected-vs-built 完整性门（P0-2；R2 缺席归因口径；audit pass 判定的
    纯账面）。

    full 代（meta.full_build=1）：缺席归因账（warm.account_for_cards——与
    warm.plan/schema.expected_vs_built 同一判据单源）**missing_gap==0 且
    anomaly==0** → pass；可归因数据缺席（absent_expectationless +
    absent_locator_missing）显式计数进 accounted_absent 不判红——full 代完整
    性 = expected-vs-built 零缺口，数据缺席单列不算失败。给了 child（offline
    走查报告）时加自洽断言：assembled+absent+gap==cards、child absent==DB
    归因 absent（walk 跳过集必须等于 DB 归因集）。partial 代：不按全卡严格门
    （scope 外缺项是 partial 代定义），输出显式 partial 标注。"""
    layout = SupplyLayout(cache_root)
    full = _read_meta_full_build(layout)
    out: dict = {"full_build": full, "partial": not full, "pass": True,
                 "why": []}
    if not full:
        return out
    from eidolon.core.supply_index.warm import account_for_cards

    cur = layout.read_current()
    conn = S.connect(layout.gen_db(cur["game_id"]), readonly=True)
    try:
        cards = [r["card_id"] for r in
                 conn.execute("SELECT card_id FROM cards")]
        acct = account_for_cards(conn, cards)
        comp = S.expected_vs_built(conn)
    finally:
        conn.close()
    counts = acct["counts"]
    n1 = counts["absent_expectationless"]
    n2 = counts["absent_locator_missing"]
    gap = counts["missing_gap"]
    out["accounted_absent"] = {"expectationless": n1, "locator_missing": n2}
    out["attribution"] = {"counts": counts, "samples": acct["samples"]}
    out["completeness"] = {k: comp[k] for k in
                           ("plans", "expectationless_cards",
                            "missing_total", "by_kind",
                            "missing_sample")}
    if gap:
        out["pass"] = False
        out["why"].append(
            f"full 代期望缺口 {gap} 卡（missing_gap——不可归因缺席）："
            f"{acct['samples']['missing_gap'][:10]}")
    if counts["anomaly_total"]:
        out["pass"] = False
        out["why"].append(
            f"unaccountable anomaly {counts['anomaly_total']} 卡："
            f"{acct['samples']['anomaly'][:10]}")
    if child is not None:
        c_n1 = child.get("absent_expectationless")
        c_n2 = child.get("absent_locator_missing")
        c_gap = child.get("missing_gap")
        total = child.get("cards")
        asm = child.get("assembled")
        if None not in (c_n1, c_n2, total, asm) and \
                asm + c_n1 + c_n2 + (c_gap or 0) != total:
            out["pass"] = False
            out["why"].append(
                f"assembled {asm} + absent {c_n1}+{c_n2} + gap {c_gap or 0}"
                f" != cards {total}")
        if None not in (c_n1, c_n2) and (c_n1, c_n2) != (n1, n2):
            out["pass"] = False
            out["why"].append(
                f"child absent {c_n1}+{c_n2} != DB 归因 absent {n1}+{n2}"
                "（walk 跳过集与 DB 归因集不一致）")
        if c_gap is not None and c_gap != gap:
            out["pass"] = False
            out["why"].append(
                f"child missing_gap {c_gap} != DB 归因 {gap}")
    return out


def audit(cache_root: Path | str, *, game_arg: str | None = None) -> dict:
    """全卡 warm 隔离（三道拦截同窗）+ require-cache 负探针 + 完整性门（P0-2）。"""
    layout = SupplyLayout(cache_root)
    fake_game = game_arg or "Z:/definitely-not-a-game-dir-audit-supply"
    results: dict = {}
    ok_all = True

    # 1+2+3：全卡 offline + import blocker + open 拦截（同一子进程三道同窗）
    p = subprocess.run([sys.executable, "-c", _WARM_CHILD, fake_game,
                        str(layout.root)], capture_output=True, text=True)
    child: dict | None = None
    try:
        child = json.loads(p.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        child = None
    full_build = _read_meta_full_build(layout)
    if full_build:
        # full 代：child 必须成功且 JSON 完整（ok 卡严格 assemble_card 门；
        # gap/anomaly 走查尾汇总 raise——缺席两类不 raise）；缺席归因自洽由
        # completeness_gate 复核（assembled+absent+gap==cards、child==DB）
        full_ok = (p.returncode == 0 and child is not None
                   and '"assembled"' in p.stdout)
        child_doc = child or {}
    else:
        # partial 代：child 成功即可（allow_partial 豁免——scope 外缺项是
        # partial 代定义）；显式 partial 标注
        full_ok = p.returncode == 0 and '"assembled"' in p.stdout
        child_doc = child or {"partial": True}
    results["full_cards_offline"] = {
        "pass": full_ok, "game_arg": fake_game,
        "full_build": full_build, "partial": not full_build,
        "child": {k: child_doc.get(k) for k in
                  ("cards", "assembled", "empty_plan_cards",
                   "absent_expectationless", "absent_locator_missing",
                   "missing_gap", "anomaly_total", "full_build",
                   "partial", "kits_total", "game_root_exists",
                   "color", "color_missing", "mip", "mip_missing",
                   "supp", "supp_missing")}
        if child_doc else None,
        "stdout": p.stdout.strip()[:1200],
        "stderr_tail": p.stderr.strip()[-500:] if p.returncode else ""}
    ok_all &= full_ok

    results["import_blocker"] = {
        "pass": full_ok,
        "blocked_modules": list(_BLOCKED),
        "open_block_game_files": list(_OPEN_BLOCK_GAME_FILES),
        "note": "blocker 内嵌于 offline 子进程（同一装配同时受三道拦截；"
                "P2 车2 面扩大到全卡装配+text/kit/gems 重组——codec 三件套过闸；"
                "P1-7 返工 R1：open 拦截扩到游戏文件族 unity3d/gmm/resources/"
                "dll）"}
    ok_all &= full_ok

    # 6：完整性门（P0-2/R2——full 代缺席归因账 gap==0 + 走查自洽断言）
    gate = completeness_gate(cache_root, child=child)
    results["completeness_gate"] = gate
    ok_all &= gate["pass"]

    # 4：require-cache 负探针（fail-loud 存续）
    p2 = subprocess.run([sys.executable, "-c", _NEGATIVE_CHILD, str(layout.root),
                         "__audit_ghost_card__"], capture_output=True, text=True)
    neg_ok = p2.returncode != 0 and "SupplyMissingError" in (p2.stderr + p2.stdout) \
        and "__audit_ghost_card__" in (p2.stderr + p2.stdout)
    results["require_cache_negative"] = {
        "pass": neg_ok, "ghost_card": "__audit_ghost_card__",
        "rc": p2.returncode, "stderr_tail": p2.stderr.strip()[-300:]}
    ok_all &= neg_ok

    return {"pass": ok_all, "results": results,
            "selfheal_counters": _read_selfheal_counters(layout)}


def _read_selfheal_counters(layout: SupplyLayout) -> dict:
    """自愈留账（代库 meta selfheal_*；读不到=空账，损坏面由子进程响亮）。"""
    try:
        from eidolon.core.supply_index import schema as S
        from eidolon.core.supply_index.selfheal import read_counters

        cur = layout.read_current()
        if not cur:
            return {}
        conn = S.connect(layout.gen_db(cur["game_id"]), readonly=True)
        try:
            return read_counters(conn)
        finally:
            conn.close()
    except Exception:                                   # noqa: BLE001
        return {}


def audit_auto(cache_root: Path | str, *, game: Path, locale: str,
               scratch_root: str | None = None) -> dict:
    """auto 模式行为审计（一次性缓存根；合法用 UnityPy 的唯一模式的机器演练）。

    序列：partial-init build（sample=2）→ require-cache 对 [已建2+未建3+不可补1]
    fail loud → auto 冷补 3 卡 → auto 全绿 → 不可补卡（无 locator 的域外卡）仍在
    缺项清单。scratch 缓存根用完即焚（缺省=系统临时目录——上游树内 output/ 面
    属 repo 派生，Phase 5 去 repo 定案不搬）。game/locale 必填。"""
    import tempfile

    from eidolon.core.supply_index import cold
    from eidolon.core.supply_index.warm import SupplyIndex, SupplyMissingError

    root = Path(scratch_root) if scratch_root else Path(tempfile.mkdtemp(
        prefix="supply-auto-audit-", dir=str(_scratch_dir())))
    made_tmp = scratch_root is None
    out: dict = {"scratch_root": str(root)}
    try:
        # 1. 部分代初始化（全表+kit/gems/text/wm 域项+2 卡 decode）
        t0 = time.perf_counter()
        built = cold.build(root, game=game, locale=locale, sample=2)
        out["partial_build"] = {"mode": built["mode"],
                                "items": built["items"],
                                "wall_s": built["wall_s"]}
        with SupplyIndex(root) as idx:
            all_cards = idx.card_ids()
            built_cards = []
            for r in idx.conn.execute(
                    "SELECT params_json FROM items WHERE domain='art'"):
                built_cards.append(json.loads(r["params_json"])["card_id"])
            built_cards = sorted(set(built_cards))
            # 未建卡=locator-ok 有 portrait 的卡中无 item 者（可补面）
            with_item = set(built_cards)
            unfilled = [c for c in all_cards
                        if c not in with_item and _has_portrait_locator(idx, c)]
            # 不可补面：有 locator 行（含 status=missing）而无 item——auto 补不动，
            # fail loud 面；_locator_any=False 的缺席卡=数据缺席（check 合法不报缺）
            unfillable = [c for c in all_cards
                          if c not in with_item and not _has_portrait_locator(idx, c)
                          and _has_any_portrait_locator(idx, c)]
        probe = built_cards[:2] + unfilled[:3]
        ghost = unfillable[0] if unfillable else "__no_such_card__"
        out["cards"] = {"built": built_cards[:2], "fillable": unfilled[:3],
                        "unfillable_sample": ghost}

        # 2. require-cache 对混合集 fail loud（未建卡必须列缺）
        with SupplyIndex(root) as idx:
            rep = idx.check(probe + ([ghost] if ghost not in probe else []))
        step2_ok = rep["miss"] > 0
        out["require_cache_before_fill"] = {"pass": step2_ok, "miss": rep["miss"]}

        # 3. auto 模式（冷补→复验）：fill 面只对可补卡；ghost 恒缺（数据缺席）
        with SupplyIndex(root) as idx:
            fm = idx.fillable_missing(probe + ([ghost] if ghost not in probe else []))
        fill_cards = fm["fillable"]
        if fill_cards:
            cold.build(root, game=game, locale=locale, cards=fill_cards)
        with SupplyIndex(root) as idx:
            rep_after = idx.check(probe)
            try:
                for cid in probe:
                    idx.assemble_card(cid)
                assemble_ok = True
                why = None
            except SupplyMissingError as exc:
                assemble_ok = False
                why = str(exc)[:200]
        step3_ok = rep_after["miss"] == 0 and assemble_ok
        out["auto_fill"] = {"filled": fill_cards, "pass": step3_ok,
                            "miss_after": rep_after["miss"], "why": why}

        # 4. 不可补卡保持 fail loud（ghost 恒缺——auto 语义=响应亮不静默）
        with SupplyIndex(root) as idx:
            rep_ghost = idx.check([ghost])
        step4_ok = rep_ghost["miss"] > 0
        out["unfillable_still_fails"] = {"pass": step4_ok, "card": ghost,
                                         "miss": rep_ghost["miss"]}
        out["pass"] = bool(step2_ok and step3_ok and step4_ok)
        out["wall_s"] = round(time.perf_counter() - t0, 1)
        return out
    finally:
        if made_tmp and root.exists():
            shutil.rmtree(root, ignore_errors=True)


def _has_portrait_locator(idx, card_id: str) -> bool:
    row = idx.conn.execute(
        "SELECT 1 FROM locators WHERE kind='portrait' AND subject=? AND "
        "status='ok' LIMIT 1", (card_id,)).fetchone()
    return row is not None


def _has_any_portrait_locator(idx, card_id: str) -> bool:
    row = idx.conn.execute(
        "SELECT 1 FROM locators WHERE kind='portrait' AND subject=? LIMIT 1",
        (card_id,)).fetchone()
    return row is not None


def _scratch_dir() -> Path:
    """auto 审计 scratch 缓存根的宿主目录（系统临时目录——上游树内 output/ 面
    属 repo 派生，Phase 5 去 repo 定案不搬；焚后无痕由调用方 rmtree 保证）。

    P1-1 返工 R1：宿主目录 mkdir(parents=True, exist_ok=True)——旧形直接把该
    路径喂 tempfile.mkdtemp(dir=...)，宿主目录不存在时 FileNotFoundError（audit
    --auto 从未真正跑通过的根因）。"""
    import tempfile

    d = Path(tempfile.gettempdir()) / "eidolon-supply-audit-auto"
    d.mkdir(parents=True, exist_ok=True)
    return d
