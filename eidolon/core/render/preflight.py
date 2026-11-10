"""渲染前覆盖语义轻校验（设计 §7.7 第 9 步的 core 侧）。

``validate_overrides(cards)`` 对覆盖项做**不渲染**的语义试算：
``card_overrides.apply`` 逐卡打在真实 ``Card.from_dbf`` 上（HERO×bg、
``classes`` INVALID、``runes`` 键、banner 值、镜像缺口都在这里响亮），
返回 ``tuple[Problem, ...]``（空=通过）。adapter 按 kind 分流：
INPUT → 输入错误（2）；ENVIRONMENT（``constants_unavailable`` 等）→
EnvironmentUnavailable（3）。

前置：``context.install`` 已完成（§7.7 序）。**前置不满足时跳过**：
``core.infra.dbf.installed_default()`` 为空（fake provider / 测试注入）→
返回空——不把「没有 dbf 会话」误报成输入错误。

本模块顶层只 import 标准库 + contracts；``Card`` / ``card_overrides`` /
``constants`` 等 CLR 链只进函数体（§6.5 规则，守卫钉住）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from eidolon.contracts import (
    EnvironmentUnavailable,
    InputRejected,
    Problem,
    ProblemKind,
    RenderCard,
)

if TYPE_CHECKING:
    from eidolon.core.render.constants import CardConstants

__all__ = ["validate_overrides", "problem_of"]


def problem_of(exc: BaseException) -> Problem | None:
    """纯抽取面：``InputRejected`` / ``EnvironmentUnavailable`` → 其
    ``Problem``；其余异常 → ``None``（不依赖 dbf/CLR，可直接单测）。"""
    if isinstance(exc, (InputRejected, EnvironmentUnavailable)):
        return exc.problem
    return None


def _form_of(render_card: RenderCard) -> str:
    return ("hero" if render_card.hero_style
            else "bg" if render_card.bg_style else "plain")


def _dbf_id_of(render_card: RenderCard) -> int | None:
    """``RenderCard.ref`` → dbf id（只查 dbf 会话索引，无 CLR/Card 构造）。

    查无 → ``None``：unknown_card 已在 compile_spec 拦；Card 级校验无对象，
    跳过（不误报）。
    """
    ref = render_card.ref
    if ref.kind == "dbf":
        return int(ref.value)
    from eidolon.core.infra.dbf import default_dbf

    return default_dbf().card_id_to_dbf.get(str(ref.value).casefold())


def _validate_one(
    render_card: RenderCard, index: int, dbf_id: int, constants: CardConstants
) -> Problem | None:
    """单卡试算（``card_overrides.apply`` + form 守卫）；返回 Problem 或 None。

    ``constants`` 由调用方批级构造一次传入（P1-12）；dbf id 已由调用方解析
    （unknown ref 不进本函数）。``InputRejected`` / ``EnvironmentUnavailable``
    由调用方统一抽取；这里只返回「不抛异常路径」上的 form 类 INPUT Problem。
    """
    from eidolon.core.infra.card import Card
    from eidolon.core.render import card_overrides

    card = Card.from_dbf(dbf_id)
    card_overrides.apply(card, render_card, constants)
    if render_card.hero_style and render_card.bg_style:
        return Problem(
            ProblemKind.INPUT,
            "style",
            f"cards[{index}]",
            "style: hero_style 与 bg_style 同时为真——二者互斥",
        )
    from eidolon.core.render.game.actor.components import resolve_form

    try:
        resolve_form(card, _form_of(render_card))
    except ValueError as exc:
        return Problem(
            ProblemKind.INPUT,
            "style",
            f"cards[{index}]",
            f"style: form 组合非法（{exc}）",
        )
    return None


def validate_overrides(cards: Sequence[RenderCard]) -> tuple[Problem, ...]:
    """覆盖语义轻校验（不渲染）→ Problem 元组（空=通过）。

    - 无 dbf 会话（fake provider / 测试注入）→ 空元组，跳过 Card 级校验；
    - 有会话：只对「有 overrides 或有 style 请求」的卡做 Card 级校验
      （P1-12：无覆盖无 style 的 plain 卡零 ``Card`` / ``constants`` 构造；
      dbf id 查无的卡同样跳过，不误报）；``live_card_constants()`` 批级
      构造一次传给逐卡循环；``InputRejected`` → 其 problem（INPUT）、
      ``EnvironmentUnavailable`` → 其 problem（ENV，如
      ``constants_unavailable``）；逐卡继续，不 fail-fast（轻校验收集面）。
    """
    from eidolon.core.infra import dbf

    if dbf.installed_default() is None:
        return ()
    pending: list[tuple[int, RenderCard, int]] = []
    for index, render_card in enumerate(cards):
        if not (render_card.overrides
                or render_card.hero_style or render_card.bg_style):
            continue  # plain 卡（无覆盖无 style）：无语义可验，快速跳过
        dbf_id = _dbf_id_of(render_card)
        if dbf_id is None:
            continue  # 未知 dbf id：Card 级校验无对象，跳过
        pending.append((index, render_card, dbf_id))
    if not pending:
        return ()
    from eidolon.core.render.constants import live_card_constants

    try:
        constants = live_card_constants()   # 批级一次（原为逐卡构造）
    except Exception as exc:  # noqa: BLE001 —— constants 失败按既有抽取面回 ENV problem
        problem = problem_of(exc)
        if problem is None:
            raise
        return (problem,)
    problems: list[Problem] = []
    for index, render_card, dbf_id in pending:
        try:
            problem = _validate_one(render_card, index, dbf_id, constants)
        except Exception as exc:  # noqa: BLE001 —— InputRejected/ENV 之外的异常不吞
            problem = problem_of(exc)
            if problem is None:
                raise
        if problem is not None:
            problems.append(problem)
    return tuple(problems)
