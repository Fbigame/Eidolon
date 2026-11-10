"""输入阶段二 + 统一面：InputDraft + CatalogBinding → :class:`RenderSpec`。

``compile_spec`` 只做 catalog 依赖的检查：``unknown_card``、classes /
cardtype / rarity / spell_school 的 ``known_*`` 成员、hero/bg style 适用
性。产品常量（premium / cost_banner）已在 ``load_input`` 校验，永不
deferred。``build_spec`` 保留为兼容包装（load_input + 手工 binding +
compile_spec）；新代码走两阶段。

id 解析与产品常量定义在 :mod:`eidolon.shell.input`（阶段一），此处按公开
API 兼容 re-export。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Sequence

from eidolon.contracts import (
    CardCatalog,
    CardFacts,
    CardRef,
    CatalogBinding,
    CatalogIdentity,
    GameContext,
)

from .catalog import NullCatalog
from .errors import SpecErrors
from .input import BANNERS, PREMIUMS, load_input, parse_id

if TYPE_CHECKING:
    from .input import CardDraft, InputDraft

__all__ = [
    "BANNERS",
    "PREMIUMS",
    "CardSpec",
    "RenderOptions",
    "RenderSpec",
    "build_spec",
    "compile_spec",
    "parse_id",
]

# manifest overrides.fields 的稳定输出顺序（只输出显式给出的字段）。
FIELD_ORDER = (
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
    "tech_level",
    "runes",
)

# deferred 的稳定输出顺序。premium / cost_banner 是产品常量（PREMIUMS /
# BANNERS），永不 deferred，故不在序列里。
DEFERRED_ORDER = (
    "classes",
    "cardtype",
    "rarity",
    "spell_school",
    "hero_style",
    "bg_style",
)

ASSET_KEYS = ("portrait", "frame", "watermark")


@dataclass(frozen=True)
class RenderOptions:
    out_dir: Path
    jobs: int = 1
    antialias: bool = False


@dataclass
class CardSpec:
    """一张卡的归一化结果。``None`` 表示未覆盖、交给渲染层走数据。"""

    input_id: str
    ref: CardRef
    outname: str
    out_path: Path
    name: str | None = None
    desc: str | None = None
    classes: list[str] | None = None
    races: list[str] | None = None
    cost: int | None = None
    attack: int | None = None
    health: int | None = None
    armor: int | None = None
    cardtype: str | None = None
    rarity: str | None = None
    premium: str | None = None
    spell_school: str | None = None
    cost_banner: str | None = None
    elite: bool | None = None
    runes: dict[str, int] | None = None
    tech_level: int | None = None
    hero_style: bool = False
    bg_style: bool = False
    # 用户请求原样保留（全局开关 or 卡级开关；§5.4），不按 catalog 事实裁剪。
    # 不进 plan manifest；进结果 manifest，是 adapter→core 的 hero/bg 语义输入。
    style_requested: tuple[bool, bool] = (False, False)
    assets: dict[str, Path] = field(default_factory=dict)
    deferred: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderSpec:
    """统一输入面：CardSpec 列表 + 全局选项 + game / catalog 身份。"""

    source: str
    options: RenderOptions
    cards: tuple[CardSpec, ...]
    game: GameContext | None = None
    catalog: CatalogIdentity = CatalogIdentity(kind="null")
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# compile_spec（阶段二）
# ---------------------------------------------------------------------------


def compile_spec(draft: InputDraft, binding: CatalogBinding) -> RenderSpec:
    """只做 catalog 依赖的检查；校验错误全部收集后抛 :class:`SpecErrors`。"""
    catalog = binding.catalog
    errors = SpecErrors()
    facts = [catalog.lookup(card.ref) for card in draft.cards]

    if draft.source == "inline":
        # §5.4：批级 style 检查按「每卡生效 cardtype」（含 cardtype 覆盖）。
        _check_batch_styles(
            draft.options,
            [_effective_cardtype(card, fact) for card, fact in zip(draft.cards, facts)],
            errors,
        )

    warnings: list[str] = list(draft.warnings) + list(binding.warnings)
    cards = [
        _compile_card(draft, index, card, card_facts, catalog, errors)
        for index, (card, card_facts) in enumerate(zip(draft.cards, facts))
    ]
    errors.raise_if_any()
    if any(card.deferred for card in cards):
        # catalog_incomplete：仅当 complete=False、非 null catalog、且实际
        # 产生了 deferred；null catalog 的逐卡 deferred 已说明弱化范围。
        if not catalog.complete and binding.identity.kind != "null":
            warnings.append("catalog_incomplete")
    return RenderSpec(
        source=draft.source,
        options=RenderOptions(
            out_dir=draft.options.out_dir,
            jobs=draft.options.jobs,
            antialias=draft.options.antialias,
        ),
        cards=tuple(cards),
        game=binding.game,
        catalog=binding.identity,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _effective_cardtype(card: "CardDraft", card_facts: CardFacts | None) -> str | None:
    """生效 cardtype（§5.4）：``cardtype`` 覆盖优先；facts 缺失/空才 ``None``。"""
    override = card.overrides.get("cardtype")
    if override:
        return str(override)
    if card_facts is not None and card_facts.cardtype:
        return card_facts.cardtype
    return None


def _check_batch_styles(
    options: Any, cardtypes: Sequence[str | None], errors: SpecErrors
) -> None:
    """CLI 全局 style 开关的「本批无适用卡」检查（按生效 cardtype，§5.4）。

    ``cardtypes`` 是每卡生效 cardtype（含 cardtype 覆盖）；存在生效
    cardtype 未知的卡时 defer（不报「本批没有适用卡」——未知卡可能适用）。
    """
    hero_requested = bool(options.hero_style)
    bg_requested = bool(options.bg_style)
    if not (hero_requested or bg_requested) or not cardtypes:
        return
    known = [cardtype for cardtype in cardtypes if cardtype]
    unknown_any = any(not cardtype for cardtype in cardtypes)
    if (
        hero_requested
        and not any(cardtype == "HERO" for cardtype in known)
        and not unknown_any
    ):
        errors.add(
            "style", "--hero-style", "本批没有任何 HERO 卡适用 --hero-style"
        )
    if (
        bg_requested
        and not any(cardtype != "HERO" for cardtype in known)
        and not unknown_any
    ):
        errors.add(
            "style", "--bg-style", "本批没有任何非 HERO 卡适用 --bg-style"
        )


def _compile_card(
    draft: InputDraft,
    index: int,
    card: CardDraft,
    card_facts: CardFacts | None,
    catalog: CardCatalog,
    errors: SpecErrors,
) -> CardSpec:
    prefix = f"cards[{index}]" if draft.source == "toml" else f"ids[{index}]"
    deferred: set[str] = set()
    overrides = card.overrides
    # 生效 cardtype（§5.4）：cardtype 覆盖优先；style 语义全部按它。
    effective_cardtype = _effective_cardtype(card, card_facts)

    # 存在性判定：complete catalog 查不到卡 = 输入错误；不 complete 只 deferred。
    if card_facts is None and catalog.complete:
        errors.add(
            "unknown_card",
            prefix if draft.source == "toml" else f"ids[{index}]",
            f"{'dbf' if card.ref.is_dbf else 'card'} id {card.ref.value} 不在当前游戏数据中",
        )

    classes = overrides.get("classes")
    if classes is not None:
        known_classes = catalog.known_classes
        if not known_classes:
            deferred.add("classes")
        else:
            for i, name in enumerate(classes):
                if name and name not in known_classes:
                    errors.add(
                        "unknown_class",
                        f"{prefix}.classes[{i}]",
                        f"未知职业 {name!r}",
                    )

    for key, known in (
        ("cardtype", catalog.known_cardtypes),
        ("rarity", catalog.known_rarities),
        ("spell_school", catalog.known_spell_schools),
    ):
        value = overrides.get(key)
        if value is None:
            continue
        if not known:
            deferred.add(key)
        elif value not in known:
            errors.add("enum", f"{prefix}.{key}", f"未知的 {key}: {value!r}")

    hero_requested = bool(draft.options.hero_style) or bool(card.hero_style)
    bg_requested = bool(draft.options.bg_style) or bool(card.bg_style)

    if effective_cardtype is not None:
        # TOML 显式意图错误：显式给出的开关落不到该卡上（按生效 cardtype）。
        if draft.source == "toml":
            if card.hero_style and effective_cardtype != "HERO":
                errors.add(
                    "style",
                    f"{prefix}.hero_style",
                    f"hero_style 只适用于 HERO 卡；该卡 cardtype={effective_cardtype!r}",
                )
            if card.bg_style and effective_cardtype == "HERO":
                errors.add(
                    "style",
                    f"{prefix}.bg_style",
                    "bg_style 不适用于 HERO 卡",
                )
        hero_style = hero_requested and effective_cardtype == "HERO"
        bg_style = bg_requested and effective_cardtype != "HERO"
    else:
        # 卡未知（且无 cardtype 覆盖）：开关请求保留为 True，检查 deferred。
        hero_style = hero_requested
        bg_style = bg_requested
        if hero_requested:
            deferred.add("hero_style")
        if bg_requested:
            deferred.add("bg_style")

    return CardSpec(
        input_id=card.input_id,
        ref=card.ref,
        outname=card.outname,
        out_path=card.out_path,
        name=overrides.get("name"),  # type: ignore[arg-type]
        desc=overrides.get("desc"),  # type: ignore[arg-type]
        classes=overrides.get("classes"),  # type: ignore[arg-type]
        races=overrides.get("races"),  # type: ignore[arg-type]
        cost=overrides.get("cost"),  # type: ignore[arg-type]
        attack=overrides.get("attack"),  # type: ignore[arg-type]
        health=overrides.get("health"),  # type: ignore[arg-type]
        armor=overrides.get("armor"),  # type: ignore[arg-type]
        cardtype=overrides.get("cardtype"),  # type: ignore[arg-type]
        rarity=overrides.get("rarity"),  # type: ignore[arg-type]
        premium=overrides.get("premium"),  # type: ignore[arg-type]
        spell_school=overrides.get("spell_school"),  # type: ignore[arg-type]
        cost_banner=overrides.get("cost_banner"),  # type: ignore[arg-type]
        elite=overrides.get("elite"),  # type: ignore[arg-type]
        runes=overrides.get("runes"),  # type: ignore[arg-type]
        tech_level=overrides.get("tech_level"),  # type: ignore[arg-type]
        hero_style=hero_style,
        bg_style=bg_style,
        style_requested=(hero_requested, bg_requested),
        assets=dict(card.assets),
        deferred=_ordered_deferred(deferred),
    )


# ---------------------------------------------------------------------------
# build_spec（兼容包装）
# ---------------------------------------------------------------------------


def build_spec(
    ids: Sequence[object] | None = None,
    *,
    toml_path: str | Path | None = None,
    out_dir: str | Path | None = None,
    jobs: int | None = None,
    antialias: bool | None = None,
    hero_style: bool | None = None,
    bg_style: bool | None = None,
    catalog: CardCatalog | None = None,
    cwd: str | Path | None = None,
) -> RenderSpec:
    """兼容包装：``compile_spec(load_input(...), binding)``。新代码走两阶段。

    参数 ``out_dir`` / ``jobs`` / ``antialias`` / ``hero_style`` /
    ``bg_style`` 是「命令行显式给出的选项」；TOML 模式下任何一个非 None
    都会报错（TOML 只认文件）。
    """
    args = SimpleNamespace(
        command="spec",
        ids=list(ids) if ids is not None else None,
        toml=toml_path,
        outdir=out_dir,
        jobs=jobs,
        antialias=antialias,
        hero_style=hero_style,
        bg_style=bg_style,
        catalog=None,  # catalog 对象走 binding 注入，不经 --catalog 路径
        game=None,
        locale=None,
        cache_root=None,
    )
    draft = load_input(args, cwd)
    effective_catalog = catalog if catalog is not None else NullCatalog()
    binding = CatalogBinding(
        catalog=effective_catalog,
        game=None,
        identity=CatalogIdentity(
            kind="null" if catalog is None else "json",
            path="" if catalog is None else "<memory>",
            complete=effective_catalog.complete,
        ),
    )
    return compile_spec(draft, binding)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _ordered_deferred(values: set[str]) -> tuple[str, ...]:
    return tuple(name for name in DEFERRED_ORDER if name in values)
