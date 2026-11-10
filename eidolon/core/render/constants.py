"""constants — CardConstants 注入面（设计 §7.4 常量注入单点）。

``card_overrides`` 的**全部** name→值查询与 tag 名→id 查询走
:class:`CardConstants`；本件是生产构造器（``live_card_constants()``）。

P0 纪律：模块顶层只 import 标准库 + ``eidolon.contracts``——dataclass 定义
不触 live 枚举；live ``CardClass``/``CardType``/``Rarity``/``SpellSchool``/
``Premium``/``GameTag`` 只在 ``live_card_constants()`` **函数体内** import
（CLR-at-import 链，设计 §6.5/§7.1.1：只在 ``context.install`` 之后触达）。

缺名语义（§7.4 缺名两分类的 ENV 侧）：live 枚举/白名单缺名（版本漂移）、
coreclr 装载失败 → ``EnvironmentUnavailable(ENVIRONMENT, "constants_unavailable")``
（§12.1，比 ``dependency_missing`` 更具体）；pythonnet 包缺失
（ModuleNotFoundError）保持原类型上抛——§7.8 归 ``dependency_missing``。
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from eidolon.contracts import Problem, ProblemKind, EnvironmentUnavailable

__all__ = ["CardConstants", "live_card_constants"]


@dataclass(frozen=True)
class CardConstants:
    """覆盖映射查表面（生产=live 枚举镜像；测试=手工 dict）。

    表键一律**用户词汇**（shell ``CardSpec`` 同名值）；表值 int：
    - ``classes``：CardClass name → value（生产=live ``CardClass`` 全镜像，
      含 ``INVALID=0``——value>=1 由 ``card_overrides`` 校验）；
    - ``cardtypes`` / ``rarities`` / ``schools``：同名枚举 name → value；
    - ``premiums``：只 ``NORMAL`` / ``GOLDEN``（产品政策，shell ``PREMIUMS``
      常量同词汇；DIAMOND/SIGNATURE/MAX 非品质档，不入表）；
    - ``banners``：BANNER name → tag id（9 个 faction/badge 名；``NONE``
      不在表内——它只清空，无 tag 可写）；
    - ``tags``：tag 名 → tag id（COST/ATK/HEALTH/ARMOR/CARDTYPE/RARITY/
      PREMIUM/SPELL_SCHOOL/ELITE/TECH_LEVEL/CLASS/MULTIPLE_CLASSES/
      COST_BLOOD/COST_FROST/COST_UNHOLY）。
    """

    classes: Mapping[str, int]
    cardtypes: Mapping[str, int]
    rarities: Mapping[str, int]
    schools: Mapping[str, int]
    premiums: Mapping[str, int]
    banners: Mapping[str, int]
    tags: Mapping[str, int]


_PREMIUM_NAMES = ("NORMAL", "GOLDEN")
"""产品品质档词汇（shell ``PREMIUMS`` 常量同词汇；§7.4 premiums 行）。"""

_BANNER_NAMES = (
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
"""banner 九选一词汇（§7.4 cost_banner 行；shell ``BANNERS`` 去 NONE 同序）。"""

_TAG_NAMES = (
    "COST",
    "ATK",
    "HEALTH",
    "ARMOR",
    "CARDTYPE",
    "RARITY",
    "PREMIUM",
    "SPELL_SCHOOL",
    "ELITE",
    "TECH_LEVEL",
    "CLASS",
    "MULTIPLE_CLASSES",
    "COST_BLOOD",
    "COST_FROST",
    "COST_UNHOLY",
)
"""覆盖映射要写的 tag 名集（§7.4 全表；id 一律 live ``GameTag`` 供货）。"""


def _constants_unavailable(what: str, exc: Exception) -> EnvironmentUnavailable:
    cause = f"{type(exc).__name__}: {exc}"
    return EnvironmentUnavailable(Problem(
        ProblemKind.ENVIRONMENT,
        "constants_unavailable",
        "eidolon",
        f"constants_unavailable: {what}（{cause}）",
        cause=cause,
    ))


def live_card_constants() -> CardConstants:
    """live 枚举镜像 → CardConstants（``_render_one`` 在 ``Card.from_dbf``
    之后调用；CLR-at-import，函数体内才触）。

    缺名/装载失败 → ``EnvironmentUnavailable(constants_unavailable)``，
    message 点名缺失成员（live 镜像的 ImportError 消息透传进 cause）；
    pythonnet 包缺失（ModuleNotFoundError）原样上抛（§7.8 →
    ``dependency_missing``）。
    """
    try:
        from eidolon.core.infra.card import (
            CardClass,
            CardType,
            Rarity,
            SpellSchool,
            Premium,
        )
        from eidolon.core.infra.game_tag import GameTag

        classes = {m.name: int(m) for m in CardClass}
        cardtypes = {m.name: int(m) for m in CardType}
        rarities = {m.name: int(m) for m in Rarity}
        schools = {m.name: int(m) for m in SpellSchool}
        premiums = {name: int(getattr(Premium, name)) for name in _PREMIUM_NAMES}
        banners = {name: int(getattr(GameTag, name)) for name in _BANNER_NAMES}
        tags = {name: int(getattr(GameTag, name)) for name in _TAG_NAMES}
    except ModuleNotFoundError:
        raise
    except (ImportError, RuntimeError, AssertionError, AttributeError) as exc:
        raise _constants_unavailable(
            "live 枚举/GameTag 白名单缺名或装载失败（先核 Assembly-CSharp）", exc
        ) from exc
    return CardConstants(
        classes=MappingProxyType(classes),
        cardtypes=MappingProxyType(cardtypes),
        rarities=MappingProxyType(rarities),
        schools=MappingProxyType(schools),
        premiums=MappingProxyType(premiums),
        banners=MappingProxyType(banners),
        tags=MappingProxyType(tags),
    )
