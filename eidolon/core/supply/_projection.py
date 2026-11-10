"""_projection — 资产投影单一出口（形状归一 + 基数守恒 + 域项上下文）。纯 stdlib。

来路（2026-10-31 badge-vcolor 事故）：Material `m_SavedProperties.m_Colors/m_Floats` 的
UnityPy typetree 形态是**两元素数组对** `[["_Color", {…}], …]`，旧实现按
`{"first","second"}` 字典过滤 ⇒ 两张表恒空、**不报错** → 渲染侧 `vColor` 取默认 0，
127155 条带只暗 7 灰阶（62.97 vs 70.05）。根因是三者叠加：**形状假设 + 过滤式丢弃 +
消费者中性默认**。本模块把「形状假设」收敛成唯一出口：

  - 只承认两种**已知**形态：`{"first","second"}` 字典 / 两元素 `list|tuple`；
  - 未知形态 `ProjectionError`（消息带索引与 repr 片段），**绝不 continue 跳过**——
    静默空集比崩溃危险（铁律：探针产出静默空集先疑 schema 假设）；
  - `projection(pairs=True)` 守**源-目标基数守恒**：源 n 条必须解出 n 条，少一条即 raise。
    即使转换器哪天退回过滤式写法，这条不变量也会在门里响亮；
  - `projection(require=…)` 只用于**显式已知项**的非空契约（不是通用默认）；
  - 错误消息带 `current_item()`——`machine.item` 会话包装写入的「域项」名
    （如 `frames.badges_kit`），报错直接定位到供给面项；
  - 颜色走 `as_rgba`：`{r,g,b,a}` / 四元序列 → `[r,g,b,a]`（**不取整**，要与引擎抓帧
    常量缓冲逐值对得上；`btf` 侧 `round(…,5)` 是另一条账的形态，不在本模块）。

"""
from __future__ import annotations

import functools
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterable

__all__ = [
    "ProjectionError", "as_pairs", "as_rgba", "projection",
    "current_item", "item_scope",
]


class ProjectionError(RuntimeError):
    """资产投影失败：形态不认识 / 基数不守恒 / 显式已知项缺失（一律响亮）。"""


# ---------------------------------------------------------------------------
# 域项上下文（machine.item 写入；报错消息的定位轴）
# ---------------------------------------------------------------------------

_CURRENT_ITEM: ContextVar[str | None] = ContextVar("supply_projection_item", default=None)


def current_item() -> str | None:
    """当前供给域项名（`machine.item` 解码期间有效；会话外为 None）。"""
    return _CURRENT_ITEM.get()


@contextmanager
def item_scope(name: str):
    """把「当前域项」压入 ContextVar（token 形式，try/finally 复位；开销=一次 set/reset）。"""
    tok = _CURRENT_ITEM.set(name)
    try:
        yield
    finally:
        _CURRENT_ITEM.reset(tok)


def _where(what: str, index: int | None = None) -> str:
    loc = f"{what}[{index}]" if index is not None else what
    it = _CURRENT_ITEM.get()
    return f"{it} {loc}" if it else loc


# ---------------------------------------------------------------------------
# 形状归一
# ---------------------------------------------------------------------------

def as_pairs(seq: Any, *, what: str = "pairs") -> dict:
    """`m_Colors`/`m_Floats`/`m_TexEnvs` 之类「键-值对序列」→ {名: 值}。

    两种已知形态（UnityPy typetree 实测：列表对是现役形态，字典形态是旧 typetree/手写
    口径的兜底）：`[["_Color", {…}], …]` 或 `[{"first": "_Color", "second": {…}}, …]`。
    未知形态 raise（带索引与 repr 片段）——**不做过滤式跳过**：形状不认识就说明假设错了，
    静默丢一条 = 下游拿到空表且不报错（badge-vcolor 原形）。
    """
    out: dict = {}
    if seq is None:
        return out
    if not isinstance(seq, (list, tuple)):
        raise ProjectionError(
            f"{_where(what)}：源形态不是序列"
            f"（{type(seq).__name__}，{repr(seq)[:120]}）——m_* 属性应为对序列")
    for i, item in enumerate(seq):
        if isinstance(item, dict):
            if "first" not in item or "second" not in item:
                raise ProjectionError(
                    f"{_where(what, i)}：dict 形态缺 first/second 键"
                    f"（键={sorted(item)}，{repr(item)[:120]}）")
            name, val = item["first"], item["second"]
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            name, val = item[0], item[1]
        else:
            raise ProjectionError(
                f"{_where(what, i)}：对形态未知"
                f"（{type(item).__name__}，{repr(item)[:120]}）——只认两元素 list|tuple 或"
                " {'first','second'} 字典")
        if not isinstance(name, str) or not name:
            raise ProjectionError(
                f"{_where(what, i)}：属性名非字符串/为空（{type(name).__name__}，"
                f"{repr(name)[:80]}）")
        out[name] = val
    return out


def as_rgba(v: Any) -> list | None:
    """颜色值 → `[r,g,b,a]`（不取整；`None` 原样传回=该属性缺值，其余未知形态 raise）。"""
    if v is None:
        return None
    if isinstance(v, dict):
        missing = [k for k in ("r", "g", "b", "a") if k not in v]
        if missing:
            raise ProjectionError(
                f"{_where('color')}：四元 dict 缺键 {missing}"
                f"（键={sorted(v)}，{repr(v)[:120]}）")
        vals = [v["r"], v["g"], v["b"], v["a"]]
    elif isinstance(v, (list, tuple)) and len(v) == 4:
        vals = list(v)
    else:
        raise ProjectionError(
            f"{_where('color')}：形态未知（{type(v).__name__}，{repr(v)[:120]}）——"
            "只认 {r,g,b,a} 或四元序列")
    try:
        return [float(x) for x in vals]
    except (TypeError, ValueError) as exc:
        raise ProjectionError(
            f"{_where('color')}：分量非数值（{repr(vals)[:120]}）") from exc


# ---------------------------------------------------------------------------
# 契约装饰器
# ---------------------------------------------------------------------------

def projection(*, name: str, pairs: bool = False, require: Iterable[str] | None = None
               ) -> Callable:
    """投影契约装饰器（被装饰函数首参=对序列源，返回 dict）。

    - `pairs=True`：**源-目标基数守恒**（`len(源) == len(解出)`）。这是「覆盖率不变量」：
      只允许转换器产出与源同基数的字典，任何丢弃（过滤/跳过/键折叠）都 raise。
    - `require=("_Color", …)`：显式已知项的非空契约（仅当调用方确知该属性必须在场时用；
      资产面可缺省的属性禁拿它当「通用默认」）。
    """
    required = tuple(require or ())

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> dict:
            out = fn(*args, **kwargs)
            ctx = f"{name}"
            it = _CURRENT_ITEM.get()
            if it:
                ctx = f"{it} {name}"
            if pairs:
                src = args[0] if args else kwargs.get("seq")
                n_src = len(src) if src is not None else 0
                if not isinstance(out, dict):
                    raise ProjectionError(
                        f"{ctx}：pairs 契约要求 dict 返回值，实得 {type(out).__name__}")
                if len(out) != n_src:
                    raise ProjectionError(
                        f"{ctx}：源-目标基数不守恒（源 {n_src} 条 → 解出 {len(out)} 条）——"
                        "转换器丢弃了形状不认识的条目；禁过滤式跳过")
            for key in required:
                if out.get(key) in (None, "", [], {}, ()):
                    raise ProjectionError(
                        f"{ctx}：显式已知项 {key!r} 缺失/为空（实得 {out.get(key)!r}）")
            return out

        return wrapped

    return deco
