"""api — core 渲染端口（设计 §7.2/§7.3/§7.8 的逐字实现）。

``render(request)`` 是产品渲染入口：安装进程身份与 dbf 会话（幂等），
jobs<=1 或单卡走串行，否则 ``ProcessPoolExecutor``（Windows spawn，worker
initializer 装 ctx/dbf/font）。逐卡失败不穿出（``_render_one`` 顶层
``except Exception`` 全部转 ``RenderFailure``）——异常对象不得跨进程
（``EnvironmentUnavailable`` 的 pickle 反序列化只带 message，problem 会丢）。

import 时序（§7.1.1，守卫钉住）：本模块顶层只 import 标准库 +
``eidolon.contracts`` + ``eidolon.core.render.params``；``dbf`` / ``context`` /
``DbfModule`` / ``card`` / ``card_overrides`` / ``components`` / ``glyph_supply``
等一律函数体内延迟引入（``_render_one`` 的 ``*_factory`` / ``render_fn`` /
``resolve_form_fn`` / ``cfg_factory`` 参数是默认测试的 fake 注入点；生产不传，
默认走 ``_default_*``，这些函数体内才 import 渲染链）。

A2 pending seed seam（supply-source.md §3.7）：``_render_one`` 增可选
``seed_provider``（零参可调用 → token 种子 dict；默认 None=产品 0.1.0 不启用，
行为逐位不变）——给出种子时以 ``machine.seed_session`` 预置 pending，render_fn
（``_in_session``）内的首个 ``session()`` 一次性消费为初始 memo，命中 token
不再执行域函数、未命中 token 照旧 live。
"""
from __future__ import annotations

import contextlib
import errno
import functools
import hashlib
import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import replace
from pathlib import Path
from typing import Callable, Sequence

from eidolon.contracts import (
    CardRef,
    EnvironmentUnavailable,
    InputRejected,
    Problem,
    ProblemKind,
    RenderCard,
    RenderedCard,
    RenderFailure,
    RenderRequest,
    RenderReport,
)
from eidolon.core.render.params import PRODUCT_SESSION_T

__all__ = ["render"]


# ---------------------------------------------------------------------------
# render（§7.2）
# ---------------------------------------------------------------------------

def render(request: RenderRequest) -> RenderReport:
    """产品渲染入口：串行 / 进程池 → RenderReport（顺序=输入顺序）。"""
    from eidolon.core.infra import context, dbf

    context.install(request.game)                 # 幂等；同身份 no-op
    if dbf.installed_default() is None:
        from eidolon.core.infra.dbf import DbfModule

        dbf.install_default(DbfModule(request.game.dbf_path))
    cards = request.cards
    if request.jobs <= 1 or len(cards) <= 1:
        # 串行分支同 worker initializer 装 font_dirs（§7.2 顺序：ctx → dbf →
        # 字体目录；无条件调用——空元组=glyph_supply 自落产品兜底目录），
        # 否则串行路径字形回退族索引停留在未注入态（P1-4）。
        from eidolon.core.render.text import glyph_supply

        glyph_supply.install_font_dirs(request.font_dirs,
                                       cache_dir=request.game.cache_root / "fonts")
        outcomes: list[RenderedCard | RenderFailure] = [
            _render_one(render_card, antialias=request.antialias)
            for render_card in cards
        ]
    else:
        pool_job = functools.partial(_render_one, antialias=request.antialias)
        try:
            with ProcessPoolExecutor(
                max_workers=min(request.jobs, len(cards)),
                initializer=_worker_init,
                initargs=(request.game, request.font_dirs),
            ) as pool:
                outcomes = list(pool.map(pool_job, cards))
        except (BrokenProcessPool, OSError) as exc:
            # §11.3：worker 崩溃/池启动失败整批失败 → ENV 3，不静默丢卡，
            # 不落未预期 internal 1。
            cause = f"{type(exc).__name__}: {exc}"
            raise EnvironmentUnavailable(Problem(
                ProblemKind.ENVIRONMENT,
                "dependency_missing",
                "env:worker",
                f"dependency_missing: 渲染 worker 进程池启动/崩溃（{cause}）",
                cause=cause,
            )) from exc
    rendered = tuple(o for o in outcomes if isinstance(o, RenderedCard))
    failures = tuple(o for o in outcomes if isinstance(o, RenderFailure))
    return RenderReport(
        rendered=rendered,
        failures=failures,
        warnings=_merge_warnings(outcomes),
    )


def _worker_init(ctx, font_dirs) -> None:
    """worker initializer：装 ctx → dbf 会话 → 字体目录（§7.2 顺序）。"""
    from eidolon.core.infra import context, dbf
    from eidolon.core.infra.dbf import DbfModule
    from eidolon.core.render.text import glyph_supply

    context.install(ctx)
    dbf.install_default(DbfModule(ctx.dbf_path))
    glyph_supply.install_font_dirs(font_dirs, cache_dir=ctx.cache_root / "fonts")


# ---------------------------------------------------------------------------
# 单卡渲染（§7.3；try 覆盖整个函数体，异常全转 RenderFailure 不穿出）
# ---------------------------------------------------------------------------

def _seed_scope(seed_provider):
    """``seed_provider`` → 会话种子上下文（A2 S1 seam；0.1.0 产品不启用）。

    provider=零参可调用（组合层/测试注入；返回非空 dict → 种子面，None/空 →
    纯 live）。给出种子时用 ``machine.seed_session`` 预置 pending——render_fn
    （``_in_session``）内的首个 ``session()`` 进入时一次性消费为初始 memo，
    命中 token 不再执行域函数、未命中 token 照旧 live（fallback 天然）。
    provider 异常不在本层兜底（种子器按 supply-source.md §3.6 自行弃种回
    live）；machine import 留函数体（§7.1.1：供给链延迟装载）。"""
    if seed_provider is None:
        return contextlib.nullcontext()
    seeds = seed_provider()
    if not seeds:
        return contextlib.nullcontext()
    from eidolon.core.supply.machine import seed_session

    return seed_session(seeds)


def _render_one(render_card: RenderCard, *, antialias: bool,
                card_factory=None, constants_factory=None,
                render_fn=None, resolve_form_fn=None, cfg_factory=None,
                seed_provider=None
                ) -> RenderedCard | RenderFailure:
    started = time.perf_counter()
    try:
        from eidolon.core.render import card_overrides

        dbf_id = resolve_dbf_id(render_card.ref)
        if dbf_id is None:
            raise ValueError("unknown dbf id")       # _classify → render_failed
        card = (card_factory or _default_card_from_dbf)(dbf_id)
        constants = (constants_factory or _default_live_constants)()
        card_overrides.apply(card, render_card, constants)
        if render_card.hero_style and render_card.bg_style:
            raise InputRejected(Problem(
                ProblemKind.INPUT,
                "style",
                str(render_card.out_path),
                "style: hero_style 与 bg_style 同时为真——二者互斥",
            ))
        form = ("hero" if render_card.hero_style
                else "bg" if render_card.bg_style else "plain")
        resolve_form_fn = resolve_form_fn or _default_resolve_form
        use_bg_style, zone = resolve_form_fn(card, form)
        cfg = (cfg_factory or _default_canonical_cfg)()
        cfg = replace(cfg, use_bg_style=use_bg_style,
                      supersample=4 if antialias else 1, name="eidolon")
        t = (render_card.session_t if render_card.session_t is not None
             else PRODUCT_SESSION_T)
        render = render_fn or _default_render_with
        with _seed_scope(seed_provider):
            sha, result = _atomic_render(
                render_card.out_path,
                lambda p: render(card, cfg, t_phase=t, zone=zone, notext=False,
                                 textonly=False, out_png=p, session_time=None))
        return RenderedCard(ref=render_card.ref, path=render_card.out_path,
                            sha256=sha,
                            elapsed_ms=int((time.perf_counter() - started) * 1000),
                            warnings=_warnings_from(result))
    except KeyboardInterrupt:
        raise
    except Exception as exc:                          # 整个函数体都在 try 内
        return RenderFailure(ref=render_card.ref, path=render_card.out_path,
                             problem=_classify_card_failure(exc, render_card))


def resolve_dbf_id(ref: CardRef) -> int | None:
    """``CardRef`` → dbf id：``kind=="dbf"`` → int；``"card"`` → default_dbf
    索引（casefold）；查无 → None（§7.3 辅助函数归属单点）。"""
    if ref.kind == "dbf":
        return int(ref.value)
    from eidolon.core.infra.dbf import default_dbf

    return default_dbf().card_id_to_dbf.get(ref.value.casefold())


def _default_card_from_dbf(dbf_id: int):
    from eidolon.core.infra.card import Card

    return Card.from_dbf(dbf_id)


def _default_live_constants():
    from eidolon.core.render.constants import live_card_constants

    return live_card_constants()


def _default_resolve_form(card, form: str) -> tuple["bool | None", str]:
    from eidolon.core.render.game.actor.components import resolve_form

    return resolve_form(card, form)


def _default_canonical_cfg():
    from eidolon.core.render.game.actor.components import canonical_cfg

    return canonical_cfg()


def _default_render_with(card, cfg, **kwargs):
    from eidolon.core.render.game.actor.components import render_with

    return render_with(card, cfg, **kwargs)


# ---------------------------------------------------------------------------
# PNG 原子性（§7.3 docstring 语义逐字）
# ---------------------------------------------------------------------------

_WRITE_ERRNOS = frozenset({errno.ENOSPC, errno.EACCES, errno.EROFS, errno.EDQUOT})


def _write_failed(out_path: Path, what: str, exc: OSError) -> Exception:
    from eidolon.core.infra.errors import WriteFailed

    cause = f"{type(exc).__name__}: {exc}"
    return WriteFailed(
        path=str(out_path),
        message=f"write_failed: {what}（{cause}）",
        cause=cause,
    )


def _write_like_oserror(exc: OSError, out_path: Path, tmp_path: Path) -> bool:
    """render_callable 内的 OSError 是否按写盘失败包 WriteFailed（§7.3）：
    ``exc.filename`` 在 out_path.parent / tmp 下，或 errno ∈
    {ENOSPC, EACCES, EROFS, EDQUOT}（覆盖 img.save / V-pass save）。"""
    if exc.errno in _WRITE_ERRNOS:
        return True
    filename = exc.filename
    if not filename:
        return False
    candidate = Path(os.path.normcase(os.path.abspath(os.fspath(filename))))
    for root in (out_path.parent, tmp_path.parent):
        base = Path(os.path.normcase(os.path.abspath(os.fspath(root))))
        if candidate == base or candidate.is_relative_to(base):
            return True
    return False


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_render(out_path: Path,
                   render_callable: Callable[[Path], object]) -> tuple[str, object]:
    """纯 helper（默认可单测）：mkstemp→close→render(tmp)→replace→sha。

    render_callable 抛错（含 BaseException）时 finally 删除 tmp 并重抛；
    句柄 close 失败先 best-effort 删空 tmp 再包 WriteFailed（不留 tmp）；
    mkstemp/replace/临时文件写失败包成 WriteFailed(write_failed)。
    render_callable 内的 OSError 若 ``exc.filename`` 在 out_path.parent/tmp 下
    或 errno ∈ {ENOSPC, EACCES, EROFS, EDQUOT}，也包成 WriteFailed（覆盖
    img.save / V-pass save）；其余 OSError 原样重抛。返回 (最终文件 sha256,
    render 结果)。临时路径以 ``Path`` 传给 render_callable——不得传 str
    （render_with 会对 ``out_png.parent`` 取属性）。
    临时文件 suffix 用 ``.png``（非 ``.tmp``）：render_with 的
    ``Image.save(out_png)`` 不传 format，PIL 按扩展名推断（V-pass 重开
    ``Image.open(out_png)`` 同理）——``.tmp`` 会 ValueError: unknown file
    extension（Phase 3c 产品端口实测）；同目录 ``.`` 前缀 + finally 清理的
    原子性语义不变。
    """
    out_path = Path(out_path)
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=out_path.parent, prefix=f".{out_path.name}.", suffix=".png")
    except OSError as exc:
        raise _write_failed(out_path, "mkstemp 失败", exc) from exc
    tmp_path = Path(tmp_name)
    try:
        os.close(fd)
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)   # best-effort：不留空 tmp（P1-5）
        except OSError:
            pass   # 清理尽力而为，不掩盖原异常
        raise _write_failed(out_path, "临时文件句柄关闭失败", exc) from exc
    replaced = False
    try:
        try:
            result = render_callable(tmp_path)
        except BaseException as exc:
            if isinstance(exc, OSError) and _write_like_oserror(exc, out_path, tmp_path):
                raise _write_failed(out_path, "渲染写盘失败", exc) from exc
            raise
        try:
            os.replace(tmp_path, out_path)
        except OSError as exc:
            raise _write_failed(out_path, "输出文件替换失败", exc) from exc
        replaced = True
        try:
            return _sha256_of(out_path), result
        except OSError as exc:
            raise _write_failed(out_path, "输出文件读取失败", exc) from exc
    finally:
        if not replaced:
            try:
                tmp_path.unlink()
            except OSError:
                pass   # 清理尽力而为，不掩盖原异常


# ---------------------------------------------------------------------------
# 错误分类（§7.8 映射表逐行）与 warnings 形状（§7.3）
# ---------------------------------------------------------------------------

def _installed_data_win():
    """已装 ctx 的数据根（FileNotFoundError 的资产路径判定用）；未装 → None。"""
    from eidolon.core.infra import context

    ctx = context.installed()
    return ctx.data_win if ctx is not None else None


_BUNDLE_ERROR_NAMES = frozenset({"BundleBlockCorruptError", "BundleContentMismatch"})
"""bundle 两 typed error 的类名预筛：``bundle_lazy``/``bundle_guard`` 顶层吃
UnityPy，render_failed 热路径不付该 import 税；两个类都是我方自有件（类名
稳定），预筛后仍以真实类 isinstance 定案（下方``_bundle_asset_classes``）。"""


def _bundle_asset_classes() -> tuple[type, ...]:
    """bundle typed error 类组（函数体内 import——UnityPy 链，§6.5）。"""
    from eidolon.core.infra.bundle_guard import BundleContentMismatch
    from eidolon.core.infra.bundle_lazy import BundleBlockCorruptError

    return (BundleBlockCorruptError, BundleContentMismatch)


def _classify_card_failure(exc: Exception, render_card: RenderCard) -> Problem:
    """逐卡异常 → Problem（§7.8 映射表；唯一映射函数）。

    ``InputRejected`` 在 preflight 之外一律归 ``render_failed``（RENDER 1）：
    此时 plan manifest 已打印，不能再声称 INPUT/2。
    """
    path = str(render_card.out_path)
    cause = f"{type(exc).__name__}: {exc}"

    def render_failed(message: str, *, hint: str = "") -> Problem:
        return Problem(ProblemKind.RENDER, "render_failed", path, message,
                       hint=hint, cause=cause)

    if isinstance(exc, InputRejected):
        return render_failed(
            f"render_failed: 覆盖语义校验失败（preflight 之外；原 "
            f"{exc.problem.code}）：{exc}",
            hint=exc.problem.hint,
        )
    if isinstance(exc, EnvironmentUnavailable):
        return exc.problem                     # 含 GameAssetMissing/WriteFailed/
                                               # dbf_unreadable/constants_unavailable
    if type(exc).__name__ in _BUNDLE_ERROR_NAMES and isinstance(
            exc, _bundle_asset_classes()):
        # bundle 块解码失败/内容不符：dbf 包在 worker init 已装，逐卡期出现
        # 按资产包（route/supply）读坏归 asset_missing_in_game（ENV）。
        # route 内容失配自带 path=bundle + 扫描/修复/refresh hint → 优先采用。
        return Problem(ProblemKind.ENVIRONMENT, "asset_missing_in_game",
                       getattr(exc, "path", None) or path,
                       f"asset_missing_in_game: 游戏资产包读坏（{cause}）",
                       hint=getattr(exc, "hint", None) or "",
                       cause=cause)
    if isinstance(exc, FileNotFoundError):
        # §7.8 注：FileNotFoundError 只在游戏资产路径（ctx.data_win 下）归
        # asset_missing_in_game，否则按 render_failed。
        data_win = _installed_data_win()
        if data_win is not None and exc.filename:
            asset = Path(os.path.normcase(os.path.abspath(os.fspath(exc.filename))))
            root = Path(os.path.normcase(os.path.abspath(os.fspath(data_win))))
            if asset.is_relative_to(root):
                return Problem(ProblemKind.ENVIRONMENT, "asset_missing_in_game",
                               str(exc.filename),
                               f"asset_missing_in_game: 游戏资产缺失（{cause}）",
                               cause=cause)
        return render_failed(f"render_failed: {cause}")
    if isinstance(exc, (PermissionError, OSError)):
        return render_failed(f"render_failed: {cause}")
    if isinstance(exc, ValueError):
        return render_failed(f"render_failed: {cause}")
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return Problem(ProblemKind.ENVIRONMENT, "dependency_missing", path,
                       f"dependency_missing: 渲染依赖缺失/装载失败（{cause}）",
                       cause=cause)
    return render_failed(f"render_failed: 未预期异常（{cause}）")


def _warnings_from(result: object) -> tuple[str, ...]:
    """``result["log"]["missing_glyphs"]``（list[dict]）扁平化（§7.3）。

    上游事件字段=glyph_supply.record_missing 的现役键
    ``font/size/ch/cp/reason/source/count``；warning 形状
    ``missing_glyphs:<ch>:<font>``（font=字体标签，含 face 信息）。
    result 非 dict / 无 log / 无 missing_glyphs → ()。
    """
    if not isinstance(result, dict):
        return ()
    log = result.get("log")
    if not isinstance(log, dict):
        return ()
    missing = log.get("missing_glyphs")
    if not isinstance(missing, list):
        return ()
    out: list[str] = []
    for event in missing:
        if not isinstance(event, dict):
            continue
        out.append(f"missing_glyphs:{event.get('ch', '')}:{event.get('font', '')}")
    return tuple(out)


def _merge_warnings(outcomes: Sequence[RenderedCard | RenderFailure]) -> tuple[str, ...]:
    """全局 warnings = 各卡 warnings 串联去重（保序；简单正确者）。"""
    seen: set[str] = set()
    out: list[str] = []
    for outcome in outcomes:
        if not isinstance(outcome, RenderedCard):
            continue
        for warning in outcome.warnings:
            if warning not in seen:
                seen.add(warning)
                out.append(warning)
    return tuple(out)
