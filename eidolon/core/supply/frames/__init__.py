"""frames — 帧域：五帧族+hero 双帧 kit（Batch A）+ ability 三件套（Batch B）
+ bacon/DK 符文/badges/supplements/ornaments/btf（Batch C 收官）。

域面：`kit(frame) -> Kit`（ally/weapon/heropower/location/hero_hand/hero_play/
trinket/anomaly）；`ability_kit() -> AbilityKit`；`bacon_kit() -> Kit`（五面+帧 rig
三件一体）；`dk.rune_atlas() -> Image`（走链符文图集）；`badges_kit() -> BadgesKit`；
`supplements.{ta_supplement,portrait_uv1,material_state}()`（kit 派生件三配方）；
`ornaments_kit() -> OrnamentsKit`；`btf_kit() -> BtfKit`。
排版：engine=共享走查引擎（Recon）｜specs=FRAME_SPECS｜kits=主流程+Kit｜
ability/bacon/dk/badges/supplements/ornaments/btf=各件对照表住模块 docstring。
mips 已收编 textures.mip_registry（游戏直提）。

包面是 **PEP 562 惰性**的（域对象 is 对应子模块的同一对象）：``eidolon/core/supply/frames`` 的 __init__ 保持轻 import
——``import eidolon.core.supply.frames.specs``（纯数据规格表）不得被 ability 等
UnityPy 消费件拖累（§13.1 默认 discover 轻面约束）。
"""
from importlib import import_module

__all__ = ["Kit", "kit", "AbilityKit", "ability_kit", "bacon_kit",
           "BadgesKit", "badges_kit", "OrnamentsKit", "ornaments_kit",
           "BtfKit", "btf_kit"]

_EXPORTS = {
    "AbilityKit": "eidolon.core.supply.frames.ability",
    "ability_kit": "eidolon.core.supply.frames.ability",
    "BadgesKit": "eidolon.core.supply.frames.badges",
    "badges_kit": "eidolon.core.supply.frames.badges",
    "bacon_kit": "eidolon.core.supply.frames.bacon",
    "BtfKit": "eidolon.core.supply.frames.btf",
    "btf_kit": "eidolon.core.supply.frames.btf",
    "Kit": "eidolon.core.supply.frames.kits",
    "kit": "eidolon.core.supply.frames.kits",
    "OrnamentsKit": "eidolon.core.supply.frames.ornaments",
    "ornaments_kit": "eidolon.core.supply.frames.ornaments",
}


def __getattr__(name: str):
    if name in _EXPORTS:
        mod = import_module(_EXPORTS[name])
        attr = getattr(mod, name)
        globals()[name] = attr         # 首访问后驻留
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
