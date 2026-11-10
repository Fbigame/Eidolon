"""object_cache — "唯一缓存点"的**对象级**（v2：句柄携带地址），2026-10-17。

状态：**实验性、默认关闭**（门级实测为负，见下"实测"）。保留作后续定点开启的底座。

## 为什么是 v2（v1 的教训）

v1 把缓存挂在 UnityPy 的 `.image` 属性上，键要求从**被缓存对象**上反推身份
（`obj.path_id`）；而 `Texture2D` 实例上没有该字段 ⟹ `getattr(..., -1)` 静默兜底 ⟹
同一 CAB 内所有纹理键塌缩成 `(cab, -1)`，全包串图（container/pptr/typetree 三类
键面全绿而 image 单类全红——门级实测为负的根因）。

v2 的两条修正：
1. **身份由调用方携带**：容器面的地址天生是 `(bundle, guid)`（供给链手里就有 GUID，
   无需任何跳转），随 `ObjectHandle` 一路带下去；不在对象上反推字段。
2. **不 monkeypatch**：全局属性补丁会让"我拿到了什么对象"变成常态盲区；
   缓存只在 resolver 的**返回边界**发生。

## 地址的两面（互不替代；不要把 path_id 当唯一路线）

- **容器面**：`(bundle, guid)` —— GUID 是 container 键（供给主路径：catalog 查 bundle、
  container 查对象，两次纯表，无 PPtr 跳转）。本模块用它。
- **内部引用面**：`(cab, file_id, path_id)` —— typetree 里的 PPtr。只在 `resolve_pptr`
  内部使用；那里 `ObjectReader` 在手、字段确定存在。
  cab 取不到（调用方没给 owner）时**不缓存**并计数——**不用 bundle 名冒充 cab**。

## 无默认值纪律

键的任何分量缺失都**不兜底**：`ObjectHandle` 构造即校验 `bundle/guid` 非空，
缺失抛 `MissingAddress`；`memo_pptr` 的 cab 缺失走显式 skip 分支（计数可见）。
"""
from __future__ import annotations

from collections import Counter, OrderedDict, namedtuple

# 产品态固定默认关（设计 §8：三处 env 旋钮全删，默认零 IO 零目录；如未来要开，
# 走显式参数/测试注入——模块常量是唯一开关面，测试直接 patch）。
_STATS: Counter = Counter()
_ENABLED = False
_BUDGET_BYTES = 256 * 2**20
_KINDS = {"container", "typetree", "pptr"}

_TT: OrderedDict = OrderedDict()      # (bundle, guid) → 原始 typetree dict（只读）
_PPTR: OrderedDict = OrderedDict()    # (cab, file_id, path_id) → (对象, bundle)
_CG: OrderedDict = OrderedDict()      # (bundle, guid) → ObjectHandle
_BYTES: dict[str, int] = {"typetree": 0, "pptr": 0, "container": 0}


class MissingAddress(RuntimeError):
    """键分量缺失。**响亮失败**，不得用默认值继续（v1 事故根因）。"""


def enabled() -> bool:
    return _ENABLED


def kind_on(kind: str) -> bool:
    return _ENABLED and kind in _KINDS


def stats() -> dict:
    return {"enabled": _ENABLED, "kinds": sorted(_KINDS),
            "budget_mb": round(_BUDGET_BYTES / 2**20, 1),
            "entries": {"typetree": len(_TT), "pptr": len(_PPTR), "container": len(_CG)},
            "bytes_mb": {k: round(v / 2**20, 2) for k, v in _BYTES.items()},
            "hits": {k: v for k, v in _STATS.items() if k.startswith("hit_")},
            "miss": {k: v for k, v in _STATS.items() if k.startswith("miss_")},
            "skip": {k: v for k, v in _STATS.items() if k.startswith("skip_")},
            "evicted": {k: v for k, v in _STATS.items() if k.startswith("evict_")}}


# ---------------------------------------------------------------- 估算（infra 不得 import supply）

def _est_bytes(obj, _seen=None) -> int:
    if _seen is None:
        _seen = set()
    if len(_seen) > 20000 or id(obj) in _seen:
        return 0
    _seen.add(id(obj))
    try:
        if isinstance(obj, (str, bytes, bytearray)):
            return len(obj)
        if isinstance(obj, memoryview):
            return obj.nbytes
        if hasattr(obj, "nbytes"):
            return int(obj.nbytes)
        if hasattr(obj, "getbands") and hasattr(obj, "width"):
            return int(obj.width * obj.height * len(obj.getbands()))
        if isinstance(obj, dict):
            return sum(_est_bytes(k, _seen) + _est_bytes(v, _seen)
                       for k, v in list(obj.items())[:5000])
        if isinstance(obj, (list, tuple, set, frozenset)):
            return sum(_est_bytes(v, _seen) for v in list(obj)[:5000])
        d = getattr(obj, "__dict__", None)
        if d:
            return sum(_est_bytes(v, _seen) for v in d.values())
        slots = getattr(type(obj), "__slots__", ()) or ()
        if slots:
            return sum(_est_bytes(getattr(obj, s, None), _seen) for s in slots)
    except Exception:                                   # noqa: BLE001
        return 0
    return 0


def _total() -> int:
    return sum(_BYTES.values())


def _put(kind: str, store, key, val) -> None:
    store[key] = val
    _BYTES[kind] = _BYTES.get(kind, 0) + _est_bytes(val)
    while _total() > _BUDGET_BYTES and len(store) > 1:
        _k, old = store.popitem(last=False)
        _BYTES[kind] -= _est_bytes(old)
        _STATS[f"evict_{kind}"] += 1


# ---------------------------------------------------------------- 地址：两族并列（带标签）

class Addr(namedtuple("Addr", "kind bundle ref")):
    """**带类型标签的地址**——两族并列，键天然隔离，可互换（换需经转换函数）。

    - `Addr.guid(bundle, guid)`            容器面：GUID 即 container 键；供给主路径天然持有
    - `Addr.path(bundle, cab, path_id)`    内部面：typetree 里的 PPtr / mip 链寻址

    为什么必须带标签：两族的键空间**看起来**都是"bundle + 一个 id"，混用即静默串键
    （v1 事故：把 path_id 当唯一路线，键塌缩成 (cab, -1) → 同包串图）。
    标签让"当前在用哪一族"成为显式事实，也让缓存键跨族不可碰撞。
    """

    __slots__ = ()

    def __new__(cls, kind: str, bundle: str, ref):
        if kind not in ("guid", "path"):
            raise MissingAddress(f"未知地址族 {kind!r}")
        if not bundle or ref in (None, ""):
            raise MissingAddress(f"地址不完整：kind={kind!r} bundle={bundle!r} ref={ref!r}")
        return super().__new__(cls, kind, bundle, ref)

    @classmethod
    def guid(cls, bundle: str, guid: str) -> "Addr":
        return cls("guid", bundle, str(guid).lower())

    @classmethod
    def path(cls, bundle: str, cab: str, path_id: int) -> "Addr":
        if not cab:
            raise MissingAddress("path 族地址必须有 cab（bundle 名不能冒充 CAB）")
        return cls("path", bundle, (str(cab).lower(), int(path_id)))

    # ---- 族内取字段（错族即响亮失败）----
    @property
    def guid_value(self) -> str:
        if self.kind != "guid":
            raise MissingAddress(f"不是 guid 族地址：{self!r}")
        return self.ref                                  # type: ignore[return-value]

    @property
    def path_value(self) -> tuple[str, int]:
        if self.kind != "path":
            raise MissingAddress(f"不是 path 族地址：{self!r}")
        return self.ref                                  # type: ignore[return-value]


def to_path(addr: Addr, env) -> Addr:
    """guid 族 → path 族（经 container 索引）。找不到即响亮失败，不猜。"""
    if addr.kind == "path":
        return addr
    pptr = env.container.container_dict.get(addr.guid_value)
    if pptr is None:
        raise MissingAddress(f"container 无 {addr.guid_value}（无法转 path 族）")
    obj = pptr.deref()
    af = getattr(obj, "assets_file", None)
    cab = str(getattr(af, "name", "") or "")
    return Addr.path(addr.bundle, cab, int(getattr(obj, "path_id", -1)))


def to_guid(addr: Addr, env) -> Addr:
    """path 族 → guid 族（经 SerializedFile.container.path_dict 反查）。找不到即失败。"""
    if addr.kind == "guid":
        return addr
    cab, path_id = addr.path_value
    sf = env.get_cab(cab)
    if sf is None:
        raise MissingAddress(f"env 无 CAB {cab}（无法转 guid 族）")
    key = getattr(sf, "container", None)
    guid = (getattr(key, "path_dict", {}) or {}).get(path_id)
    if not guid:
        raise MissingAddress(f"{cab} 的 container 无 path_id {path_id}（无法转 guid 族）")
    return Addr.guid(addr.bundle, guid)


# ---------------------------------------------------------------- 句柄（地址随行）

class ObjectHandle:
    """Resolver 交出对象的轻代理：**带标签地址随句柄走**，其余全权委托给底层对象。

    - 鸭子型兼容：`.type` / `.path_id` / `.assets_file` / `resolve_pptr(owner_obj=…)` 等
      全部经 `__getattr__` 委托，故 `reader, _ = res.container_get(...)` 的既有写法零改动；
    - `read_typetree(wrap=False)` 按 `addr` 缓存（只读 dict）；键含族标签，不会与 path 族互撞；
    - `read()`（wrap=True 实例）**不缓存**——渲染管线会原地改写实例，共享即泄漏（v1 实证）；
    - `.image` 不在本类缓存（需实例级代理；门级实测不划算）。
    """

    __slots__ = ("addr", "reader")

    def __init__(self, addr: Addr, reader):
        object.__setattr__(self, "addr", addr)
        object.__setattr__(self, "reader", reader)

    # ---- 委托 ----
    def __getattr__(self, name):                        # 仅在常规查找失败时触发
        try:
            reader = object.__getattribute__(self, "reader")
        except AttributeError:                          # 极端：构造未完成
            raise AttributeError(name) from None
        return getattr(reader, name)

    def __repr__(self) -> str:
        addr = object.__getattribute__(self, "addr")
        return f"<ObjectHandle {addr.kind}:{addr.bundle}:{addr.ref} → {type(self.reader).__name__}>"

    # ---- 缓存面 ----
    def read_typetree(self, nodes=None, wrap=False, check_read=True):
        reader = object.__getattribute__(self, "reader")
        if nodes is not None or wrap or not kind_on("typetree"):
            return reader.read_typetree(nodes=nodes, wrap=wrap, check_read=check_read)
        key = object.__getattribute__(self, "addr")          # 带族标签：跨族不可碰撞
        got = _TT.get(key)
        if got is not None:
            _TT.move_to_end(key)
            _STATS["hit_typetree"] += 1
            return got
        _STATS["miss_typetree"] += 1
        val = reader.read_typetree(nodes=None, wrap=False, check_read=check_read)
        _put("typetree", _TT, key, val)
        return val

    def read(self, check_read=True):
        return object.__getattribute__(self, "reader").read(check_read=check_read)


# ---------------------------------------------------------------- resolver 侧入口

def memo_container(bundle: str, guid: str, build):
    """container_get 的地址键 memo：`Addr.guid(bundle, guid)` → `(ObjectHandle, 实际 container 键)`。

    `build()` 返回 `(obj, container_key)`；obj 为 None 表示确实没有（不缓存、原样返回）。
    命中返回**同一个 handle**，且实际 container 键原样带回（兼容带路径键的包）。
    """
    if not kind_on("container"):
        return build()
    addr = Addr.guid(bundle, guid)                         # 构造即校验，缺即响亮失败
    got = _CG.get(addr)
    if got is not None:
        _CG.move_to_end(addr)
        _STATS["hit_container"] += 1
        return got
    obj, ckey = build()
    if obj is None:
        return None, ckey
    _STATS["miss_container"] += 1
    val = (ObjectHandle(addr, obj), ckey)
    _put("container", _CG, addr, val)
    return val


def memo_pptr(bundle: str, cab: str | None, file_id: int, path_id: int, build):
    """resolve_pptr 的**内部面**地址键 memo：`Addr.path(bundle, cab, path_id)`。

    `cab` 取不到（调用方未持有 owner）时：**不缓存**并计数——不拿 bundle 名冒充 cab
    （一个 bundle 内可有多个 SerializedFile，externals 表按 CAB 各自不同）。
    """
    if not kind_on("pptr"):
        return build()
    if not cab:
        _STATS["skip_pptr_no_cab"] += 1
        return build()
    key = Addr.path(bundle, cab, path_id)
    got = _PPTR.get(key)
    if got is not None:
        _PPTR.move_to_end(key)
        _STATS["hit_pptr"] += 1
        return got
    _STATS["miss_pptr"] += 1
    val = build()
    _put("pptr", _PPTR, key, val)
    return val


def clear() -> None:
    for d in (_TT, _PPTR, _CG):
        d.clear()
    for k in _BYTES:
        _BYTES[k] = 0
