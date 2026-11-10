"""recipes — 配方面（消费方唯一 import 面）。

阶段=supply 域项的**纯别名转发**（re-export）——域对象 is eidolon.core.supply
对应域对象本身（is 同一对象），memo 语义/__supply_token__ 天然透传；不新增 memo 层、
不重新 @item、不加任何包装。后续逐域还原（supply 域函数体搬进本包再装饰）后，
别名消失、本包成为配方实现住址。
域清单=配方调用点清册 24 域项签名表；textures 在 supply 包 __init__ 未导出
（消费方现用直模块 import），此处照实转发。

转发是 **PEP 562 惰性**的（域对象形状不变，首属性访问才装载）——本包 __init__
保持轻 import（与 supply 包同纪律，§13.1 默认 discover 轻面约束）。
"""
from importlib import import_module

__all__ = ["art", "color", "frames", "gems", "text", "textures", "watermarks"]

_DOMAINS = {
    "art": "eidolon.core.recipes.art",
    "color": "eidolon.core.recipes.color",
    "frames": "eidolon.core.recipes.frames",
    "gems": "eidolon.core.recipes.gems",
    "text": "eidolon.core.recipes.text",
    "textures": "eidolon.core.recipes.textures",
    "watermarks": "eidolon.core.recipes.watermarks",
}


def __getattr__(name: str):
    if name in _DOMAINS:
        mod = import_module(_DOMAINS[name])
        globals()[name] = mod          # 首访问后驻留（域对象 is 模块本身）
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
