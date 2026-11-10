"""通用 UberText 引擎文字路径——字形供给 v3.1（unhinted 驱动单路）。

历史账：本模块原名「字体图集路径」（text-rdc-align 2026-10-18 A 段正典化），供给=
data/fonts_zhcn/atlas/ 采集快照（AlphaTool -dumpfonts 链）。v3 改成「按需 hinted FT」
（PIL 的 hinted 字体对象）——那条路**永远 hinted**，与引擎（FT_LOAD_NO_HINTING，见
docs/notes/text-rendering-pipeline.md §字形栅格化口径）差 8–14% 位级，是 v3.1 换轨的
直接动因。v3.1（2026-10-22）供给换成**驱动单路**：`ft_unhinted`（FT 2.13.x +
NO_HINTING）出位图/advance/bearings，格框留白 p 读资产 `m_CharacterPadding`。
采集快照（快照锚依赖 data/fonts_zhcn 语料，产品无此素材）整层退**实验侧对拍**，
其两个对拍入口函数不进本产品。

  * 供给=glyph_quad（下）：全角色单路——无白名单、无快照分支、无逐字 legacy 像素回退。
    缺字（cmap 前置判定）由 uber_text.FontMetrics 走 glyph_supply 的引擎两级回退，
    位图+advance 与该回退 face 同源。
  * 格框 = `(rows+2p, width+2p)`，**p = 资产 `m_CharacterPadding`**（GLEI=4、BGO=2；
    未知 fontObjectName = 响亮 KeyError，禁写死）。摆位 `vert=(left−p, top+p, w+2p,
    −(h+2p))`（= 引擎 CharacterInfo.vert 语义）。
  * 有描边角色 = 目标分辨率 9-tap（引擎 Hidden/TextOutline_Unlit：4 对角 ×0.6r +
    4 轴向 ×1.0r + center，α=saturate(Σ9)，RGB=lerp(outline, fill, center)）。
  * 无描边角色 = 单次 center 双线性（引擎 desc PS：α=字形α×顶点α，RGB=顶点色）。
  * 无描边角色的 `<b>` = **独立第二绘制**（引擎 BOLD 材质子网格，UB UpdateTexelSize
    :2031-2053 SetBoldOffset(texelSize×m_BoldSize)；`Hidden/Text_Bold` 的 PS 抓帧
    反汇编=8 次 tap ×0.23 求和，偏移 ±B 轴向 + ±0.6B 对角，B=m_BoldSize 字体 px）。
    正常字形单次 center；粗体字形**不在**正常 pass 绘制，只在第二 pass 以 8-tap
    求和 α 叠一次（source-over）——与引擎「独立子网格 + Text_Bold 材质」同构。
    证据=docs/notes/text-rendering-pipeline.md「引擎图集文字路径」（抓帧 129851 ev745
    的 ps_4_0 反汇编与 UberText.cs:UberText.UpdateTexelSize 逐项对账）。
  * `<i>` = 引擎**合成斜切** s=0.25（`FT_Set_Transform(xx=1.0, xy=0x4000)`；
    **读值**=引擎原生立即数 xy=0x4000（`UnityPlayer.dll!0xD9F8E0` 斜体分支，
    2026-11-01 反汇编直读；账=正典「字形栅格化口径」斜体行）；
    BGO@40 Italic 682/682 位级实证；679 字拟合 0.24986±0.00051 与读值相容
    0.28σ）——不是字体真斜体、也不是 FT 自带 12° Oblique（IoU 0.846）。
    经 `styles` 位传入 glyph_quad。

摆位语义与正典 `layout_text` 一致：x0 = pen + minX·k + phase_x，
y0 = baseline − maxY·k + phase_y；k = layout["k"] × local_scale × scene.s
（目标像素/字体像素）。相位单位=卡面 px，不乘 k。基线取 `ascent_round`；
`float_ascent=True` 取浮点 `ascent_f`（desc 正典：引擎基线来自浮点 ascent，
FT 整型 round 的 0.21875 字体 px 差在卡面 ≈0.175 px，是 desc 主残差）。
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image
from scipy import ndimage as _ndi

from eidolon.core.render._provenance import fitted  # noqa: F401 （族默认）

# 实验 A/B（2026-10-24 trinket 文字零残差）：逐 glyph 8-bit 合成（引擎每个 text draw
# 直接写 8-bit RT；我方现为 float 层最后一次性量化）。False=现役。
_PLANE_PER_GLYPH_8 = False
# 实验捕获（2026-10-24）：保留 8-bit 出口前的 float 层，供 float-to-float 对照。
_FLOAT_CAPTURE = False
_FLOAT_LAYERS: list = []
_BOLD_TAP_WEIGHT = 0.23  # Hidden/Text_Bold PS：8 次 tap 求和后 ×0.23（抓帧 ps_4_0 反汇编）
_BOLD_DIAG = 0.6         # 对角 tap 半径 = 0.6×bold 偏移（同上反汇编）
# name RT 内容 pass 的引擎 view 平移（`UberTextRenderToTexture.SetupMatrices:375-400`：
# `num=-3000`、`num2=0` ⇒ x 平移 −3000、y 平移 +3000）。这是**代码常数**不是逐卡常数：
# 它只在 float32 位置链里起作用（见 `render_rt_content(vs_f32=...)`），物理上被 VP 平移
# `−s·translate` 精确抵消，唯一残留是 |world|≈3000 上的 float32 ulp 量化。
_VS_F32_TRANSLATE = (-3000.0, 3000.0)


def _vs_f32_axis(px, rt, s, translate):
    """引擎 VS 的**单轴 float32 位置链**：RT px → clip(float32) → RT px。

    逐指令复刻 `Hidden/TextOutline_Unlit` vs_4_0（抓帧 DXBC：mul/mad/add，见
    findings/name-rtt-canon.md §17/§18）：
        world = local + translate            (cb1[3]，float32)
        clip  = world·s + (−s·translate)     (cb0[79..82] 的对应列，float32)
        px    = (0.5·clip + 0.5)·rt
    `s` = 该轴的投影缩放（x: +2/m_Width，y: **−**2/m_Height；抓帧 cb0[79].x/cb0[80].y
    的符号逐帧实测），`translate` = 该轴的 view 平移（x −3000、y +3000）。

    **为什么需要它**：`local` 量级 ~1、`translate` 3000 ⇒ `world` 的 float32 ulp 是
    2.4e-4；与 VP 平移相消后这个 ulp 原样留在 clip 上，等于每个顶点在 RT 上有
    ~0.01–0.03 px 的**量化位移**（逐顶点不同，不是逐帧常数）。float64 精确 VP 没有它，
    UV 相位差 0.01–0.03 texel ⇒ RT 内容 αMAE 0.43–0.66（第十三轮实测）。
    """
    f32 = np.float32
    ndc = f32(np.float64(px) / float(rt) * 2.0 - 1.0)
    local = f32(np.float64(ndc) / float(s))
    world = f32(np.float64(local) + float(translate))
    vp_t = f32(-(np.float64(s) * float(translate)))     # = fl(±s·3000)，抓帧 cb0[82] 同值
    clip = f32(np.float64(f32(np.float64(world) * float(s))) + np.float64(vp_t))
    return float((np.float64(f32(np.float64(clip) * 0.5 + 0.5))) * float(rt))


def _vs_f32_quad(x0, y0, w, h, rt_w, rt_h, sx, sy):
    """把一个 glyph quad 的四角过 float32 VS 链，返回量化后的 (x0, y0, kx, ky) 等价量。

    轴对齐 quad ⇒ 只需左右/上下两条边；返回 (x0', y0', w', h')（RT px，float64 承载
    float32 结果）。`sx`/`sy` 必须是 float32 值（由 m_Width/m_Height 算出）。"""
    tx, ty = _VS_F32_TRANSLATE
    xl = _vs_f32_axis(x0, rt_w, sx, tx)
    xr = _vs_f32_axis(x0 + w, rt_w, sx, tx)
    yt = _vs_f32_axis(y0, rt_h, sy, ty)
    yb = _vs_f32_axis(y0 + h, rt_h, sy, ty)
    return xl, yt, (xr - xl), (yb - yt)


# ---------------------------------------------------------------------------
# 字形供给 v3.1（unhinted 驱动单路；判据/对拍账=docs/notes/text-rendering-pipeline.md
# §字形栅格化口径 与 2026-10-22-font-supply-unhinted 实验）
# ---------------------------------------------------------------------------

def _font_pad(font: str) -> int:
    """该 Font 对象的图集格框留白 p = 资产 `m_CharacterPadding`（**禁写死**）。

    GLEI00M_t_Outline=4、BlizzardGlobal=2（值源=recipes.text.font_asset_params，
    游戏 assets 的 Unity Font 对象直读；原 data 档只作对拍参照，生产零读）；
    未知 fontObjectName → 响亮 KeyError（不猜默认值）。"""
    from eidolon.core.render.text import glyph_supply as _gs
    return _gs.character_padding(font)


def _fm_quad(fm, ch: str, font: str | None = None, style: str | None = None) -> tuple:
    """驱动字形 quad（ft_unhinted 单源）→ `(tex, minX, maxY, advance)`。

    `font` = Font 对象名（格框 p 的资产键；None = 用 `fm.font_name`——FontMetrics
    已带该名，诊断直调兼容）。`style=="Italic"` → 引擎合成斜切 s=0.25（xy=0x4000）。
    格框 = `(rows+2p, width+2p)`，摆位 `vert=(left−p, top+p, w+2p, −(h+2p))`；位图
    补 p 圈零边（引擎 GPU 双线性在格边界与零邻混合，紧墨位图无外延会在顶底边缘丢
    半像素 AA）。"""
    key = font if font else getattr(fm, "font_name", "")
    p = _font_pad(key)
    shear = 0x4000 if str(style or "") == "Italic" else 0
    info, arr = fm.char_info(ch, shear)
    h, w = arr.shape
    tex = np.zeros((h + 2 * p, w + 2 * p), np.float64)
    if h and w:
        tex[p:p + h, p:p + w] = arr.astype(np.float64) / 255.0
    return (tex, float(info.minX - p), float(info.maxY + p), float(info.advance))


@fitted(kind="artifact")
def glyph_quad(fm, font: str, ch: str, style: str | None = None) -> tuple:
    """字形供给 v3.1 单一入口（布局与栅格化同经 `fm.char_info`——一次定案同判）。

    返回 (tex float 0..1 正立行主序, minX, maxY, advance)。**全角色单路**：
    ft_unhinted（FT_LOAD_NO_HINTING）位图 + 驱动 advance；`style=="Italic"` 走引擎
    合成斜切；缺字（cmap 前置判定）已由 char_info 走 glyph_supply 两级回退并记
    响亮事件。无快照分支、无逐字 legacy 像素回退（v3.1 换轨）。"""
    return _fm_quad(fm, ch, font=font, style=style)


def _composite(dst: np.ndarray, src: np.ndarray, x: int, y: int) -> None:
    """float RGBA source-over（与 uber_text._composite 同式；本模块零反向依赖）。"""
    h, w = src.shape[:2]
    H, W = dst.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, W), min(y + h, H)
    if x0 >= x1 or y0 >= y1:
        return
    sub = src[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    sa = sub[..., 3:4]
    da = d[..., 3:4]
    out_a = sa + da * (1 - sa)
    safe = np.where(out_a > 1e-6, out_a, 1.0)
    d[..., :3] = (sub[..., :3] * sa + d[..., :3] * da * (1 - sa)) / safe
    d[..., 3:4] = out_a


def _unorm_round(layer: np.ndarray) -> None:
    """整张 RT 按 8-bit UNORM round-to-nearest 写回（模拟每次 draw 的 RT 写）。"""
    layer[...] = np.rint(np.clip(layer, 0.0, 1.0) * 255.0) / 255.0


def _tap_quant(v: np.ndarray, mode: str) -> np.ndarray:
    """单个双线性 tap 结果的定点化（A/B：GPU 的 UNORM8 过滤精度）。

    D3D11 对 UNORM 格式的过滤精度是 **implementation-defined**（规范给出允许误差，
    不要求 float 累加）：若硬件把每次过滤结果 round 回 8-bit（n/255）再进 shader，
    9-tap 求和会带 ~0.5/255×9 的偏置。`mode`：""=不量化；"u8r"=round(n/255)；
    "u8t"=trunc(n/255)；"u8_256r"=round(n/256)（1/256 栅格）。"""
    if not mode:
        return v
    if mode == "u8r":
        return np.rint(v * 255.0) / 255.0
    if mode == "u8t":
        return np.floor(v * 255.0) / 255.0
    if mode == "u8_256r":
        return np.rint(v * 256.0) / 256.0
    raise ValueError(mode)


def _sample_bilinear(tex, ii, jj, subtexel_bits: int = 0,
                     subtexel_round: str = "nearest", lerp_quant: str = ""):
    """图集双线性采样；`subtexel_bits>0` → 采样坐标小数按 2^-bits 定点量化。

    D3D11 采样器对双线性权重用定点子纹素精度（规范见 docs/notes/
    text-rendering-pipeline.md「D3D11 采样语义」节；8-bit = 1/256 权重栅格），
    GPU 的 `frac(uv)` 因此不是任意实数。`subtexel_bits=0`（默认）= 现役 float
    采样，逐位不变；A/B 用 8 复刻硬件权重栅格（`subtexel_round`=硬件转换的
    取整方向：`nearest`/`trunc`，驱动实现差异按实测择一）。

    `lerp_quant` → 每次一维 lerp 的结果按 UNORM8 定点化后再进下一级（A/B：
    硬件双线性在定点累加器里算，中间结果精度有限；""=现役 float）。"""
    if subtexel_bits:
        q = float(1 << int(subtexel_bits))
        def _quant(c):
            f = np.floor(c)
            frac = c - f
            frac = (np.floor(frac * q + 0.5) if subtexel_round == "nearest"
                    else np.floor(frac * q))
            return f + frac / q
        ii, jj = _quant(ii), _quant(jj)
    if not lerp_quant:
        return _ndi.map_coordinates(tex, [ii, jj], order=1, mode="constant",
                                    cval=0.0, prefilter=False)
    # 注意参数约定与 `map_coordinates(tex, [ii, jj])` 一致：ii=行(y)、jj=列(x)。
    h, w = tex.shape
    ok = (jj >= 0) & (jj <= w - 1) & (ii >= 0) & (ii <= h - 1)
    j0 = np.clip(np.floor(ii).astype(np.int64), 0, h - 1)
    i0 = np.clip(np.floor(jj).astype(np.int64), 0, w - 1)
    j1 = np.clip(j0 + 1, 0, h - 1)
    i1 = np.clip(i0 + 1, 0, w - 1)
    fy = ii - j0
    fx = jj - i0

    def q8(v):
        if lerp_quant == "u8r":
            return np.rint(v * 255.0) / 255.0
        if lerp_quant == "u8t":
            return np.floor(v * 255.0) / 255.0
        return np.rint(v * 256.0) / 256.0       # "u256r"

    h0 = q8(tex[j0, i0] * (1 - fx) + tex[j0, i1] * fx)
    h1 = q8(tex[j1, i0] * (1 - fx) + tex[j1, i1] * fx)
    out = q8(h0 * (1 - fy) + h1 * fy)
    return np.where(ok, out, 0.0)


def _taps(r: float) -> tuple:
    """描边 tap 偏移（字体像素；r=描边半径 texel）——引擎常量序，不可换序。

    4 轴向（±r）+ 4 对角（±0.6r）= VS 给出的 8 个 UV 偏移。引擎 PS 还有**第 9 次
    sample = center**（`Hidden/TextOutline_Unlit` 反汇编：`add_sat` 前共 9 次 sample
    求和、RGB 取最后那次 center；129851 ev769/ev799）。该 center 在字形笔画 ≥8 字体 px
    （数字/race/desc）时被 9-tap 和饱和吞掉，故**平面图集路径**（数字/desc/race/plate）沿用
    8 外 tap（cost 桥按此逐位验收）；name RT 内容路径与 race/plate 平面路径用
    `center_tap=True` 显式补第 9 次 sample（引擎同款，2026-10-18 第四/五/八轮落地，见
    `render_rt_content` 与 findings §13 / plate-atlas-canon §3）。"""
    return ((r, 0.0), (-r, 0.0), (0.0, r), (0.0, -r),
            (0.6 * r, 0.6 * r), (-0.6 * r, 0.6 * r),
            (0.6 * r, -0.6 * r), (-0.6 * r, -0.6 * r))


def _rot_pad(tw: float, th: float, k: float, deg: float) -> int:
    """旋转后的包围盒外扩（像素）：glyph 尺寸 × |sin θ| 的保守上界。"""
    if abs(deg) < 1e-9:
        return 0
    return int(math.ceil(max(tw, th) * k * abs(math.sin(math.radians(deg))))) + 1


def _rot_coords(xx: np.ndarray, yy: np.ndarray, cx: float, cy: float,
                deg: float) -> tuple[np.ndarray, np.ndarray]:
    """目标像素坐标绕 (cx,cy) 逆旋转 deg 度（deg=节点面内旋转）。

    文字 mesh 的每个 quad 由节点世界矩阵旋转（引擎 cb 矩阵的 x-z 面内旋转分量），
    采样必须在字形局部坐标里做——先把目标像素逆变换回未旋转的文字平面，再算
    (u,v) 与 9-tap，等价于引擎「旋转后的 mesh 采样图集」，且只有一次重采样。"""
    if abs(deg) < 1e-9:
        return xx, yy
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    dx, dy = xx - cx, yy - cy
    return cx + c * dx + s * dy, cy - s * dx + c * dy


@fitted(kind="artifact")
def render_atlas_text(layout: dict, fm, ns, scene, fill: tuple,
                      outline: dict | None, phase: tuple[float, float],
                      font: str, node_px_offset: tuple[float, float] = (0.0, 0.0),
                      rotation_deg: float = 0.0, float_ascent: bool = False,
                      bold_px: float = 0.0, bold_taps: str = "shader8",
                      quantize: str = "trunc", center_tap: bool = False):
    """有描边文字层（canvas 尺寸 straight RGBA）；字形供给=glyph_quad（v3 单入口）。

    layout/fm/ns/scene 与 uber_text.render_text 同形；font=FontDef 的
    `_font_object_name`（供给策略/快照键）。rotation_deg=节点面内旋转（度，绕节点
    中心；引擎 mesh 旋转的离线等价）。float_ascent=基线用浮点 ascent_f（desc/race/
    plate 正典；数字角色保持 ascent_round 逐位行为）。quantize=浮点层→8-bit 的取整：
    引擎 RT 写入=GPU float→UNORM round-to-nearest（desc 正典用 "round"；数字角色/
    描边支历史态为 "trunc"——cost 桥按 trunc 逐位验收）。**末级量化 round 化
    （quant-ab 2026-11-05）后，本参数失去区分作用**：三处出口（本函数、
    `render_rt_content`、无描边 center 支）统一在出口 `np.rint`，trunc 角色的
    差异只剩历史账；参数保留（签名兼容），不再改变出口取整。
    center_tap=补引擎 PS 的第 9 次 sample（center，8 外 tap 之后等权相加再 saturate）：
    数字角色保持 8-tap（cost 桥逐位口径），`_CENTER_TAP_ROLES` 只开 race/race_multi/
    plate。
    （v3 退役：`fallback` 逐字回退闭包与 `allow_flipped` 整层回退删除——缺字/advance
    分歧由 glyph_quad 显式判定 + 响亮事件，快照翻转字形=存储形态非回退条件。）"""
    if outline is None:
        return _render_atlas_text_center(
            layout, fm, ns, scene, fill, phase, font, node_px_offset,
            rotation_deg=rotation_deg, float_ascent=float_ascent,
            bold_px=bold_px, bold_taps=bold_taps, quantize=quantize)
    fill_rgb = np.array(fill[:3], dtype=np.float64)
    ol_rgb = np.array(outline["color"][:3], dtype=np.float64)
    r = float(outline["r"])
    W, H = scene.canvas
    k = layout["k"] * ns.local_scale * scene.s
    ns_scale_s = ns.local_scale * scene.s
    cx = scene.project(*ns.world_pos[::2])[0] + node_px_offset[0]
    cy = scene.project(*ns.world_pos[::2])[1] + node_px_offset[1]
    pitch_c = layout["pitch"] * ns_scale_s
    box_h_c = layout["box_h"] * ns_scale_s
    ascent_c = (fm.ascent_f if float_ascent else fm.ascent_round) * k
    taps = _taps(r)
    layer = np.zeros((H, W, 4), np.float64)
    for li, row in enumerate(layout["lines"]):
        pen0 = cx - layout["line_widths"][li] * ns_scale_s / 2.0
        baseline = cy - box_h_c / 2.0 + li * pitch_c + ascent_c
        for g in row:
            pen = pen0 + g["pen_x"] * ns_scale_s
            tex, minx, maxy, _adv = glyph_quad(fm, font, g["ch"])
            th, tw = tex.shape
            x0 = pen + minx * k + phase[0]
            y0 = baseline - maxy * k + phase[1]
            pad = int(np.ceil(r * k + 3)) + _rot_pad(tw, th, k, rotation_deg)
            bx0 = max(0, int(np.floor(x0 - pad)))
            bx1 = min(W, int(np.ceil(x0 + tw * k + pad)))
            by0 = max(0, int(np.floor(y0 - pad)))
            by1 = min(H, int(np.ceil(y0 + th * k + pad)))
            if bx0 >= bx1 or by0 >= by1:
                continue
            yy, xx = np.mgrid[by0:by1, bx0:bx1]
            xx, yy = xx + 0.5, yy + 0.5
            xx, yy = _rot_coords(xx, yy, cx, cy, rotation_deg)
            u, v = (xx - x0) / k, (yy - y0) / k
            jj, ii = u - 0.5, v - 0.5
            acc = np.zeros_like(jj)
            for tx, ty in taps:
                acc += _ndi.map_coordinates(tex, [ii + ty, jj + tx], order=1,
                                            mode="constant", cval=0.0, prefilter=False)
            center = _ndi.map_coordinates(tex, [ii, jj], order=1,
                                          mode="constant", cval=0.0, prefilter=False)
            if center_tap:           # 引擎 PS 第 9 次 sample（center，等权求和后 saturate）
                acc = acc + center
            a = np.clip(acc, 0.0, 1.0)
            c = np.clip(center, 0.0, 1.0)
            rgb = ol_rgb[None, None, :] * (1 - c[..., None]) \
                + fill_rgb[None, None, :] * c[..., None]
            src = np.zeros((by1 - by0, bx1 - bx0, 4), np.float64)
            src[..., :3] = rgb
            src[..., 3] = a
            _composite(layer, src, bx0, by0)
            if _PLANE_PER_GLYPH_8:
                layer[...] = np.rint(np.clip(layer, 0.0, 1.0) * 255.0) / 255.0
    if _FLOAT_CAPTURE:
        _FLOAT_LAYERS.append(np.array(layer, dtype=np.float64, copy=True))
    # 末级量化 round 化（quant-ab 2026-11-05）：描边支出口 trunc→round-to-nearest
    # （引擎 RT 写入=UNORM round-to-nearest，同 tex_atlas docstring 账）。
    return Image.fromarray(np.rint(np.clip(layer, 0, 1) * 255).astype(np.uint8), "RGBA")


@fitted(kind="artifact")
def render_rt_content(layout: dict, fm, font: str, fill: tuple, outline: dict,
                      rt_w: int, rt_h: int, qx: float, qy: float,
                      float_ascent: bool = True, quantize: str = "round",
                      center_tap: bool = False, alpha_blend: str = "srcover",
                      subtexel_bits: int = 0, subtexel_round: str = "nearest",
                      per_glyph_round: bool = False, quad_clip: bool = False,
                      phase_rt: tuple = (0.0, 0.0), glyph_log: list | None = None,
                      tap_quant: str = "", lerp_quant: str = "",
                      vs_f32: tuple | None = None):
    """name 曲面 RTT 的 **RT 内容**（UB SetupRenderToTexture/SetupCamera:2268-2277）。

    引擎语义（2026-10-18 抓帧实证；过程账在 docs/notes/text-rendering-pipeline.md
    的「name 曲面 RTT」节，待统筹晋升）：
      * clear = m_OutlineColor（RGB 保留、A=0）——UberTextRenderToTexture.cs:UberTextRenderToTexture.SetTargetClearColor `SetTargetClearColor`
        把 outline 色写进 clear，UberTextRenderToTexture.cs:UberTextRenderToTexture.SetTargetClearColor 显式置 A=0。
        于是 RT 内「描边色的 RGB 无处不在」，合成阶段的 α 扩张把这块 RGB 显影成描边。
      * 字形 = `Hidden/TextOutline_Unlit`（与平面路径同 shader）：α=saturate(Σ9)、
        RGB=lerp(outline, fill, center)。RT 内**有**描边（旧账「RT 内无描边」被
        caps4 RT 纹理反证：α=255 而 RGB=outline 色的像素 2440/3047 个）。
      * 缩放 qx/qy = RT px / 局部单位（UberTextRenderToTexture.cs:UberTextRenderToTexture.SetupMatrices 正交相机覆盖 m_Width×m_Height）；
        kx=layout.k×qx、ky=layout.k×qy（非均匀：RT 由 int 截断，纵横比与盒略有差）。
      * `center_tap=True` → 补引擎 PS 的第 9 次 sample（center，`add_sat` 前共 9 次
        sample；反汇编=cost-glyph-bitwise 实验 output/TextOutline_Unlit_1_ps.asm:35-53）。
        8 外 tap + center，等权求和后 saturate。
      * `alpha_blend="gpu"` → 按 pass blend `SrcAlpha/OneMinusSrcAlpha`
        （m_State src=5/dst=10，出处=cost-glyph-bitwise 实验 NOTES.md:40；
        docs/notes/text-rendering-pipeline.md:56）逐 glyph 混合。固定功能混合对
        **α 通道同样**用 srcAlpha 因子：clear A=0 ⇒ out.a = s²（s=shader α），
        out.rgb = rgb·s + dst.rgb·(1−s)；`srcover` 是旧 straight source-over 近似
        （out.a=s，fringe 偏高 ~0.90× 的等效半径补偿来源）。
      * `subtexel_bits=8` → 双线性采样坐标小数按 1/256 定点量化（复刻 D3D11 采样器
        子纹素精度；见 `_sample_bilinear` 与 docs/notes/text-rendering-pipeline.md）。
      * `per_glyph_round=True` → **每个 glyph 混合后**把整张 RT 量化回 8-bit UNORM
        （引擎 4 个 glyph 是 4 个 draw，每次写回都过 8-bit RT；我方默认是 float 累加
        后整张 round 一次）。`quad_clip=True` → 只写 quad 覆盖的像素中心（其余不着色）。
      * `phase_rt` → 逐 glyph 位置的整体 RT px 平移（A/B 相位探针，不逐卡拟合）。
      * `vs_f32=(sx, sy)` → 把每个 glyph quad 的角点过**引擎 VS 的 float32 位置链**
        （`_vs_f32_quad`：±3000 的 view/VP 平移相消后留下 float32 ulp 量化），
        sx=+2/m_Width、sy=−2/m_Height（float32）。默认 None=旧行为（float64 精确 VP）。
        机制与判据见 findings/name-rtt-canon.md §18。
      * `glyph_log` → 逐 glyph 记录 quad（A/B/分解用，默认 None）。
    返回 (rt_h, rt_w, 4) uint8。字形供给=glyph_quad（v3：缺字→cmap 判定显式回退，
    旧「图集缺失→None/逐字 FreeType 闭包」退役）。"""
    fill_rgb = np.array(fill[:3], dtype=np.float64)
    ol_rgb = np.array(outline["color"][:3], dtype=np.float64)
    taps = _taps(float(outline["r"]))   # A/B：tap 语义见 findings/name-rtt-canon.md §11
    kx = layout["k"] * qx
    ky = layout["k"] * qy
    layer = np.zeros((rt_h, rt_w, 4), np.float64)
    layer[..., :3] = ol_rgb                      # clear = m_OutlineColor (A=0)
    if per_glyph_round:
        # 引擎 RT=ARGB32：clear 也是一次 8-bit 写回（UNORM round-to-nearest）。
        _unorm_round(layer)
    ascent = (fm.ascent_f if float_ascent else fm.ascent_round)
    cx, cy = rt_w / 2.0, rt_h / 2.0
    for li, row in enumerate(layout["lines"]):
        pen0 = cx - layout["line_widths"][li] * qx / 2.0
        baseline = cy - layout["box_h"] * qy / 2.0 + li * layout["pitch"] * qy + ascent * ky
        for g in row:
            pen = pen0 + g["pen_x"] * qx
            tex, minx, maxy, _adv = glyph_quad(fm, font, g["ch"])
            th, tw = tex.shape
            x0 = pen + minx * kx + phase_rt[0]
            y0 = baseline - maxy * ky + phase_rt[1]
            gw, gh = tw * kx, th * ky
            if vs_f32 is not None:
                # 引擎 VS 的 float32 位置链（±3000 平移相消后的 ulp 量化，逐顶点）
                x0, y0, gw, gh = _vs_f32_quad(x0, y0, gw, gh, rt_w, rt_h,
                                              vs_f32[0], vs_f32[1])
                kx_q, ky_q = gw / tw, gh / th
            else:
                kx_q, ky_q = kx, ky
            if glyph_log is not None:
                glyph_log.append({"ch": g["ch"], "li": li, "pen": float(pen),
                                  "x0": float(x0), "y0": float(y0),
                                  "w": float(gw), "h": float(gh),
                                  "bold": bool(g.get("bold"))})
            reach = max(max(abs(t[0]), abs(t[1])) for t in taps)
            bx0 = max(0, int(np.floor(x0 - reach * kx_q - 2)))
            bx1 = min(rt_w, int(np.ceil(x0 + gw + reach * kx_q + 2)))
            by0 = max(0, int(np.floor(y0 - reach * ky_q - 2)))
            by1 = min(rt_h, int(np.ceil(y0 + gh + reach * ky_q + 2)))
            if bx0 >= bx1 or by0 >= by1:
                continue
            yy, xx = np.mgrid[by0:by1, bx0:bx1]
            xx, yy = xx + 0.5, yy + 0.5
            jj, ii = (xx - x0) / kx_q - 0.5, (yy - y0) / ky_q - 0.5
            center = np.clip(_tap_quant(_sample_bilinear(tex, ii, jj, subtexel_bits,
                                                        subtexel_round, lerp_quant),
                                       tap_quant), 0.0, 1.0)
            acc = np.zeros_like(jj)
            for tx, ty in taps:
                acc += _tap_quant(_sample_bilinear(tex, ii + ty, jj + tx, subtexel_bits,
                                                   subtexel_round, lerp_quant), tap_quant)
            if center_tap:      # 引擎 PS 第 9 次 sample（center，add_sat 前等权求和）
                acc = acc + center
            a = np.clip(acc, 0.0, 1.0)
            c = center
            if quad_clip:
                # GPU 只为 quad 覆盖的像素中心跑 PS；其余像素不着色（α=0 → 混合恒等）。
                inside = ((xx >= x0) & (xx < x0 + gw)
                          & (yy >= y0) & (yy < y0 + gh))
                a = np.where(inside, a, 0.0)
                c = np.where(inside, c, 0.0)
            src = np.zeros((by1 - by0, bx1 - bx0, 4), np.float64)
            src[..., :3] = ol_rgb[None, None, :] * (1 - c[..., None]) \
                + fill_rgb[None, None, :] * c[..., None]
            src[..., 3] = a
            if alpha_blend == "gpu":
                # pass blend SrcAlpha/OneMinusSrcAlpha：α 通道也乘 srcAlpha ⇒ clear A=0
                # 时 out.a = s²；RGB = src.rgb·s + clear·(1−s)。
                d = layer[by0:by1, bx0:bx1]
                sa = a[..., None]
                out_a = sa * sa + d[..., 3:4] * (1 - sa)
                d[..., :3] = src[..., :3] * sa + d[..., :3] * (1 - sa)
                d[..., 3:4] = out_a
            elif alpha_blend == "gpu_a":
                # A/B 支：α 走引擎混合（s²），RGB 保留旧 straight source-over。
                d = layer[by0:by1, bx0:bx1]
                sa = a[..., None]
                da = d[..., 3:4]
                out_a = sa * sa + da * (1 - sa)
                safe = np.where(out_a > 1e-6, out_a, 1.0)
                d[..., :3] = (src[..., :3] * sa + d[..., :3] * da * (1 - sa)) / safe
                d[..., 3:4] = out_a
            else:
                _composite(layer, src, bx0, by0)
            if per_glyph_round:
                _unorm_round(layer)
    arr = np.clip(layer, 0, 1) * 255.0
    if quantize == "round":
        arr = np.rint(arr)
    # 末级量化 round 化（quant-ab 2026-11-05）：出口统一 round；quantize="round"
    # 支先前已 rint，此处幂等二饮。
    return np.rint(arr).astype(np.uint8)


def _bold_offsets(bold_px: float) -> tuple:
    """`Hidden/Text_Bold` 的 8 个 UV tap 偏移（字体 px）：±B 轴向 + ±0.6B 对角。

    抓帧证据=129851 desc bold draw（ev745，PS hash e72937e9-f0fa7fb4-cd43d52c-c03a6c9e）
    的 ps_4_0 反汇编：8 次 sample 由 VS 的 o2..o5 给出，偏移来自 cb2[2]
    = texelSize×m_BoldSize（cb2[2]=(1.25/256,1.25/512)，与 UB.Bold 的
    m_BoldSize=1.25 逐位吻合）；PS `sum(8 taps) × 0.23 × vertexAlpha`。"""
    d = _BOLD_DIAG * bold_px
    return ((bold_px, 0.0), (-bold_px, 0.0), (0.0, bold_px), (0.0, -bold_px),
            (d, d), (-d, d), (d, -d), (-d, -d))


def _paste_glyph(layer: np.ndarray, tex: np.ndarray, x0: float, y0: float, k: float,
                 W: int, H: int, deg: float, cx: float, cy: float,
                 fill_rgb: np.ndarray, taps: tuple | None = None,
                 weight: float = _BOLD_TAP_WEIGHT) -> None:
    """把字形（atlas 裁剪）按引擎取样语义贴到 layer。

    taps=None → 单次 center 双线性（无描边）；否则按 taps（字体 px）逐 tap 采样后
    ×weight 求和（粗体第二 pass）。"""
    th, tw = tex.shape
    pad = 0
    if taps is not None:
        reach = max(max(abs(t[0]), abs(t[1])) for t in taps)
        pad = int(math.ceil(reach * k)) + 2
    pad += _rot_pad(tw, th, k, deg)
    bx0 = max(0, int(math.floor(x0)) - pad)
    bx1 = min(W, int(math.ceil(x0 + tw * k)) + pad)
    by0 = max(0, int(math.floor(y0)) - pad)
    by1 = min(H, int(math.ceil(y0 + th * k)) + pad)
    if bx0 >= bx1 or by0 >= by1:
        return
    yy, xx = np.mgrid[by0:by1, bx0:bx1]
    xx, yy = xx + 0.5, yy + 0.5
    xx, yy = _rot_coords(xx, yy, cx, cy, deg)
    u, v = (xx - x0) / k, (yy - y0) / k
    if taps is None:
        c = np.clip(_ndi.map_coordinates(tex, [v - 0.5, u - 0.5], order=1,
                                         mode="constant", cval=0.0, prefilter=False),
                    0.0, 1.0)
    else:
        acc = np.zeros_like(u)
        for tx, ty in taps:
            acc += _ndi.map_coordinates(tex, [v - 0.5 + ty, u - 0.5 + tx], order=1,
                                        mode="constant", cval=0.0, prefilter=False)
        c = np.clip(acc * weight, 0.0, 1.0)
    src = np.zeros((by1 - by0, bx1 - bx0, 4), np.float64)
    src[..., :3] = fill_rgb
    src[..., 3] = c
    _composite(layer, src, bx0, by0)


def _render_atlas_text_center(layout: dict, fm, ns, scene, fill: tuple,
                              phase: tuple[float, float], font: str,
                              node_px_offset: tuple[float, float],
                              rotation_deg: float = 0.0, float_ascent: bool = False,
                              bold_px: float = 0.0, bold_taps: str = "shader8",
                              quantize: str = "trunc"):
    """无描边角色（desc）：正常字形=单次 center 双线性（引擎 desc PS）；`<b>`=第二 pass。

    字形供给=glyph_quad（v3.1 驱动单路）：Normal 档 FT unhinted；`<i>` 走引擎合成
    斜切（s=0.25，`style="Italic"` → glyph_quad 的 shear_xy=0x4000）。
    第二 pass 语义=引擎独立 BOLD 子网格 + `Hidden/Text_Bold`（8 tap ×0.23 求和），
    粗体字形**不**在正常 pass 出现。`bold_taps="offset1"` 仅供 A/B（单偏移二绘假设）。"""
    fill_rgb = np.array(fill[:3], dtype=np.float64)
    W, H = scene.canvas
    k = layout["k"] * ns.local_scale * scene.s
    ns_scale_s = ns.local_scale * scene.s
    cx = scene.project(*ns.world_pos[::2])[0] + node_px_offset[0]
    cy = scene.project(*ns.world_pos[::2])[1] + node_px_offset[1]
    pitch_c = layout["pitch"] * ns_scale_s
    box_h_c = layout["box_h"] * ns_scale_s
    ascent_c = (fm.ascent_f if float_ascent else fm.ascent_round) * k
    layer = np.zeros((H, W, 4), np.float64)

    def draw_glyph(g, style: str | None, taps, pen, baseline,
                   weight=_BOLD_TAP_WEIGHT) -> None:
        tex, minx, maxy, _adv = glyph_quad(fm, font, g["ch"], style=style)
        x0 = pen + minx * k + phase[0]
        y0 = baseline - maxy * k + phase[1]
        _paste_glyph(layer, tex, x0, y0, k, W, H, rotation_deg, cx, cy,
                     fill_rgb, taps=taps, weight=weight)

    # pass 1：正常字形（粗体不在本 pass 绘制——引擎粗体是独立子网格）
    for li, row in enumerate(layout["lines"]):
        pen0 = cx - layout["line_widths"][li] * ns_scale_s / 2.0
        baseline = cy - box_h_c / 2.0 + li * pitch_c + ascent_c
        for g in row:
            pen = pen0 + g["pen_x"] * ns_scale_s
            if g["bold"]:
                continue
            draw_glyph(g, "Italic" if g.get("italic") else None, None, pen, baseline)

    # pass 2：粗体字形（独立第二绘制，source-over；8-tap ×0.23 或单偏移 A/B）
    if bold_px >= 0.5:
        if bold_taps == "offset1":      # A/B 假设：单偏移第二次绘制（非引擎语义）
            taps, weight = ((bold_px, 0.0),), 1.0
        else:
            taps, weight = _bold_offsets(bold_px), _BOLD_TAP_WEIGHT
        for li, row in enumerate(layout["lines"]):
            pen0 = cx - layout["line_widths"][li] * ns_scale_s / 2.0
            baseline = cy - box_h_c / 2.0 + li * pitch_c + ascent_c
            for g in row:
                if not g["bold"]:
                    continue
                pen = pen0 + g["pen_x"] * ns_scale_s
                draw_glyph(g, "Italic" if g.get("italic") else None,
                           taps, pen, baseline, weight)
    arr = np.clip(layer, 0, 1) * 255.0
    if quantize == "round":
        arr = np.rint(arr)
    if _FLOAT_CAPTURE:
        _FLOAT_LAYERS.append(np.array(layer, dtype=np.float64, copy=True))
    # 末级量化 round 化（quant-ab 2026-11-05）：出口统一 round（幂等二饮同上）。
    return Image.fromarray(np.rint(arr).astype(np.uint8), "RGBA")
