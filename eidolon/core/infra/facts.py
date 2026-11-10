"""facts — 静态枚举镜像（spec 用；不 import live 枚举 / CLR）。

只服务 ``spec`` 的 catalog 事实投影：CARDTYPE / CLASS / RARITY / SPELL_SCHOOL
四个表的**枚举名快照**（取自上游 2026-11-08 对活表 ``dll_reflect.enum_table``
的实测，客户端 37.0.2）＋ ``cardtype_name`` 投影函数。集成测试在游戏可用时
逐表对拍活枚举，漂移即红（默认 discover 不收集该文件）。

维护纪律：镜像缺值 = 「版本未支持」，``bind`` / 覆盖映射响亮失败
（``EnvironmentUnavailable(constants_unavailable)``），不静默猜。

``known_*`` 是**名称集合**（含 ``INVALID``），不是 dbf 观测集；顺序固定为
枚举声明序（即下方各表的书写顺序），测试钉死。

本文件不依赖游戏运行时（只标准库 + contracts），也不得出现任何进程级
上下文读取——纯数据模块。
"""
from __future__ import annotations

from eidolon.contracts import EnvironmentUnavailable, Problem, ProblemKind

#: ``GAME_TAG.CARDTYPE`` 的 tag id（37.0.2 实测；集成测试对活表）。
CARD_TYPE_TAG_ID = 202

CARDTYPE_NAMES: dict[int, str] = {
    0: "INVALID",
    1: "GAME",
    2: "PLAYER",
    3: "HERO",
    4: "MINION",
    5: "SPELL",
    6: "ENCHANTMENT",
    7: "WEAPON",
    8: "ITEM",
    9: "TOKEN",
    10: "HERO_POWER",
    11: "BLANK",
    12: "GAME_MODE_BUTTON",
    22: "MOVE_MINION_HOVER_TARGET",
    23: "LETTUCE_ABILITY",
    24: "BATTLEGROUND_HERO_BUDDY",
    39: "LOCATION",
    40: "BATTLEGROUND_QUEST_REWARD",
    42: "BATTLEGROUND_SPELL",
    43: "BATTLEGROUND_ANOMALY",
    44: "BATTLEGROUND_TRINKET",
    45: "PET",
}

CLASS_NAMES: dict[int, str] = {
    0: "INVALID",
    1: "DEATHKNIGHT",
    2: "DRUID",
    3: "HUNTER",
    4: "MAGE",
    5: "PALADIN",
    6: "PRIEST",
    7: "ROGUE",
    8: "SHAMAN",
    9: "WARLOCK",
    10: "WARRIOR",
    11: "DREAM",
    12: "NEUTRAL",
    13: "WHIZBANG",
    14: "DEMONHUNTER",
}

RARITY_NAMES: dict[int, str] = {
    0: "INVALID",
    1: "COMMON",
    2: "FREE",
    3: "RARE",
    4: "EPIC",
    5: "LEGENDARY",
}

SPELL_SCHOOL_NAMES: dict[int, str] = {
    0: "NONE",
    1: "ARCANE",
    2: "FIRE",
    3: "FROST",
    4: "NATURE",
    5: "HOLY",
    6: "SHADOW",
    7: "FEL",
    8: "PHYSICAL_COMBAT",
    9: "TAVERN",
    10: "SPELLCRAFT",
    11: "LESSER_TRINKET",
    12: "GREATER_TRINKET",
    13: "UPGRADE",
}

#: 名称集合（枚举声明序；与上表书写顺序一致，测试钉死）。
KNOWN_CARDTYPES: tuple[str, ...] = tuple(CARDTYPE_NAMES.values())
KNOWN_CLASSES: tuple[str, ...] = tuple(CLASS_NAMES.values())
KNOWN_RARITIES: tuple[str, ...] = tuple(RARITY_NAMES.values())
KNOWN_SPELL_SCHOOLS: tuple[str, ...] = tuple(SPELL_SCHOOL_NAMES.values())


def cardtype_name(value: int) -> str:
    """dbf cardtype tag 值 → 枚举名；未命中 = 镜像缺口，响亮 ENV。"""
    name = CARDTYPE_NAMES.get(int(value))
    if name is None:
        raise EnvironmentUnavailable(Problem(
            ProblemKind.ENVIRONMENT,
            "constants_unavailable",
            "eidolon",
            f"constants_unavailable: CARDTYPE 值 {value!r} 不在静态镜像中"
            "（客户端版本超出已支持集合；升级 facts 镜像）",
        ))
    return name
