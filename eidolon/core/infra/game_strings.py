"""game_strings — GameStrings 常量表数据面（活程序集直取，零 decomp 依赖）。

race 腿走**活程序集反射**（`dll_reflect.static_dict` + `enum_table`）——
`GameStrings.s_raceNames` 与 `TAG_RACE` 枚举直接取自 Assembly-CSharp.dll，
不依赖反编译快照的版本与 ilspy 输出形制（旧正则假设初始化器/枚举行形态，
ilspy 升级即碎）。

取舍（上游裁决）：
  * 活二进制=权威源：常量表随客户端走，省掉「先反编译、再解析」两步维护；
  * 代价：首次读取装载 coreclr——渲染链本来就用 `dll_reflect.tables`，
    不新增依赖类别；
  * 语义输入=Assembly-CSharp.dll 字节（版本漂移由渲染链的 ctx 版本记录面承载）。

对账：切换前 decomp 43 键 vs 活表 43 键逐键相等（上游实验账）。

消费面：core/render 的 race 名段（compiler 族）。
"""
from __future__ import annotations

from eidolon.core.infra.dll_reflect import enum_table, static_dict

__all__ = ["race_names"]


def _load_race_names() -> dict[int, str]:
    """活表 → {TAG_RACE int: GLOBAL_RACE_* 键}。

    表引用枚举外成员、同 id 异键、空表=解析漂移，一律响亮失败（不猜、不降级）。
    """
    enum = enum_table("TAG_RACE")
    raw = static_dict("GameStrings", "s_raceNames")
    assert raw, "活表 GameStrings.s_raceNames 为空"
    out: dict[int, str] = {}
    for name, key in raw.items():
        assert name in enum, f"s_raceNames 引用枚举外成员：TAG_RACE.{name}"
        rid = enum[name]
        assert out.get(rid, key) == key, f"s_raceNames 同 id 异键：TAG_RACE.{name}({rid})"
        out[rid] = key
    return out


race_names: dict[int, str] = _load_race_names()
