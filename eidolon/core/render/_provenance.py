"""_provenance — 认识论挂牌机制（consumer-v2 段0 定案，2026-10-29）。

四类顶层（消费面分类学，用户裁定）：平行/直调/拟合/发明；拟合内部 kind 区分
证据形态——artifact（权威工件直译：DXBC/序列化）| calibration（实测标定闭环）。

机制：no-op 装饰器，仅设 ``fn.__epistemic__ = (类, 参数 dict)``，零行为影响。
锚账住 docstring（既有 file:Class.Method 约定+审计探针沿用），装饰器只装机器
可读最小集——防双写漂移；探针交叉校验（@parallel/@hosted 无 decomp 锚=fail）。

发明牌只装现在时（无时态定律同款）：reason=**可证伪陈述**（"现在为什么必须
发明"；答案变否=该件应死，退役检测=reason 失真，ledger 复盘触发）；counterpart=
它替代/对位的游戏行为锚。方向账住正典文不入码面——无 kill 预测字段。

牌面范围=eidolon/core/render/ 包内公开行为符号（非 _ 前缀 callables：函数/类/表
访问器）；私有 helper 免挂（探针计数不门禁）。**两规约分治**：本牌面管行为面
（四类来路），supply/recipes/infra=数据通道面（@item+双射闸+哈希绑定规约）——
render_cards 闭包穿透两层，各按其规约验收。边界件出域：batch（穿透入口门面）/
params（政策常量）/shaders·textmesh（dormant 宿位）；_duipai 已移实验档归档
（2026-10-29，随旧链退役）。
粒度=方法族/访问器（与锚账同粒度），行级来路留表行注。
"""
from __future__ import annotations
from typing import Any, Callable

__all__ = ["parallel", "hosted", "fitted", "invented"]


def _tag(fn: Any, kind: str, params: dict) -> Any:
    setattr(fn, "__epistemic__", (kind, params))
    return fn


def parallel(fn: Callable) -> Callable:
    """平行转写件：游戏 DLL 类方法的逐字转写。docstring 必含 decomp 锚
    （file:Class.Method；探针核验存在性）。"""
    return _tag(fn, "parallel", {})


def hosted(fn: Callable) -> Callable:
    """宿主直调件：pythonnet 直跑游戏本体（零平行代码，构造上无平行漂移）。
    docstring 必含宿主类锚。"""
    return _tag(fn, "hosted", {})


def fitted(kind: str, *, closed: bool | None = None) -> Callable:
    """拟合件：对原生层（引擎/字体/GPU）的行为拟合。

    kind="artifact"：权威工件直译（DXBC 指令/序列化真值——换版重反汇编可再推导）；
    kind="calibration"：实测标定（oracle 闭环/扫描定值——引擎或字体一动即静默
    失效）。closed=引擎闭算与否（None=不适用；False=明标未闭，是削减队列对象）。
    """
    assert kind in ("artifact", "calibration"), f"fitted.kind 非法：{kind!r}"
    def deco(fn: Callable) -> Callable:
        return _tag(fn, "fitted", {"kind": kind, "closed": closed})
    return deco


def invented(reason: str, counterpart: str | None = None) -> Callable:
    """发明件：行为对位、机制自造（有行为对应物，无机制对应物——离线前提下的
    替换件：编排/差分/tripwire 换座；纯我方调度配置亦入此类，reason 注记）。

    reason 必填——可证伪的现在时陈述（现在为什么必须发明）；counterpart 可选
    ——它替代/对位的游戏行为锚。退役=reason 失真时刻（ledger 复盘触发），
    不在本牌预测。
    """
    assert reason and reason.strip(), "发明牌 reason 必填（可证伪现在时陈述）"
    def deco(fn: Callable) -> Callable:
        return _tag(fn, "invented", {"reason": reason, "counterpart": counterpart})
    return deco
