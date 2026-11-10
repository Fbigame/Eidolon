"""provider — DbfCatalogProvider：dbf 装载 + GameContext 解析（spec 的 bind）。

分层：本模块是 ``core/infra`` 里唯一在 spec 路径触 UnityPy 的点（经 ``dbf``）；
**不** import ``card`` / ``game_tag`` / ``dll_reflect``——``spec`` 不加载 CLR，
``bind`` 只建 facts 索引、不构造 ``Card``。

``bind`` fail-fast 顺序（失败即 raise，不吞）：

1. ``resolve_context``（显式/探测两路；探测失败 → ``game_not_found``）；
   显式 game_dir 时验 ``ctx.game_exe`` → ``game_dir_incomplete``（ENV）；
2. ``ctx.dbf_path`` 不存在 → ``dbf_missing``；
3. ``DbfModule(dbf_path)`` 建 ``card`` / ``card_tag`` → 失败 ``dbf_unreadable``
   （cause 保留；含坏块 typed error 的 bundle/块上下文）；
4. 空表守卫：``card`` 或 ``card_tag`` 为空 → ``dbf_unreadable``
   （不得让 ``complete=True`` 把所有卡误判成 ``unknown_card``）；
5. 构建 ``DbfCatalog``（cardtype 经静态镜像投影；镜像缺值 = 版本未支持，
   响亮 ``constants_unavailable``）；
6. ``dbf.install_default(module)``（供后续 render 复用同一 dbf 会话；
   spec 进程内一次 CLI 可接受）；
7. 返回 ``CatalogBinding``（identity 含 dbf stat 账面；重复 card id 转
   ``duplicate_card_id`` warning）。
"""
from __future__ import annotations

from pathlib import Path

from eidolon.contracts import (
    CatalogBinding,
    CatalogIdentity,
    CardFacts,
    EnvironmentUnavailable,
    GameRequest,
    Problem,
    ProblemKind,
)
from eidolon.core.infra import dbf
from eidolon.core.infra.catalog import DbfCatalog
from eidolon.core.infra.dbf import DbfModule
from eidolon.core.infra.facts import CARD_TYPE_TAG_ID, CARDTYPE_NAMES
from eidolon.core.infra.game_install import resolve_context

__all__ = ["DbfCatalogProvider"]


class DbfCatalogProvider:
    """真实 catalog provider：本机游戏安装（显式 game_dir 或 product.db 探测）。

    ``cache_root`` / ``locale`` 由组合层（entry factory）传入；locale 存原始值，
    归一化交给 ``resolve_context``。
    """

    def __init__(self, *, cache_root: Path, locale: str) -> None:
        self.cache_root = Path(cache_root)
        self.locale = locale

    def bind(self, request: GameRequest) -> CatalogBinding:
        ctx = resolve_context(
            request, cache_root=self.cache_root, locale=self.locale)
        provenance = f"root={ctx.root}（{ctx.root_source or '来路未记'}）"
        if request.game_dir is not None and not ctx.game_exe.is_file():
            raise EnvironmentUnavailable(Problem(
                ProblemKind.ENVIRONMENT,
                "game_dir_incomplete",
                str(ctx.root),
                f"game_dir_incomplete: 显式游戏根缺 Hearthstone.exe（{provenance}）",
            ))

        dbf_path = ctx.dbf_path
        if not dbf_path.is_file():
            raise EnvironmentUnavailable(Problem(
                ProblemKind.ENVIRONMENT,
                "dbf_missing",
                str(dbf_path),
                f"dbf_missing: 游戏安装缺 Data/Win/dbf.unity3d（{provenance}）",
            ))

        module = DbfModule(dbf_path)
        try:
            card_rows = module.card
            card_tag_rows = module.card_tag
        except Exception as exc:                        # noqa: BLE001 —— dbf_unreadable 收口
            if isinstance(exc, EnvironmentUnavailable):
                raise
            cause = f"{type(exc).__name__}: {exc}"
            raise EnvironmentUnavailable(Problem(
                ProblemKind.ENVIRONMENT,
                "dbf_unreadable",
                str(dbf_path),
                f"dbf_unreadable: dbf 装载/解析失败（{cause}）",
                cause=cause,
            )) from exc
        if not card_rows or not card_tag_rows:
            raise EnvironmentUnavailable(Problem(
                ProblemKind.ENVIRONMENT,
                "dbf_unreadable",
                str(dbf_path),
                "dbf_unreadable: dbf 空表（CARD 或 CARD_TAG 为空）——疑似坏包/版本异常",
            ))

        by_dbf_id: dict[int, CardFacts] = {}
        by_card_id: dict[str, CardFacts] = {}
        duplicates: list[str] = []
        seen_dup: set[str] = set()
        for card_id, row in card_rows.items():
            tags = card_tag_rows.get(str(card_id), {})
            raw = tags.get(CARD_TYPE_TAG_ID)
            if raw is None:
                # 卡存在但事实不全：compile_spec 会 defer style 检查，不误报 unknown_card。
                facts = CardFacts(cardtype="")
            else:
                try:
                    cardtype = CARDTYPE_NAMES.get(int(raw))
                except (TypeError, ValueError):
                    cardtype = None
                if cardtype is None:
                    raise EnvironmentUnavailable(Problem(
                        ProblemKind.ENVIRONMENT,
                        "constants_unavailable",
                        str(dbf_path),
                        f"constants_unavailable: CARDTYPE 值 {raw!r} 不在静态镜像中"
                        "（客户端版本超出已支持集合；升级 facts 镜像）",
                    ))
                facts = CardFacts(cardtype=cardtype)
            by_dbf_id[int(card_id)] = facts
            guid = row.get("m_noteMiniGuid")
            if guid:
                key = str(guid).casefold()
                if key in by_card_id:
                    if key not in seen_dup:
                        duplicates.append(str(guid))
                        seen_dup.add(key)
                else:
                    by_card_id[key] = facts

        dbf.install_default(module)
        stat = dbf_path.stat()
        return CatalogBinding(
            catalog=DbfCatalog(
                by_dbf_id=by_dbf_id,
                by_card_id=by_card_id,
                duplicates=tuple(duplicates),
            ),
            game=ctx,
            identity=CatalogIdentity(
                kind="dbf",
                path=str(dbf_path),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                complete=True,
            ),
            warnings=("duplicate_card_id",) if duplicates else (),
        )
