"""mip_extract — mip 面 UnityPy 链提取（Phase 1 A5；cold 编排、本单点）。

三件（任务单 A5）：
1. **静态注册表**（live ``textures.mip_registry``，23 条手工链）：``MIP_CHAINS``
   逐字搬迁 live ``supply.textures._MIP_CHAINS``——**逐字符一致是链面契约**
   （color_extract.SWITCHER_REF 同款：live 与 cold 必须提取同一对象集）；
   ``test_supply_index_mip`` 有 live vs cold 表全等机器证明（防漂移）。
2. **per-card 肖像链**：fold 进 cold 解码 worker（``cold._decode_bundle_worker``
   kind='portrait' 任务顺带提取——同一包已开，免二次开包），分类三态：
   - ``registry``：链名在注册表且 (bundle,path_id) 与注册表地址相等（live
     chain_for_name 注册表分支同判据）→ 不落自有 blob（warm 从 registry 派生）；
   - ``chain``：m_MipCount>1 且非注册表 → 提取第 1..n-1 级落 NPZ（L0 由
     portrait PNG 派生——cold 期逐纹理验证 UnityPy 解码与链解码位等，失配落
     显式 L0 级，manifest "l0" 字段裁决）；
   - ``portrait``：m_MipCount<=1 → 单级链（无自有链数据，L0=肖像像素）。
3. **atlas 链账**（entry_for_ref 的 seeded 查找数据面）：fold 进 color atlas
   worker——逐 guid 记 m_MipCount/name/filter/bias 判定（mips=1=「无链」裁决值）
   ，mips>1 全级提取落 NPZ（12 条带 mip 图集：weapon DK + location 11 族；
   其中 location Mage 名在注册表——warm 查找面按名回落 registry，与 live
   chain_for_name 注册表分支同判）。

live 对位（eidolon/core/supply/textures.py，形状逐字复刻——S1 种子形状契约）：
  - ``_extract_chain``：typetree 取格式/尺寸/滤波设置，.resS 流逐层切片解码，
    字节账断言（off==len(data)）=链切片完整性结构检查，flipud 对齐渲染数组；
  - ``_decode_level/_level_dims/_level_bytes``：纯数学件逐字搬迁（fmt
    10=DXT1 12=DXT5 3=RGB24 4=RGBA32 13=RGBA4444）。

纪律沿 cold/kit_extract/text_extract 同款：UnityPy 非线程安全→按 bundle 分进程
（worker spawn 可 pickle）；链解码器=texture2ddecoder（live 同库——**解码器
一致性**是「seeded 链==live 链」逐位判据的根基）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import texture2ddecoder

from eidolon.core.supply_index._unity import (
    container_pairs,
    iter_serialized,
    load_bundle,
)

# ---------------------------------------------------------------------------
# 静态注册表（live supply.textures._MIP_CHAINS 逐字搬迁；漂移由单测钉住）
# ---------------------------------------------------------------------------

MIP_CHAINS: tuple[tuple[str, str, int], ...] = (
    ("W3_141_D", "cardtexture_base_global-244154c1-texture-0.unity3d", -1602847098564489785),
    ("Draenei2_D", "cardtexture_base_global-775a814d-texture-1.unity3d", 4289398879984128315),
    ("W2_387_D", "cardtexture_base_global-3aaf7c48-texture-0.unity3d", -6164241411173700911),
    ("W17_a009_D", "cardtexture_base_global-74f6be89-texture-0.unity3d", -9101074624978776141),
    ("W2_032_D", "cardtexture_base_global-775a814d-texture-1.unity3d", -5052237005613840206),
    ("HS11-132_W", "cardtexture_base_global-06d41e57-texture-0.unity3d", -8783332919758037587),
    ("W4_080_D", "cardtexture_base_global-244154c1-texture-1.unity3d", 315780230582378923),
    ("w14_a208_D", "essential_base_global-texture-3.unity3d", -442804245900451206),
    ("Garrosh_D", "essential_base_global-texture-0.unity3d", -641007567816002583),
    ("HS26-161_L", "cardtexture_base_global-0516e06c-texture-2.unity3d", -875928073585824811),
    ("HS28-130_S", "cardtexture_base_global-786af98e-texture-0.unity3d", 4053842576122521015),
    ("CardRunes_DeathKnight", "essential_base_global-texture-1.unity3d", -8374584392692364380),
    ("CardRunes_DeathKnight_sm", "essential_base_global-texture-1.unity3d", -7217558262942142559),
    ("Deathknight_Card_Hand_RuneHolder", "essential_base_global-texture-1.unity3d", 722852026899807080),
    ("REV_Icon", "initial_base_global-4bbced1c-texture-4.unity3d", -4429388145647349000),
    ("Card_InHand_Location_Mage", "initial_base_global-8411aad9-texture-4.unity3d", 3657745995071084785),
    ("Multitribe_HSBG_Nameplates", "essential_base_global-texture-1.unity3d", -695423779591078699),
    ("Multitribe_HSBG_Nameplates_Spec", "initial_base_global-8411aad9-texture-12.unity3d", -1623763288469544269),
    ("PoAIcon", "initial_base_global-4bbced1c-texture-5.unity3d", -7214246542155689089),
    ("RLKIcon", "initial_base_global-4bbced1c-texture-4.unity3d", -6679188991779832773),
    ("CoreIcon_Even", "initial_base_global-4bbced1c-texture-3.unity3d", 5440975720784402096),
    ("SCIcon", "initial_base_global-4bbced1c-texture-4.unity3d", -8675088962978514531),
    ("Card_Inhand_Forgeable_Banner", "initial_base_global-8411aad9-texture-3.unity3d", 760062728052139132),
)

MIP_CHAIN_ADDR = {e[0]: (e[1], int(e[2])) for e in MIP_CHAINS}
REGISTRY_NAMES = frozenset(e[0] for e in MIP_CHAINS)

# portrait_mip 分类四态（cold manifest "source" 字段词面）
SOURCE_REGISTRY = "registry"     # 链名在注册表且地址相等——warm 从 registry 派生
SOURCE_CHAIN = "chain"           # mips>1 非注册表——自有 NPZ（1..n-1 级）
SOURCE_PORTRAIT = "portrait"     # mips<=1——单级链（L0=肖像像素）
SOURCE_UNSUPPORTED = "unsupported"  # mips>1 且格式在链解码器域外——不建 item 不期望

# 链解码器格式域（decode_level 支持集；live supply.textures._decode_level 同集）。
# 域外（如 25=BC7）：portrait PNG（UnityPy）可解、链解码不可解——live
# portrait_mip 对其 raise（ValueError fmt N），渲染失败属 live 现状；cold 同判
# 「不支持」记账（缺席可归因≠缺口），种子路径 token 不种 → live 兜底 → 同样
# raise——seeded/live 失败模式逐位一致。
SUPPORTED_FORMATS = frozenset({10, 12, 3, 4, 13})


# ---------------------------------------------------------------------------
# 解码件（live supply.textures 同名函数逐字搬迁；漂移由单测钉住）
# ---------------------------------------------------------------------------

def decode_level(data: bytes, w: int, h: int, fmt: int) -> "np.ndarray":
    """单 mip 层 → RGBA uint8。fmt: 10=DXT1 12=DXT5 3=RGB24 4=RGBA32 13=RGBA4444。"""
    if fmt == 10:
        arr = np.frombuffer(texture2ddecoder.decode_bc1(data, w, h), dtype=np.uint8).reshape(h, w, 4)
        return arr[..., [2, 1, 0, 3]].copy()
    if fmt == 12:
        arr = np.frombuffer(texture2ddecoder.decode_bc3(data, w, h), dtype=np.uint8).reshape(h, w, 4)
        return arr[..., [2, 1, 0, 3]].copy()
    if fmt == 3:
        rgb = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)
        return np.concatenate([rgb, np.full((h, w, 1), 255, np.uint8)], axis=-1)
    if fmt == 4:
        return np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4).copy()
    if fmt == 13:
        v = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4).astype(np.uint16)
        rgba = np.empty((h, w, 4), np.uint8)
        rgba[..., 0] = ((v[..., 0] & 0xF0) >> 4) * 17
        rgba[..., 1] = ((v[..., 0] & 0x0F)) * 17
        rgba[..., 2] = ((v[..., 1] & 0xF0) >> 4) * 17
        rgba[..., 3] = ((v[..., 1] & 0x0F)) * 17
        return rgba
    raise ValueError(f"fmt {fmt}")


def level_dims(w: int, h: int, level: int) -> tuple[int, int]:
    return max(w >> level, 1), max(h >> level, 1)


def level_bytes(fmt: int, w: int, h: int) -> int:
    if fmt in (10, 12):
        return ((w + 3) // 4) * ((h + 3) // 4) * (8 if fmt == 10 else 16)
    return w * h * (3 if fmt == 3 else 4)


def texture_head(tree: dict) -> dict:
    """Texture2D typetree → 链提取头部（live _extract_chain 同字段面）。"""
    return {"name": tree.get("m_Name"),
            "fmt": int(tree["m_TextureFormat"]),
            "w": int(tree["m_Width"]),
            "h": int(tree["m_Height"]),
            "n": int(tree.get("m_MipCount") or 1),
            "filter": int(tree["m_TextureSettings"]["m_FilterMode"]),
            "bias": tree["m_TextureSettings"]["m_MipBias"]}


def extract_all_levels(data: bytes, *, fmt: int, w: int, h: int, n: int,
                       name: str) -> list:
    """全链提取（0..n-1 级；live _extract_chain 同约定：flipud 对齐渲染数组、
    字节账断言=链切片完整性结构检查、真 mip 不取 box）。"""
    lods, off = [], 0
    for i in range(n):
        lw, lh = level_dims(w, h, i)
        lb = level_bytes(fmt, lw, lh)
        lods.append(np.flipud(decode_level(data[off:off + lb], lw, lh, fmt)).copy())
        off += lb
    assert off == len(data), f"{name}: 字节账不合（{off} vs {len(data)}）"
    return lods


def classify_portrait(tree: dict, bundle: str, path_id: int) -> tuple[str, int]:
    """portrait 纹理 → (source 四态, n)。live chain_for_name 寻址判据同构：
    注册表分支=名在表**且**地址相等（变体件同址才复用——防同名劫持）；
    mips≤1 单级链（L0=PNG 派生，与链解码器格式域无关）；mips>1 且格式在
    decode_level 支持集外（如 BC7）→ unsupported（live 链解码 raise 同现状）。"""
    head = texture_head(tree)
    if head["n"] <= 1:
        return SOURCE_PORTRAIT, head["n"]
    if head["fmt"] not in SUPPORTED_FORMATS:
        return SOURCE_UNSUPPORTED, head["n"]
    addr = (bundle, int(path_id))
    if head["name"] in REGISTRY_NAMES and addr == MIP_CHAIN_ADDR.get(head["name"]):
        return SOURCE_REGISTRY, head["n"]
    return SOURCE_CHAIN, head["n"]


# ---------------------------------------------------------------------------
# 注册表提取 worker（单进程段：23 链 16 包，秒级；fold 进主建库的 decode 池
# 不划算——包集与 portrait 包几乎不相交，spawn 一次净进程更省）
# ---------------------------------------------------------------------------

def _find_texture(sf, name: str, path_id: int):
    """bundle 内纹理寻址（live supply.textures._find_texture 同判据逐字）：
    (bundle, path_id) 主键 + 名字校验，失配退名字扫描；双未命中=None（调用方
    响亮——typed 边界 GameAssetMissing 语义在 cold=raise）。"""
    cand = None
    objs = sf.objects
    it = objs.items() if hasattr(objs, "items") else enumerate(objs)
    for pid, o in it:
        try:
            if o.type.name != "Texture2D":
                continue
        except Exception:      # noqa: BLE001  非对象条目跳过（live 同形）
            continue
        if int(pid) == int(path_id):
            if o.read_typetree().get("m_Name") == name:
                return o
            cand = cand or o
    it = objs.items() if hasattr(objs, "items") else enumerate(objs)
    for _pid, o in it:
        try:
            if o.type.name == "Texture2D" and o.read_typetree().get("m_Name") == name:
                return o
        except Exception:      # noqa: BLE001
            continue
    return cand


def extract_registry_worker(payload):
    """单包 worker：一包一开，提取该包内的注册表链 → (bundle, [链账], wall)。

    链账={"name","lods"(uint8 全级),"filter","bias","path_id"}；包级异常整包
    报错（禁静默吞——portrait decode worker 判例）。"""
    win_s, bundle, entries = payload
    win = Path(win_s)
    import time
    t0 = time.time()
    try:
        env = load_bundle(win / bundle)
    except Exception as exc:  # noqa: BLE001
        return (bundle, [{"name": e[0], "error": f"bundle-open: "
                          f"{type(exc).__name__}: {exc}"} for e in entries],
                time.time() - t0)
    out = []
    sfs = list(iter_serialized(env))
    for name, _b, pid in entries:
        obj = None
        for sf in sfs:
            obj = _find_texture(sf, name, int(pid))
            if obj is not None and obj.read_typetree().get("m_Name") == name:
                break
            obj = None
        if obj is None:
            out.append({"name": name, "error":
                        f"texture-not-found path_id={pid}"})
            continue
        try:
            tree = obj.read_typetree()
            head = texture_head(tree)
            data = obj.read().get_image_data()
            lods = extract_all_levels(data, fmt=head["fmt"], w=head["w"],
                                      h=head["h"], n=head["n"], name=name)
            out.append({"name": name, "lods": lods, "filter": head["filter"],
                        "bias": float(head["bias"]), "path_id": int(obj.path_id),
                        "width": head["w"], "height": head["h"],
                        "mip_count": head["n"], "error": None})
        except Exception as exc:  # noqa: BLE001
            out.append({"name": name, "error":
                        f"extract: {type(exc).__name__}: {exc}"})
    return (bundle, out, time.time() - t0)


def registry_bundles() -> dict[str, list[tuple[str, str, int]]]:
    """MIP_CHAINS 按包分组（worker payload 形）。"""
    out: dict[str, list[tuple[str, str, int]]] = {}
    for name, bundle, pid in MIP_CHAINS:
        out.setdefault(bundle, []).append((name, bundle, pid))
    return out
