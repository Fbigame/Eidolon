"""core/render/api 单测（§7.3/§7.8；只测 _atomic_render / _render_one /
_classify_card_failure / _warnings_from 的 fake 注入面）。

**默认不调 ``api.render`` 全链**：它函数体内 import ``context``/``dbf``（需
真实 ctx+dbf 会话），install 分支归 integration。``--jobs`` 进程池等价同样
归 integration。唯一例外=串行分支 font_dirs 注入（P1-4）：cards 为空 +
ctx/dbf 桩 + glyph_supply 打点，不触真实渲染链。
"""

from __future__ import annotations

import contextlib
import dataclasses
import errno
import hashlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from eidolon.contracts import (
    CardRef,
    EnvironmentUnavailable,
    GameContext,
    InputRejected,
    Problem,
    ProblemKind,
    RenderCard,
    RenderedCard,
    RenderFailure,
    RenderRequest,
)
from eidolon.core.infra.errors import (
    GameAssetFormatUnsupported,
    GameAssetMissing,
    WriteFailed,
)
from eidolon.core.render.api import (
    _atomic_render,
    _bundle_asset_classes,
    _classify_card_failure,
    _merge_warnings,
    _render_one,
    _warnings_from,
    render,
    resolve_dbf_id,
)
from eidolon.core.render.params import PRODUCT_SESSION_T

from tests.core.test_card_overrides import TAGS, FakeCard, fake_constants


@dataclasses.dataclass
class FakeCfg:
    """``dataclasses.replace`` 可用的最小 cfg 替身（api 用 replace 改它）。"""

    use_bg_style: "bool | None" = None
    supersample: int = 1
    name: str = "fake"


class FakeBundleBlockCorrupt(RuntimeError):
    """``BundleBlockCorruptError`` 替身（不 import UnityPy 链——tests/core 纪律）。"""


class FakeBundleContentMismatch(RuntimeError):
    """``BundleContentMismatch`` 替身（同上）。"""


FakeBundleBlockCorrupt.__name__ = "BundleBlockCorruptError"
FakeBundleContentMismatch.__name__ = "BundleContentMismatch"


class _DbfSession:
    """dbf 会话替身（duck type：只吃 card_id_to_dbf）。"""

    def __init__(self, mapping: dict[str, int]) -> None:
        self.card_id_to_dbf = mapping


@contextlib.contextmanager
def _dbf_stub(session):
    """``sys.modules`` 注入 dbf 桩（真件顶层 import UnityPy——tests/core 纪律
    禁拖；seams 守卫以 sys.modules 全局断言，桩保证不污染）。

    退场时剥掉 parent 包上被 import 系统缓存的桩属性，防 ``from
    eidolon.core.infra import dbf`` 的 getattr 捷径跨用例漏桩。"""
    import eidolon.core.infra as infra_pkg

    had_attr = hasattr(infra_pkg, "dbf")
    stub = types.ModuleType("eidolon.core.infra.dbf")
    stub.default_dbf = lambda: session            # resolve_dbf_id 消费
    stub.installed_default = lambda: session
    stub.install_default = lambda module: session
    stub.reset_default = lambda: None
    with mock.patch.dict(sys.modules, {"eidolon.core.infra.dbf": stub}):
        try:
            yield stub
        finally:
            if not had_attr and getattr(infra_pkg, "dbf", None) is stub:
                delattr(infra_pkg, "dbf")


def render_card(ref=None, **overrides) -> RenderCard:
    return RenderCard(ref=ref or CardRef("dbf", 8), out_path=Path("o.png"),
                      overrides=overrides)


def sha_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# _atomic_render（§7.3 docstring 语义）
# ---------------------------------------------------------------------------

class AtomicRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "a.png"

    def tmp_files(self) -> list[str]:
        return sorted(p.name for p in self.dir.iterdir()
                      if p.name != self.out.name)

    def test_success_replaces_and_hashes(self) -> None:
        payload = b"PNG-BYTES-0"
        def render(tmp_path: Path) -> dict:
            tmp_path.write_bytes(payload)
            return {"log": {}}

        sha, result = _atomic_render(self.out, render)
        self.assertEqual(sha, sha_of(payload))
        self.assertEqual(self.out.read_bytes(), payload)
        self.assertEqual(result, {"log": {}})
        self.assertEqual(self.tmp_files(), [])   # 无 tmp 残留

    def test_callable_error_cleans_tmp_and_reraises(self) -> None:
        def render(tmp_path: Path) -> None:
            tmp_path.write_bytes(b"partial")
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            _atomic_render(self.out, render)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.tmp_files(), [])

    def test_base_exception_also_cleans(self) -> None:
        def render(tmp_path: Path) -> None:
            tmp_path.write_bytes(b"x")
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            _atomic_render(self.out, render)
        self.assertEqual(self.tmp_files(), [])

    def test_callable_oserror_write_errno_wrapped(self) -> None:
        def render(tmp_path: Path) -> None:
            raise OSError(errno.ENOSPC, "no space", str(tmp_path))

        with self.assertRaises(EnvironmentUnavailable) as ctx:
            _atomic_render(self.out, render)
        self.assertEqual(ctx.exception.problem.code, "write_failed")
        self.assertEqual(self.tmp_files(), [])

    def test_callable_oserror_filename_under_outdir_wrapped(self) -> None:
        victim = self.out.parent / "other.bin"   # 在 out_path.parent 下
        def render(tmp_path: Path) -> None:
            raise OSError(errno.EIO, "io", str(victim))

        with self.assertRaises(EnvironmentUnavailable) as ctx:
            _atomic_render(self.out, render)
        self.assertEqual(ctx.exception.problem.code, "write_failed")

    def test_callable_oserror_elsewhere_reraised(self) -> None:
        def render(tmp_path: Path) -> None:
            raise OSError(errno.EIO, "io", "D:/somewhere/else.bin")

        with self.assertRaises(OSError) as ctx:
            _atomic_render(self.out, render)
        self.assertNotIsInstance(ctx.exception, EnvironmentUnavailable)
        self.assertEqual(ctx.exception.errno, errno.EIO)

    def test_mkstemp_failure_wrapped(self) -> None:
        with mock.patch("tempfile.mkstemp",
                        side_effect=OSError(errno.EROFS, "read-only")):
            with self.assertRaises(EnvironmentUnavailable) as ctx:
                _atomic_render(self.out, lambda p: None)
        self.assertEqual(ctx.exception.problem.code, "write_failed")

    def test_replace_failure_wrapped(self) -> None:
        def render(tmp_path: Path) -> None:
            tmp_path.write_bytes(b"x")

        def broken_replace(src, dst):
            raise OSError(errno.EACCES, "denied", str(dst))

        with mock.patch("eidolon.core.render.api.os.replace", broken_replace):
            with self.assertRaises(EnvironmentUnavailable) as ctx:
                _atomic_render(self.out, render)
        self.assertEqual(ctx.exception.problem.code, "write_failed")
        self.assertEqual(self.tmp_files(), [])

    def test_close_failure_cleans_tmp_and_wraps(self) -> None:
        # P1-5：句柄 close 报错但 fd 已释放（POSIX EINTR 同象）→ best-effort
        # 删 mkstemp 留下的空 tmp → WriteFailed；任何路径不留 tmp。
        real_close = os.close

        def close_then_fail(fd):
            real_close(fd)                     # 先真关闭，再报失败
            raise OSError(errno.EINTR, "interrupted")

        with mock.patch("os.close", side_effect=close_then_fail):
            with self.assertRaises(EnvironmentUnavailable) as ctx:
                _atomic_render(self.out, lambda p: None)
        self.assertEqual(ctx.exception.problem.code, "write_failed")
        self.assertIn("句柄关闭失败", ctx.exception.problem.message)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.tmp_files(), [])   # 无空 tmp 残留

    def test_close_failure_stuck_handle_still_wraps(self) -> None:
        # P1-5 尽力而为边界：句柄真卡死（Windows 独占锁，unlink 吃共享冲突）
        # → 清理失败被吞、不掩盖原异常，WriteFailed 照抛（残留由 OS 句柄
        # 生命周期兜底——进程退出即释放）。测末显式释放真句柄防 tmp 清理炸。
        real_close = os.close
        stuck: list[int] = []

        def fail_close(fd):
            stuck.append(fd)
            raise OSError(errno.EIO, "close failed")

        with mock.patch("os.close", side_effect=fail_close):
            with self.assertRaises(EnvironmentUnavailable) as ctx:
                _atomic_render(self.out, lambda p: None)
        real_close(stuck[0])               # 释放真实句柄，防 TemporaryDirectory 清理 WinError 32
        self.assertEqual(ctx.exception.problem.code, "write_failed")
        self.assertIn("句柄关闭失败", ctx.exception.problem.message)


# ---------------------------------------------------------------------------
# _render_one（fake 注入面）
# ---------------------------------------------------------------------------

class RenderOneTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "a.png"
        self.constants = fake_constants()
        self.calls: dict = {}

    def fake_render_fn(self, card, cfg, **kwargs):
        self.calls["card"] = card
        self.calls["cfg"] = cfg
        self.calls["kwargs"] = kwargs
        kwargs["out_png"].write_bytes(b"PNG-DATA")
        return {"log": {}}

    def fake_resolve_form(self, card, form):
        self.calls["form"] = form
        return False, "PLAY"

    def run_one(self, rc: RenderCard, *, antialias=False, **fns):
        return _render_one(rc, antialias=antialias,
                           card_factory=lambda dbf_id: FakeCard(),
                           constants_factory=lambda: self.constants,
                           render_fn=self.fake_render_fn,
                           resolve_form_fn=self.fake_resolve_form,
                           cfg_factory=FakeCfg, **fns)

    def test_success_fields(self) -> None:
        rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out, overrides={"cost": 9})
        outcome = self.run_one(rc, antialias=False)
        self.assertIsInstance(outcome, RenderedCard)
        self.assertEqual(outcome.sha256, sha_of(b"PNG-DATA"))
        self.assertEqual(outcome.path, self.out)
        self.assertGreaterEqual(outcome.elapsed_ms, 0)
        self.assertEqual(outcome.warnings, ())
        # 覆盖已打在 card 上（card_overrides.apply 经 fake constants）
        self.assertEqual(self.calls["card"].tags[TAGS["COST"]], 9)
        # render_fn kwargs 与 form 解码
        self.assertEqual(self.calls["kwargs"]["zone"], "PLAY")
        self.assertEqual(self.calls["kwargs"]["t_phase"], PRODUCT_SESSION_T)
        self.assertEqual(self.calls["kwargs"]["notext"], False)
        self.assertEqual(self.calls["kwargs"]["textonly"], False)
        self.assertIsNone(self.calls["kwargs"]["session_time"])
        self.assertEqual(self.calls["form"], "plain")

    def test_cfg_canonical_replace_semantics(self) -> None:
        rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out)
        outcome = self.run_one(rc, antialias=False)
        self.assertIsInstance(outcome, RenderedCard)
        cfg = self.calls["cfg"]
        self.assertIsInstance(cfg, FakeCfg)          # cfg_factory 后 replace
        self.assertEqual(cfg.use_bg_style, False)    # resolve_form_fn 的返回值
        self.assertEqual(cfg.supersample, 1)         # antialias=False → 1
        self.assertEqual(cfg.name, "eidolon")        # 必须 canonical 后 replace 出的名

    def test_resolve_form_return_forwarded_to_render(self) -> None:
        rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out)
        outcome = _render_one(rc, antialias=False,
                              card_factory=lambda dbf_id: FakeCard(),
                              constants_factory=lambda: self.constants,
                              render_fn=self.fake_render_fn,
                              resolve_form_fn=lambda card, form: (True, "GRAVEYARD"),
                              cfg_factory=FakeCfg)
        self.assertIsInstance(outcome, RenderedCard)
        self.assertIs(self.calls["cfg"].use_bg_style, True)
        self.assertEqual(self.calls["kwargs"]["zone"], "GRAVEYARD")

    def test_antialias_true_sets_supersample_4(self) -> None:
        rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out)
        outcome = self.run_one(rc, antialias=True)
        self.assertIsInstance(outcome, RenderedCard)
        self.assertEqual(self.calls["cfg"].supersample, 4)

    def test_session_t_passthrough_and_default(self) -> None:
        rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out, session_t=0.1472)
        self.assertIsInstance(self.run_one(rc), RenderedCard)
        self.assertEqual(self.calls["kwargs"]["t_phase"], 0.1472)
        rc_default = RenderCard(ref=CardRef("dbf", 8), out_path=self.out)
        self.assertIsInstance(self.run_one(rc_default), RenderedCard)
        self.assertEqual(self.calls["kwargs"]["t_phase"], PRODUCT_SESSION_T)
        self.assertEqual(PRODUCT_SESSION_T, 0.0)

    def test_form_decode_hero_bg_plain(self) -> None:
        for style, expected in (({"hero_style": True}, "hero"),
                                ({"bg_style": True}, "bg"),
                                ({}, "plain")):
            with self.subTest(style=style):
                self.calls.clear()
                rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out, **style)
                outcome = self.run_one(rc)
                self.assertIsInstance(outcome, RenderedCard)
                self.assertEqual(self.calls["form"], expected)

    def test_hero_and_bg_together_is_render_failure(self) -> None:
        rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out,
                        hero_style=True, bg_style=True)
        called = []
        outcome = _render_one(rc, antialias=False,
                              card_factory=lambda dbf_id: FakeCard(),
                              constants_factory=lambda: self.constants,
                              render_fn=lambda *a, **k: called.append(1),
                              resolve_form_fn=lambda card, form: (False, "PLAY"),
                              cfg_factory=FakeCfg)
        self.assertIsInstance(outcome, RenderFailure)
        self.assertEqual(outcome.problem.kind, ProblemKind.RENDER)
        self.assertEqual(outcome.problem.code, "render_failed")
        self.assertEqual(called, [])   # 渲染未发生

    def test_value_error_becomes_render_failed(self) -> None:
        def bad_render(card, cfg, **kwargs):
            raise ValueError("覆盖无写点")

        rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out)
        outcome = _render_one(rc, antialias=False,
                              card_factory=lambda dbf_id: FakeCard(),
                              constants_factory=lambda: self.constants,
                              render_fn=bad_render,
                              resolve_form_fn=lambda card, form: (False, "PLAY"),
                              cfg_factory=FakeCfg)
        self.assertIsInstance(outcome, RenderFailure)
        self.assertEqual(outcome.problem.kind, ProblemKind.RENDER)
        self.assertEqual(outcome.problem.code, "render_failed")
        self.assertEqual(outcome.problem.cause, "ValueError: 覆盖无写点")

    def test_environment_unavailable_keeps_problem(self) -> None:
        env_problem = Problem(ProblemKind.ENVIRONMENT, "asset_missing_in_game",
                              "p", "m")
        def bad_render(card, cfg, **kwargs):
            raise EnvironmentUnavailable(env_problem)

        rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out)
        outcome = _render_one(rc, antialias=False,
                              card_factory=lambda dbf_id: FakeCard(),
                              constants_factory=lambda: self.constants,
                              render_fn=bad_render,
                              resolve_form_fn=lambda card, form: (False, "PLAY"),
                              cfg_factory=FakeCfg)
        self.assertIsInstance(outcome, RenderFailure)
        self.assertIs(outcome.problem, env_problem)

    def test_input_rejected_post_preflight_is_render_failed(self) -> None:
        def bad_render(card, cfg, **kwargs):
            raise InputRejected(Problem(ProblemKind.INPUT, "enum", "k", "m"))

        rc = RenderCard(ref=CardRef("dbf", 8), out_path=self.out)
        outcome = _render_one(rc, antialias=False,
                              card_factory=lambda dbf_id: FakeCard(),
                              constants_factory=lambda: self.constants,
                              render_fn=bad_render,
                              resolve_form_fn=lambda card, form: (False, "PLAY"),
                              cfg_factory=FakeCfg)
        self.assertIsInstance(outcome, RenderFailure)
        self.assertEqual(outcome.problem.kind, ProblemKind.RENDER)
        self.assertEqual(outcome.problem.code, "render_failed")

    def test_unknown_card_ref_uses_default_dbf(self) -> None:
        with _dbf_stub(_DbfSession({"cs2_182": 8})):
            self.assertEqual(resolve_dbf_id(CardRef("card", "CS2_182")), 8)  # casefold
            self.assertIsNone(resolve_dbf_id(CardRef("card", "nope")))
            self.assertEqual(resolve_dbf_id(CardRef("dbf", 1121)), 1121)
            rc = RenderCard(ref=CardRef("card", "nope"), out_path=self.out)
            outcome = _render_one(rc, antialias=False,
                                  card_factory=lambda dbf_id: FakeCard(),
                                  constants_factory=lambda: self.constants,
                                  render_fn=self.fake_render_fn,
                                  resolve_form_fn=lambda card, form: (False, "PLAY"),
                                  cfg_factory=FakeCfg)
        self.assertIsInstance(outcome, RenderFailure)
        self.assertEqual(outcome.problem.code, "render_failed")
        self.assertIn("unknown dbf id", outcome.problem.cause)


# ---------------------------------------------------------------------------
# render 串行分支（P1-4：font_dirs 注入与 worker 对齐；ctx/dbf 桩，零渲染链）
# ---------------------------------------------------------------------------

class RenderSerialFontDirsTests(unittest.TestCase):
    """串行分支装 font_dirs（P1-4）：api 函数体内 import glyph_supply →
    patch 模块属性即可；空 cards 走串行分支但零卡渲染，不触真实链。"""

    def test_serial_branch_installs_font_dirs(self) -> None:
        game = GameContext(root=Path("game-root"), cache_root=Path("C:/cache"))
        request = RenderRequest(
            cards=(), out_dir=Path("o"), jobs=1, game=game,
            font_dirs=(Path("D:/fonts/a"), Path("D:/fonts/b")))
        calls: list[tuple[tuple[Path, ...], dict]] = []

        def record(dirs, *, cache_dir=None):
            calls.append((tuple(Path(d) for d in dirs), {"cache_dir": cache_dir}))

        with mock.patch("eidolon.core.infra.context.install"), \
                _dbf_stub(_DbfSession({})), \
                mock.patch("eidolon.core.render.text.glyph_supply.install_font_dirs",
                           side_effect=record):
            report = render(request)
        # 与 _worker_init 同序同参：dirs 原样 + cache_dir=ctx.cache_root/"fonts"
        self.assertEqual(calls, [
            ((Path("D:/fonts/a"), Path("D:/fonts/b")),
             {"cache_dir": Path("C:/cache") / "fonts"}),
        ])
        self.assertEqual(report.rendered, ())
        self.assertEqual(report.failures, ())
        self.assertEqual(report.warnings, ())


# ---------------------------------------------------------------------------
# _classify_card_failure（§7.8 表逐行）
# ---------------------------------------------------------------------------

class ClassifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rc = RenderCard(ref=CardRef("dbf", 8), out_path=Path("out/a.png"))

    def classify(self, exc: Exception) -> Problem:
        return _classify_card_failure(exc, self.rc)

    def test_environment_unavailable_problem_carried_as_is(self) -> None:
        problem = Problem(ProblemKind.ENVIRONMENT, "dbf_unreadable", "p", "m")
        result = self.classify(EnvironmentUnavailable(problem))
        self.assertIs(result, problem)

    def test_game_asset_missing(self) -> None:
        exc = GameAssetMissing(path="x", message="无对象")
        result = self.classify(exc)
        self.assertEqual(result.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(result.code, "asset_missing_in_game")
        self.assertIs(result, exc.problem)

    def test_write_failed(self) -> None:
        exc = WriteFailed(path="x", message="满")
        result = self.classify(exc)
        self.assertEqual(result.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(result.code, "write_failed")

    def test_game_asset_format_unsupported(self) -> None:
        # B2 收口：格式域外（BC7 肖像链）typed 穿出，ENV 3（不再落
        # ValueError → render_failed 的 1）。
        exc = GameAssetFormatUnsupported(path="b::tex",
                                         message="asset_format_unsupported: fmt=25",
                                         cause="TextureFormat 25")
        result = self.classify(exc)
        self.assertIs(result, exc.problem)
        self.assertEqual(result.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(result.code, "asset_format_unsupported")

    def test_bare_valueerror_still_render_failed(self) -> None:
        # 非资产类裸 ValueError（真编程/契约错误）映射不变——B2 只收口资产类。
        result = self.classify(ValueError("supersample 只支持 1 或 4"))
        self.assertEqual(result.kind, ProblemKind.RENDER)
        self.assertEqual(result.code, "render_failed")
        self.assertEqual(result.cause, "ValueError: supersample 只支持 1 或 4")

    def test_bundle_block_corrupt(self) -> None:
        # 不 import 真类（bundle_lazy 顶层吃 UnityPy；tests/core 纪律）——
        # 以 _bundle_asset_classes 注入缝 + 类名预筛伪造；真类场景等价
        # （名字/继承面同形，真 isinstance 在 api 内发生）。
        exc = FakeBundleBlockCorrupt("b.unity3d 块 1")
        with mock.patch("eidolon.core.render.api._bundle_asset_classes",
                        return_value=(FakeBundleBlockCorrupt,
                                      FakeBundleContentMismatch)):
            result = self.classify(exc)
        self.assertEqual(result.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(result.code, "asset_missing_in_game")
        self.assertEqual(result.path, str(self.rc.out_path))

    def test_bundle_content_mismatch(self) -> None:
        with mock.patch("eidolon.core.render.api._bundle_asset_classes",
                        return_value=(FakeBundleBlockCorrupt,
                                      FakeBundleContentMismatch)):
            result = self.classify(FakeBundleContentMismatch("md5 不符"))
        self.assertEqual(result.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(result.code, "asset_missing_in_game")

    def test_bundle_name_prefilter_does_not_alias_other_errors(self) -> None:
        # 预筛键=类名：非 bundle 类名不触发 asset_missing_in_game（哪怕同形异常）。
        result = self.classify(RuntimeError("BundleBlockCorruptError 字样"))
        self.assertEqual(result.kind, ProblemKind.RENDER)
        self.assertEqual(result.code, "render_failed")

    def test_file_not_found_under_data_win_is_asset_missing(self) -> None:
        data_win = Path("D:/Games/hs/Data/Win")
        exc = FileNotFoundError(errno.ENOENT, "no file",
                                str(data_win / "textures" / "a.blp"))
        with mock.patch("eidolon.core.render.api._installed_data_win",
                        return_value=data_win):
            result = self.classify(exc)
        self.assertEqual(result.kind, ProblemKind.ENVIRONMENT)
        self.assertEqual(result.code, "asset_missing_in_game")
        self.assertEqual(result.path, str(data_win / "textures" / "a.blp"))

    def test_file_not_found_outside_data_win_is_render_failed(self) -> None:
        exc = FileNotFoundError(errno.ENOENT, "no file", "D:/elsewhere/a.bin")
        with mock.patch("eidolon.core.render.api._installed_data_win",
                        return_value=Path("D:/Games/hs/Data/Win")):
            result = self.classify(exc)
        self.assertEqual(result.kind, ProblemKind.RENDER)
        self.assertEqual(result.code, "render_failed")

    def test_file_not_found_without_ctx_is_render_failed(self) -> None:
        result = self.classify(
            FileNotFoundError(errno.ENOENT, "no file", "D:/Games/hs/Data/Win/x"))
        self.assertEqual(result.kind, ProblemKind.RENDER)

    def test_permission_error_and_oserror_render_failed(self) -> None:
        for exc in (PermissionError(errno.EACCES, "denied", "x"),
                    OSError(errno.EIO, "io", "x")):
            with self.subTest(type=type(exc).__name__):
                result = self.classify(exc)
                self.assertEqual(result.kind, ProblemKind.RENDER)
                self.assertEqual(result.code, "render_failed")

    def test_value_error_render_failed(self) -> None:
        result = self.classify(ValueError("watermark 无 desc 层"))
        self.assertEqual(result.kind, ProblemKind.RENDER)
        self.assertEqual(result.code, "render_failed")
        self.assertEqual(result.cause, "ValueError: watermark 无 desc 层")

    def test_input_rejected_post_preflight(self) -> None:
        exc = InputRejected(Problem(ProblemKind.INPUT, "style", "k", "互斥",
                                    hint="style-hint"))
        result = self.classify(exc)
        self.assertEqual(result.kind, ProblemKind.RENDER)
        self.assertEqual(result.code, "render_failed")
        self.assertEqual(result.hint, "style-hint")   # 原 INPUT hint 保留
        self.assertIn("style", result.message)

    def test_import_error_dependency_missing(self) -> None:
        for exc in (ImportError("x"), ModuleNotFoundError("y")):
            with self.subTest(type=type(exc).__name__):
                result = self.classify(exc)
                self.assertEqual(result.kind, ProblemKind.ENVIRONMENT)
                self.assertEqual(result.code, "dependency_missing")

    def test_unexpected_runtime_error_render_failed(self) -> None:
        result = self.classify(RuntimeError("CLR 装载炸了"))
        self.assertEqual(result.kind, ProblemKind.RENDER)
        self.assertEqual(result.code, "render_failed")
        self.assertEqual(result.cause, "RuntimeError: CLR 装载炸了")

    def test_problem_path_is_out_path(self) -> None:
        result = self.classify(ValueError("x"))
        self.assertEqual(result.path, str(self.rc.out_path))


# ---------------------------------------------------------------------------
# _warnings_from / _merge_warnings（§7.3 warnings 形状）
# ---------------------------------------------------------------------------

class WarningsTests(unittest.TestCase):
    def test_missing_glyphs_flattened(self) -> None:
        # 上游事件字段=glyph_supply.record_missing 现役键：
        # font/size/ch/cp/reason/source/count。
        result = {"log": {"missing_glyphs": [
            {"font": "game:Futura", "size": 24, "ch": "⚙", "cp": 9881,
             "reason": "cmap 缺字", "source": "game", "count": 2},
        ]}}
        self.assertEqual(_warnings_from(result),
                         ("missing_glyphs:⚙:game:Futura",))

    def test_non_dict_or_missing_log_is_empty(self) -> None:
        self.assertEqual(_warnings_from(None), ())
        self.assertEqual(_warnings_from("nope"), ())
        self.assertEqual(_warnings_from({}), ())
        self.assertEqual(_warnings_from({"log": {}}), ())
        self.assertEqual(_warnings_from({"log": {"missing_glyphs": "x"}}), ())

    def test_merge_warnings_dedupes_in_order(self) -> None:
        def done(warnings) -> RenderedCard:
            return RenderedCard(ref=CardRef("dbf", 8), path=Path("x"),
                                sha256="s", elapsed_ms=1, warnings=warnings)

        outcomes = [done(("a", "b")), RenderFailure(
            ref=CardRef("dbf", 9), path=Path("y"),
            problem=Problem(ProblemKind.RENDER, "render_failed", "y", "m")),
            done(("b", "c"))]
        self.assertEqual(_merge_warnings(outcomes), ("a", "b", "c"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
