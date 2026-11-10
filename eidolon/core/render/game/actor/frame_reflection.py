"""frame_reflection — 金框反射层（shader=Custom/Card/UnlitTextureReflection）。

游戏锚（37.0 实测序列化，证据=实验档 evidence/premium_frame_370.json：
  * 材质 `GenFX_Card_Inhand_Premium`（金卡框体 Mesh sub0）/
    `GenFX_Card_InHand_BannerAtlas_Premium`（名牌 NameBanner_mesh 与种族板
    RacePlate_mesh）三处同族；`_MainTex/_SpecTex/_ReflTex` 三槽 + 浮点
    `_ReflectionIntensity=1.5`、`_ReflectionRotation=0.2`、`_LightingBlend=0`、
    `_ShaderTime=0`；`_Color=白`、`_MainTex_ST=恒等`；pass0 = One/Zero、
    cull=2（Back）、zWrite=1、zTest=4。
  * shader Pass 0 两程序：VS 32 指令 / PS 9 指令（37.0 反汇编
    output/shader_370/refl370_{0,1}.asm；与 36.6 e10 记录的 32/9 同构）。

DXBC 直译（逐指令，符号沿用 asm）：
  VS   v1.xy = uv0·_MainTex_ST + _MainTex_Offset              （ST 恒等 → uv0）
       n_w    = (unity_ObjectToWorld·n).xz                    （`mul r0.zw, v1.yyyy` 链）
       t      = dp2(_Time.x.xx, _ReflectionRotation.yy) = 2·_Time.x·_ReflectionRotation
       v1.zw  = 2·( 0.07·(world.xz − uv0.x·0.3·n_w) + t )
  PS   refl   = _SpecTex(v1.xy) · _ReflTex(v1.zw) · _ReflectionIntensity
       out    = sat(refl·0.5 + _MainTex(v1.xy)) · vColor
       vColor = 1（_LightingBlend/_ShaderTime 序列化 0 → VS 末块项恒 0）

_Time.x = 会话冻结时刻/20（docs/notes/renderdoc-capture.md「相位：会话相关，必须逐会话
直读」节；37.0 代逐会话冻结 P≈11.0 ⇒ _Time.x≈0.55，data/card-image/<代>/capture.json
sessions[].frozen_p）。**注意**：会话相位 t=(P/20)%0.2 只够驱动在 0.2 步长上闭合的项；
本层时间项步长 4·rot=0.8 ≠ 0.2 的整数倍，必须吃**完整 _Time.x**（不是 t 的余数）。

消费形：`apply_reflection(canvas, zbuf, nodes, npz, get_tex, time)`——在 opaque 光栅
之后立即调用（引擎队列序：框体先画，肖像/文字后画盖其上）；只写「本反射材质当帧为
最前表面」的像素（zbuf 等值判据），故后续层照常覆盖。

`_SpecTex` 采样（2026-10-30 mip-q1 nameplates）：此前恒 plain 双线性（引擎采样器实际
按纹理自身 FilterMode/MipBias 选层）——多族名牌板 `Multitribe_HSBG_Nameplates_Spec`
（1024²/11 级/filter=1/bias=0）因此被当 mip0 用，是覆盖审计的 gap #2
（见 docs/notes/mip-chain.md）。现走 `raster.sample_mip_rgba`（与光栅面同一
LOD 闭式/层间处理），entry 由 `_spec_mip_entry` 三重守卫解析（名字面注册 + 结构尺寸 +
L0 内容逐位）——无链/尺寸不符/同名异资产一律退回旧 plain 路径（逐位等同旧行为）。
`_ReflTex` 仍恒 plain：它是 Repeat wrap（`sample_wrap` 吃 uv 不吃 texel 坐标，与
`_sample_level` 的层缩放不同构），且本语料该槽纹理 m_MipCount=1（审计 exempt）。
MIP_ENABLE=False（阴性对照）时本层同样退回 plain。

失效条件：shader 换代（props/时间项公式变）、材质 `_ReflectionIntensity`/
`_ReflectionRotation` 序列化值变、或采集代不提供会话冻结时刻（capture.json 无
sessions[].frozen_p）——此时调用方回退 `plan["gem"]["t"]` 并须登记相位失配风险。
"""
from __future__ import annotations

import numpy as np

from eidolon.core.render.engine.raster import (
    get_coverage_offset,
    mip_enabled,
    project_world,
    sample_bilinear_safe,
    sample_mip_rgba,
    sample_wrap,
    tri_front_facing,
    tri_lambda,
)
from eidolon.core.recipes.textures import chain_for_name
from eidolon.core.render._provenance import fitted  # noqa: F401 （族默认）

# asm 字面常量（VS：`mul r0.zw, l(0.3,0.3)`、`mad r0.xy, l(0.07,0.07)`、
# `add o1.zw, r0.xxxy, r0.xxxy`）
N_PERTURB = 0.3
UV_SCALE = 0.07
UV_DOUBLE = 2.0
REFL_TEXTURE_SLOTS = ("_SpecTex", "_ReflTex")
DEFAULT_INTENSITY = 1.5


def _slot_file(mat: dict, slot: str) -> str | None:
    tex = ((mat.get("tex") or {}).get(slot) or {})
    info = tex.get("texture") or {}
    return info.get("file") or (f"{info['name']}.png" if info.get("name") else None)


def _chain_shape0(chain) -> tuple[int, int]:
    """链 L0 尺寸（惰性链零物化；list 回落 chain[0]）。"""
    f = getattr(chain, "shape0", None)
    return tuple(f()) if f is not None else tuple(chain[0].shape[:2])


@fitted(kind="artifact")
def _spec_mip_entry(info: dict | None, arr: np.ndarray) -> dict | None:
    """反射 `_SpecTex` 的真 mip 链条目（None = 走旧 plain 双线性，逐位等同旧行为）。

    引擎采样器对 `_SpecTex` 也按纹理自身 `m_MipCount/FilterMode/MipBias` 选层，故这里
    与光栅面同一判定与同一层间处理（`raster.sample_mip_rgba` / `raster.tri_lambda`）。
    三重守卫**宁可不动也不错采**（与 `raster.sample_tex_mip` 的显式 entry 面同判）：
      * 名字面：`chain_for_name`（手工链注册表 + 消费点登记）无条目 → None；
      * 结构：链 L0 尺寸 ≠ 在手数组尺寸 → None（`_sample_level` 的层坐标会整体错位）；
      * 内容：链 L0 与在手数组**逐位**不等 → None（同名异资产，名字只是注册表键）。
    阴性对照 `MIP_ENABLE=False` → None（本层与内容指纹面同闸）。"""
    if not mip_enabled():
        return None
    name = (info or {}).get("name")
    if not name:
        return None
    ent = chain_for_name(name)
    if ent is None:
        return None
    chain = ent["chain"]
    if _chain_shape0(chain) != tuple(arr.shape[:2]):
        return None
    l0 = chain.peek(0) if hasattr(chain, "peek") else chain[0]
    if not np.array_equal(arr, l0):
        return None
    return ent


@fitted(kind="artifact")
def is_reflection_material(mat: dict | None) -> bool:
    """反射族判式=材质槽同时带 _SpecTex 与 _ReflTex（shader 名 shipping 被剥，
    槽位组合是稳定判据；37.0 全量 prefab dump 仅这两个材质族命中）。"""
    if not mat:
        return False
    tex = mat.get("tex") or {}
    return all(s in tex and _slot_file(mat, s) for s in REFL_TEXTURE_SLOTS)


def _tri_bary(gx, gy, xs, ys):
    d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
    if abs(d) < 1e-12:
        return None
    l1 = ((gx - xs[0]) * (ys[2] - ys[0]) - (gy - ys[0]) * (xs[2] - xs[0])) / d
    l2 = ((xs[1] - xs[0]) * (gy - ys[0]) - (ys[1] - ys[0]) * (gx - xs[0])) / d
    l0 = 1.0 - l1 - l2
    return l0, l1, l2


@fitted(kind="artifact")
def apply_reflection(canvas: np.ndarray, zbuf: np.ndarray, nodes, npz, get_tex,
                     time: float, *, cull: bool = False, log: dict | None = None,
                     depth_eps: float = 1e-3) -> dict:
    """金框反射层叠加（原地改 canvas；返回统计账）。

    canvas 浮点 RGBA（直式 alpha，与 raster 同式）；zbuf = 世界 Y 深度（大者在前）。
    nodes = build_render_list 产物 (name, key, mats, M, comp) 列；time = _Time.x。
    """
    stats = {"materials": [], "pixels": 0}
    tex_cache: dict[str, np.ndarray] = {}

    def tex_arr(fname: str) -> np.ndarray | None:
        if fname not in tex_cache:
            try:
                img = get_tex(fname)
            except Exception:  # noqa: BLE001  缺纹理=该槽跳过（记账不静默）
                return None
            tex_cache[fname] = np.asarray(img.convert("RGBA"), dtype=np.float64) / 255.0
        return tex_cache[fname]

    for name, key, mats, M, comp in nodes:
        if f"{key}/verts" not in npz.files:
            continue
        n_sub = len([k for k in npz.files if k.startswith(f"{key}/sub")])
        for si in range(n_sub):
            if si >= len(mats):
                continue
            mat = mats[si]
            if not is_reflection_material(mat):
                continue
            spec_file = _slot_file(mat, "_SpecTex")
            refl_file = _slot_file(mat, "_ReflTex")
            spec_info = ((mat.get("tex") or {}).get("_SpecTex") or {}).get("texture") or {}
            spec = tex_arr(spec_file) if spec_file else None
            refl = tex_arr(refl_file) if refl_file else None
            if spec is None or refl is None:
                stats["materials"].append({"path": name, "slot": si,
                                           "skipped": "纹理缺失",
                                           "spec": spec_file, "refl": refl_file})
                continue
            spec_entry = _spec_mip_entry(spec_info, spec)   # None = 旧 plain 路径
            floats = mat.get("floats") or {}
            k = float(floats.get("_ReflectionIntensity", DEFAULT_INTENSITY))
            rot = float(floats.get("_ReflectionRotation", 0.0))
            verts = npz[f"{key}/verts"]
            uv0 = npz[f"{key}/uv0"]
            if f"{key}/normals" in npz.files:
                normals = npz[f"{key}/normals"]
            else:
                normals = np.zeros_like(verts)
            tris = npz[f"{key}/sub{si}"]
            M = np.asarray(M, dtype=np.float64)
            vw = (M[:3, :3] @ verts.T).T + M[:3, 3]
            px, py = project_world(vw)
            depth = vw[:, 1]
            nw = (M[:3, :3] @ normals.T).T
            world_xz = np.stack([vw[:, 0], vw[:, 2]], axis=1)
            # VS 直译：v1.zw = 2·(0.07·(world.xz − uv0.x·0.3·n.xz) + 2·_Time.x·rot)
            t_scalar = 2.0 * float(time) * rot
            ruv = UV_DOUBLE * (UV_SCALE * (world_xz
                                           - uv0[:, 0:1] * N_PERTURB * nw[:, [0, 2]])
                               + t_scalar)
            hit = np.zeros(canvas.shape[:2], bool)
            for tri in tris:
                xs, ys = px[tri], py[tri]
                tri2d = np.stack([xs, ys], axis=1)
                if cull and not tri_front_facing(tri2d):
                    continue
                xmin = max(int(np.floor(xs.min())), 0)
                xmax = min(int(np.ceil(xs.max())), canvas.shape[1] - 1)
                ymin = max(int(np.floor(ys.min())), 0)
                ymax = min(int(np.ceil(ys.max())), canvas.shape[0] - 1)
                if xmin > xmax or ymin > ymax:
                    continue
                gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5,
                                     np.arange(ymin, ymax + 1) + 0.5)
                bary = _tri_bary(gx, gy, xs, ys)
                if bary is None:
                    continue
                l0, l1, l2 = bary
                cov_x, cov_y = get_coverage_offset()
                cbary = _tri_bary(gx + cov_x, gy + cov_y, xs, ys)
                if cbary is None:
                    continue
                cc0, cc1, cc2 = cbary
                inside = (cc0 >= -1e-6) & (cc1 >= -1e-6) & (cc2 >= -1e-6)
                if not inside.any():
                    continue
                z = cc0 * depth[tri[0]] + cc1 * depth[tri[1]] + cc2 * depth[tri[2]]
                zb = zbuf[ymin:ymax + 1, xmin:xmax + 1]
                inside &= np.abs(zb - z) <= depth_eps
                if not inside.any():
                    continue
                u = (l0 * uv0[tri[0], 0] + l1 * uv0[tri[1], 0]
                     + l2 * uv0[tri[2], 0])
                v = (l0 * uv0[tri[0], 1] + l1 * uv0[tri[1], 1]
                     + l2 * uv0[tri[2], 1])
                ru = (l0 * ruv[tri[0], 0] + l1 * ruv[tri[1], 0]
                      + l2 * ruv[tri[2], 0])
                rv = (l0 * ruv[tri[0], 1] + l1 * ruv[tri[1], 1]
                      + l2 * ruv[tri[2], 1])
                sp_col = u * spec.shape[1] - 0.5
                sp_row = (1.0 - v) * spec.shape[0] - 0.5
                if spec_entry is not None:
                    sp = sample_mip_rgba(
                        spec, sp_col, sp_row,
                        tri_lambda(np.stack([xs, ys], axis=1), uv0[tri], spec),
                        spec_entry, sample_bilinear_safe)
                else:
                    sp = sample_bilinear_safe(spec, sp_col, sp_row)
                rf = sample_wrap(refl, ru, rv)
                add = sp * rf * (0.5 * k)          # vColor=1，PS `mad_sat ×0.5`
                sub = canvas[ymin:ymax + 1, xmin:xmax + 1]
                yy, xx = np.nonzero(inside)
                sel = sub[yy, xx]
                sel[:, :3] = np.clip(sel[:, :3] + add[inside][:, :3], 0.0, 1.0)
                sel[:, 3] = np.clip(sel[:, 3] + add[inside][:, 3], 0.0, 1.0)
                sub[yy, xx] = sel
                hit[ymin:ymax + 1, xmin:xmax + 1][inside] = True
            stats["materials"].append({"path": name, "slot": si, "material": mat.get("name"),
                                       "intensity": k, "rotation": rot,
                                       "pixels": int(hit.sum()),
                                       # 记账位（同 portrait.mip / mip_skip 族）：
                                       # 非 None = 该槽 _SpecTex 走了真 mip 链
                                       "spec_mip": (spec_entry or {}).get("name")})
            stats["pixels"] += int(hit.sum())
    if log is not None:
        log["reflection"] = stats
    return stats
