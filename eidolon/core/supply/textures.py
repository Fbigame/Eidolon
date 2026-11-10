"""textures — 纹理域（mip 链等纹理派生资产的内存面）。

mip 链游戏直提（consumer-arch 批10e，直提化战役收口）：bundle 内 Texture2D 序列化
真 mip 逐层 DXT 解码 → {lod: ndarray} 内存面——供给层 data 读点就此清零（此前=批2
data/mip_chains 语料直读，语料降档案；寻址表即语料 index.json 的 (bundle, path_id)
列，提取码逐字移植自语料配方，出处账=docs/notes/supply-v3.md 直提化节 + data README）。
真 mip 数据源依据：真 mip vs box 降采样 MAE 1.9→13 结构性差异（不取 box）；
mip0 双解码器逐位一致（渲染侧 PNG==游戏 mip0）。机制账（MipBias/LOD 公式/单例教训）
= paint/_mip_state.py mip 机制节。
"""
from __future__ import annotations

import logging
import numpy as np
import texture2ddecoder

from eidolon.core.infra.errors import GameAssetMissing
from eidolon.core.infra.resolve_asset_ref import get_resolver
from eidolon.core.supply.machine import item

logger = logging.getLogger(__name__)

_SUPPORTED_MIP_FORMATS = frozenset({10, 12, 3, 4, 13})
"""链解码格式域（=``_decode_level`` 臂集的声明面；域外 → ``GameAssetFormatUnsupported``
typed，B2 收口——原裸 ``ValueError(f"fmt {fmt}")`` 残留）。supply_index 的
``mip_extract.SUPPORTED_FORMATS`` 同域搬迁件；单测钉住两侧与 ``_decode_level``
臂集一致（加臂须同步加集）。"""

# 渲染集内 m_MipCount>1 全部纹理（2026-10-03 首版 12 卡取证；现手工注册表 23 条——
# 2026-10-30 补 2 条 nameplates + 5 条 C 集水印/横幅，含 SIcon）：(name, bundle, path_id)。
# CardRunes 三件/DK 族=essential 纹理包；REV_Icon=76981 desc 水印；Location_Mage=76981 肖像 _SecondTex。
_MIP_CHAINS: tuple[tuple[str, str, int], ...] = (
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
    # 2026-10-30 nameplates 身份链：覆盖审计 gap #1/#2（多族名牌板，见 docs/notes/mip-chain.md）。
    # 多族名牌板 1024²/11 级/filter=1/bias=0：`Multitribe_HSBG_Nameplates` 走 hand 帧静态
    # 材质槽（`Multi_RacePlate_mesh`，内容指纹派发面）；`_Spec` 走金框反射层 `_SpecTex`。
    ("Multitribe_HSBG_Nameplates", "essential_base_global-texture-1.unity3d", -695423779591078699),
    ("Multitribe_HSBG_Nameplates_Spec", "initial_base_global-8411aad9-texture-12.unity3d", -1623763288469544269),
    # 2026-10-30 mip 55 卡审计补齐：C 集新帧族的水印/可锻造横幅（V-pass wm_ref / 运行期槽），
    # 审计 gap #3-#7（2026-10-30 覆盖收口；账=docs/notes/mip-chain.md）。
    # PoAIcon / RLKIcon / CoreIcon_Even 走 desc 垫图 V-pass `_SecondTex`（watermark.py:721-723）；
    # Card_Inhand_Forgeable_Banner 走 Forgeable_Banner 运行期槽（raster.py:922）。
    ("PoAIcon", "initial_base_global-4bbced1c-texture-5.unity3d", -7214246542155689089),
    ("RLKIcon", "initial_base_global-4bbced1c-texture-4.unity3d", -6679188991779832773),
    ("CoreIcon_Even", "initial_base_global-4bbced1c-texture-3.unity3d", 5440975720784402096),
    # corpus 611 普查补：SCIcon（73434/105108 的 desc V-pass wm_ref；9 级 256²/2/−0.5）。
    ("SCIcon", "initial_base_global-4bbced1c-texture-4.unity3d", -8675088962978514531),
    ("Card_Inhand_Forgeable_Banner", "initial_base_global-8411aad9-texture-3.unity3d", 760062728052139132),
)

_MIP_REGISTRY: dict | None = None   # 进程 memo（卡不变；kits._KIT_CACHE 同法）
_MIP_PROBE_SEEN: set[str] = set()   # 探针报点去重（同名纹理进程级只报一次）
_MIP_NAMES = frozenset(e[0] for e in _MIP_CHAINS)
_MIP_CHAIN_ADDR = {e[0]: (e[1], int(e[2])) for e in _MIP_CHAINS}   # 手工链名→地址（变体判等）

# ---- 按需链（2026-10-20 portrait-mip-lod）：(bundle, path_id) → 链 ----
# 与 _MIP_CHAINS 分工：手工表=渲染集 12 卡原画 + 4 条符文/水印/地标（批10e 取证定案，
# 行为冻结）；本缓存=**消费点按需**（肖像 CardDef 链：纹理地址在消费前不可知，全量
# 预注册=127 条语料链常驻）。键=(bundle, path_id) 而非名字：名字只是派发键，地址才是
# 资产身份（同名不同地址=不同资产，防名字劫持——渲染铁律「共享查找目录按文件名活查询」）。
_CHAIN_REFS: dict[str, tuple[str, int]] = {}   # name → (bundle, path_id)（消费点登记）
_CHAIN_CACHE: dict[tuple[str, int], dict] = {}  # (bundle, path_id) → 链条目（进程 memo）
_REG_ENTRY: dict[str, dict] = {}   # 手工链的惰性 float 链条目（链名 → 采样器形态）


class LazyFloatChain:
    """uint8 mip 层 → 0..1 float64 的**逐层惰性**视图（层数组首次访问才物化并驻留）。

    sample_mip_rgba 只消费 `len(chain)`/`chain[i]`（层内双线性由 base_sampler 做），
    故视图足够。内存账：512²/10 级整链 float64 ≈ 11.2MB；1024²/11 级 ≈ 44.7MB（L0 独占
    33.5MB）。**全链 eager 物化**在 18 链注册面（当时；现 23 链）上是 +268MB/进程（门每 worker 各一份；
    1024² 三条各 44.7MB 是大头），而实际采样只碰得到 1–3 层——故注册面（raster._registry）
    与手工链（chain_for_name）都吃本视图。

    `peek(i)` = 物化但不驻留（内容指纹比较用：`meta_for` 每卡对同形桶逐条比 L0，
    驻留会把 11 条 512² 的 L0（92MB）+ 3 条 1024² 的 L0（100MB）全部钉死在进程里）；
    `chain[i]` 才入 `_cache`。两法同一表达式（`astype(float64)/255`），值逐位相同。
    """

    __slots__ = ("_lods", "_cache")

    def __init__(self, lods: list[np.ndarray]) -> None:
        self._lods = lods
        self._cache: dict[int, np.ndarray] = {}

    def __len__(self) -> int:
        return len(self._lods)

    def peek(self, i: int) -> np.ndarray:
        """物化第 i 层但**不入缓存**（调用方自持引用）；值面与 `self[i]` 逐位相同。"""
        return self._lods[i].astype(np.float64) / 255.0

    def __getitem__(self, i: int) -> np.ndarray:
        lev = self._cache.get(i)
        if lev is None:
            lev = self.peek(i)
            self._cache[i] = lev
        return lev

    def shape0(self) -> tuple[int, int]:
        """链 L0 的 (h, w)——结构守卫用，零物化（uint8 层本身）。"""
        return tuple(self._lods[0].shape[:2])


def note_texture_ref(tree: dict, bundle: str, path_id: int) -> None:
    """消费点登记纹理地址（廉价：typetree 已在手）；链解码留到 chain_for_name 真被调用。

    只登记 m_MipCount>1（=1 的纹理无链可提，登记也无消费面）。"""
    if (tree.get("m_MipCount") or 1) <= 1:
        return
    name = tree.get("m_Name")
    if not name:
        return
    _CHAIN_REFS[name] = (bundle, int(path_id))


def chain_for_name(name: str, addr: tuple[str, int] | None = None) -> dict | None:
    """按需真链：name → {"name","chain","filter","bias"}；未登记/无 mip → None。

    三层寻址：①手工链名集（`_MIP_CHAINS`）→ mip_registry 原条目（不重复解码）；
    ②消费点登记地址 → 直提并进程 memo；③无登记 → None（调用方落 mip0 直采降级，
    逐位等同旧行为）。
    真链 vs box 降采样 MAE 1.9→13 随层增长（结构性差异，box 不取）——按需链同样只取
    序列化真 mip（`_extract_chain` 单一解码面）。

    两条路都返回 `LazyFloatChain`（2026-10-30 mip-q1 lazy）：手工链此前是整链 eager
    float64（1024²/11 级 ≈ 44.7MB/条），18 链注册面（当时；现 23 链）≈ +268MB/进程 × 门 worker 数；
    惰性视图只在真被采到/被内容守卫比到的层付内存，值面逐位不变（同一 astype/255
    表达式，只是物化时点从"注册时"挪到"首次访问时"）。

    `addr`（可选，(bundle, path_id)）=**资产身份**优先于名字：同名不同地址是不同资产
    （locale 变体即此形，2026-10-23 portrait-locale）。手工链仅当地址与登记地址相等时
    复用（否则手工链会把 base 纹理的 mip 静默发给变体件）；不传 addr 时回落
    `_CHAIN_REFS` 消费点登记（旧行为等价）。"""
    if addr is None:
        addr = _CHAIN_REFS.get(name)
    if name in _MIP_NAMES and (addr is None or addr == _MIP_CHAIN_ADDR.get(name)):
        ent = _REG_ENTRY.get(name)
        raw = mip_registry().get(name)
        if raw is None:
            return None
        if ent is None:
            ent = {"name": name, "chain": LazyFloatChain(raw["lods"]),
                   "filter": raw["filter"], "bias": float(raw["bias"])}
            _REG_ENTRY[name] = ent
        return ent
    if addr is None:
        return None
    ent = _CHAIN_CACHE.get(addr)
    if ent is None or ent["name"] != name:
        raw = _extract_chain(name, addr[0], addr[1])
        ent = {"name": name, "chain": LazyFloatChain(raw["lods"]),
               "filter": raw["filter"], "bias": float(raw["bias"])}
        _CHAIN_CACHE[addr] = ent
    return ent


def _decode_level(data: bytes, w: int, h: int, fmt: int) -> np.ndarray:
    """单 mip 层 → RGBA uint8。fmt: 10=DXT1 12=DXT5 3=RGB24 4=RGBA32 13=RGBA4444。

    域外 fmt 的裸 ``ValueError`` 是纯函数背板（无资产身份可带）；上游
    ``_extract_chain`` 已按 ``_SUPPORTED_MIP_FORMATS`` 预检抛 typed，生产路径
    不可达。supply_index.mip_extract.decode_level 为本函数搬迁件（同 ValueError
    背板），漂移由 test_supply_index_mip 钉住。"""
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


def _level_dims(w: int, h: int, level: int) -> tuple[int, int]:
    return max(w >> level, 1), max(h >> level, 1)


def _level_bytes(fmt: int, w: int, h: int) -> int:
    if fmt in (10, 12):
        return ((w + 3) // 4) * ((h + 3) // 4) * (8 if fmt == 10 else 16)
    return w * h * (3 if fmt == 3 else 4)


def _find_texture(env, name: str, path_id: int, bundle: str = ""):
    """bundle 内纹理寻址：(bundle, path_id) 主键 + 名字校验，失配退名字扫描。

    path_id 是 SerializedFile 内地址（bundle 可含多文件——极端下跨文件同 path_id），
    故按手工链既有约定先命 path_id，再以 typetree 名复核；名字不符不采信（防同号
    异资产），退全扫描命名命中（报告 mip_chain_probe 同法）。

    typed 边界（设计 §5.3）：bundle 内无该纹理（path_id 与名字双未命中）→
    ``GameAssetMissing``。"""
    cand = None
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        if o.path_id == path_id:
            if (o.read_typetree().get("m_Name")) == name:
                return o
            cand = cand or o
    for o in env.objects:
        if o.type.name == "Texture2D" and o.read_typetree().get("m_Name") == name:
            return o
    raise GameAssetMissing(
        path=f"{bundle}::{name}" if bundle else name,
        message=f"asset_missing_in_game: bundle 内无纹理 {name!r}"
                f"（path_id={path_id}，候选={getattr(cand, 'path_id', None)}"
                + (f"，bundle={bundle}）" if bundle else "）"))


def _extract_chain(name: str, bundle: str, path_id: int) -> dict:
    """bundle 直提一条链：typetree 取格式/尺寸/滤波设置，.resS 流逐层切片解码。

    格式域守卫（B2 typed 收口）：fmt 在 ``_SUPPORTED_MIP_FORMATS`` 域外（如
    25=BC7 肖像，DMF_254t5 实证）→ ``GameAssetFormatUnsupported``（资产在场、
    离线链解码不可解——不再裸 ``ValueError``）。守卫在 ``get_image_data()``
    **之前**：域外纹理不付整图数据读取消耗。
    字节账断言（off==len(data)）=链切片完整性结构检查。Unity 纹理数据自底向上
    （OpenGL 行序）：flipud 对齐渲染侧数组（全部提取链同约定——内容指纹派发要求
    链与渲染数组同向）。"""
    env = get_resolver().open_bundle(bundle)
    obj = _find_texture(env, name, path_id, bundle)
    d = obj.read_typetree()
    fmt = d["m_TextureFormat"]
    w, h = d["m_Width"], d["m_Height"]
    n = d.get("m_MipCount") or 1
    s = d["m_TextureSettings"]
    if fmt not in _SUPPORTED_MIP_FORMATS:
        from eidolon.core.infra.errors import GameAssetFormatUnsupported

        raise GameAssetFormatUnsupported(
            path=f"{bundle}::{name}" if bundle else name,
            message=f"asset_format_unsupported: 纹理 {name!r} 的 mip 链格式域外"
                    f"（fmt={fmt}，mip_count={n}，{w}x{h}；离线解码域="
                    f"{sorted(_SUPPORTED_MIP_FORMATS)}）",
            cause=f"TextureFormat {fmt} 不在离线链解码域"
                  "（10=DXT1 12=DXT5 3=RGB24 4=RGBA32 13=RGBA4444）；"
                  "游戏内可渲染，离线不可解",
        )
    data = obj.read().get_image_data()
    lods, off = [], 0
    for i in range(n):
        lw, lh = _level_dims(w, h, i)
        lb = _level_bytes(fmt, lw, lh)
        lods.append(np.flipud(_decode_level(data[off:off + lb], lw, lh, fmt)).copy())
        off += lb
    assert off == len(data), f"{name}: 字节账不合（{off} vs {len(data)}）"
    return {"lods": lods, "filter": s["m_FilterMode"], "bias": s["m_MipBias"]}


@item("textures", "mip_registry")
def mip_registry() -> dict[str, dict]:
    """mip 链注册表：name → {"lods": [L0..Ln uint8 ndarray], "filter": int, "bias": float}。

    内容指纹派发的数据面（paint/_mip_state 消费）：渲染纹理数组与链 L0 位等者判同纹理。
    游戏直提一次性成本（16 bundle 读 + DXT 解码；bundle 字节由 resolver _envs LRU
    预算托管，链数组进程 memo）。恒可重现——冷缓存响亮失败/豁免面语义随之消亡。"""
    global _MIP_REGISTRY
    if _MIP_REGISTRY is None:
        _MIP_REGISTRY = {name: _extract_chain(name, bundle, pid)
                         for name, bundle, pid in _MIP_CHAINS}
    return _MIP_REGISTRY


_REF_ENTRY: dict[str, dict | None] = {}   # ref 串 → 条目|None（进程 memo；纹理资产卡不变）

# ---- seeded entry 查找面（A5：模块级注入位，"现有代码已是模块级 registry 模式
#      则顺着接"——本模块 _MIP_REGISTRY/_REG_ENTRY/_CHAIN_REFS 同族）----
# 契约（supply_index.seed.AtlasEntrySeed 注入；CardSeeder.open 安装 / close 卸载）：
#   lookup(ref) → 条目 dict | None | ENTRY_SEED_UNSET
#     - dict：seeded 链条目（{"name","chain","filter","bias"}，chain=LazyFloatChain
#       live 形——值面与 live 解析产物逐位一致：index 链=cold 期同一解码器提取）；
#     - None：已裁决无链（索引在账、纹理 m_MipCount<=1——零开包的「无 mip」判定）；
#     - ENTRY_SEED_UNSET：ref 不在索引账（override/composite/未知 ref 等）→ 落
#       既有 live 解析路（逐位不变）。
# 安装面=CardSeeder 生命周期（seeds 成功构建即装、close 即卸）；未安装时本面
# 零参与，live 路径行为逐位不变。
ENTRY_SEED_UNSET = object()
_ENTRY_SEED_LOOKUP = None


def set_entry_seed_lookup(fn) -> None:
    """安装 seeded entry 查找面（A5；显式注入——种子器/测试调用，产品 0.1.0 路径
    不调用）。覆盖式安装：单线程纪律下后装者生效。"""
    global _ENTRY_SEED_LOOKUP
    _ENTRY_SEED_LOOKUP = fn


def clear_entry_seed_lookup(fn=None) -> None:
    """卸载 seeded entry 查找面（fn 给定时仅当在位者 is fn 才卸——防晚开的旧
    seeder.close() 误卸新 seeder 的句柄）。"""
    global _ENTRY_SEED_LOOKUP
    if fn is None or _ENTRY_SEED_LOOKUP is fn:
        _ENTRY_SEED_LOOKUP = None


def entry_for_ref(ref: str) -> dict | None:
    """资产 ref（"名.ext:GUID" 形，色表/PPtr 同形）→ 真 mip 链条目（无 mip 返回 None）。

    用途=**运行期纹理槽**的 mip 派发（画面上某槽的 _MainTex 被类色图集覆写时，纹理身份
    只剩计划里的 atlas_ref；静态 kit 纹理走手工链内容指纹面，不经过本项）。

    判定＝纹理自身序列化：`m_MipCount<=1` → None（Trilinear 退化 Bilinear、bias 失效，
    mip0 直采与引擎同象——mip-chain 正典 §16 链账）；`>1` → 登记消费点地址
    （note_texture_ref）后按需直提真 mip（chain_for_name 同一解码面，进程 memo）。
    条目={"name","chain","filter","bias"}，filter/bias 取纹理序列化值（引擎采样器语义），
    不做任何拟合；LOD 公式与层间处理在 engine/raster.sample_mip_rgba（同一实现）。

    A5 seeded 查找面：`set_entry_seed_lookup` 安装的索引句柄先行——类色图集 ref 的
    mip 判定/链数据由 supply_index 账面供给（warm 零开包），未覆盖 ref
    （ENTRY_SEED_UNSET）落既有解析路（行为逐位不变）。未安装=纯 live。

    失效条件：ref 解析不到 Texture2D → 返回 None（mip0 直采降级，不红——纹理身份面
    解析失败属供给链边界，另有 resolve 侧响亮账）；纹理被重导入成 mips=1 时本项自动
    失效为 None（无手工清单要维护）。
    """
    if ref in _REF_ENTRY:
        return _REF_ENTRY[ref]
    if _ENTRY_SEED_LOOKUP is not None:
        verdict = _ENTRY_SEED_LOOKUP(ref)
        if verdict is not ENTRY_SEED_UNSET:
            _REF_ENTRY[ref] = verdict
            return verdict
    ent = None
    try:
        res = get_resolver().resolve(ref)
        bundle = (res.get("resolved") or {}).get("bundle")
        guid = (res.get("resolved") or {}).get("guid")
        if bundle and guid:
            obj, _ = get_resolver().container_get(bundle, guid)
            if obj is not None and obj.type.name == "Texture2D":
                tree = obj.read_typetree()
                if (tree.get("m_MipCount") or 1) > 1:
                    note_texture_ref(tree, bundle, obj.path_id)
                    ent = chain_for_name(tree.get("m_Name"))
    except Exception:  # noqa: BLE001  解析边界：失败=降级 mip0（渲染不变），不吞渲染错
        ent = None
    _REF_ENTRY[ref] = ent
    return ent


def mip_probe(tree: dict, *, source: str) -> None:
    """消费时 mip 探针（批24⑤）：配方纹理在手时 typetree 顺带读 m_MipCount，
    「带 mip 未注册」响亮报出（**非致命**——降级路径=直采 mip0 不动）。

    注册面=_MIP_CHAINS 名集（23 条 = 批10e 直提化定案的 16 条 37.0 渲染集取证链
    + 2026-10-30 补的两条多族名牌板链 + 四条 C 集水印/横幅链）；存量内容靠批18 M 段对拍 + 各轮 A/B 守
    （本探针不重复）。未注册纹理光栅面=mip0 直采降级路径（engine/raster.sample_tex_mip，
    逐位等同旧行为）照旧——本探针只把该现象从静默变响亮：首发 stderr 报点（进程级按名
    去重，_probe_cache 形态语言），游戏升版新增带 mip 纹理即现形。
    批24⑤ 首跑实测：语料 weaponCardTextures[1] 腿 Card_Inhand_Weapon_DeathKnight
    m_MipCount=11 未注册（手工链取证面=12 卡渲染集，类色图集消费面在其外）——
    降级路径在役实证，报点即证据位。
    调用位=supply 消费面 Texture2D 在手处（color.atlas / art.portrait）；
    触发演示与升版重跑入口=drift_probe_game_tables.py D 段。"""
    n = tree.get("m_MipCount") or 1
    if n <= 1:
        return
    name = tree.get("m_Name")
    if name in _MIP_NAMES or name in _CHAIN_REFS or name in _MIP_PROBE_SEEN:
        return
    _MIP_PROBE_SEEN.add(name)
    logger.warning(f"[MIP_PROBE] 带 mip 未注册：{name} m_MipCount={n}（source={source}）"
                   f"——**静态纹理**内容指纹派发面（手工链）不含此纹理，mip0 直采降级路径照旧；"
                   "运行期纹理槽（计划 atlas_ref）另有按需链 supply.textures.entry_for_ref"
                   "（2026-10-23 weapon-dk-frame）"
                   "（批24⑤；游戏升版新增带 mip 纹理须评估补链）")
