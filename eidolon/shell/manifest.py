"""RenderSpec → 稳定、JSON-able 的 manifest（计划 + 结果两份文档）。

``build_manifest`` 只描述「要做什么」（plan，stdout）；``build_result_manifest``
描述「做了什么」（结果，``out_dir/manifest.json``，设计 §7.9）。可选项只
输出显式给出的内容；路径一律绝对路径。输出顺序由本模块固定，保证同一
输入得到逐字节相同的 manifest。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from eidolon.contracts import (
    CardRef,
    EnvironmentUnavailable,
    GameContext,
    Problem,
    ProblemKind,
    RenderedCard,
    RenderFailure,
    RenderReport,
)
from eidolon.version import __version__

from .errors import EXIT_ENVIRONMENT, EXIT_OK, EXIT_RENDER_FAILED
from .spec import FIELD_ORDER, CardSpec, RenderSpec

FORMAT_VERSION = 1


def build_manifest(spec: RenderSpec) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "source": spec.source,
        "options": {
            "out_dir": str(spec.options.out_dir),
            "jobs": spec.options.jobs,
            "antialias": spec.options.antialias,
        },
        "environment": _environment(spec),
        "cards": [_card_manifest(card) for card in spec.cards],
        "warnings": list(spec.warnings),
    }


def _environment(spec: RenderSpec) -> dict[str, Any]:
    return {
        # game 由真实 provider（core）构造；dev null catalog 路径恒 None。
        "game": _game_manifest(spec.game),
        # dbf 文件账：catalog.kind == "dbf" 时复现 path/size/mtime_ns。
        "dbf": _dbf_manifest(spec.catalog),
        "catalog": _catalog_manifest(spec.catalog),
        "eidolon": __version__,
    }


def _dbf_manifest(identity: Any) -> dict[str, Any] | None:
    if identity.kind != "dbf":
        return None
    return {
        "path": identity.path,
        "size": identity.size,
        "mtime_ns": identity.mtime_ns,
    }


def _game_manifest(game: GameContext | None) -> dict[str, Any] | None:
    if game is None:
        return None
    return {
        "root": str(game.root),
        "locale": game.locale,
        "version": game.version,
        "version_source": game.version_source,
        "root_source": game.root_source,
    }


def _catalog_manifest(identity: Any) -> dict[str, Any]:
    return {
        "kind": identity.kind,
        "path": identity.path,
        "size": identity.size,
        "mtime_ns": identity.mtime_ns,
        "complete": identity.complete,
    }


def manifest_json(spec: RenderSpec, *, indent: int | None = 2) -> str:
    """manifest 的 JSON 文本；默认缩进、UTF-8 原文输出、无排序键抖动。"""
    return json.dumps(
        build_manifest(spec), ensure_ascii=False, indent=indent
    )


def _ref_manifest(ref: CardRef) -> dict[str, object]:
    """CardRef → manifest 的 ``id`` 字段（映射归 manifest，不进 contracts）。"""
    return {"kind": ref.kind, "value": ref.value}


def _card_manifest(card: CardSpec) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "input_id": card.input_id,
        "id": _ref_manifest(card.ref),
        "out": str(card.out_path),
        "hero_style": card.hero_style,
        "bg_style": card.bg_style,
    }
    overrides = _overrides(card)
    if overrides:
        entry["overrides"] = overrides
    entry["deferred"] = list(card.deferred)
    return entry


def _overrides(card: CardSpec) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if card.name is not None:
        overrides["name"] = card.name
    if card.desc is not None:
        overrides["desc"] = card.desc
    if card.classes is not None:
        overrides["classes"] = list(card.classes)
    if card.races is not None:
        overrides["races"] = list(card.races)

    fields: dict[str, Any] = {}
    for name in FIELD_ORDER:
        value = getattr(card, name)
        if value is None:
            continue
        if name == "runes":
            fields[name] = {
                key: value[key] for key in sorted(value)  # type: ignore[index]
            }
        else:
            fields[name] = value
    if fields:
        overrides["fields"] = fields

    if card.assets:
        overrides["assets"] = {
            key: str(path) for key, path in sorted(card.assets.items())
        }
    return overrides


def out_paths(spec: RenderSpec) -> tuple[Path, ...]:
    """便利：manifest 中按输入顺序排列的绝对输出路径。"""
    return tuple(card.out_path for card in spec.cards)


# ---------------------------------------------------------------------------
# 结果 manifest（设计 §7.9；与 plan manifest 是两份不同文档）
# ---------------------------------------------------------------------------

RESULT_FILENAME = "manifest.json"


def report_exit_code(report: RenderReport) -> int:
    """RenderReport → 退出码（§9.3 单一来源）：ENV 3 优先，其次 RENDER/
    INTERNAL 1，否则 0。逐卡 failure 的 kind ∈ {ENVIRONMENT, RENDER}（INPUT
    不允许进入 RenderFailure），INTERNAL 仅为防御面。``cli.run`` 只调用本
    函数，不重复散落判断。"""
    kinds = [failure.problem.kind for failure in report.failures]
    if any(kind is ProblemKind.ENVIRONMENT for kind in kinds):
        return EXIT_ENVIRONMENT
    if any(kind in (ProblemKind.RENDER, ProblemKind.INTERNAL) for kind in kinds):
        return EXIT_RENDER_FAILED
    return EXIT_OK


def _norm_out(path: Path) -> Path:
    """out_path 规范化（报告条目对回 CardSpec 的映射键；Windows 大小写无关）。"""
    return Path(os.path.normcase(os.path.abspath(os.fspath(path))))


def _problem_dict(problem: Problem) -> dict[str, str]:
    """Problem 全字段 → JSON dict（结果 manifest 的 ``error`` 形状）。"""
    return {
        "kind": str(problem.kind.value),
        "code": problem.code,
        "path": problem.path,
        "message": problem.message,
        "hint": problem.hint,
        "cause": problem.cause,
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assets_sha256(card: CardSpec, shell_warnings: list[str]) -> dict[str, str]:
    """覆盖资产文件字节 sha256 现算（§7.9）。

    文件在 preflight 后消失/不可读 → 该键省略并加 ``asset_hash_unavailable``
    warning（用户覆盖资产不是游戏安装，不能 ``asset_missing_in_game`` 3，
    也不伪装成渲染失败）。
    """
    hashes: dict[str, str] = {}
    for key in sorted(card.assets):
        path = card.assets[key]
        try:
            hashes[key] = _file_sha256(path)
        except OSError:
            shell_warnings.append(f"asset_hash_unavailable:{key}:{path}")
    return hashes


def build_result_manifest(spec: RenderSpec, report: RenderReport) -> dict[str, Any]:
    """结果 manifest（§7.9）：cards 按输入顺序一张不落。

    对齐方式：规范化 ``out_path`` 把 ``report.rendered/failures`` 对回
    ``CardSpec``；``len(rendered)+len(failures)==len(cards)`` 断言（缺失/
    多余都不可静默），逐卡查不到 → ``render_failed`` error +
    ``report_missing`` warning（不静默丢卡）。全局 warnings =
    ``spec.warnings + report.warnings + shell 侧``按出现顺序去重。
    """
    rendered = len(report.rendered) + len(report.failures)
    if rendered != len(spec.cards):
        raise AssertionError(
            f"render report 条目数 {rendered} 与 cards 数 {len(spec.cards)} 不一致"
            "（不可静默丢卡/多卡）"
        )

    by_path: dict[Path, RenderedCard | RenderFailure] = {}
    for outcome in (*report.rendered, *report.failures):
        key = _norm_out(outcome.path)
        if key in by_path:
            raise AssertionError(f"render report 对同一 out_path 重复条目: {outcome.path}")
        by_path[key] = outcome

    shell_warnings: list[str] = []
    cards: list[dict[str, Any]] = []
    for card in spec.cards:
        outcome = by_path.get(_norm_out(card.out_path))
        if outcome is None:
            # 规范化后仍对不回报告（防御面；上面条目数断言已拦住主要路径）。
            shell_warnings.append(f"report_missing:{card.outname}")
            problem = Problem(
                ProblemKind.RENDER,
                "render_failed",
                str(card.out_path),
                f"render_failed: 渲染报告缺少该卡的结果条目（{card.input_id}）",
            )
            cards.append({
                "input_id": card.input_id,
                "id": _ref_manifest(card.ref),
                "out": str(card.out_path),
                "ok": False,
                "error": _problem_dict(problem),
            })
            continue
        if isinstance(outcome, RenderedCard):
            entry: dict[str, Any] = {
                "input_id": card.input_id,
                "id": _ref_manifest(card.ref),
                "out": str(card.out_path),
                "ok": True,
                "sha256": outcome.sha256,
                "elapsed_ms": outcome.elapsed_ms,
                "hero_style": card.hero_style,
                "bg_style": card.bg_style,
                "style_requested": [card.style_requested[0], card.style_requested[1]],
                "warnings": list(outcome.warnings),
            }
            overrides = _overrides(card)
            if overrides:
                entry["overrides"] = overrides
            assets_sha256 = _assets_sha256(card, shell_warnings)
            if assets_sha256:
                entry["assets_sha256"] = assets_sha256
            cards.append(entry)
        else:
            cards.append({
                "input_id": card.input_id,
                "id": _ref_manifest(card.ref),
                "out": str(card.out_path),
                "ok": False,
                "error": _problem_dict(outcome.problem),
            })

    warnings = list(spec.warnings) + list(report.warnings) + shell_warnings
    return {
        "format_version": FORMAT_VERSION,
        "source": spec.source,
        "options": {
            "out_dir": str(spec.options.out_dir),
            "jobs": spec.options.jobs,
            "antialias": spec.options.antialias,
        },
        "environment": _environment(spec),
        "cards": cards,
        "warnings": list(dict.fromkeys(warnings)),
    }


def write_result_manifest(spec: RenderSpec, report: RenderReport) -> Path:
    """结果 manifest 写 ``out_dir/manifest.json``（§7.9）。

    同目录临时文件 + ``os.replace``；写盘失败 →
    ``EnvironmentUnavailable(write_failed)``（ENV 3），已渲染 PNG 保留
    （本函数只管 manifest 写盘）。
    """
    out_dir = spec.options.out_dir
    manifest_path = out_dir / RESULT_FILENAME
    payload = json.dumps(
        build_result_manifest(spec, report), ensure_ascii=False, indent=2
    )
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=out_dir, prefix=f".{RESULT_FILENAME}.", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
        os.replace(tmp_path, manifest_path)
        tmp_path = None
        return manifest_path
    except OSError as exc:
        cause = f"{type(exc).__name__}: {exc}"
        raise EnvironmentUnavailable(Problem(
            ProblemKind.ENVIRONMENT,
            "write_failed",
            str(manifest_path),
            f"write_failed: 结果 manifest 写盘失败（{cause}）；已渲染 PNG 保留",
            cause=cause,
        )) from exc
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass  # 清理尽力而为，不掩盖原异常
