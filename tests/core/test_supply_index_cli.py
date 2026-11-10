"""core/supply_index CLI 参数面与退出码单测（默认 discover 收集；不跑真 build）。

覆盖（任务 A3）：
  * 子命令面：build / warm / diff / revalidate / verify / bench / bench-process /
    audit / measure / integrity / maintain 全部存在且参数可解析（cmd_* 打桩记录，
    不触 cold/UnityPy）；
  * ``--game/--locale`` build 必填（argparse required → SystemExit 2）；
    ``_need_identity`` 按消费路径校验（缺省 → SystemExit 2）；
  * ``--cache-root`` 缺省语义：解析后统一裁决 exit 2（顶层/子命令任一位置可给；
    子进程 e2e 钉 ``python -m eidolon.core.supply_index`` 形态）；
  * 退出码映射：verify 的 bad/gate/段红 → 1；revalidate 缺 --exact → 2；
    warm 的 miss → 1、全绿 → 0（fake SupplyIndex 面）；
  * stdout 契约：``_emit`` 恒 JSON（CLI 无 --json 旗标——输出恒为 JSON，见偏差账）。

本文件禁触游戏文件与真实缓存根；不打真 build（cmd_build 打桩，cold 不 import）。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from eidolon.core.supply_index import cli
# 预加载 selfheal：WarmCliFlowTests 会临时把 warm.SupplyIndex 换成 Fake；若
# selfheal 在该 patch 窗口内首次 import，会把 Fake 绑进 selfheal 模块（跨文件
# 测试污染，Phase 5 审计 P2 抓到）。模块加载期先绑定真实类。
import eidolon.core.supply_index.selfheal as _selfheal  # noqa: E402,F401

_REPO = Path(__file__).resolve().parents[2]

SUBCOMMANDS = ("build", "warm", "diff", "revalidate", "verify", "bench",
               "bench-process", "audit", "measure", "integrity", "maintain")


def _identity() -> list[str]:
    return ["--game", "game-root", "--locale", "zhcn"]


class CliCase(unittest.TestCase):
    """cmd_* 打桩 + stdout/stderr 捕获的 main() 调用面。"""

    def setUp(self) -> None:
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.calls: dict[str, list] = {name: [] for name in SUBCOMMANDS}

    def _patch_cmds(self, *names: str, **returns) -> None:
        """把 cli.cmd_* 换成记录器（可选返回值）；main() 构 parser 时取桩。

        names=只打桩这些子命令（缺省全部）——被测 cmd 本体不打桩（退出码映射
        在 cmd_* 函数体内，打桩会掩盖被测逻辑）。"""
        patches = []
        for name in (names or SUBCOMMANDS):
            rec = self._record(name)

            def make(rec=rec, ret=returns.get(name, 0)):
                def fn(args):
                    rec.append(vars(args).copy())
                    return ret
                return fn
            # 子命令名带连字符（bench-process）→ 模块函数名用下划线
            patches.append(mock.patch.object(cli, f"cmd_{name.replace('-', '_')}",
                                             make(rec)))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _record(self, name: str) -> list:
        return self.calls[name]

    def _main(self, argv: list[str]) -> int:
        """跑一次 main()；stdout/stderr 快照存 self.out_text / self.err_text
        （_emit 输出是多行 JSON 文档——按整段解析，不按行）。"""
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        with contextlib.redirect_stdout(self.stdout), \
                contextlib.redirect_stderr(self.stderr):
            rc = cli.main(argv)
        self.out_text = self.stdout.getvalue()
        self.err_text = self.stderr.getvalue()
        return rc


class SubcommandSurfaceTests(CliCase):
    """子命令存在性与参数默认值（打桩解析面）。"""

    def test_help_lists_all_subcommands(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as buf, \
                self.assertRaises(SystemExit) as cm:
            cli.main(["--help"])
        self.assertEqual(cm.exception.code, 0)
        text = buf.getvalue()
        for name in SUBCOMMANDS:
            self.assertIn(name, text)

    def test_build_parse_defaults(self) -> None:
        self._patch_cmds()
        rc = self._main(["--cache-root", "X", "build", *_identity()])
        self.assertEqual(rc, 0)
        (args,) = self.calls["build"]
        self.assertEqual(args["cache_root"], "X")
        self.assertEqual(args["game"], "game-root")
        self.assertEqual(args["locale"], "zhcn")
        self.assertEqual(args["jobs"], 4)
        self.assertIsNone(args["cards"])
        self.assertIsNone(args["sample"])
        self.assertFalse(args["skip_bundle_hash"])

    def test_warm_parse_defaults(self) -> None:
        self._patch_cmds()
        rc = self._main(["--cache-root", "X", "warm"])
        self.assertEqual(rc, 0)
        (args,) = self.calls["warm"]
        self.assertEqual(args["mode"], "require-cache")
        self.assertIsNone(args["cards"])
        self.assertIsNone(args["save_png"])

    def test_verify_parse_defaults(self) -> None:
        self._patch_cmds()
        rc = self._main(["--cache-root", "X", "verify", *_identity()])
        self.assertEqual(rc, 0)
        (args,) = self.calls["verify"]
        self.assertEqual(args["sample"], 500)
        self.assertEqual(args["golden_sample"], 100)
        self.assertIsNone(args["gate_cards"])
        self.assertEqual(args["seed"], 42)
        self.assertEqual(args["jobs"], 4)
        self.assertFalse(args["no_kits"])
        self.assertFalse(args["all_items"])

    def test_verify_all_mode_parse(self) -> None:
        self._patch_cmds()
        rc = self._main(["--cache-root", "X", "verify", "--all", *_identity()])
        self.assertEqual(rc, 0)
        (args,) = self.calls["verify"]
        self.assertTrue(args["all_items"])
        self.assertEqual(args["sample"], 500)      # 显式档不改默认抽样值

    def test_revalidate_parse_defaults(self) -> None:
        self._patch_cmds()
        rc = self._main(["--cache-root", "X", "revalidate", "--exact",
                         *_identity()])
        self.assertEqual(rc, 0)
        (args,) = self.calls["revalidate"]
        self.assertTrue(args["exact"])
        self.assertIsNone(args["from_gen"])
        self.assertIsNone(args["limit"])

    def test_misc_parse_defaults(self) -> None:
        self._patch_cmds()
        self.assertEqual(self._main(["--cache-root", "X", "bench",
                                     *_identity()]), 0)
        self.assertEqual(self.calls["bench"][0]["repeat"], 5)
        self.assertEqual(self.calls["bench"][0]["cold_sample"], 20)
        self.assertEqual(self._main(["--cache-root", "X", "diff"]), 0)
        self.assertFalse(self.calls["diff"][0]["synthetic"])
        self.assertEqual(self._main(["--cache-root", "X", "audit"]), 0)
        self.assertIsNone(self.calls["audit"][0]["fake_game"])
        self.assertFalse(self.calls["audit"][0]["auto"])
        self.assertEqual(self._main(["--cache-root", "X", "integrity",
                                     *_identity()]), 0)
        self.assertFalse(self.calls["integrity"][0]["repair"])
        self.assertEqual(self._main(["--cache-root", "X", "maintain"]), 0)
        self.assertEqual(self.calls["maintain"][0]["keep"], 2)
        self.assertFalse(self.calls["maintain"][0]["prune"])
        self.assertEqual(self._main(["--cache-root", "X", "bench-process"]), 0)
        self.assertEqual(self.calls["bench-process"][0]["rounds"], 2)
        self.assertEqual(self.calls["bench-process"][0]["single_repeat"], 8)

    def test_cache_root_at_either_position(self) -> None:
        self._patch_cmds()
        self.assertEqual(self._main(["measure", "--cache-root", "Y"]), 0)
        self.assertEqual(self.calls["measure"][0]["cache_root"], "Y")
        self.assertEqual(self._main(["--cache-root", "T", "measure"]), 0)
        self.assertEqual(self.calls["measure"][1]["cache_root"], "T")


class CliExitCodeTests(CliCase):
    """退出码语义：2=参数错误；1=供给失败/红；0=绿。"""

    def test_build_requires_game_and_locale(self) -> None:
        self._patch_cmds()
        with self.assertRaises(SystemExit) as cm:
            self._main(["--cache-root", "X", "build"])
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(self.calls["build"], [])
        with self.assertRaises(SystemExit) as cm2:
            self._main(["--cache-root", "X", "verify"])
        self.assertEqual(cm2.exception.code, 2)

    def test_cache_root_missing_returns_2_without_calling_cmd(self) -> None:
        self._patch_cmds()
        rc = self._main(["build", *_identity()])
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls["build"], [])
        self.assertIn("--cache-root", self.err_text)

    def test_unknown_and_missing_subcommand_exit_2(self) -> None:
        self._patch_cmds()
        with self.assertRaises(SystemExit) as cm:
            self._main(["nope"])
        self.assertEqual(cm.exception.code, 2)
        with self.assertRaises(SystemExit) as cm2:
            self._main([])
        self.assertEqual(cm2.exception.code, 2)

    def test_need_identity_unit(self) -> None:
        from eidolon.core.supply_index.cli import _need_identity

        with contextlib.redirect_stderr(io.StringIO()) as err, \
                self.assertRaises(SystemExit) as cm:
            _need_identity(SimpleNamespace(game=None, locale=None), "warm --mode auto")
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--game 与 --locale", err.getvalue())
        game, locale = _need_identity(SimpleNamespace(game="g", locale="l"), "x")
        self.assertEqual(game, Path("g"))
        self.assertEqual(locale, "l")

    def test_revalidate_without_exact_is_cheap_reject_2(self) -> None:
        # cmd_revalidate 本体不打桩（cheap 拒绝逻辑在被测函数体内）
        self._patch_cmds("measure")
        rc = self._main(["--cache-root", "X", "revalidate", *_identity()])
        self.assertEqual(rc, 2)
        self.assertIn("--exact", self.err_text)

    def test_revalidate_exact_calls_diff(self) -> None:
        import eidolon.core.supply_index.diff as diff_mod

        self._patch_cmds("measure")
        with mock.patch.object(diff_mod, "revalidate_exact",
                               return_value={"checked": 0}) as fx:
            rc = self._main(["--cache-root", "X", "revalidate", "--exact",
                             *_identity()])
        self.assertEqual(rc, 0)
        fx.assert_called_once()
        self.assertEqual(fx.call_args.kwargs["game"], Path("game-root"))

    def test_verify_exit_mapping(self) -> None:
        import eidolon.core.supply_index.verify as verify_mod

        green = {"bad": 0, "full_build": True, "partial": False,
                 "gate_pixel_checks": {"bad": [], "not_built": 0,
                                       "not_built_gap": 0,
                                       "not_built_absent": 0},
                 "kit": {"ok": True}, "gems": {"ok": True},
                 "text": {"ok": True}, "watermark": {"ok": True}}
        with mock.patch.object(verify_mod, "verify", return_value=green) as fx:
            self.assertEqual(self._main(["--cache-root", "X", "verify",
                                         *_identity()]), 0)
            self.assertEqual(fx.call_args.kwargs["n_sample"], 500)
            self.assertFalse(fx.call_args.kwargs["all_items"])
            # --all 透传到 verify（全量档开关；默认行为不变）
            self.assertEqual(self._main(["--cache-root", "X", "verify", "--all",
                                         *_identity()]), 0)
            self.assertTrue(fx.call_args.kwargs["all_items"])
            # bad 计数非零 → 1
            fx.return_value = {**green, "bad": 2}
            self.assertEqual(self._main(["--cache-root", "X", "verify",
                                         *_identity()]), 1)
            # gate 像素失配清单非空 → 1
            fx.return_value = {**green, "gate_pixel_checks":
                               {"bad": [{"card_id": "C", "ok": False}],
                                "not_built": 0, "not_built_gap": 0,
                                "not_built_absent": 0}}
            self.assertEqual(self._main(["--cache-root", "X", "verify",
                                         *_identity()]), 1)
            # kit/gems/text/watermark 段红 → 1（旧形 `list != 0` 恒真坑的回归钉）
            fx.return_value = {**green, "gems": {"ok": False}}
            self.assertEqual(self._main(["--cache-root", "X", "verify",
                                         *_identity()]), 1)
            # full 代 gate 全查 not_built_gap>0（有期望未建）→ 1（R2 门禁）
            fx.return_value = {**green, "gate_pixel_checks":
                               {"bad": [], "not_built": 2, "not_built_gap": 2,
                                "not_built_absent": 0}}
            self.assertEqual(self._main(["--cache-root", "X", "verify",
                                         *_identity()]), 1)
            # full 代 not_built_absent>0（数据缺席可归因）且 gap=0 → 0（R2）
            fx.return_value = {**green, "gate_pixel_checks":
                               {"bad": [], "not_built": 9, "not_built_gap": 0,
                                "not_built_absent": 9}}
            self.assertEqual(self._main(["--cache-root", "X", "verify",
                                         *_identity()]), 0)
            # partial 代（full_build=0）not_built>0 → 0（不作门禁；其余全绿）
            fx.return_value = {**green, "full_build": False, "partial": True,
                               "gate_pixel_checks":
                               {"bad": [], "not_built": 40, "not_built_gap": 1,
                                "not_built_absent": 39}}
            self.assertEqual(self._main(["--cache-root", "X", "verify",
                                         *_identity()]), 0)
            # partial 显式标注走 stdout JSON（stderr 注记只在红项 exit 1 时）
            self.assertIn('"partial": true', self.out_text)
        # 报告 JSON 上 stdout（_emit 契约）——最后一次调用=partial 全绿形态
        doc = json.loads(self.out_text.strip())
        self.assertTrue(doc["partial"])

    def test_diff_synthetic_selfcheck_failure_exit_1(self) -> None:
        """五态演练自校验失败 → 干净 stderr + exit 1（不裸 traceback、不静默绿）。"""
        import eidolon.core.supply_index.diff as diff_mod

        self._patch_cmds("measure")
        with mock.patch.object(diff_mod, "five_state_exercise",
                               side_effect=RuntimeError("stale: injected=2 diff=1")):
            rc = self._main(["--cache-root", "X", "diff", "--synthetic",
                             *_identity()])
        self.assertEqual(rc, 1)
        self.assertIn("五态演练自校验失败", self.err_text)
        self.assertIn("stale: injected=2 diff=1", self.err_text)

    def test_emit_is_json_by_contract(self) -> None:
        # CLI 无 --json 旗标（P5-1 定案：stdout 恒 JSON——_emit 单源）
        for flag_args in (["verify", "--json"],):
            self._patch_cmds()
            with self.assertRaises(SystemExit):
                self._main(["--cache-root", "X", *flag_args, *_identity()])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._emit({"a": 1, "b": ["x", "y"], "p": Path("z")})
        self.assertEqual(json.loads(buf.getvalue()),
                         {"a": 1, "b": ["x", "y"], "p": "z"})


class WarmCliFlowTests(CliCase):
    """warm CLI 的 miss→1 / 全绿→0 流程（fake SupplyIndex 面）。"""

    def _fake_index(self, rep: dict):
        import eidolon.core.supply_index.warm as warm_mod

        made = []

        class _FakeIdx:
            def __init__(self, cache_root, locale=None, **kw):
                self.cache_root = cache_root
                self.locale = locale
                self.health_error = None
                self.probe = {}
                made.append(self)

            def check(self, cards):
                return dict(rep)

            def plan(self, cid):
                return None

            def close(self):
                pass

        return mock.patch.object(warm_mod, "SupplyIndex", _FakeIdx), made

    def test_warm_miss_fails_loud_exit_1(self) -> None:
        rep = {"total": 2, "hit": 0, "absent_portrait": 0, "missing_cards":
               ["GHOST: 卡不在 cards 表"], "missing_items": [], "miss": 1}
        patcher, made = self._fake_index(rep)
        self._patch_cmds("measure")        # cmd_warm 本体不打桩（被测面）
        with patcher:
            rc = self._main(["--cache-root", "X", "warm", "--cards", "C1", "C2"])
        self.assertEqual(rc, 1)
        self.assertEqual(made[0].cache_root, "X")
        # miss 路径 stdout=check 报告本体（顶层 miss/missing_cards；ok+check
        # 包裹是成功路径形状，见 cmd_warm fail-loud 分支）
        doc = json.loads(self.out_text.strip())
        self.assertEqual(doc["miss"], 1)
        self.assertEqual(doc["missing_cards"], ["GHOST: 卡不在 cards 表"])
        self.assertIn("WARM MISS(require-cache)", self.err_text)

    def test_warm_clean_exit_0(self) -> None:
        rep = {"total": 2, "hit": 2, "absent_portrait": 0, "missing_cards": [],
               "missing_items": [], "miss": 0}
        patcher, made = self._fake_index(rep)
        self._patch_cmds("measure")
        with patcher:
            rc = self._main(["--cache-root", "X", "warm", "--cards", "C1", "C2"])
        self.assertEqual(rc, 0)
        doc = json.loads(self.out_text.strip())
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["mode"], "require-cache")
        self.assertEqual(doc["check"]["hit"], 2)


class CliSubprocessTests(unittest.TestCase):
    """e2e 钉子：``python -m eidolon.core.supply_index`` 的参数错误退出码。"""

    def _run(self, *argv: str,
             env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m",
                               "eidolon.core.supply_index", *argv],
                              capture_output=True, encoding="utf-8",
                              errors="replace", cwd=str(_REPO),
                              env=env, timeout=120)

    def test_help_ok(self) -> None:
        p = self._run("--help")
        self.assertEqual(p.returncode, 0)
        for name in SUBCOMMANDS:
            self.assertIn(name, p.stdout)

    def test_help_ok_under_cp1252(self) -> None:
        """Windows 非 UTF-8 代码页下 help 含中文也必须退出 0。"""
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        p = self._run("--help", env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        for name in SUBCOMMANDS:
            self.assertIn(name, p.stdout)

    def test_missing_cache_root_exit_2(self) -> None:
        p = self._run("build", "--game", "g", "--locale", "l")
        self.assertEqual(p.returncode, 2)
        self.assertIn("--cache-root", p.stderr)
        self.assertNotIn("{", p.stdout)          # 无报告输出（参数错误不发 JSON）

    def test_no_args_exit_2(self) -> None:
        p = self._run()
        self.assertEqual(p.returncode, 2)


# ---------------------------------------------------------------------------
# audit 完整性门（R2 缺席归因口径）+ open 拦截扩面（Phase 5 返工 R1，P0-2/P1-7）
# ---------------------------------------------------------------------------

class AuditCompletenessGateTests(unittest.TestCase):
    """audit.completeness_gate（R2 缺席归因口径：gap 红 / absent 单列 /
    child 走查自洽；纯 DB 面，零 UnityPy）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        from eidolon.core.supply_index import schema as S
        from eidolon.core.supply_index.paths import SupplyLayout

        self.S = S
        self.layout = SupplyLayout(self.root)
        self.gid = "gatetest"
        db = self.layout.gen_db(self.gid)
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = S.connect(db)
        try:
            S.init_schema(conn)
            conn.executemany("INSERT INTO meta(key,value) VALUES(?,?)",
                             [("game_id", self.gid), ("locale", "zhcn")])
            conn.commit()
        finally:
            conn.close()

    def _set_full(self, v: str) -> None:
        S = self.S
        conn = S.connect(self.layout.gen_db(self.gid))
        try:
            conn.execute("INSERT OR REPLACE INTO meta(key,value) "
                         "VALUES('full_build',?)", (v,))
            conn.commit()
        finally:
            conn.close()
        self.layout.write_current({"game_id": self.gid,
                                   "generation": f"gen-{self.gid}",
                                   "locale": "zhcn", "full_build": v == "1"})

    def _add_card(self, cid: str, *, locator: str | None, status: str = "ok",
                  plan_key: str | None = None) -> None:
        """造卡行（+可选 locator 行 +可选 plan 行——归因账的四种原料）。"""
        S = self.S
        conn = S.connect(self.layout.gen_db(self.gid))
        try:
            conn.execute(
                "INSERT INTO cards(card_id,dbf_id,carddef_ref,carddef_guid,"
                "carddef_bundle,carddef_cab,carddef_path_id,data_sha) "
                "VALUES(?,NULL,'','','','',0,?)", (cid, f"ds-{cid}"))
            if locator is not None:
                conn.execute(
                    "INSERT INTO locators(id,kind,subject,locale,premium,"
                    "ref,guid,bundle,cab,path_id,status,source_json) "
                    "VALUES((SELECT COALESCE(MAX(id),0)+1 FROM locators),"
                    "'portrait',?,'zhcn','','r','g','b1','',0,?,'{}')",
                    (cid, status))
            if plan_key is not None:
                conn.execute(
                    "INSERT INTO plans(plan_key,card_id,options_json,status,"
                    "plan_version,card_data_sha,created_at) "
                    "VALUES(?,?,'{}','complete',?,?,0)",
                    (plan_key, cid, S.PLAN_VERSION, f"ds-{cid}"))
            conn.commit()
        finally:
            conn.close()

    def test_partial_gen_gate_is_informational(self) -> None:
        """partial 代（full_build=0）：不按全卡严格门，partial 显式标注、pass。"""
        from eidolon.core.supply_index.audit import completeness_gate

        self._set_full("0")
        gate = completeness_gate(self.root, child={"cards": 4, "assembled": 1,
                                                   "empty_plan_cards": 3,
                                                   "partial": True})
        self.assertTrue(gate["pass"])
        self.assertTrue(gate["partial"])
        self.assertFalse(gate["full_build"])

    def test_full_gen_gate_blocks_on_gap(self) -> None:
        """full 代：期望缺口（ok locator 无 item——missing_gap）→ pass=False，
        why 点名 unaccountable 卡。"""
        from eidolon.core.supply_index.audit import completeness_gate

        self._set_full("1")
        self._add_card("cX", locator="portrait", status="ok",
                       plan_key="pk-cX")
        gate = completeness_gate(self.root, child={"cards": 1, "assembled": 0,
                                                   "absent_expectationless": 0,
                                                   "absent_locator_missing": 0,
                                                   "missing_gap": 1})
        self.assertFalse(gate["pass"])
        self.assertTrue(any("期望缺口" in w and "missing_gap" in w
                            for w in gate["why"]))
        self.assertIn("cX", gate["attribution"]["samples"]["missing_gap"])
        # child 账自洽（assembled+absent+gap==cards ✓）——红只来自 DB 面 gap
        self.assertEqual(gate["accounted_absent"],
                         {"expectationless": 0, "locator_missing": 0})

    def test_full_gen_gate_absent_passes(self) -> None:
        """full 代：可归因缺席（expectationless 1 + locator_missing 1、gap=0）
        → pass，accounted_absent 显式计数。"""
        from eidolon.core.supply_index.audit import completeness_gate

        self._set_full("1")
        self._add_card("cA", locator=None)                      # 无 locator 无 plan
        self._add_card("cL", locator="portrait", status="missing")
        gate = completeness_gate(self.root, child={"cards": 2, "assembled": 0,
                                                   "absent_expectationless": 1,
                                                   "absent_locator_missing": 1,
                                                   "missing_gap": 0})
        self.assertTrue(gate["pass"], gate["why"])
        self.assertEqual(gate["accounted_absent"],
                         {"expectationless": 1, "locator_missing": 1})
        self.assertEqual(gate["completeness"]["missing_total"], 0)

    def test_full_gen_gate_child_absent_mismatch_blocks(self) -> None:
        """full 代：walk 跳过集与 DB 归因集不一致（child 多账 assembled、少账
        缺席）→ pass=False（自洽断言：child absent==DB 归因 absent）。"""
        from eidolon.core.supply_index.audit import completeness_gate

        self._set_full("1")
        self._add_card("cA", locator=None)
        self._add_card("cL", locator="portrait", status="missing")
        gate = completeness_gate(self.root, child={"cards": 2, "assembled": 2,
                                                   "absent_expectationless": 0,
                                                   "absent_locator_missing": 0,
                                                   "missing_gap": 0})
        self.assertFalse(gate["pass"])
        self.assertTrue(any("child absent 0+0 != DB 归因 absent 1+1" in w
                            for w in gate["why"]))
        # 破坏 assembled 账（assembled 3 + absent 0 != cards 2）也要红
        gate2 = completeness_gate(self.root, child={"cards": 2, "assembled": 3,
                                                    "absent_expectationless": 0,
                                                    "absent_locator_missing": 0,
                                                    "missing_gap": 0})
        self.assertFalse(gate2["pass"])
        self.assertTrue(any("assembled 3 + absent 0+0 + gap 0 != cards 2" in w
                            for w in gate2["why"]))

    def test_full_gen_gate_complete_passes(self) -> None:
        """full 代全齐（零卡=零缺项零缺席 + child 全 assembled）→ pass。"""
        from eidolon.core.supply_index.audit import completeness_gate

        self._set_full("1")
        gate = completeness_gate(self.root, child={"cards": 5, "assembled": 5,
                                                   "absent_expectationless": 0,
                                                   "absent_locator_missing": 0,
                                                   "missing_gap": 0})
        self.assertTrue(gate["pass"])
        self.assertEqual(gate["completeness"]["missing_total"], 0)
        self.assertEqual(gate["accounted_absent"],
                         {"expectationless": 0, "locator_missing": 0})


class AuditAutoScratchTests(unittest.TestCase):
    """audit --auto 默认 scratch 目录（P2 审计）：mkdir 后 mkdtemp 能跑、用完即焚。"""

    def test_scratch_dir_created(self) -> None:
        from eidolon.core.supply_index.audit import _scratch_dir

        d = _scratch_dir()
        self.assertTrue(d.is_dir(), f"scratch 宿主目录未创建：{d}")
        self.assertIn("eidolon-supply-audit-auto", d.name)

    def test_audit_auto_default_scratch_is_created_and_burned(self) -> None:
        from eidolon.core.supply_index import audit

        seen: dict = {}

        def fake_build(cache_root, **kw):
            seen["root"] = Path(cache_root)
            self.assertTrue(Path(cache_root).is_dir(),
                            "默认 scratch 根未 mkdir 就进 build")
            raise RuntimeError("sentinel-stop-after-scratch")

        fake_cold = mock.Mock(build=fake_build)
        # 不 import 真 cold（会拉 UnityPy，污染 test_text_atlas 的进程级
        # import 卫生断言）；用 sys.modules 注入同形模块。
        with mock.patch.dict(
                "sys.modules",
                {"eidolon.core.supply_index.cold": fake_cold}):
            with self.assertRaisesRegex(RuntimeError, "sentinel-stop"):
                audit.audit_auto(Path("ignored-cache-root"),
                                 game=Path("game-root"), locale="zhcn")
        root = seen["root"]
        self.assertEqual(root.parent, audit._scratch_dir())
        self.assertFalse(root.exists(), f"默认 scratch 用完未焚：{root}")


class AuditOpenBlockPatternsTests(unittest.TestCase):
    """open 拦截游戏文件族扩面（P1-7 返工 R1）：模式集合与 fnmatch 行为钉死。"""

    def test_blocked_pattern_set(self) -> None:
        from eidolon.core.supply_index.audit import _OPEN_BLOCK_GAME_FILES

        for pat in ("*.unity3d", "globalgamemanagers*", "resources.assets*",
                    "*.dll"):
            self.assertIn(pat, _OPEN_BLOCK_GAME_FILES)

    def test_fnmatch_semantics(self) -> None:
        import fnmatch

        from eidolon.core.supply_index.audit import _OPEN_BLOCK_GAME_FILES

        def blocked(name: str) -> bool:
            return any(fnmatch.fnmatch(name.lower(), pat)
                       for pat in _OPEN_BLOCK_GAME_FILES)

        for name in ("a.unity3d", "asset_manifest_zhcn.unity3d",
                     "globalgamemanagers", "globalgamemanagers.assets",
                     "resources.assets", "resources.assets.resS",
                     "Assembly-CSharp.dll", "UnityPlayer.dll"):
            self.assertTrue(blocked(name), name)
        for name in ("index.sqlite", "portrait.png", "current.json",
                     "fontdefs.json", "Atlas.ttf"):
            self.assertFalse(blocked(name), name)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
