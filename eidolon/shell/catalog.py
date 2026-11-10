"""卡牌事实目录（catalog）：dev/test 用的 NullCatalog / JsonCatalog。

外壳不依赖游戏数据；catalog 只提供「已知枚举值」与逐卡 ``cardtype``，
用于把可选校验从 ``deferred`` 提升为真实校验。没有 catalog 时用
:class:`NullCatalog`。``complete`` 表示索引覆盖是否完整：complete 的
catalog 查不到卡即 ``unknown_card``（输入错误）；不 complete 只
``deferred``。真实的 dbf catalog（``DbfCatalog`` / ``DbfCatalogProvider``）
在 core 接入轮落地。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eidolon.contracts import (
    CardFacts,
    CardRef,
    CatalogBinding,
    CatalogIdentity,
    GameRequest,
)


class CatalogError(ValueError):
    """catalog 文件/结构非法。"""


class NullCatalog:
    """空 catalog：complete=False，所有 known_* 为空，lookup 恒为 None。"""

    complete: bool = False
    known_classes: tuple[str, ...] = ()
    known_cardtypes: tuple[str, ...] = ()
    known_rarities: tuple[str, ...] = ()
    known_spell_schools: tuple[str, ...] = ()

    def lookup(self, ref: CardRef) -> CardFacts | None:
        return None


def _string_tuple(data: dict[str, Any], key: str, *, required: bool = False) -> tuple[str, ...]:
    if key not in data:
        if required:
            raise CatalogError(f"缺少 {key}")
        return ()
    value = data[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CatalogError(f"{key} 必须是字符串数组")
    return tuple(value)


# catalog 顶层只接受这些键；未知键一律拒绝（与 TOML 侧同样严格）。
_TOP_LEVEL_KEYS = frozenset(
    {
        "complete",
        "known_classes",
        "known_cardtypes",
        "known_rarities",
        "known_spell_schools",
        "cards",
    }
)


class JsonCatalog:
    """从 JSON fixture 读取的 catalog。

    结构::

        {
          "complete": false,
          "known_classes": ["MAGE", ...],
          "known_cardtypes": ["HERO", ...],
          "known_rarities": [...],
          "known_spell_schools": [...],
          "cards": {
            "8": {"cardtype": "MINION"},
            "CS2_182": {"cardtype": "MINION"}
          }
        }

    ``complete`` 从顶层读取，缺省 ``False``。``cards`` 的 key 与
    :class:`~eidolon.contracts.CardRef` 的归一化 ``value`` 一致（dbf id
    用十进制字符串，card id 原样）；卡条目 v1 只投影 ``cardtype``。
    """

    def __init__(
        self,
        *,
        cards: dict[str, CardFacts],
        known_classes: tuple[str, ...] = (),
        known_cardtypes: tuple[str, ...] = (),
        known_rarities: tuple[str, ...] = (),
        known_spell_schools: tuple[str, ...] = (),
        complete: bool = False,
    ) -> None:
        self._cards = dict(cards)
        self.complete = bool(complete)
        self.known_classes = tuple(known_classes)
        self.known_cardtypes = tuple(known_cardtypes)
        self.known_rarities = tuple(known_rarities)
        self.known_spell_schools = tuple(known_spell_schools)

    def lookup(self, ref: CardRef) -> CardFacts | None:
        return self._cards.get(str(ref.value))

    @property
    def cards(self) -> dict[str, CardFacts]:
        return dict(self._cards)

    @classmethod
    def from_path(cls, path: str | Path) -> "JsonCatalog":
        source = Path(path)
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise CatalogError(f"无法读取 catalog {source}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise CatalogError(f"catalog 不是合法 UTF-8 {source}: {exc}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CatalogError(f"catalog JSON 非法 {source}: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "JsonCatalog":
        if not isinstance(data, dict):
            raise CatalogError("catalog 顶层必须是 JSON 对象")

        for key in sorted(data):
            if key not in _TOP_LEVEL_KEYS:
                raise CatalogError(f"未知的 catalog 顶层键 {key!r}")

        complete = data.get("complete", False)
        if type(complete) is not bool:
            raise CatalogError("complete 必须是 bool")

        raw_cards = data.get("cards", {})
        if not isinstance(raw_cards, dict):
            raise CatalogError("cards 必须是 JSON 对象")
        cards: dict[str, CardFacts] = {}
        for key, item in raw_cards.items():
            if not isinstance(key, str) or not key:
                raise CatalogError("cards 的 key 必须是非空字符串")
            if not isinstance(item, dict):
                raise CatalogError(f"cards[{key!r}] 必须是 JSON 对象")
            for field_name in sorted(item):
                if field_name != "cardtype":
                    raise CatalogError(
                        f"cards[{key!r}] 不支持键 {field_name!r}（v1 只投影 cardtype）"
                    )
            cardtype = item.get("cardtype")
            if not isinstance(cardtype, str) or not cardtype:
                raise CatalogError(f"cards[{key!r}].cardtype 必须是非空字符串")
            cards[key] = CardFacts(cardtype=cardtype)

        return cls(
            cards=cards,
            known_classes=_string_tuple(data, "known_classes"),
            known_cardtypes=_string_tuple(data, "known_cardtypes"),
            known_rarities=_string_tuple(data, "known_rarities"),
            known_spell_schools=_string_tuple(data, "known_spell_schools"),
            complete=complete,
        )

    def __repr__(self) -> str:  # pragma: no cover - 调试便利
        return f"JsonCatalog(cards={len(self._cards)}, complete={self.complete})"


class NullCatalogProvider:
    """dev 默认 provider：NullCatalog + 无 game。

    真实实现是 core 的 ``DbfCatalogProvider``（core 接入轮落地）；本类只
    让壳在无游戏数据时可跑（``spec`` 默认路径 / 测试注入）。``cache_root``
    / ``locale`` 是 CLI 级参数，不进 GameRequest；当前实现不使用它们。
    """

    def __init__(
        self, *, cache_root: Path | None = None, locale: str = "zhcn"
    ) -> None:
        self.cache_root = cache_root
        self.locale = locale

    def bind(self, request: GameRequest) -> CatalogBinding:
        return CatalogBinding(
            catalog=NullCatalog(),
            game=None,
            identity=CatalogIdentity(kind="null"),
        )


def bind_json_catalog(path: str | Path) -> CatalogBinding:
    """shell 直读 ``--catalog`` JSON（dev 路径），返回带文件身份的 binding。

    身份（kind=json、path、size、mtime_ns、complete）供 manifest 的
    ``environment.catalog`` 复现字段使用。
    """
    source = Path(path)
    try:
        stat = source.stat()
    except OSError as exc:
        raise CatalogError(f"无法读取 catalog {source}: {exc}") from exc
    catalog = JsonCatalog.from_path(source)
    identity = CatalogIdentity(
        kind="json",
        path=str(source),
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        complete=catalog.complete,
    )
    return CatalogBinding(catalog=catalog, game=None, identity=identity)
