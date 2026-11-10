"""输入阶段一：CLI / TOML → :class:`InputDraft`（结构 / 类型 / 路径）。

``load_input`` 只做不依赖 catalog 的检查：语法、结构、类型、id、outname、
asset、runes、classes/races 结构规则、premium/cost_banner 产品常量、显式
``game_dir`` 安装根校验、``--catalog`` 互斥。**不碰 dbf、不探测
product.db、不 import core**。catalog 依赖的检查在 :mod:`eidolon.shell.spec`
的 ``compile_spec``（阶段二）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from eidolon.contracts import CardRef, GameRequest

from . import toml_io
from .errors import SpecErrors

DBF_RE = re.compile(r"^[0-9]+$")
CARD_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")

PREMIUMS = ("NORMAL", "GOLDEN")
# runes 键名白名单（产品词汇；未知键 = INPUT 2，未知键名不接受 deferred）。
RUNE_NAMES = ("BLOOD", "FROST", "UNHOLY")
BANNERS = (
    "NONE",
    "GRIMY_GOONS",
    "KABAL",
    "JADE_LOTUS",
    "ZERG",
    "TERRAN",
    "PROTOSS",
    "TRADEABLE",
    "FORGE",
    "PREPARE",
)

# 与 --toml 互斥的命令行全局选项（TOML 模式只认文件）。--game / --locale /
# --cache-root / -v / --debug 允许与 --toml 同用，不在此列。
_TOML_CONFLICT_FLAGS = (
    ("--outdir", "outdir"),
    ("--jobs", "jobs"),
    ("--antialias", "antialias"),
    ("--hero-style", "hero_style"),
    ("--bg-style", "bg_style"),
)


@dataclass(frozen=True)
class InputOptions:
    """输入期全局选项（CLI 模式的显式请求；TOML 模式 style 恒 False）。"""

    out_dir: Path
    jobs: int
    antialias: bool
    hero_style: bool = False
    bg_style: bool = False


@dataclass(frozen=True)
class CardDraft:
    """一张卡的输入期形状；overrides 的字段名与 CardSpec 一致。"""

    input_id: str
    ref: CardRef
    outname: str
    out_path: Path
    overrides: Mapping[str, object] = field(default_factory=dict)
    assets: Mapping[str, Path] = field(default_factory=dict)
    hero_style: bool = False
    bg_style: bool = False


@dataclass(frozen=True)
class InputDraft:
    """阶段一产物：结构合法的输入，等待 provider.bind + compile_spec。"""

    command: str  # "spec" | "render"
    source: str  # "inline" | "toml"
    base: Path
    game: GameRequest
    catalog_path: Path | None
    options: InputOptions
    cards: tuple[CardDraft, ...]
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# id（公开 API 由 eidolon.shell.spec re-export）
# ---------------------------------------------------------------------------


def parse_id(value: Any, path: str = "id") -> CardRef:
    """解析单 id（命令行语义：纯数字字符串按 dbf）；非法时抛 SpecErrors。"""
    errors = SpecErrors()
    ref = _parse_id(value, path, errors, allow_numeric_string=True)
    errors.raise_if_any()
    assert ref is not None
    return ref


def _parse_id(
    value: Any, path: str, errors: SpecErrors, *, allow_numeric_string: bool
) -> CardRef | None:
    if type(value) is bool:
        errors.add("invalid_id", path, f"id 不能是 bool: {value!r}")
        return None
    if isinstance(value, int):
        if value < 0:
            errors.add("invalid_id", path, f"dbf id 不能为负数: {value}")
            return None
        return CardRef("dbf", value)
    if not isinstance(value, str):
        errors.add(
            "invalid_id",
            path,
            f"id 必须是 int 或 str，实际为 {toml_io.type_name(value)}",
        )
        return None

    if DBF_RE.fullmatch(value):
        if not allow_numeric_string:
            errors.add(
                "invalid_id",
                path,
                f"字符串形式的纯数字 id 非法：{value!r}；dbf id 请用整数 {int(value)}",
            )
            return None
        return CardRef("dbf", int(value, 10))
    if CARD_ID_RE.fullmatch(value):
        return CardRef("card", value)
    errors.add(
        "invalid_id",
        path,
        f"id 只能由 [A-Za-z0-9_] 组成（或纯数字 dbf id），实际为 {value!r}",
    )
    return None


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def load_input(args: Any, cwd: str | Path | None = None) -> InputDraft:
    """把 CLI namespace（或同形 SimpleNamespace）归一成 :class:`InputDraft`。

    校验错误全部收集后抛 :class:`~eidolon.shell.errors.SpecErrors`。
    """
    errors = SpecErrors()
    base = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
    ids: Sequence[object] = list(args.ids or [])

    catalog_path: Path | None = None
    if args.catalog:
        catalog_path = _resolve(base, str(args.catalog))
        if args.command == "render":
            errors.add(
                "usage",
                "--catalog",
                "--catalog 仅用于 spec；render 必须使用与 core 同源的游戏数据",
            )
        if getattr(args, "game", None) is not None:
            errors.add(
                "usage",
                "--catalog",
                "--catalog 与 --game 不能同时使用（不要混用两个事实源）",
            )

    if args.toml is not None:
        if ids:
            errors.add(
                "mode",
                "<input>",
                "位置 id 与 --toml 不能同时使用（两种输入模式互斥）",
            )
        for flag, attr in _TOML_CONFLICT_FLAGS:
            if getattr(args, attr, None) is not None:
                errors.add(
                    "option_not_allowed",
                    flag,
                    f"{flag} 不能与 --toml 同时使用；TOML 模式只认文件",
                )
        errors.raise_if_any()
        return _load_toml(args, base, catalog_path, errors)

    if not ids:
        errors.add("mode", "<input>", "至少需要一个位置 id，或使用 --toml FILE")
        errors.raise_if_any()
        raise AssertionError("unreachable")
    return _load_inline(args, base, catalog_path, ids, errors)


# ---------------------------------------------------------------------------
# inline（命令行）模式
# ---------------------------------------------------------------------------


def _load_inline(
    args: Any,
    base: Path,
    catalog_path: Path | None,
    ids: Sequence[object],
    errors: SpecErrors,
) -> InputDraft:
    out_dir = _option_out_dir(args.outdir, base, errors)
    jobs = _option_jobs(args.jobs, errors)
    antialias = _option_bool(args.antialias, "--antialias", False, errors)
    hero_style = _option_bool(args.hero_style, "--hero-style", False, errors)
    bg_style = _option_bool(args.bg_style, "--bg-style", False, errors)

    game = _resolve_game(args, base, base, None, catalog_path, errors)

    # 不在这里提前 raise：多错误一次收集（与 TOML 路径一致），函数末尾统一抛。
    refs: list[tuple[str, CardRef]] = []
    seen_ids: set[tuple[str, int | str]] = set()
    for index, raw_id in enumerate(ids):
        path = f"ids[{index}]"
        ref = _parse_id(raw_id, path, errors, allow_numeric_string=True)
        if ref is None:
            continue
        key = (ref.kind, ref.value)
        if key in seen_ids:
            errors.add("duplicate_id", path, f"重复的 id {ref.value!r}")
            continue
        seen_ids.add(key)
        refs.append((str(raw_id), ref))

    cards: list[CardDraft] = []
    seen_outnames: set[str] = set()
    for input_id, ref in refs:
        outname = f"{ref.value}.png"
        key = outname.casefold()
        if key in seen_outnames:  # pragma: no cover - 唯一 ref 已保证不重名
            errors.add("duplicate_outname", "outname", f"outname 重名: {outname}")
        seen_outnames.add(key)
        cards.append(
            CardDraft(
                input_id=input_id,
                ref=ref,
                outname=outname,
                out_path=(out_dir / outname).resolve(),
            )
        )

    errors.raise_if_any()
    return InputDraft(
        command=args.command,
        source="inline",
        base=base,
        game=game,
        catalog_path=catalog_path,
        options=InputOptions(
            out_dir=out_dir,
            jobs=jobs,
            antialias=antialias,
            hero_style=hero_style,
            bg_style=bg_style,
        ),
        cards=tuple(cards),
    )


def _option_out_dir(value: Any, base: Path, errors: SpecErrors) -> Path:
    if value is None:
        return base.resolve()
    if not isinstance(value, (str, Path)):
        errors.add("type", "--outdir", "应为 str 路径")
        return base.resolve()
    return _resolve(base, str(value))


def _option_jobs(value: Any, errors: SpecErrors) -> int:
    if value is None:
        return 1
    if type(value) is not int:
        errors.add("type", "--jobs", f"应为 int，实际为 {toml_io.type_name(value)}")
        return 1
    if value < 1:
        errors.add("range", "--jobs", f"jobs 必须 >= 1，实际为 {value}")
    return value


def _option_bool(value: Any, flag: str, default: bool, errors: SpecErrors) -> bool:
    if value is None:
        return default
    if type(value) is not bool:
        errors.add("type", flag, f"应为 bool，实际为 {toml_io.type_name(value)}")
        return default
    return value


# ---------------------------------------------------------------------------
# TOML 模式
# ---------------------------------------------------------------------------


def _load_toml(
    args: Any,
    base: Path,
    catalog_path: Path | None,
    errors: SpecErrors,
) -> InputDraft:
    path = Path(args.toml)
    path = path if path.is_absolute() else (base / path)
    path = path.resolve()
    data = toml_io.load_document(path, errors)
    if data is None:
        errors.raise_if_any()
        raise AssertionError("unreachable")
    toml_io.validate_document(data, errors)
    toml_dir = path.parent

    format_version = data.get("format_version")
    if type(format_version) is int and format_version != 1:
        errors.add(
            "format_version",
            "format_version",
            f"仅支持 format_version = 1，实际为 {format_version}",
        )

    raw_out_dir = data.get("out_dir", ".")
    out_dir_text = raw_out_dir if isinstance(raw_out_dir, str) else "."
    out_dir = _resolve(toml_dir, out_dir_text)

    raw_jobs = data.get("jobs", 1)
    if type(raw_jobs) is int:
        jobs = raw_jobs
        if jobs < 1:
            errors.add("range", "jobs", f"jobs 必须 >= 1，实际为 {jobs}")
    else:
        jobs = 1

    raw_antialias = data.get("antialias", False)
    antialias = raw_antialias if type(raw_antialias) is bool else False

    game_toml = data.get("game_dir")
    game = _resolve_game(args, base, toml_dir, game_toml, catalog_path, errors)

    raw_cards = data.get("cards")
    if not isinstance(raw_cards, list):
        raw_cards = []
    elif not raw_cards:
        errors.add("empty_cards", "cards", "cards 不能为空")

    seen_ids: set[tuple[str, int | str]] = set()
    seen_outnames: set[str] = set()
    cards: list[CardDraft] = []
    for index, raw_card in enumerate(raw_cards):
        prefix = f"cards[{index}]"
        if not isinstance(raw_card, dict):
            continue
        if "id" not in raw_card:
            continue
        ref = _parse_id(raw_card["id"], f"{prefix}.id", errors, allow_numeric_string=False)
        if ref is None:
            continue
        key = (ref.kind, ref.value)
        if key in seen_ids:
            errors.add("duplicate_id", f"{prefix}.id", f"重复的 id {ref.value!r}")
            continue
        seen_ids.add(key)

        card = _card_draft(raw_card, prefix, ref, toml_dir, out_dir, errors)
        out_key = card.outname.casefold()
        if out_key in seen_outnames:
            errors.add(
                "duplicate_outname",
                f"{prefix}.outname",
                f"同批 outname 重名: {card.outname!r}",
            )
        else:
            seen_outnames.add(out_key)
        cards.append(card)

    errors.raise_if_any()
    return InputDraft(
        command=args.command,
        source="toml",
        base=toml_dir,
        game=game,
        catalog_path=catalog_path,
        options=InputOptions(out_dir=out_dir, jobs=jobs, antialias=antialias),
        cards=tuple(cards),
    )


# ---------------------------------------------------------------------------
# game_dir（显式安装根）
# ---------------------------------------------------------------------------


def _resolve_game(
    args: Any,
    base: Path,
    toml_dir: Path,
    game_toml: Any,
    catalog_path: Path | None,
    errors: SpecErrors,
) -> GameRequest:
    """--game > TOML game_dir；显式值必须在 load_input 里通过安装根校验。"""
    game_cli = getattr(args, "game", None)
    source = ""
    flag = ""
    raw = None
    if game_cli is not None:
        raw, source, flag = game_cli, "--game", "--game"
    elif isinstance(game_toml, str):
        raw, source, flag = game_toml, "toml game_dir", "game_dir"

    if catalog_path is not None and game_toml is not None and game_cli is None:
        errors.add(
            "usage",
            "--catalog",
            "--catalog 与 TOML game_dir 不能同时使用（TOML game_dir 也算 --game）",
        )

    if raw is None:
        return GameRequest(game_dir=None, source="")

    game_dir = _resolve(toml_dir if source == "toml game_dir" else base, str(raw))
    _validate_game_root(game_dir, flag, errors)
    return GameRequest(game_dir=game_dir, source=source)


def _validate_game_root(game_dir: Path, flag: str, errors: SpecErrors) -> None:
    if not game_dir.exists():
        errors.add("game_dir_invalid", flag, f"目录不存在: {game_dir}")
    elif not game_dir.is_dir():
        errors.add("game_dir_invalid", flag, f"不是目录: {game_dir}")
    elif not (game_dir / "Hearthstone.exe").is_file():
        errors.add(
            "game_dir_invalid", flag, f"缺少 Hearthstone.exe: {game_dir}"
        )


# ---------------------------------------------------------------------------
# 卡级结构（无 catalog 依赖）
# ---------------------------------------------------------------------------


def _card_draft(
    raw: dict[str, Any],
    prefix: str,
    ref: CardRef,
    toml_dir: Path,
    out_dir: Path,
    errors: SpecErrors,
) -> CardDraft:
    overrides: dict[str, object] = {}

    name = _string_or_none(raw, "name")
    if name is not None:
        overrides["name"] = name
    desc = _string_or_none(raw, "desc")
    if desc is not None:
        # TOML 多行字符串会在收尾定界符前保留一个换行；卡面描述不需要它。
        overrides["desc"] = desc.strip("\r\n")

    classes = _string_list_or_none(raw, "classes")
    if classes is not None:
        _validate_classes(classes, prefix, errors)
        overrides["classes"] = classes
    races = _string_list_or_none(raw, "races")
    if races is not None:
        _validate_races(races, prefix, errors)
        overrides["races"] = races

    for key in ("cost", "attack", "health", "armor", "tech_level"):
        value = _int_or_none(raw, key)
        if value is None:
            continue
        if key == "tech_level" and not (0 <= value <= 7):
            errors.add(
                "range",
                f"{prefix}.tech_level",
                f"tech_level 必须在 0..7，实际为 {value}",
            )
            continue
        overrides[key] = value

    for key in ("cardtype", "rarity", "spell_school"):
        value = _enum_or_none(raw, key, prefix, errors)
        if value is not None:
            overrides[key] = value

    premium = _validate_premium(raw, prefix, errors)
    if premium is not None:
        overrides["premium"] = premium
    banner = _validate_banner(raw, prefix, errors)
    if banner is not None:
        overrides["cost_banner"] = banner

    elite = _bool_or_none(raw, "elite")
    if elite is not None:
        overrides["elite"] = elite
    runes = _validate_runes(raw, prefix, errors)
    if runes is not None:
        overrides["runes"] = runes

    raw_hero = raw.get("hero_style", False)
    hero_style = raw_hero if type(raw_hero) is bool else False
    raw_bg = raw.get("bg_style", False)
    bg_style = raw_bg if type(raw_bg) is bool else False

    outname = _resolve_outname(raw, ref, prefix, errors)
    assets = _resolve_assets(raw, prefix, toml_dir, errors)

    return CardDraft(
        input_id=str(raw["id"]),
        ref=ref,
        outname=outname,
        out_path=(out_dir / outname).resolve(),
        overrides=overrides,
        assets=assets,
        hero_style=hero_style,
        bg_style=bg_style,
    )


def _validate_classes(
    classes: list[str], prefix: str, errors: SpecErrors
) -> None:
    if not classes:
        errors.add("empty_classes", f"{prefix}.classes", "classes 不能为空")
        return
    seen: set[str] = set()
    for index, name in enumerate(classes):
        path = f"{prefix}.classes[{index}]"
        if not name:
            errors.add("empty_class", path, "class 名不能为空")
        if name in seen:
            errors.add("duplicate_class", path, f"重复的职业 {name!r}")
        seen.add(name)


def _validate_races(races: list[str], prefix: str, errors: SpecErrors) -> None:
    seen: set[str] = set()
    for index, name in enumerate(races):
        path = f"{prefix}.races[{index}]"
        if not name.strip():
            errors.add("empty_race", path, "race 必须是非空字符串")
        if name in seen:
            errors.add("duplicate_race", path, f"重复的种族 {name!r}")
        seen.add(name)


def _enum_or_none(
    raw: dict[str, Any], key: str, prefix: str, errors: SpecErrors
) -> str | None:
    """字符串形状检查（非空）；成员校验属 compile_spec（需要 catalog）。"""
    if key not in raw:
        return None
    value = raw[key]
    if not isinstance(value, str):
        return None
    if not value:
        errors.add("enum", f"{prefix}.{key}", f"{key} 不能为空")
        return None
    return value


def _validate_premium(
    raw: dict[str, Any], prefix: str, errors: SpecErrors
) -> str | None:
    """premium 是产品常量（NORMAL/GOLDEN），只查 PREMIUMS，永不 deferred。"""
    if "premium" not in raw:
        return None
    value = raw["premium"]
    if not isinstance(value, str):
        return None
    path = f"{prefix}.premium"
    if not value:
        errors.add("enum", path, "premium 不能为空")
        return None
    if value not in PREMIUMS:
        errors.add("enum", path, f"premium 仅允许 NORMAL/GOLDEN，实际为 {value!r}")
    return value


def _validate_banner(
    raw: dict[str, Any], prefix: str, errors: SpecErrors
) -> str | None:
    if "cost_banner" not in raw:
        return None
    value = raw["cost_banner"]
    if not isinstance(value, str):
        return None
    path = f"{prefix}.cost_banner"
    if value not in BANNERS:
        errors.add("banner", path, f"未知的 cost_banner: {value!r}")
    return value


def _validate_runes(
    raw: dict[str, Any], prefix: str, errors: SpecErrors
) -> dict[str, int] | None:
    if "runes" not in raw:
        return None
    value = raw["runes"]
    if not isinstance(value, dict):
        return None
    runes: dict[str, int] = {}
    total = 0
    for rune, count in value.items():
        if not isinstance(rune, str):
            continue
        if type(count) is not int:
            continue
        runes[rune] = count
        path = f"{prefix}.runes.{rune}"
        if not rune:
            errors.add("empty_rune", path, "rune 名不能为空")
        elif rune not in RUNE_NAMES:
            errors.add(
                "unknown_rune",
                path,
                f"未知 rune 名 {rune!r}（只允许 BLOOD/FROST/UNHOLY）",
            )
        if not (0 <= count <= 3):
            errors.add("range", path, f"rune 计数必须在 0..3，实际为 {count}")
        else:
            total += count
    if total > 3:
        errors.add(
            "runes_total",
            f"{prefix}.runes",
            f"符文总和必须 <= 3，实际为 {total}",
        )
    return runes


def _resolve_outname(
    raw: dict[str, Any], ref: CardRef, prefix: str, errors: SpecErrors
) -> str:
    path = f"{prefix}.outname"
    value = raw.get("outname")
    candidate: str | None = None
    if isinstance(value, str):
        if not value:
            errors.add("outname", path, "outname 不能为空")
        else:
            candidate = value
    if candidate is not None:
        if "/" in candidate or "\\" in candidate or ".." in candidate:
            errors.add(
                "outname",
                path,
                f"outname 不能包含路径分隔符或 '..': {candidate!r}",
            )
            candidate = None
        elif not candidate.endswith(".png"):
            candidate = candidate + ".png"
    if candidate is None:
        candidate = f"{ref.value}.png"
    # 以 '.png' 结尾的路径仍然不能包含 '..'（例如 '..png'）。
    if ".." in candidate:
        errors.add("outname", path, f"outname 不能包含 '..': {candidate!r}")
        candidate = f"{ref.value}.png"
    return candidate


def _resolve_assets(
    raw: dict[str, Any],
    prefix: str,
    toml_dir: Path,
    errors: SpecErrors,
) -> dict[str, Path]:
    assets: dict[str, Path] = {}
    value = raw.get("asset")
    if not isinstance(value, dict):
        return assets
    for key in ("portrait", "frame", "watermark"):
        if key not in value:
            continue
        entry = value[key]
        if not isinstance(entry, str):
            continue
        path = f"{prefix}.asset.{key}"
        if not entry:
            errors.add("asset", path, "asset 路径不能为空")
            continue
        resolved = _resolve(toml_dir, entry)
        assets[key] = resolved
        if resolved.suffix.lower() != ".png":
            errors.add("asset_ext", path, f"asset 必须是 .png 文件: {entry!r}")
        if not resolved.is_file():
            errors.add("asset_missing", path, f"asset 文件不存在: {resolved}")
    return assets


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _string_or_none(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) else None


def _int_or_none(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    return value if type(value) is int else None


def _bool_or_none(raw: dict[str, Any], key: str) -> bool | None:
    value = raw.get(key)
    return value if type(value) is bool else None


def _string_list_or_none(raw: dict[str, Any], key: str) -> list[str] | None:
    value = raw.get(key)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return None
