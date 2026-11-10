"""il_tables — 方法体 IL 直读（活程序集字节面机械 extractor，零 decomp 依赖）。

机制（上游立件）：先例=
`dll_reflect.enum_table/static_dict`（字段/枚举反射面）；本件下探一层——
`MethodBody.GetILAsByteArray()` 字节面 + ECMA-335 指令解码。操作数尺寸表自活运行时
`System.Reflection.Emit.OpCodes` 构建（零手抄 opcode 表——尺寸随运行时供货）。

本模块零游戏语义：不知道 Actor/Color 是什么，只提供机械 pattern extractor：
  - `ctor_object_fields`：构造器内「ldarg.0 + 常量×n + newobj <T> + stfld 字段」
    初始化三元组（readonly Color/Vector2 字段族的正典初始化形态）；
  - `switch_ldfld_arms`：方法体单一 switch 指令的臂表（值 → ldfld 字段名）+
    default 腿形状（引擎 enum 分派的正典形态）；
  - `method_rva_arrays`：方法体内「Ldtoken + InitializeArray」RVA 常量数组原始
    字节（Release 编译器把方法内常量数组收进 <PrivateImplementationDetails>，
    实证=EntityBase.SortRaceList 序表）；
  - `ctor_list_const_items`：构造器内 List 常量初始化集（实证=Actor..ctor
    VALID_FACTIONS 六项——同批立件）；
  - `dispatch_call_consts`：枚举分派方法「case → call 前常量」臂表+字面量腿
    （实证=ActorNames.GetHandActor——同批立件）。
消费方自做语义断言（臂数/值域/default 形状），失败响亮在本层以 assert 前置兜底
（pattern 不匹配=方法形态漂移，必须红——禁静默空集，探针产出静默空集判表假设教训）。

锚账（decomp 对照，转写验证用；运行时不读 decomp）：
  - ctor pattern 实证=Actor.cs:Actor..ctor（GEM_*/CLASS_COLOR_* readonly 字段族）；
  - switch pattern 实证=Actor.cs:Actor.GetClassColor/:GetDualClassColor/
    :GetLocationClassColor（ldarg.1; ldc.i4 BASE; sub; switch(t₁..t₁₁); br default;
    臂=ldarg.0; ldfld F; stloc/ret）。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

# 程序集路径单源=GameContext（契约 D：ctx.assembly_csharp/managed，入口显式 install；
# 本模块不直接消费路径——IL 抽取吃 dll_reflect 已装载的活程序集内存字节）。

# 操作数尺寸语义（ECMA-335 OperandType → 字节数；InlineSwitch=变长由指令内 count 定）
_OPERAND_SIZES = {
    "InlineNone": 0, "ShortInlineBrTarget": 1, "InlineBrTarget": 4,
    "ShortInlineI": 1, "InlineI": 4, "InlineI8": 8,
    "ShortInlineR": 4, "InlineR": 8, "InlineMethod": 4, "InlineField": 4,
    "InlineType": 4, "InlineTok": 4, "InlineString": 4, "InlineVar": 2,
    "ShortInlineVar": 1, "InlineSwitch": -1, "InlineSig": 4,
}


@lru_cache(maxsize=1)
def _opcode_tables() -> tuple[dict[int, tuple[str, int]], dict[int, tuple[str, int]]]:
    """(单字节表, 0xFE 双字节表)：opcode 字节 → (助记名, 操作数字节数)。

    表自活运行时 System.Reflection.Emit.OpCodes 构建（零手抄）；pythonnet 侧
    System 导入必须后于 coreclr 装载（dll_reflect.assembly/type_ 先行）。

    字节序（上游勘误）：双字节指令 Value=0xFE??（0xFE
    在**高**字节、编码第二字节在低字节——Ceq Value=0xFE01 → 编码 FE 01）。旧版
    取反（按低字节==0xFE 分桶）把全部双字节指令塞进单字节表，遮蔽同字节真指令
    （Ldnull 0x14 被 Tailcall 占、ldc.i4.6 0x1C 被 Sizeof 占、break 0x01 被 Ceq
    占；dir 序不定=同进程群内非确定），且含 FE 前缀指令的方法体在 disassemble
    走 double.get 命中 None 必炸。凡含双字节指令的方法，旧表解码必错。"""
    from eidolon.core.infra import dll_reflect  # noqa: PLC0415（确保 coreclr 已装载）

    dll_reflect.assembly()   # boot（幂等；System 导入前置闸）
    from System.Reflection.Emit import OpCodes  # noqa: PLC0415

    single: dict[int, tuple[str, int]] = {}
    double: dict[int, tuple[str, int]] = {}
    for name in dir(OpCodes):
        if name.startswith("_") or name in ("EmptyOperandTypes",):
            continue
        op = getattr(OpCodes, name, None)
        if op is None or type(op).__name__ != "OpCode":
            continue
        val = int(op.Value)   # short：双字节指令 Value=0xFE??（高字节=0xFE 前缀）
        sz = _OPERAND_SIZES[str(op.OperandType)]
        low, high = val & 0xFF, (val >> 8) & 0xFF
        if high == 0xFE:
            double[low] = (name, sz)   # 助记名=OpCodes 字段名（PascalCase，如 Ldc_R4）
        else:
            single[low] = (name, sz)
    assert single and double, "活运行时 OpCode 表空——pythonnet 装载态异常"
    assert double.get(0x01) == ("Ceq", 0) and single.get(0x14) == ("Ldnull", 0), (
        "OpCode 字节序自检失败（双字节桶装反？）——disassemble 语义不可信，先修本表")
    return single, double


def disassemble(il: bytes, module: Any) -> list[tuple[int, str, Any, str | None]]:
    """IL 线性反汇编 → [(offset, 助记名, 操作数, 操作数字节hex)]。

    token 类操作数（ldfld/stfld/newobj/call/...）附带解析名（module.ResolveField/
    ResolveMethod，解析失败保 token hex 不炸）；switch 操作数=(基相对跳转 rel 列表)。
    未知 opcode 即 raise（字节面形态漂移必须响，禁静默滑过）。"""
    single, double = _opcode_tables()
    out: list[tuple[int, str, Any, str | None]] = []
    i, n = 0, len(il)
    while i < n:
        off = i
        b = il[i]
        i += 1
        if b == 0xFE:
            entry = double.get(il[i]) if i < n else None
            if entry is None:
                raise AssertionError(f"IL 未知双字节 opcode 0xFE {il[i:i+1].hex()} @ {off}")
            name, sz = entry
            i += 1
        else:
            entry = single.get(b)
            if entry is None:
                raise AssertionError(f"IL 未知 opcode 0x{b:02x} @ {off}")
            name, sz = entry
        if sz == -1:   # switch：u4 count + count×u4 相对偏移
            cnt = int.from_bytes(il[i:i + 4], "little")
            i += 4
            rels = tuple(int.from_bytes(il[i + 4 * k:i + 4 + 4 * k], "little")
                         for k in range(cnt))
            i += 4 * cnt
            out.append((off, name, rels, None))
            continue
        operand_hex = il[i:i + sz].hex()
        operand: Any = il[i:i + sz]
        i += sz
        resolved = None
        if name in ("Ldfld", "Ldflda", "Stfld", "Ldsfld", "Stsfld"):
            tok = int.from_bytes(operand, "little")
            try:
                fi = module.ResolveField(tok)
                resolved = f"{fi.DeclaringType.Name}.{fi.Name}" if fi is not None else None
            except Exception:  # noqa: BLE001（token 解析失败=跨模块 ref，交调用方裁决）
                resolved = None
        elif name in ("Call", "Callvirt", "Newobj", "Ldftn"):
            tok = int.from_bytes(operand, "little")
            try:
                mi = module.ResolveMethod(tok)
                if mi is not None:
                    dt = mi.DeclaringType.Name if mi.DeclaringType is not None else "?"
                    resolved = f"{dt}::{mi.Name}"
            except Exception:  # noqa: BLE001
                resolved = None
        elif sz == 4:
            operand = int.from_bytes(operand, "little")
        elif sz == 1:
            operand = operand[0]
        elif sz == 8:
            operand = int.from_bytes(operand, "little")
        out.append((off, name, operand, resolved if resolved is not None else operand_hex))
    return out


def _il_of(method: Any) -> tuple[bytes, Any]:
    body = method.GetMethodBody()
    assert body is not None, f"{method} 无方法体（abstract/pinvoke?）——IL 直读不可及"
    return bytes(bytearray(body.GetILAsByteArray())), method.Module


def _method(type_name: str, method_name: str,
            param_count: int | None = None) -> Any:
    from eidolon.core.infra import dll_reflect  # noqa: PLC0415

    t = dll_reflect.type_(type_name)
    from System.Reflection import BindingFlags  # noqa: PLC0415（coreclr 后置导入）
    hits = [m for m in t.GetMethods(BindingFlags.Instance | BindingFlags.Static
                                    | BindingFlags.Public | BindingFlags.NonPublic)
            if m.Name == method_name]
    if param_count is not None:
        hits = [m for m in hits if len(m.GetParameters()) == param_count]
    assert len(hits) == 1, (
        f"{type_name}.{method_name}（params={param_count}）命中 {len(hits)} 个重载"
        "——IL 直读需唯一方法名（形态漂移，先核 Assembly-CSharp）")
    return hits[0]


def ctor_object_fields(type_name: str, obj_type_name: str,
                       const_count: int = 3) -> dict[str, tuple[float, ...]]:
    """构造器内「ldarg.0 + 常量×n + newobj <obj_type_name> + stfld 字段」初始化集。

    返回 {字段名: 常量元组}（float 化）。readonly 字段族的正典初始化形态
    （实证=Actor.cs:Actor..ctor CLASS_COLOR_*/GEM_COLOR_*）。pattern 不匹配/
    零命中即 raise（形态漂移必须响）。"""
    from eidolon.core.infra import dll_reflect  # noqa: PLC0415

    t = dll_reflect.type_(type_name)
    from System.Reflection import BindingFlags  # noqa: PLC0415
    ctors = list(t.GetConstructors(BindingFlags.Instance | BindingFlags.Public
                                   | BindingFlags.NonPublic))
    assert ctors, f"{type_name} 无实例构造器——IL 直读不可及"
    out: dict[str, tuple[float, ...]] = {}
    for ctor in ctors:
        il, module = _il_of(ctor)
        code = disassemble(il, module)
        k = const_count
        for idx in range(len(code) - k - 3):
            ops = code[idx:idx + k + 3]
            if ops[0][1] != "Ldarg_0":
                continue
            consts = []
            ok = True
            for op in ops[1:1 + k]:
                if op[1] != "Ldc_R4":
                    ok = False
                    break
                import struct  # noqa: PLC0415
                consts.append(struct.unpack("<f", bytes.fromhex(op[3]))[0])
            if not ok:
                continue
            newobj, stfld = ops[1 + k], ops[2 + k]
            if newobj[1] != "Newobj" or stfld[1] != "Stfld":
                continue
            if newobj[3] != f"{obj_type_name}::.ctor":
                continue
            assert stfld[3] is not None, (
                f"{type_name}..ctor Stfld token 未解析（{stfld[2]}）——字段面漂移")
            fld = stfld[3].split(".", 1)[1]
            out[fld] = tuple(consts)
    assert out, (
        f"{type_name}..ctor 未命中「ldc.r4×{const_count}+newobj {obj_type_name}+stfld」"
        "初始化 pattern——字段初始化形态漂移，先核 Assembly-CSharp 再动消费面")
    return out


_IMPLICIT_I4 = {"Ldc_I4_M1": -1, "Ldc_I4_0": 0, "Ldc_I4_1": 1, "Ldc_I4_2": 2,
                "Ldc_I4_3": 3, "Ldc_I4_4": 4, "Ldc_I4_5": 5, "Ldc_I4_6": 6,
                "Ldc_I4_7": 7, "Ldc_I4_8": 8}
"""ldc.i4.M1/.0.../.8 无操作数指令的隐式常量值（ECMA-335 III 1.1 表）。"""


def _iconst(entry: tuple) -> int:
    """Ldc_I4* 指令的 int 常量（隐式/单字节/四字节全型）。"""
    name, opnd = entry[1], entry[2]
    if name in ("Ldc_I4_S", "Ldc_I4", "Ldc_I8"):
        return int(opnd)
    return _IMPLICIT_I4[name]


def switch_ldfld_arms(type_name: str, method_name: str) \
        -> tuple[dict[int, str], dict[str, Any]]:
    """方法体单一 switch 的臂表 + default 腿形状。

    返回 (arms, default)：arms={case 值: ldfld 字段名}；default={"target": off,
    "ldfld": [字段名…], "call": [解析名…]}（default 腿自 Br 目标起解码至 Ret）。

    正典形态（实证=Actor.cs:Actor.GetClassColor/:GetDualClassColor/
    :GetLocationClassColor）：`ldarg.1; ldc.i4 BASE; sub; switch(rel…); br default`，
    每臂=「ldarg.0; ldfld F; stloc/ret」。形态偏离（多 switch/无 sub 前置/臂多
    ldfld）即 raise——引擎 enum 分派形态漂移必须响。"""
    method = _method(type_name, method_name)
    il, module = _il_of(method)
    code = disassemble(il, module)
    sw_idx = [i for i, c in enumerate(code) if c[1] == "Switch"]
    assert len(sw_idx) == 1, (
        f"{type_name}.{method_name} 含 {len(sw_idx)} 个 switch 指令——直读器以单 switch "
        "为前提（形态漂移，先核 Assembly-CSharp）")
    si = sw_idx[0]
    off, _nm, rels, _hx = code[si]
    # base 检测：[..., Ldc_I4*<BASE>, Sub] 前置 → base=BASE；否则 base=0
    base = 0
    if si >= 2 and code[si - 1][1] == "Sub" and code[si - 2][1].startswith("Ldc_I4"):
        base = _iconst(code[si - 2])
    else:
        assert si >= 1 and code[si - 1][1].startswith("Ldarg"), (
            f"{type_name}.{method_name} switch 前置形态非「ldarg[; ldc; sub]」"
            "——分派值装载形态漂移")
    sw_end = off + 1 + 4 + 4 * len(rels)
    assert len(rels) > 0, f"{type_name}.{method_name} switch 空臂"
    arms: dict[int, str] = {}
    for i, rel in enumerate(rels):
        target = sw_end + rel
        run = _run_until_branch(code, target, f"{type_name}.{method_name} 臂值 {base + i}")
        ldflds = [c[3] for c in run if c[1] == "Ldfld"]
        assert len(ldflds) == 1 and ldflds[0] is not None, (
            f"{type_name}.{method_name} 臂值 {base + i} 含 {len(ldflds)} 个 ldfld——"
            "臂形态漂移（正典=单 ldfld），先核 Assembly-CSharp")
        arms[base + i] = ldflds[0].split(".", 1)[1]
    # default 腿：switch 后第一条 Br 的目标（Br_S=1 字节操作数 → 目标=off+2+rel；Br=off+5+rel）
    nxt = code[si + 1]
    assert nxt[1] in ("Br", "Br_S"), (
        f"{type_name}.{method_name} switch 后非 Br（default 腿定位失效）——形态漂移")
    default_target = nxt[0] + (2 if nxt[1] == "Br_S" else 5) + int(nxt[2])
    drun = _run_until_ret(code, default_target, f"{type_name}.{method_name} default")
    dinfo: dict[str, Any] = {
        "target": default_target,
        "ldfld": [c[3].split(".", 1)[1] for c in drun if c[1] == "Ldfld"],
        "call": [c[3] for c in drun if c[1] in ("Call", "Callvirt")],
    }
    return arms, dinfo


def _run_until_branch(code: list, start: int, tag: str) -> list:
    by_off = {c[0]: i for i, c in enumerate(code)}
    assert start in by_off, f"{tag} 目标偏移 {start} 不在指令边界（跳进操作数?）"
    run = []
    i = by_off[start]
    while i < len(code):
        c = code[i]
        if c[1] in ("Br", "Br_S", "Brtrue", "Brtrue_S", "Brfalse", "Brfalse_S", "Ret"):
            break
        run.append(c)
        i += 1
    return run


def _run_until_ret(code: list, start: int, tag: str) -> list:
    by_off = {c[0]: i for i, c in enumerate(code)}
    assert start in by_off, f"{tag} 目标偏移 {start} 不在指令边界（跳进操作数?）"
    run = []
    i = by_off[start]
    while i < len(code):
        c = code[i]
        run.append(c)
        if c[1] == "Ret":
            break
        i += 1
    assert run and run[-1][1] == "Ret", f"{tag} 腿未以 Ret 收口（解码越界?）"
    return run


# ============================================================================
# 扩面：三个机械 pattern extractor（零游戏语义）
# ============================================================================


def method_rva_arrays(type_name: str, method_name: str,
                      param_count: int | None = None) -> list[tuple[str, bytes]]:
    """方法体内「Ldtoken <RVA 数据字段> + Call RuntimeHelpers::InitializeArray」
    装载集 → [(RVA 字段名, 原始字节)]。

    Release 编译器把常量数组初始化收进 `<PrivateImplementationDetails>` RVA 静态
    数据（实证=EntityBase.cs:EntityBase.SortRaceList 的 TAG_RACE[13] 序表：方法内
    数组经闭包字段 order 由 Ldtoken+InitializeArray 装载）。字节读出=引擎同款机制
    `RuntimeHelpers.InitializeArray` 灌入自建 byte[]（元素类型无关，调用方解释）。
    pattern 不匹配/零命中即 raise（形态漂移必须响）。"""
    from eidolon.core.infra import dll_reflect  # noqa: PLC0415

    dll_reflect.assembly()   # System 导入前置闸
    from System import Array, Byte  # noqa: PLC0415
    from System.Runtime.CompilerServices import RuntimeHelpers  # noqa: PLC0415

    method = _method(type_name, method_name, param_count)
    il, module = _il_of(method)
    code = disassemble(il, module)
    out: list[tuple[str, bytes]] = []
    for i, c in enumerate(code):
        if c[1] != "Ldtoken":
            continue
        nxt = code[i + 1] if i + 1 < len(code) else None
        assert nxt is not None and nxt[1] == "Call" and nxt[3] \
            and "InitializeArray" in str(nxt[3]), (
            f"{type_name}.{method_name} Ldtoken 后非 InitializeArray @ {c[0]}"
            "——RVA 数组装载形态漂移")
        fi = module.ResolveField(c[2])
        assert fi is not None, f"{type_name}.{method_name} Ldtoken token 未解析"
        size_name = str(fi.FieldType).rsplit("=", 1)[-1].rstrip(">]$")
        size = int(size_name)   # __StaticArrayInitTypeSize=N（N 属类型名）
        arr = Array.CreateInstance(Byte, size)
        RuntimeHelpers.InitializeArray(arr, fi.FieldHandle)
        out.append((str(fi.Name), bytes(bytearray(arr))))
    assert out, (f"{type_name}.{method_name} 未命中 Ldtoken+InitializeArray"
                 "——RVA 数组装载形态漂移，先核 Assembly-CSharp 再动消费面")
    return out


def ctor_list_const_items(type_name: str, field_name: str) -> list[int]:
    """构造器内「newobj List`1::.ctor; Dup; (常量; Callvirt Add)*; stfld 字段」
    列表初始化集 → 按声明序的常量列表（int）。

    正典形态（实证=Actor.cs:Actor..ctor VALID_FACTIONS List<GAME_TAG> 六项）。
    每项=单 Ldc_I4* 常量（隐式/单字节/四字节全型）；多指令项/非常量项=形态漂移
    raise。字段未命中即 raise（零命中禁静默）。"""
    from eidolon.core.infra import dll_reflect  # noqa: PLC0415

    t = dll_reflect.type_(type_name)
    from System.Reflection import BindingFlags  # noqa: PLC0415
    ctors = list(t.GetConstructors(BindingFlags.Instance | BindingFlags.Public
                                   | BindingFlags.NonPublic))
    assert ctors, f"{type_name} 无实例构造器——IL 直读不可及"
    for ctor in ctors:
        il, module = _il_of(ctor)
        code = disassemble(il, module)
        for i, c in enumerate(code):
            if c[1] != "Stfld" or not c[3] or c[3].split(".", 1)[-1] != field_name:
                continue
            items: list[int] = []
            j = i - 1
            while j >= 0 and code[j][1] == "Callvirt" \
                    and str(code[j][3]).endswith("::Add"):
                assert code[j - 1][1].startswith("Ldc_I4") and code[j - 2][1] == "Dup", (
                    f"{type_name}..ctor {field_name} 列表项形态漂移（期 Dup+单常量+Add）")
                items.append(_iconst(code[j - 1]))
                j -= 3
            assert j >= 0 and code[j][1] == "Newobj" and "::.ctor" in str(code[j][3]), (
                f"{type_name}..ctor {field_name} 列表头非 newobj——初始化形态漂移")
            assert items, f"{type_name}..ctor {field_name} 列表零项"
            items.reverse()   # 自 stfld 向回走=声明逆序
            return items
    raise AssertionError(
        f"{type_name}..ctor 未命中 stfld {field_name} 的常量列表初始化——"
        "字段初始化形态漂移，先核 Assembly-CSharp 再动消费面")


def dispatch_call_consts(type_name: str, method_name: str, callee_name: str,
                         param_count: int | None = None) \
        -> tuple[dict[int, int], dict[str, Any]]:
    """枚举分派方法「case 值 → call <callee_name> 前装载的 Ldc_I4 常量」臂表。

    返回 (arms, default)：arms={case 值: 常量}；default={"ldstr": [串…]}（字面量
    腿，Ldstr 常量串列表——实证=ActorNames.GetHandActor default 腿 Card_Hidden）。

    分派构造（实证=ActorNames.cs:ActorNames.GetHandActor，Release 形态）：主 switch
    （base=枚举值下界，`ldarg.0; ldc.i4 b; sub; switch`）+ 稀疏值 Beq 链
    （`ldarg.0; ldc.i4 k; beq* t`）+ 次级 switch；臂=[Ldc_I4* 常量; (Ldarg*/Ldnull)*;
    Call <callee>; Ret]，臂可多 case 共享（SPELL/QUEST_REWARD/BG_SPELL 同臂）。
    case 目标经 Br/Br_S 跳转即跟随；非臂非跳=形态漂移 raise。重载按 param_count 消歧。"""
    method = _method(type_name, method_name, param_count)
    il, module = _il_of(method)
    code = disassemble(il, module)

    arms: dict[int, int] = {}   # 臂起始偏移 → Ldc 常量
    for i in range(1, len(code) - 1):
        if code[i][1] != "Call" or not code[i][3] \
                or not str(code[i][3]).endswith(f"::{callee_name}"):
            continue
        assert i + 1 < len(code) and code[i + 1][1] == "Ret", (
            f"{type_name}.{method_name} call {callee_name} 后非 Ret @ {code[i][0]}"
            "——臂形态漂移")
        j = i - 1
        while j >= 0 and code[j][1] in ("Ldarg", "Ldarg_S", "Ldarg_0", "Ldarg_1",
                                        "Ldarg_2", "Ldarg_3", "Ldnull"):
            j -= 1
        assert j >= 0 and code[j][1].startswith("Ldc_I4"), (
            f"{type_name}.{method_name} {callee_name} 臂首非 Ldc_I4 常量 @ "
            f"{code[j][0] if j >= 0 else '?'}——臂形态漂移")
        arms[code[j][0]] = _iconst(code[j])

    edges: dict[int, int] = {}   # case 值 → 目标偏移
    for i, c in enumerate(code):
        if c[1] == "Switch":
            base = 0
            if i >= 2 and code[i - 1][1] == "Sub" and code[i - 2][1].startswith("Ldc_I4"):
                base = _iconst(code[i - 2])
            else:
                assert i >= 1 and code[i - 1][1].startswith("Ldarg"), (
                    f"{type_name}.{method_name} switch 前置形态漂移 @ {c[0]}")
            sw_end = c[0] + 1 + 4 + 4 * len(c[2])
            for k, rel in enumerate(c[2]):
                edges[base + k] = sw_end + rel
        elif c[1] in ("Beq", "Beq_S") and i >= 2 \
                and code[i - 1][1].startswith("Ldc_I4") and code[i - 2][1] == "Ldarg_0":
            sz = 2 if c[1] == "Beq_S" else 5
            edges[_iconst(code[i - 1])] = c[0] + sz + int(c[2])

    by_off = {c[0]: i for i, c in enumerate(code)}
    # 字面量 default 腿（Ldstr+Ret）：case 显式指向它=该 case 无常量臂（default 语义）
    ldstr_offs = {c[0] for i, c in enumerate(code) if c[1] == "Ldstr"
                  and i + 1 < len(code) and code[i + 1][1] == "Ret"}
    out: dict[int, int] = {}
    default_cases: list[int] = []
    for case, target in edges.items():
        t = target
        while t not in arms and t not in ldstr_offs:
            assert t in by_off, f"{type_name}.{method_name} case {case} 目标 {t} 越界"
            instr = code[by_off[t]]
            assert instr[1] in ("Br", "Br_S"), (
                f"{type_name}.{method_name} case {case} 落点非臂非跳 @ {t}——分派形态漂移")
            t = instr[0] + (2 if instr[1] == "Br_S" else 5) + int(instr[2])
        if t in ldstr_offs:
            default_cases.append(case)   # case→default 腿（无常量臂）
            continue
        prev = out.get(case)
        assert prev is None or prev == arms[t], (
            f"{type_name}.{method_name} case {case} 双臂冲突（{prev} vs {arms[t]}）")
        out[case] = arms[t]

    ldstrs = [str(module.ResolveString(c[2])) for c in code if c[1] == "Ldstr"]
    return out, {"ldstr": ldstrs, "default_cases": sorted(default_cases)}
