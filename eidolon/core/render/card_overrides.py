"""card_overrides — 覆盖映射单点（设计 §7.4 映射表的逐行实现）。

``apply(card, render_card, constants)`` 把 ``RenderCard.overrides`` /
``RenderCard.assets`` 逐行写到 Card 的覆盖座位（tag / text / 资产座位）。
form（hero_style/bg_style/resolve_form）**不在本函数**——由 ``api._render_one``
与 ``preflight.validate_overrides`` 在覆盖后的 Card 上计算（§7.3）。

P0 纪律（守卫钉住）：顶层只 import 标准库 + ``eidolon.contracts`` +
``eidolon.core.render.constants``；**禁止** import ``core.infra.card`` /
``game_tag`` / ``dll_reflect``——全部 name→值查询与 tag 名→id 查询走
``CardConstants``，本模块对 live 枚举零依赖（测试用 fake Card + fake
CardConstants 直调，不载 CLR）。

失败语义：每步失败抛 ``InputRejected``（INPUT，preflight → 2；render 期被
``_classify`` 归 render_failed 1）或 ``EnvironmentUnavailable``（镜像缺口，
ENV 3）。``Problem.path`` 只带键级定位（如 ``cost`` / ``assets.frame``）——
``cards[i]`` 的卡序由调用方（adapter / preflight）补；message 必带 key 名。
"""
from __future__ import annotations

from typing import Mapping

from eidolon.contracts import Problem, ProblemKind, InputRejected, EnvironmentUnavailable
from eidolon.core.render.constants import CardConstants

__all__ = ["apply"]


def _input_rejected(key: str, code: str, message: str) -> InputRejected:
    return InputRejected(Problem(
        ProblemKind.INPUT,
        code,
        key,
        f"{code}: 覆盖项 {key!r} {message}",
    ))


def _mirror_gap(key: str, name: str, what: str) -> EnvironmentUnavailable:
    return EnvironmentUnavailable(Problem(
        ProblemKind.ENVIRONMENT,
        "constants_unavailable",
        "eidolon",
        f"constants_unavailable: 覆盖项 {key!r} 的值 {name!r} 不在 live 枚举镜像"
        f"（{what}）——版本漂移，先核 Assembly-CSharp",
        cause=f"KeyError: {name}",
    ))


def _as_int(key: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _input_rejected(key, "type", f"需要整数，实际为 {value!r}")
    return value


def _str_value(key: str, value: object) -> str:
    if not isinstance(value, str):
        raise _input_rejected(key, "type", f"需要字符串，实际为 {value!r}")
    return value


def _apply_classes(card, key: str, value: object, constants: CardConstants) -> None:
    """classes → CLASS / MULTIPLE_CLASSES（§7.4 位掩码行）。

    1 个 → CLASS=值、MULTIPLE_CLASSES=0；≥2 → 位掩码 ``OR(1<<(v-1))``、
    CLASS=0（引擎 GetClasses：bit i → TAG_CLASS i+1）。``value>=1`` 之外
    （含 INVALID=0）一律 ``InputRejected(enum)``——INVALID 不参与覆盖。
    """
    if not isinstance(value, (list, tuple)):
        raise _input_rejected(key, "type", f"需要职业名列表，实际为 {value!r}")
    if not value:
        raise _input_rejected(key, "empty_classes", "classes 不能为空")
    values: list[int] = []
    for name in value:
        name = _str_value(key, name)
        cls = constants.classes.get(name)
        if cls is None:
            raise _input_rejected(
                key, "enum", f"未知职业名 {name!r}（不在 CardClass 镜像）")
        if cls < 1:
            raise _input_rejected(
                key, "enum", f"职业 {name!r} 值为 {cls}（value>=1 才可覆盖）")
        values.append(cls)
    class_tag = constants.tags["CLASS"]
    multi_tag = constants.tags["MULTIPLE_CLASSES"]
    if len(values) == 1:
        card.tags[class_tag] = values[0]
        card.tags[multi_tag] = 0
        return
    mask = 0
    for cls in values:
        mask |= 1 << (cls - 1)
    card.tags[multi_tag] = mask
    card.tags[class_tag] = 0


def _apply_races(card, key: str, value: object) -> None:
    """races → ``card.races_text_override = tuple(str)``（§7.4/§10.2 显示覆盖）。

    **不写种族 tag**（CARDRACE/CARD_RACE 数据轴不动——颜色/种族板几何仍吃
    数据轴；本座位只改 GetRaceText 输出与板数）。空 tuple 合法 = 隐藏文本。
    """
    if not isinstance(value, (list, tuple)):
        raise _input_rejected(key, "type", f"需要种族名列表，实际为 {value!r}")
    card.races_text_override = tuple(_str_value(key, race) for race in value)


def _apply_enum_tag(
    card, key: str, value: object, constants: CardConstants,
    table: Mapping[str, int], tag_name: str, what: str,
    *, input_on_miss: bool,
) -> None:
    """cardtype/rarity/premium/spell_school → constants 查表写 tag。

    缺名分两类（§7.4）：产品政策词汇（premium：只 NORMAL/GOLDEN）缺名=
    用户输入错 → ``InputRejected``；live 镜像词汇（cardtype/rarity/
    spell_school，shell 已按 facts 拦截）缺名=镜像缺口 → ENV
    ``constants_unavailable``。
    """
    name = _str_value(key, value)
    mapped = table.get(name)
    if mapped is None:
        if input_on_miss:
            raise _input_rejected(
                key, "enum", f"未知 {what} 名 {name!r}（产品只收 "
                f"{sorted(table)}）")
        raise _mirror_gap(key, name, what)
    card.tags[constants.tags[tag_name]] = mapped


_BANNER_CLEAR_TAGS = (
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
"""cost_banner 九清一置的清空序（§7.4：faction 6 + badge 3，保证九选一）。"""


def _apply_cost_banner(card, key: str, value: object, constants: CardConstants) -> None:
    """cost_banner → 先清 9 个 banner tag 再置 1；``NONE`` 只清空。"""
    name = _str_value(key, value)
    ids = []
    for bn in _BANNER_CLEAR_TAGS:
        tag_id = constants.banners.get(bn)
        if tag_id is None:
            raise _mirror_gap(key, bn, "banner tag（GameTag 白名单）")
        ids.append(tag_id)
    for tag_id in ids:
        card.tags[tag_id] = 0
    if name == "NONE":
        return
    tag_id = constants.banners.get(name)
    if tag_id is None:
        raise _input_rejected(
            key, "banner",
            f"未知 banner 名 {name!r}（NONE + {', '.join(_BANNER_CLEAR_TAGS)} 之外）")
    card.tags[tag_id] = 1


_RUNE_TAGS = ("COST_BLOOD", "COST_FROST", "COST_UNHOLY")
_RUNE_KEYS = {"BLOOD": "COST_BLOOD", "FROST": "COST_FROST", "UNHOLY": "COST_UNHOLY"}


def _apply_runes(card, key: str, value: object, constants: CardConstants) -> None:
    """runes → 先清三个 rune tag 再按 dict 置值（键只允许 BLOOD/FROST/UNHOLY）。"""
    if not isinstance(value, Mapping):
        raise _input_rejected(key, "type", f"需要符文 dict，实际为 {value!r}")
    tag_ids = {tag_name: constants.tags[tag_name] for tag_name in _RUNE_TAGS}
    for tag_id in tag_ids.values():
        card.tags[tag_id] = 0
    for rune, count in value.items():
        tag_name = _RUNE_KEYS.get(rune)
        if tag_name is None:
            raise _input_rejected(
                key, "unknown_rune",
                f"未知符文键 {rune!r}（只允许 BLOOD/FROST/UNHOLY）")
        card.tags[tag_ids[tag_name]] = _as_int(f"{key}.{rune}", count)


_ASSET_SEATS = ("portrait", "frame", "watermark")


def _apply_assets(card, key: str, value: object) -> None:
    """assets 三座位 → Card 资产座位（契约 E 接缝；§10.0 语义）。

    ``watermark`` 覆盖同时置 ``watermark_force=True``（显式覆盖即强制显示，
    忽略 HIDE_WATERMARK 闸）。值=Path（contracts ``RenderCard.assets``）。
    """
    if not isinstance(value, Mapping):
        raise _input_rejected(key, "type", f"需要资产 dict，实际为 {value!r}")
    for seat, path in value.items():
        seat_key = f"{key}.{seat}"
        if seat not in _ASSET_SEATS:
            raise _input_rejected(
                seat_key, "unknown_key",
                f"未知资产座位 {seat!r}（只允许 portrait/frame/watermark）")
        text = str(path)
        if seat == "portrait":
            card.portrait_asset = text
        elif seat == "frame":
            card.frame_asset = text
        else:
            card.watermark_asset = text
            card.watermark_force = True


_STAT_TAG_NAMES = {"cost": "COST", "attack": "ATK", "health": "HEALTH", "armor": "ARMOR"}
"""数值四键 → tag 名（引擎 tag 名是 ATK，不是 ATTACK）。"""


def apply(card, render_card, constants: CardConstants) -> None:
    """按 §7.4 映射表把 ``render_card`` 的覆盖写到 ``card``（就地修改）。

    顺序=映射表行序（name/desc/classes/races → 数值 tag → 枚举查表 →
    banner/runes → elite/tech_level → assets）。每行失败即抛（带键级
    path）；不回滚已写行——preflight/渲染两条路都会整体放弃该卡。
    """
    overrides = render_card.overrides
    if overrides:
        for key, value in overrides.items():
            if key == "name":
                card.name = _str_value(key, value)
            elif key == "desc":
                card.text = _str_value(key, value)   # text_overridden 自动为真
            elif key == "classes":
                _apply_classes(card, key, value, constants)
            elif key == "races":
                _apply_races(card, key, value)
            elif key in _STAT_TAG_NAMES:
                card.tags[constants.tags[_STAT_TAG_NAMES[key]]] = _as_int(key, value)
            elif key == "cardtype":
                _apply_enum_tag(card, key, value, constants, constants.cardtypes,
                                "CARDTYPE", "cardtype", input_on_miss=False)
            elif key == "rarity":
                _apply_enum_tag(card, key, value, constants, constants.rarities,
                                "RARITY", "rarity", input_on_miss=False)
            elif key == "premium":
                _apply_enum_tag(card, key, value, constants, constants.premiums,
                                "PREMIUM", "premium", input_on_miss=True)
            elif key == "spell_school":
                _apply_enum_tag(card, key, value, constants, constants.schools,
                                "SPELL_SCHOOL", "spell_school", input_on_miss=False)
            elif key == "cost_banner":
                _apply_cost_banner(card, key, value, constants)
            elif key == "elite":
                card.tags[constants.tags["ELITE"]] = 1 if value else 0
            elif key == "runes":
                _apply_runes(card, key, value, constants)
            elif key == "tech_level":
                card.tags[constants.tags["TECH_LEVEL"]] = _as_int(key, value)
            else:
                raise _input_rejected(
                    key, "unknown_key",
                    f"未知覆盖键 {key!r}（§7.4 映射表 16 键之外）")
    if render_card.assets:
        _apply_assets(card, "assets", render_card.assets)
