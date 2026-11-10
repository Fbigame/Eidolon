"""integration_route_scope — P0-2 route.prewarm 接产品（显式跑；需游戏）。

任务单 0.1.1 §3 判据的产品路径验证：``adapters.CoreRenderPort.preflight``
尾部新增的组合层预热步（``_prewarm_route``）让 fresh cache 首跑只建请求
卡集的 scoped 库，不再触发全量建库（B1 条件实验实测 348.9s / 11,159 包）。

四条判据：

1. **fresh cache 首跑 5 卡**：render 退出 0；preflight 预热建 scoped 库
   （meta ``scope=cards``、bundle 行数 < 1,000 vs 全量 11,159）；墙钟
   < 120s（B1 对照：无预热全量建库 348.9s）；结果 manifest 全 ok；
   EX1_350（dbf 9）sha == Phase 0 spike 冻结值（1x 口径）。
2. **第二次同 cache 再跑**（``--jobs 2``：父进程 prewarm 命中，worker 只
   用 scoped 库）：``route_prewarm_hit`` == 1（route.stats 口径）；不重建
   （meta ``built_at`` 不变）；逐卡 sha 与串行首跑一致。
3. **工作集外卡**：哨兵卡 CS2_182（card ref，不在首跑 5 卡集）同 cache
   渲染成功、sha == 仓冻结哨兵；preflight 预热照常命中（``prewarm_hit``
   == 1）、不重建（``built_at`` 不变）。lazy 补行机制本身由判据 1 承担：
   fresh 首跑渲染需要工作集外的包（工作集=最小 prefab 闭包）→ 渲染期
   ``route_augment_built`` 真发生（实测 ~887 行）且逐卡 sha 仍逐字节
   == 冻结值——补行产物正确的最强证明。
4. **故障回退**：monkeypatch ``route.prewarm`` 抛 OSError → render 仍成功
   （哨兵卡 sha 不变），stderr 可见 ``route prewarm skipped`` WARN。

驱动形态：渲染走 ``eidolon render`` 产品路径，但在**专用 driver 子进程**
内经 ``entry.main`` 驱动（fresh 每跑进程身份干净；``route.stats()`` /
meta 证据由 driver 落 JSON——integration 大扫描同进程身份约束见
integration_render_port 头注，本文件不进程内 main）。回退判据的
``route.prewarm`` 打桩由 driver 读 ``EIDOLON_P02_FAIL_PREWARM`` 完成
（测试进程打桩传不进子进程；driver 是测试专属件，非产品面）。

用法（默认 discover pattern ``test*.py`` 不收集本文件；需游戏 + 渲染
依赖）::

    set EIDOLON_TEST_GAME=<game-install-root>
    .venv-release\\Scripts\\python.exe -m unittest discover -s tests/integration -p 'integration_route_scope.py' -t . -v

scratch 只落 ``build/p02/it_route_scope/<时间戳>/``（已 gitignore）；
缓存/输出目录每跑新建，不清理旧跑（断点留证）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None

OUT_BASE = REPO / "build" / "p02" / "it_route_scope"

# 首跑 5 卡（dbf id；全部 A7/历史对照语料 已证可渲的普通面卡）。
# 哨兵卡 CS2_182 **不在集内**（card ref 形态的工作集外卡——其 prefab 在
# 共享全局包族，补行后同族全覆盖；承担判据 3/4 的渲染正确性锚）。
CARD_DBFS = (9, 40474, 56791, 78325, 78332)
SENTINEL_CARD = "CS2_182"

# 冻结锚（1x 口径 = 产品缺省 antialias off；换游戏版本由上游 re-bless）：
# - CS2_182 哨兵（仓验收判据同值）；
# - EX1_350 dbf 9（Phase 0 spike 冻结 + B1 verify_1x frozen_match=true）。
SENTINEL_CS2_182 = "89306531816a36c7ae0423073943f3996dea6d11488b6288b1c9e4427577d0ba"
FROZEN_EX1_350_1X = "671e19a2188f7126d0627b5a7b2c647cbe53106c49f9916e384213d88892186e"

# driver：fresh 子进程内跑产品 main，落 route.stats() + route.db meta 证据。
# stdin/stdout 语义：stdout 承接计划 manifest（断言可忽略），证据走文件。
_DRIVER = r'''
import json, os, sys, time
from pathlib import Path

evidence = Path(sys.argv[1])
args = sys.argv[2:]

from eidolon.entry import main
from eidolon.core.infra import context, route

if os.environ.get("EIDOLON_P02_FAIL_PREWARM"):
    def _boom(*_a, **_k):
        raise OSError("p02 probe: route.prewarm 人为失败（回退验证）")
    route.prewarm = _boom

t0 = time.perf_counter()
rc = main(args)
elapsed = time.perf_counter() - t0

stats = dict(route.stats())
meta = {}
ctx = context.installed()
if ctx is not None:
    tbl = route.peek_existing(root=ctx.cache_root, mode=ctx.route_mode,
                              data_win=ctx.data_win, version=ctx.version)
    if tbl is not None:
        meta = {k: tbl.meta.get(k)
                for k in ("scope", "built_at", "n_bundles", "n_cabs")}
        meta["route_names"] = len(tbl.names())
        tbl.close()
evidence.write_text(json.dumps(
    {"rc": rc, "elapsed_s": round(elapsed, 2),
     "stats": stats, "meta": meta},
    ensure_ascii=False, indent=1), encoding="utf-8")
sys.exit(rc)
'''


def _result_shas(outdir: Path) -> dict[str, str]:
    """结果 manifest → {input_id: sha256}（只收 ok 卡）。"""
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    return {c["input_id"]: c["sha256"] for c in manifest["cards"] if c.get("ok")}


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class RoutePrewarmProductTests(unittest.TestCase):
    """P0-2 产品路径四判据。方法名 ``test_1_..`` 排序即执行序（共享
    cache/首跑 sha 状态；单跑后序方法会 skipTest 并说明依赖）。"""

    @classmethod
    def setUpClass(cls) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        cls.work = OUT_BASE / f"{stamp}-{os.getpid()}"
        cls.cache = cls.work / "cache"          # 四跑共用；首跑建 scoped 库
        cls.cache.mkdir(parents=True, exist_ok=True)
        cls.shas_run1: dict[str, str] = {}
        cls.built_at_run1: int | None = None

    # ---- driver 调用 ----------------------------------------------------

    def _drive(self, name: str, card_ids: tuple[str, ...], *,
               jobs: int | None = None,
               fail_prewarm: bool = False) -> tuple[subprocess.CompletedProcess, dict]:
        outdir = self.work / name
        evidence = self.work / f"{name}-evidence.json"
        args = [sys.executable, "-c", _DRIVER, str(evidence),
                "render", *card_ids,
                "--game", str(GAME_ROOT),
                "--cache-root", str(self.cache),
                "--outdir", str(outdir)]
        if jobs:
            args += ["--jobs", str(jobs)]
        env = dict(os.environ)
        if fail_prewarm:
            env["EIDOLON_P02_FAIL_PREWARM"] = "1"
        proc = subprocess.run(args, cwd=str(REPO), env=env,
                              capture_output=True, text=True, timeout=1200)
        data = {}
        if evidence.exists():
            data = json.loads(evidence.read_text(encoding="utf-8"))
        return proc, data

    def _assert_all_ok(self, outdir: Path) -> None:
        manifest = json.loads(
            (outdir / "manifest.json").read_text(encoding="utf-8"))
        bad = [c["input_id"] for c in manifest["cards"] if not c.get("ok")]
        self.assertEqual(bad, [], f"结果 manifest 有非 ok 卡: {bad}")

    # ---- 1) fresh cache 首跑：scoped 建库 -------------------------------

    def test_1_fresh_cache_scoped_build(self) -> None:
        proc, data = self._drive("run1-fresh", tuple(str(d) for d in CARD_DBFS))
        self.assertEqual(proc.returncode, 0,
                         f"render 失败：{proc.stderr[-800:]}")
        self.assertEqual(data.get("rc"), 0)
        # 墙钟远小于全量建库（B1 条件实验 348.9s；判据 < 120s）。
        self.assertLess(data.get("elapsed_s", 1e9), 120,
                        f"首跑墙钟 {data.get('elapsed_s')}s 疑似全量建库")
        meta = data.get("meta", {})
        self.assertEqual(meta.get("scope"), "cards",
                         f"route.db 非 scoped：meta={meta}")
        names = meta.get("route_names", 0)
        self.assertLess(names, 1_000,
                        f"scoped 库 {names} 行 ≥ 1000，疑似全量（全量 11,159）")
        # fresh → prewarm 建库而非命中；预热只建一次。工作集=最小 prefab
        # 闭包，渲染所需的其余包在首跑经 lazy 补行（augment）进来——补行
        # 必真发生，且下面 EX1_350 冻结 sha 证明补行产物逐字节正确。
        stats = data.get("stats", {})
        self.assertEqual(stats.get("route_prewarm_hit", 0), 0,
                         f"fresh cache 不该命中：stats={stats}")
        self.assertEqual(stats.get("route_built"), 1,
                         f"预热情景应恰好建一次库：stats={stats}")
        self.assertGreaterEqual(stats.get("route_augment_built", 0), 1,
                                f"首跑渲染未走缺行 lazy 补行：stats={stats}")
        self.assertGreater(meta.get("n_bundles", 0), 0, "scoped 库空")
        outdir = self.work / "run1-fresh"
        self._assert_all_ok(outdir)
        type(self).shas_run1 = _result_shas(outdir)
        self.assertEqual(len(type(self).shas_run1), len(CARD_DBFS))
        # 冻结锚：EX1_350（dbf 9）1x sha（Phase 0 spike 冻结；B1 verify_1x
        # frozen_match=true 同值）。
        self.assertEqual(type(self).shas_run1.get("9"), FROZEN_EX1_350_1X)
        type(self).built_at_run1 = meta.get("built_at")
        self.assertIsNotNone(type(self).built_at_run1)

    # ---- 2) 复跑：prewarm 命中 + 不重建 + sha 一致（jobs2 worker 路）---

    def test_2_rerun_prewarm_hit_jobs2(self) -> None:
        if not type(self).shas_run1:
            self.skipTest("依赖 test_1_fresh_cache_scoped_build 先跑（整文件显式运行）")
        proc, data = self._drive("run2-jobs2", tuple(str(d) for d in CARD_DBFS),
                                 jobs=2)
        self.assertEqual(proc.returncode, 0,
                         f"render 失败：{proc.stderr[-800:]}")
        stats = data.get("stats", {})
        # 复跑 preflight 预热命中既有 scoped 库（stats 口径 +1；父进程命中，
        # worker 只消费不建库）。
        self.assertEqual(stats.get("route_prewarm_hit"), 1,
                         f"复跑应恰命中一次：stats={stats}")
        self.assertEqual(stats.get("route_built", 0), 0,
                         f"复跑发生了重建：stats={stats}")
        meta = data.get("meta", {})
        self.assertEqual(meta.get("built_at"), type(self).built_at_run1,
                         "built_at 变了 = 复跑重建（违反命中语义）")
        self.assertEqual(meta.get("scope"), "cards")
        outdir = self.work / "run2-jobs2"
        self._assert_all_ok(outdir)
        # jobs2（worker 池）与串行首跑逐卡 sha 一致。
        self.assertEqual(_result_shas(outdir), type(self).shas_run1,
                         "jobs2 与串行首跑 sha 不一致")

    # ---- 3) 工作集外卡：预热命中 + 哨兵 sha 正确 ------------------------

    def test_3_out_of_set_card_sentinel(self) -> None:
        if type(self).built_at_run1 is None:
            self.skipTest("依赖 test_1_fresh_cache_scoped_build 先跑（整文件显式运行）")
        proc, data = self._drive("run3-outofset", (SENTINEL_CARD,))
        self.assertEqual(proc.returncode, 0,
                         f"render 失败：{proc.stderr[-800:]}")
        stats = data.get("stats", {})
        # 工作集外卡照常预热命中 + 不重建（缺行走补行/惰性兜底，绝不假命中）。
        self.assertEqual(stats.get("route_prewarm_hit"), 1,
                         f"预热应命中既有 scoped 库：stats={stats}")
        self.assertEqual(stats.get("route_built", 0), 0,
                         f"工作集外卡触发了重建：stats={stats}")
        meta = data.get("meta", {})
        self.assertEqual(meta.get("built_at"), type(self).built_at_run1,
                         "built_at 变了 = 重建（违反 scoped 命中语义）")
        outdir = self.work / "run3-outofset"
        self._assert_all_ok(outdir)
        self.assertEqual(_result_shas(outdir).get(SENTINEL_CARD),
                         SENTINEL_CS2_182, "工作集外哨兵卡 sha 不符")

    # ---- 4) 故障回退：prewarm 抛异常不阻塞渲染 --------------------------

    def test_4_prewarm_failure_fallback(self) -> None:
        if type(self).built_at_run1 is None:
            self.skipTest("依赖 test_1_fresh_cache_scoped_build 先跑（整文件显式"
                          "运行；否则 fresh cache 回退会触发全量建库 ~350s）")
        proc, data = self._drive("run4-fallback", (SENTINEL_CARD,),
                                 fail_prewarm=True)
        self.assertEqual(proc.returncode, 0,
                         f"prewarm 失败后 render 应仍成功：{proc.stderr[-800:]}")
        self.assertIn("route prewarm skipped", proc.stderr,
                      "回退 WARN 不可见")
        outdir = self.work / "run4-fallback"
        self._assert_all_ok(outdir)
        self.assertEqual(_result_shas(outdir).get(SENTINEL_CARD),
                         SENTINEL_CS2_182, "回退渲染哨兵 sha 不符")


if __name__ == "__main__":
    unittest.main(verbosity=2)
