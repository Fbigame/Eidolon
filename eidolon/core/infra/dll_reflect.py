"""dll_reflect — 活程序集反射（pythonnet coreclr）：游戏常量表直取，零 decomp 依赖。

机制（上游 boot 习语逐字承接）：coreclr 装载 + Managed 解析器 +
Assembly-CSharp.LoadFrom。静态字段读触发纯字典填充型静态构造，无引擎副作用。
宿主进程内懒建复用。

本模块是渲染链常量表的**唯一来源**——``game_tag``（GAME_TAG 名册）、
``game_strings``（s_raceNames × TAG_RACE）、``card``（五枚举值域镜像）均吃
这里的 ``enum_table``/``static_dict``。语义输入 = Assembly-CSharp.dll 字节；
路径单源 = GameContext（``ctx.assembly_csharp`` / ``ctx.managed``，render
路径 ``context.install`` 后经 ``current()`` 流入）。

守则（上游实证）：pythonnet 宿主损坏为瞬态环境问题（重启机器恢复）。

本模块零供给语义：不知道 ActorNames/GameStrings 是什么，只提供「类型名+字段名 →
python 字典」的机械面；表语义与缓存生命周期住同层活表模块。
"""
from __future__ import annotations

import logging
from functools import cached_property
from typing import Any

from eidolon.core.infra import context   # 契约 D：Managed/Assembly 路径=ctx 流入

logger = logging.getLogger(__name__)

_asm: Any = None


def assembly():
    """Assembly-CSharp 懒装载（进程一次；解析器兜住 Managed 同级依赖）。

    进程级 `_asm` 以「ctx 不变」为前提（context.install 重装异值即 raise）。
    import 期不装载 CLR——首次 ``assembly()`` 才 load（game_tag / card 的
    模块级枚举镜像调用点即首触点，见设计 §6.5 CLR-at-import 清单）。"""
    global _asm
    if _asm is None:
        ctx = context.current()
        from pythonnet import load

        load("coreclr")
        from System import AppDomain, ResolveEventHandler
        from System.Reflection import Assembly

        def _resolve(sender, args):
            cand = ctx.managed / f"{args.Name.split(',')[0]}.dll"
            if cand.exists():
                try:
                    return Assembly.LoadFrom(str(cand))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[dll_reflect] resolve-fail %s: %s", args.Name, exc)
            return None

        AppDomain.CurrentDomain.add_AssemblyResolve(ResolveEventHandler(_resolve))
        _asm = Assembly.LoadFrom(str(ctx.assembly_csharp))
    return _asm


def type_(name: str):
    t = assembly().GetType(name)
    assert t is not None, f"活程序集无类型 {name}"
    return t


def static_dict(type_name: str, field_name: str) -> dict[str, str]:
    """静态字典型字段 → {str: str}（键值 str 化，与上游探针同口径）。"""
    t = type_(type_name)   # 先确保 coreclr 已装载（System 导入必须后于 load）
    from System.Reflection import BindingFlags

    field = t.GetField(field_name, BindingFlags.Public | BindingFlags.Static)
    assert field is not None, f"{type_name}.{field_name} 字段未命中"
    return _py_dict(field.GetValue(None))   # 触发静态构造（纯字典填充）


def static_value(type_name: str, field_name: str) -> Any:
    """静态标量字段（含 const——C# const=IL literal 静态字段，反射可读）→ 标量。"""
    t = type_(type_name)
    from System.Reflection import BindingFlags

    field = t.GetField(field_name, BindingFlags.Public | BindingFlags.Static)
    assert field is not None, f"{type_name}.{field_name} 字段未命中"
    return field.GetValue(None)


def static_enum_dict(type_name: str, field_name: str) -> dict[int, int]:
    """静态只读字典字段（枚举键值）→ {键 int: 值 int}。

    键值枚举（GAME_TAG→TAG_RACE 族，上游实证=EntityBase.s_raceSubsetToRaceTable）。
    读触发静态构造（该类型唯一静态成员=本字典时=纯字典填充，GameStrings 先例同判）；
    私有字段 NonPublic 档。迭代序=.NET Dictionary 插入序（add-only 字典实现细节，
    稳定；语义消费方按键值映射用，序敏感面另做序断言）。"""
    t = type_(type_name)
    from System.Reflection import BindingFlags

    field = t.GetField(field_name, BindingFlags.Public | BindingFlags.NonPublic
                       | BindingFlags.Static)
    assert field is not None, f"{type_name}.{field_name} 字段未命中"
    raw = field.GetValue(None)   # 触发静态构造
    assert raw is not None, f"{type_name}.{field_name} 字段值为 null"
    out: dict[int, int] = {}
    for e in raw:
        out[int(e.Key)] = int(e.Value)
    assert out, f"{type_name}.{field_name} 字典零条目"
    return out


def enum_table(type_name: str) -> dict[str, int]:
    """枚举 → {名: 值}。"""
    t = type_(type_name)   # 先确保 coreclr 已装载（System 导入必须后于 load——static_dict 同款）
    from System import Enum

    return {str(n): int(v) for n, v in zip(Enum.GetNames(t), Enum.GetValues(t))}


def _py_dict(raw) -> dict:
    """.NET 字典/自定义 Map → python dict（迭代面多态尝试：items/Keys/枚举）。"""
    try:
        return {str(k): str(v) for k, v in raw.items()}
    except (AttributeError, TypeError):
        pass
    try:
        return {str(k): str(raw[k]) for k in raw.Keys}
    except (AttributeError, TypeError, KeyError):
        pass
    return {str(e.Key): str(e.Value) for e in raw}   # IEnumerable<KeyValuePair<..>>


# ============================================================================
# 语义面：活表命名空间（进程生存期 cached_property；形态语言=属性读=进程数据）
# ============================================================================


class Tables:
    """活程序集常量表命名空间（模块单例 `tables`）。

    层界定案（上游 Card 门面先例）：游戏数据归 infra——DLL 活表住本文件
    （机制+语义同址），DBF 活表住 dbf；供给面收束为纯资产。
    """

    @cached_property
    def actor_slots(self) -> dict[str, str]:
        """ACTOR_ASSET 槽位 → actor prefab "名.ext:GUID"（ActorNames.s_actorAssets）。"""
        return static_dict("ActorNames", "s_actorAssets")

    @cached_property
    def premium_actors(self) -> dict[str, str]:
        """品质变体（金卡族）槽位表（ActorNames.s_premiumActorAssets）。"""
        return static_dict("ActorNames", "s_premiumActorAssets")

    @cached_property
    def diamond_actors(self) -> dict[str, str]:
        """钻石品质变体槽位表（ActorNames.s_diamondActorAssets）。"""
        return static_dict("ActorNames", "s_diamondActorAssets")

    @cached_property
    def spell_school_names(self) -> dict[int, str]:
        """TAG_SPELL_SCHOOL 枚举值 → GLOBAL_SPELL_SCHOOL_* 本地化键
        （GameStrings.s_spellSchoolNames；race_names 同族）。键的 locale 解析归
        supply（GLOBAL_STRINGS）。"""
        enum = enum_table("TAG_SPELL_SCHOOL")
        raw = static_dict("GameStrings", "s_spellSchoolNames")
        return {enum[k]: v for k, v in raw.items()}

    @cached_property
    def year_icon_even(self) -> str:
        """Core 轮换年标（偶数轮）水印 ref（SetRotationIcon.CORE_SET_WATERMARK_EVEN，
        公开 const 反射直取——资产身份 ref 由游戏自己的常量供货）。

        偶数轮=冻结参照裁决（GetActiveSetRotationYear()%2 运行时态不取）。奇数轮
        变体=CORE_SET_WATERMARK_ODD，无消费方不开面。"""
        return static_value("SetRotationIcon", "CORE_SET_WATERMARK_EVEN")


tables = Tables()
