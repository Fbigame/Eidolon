"""TOML 读取与结构校验。

本模块只负责：

* 用标准库 ``tomllib`` 读取文件 / 解析文本；
* 顶层、卡级、asset 级未知键检查；
* 字段类型检查（bool 不算 int）。

语义校验（范围、枚举、路径存在性、重名等）在 :mod:`eidolon.shell.spec`。
所有错误追加到传入的 :class:`~eidolon.shell.errors.SpecErrors`，不提前中断。
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .errors import SpecErrors

TOP_LEVEL_KEYS = frozenset(
    {"format_version", "out_dir", "jobs", "antialias", "game_dir", "cards"}
)
CARD_KEYS = frozenset(
    {
        "id",
        "name",
        "desc",
        "classes",
        "races",
        "cost",
        "attack",
        "health",
        "armor",
        "cardtype",
        "rarity",
        "premium",
        "spell_school",
        "cost_banner",
        "elite",
        "runes",
        "tech_level",
        "hero_style",
        "bg_style",
        "outname",
        "asset",
    }
)
ASSET_KEYS = frozenset({"portrait", "frame", "watermark"})

_STRING_FIELDS = ("name", "desc", "outname", "cardtype", "rarity", "premium", "spell_school", "cost_banner")
_INT_FIELDS = ("cost", "attack", "health", "armor", "tech_level")
_BOOL_FIELDS = ("elite", "hero_style", "bg_style")


def type_name(value: Any) -> str:
    if type(value) is bool:
        return "bool"
    return type(value).__name__


def load_document(path: str | Path, errors: SpecErrors) -> dict[str, Any] | None:
    """读取 TOML；IO / 语法错误写入 errors 并返回 None。"""
    source = Path(path)
    try:
        with source.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        errors.add("io", str(source), "文件不存在")
        return None
    except IsADirectoryError:
        errors.add("io", str(source), "不是文件")
        return None
    except OSError as exc:
        errors.add("io", str(source), f"无法读取: {exc}")
        return None
    except tomllib.TOMLDecodeError as exc:
        errors.add("toml_syntax", str(source), str(exc))
        return None
    except UnicodeDecodeError as exc:
        errors.add("toml_syntax", str(source), f"文件不是合法 UTF-8: {exc}")
        return None
    if not isinstance(data, dict):  # pragma: no cover - tomllib 保证顶层表
        errors.add("toml_syntax", str(source), "顶层必须是 TOML 表")
        return None
    return data


def parse_text(text: str, *, source: str = "<string>") -> dict[str, Any]:
    """解析 TOML 文本，语法错误抛 :class:`ValueError`（测试/内部便利）。"""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{source}: {exc}") from exc
    if not isinstance(data, dict):  # pragma: no cover
        raise ValueError(f"{source}: 顶层必须是 TOML 表")
    return data


def _check_type(value: Any, expected: str, path: str, errors: SpecErrors) -> bool:
    """按 expected（'str' / 'int' / 'bool' / 'list' / 'dict'）检查。"""
    if expected == "int":
        ok = type(value) is int
    elif expected == "bool":
        ok = type(value) is bool
    elif expected == "str":
        ok = isinstance(value, str)
    elif expected == "list":
        ok = isinstance(value, list)
    elif expected == "dict":
        ok = isinstance(value, dict)
    else:  # pragma: no cover - 内部错误
        raise AssertionError(expected)
    if not ok:
        errors.add("type", path, f"应为 {expected}，实际为 {type_name(value)}")
    return ok


def _check_string_list(value: Any, path: str, errors: SpecErrors) -> bool:
    if not _check_type(value, "list", path, errors):
        return False
    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.add(
                "type",
                f"{path}[{index}]",
                f"应为 str，实际为 {type_name(item)}",
            )
    return True


def validate_document(data: dict[str, Any], errors: SpecErrors) -> None:
    """检查顶层 / 卡级 / asset 级的未知键与类型。"""
    for key in sorted(data):
        if key not in TOP_LEVEL_KEYS:
            errors.add("unknown_key", key, f"未知的顶层键 {key!r}")

    if "format_version" not in data:
        errors.add("missing", "format_version", "缺少必填键 format_version")
    else:
        _check_type(data["format_version"], "int", "format_version", errors)

    if "out_dir" in data:
        _check_type(data["out_dir"], "str", "out_dir", errors)
    if "game_dir" in data:
        _check_type(data["game_dir"], "str", "game_dir", errors)
    if "jobs" in data:
        _check_type(data["jobs"], "int", "jobs", errors)
    if "antialias" in data:
        _check_type(data["antialias"], "bool", "antialias", errors)

    if "cards" not in data:
        errors.add("missing", "cards", "缺少 [[cards]] 表")
        return
    cards = data["cards"]
    if not _check_type(cards, "list", "cards", errors):
        return

    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(card, dict):
            errors.add("type", prefix, f"应为 TOML 表，实际为 {type_name(card)}")
            continue
        _validate_card(card, prefix, errors)


def _validate_card(card: dict[str, Any], prefix: str, errors: SpecErrors) -> None:
    for key in sorted(card):
        if key not in CARD_KEYS:
            errors.add("unknown_key", f"{prefix}.{key}", f"未知的卡级键 {key!r}")

    if "id" not in card:
        errors.add("missing", f"{prefix}.id", "缺少 id")
    else:
        value = card["id"]
        if type(value) is bool or not isinstance(value, (int, str)):
            errors.add(
                "type",
                f"{prefix}.id",
                f"id 应为 int 或 str，实际为 {type_name(value)}",
            )

    for key in _STRING_FIELDS:
        if key in card:
            _check_type(card[key], "str", f"{prefix}.{key}", errors)

    for key in _INT_FIELDS:
        if key in card:
            _check_type(card[key], "int", f"{prefix}.{key}", errors)

    for key in _BOOL_FIELDS:
        if key in card:
            _check_type(card[key], "bool", f"{prefix}.{key}", errors)

    if "classes" in card:
        _check_string_list(card["classes"], f"{prefix}.classes", errors)
    if "races" in card:
        _check_string_list(card["races"], f"{prefix}.races", errors)

    if "runes" in card:
        runes = card["runes"]
        if _check_type(runes, "dict", f"{prefix}.runes", errors):
            for rune, count in runes.items():
                path = f"{prefix}.runes.{rune}"
                if not isinstance(rune, str) or not rune:
                    errors.add("type", path, "rune 名必须是非空字符串")
                _check_type(count, "int", path, errors)

    if "asset" in card:
        asset = card["asset"]
        if _check_type(asset, "dict", f"{prefix}.asset", errors):
            for key in sorted(asset):
                path = f"{prefix}.asset.{key}"
                if key not in ASSET_KEYS:
                    errors.add("unknown_key", path, f"未知的 asset 键 {key!r}")
                _check_type(asset[key], "str", path, errors)
