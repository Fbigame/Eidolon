"""bundle_lazy — UnityFS 包级惰性读取层（"唯一缓存点"的块级形态）。

定位：`BundleStore.open_bundle` 的内部实现替换件。把 UnityPy 现行的
「`BundleFile.read_fs` 把**所有块**解压后 `b"".join(...)` 成单 bytes 并随 Environment 常驻」
（包源码 `UnityPy/files/BundleFile.py:173-184`）换成
「mmap 原包 + 按需解压块 + 字节预算 LRU」。

**对外零 API 变化**：产出的仍是标准 `UnityPy.Environment`，`env.files` / `env.cabs` /
`env.container` / `resolve_pptr` 语义与老路逐项一致（上游以扫描探针对拍验证过等价）。

保真面（逐字镜像 `File.read_files`，`UnityPy/files/File.py:76-90`）：
    node → reader（惰性块流）→ `ImportHelper.parse_file` → `env.register_cab(name, f)`
    → `env.files[name] = f`
`.resS` 等流资产就是靠这个 **cab 名**被 `helpers/ResourceReader.py:10-33` 找到的——
故注册面一个字都不能少。

接缝依据：`EndianBinaryReader.__new__` 对 `IOBase` 走 Streamable 通路
（`UnityPy/streams/EndianBinaryReader.py:48-49`），所以自定义 file-like 即可全链路惰性化，
**零改包源码**。

退回面（显式、计数、不静默）：
- 非 UnityFS 签名 / 加密包（`ArchiveFlags.UsesAssetBundleEncryption`）/ 块级加密位 /
  未知压缩（LZHAM 等）→ 抛 `LazyUnsupported`，由调用方显式退回 `UnityPy.load` 并计数；
- 上游另有 strict-lazy 诊断开关（把 `SerializedFile.load_dependencies` 变成硬失败，用于
  证明"图驱动没漏 cab 注册、没去开原包兜底"）；产品化后该旋钮出库，固定关闭
  （`_STRICT = False` 常量，无 env）。

旋钮：单包解压块 LRU 预算 = 模块常量 `_BLOCK_CACHE_MB`（沿用上游缺省 64 MB；≤0 = 不限；
无 env，未来要调走显式参数）。
遥测：模块级计数器，`stats()` 读出。

坏盘读防护（上游 2026-11-08 判据卡第 1/2 件，落在本自有块级读层——块号/物理偏移/uc/cs/
flags 只有这里拿得到，等效 fork/pin 收益而零 vendor）：
- **坏块 typed error**：块解压失败 → `BundleBlockCorruptError`（bundle 路径/块号/
  物理偏移/uc/cs/flags/原始异常全带），不再裸抛 `LZ4BlockError` 等无上下文异常；
- **单次重试铁律**：解压失败先按同物理偏移重读重解**恰一次**（瞬时坏读面），二次
  仍失败响亮 typed error，**禁循环**（循环会掩盖介质故障——上游 selfheal L2 同源铁律）。
  干净数据零行为（首次成功路径与旧实现逐字节同态，仅多一层方法调用）。
  注意边界：LZ4 字面量区的单字节翻坏**不必然**炸解码——解码成功但字节错的静默形态
  由 bundle_guard 内容哈希轴（可选）兜；`uncompressedDataHash` 实测全零，不可当块校验源。
文件级两件（内容哈希/好副本回退）住 `eidolon.core.infra.bundle_guard`。
"""
from __future__ import annotations

import io
import mmap
import struct
from collections import Counter, OrderedDict
from pathlib import Path

import UnityPy
from UnityPy.files import SerializedFile
from UnityPy.helpers import CompressionHelper, ImportHelper
from UnityPy.streams import EndianBinaryReader

# ArchiveFlags（UnityPy/enums/BundleFile.py 逐字）
COMP_MASK = 0x3F
FLAG_INFO_AT_END = 0x80          # blocksInfo 在文件尾
FLAG_PADDING = 0x200             # BlockInfoNeedPaddingAtStart
FLAG_ENCRYPT = 0x1400            # UsesAssetBundleEncryption（old 0x400 / new 0x1000）
BLOCK_ENCRYPT_BIT = 0x100        # 块级加密位（decompress_data 里与 decryptor 配对）
_DECOMP = CompressionHelper.DECOMPRESSION_MAP

# 上游缺省行为固化：单包解压块 LRU 预算 64 MB（无 env 旋钮；要调走显式参数）。
_BLOCK_CACHE_MB = 64.0
# 上游 strict-lazy 诊断开关固化关闭（无 env 旋钮；它只服务对拍判据，产品面无用）。
_STRICT = False

DEFAULT_BUDGET_MB = 64.0

_STATS: Counter = Counter()


class LazyUnsupported(RuntimeError):
    """本包不适配惰性读（加密/未知压缩/非 UnityFS）——调用方须显式退回老路并计数。"""


class BundleBlockCorruptError(RuntimeError):
    """坏块 typed error：bundle 路径/块号/物理偏移/uc/cs/flags/原始异常全带。

    单次重读重解后仍失败才投出——二次响亮，禁循环。
    不得用「uc+1 能解就算修好」类症状修复（上游实证案例是坏块症状不是修复）。"""

    def __init__(self, bundle, block: int, phys: int, uc: int, cs: int,
                 flags: int, orig: Exception):
        self.bundle = str(bundle)
        self.block = block
        self.phys = phys
        self.uc = uc
        self.cs = cs
        self.flags = flags
        self.orig = orig
        super().__init__(
            f"bundle 块解码失败（坏块，同偏移重读重解 1 次后仍失败）: "
            f"bundle={bundle} block={block} phys={phys} uc={uc} cs={cs} "
            f"flags={flags:#x} orig={type(orig).__name__}: {orig}")


def stats() -> dict:
    """本进程惰性层计数（诊断用）。"""
    return dict(_STATS)


def budget_bytes() -> int:
    mb = _BLOCK_CACHE_MB
    return 0 if mb <= 0 else int(mb * 2**20)


def _install_dependency_guard() -> None:
    """`SerializedFile.load_dependencies` 观察位（strict 时硬失败；产品固定计数观察）。

    为什么盯它：`ResourceReader.get_resource_data` 在 cab 找不到时走
    `assets_file.load_dependencies(...)` → `environment.load_file(path)`，那条路会**绕开
    我们的图**去开原包——若它被触发，说明图驱动有洞。"""
    if getattr(SerializedFile.load_dependencies, "_bundle_lazy_guard", False):
        return
    orig = SerializedFile.load_dependencies

    def guarded(self, possible_dependencies=None):     # noqa: ANN001
        _STATS["load_dependencies_calls"] += 1
        if _STRICT:
            raise RuntimeError(
                "strict-lazy：SerializedFile.load_dependencies 被调用——图驱动的 cab 注册有洞，"
                "老路兜底会污染判据（见 bundle_lazy docstring）")
        return orig(self, possible_dependencies)

    guarded._bundle_lazy_guard = True                  # type: ignore[attr-defined]
    SerializedFile.load_dependencies = guarded


_install_dependency_guard()


def _align16(x: int) -> int:
    return (x + 15) // 16 * 16


class _R:
    """大端小 reader（UnityFS 头与 blocksInfo 均为大端）。"""

    def __init__(self, buf: bytes, pos: int = 0):
        self.b = buf
        self.p = pos

    def u16(self) -> int:
        v = struct.unpack_from(">H", self.b, self.p)[0]
        self.p += 2
        return v

    def u32(self) -> int:
        v = struct.unpack_from(">I", self.b, self.p)[0]
        self.p += 4
        return v

    def i64(self) -> int:
        v = struct.unpack_from(">q", self.b, self.p)[0]
        self.p += 8
        return v

    def strz(self) -> str:
        end = self.b.index(b"\x00", self.p)
        s = self.b[self.p:end].decode("utf8", "surrogateescape")
        self.p = end + 1
        return s

    def align(self, n: int) -> None:
        self.p = (self.p + n - 1) // n * n


class LazyBundle:
    """单包：头/blocksInfo 解析 + 块级按需解压（mmap 只读原包，不 join）。"""

    def __init__(self, path: str | Path, budget: int | None = None):
        self.path = Path(path)
        self._fh = open(self.path, "rb")
        self.mm = mmap.mmap(self._fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            self.file_bytes = len(self.mm)
            self.blocks: list[tuple[int, int, int]] = []       # (uncompressedSize, compressedSize, flags)
            self.nodes: list[tuple[int, int, int, str]] = []
            self._cum_uc: list[int] = [0]
            self._cum_cs: list[int] = [0]
            self.blocks_start = 0
            self.budget = budget_bytes() if budget is None else budget
            self._cache: OrderedDict[int, bytes] = OrderedDict()
            self._cache_bytes = 0
            self.n_decomp = 0
            self.bytes_decomp = 0
            self._parse()
        except BaseException:
            # 头/blocksInfo 阶段失败（坏文件/签名不符）也要放手——否则 mmap 锁死
            # 原文件（Windows 上临时目录清理会炸）。
            self.close()
            raise

    # ---------- 头 + blocksInfo ----------

    def _parse(self) -> None:
        head = self.mm[: min(65536, self.file_bytes)]
        r = _R(head)
        sig = r.strz()
        if sig != "UnityFS":
            raise LazyUnsupported(f"{self.path.name}: 签名 {sig!r}（非 UnityFS）")
        version = r.u32()
        self.player_version = r.strz()                       # player version
        self.version_engine = r.strz()                       # engine version（CAB 级 unity_version 常为 0.0.0，真值在这）
        r.i64()                                             # size
        csize = r.u32()
        ucs = r.u32()
        dataflags = r.u32()
        if version >= 7:
            r.align(16)
        start = r.p
        if dataflags & FLAG_ENCRYPT:
            raise LazyUnsupported(f"{self.path.name}: 加密包（dataflags={dataflags:#x}）")
        if dataflags & FLAG_INFO_AT_END:
            info_off = self.file_bytes - csize
            self.blocks_start = start
        else:
            info_off = start
            self.blocks_start = start + csize
            if dataflags & FLAG_PADDING:
                self.blocks_start = _align16(self.blocks_start)
        info_comp = dataflags & COMP_MASK
        raw = self.mm[info_off:info_off + csize]
        if info_comp not in _DECOMP:
            raise LazyUnsupported(f"{self.path.name}: blocksInfo 压缩 {info_comp} 不支持")
        info = raw if info_comp == 0 else _DECOMP[info_comp](raw, ucs)
        ri = _R(info, 16)                                   # 前 16B = 数据哈希
        for _ in range(ri.u32()):
            self.blocks.append((ri.u32(), ri.u32(), ri.u16()))
        for _ in range(ri.u32()):
            self.nodes.append((ri.i64(), ri.i64(), ri.u32(), ri.strz()))
        for uc, cs, flags in self.blocks:
            if flags & BLOCK_ENCRYPT_BIT:
                raise LazyUnsupported(f"{self.path.name}: 块级加密位（flags={flags:#x}）")
            if (flags & COMP_MASK) not in _DECOMP:
                raise LazyUnsupported(f"{self.path.name}: 块压缩 {flags & COMP_MASK} 不支持")
            self._cum_uc.append(self._cum_uc[-1] + uc)
            self._cum_cs.append(self._cum_cs[-1] + cs)
        _STATS["blocks_total"] += len(self.blocks)

    @property
    def total_uc(self) -> int:
        return self._cum_uc[-1]

    # ---------- 块级读 ----------

    def _block(self, i: int) -> bytes:
        b = self._cache.get(i)
        if b is not None:
            self._cache.move_to_end(i)
            return b
        uc, cs, flags = self.blocks[i]
        phys = self.blocks_start + self._cum_cs[i]
        b = self._decode_block(i, phys, uc, cs, flags)
        self.n_decomp += 1
        self.bytes_decomp += len(b)
        _STATS["blocks_decompressed"] += 1
        _STATS["bytes_decompressed"] += len(b)
        self._cache[i] = b
        self._cache_bytes += len(b)
        while self.budget and self._cache_bytes > self.budget and len(self._cache) > 1:
            _k, old = self._cache.popitem(last=False)
            self._cache_bytes -= len(old)
            _STATS["blocks_evicted"] += 1
        return b

    def _read_raw(self, phys: int, cs: int) -> bytes:
        """单次物理读（mmap 切片）。瞬时坏读的重试面=重新走这里（OS 重新供页）。"""
        return self.mm[phys:phys + cs]

    def _decode_block(self, i: int, phys: int, uc: int, cs: int, flags: int) -> bytes:
        """解压一个块：失败重读重解恰一次（单次重试铁律，禁循环），二次投 typed error。

        干净数据零行为：首次成功路径与旧实现逐字节同态。"""
        comp = flags & COMP_MASK
        last: Exception | None = None
        for attempt in (1, 2):
            raw = self._read_raw(phys, cs)
            try:
                out = raw if comp == 0 else _DECOMP[comp](raw, uc)
            except Exception as exc:                    # noqa: BLE001 —— 统一包装进 typed error
                last = exc
                if attempt == 1:
                    _STATS["block_retry_attempts"] += 1
                continue
            if attempt == 2:
                _STATS["block_retry_recovered"] += 1
            return out
        _STATS["block_corrupt"] += 1
        raise BundleBlockCorruptError(self.path, i, phys, uc, cs, flags, last) from last

    def _block_of(self, off: int) -> int | None:
        if off < 0 or off >= self.total_uc:
            return None
        lo, hi = 0, len(self.blocks)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._cum_uc[mid + 1] <= off:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def read(self, off: int, n: int) -> bytes:
        # 快路：整段落在同一块内（顺序小读=元数据解析主形态；省掉循环与 bytearray 装配）
        i = self._block_of(off)
        if i is not None:
            b = self._cache.get(i)
            if b is not None:
                inblk = off - self._cum_uc[i]
                if inblk + n <= len(b):
                    return b[inblk:inblk + n]
        out = bytearray()
        while n > 0:
            i = self._block_of(off)
            if i is None:
                break
            b = self._block(i)
            inblk = off - self._cum_uc[i]
            take = min(n, len(b) - inblk)
            if take <= 0:
                break
            out += b[inblk:inblk + take]
            off += take
            n -= take
        return bytes(out)

    def close(self) -> None:
        try:
            self.mm.close()
        finally:
            self._fh.close()


class BlockStream(io.RawIOBase):
    """逻辑区间 [base, base+size) 的惰性 file-like 视图（UnityPy 认 IOBase → Streamable）。"""

    def __init__(self, br: LazyBundle, base: int, size: int):
        super().__init__()
        self.br = br
        self.base = base
        self.size = size
        self.pos = 0
        # 单块窗口（顺序小读快路；元数据解析每包上万次 read(1) 级调用，走块装配会慢一个量级）
        self._w_start: int | None = None
        self._w_buf = b""

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, off: int, whence: int = 0) -> int:
        if whence == 0:
            p = off
        elif whence == 1:
            p = self.pos + off
        elif whence == 2:
            p = self.size + off
        else:
            raise ValueError(f"bad whence {whence}")
        self.pos = max(0, p)
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        lo = self.base + self.pos
        hi = lo + n
        w0 = self._w_start
        if w0 is not None and w0 <= lo and hi <= w0 + len(self._w_buf):
            data = self._w_buf[lo - w0:hi - w0]
            self.pos += n
            return data
        br = self.br
        data = br.read(lo, n)
        self.pos += len(data)
        i = br._block_of(lo)                            # noqa: SLF001 —— 同层内部件，取窗口
        if i is not None:
            b = br._block(i)
            b0 = br._cum_uc[i]                          # noqa: SLF001
            if b0 <= lo and hi <= b0 + len(b):
                self._w_start = b0
                self._w_buf = b
        return data


def open_env(path: str | Path, budget: int | None = None) -> UnityPy.Environment:
    """按惰性路构建一个 bundle 的 Environment（镜像 `File.read_files`）。

    不适配的包抛 `LazyUnsupported`（调用方显式退回 `UnityPy.load`）。
    """
    br = LazyBundle(path, budget=budget)
    env = UnityPy.Environment()
    for (off, size, nflags, npath) in br.nodes:
        if size <= 0:
            continue
        try:
            reader = EndianBinaryReader(BlockStream(br, off, size))
            f = ImportHelper.parse_file(reader, env, npath, is_dependency=False)
        except BundleBlockCorruptError:
            br.close()
            raise                                   # 坏块 typed error 直通——本包适配惰性路,
                                                    # 坏的是数据；包成 LazyUnsupported 会错退老路丢上下文
        except Exception as exc:                        # noqa: BLE001
            br.close()
            raise LazyUnsupported(f"{Path(path).name}:{npath}: {type(exc).__name__}: {exc}") from exc
        if isinstance(f, (EndianBinaryReader, SerializedFile)):
            env.register_cab(npath, f)
        try:
            f.flags = nflags
        except Exception:                               # noqa: BLE001
            pass
        env.files[npath] = f
    env._lazy_bundles = [br]                             # 生命周期：env 活 → mmap 活  # noqa: SLF001
    _STATS["open_lazy"] += 1
    return env


def close_env(env) -> None:
    """显式关闭一个惰性 env 持有的 mmap（老路 env 调用为 no-op）。"""
    for br in getattr(env, "_lazy_bundles", []) or []:
        br.close()
    try:
        env._lazy_bundles = []
    except Exception:                                   # noqa: BLE001
        pass


def is_lazy_env(env) -> bool:
    return bool(getattr(env, "_lazy_bundles", None))
