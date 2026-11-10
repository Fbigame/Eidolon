"""raster — 引擎光栅核心（段 S9 材质状态与纹理基底；engine 侧第一段）。

游戏锚：引擎 Blend 状态语义（SrcAlpha/InvSrcAlpha over、One/Zero opaque 分流、
DstColor/Zero multiply、SrcAlpha/One add——各帧 material_state pass 实测）·
材质序列化 m_SavedProperties/pass 状态（blend/zwrite 真值源）· 渲染队列序
opaque→肖像→transparent（透明件 ZWrite Off 延期补画；dragon-zorder findings §5
边界条款；E9 收敛后单栅 zbuf=scene-compiler-mvp「渲染正典」）· Texture2D
m_MipCount/.resS 流（真 mip 数据）· MipBias/FilterMode（m_TextureSettings 采样
档位——mip-chain 正典：MipBias 序列化于纹理侧/16 链/LOD 闭式）。

我方对位（批18 2026-10-14 转写 old_paint/ur_core.py——E9 收敛正典公式层，转写
偏差零容忍；mip 机制转写 old_paint/_mip_state.py 全机制+ur_core MEMO id 复用
防护硬化的直写形）：
  * 相机自然映射 project_world（scene_compiler.py:62-88 逐字——光栅前置面）。
  * 采样器 sample_bilinear/sample_bilinear_safe（ur_core:66-96）。
  * mip 链采样族 reset_memo/set_enabled/_registry/meta_for/tri_lambda/
    sample_mip_rgba/sample_tex_mip + sample_mip_aware（ur_core:171 hook）。
  * 材质状态表消费 load_state_table/primary_cull/primary_zwrite/primary_queue/
    blend_mode_of（ur_core:429-482）——blend/zWrite/Queue 序列化真值判定。
  * 引擎 Blend 三+一像素写回式 raster_zbuf_alpha/mode/multiply/add（ur_core
    :208/:259/:314/:364）+ tri_front_facing（:415）。
  * 队列序离线等价 raster_bucket_zbuf_unified（ur_core:489）+
    draw_transparent_deferred（:648）——**表驱动** defer_transparent（2026-10-31
    zbuf-table-driven：九链统一直读材质态表，逐链 zwrite_from_table 键退役；spell_dk
    肖像挡白修的正典形）。
  * raster_depth_only（gem-zbuf 2026-11-02 路线 A 深度影子；ur_core 无对位——
    宝石族 PIL 覆盖不写 zbuf 的深度面补件，公式层 gems.gem_depth_shadow 接线）。
  * _ZBUF_POLICY 九帧链策略平行表+zbuf_policy_for（旧链 registry.py
    FRAME_DESC "zbuf_policy" 行平行——批13 _PORTRAIT_PARAMS/批17 _DESC_FRAME
    选型账同形，本模块自带）。

配方面：材质状态表经 supply.frames.supplements.material_state（116 材质内存
面）；mip 链经 recipes.textures.mip_registry（16 链 (bundle,path_id) 寻址表，
游戏直提）。两者均 @item 供给配方——消费须在入口层开的 supply session 内
（本模块不开 session，批12-17 纪律）。

边界：逐 shader 的 PS 直译公式（肖像/gems/水印已在前段立户）属 S11 组装段
接线——ur_core 的 render_portrait_pass/宝石族公式/set_mip_hooks（PORTRAIT_FN/
DESC_PASS_ARRAYS_FN 勾替位）不在本段；公式层经本模块的采样与写回式消费。
mip 状态宿位说明：旧件因 scene_compiler 七实例各自 spec 实例化须
sys.modules 单例桥（_mip_state 头注实测教训）；新包 plain import 天然单实例，
状态直住本模块=同一共享语义的机制化简（行为面逐位同）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from eidolon.core.recipes.textures import (
    LazyFloatChain,
    chain_for_name,
    entry_for_ref,
    mip_registry,
)
from eidolon.core.render._provenance import fitted, invented  # noqa: F401 （族默认）

# ============================================================================
# 消费计数白名单：vColor 落到「消费者中性默认」（2026-10-31 silent-loss-guard）
# ============================================================================
VCOLOR_DEFAULT_KNOWN: dict[str, str] = {}
"""`log["vcolor_default"]` 的冻结白名单（材质名 → 理由串）。**初始为空，每条须带证据。**

语义＝该材质走 `MULTIPLY_FORM_ADD_VCOLOR`（`Hero/Multiply/Multiply`，PS `tex+vColor`），
但材质 `_Color` 解析不到、网格也无 `m_Colors` 顶点色流 ⇒ vColor 取 IA 缺省 0（`tex+0`）。
这是 badge-vcolor 事故三层里的最后一层：**消费端中性默认**——不报错、只悄悄偏暗。

入册必须有证据（资产侧 `_Color` 真的缺席 / 网格真的无色流 / shader 真的 ADD_VCOLOR），
每条一行注释理由；门（上游 gate/impl.py）把白名单外的名字记 global_error → verdict=fail。
**发现某材质其实是漏读（应读却读不到）= 按缺陷报出，禁白名单掩盖。**
"""


# ============================================================================
# 相机（自然映射）—— scene_compiler.py:62-88 逐字搬运（光栅前置面）
# ============================================================================

PX_PER_UNIT = 707.0 / 4.0      # 176.75
HALF_H = 2.0
HALF_W = 2.0 * 512.0 / 707.0
SIZE = (512, 707)   # 出图画布（SnapshotCamera 出图 512x707；ur_core.SIZE 同源）
# 锚位勘误（2026-11-03 D1，recipe-readback §4.2）：SnapshotCamera/AlphaTool 是注入器源码
# （tools/alphatool/，我方人手写、零逆向），decomp（data/full_cs）无此类——引用必须带
# tools/alphatool/ 前缀，禁裸文件名（会被读成 decomp 锚）。

CAMERA_PROVENANCE = {
    "model": "orthographic_natural",
    "px_per_unit": PX_PER_UNIT,
    "px_per_unit_source": "orthographicSize=2(半高) → 全高4单位 × 707px 出图（tools/alphatool/SnapshotCamera.cs:SnapshotCamera.MakeSnapshotCamera, tools/alphatool/AlphaTool.cs:AlphaTool; alphatool-recipe §1.d）",
    "half_w": HALF_W,
    "half_h": HALF_H,
    "half_pixel_offset": 0.0,
    "half_pixel_evidence": "D3D11 后端 viewport TopLeft=0 vs −0.5：净口径 294.8/0.8344 vs 440.8/0.7959（redline-marker-probe rp5）",
}


# 4x 子像素多遍的**覆盖**采样偏移（geometry-aa-4x 2026-11-04）：
# 缺省 (0,0) 时 inside 测试与旧式逐位同。只移“样本在像素内的位置”，不移几何、
# 不移着色位置——颜色/UV 仍按像素中心求值，避免全帧 SSAA 把纹理一起平均糊。
# 由 components 的 supersample 包装器逐遍设置，渲完复位。
_COVERAGE_OFFSET: tuple[float, float] = (0.0, 0.0)

AA_COVERAGE_OFFSETS: tuple[tuple[float, float], ...] = (
    (-0.125, -0.375),
    (0.375, -0.125),
    (0.125, 0.375),
    (-0.375, 0.125),
)
"""D3D 4x 标准旋转网格样本位置（相对像素中心；与 oracle 的 4x MSAA 同阶）。

单一事实源：components 的 supersample 包装器按本表逐遍 `set_coverage_offset`；
watermark 的 V-pass 必须按**同一张表逐样本**跑 desc pass 才与各遍 zbuf 同样本
（geometry-aa-4x 2026-11-04 修：V-pass 若只在中心样本求值，`z_desc == zbuf`
在斜面/曲面上大面积不成立，写域塌成 0——114363 desc 区 mae 0.77→1.94）。
只作**覆盖**样本偏移（着色仍钉像素中心），不声称驱动级逐位同。"""


def set_coverage_offset(dx: float, dy: float) -> None:
    """设置覆盖采样偏移（canvas 像素域；0,0=旧行为）。"""
    global _COVERAGE_OFFSET
    _COVERAGE_OFFSET = (float(dx), float(dy))


def get_coverage_offset() -> tuple[float, float]:
    return _COVERAGE_OFFSET


def _bary(gx: np.ndarray, gy: np.ndarray, xs: np.ndarray, ys: np.ndarray,
          d: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """三角形重心坐标 (l0,l1,l2)（与旧式逐字同式；供中心/覆盖两套位置共用）。"""
    l1 = ((gx - xs[0]) * (ys[2] - ys[0]) - (gy - ys[0]) * (xs[2] - xs[0])) / d
    l2 = ((xs[1] - xs[0]) * (gy - ys[0]) - (ys[1] - ys[0]) * (gx - xs[0])) / d
    return 1.0 - l1 - l2, l1, l2


@fitted(kind="artifact")
def project_world(vw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """世界 (x, y, z) → canvas (px, py)。自然映射，无任何手调偏移（scene_compiler.py:84-88）。

    geometry-aa-4x：投影本身不加偏移（避免纹理随几何平移被平均糊）；4x 覆盖
    偏移只在各光栅函数的 inside/z 测试中使用（`_COVERAGE_OFFSET`）。
    """
    px = (vw[:, 0] + HALF_W) * PX_PER_UNIT
    py = (HALF_H - vw[:, 2]) * PX_PER_UNIT
    return px, py


# ============================================================================
# 采样器（ur_core:66-96 逐字）
# ============================================================================

@fitted(kind="artifact")
def sample_bilinear(img_a: np.ndarray, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """scene_compiler.py:539-551 逐字（y1 上界 clamp 用 w——方纹理下与 safe 等同）。"""
    h, w, _ = img_a.shape
    x = np.clip(px, 0, w - 1)
    y = np.clip(py, 0, h - 1)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, w - 1)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    a = img_a[y0, x0] * (1 - fx) + img_a[y0, x1] * fx
    b = img_a[y1, x0] * (1 - fx) + img_a[y1, x1] * fx
    return a * (1 - fy) + b * fy


@fitted(kind="artifact")
def sample_bilinear_safe(img_a: np.ndarray, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """wf_render.sample_bilinear_safe 正典（scene_compiler.py:554-567 同文本）：
    上界 clamp，浮点边沿防越界；非方纹理 y 界用 h（对 sample_bilinear 的唯一差异）。"""
    h, w, _ = img_a.shape
    x = np.clip(px, 0, w - 1)
    y = np.clip(py, 0, h - 1)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    a = img_a[y0, x0] * (1 - fx) + img_a[y0, x1] * fx
    b = img_a[y1, x0] * (1 - fx) + img_a[y1, x1] * fx
    return a * (1 - fy) + b * fy


@fitted(kind="artifact")
def sample_wrap(arr: np.ndarray, u, v) -> np.ndarray:
    """Repeat wrap 双线性采样（scene_compiler_ally._sample_wrap :841-853 逐字；
    = render_gem._sample clamp=False 同式）。稀有度宝石 ±0.5 图集偏移越界时的
    引擎语义（批22 自 ur_core:99 兑现入本模块——宝石公式层的采样原语）。"""
    h, w = arr.shape[:2]
    x = np.mod(u * w - 0.5, w)
    y = np.mod((1.0 - v) * h - 0.5, h)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = (x0 + 1) % w
    y1 = (y0 + 1) % h
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    return (arr[y0, x0] * (1 - fx) * (1 - fy) + arr[y0, x1] * fx * (1 - fy)
            + arr[y1, x0] * (1 - fx) * fy + arr[y1, x1] * fx * fy)


# ============================================================================
# mip 链采样（_mip_state 全机制转写；机制出处=mip-sampler 实验档取证 +
# mip-chain 正典：MipBias 纹理侧序列化/16 链/LOD 闭式）
#
# 引擎机制（取证=纹理全量 typetree dump）：
#   - MipBias 是纹理侧序列化字段 Texture2D.m_TextureSettings.m_MipBias
#     （Material 的 m_SavedProperties.m_TexEnvs 只含 m_Texture/m_Scale/m_Offset）。
#     渲染集内带 mip 纹理 bias 全 = −0.5（RuneHolder 族 0.0）。
#   - FilterMode：2=Trilinear（MIP_LINEAR）、1=Bilinear（MIP_POINT）；mips=1 时
#     Trilinear 退化为 Bilinear、bias 失效 → 未注册纹理走 mip0 直采（逐位等同）。
#   - LOD = log2(ρ) + MipBias，ρ = max(‖dX‖, ‖dY‖)，dX=(du/dx·W, dv/dx·H)、
#     dY=(du/dy·W, dv/dy·H)（D3D11.3 spec §7.18.11 LOD Calculations 屏幕轴各向同性式，
#     aniso=1 渲染集全 1）；MIP_POINT 选层 = floor(LOD+0.5)
#     （D3D11 spec §Sample 伪代码注 "not a round, this is a floor(+0.5)"），
#     MIP_LINEAR = floor/frac 两层插值。
#   - 负 LOD clamp 到 mip0 → 近 1:1 区逐位不动（阴性对照机制基础）。
#
# mip 数据源 = 游戏直提（recipes.textures.mip_registry：bundle 内序列化真 mip
# 逐层 DXT 解码；真 mip vs box 降采样 MAE 1.9→13 结构性差异，故不取 box）。
# 派发 = 内容指纹：渲染时 tex 数组（PNG/255）与链 L0 array_equal 者判同纹理
# （mip0 双解码器逐位一致已证 → 渲染 PNG == 游戏 mip0）。
# ============================================================================

# ---- 状态（模块级=进程共享；plain import 天然单实例，行为面同旧 sys.modules 桥）----
MIP_ENABLE = True   # 阴性对照开关：False 时**内容指纹派发面**（16 链静态纹理，meta_for）与
# 肖像按需链（portrait.portrait_mip_entry）退化为 mip0 直采（与旧采样器逐位一致）；显式
# `entry`（运行期槽 atlas_ref/mip_name 按需链，_slot_mip_entry→entry_for_ref/chain_for_name）**不受**
# 本开关管——其链由纹理自身序列化 m_MipCount 决定，见 sample_tex_mip
MIP_LAMBDA_LOG: list | None = None  # 探针：非 None 时逐采样记录 (纹理名, lod, i0, f)

READY = False
BY_SHAPE: dict[tuple, list[dict]] = {}
# MEMO 持强引用 (meta, tex)——id 复用防护（E9 ④A/B 实证伴生加固的直写形）：
# 条目持有期间 id 不可能被复用，复用必致 is 判失败 → 落内容比对重判。
MEMO: dict[int, tuple] = {}


@fitted(kind="artifact")
def reset_memo() -> None:
    """每次渲染前调用：tex 数组按 id 记忆，id 可被后续渲染复用，须清（防跨渲染污染）。"""
    MEMO.clear()


@fitted(kind="artifact")
def set_enabled(v: bool) -> None:
    global MIP_ENABLE
    MIP_ENABLE = v


@fitted(kind="artifact")
def mip_enabled() -> bool:
    """阴性对照态读取：**只**覆盖内容指纹派发面（meta_for）与肖像按需链
    （portrait.portrait_mip_entry）——这两处关闭=纯 mip0 直采。运行期槽的显式 `entry`
    （计划 atlas_ref/mip_name 经 entry_for_ref/chain_for_name 解析来的链）不在本开关覆盖面内：
    `sample_tex_mip` 对 `entry is not None` 直接走链，不看本开关（该通道的「关」是
    纹理自身 m_MipCount<=1 → entry_for_ref 返回 None）。"""
    return MIP_ENABLE


# 材质序列化 _MainTex ST 兜底开关（2026-10-23 dual-race-plate，阴性对照同 MIP_ENABLE 族）：
# False = 关闭兜底（=改动前行为：uv_scale=False ∧ 无 mo_st 的链丢弃材质 ST），
# 用于同进程 A/B 与回归取证；生产恒 True。
MAT_ST_ENABLE = True


@fitted(kind="artifact")
def set_mat_st_enabled(v: bool) -> None:
    global MAT_ST_ENABLE
    MAT_ST_ENABLE = v


@fitted(kind="artifact")
def mat_st_enabled() -> bool:
    return MAT_ST_ENABLE


def _registry() -> None:
    """注册面构建（内容指纹派发）：形状桶键 = **uint8 L0 的 shape[:2]**，链条目 = 惰性视图。

    2026-10-30 mip-q1 lazy：此前每个条目把整链 11 级急切转 float64（1024² ≈ 44.7MB/条），
    18 链 ≈ +268MB/进程（门每 worker 一份）；而采样只碰得到 1–3 层。改惰性后桶键仍只需
    L0 尺寸——取 uint8 层的 shape 即零物化；`meta_for` 的 L0 内容比对走 `peek(0)`
    （物化不驻留），`_sample_level` 只在真采到的层上物化。值面逐位不变。
    """
    global READY
    if READY:
        return
    for name, e in mip_registry().items():
        lods = e["lods"]
        entry = {"name": name, "chain": LazyFloatChain(lods),
                 "filter": e["filter"], "bias": e["bias"]}
        BY_SHAPE.setdefault(lods[0].shape[:2], []).append(entry)
    READY = True


@fitted(kind="artifact")
def meta_for(tex: np.ndarray) -> dict | None:
    """内容指纹派发：tex 数组（np.asarray(PNG).astype/255 产物）与链 L0 array_equal 者判同纹理。

    依据：mip0 双解码器逐位一致 → 渲染 PNG == 游戏 mip0（同向，flipud 后）。
    L0 比对走 `peek(0)`：物化但**不驻留**（同形桶里逐条比，驻留会把整桶 L0 钉死在进程，
    见 textures.LazyFloatChain 注）；比较式与 L0 采样同源，逐位等价。
    MEMO id 复用防护（ur_core._harden_mip_memo 直写形）：条目持强引用+`hit[1] is tex`
    身份复核（卡 9 盘区 38k px 低幅跨进程漂移实证——id 键陈旧条目假命中把注册纹理
    误判成未注册、mip 态静默翻转）。"""
    if not MIP_ENABLE:
        return None
    _registry()
    hit = MEMO.get(id(tex), False)
    if hit is not False and hit[1] is tex:
        return hit[0]
    _registry()
    meta = None
    for e in BY_SHAPE.get(tex.shape[:2], []):
        chain = e["chain"]
        l0 = chain.peek(0) if hasattr(chain, "peek") else chain[0]
        if np.array_equal(tex, l0):
            meta = e
            break
    MEMO[id(tex)] = (meta, tex)
    return meta


@fitted(kind="artifact")
def tri_lambda(tri2d: np.ndarray, tri_uv: np.ndarray, tex: np.ndarray) -> float:
    """D3D11.3 §7.18.11 LOD Calculations 屏幕轴各向同性 footprint（texel/像素）：

        ρ = max(‖dX‖, ‖dY‖)，dX=(du/dx·W, dv/dx·H)、dY=(du/dy·W, dv/dy·H)

    即先按 W/H 把 UV 梯度换成 texel 空间向量，再取**屏幕轴两列**范数的大者。
    （旧引「§3.2.4.1」实为 FLOAT→Fixed Point 节，非 LOD 节；2026-11-05 sampling-chain
    审计更正。旧实现按**纹理轴**分组取 `max(‖∇u‖·W, ‖∇v‖·H)`：两式在 UV 基与屏幕轴
    对齐时无条件同值、方形纹素下纯旋转/纯错切同值，非等比缩放+旋转 UV 分叉（W≠H 时
    纯旋转也分叉）——旧式已无条件删除。）

    正交投影 + 屏幕空间线性 UV 插值 → 三角形内 ∇ 恒定（重心梯度闭式），确定性无拟合。"""
    xs, ys = tri2d[:, 0], tri2d[:, 1]
    d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
    if abs(d) < 1e-12:
        return 0.0
    uu, vv = tri_uv[:, 0], tri_uv[:, 1]
    du_dx = ((uu[1] - uu[0]) * (ys[2] - ys[0]) - (uu[2] - uu[0]) * (ys[1] - ys[0])) / d
    du_dy = ((uu[2] - uu[0]) * (xs[1] - xs[0]) - (uu[1] - uu[0]) * (xs[2] - xs[0])) / d
    dv_dx = ((vv[1] - vv[0]) * (ys[2] - ys[0]) - (vv[2] - vv[0]) * (ys[1] - ys[0])) / d
    dv_dy = ((vv[2] - vv[0]) * (xs[1] - xs[0]) - (vv[1] - vv[0]) * (xs[2] - xs[0])) / d
    h, w = tex.shape[:2]
    dx = float(np.hypot(du_dx * w, dv_dx * h))
    dy = float(np.hypot(du_dy * w, dv_dy * h))
    return max(dx, dy)


def _chain_shape0(chain) -> tuple[int, int]:
    """链 L0 尺寸：惰性链走零物化 `shape0()`；list 等旧形态回落 `chain[0].shape[:2]`。

    结构守卫（链与在手纹理不同尺寸 → 不同资产 → 退回 mip0 直采）每次采样都要判，
    故这里不物化 L0（1024² L0 = 33.5MB float64；守卫只看尺寸）。"""
    f = getattr(chain, "shape0", None)
    return tuple(f()) if f is not None else tuple(chain[0].shape[:2])


def _sample_level(chain: list, i: int, col: np.ndarray, row: np.ndarray,
                  base_sampler, shape0: tuple) -> np.ndarray:
    ci = chain[i]
    return base_sampler(ci,
                        (col + 0.5) * (ci.shape[1] / shape0[1]) - 0.5,
                        (row + 0.5) * (ci.shape[0] / shape0[0]) - 0.5)


@fitted(kind="artifact")
def sample_mip_rgba(tex: np.ndarray, col: np.ndarray, row: np.ndarray, lam: float,
                    entry: dict, base_sampler) -> np.ndarray:
    """filterMode 对应的层间处理 + MipBias；负 LOD 段落回原数组（mip0，位等同）。"""
    chain = entry["chain"]
    n = len(chain)
    lod = float(np.log2(max(lam, 1e-9))) + entry["bias"]
    if MIP_LAMBDA_LOG is not None:
        if entry["filter"] == 2:
            lod_c = min(max(lod, 0.0), float(n - 1))
            i0 = int(np.floor(lod_c))
            f = lod_c - i0
        else:
            i0, f = int(np.floor(lod + 0.5)), 0.0
        MIP_LAMBDA_LOG.append((entry["name"], round(lod, 4), i0, round(f, 4)))
    if entry["filter"] == 2:  # Trilinear = MIP_LINEAR
        if lod <= 0.0:
            return base_sampler(tex, col, row)
        lod_c = min(lod, float(n - 1))
        i0 = int(np.floor(lod_c))
        f = lod_c - i0
        s0 = _sample_level(chain, i0, col, row, base_sampler, tex.shape)
        if f <= 0.0 or i0 + 1 >= n:
            return s0
        s1 = _sample_level(chain, i0 + 1, col, row, base_sampler, tex.shape)
        return s0 * (1.0 - f) + s1 * f
    # Bilinear = MIP_POINT：选层 floor(LOD+0.5)（D3D11 spec Sample 伪代码）
    i = int(np.floor(lod + 0.5))
    if i <= 0:
        return base_sampler(tex, col, row)
    return _sample_level(chain, min(i, n - 1), col, row, base_sampler, tex.shape)


@fitted(kind="artifact")
def sample_tex_mip(tex: np.ndarray, col: np.ndarray, row: np.ndarray,
                   tri2d: np.ndarray, tri_uv: np.ndarray, base_sampler,
                   entry: dict | None = None) -> np.ndarray:
    """光栅统一采样入口：未注册纹理 = base_sampler 直采（逐位等同旧行为）。

    `entry` 给定 = **显式链**（运行期纹理槽：计划里的 atlas_ref 经 recipes.textures
    .entry_for_ref 解析，纹理序列化 m_MipCount>1 才有；2026-10-23 weapon-dk-frame），
    不走内容指纹派发（该面只覆盖手工链表）；未给定 = 既有 meta_for 内容指纹面。"""
    if entry is None:
        entry = meta_for(tex)
        if entry is None:
            return base_sampler(tex, col, row)
    elif _chain_shape0(entry["chain"]) != tex.shape[:2]:
        # 结构守卫：链与在手纹理不同尺寸 → 判定为不同资产（composite/合成面等），
        # 退回 mip0 直采（宁可不动也不错采——层坐标会整体错位）。
        return base_sampler(tex, col, row)
    elif entry.get("verify_content") and not np.array_equal(tex, entry["chain"][0]):
        # 内容守卫（名字通道专用）：同名异资产即退回 mip0 直采——名字只是注册表键，
        # 内容才是资产身份（渲染铁律「同名提取文件劫持」的反向保护）。
        return base_sampler(tex, col, row)
    lam = tri_lambda(tri2d, tri_uv, tex)
    return sample_mip_rgba(tex, col, row, lam, entry, base_sampler)


@fitted(kind="artifact")
def sample_mip_aware(tex, col, row, tri2d, tri_uv, base_sampler):
    """mip 采样 hook（ur_core:171 逐字）：未注册纹理 = base_sampler 直采（逐位等同）；
    注册纹理走真 mip 链（sample_tex_mip）。

    mip 链经 recipes.textures.mip_registry（内容指纹派发：渲染数组↔链 L0 位等
    判同纹理）。返回采样值。"""
    return sample_tex_mip(tex, col, row, tri2d, tri_uv, base_sampler)


# ============================================================================
# 计划纹理装载（ur_core:197-201 逐字；桶构建器消费位）
# ============================================================================

@fitted(kind="artifact")
def load_plan_tex(path: Path, get_tex) -> Image.Image:
    """计划/材质里的运行时纹理：**只接受非绝对路径名字** → get_tex 内存面。

    2026-10-21 render-data-decouple：`path.is_absolute() and path.exists()` →
    `Image.open` 直读分支**删除**——绝对路径/盘符/UNC = 已退役的 assets_dir 语义
    （「路径即资源」），响亮 ValueError；不读盘、不静默回退。裸文件名（含相对子路径）
    按 basename 走 kit 内存名，与旧非绝对路径行为逐位同。"""
    if path.is_absolute() or path.drive or path.anchor:
        raise ValueError(
            f"计划纹理路径 {str(path)!r} 为绝对路径/盘符/UNC——已退役的 assets_dir 语义"
            "（渲染只接受 kit 内存名，路径不得直读盘）")
    return get_tex(path.name)


# ============================================================================
# 光栅（像素写回式；三角判定段三式逐字同构；E9 收敛后单栅 zbuf）
# ============================================================================

@fitted(kind="artifact")
def raster_zbuf_alpha(canvas: np.ndarray, zbuf: np.ndarray, tri2d: np.ndarray, tri_z: np.ndarray,
                      tri_uv: np.ndarray, tex: np.ndarray, tint: np.ndarray,
                      uv_offset=(0.0, 0.0), mip: bool = False, zwrite: bool = True,
                      mip_entry: dict | None = None, dual: tuple | None = None):
    """zbuf 判定 + alpha-over + zWrite（wf_render.raster_zbuf :590-629 正典文本；
    mip=True 时采样走 sample_tex_mip（= scene_compiler.raster_zbuf_mip :648-691 同构）。
    zwrite=False = 材质表 zWrite=0 的透明队列件（引擎 ZWrite Off 语义，portrait-chain
    2026-10-04 增参——缺省 True 保持既有调用逐位）。

    `dual`（premium-dualclass-color 2026-11-01，缺省 None=旧单 tint 路径逐位不变）=
    (判式常量组, 逐顶点对象空间 x)：判式常量组=引擎运行时三写点（_Color/_SecondColor/
    _EnableDualClass）+ shader 判式常量（middle=_MiddleValue/m1=_FirstColorRightMargin/
    m2=_SecondColorLeftMargin，材质序列化直读）。逐像素 tint 判式=
    Custom/Card/UnlitDualClassTextureTint PS 逐字（premium 名牌，机制锚=
    Actor.cs:Actor.SetMaterialPremium 双职业支 + prog_1_clean.asm）：

        first  = (x >= middle + m1)                       # ge，含等号
        second = (x <  middle − m2) ? enable : 0          # movc，enable 权重
        tint   = _Color·first + _SecondColor·second + (1 − first − second)   # 缝带=白

    x=重心插值 l0/xs[0]+l1/xs[1]+l2/xs[2]（与 u/v 同式；判轴=网格局部 POSITION.x，
    引擎变换前原值——VS `mov o1.z, v0.x`）。tint 第四通道同式（引擎 xyzw 一体计算；
    _Color/_SecondColor a=1 时 α 因子恒 1，与旧路径 tint[3]=1 同象）。"""
    xs, ys = tri2d[:, 0], tri2d[:, 1]
    xmin = max(int(np.floor(xs.min())), 0)
    xmax = min(int(np.ceil(xs.max())), canvas.shape[1] - 1)
    ymin = max(int(np.floor(ys.min())), 0)
    ymax = min(int(np.ceil(ys.max())), canvas.shape[0] - 1)
    if xmin > xmax or ymin > ymax:
        return
    gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
    d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
    if abs(d) < 1e-12:
        return
    l0, l1, l2 = _bary(gx, gy, xs, ys, d)
    cc0, cc1, cc2 = _bary(gx + _COVERAGE_OFFSET[0], gy + _COVERAGE_OFFSET[1], xs, ys, d)
    inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
    if not inside.any():
        return
    z = cc0 * tri_z[0] + cc1 * tri_z[1] + cc2 * tri_z[2]
    zb = zbuf[ymin:ymax + 1, xmin:xmax + 1]
    inside = inside & (z >= zb)
    if not inside.any():
        return
    if dual is not None:
        cfg, tri_x = dual
        x_local = l0 * tri_x[0] + l1 * tri_x[1] + l2 * tri_x[2]
        first = (x_local >= cfg["middle"] + cfg["m1"]).astype(np.float64)
        second = np.where(x_local < cfg["middle"] - cfg["m2"], cfg["enable"], 0.0)
        wt = 1.0 - first - second
        t_rgba = (cfg["color"] * first[..., None]
                  + cfg["second"] * second[..., None]
                  + wt[..., None])
    u = l0 * tri_uv[0, 0] + l1 * tri_uv[1, 0] + l2 * tri_uv[2, 0] + uv_offset[0]
    v = l0 * tri_uv[0, 1] + l1 * tri_uv[1, 1] + l2 * tri_uv[2, 1] + uv_offset[1]
    col = u * tex.shape[1] - 0.5
    row = (1.0 - v) * tex.shape[0] - 0.5
    if mip or mip_entry is not None:
        rgba = sample_tex_mip(tex, col, row, tri2d, tri_uv, sample_bilinear_safe,
                              entry=mip_entry)
    else:
        rgba = sample_bilinear_safe(tex, col, row)
    if dual is None:
        rgb = rgba[..., :3] * tint[None, :3]
        alpha = rgba[..., 3:] * tint[3]
    else:
        rgb = rgba[..., :3] * t_rgba[..., :3]
        alpha = rgba[..., 3:] * t_rgba[..., 3:4]
    sub = canvas[ymin:ymax + 1, xmin:xmax + 1]
    m = inside
    dst = sub[m]
    sa = alpha[m]
    out_a = sa + dst[..., 3:4] * (1 - sa)
    safe = np.where(out_a > 1e-6, out_a, 1.0)
    sub[m] = np.concatenate(
        [(rgb[m] * sa + dst[..., :3] * dst[..., 3:4] * (1 - sa)) / safe, out_a], axis=-1)
    if zwrite:
        zb[m] = z[m]


@fitted(kind="artifact")
def raster_zbuf_mode(canvas: np.ndarray, zbuf: np.ndarray, tri2d: np.ndarray,
                     tri_z: np.ndarray, tri_uv: np.ndarray, tex: np.ndarray,
                     tint: np.ndarray, uv_offset=(0.0, 0.0), mode: str = "alpha",
                     mip: bool = False, mip_entry: dict | None = None):
    """+opaque/alpha 材质状态分流（location_render.raster_zbuf :638-687 正典文本；
    mip=True = scene_compiler.raster_zbuf_mip_mode 同构）。opaque = srcBlend One/dest Zero
    （RGB 直写、alpha 置 1——RGBA4444 图集透明区 RGB 是美填连续色，硬规矩第 6 例）。"""
    xs, ys = tri2d[:, 0], tri2d[:, 1]
    xmin = max(int(np.floor(xs.min())), 0)
    xmax = min(int(np.ceil(xs.max())), canvas.shape[1] - 1)
    ymin = max(int(np.floor(ys.min())), 0)
    ymax = min(int(np.ceil(ys.max())), canvas.shape[0] - 1)
    if xmin > xmax or ymin > ymax:
        return
    gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
    d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
    if abs(d) < 1e-12:
        return
    l0, l1, l2 = _bary(gx, gy, xs, ys, d)
    cc0, cc1, cc2 = _bary(gx + _COVERAGE_OFFSET[0], gy + _COVERAGE_OFFSET[1], xs, ys, d)
    inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
    if not inside.any():
        return
    z = cc0 * tri_z[0] + cc1 * tri_z[1] + cc2 * tri_z[2]
    zb = zbuf[ymin:ymax + 1, xmin:xmax + 1]
    inside = inside & (z >= zb)
    if not inside.any():
        return
    u = l0 * tri_uv[0, 0] + l1 * tri_uv[1, 0] + l2 * tri_uv[2, 0] + uv_offset[0]
    v = l0 * tri_uv[0, 1] + l1 * tri_uv[1, 1] + l2 * tri_uv[2, 1] + uv_offset[1]
    col = u * tex.shape[1] - 0.5
    row = (1.0 - v) * tex.shape[0] - 0.5
    if mip or mip_entry is not None:
        rgba = sample_tex_mip(tex, col, row, tri2d, tri_uv, sample_bilinear_safe,
                              entry=mip_entry)
    else:
        rgba = sample_bilinear_safe(tex, col, row)
    rgb = rgba[..., :3] * tint[None, :3]
    sub = canvas[ymin:ymax + 1, xmin:xmax + 1]
    m = inside
    if mode == "opaque":
        sub[m, :3] = rgb[m]
        sub[m, 3] = 1.0
        zb[m] = z[m]
        return
    alpha = rgba[..., 3:] * tint[3]
    dst = sub[m]
    sa = alpha[m]
    out_a = sa + dst[..., 3:4] * (1 - sa)
    safe = np.where(out_a > 1e-6, out_a, 1.0)
    sub[m] = np.concatenate(
        [(rgb[m] * sa + dst[..., :3] * dst[..., 3:4] * (1 - sa)) / safe, out_a], axis=-1)
    zb[m] = z[m]


# ---- multiply 合成式（DstColor/Zero 两种 PS 语义；逐 shader 取证，禁逐卡/逐材质名）----
MULTIPLY_FORM_TINT = "tint"
"""旧式：src.rgb = tex × tint（材质 `_Color` / 组件 `_tint_rgb` 进 rgb 因子）。"""

MULTIPLY_FORM_ADD_VCOLOR = "add_vcolor"
"""引擎 `Hero/Multiply/Multiply`：src.rgb = tex + vColor（vColor=顶点色，材质 `_Color`
不进 PS 常量）。RenderDoc 实证（104027 ev438 币阴盘 / ev516 盾影，PS `ResourceId::1301`
hash 147717bb…）：`sample_b r0.xyzw, v1.xyxx, t0.xyzw, s0, cb0[4].x` /
`add o0.xyz, r0.xyzx, v2.xyzx` / `mov o0.w, l(0)`；`dcl_constantbuffer cb0[5]` 只有
_Time；材质序列化 pass=Hero/Multiply/Multiply srcBlend=2(DstColor)/destBlend=0(Zero)。
vColor 实测=币影 0.11321、盾影 0（与材质 `_Color` 逐值相等；序列化 prefab 网格无
m_Colors 流 ⇒ 材质色在运行时影网格里烘为色流）。"""

MULTIPLY_ADD_SHADER = "Hero/Multiply/Multiply"
"""add 式 shader 身份（材质态表 `shader_name`/btf 提取账 `materials[名].shader`）。"""


@fitted(kind="artifact")
def raster_multiply(canvas: np.ndarray, zbuf: np.ndarray, tri2d: np.ndarray,
                    tri_z: np.ndarray, tri_uv: np.ndarray, tex: np.ndarray,
                    tint: np.ndarray, zwrite: bool = False, alpha_one: bool = False,
                    mip: bool = False, form: str = MULTIPLY_FORM_TINT,
                    tri_vcolor: np.ndarray | None = None,
                    mip_entry: dict | None = None):
    """Blend DstColor/Zero：dk_render.raster_zbuf_multiply（2026-10-11 ③外迁退役；zwrite=True, alpha_one=True）
    与 location_render.raster_multiply :690-727（False/False）的参数化合并体；
    mip=True = scene_compiler.raster_multiply_mip 同构（采样 base=sample_bilinear_safe，
    对 dk 原版的 sc.sample_bilinear 仅 y-clamp 界 w→h 之差，方纹理下逐位等同）。

    合成式 `form`（引擎 PS 语义分叉，逐 shader 取证；见 multiply_form）：
      * `MULTIPLY_FORM_TINT`（旧式，缺省）——src.rgb = tex × tint，tint 来自材质
        `_Color` / 组件 `_tint_rgb`（RuneBanner_Card_Shadow_Mat 等 PS=`tex×vCOLOR`
        族；表无 shader 名者按旧式保守沿袭）。
      * `MULTIPLY_FORM_ADD_VCOLOR`——src.rgb = tex + vColor（`Hero/Multiply/Multiply`
        PS：`sample_b r0; add o0.xyz,r0,v2; mov o0.w,l(0)`；cb0 只有 _Time，材质
        `_Color` 不进 PS 常量 ⇒ tint 通道=顶点色）。vColor 取值优先级：网格顶点色
        `tri_vcolor`（应材质的 vColor，逐三角插值）＞ 材质 `_Color` 常量（资产链把
        材质色烘进运行时影网格的色流，序列化 prefab 网格无 m_Colors——本两件
        `_Color`==vColor 逐值实证）＞ 0（IA 缺省=0,0,0,0；`tex+0 ≡ tex×1`，旧式
        缺省白 tint 的链由此逐位不变）。**弃用条件**：一旦某 multiply 材质的网格
        带真 m_Colors 流（供给 npz `/colors` 或运行时影网格 dump 可得），`tri_vcolor`
        路径即取代 `_Color` 代偿；`_Color` 代偿只保 `Hero/Multiply/Multiply` 链。
    α：引擎 color 遍 PS 写 o0.w=0（src.a=0 ⇒ DstColor/Zero 下 out.a=0），而交付画布
    α 是**卡片剪影**（renderdoc-capture α 契约）——故 multiply 一律不写 α
    （alpha_one=False 恒），**不**照抄 0。"""
    xs, ys = tri2d[:, 0], tri2d[:, 1]
    xmin = max(int(np.floor(xs.min())), 0)
    xmax = min(int(np.ceil(xs.max())), canvas.shape[1] - 1)
    ymin = max(int(np.floor(ys.min())), 0)
    ymax = min(int(np.ceil(ys.max())), canvas.shape[0] - 1)
    if xmin > xmax or ymin > ymax:
        return
    gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
    d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
    if abs(d) < 1e-12:
        return
    l0, l1, l2 = _bary(gx, gy, xs, ys, d)
    cc0, cc1, cc2 = _bary(gx + _COVERAGE_OFFSET[0], gy + _COVERAGE_OFFSET[1], xs, ys, d)
    inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
    if not inside.any():
        return
    z = cc0 * tri_z[0] + cc1 * tri_z[1] + cc2 * tri_z[2]
    zb = zbuf[ymin:ymax + 1, xmin:xmax + 1]
    inside = inside & (z >= zb)
    if not inside.any():
        return
    u = l0 * tri_uv[0, 0] + l1 * tri_uv[1, 0] + l2 * tri_uv[2, 0]
    v = l0 * tri_uv[0, 1] + l1 * tri_uv[1, 1] + l2 * tri_uv[2, 1]
    col = u * tex.shape[1] - 0.5
    row = (1.0 - v) * tex.shape[0] - 0.5
    if mip or mip_entry is not None:
        rgba = sample_tex_mip(tex, col, row, tri2d, tri_uv, sample_bilinear_safe,
                              entry=mip_entry)
    else:
        rgba = sample_bilinear_safe(tex, col, row)
    sub = canvas[ymin:ymax + 1, xmin:xmax + 1]
    m = inside
    if form == MULTIPLY_FORM_ADD_VCOLOR:
        if tri_vcolor is not None:
            vc = (l0[..., None] * tri_vcolor[0] + l1[..., None] * tri_vcolor[1]
                  + l2[..., None] * tri_vcolor[2])
            src_rgb = np.clip(rgba[..., :3] + vc[..., :3], 0.0, 1.0)
        else:
            src_rgb = np.clip(rgba[..., :3] + tint[None, :3], 0.0, 1.0)
        # D3D11 UNorm8 RT 写回截断（dst×src 超 1 时钳 1）
        sub[m, :3] = np.clip(sub[m, :3] * src_rgb[m], 0.0, 1.0)
    else:
        src_rgb = rgba[..., :3] * tint[None, :3]
        sub[m, 0] *= src_rgb[m, 0]
        sub[m, 1] *= src_rgb[m, 1]
        sub[m, 2] *= src_rgb[m, 2]
    if alpha_one:
        sub[m, 3] = 1.0
    if zwrite:
        zb[m] = z[m]


@fitted(kind="artifact")
def raster_zbuf_add(canvas: np.ndarray, zbuf: np.ndarray, tri2d: np.ndarray,
                    tri_z: np.ndarray, tri_uv: np.ndarray, tex: np.ndarray,
                    tint: np.ndarray, uv_offset=(0.0, 0.0), mip: bool = False,
                    zwrite: bool = False, mip_entry: dict | None = None):
    """Blend SrcAlpha/One（加色，SrcAlpha 因子对 rgb）：multiclass-render 2026-10-05 新增——
    Faction_Icon_* 材质 shader Hero/Unlit_Transparent 主色 pass 实测
    (srcBlend=5, destBlend=10, zWrite=0)：out.rgb = dst.rgb + src.rgb·src.a；
    alpha 通道同因子对（out.a = dst.a + src.a²），clip [0,1]。既有调用无 "add" 模式，
    零行为变化面（派系图标组件唯一消费者）。"""
    xs, ys = tri2d[:, 0], tri2d[:, 1]
    xmin = max(int(np.floor(xs.min())), 0)
    xmax = min(int(np.ceil(xs.max())), canvas.shape[1] - 1)
    ymin = max(int(np.floor(ys.min())), 0)
    ymax = min(int(np.ceil(ys.max())), canvas.shape[0] - 1)
    if xmin > xmax or ymin > ymax:
        return
    gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
    d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
    if abs(d) < 1e-12:
        return
    l0, l1, l2 = _bary(gx, gy, xs, ys, d)
    cc0, cc1, cc2 = _bary(gx + _COVERAGE_OFFSET[0], gy + _COVERAGE_OFFSET[1], xs, ys, d)
    inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
    if not inside.any():
        return
    z = cc0 * tri_z[0] + cc1 * tri_z[1] + cc2 * tri_z[2]
    zb = zbuf[ymin:ymax + 1, xmin:xmax + 1]
    inside = inside & (z >= zb)
    if not inside.any():
        return
    u = l0 * tri_uv[0, 0] + l1 * tri_uv[1, 0] + l2 * tri_uv[2, 0] + uv_offset[0]
    v = l0 * tri_uv[0, 1] + l1 * tri_uv[1, 1] + l2 * tri_uv[2, 1] + uv_offset[1]
    col = u * tex.shape[1] - 0.5
    row = (1.0 - v) * tex.shape[0] - 0.5
    if mip or mip_entry is not None:
        rgba = sample_tex_mip(tex, col, row, tri2d, tri_uv, sample_bilinear_safe,
                              entry=mip_entry)
    else:
        rgba = sample_bilinear_safe(tex, col, row)
    rgb = rgba[..., :3] * tint[None, :3]
    alpha = rgba[..., 3:] * tint[3]
    sub = canvas[ymin:ymax + 1, xmin:xmax + 1]
    m = inside
    sa = alpha[m]
    sub[m, :3] = np.clip(sub[m, :3] + rgb[m] * sa, 0.0, 1.0)
    sub[m, 3] = np.clip(sub[m, 3] + sa[:, 0] ** 2, 0.0, 1.0)
    if zwrite:
        zb[m] = z[m]


@fitted(kind="artifact")
def tri_front_facing(tri2d: np.ndarray) -> bool:
    """正面 ⟺ 屏幕顺时针（y 向下坐标系 a2>0；ef_fix.tri_front_facing /
    rd_render.tri_front_facing :199-202 同式）。"""
    x, y = tri2d[:, 0], tri2d[:, 1]
    return (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0]) > 0


# ---- ColorAsAlpha 合成式（Effects/FX_Transparent_ColorAsAlpha，亮度当真值 α）----
COLOR_AS_ALPHA_SHADER = "Effects/FX_Transparent_ColorAsAlpha"
"""ColorAsAlpha 着色器身份（37.0 序列化 `m_ParsedForm.m_Name`）。

37.0 Card_Play_Hero/**Card_Play_Bacon_Hero** 的 `RootObject/Mesh/Shadow` 节点
（mesh=ShadowRenderPlane360 20v/25tri 平面、材质=GenFX_CardShadow_Hero、
纹理=GenFX_HeroShadow 128² 拱形遮罩）即本 shader 唯一现役消费件。

**PS 反汇编逐指令**（本批 DXBC 直取，`evidence/shadow_shader_PS_asm.txt`）：
    ps_4_0
    dcl_constantbuffer CB0[5] / CB1[3] / dcl_sampler s0 / dcl_resource_texture2d t0
    sample_b r0.xyzw, v1.xyxx, t0.xyzw, s0, cb0[4].x      ; tex = _MainTex
    dp3      r0.w,   l(0.300000, 0.590000, 0.110000, 0), r0.xyzx   ; lum = Rec.601(tex.rgb)
    mul      r1.xyz, r0.xyzx, cb1[1].xyzx                  ; rgb = tex.rgb × _Color.rgb
    mul      r1.w,   r0.w,   cb1[2].y                      ; a   = lum × _AlphaIntensity
    mul      o0.xyzw, r1.xyzw, cb1[2].xxxx                 ; × _Intensity（rgb 与 a 同乘）
  ⇒ **o0.rgb = tex.rgb·_Color.rgb·_Intensity**；**o0.a = Rec.601(tex.rgb)·_AlphaIntensity·_Intensity**
  （α 不含 `_Color`，故材质 `_Color.a=0` 是惰性字段，不参与判定）。

混合态（材质态表 `GenFX_CardShadow_Hero` 主色 pass）：srcBlend=1(One) /
destBlend=10(OneMinusSrcAlpha) / zWrite=0 / zTest=4(LEqual) / culling=0(Off)
⇒ **预乘式 alpha over**（RGB 不乘 α，直接 One/OneMinusSrcAlpha）：
    out.rgb = src.rgb + dst.rgb·(1−src.a)
    out.a   = src.a   + dst.a·(1−src.a)
（`_Color`=(0.216418,0.155923,0.033916,0)、`_Intensity`=0.5、`_AlphaIntensity`=1：
遮罩白区 ⇒ rgb=(27.5,19.9,4.3)/255、α=0.5 —— 7_hero 参照影带（左缘 x=105,y=400）
实测 (27,19,4,124) 逐值命中，PS 直读值与参照同量级。）

**弃用条件**：若日后该 shader 的 cbuffer 槽位/常量语义变更（`_Intensity` 不再
同乘 α、或 blend 改 (5,10)），本式须按新 DXBC 重述；仅按 shader 身份分派，
不按材质名/卡 id。"""


@fitted(kind="artifact")
def raster_color_as_alpha(canvas: np.ndarray, zbuf: np.ndarray, tri2d: np.ndarray,
                          tri_z: np.ndarray, tri_uv: np.ndarray, tex: np.ndarray,
                          color: np.ndarray, intensity: float,
                          alpha_intensity: float, uv_offset=(0.0, 0.0),
                          mip: bool = False, zwrite: bool = False):
    """Effects/FX_Transparent_ColorAsAlpha 直译（见 `COLOR_AS_ALPHA_SHADER` 头注）。

    color=材质 `_Color`（只取 rgb；a 惰性不进 PS）；intensity/alpha_intensity=
    材质 `m_Floats` 序列化常量（`_Intensity`/`_AlphaIntensity`）。混合=
    One/OneMinusSrcAlpha（表读数，预乘式），zWrite=0（表）故缺省不写深度、
    由透明队列延期位补画。"""
    xs, ys = tri2d[:, 0], tri2d[:, 1]
    xmin = max(int(np.floor(xs.min())), 0)
    xmax = min(int(np.ceil(xs.max())), canvas.shape[1] - 1)
    ymin = max(int(np.floor(ys.min())), 0)
    ymax = min(int(np.ceil(ys.max())), canvas.shape[0] - 1)
    if xmin > xmax or ymin > ymax:
        return
    gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
    d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
    if abs(d) < 1e-12:
        return
    l0, l1, l2 = _bary(gx, gy, xs, ys, d)
    cc0, cc1, cc2 = _bary(gx + _COVERAGE_OFFSET[0], gy + _COVERAGE_OFFSET[1], xs, ys, d)
    inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
    if not inside.any():
        return
    z = cc0 * tri_z[0] + cc1 * tri_z[1] + cc2 * tri_z[2]
    zb = zbuf[ymin:ymax + 1, xmin:xmax + 1]
    inside = inside & (z >= zb)
    if not inside.any():
        return
    u = l0 * tri_uv[0, 0] + l1 * tri_uv[1, 0] + l2 * tri_uv[2, 0] + uv_offset[0]
    v = l0 * tri_uv[0, 1] + l1 * tri_uv[1, 1] + l2 * tri_uv[2, 1] + uv_offset[1]
    col = u * tex.shape[1] - 0.5
    row = (1.0 - v) * tex.shape[0] - 0.5
    if mip:
        rgba = sample_tex_mip(tex, col, row, tri2d, tri_uv, sample_bilinear_safe)
    else:
        rgba = sample_bilinear_safe(tex, col, row)
    src_rgb = rgba[..., :3] * np.asarray(color, dtype=np.float64)[None, :3] * float(intensity)
    lum = rgba[..., 0] * 0.3 + rgba[..., 1] * 0.59 + rgba[..., 2] * 0.11
    src_a = (lum * float(alpha_intensity) * float(intensity))[..., None]
    sub = canvas[ymin:ymax + 1, xmin:xmax + 1]
    m = inside
    dst = sub[m]
    dst_rgb, dst_a = dst[..., :3], dst[..., 3:4]
    # One / OneMinusSrcAlpha（预乘式混合）→ **画布直式存储**：本链 canvas 恒存
    # straight（非预乘）RGB + α（raster_zbuf_alpha 同式；交付 comp_of 再 ×α 成黑底图）。
    # 故先按引擎混合式求预乘结果，再按 out_a 还原直式——否则 comp_of 会二次乘 α，
    # 影带 RGB 掉一半（7_hero 首跑实测 13,9,2 vs 参照 27,19,4，α 面已逐值对）。
    out_a = src_a[m] + dst_a * (1.0 - src_a[m])
    safe = np.where(out_a > 1e-6, out_a, 1.0)
    pre_rgb = src_rgb[m] + dst_rgb * (1.0 - src_a[m])
    sub[m] = np.concatenate([pre_rgb / safe, out_a], axis=-1)
    if zwrite:
        zb[m] = z[m]


@invented(reason="离线深度影子：宝石族 RGB 走 PIL 空间覆盖（不写 zbuf），desc 直接合成的"
                 "深度门控结构性看不见它们；引擎侧宝石=不透明几何队列成员，遮挡序内建——"
                 "本件把宝石几何补进深度面而不出颜色（RGB 路径零接触）",
          counterpart="Unity 不透明几何 ZWrite/ZTest（深度面内建）")
def raster_depth_only(zbuf: np.ndarray, tri2d: np.ndarray, tri_z: np.ndarray,
                      cull: float | None = None) -> bool:
    """depth-only 三角写入（gem-zbuf 路线 A 深度影子，2026-11-02）：几何进深度面、
    不触 canvas。z 判定与写入=主光栅同式（世界 Y 轴、LEqual、单调 max——
    raster_zbuf_alpha 的 zb 段逐字同构）；调用方保证本三角不被 canvas 消费
    （时点=透明延期队补画之后）。cull=可选剔除（2.0=Back，引擎剔除语义）；
    现役消费方 gem_depth_shadow 恒不剔（路线 A 契约=镜像 PIL 覆盖全体三角——
    cull=Back 变体实测 W′∖W 残 289 px：RGB 画家序写背面 sliver 而引擎深度无；
    引擎语义深度归路线 B）。None=不剔。返回是否写入过像素（记账用）。"""
    xs, ys = tri2d[:, 0], tri2d[:, 1]
    xmin = max(int(np.floor(xs.min())), 0)
    xmax = min(int(np.ceil(xs.max())), zbuf.shape[1] - 1)
    ymin = max(int(np.floor(ys.min())), 0)
    ymax = min(int(np.ceil(ys.max())), zbuf.shape[0] - 1)
    if xmin > xmax or ymin > ymax:
        return False
    if cull == 2.0 and not tri_front_facing(tri2d):
        return False
    gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
    d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
    if abs(d) < 1e-12:
        return False
    l0, l1, l2 = _bary(gx, gy, xs, ys, d)
    cc0, cc1, cc2 = _bary(gx + _COVERAGE_OFFSET[0], gy + _COVERAGE_OFFSET[1], xs, ys, d)
    inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
    if not inside.any():
        return False
    z = cc0 * tri_z[0] + cc1 * tri_z[1] + cc2 * tri_z[2]
    zb = zbuf[ymin:ymax + 1, xmin:xmax + 1]
    m = inside & (z >= zb)
    if not m.any():
        return False
    zb[m] = z[m]
    return True


# ============================================================================
# 材质状态表（剔除/混合）——merged 正典表单一实现
# ============================================================================

# 2026-10-06 asset-direct-supply 换轨 → 直读内存面（supplements.material_state
# 同 json 内容面，②对拍 92 材质逐字段已证）；STATE_TABLE 模块缓存原样保留
# （首查一次，进程级独扛）。供给配方消费——入口层 supply session 内（见头注）。
@fitted(kind="artifact")
def load_state_table() -> dict:
    """材质状态表装载（ur_core._load_state_table :429 对位）：
    返回 materials dict（blend/cull/zwrite 判定真值；资产经
    recipes.frames.supplements.material_state）。"""
    from eidolon.core.recipes.frames import supplements as _supp
    return _supp.material_state()["materials"]


STATE_TABLE: dict = {}


def _state_table() -> dict:
    if not STATE_TABLE:
        STATE_TABLE.update(load_state_table())
    return STATE_TABLE


@fitted(kind="artifact")
def primary_cull(mat_name: str):
    """剔除表主色 pass（colMask=15）的 culling（ef_fix.primary_cull 同式；
    表 = material_state（五源合并同构再生），共享键零冲突）。
    返回序列化数值（2.0=Back）或 None（表缺）。"""
    e = _state_table().get(mat_name)
    if not e:
        return None
    for p in e.get("passes") or []:
        if p.get("colMask") == 15.0:
            return p.get("culling")
    return None


@fitted(kind="artifact")
def primary_zwrite(mat_name: str):
    """剔除表主色 pass 的 zWrite（primary_cull 同法取列）。
    zWrite=0 = 引擎 transparent 队列（ZWrite Off）成员——符文字形/符文阴影等。
    返回序列化数值（1.0/0.0）或 None（表缺）。"""
    e = _state_table().get(mat_name)
    if not e:
        return None
    for p in e.get("passes") or []:
        if p.get("colMask") == 15.0:
            return p.get("zWrite")
    return None


ZBUF_STATE_EXEMPT: dict[str, str] = {
    "Glow_Warm": "加色辉光：无 colMask=15 主色 pass（主色遍不存在）——队列/深度面未定义",
    "GenFX_HighlightGreen": "加色辉光：无主色 pass（同上）",
    "Deathknight_Card_Hand_RuneHolder_BlueGlow": "符文 holder 蓝辉光：无主色 pass（同上）",
    "Card_Hand_BG_Tray_Glow_Mesh_Mat": "BG 托盘辉光：无主色 pass（同上）",
}
"""材质态表**冻结豁免**（2026-10-31 zbuf-table-driven）：无主色 pass 的加色辉光族。

语义=「该材质在主色遍上不存在（colMask=15 行缺），队列/深度决定源未定义」；渲染走
add/alpha 专用通路（raster_zbuf_add 恒 zwrite=False），不参与表驱动分派。新增条目须先
证明该材质确实不进主色光栅，并在 docs/notes/scene-compiler-mvp.md 判据账登记；
上游 tools/zbuf_audit.py 逐链核此集合，门内亦以它为缺口白名单（未知材质=红）。"""


_GAP_FX = ("GenFX_FlareStarGold：shader 序列化不可得（m_Shader deref + 双 shader bundle "
           "扫描均无 m_ParsedForm，报告 shader=\"?\"）——无主色 pass 数据即无决定源可并表；"
           "Animator 驱动星芒 quad（timewarped-cost-base.md：Health_Quad1..6 序列化局部 "
           "TRS 全零、rest pose 不进光栅），无渲染行为可失。补齐前缺行=照写深不延期（同键时代）。")
ZBUF_STATE_KNOWN_GAPS: dict[str, str] = {
    "GenFX_FlareStarGold": _GAP_FX,
}
"""**已知缺口冻结集**（2026-10-31 zbuf-table-driven 立；2026-11-01 zbuf-blindspots ② 收缩
16→1）：应当有态表行、但提取面尚未覆盖的注入面材质。逐名冻结（不许前缀通配——新名字必须
被看见，而不是被族前缀吞掉）。

语义=「缺口已记账、待补；出现**新**名字=红」。门每次打印此集，本集只许缩、不许长。

**16→1 收缩账（2026-11-01 zbuf-blindspots ②）**：btf-kit 8 件 + faction-ornaments 8 件
已由 material_state 从两报告面通用并入（zWrite/queue 列直读，culling/blend 两列暂缓——
消费归因不符，见 supplements.material_state 注入面并入注；共享键冲突校验同五源纪律），
`zbuf_audit --fast` 自此可全量可判。上轮并表微退（5 张 BG/任务卡 +0.001~+0.009，左缘
39~86 px）已归因=**CullMode 列**（cull=True 链 primary_cull None→2.0 剔除盾徽/金币网格，
五卡对 oracle 全变差；剥离后 changed=0 bit-identical）——非 zWrite/queue 列；icon 延期
（zW0 ∧ Queue=Transparent）7 张派系卡 7/7 向 oracle 改善（每卡 3 px）。
判据账=docs/notes/scene-compiler-mvp.md §透明队列条。"""


@fitted(kind="artifact")
def primary_queue(mat_name: str):
    """主色 pass 所在 SubShader 的 Queue tag（primary_cull 同法取列）。

    "Transparent" = 引擎透明队列成员（不透明队列之后绘制）；None = 无 tag（引擎默认
    Geometry）或表缺/badge 来源无此字段——两种 None 语义不同，消费方一律回落 zWrite
    判据（primary_zwrite），**不得把 None 当 Geometry**（2026-10-31 zbuf-table-driven：
    无 queue 字段的徽章影行仍靠 zWrite=0 进延期，回落是保行为不变的必要条件）。"""
    e = _state_table().get(mat_name)
    if not e:
        return None
    for p in e.get("passes") or []:
        if p.get("colMask") == 15.0:
            return p.get("queue")
    return None


@fitted(kind="artifact")
def blend_mode_of(mat_name: str) -> str:
    """主色 pass (srcBlend, destBlend) → 光栅模式（location_render.blend_mode :741-756 正典）：
    (One, Zero)=(1,0) → opaque；(DstColor, Zero)=(2,0) → multiply；其余 → alpha over。
    帧型差异：DXT5 图集 alpha 恒 1 时 alpha-over ≡ opaque；RGBA4444（地标）必须分流
    （渲染状态硬规矩 STATUS 未决 9）。"""
    e = _state_table().get(mat_name) or {}
    for p in e.get("passes") or []:
        if p.get("colMask") != 15.0:
            continue
        src, dst = p.get("srcBlend"), p.get("destBlend")
        if src == 1.0 and dst == 0.0:
            return "opaque"
        if src == 2.0 and dst == 0.0:
            return "multiply"
        return "alpha"
    return "alpha"


@fitted(kind="artifact")
def multiply_form(mat_name: str, shader: str | None = None) -> str:
    """材质 → multiply 合成式（引擎 PS 语义分叉的机制化判定）。

    判据=**材质实名 shader 身份**，不是材质名/卡 id：只有 `Hero/Multiply/Multiply`
    （PS `add o0.xyz,r0,v2`，见 MULTIPLY_FORM_ADD_VCOLOR）的材质走加性 `tex+vColor`。
    身份来源两路，均属序列化资产事实：
      1. 调用方传入的材质记录 `shader`（kit 提取 `m_ParsedForm.m_Name`，37.0 序列化直读）；
      2. 材质态表 `shader_name`（补 1 缺省位的旧表）。
    两路都缺 → 回落旧式 tint 合成（无证据不改）。

    2026-10-24（trinket 章环影）：`Anomalies_Atlas_Shadow_Mat` 的材质态表行
    `shader_name` 为空（36.6.0.253216 束遗留，37.0 材质落在
    essential_base_global-material-0 束内、旧表扫不到），旧实现因此回落 tint
    （`tex×_Color`，_Color=0.434）→ 章环影把紫角板压成近黑；引擎实为
    `tex+_Color`（_Color 是运行时影网格 vColor 的烘焙等价物，先例
    bacon-shadow-semantics 2026-10-20）。材质记录实名通道即补此缺省位。"""
    if shader == MULTIPLY_ADD_SHADER:
        return MULTIPLY_FORM_ADD_VCOLOR
    e = _state_table().get(mat_name) or {}
    if e.get("shader_name") == MULTIPLY_ADD_SHADER:
        return MULTIPLY_FORM_ADD_VCOLOR
    return MULTIPLY_FORM_TINT


# ============================================================================
# 桶构建器（zbuf 家族统一；策略参数保留各链已验证的差异语义）
# ============================================================================

def _slot_mip_entry(rt: dict) -> dict | None:
    """计划运行期槽 → 真 mip 链条目（无身份键/无 mip → None）。

    引擎语义＝采样器自动按纹理自身 m_MipCount/FilterMode/MipBias 选层：纹理带 mip 而
    渲染层只拿 mip0，等价于把 Trilinear/点选层降级成「无预滤波缩小」——高频框缘处
    系统性偏差（2026-10-23 weapon-dk-frame 实证：DK 武器图集 1024²/mips=11/filter=1/
    bias=0 是 37.0 武器族唯一带 mip 的图集，z_frame_base 2.17→0.95）。

    两个身份通道（都来自计划里已写的资产事实，不做文件名扫描）：
      * `atlas_ref`：类色图集写点槽（cardMesh[cardFront] / portraitMesh[portraitFrame]）——
        按资产 ref 解析（supply.textures.entry_for_ref，判定全在纹理序列化）；
      * `mip_name`：运行期贴图**名字即身份**的槽（现唯一消费者=DK 符文字形 quad，
        图集 CardRunes_DeathKnight_sm 走 16 链注册表按名取链——与 mip_registry 同键面）；
        该通道加 `verify_content` 标记，采样时以 L0 逐位比对守住「同名异资产」。
     """
    ref = rt.get("atlas_ref")
    if ref:
        return entry_for_ref(ref)
    name = rt.get("mip_name")
    if name:
        ent = chain_for_name(name)
        if ent is not None and not ent.get("verify_content"):
            ent = {**ent, "verify_content": True}
        return ent
    return None


@fitted(kind="artifact")
def raster_bucket_zbuf_unified(bucket, npz, canvas, zbuf, get_tex, *,
                               cull: bool = False,
                               uv_scale: bool = False,
                               apply_mo_uv_offset: bool = True,
                               blend_from_table: bool = False,
                               blend_from_override: bool = False,
                               multiply_prepass: bool = False,
                               multiply_zwrite: bool = False,
                               multiply_alpha_one: bool = False,
                               component_tex_override: bool = False,
                               mip: bool = False,
                               cull_log: dict | None = None,
                               defer_transparent: list | None = None,
                               skip_materials: frozenset | set | None = None) -> dict | None:
    """zbuf 家族桶构建器统一体。策略 ↔ 来源渲染器对照（全部经逐位回归验证后启用）：

    dk（corpus spell 链）   = cull=F(旧缺省；2026-10-16 起九链全 T), uv_scale=T,
                             blend_from_override=T, multiply inline
                             （dk_render.raster_bucket_zbuf_uvscale，2026-10-11 ③外迁退役）
    rd（DK 正典后链）       = 同 dk + cull=T（rd_render.raster_bucket_zbuf_uvscale_cull :205-275）
    wf/hp/hero              = cull=T, 其余 F（wf_render.raster_bucket_zbuf :646-696 同构三份）
    loc                     = cull=T, blend_from_table=T, multiply prepass(zwrite=F),
                             component_tex_override=T（location_render.raster_bucket_zbuf :762-819）
    绘序 = (世界Y均值, DFS seq) 升序；multiply inline = 逐三角按混合模式分流（dk/rd），
    prepass = 乘法三角先于全部其他三角（引擎不透明队列 front-to-back 语义，loc :808-813）。
    bucket = S11 build_render_list 产物五元组列 (name, key, mats, M, comp)。

    `skip_materials`（2026-10-16 用户裁决）＝**几何级**排除集：命中的 submesh 既不投影也
    不光栅（判据=该材质在本链支持的展示态下没有可见面，见 compiler.NON_RASTER_MATERIALS）；
    与执行级的 `cull`（材质表 CullMode，逐三角绕向）是两件事，各自独立生效。

    透明队列决定源（2026-10-31 zbuf-table-driven）：zWrite 与 Queue **一律直读材质态表**
    （primary_zwrite/primary_queue），无逐链开关——`zwrite_from_table` 键退役（它曾让
    spell/hero_play/location 三链开、其余链静默沿用「照写深」反引擎默认；ally 链漏键即
    79480 符文挡肖像根因）。表缺行/无主色 pass 不再静默：分记 log["zbuf_no_row"] /
    log["zbuf_no_primary_pass"]，由上游 tools/zbuf_audit.py 冻结白名单核。
    延期判据 = 渲染模式 multiply ∨ Queue=Transparent ∨ zWrite=0（合流；后两条在现数据显示
    同构，Queue 是主判据，zWrite 兜住无 queue 字段的徽章来源行）。
    """
    log = cull_log if cull_log is not None else {}
    tris_out = []
    seq = 0
    for name, key, mats, M, comp in bucket:
        verts = npz[f"{key}/verts"]
        uv0 = npz[f"{key}/uv0"]
        vw = (M[:3, :3] @ verts.T).T + M[:3, 3]
        px, py = project_world(vw)
        depth = vw[:, 1]
        n_sub = len([k for k in npz.files if k.startswith(f"{key}/sub")])
        if n_sub == 0:
            continue   # 防御位：桶节点恒带 submesh（mesh_stats 前提）；零 sub 不画（旧形同）
        # Unity MeshRenderer 语义（elite-dragon-shadow 2026-10-24）：材质槽多于 submesh
        # → **末 submesh 逐多余材质重画**（引擎文档行为）。37.0 全帧唯一命中=
        # weapon `RootObject/Mesh/Unique_Weapon_Dragon`：mesh polySurface1 束内序列化单
        # submesh（264 tri）×双材质槽〔Drake 不透明 + Drake_shadow 乘性〕——龙影=龙几何
        # 的乘性 overlay（Hero/Multiply/Multiply，tex+0.5 → dst×min(tex+0.5,1)）。
        # 其余帧 n_sub ≥ len(mats)，n_draw=n_sub 逐位同旧形。
        for si in range(max(n_sub, len(mats))):
            sub_i = min(si, n_sub - 1)
            mi = min(si, len(mats) - 1)
            mat = mats[mi]
            if mat is None:
                continue
            if skip_materials and mat["name"] in skip_materials:
                # 几何级排除（compile_plan._exclude_non_raster_components 计划级单源）：
                # 不投影、不光栅、不入 tris_out——该材质在本链支持的展示态下无可见面
                log.setdefault("non_raster_skipped", []).append(f"{name}/sub{si}:{mat['name']}")
                continue
            slot_plan = next((s for s in comp["material_slots"] if s["slot"] == mi), None)
            _mat_tex = (mat["tex"].get("_MainTex", {}).get("texture") or {})
            tex_image = _mat_tex.get("image")   # 批9c：mat tex 内存形态（注入器 shadow 等）
            tex_file = _mat_tex.get("file")
            rt = (slot_plan or {}).get("_MainTex_runtime", {})
            rt_image = rt.get("image")   # 批4：内存面形态（洋红探针/双职业 composite/ST 烘焙）
            rt_file = rt.get("file")
            # 运行期纹理槽的真 mip 链（2026-10-23 weapon-dk-frame）：类色图集写点槽
            # （cardMesh[cardFront] / portraitMesh[portraitFrame]）在计划里以 atlas_ref
            # 记纹理身份；纹理序列化 m_MipCount>1 → 按自身 FilterMode/MipBias 采样
            # （引擎采样器语义，静态 kit 纹理走 16 链内容指纹面不受影响）。
            # 无 atlas_ref / 纹理无 mip → None = 旧 mip0 直采路径逐位不变。
            mip_e = _slot_mip_entry(rt)
            if component_tex_override:
                mo0 = comp.get("material_override") or {}
                if not rt_image and not rt_file and mo0.get("_MainTex_runtime", {}).get("file") and mi == 0:
                    rt_file = mo0["_MainTex_runtime"]["file"]
            if rt_image is not None:
                tex = np.asarray(rt_image.convert("RGBA"), dtype=np.float64) / 255.0
            elif tex_image is not None:
                tex = np.asarray(tex_image.convert("RGBA"), dtype=np.float64) / 255.0
            elif rt_file:
                tex = np.asarray(load_plan_tex(Path(rt_file), get_tex), dtype=np.float64) / 255.0
            elif tex_file:
                # 材质序列化纹理名同样经 load_plan_tex 单一口：绝对路径/盘符=退役语义
                tex = np.asarray(load_plan_tex(Path(tex_file), get_tex),
                                 dtype=np.float64) / 255.0
            else:
                continue
            tint = np.array(mat["colors"].get("_Color", [1, 1, 1, 1]))
            mo = comp.get("material_override") or (slot_plan or {}).get("material_override")
            blend_mode = "over"
            # 组件级 ST 消费口（rune-banner-any-frame 2026-10-07）：mo._uv_transform=True
            # 的组件（现唯一消费者=符文字形）在 uv_scale=False 桶（weapon/hero/ally/location）
            # 也消费 _MainTex ST——引擎语义=材质 _MainTex_ST 恒被 shader 消费（符文 shader
            # 常量槽 cb2[0]，TINT_FIX_PROVENANCE asm 账）。既有计划无此键 → mo_st 恒 False，
            # 下列各分支与旧式逐位同（非符文卡零变化锚的机制保证）。
            mo_st = bool(mo and mo.get("_uv_transform"))
            # 材质序列化 _MainTex ST 兜底（2026-10-23 dual-race-plate）：
            # 引擎 shader 对 _MainTex 一律走 TRANSFORM_TEX（uv*_MainTex_ST.xy+zw），材质
            # 序列化 m_TexEnvs 的 scale/offset 即该 ST；旧式只在 uv_scale 谱系或 plan 级
            # mo._uv_transform 时消费，**其余链把 ST 直接丢弃**。唯一非恒等落在多族宽板
            # 材质 `Multitribe_Nameplates_HSBG_Normal`：_MainTex offset=(0,-0.001)
            # （texel 域 −1.02 texel ≈ 0.7px，板缘/文字描边=高对比带 → 种族区残差主项）。
            # 适用范围刻意最窄：仅 (uv_scale=False ∧ 无 mo_st ∧ 纹理取序列化材质原件) 三
            # 条同真时把材质 ST 当基底；供给侧已烘 ST 的运行时纹理（_MainTex_runtime
            # image/file：ribbon shadow 烘焙、rune atlas）与符文 mo_st 路径一概不动
            # ⇒ 现消费面逐位不变（ST 恒等材质 st_apply=False，旧行为原样）。
            _st_slot = (mat.get("tex") or {}).get("_MainTex") or {}
            _st_raw = (MAT_ST_ENABLE and (not uv_scale) and (not mo_st)
                       and rt_image is None and rt_file is None)
            uv_offset = tuple(_st_slot.get("offset") or (0.0, 0.0)) if _st_raw else (0.0, 0.0)
            uv_scale_v = tuple(_st_slot.get("scale") or (1.0, 1.0)) if _st_raw else (1.0, 1.0)
            st_apply = _st_raw and (tuple(uv_offset) != (0.0, 0.0)
                                    or tuple(uv_scale_v) != (1.0, 1.0))
            if mo:
                if mo.get("_tint_rgb"):
                    if isinstance(mo.get("_tint_rgb"), list):
                        tint = np.array(list(mo["_tint_rgb"]) + [1.0])
                if (apply_mo_uv_offset or mo_st) and mo.get("_MainTex.offset"):
                    uv_offset = tuple(mo["_MainTex.offset"])
                    st_apply = True
                if (uv_scale or mo_st) and mo.get("_MainTex.scale"):
                    uv_scale_v = tuple(mo["_MainTex.scale"])
                    st_apply = True
                if blend_from_override:
                    blend_mode = mo.get("blend", "over")
            # 双职业 premium 名牌双色判式（premium-dualclass-color 2026-11-01）：
            # 引擎运行时三写点（_Color/_SecondColor/_EnableDualClass）随 mo
            # （compiler SetMaterialPremium 双职业支注入）；判式常量
            # _MiddleValue/_FirstColorRightMargin/_SecondColorLeftMargin=材质序列化
            # （C# 零写点，正典解同账）→ 自 mat 直读，不抄第二份事实源。
            # 判式=Custom/Card/UnlitDualClassTextureTint PS 逐字：判轴=对象空间
            # POSITION.x（VS o1.z=v0.x）、_Color 高 x 侧、_SecondColor 低 x 侧、
            # [M−m2,M+m1) 缝带 tint=白。缺常量 → 不套用（保单色 tint 旧行为）+
            # dual_tint_missing_const 计数（gate 闸，silent-loss-guard 同形）。
            dual_tint = None
            if mo and isinstance(mo.get("_dual_class_tint"), dict):
                _fl = mat.get("floats") or {}
                _mv = _fl.get("_MiddleValue")
                _m1 = _fl.get("_FirstColorRightMargin")
                _m2 = _fl.get("_SecondColorLeftMargin")
                if _mv is None or _m1 is None or _m2 is None:
                    log.setdefault("dual_tint_missing_const", {})[mat["name"]] = 1
                else:
                    _dc = mo["_dual_class_tint"]
                    dual_tint = {
                        "color": np.array(list(_dc["_Color"]) + [1.0], dtype=np.float64),
                        "second": np.array(list(_dc["_SecondColor"]) + [1.0], dtype=np.float64),
                        "enable": float(_dc.get("_EnableDualClass", 0.0)),
                        "middle": float(_mv), "m1": float(_m1), "m2": float(_m2),
                    }
            if uv_scale or mo_st or st_apply:
                uv0_x = uv0[:, 0] * uv_scale_v[0] + uv_offset[0]
                uv0_y = uv0[:, 1] * uv_scale_v[1] + uv_offset[1]
                uv_t = np.stack([uv0_x, uv0_y], axis=1)
            else:
                uv_t = uv0
            cm = primary_cull(mat["name"]) if cull else None
            mode = blend_mode_of(mat["name"]) if blend_from_table else blend_mode
            # 显式 mo.blend 优先于表查（multiclass-render 2026-10-05：Faction_Icon add 模式
            # 在 blend_from_table 链（location/weapon/hero）的消费口；既有计划无组件级
            # mo.blend 键于表查链（rune/badge shadow 均在 blend_from_override 链）→ 零行为变化）
            if mo and mo.get("blend") in ("over", "opaque", "multiply", "add"):
                mode = mo["blend"]
            # 透明队列决定源 = 材质态表直读（2026-10-31 zbuf-table-driven；无逐链开关）。
            # zw=主色 pass zWrite（深度写），queue=SubShader Queue tag（队列带）。
            # 表缺行/无主色 pass 保旧行为（写深）但入 log 供 zbuf_audit 冻结白名单核。
            zw = primary_zwrite(mat["name"])
            queue = primary_queue(mat["name"])
            if _state_table().get(mat["name"]) is None:
                log.setdefault("zbuf_no_row", {})[mat["name"]] = 1
            elif zw is None and mat["name"] not in ZBUF_STATE_EXEMPT:
                log.setdefault("zbuf_no_primary_pass", {})[mat["name"]] = 1
            if zw is None:
                zw = True
            # multiply 合成式（见 multiply_form）：注入期组件 override 可显式指定
            # （btf 供给材质不在材质态表内，其 shader 名由提取账随 override 透传）；
            # 否则按材质实名 shader（plan 记录）→ 材质态表 shader_name 兜底判。
            # 非 multiply 模式下本值不被消费。
            mul_form = (mo or {}).get("_multiply_form") or multiply_form(
                mat["name"], mat.get("shader"))
            if mul_form == MULTIPLY_FORM_ADD_VCOLOR:
                # vColor 语义（引擎 PS `add o0.xyz, r0, v2`）：vColor = 材质 `_Color`
                # （运行时影网格色流的序列化等价物）＞ 0（IA 缺省）。**不消费
                # mo._tint_rgb**——那是旧 tint 合成（tex×tint）的旋钮：符文影用它把
                # _Color=0 补白，add 式下 `tex+0 ≡ tex` 已等价；若继续消费会变 tex+1
                # 过曝（2026-10-24 trinket 章环影修复的配套语义）。
                mc = (mat.get("colors") or {}).get("_Color")
                tint = np.array(list(mc) + [1.0]) if mc else np.zeros(4)
                # 消费计数（**只记不改行为**，2026-10-31 silent-loss-guard）：加性
                # multiply 真会消费 vColor（mode=multiply 且本 submesh 无 tri_vcolor 流）
                # 而 `_Color` 又解析不到 ⇒ 落到 IA 缺省 0（`tex+0`），画面只悄悄偏暗。
                # 白名单外的名字由上游 gate/impl.py 记为 global_error（fail-closed）。
                if mode == "multiply" and not mc and f"{key}/colors" not in npz.files:
                    log.setdefault("vcolor_default", {})[mat["name"]] = 1
            # ColorAsAlpha 合成式参数面（shader 身份判据，见 COLOR_AS_ALPHA_SHADER）：
            # 材质 `_Color` 只取 rgb（a 惰性，PS 不入 α）；两强度=序列化 m_Floats。
            ca_params = None
            if mat.get("shader") == COLOR_AS_ALPHA_SHADER:
                _c = (mat.get("colors") or {}).get("_Color") or [1.0, 1.0, 1.0, 1.0]
                ca_params = {
                    "color": np.array(list(_c)[:3], dtype=np.float64),
                    "intensity": float((mat.get("floats") or {}).get("_Intensity", 1.0)),
                    "alpha_intensity": float((mat.get("floats") or {}).get("_AlphaIntensity", 1.0)),
                }
            colors_key = f"{key}/colors"
            tris = npz[f"{key}/sub{sub_i}"]
            nc = 0
            for t in tris:
                tri2d = np.stack([px[t], py[t]], axis=1)
                if cm == 2.0 and not tri_front_facing(tri2d):
                    nc += 1
                    continue
                tri_vc = npz[colors_key][t] if colors_key in npz.files else None
                tris_out.append((float(depth[t].mean()), seq, tri2d, uv_t[t], depth[t], tex, tint,
                                 mode,
                                 # 光栅参 uvo：tri_uv 已烘 ST 的通路（uv_scale 链或 mo_st 组件）
                                 # 恒收 (0,0)——uv_scale=False 链的 raster_zbuf_alpha 会再加一次
                                 # uvo（draw else 分支 uvo_eff），mo_st 烘入+offset 参=二次偏移
                                 # （rune-banner-any-frame 2026-10-07 实测：offset(0,0.5) 字形
                                 # 采样出界钳到图集顶缘透明区，血/霜字形隐身、(0,0) 邪字形免疫）。
                                 # uv_scale=True 链旧形 draw 内 uvo_eff 本就归零 → 逐位同。
                                 # 2026-10-23 dual-race-plate：材质 ST 兜底（st_apply）同属
                                 # 「tri_uv 已烘」族，uvo 必须归零，否则 ST 叠加两次
                                 # （offset −0.001 变 −0.002，实测 z_race 反向抵回原值）。
                                 (0.0, 0.0) if (uv_scale or mo_st or st_apply) else uv_offset, zw,
                                 mul_form, tri_vc, mip_e, ca_params, queue,
                                 # 双职业 premium 名牌判式载荷（16th，premium-dualclass-color
                                 # 2026-11-01）：(判式常量组, 逐顶点对象空间 x)——xs=npz verts
                                 # 原值（M 变换前），与 shader VS o1.z=v0.x 同源；
                                 # fancy 索引 verts[t] 已是新数组。None=单职业/非名牌路径
                                 # 逐位旧形。
                                 None if dual_tint is None
                                 else (dual_tint, verts[t][:, 0])))
                seq += 1
            if nc:
                log[f"{name}/sub{si}:{mat['name']}"] = nc
    tris_out.sort(key=lambda e: (e[0], e[1]))

    def draw(e):
        (_, _, tri2d, tri_uv, tri_z, tex, tint, mode, uvo, zw, mul_form,
         tri_vc, mip_e, ca, queue, dual) = e
        if dual is not None and mode != "over":
            # 双职业判式只在 alpha-over 主路径（raster_zbuf_alpha）兑现——multiply/add/
            # 透明延期臂吃到载荷=判式静默丢失，tripwire 计数（gate 闸 fail-closed；
            # 现消费面 premium ribbon=不透明 over，结构性不命中）。
            log.setdefault("dual_tint_unsupported_branch", {})[mode] = 1
        if ca is not None:
            # ColorAsAlpha（Effects/FX_Transparent_ColorAsAlpha）：材质表 zWrite=0
            # ⇒ 透明队列件——有延期位则延后到肖像之后补画，否则就地按 zwrite=False 画
            # （两者都不写深度：近平面上有卡片本体，写深度会把卡片背面雕边剔出洞）。
            if defer_transparent is not None:
                defer_transparent.append(e)
                return
            uvo_eff = (0.0, 0.0) if uv_scale else uvo
            raster_color_as_alpha(canvas, zbuf, tri2d, tri_z, tri_uv, tex,
                                  ca["color"], ca["intensity"], ca["alpha_intensity"],
                                  uvo_eff, mip=mip, zwrite=False)
            return
        if defer_transparent is not None and (mode == "multiply"
                                              or queue == "Transparent" or not zw):
            # 引擎队列序：不透明几何 → 肖像 → 透明队列。两类件延期：            #   ① Queue=Transparent 的透明件（主判据：SubShader Queue tag 直读，
            #      2026-10-31 zbuf-table-driven）。zWrite=0 是同族事实、作兜底——徽章
            #      来源行无 queue 字段时仍靠它进延期（badge-trio 影件）。
            #   ② **multiply 件恒在透明后队列**（DstColor/Zero=混合队列语义；RenderDoc
            #      104027 币阴盘 order18 / 盾影 order31 均晚于肖像 order8-17）。判据按
            #      混合模式而非材质行——先前抓不到两影材质（态表无行→zw=None→回落 True）。
            defer_transparent.append(e)
            return
        if mode == "multiply":
            raster_multiply(canvas, zbuf, tri2d, tri_z, tri_uv, tex, tint,
                            zwrite=multiply_zwrite, alpha_one=multiply_alpha_one, mip=mip,
                            form=mul_form, tri_vcolor=tri_vc, mip_entry=mip_e)
        elif mode == "add":
            # SrcAlpha/One 加色（multiclass-render：Faction_Icon_*，Hero/Unlit_Transparent
            # zWrite=0 实测——add 模式当前唯一消费者，zwrite=False 即引擎态）
            uvo_eff = (0.0, 0.0) if uv_scale else uvo
            raster_zbuf_add(canvas, zbuf, tri2d, tri_z, tri_uv, tex, tint, uvo_eff, mip=mip,
                            zwrite=False, mip_entry=mip_e)
        elif blend_from_table:
            raster_zbuf_mode(canvas, zbuf, tri2d, tri_z, tri_uv, tex, tint, uvo,
                             mode="alpha" if mode == "over" else mode, mip=mip,
                             mip_entry=mip_e)
        else:
            # dk/rd 谱系：uv_scale=True 时 offset/scale 已烘进 tri_uv，光栅收 (0,0)
            # （rd_render.raster_bucket_zbuf_uvscale_cull :274 同式）；wf 谱系 uv_scale=False，
            # offset 经光栅参生效（wf_render.raster_bucket_zbuf :695 同式）
            uvo_eff = (0.0, 0.0) if uv_scale else uvo
            raster_zbuf_alpha(canvas, zbuf, tri2d, tri_z, tri_uv, tex, tint, uvo_eff, mip=mip,
                              zwrite=bool(zw), mip_entry=mip_e, dual=dual)

    if multiply_prepass:
        for e in tris_out:
            if e[7] == "multiply":
                draw(e)
        for e in tris_out:
            if e[7] != "multiply":
                draw(e)
    else:
        for e in tris_out:
            draw(e)
    return log


@invented(reason="离线单画布无引擎 renderQueue 排序——透明件只能先收集、在肖像公式层之后"
                 "统一补画（ordering 以收集序=世界Y深度升序近似）", counterpart="Unity renderQueue 排序（引擎内建，逐物体按队列带+距离）")
def draw_transparent_deferred(deferred: list, canvas, zbuf, mip: bool = False) -> int:
    """raster_bucket_zbuf_unified(defer_transparent=...) 延期件的补画（引擎队列序：
    不透明几何 → 肖像公式层 → 透明队列（Queue=Transparent / zWrite=0 的透明件 +
    multiply 件恒属混合后队列——见 draw 内延期判据；dragon-zorder findings §5 边界
    条款）。须在肖像公式层之后调用。
    multiply 分支**不写 α**（引擎 PS o0.w=0 属 RT 内部语义；交付画布 α 是卡片剪影，
    见 raster_multiply 头注），合成式/顶点色随延期项原样透传。ColorAsAlpha 分支
    （ca 参数非 None）走预乘式 One/OneMinusSrcAlpha 且写 α（引擎 PS o0.a=亮度×强度，
    参照 7_hero 影带 α=124 实证），同样不写深度。返回补画三角数。"""
    for (_, _, tri2d, tri_uv, tri_z, tex, tint, mode, _uvo, _zw, mul_form,
         tri_vc, mip_e, ca, _queue, _dual) in deferred:
        if ca is not None:
            # _uvo 已按链口径归零（uv_scale 链烘进 tri_uv；wf 链=材质 offset）
            raster_color_as_alpha(canvas, zbuf, tri2d, tri_z, tri_uv, tex,
                                  ca["color"], ca["intensity"], ca["alpha_intensity"],
                                  _uvo, mip=mip, zwrite=False)
        elif mode == "multiply":
            raster_multiply(canvas, zbuf, tri2d, tri_z, tri_uv, tex, tint,
                            zwrite=False, alpha_one=False, mip=mip,
                            form=mul_form, tri_vcolor=tri_vc, mip_entry=mip_e)
        else:
            raster_zbuf_alpha(canvas, zbuf, tri2d, tri_z, tri_uv, tex, tint,
                              mip=mip, zwrite=False, mip_entry=mip_e)
    return len(deferred)


# ============================================================================
# 帧链光栅策略（FRAME_DESC "zbuf_policy" 行平行表——策略冻结值消费面）
# ============================================================================

_ZBUF_POLICY: dict[str, dict] = {
    # 透明队列决定源（2026-10-31 zbuf-table-driven，全局）：zWrite/Queue 一律直读材质态表，
    # **本表不再有 zwrite_from_table 键**。键时代的三次同根事故账：
    #   ① 2026-10-20 spell-multiply-zbuf：multiply 徽章 ShadowQuad（表 zW0）被当不透明三角
    #      写深且排在肖像前，肖像左缘整段 LEqual 拒掉（126616/124080/126841 竖带）；
    #   ② 2026-10-23 hero-play-frame：近平面阴影写进 zbuf，把卡片背面雕边剔出洞；
    #   ③ 2026-10-31 rune-quad-zblock：ally 链**漏键**——符文 quad（表 zW0）写深挡掉肖像
    #      公式层（79480 残差条带）；根因=键是逐链 opt-in，后建的链默认「照写深」。
    # 键退役后：新链/新材质无「默认反引擎」可踩；缺行/无主色 pass 由 zbuf_audit 冻结白名单核。
    # 法术（Card_Hand_Ability）：corpus 正典 dk 谱系（uv_scale+blend_from_override，
    # multiply alpha_one=True）。cull=True（2026-10-16 用户裁决）：材质表
    # CullMode 是引擎恒常语义、非链选择——旧 False 系旧链基线镜像，会多画卡背壳金边
    # （三态语料 133 卡验证零劣化、改善 25 卡；判据账见 docs/notes/scene-compiler-mvp.md
    # §渲染正典与 material_cull_table 谱系）。
    # multiply_alpha_one=False（2026-10-20）：引擎 color 遍 PS `mov o0.w,l(0)`，α 不进
    # 混合；交付画布 α=卡片剪影，故 multiply 一律不动 α（旧 True 把盾影 6tri 四边形
    # 写成 α=255 → 黑三角/黑缝 1332 px）。
    "Card_Hand_Ability": dict(cull=True, uv_scale=True, apply_mo_uv_offset=True,
                  blend_from_table=False, blend_from_override=True,
                  multiply_prepass=False, multiply_zwrite=False,
                  multiply_alpha_one=False, component_tex_override=False),
    # 金法术（Card_Hand_Ability_Premium）= ability 行逐字段同构（capture-determinism
    # 2026-10-30；同族 prefab 同光栅谱系——ally/ally_premium 先例同注）
    "Card_Hand_Ability_Premium": dict(cull=True, uv_scale=True, apply_mo_uv_offset=True,
                            blend_from_table=False, blend_from_override=True,
                            multiply_prepass=False, multiply_zwrite=False,
                            multiply_alpha_one=False, component_tex_override=False),
    # 随从（Card_Hand_Ally）：④dragon-zorder 根修回迁 zbuf——ally 既有语义
    # （blend_from_override=T 供 badge ShadowQuad multiply；multiply 双 F=徽章乘法
    # 引擎语义）。符文 quad 挡肖像（79480）在键时代因本行缺键而复发——键退役后由表判定。
    "Card_Hand_Ally": dict(cull=False, uv_scale=False, apply_mo_uv_offset=True,
                 blend_from_table=False, blend_from_override=True,
                 multiply_prepass=False, multiply_zwrite=False,
                 multiply_alpha_one=False, component_tex_override=False),
    # 金卡随从（Card_Hand_Ally_Premium）= ally 行逐字段同构（mechorse-golden
    # 2026-10-21；同族 prefab 同光栅谱系，premium 材质态表已入行）
    "Card_Hand_Ally_Premium": dict(cull=False, uv_scale=False, apply_mo_uv_offset=True,
                         blend_from_table=False, blend_from_override=True,
                         multiply_prepass=False, multiply_zwrite=False,
                         multiply_alpha_one=False, component_tex_override=False),
    # 武器/英雄手牌/英雄打出/BG 英雄/技能：wf 谱系（cull=T，余 F）
    "Card_Hand_Weapon": dict(cull=True, uv_scale=False, apply_mo_uv_offset=True,
                   blend_from_table=False, blend_from_override=False,
                   multiply_prepass=False, multiply_zwrite=False,
                   multiply_alpha_one=False, component_tex_override=False),
    "Card_Hand_Hero": dict(cull=True, uv_scale=False, apply_mo_uv_offset=True,
                      blend_from_table=False, blend_from_override=False,
                      multiply_prepass=False, multiply_zwrite=False,
                      multiply_alpha_one=False, component_tex_override=False),
    # hero play 双链（2026-10-23 hero-play-frame）：本帧唯一命中的可见透明件=
    # `RootObject/Mesh/Shadow`（GenFX_CardShadow_Hero，zW0/One/OneMinusSrcAlpha），
    # 其余可见件（HeroFrame/HeroPortrait 两 sub、Gem_*）表内 zW1 或宝石公式层不参与本桶。
    # 表驱动下该类件不写深、延期到肖像之后（引擎队列序）。
    "Card_Play_Hero": dict(cull=True, uv_scale=False, apply_mo_uv_offset=True,
                      blend_from_table=False, blend_from_override=False,
                      multiply_prepass=False, multiply_zwrite=False,
                      multiply_alpha_one=False, component_tex_override=False),
    "Card_Play_Bacon_Hero": dict(cull=True, uv_scale=False, apply_mo_uv_offset=True,
                            blend_from_table=False, blend_from_override=False,
                            multiply_prepass=False, multiply_zwrite=False,
                            multiply_alpha_one=False, component_tex_override=False),
    "History_HeroPower": dict(cull=True, uv_scale=False, apply_mo_uv_offset=True,
                      blend_from_table=False, blend_from_override=False,
                      multiply_prepass=False, multiply_zwrite=False,
                      multiply_alpha_one=False, component_tex_override=False),
    # 地标：loc 谱系（blend_from_table+component_tex_override）。multiply_prepass
    # →False（2026-10-25 be780-rune-location）：prepass 把 multiply 三角画在**空黑板布**
    # 上（dst=0 → dst×tex≡0 恒黑），露出区写黑——BE_780 符文旗板 shadow quad 超出八角板
    # 右肩=硬边黑条实锤；引擎实证（evidence/renderdoc/be780 cap_004_frame919 逐 draw
    # 差分）multiply 在不透明（板 ev147→框体 ev231）之后（shadow ev284），与 spell/
    # hero_play「multiply 恒在透明后队列」同判据。表驱动下 zW0 件（符文影/字形/图标）
    # 一律进延期透明队列。
    "Card_Hand_Location": dict(cull=True, uv_scale=False, apply_mo_uv_offset=False,
                     blend_from_table=True, blend_from_override=False,
                     multiply_prepass=False, multiply_zwrite=False,
                     multiply_alpha_one=False, component_tex_override=True),
    # 饰品（Card_Hand_BG_Trinket；bg-ct40-43-44-routing 2026-10-24）：loc 谱系
    # （blend_from_table+multiply prepass+表驱动透明队列延期）——帧内 multiply 材质=
    # 章环影 Anomalies_Atlas_Shadow_Mat（表 (2,0)/zW0/cull Back），接触影 CardShadow_Ally
    # （(1,10)/zW0，序列化 enabled=true=捕获展示态，hero-play-frame 先例）；其余材质主色
    # pass 全 opaque（材质态表实测）。
    # apply_mo_uv_offset=True（ally 形保留——稀有度宝石 mo._MainTex.offset 消费口）。
    "Card_Hand_BG_Trinket": dict(cull=True, uv_scale=False, apply_mo_uv_offset=True,
                    blend_from_table=True, blend_from_override=False,
                    multiply_prepass=True, multiply_zwrite=False,
                    multiply_alpha_one=False, component_tex_override=False),
    # 畸变（Card_Hand_BG_Anomaly；bg-ct40-43-44-routing 2026-10-24）：spell 谱系
    # 逐字段同构——帧=Card_Hand_Ability 族变体（材质集=ability 子集+Card_Inhand_
    # Ability_Anomaly 主纹理，probe 实测 Warlock 系 banner/GenFX 卡背同 pid），无
    # trinket 型 multiply 影件（接触影 CardShadow_Ability 序列化 renderer.enabled=
    # false，elite 龙影同隐——材质态表主色 pass 全 opaque）。
    "Card_Hand_BG_Anomaly": dict(cull=True, uv_scale=True, apply_mo_uv_offset=True,
                    blend_from_table=False, blend_from_override=True,
                    multiply_prepass=False, multiply_zwrite=False,
                    multiply_alpha_one=False, component_tex_override=False),
}
"""prefab→光栅策略（consumer-v2 改键：键=prefab 资产名；spell_dk 行消亡〔与 spell 逐字段同构的冗余，DK 差异归 tag 组件通路〕；行值=old 逐字。
谱系账=FRAME_DESC "zbuf_policy" 行平行表，旧链 registry.py
:158/:195/:218/:241/:261/:288/:314/:332/:354 九行——本模块自带，批17 _DESC_FRAME
选型账同形；开放位=九帧链，未知键 assert 响亮）。**九行 cull 现已全 True**
（2026-10-16：spell 行由 False 改 True，材质表 CullMode 归位引擎恒常语义）。
**2026-10-31 zbuf-table-driven：zwrite_from_table 变体键全部退役**——透明队列决定源
（zWrite/Queue）移入材质态表直读，本表只管几何/采样/合成式差异（cull/uv_scale/
blend_from_table/blend_from_override/multiply_* /component_tex_override）。链级只保留
**显式豁免位** `zbuf_inline_reason`（非空说明串；语义=「本链故意不延期」），
默认零条、由 zbuf_audit 冻结集合核。execute 位 cull 覆写支（`cull_non_dk_spell`）随
缺省 True 退化为 A/B 回归通路（显式置 False 才生效，须记账）。"""


@fitted(kind="artifact")
def zbuf_policy_for(key: str) -> dict:
    """帧键 → 光栅策略 dict（FRAME_DESC[key]["zbuf_policy"] 对位）。返回副本
    （消费方 pop 变体键不污染表——render_card.py:409 policy=dict(...) 同纪律）。
    未知帧键 assert 响亮（tripwire 纪律，批14/17 同款）。"""
    assert key in _ZBUF_POLICY, (
        f"未知帧键 {key!r}——_ZBUF_POLICY 无此键（开放位={sorted(_ZBUF_POLICY)}）")
    return dict(_ZBUF_POLICY[key])


# ============================================================================
# 公式层 mip 勾替位（PORTRAIT_FN/DESC_PASS_ARRAYS_FN——批18 边界注记的 S11 面，
# 批22 兑现；转写 old_paint/ms_layers_mip.py 两工厂：dz 公式层/desc pass 的
# 逐行同构 mip 副本，采样行走 sample_mip_aware；λ=tri_lambda D3D11.3 §7.18.11）
# ============================================================================

PORTRAIT_FN = None          # None = 公式层 plain 采样（game/actor/portrait.render_portrait_submesh）
DESC_PASS_ARRAYS_FN = None  # None = game/actor/watermark.desc_pass_arrays


@fitted(kind="artifact")
def sample_texel_bilinear(arr: np.ndarray, col: np.ndarray, row: np.ndarray) -> np.ndarray:
    """texel 坐标双线性基采样器（dz_portrait_layer.sample_bilinear 的 texel 形态，
    ms_layers_mip:21 逐字；4 角加权浮点序保持）。

    mip 族统一基采样器：sample_mip_rgba 的 base_sampler 面——层内双线性 × 层间
    MIP_LINEAR 加权即三线性；肖像公式层显式链消费（U/V→texel 换算在调用方）同用本件，
    保证「mip0 段落」与 plain 采样逐位同式。"""
    h, w = arr.shape[:2]
    x = np.clip(col, 0, w - 1.001)
    y = np.clip(row, 0, h - 1.001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = x0 + 1
    y1 = y0 + 1
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    return (arr[y0, x0] * (1 - fx) * (1 - fy) + arr[y0, x1] * fx * (1 - fy)
            + arr[y1, x0] * (1 - fx) * fy + arr[y1, x1] * fx * fy)


def _make_render_portrait_submesh_mip(pl):
    """dz_portrait_layer.render_portrait_submesh 的 mip 化逐行同构副本
    （ms_layers_mip.make_render_portrait_submesh_mip :39 转写；pl=game/actor/
    portrait 模块——公式常量与 portrait_factor 消费位）。

    采样两路：`mip_entry` 给定 = 肖像纹理显式按需链（(bundle, path_id) 直提，
    LOD+Bias 三线性——portrait-mip-lod 2026-10-20 正典）；未给定 = 既有内容指纹派发
    （sample_mip_aware，16 条手工链面）。两路同一 sample_mip_rgba/tri_lambda，落层
    加权逐位同式。"""
    BRIGHTNESS_LIFT = pl.BRIGHTNESS_LIFT
    ALPHA_LIFT = pl.ALPHA_LIFT
    portrait_factor = pl.portrait_factor

    def render_portrait_submesh_mip(canvas, zbuf, depth, px, py, uv0, uv1, tris,
                                    main_rgba, second_rgba, second_tint, blend_intensity,
                                    color=(1.0, 1.0, 1.0, 1.0), vcolor=(1.0, 1.0, 1.0, 1.0),
                                    mip_entry=None):
        color = np.asarray(color, dtype=np.float64)
        vcol = np.asarray(vcolor, dtype=np.float64) * color
        order = sorted(range(len(tris)), key=lambda i: float(py[tris[i]].mean()))
        for i in order:
            tri = tris[i]
            xs, ys = px[tri], py[tri]
            xmin = max(int(np.floor(xs.min())), 0)
            xmax = min(int(np.ceil(xs.max())), canvas.shape[1] - 1)
            ymin = max(int(np.floor(ys.min())), 0)
            ymax = min(int(np.ceil(ys.max())), canvas.shape[0] - 1)
            if xmin > xmax or ymin > ymax:
                continue
            gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5,
                                 np.arange(ymin, ymax + 1) + 0.5)
            d = ((xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0]))
            if abs(d) < 1e-12:
                continue
            l0, l1, l2 = _bary(gx, gy, xs, ys, d)
            cov_x, cov_y = _COVERAGE_OFFSET
            cc0, cc1, cc2 = _bary(gx + cov_x, gy + cov_y, xs, ys, d)
            inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
            if not inside.any():
                continue
            zs = depth[tri]
            zpix = cc0 * zs[0] + cc1 * zs[1] + cc2 * zs[2]
            zb = zbuf[ymin:ymax + 1, xmin:xmax + 1]
            inside = inside & (zpix >= zb)
            if not inside.any():
                continue
            u0 = l0 * uv0[tri[0], 0] + l1 * uv0[tri[1], 0] + l2 * uv0[tri[2], 0]
            v0 = l0 * uv0[tri[0], 1] + l1 * uv0[tri[1], 1] + l2 * uv0[tri[2], 1]
            u1 = l0 * uv1[tri[0], 0] + l1 * uv1[tri[1], 0] + l2 * uv1[tri[2], 0]
            v1 = l0 * uv1[tri[0], 1] + l1 * uv1[tri[1], 1] + l2 * uv1[tri[2], 1]
            if pl.UV_WRAP:   # hp 帧 Repeat（uservisual 725 案提案 A 正典）
                u0 = np.mod(u0, 1.0)
                v0 = np.mod(v0, 1.0)
                u1 = np.mod(u1, 1.0)
                v1 = np.mod(v1, 1.0)
            tri2d = np.stack([xs, ys], axis=1)
            col0 = u0 * main_rgba.shape[1] - 0.5
            row0 = (1.0 - v0) * main_rgba.shape[0] - 0.5
            if mip_entry is not None:
                main = sample_mip_rgba(main_rgba, col0, row0,
                                       tri_lambda(tri2d, uv0[tri], main_rgba),
                                       mip_entry, sample_texel_bilinear)
            else:
                main = sample_mip_aware(main_rgba, col0, row0, tri2d, uv0[tri],
                                        sample_texel_bilinear)
            col1 = u1 * second_rgba.shape[1] - 0.5
            row1 = (1.0 - v1) * second_rgba.shape[0] - 0.5
            sec = sample_mip_aware(second_rgba, col1, row1, tri2d, uv1[tri], sample_texel_bilinear)
            F = portrait_factor(sec, second_tint, blend_intensity)
            blend = main[..., :3] * F
            cand1 = np.concatenate([blend, np.full(blend.shape[:2] + (1,), 1.0)], axis=-1)
            cand2_rgb = (blend + BRIGHTNESS_LIFT) * vcol[None, None, :3]
            cand2_a = ALPHA_LIFT * vcol[3]
            cand2 = np.concatenate([cand2_rgb, np.full(blend.shape[:2] + (1,), cand2_a)], axis=-1)
            out = np.minimum(cand1, cand2)
            sub = canvas[ymin:ymax + 1, xmin:xmax + 1]
            sub[inside] = out[inside]
            zb[inside] = zpix[inside]

    return render_portrait_submesh_mip


def _make_desc_pass_arrays_mip(tw):
    """ta_watermark.desc_pass_arrays 的 mip 化逐行同构副本（ms_layers_mip
    .make_desc_pass_arrays_mip :108 转写；签名不变可直补——tw=game/actor/watermark
    模块，_find_node/supplements 消费位）。

    与 plain 版同步（2026-10-20 desc 底缘修）：逐 submesh 按
    `tw.desc_submesh_mode` 分派 PS 语义——materials[0]（运行时水印载体）走 PS 全式；
    其余 submesh（ability 网格 sub1=另一支序列化 shader，无 _SecondTint/_Color）
    输出=主纹理。"""
    def desc_pass_arrays_mip(wm: dict, frame_recon: dict, desc_path: str,
                             array_prefix: str, size: tuple, project_world,
                             sample_bilinear, main_tex, return_z: bool = False):
        W, H = size
        node = tw._find_node(frame_recon, desc_path)
        M = np.array(node["world"], dtype=np.float64)

        from eidolon.core.recipes.frames import supplements as _supp
        sup = _supp.ta_supplement()
        verts = sup[f"{array_prefix}/verts"]
        uv0 = sup[f"{array_prefix}/uv0"]
        uv1 = sup[f"{array_prefix}/uv1"]
        color0 = sup[f"{array_prefix}/color0"]
        n_sub = len([k for k in sup if k.startswith(f"{array_prefix}/sub")])

        vw = (M[:3, :3] @ verts.T).T + M[:3, 3]
        px, py = project_world(vw)

        tex_main = np.asarray(main_tex.convert("RGBA"), dtype=np.float64) / 255.0
        tex_wm = np.asarray(wm["tex_img"].convert("RGBA"), dtype=np.float64) / 255.0
        sx, sy = wm["st_scale"]
        ox, oy = wm["offset_runtime"]
        tint = np.array(wm["tint_rgba"], dtype=np.float64)
        tint = tint.copy()
        tint[3] = wm["alpha"]
        blend = wm["blend_intensity"]
        color = np.array(wm["color_rgba"], dtype=np.float64)

        rgb_out = np.zeros((H, W, 3), dtype=np.float64)
        a_out = np.zeros((H, W), dtype=np.float64)
        cov = np.zeros((H, W), dtype=bool)
        # return_z（vpass-direct 2026-11-03）：desc 几何 z（世界 Y 重心插值，
        # 主光栅 depth=vw[:,1] 同源定义）——plain 版 desc_pass_arrays 同款逐行同构
        # （gem-zbuf 探针 _desc_geo 上正典；覆盖域外 NaN、后写覆盖=画家序）。
        z_desc = np.full((H, W), np.nan) if return_z else None
        zv = vw[:, 1] if return_z else None

        modes = tw.desc_submesh_mode(frame_recon, desc_path, n_sub)
        for si in range(n_sub):
            wm_like = modes[si] == "watermark"
            tris = sup[f"{array_prefix}/sub{si}"]
            if not wm_like:
                # 非载体 submesh 顶点色契约（同 plain 版）：冻结资产全 1.0；非常数=拒绝
                _csub = color0[np.unique(tris.reshape(-1))]
                assert np.all(_csub == 1.0), (
                    f"{desc_path}/sub{si} 顶点色非常数 1.0（min={_csub.min(axis=0)} "
                    f"max={_csub.max(axis=0)}）——main_only 的 out=main×v2 需引擎侧取证后再放开")
            for t in tris:
                xs, ys = px[t], py[t]
                xmin = max(int(np.floor(xs.min())), 0)
                xmax = min(int(np.ceil(xs.max())), W - 1)
                ymin = max(int(np.floor(ys.min())), 0)
                ymax = min(int(np.ceil(ys.max())), H - 1)
                if xmin > xmax or ymin > ymax:
                    continue
                gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5,
                                     np.arange(ymin, ymax + 1) + 0.5)
                d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
                if abs(d) < 1e-12:
                    continue
                l0, l1, l2 = _bary(gx, gy, xs, ys, d)
                cov_x, cov_y = _COVERAGE_OFFSET
                cc0, cc1, cc2 = _bary(gx + cov_x, gy + cov_y, xs, ys, d)
                inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
                if not inside.any():
                    continue
                if return_z:
                    z = cc0 * zv[t[0]] + cc1 * zv[t[1]] + cc2 * zv[t[2]]
                u0 = l0 * uv0[t[0], 0] + l1 * uv0[t[1], 0] + l2 * uv0[t[2], 0]
                v0 = l0 * uv0[t[0], 1] + l1 * uv0[t[1], 1] + l2 * uv0[t[2], 1]
                col0 = u0 * tex_main.shape[1] - 0.5
                row0 = (1.0 - v0) * tex_main.shape[0] - 0.5
                tri2d = np.stack([xs, ys], axis=1)
                main = sample_mip_aware(tex_main, col0, row0, tri2d, uv0[t], sample_bilinear)
                if wm_like:
                    u1 = (l0 * uv1[t[0], 0] + l1 * uv1[t[1], 0] + l2 * uv1[t[2], 0]) * sx + ox
                    v1 = (l0 * uv1[t[0], 1] + l1 * uv1[t[1], 1] + l2 * uv1[t[2], 1]) * sy + oy
                    col1 = u1 * tex_wm.shape[1] - 0.5
                    row1 = (1.0 - v1) * tex_wm.shape[0] - 0.5
                    tri_uv1 = np.stack([uv1[t][:, 0] * sx + ox, uv1[t][:, 1] * sy + oy], axis=1)
                    second = sample_mip_aware(tex_wm, col1, row1, tri2d, tri_uv1, sample_bilinear)
                    st = second * tint[None, :] * blend
                    out = st[..., 3:4] * (main * st - main) + main
                    v2 = color[None, None, :] * color0[t[0]][None, None, :]
                    out = np.minimum(out, (out + 0.15) * v2)
                else:
                    # 非水印载体 submesh：序列化 shader（双职业拼贴族）PS 退化态
                    # out=main×v2，v2=顶点色重心插值（冻结资产全 1.0，上方 assert 守门）
                    v2 = (l0[..., None] * color0[t[0]][None, None, :]
                          + l1[..., None] * color0[t[1]][None, None, :]
                          + l2[..., None] * color0[t[2]][None, None, :])
                    out = main * v2
                sub_r = rgb_out[ymin:ymax + 1, xmin:xmax + 1]
                sub_a = a_out[ymin:ymax + 1, xmin:xmax + 1]
                sub_c = cov[ymin:ymax + 1, xmin:xmax + 1]
                sub_r[inside] = out[inside, :3]
                sub_a[inside] = out[inside, 3]
                sub_c[inside] = True
                if return_z:
                    sub_z = z_desc[ymin:ymax + 1, xmin:xmax + 1]
                    sub_z[inside] = z[inside]
        if return_z:
            return rgb_out, a_out, cov, z_desc
        return rgb_out, a_out, cov

    return desc_pass_arrays_mip


@fitted(kind="artifact")
def set_mip_hooks(on: bool) -> None:
    """公式层 mip 勾替位（ur_core.set_mip_hooks :955 对位；批22 兑现）。on=False
    恢复 plain 采样公式层（corpus 正典口径 mip=False——勾替位即 base21 铸造条件
    专用）。"""
    global PORTRAIT_FN, DESC_PASS_ARRAYS_FN
    if not on:
        PORTRAIT_FN = None
        DESC_PASS_ARRAYS_FN = None
        return
    from eidolon.core.render.game.actor import portrait as _portrait
    from eidolon.core.render.game.actor import watermark as _watermark
    PORTRAIT_FN = _make_render_portrait_submesh_mip(_portrait)
    DESC_PASS_ARRAYS_FN = _make_desc_pass_arrays_mip(_watermark)
