"""catalog — DbfCatalog：纯 facts 索引（spec 消费面）。

分层约束（设计 §6.4）：本模块**只** import 标准库 + contracts + facts——
不得 import UnityPy / ``dbf`` / ``bundle_guard`` / ``card`` / ``game_tag`` /
``dll_reflect``。这保证 ``tests/core/test_catalog.py`` 无 UnityPy 可跑，且
``spec`` 路径不加载 CLR（提供方 ``provider.py`` 才 import ``dbf``）。

``complete = True`` 的语义：索引来自全量 dbf，查不到卡即 ``unknown_card``
（而非 deferred）。``duplicates`` 是 bind 期观测到的重复 card id 账面
（provider 负责转 warning）。
"""
from __future__ import annotations

from eidolon.contracts import CardFacts, CardRef
from eidolon.core.infra.facts import (
    KNOWN_CARDTYPES,
    KNOWN_CLASSES,
    KNOWN_RARITIES,
    KNOWN_SPELL_SCHOOLS,
)

__all__ = ["DbfCatalog"]


class DbfCatalog:
    """dbf 全量索引的只读 catalog（CardCatalog 协议实现）。

    构造收现成索引数据（provider 从 dbf 行构建；测试直接用 dict 构建，
    不经 dbf/UnityPy）：

    - ``by_dbf_id``：dbf id → CardFacts；
    - ``by_card_id``：guid casefold → CardFacts（查询同样 casefold）；
    - ``duplicates``：重复 card id（先到先得，重复者只记账不覆盖）。
    """

    complete = True
    known_classes = KNOWN_CLASSES
    known_cardtypes = KNOWN_CARDTYPES
    known_rarities = KNOWN_RARITIES
    known_spell_schools = KNOWN_SPELL_SCHOOLS

    def __init__(
        self,
        *,
        by_dbf_id: dict[int, CardFacts],
        by_card_id: dict[str, CardFacts],
        duplicates: tuple[str, ...] = (),
    ) -> None:
        self.by_dbf_id = by_dbf_id
        self.by_card_id = by_card_id
        self.duplicates: tuple[str, ...] = tuple(duplicates)

    def lookup(self, ref: CardRef) -> CardFacts | None:
        """按归一化 ref 查卡；索引里没有 → ``None``。"""
        if ref.kind == "dbf":
            return self.by_dbf_id.get(int(ref.value))
        return self.by_card_id.get(str(ref.value).casefold())
