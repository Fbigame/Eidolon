"""diff — 版本失效感知：cheap diff（默认，秒级）+ revalidate --exact（按需重读）。

**范围账（Phase 5 审计 P2 修复）**：五态迁移的槽位面=**全供给域**——art
（portrait/portrait_golden）、watermark（per-card）、frames（kit，卡不变域）、
gems（ally kit 派生域）、text（fontdefs/TTF 全域项）。卡不变域无 orphan 语义
（没有卡归属可消失），其余四态照判；`revalidate --exact` 按域重推导：
art/watermark 走来源包解码，kit/gems 走 kit 重提取，text 走字体重提取。
gems 的 source 无 bundle 地址（bundle=None）时 cheap 面保守判 revalidate
（不冒充 missing），由 exact 用 ally kit 重提取裁决。docs/architecture.md §2.3
同口径。

五态语义（必须保留 #4；revalidate≠不能用）：
- reused      槽位在新代有同内容 item（content sha 相等）→ 直接可用
- revalidate  新代无此槽位 item，且来源 guid 仍在 catalog、来源包在（sha 变了
              或 sha 未记账）→ 未确认（可能还能用，待 --exact 重读）
- stale       槽位两侧都有但 content sha/codec 不同，或 exact 重读证实内容变了
              → 确定不能用（按新内容重建）
- missing     新代无此槽位 item 且来源包/guid 已消失 → 确定不能用
- orphan      卡在新代 cards 里没了 → 不再被使用

cheap 判定面 = bundle sha（对表，stat 快路语义）+ guid 存在性（catalog 查表），
不开任何游戏包；exact 才开包重读对象比 content sha（P1 content sha=解码像素 sha）。
报告落 to 代 migration_report（game_id=from 代），kind ∈ item/bundle。

P3 件1 exact 闭环：revalidate 槽位逐项重读 → reused/stale 终态转移（重读失败/
无来源=保持 revalidate 且 reason 记因——闭环禁静默丢槽位）；reused 槽位 item 面
复制进 to 代（设计 §7.1「reused=直接复制 item 行；blob 复用」——闭环不止记账，
槽位变可用；_apply_exact_transitions/_carryover_reused，离线单测覆盖转移语义）。

Exercise：无真实版本升级事件时的五态机器演练——合成 from/to 代副本注入差异
（内容 sha 变→stale、to 缺 item+包 sha 变→revalidate、guid 删→missing、卡删→
orphan、其余→reused），走真 diff 分类器 + 真 exact 重读 + reused 面 warm 命中
复验（SupplyIndex(gen=) 演练绑代），演练完焚副本（DB+sidecar+残目录）。
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.paths import SupplyLayout


def _gen_db_path(layout: SupplyLayout, gen: str) -> Path:
    gid = gen[4:] if gen.startswith("gen-") else gen
    p = layout.gen_db(gid)
    if not p.is_file():
        raise FileNotFoundError(f"代库不存在：{p}")
    return p


def resolve_gens(layout: SupplyLayout, from_gen: str | None,
                 to_gen: str | None) -> tuple[str, str]:
    """默认 to=current（current.json），from=磁盘上另一个代（唯一才自动，多代点名）。"""
    cur = layout.read_current()
    if to_gen is None:
        if cur is None:
            raise FileNotFoundError("无 current.json，--to 需显式给代名")
        to_gen = cur["generation"]
    if from_gen is None:
        others = sorted(p.name for p in layout.gens_dir.glob("gen-*")
                        if p.is_dir() and p.name != to_gen
                        and not p.name.startswith("gen-synth"))
        if len(others) == 1:
            from_gen = others[0]
        elif not others:
            raise FileNotFoundError(
                "无另一代可 diff（首次建库无版本升级事件）——五态语义演练见 "
                "cli diff --synthetic（合成代副本注入差异）")
        else:
            raise KeyError(f"磁盘上有多个其它代 {others[:4]}…，--from 需显式指定")
    return from_gen, to_gen


def _content_sha(domain: str, item: str, content: dict) -> str:
    """item 的内容身份（跨代五态比较面）：各域取 content_inputs 的产物 sha。"""
    if domain == "art":
        if item == S.ITEM_PORTRAIT_MIP:
            # A5：链项=portrait（L0 派生源）+ chain（存储级数组）+ meta（采样
            # 语义）三段联合身份——任一变化=槽位内容变
            c = content or {}
            return "|".join([c.get("portrait", ""), c.get("chain", ""),
                             c.get("meta", "")])
        return (content or {}).get("portrait", "")
    if domain == S.DOMAIN_WATERMARK:
        return (content or {}).get("watermark", "")
    if domain == S.DOMAIN_FRAMES:
        if item == S.ITEM_KIT_LIGHT:
            # A6：kit_light=轻走查 kit（同 kit 六面聚合 sha 键面）
            return (content or {}).get("kit", "")
        if item != S.ITEM_KIT:
            # A6：supp 域（ability/badges/btf/ornaments/ta/material_state/
            # portrait_uv1）=parts 内容聚合 sha
            return (content or {}).get("supp", "")
        return (content or {}).get("kit", "")
    if domain == S.DOMAIN_GEMS:
        return (content or {}).get("pixel", "")
    if domain == S.DOMAIN_TEXT:
        if item == S.ITEM_FONTDEFS:
            return (content or {}).get("fontdefs", "")
        if item == S.ITEM_FONT_ASSET_PARAMS:
            return (content or {}).get("supp", "")
        return (content or {}).get("ttf", "")
    if domain == S.DOMAIN_COLOR:
        if item == S.ITEM_COLOR_PROBE:
            return (content or {}).get("probe", "")
        return (content or {}).get("pixel", "")
    if domain == S.DOMAIN_TEXTURES:
        # A5：mip_registry 全局项（链数组聚合 sha）
        return (content or {}).get("chains", "")
    return ""


def _slots(conn: sqlite3.Connection) -> dict[tuple[str, ...], dict]:
    """items → 语义槽位（**全供给域**；Phase 5 审计 P2 起不再 art-only）。

    槽位身份=（domain, subject, locale）：
    - art：subject=``<card_id>|<kind>``（per-card per-kind；portrait/golden）；
    - watermark：subject=``<card_id>|watermark``（per-card；R2 起同权供给项）；
    - frames：subject=``frame:<frame>``（卡不变域，无 card 归属）；
    - gems：subject=``gem:<gem>``（ally kit 派生的卡不变域）；
    - text：subject=``text:<item>:<font|fontdefs>``（全域项，无 card 归属）；
    - color：subject=``color:probe`` / ``atlas:<family>[<ct>]``（A4 域级项，无
      card 归属——probe 的 per-card 挂接不落本轴，槽位=item 本体）；
    - textures：subject=``textures:<item>``（A5 mip_registry 全局项，无 card
      归属）。
    migration_report 的 key 保持 art 旧格式 ``card|kind|locale``（兼容既有账/
    集成断言），其余域用稳定前缀串（卡 ID 不会含冒号，构造性不撞键）。
    """
    out: dict[tuple[str, ...], dict] = {}
    for r in conn.execute(
            "SELECT item_key, domain, item, params_json, content_inputs_json, "
            "source_json, codec, codec_version, manifest_json FROM items"):
        domain = r["domain"]
        params = json.loads(r["params_json"])
        manifest = json.loads(r["manifest_json"])
        content = json.loads(r["content_inputs_json"])
        item = r["item"]
        if domain == "art":
            card_id, kind = params["card_id"], params["kind"]
            subject = f"{card_id}|{kind}"
            locale = manifest.get("locale", "")
            skey = f"{card_id}|{kind}|{locale}"
            card_scope = card_id
        elif domain == S.DOMAIN_WATERMARK:
            card_id = params["card_id"]
            subject = f"{card_id}|watermark"
            locale = manifest.get("locale", "")
            skey = f"{card_id}|watermark|{locale}"
            card_scope = card_id
        elif domain == S.DOMAIN_FRAMES:
            frame = params.get("frame")
            if item == S.ITEM_KIT:
                subject = f"frame:{frame}"
            elif item == S.ITEM_KIT_LIGHT:
                # A6：kit_light（轻走查 kit——独立 item 名，槽位前缀区分）
                subject = f"frame_light:{frame}"
            else:
                # A6：supp 域（ability_kit params={quality} 等）
                subject = f"frames:{item}:" + json.dumps(params, sort_keys=True)
            locale = manifest.get("locale", "")
            skey = subject
            card_scope = None
        elif domain == S.DOMAIN_GEMS:
            gem = item
            subject = f"gem:{gem}"
            locale = manifest.get("locale", "")
            skey = subject
            card_scope = None
        elif domain == S.DOMAIN_TEXT:
            sub = params.get("font") or item
            subject = f"text:{item}:{sub}"
            locale = manifest.get("locale", "")
            skey = subject
            card_scope = None
        elif domain == S.DOMAIN_COLOR:
            if item == S.ITEM_COLOR_PROBE:
                subject = "color:probe"
            else:
                subject = f"atlas:{params['family']}[{params['ct']}]"
            locale = manifest.get("locale", "")
            skey = subject
            card_scope = None
        elif domain == S.DOMAIN_TEXTURES:
            # A5：mip_registry 全局项（卡不变域级——probe/atlas 同款记账）
            subject = f"textures:{item}"
            locale = manifest.get("locale", "")
            skey = subject
            card_scope = None
        else:
            continue
        out[(domain, subject, locale)] = {
            "item_key": r["item_key"], "domain": domain, "item": item,
            "params": params, "content": content,
            "content_sha": _content_sha(domain, item, content),
            "source": json.loads(r["source_json"]),
            "codec": r["codec"], "codec_version": r["codec_version"],
            "manifest": manifest, "skey": skey, "card_scope": card_scope,
            "locale": locale,
        }
    return out


def diff(cache_root: Path | str, *, from_gen: str | None = None,
         to_gen: str | None = None) -> dict:
    """cheap diff：item 五态 + bundle 三态，报告写 to 代 migration_report。"""
    layout = SupplyLayout(cache_root)
    from_gen, to_gen = resolve_gens(layout, from_gen, to_gen)
    from_db = _gen_db_path(layout, from_gen)
    to_db = _gen_db_path(layout, to_gen)
    fconn = S.connect(from_db, readonly=True)
    tconn_ro = S.connect(to_db, readonly=True)

    f_slots = _slots(fconn)
    t_slots = _slots(tconn_ro)
    t_cards = {r["card_id"] for r in tconn_ro.execute("SELECT card_id FROM cards")}
    t_catalog = {r["guid"] for r in tconn_ro.execute("SELECT guid FROM asset_catalog")}
    t_bundles = {r["name"]: r["sha256"] for r in tconn_ro.execute(
        "SELECT name,sha256 FROM bundles")}

    rows = []           # (game_id, kind, key, status, reason, detail)
    counts = {"reused": 0, "revalidate": 0, "stale": 0, "missing": 0, "orphan": 0}
    from_game_id = fconn.execute(
        "SELECT value FROM meta WHERE key='game_id'").fetchone()["value"]

    for slot, fitem in sorted(f_slots.items(), key=lambda kv: kv[1]["skey"]):
        skey = fitem["skey"]
        card_id = fitem["card_scope"]
        # orphan 只对 per-card 域有语义（卡在新代没了=不再被使用）；卡不变域
        # （frames/gems/text）没有卡归属，代际迁移面只有 reused/revalidate/
        # stale/missing 四态。
        if card_id is not None and card_id not in t_cards:
            counts["orphan"] += 1
            rows.append((from_game_id, "item", skey, "orphan",
                         "card-absent-in-to-gen", None))
            continue
        titem = t_slots.get(slot)
        if titem is not None:
            fc = fitem["content_sha"]
            tc = titem["content_sha"]
            if fitem["codec"] != titem["codec"] or (
                    fitem["codec_version"] != titem["codec_version"]):
                counts["stale"] += 1
                rows.append((from_game_id, "item", skey, "stale",
                             "codec-changed", None))
            elif fc and fc == tc:
                counts["reused"] += 1
                rows.append((from_game_id, "item", skey, "reused",
                             "content-sha-equal", None))
            else:
                counts["stale"] += 1
                rows.append((from_game_id, "item", skey, "stale",
                             "object-content-changed", None))
            continue
        # to 代无此槽位 item：按来源包/guid 存在性判（revalidate=未确认，非不能用）。
        # 卡不变域（gems）的 source 可能没有 bundle 地址（bundle=None）——无可
        # 核对地址时保守判 revalidate（不可声称 missing），由 exact 重推导裁决。
        src = [s for s in (fitem["source"] or []) if s.get("bundle")]
        if not src:
            counts["revalidate"] += 1
            rows.append((from_game_id, "item", skey, "revalidate",
                         "item-absent-in-to-gen-no-source", None))
            continue
        gone = [s for s in src
                if s.get("bundle") not in t_bundles
                or (s.get("guid") or "").lower() not in t_catalog]
        changed = [s for s in src if s.get("bundle") in t_bundles
                   and s.get("bundle_sha256") and t_bundles[s["bundle"]] != s.get("bundle_sha256", "")]
        if gone:
            counts["missing"] += 1
            rows.append((from_game_id, "item", skey, "missing",
                         "source-bundle-or-guid-gone",
                         json.dumps({"sources": [
                             {"bundle": g.get("bundle"), "guid": g.get("guid")}
                             for g in gone[:3]]})))
        else:
            counts["revalidate"] += 1
            rows.append((from_game_id, "item", skey, "revalidate",
                         "source-bundle-sha-changed" if changed else
                         "item-absent-in-to-gen-unconfirmed",
                         json.dumps({"changed_bundles":
                                     [c["bundle"] for c in changed[:3]]}) if changed else None))

    # bundle 三态（cheap 面：sha 对表；真文件存在性=stat，此处对表口径）
    for r in fconn.execute("SELECT name,sha256 FROM bundles"):
        name, fsha = r["name"], r["sha256"]
        tsha = t_bundles.get(name)
        if tsha is None:
            status, reason = "missing", "bundle-absent-in-to-gen"
        elif not fsha or not tsha:
            status, reason = "revalidate", "sha-unrecorded"
        elif fsha == tsha:
            status, reason = "reused", "sha-equal"
        else:
            status, reason = "revalidate", "sha-changed"
        rows.append((from_game_id, "bundle", name, status, reason, None))
    fconn.close()
    tconn_ro.close()

    # 报告写 to 代（migration_report；短写不扰 warm 只读句柄）
    tconn = S.connect(to_db)
    tconn.execute("BEGIN")
    tconn.execute("DELETE FROM migration_report WHERE game_id=?", (from_game_id,))
    tconn.executemany(
        "INSERT OR REPLACE INTO migration_report(game_id,kind,key,status,reason,"
        "detail_json) VALUES(?,?,?,?,?,?)", rows)
    tconn.commit()
    tconn.close()

    samples = {k: [] for k in counts}
    for row in rows:
        if row[1] == "item" and row[3] in samples and len(samples[row[3]]) < 5:
            samples[row[3]].append({"key": row[2], "reason": row[4]})
    return {"from": from_gen, "to": to_gen, "counts": counts,
            "rows": len(rows), "samples": samples}


# ---------------------------------------------------------------------------
# revalidate --exact（按需重读；cold 面——允许 UnityPy）
# ---------------------------------------------------------------------------

def _apply_exact_transitions(fconn: sqlite3.Connection, wconn: sqlite3.Connection,
                             targets: list[dict], got: dict, got_err: dict,
                             *, carry: bool = True) -> dict:
    """exact 转移记账核心（离线可测；fconn=from 代只读、wconn=to 代可写）。

    逐槽位终态（migration_report 实账；闭环=每槽位必有终态或显式残留账）：
    - 重读 sha == from 代 content → reused（carry=True 时**复制 item 面进 to 代**
      ——设计 §7.1「reused=直接复制 item 行；blob 复用」，闭环不止记账，槽位变
      可用）；
    - 重读 sha 变 → stale（确定不能用，detail 记重读 sha）；
    - 重读失败 → 保持 revalidate，reason=exact-redecode-failed:<err>（显式残留账，
      禁静默丢槽位）；
    - 无来源可读 → 保持 revalidate，reason=exact-no-source。"""
    updates: list[tuple[str, str, str | None, str]] = []
    reused_targets: list[dict] = []
    counts = {"checked": 0, "reused": 0, "stale": 0, "unresolved": 0}
    for t in targets:
        skey = t.get("skey") or (
            f"{t.get('card_id') or ''}|{t.get('kind') or ''}|{t.get('locale') or ''}")
        counts["checked"] += 1
        new_sha = got.get(skey)
        key2 = (t.get("card_id"), t.get("kind"))
        if new_sha is None and key2 in got:
            # 兼容旧调用面（单测直接注入 (card,kind) 键）
            new_sha = got[key2]
        err = got_err.get(skey)
        if err is None and key2 in got_err:
            err = got_err[key2]
        old_sha = t.get("content_sha")
        if old_sha is None:
            content = t.get("content") or {}
            old_sha = content.get("portrait") or content.get("watermark") or ""
        if new_sha is None:
            counts["unresolved"] += 1
            if err is None:
                # 无解码结果亦无错误（来源 bundle 缺位等）——无来源可读
                updates.append(("revalidate", "exact-no-source", None, skey))
            else:
                updates.append(("revalidate",
                                f"exact-redecode-failed:{err[:120]}",
                                None, skey))
            continue
        if new_sha == old_sha:
            counts["reused"] += 1
            reused_targets.append(t)
            updates.append(("reused", "exact-object-sha-equal", None, skey))
        else:
            counts["stale"] += 1
            updates.append(("stale", "exact-object-sha-differs",
                            json.dumps({"redecoded_sha": new_sha}), skey))
    wconn.executemany(
        "UPDATE migration_report SET status=?, reason=?, detail_json=? "
        "WHERE kind='item' AND key=?",
        updates)
    carried = _carryover_reused(fconn, wconn, reused_targets) if carry \
        else {"slots": 0, "items": 0, "blob_rows": 0, "plan_items": 0}
    wconn.commit()
    return {**counts, "carryover": carried}


def _carryover_reused(fconn: sqlite3.Connection, wconn: sqlite3.Connection,
                      reused_targets: list[dict]) -> dict:
    """reused 槽位 item 面 from→to 复制（设计 §7.1：reused=直接复制 item 行）。

    复制面：items/item_blobs 整行 + blobs 行（OR IGNORE——内容寻址跨代共享，行在
    即跳，blob 文件零复制零重写）+ plan_items 重挂 to 代 plan_key（plan_key 含
    card_data_sha，两代各派；plans 行缺则按角色派生 status 补——_write_decoded
    同规则）。locator 面不复制（to 代 locate 自有账；warm 供图走 blob 内容寻址
    不经 locator）。"""
    n_items = n_blob_rows = n_plan_items = n_slots = 0
    for t in reused_targets:
        fik = t["item_key"]
        irow = fconn.execute(
            "SELECT item_key,domain,item,params_json,codec,codec_version,"
            "manifest_json,status,source_kind,source_json,content_inputs_json,"
            "created_at FROM items WHERE item_key=?", (fik,)).fetchone()
        if irow is None:
            continue          # from 代行消失（异常面；迁移账已有该槽位状态）
        wconn.execute(
            "INSERT OR REPLACE INTO items(item_key,domain,item,params_json,codec,"
            "codec_version,manifest_json,status,source_kind,source_json,"
            "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (irow["item_key"], irow["domain"], irow["item"], irow["params_json"],
             irow["codec"], irow["codec_version"], irow["manifest_json"],
             irow["status"], irow["source_kind"], irow["source_json"],
             irow["content_inputs_json"], irow["created_at"]))
        n_items += 1
        for brow in fconn.execute(
                "SELECT ib.role AS role, b.blob_key AS blob_key, "
                "b.payload_sha256 AS payload_sha256, b.size AS size, "
                "b.codec AS codec, b.codec_version AS codec_version, "
                "b.last_used AS last_used, b.created_at AS created_at "
                "FROM item_blobs ib JOIN blobs b ON b.blob_key=ib.blob_key "
                "WHERE ib.item_key=?", (fik,)):
            wconn.execute(
                "INSERT OR REPLACE INTO item_blobs(item_key,blob_key,role) "
                "VALUES(?,?,?)", (fik, brow["blob_key"], brow["role"]))
            wconn.execute(
                "INSERT OR IGNORE INTO blobs(blob_key,payload_sha256,size,codec,"
                "codec_version,last_used,created_at) VALUES(?,?,?,?,?,?,?)",
                (brow["blob_key"], brow["payload_sha256"], brow["size"],
                 brow["codec"], brow["codec_version"], brow["last_used"],
                 brow["created_at"]))
            n_blob_rows += 1
        crow_roles = fconn.execute(
            "SELECT p.card_id AS card_id, pi.role AS role FROM plans p "
            "JOIN plan_items pi ON pi.plan_key=p.plan_key "
            "WHERE pi.item_key=?", (fik,)).fetchall()
        roles_by_card: dict[str, list[str]] = {}
        for rr in crow_roles:
            roles_by_card.setdefault(rr["card_id"], []).append(rr["role"] or "")
        for card_id, raw_roles in sorted(roles_by_card.items()):
            roles = [r for r in raw_roles if r]
            if not roles:
                continue
            crow = wconn.execute("SELECT data_sha FROM cards WHERE card_id=?",
                                 (card_id,)).fetchone()
            if crow is None:
                continue          # 卡不在 to 代（orphan 面不进 reused——防御）
            pk = S.plan_key(card_id=card_id, locale=t["locale"],
                            card_data_sha=crow["data_sha"] or "")
            wconn.execute(
                "INSERT OR IGNORE INTO plans(plan_key,card_id,options_json,status,"
                "plan_version,card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)",
                (pk, card_id, S.cjson({}),
                 "complete" if any(r == "portrait" for r in roles) else "partial",
                 S.PLAN_VERSION, crow["data_sha"] or "", int(time.time())))
            for role in roles:
                wconn.execute(
                    "INSERT OR REPLACE INTO plan_items(plan_key,item_key,role) "
                    "VALUES(?,?,?)", (pk, fik, role))
                n_plan_items += 1
            # plan status 按 expected-vs-built 重算（P0-1 语义单源——初值仍是
            # portrait 单轴老口径）
            S.recompute_plan_status(wconn, [pk])
        n_slots += 1
    return {"slots": n_slots, "items": n_items, "blob_rows": n_blob_rows,
            "plan_items": n_plan_items}


def _rederive_exact_slots(layout: SupplyLayout, win: Path,
                          targets: list[dict], *, jobs: int) -> tuple[dict, dict]:
    """exact 重推导全供给域（cold 面）：返回 ({skey: content_sha}, {skey: err})。

    - art / watermark：开来源包按 guid 解码（_decode_bundle_worker 同款），比较
      解码像素 sha；
    - frames：整 kit 重提取（_extract_kit_now=build worker 本体），比较
      kit_content_sha；
    - gems：ally kit 重提取一次，取 gem 纹理像素 sha；
    - text：extract_fonts 重提取一次，fontdefs=canonical 内容 sha / ttf=文件 sha。
    逐域失败落 err（不中止其他域）——调用方保持 revalidate 记因。"""
    from eidolon.core.supply_index import cold as cold_mod

    got: dict[str, str] = {}
    got_err: dict[str, str] = {}

    # ---- art / watermark（来源包+guid 解码） ----
    pixel_targets = [t for t in targets
                     if t["domain"] in (S.DOMAIN, S.DOMAIN_WATERMARK)]
    by_bundle: dict[str, list[dict]] = {}
    for t in pixel_targets:
        src0 = t["source"][0] if t["source"] else {}
        guid = src0.get("guid") or ""
        bundle = src0.get("bundle") or ""
        if not guid or not bundle:
            got_err[t["skey"]] = "no-source-guid-or-bundle"
            continue
        by_bundle.setdefault(bundle, []).append(
            {"card_id": t["card_id"], "kind": t["kind"], "guid": guid,
             "skey": t["skey"]})
    payload = [(str(win), b, ts) for b, ts in sorted(by_bundle.items())]
    if payload:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=max(1, jobs)) as ex:
            for bundle, res, _c, _o, _w in ex.map(
                    cold_mod._decode_bundle_worker, payload, chunksize=1):
                for r in res:
                    # 回填 skey：worker 只认识 (card_id,kind)；按任务表反查
                    skey = next((ts["skey"] for ts in
                                 by_bundle.get(bundle, [])
                                 if ts["card_id"] == r["card_id"]
                                 and ts["kind"] == r["kind"]), None)
                    if skey is None:
                        continue
                    if r.get("ok"):
                        got[skey] = r["pixel_sha"]
                    else:
                        got_err[skey] = r.get("error") or "unknown"

    # ---- frames（卡不变域） ----
    frame_targets = [t for t in targets if t["domain"] == S.DOMAIN_FRAMES]
    if frame_targets:
        from eidolon.core.supply_index.kit_extract import (
            FRAME_SPECS_KIT,
            _extract_kit_now,
        )

        deps = cold_mod.read_bundle_deps(win)
        for t in frame_targets:
            m = t["manifest"]
            try:
                out = _extract_kit_now(
                    win, frame=m["frame"], spec=FRAME_SPECS_KIT[m["frame"]],
                    actor_ref=m["prefab_ref"], guid=m["guid"],
                    bundle=m["bundle"], card_id=m.get("card_id"),
                    dbf_id=m.get("dbf_id"), bundle_deps=deps,
                    cache_root=layout.root,
                    strings_txt=cold_mod.ctx_strings_path(
                        win, m.get("locale") or "zhcn"))
            except Exception as exc:                     # noqa: BLE001
                got_err[t["skey"]] = f"kit-extract: {type(exc).__name__}: {exc}"
                continue
            if not out.get("ok"):
                got_err[t["skey"]] = f"kit-extract: {out.get('error')}"
            else:
                got[t["skey"]] = out["kit_content_sha"]

    # ---- gems（ally kit 派生域；一次重提取） ----
    gem_targets = [t for t in targets if t["domain"] == S.DOMAIN_GEMS]
    if gem_targets:
        from eidolon.core.supply_index.kit_extract import (
            FRAME_SPECS_KIT,
            _extract_kit_now,
        )

        ally_meta = gem_targets[0].get("ally_meta")
        if ally_meta is None:
            for t in gem_targets:
                got_err[t["skey"]] = "ally-kit-manifest-missing"
        else:
            deps = cold_mod.read_bundle_deps(win)
            out = _extract_kit_now(
                win, frame="ally", spec=FRAME_SPECS_KIT["ally"],
                actor_ref=ally_meta["prefab_ref"], guid=ally_meta["guid"],
                bundle=ally_meta["bundle"], card_id=ally_meta.get("card_id"),
                dbf_id=ally_meta.get("dbf_id"), bundle_deps=deps,
                cache_root=layout.root,
                strings_txt=cold_mod.ctx_strings_path(
                    win, ally_meta.get("locale") or "zhcn"))
            if not out.get("ok"):
                for t in gem_targets:
                    got_err[t["skey"]] = f"ally-kit-extract: {out.get('error')}"
            else:
                gem_acc = out.get("gems") or {}
                for t in gem_targets:
                    acc = gem_acc.get(t["item"])
                    if acc is None:
                        got_err[t["skey"]] = "gem-not-found-in-ally-kit"
                    else:
                        got[t["skey"]] = acc["pixel_sha256"]

    # ---- text（全域项；一次重提取） ----
    text_targets = [t for t in targets if t["domain"] == S.DOMAIN_TEXT]
    if text_targets:
        from eidolon.core.supply_index import text_codec as TC
        from eidolon.core.supply_index.text_extract import extract_fonts

        loc = text_targets[0]["locale"] or "zhcn"
        tables = cold_mod.read_manifest_tables(win, loc)
        zhcat = {base: (guid, bundle) for base, _layer, locale, guid, bundle
                 in tables["variant_rows"] if locale == "zhcn"}
        fonts = extract_fonts(win, catalog=tables["catalog"], zhcat=zhcat,
                              bundle_deps=tables["bundle_deps"])
        for t in text_targets:
            if t["item"] == S.ITEM_FONTDEFS:
                got[t["skey"]] = TC.fontdefs_content_sha(fonts["fontdefs"])
            else:
                font = t["params"].get("font") or ""
                raw = fonts["ttfs"].get(font)
                if raw is None:
                    got_err[t["skey"]] = f"ttf-not-found: {font}"
                else:
                    got[t["skey"]] = TC.ttf_content_sha(raw)
    return got, got_err


def revalidate_exact(cache_root: Path | str, *, from_gen: str | None = None,
                     to_gen: str | None = None, limit: int | None = None,
                     game: Path, locale: str,
                     jobs: int = 2, carry: bool = True) -> dict:
    """exact 闭环：revalidate 槽位逐项开包重读 → reused/stale 终态转移 + 残留账。

    报告（migration_report）在 to 代；content 基准=from 代 item 行。exact 开游戏包
    （cold 面），与 build 共用 decode worker。重读失败/无来源的槽位保持 revalidate
    且 reason 记失败因（闭环禁静默丢槽位）；reused 槽位 item 面复制进 to 代
    （_apply_exact_transitions / _carryover_reused）。limit=N 只处理前 N 槽位，
    remaining=未处理残留账。game/locale 必填（exact 开游戏包=显式身份）。"""
    layout = SupplyLayout(cache_root)
    from_gen, to_gen = resolve_gens(layout, from_gen, to_gen)
    to_db = _gen_db_path(layout, to_gen)
    from_db = _gen_db_path(layout, from_gen)

    tconn = S.connect(to_db, readonly=True)
    # 全库 revalidate 总量（P1-9 返工 R1：remaining=全库未处理数——limit 前先
    # COUNT，limit 只截取本批处理面，不吞掉余量账）
    total_revalidate = int(tconn.execute(
        "SELECT COUNT(*) FROM migration_report WHERE kind='item' "
        "AND status='revalidate'").fetchone()[0])
    rkeys = [r["key"] for r in tconn.execute(
        "SELECT key FROM migration_report WHERE kind='item' AND status='revalidate' "
        "ORDER BY key" + (f" LIMIT {int(limit)}" if limit else ""))]
    tconn.close()
    fconn = S.connect(from_db, readonly=True)
    slots = _slots(fconn)
    slots_by_key = {info["skey"]: info for info in slots.values()}

    targets = []
    no_source = 0
    for key in rkeys:
        item = slots_by_key.get(key)
        if not item:
            no_source += 1     # from 代槽位已不在（迁移账陈旧）——残留账面
            continue
        if not item["source"] and item["domain"] != S.DOMAIN_GEMS:
            no_source += 1
            continue
        targets.append({
            "skey": key, "card_id": item["card_scope"],
            "kind": (item["params"].get("kind")
                     if item["domain"] == S.DOMAIN else
                     "watermark" if item["domain"] == S.DOMAIN_WATERMARK else
                     "kit" if item["domain"] == S.DOMAIN_FRAMES else
                     "gem" if item["domain"] == S.DOMAIN_GEMS else "text"),
            "locale": item["locale"], "item_key": item["item_key"],
            "domain": item["domain"], "item": item["item"],
            "params": item["params"], "manifest": item["manifest"],
            "source": item["source"], "content": item["content"],
            "content_sha": item["content_sha"]})
    # gems exact 需要 ally kit manifest（gems item 的 source 只有 note，无可解码
    # 地址；重提取源=ally kit item，与 integrity.repair 的 gems 归一同一判据）
    gem_targets = [t for t in targets if t["domain"] == S.DOMAIN_GEMS]
    if gem_targets:
        ally = fconn.execute(
            "SELECT manifest_json FROM items WHERE domain=? AND item=? "
            "AND params_json=?", (S.DOMAIN_FRAMES, S.ITEM_KIT,
                                  S.cjson({"frame": "ally"}))).fetchone()
        ally_meta = json.loads(ally["manifest_json"]) if ally else None
        for t in gem_targets:
            t["ally_meta"] = ally_meta
    if not targets:
        fconn.close()
        return {"from": from_gen, "to": to_gen, "checked": 0, "reused": 0,
                "stale": 0, "unresolved": no_source,
                "remaining": max(0, total_revalidate - no_source),
                "total_revalidate": total_revalidate,
                "carryover": {"slots": 0, "items": 0, "blob_rows": 0,
                              "plan_items": 0},
                "note": "无 revalidate 槽位"}

    from eidolon.core.infra import context
    from eidolon.core.infra.game_install import resolve_context
    from eidolon.contracts import GameRequest

    ctx = resolve_context(GameRequest(Path(game), "--game"),
                          cache_root=Path(cache_root), locale=locale or "zhcn")
    context.install(ctx)            # 同身份幂等；异身份 raise（进程单渲染身份）
    win = ctx.data_win
    got, got_err = _rederive_exact_slots(layout, win, targets, jobs=jobs)

    wconn = S.connect(to_db)
    try:
        account = _apply_exact_transitions(fconn, wconn, targets, got, got_err,
                                           carry=carry)
    finally:
        fconn.close()
        wconn.close()
    # remaining=全库未处理数（P1-9）：本轮终态转移的槽位（reused/stale）出队，
    # 其余（含 unresolved/no_source 的残留账）仍在 revalidate 态。
    remaining = max(0, total_revalidate
                    - account["reused"] - account["stale"])
    return {"from": from_gen, "to": to_gen, **account,
            "no_source": no_source, "total_revalidate": total_revalidate,
            "remaining": remaining}


# ---------------------------------------------------------------------------
# 五态机器演练（合成代副本；不碰真代）
# ---------------------------------------------------------------------------

def _exercise_mismatches(injected: dict, diff_counts: dict, exact: dict,
                         warm_check: dict | None) -> list[str]:
    """五态演练自校验（纯函数；注入账 vs 结果账逐项比对）。

    注入账固定为 stale=2 / revalidate=3 / missing=2 / orphan=1（five_state 的
    构造），任一结果账偏离→返回逐项 mismatch 文案；空 list=演练面有效。
    单测直接注入错误账即可钉住（不依赖真机/真代）。"""
    mismatches = []
    for state, want_n in injected.items():
        got_n = diff_counts.get(state)
        if got_n != want_n:
            mismatches.append(f"{state}: injected={want_n} diff={got_n}")
    if exact["checked"] != injected.get("revalidate", 0):
        mismatches.append(
            f"exact.checked={exact['checked']} ≠ injected revalidate="
            f"{injected.get('revalidate', 0)}")
    want_transferred = injected.get("revalidate", 0)
    got_transferred = exact["reused"] + exact["stale"]
    if got_transferred != want_transferred:
        mismatches.append(
            f"exact 终态 transferred={got_transferred} ≠ "
            f"injected revalidate={want_transferred}")
    if isinstance(warm_check, dict) and "error" not in warm_check \
            and warm_check.get("hit") != want_transferred:
        mismatches.append(
            f"warm 闭环 hit={warm_check.get('hit')} ≠ injected revalidate="
            f"{want_transferred}")
    return mismatches


def five_state_exercise(cache_root: Path | str, *, game: Path,
                        locale: str) -> dict:
    """合成 from/to 代副本注入差异 → 真 diff 分类 + 真 exact 重读 → 焚副本。

    注入面（真实代码路径零改动）：
    - stale    ×2：from item content_inputs.portrait sha 篡改
    - revalidate ×3：to 删 item，且 to bundles 表该来源包 sha 篡改
    - missing  ×2：to 删 item + to catalog 删来源 guid
    - orphan   ×1：to 删该卡
    - reused   其余全部（内容相等直通）"""
    layout = SupplyLayout(cache_root)
    cur = layout.read_current()
    assert cur, "无 current.json"
    src = layout.gen_db(cur["game_id"])

    def copy_gen(tag: str) -> tuple[str, Path]:
        gid = f"synth{tag}{secrets.token_hex(3)}"
        dst = layout.gen_db(gid)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        conn = S.connect(dst)
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('game_id',?)",
                     (gid,))
        conn.commit()
        conn.close()
        return f"gen-{gid}", dst

    from_gen, from_db = copy_gen("from")
    to_gen, to_db = copy_gen("to")

    fc = S.connect(from_db)
    # 演练注入面=art 槽位（per-card per-kind；content sha 篡改/卡删/orphan 语义
    # 只对 art 可构造）。全供给域分类器由单测 test_diff_all_domains 覆盖。
    fitems = {k: v for k, v in _slots(fc).items() if v["domain"] == "art"}
    if len(fitems) < 8:
        fc.close()
        _burn(from_db)
        _burn(to_db)
        raise RuntimeError(
            f"五态演练需 ≥8 个 item（现 {len(fitems)}）——先定向 build 补样本再演练")
    # 注入 1：2 个 item 内容 sha 篡改（→stale）
    stale_keys = [k for k in list(fitems)[:2]]
    for k in stale_keys:
        c = dict(fitems[k]["content"])
        c["portrait"] = "f" * 64
        fc.execute("UPDATE items SET content_inputs_json=? WHERE item_key=?",
                   (S.cjson(c), fitems[k]["item_key"]))
    fc.commit()
    fc.close()

    tc = S.connect(to_db)
    # 注入 2：6 个槽位 to 侧删 item（revalidate×3 / missing×2 / orphan×1）
    victim_slots = [k for k in list(fitems)[2:8]]
    for k in victim_slots:
        tc.execute("DELETE FROM item_blobs WHERE item_key=?",
                   (fitems[k]["item_key"],))
        tc.execute("DELETE FROM items WHERE item_key=?", (fitems[k]["item_key"],))
        tc.execute("DELETE FROM plan_items WHERE item_key=?",
                   (fitems[k]["item_key"],))
    # revalidate 组：来源包 sha 在 to bundles 篡改
    for k in victim_slots[:3]:
        for s in (fitems[k]["source"] or [])[:1]:
            tc.execute("UPDATE bundles SET sha256=? WHERE name=?",
                       ("0" * 64, s["bundle"]))
    # missing 组：来源 guid 在 to catalog 删
    for k in victim_slots[3:5]:
        for s in (fitems[k]["source"] or [])[:1]:
            tc.execute("DELETE FROM asset_catalog WHERE guid=?", (s["guid"],))
    # orphan 组：卡删
    tc.execute("DELETE FROM cards WHERE card_id=?", (victim_slots[5][0],))
    tc.commit()
    tc.close()

    try:
        rep = diff(cache_root, from_gen=from_gen, to_gen=to_gen)
        exact = revalidate_exact(cache_root, from_gen=from_gen, to_gen=to_gen,
                                 game=game, locale=locale)
        # 闭环复验（P3 件1）：reused 槽位 item 面已复制进 to 代——warm（绑 to 代）
        # 应命中并出图（blob 共享面零复制）。
        warm_check = None
        reval_cards = [k[0] for k in victim_slots[:3]]
        try:
            from eidolon.core.supply_index.warm import SupplyIndex

            with SupplyIndex(cache_root, gen=to_gen) as idx:
                chk = idx.check(reval_cards)
                warm_check = {"cards": reval_cards, "hit": chk["hit"],
                              "miss": chk["miss"]}
        except Exception as exc:  # noqa: BLE001  演练面复验失败如实记账（不掩盖）
            warm_check = {"cards": reval_cards, "error": str(exc)[:200]}
    finally:
        for p in (from_db, to_db):
            _burn(p)
    # 自校验（P1-12 返工 R1）：注入的 stale/revalidate/missing/orphan 计数必须与
    # diff/exact/warm 结果账一致——不一致=演练面失效（分类器或转移语义漂移），
    # 响亮 raise（CLI 同步 exit 非 0），禁静默绿。
    injected_counts = {"stale": len(stale_keys),
                       "revalidate": len(victim_slots[:3]),
                       "missing": len(victim_slots[3:5]),
                       "orphan": len(victim_slots[5:])}
    mismatches = _exercise_mismatches(injected_counts, rep["counts"], exact,
                                      warm_check)
    if mismatches:
        raise RuntimeError(
            "五态演练自校验失败（注入账 vs 结果账不一致——演练面失效响亮）："
            + "; ".join(mismatches))
    return {"exercise": "five-state (synthetic pair; copies burned after)",
            "diff": {"from": from_gen, "to": to_gen, "counts": rep["counts"]},
            "exact": exact, "warm_closure_check": warm_check,
            "injected": {"stale": [f"{k[0]}|{k[1]}" for k in stale_keys],
                         "revalidate": [f"{k[0]}|{k[1]}" for k in victim_slots[:3]],
                         "missing": [f"{k[0]}|{k[1]}" for k in victim_slots[3:5]],
                         "orphan": [f"{k[0]}|{k[1]}" for k in victim_slots[5:]]}}


def _burn(gen_db: Path) -> None:
    """焚副本代（DB+WAL/SHM sidecar+残目录）。

    P3 实坑：旧形只 unlink 主 DB——WAL 模式写连接留下的 -shm/-wal sidecar 与
    空目录残留（真实缓存 gens/ 下 gen-synthfrom*/gen-synthto* 四个残目录判例）；
    残留面由 maintain 列代收口，本函数源头不再产残。"""
    for suffix in ("", "-wal", "-shm", "-journal", ".health.json"):
        try:
            Path(str(gen_db) + suffix).unlink()
        except OSError:
            pass
    try:
        gen_db.parent.rmdir()
    except OSError:
        pass
