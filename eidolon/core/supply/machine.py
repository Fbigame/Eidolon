"""machine — 会话域 memo + 正式单例（机制；契约见包 docstring）。

重资源留位：UnityPy env 句柄的进程级缓存与驱逐（mip 链=首个占据者），并发下升级为
并发安全缓存——开写时决议。进程级表数据不走此间（game_dll cached_property 自带进程 memo）。
三态缓存已随 materialize 退役（消费归零实证见上游 supply-v3 记账）；上游的项遥测轴
（env 开关包装 + atexit 落盘）与 REPO 容器依赖随 Phase 2b 蒸馏删除——``served`` 的
memo 语义逐字未动。
"""
from __future__ import annotations

import functools
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable

from eidolon.core.infra.context import current   # 契约 D：Data/Win=ctx 流入（入口显式 install）
from eidolon.core.infra.resolve_asset_ref import Resolver
from eidolon.core.supply._projection import item_scope


@dataclass
class Session:
    memo: dict = field(default_factory=dict)   # (域, 项, 参数) → 解码物


_s_current: ContextVar[Session | None] = ContextVar("supply_v3_session", default=None)

_pending_seed: ContextVar[dict | None] = ContextVar("supply_v3_pending_seed", default=None)
"""pending 种子（A2 S1 seam，supply-source.md §2/§3.7）：``seed_session`` 预置、
``session()`` 进入时一次性消费为初始 memo。预填既有 memo 缓存=不引入新协议；
命中 token 不执行域函数、未命中 token 照旧 live（fallback 天然，性能语义）。"""


@contextmanager
def session():
    """会话=一次渲染的 memo 作用域，入口层（gate 驱动循环）独占开。

    契约：消费方永不开 session、不见 mode、不见 Path（Path 返回方法除外）；
    解码物不跨卡。并发化=session 挪进 worker（contextvar 为并发而生）。
    替身账：接替旧 _mip_state.reset_memo() 手工纪律与 AssetResolver._memo
    （后者进程级驻留 Path 可堪，解码物不可堪）。

    A2 pending seed：进入时一次性消费 ``seed_session`` 预置的 pending——有
    种子则以 ``Session(memo=dict(seeds))`` 开会话（浅拷贝，种子 dict 不被会话
    写面触碰）；消费即 ``set(None)``，同一 pending 只种首个会话（重复 session()
    不重种）；无 pending 时逐位不变（``in_session`` 语义不变）。"""
    seeds = _pending_seed.get()
    _pending_seed.set(None)                     # 一次性消费：不留残种
    tok = _s_current.set(Session(memo=dict(seeds)) if seeds else Session())
    try:
        yield
    finally:
        _s_current.reset(tok)


@contextmanager
def seed_session(seeds: dict):
    """pending 种子作用域（S1 seam 的装配端；与 ``session()`` 配对）。

    进入把 ``seeds`` 预置为 pending，其内**首个** ``session()`` 进入时一次性
    消费为初始 memo（会话预填）；出口 token reset 复位进入前值（栈式遮蔽：
    嵌套时内层遮蔽外层、内层出口后外层恢复可见）。未消费/异常路径同样经
    finally 复位——pending 不跨作用域泄漏。

    装配位=``api._render_one`` 的 render_fn 包装层（组合层/测试注入；产品
    0.1.0 不启用，消费方零感知）::

        with seed_session(seeds):
            render_with(...)     # _in_session 内的首个 session() 消费 seeds
    """
    tok = _pending_seed.set(seeds)
    try:
        yield
    finally:
        _pending_seed.reset(tok)


class _Core:
    """进程唯一（config/状态权威）。解码物不进单例（随会话生死）。"""

    def __init__(self) -> None:
        self._res: Resolver | None = None

    @property
    def res(self) -> Resolver:
        if self._res is None:
            # 契约 D（2026-11-06）：DATA_WIN 模块常量硬编码解除——Data/Win 从已安装的
            # GameContext 流入（入口显式 install；未安装=current() raise）。
            self._res = Resolver(current().data_win)
        return self._res


_core: _Core | None = None


def core() -> _Core:
    global _core
    if _core is None:
        _core = _Core()
    return _core


def in_session() -> bool:
    """会话活性探针（②壳保底用：模块级供给调用发生在 import 期，会话之外）。"""
    return _s_current.get() is not None


def item(domain: str, name: str) -> Callable:
    """域项装饰器：面函数包会话 memo（token=(域, 项, 参数)，decode-once 单实例）。

    被装饰函数保持纯函数纪律：只读 core().res 与参数，不摸单例可变态。
    __supply_token__=域内寻址标签（盘点表/审计对账用）。

    解码期间把「当前域项」压进 `item_scope`（ContextVar）——投影层报错因此
    能带项名（`frames.badges_kit m_Colors[3] …`）；token 形式 try/finally 复位，开销=
    每次冷产出一次 set/reset（memo 命中不压栈）。"""
    def wrap(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def served(*args: Any):
            s = _s_current.get()
            assert s is not None, "供给访问必须在 session() 内（错在消费方越层）"
            token = (domain, name, args)
            if token not in s.memo:
                with item_scope(f"{domain}.{name}"):
                    s.memo[token] = fn(*args)
            return s.memo[token]

        served.__supply_token__ = (domain, name)
        return served

    return wrap
