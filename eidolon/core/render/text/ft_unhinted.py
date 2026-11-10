"""ft_unhinted — 引擎口径字形供给驱动（FreeType 2.13.x + FT_LOAD_NO_HINTING）。

批 A（v3.1 字形供给换轨）：本模块是**唯一共享件改动面**。本模块
只出「位图 + 度量 + bearings」，**不碰现役渲染路径**（text_atlas/glyph_supply/uber_text
由 B 号接）。口径逐位实证见 docs/notes/text-rendering-pipeline.md §字形栅格化口径。

引擎口径（都已在 oracle 逐位闭环，勿凭猜测改）：
  * 栅格化 = FreeType 2.13.x + ``FT_LOAD_NO_HINTING``（0x2）→ ``FT_Render_Glyph(NORMAL)``：
    8-bit 灰阶、**top-down**（第 0 行 = 最上一行）、pitch 裁到 width。
    本仓钉 freetype-py==2.5.1（自带 libfreetype 2.13.2；与引擎 2.13.3 在本仓字体/
    尺寸上位图逐位相同，2026-10-22 实证）。
  * advance = FT 26.6 定点整数（``slot.advance.x``，1/64 px）；上层取整
    ``(advance_26_6 + 32) >> 6``（round half up；GLEI@36 的 4 个 .5 由此与图集一致，
    half-even 会错 3 个字）。
  * 斜体 = 引擎**合成斜切** ``s=0.25``：``FT_Set_Transform(xx=0x10000, xy=0x4000,
    yx=0, yy=0x10000)``（16.16 定点）。**读值**（2026-11-01 反汇编直读，非拟合）：
    ``UnityPlayer.dll!0xD9F8E0`` 斜体分支 ``mov eax,0x4000``（face 无真斜体 face
    ∧ 请求 style 位 1 ⇒ 存 ``FT_Matrix{1,0x4000,0,1}`` 到 face->internal->
    transform_matrix 再 FT_Load_Glyph；账=正典「字形栅格化口径」斜体行）。
    不是字体真斜体、也不是 FT 自带 ``FT_GlyphSlot_Oblique``（12°/0x366A → IoU 0.846）。
  * 图集格框/摆位**不属本模块**：格 = ``(rows+2p, width+2p)``、``vert = (left−p,
    top+p, w+2p, −(h+2p))``，其中 p = 字体资产 ``m_CharacterPadding``（GLEI=4、BGO=2；
    **禁写死**，由消费方按资产字段传 p）。

单位与取向：
  * ``Glyph.bitmap``：``np.ndarray`` uint8，shape ``(rows, width)``，行序 top-down，
    空字形（空格/NBSP 等无轮廓字）shape ``(0, 0)``；
  * ``Glyph.left`` / ``Glyph.top``：FT ``bitmap_left`` / ``bitmap_top``，整数像素；
    top 为基线到最上一行墨的向上距离（正=基线以上）；
  * ``Glyph.advance_26_6``：FT 26.6 定点整数；``Glyph.advance_px``：已按引擎规则
    取整的整数像素；``Glyph.width`` / ``Glyph.rows`` 与 ``bitmap`` 形状同源（非独立求值）。

异常（B 号**先 has_glyph 再 glyph**，勿静默 tofu）：
  * ``FileNotFoundError`` — font_path 不存在/不是文件；
  * ``ValueError`` — ppem <= 0；ch 不是恰好一个码点；
  * ``LookupError`` — 该字体 cmap 无此字（引擎侧走 OS 兜底，属供给策略、不归本模块）；
  * ``RuntimeError`` — close() 后再用；pitch/pixel_mode 非预期（响亮，不猜）；
  * ``freetype.ft_errors.FT_Exception`` — FT 底层错误（坏字体等），原样上抛不吞。

并发：**非线程安全**。FT_Face/字形槽是有状态的（transform + load 序列），多线程须
各自 ``get_face`` 或外部加锁。``get_face`` 只 memo face（不 memo 位图）。

坑（前任实测；改本模块前先读）：
  * freetype-py 2.5.1 的 ``Bitmap.buffer`` 是 **list[int]**，长度 = rows*|pitch|；
    pitch > width 时行内有对齐填充 → 必须按 |pitch| reshape 再裁 ``[:, :width]``；
    pitch < 0（底朝上）时该属性用 ``range(rows*pitch)`` 取值 → **直接是空表**，
    只能按 C 结构指针读原始内存再翻行。本模块两种都处理。
  * ``load_char/load_glyph(..., FT_LOAD_NO_HINTING)`` 只把轮廓装进槽（format=OUTLINE），
    **必须先 ``slot.render(FT_RENDER_MODE_NORMAL)`` 再读 ``slot.bitmap``**；否则读到
    上一次的/空的位图（render 前 bitmap 不反映本次 load）。
  * ``FT_Property_Set`` 在 freetype-py 里是 4 参（library, module, name, value）——
    本批**不用**：引擎构建关闭了 FT_CONFIG_OPTION_ENVIRONMENT_PROPERTIES，没有任何
    属性开关是口径的一部分。
  * TTC 固定 face index 0（Microsoft YaHei 的 ttc face0/face1 对样本字逐位相同、
    face2 报错，引擎侧不可判别 → 按默认 face0）。
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import freetype
import numpy as np
from eidolon.core.render._provenance import fitted  # noqa: F401 （族默认）

__all__ = [
    "FT_LOAD_NO_HINTING",
    "Glyph",
    "UnhintedFace",
    "advance_to_px",
    "get_face",
]

# 与 freetype.h 的 FT_LOAD_NO_HINTING (1 << 1) 同值；显式导出给消费方当唯一字面量源。
FT_LOAD_NO_HINTING = 0x2

_GRAY = freetype.FT_PIXEL_MODE_GRAY          # 8-bit 灰阶（NORMAL 渲染的唯一合法输出）
_ONE = 0x10000                               # 16.16 定点 1.0


@dataclass
@fitted(kind="calibration", closed=True)
class Glyph:
    """一个已栅格化的字形（8-bit 灰阶，top-down）。

    字段语义与单位见模块 docstring；``bitmap`` 是**唯一**像素事实源，
    ``width`` / ``rows`` 与 ``bitmap.shape`` 同值（消费方任取其一）。
    """
    bitmap: np.ndarray        # uint8 (rows, width)，top-down；空字形 (0,0)
    width: int                # = bitmap.shape[1]
    rows: int                 # = bitmap.shape[0]
    advance_26_6: int         # FT 26.6 定点 advance（1/64 px）
    advance_px: int           # (advance_26_6 + 32) >> 6
    left: int                 # FT bitmap_left（整数像素）
    top: int                  # FT bitmap_top（整数像素，基线向上为正）


@fitted(kind="calibration", closed=True)
def advance_to_px(advance_26_6: int) -> int:
    """FT 26.6 → 引擎整数像素 advance：``(advance_26_6 + 32) >> 6``（round half up）。

    等价于 C 整数式 ``(advance_x + 32) >> 6``；负数同样按算术右移（floor）语义。
    """
    return (int(advance_26_6) + 32) >> 6


def _codepoint(ch: str) -> int:
    """单码点校验（str 的 len==1 即单码点；代理对在 Python 里也是一个码点）。"""
    if not isinstance(ch, str) or len(ch) != 1:
        raise ValueError(f"ch 必须是单个码点的 str（收到 {ch!r}）")
    return ord(ch)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _bitmap_array(bm) -> np.ndarray:
    """FT_Bitmap（freetype-py 包装）→ uint8 (rows, width) top-down 位图。

    freetype-py 2.5.1 的 ``Bitmap.buffer`` 只对 pitch>0 可用（list[int]）；
    pitch<0 时该属性为空表 → 本函数统一按 C 结构指针读原始内存（只读），
    再按 pitch 符号决定是否翻行。见模块 docstring「坑」。
    """
    rows, width = int(bm.rows), int(bm.width)
    if rows == 0 or width == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    if int(bm.pixel_mode) != _GRAY:
        raise RuntimeError(
            f"非预期 pixel_mode={int(bm.pixel_mode)}（期望 GRAY={_GRAY}）——"
            "本模块只用 FT_RENDER_MODE_NORMAL 8-bit 灰阶")
    pitch = int(bm.pitch)
    stride = abs(pitch)
    if stride < width:
        raise RuntimeError(f"pitch 异常：|pitch|={stride} < width={width}")
    ptr = bm._FT_Bitmap.buffer          # freetype-py 只读访问内部 C 结构
    if not ptr:
        raise RuntimeError(f"位图 buffer 为空但 rows={rows} width={width}")
    raw = ctypes.string_at(ptr, rows * stride)
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(rows, stride)[:, :width]
    if pitch < 0:                        # 底朝上存储 → 翻成 top-down
        arr = arr[::-1, :]
    return np.ascontiguousarray(arr)


def _decode_name(platform_id: int, raw: bytes) -> str:
    """name 表原始字节 → str：平台 0/3 是 UTF-16BE，平台 1 是 Mac Roman。"""
    if platform_id in (0, 3):
        return raw.decode("utf-16-be", "replace")
    if platform_id == 1:
        return raw.decode("mac_roman", "replace")
    return raw.decode("latin-1", "replace")


def _pick_sfnt_name(face, name_ids: tuple[int, ...] = (16, 1)) -> str | None:
    """按 name 表取族名：nameID 16（typographic family）优先，退 nameID 1（family）。

    平台优先级（逐级退让，每级内语言优先 0x409 英文、再按 language id 升序）：
    Windows(3,1) → Mac(1,0) → Unicode(0,*) → Windows 其它(3,*)。
    name 表缺失/无匹配 → None。
    """
    try:
        count = int(face.sfnt_name_count)
    except Exception:
        return None
    records = []
    for i in range(count):
        try:
            records.append(face.get_sfnt_name(i))
        except Exception:
            continue
    selectors = (
        lambda r: r.platform_id == 3 and r.encoding_id == 1,
        lambda r: r.platform_id == 1 and r.encoding_id == 0,
        lambda r: r.platform_id == 0,
        lambda r: r.platform_id == 3,
    )
    for name_id in name_ids:
        for pick in selectors:
            cands = [r for r in records if int(r.name_id) == name_id and pick(r)]
            if not cands:
                continue
            cands.sort(key=lambda r: (int(r.language_id) != 0x409,
                                      int(r.language_id), int(r.platform_id),
                                      int(r.encoding_id)))
            text = _decode_name(int(cands[0].platform_id),
                                bytes(cands[0].string)).strip()
            if text:
                return text
    return None


def _resolve_family(face) -> str:
    """首选族名：name 表 nameID 16 → 1；再退 FreeType 的 family_name；最后空串。"""
    text = _pick_sfnt_name(face)
    if text:
        return text
    raw = face.family_name
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace").strip()
    return str(raw or "").strip()


@fitted(kind="calibration", closed=True)
class UnhintedFace:
    """单个字体文件 @ ppem 的 unhinted 栅格化句柄（face index 固定 0）。

    构造即开 face + 设像素尺寸；**用完 close()**（或由 get_face 的进程级 memo 持有）。
    同一实例可反复 ``glyph()``（每次 load+render 覆盖槽状态）；``shear_xy`` 改变时
    自动重设 FT transform，0 表示复位为不变换。
    """

    def __init__(self, font_path: str | Path, ppem: int):
        path = Path(font_path)
        if not path.is_file():
            raise FileNotFoundError(f"字体文件不存在：{path}")
        ppem = int(ppem)
        if ppem <= 0:
            raise ValueError(f"ppem 必须为正整数（收到 {ppem}）")
        self.path: Path = path
        self.ppem: int = ppem
        self.sha256: str = _sha256_file(path)
        self._face = freetype.Face(str(path), 0)
        self._face.set_pixel_sizes(0, self.ppem)
        self.family: str = _resolve_family(self._face)
        self._closed = False
        self._shear_xy: int | None = None
        self._memo_key: tuple | None = None
        self._set_shear(0)               # 显式钉恒等变换（不依赖 FT 默认态）

    # -- 生命周期 -----------------------------------------------------------
    @property
    def closed(self) -> bool:
        return self._closed

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError(f"UnhintedFace 已 close()：{self.path}@{self.ppem}")

    def close(self) -> None:
        """释放 FT_Face（幂等）；若本实例在 get_face memo 里，同时摘除。"""
        if self._closed:
            return
        self._closed = True
        face, self._face = self._face, None
        if face is not None:
            ft_face = getattr(face, "_FT_Face", None)
            if ft_face is not None:
                try:
                    freetype.FT_Done_Face(ft_face)
                finally:
                    face._FT_Face = None    # 防 __del__ 二次 FT_Done_Face
        key = self._memo_key
        if key is not None and _FACES.get(key) is self:
            del _FACES[key]

    # -- 查询 ---------------------------------------------------------------
    def has_glyph(self, ch: str) -> bool:
        """该字体 cmap 是否覆盖单字符 ``ch``（glyph index 0 = 不覆盖）。"""
        self._check_open()
        return int(self._face.get_char_index(_codepoint(ch))) != 0

    def advance_26_6(self, ch: str) -> int:
        """单字符的水平 advance（FT 26.6 定点，**无变换**口径）。

        引擎布局用的就是这个值再 ``(x+32)>>6``；斜切不改 x advance（xy 只乘 y 分量）。
        字体无此字 → LookupError。
        """
        self._check_open()
        gindex = self._glyph_index(ch)
        self._set_shear(0)
        self._face.load_glyph(gindex, FT_LOAD_NO_HINTING)
        return int(self._face.glyph.advance.x)

    def glyph(self, ch: str, shear_xy: int = 0) -> Glyph:
        """栅格化单字符。``shear_xy``：0=不变换；0x4000=引擎斜体 s=0.25（16.16；
        引擎读值=UnityPlayer.dll!0xD9F8E0 立即数 ``mov eax,0x4000``，2026-11-01）。

        字体无此字 → LookupError（先 has_glyph）。空字形返回 (0,0) 位图 + 照常 advance。
        """
        self._check_open()
        gindex = self._glyph_index(ch)
        self._set_shear(shear_xy)
        self._face.load_glyph(gindex, FT_LOAD_NO_HINTING)
        slot = self._face.glyph
        slot.render(freetype.FT_RENDER_MODE_NORMAL)   # 必须 render 后再读位图
        bm = slot.bitmap
        bitmap = _bitmap_array(bm)
        adv26 = int(slot.advance.x)
        return Glyph(bitmap=bitmap, width=int(bm.width), rows=int(bm.rows),
                     advance_26_6=adv26, advance_px=advance_to_px(adv26),
                     left=int(slot.bitmap_left), top=int(slot.bitmap_top))

    # -- 内部 ---------------------------------------------------------------
    def _glyph_index(self, ch: str) -> int:
        cp = _codepoint(ch)
        gindex = int(self._face.get_char_index(cp))
        if gindex == 0:
            raise LookupError(
                f"字体无此字：ch={ch!r} U+{cp:04X}（{self.path.name}@{self.ppem}）——"
                "缺字兜底属供给策略（B 号），本模块不静默出 tofu")
        return gindex

    def _set_shear(self, shear_xy: int) -> None:
        shear_xy = int(shear_xy)
        if shear_xy == self._shear_xy:
            return
        matrix = freetype.Matrix(_ONE, shear_xy, 0, _ONE)   # x' = x + s*y
        delta = freetype.Vector(0, 0)
        self._face.set_transform(matrix, delta)   # FT 内部拷贝矩阵，无需持引用
        self._shear_xy = shear_xy


# ---------------------------------------------------------------------------
# 进程级 face memo（只缓存 face，不缓存位图）
# ---------------------------------------------------------------------------

_FACES: dict[tuple, UnhintedFace] = {}


def _memo_key(path: Path, ppem: int) -> tuple:
    """memo 键 = (realpath, mtime_ns, size, ppem)：字体文件一改即失配重建。"""
    st = os.stat(path)
    return (os.path.realpath(path), int(st.st_mtime_ns), int(st.st_size), int(ppem))


@fitted(kind="calibration", closed=True)
def get_face(font_path: str | Path, ppem: int) -> UnhintedFace:
    """取进程级 memo 的 UnhintedFace（键 = (realpath, mtime_ns, size, ppem)）。

    * 同键复用同一实例（**调用方不要 close 借来的共享实例**，除非确定没别人用；
      close 后 memo 自动摘除，下次 get_face 重开）；
    * 同一文件同一 ppem 但 mtime/size 变了（字体被替换）→ 旧 face 先 close 再新建；
    * 路径不存在 → FileNotFoundError；ppem<=0 → ValueError（与构造器同口径）。
    """
    path = Path(font_path)
    key = _memo_key(path, int(ppem))          # ppem<=0 由构造器统一校验
    hit = _FACES.get(key)
    if hit is not None:
        return hit
    for old_key, old in list(_FACES.items()):
        if old_key[0] == key[0] and old_key[3] == key[3]:
            old.close()                        # 字体文件已变：旧 face 退役
    face = UnhintedFace(path, int(ppem))
    face._memo_key = key
    _FACES[key] = face
    return face
