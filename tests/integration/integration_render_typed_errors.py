"""integration_render_typed_errors — B2 判据（真实卡采样；显式跑，需游戏安装）。

任务单 §10 B2：``render_failed`` 残留裸 ``ValueError`` → typed error；
**判据 = 采样卡全 typed**（资产缺失/游戏数据不在预期形态类不再落
``render_failed``(RENDER 1) 的裸 ValueError 形状）。

采样面（build/phase1/b2/ 有 before/after 全套证据）：

* 失败样本：``DMF_254t5``（BC7 肖像 ``HS21-109``，fmt=25，mip_count=10）——
  supply_index canonical 账（36,373 卡全普查）``mip_unsupported`` 唯一在案卡，
  ``decode_errors_json`` 全域 count=0（其余失败面为空）；plain 与 GOLDEN 两种
  形态各采一次；
* 成功控制：``CS2_182``（哨兵 sha 逐字节钉住）、``EX1_350``（冻结 sha）、
  ``BG27_822_G``（金卡控制）、``HERO_05``（hero_style 控制,TOML 面）。

驱动方式 = **产品路径**（子进程 ``python -m eidolon render``，CLI 与 TOML 两种
输入面各一批）；断言读结果 manifest（``out_dir/manifest.json``）：

1. 失败卡行：``error.kind == "environment"``、``error.code ==
   "asset_format_unsupported"``、path=``bundle::纹理名``、message 带
   ``fmt=25`` 与 ``card_id=DMF_254t5``、cause 非空——且**全采样**无任何
   ``code=="render_failed"`` 且 ``cause`` 以 ``ValueError`` 开头的行（裸
   ValueError 残留判据）；
2. 退出码：两批都为 3（ENV 优先粗分类；typed 前 DMF_254t5 是 1）；
3. 成功控制卡 ``ok=true``；CS2_182 sha 逐字节等于哨兵
   ``89306531…7577d0ba``（成功卡渲染行为逐位不变的机器证明之一）。

用法::

    set EIDOLON_TEST_GAME=D:\\game\\Hearthstone
    .venv-release\\Scripts\\python.exe -m unittest discover -s tests/integration -p integration_render_typed_errors.py -t . -v

证据落盘：``build/phase1/b2/b2-evidence.json``（每卡 before 断言输入 +
after 实测行 + 退出码）。默认 discover（pattern ``test*.py``）不收集本文件。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT: Path | None = Path(_game_env) if _game_env else None

_cache_env = os.environ.get("EIDOLON_TEST_CACHE", "").strip()
CACHE_ROOT: Path = (Path(_cache_env) if _cache_env
                    else REPO / "build" / "integration_supply_cache")

OUT_DIR = REPO / "build" / "phase1" / "b2"

CS2_182_SENTINEL = "89306531816a36c7ae0423073943f3996dea6d11488b6288b1c9e4427577d0ba"

FAIL_ID = "DMF_254t5"
CONTROLS_CLI = ("CS2_182", "EX1_350")

TOML_TEMPLATE = """format_version = 1
out_dir = "."

[[cards]]
id = "{fail_id}"
premium = "GOLDEN"

[[cards]]
id = "BG27_822_G"

[[cards]]
id = "HERO_05"
hero_style = true
"""


def _run_cli(args: list[str], manifest_path: Path) -> tuple[int, dict]:
    """子进程产品路径：``python -m eidolon render ...`` → (exit, 结果 manifest)。

    ``manifest_path`` 由调用方按输入面显式给（CLI=--outdir 值；TOML=out_dir），
    不在 args 里猜。"""
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "eidolon", "render", *args],
        capture_output=True, text=True, cwd=str(REPO), timeout=1200,
    )
    if not manifest_path.exists():
        raise AssertionError(f"产品路径未落结果 manifest：{manifest_path}\n"
                             f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}")
    return proc.returncode, json.loads(manifest_path.read_text(encoding="utf-8"))


def _typed_failure_shape(row: dict) -> dict:
    """失败卡行 → 断言输入的实测形状（evidence 用）。"""
    err = row.get("error") or {}
    return {"ok": row.get("ok"), "kind": err.get("kind"), "code": err.get("code"),
            "path": err.get("path"), "message": err.get("message"),
            "hint": err.get("hint"), "cause": err.get("cause")}


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class RenderTypedErrorsTests(unittest.TestCase):
    """B2 判据：真实卡采样经产品路径逐卡全 typed。"""

    @classmethod
    def setUpClass(cls) -> None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        cls.evidence: dict = {"fail_id": FAIL_ID, "sentinel": CS2_182_SENTINEL,
                              "batches": []}

    def tearDown(self) -> None:
        (OUT_DIR / "b2-evidence.json").write_text(
            json.dumps(self.evidence, ensure_ascii=False, indent=1),
            encoding="utf-8")

    # ---- 共享断言面 -----------------------------------------------------

    def _assert_no_bare_valueerror(self, manifest: dict, batch: str) -> None:
        """全采样判据：无任何失败行是「render_failed + 裸 ValueError cause」。"""
        offenders = []
        for row in manifest.get("cards", []):
            if row.get("ok"):
                continue
            err = row.get("error") or {}
            if err.get("code") == "render_failed" and \
                    str(err.get("cause", "")).startswith("ValueError"):
                offenders.append(f"{row.get('input_id')}: {err.get('cause')}")
        self.assertEqual(offenders, [], f"{batch}: 裸 ValueError 残留（B2 判据红）")

    def _assert_dmf_typed(self, manifest: dict, batch: str) -> None:
        rows = {r["input_id"]: r for r in manifest.get("cards", [])}
        row = rows.get(FAIL_ID)
        self.assertIsNotNone(row, f"{batch}: 缺 {FAIL_ID} 行")
        self.assertFalse(row["ok"], f"{batch}: {FAIL_ID} 应失败（live 现状不变）")
        err = row["error"]
        self.assertEqual(err["kind"], "environment", f"{batch}: kind 面红")
        self.assertEqual(err["code"], "asset_format_unsupported",
                         f"{batch}: code 面红（typed 收口判据）")
        self.assertTrue(err["path"].endswith("::HS21-109"),
                        f"{batch}: path 应为 bundle::纹理名（资产身份）：{err['path']}")
        self.assertIn("fmt=25", err["message"], f"{batch}: message 缺格式根因")
        self.assertIn(f"card_id={FAIL_ID}", err["message"],
                      f"{batch}: message 缺卡 id")
        self.assertTrue(err["cause"], f"{batch}: cause 空")
        self.evidence["batches"].append(
            {"batch": batch, "exit": self._last_exit,
             "cards": {r["input_id"]: _typed_failure_shape(r)
                       for r in manifest.get("cards", [])}})

    # ---- 批 1：CLI 面（plain 失败样本 + 哨兵/冻结控制） ----------------

    def test_cli_batch_plain_sample_typed_and_sentinel_stable(self) -> None:
        out = OUT_DIR / "cli-batch"
        out.mkdir(parents=True, exist_ok=True)
        exit_code, manifest = _run_cli(
            [FAIL_ID, *CONTROLS_CLI, "--game", str(GAME_ROOT),
             "--cache-root", str(CACHE_ROOT), "--outdir", str(out)],
            manifest_path=out / "manifest.json")
        self._last_exit = exit_code
        self.assertEqual(exit_code, 3,
                         f"typed 后 DMF_254t5 批应 ENV 3（typed 前是 1）；实得 {exit_code}")
        rows = {r["input_id"]: r for r in manifest["cards"]}
        self._assert_dmf_typed(manifest, "cli-plain")
        for cid in CONTROLS_CLI:
            self.assertTrue(rows[cid]["ok"], f"{cid} 控制卡不应失败")
        self.assertEqual(rows["CS2_182"]["sha256"], CS2_182_SENTINEL,
                         "CS2_182 哨兵 sha 漂移——错误重构不得动成功路径")
        self._assert_no_bare_valueerror(manifest, "cli-plain")

    # ---- 批 2：TOML 面（GOLDEN 失败样本 + 金卡/hero 控制） -------------

    def test_toml_batch_golden_sample_typed(self) -> None:
        out = OUT_DIR / "toml-batch"
        out.mkdir(parents=True, exist_ok=True)
        toml = out / "batch.toml"
        toml.write_text(TOML_TEMPLATE.format(fail_id=FAIL_ID), encoding="utf-8")
        exit_code, manifest = _run_cli(
            ["--toml", str(toml), "--game", str(GAME_ROOT),
             "--cache-root", str(CACHE_ROOT)],
            manifest_path=out / "manifest.json")
        self._last_exit = exit_code
        self.assertEqual(exit_code, 3, f"GOLDEN 批应 ENV 3；实得 {exit_code}")
        rows = {r["input_id"]: r for r in manifest["cards"]}
        self._assert_dmf_typed(manifest, "toml-golden")
        self.assertTrue(rows["BG27_822_G"]["ok"], "金卡控制不应失败")
        self.assertTrue(rows["HERO_05"]["ok"], "hero 控制不应失败")
        self._assert_no_bare_valueerror(manifest, "toml-golden")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
