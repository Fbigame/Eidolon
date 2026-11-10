"""integration_supply_index — Phase 5 supply_index 冷暖闭环集成（真实游戏；显式跑）。

覆盖（P5-2b 任务卡四用例 + Phase 5 返工 R1 增两用例；真实游戏 + tmp 缓存根，
全冷面走子进程）：
  1. cold→warm 逐字节：tmp cache_root 子进程 ``build --cards``（partial-init，
     P5-1 冒烟同款 2 卡 + AT_001 golden 载卡）→ ``verify`` CLI（cold 现算 payload/pixel sha 对照 +
     gate 像素级全查）exit 0 且 ``partial: true`` 显式标注；进程内
     ``SupplyIndex``（零 UnityPy 面）assemble_portrait 复验账面 pixel sha；
     **golden 端到端**（R1）：expected 含 portrait_golden 的卡 assemble_card
     出 golden 图（expected-vs-built 零缺项）。
  2. warm 隔离机器证明：``audit`` CLI——不存在 --game + import blocker
     （UnityPy 禁入）+ open 拦截（游戏文件族 *.unity3d / globalgamemanagers* /
     resources.assets* / *.dll 全禁）同窗全卡 API 走查 pass（partial 代
     allow_partial 形态 + 报告 partial 标注；completeness_gate 过）；
     **R2 缺席归因**：走查按 account_for_cards 分道（ok 卡严格装配、absent
     两类跳过计账、gap 走查尾不 raise——partial 代 scope 外可缺），报告
     absent/gap 单列计数 + 账面自洽断言。
  2b. verify gate 缺席归因（R2）：gate 卡集含无期望卡 + 期望缺口卡各一 →
     gate_pixel_checks 拆分 not_built_absent / not_built_gap 两态计数
     （partial 代不作 not_built 门禁）。
  3. 五态 cheap diff（同代 from==to）：CLI exit 0；migration_report 分轴断言
     item 轴全 reused（bundle 轴 partial-init sha 记空串 → sha-unrecorded→
     revalidate 是设计账——``cold._build_partial_init`` 头注明载）。
  4. 响亮负例：篡改 blob 字节 → 进程内 assemble_portrait
     SupplyBlobCorruptError + warm CLI exit 1（stderr blob sha 不匹配；
     finally 还原后复验全绿）；未 build 卡 → check miss 账 +
     assemble_portrait SupplyMissingError + warm CLI exit 1（WARM MISS）。
  5. targeted (card,kind) 补建（R1）：删一卡 golden 面（有 portrait 缺 golden
     形态）→ ``build --cards <该卡>`` DB 驱动定向补齐 golden（(card,kind) 粒度
     幂等不再跳过）→ plan complete + warm assemble_card 出 golden；meta counts
     全量重算断言。
  6. 身份门负例（R1）：伪造 current.json 指向异 game_id（最小假代库使 has_gen
     成立）→ targeted build 响亮拒绝（exit 1 + 身份已换代判据）且不写库
     （current.json 复原断言）。
  7. targeted 完整性门负例（Phase 5 审计 P2）：tmp 副本把 portrait locator 的
     bundle 置坏 + 删对应 item → ``build --cards`` exit 1 且 stderr 点名
     「targeted build 完整性门 / scope 缺项」；共享 cache 不污染。
  8. integrity --repair（P2）：tmp 副本篡改 art blob → ``integrity --repair``
     定点重推导 → rescan 0 bad；共享 cache 的原 blob 不变。
  9. audit --auto 默认 scratch（P2）：真实 partial-init→冷补→复验→不可补仍
     fail loud，pass=True；默认系统临时 scratch 用完即焚（不传 --auto-scratch）。

默认 discover（pattern ``test*.py``）**不收集**本文件；显式跑（需游戏 + UnityPy）：
    EIDOLON_TEST_GAME=<游戏根> python -m unittest \\
        tests.integration.integration_supply_index -v

进程身份纪律：本文件测试进程**不 install GameContext**（identity 六元组含
cache_root，跨文件全量跑会撞进程单渲染身份不变量）——build/verify/audit/diff
全部经 ``python -m eidolon.core.supply_index`` 子进程（自带身份进程），测试进程
只碰 warm 只读面（SupplyIndex/SupplyLayout，零 UnityPy——audit 机器证明同面）。

缓存根：per-run ``tempfile.TemporaryDirectory``（tearDownClass 清理）——build 为
partial-init 定向 3 卡（P5-1 冒烟 2 卡 ~66s；+AT_001 同量级），整文件预算 <5 min（各段超时上限
见常量；超时=error 带日志尾）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from eidolon.core.supply_index import kit_codec as KC
from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.paths import SupplyLayout
from eidolon.core.supply_index.warm import (
    SupplyBlobCorruptError,
    SupplyIndex,
    SupplyMissingError,
)

_REPO = Path(__file__).resolve().parents[2]
_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None

CARDS = ["LETL_316_03", "BRMA06_2H", "AT_001"]   # P5-1 冒烟同款 2 卡 + AT_001
#（portrait+portrait_golden 双 locator——golden 端到端/定向补建用例的期望载卡；
#  前两张实测只有 portrait locator，无 golden 期望）
BUILD_TIMEOUT_S = 240.0                   # P5-1 冒烟 partial-init 实测 ~66s
VERIFY_TIMEOUT_S = 180.0                  # verify（--no-kits）：pixel+payload+三段
AUDIT_TIMEOUT_S = 300.0                   # 全卡装配（cards 表全集，共享域 LRU）
QUICK_TIMEOUT_S = 60.0                    # warm/diff（秒级面）


def _supply_cli(*args: str, timeout: float) -> subprocess.CompletedProcess:
    """``python -m eidolon.core.supply_index <args>``（cwd=repo；显式参数面）。"""
    return subprocess.run(
        [sys.executable, "-m", "eidolon.core.supply_index", *args],
        capture_output=True, text=True, cwd=str(_REPO), timeout=timeout)


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class SupplyIndexColdWarmIntegration(unittest.TestCase):
    """supply_index 冷建→暖供闭环（build 一次；四用例共享）。"""

    @classmethod
    def setUpClass(cls) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="eidolon-supply-int-")
        cls.addClassCleanup(tmp.cleanup)
        cls.cache_root = Path(tmp.name)
        cls.layout = SupplyLayout(cls.cache_root)
        # build 子进程后台跑，stdout/stderr 落日志文件，等待落盘完成
        # （partial-init：全表+全量 locate+定向 3 卡 decode）。
        out_log = cls.cache_root / "build.stdout.log"
        err_log = cls.cache_root / "build.stderr.log"
        argv = ["build", "--game", str(GAME_ROOT), "--cache-root",
                str(cls.cache_root), "--locale", "zhcn", "--cards", *CARDS,
                "--jobs", "2"]
        with out_log.open("w", encoding="utf-8") as fo, \
                err_log.open("w", encoding="utf-8") as fe:
            proc = subprocess.Popen(
                [sys.executable, "-m", "eidolon.core.supply_index", *argv],
                stdout=fo, stderr=fe, cwd=str(_REPO))
            try:
                cls.build_rc = proc.wait(timeout=BUILD_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise AssertionError(
                    f"build 超时（>{BUILD_TIMEOUT_S}s）——日志尾：\n"
                    f"{_tail(err_log)}") from None
        # 日志文件必须落盘（build 响应面留档）
        cls.build_doc: dict | None = None
        if cls.build_rc == 0:
            text = out_log.read_text(encoding="utf-8").strip()
            cls.build_doc = json.loads(text)
        else:
            raise AssertionError(
                f"build exit={cls.build_rc}——stderr 尾：\n{_tail(err_log)}")

    # ---- 用例 1：cold→warm 逐字节 ----

    def test_1_cold_warm_verify_byte_identical(self) -> None:
        self.assertEqual(self.build_doc["mode"], "partial-init",
                         f"build 形态非 partial-init：{self.build_doc}")
        # 定向 decode 面：art 域 item 数=scope 内 (card,kind) locator-ok 期望数
        # （golden 载卡 AT_001 双 kind——旧形「每卡 1 item」口径随 (card,kind)
        # 粒度失效；plans 行数是全卡账，不随 decode scope 收窄）
        conn = S.connect(self.layout.gen_db(self.build_doc["game_id"]),
                         readonly=True)
        try:
            n_art = conn.execute(
                "SELECT COUNT(*) AS n FROM items WHERE domain='art'").fetchone()["n"]
            n_expected = 0
            for cid in CARDS:
                n_expected += conn.execute(
                    "SELECT COUNT(*) FROM locators WHERE subject=? AND "
                    "status='ok' AND kind IN ('portrait','portrait_golden')",
                    (cid,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n_art, n_expected,
                         f"decode 产物≠scope (card,kind) 期望数：{n_art}≠{n_expected}")
        p = _supply_cli(
            "verify", "--game", str(GAME_ROOT), "--cache-root",
            str(self.cache_root), "--locale", "zhcn",
            "--sample", "30", "--golden-sample", "5",
            "--gate-cards", *CARDS, "--no-kits", "--jobs", "2",
            timeout=VERIFY_TIMEOUT_S)
        self.assertEqual(p.returncode, 0,
                         f"verify exit={p.returncode}\n{_stderr_tail(p)}")
        doc = json.loads(p.stdout)
        # payload 级：warm blob sha == cold 现算 PNG sha（全等，零 mismatch）
        self.assertEqual(doc["bad"], 0, str(doc["mismatches"]))
        self.assertEqual(doc["ok"], doc["sample"])
        # partial 代显式标注（R1 P0-2）：full_build=0 → partial true（not_built
        # 不作门禁——本代 gate 卡全建，全绿是另一判据）
        self.assertTrue(doc["partial"])
        self.assertFalse(doc["full_build"])
        # 像素级 gate 全查：两卡全 ok（not_built=0——刚 build 的两卡必在库）
        gp = doc["gate_pixel_checks"]
        self.assertEqual(gp["ok"], len(CARDS), str(gp))
        self.assertEqual(gp["not_built"], 0)
        self.assertEqual(gp["bad"], [])
        # kit 轴 --no-kits 跳过；gems/text/watermark 三段全绿
        self.assertNotIn("kit", doc)
        for section in ("gems", "text", "watermark"):
            self.assertTrue(doc[section]["ok"],
                            f"{section} 段红：{str(doc[section])[:400]}")
        # 进程内 warm 面（零 UnityPy）复验：PIL 解码像素 sha == 账面 pixel sha
        with SupplyIndex(self.cache_root) as idx:
            for cid in CARDS:
                plan = idx.plan(cid)
                self.assertIsNotNone(plan, f"{cid}: 卡不在 cards 表")
                self.assertEqual(plan.missing, [], f"{cid}: plan 缺项")
                m = next(i.manifest for i in plan.items if i.role == "portrait")
                img = idx.assemble_portrait(cid)
                self.assertEqual(S.sha256_hex(img.tobytes()),
                                 m["pixel_sha256"], f"{cid}: warm 像素失配")

    # ---- 用例 1b：golden 端到端（R1 expected-vs-built 零缺项） ----

    def test_1b_golden_end_to_end(self) -> None:
        """build --cards 含 golden 的卡 → warm assemble_card 出 golden。

        golden 是「完整供给」必须项（P0-1）：期望（locator-ok）与产物同账零缺，
        plan complete、assemble_card（严格门）全 role 出货。"""
        with SupplyIndex(self.cache_root) as idx:
            golden_cards = [cid for cid in CARDS
                            if "portrait_golden" in idx.plan(cid).expected]
        self.assertTrue(golden_cards,
                        f"定向卡均无 golden 期望（fixture 失效）：{CARDS}")
        cid = golden_cards[0]
        with SupplyIndex(self.cache_root) as idx:
            plan = idx.plan(cid)
            self.assertEqual(plan.missing, [])
            self.assertEqual(plan.status, "complete")
            bundle = idx.assemble_card(cid)          # 严格门（缺省 allow_partial=False）
            self.assertIn("portrait_golden", bundle)
            gimg = bundle["portrait_golden"]
            self.assertIsInstance(gimg, Image.Image)
            gm = next(i.manifest for i in plan.items
                      if i.role == "portrait_golden")
            self.assertEqual(S.sha256_hex(gimg.tobytes()),
                             gm["pixel_sha256"], "golden warm 像素失配")

    # ---- 用例 2：warm 隔离机器证明（audit） ----

    def test_2_audit_warm_isolation_report(self) -> None:
        p = _supply_cli("audit", "--cache-root", str(self.cache_root),
                        timeout=AUDIT_TIMEOUT_S)
        self.assertEqual(p.returncode, 0,
                         f"audit exit={p.returncode}\n{_stderr_tail(p)}")
        doc = json.loads(p.stdout)
        self.assertTrue(doc["pass"],
                        f"audit fail：{json.dumps(doc['results'],
                                                  ensure_ascii=False)[:1500]}")
        res = doc["results"]
        # import blocker 面：UnityPy 在禁入清单（同窗全卡装配跑通=机器证明）
        self.assertIn("UnityPy", res["import_blocker"]["blocked_modules"])
        self.assertTrue(res["import_blocker"]["pass"])
        # open 拦截扩面（R1 P1-7）：游戏文件族四形态全在禁开清单
        for pat in ("*.unity3d", "globalgamemanagers*", "resources.assets*",
                    "*.dll"):
            self.assertIn(pat, res["import_blocker"]["open_block_game_files"])
        # 全卡 offline：坏 --game + open 拦截下全卡 API 走查 pass（warm 零游戏文件；
        # partial 代 allow_partial 形态 + partial 标注）
        full = res["full_cards_offline"]
        self.assertTrue(full["pass"])
        self.assertFalse(full["full_build"])
        self.assertTrue(full["partial"])
        # open 拦截字段证据：fake game 根不存在 ∧ 装配仍跑通（stdout 内嵌 JSON）
        try:
            child = json.loads(full["stdout"])
            self.assertFalse(child["game_root_exists"],
                             "审计子进程竟真触到游戏根（fake game 应不存在）")
            self.assertTrue(child["partial"])
        except json.JSONDecodeError:
            self.assertIn('"game_root_exists": false', full["stdout"])
        # 完整性门（R1 P0-2）：partial 代 informational pass（不按全卡严格门）
        gate = res["completeness_gate"]
        self.assertTrue(gate["pass"])
        self.assertTrue(gate["partial"])
        self.assertTrue(res["require_cache_negative"]["pass"])
        # R2 缺席归因分道（partial 代 scope 外可缺=partial 定义，不走查尾
        # raise）：ok 卡装配账 + absent 两类/gap 归因单列，账面自洽
        c = full["child"]
        self.assertGreaterEqual(c["absent_expectationless"], 1,
                                f"partial 代必有零期望缺席卡：{c}")
        self.assertGreaterEqual(c["missing_gap"], 1,
                                f"partial 代必有 scope 外期望缺口卡：{c}")
        self.assertEqual(c["assembled"] + c["absent_expectationless"]
                         + c["absent_locator_missing"] + c["missing_gap"],
                         c["cards"], f"归因账不自洽：{c}")

    # ---- 用例 2b：verify gate 缺席归因（R2） ----

    def test_2b_verify_gate_absent_attribution(self) -> None:
        """verify gate 判定处缺席归因：gate 卡含无期望卡（数据缺席）与期望缺口
        卡各 ≥1 → not_built 拆分 not_built_absent / not_built_gap 两态计数
        （partial 代不作 not_built 门禁，exit 0）。"""
        with SupplyIndex(self.cache_root) as idx:
            built = {json.loads(r["params_json"])["card_id"] for r in
                     idx.conn.execute(
                         "SELECT params_json FROM items WHERE domain='art'")}
            gap_card = next(r["subject"] for r in idx.conn.execute(
                "SELECT subject FROM locators WHERE kind='portrait' "
                "AND status='ok'") if r["subject"] not in built)
            # 严格 absent_expectationless 形态：无 locator 行且无 plan_items 行
            #（cardtype 未知/域外族卡——kit 挂接不落行）
            absent_card = next(r["card_id"] for r in idx.conn.execute(
                "SELECT c.card_id AS card_id FROM cards c "
                "LEFT JOIN locators l ON l.subject=c.card_id "
                "LEFT JOIN plans p ON p.card_id=c.card_id "
                "LEFT JOIN plan_items pi ON pi.plan_key=p.plan_key "
                "WHERE l.subject IS NULL AND pi.plan_key IS NULL "
                "GROUP BY c.card_id LIMIT 1"))
        p = _supply_cli(
            "verify", "--game", str(GAME_ROOT), "--cache-root",
            str(self.cache_root), "--locale", "zhcn",
            "--sample", "4", "--golden-sample", "2",
            "--gate-cards", absent_card, gap_card, sorted(built)[0],
            "--no-kits", "--jobs", "2", timeout=VERIFY_TIMEOUT_S)
        self.assertEqual(p.returncode, 0,
                         f"verify exit={p.returncode}\n{_stderr_tail(p)}")
        doc = json.loads(p.stdout)
        self.assertTrue(doc["partial"])     # partial 代不作 not_built 门禁
        gp = doc["gate_pixel_checks"]
        self.assertEqual(gp["n"], 3)
        self.assertEqual(gp["not_built"],
                         gp["not_built_gap"] + gp["not_built_absent"])
        self.assertGreaterEqual(gp["not_built_absent"], 1,
                                f"无期望卡应归 absent：{gp}")
        self.assertGreaterEqual(gp["not_built_gap"], 1,
                                f"期望缺口卡应归 gap：{gp}")
        self.assertIn(absent_card, gp["not_built_absent_cards"])
        self.assertIn(gap_card, gp["not_built_gap_cards"])
        self.assertEqual(gp["ok"], 1)       # built 卡正常像素级全查
        self.assertEqual(gp["bad"], [])

    # ---- 用例 3：五态 cheap diff（同代 reused 主导） ----

    def test_3_diff_same_gen_reused_dominant(self) -> None:
        gen = self.layout.read_current()["generation"]
        p = _supply_cli("diff", "--cache-root", str(self.cache_root),
                        "--from-gen", gen, "--to-gen", gen,
                        timeout=QUICK_TIMEOUT_S)
        self.assertEqual(p.returncode, 0,
                         f"diff exit={p.returncode}\n{_stderr_tail(p)}")
        doc = json.loads(p.stdout)
        self.assertEqual(doc["from"], gen)
        self.assertEqual(doc["to"], gen)
        counts = doc["counts"]
        self.assertEqual(counts["stale"], 0)
        self.assertEqual(counts["missing"], 0)
        self.assertEqual(counts["orphan"], 0)
        self.assertGreaterEqual(counts["reused"], len(CARDS))
        # item 轴全 reused（分轴断言——counts 合并 bundle 轴；partial-init bundles
        # sha 记空串 → bundle 轴 sha-unrecorded→revalidate 是设计账，不算红）
        gid = gen[4:] if gen.startswith("gen-") else gen
        conn = S.connect(self.layout.gen_db(gid), readonly=True)
        try:
            rows = conn.execute(
                "SELECT kind, status, COUNT(*) AS n FROM migration_report "
                "GROUP BY kind, status").fetchall()
            n_items = conn.execute(
                "SELECT COUNT(*) AS n FROM items").fetchone()["n"]
            n_art = conn.execute(
                "SELECT COUNT(*) AS n FROM items WHERE domain='art'").fetchone()["n"]
        finally:
            conn.close()
        item_axis = {r["status"]: r["n"] for r in rows if r["kind"] == "item"}
        self.assertEqual(set(item_axis), {"reused"},
                         f"item 轴含非 reused 态：{item_axis}")
        # 全供给域（art/watermark/frames/gems/text）同代全 reused；条目数按全表
        self.assertEqual(item_axis["reused"], n_items)
        self.assertGreaterEqual(item_axis["reused"], n_art)
        self.assertTrue(doc["samples"]["reused"])

    # ---- 用例 4：响亮负例 ----

    def test_4_loud_negatives(self) -> None:
        # 4a. 篡改 portrait blob 字节 → assemble 面响亮（介质损坏 ≠ 静默）
        with SupplyIndex(self.cache_root) as idx:
            row = idx.conn.execute(
                "SELECT b.payload_sha256 AS sha, b.codec AS codec "
                "FROM item_blobs ib JOIN blobs b ON b.blob_key=ib.blob_key "
                "JOIN items i ON i.item_key=ib.item_key "
                "WHERE i.domain='art' AND i.params_json LIKE ? LIMIT 1",
                (f'%"{CARDS[1]}"%',)).fetchone()
        self.assertIsNotNone(row, "定向卡无 art blob 行（build 账坏）")
        blob = self.layout.blob_path(
            row["sha"], ext=KC.BLOB_CODEC_EXT.get(row["codec"] or "png", ".png"))
        original = blob.read_bytes()
        try:
            blob.write_bytes(original[:-1] + bytes([original[-1] ^ 0xFF]))
            # 进程内：精确异常类型断言
            with SupplyIndex(self.cache_root) as idx:
                with self.assertRaises(SupplyBlobCorruptError):
                    idx.assemble_portrait(CARDS[1])
            # CLI 面：require-cache 不自愈，exit 1 + stderr 判据
            p = _supply_cli("warm", "--cache-root", str(self.cache_root),
                            "--cards", CARDS[1], timeout=QUICK_TIMEOUT_S)
            self.assertEqual(p.returncode, 1, f"篡改后 warm 应 exit 1：{p.stdout}")
            self.assertIn("blob sha 不匹配", p.stderr)
        finally:
            blob.write_bytes(original)          # 还原（后续用例/审计面不受扰）
        p2 = _supply_cli("warm", "--cache-root", str(self.cache_root),
                         "--cards", *CARDS, timeout=QUICK_TIMEOUT_S)
        self.assertEqual(p2.returncode, 0, f"还原后 warm 应全绿：{p2.stderr}")
        doc = json.loads(p2.stdout)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["check"]["miss"], 0)
        self.assertEqual(doc["check"]["hit"], len(CARDS))

        # 4b. 未 build 卡：check 缺项账 + SupplyMissingError + warm CLI fail loud
        ghost = "__integration_ghost_card__"
        with SupplyIndex(self.cache_root) as idx:
            rep = idx.check([ghost])
            self.assertEqual(rep["miss"], 1)
            self.assertEqual(rep["missing_cards"], [f"{ghost}: 卡不在 cards 表"])
            with self.assertRaises(SupplyMissingError):
                idx.assemble_portrait(ghost)
        p3 = _supply_cli("warm", "--cache-root", str(self.cache_root),
                         "--cards", ghost, timeout=QUICK_TIMEOUT_S)
        self.assertEqual(p3.returncode, 1, f"ghost 卡 warm 应 exit 1：{p3.stdout}")
        self.assertIn("WARM MISS(require-cache)", p3.stderr)
        # miss 路径 stdout=check 报告本体（顶层 miss 键——同单测口径）
        self.assertEqual(json.loads(p3.stdout)["miss"], 1)

    # ---- 用例 5：targeted (card,kind) 补建（R1 P1-2） ----

    def test_5_targeted_golden_refill(self) -> None:
        """「有 portrait 缺 golden」形态定向补建：(card,kind) 粒度幂等不再跳过。

        删一卡 golden 面（plan_items/items/item_blobs）→ warm 期望账点名缺口 →
        ``build --cards <该卡>`` DB 驱动定向（decode_targets 只含 golden 一项
        ——portrait 已在 (card,kind) 账面被跳过）→ 补齐后 plan complete、
        assemble_card 全 role 出货、meta counts 全量重算。"""
        # 选一张有 golden 期望的定向卡
        with SupplyIndex(self.cache_root) as idx:
            cid = next(c for c in CARDS
                       if "portrait_golden" in idx.plan(c).expected)
            plan = idx.plan(cid)
            gitem = next(i.item_key for i in plan.items
                         if i.role == "portrait_golden")
        # 删 golden 面（构造「有 portrait 缺 golden」）
        conn = S.connect(self.layout.gen_db(self.layout.read_current()["game_id"]))
        try:
            conn.execute("DELETE FROM plan_items WHERE item_key=?", (gitem,))
            conn.execute("DELETE FROM item_blobs WHERE item_key=?", (gitem,))
            conn.execute("DELETE FROM items WHERE item_key=?", (gitem,))
            conn.commit()
        finally:
            conn.close()
        with SupplyIndex(self.cache_root) as idx:
            plan = idx.plan(cid)
            self.assertTrue(any("portrait_golden" in m for m in plan.missing),
                            f"删 golden 后期望账未点名：{plan.missing}")
            self.assertEqual(plan.status, "partial")
            with self.assertRaises(SupplyMissingError):
                idx.assemble_card(cid)
        # DB 驱动定向补建（同代；身份门走 ident==current 正路）
        p = _supply_cli("build", "--game", str(GAME_ROOT), "--cache-root",
                        str(self.cache_root), "--locale", "zhcn",
                        "--cards", cid, "--jobs", "2",
                        timeout=QUICK_TIMEOUT_S)
        self.assertEqual(p.returncode, 0,
                         f"targeted 补建 exit={p.returncode}\n{_stderr_tail(p)}")
        doc = json.loads(p.stdout)
        self.assertEqual(doc["mode"], "targeted-db")
        # (card,kind) 粒度证据：只补 golden 一项（portrait 已在账）
        self.assertEqual(doc["decode_targets"], 1,
                         f"decode_targets≠1（粒度退化为按卡）：{doc}")
        self.assertEqual(doc["plan_status"]["complete"], 1)
        self.assertEqual(doc["decode_errors"]["portrait_golden"]["count"], 0)
        # 补齐后：plan complete + 全 role 出货
        with SupplyIndex(self.cache_root) as idx:
            plan = idx.plan(cid)
            self.assertEqual(plan.missing, [])
            self.assertEqual(plan.status, "complete")
            bundle = idx.assemble_card(cid)
            self.assertIsInstance(bundle["portrait_golden"], Image.Image)
        # meta counts 全量重算（R1 P1-10）：plan/blob_bytes 账与表现一致
        gid = self.layout.read_current()["game_id"]
        conn = S.connect(self.layout.gen_db(gid), readonly=True)
        try:
            meta = {r["key"]: r["value"] for r in conn.execute(
                "SELECT key,value FROM meta")}
            n_pi = conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0]
            n_pl = conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
            s_blobs = conn.execute(
                "SELECT COALESCE(SUM(size),0) FROM blobs").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(int(meta["counts_plan_items"]), n_pi)
        self.assertEqual(int(meta["counts_plans"]), n_pl)
        self.assertEqual(int(meta["blob_bytes"]), s_blobs)

    # ---- 用例 6：身份门负例（R1 P1-2） ----

    def test_6_identity_gate_rejects_forged_generation(self) -> None:
        """伪造 current.json 指向异 game_id → targeted build 响亮拒绝、不写库。"""
        cur_path = self.layout.current_json
        saved = cur_path.read_text(encoding="utf-8")
        cur = json.loads(saved)
        fake_gid = "0" * 64
        fake_db = self.layout.gen_db(fake_gid)
        fake_db.parent.mkdir(parents=True, exist_ok=True)
        conn = S.connect(fake_db)
        try:
            S.init_schema(conn)     # 最小假代库（has_gen 只查文件在）
            conn.commit()
        finally:
            conn.close()
        self.addCleanup(fake_db.unlink)
        try:
            self.layout.write_current({**cur, "game_id": fake_gid,
                                       "generation": f"gen-{fake_gid}"})
            p = _supply_cli("build", "--game", str(GAME_ROOT), "--cache-root",
                            str(self.cache_root), "--locale", "zhcn",
                            "--cards", CARDS[0], timeout=QUICK_TIMEOUT_S)
            self.assertNotEqual(p.returncode, 0,
                                f"异代定向 build 竟成功：{p.stdout[:300]}")
            self.assertIn("游戏身份已换代", p.stderr)
            self.assertIn("全量", p.stderr)
        finally:
            cur_path.write_text(saved, encoding="utf-8")     # 还原（不写库判据）
        self.assertEqual(json.loads(cur_path.read_text(encoding="utf-8"))["game_id"],
                         cur["game_id"])


    # ---- 用例 7：targeted 失败负例（P2 审计 P1-2 固化） ----

    def test_7_targeted_failure_integrity_gate(self) -> None:
        """临时副本把 portrait locator 的 bundle 置坏 + 删对应 item → targeted
        build 必须 exit 1 且 stderr 点名完整性门/scope 缺项；共享 cache 不被污染。"""
        tmp = tempfile.TemporaryDirectory(prefix="eidolon-supply-neg-")
        self.addCleanup(tmp.cleanup)
        copy_root = Path(tmp.name) / "cache"
        shutil.copytree(self.cache_root, copy_root)
        layout = SupplyLayout(copy_root)
        cid = CARDS[1]
        gid = layout.read_current()["game_id"]
        db = layout.gen_db(gid)
        conn = S.connect(db)
        try:
            item_key = conn.execute(
                "SELECT pi.item_key FROM plan_items pi JOIN plans p "
                "ON p.plan_key=pi.plan_key WHERE p.card_id=? AND pi.role='portrait'",
                (cid,)).fetchone()["item_key"]
            conn.execute("DELETE FROM plan_items WHERE item_key=?", (item_key,))
            conn.execute("DELETE FROM item_blobs WHERE item_key=?", (item_key,))
            conn.execute("DELETE FROM items WHERE item_key=?", (item_key,))
            conn.execute(
                "UPDATE locators SET bundle='no-such-bundle.unity3d' "
                "WHERE kind='portrait' AND subject=?", (cid,))
            conn.commit()
        finally:
            conn.close()
        p = _supply_cli("build", "--game", str(GAME_ROOT), "--cache-root",
                        str(copy_root), "--locale", "zhcn",
                        "--cards", cid, "--jobs", "2",
                        timeout=QUICK_TIMEOUT_S)
        self.assertEqual(p.returncode, 1,
                         f"坏 locator 的 targeted build 应 exit 1：{p.stdout[:400]}")
        self.assertIn("targeted build 完整性门", p.stderr)
        self.assertIn("scope", p.stderr)
        # 共享 cache 未被污染：item 仍在、locator bundle 仍是原值
        conn = S.connect(self.layout.gen_db(
            self.layout.read_current()["game_id"]), readonly=True)
        try:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM items WHERE item_key=?", (item_key,)
            ).fetchone()[0], 1)
            self.assertNotEqual(conn.execute(
                "SELECT bundle FROM locators WHERE kind='portrait' AND subject=?",
                (cid,)).fetchone()["bundle"], "no-such-bundle.unity3d")
        finally:
            conn.close()

    # ---- 用例 8：integrity --repair 坏 blob → 复扫 0 bad（tmp 副本） ----

    def test_8_integrity_repair_bad_blob(self) -> None:
        """tmp 副本篡改一个 art blob → integrity --repair 定点重推导 → rescan 0
        bad（字节全等）；真实源与共享 cache 的 blob 均不被改写。"""
        tmp = tempfile.TemporaryDirectory(prefix="eidolon-supply-repair-")
        self.addCleanup(tmp.cleanup)
        copy_root = Path(tmp.name) / "cache"
        shutil.copytree(self.cache_root, copy_root)
        layout = SupplyLayout(copy_root)
        with SupplyIndex(copy_root) as idx:
            row = idx.conn.execute(
                "SELECT b.payload_sha256 AS sha, b.codec AS codec "
                "FROM item_blobs ib JOIN blobs b ON b.blob_key=ib.blob_key "
                "JOIN items i ON i.item_key=ib.item_key "
                "WHERE i.domain='art' LIMIT 1").fetchone()
        self.assertIsNotNone(row, "副本无 art blob 行")
        blob = layout.blob_path(
            row["sha"], ext=KC.BLOB_CODEC_EXT.get(row["codec"] or "png", ".png"))
        original = blob.read_bytes()
        blob.write_bytes(original[:-1] + bytes([original[-1] ^ 0xFF]))
        p = _supply_cli("integrity", "--game", str(GAME_ROOT),
                        "--cache-root", str(copy_root), "--locale", "zhcn",
                        "--repair", timeout=VERIFY_TIMEOUT_S)
        self.assertEqual(p.returncode, 0,
                         f"integrity --repair exit={p.returncode}\n"
                         f"{_stderr_tail(p)}")
        doc = json.loads(p.stdout)
        self.assertEqual(doc["scan"]["bad"], 1, f"扫描未发现坏 blob：{doc['scan']}")
        self.assertEqual(doc["rescan"]["bad"], 0,
                         f"repair 后复扫仍坏：{doc['rescan']}")
        self.assertTrue(doc["repair"]["repaired"], f"无修复账：{doc.get('repair')}")
        self.assertEqual(doc["bad"], 0)
        # 共享 cache 的原 blob 未被动过
        with SupplyIndex(self.cache_root) as idx:
            orig = idx.conn.execute(
                "SELECT b.payload_sha256 AS sha, b.codec AS codec "
                "FROM item_blobs ib JOIN blobs b ON b.blob_key=ib.blob_key "
                "JOIN items i ON i.item_key=ib.item_key "
                "WHERE i.domain='art' AND b.payload_sha256=? LIMIT 1",
                (row["sha"],)).fetchone()
        self.assertIsNotNone(orig, "共享 cache 的 blob 行被污染")
        self.assertEqual(self.layout.blob_path(
            row["sha"], ext=KC.BLOB_CODEC_EXT.get(row["codec"] or "png", ".png")
        ).read_bytes()[:4], b"\x89PNG", "共享 cache 的 blob 字节被改写")

    # ---- 用例 9：audit --auto 默认 scratch（P2 审计） ----

    def test_9_audit_auto_default_scratch(self) -> None:
        """``audit --auto`` 默认系统临时 scratch（不经 --auto-scratch）：partial
        建库→require-cache 负探针→auto 冷补→复验→不可补仍 fail loud，pass=True，
        用完即焚。"""
        p = _supply_cli("audit", "--cache-root", str(self.cache_root),
                        "--game", str(GAME_ROOT), "--locale", "zhcn",
                        "--auto", timeout=AUDIT_TIMEOUT_S)
        self.assertEqual(p.returncode, 0,
                         f"audit --auto exit={p.returncode}\n{_stderr_tail(p)}")
        doc = json.loads(p.stdout)
        auto = doc["auto_mode"]
        self.assertTrue(auto["pass"], f"auto 审计非绿：{auto}")
        self.assertTrue(auto["partial_build"]["mode"].startswith("partial"))
        self.assertTrue(auto["require_cache_before_fill"]["pass"])
        self.assertTrue(auto["auto_fill"]["pass"])
        self.assertTrue(auto["unfillable_still_fails"]["pass"])
        self.assertFalse(Path(auto["scratch_root"]).exists(),
                         f"默认 scratch 未焚：{auto['scratch_root']}")


def _tail(path: Path, n: int = 1500) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()[-n:]
    except OSError:
        return "<日志文件缺失>"


def _stderr_tail(p: subprocess.CompletedProcess, n: int = 1500) -> str:
    return (p.stderr or "").strip()[-n:]


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
