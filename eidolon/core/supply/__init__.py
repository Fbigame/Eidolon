"""supply — L1 供给层：语义域命名空间（单例流式核心，游戏直提）。

外壳契约（2026-10-10 讨论轮定案）：
  - 面=语义域命名空间（color/art/text/gems…域清单由盘点表正式化）；供给键退居内部寻址；
  - 会话=入口层（驱动循环）独占开，解码物不跨卡；消费方对生命周期零意识；
  - 形态语言=生命周期档位信号：属性读=进程级数据（infra 活表：dll_reflect.tables/
    dbf，Card 门面先例——游戏数据归 infra），调用=会话资源（解码物）；
  - 配方纯函数纪律：配方只读 core().res 与参数（UnityPy 不可并发=已裁决；
    未来并发=多进程扇出+句柄层单点收口）；
  - 中间产物盘位三类合法：最终产物/观察证据（opt-in）/supply 私有事务。

层纪律：不 import 渲染层（supply 禁 paint，§4.2 AST 守卫在案）；
Path 返回方法（materialize 逃生口）已随三态缓存退役。

域转发是 **PEP 562 惰性**的：域对象 is 对应域模块本身（memo 语义/__supply_token__
透传不变），只是首属性访问才装载——``eidolon/core/supply`` 包 __init__ 保持轻
import（默认 discover 的 supply 纯函数测试经 ``import eidolon.core.supply._projection``
先执行本 __init__，不得被 frames 的 UnityPy/CLR 链拖累；§13.1 轻面约束）。
"""
from importlib import import_module

__all__ = ["art", "color", "frames", "gems", "overrides", "text", "watermarks",
           "core", "session"]

_DOMAINS = {
    "art": "eidolon.core.supply.art",
    "color": "eidolon.core.supply.color",
    "frames": "eidolon.core.supply.frames",
    "gems": "eidolon.core.supply.gems",
    "overrides": "eidolon.core.supply.overrides",
    "text": "eidolon.core.supply.text",
    "watermarks": "eidolon.core.supply.watermarks",
}


def __getattr__(name: str):
    if name in _DOMAINS:
        mod = import_module(_DOMAINS[name])
        globals()[name] = mod          # 首访问后驻留（域对象 is 模块本身）
        return mod
    if name in ("core", "session"):    # machine 会话机制面（按需装载）
        from eidolon.core.supply import machine
        globals()["machine"] = machine
        return getattr(machine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
