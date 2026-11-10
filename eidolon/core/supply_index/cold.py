"""cold — 冷侧建库（UnityPy；唯一允许 import UnityPy 的库面模块）。

流程（v4 设计 §3/§6，P1=portrait 闭环 + P2 车1=frame_kit 六面 + P2 车2=gems/
watermark/text 三域 + 全卡 plan 挂接 + P3=流水并行+介质卫兵）::

    install（resolve_context 显式 game/locale + context.install）→ game_id
    （build+manifest+DLL+constants stamp）
    → 原子 mkdir 锁 → 建库前 integrity 前置（现行代 bad>0=响亮，P3 件7）
    → bundle sha 后台池（64 包/片细片）×主线流水：manifest 表导入（catalog 392k
      流式 insert + bundle_deps）→ dbf CARD → 定向 locate（cards→CardDef→
      portrait/golden→变体→(bundle,guid)，单进程按包分组；locate 恒全卡）
    → hash 收割落 bundles → 解码（同一进程池按 bundle 分进程；一包一开读多对象；
      PNG blob 内容寻址落盘）
    → kit 提取（六帧族 actor prefab→六面 codec；ally 帧随走查产 gems 域项；
      actor 活表定位+PPtr 原始 pairs 解析；kit_extract.py 单点）
    → text 域（fontdefs 全表 JSON + locale 生效侧 TTF；全域项不进 plan_items）
    → watermark 域（dbf 四级裁决→ref→**guid 去重**解码→per-card items+plan 挂接）
    → color 域（Phase 1 A4：switcher probe + probe 族表全纹理槽图集；probe per-card
      挂接 role='color'，atlas=域级项不挂 plan）
    → plan 挂接（kit/kit_play/gems 全 role 落 plan_items；期望但未建落显式哨兵
      行 expect::*——D-决策 2 期望落账；text/color.atlas 除外——全域项/域级项）
    → plans/items/blobs 落库 → plan status 重算（expected-vs-built 单源语义，
      P0-1）→ 尾部 integrity 全量扫（0 bad 或 fail loud 不发布，P3 件7）
    → 尾部完整性发布门（expected-vs-built：full 代任何 expected 未 built=不发布；
      partial 代只挡 scope 内缺项，P0-2 返工 R1）→ current.json 原子切代

两种 build 形态：
- 全量（默认）：重建整代 DB（index.sqlite.build → os.replace 发布）；前后 integrity
  双卫兵（件7）。
- 定向（--cards/--sample）：locate 全量 + **只解**指定卡 portrait item，upsert 进
  现行代（部分代形态；meta.full_build=0）。game_id 不符=游戏已换代 → 响亮报错要求
  全量。定向 DB 驱动路零 kit/text/wm 面（域级项=全量 build 六件套——定向路不读
  manifest，保持 p50<1s 冷定向预算；warm auto 冷补只补 portrait 面，域级项缺失
  fail loud 列清单）；**不走 integrity 双卫兵**（p50<1s 预算；写面 _write_blob_atomic
  逐块复验兜底）。

铁律：container 读取一律 SerializedFile.container.container 原始 pairs（禁
env.container，225s 首触判例；kit/text 的 PPtr 解析=kit_extract._KitResolver 自写，
externals+bundle_deps 闭包）；UnityPy 非线程安全→并行按 bundle 分进程；blob 只落
缓存根（GB 级派生物，不入库）；库面零 env 旋钮；游戏身份全显式（game/locale 必填，
无 repo/env 解析链）。
"""
from __future__ import annotations

import collections
import io
import json
import os
import random
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.lock import CacheLock
from eidolon.core.supply_index.paths import SupplyLayout
from eidolon.core.supply_index._unity import (
    FALLBACK_UNITY_VERSION,
    container_pairs,
    iter_serialized,
    load_bundle,
    path_id_for,
    sha256_file,
)

MANIFEST_KEYS = {
    "catalog": "Assets/AssetManifest/base_assets_catalog.asset",
    "cards_map": "Assets/AssetManifest/AssetMaps/cards_map.asset",
    "platform": "Assets/AssetManifest/asset_catalog_platform_phone.asset",
}

# bundle sha 流水段细分片（包/片）：11k 包按 jobs 整除粗分有长尾（最大片决定收尾），
# 细片+submit 逐片调度负载均衡；片大小以 stat+hash 单片 ~0.2s 量级为度。
_HASH_CHUNK = 64

PORTRAIT_FIELD = {"portrait": "m_PortraitTexturePath",
                  "portrait_golden": "m_GoldenPortraitTexturePath"}
KIND_PREMIUM = {"portrait": "", "portrait_golden": "gold"}


@dataclass
class PortraitTarget:
    """一个 portrait 型 locator 的解析目标（decode 前形态）。"""
    card_id: str
    kind: str                    # portrait / portrait_golden
    ref: str
    guid: str
    bundle: str | None           # None=登记不在 catalog（status missing）
    locale: str


@dataclass
class CardLoc:
    card_id: str
    carddef: dict                # {ref,guid,bundle,cab,path_id,sha256}
    targets: list[PortraitTarget] = field(default_factory=list)


# ---------------------------------------------------------------------------
# game_id（必须保留 #9：含 DLL/constants stamp；活表变化=新代）
# ---------------------------------------------------------------------------

def compute_identity(win: Path, version: str | None, *, dll_path: Path) -> dict:
    """代身份四输入：build 版本串 + manifest stamp + platform + DLL/constants stamp。

    DLL stamp=Assembly-CSharp.dll sha256（活表常量的载体；P1 portrait 闭环零活表
    消费但仍进 game_id——必须保留 #9：活表变化=新代）。dll_path 显式传入
    （=GameContext.assembly_csharp——安装布局字面量归 contracts GameContext 单源，
    本模块不复制字面量）。"""
    manifest = win / "asset_manifest.unity3d"
    if not manifest.is_file():
        raise FileNotFoundError(f"asset_manifest.unity3d 缺失：{win}")
    dll = dll_path
    # P1 portrait 闭环零活表常量消费：constants stamp=空集 sha（P2 text codec 等接入
    # 时换成真实常量集派生——结构性占位，键面条款先落实）。
    constants_stamp = S.sha256_hex(b"[]")
    ident = {
        "build": version or "",
        "manifest_stamp": sha256_file(manifest),
        "platform": "pc",
        "dll_stamp": sha256_file(dll) if dll.is_file() else "missing",
        "constants_stamp": constants_stamp,
    }
    return {"game_id": S.sha256_hex(S.cjson(ident).encode("utf-8")), "identity": ident}


# ---------------------------------------------------------------------------
# manifest 表 + dbf（原始 pairs 读取；禁 env.container）
# ---------------------------------------------------------------------------

def read_manifest_tables(win: Path, locale: str) -> dict:
    """asset_manifest.unity3d + asset_manifest_<locale>.unity3d → 纯表 dict。"""
    env = load_bundle(win / "asset_manifest.unity3d")
    sf = next(iter_serialized(env))
    pairs = {k: pid for k, pid in container_pairs(sf)}
    objs = sf.objects

    def read(key: str):
        pid = pairs.get(key)
        if pid is None:
            raise KeyError(f"asset_manifest 缺 {key}（实际 keys={sorted(pairs)[:6]}…）")
        return objs[pid].read_typetree()

    cat = read(MANIFEST_KEYS["catalog"])
    bnames = cat["m_bundleNames"]
    catalog_pairs = [(a["guid"], bnames[a["bundleId"]]) for a in cat["m_assets"]]
    cm = read(MANIFEST_KEYS["cards_map"])["map"]
    cards_map = dict(zip(cm["keys"], cm["values"]))
    plat = read(MANIFEST_KEYS["platform"])
    plat_rows = [(a["baseGuid"], a["guid"], bnames[a["bundleId"]])
                 for a in plat["m_assets"]]

    # bundle_deps（P2 kit PPtr 闭包扫描用；allBundleNames×bundles.allDependencies）
    bd = read("Assets/AssetManifest/bundle_deps.asset")
    bd_names = bd["allBundleNames"]
    bundle_deps = {n: [bd_names[i] for i in d["allDependencies"] if bd_names[i] != n]
                   for n, d in zip(bd_names, bd["bundles"])}

    variant_rows: list[tuple[str, str, str, str, str]] = [
        (base, "platform_phone", "", guid, bundle)
        for base, guid, bundle in plat_rows
    ]
    if locale and locale not in ("enus", "", "global", "none"):
        lpath = win / f"asset_manifest_{locale}.unity3d"
        if not lpath.is_file():
            raise FileNotFoundError(f"locale manifest 缺失：{lpath}")
        lenv = load_bundle(lpath)
        lsf = next(iter_serialized(lenv))
        lpairs = {k: pid for k, pid in container_pairs(lsf)}
        lkey = next((k for k in lpairs
                     if k.lower().endswith(f"asset_catalog_locale_{locale}.asset")), None)
        if lkey is None:
            raise KeyError(f"{lpath.name} 内无 asset_catalog_locale_{locale}.asset")
        loc = lsf.objects[lpairs[lkey]].read_typetree()
        lnames = loc["m_bundleNames"]
        # locale 行排在 platform 行之后写入：变体叠加=platform→locale（locale 最后生效）
        variant_rows.extend(
            (a["baseGuid"], f"locale_{locale}", locale, a["guid"], lnames[a["bundleId"]])
            for a in loc["m_assets"])

    return {
        "catalog_pairs": catalog_pairs,
        "catalog": dict(catalog_pairs),
        "cards_map": cards_map,
        "variant_rows": variant_rows,
        "bundle_deps": bundle_deps,
    }


def read_dbf_card_ids(win: Path) -> tuple[dict[str, int], int]:
    """dbf.unity3d CARD 表 → ({card_id(m_noteMiniGuid): dbf_id(m_ID)}, 冲突数）。

    同 card_id 多行先到先得（冲突计数入 meta，不静默丢）。"""
    env = load_bundle(win / "dbf.unity3d")
    sf = next(iter_serialized(env))
    pairs = {k: pid for k, pid in container_pairs(sf)}
    key = next((k for k in pairs if k.upper().endswith("CARD.ASSET")), None)
    if key is None:
        raise KeyError("dbf.unity3d 内无 CARD.asset")
    recs = sf.objects[pairs[key]].read_typetree()["Records"]
    out: dict[str, int] = {}
    dup = 0
    for r in recs:
        cid = r.get("m_noteMiniGuid")
        if not cid:
            continue
        if cid in out:
            dup += 1
            continue
        out[cid] = int(r["m_ID"])
    return out, dup


def read_bundle_deps(win: Path) -> dict[str, list[str]]:
    """manifest bundle_deps.asset → {bundle: [依赖包]}（轻读；verify kit 冷腿用——
    全量 build 走 read_manifest_tables 一并读）。"""
    env = load_bundle(win / "asset_manifest.unity3d")
    sf = next(iter_serialized(env))
    pairs = {k: pid for k, pid in container_pairs(sf)}
    key = next((k for k in pairs if k.endswith("/bundle_deps.asset")), None)
    if key is None:
        raise KeyError("asset_manifest 内无 bundle_deps.asset")
    bd = sf.objects[pairs[key]].read_typetree()
    names = bd["allBundleNames"]
    return {n: [names[i] for i in d["allDependencies"] if names[i] != n]
            for n, d in zip(names, bd["bundles"])}


# ---------------------------------------------------------------------------
# 分进程 worker（spawn 可 pickle；UnityPy 非线程安全→按 bundle 分进程）
# ---------------------------------------------------------------------------

def _hash_bundles_worker(payload):
    win, names = payload
    win = Path(win)
    return [(n, (win / n).stat().st_size, (win / n).stat().st_mtime_ns,
             sha256_file(win / n)) for n in names]


def _encode_png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _write_blob_atomic(root: Path, payload_sha: str, data: bytes,
                       ext: str = ".png") -> tuple[str, bool]:
    """内容寻址 blob 原子落盘；返回 (相对缓存根路径, 是否本 build 落了字节)。

    P2 车2 修复（事故账 2026-11-07）：旧形「已存在且等长=复用」只验尺寸——同长
    异内容坏块被三次 build 静默复用（44fa2da6 判例：P1 build 写入即坏，穿车1/
    P2C2 复用存活）。现语义：
    - 已存在 → **读回 hash 复验**：相等=复用（False）；失配（含等长撞车）=重写
      覆盖（True）——复用面禁尺寸免检；
    - 新写 → tmp + os.replace + **读回复验**：盘上字节 hash ≠ 应写 payload sha
      → 删坏文件响亮 RuntimeError（写面禁静默——sha 与落盘字节在同一缓冲算出，
      失配即存储/过滤驱动层异常，禁止带病继续）。"""
    dst = SupplyLayout(root).blob_path(payload_sha, ext=ext)
    existed = dst.is_file()
    if existed and dst.stat().st_size == len(data) \
            and sha256_file(dst) == payload_sha:
        return str(dst.relative_to(root)), False
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dst.parent), prefix=".blob.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    actual = sha256_file(dst)
    if actual != payload_sha:
        try:
            os.unlink(dst)
        except OSError:
            pass
        raise RuntimeError(
            f"blob 写后复验失配 {dst.name}：盘上 {actual[:12]}… ≠ 应写 "
            f"{payload_sha[:12]}…（写面 sha 与字节同缓冲，失配=存储/过滤驱动层"
            "异常）——fail loud，禁止带病入账")
    return str(dst.relative_to(root)), True


def _extract_chain_for_worker(obj, img, bundle: str, root: Path) -> dict:
    """portrait 纹理 → 真 mip 链账（A5；worker 内联——包已开、img 已解码）。

    分类四态（mip_extract.classify_portrait，live chain_for_name 寻址判据同构）：
    - registry：链名在注册表且地址相等 → 不落自有 blob（warm 从 registry 项
      派生——live chain_for_name 注册表分支同源单链）；
    - portrait（m_MipCount<=1）：单级链，无自有链数据（L0=肖像像素）；
    - chain（mips>1 非注册表）：全链提取（0..n-1）→ **L0 位等验证**（UnityPy
      解码 vs texture2ddecoder 解码——「mip0 双解码器逐位一致」的逐纹理 cold
      期落实；失配落显式 L0 级，manifest "l0" 字段裁决 derived/explicit）→
      第 1..n-1 级（失配时 0..n-1）NPZ 落盘；
    - unsupported（mips>1 且格式在链解码器域外，如 BC7）：无链账（缺席可归因
      ——live 链解码对其 raise；调用方不建 item 不期望，账面列卡）。
    返回元数据 dict（lods 数组不返回——blob 已在盘，跨进程只搬 sha/账）。"""
    from eidolon.core.supply_index import mip_codec as MC
    from eidolon.core.supply_index import mip_extract as ME

    import numpy as np

    tree = obj.read_typetree()
    head = ME.texture_head(tree)
    source, n = ME.classify_portrait(tree, bundle, int(obj.path_id))
    meta = {"ok": True, "source": source, "name": head["name"],
            "filter": head["filter"], "bias": float(head["bias"]),
            "mip_count": n, "width": head["w"], "height": head["h"],
            "fmt": head["fmt"],
            "l0": "derived", "lods_stored": 0,
            "chain_payload_sha256": "", "chain_payload_size": 0,
            "chain_content_sha": "", "chain_blob_fresh": False, "error": None}
    if source == ME.SOURCE_UNSUPPORTED:
        # 格式域外（如 BC7）：不建 item 不期望（缺席可归因——live 链解码对其
        # raise，渲染失败属 live 现状；种子 token 不种 → live 兜底 → 同样
        # raise，失败模式逐位一致）；账面 mip_unsupported 显式列卡
        return meta
    if source != ME.SOURCE_CHAIN:
        # registry/portrait 源：无自有链数据（warm 派生面），blob=1 字节标记
        # （expected-vs-built 的 built 判据要求 item 带 ≥1 blob 行；内容恒定
        # → 跨卡 blob 去重）
        payload = MC.meta_marker_payload()
        payload_sha = S.sha256_hex(payload)
        _rel, fresh = _write_blob_atomic(root, payload_sha, payload, ext=".npz")
        meta.update({"chain_payload_sha256": payload_sha,
                     "chain_payload_size": len(payload),
                     "chain_blob_fresh": fresh})
        return meta
    data = obj.read().get_image_data()
    lods = ME.extract_all_levels(data, fmt=head["fmt"], w=head["w"],
                                 h=head["h"], n=head["n"], name=head["name"])
    l0_png = np.asarray(img.convert("RGBA"), dtype=np.uint8)
    l0_exact = (l0_png.shape == lods[0].shape
                and bool(np.array_equal(l0_png, lods[0])))
    stored = lods[1:]
    keys = [MC.level_key(i) for i in range(1, n)]
    if not l0_exact:
        meta["l0"] = "explicit"
        stored = lods[:]
        keys = [MC.level_key(i) for i in range(n)]
    payload = MC.encode_chain_npz(dict(zip(keys, stored)))
    payload_sha = S.sha256_hex(payload)
    _rel, fresh = _write_blob_atomic(root, payload_sha, payload, ext=".npz")
    meta.update({"lods_stored": len(stored),
                 "chain_payload_sha256": payload_sha,
                 "chain_payload_size": len(payload),
                 "chain_content_sha": MC.chain_content_sha(stored),
                 "chain_blob_fresh": fresh})
    return meta


def _decode_bundle_worker(payload):
    """单包 worker：一包一开，读多对象 → 解码 → PNG → blob 落盘。

    返回 (bundle, per-task results, container_rows, object_rows, wall)。对象级异常
    逐任务捕获记账（行级 error 字段），包级异常整包报错——建库异常禁静默吞
    （route 判例：containers 全空曾让整批静默退化）。

    A5 mip 面：kind='portrait' 任务顺带提取真 mip 链（同一包已开、img 已在
    手——免二次开包；per-worker guid memo 去重，共享纹理 128 卡一解）。链
    提取失败 ≠ portrait 解码失败：行级 mip.error 记账、portrait 照常出货
    （期望面缺口由 plan 哨兵行显式落账——fail loud 归 expected-vs-built 门）。"""
    win_s, cache_root_s, bundle, tasks = payload
    win = Path(win_s)
    from PIL import Image  # noqa: F401  (worker 内 import，spawn 进程自取)

    t0 = time.time()
    try:
        env = load_bundle(win / bundle)
    except Exception as exc:  # noqa: BLE001
        return (bundle,
                [{"card_id": t["card_id"], "kind": t["kind"], "guid": t["guid"],
                  "ok": False, "error": f"bundle-open: {type(exc).__name__}: {exc}"}
                 for t in tasks],
                [], [], time.time() - t0)
    container_rows = []
    sf_indexes = []
    for sf in iter_serialized(env):
        cab = Path(str(getattr(sf, "name", ""))).name.lower()
        pairs = container_pairs(sf)
        for i, (k, pid) in enumerate(pairs):
            container_rows.append((bundle, k, pid, i))
        idx: dict[str, int] = {}
        for k, pid in pairs:
            kl = k.lower()
            idx.setdefault(kl, pid)
            tail = kl.rsplit("/", 1)[-1]
            idx.setdefault(tail, pid)
        sf_indexes.append((cab, sf, idx))

    results = []
    object_rows = []
    root = Path(cache_root_s)
    mip_memo: dict[str, dict] = {}    # guid → 链账（同包共享纹理一解——A5）
    for t in tasks:
        guid = t["guid"].lower()
        hit = next(((cab, sf, idx) for cab, sf, idx in sf_indexes if guid in idx), None)
        if hit is None:
            results.append({"card_id": t["card_id"], "kind": t["kind"],
                            "guid": t["guid"], "ok": False,
                            "error": "guid-not-in-container"})
            continue
        cab, sf, idx = hit
        pid = idx[guid]
        try:
            obj = sf.objects[pid]
            if obj.type.name != "Texture2D":
                raise TypeError(f"期望 Texture2D，实际 {obj.type.name}")
            img = obj.read().image
            pixel_sha = S.sha256_hex(img.tobytes())
            png = _encode_png(img)
            payload_sha = S.sha256_hex(png)
            _rel, fresh = _write_blob_atomic(root, payload_sha, png)
            object_rows.append((bundle, cab, int(obj.path_id),
                                int(getattr(obj.type, "value", 0) or 0),
                                int(obj.byte_start), int(obj.byte_size)))
            mip = None
            if t["kind"] == "portrait":
                memo = mip_memo.get(guid)
                if memo is None:
                    try:
                        memo = _extract_chain_for_worker(obj, img, bundle, root)
                    except Exception as exc:  # noqa: BLE001 ——链失败≠portrait 失败
                        memo = {"ok": False,
                                "error": f"mip-extract: {type(exc).__name__}: {exc}"}
                    mip_memo[guid] = memo
                    mip = dict(memo)              # 首解：保留 blob_fresh 真值
                else:
                    mip = dict(memo)
                    if mip.get("ok"):
                        mip["chain_blob_fresh"] = False   # memo 复用面不计 fresh
            results.append({
                "card_id": t["card_id"], "kind": t["kind"], "guid": t["guid"],
                "ok": True, "bundle": bundle, "path_id": int(obj.path_id), "cab": cab,
                "width": img.width, "height": img.height, "mode": img.mode,
                "pixel_sha": pixel_sha, "payload_sha": payload_sha,
                "payload_size": len(png), "blob_fresh": fresh, "error": None,
                "mip": mip,
            })
        except Exception as exc:  # noqa: BLE001
            results.append({"card_id": t["card_id"], "kind": t["kind"],
                            "guid": t["guid"], "ok": False,
                            "error": f"decode: {type(exc).__name__}: {exc}"})
    return (bundle, results, container_rows, object_rows, time.time() - t0)


# ---------------------------------------------------------------------------
# locate（单进程全卡；282 carddef 包 3s 实测）
# ---------------------------------------------------------------------------

def build_variants_by_base(variant_rows: list, locale: str) -> dict[str, tuple[str, str]]:
    """base_guid → (变体 guid, bundle)：platform 先写、locale 后写覆盖
    （引擎加载次序 platform→locale；单层覆盖语义与游戏一致）。"""
    out: dict[str, tuple[str, str]] = {}
    for base, layer, loc, guid, bundle in variant_rows:
        if layer.startswith("locale_") and loc != locale:
            continue
        out[base] = (guid, bundle)
    return out


def _resolve_ref(ref: str, catalog: dict, variants_by_base: dict) -> tuple[str, str | None]:
    """「名:GUID」→ (resolved_guid, bundle)。命中变体即用，未命中落 base
    （引擎 GetRuntimeAssetVariant 同式；resolve_asset_ref 同判据）。"""
    _, guid = ref.rsplit(":", 1)
    g = guid.lower()
    v = variants_by_base.get(g)
    if v:
        vg, vb = v
        return vg, (catalog.get(vg) or vb)
    return g, catalog.get(g)


def locate_cards(win: Path, cards_map: dict, catalog: dict, variant_rows: list,
                 locale: str) -> dict[str, CardLoc]:
    """全卡定向 locate：cards→CardDef→portrait/golden→变体→(bundle,guid)。

    按包分组开 carddef bundle（一包一开读多对象）；portrait 指针 top 缺席扫组件
    （art._portrait_tex 同式）；path_id 留给 decode worker（包开着才有 pairs）。"""
    variants_by_base = build_variants_by_base(variant_rows, locale)
    refs = {}
    for cid, ref in cards_map.items():
        rg, rb = _resolve_ref(ref, catalog, variants_by_base)
        refs[cid] = (ref, rg, rb)

    by_bundle: dict[str | None, list[tuple[str, str, str]]] = collections.defaultdict(list)
    for cid, (ref, rg, rb) in refs.items():
        by_bundle[rb].append((cid, ref, rg))

    FIELDS = tuple(PORTRAIT_FIELD.values())
    locs: dict[str, CardLoc] = {}
    for rb, items in sorted(by_bundle.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        if rb is None:
            # carddef 本身登记缺失：卡级 missing 账（无包可开）
            for cid, ref, rg in items:
                locs[cid] = CardLoc(cid, {"ref": ref, "guid": rg, "bundle": "",
                                          "cab": "", "path_id": 0, "sha256": ""}, [])
            continue
        env = load_bundle(win / rb)
        sf = next(iter_serialized(env))
        pairs = {k: pid for k, pid in container_pairs(sf)}
        cab = Path(str(getattr(sf, "name", ""))).name.lower()
        for cid, ref, rg in items:
            pid = path_id_for(pairs, rg)
            if pid is None:
                locs[cid] = CardLoc(cid, {"ref": ref, "guid": rg, "bundle": rb,
                                          "cab": cab, "path_id": 0, "sha256": ""}, [])
                continue
            obj = sf.objects[pid]
            tt = obj.read_typetree()
            f = {k: tt[k] for k in FIELDS if tt.get(k)}
            if len(f) < len(FIELDS):
                for comp in tt.get("m_Component", []):
                    ptr = comp.get("component") or {}
                    cpid = ptr.get("m_PathID")
                    if not cpid:
                        continue
                    t2 = sf.objects[cpid].read_typetree()
                    for k in FIELDS:
                        if k not in f and t2.get(k):
                            f[k] = t2[k]
            raw_sha = S.sha256_hex(obj.get_raw_data())
            card = CardLoc(cid, {"ref": ref, "guid": rg, "bundle": rb, "cab": cab,
                                 "path_id": int(obj.path_id), "sha256": raw_sha}, [])
            for kind in PORTRAIT_FIELD:
                ref2 = f.get(PORTRAIT_FIELD[kind])
                if not ref2:
                    continue
                rg2, rb2 = _resolve_ref(ref2, catalog, variants_by_base)
                card.targets.append(PortraitTarget(cid, kind, ref2, rg2, rb2, locale))
            locs[cid] = card
    return locs


# ---------------------------------------------------------------------------
# DB 写入共用段
# ---------------------------------------------------------------------------

def _write_located(conn, locs: dict[str, CardLoc], dbf_ids: dict[str, int]) -> int:
    rows = []
    for cid, cl in sorted(locs.items()):
        rows.append((cid, dbf_ids.get(cid), cl.carddef["ref"], cl.carddef["guid"],
                     cl.carddef["bundle"], cl.carddef["cab"],
                     cl.carddef["path_id"], cl.carddef["sha256"] or None))
    conn.executemany("INSERT OR REPLACE INTO cards(card_id,dbf_id,carddef_ref,"
                     "carddef_guid,carddef_bundle,carddef_cab,carddef_path_id,"
                     "data_sha) VALUES(?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def _consume_decode_map(ex, payload, results: dict, container_rows: list,
                        object_rows: list, walls: dict) -> None:
    """消费 decode map 结果（ex.map 保序；行账聚合共用）。"""
    for (bundle, res, crows, orows, wall) in ex.map(
            _decode_bundle_worker, payload, chunksize=1):
        walls[bundle] = wall
        container_rows.extend(crows)
        object_rows.extend(orows)
        for r in res:
            results[(r["card_id"], r["kind"])] = r


def _decode_targets(win: Path, layout: SupplyLayout, targets: list[PortraitTarget],
                    jobs: int, *, pool=None) -> tuple[dict, list, list, dict[str, float]]:
    """目标按 bundle 分组分进程解码。返回 (results, container_rows, object_rows, walls)。

    pool=外部进程池（P3 流水建库：hash 池收敛后同池解码——worker 已热免二次
    spawn）；None=自建自关（原语义，wm 段/定向路）。"""
    by_target: dict[str, list[dict]] = collections.defaultdict(list)
    for tg in targets:
        if tg.bundle:
            by_target[tg.bundle].append(
                {"card_id": tg.card_id, "kind": tg.kind, "guid": tg.guid})
    payload = [(str(win), str(layout.root), b, ts)
               for b, ts in sorted(by_target.items(),
                                   key=lambda kv: -len(kv[1]))]
    results: dict[tuple[str, str], dict] = {}
    container_rows: list[tuple] = []
    object_rows: list[tuple] = []
    walls: dict[str, float] = {}
    if payload:
        if jobs <= 1 or len(payload) == 1:
            # 定向单包/单进程：免 spawn（设计 §1 冷定向 p50<1s——进程池启动 ~1s
            # 会吃满预算；UnityPy 非线程安全不涉并行，单包顺序解等价）
            for p in payload:
                bundle, res, crows, orows, wall = _decode_bundle_worker(p)
                walls[bundle] = wall
                container_rows.extend(crows)
                object_rows.extend(orows)
                for r in res:
                    results[(r["card_id"], r["kind"])] = r
        elif pool is not None:
            _consume_decode_map(pool, payload, results, container_rows,
                                object_rows, walls)
        else:
            with ProcessPoolExecutor(max_workers=jobs) as ex:
                _consume_decode_map(ex, payload, results, container_rows,
                                    object_rows, walls)
    return results, container_rows, object_rows, walls




def _write_locators(conn, locs: dict[str, CardLoc]) -> dict:
    """locate 时全量落 locator（resolve 结果=地址已知；cab/path_id 解码时回填）。

    absent（卡无该资产字段）不落行——计划内缺席不是 resolution 失败；
    missing（ref 不在 catalog）落行记账，warm 缺项面可见。"""
    rows = []
    lid = 0
    for cid in sorted(locs):
        cl = locs[cid]
        for kind in PORTRAIT_FIELD:
            tg = next((t for t in cl.targets if t.kind == kind), None)
            if tg is None:
                continue
            lid += 1
            if tg.bundle is None:
                status, lb, lc, lp = "missing", "", "", 0
            else:
                status, lb, lc, lp = "ok", tg.bundle, "", 0
            src = {"ref": tg.ref, "base_guid": tg.guid, "bundle": tg.bundle,
                   "locale": tg.locale, "kind": kind}
            rows.append((lid, kind, cid, tg.locale, KIND_PREMIUM[kind],
                         tg.ref, tg.guid, lb, lc, lp, status, S.cjson(src)))
    conn.executemany(
        "INSERT INTO locators(id,kind,subject,locale,premium,ref,guid,bundle,cab,"
        "path_id,status,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return {"locators": len(rows),
            "missing": sum(1 for r in rows if r[10] == "missing")}


def _write_decoded(conn, scope_locs: dict[str, "CardLoc"], results: dict,
                   bundle_sha: dict, loc: str, now: int,
                   container_rows=None, object_rows=None) -> dict:
    """解码产物落库：items/item_blobs/blobs/locator_inputs/objects/containers/
    plans/plan_items（按 decode scope 子集；幂等 upsert）。

    decode 失败（r.error）=该 kind 无 item、plan partial——fail loud 落到 warm
    缺项面，不在库面静默；同时落账 decode_errors（{kind: [{card_id, why}]}，
    随返回账面进 build 报告与 DB meta *_errors——P0-1 返工 R1：locator-ok 而解
    码失败不再只留 plans.status=partial 一处暗示）。"""
    cur = conn.cursor()
    items_rows, item_blob_rows, blob_rows = [], [], []
    locator_input_rows, plan_rows, plan_item_rows = [], [], []
    seen_payload: dict[str, int] = {}
    n_fresh = 0
    mip_fresh = 0
    mip_sentinels = 0
    mip_unsupported: list[dict] = []
    decode_errors: dict[str, list[dict]] = {k: [] for k in PORTRAIT_FIELD}
    decode_errors["portrait_mip"] = []
    for cid in sorted(scope_locs):
        cl = scope_locs[cid]
        plan_items = []
        for kind in PORTRAIT_FIELD:
            tg = next((t for t in cl.targets if t.kind == kind), None)
            r = results.get((cid, kind))
            if tg is not None and tg.bundle is not None and \
                    (r is None or not r.get("ok")):
                # locator-ok 而解码失败：无 item（warm expected-vs-built 缺项面
                # 响亮）+ 显式错误账（build 报告 + DB meta）
                decode_errors[kind].append(
                    {"card_id": cid, "kind": kind,
                     "why": (r or {}).get("error") or "no-result"})
                continue
            if tg is None or tg.bundle is None:
                continue      # absent/missing locator：计划内缺席（非 decode 失败）
            content_inputs = {"carddef": cl.carddef["sha256"] or "",
                              "portrait": r["pixel_sha"]}
            ik = S.item_key(card_id=cid, kind=kind, locale=loc,
                            premium=KIND_PREMIUM[kind], content_inputs=content_inputs)
            manifest = {
                "card_id": cid, "kind": kind, "locale": loc,
                "ref": tg.ref, "guid": tg.guid, "bundle": tg.bundle,
                "cab": r["cab"], "path_id": r["path_id"],
                "width": r["width"], "height": r["height"], "mode": r["mode"],
                "pixel_sha256": r["pixel_sha"],
                "payload_sha256": r["payload_sha"],
                "payload_size": r["payload_size"],
                "carddef": cl.carddef,
            }
            items_rows.append((ik, S.DOMAIN, S.ITEM_PORTRAIT,
                               S.cjson({"card_id": cid, "kind": kind}),
                               S.CODEC, S.CODEC_VERSION, S.cjson(manifest),
                               "ok", "asset",
                               S.cjson([{"bundle": tg.bundle, "cab": r["cab"],
                                         "path_id": r["path_id"], "guid": tg.guid,
                                         "bundle_sha256": bundle_sha.get(tg.bundle, ""),
                                         "object_sha256": r["pixel_sha"]}]),
                               S.cjson(content_inputs), now))
            bk = S.blob_key(portrait_content_sha=r["pixel_sha"])
            item_blob_rows.append((ik, bk, kind))
            blob_rows.append((bk, r["payload_sha"], r["payload_size"],
                              S.CODEC, S.CODEC_VERSION, now, now))
            seen_payload[r["payload_sha"]] = r["payload_size"]
            n_fresh += 1 if r.get("blob_fresh") else 0
            lrow = cur.execute(
                "SELECT id FROM locators WHERE kind=? AND subject=? AND locale=?",
                (kind, cid, tg.locale)).fetchone()
            if lrow is not None:
                lid = lrow["id"]
                cur.execute("UPDATE locators SET cab=?, path_id=? WHERE id=?",
                            (r["cab"], r["path_id"], lid))
                locator_input_rows.append((lid, tg.bundle, r["cab"], r["path_id"],
                                           bundle_sha.get(tg.bundle, ""), r["pixel_sha"]))
                locator_input_rows.append((lid, cl.carddef["bundle"], cl.carddef["cab"],
                                           cl.carddef["path_id"],
                                           bundle_sha.get(cl.carddef["bundle"], ""),
                                           cl.carddef["sha256"] or ""))
            plan_items.append((ik, kind))

        # ---- A5 mip 面：portrait_mip item + plan 挂接（portrait locator-ok 卡
        #     =期望人口；期望但未建=哨兵行 expect::portrait_mip——链提取失败
        #     ≠portrait 失败，fail loud 归 expected-vs-built 门；格式域外=
        #     可归因缺席，不期望不哨兵，账面显式列卡） ----
        r_n = results.get((cid, "portrait"))
        tg_n = next((t for t in cl.targets if t.kind == "portrait"), None)
        mip = (r_n or {}).get("mip") if (r_n is not None and r_n.get("ok")) else None
        if mip is not None and mip.get("ok") \
                and mip.get("source") == "unsupported":
            mip_unsupported.append(
                {"card_id": cid, "name": mip.get("name"),
                 "fmt": mip.get("fmt"), "mip_count": mip.get("mip_count")})
        elif mip is not None and mip.get("ok"):
            meta_sha = S.sha256_hex(S.cjson(
                {"name": mip["name"], "filter": mip["filter"],
                 "bias": mip["bias"], "mip_count": mip["mip_count"],
                 "source": mip["source"]}).encode("utf-8"))
            content_mip = {"carddef": cl.carddef["sha256"] or "",
                           "portrait": r_n["pixel_sha"],
                           "chain": mip["chain_content_sha"] or "",
                           "meta": meta_sha}
            mik = S.portrait_mip_item_key(card_id=cid, locale=loc,
                                          content_inputs=content_mip)
            mmanifest = {"card_id": cid, "kind": S.ITEM_PORTRAIT_MIP,
                         "locale": loc, "source": mip["source"],
                         "name": mip["name"], "filter": mip["filter"],
                         "bias": mip["bias"], "mip_count": mip["mip_count"],
                         "width": mip["width"], "height": mip["height"],
                         "l0": mip["l0"], "lods_stored": mip["lods_stored"],
                         "chain_payload_sha256": mip["chain_payload_sha256"],
                         "chain_payload_size": mip["chain_payload_size"],
                         "portrait_pixel_sha256": r_n["pixel_sha"],
                         "guid": r_n["guid"], "bundle": r_n["bundle"],
                         "cab": r_n["cab"], "path_id": r_n["path_id"]}
            items_rows.append((mik, S.DOMAIN, S.ITEM_PORTRAIT_MIP,
                               S.cjson({"card_id": cid,
                                        "kind": S.ITEM_PORTRAIT_MIP}),
                               "npz", 1, S.cjson(mmanifest), "ok", "asset",
                               S.cjson([{"bundle": r_n["bundle"],
                                         "cab": r_n["cab"],
                                         "path_id": r_n["path_id"],
                                         "guid": r_n["guid"],
                                         "bundle_sha256": bundle_sha.get(
                                             r_n["bundle"], ""),
                                         "object_sha256": mip["chain_content_sha"]
                                         or mip["chain_payload_sha256"]}]),
                               S.cjson(content_mip), now))
            mbk = S.blob_key_generic(domain="mip",
                                     content_sha=mip["chain_payload_sha256"],
                                     codec="npz")
            item_blob_rows.append((mik, mbk, "chain"))
            blob_rows.append((mbk, mip["chain_payload_sha256"],
                              mip["chain_payload_size"], "npz", 1, now, now))
            seen_payload[mip["chain_payload_sha256"]] = mip["chain_payload_size"]
            mip_fresh += 1 if mip.get("chain_blob_fresh") else 0
            plan_items.append((mik, "portrait_mip"))
        elif tg_n is not None and tg_n.bundle is not None:
            # portrait locator-ok 而链未建（链提取失败或 portrait 解码失败）——
            # 显式哨兵行（expected-vs-built 门 fail loud 名单）
            pk0 = S.plan_key(card_id=cid, locale=loc,
                             card_data_sha=cl.carddef["sha256"] or "")
            plan_item_rows.append((pk0, S.expected_item_key("portrait_mip"),
                                   "portrait_mip"))
            mip_sentinels += 1
            if mip is not None and not mip.get("ok"):
                decode_errors["portrait_mip"].append(
                    {"card_id": cid, "kind": "portrait_mip",
                     "why": mip.get("error") or "no-result"})
        pk = S.plan_key(card_id=cid, locale=loc,
                        card_data_sha=cl.carddef["sha256"] or "")
        # 初值仍按 portrait 单轴（尾部 recompute_plan_status 统一重算为
        # expected-vs-built 语义——golden/kit/gems/watermark 同权，P0-1）
        status = "complete" if any(role == "portrait" for _ik, role in plan_items) \
            else "partial"
        plan_rows.append((pk, cid, S.cjson({}), status, S.PLAN_VERSION,
                          cl.carddef["sha256"] or "", now))
        for ik, role in plan_items:
            plan_item_rows.append((pk, ik, role))

    cur.executemany(
        "INSERT OR REPLACE INTO items(item_key,domain,item,params_json,codec,"
        "codec_version,manifest_json,status,source_kind,source_json,"
        "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", items_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO item_blobs(item_key,blob_key,role) VALUES(?,?,?)",
        item_blob_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO blobs(blob_key,payload_sha256,size,codec,codec_version,"
        "last_used,created_at) VALUES(?,?,?,?,?,?,?)", blob_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locator_inputs(locator_id,bundle,cab,path_id,"
        "bundle_sha256,object_sha256) VALUES(?,?,?,?,?,?)", locator_input_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO containers(bundle,key,path_id,ord) VALUES(?,?,?,?)",
        container_rows or [])
    cur.executemany(
        "INSERT OR REPLACE INTO objects(bundle,cab,path_id,class_id,byte_start,"
        "byte_size) VALUES(?,?,?,?,?,?)", object_rows or [])
    cur.executemany(
        "INSERT OR REPLACE INTO plans(plan_key,card_id,options_json,status,plan_version,"
        "card_data_sha,created_at) VALUES(?,?,?,?,?,?,?)", plan_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO plan_items(plan_key,item_key,role) VALUES(?,?,?)",
        plan_item_rows)
    return {"locators": 0, "missing": 0,
            "items": len(items_rows), "blobs_unique": len(seen_payload),
            "blob_bytes_unique": sum(seen_payload.values()),
            "blob_fresh": n_fresh, "plans": len(plan_rows),
            "mip_blob_fresh": mip_fresh, "mip_sentinels": mip_sentinels,
            "mip_unsupported": mip_unsupported,
            "decode_errors": decode_errors}


# ---------------------------------------------------------------------------
# kit 提取（P2 车1：frame_kit 六面 codec；cold 面 UnityPy——kit_extract 单点）
# ---------------------------------------------------------------------------

def ctx_strings_path(win: Path, loc: str) -> Path:
    """GLOBAL.txt 路径（races 面；GameContext.strings_dir 同式——data_win 上溯两级）。"""
    return win.parent.parent / "Strings" / loc / "GLOBAL.txt"


def build_kits(conn, win: Path, layout: SupplyLayout, tables: dict, loc: str,
               now: int, dbf_ids: dict[str, int], bundle_sha: dict[str, str],
               jobs: int) -> dict:
    """六帧族 kit 提取→六面 blob 落盘→items/item_blobs/blobs/locators 落库。

    kit=卡不变游戏结构：item 键无 card_id（params={"frame"}），content_inputs=
    {actor_ref 活表串, guid, kit 六面内容聚合 sha}——全部**解析后产物 sha**
    （m_StreamData 判例：raw 序列化字节是假内容身份）。plan 挂接=车2 全卡装配域
    （车1 不落 plan_items）。actor 活表=dll_reflect（ActorNames.s_actorAssets）。
    kit 失败=该族无 item（warm 缺项面响亮）+账面 kit_errors 显式记，不炸全量
    （P1 portrait decode 行级记账同口径）。"""
    from concurrent.futures import ProcessPoolExecutor

    from eidolon.core.supply_index import kit_codec as KC
    from eidolon.core.supply_index.kit_extract import (
        FRAME_SPECS_KIT,
        extract_kit_worker,
    )

    from eidolon.core.infra.dll_reflect import tables as dll_tables

    slots = dll_tables.actor_slots
    variants_by_base = build_variants_by_base(tables["variant_rows"], loc)
    catalog = tables["catalog"]
    dbf_inv: dict[int, str] = {}
    for cid, did in dbf_ids.items():
        dbf_inv.setdefault(int(did), cid)

    targets = []
    for frame, spec in sorted(FRAME_SPECS_KIT.items()):
        try:
            ref = slots[spec["slot"]]
        except KeyError:
            raise KeyError(f"kit {frame}: actor 活表无槽 {spec['slot']}"
                           f"（语料现役帧缺位——先核 ActorNames 活表）") from None
        rg, rb = _resolve_ref(ref, catalog, variants_by_base)
        if not rb:
            raise KeyError(f"kit {frame}: actor ref 不在 catalog（{ref}）")
        targets.append({"frame": frame, "spec": spec, "actor_ref": ref,
                        "guid": rg, "bundle": rb,
                        "card_id": dbf_inv.get(int(spec["dbf"])),
                        "dbf_id": int(spec["dbf"])})

    strings_txt = ctx_strings_path(win, loc)
    payload = [(str(win), str(layout.root), t["frame"], t["spec"], t["actor_ref"],
                t["guid"], t["bundle"], t["card_id"], t["dbf_id"],
                tables["bundle_deps"], str(strings_txt)) for t in targets]
    results: list[dict] = []
    if len(payload) == 1 or jobs <= 1:
        for p in payload:
            results.append(extract_kit_worker(p))
    else:
        # kit worker 的 bundle env 零驱逐（dep 闭包驻留）——并发压 2 为内存保险
        with ProcessPoolExecutor(max_workers=max(1, min(2, len(payload)))) as ex:
            results.extend(ex.map(extract_kit_worker, payload, chunksize=1))
    return _write_kit_items(conn, targets, results, bundle_sha, loc, now)


def _write_kit_items(conn, targets: list[dict], results: list[dict],
                     bundle_sha: dict[str, str], loc: str, now: int, *,
                     item_name: str = S.ITEM_KIT) -> dict:
    """kit 结果落库（items/item_blobs/blobs/locators/locator_inputs/containers/
    objects；幂等 upsert；blob 行 codec=json/npz/png 按 face 派生）。

    item_name（A6）：ITEM_KIT（全帧族）/ ITEM_KIT_LIGHT（轻走查 kit）——同一
    codec 两 item 名（kit_item_key 的 frame→key memo 以 item 过滤，不撞键）。

    P2 车2 gems 挂接：ally 帧结果的 gems 账→gems 域 items（卡不变域，键无
    card_id；plan 挂接=_link_shared_items）。"""
    from eidolon.core.supply_index import kit_codec as KC

    cur = conn.cursor()
    lid0 = int(cur.execute("SELECT COALESCE(MAX(id),0) FROM locators").fetchone()[0])
    items_rows, ib_rows, blob_rows, loc_rows, li_rows = [], [], [], [], []
    cont_rows, obj_rows = [], []
    seen_payload: dict[str, int] = {}
    errors = []
    gem_items = 0
    by_frame = {t["frame"]: t for t in targets}
    for r in results:
        t = by_frame[r["frame"]]
        lid = lid0 + len(loc_rows) + 1
        if not r.get("ok"):
            errors.append({"frame": r["frame"], "error": r.get("error")})
            src = {"frame": t["frame"], "ref": t["actor_ref"], "guid": t["guid"],
                   "bundle": t["bundle"], "locale": loc}
            loc_rows.append((lid, "kit", t["frame"], loc, "", t["actor_ref"],
                             t["guid"], t["bundle"], "", 0, "missing", S.cjson(src)))
            continue
        # ---- gems 域 items（ally 帧随走查产出；缺 gem=gem_issues 记账无 item） ----
        for gem, acc in (r.get("gems") or {}).items():
            content_inputs = {"kit": r["kit_content_sha"],
                              "pixel": acc["pixel_sha256"]}
            gik = S.gem_item_key(gem=gem, locale=loc, content_inputs=content_inputs)
            gmanifest = {"gem": gem, "locale": loc, "node": acc["node"],
                         "slot": acc["slot"], "fname": acc["fname"],
                         "width": acc["width"], "height": acc["height"],
                         "mode": acc["mode"],
                         "pixel_sha256": acc["pixel_sha256"],
                         "payload_sha256": acc["payload_sha256"],
                         "payload_size": acc["size"],
                         "source_kit": {"frame": "ally",
                                        "kit_content_sha256": r["kit_content_sha"]}}
            gsrc = [{"bundle": None, "cab": "", "path_id": None, "guid": None,
                     "bundle_sha256": "", "object_sha256": acc["pixel_sha256"],
                     "note": f"ally kit 走查槽 {acc['node']}:{acc['slot']}"}]
            items_rows.append((gik, S.DOMAIN_GEMS, gem, S.cjson({}), S.CODEC,
                               S.CODEC_VERSION, S.cjson(gmanifest), "ok", "asset",
                               S.cjson(gsrc), S.cjson(content_inputs), now))
            gbk = S.blob_key_generic(domain="gems", content_sha=acc["pixel_sha256"],
                                     codec=S.CODEC)
            ib_rows.append((gik, gbk, f"gem:{gem}"))
            blob_rows.append((gbk, acc["payload_sha256"], acc["size"], S.CODEC,
                              S.CODEC_VERSION, now, now))
            seen_payload[acc["payload_sha256"]] = acc["size"]
            gem_items += 1
        for gi in r.get("gem_issues") or []:
            errors.append({"frame": r["frame"], "gem_issue": gi})
        faces = r["faces"]
        content_inputs = {"actor_ref": t["actor_ref"], "guid": t["guid"],
                          "kit": r["kit_content_sha"]}
        if item_name == S.ITEM_KIT:
            ik = S.kit_item_key(frame=t["frame"], locale=loc,
                                content_inputs=content_inputs)
        else:
            ik = S.kit_light_item_key(frame=t["frame"], locale=loc,
                                      content_inputs=content_inputs)
        manifest = {"frame": t["frame"], "item": item_name, "locale": loc,
                    "prefab_ref": t["actor_ref"], "guid": t["guid"],
                    "bundle": r["prefab_bundle"], "faces": faces,
                    "kit_content_sha256": r["kit_content_sha"],
                    "counts": r["counts"], "excluded": r["excluded"],
                    "capture": r.get("capture") or "kit_extract"}
        source = [{"bundle": r["prefab_bundle"], "cab": "",
                   "path_id": r["root_path_id"], "guid": t["guid"],
                   "bundle_sha256": bundle_sha.get(r["prefab_bundle"], ""),
                   "object_sha256": r["kit_content_sha"]}]
        items_rows.append((ik, S.DOMAIN_FRAMES, item_name,
                           S.cjson({"frame": t["frame"]}),
                           KC.KIT_CODEC, KC.KIT_CODEC_VERSION, S.cjson(manifest),
                           "ok", "asset", S.cjson(source),
                           S.cjson(content_inputs), now))
        for face in KC.JSON_FACES:
            bk = KC.blob_key(face=face, content_sha=faces[face]["content_sha256"],
                             blob_codec="json")
            ib_rows.append((ik, bk, face))
            blob_rows.append((bk, faces[face]["payload_sha256"],
                              faces[face]["size"], "json", 1, now, now))
            seen_payload[faces[face]["payload_sha256"]] = faces[face]["size"]
        for face in KC.EXTRA_JSON_FACES:            # A6：races/mesh_refs 扩展面
            if face not in faces:
                continue
            bk = KC.blob_key(face=face, content_sha=faces[face]["content_sha256"],
                             blob_codec="json")
            ib_rows.append((ik, bk, face))
            blob_rows.append((bk, faces[face]["payload_sha256"],
                              faces[face]["size"], "json", 1, now, now))
            seen_payload[faces[face]["payload_sha256"]] = faces[face]["size"]
        fa = faces["arrays"]
        if fa["payload_sha256"]:
            bk = KC.blob_key(face="arrays", content_sha=fa["content_sha256"],
                             blob_codec="npz")
            ib_rows.append((ik, bk, "arrays"))
            blob_rows.append((bk, fa["payload_sha256"], fa["size"], "npz", 1,
                              now, now))
            seen_payload[fa["payload_sha256"]] = fa["size"]
        for fname, facc in faces["textures"].items():
            bk = KC.blob_key(face="texture", content_sha=facc["pixel_sha256"],
                             blob_codec="png")
            ib_rows.append((ik, bk, f"texture:{fname}"))
            blob_rows.append((bk, facc["payload_sha256"], facc["size"], "png", 1,
                              now, now))
            seen_payload[facc["payload_sha256"]] = facc["size"]
        src = {"frame": t["frame"], "ref": t["actor_ref"], "guid": t["guid"],
               "bundle": r["prefab_bundle"], "locale": loc,
               "kit_content_sha": r["kit_content_sha"]}
        loc_rows.append((lid, "kit", t["frame"], loc, "", t["actor_ref"], t["guid"],
                         r["prefab_bundle"], "", r["root_path_id"], "ok",
                         S.cjson(src)))
        li_rows.append((lid, r["prefab_bundle"], "", r["root_path_id"],
                        bundle_sha.get(r["prefab_bundle"], ""),
                        r["kit_content_sha"]))
        cont_rows.extend(r.get("container_rows") or [])
        obj_rows.extend(r.get("object_rows") or [])

    cur.executemany(
        "INSERT OR REPLACE INTO items(item_key,domain,item,params_json,codec,"
        "codec_version,manifest_json,status,source_kind,source_json,"
        "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", items_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO item_blobs(item_key,blob_key,role) VALUES(?,?,?)",
        ib_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO blobs(blob_key,payload_sha256,size,codec,codec_version,"
        "last_used,created_at) VALUES(?,?,?,?,?,?,?)", blob_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locators(id,kind,subject,locale,premium,ref,guid,"
        "bundle,cab,path_id,status,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        loc_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locator_inputs(locator_id,bundle,cab,path_id,"
        "bundle_sha256,object_sha256) VALUES(?,?,?,?,?,?)", li_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO containers(bundle,key,path_id,ord) VALUES(?,?,?,?)",
        cont_rows or [])
    cur.executemany(
        "INSERT OR REPLACE INTO objects(bundle,cab,path_id,class_id,byte_start,"
        "byte_size) VALUES(?,?,?,?,?,?)", obj_rows or [])
    return {"kits": len(results), "kit_errors": errors,
            "kit_blobs_unique": len(seen_payload),
            "kit_blob_bytes": sum(seen_payload.values()),
            "gem_items": gem_items}


# ---------------------------------------------------------------------------
# supplement 域（Phase 1 A6：特源/附件 kit + kit_light + font_asset_params；
# live 提取 harness——supplement_extract 单点）
# ---------------------------------------------------------------------------

def build_supplements(conn, win: Path, layout: SupplyLayout, loc: str, now: int,
                      bundle_sha: dict[str, str], jobs: int,
                      *, game_root: Path | None = None) -> dict:
    """supplement 域建库：live 提取 harness（独立子进程，route off）顺序捕获
    特源四 kit（ally_premium/trinket/anomaly/bacon）+ kit_light×9 + ability_kit×2
    + badges/btf/ornaments/ta_supplement/material_state/portrait_uv1 +
    font_asset_params → content 寻址 blob → items 落库。

    域定性：**卡不变全局项**（items 落库不挂 plan——text/color.atlas/mip_registry
    同款记账）；kit 六面件与 kit_extract 同 codec（KIT_CODEC_VERSION 2），
    warm kit()/kit_light()/kit_races()/kit_mesh_refs() 访问器供货；supp parts 件
    codec='supp'，warm 域访问器供货、seed 重组 live 形状。单项失败=error 记账
    （item 缺建 → warm 缺项响亮 → seed 该 token 不种回 live），不炸全量。
    注入面：KitRecon 六帧族 kit faces 读回（worker 免重走查——ta/portrait_uv1
    的 kit memo 依赖面）。"""
    from concurrent.futures import ProcessPoolExecutor

    from eidolon.core.supply_index import supp_codec as SC
    from eidolon.core.supply_index import supplement_extract as SE

    kit_manifests = {json.loads(r["params_json"])["frame"]: r["manifest_json"]
                     for r in conn.execute(
                         "SELECT item_key, params_json, manifest_json FROM items "
                         "WHERE domain=? AND item=?",
                         (S.DOMAIN_FRAMES, S.ITEM_KIT))}
    payload = {"win": str(game_root or win.parent.parent),
               "cache_root": str(layout.root), "locale": loc,
               "kit_manifests": kit_manifests}
    t0 = time.time()
    if jobs <= 1:
        result = SE.capture_worker(payload)
    else:
        with ProcessPoolExecutor(max_workers=1) as ex:
            result = ex.submit(SE.capture_worker, payload).result()
    wall = time.time() - t0

    acc = {"injected": result.get("injected") or [],
           "supplement_errors": result.get("errors") or []}
    for key, item_name in (("kits", S.ITEM_KIT), ("kit_light", S.ITEM_KIT_LIGHT)):
        rows = [r for r in (result.get(key) or []) if r.get("ok")]
        targets = []
        for r in rows:
            ident = r.get("identity") or {}
            targets.append({"frame": r["frame"], "spec": {},
                            "actor_ref": ident.get("actor_ref") or "",
                            "guid": ident.get("guid") or "",
                            "bundle": ident.get("bundle") or "",
                            "card_id": ident.get("card_id"),
                            "dbf_id": ident.get("dbf_id")})
        acc[f"{item_name}_items"] = _write_kit_items(
            conn, targets, rows, bundle_sha, loc, now, item_name=item_name)
    acc["supp_items"] = _write_supp_items(conn, result.get("supp") or [],
                                          bundle_sha, loc, now)
    acc["wall_supplement_s"] = round(wall, 2)
    return acc


def _write_supp_items(conn, supp_accounts: list[dict],
                      bundle_sha: dict[str, str], loc: str, now: int) -> dict:
    """supp parts 账 → items/item_blobs/blobs/locators 落库（幂等 upsert）。

    blob role：json/npz=part 名；png/bin=part:fname。blob_key=泛化公式
    （domain|content_sha|codec|version）——png/bin 的 content=像素/文件字节 sha，
    跨 item 同内容共 payload 文件（内容寻址去重）。"""
    from eidolon.core.supply_index import supp_codec as SC

    cur = conn.cursor()
    lid0 = int(cur.execute("SELECT COALESCE(MAX(id),0) FROM locators").fetchone()[0])
    items_rows, ib_rows, blob_rows, loc_rows = [], [], [], []
    seen_payload: dict[str, int] = {}
    for acc in supp_accounts:
        domain, item, params = acc["domain"], acc["item"], acc["params"]
        parts = acc["parts"]
        content = {"supp": acc["content_sha"]}
        ik = S.supplement_item_key(domain=domain, item=item, params=params,
                                   locale=loc, content_inputs=content)
        manifest = {"item": item, "locale": loc, "parts": parts,
                    "supp_content_sha256": acc["content_sha"],
                    **{k: v for k, v in acc.get("source", {}).items()}}
        items_rows.append((ik, domain, item, S.cjson(params), SC.SUPP_CODEC,
                           SC.SUPP_CODEC_VERSION, S.cjson(manifest), "ok",
                           "asset",
                           S.cjson([{"bundle": None, "cab": "", "path_id": None,
                                     "guid": None, "bundle_sha256": "",
                                     "object_sha256": acc["content_sha"],
                                     "note": acc.get("source", {}).get("source",
                                                                       "")}]),
                           S.cjson(content), now))
        for pname, p in parts.items():
            if p["kind"] in ("png", "bin"):
                for fname, meta in p["files"].items():
                    bk = S.blob_key_generic(domain=domain,
                                            content_sha=meta["content_sha256"],
                                            codec=p["kind"])
                    ib_rows.append((ik, bk, f"{pname}:{fname}"))
                    blob_rows.append((bk, meta["payload_sha256"], meta["size"],
                                      p["kind"], 1, now, now))
                    seen_payload[meta["payload_sha256"]] = meta["size"]
            else:
                bk = S.blob_key_generic(domain=domain,
                                        content_sha=p["content_sha256"],
                                        codec=p["kind"])
                ib_rows.append((ik, bk, pname))
                blob_rows.append((bk, p["payload_sha256"], p["size"],
                                  p["kind"], 1, now, now))
                seen_payload[p["payload_sha256"]] = p["size"]
        subject = item + (":" + json.dumps(params, sort_keys=True)
                          if params else "")
        loc_rows.append((lid0 + len(loc_rows) + 1, item, subject, loc, "", "",
                         "", "", "", 0, "ok",
                         S.cjson({"item": item, "params": params,
                                  "capture": "supplement-harness"})))
    cur.executemany(
        "INSERT OR REPLACE INTO items(item_key,domain,item,params_json,codec,"
        "codec_version,manifest_json,status,source_kind,source_json,"
        "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        items_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO item_blobs(item_key,blob_key,role) VALUES(?,?,?)",
        ib_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO blobs(blob_key,payload_sha256,size,codec,"
        "codec_version,last_used,created_at) VALUES(?,?,?,?,?,?,?)", blob_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locators(id,kind,subject,locale,premium,ref,"
        "guid,bundle,cab,path_id,status,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        loc_rows)
    return {"items": len(items_rows),
            "blob_bytes": sum(seen_payload.values()),
            "blobs_unique": len(seen_payload)}


# ---------------------------------------------------------------------------
# text 域（P2 车2：fontdefs JSON + locale 生效侧 TTF；全域项不进 plan_items）
# ---------------------------------------------------------------------------

def build_text_items(conn, win: Path, layout: SupplyLayout, tables: dict,
                     loc: str, now: int, bundle_sha: dict[str, str],
                     ctx=None) -> dict:
    """text 域提取→落库（fontdefs 一件 JSON + 每字体一件 TTF）。

    域定性：**卡不变全域供给**——items 落库（domain='text'），warm 走域访问器
    text()（缓存一次/进程）；不 per-card 挂 plan_items（26MB 级 TTF 面每卡重复
    拖运=架构错位；装配束全域段一次供货）。TTF 内容身份=**文件字节 sha**（文件
    即产物）。表级失败=结构错误响亮；单字体失败=errors 记账无 item。"""
    from eidolon.core.supply_index import text_codec as TC
    from eidolon.core.supply_index.text_extract import extract_fonts

    zhcat = {base: (guid, bundle) for base, _layer, locale, guid, bundle
             in tables["variant_rows"] if locale == "zhcn"}
    gge = ctx.globalgamemanagers if ctx is not None else None
    res = ctx.resources if ctx is not None else None
    fonts = extract_fonts(win, catalog=tables["catalog"], zhcat=zhcat,
                          bundle_deps=tables["bundle_deps"],
                          gge_path=gge, resources_path=res)
    fontdefs = fonts["fontdefs"]
    ttfs = fonts["ttfs"]

    cur = conn.cursor()
    lid0 = int(cur.execute("SELECT COALESCE(MAX(id),0) FROM locators").fetchone()[0])
    items_rows, ib_rows, blob_rows, loc_rows, li_rows = [], [], [], [], []
    n_text_items = 0

    # ---- fontdefs 全表 item ----
    data = TC.encode_fontdefs(fontdefs)
    payload_sha = S.sha256_hex(data)
    content_sha = TC.fontdefs_content_sha(fontdefs)
    tik = S.fontdefs_item_key(locale=loc, content_inputs={"fontdefs": content_sha})
    touched = sorted({side.get("bundle") for rec in fontdefs.values()
                      for side in (rec.get("enus"), rec.get("zhcn"))
                      if isinstance(side, dict) and side.get("bundle")})
    manifest = {"locale": loc, "n_entries": len(fontdefs),
                "entries": sorted(fontdefs),
                "ttf_errors": fonts["errors"],
                "payload_sha256": payload_sha, "payload_size": len(data)}
    items_rows.append((tik, S.DOMAIN_TEXT, S.ITEM_FONTDEFS, S.cjson({}), "json",
                       S.CODEC_VERSION, S.cjson(manifest), "ok", "asset",
                       S.cjson([{"bundle": b, "cab": "", "path_id": None,
                                 "guid": None,
                                 "bundle_sha256": bundle_sha.get(b, "")}
                                for b in touched]),
                       S.cjson({"fontdefs": content_sha}), now))
    bk = TC.fontdefs_blob_key(payload_sha)
    ib_rows.append((tik, bk, TC.ROLE_FONTDEFS))
    blob_rows.append((bk, payload_sha, len(data), "json", S.CODEC_VERSION, now, now))
    _write_blob_atomic(layout.root, payload_sha, data, ext=".json")
    lid = lid0 + len(loc_rows) + 1
    loc_rows.append((lid, "fontdefs", "table", loc, "", "", "", touched[0] if
                     touched else "", "", 0, "ok",
                     S.cjson({"n_entries": len(fontdefs), "locale": loc})))
    n_text_items += 1

    # ---- 每字体 TTF item（locale 生效侧；文件 sha=内容身份） ----
    for name in sorted(ttfs):
        raw = ttfs[name]
        file_sha = TC.ttf_content_sha(raw)
        fik = S.font_ttf_item_key(font=name, locale=loc,
                                  content_inputs={"ttf": file_sha})
        rec = fontdefs.get(name) or {}
        side = rec.get("zhcn") if isinstance(rec.get("zhcn"), dict) \
            and rec["zhcn"].get("guid") else rec.get("enus")
        side_tag = "zhcn" if isinstance(rec.get("zhcn"), dict) \
            and rec["zhcn"].get("guid") else "enus(base)"
        fmanifest = {"font": name, "locale": loc, "side": side_tag,
                     "bytes": len(raw),
                     "guid": (side or {}).get("guid"),
                     "bundle": (side or {}).get("bundle"),
                     "font_object": (side or {}).get("font_object"),
                     "payload_sha256": file_sha, "payload_size": len(raw)}
        items_rows.append((fik, S.DOMAIN_TEXT, S.ITEM_FONT_TTF,
                           S.cjson({"font": name}), "ttf", S.CODEC_VERSION,
                           S.cjson(fmanifest), "ok", "asset",
                           S.cjson([{"bundle": (side or {}).get("bundle"),
                                     "cab": "", "path_id": None,
                                     "guid": (side or {}).get("guid"),
                                     "bundle_sha256": bundle_sha.get(
                                         (side or {}).get("bundle") or "", ""),
                                     "object_sha256": file_sha}]),
                           S.cjson({"ttf": file_sha}), now))
        fbk = TC.ttf_blob_key(file_sha)
        ib_rows.append((fik, fbk, TC.ROLE_TTF))
        blob_rows.append((fbk, file_sha, len(raw), "ttf", S.CODEC_VERSION, now, now))
        rel, _fresh = _write_blob_atomic(layout.root, file_sha, raw, ext=".ttf")
        lid = lid0 + len(loc_rows) + 1
        loc_rows.append((lid, "font_ttf", name, loc, "",
                         f"{name}.ttf:{(side or {}).get('guid') or ''}",
                         (side or {}).get("guid") or "",
                         (side or {}).get("bundle") or "", "", 0, "ok",
                         S.cjson({"side": side_tag, "blob": rel})))
        li_rows.append((lid, (side or {}).get("bundle") or "", "", 0,
                        bundle_sha.get((side or {}).get("bundle") or "", ""),
                        file_sha))
        n_text_items += 1

    cur.executemany(
        "INSERT OR REPLACE INTO items(item_key,domain,item,params_json,codec,"
        "codec_version,manifest_json,status,source_kind,source_json,"
        "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", items_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO item_blobs(item_key,blob_key,role) VALUES(?,?,?)",
        ib_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO blobs(blob_key,payload_sha256,size,codec,codec_version,"
        "last_used,created_at) VALUES(?,?,?,?,?,?,?)", blob_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locators(id,kind,subject,locale,premium,ref,guid,"
        "bundle,cab,path_id,status,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        loc_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locator_inputs(locator_id,bundle,cab,path_id,"
        "bundle_sha256,object_sha256) VALUES(?,?,?,?,?,?)", li_rows)
    return {"text_items": n_text_items, "fontdefs": 1, "ttfs": len(ttfs),
            "ttf_bytes": sum(len(b) for b in ttfs.values()),
            "errors": fonts["errors"]}


# ---------------------------------------------------------------------------
# watermark 域（P2 车2：四级裁决→ref→纹理；guid 去重解码）
# ---------------------------------------------------------------------------

def build_watermarks(conn, win: Path, layout: SupplyLayout, loc: str, now: int,
                     bundle_sha: dict[str, str], tables: dict, jobs: int,
                     *, pool=None) -> dict:
    """水印域建库：dbf 四级裁决（wm_extract）→ 每卡 ref → catalog resolve →
    **guid 去重**解码（1,016 卡共享 ~20 张纹理——每 guid 解码一次，防 25k 重复
    decode 吃穿 build 预算）→ per-card items+plan_items 落库。

    ref=None=无水印（缺席是裁决事实，无 locator 行）；ref 不在 catalog=locator
    status='missing'（warm 缺项面可见）；解码失败=locator ok 无 item（fail loud
    账面 wm_errors）。pool=主建库流水池（件2：与 hash/decode 同池，worker 已热）。"""
    from eidolon.core.infra.dll_reflect import tables as dll_tables

    from eidolon.core.supply_index import wm_extract as WM

    wm_inputs = WM.read_dbf_watermark_inputs(win)
    year_icon = dll_tables.year_icon_even
    variants_by_base = build_variants_by_base(tables["variant_rows"], loc)
    catalog = tables["catalog"]

    # 每卡 ref（cards 表为面积：全量/部分代一致）
    card_rows = conn.execute(
        "SELECT card_id, dbf_id, data_sha FROM cards ORDER BY card_id").fetchall()
    ref_of: dict[str, str | None] = {}
    for r in card_rows:
        ref_of[r["card_id"]] = WM.resolve_watermark_ref(r["dbf_id"], wm_inputs,
                                                        year_icon)
    with_ref = {cid: ref for cid, ref in ref_of.items() if ref}
    # ref → (guid, bundle)（_resolve_ref 同款变体叠加）
    guid_of: dict[str, tuple[str, str | None]] = {}
    for cid, ref in with_ref.items():
        guid_of[cid] = _resolve_ref(ref, catalog, variants_by_base)

    # guid 去重解码（synthetic card key=wm::<guid>；_decode_targets 按包分组）
    uniq: dict[str, tuple[str, str | None]] = {}
    for cid, (g, b) in guid_of.items():
        uniq.setdefault(g, (g, b))
    targets = [PortraitTarget(card_id=f"wm::{g}", kind="watermark", ref="", guid=g,
                              bundle=b, locale=loc)
               for g, (g, b) in sorted(uniq.items()) if b]
    unresolved = [g for g, (_g, b) in uniq.items() if not b]
    results, crows, orows, _w = _decode_targets(win, layout, targets, jobs,
                                                pool=pool)

    cur = conn.cursor()
    lid0 = int(cur.execute("SELECT COALESCE(MAX(id),0) FROM locators").fetchone()[0])
    items_rows, ib_rows, blob_rows, loc_rows, li_rows = [], [], [], [], []
    plan_item_rows = []
    seen_payload: dict[str, int] = {}
    n_fresh = 0
    wm_errors: list[dict] = []
    plan_keys = {r["card_id"]: S.plan_key(card_id=r["card_id"], locale=loc,
                                          card_data_sha=r["data_sha"] or "")
                 for r in card_rows}
    data_shas = {r["card_id"]: (r["data_sha"] or "") for r in card_rows}
    n_items = 0
    for cid in sorted(with_ref):
        ref = with_ref[cid]
        g, b = guid_of[cid]
        lid = lid0 + len(loc_rows) + 1
        if b is None:
            src = {"ref": ref, "guid": g, "locale": loc}
            loc_rows.append((lid, "watermark", cid, loc, "", ref, g, "", "", 0,
                             "missing", S.cjson(src)))
            continue
        r = results.get((f"wm::{g}", "watermark"))
        if r is None or not r.get("ok"):
            wm_errors.append({"card_id": cid, "guid": g,
                              "why": (r or {}).get("error", "no-result")})
            loc_rows.append((lid, "watermark", cid, loc, "", ref, g, b, "", 0,
                             "ok", S.cjson({"ref": ref, "locale": loc})))
            continue
        content_inputs = {"carddef": data_shas[cid], "ref": ref,
                          "watermark": r["pixel_sha"]}
        ik = S.watermark_item_key(card_id=cid, locale=loc,
                                  content_inputs=content_inputs)
        manifest = {"card_id": cid, "kind": "watermark", "locale": loc,
                    "ref": ref, "guid": g, "bundle": b, "cab": r["cab"],
                    "path_id": r["path_id"], "width": r["width"],
                    "height": r["height"], "mode": r["mode"],
                    "pixel_sha256": r["pixel_sha"],
                    "payload_sha256": r["payload_sha"],
                    "payload_size": r["payload_size"]}
        items_rows.append((ik, S.DOMAIN_WATERMARK, S.ITEM_WATERMARK,
                           S.cjson({"card_id": cid}), S.CODEC, S.CODEC_VERSION,
                           S.cjson(manifest), "ok", "asset",
                           S.cjson([{"bundle": b, "cab": r["cab"],
                                     "path_id": r["path_id"], "guid": g,
                                     "bundle_sha256": bundle_sha.get(b, ""),
                                     "object_sha256": r["pixel_sha"]}]),
                           S.cjson(content_inputs), now))
        bk = S.blob_key_generic(domain="watermark", content_sha=r["pixel_sha"],
                                codec=S.CODEC)
        ib_rows.append((ik, bk, "watermark"))
        blob_rows.append((bk, r["payload_sha"], r["payload_size"], S.CODEC,
                          S.CODEC_VERSION, now, now))
        seen_payload[r["payload_sha"]] = r["payload_size"]
        n_fresh += 1 if r.get("blob_fresh") else 0
        src = {"ref": ref, "guid": g, "bundle": b, "locale": loc,
               "pixel_sha256": r["pixel_sha"]}
        loc_rows.append((lid, "watermark", cid, loc, "", ref, g, b, r["cab"],
                         r["path_id"], "ok", S.cjson(src)))
        li_rows.append((lid, b, r["cab"], r["path_id"], bundle_sha.get(b, ""),
                        r["pixel_sha"]))
        plan_item_rows.append((plan_keys[cid], ik, "watermark"))
        n_items += 1
    for g in unresolved:
        wm_errors.append({"guid": g, "why": "ref-not-in-catalog"})

    cur.executemany(
        "INSERT OR REPLACE INTO items(item_key,domain,item,params_json,codec,"
        "codec_version,manifest_json,status,source_kind,source_json,"
        "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", items_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO item_blobs(item_key,blob_key,role) VALUES(?,?,?)",
        ib_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO blobs(blob_key,payload_sha256,size,codec,codec_version,"
        "last_used,created_at) VALUES(?,?,?,?,?,?,?)", blob_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locators(id,kind,subject,locale,premium,ref,guid,"
        "bundle,cab,path_id,status,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        loc_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locator_inputs(locator_id,bundle,cab,path_id,"
        "bundle_sha256,object_sha256) VALUES(?,?,?,?,?,?)", li_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO plan_items(plan_key,item_key,role) "
        "VALUES(?,?,?)", plan_item_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO containers(bundle,key,path_id,ord) VALUES(?,?,?,?)",
        crows or [])
    cur.executemany(
        "INSERT OR REPLACE INTO objects(bundle,cab,path_id,class_id,byte_start,"
        "byte_size) VALUES(?,?,?,?,?,?)", orows or [])
    return {"wm_items": n_items, "wm_cards_with_ref": len(with_ref),
            "wm_unique_guids": len(uniq), "wm_errors": wm_errors,
            "wm_blobs_unique": len(seen_payload),
            "wm_blob_bytes": sum(seen_payload.values()),
            "wm_blob_fresh": n_fresh}


# ---------------------------------------------------------------------------
# color 域（Phase 1 A4：switcher 表 + 每 (family, ct) 图集；color_extract 单点）
# ---------------------------------------------------------------------------

def build_color_items(conn, win: Path, layout: SupplyLayout, tables: dict,
                      loc: str, now: int, bundle_sha: dict[str, str],
                      jobs: int, *, pool=None) -> dict:
    """color 域建库：switcher 表 probe item + probe 族表全纹理槽图集 atlas items。

    域定性（任务单 A4）：probe=**卡不变全域项**（12 族槽位表，compile 期类色
    pick 无条件读）——items 落库 + per-card plan 挂接（_link_color_probe，已知
    卡型卡 role='color'，kit/gems 同款）；atlas=按 (family, ct) 的域级项——
    **每纹理槽一行** item（guid 共享纹理走 blob 内容寻址天然去重；解码任务
    guid 去重防同纹理重复解码）、**不挂 plan_items**（212 纹理槽 per-card 重复
    挂接=架构错位，text 域同款记账；消费=类色写点单槽 + kit 提取全槽扇出，
    warm 访问器供给）。

    槽位分类（本函数记账，不算错误）：ref 无效（空串占位）=计划内缺席无行；
    resolved 对象非 Texture2D（faction* 材质族）=参数域外 material-slot 记账
    （按槽位计）；解码失败=color_errors（响亮账面，warm 缺项面可见）。probe
    表读取失败=raise（链根失效属语料级事件，live「失效即红」同纪律）。
    pool=主建库流水池（件2：worker 已热）。"""
    from eidolon.core.supply_index import color_extract as CE

    variants_by_base = build_variants_by_base(tables["variant_rows"], loc)
    catalog = tables["catalog"]

    # ---- probe item（switcher 表直读；键序=typetree 序） ----
    t_probe0 = time.time()
    probe = CE.read_switcher_probe(win, catalog, variants_by_base)
    families = probe["families"]
    probe_content_sha = S.sha256_hex(S.cjson(families).encode("utf-8"))
    probe_payload = json.dumps(families, ensure_ascii=False)   # 落盘保序（live 键序）
    probe_payload_sha = S.sha256_hex(probe_payload.encode("utf-8"))
    content_inputs = {"ref": CE.SWITCHER_REF, "probe": probe_content_sha}
    pik = S.color_probe_item_key(locale=loc, content_inputs=content_inputs)
    manifest = {"item": S.ITEM_COLOR_PROBE, "locale": loc,
                "switcher": {"ref": CE.SWITCHER_REF, "guid": probe["guid"],
                             "bundle": probe["bundle"], "cab": probe["cab"],
                             "path_id": probe["path_id"]},
                "families": {k: len(v) for k, v in families.items()},
                "payload_sha256": probe_payload_sha,
                "payload_size": len(probe_payload)}
    cur = conn.cursor()
    lid0 = int(cur.execute("SELECT COALESCE(MAX(id),0) FROM locators").fetchone()[0])
    probe_blob_key = S.blob_key_generic(domain=S.DOMAIN_COLOR,
                                        content_sha=probe_payload_sha,
                                        codec="json")
    _write_blob_atomic(layout.root, probe_payload_sha,
                       probe_payload.encode("utf-8"), ext=".json")
    cur.executemany(
        "INSERT OR REPLACE INTO items(item_key,domain,item,params_json,codec,"
        "codec_version,manifest_json,status,source_kind,source_json,"
        "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        [(pik, S.DOMAIN_COLOR, S.ITEM_COLOR_PROBE, S.cjson({}), "json",
          S.CODEC_VERSION, S.cjson(manifest), "ok", "asset",
          S.cjson([{"bundle": probe["bundle"], "cab": probe["cab"],
                    "path_id": probe["path_id"], "guid": probe["guid"],
                    "bundle_sha256": bundle_sha.get(probe["bundle"], ""),
                    "object_sha256": probe_content_sha}]),
          S.cjson(content_inputs), now)])
    cur.execute(
        "INSERT OR REPLACE INTO item_blobs(item_key,blob_key,role) VALUES(?,?,?)",
        (pik, probe_blob_key, "probe"))
    cur.execute(
        "INSERT OR REPLACE INTO blobs(blob_key,payload_sha256,size,codec,"
        "codec_version,last_used,created_at) VALUES(?,?,?,?,?,?,?)",
        (probe_blob_key, probe_payload_sha, len(probe_payload), "json",
         S.CODEC_VERSION, now, now))
    lid = lid0 + 1
    src = {"ref": CE.SWITCHER_REF, "guid": probe["guid"],
           "bundle": probe["bundle"], "locale": loc,
           "families": {k: len(v) for k, v in families.items()}}
    cur.execute(
        "INSERT OR REPLACE INTO locators(id,kind,subject,locale,premium,ref,"
        "guid,bundle,cab,path_id,status,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (lid, "color_probe", "table", loc, "", CE.SWITCHER_REF, probe["guid"],
         probe["bundle"], probe["cab"], probe["path_id"], "ok", S.cjson(src)))
    cur.execute(
        "INSERT OR REPLACE INTO locator_inputs(locator_id,bundle,cab,path_id,"
        "bundle_sha256,object_sha256) VALUES(?,?,?,?,?,?)",
        (lid, probe["bundle"], probe["cab"], probe["path_id"],
         bundle_sha.get(probe["bundle"], ""), probe_content_sha))
    t_probe = time.time() - t_probe0

    # ---- atlas targets（probe 族表全槽；ref 有效槽→变体解析；**槽位逐条记账**，
    #      解码任务=guid 去重（同纹理多槽一解——BG anomaly/trinket 族 45-50 槽同
    #      纹理），item 落库按槽位逐条（每 (family, ct) 一行——warm atlas 参数域
    #      全覆盖，guid 共享走 blob 内容寻址天然去重）） ----
    t_atlas0 = time.time()
    slot_list: list[tuple[str, int, str, str, str | None]] = []
    n_slots = n_empty = 0
    for fam, refs in families.items():
        for ct, ref in enumerate(refs):
            n_slots += 1
            if not (isinstance(ref, str) and ":" in ref):
                n_empty += 1
                continue
            rg, rb = _resolve_ref(ref, catalog, variants_by_base)
            slot_list.append((fam, ct, ref, rg, rb))
    uniq: dict[str, tuple[str, int, str, str | None]] = {}
    for fam, ct, ref, rg, rb in slot_list:
        uniq.setdefault(rg, (fam, ct, ref, rb))
    by_target: dict[str, list[dict]] = collections.defaultdict(list)
    for rg, (fam, ct, ref, rb) in uniq.items():
        if rb:
            by_target[rb].append({"family": fam, "ct": ct, "ref": ref,
                                  "guid": rg})
    payload = [(str(win), str(layout.root), b, ts)
               for b, ts in sorted(by_target.items(), key=lambda kv: -len(kv[1]))]
    results: list[dict] = []
    crows: list[tuple] = []
    orows: list[tuple] = []
    if payload:
        if jobs <= 1 or len(payload) == 1:
            for p in payload:
                bundle, res, cr, orr, _wall = CE.decode_color_atlas_worker(p)
                results.extend(res)
                crows.extend(cr)
                orows.extend(orr)
        elif pool is not None:
            for (bundle, res, cr, orr, _wall) in pool.map(
                    CE.decode_color_atlas_worker, payload, chunksize=1):
                results.extend(res)
                crows.extend(cr)
                orows.extend(orr)
        else:
            with ProcessPoolExecutor(max_workers=jobs) as ex:
                for (bundle, res, cr, orr, _wall) in ex.map(
                        CE.decode_color_atlas_worker, payload, chunksize=1):
                    results.extend(res)
                    crows.extend(cr)
                    orows.extend(orr)
    result_by_guid = {r["guid"]: r for r in results}

    # ---- atlas items 落库（**每槽一行**；材质槽=参数域外记账；解码失败=color_errors） ----
    items_rows, ib_rows, blob_rows, loc_rows, li_rows = [], [], [], [], []
    seen_payload: dict[str, int] = {}
    n_fresh = 0
    n_material = 0
    n_mipped = 0
    color_errors: list[dict] = []
    for fam, ct, ref, rg, rb in slot_list:
        r = result_by_guid.get(rg)
        lid = lid0 + 1 + len(loc_rows) + 1
        if r is None or not r.get("ok"):
            why = (r or {}).get("error") or \
                ("ref-not-in-catalog" if rb is None else "no-result")
            if why.startswith("material-slot:"):
                n_material += 1          # 材质族槽=参数域外（color.atlas 仅纹理族）
                continue
            color_errors.append({"family": fam, "ct": ct, "ref": ref, "why": why})
            loc_rows.append((lid, "color_atlas", f"{fam}[{ct}]", loc, "", ref,
                             rg, rb or "", "", 0, "missing",
                             S.cjson({"ref": ref, "guid": rg, "why": why})))
            continue
        content_inputs_a = {"ref": ref, "guid": rg, "pixel": r["pixel_sha"]}
        aik = S.color_atlas_item_key(family=fam, ct=ct, locale=loc,
                                     content_inputs=content_inputs_a)
        mip_acc = r.get("mip") or {}
        amanifest = {"item": S.ITEM_COLOR_ATLAS, "family": fam, "ct": ct,
                     "locale": loc, "ref": ref, "guid": rg,
                     "bundle": r["bundle"], "cab": r["cab"],
                     "path_id": r["path_id"], "width": r["width"],
                     "height": r["height"], "mode": r["mode"],
                     "pixel_sha256": r["pixel_sha"],
                     "payload_sha256": r["payload_sha"],
                     "payload_size": r["payload_size"],
                     "mip": {"count": mip_acc.get("count"),
                             "name": mip_acc.get("name"),
                             "filter": mip_acc.get("filter"),
                             "bias": mip_acc.get("bias"),
                             "chain_payload_sha256":
                                 mip_acc.get("chain_payload_sha256") or "",
                             "chain_payload_size":
                                 mip_acc.get("chain_payload_size") or 0,
                             "chain_content_sha":
                                 mip_acc.get("chain_content_sha") or "",
                             "error": mip_acc.get("error")}}
        items_rows.append((aik, S.DOMAIN_COLOR, S.ITEM_COLOR_ATLAS,
                           S.cjson({"family": fam, "ct": ct}), S.CODEC,
                           S.CODEC_VERSION, S.cjson(amanifest), "ok", "asset",
                           S.cjson([{"bundle": r["bundle"], "cab": r["cab"],
                                     "path_id": r["path_id"], "guid": rg,
                                     "bundle_sha256": bundle_sha.get(r["bundle"], ""),
                                     "object_sha256": r["pixel_sha"]}]),
                           S.cjson(content_inputs_a), now))
        abk = S.blob_key_generic(domain=S.DOMAIN_COLOR,
                                 content_sha=r["pixel_sha"], codec=S.CODEC)
        ib_rows.append((aik, abk, "atlas"))
        blob_rows.append((abk, r["payload_sha"], r["payload_size"], S.CODEC,
                          S.CODEC_VERSION, now, now))
        seen_payload[r["payload_sha"]] = r["payload_size"]
        n_fresh += 1 if r.get("blob_fresh") else 0
        if mip_acc.get("chain_payload_sha256"):
            # A5：带 mip 图集的链 blob（全级 0..n-1——图集链无派生面）
            ambk = S.blob_key_generic(
                domain="mip", content_sha=mip_acc["chain_payload_sha256"],
                codec="npz")
            ib_rows.append((aik, ambk, "mip_chain"))
            blob_rows.append((ambk, mip_acc["chain_payload_sha256"],
                              mip_acc["chain_payload_size"], "npz", 1, now, now))
            seen_payload[mip_acc["chain_payload_sha256"]] = \
                mip_acc["chain_payload_size"]
        if mip_acc.get("count") and mip_acc["count"] > 1:
            n_mipped += 1
        loc_rows.append((lid, "color_atlas", f"{fam}[{ct}]", loc, "", ref,
                         rg, r["bundle"], r["cab"], r["path_id"], "ok",
                         S.cjson({"ref": ref, "guid": rg,
                                  "pixel_sha256": r["pixel_sha"]})))
        li_rows.append((lid, r["bundle"], r["cab"], r["path_id"],
                        bundle_sha.get(r["bundle"], ""), r["pixel_sha"]))

    cur.executemany(
        "INSERT OR REPLACE INTO items(item_key,domain,item,params_json,codec,"
        "codec_version,manifest_json,status,source_kind,source_json,"
        "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        items_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO item_blobs(item_key,blob_key,role) VALUES(?,?,?)",
        ib_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO blobs(blob_key,payload_sha256,size,codec,"
        "codec_version,last_used,created_at) VALUES(?,?,?,?,?,?,?)", blob_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locators(id,kind,subject,locale,premium,ref,"
        "guid,bundle,cab,path_id,status,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        loc_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locator_inputs(locator_id,bundle,cab,path_id,"
        "bundle_sha256,object_sha256) VALUES(?,?,?,?,?,?)", li_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO containers(bundle,key,path_id,ord) VALUES(?,?,?,?)",
        crows or [])
    cur.executemany(
        "INSERT OR REPLACE INTO objects(bundle,cab,path_id,class_id,byte_start,"
        "byte_size) VALUES(?,?,?,?,?,?)", orows or [])
    return {"color_probe": 1, "color_atlas_items": len(items_rows),
            "color_slots": n_slots, "color_slots_empty": n_empty,
            "color_unique_guids": len(uniq), "color_material_slots": n_material,
            "color_mipped_slots": n_mipped,
            "color_errors": color_errors, "color_blobs_unique": len(seen_payload),
            "color_blob_bytes": sum(seen_payload.values()),
            "color_blob_fresh": n_fresh,
            "wall_probe_s": round(t_probe, 2),
            "wall_atlas_s": round(time.time() - t_atlas0, 2)}


def _link_color_probe(conn, loc: str, card_types: dict[int, int]) -> dict:
    """color probe item → 每已知卡型卡 plan_items（role='color'；kit/gems 同款
    per-card 挂接）。

    期望面=**已知卡型卡**（kit 挂接同一人口——compile 对这些卡经 kit 提取/类色
    pick 无条件读 probe）；cardtype 未知卡不挂（R2 缺席归因语义不变——
    absent_expectationless 卡不被 color 期望翻成 ok）。probe item 缺失（probe
    表读取失败已在 build_color_items raise，防御面）→ 哨兵行 expect::color:probe
    （full 代发布门红）。幂等 upsert。card_types 由 _build_full 单读注入。"""
    row = conn.execute(
        "SELECT item_key FROM items WHERE domain=? AND item=?",
        (S.DOMAIN_COLOR, S.ITEM_COLOR_PROBE)).fetchone()
    probe_ik = row["item_key"] if row is not None \
        else S.expected_item_key("color:probe")
    rows: list[tuple[str, str, str]] = []
    n_linked = 0
    for r in conn.execute("SELECT card_id, dbf_id, data_sha FROM cards"):
        if r["dbf_id"] is None or card_types.get(r["dbf_id"]) is None:
            continue            # 未知卡型：不期望 color（缺席归因语义不变）
        pk = S.plan_key(card_id=r["card_id"], locale=loc,
                        card_data_sha=r["data_sha"] or "")
        rows.append((pk, probe_ik, "color"))
        n_linked += 1
    conn.executemany(
        "INSERT OR REPLACE INTO plan_items(plan_key,item_key,role) VALUES(?,?,?)",
        rows)
    return {"color_linked_cards": n_linked,
            "color_sentinel": probe_ik.startswith(S.EXPECTED_KEY_PREFIX)}


# ---------------------------------------------------------------------------
# mip 域（Phase 1 A5：textures.mip_registry 全局项——23 条静态链全级 NPZ；
# per-card portrait_mip 链已 fold 进 decode worker/_write_decoded）
# ---------------------------------------------------------------------------

def build_mip_registry(conn, win: Path, layout: SupplyLayout, loc: str, now: int,
                       bundle_sha: dict[str, str]) -> dict:
    """textures.mip_registry 全局项建库：live 手工注册表 23 条链全级提取 → 单
    NPZ blob（chain/<name>/<i> 数组键）→ item/item_blobs/blobs/locator 落库。

    域定性（任务单 A5）：**卡不变全域项**（非 per-card——content-fingerprint
    派发面与 chain_for_name 注册表分支的单一数据源）；warm 域访问器
    ``SupplyIndex.mip_registry()`` 供货（live 同形 name → {lods,filter,bias}），
    **不挂 plan_items**（text/color.atlas 域级项同款记账）；完整性面=audit
    child mip 段（全链解码 + 内容 sha 对账，open/import blocker 同窗）。
    链提取失败（包缺/纹理缺/字节账不合）=raise 响亮——注册表是 live 逐渲染
    消费的定案面（批10e 直提化定案），静默缺链=渲染降级，禁。"""
    from eidolon.core.supply_index import mip_codec as MC
    from eidolon.core.supply_index import mip_extract as ME

    cur = conn.cursor()
    t0 = time.time()
    arrays: dict[str, "np.ndarray"] = {}
    table: dict[str, dict] = {}
    errors: list[dict] = []
    lid0 = int(cur.execute("SELECT COALESCE(MAX(id),0) FROM locators").fetchone()[0])
    loc_rows, li_rows = [], []
    touched: dict[str, int] = {}
    for bundle, entries in ME.registry_bundles().items():
        _b, results, _wall = ME.extract_registry_worker(
            (str(win), bundle, entries))
        lid = lid0 + len(loc_rows) + 1
        for r in results:
            if r.get("error"):
                errors.append({"name": r["name"], "bundle": bundle,
                               "why": r["error"]})
                continue
            name = r["name"]
            for i, lod in enumerate(r["lods"]):
                arrays[MC.registry_chain_key(name, i)] = lod
            table[name] = {"filter": r["filter"], "bias": r["bias"],
                           "mip_count": r["mip_count"], "lods": r["mip_count"],
                           "bundle": bundle, "path_id": r["path_id"]}
            touched[bundle] = touched.get(bundle, 0) + 1
            loc_rows.append((lid, "mip_registry", name, loc, "", "",
                             "", bundle, "", r["path_id"], "ok",
                             S.cjson({"name": name, "bundle": bundle,
                                      "path_id": r["path_id"],
                                      "mip_count": r["mip_count"]})))
            li_rows.append((lid, bundle, "", r["path_id"],
                            bundle_sha.get(bundle, ""),
                            MC.chain_content_sha(r["lods"])))
            lid += 1
    if errors:
        raise RuntimeError(
            f"mip registry 提取失败 {len(errors)} 条（fail loud——注册表是 "
            f"live 渲染定案面）：{S.cjson(errors[:6])}")
    payload = MC.encode_chain_npz(arrays)
    payload_sha = S.sha256_hex(payload)
    content_sha = MC.chain_content_sha(
        [arrays[k] for k in sorted(arrays)])
    table_sha = S.sha256_hex(S.cjson(
        sorted((n, b, int(p)) for n, b, p in ME.MIP_CHAINS)).encode("utf-8"))
    content_inputs = {"chains": content_sha, "table": table_sha}
    rik = S.mip_registry_item_key(locale=loc, content_inputs=content_inputs)
    manifest = {"item": S.ITEM_MIP_REGISTRY, "locale": loc,
                "chains": {n: {"filter": v["filter"], "bias": v["bias"],
                               "mip_count": v["mip_count"],
                               "bundle": v["bundle"], "path_id": v["path_id"]}
                           for n, v in sorted(table.items())},
                "chain_count": len(table),
                "array_count": len(arrays),
                "payload_sha256": payload_sha,
                "payload_size": len(payload)}
    _write_blob_atomic(layout.root, payload_sha, payload, ext=".npz")
    rbk = S.blob_key_generic(domain="mip", content_sha=payload_sha, codec="npz")
    cur.executemany(
        "INSERT OR REPLACE INTO items(item_key,domain,item,params_json,codec,"
        "codec_version,manifest_json,status,source_kind,source_json,"
        "content_inputs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        [(rik, S.DOMAIN_TEXTURES, S.ITEM_MIP_REGISTRY, S.cjson({}), "npz", 1,
          S.cjson(manifest), "ok", "asset",
          S.cjson([{"bundle": b, "cab": "", "path_id": None, "guid": None,
                    "bundle_sha256": bundle_sha.get(b, ""),
                    "object_sha256": content_sha}
                   for b in sorted(touched)]),
          S.cjson(content_inputs), now)])
    cur.execute(
        "INSERT OR REPLACE INTO item_blobs(item_key,blob_key,role) VALUES(?,?,?)",
        (rik, rbk, "registry"))
    cur.execute(
        "INSERT OR REPLACE INTO blobs(blob_key,payload_sha256,size,codec,"
        "codec_version,last_used,created_at) VALUES(?,?,?,?,?,?,?)",
        (rbk, payload_sha, len(payload), "npz", 1, now, now))
    cur.executemany(
        "INSERT OR REPLACE INTO locators(id,kind,subject,locale,premium,ref,"
        "guid,bundle,cab,path_id,status,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        loc_rows)
    cur.executemany(
        "INSERT OR REPLACE INTO locator_inputs(locator_id,bundle,cab,path_id,"
        "bundle_sha256,object_sha256) VALUES(?,?,?,?,?,?)", li_rows)
    return {"mip_registry": 1, "chains": len(table),
            "arrays": len(arrays), "payload_sha256": payload_sha,
            "payload_size": len(payload),
            "wall_registry_s": round(time.time() - t0, 2)}


# ---------------------------------------------------------------------------
# plan 挂接（P2 车2：全 items 全 role 落 plan_items——kit/kit_play/gems）
# ---------------------------------------------------------------------------

def _link_shared_items(conn, win: Path, loc: str, now: int,
                       card_types: dict[int, int] | None = None) -> dict:
    """域级共享 items → 每卡 plan_items（kit=手牌帧族+hero PLAY 腿；gems=有 kit
    卡三件）。text 域不挂（全域项走 warm 域访问器——26MB TTF 面每卡拖运错位，
    build_text_items 头注同账）。

    期望落账（Phase 5 返工 R1，D-决策 2）：kit/gems 无 per-card locator 行 →
    「期望但未建」在此落成显式哨兵行（plan_items.item_key=schema.
    expected_item_key，role 列带真实 role）——帧族已解析且**属 kit 域词汇**
    （FRAME_SPECS_KIT 六族）而 kit item 未建（build_kits 该族失败）→
    expect::kit:<fam>；有 kit 卡而期望 gem（gems_codec.GEMS 选择器表全集）缺失
    （gem_issues）→ expect::gem:<gem>。warm/check 据此把 kit/gems 缺失点名入
    plan.missing（expected-vs-built 同权）。域外两态保持：family 解析不出
    （CARD_HIDDEN）与族名不在 kit 域词汇（ability/anomaly/trinket=车2 后续域）
    → out_of_scope 记账不期望（verify 覆盖面同口径）——**禁把未来域误标期望**
    （7,496 张 ability 族卡误账判例：首版哨兵按「族不在 kit_keys」判定把车2
    域全标成缺预期，partial-scope 门连带误红）。幂等 upsert。
    card_types=A4 起可外部注入（_build_full 单读 dbf 与 _link_color_probe 共享
    ——防重复开 CARD_TAG 包；None=自读，原语义）。"""
    from eidolon.core.supply_index.gems_codec import GEMS
    from eidolon.core.supply_index.kit_extract import (
        FRAME_SPECS_KIT,
        frame_family_maps,
        read_card_types_by_dbf,
    )

    kit_keys = {}
    for r in conn.execute(
            "SELECT item_key, params_json FROM items WHERE domain=? AND item=?",
            (S.DOMAIN_FRAMES, S.ITEM_KIT)):
        kit_keys[json.loads(r["params_json"])["frame"]] = r["item_key"]
    gem_keys = {r["item"]: r["item_key"] for r in conn.execute(
        "SELECT item, item_key FROM items WHERE domain=?", (S.DOMAIN_GEMS,))}
    expected_gems = sorted(set(GEMS) | set(gem_keys))

    if card_types is None:
        card_types = read_card_types_by_dbf(win)
    hand_map, play_map = frame_family_maps()
    rows: list[tuple[str, str, str]] = []
    fam_counts: dict[str, int] = {}
    out_of_scope: dict[str, int] = {}
    expected_missing: dict[str, int] = {}
    unknown = 0
    play_leg = 0
    for r in conn.execute("SELECT card_id, dbf_id, data_sha FROM cards"):
        cid = r["card_id"]
        ct = card_types.get(r["dbf_id"]) if r["dbf_id"] is not None else None
        if ct is None:
            unknown += 1
            continue
        pk = S.plan_key(card_id=cid, locale=loc, card_data_sha=r["data_sha"] or "")
        fam = hand_map.get(ct)
        hand_item = None
        if fam is None:
            out_of_scope["CARD_HIDDEN"] = out_of_scope.get("CARD_HIDDEN", 0) + 1
        elif fam in kit_keys:
            hand_item = kit_keys[fam]
            rows.append((pk, hand_item, "kit"))
            fam_counts[fam] = fam_counts.get(fam, 0) + 1
        elif fam in FRAME_SPECS_KIT:
            # 族属 kit 域词汇而 kit item 未建（该族 build 失败）——期望落账（哨兵行）
            rows.append((pk, S.expected_item_key(f"kit:{fam}"), "kit"))
            expected_missing[f"kit:{fam}"] = \
                expected_missing.get(f"kit:{fam}", 0) + 1
        else:
            # 车2 后续域（ability/anomaly/trinket 等）——域外，不期望
            out_of_scope[fam] = out_of_scope.get(fam, 0) + 1
        pfam = play_map.get(ct)
        if pfam is not None:
            # PLAY 腿（GetPlayActorByTags :691 等）：hand/play 同帧族（heropower/
            # location）时同 item 一行——plan_items PK=(plan_key,item_key)，role 不
            # 入键，二次 INSERT OR REPLACE 会吞 kit 行（烟雾实测判例）。
            if pfam in kit_keys and kit_keys[pfam] != hand_item:
                rows.append((pk, kit_keys[pfam], "kit_play"))
                play_leg += 1
            elif pfam in FRAME_SPECS_KIT and pfam not in kit_keys \
                    and pfam != fam:
                # PLAY 期望（域内族）而 kit item 未建——期望落账（哨兵行；同帧族
                # 时 kit 行已在上方记账，不重复）
                rows.append((pk, S.expected_item_key(f"kit_play:{pfam}"),
                             "kit_play"))
                expected_missing[f"kit_play:{pfam}"] = \
                    expected_missing.get(f"kit_play:{pfam}", 0) + 1
            elif pfam not in FRAME_SPECS_KIT:
                out_of_scope[f"play:{pfam}"] = out_of_scope.get(f"play:{pfam}", 0) + 1
        if hand_item is not None:
            for gem in expected_gems:
                gk = gem_keys.get(gem)
                if gk is not None:
                    rows.append((pk, gk, f"gem:{gem}"))
                else:
                    # 期望 gem（选择器表全集）而 item 未建（gem_issues）——期望落账
                    rows.append((pk, S.expected_item_key(f"gem:{gem}"),
                                 f"gem:{gem}"))
                    expected_missing[f"gem:{gem}"] = \
                        expected_missing.get(f"gem:{gem}", 0) + 1
    conn.executemany(
        "INSERT OR REPLACE INTO plan_items(plan_key,item_key,role) VALUES(?,?,?)",
        rows)
    return {"linked_rows": len(rows), "family_card_counts": dict(sorted(fam_counts.items())),
            "out_of_scope": dict(sorted(out_of_scope.items())),
            "expected_missing": dict(sorted(expected_missing.items())),
            "cardtype_unknown": unknown,
            "play_leg_rows": play_leg,
            "gems_linked_cards": sum(fam_counts.values()) if fam_counts else 0}


# ---------------------------------------------------------------------------
# 介质自愈卫兵（P3 件7；介质事故账 2026-11-07 判例的内建化）
# ---------------------------------------------------------------------------

def _prebuild_integrity_guard(layout: SupplyLayout) -> dict | None:
    """建库前 integrity 前置：现行代全量 blob 扫，bad>0=响亮（禁在坏账上建库）。

    现行代不存在（首建/无 current.json/代库缺）=跳过返回 None。恢复路径=
    `integrity --repair` 自愈到 0 bad 再建（自愈环路，P2 事故账）。定向 DB 驱动
    decode 不走本卫兵（冷定向 p50<1s 预算；写面已有 _write_blob_atomic 逐块
    复验兜底）——全量/部分代初始化专属。"""
    from eidolon.core.supply_index.integrity import scan as _integrity_scan

    cur = layout.read_current()
    if cur is None:
        return None
    db = layout.gen_db(cur.get("game_id", ""))
    if not db.is_file():
        return None
    conn = S.connect(db, readonly=True)
    try:
        findings = _integrity_scan(conn, layout)
    finally:
        conn.close()
    if findings["bad"]:
        raise RuntimeError(
            "建库前 integrity 前置：现行代 "
            f"{cur.get('generation')} bad={findings['bad']}"
            f"（missing={len(findings['missing'])} "
            f"mismatch={len(findings['mismatch'])}）——先 "
            "`integrity --repair` 自愈到 0 bad 再建（介质事故账 2026-11-07）")
    return {"generation": cur.get("generation"), "rows": findings["rows"],
            "ok": findings["ok"]}


def _tail_integrity_guard(conn, layout: SupplyLayout) -> dict:
    """build 尾部全量 integrity 扫（发布前；0 bad 或 fail loud——不发布坏代）。

    .build DB 行账 vs 盘上 blob 逐个 hash（含本 build 复用的旧块——介质翻黑
    正是 P2 事故形态：写好→盘上翻黑→下次 build 静默复用）。bad>0=响亮：
    .build 保留待查、现行代未被切（os.replace 未执行）——恢复路径=
    `integrity --repair` 后重建。"""
    from eidolon.core.supply_index.integrity import scan as _integrity_scan

    findings = _integrity_scan(conn, layout)
    if findings["bad"]:
        raise RuntimeError(
            "build 尾部 integrity 扫：bad="
            f"{findings['bad']}（missing={len(findings['missing'])} "
            f"mismatch={len(findings['mismatch'])}）——不发布坏代（.build 保留；"
            "先 `integrity --repair` 再重建）")
    return {"rows": findings["rows"], "ok": findings["ok"]}


def _tail_completeness_guard(conn, *, full: bool,
                             scope_cards: set[str] | None) -> dict:
    """build 尾部 expected-vs-built 完整性发布门（Phase 5 返工 R1，P0-2）。

    判据=schema.expected_vs_built 单源（期望=locators ok card 级 kind + plan_items
    哨兵/实体 role；built=items 行存在的 role）。两种模式的门语义：
    - full 代（full=True）：任何 expected 未 built → **不发布**（响亮列缺项清单，
      .build 保留；错误账见 meta *_errors——decode 失败/kit 失败/wm 失败都到此
      显式现形）；
    - partial/sampled 代（full=False，scope=--cards/--sample 期望集）：只挡
      **scope 内**缺项（定向承诺建却没建=响亮）；scope 外 expected 静默缺失是
      partial 代定义本身——列账（missing_out_scope + completeness meta）不阻断。
    audit full 门消费同一账面（expected_vs_built missing==0）。"""
    comp = S.expected_vs_built(conn, scope_cards=scope_cards)
    comp["gate"] = "full" if full else "partial-scope"
    blocking = comp["missing_total"] if full else comp["missing_in_scope"]
    comp["blocking_missing"] = blocking
    if blocking:
        sample = "; ".join(f"{m['card_id']}:{m['role']}"
                           for m in comp["missing_sample"][:8])
        raise RuntimeError(
            f"build 尾部完整性门（expected-vs-built，gate={comp['gate']}）："
            f"缺预期产物 {blocking} 项（scope 外 {comp['missing_out_scope']} 项）"
            f"——不发布（.build 保留）。分域账：{S.cjson(comp['by_kind'])[:400]}；"
            f"样例：{sample}；解码/提取错误账见 build 报告 *_errors 与 meta "
            "*_errors_json")
    return comp


def _capped_errors(errors: list, *, cap: int = 10) -> dict:
    """错误账 meta 形态：全量计数 + 截断样例（meta 行禁无界增长）。"""
    return {"count": len(errors), "sample": errors[:cap]}


# ---------------------------------------------------------------------------
# build 入口（全量重建 / 定向增量）
# ---------------------------------------------------------------------------

def build(cache_root: Path | str, *, game: Path, locale: str,
          jobs: int = 4, cards: list[str] | None = None, sample: int | None = None,
          skip_bundle_hash: bool = False,
          skip_prebuild_guard: bool = False) -> dict:
    """建代库。cards/sample=None=全量重建；给了=定向。game/locale 必填（显式身份）。

    定向两形态：
    - 缓存根无代 → 部分代初始化（manifest/catalog/dbf/bundles(stat-only) + 全量
      locate + 只解指定卡；meta.full_build=0）；
    - 已有代 → **DB 驱动定向 decode**（locator/cards 全在库=「catalog 已建、产物
      未建」，不碰 manifest/dbf——设计 §1 冷定向 p50<1s 的达成路径）。

    skip_prebuild_guard=L1 索引重建专用（selfheal.ensure_index）：现行代 DB 本身
    损坏时建库前 integrity 前置会连库即炸——跳过之（尾部发布前扫仍在，坏 blob
    代照样不发布）。仅限 L1 重建路径传 True。

    返回账面 dict。锁=缓存根原子 mkdir 锁；同 gen 重跑全量=DB 重建发布
    （blob 内容寻址天然复用，blob_fresh 只计新写）。

    游戏身份全显式（Phase 5 移植定案）：``game``/``locale`` 必填；ctx 经
    ``game_install.resolve_context`` 构造 + ``context.install``（同身份幂等、
    异身份 raise——进程单渲染身份，与 render 同规）；安装根完整性再验
    ``assert_game_root``。"""
    from eidolon.core.infra import context
    from eidolon.core.infra.game_install import assert_game_root, resolve_context
    from eidolon.contracts import GameRequest

    layout = SupplyLayout(cache_root)
    t_start = time.time()
    ctx = resolve_context(GameRequest(Path(game), "--game"),
                          cache_root=Path(cache_root), locale=locale or "zhcn")
    context.install(ctx)            # 同身份幂等；异身份 raise（进程单渲染身份）
    assert_game_root(ctx.root)
    win = ctx.data_win
    loc = ctx.locale

    ident = compute_identity(win, ctx.version, dll_path=ctx.assembly_csharp)
    game_id = ident["game_id"]
    if cards is not None or sample is not None:
        cur = layout.read_current()
        has_gen = cur is not None and layout.gen_db(cur["game_id"]).is_file()
        if has_gen:
            return _build_targeted_dbdriven(layout, jobs, cards, sample, t_start,
                                            ident=ident)
        return _build_partial_init(layout, win, loc, ident, jobs, cards, sample,
                                   t_start=t_start, ctx=ctx)
    return _build_full(layout, win, loc, ident, game_id, jobs, skip_bundle_hash,
                       t_start, ctx=ctx,
                       skip_prebuild_guard=skip_prebuild_guard)


def _resolve_decode_set(cards_map: dict, cards: list[str] | None,
                        sample: int | None) -> set[str]:
    if sample is not None:
        pool = sorted(cards_map)
        rng = random.Random(42)
        return set(rng.sample(pool, min(sample, len(pool))))
    assert cards, "--cards 与 --sample 至少给一个"
    unknown = set(cards) - set(cards_map)
    if unknown:
        raise KeyError(f"--cards 含 cards_map 未知卡 {len(unknown)} 个："
                       f"{sorted(unknown)[:5]}…")
    return set(cards)


def _build_full(layout: SupplyLayout, win: Path, loc: str, ident: dict,
                game_id: str, jobs: int, skip_bundle_hash: bool,
                t_start: float, decode_set: set[str] | None = None,
                ctx=None, skip_prebuild_guard: bool = False) -> dict:
    """全量：重建整代 DB（.build → os.replace 发布）→ current.json 原子切。

    decode_set=None 解全部目标；给了=只解子集（部分代初始化共用本流程）。"""
    partial = decode_set is not None
    gen_dir = layout.gen_dir(game_id)
    gen_dir.mkdir(parents=True, exist_ok=True)
    with CacheLock(layout.lock_dir, purpose=f"build gen-{game_id[:12]}"):
        # --- 建库前 integrity 前置（件7 介质自愈内建化；现行代存在才扫；
        #     skip_prebuild_guard=L1 索引重建专用——DB 本身坏，扫即炸） ---
        if skip_prebuild_guard:
            pre_guard = None
        else:
            pre_guard = _prebuild_integrity_guard(layout)

        # --- 并行流水（件2）：bundle sha 后台池 × 主线 manifest/catalog/dbf/locate ---
        # 旧形五段纯串行（实测 manifest 0.56+catalog 9.04+dbf 0.78+bundles 32.44
        # +locate 3.77≈46.6s wall）——hash 细分片（64 包/片，原 jobs 整除粗片有
        # 长尾）后台池跑，主线四段全部藏进 hash wall；hash 收敛后同池接 decode/wm
        # 解码（worker 已热，免二次 spawn）。
        t_preflow0 = time.time()
        all_bundles = sorted(p.name for p in win.glob("*.unity3d"))
        bundle_sha: dict[str, str] = {}
        bundle_rows: list[tuple] = []
        pool: ProcessPoolExecutor | None = None
        hash_futures: list = []
        try:
            if not skip_bundle_hash:
                pool = ProcessPoolExecutor(max_workers=jobs)
                hash_futures = [
                    pool.submit(_hash_bundles_worker,
                                (str(win), all_bundles[i:i + _HASH_CHUNK]))
                    for i in range(0, len(all_bundles), _HASH_CHUNK)]

            # --- manifest 表 ---
            t0 = time.time()
            tables = read_manifest_tables(win, loc)
            t_manifest = time.time() - t0
            catalog = tables["catalog"]

            db_path = layout.gen_db_build(game_id)
            if db_path.exists():
                db_path.unlink()
            # WAL/SHM sidecar 残留同清（2026-11-07 蓝屏判例：前任 build 死于建库
            # 中，.build 主文件+74MB -wal/-shm 残留——新 DB 复名前若旧 -wal 在位，
            # SQLite 开新库会按盐值做 WAL 恢复把旧帧重放到新库=毒化。crash-safe
            # 面侧车必须与主文件同生命周期）。
            for suf in ("-wal", "-shm", "-journal"):
                sidecar = Path(str(db_path) + suf)
                if sidecar.exists():
                    sidecar.unlink()
            conn = S.connect(db_path)
            S.init_schema(conn)
            now = int(time.time())
            meta = {
                "schema_version": S.SCHEMA_VERSION, "plan_version": str(S.PLAN_VERSION),
                "codec": S.CODEC, "codec_version": str(S.CODEC_VERSION),
                "game_id": game_id,
                **{f"identity_{k}": v for k, v in ident["identity"].items()},
                "locale": loc, "unitypy_fallback": FALLBACK_UNITY_VERSION,
                "code_version": "p3", "built_at": str(now), "jobs": str(jobs),
                "full_build": "0" if partial else "1",
            }
            conn.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                             sorted(meta.items()))

            # --- catalog（392k 流式；主线段——与 hash 池流水并行） ---
            t0 = time.time()
            conn.executemany("INSERT OR REPLACE INTO asset_catalog(guid,bundle) VALUES(?,?)",
                             tables["catalog_pairs"])
            conn.executemany(
                "INSERT OR REPLACE INTO asset_variants(base_guid,layer,locale,guid,bundle) "
                "VALUES(?,?,?,?,?)", tables["variant_rows"])
            t_catalog = time.time() - t0

            # --- dbf card ids ---
            t0 = time.time()
            dbf_ids, dbf_dup = read_dbf_card_ids(win)
            t_dbf = time.time() - t0

            # --- locate（恒全卡：定向 decode 依赖全量 locator 在库） ---
            t0 = time.time()
            locs = locate_cards(win, tables["cards_map"], catalog,
                                tables["variant_rows"], loc)
            t_locate = time.time() - t0
            n_cards = _write_located(conn, locs, dbf_ids)
            acc_loc = _write_locators(conn, locs)

            # --- bundles 收割（hash 池收敛；wall=流水窗内残差等待） ---
            t0 = time.time()
            if skip_bundle_hash:
                bundle_rows = [(n, (win / n).stat().st_size,
                                (win / n).stat().st_mtime_ns, "")
                               for n in all_bundles]
            else:
                for fut in hash_futures:
                    bundle_rows.extend(fut.result())
            for n, size, mtime, sha in bundle_rows:
                bundle_sha[n] = sha
            conn.executemany(
                "INSERT OR REPLACE INTO bundles(name,size,mtime_ns,sha256) VALUES(?,?,?,?)",
                bundle_rows)
            t_bundles = time.time() - t0
            t_preflow = time.time() - t_preflow0

            # --- decode（decode_set=None=全部；共享 hash 池——worker 已热） ---
            t0 = time.time()
            targets = [t for cl in locs.values()
                       if decode_set is None or cl.card_id in decode_set
                       for t in cl.targets]
            results, crows, orows, walls = _decode_targets(win, layout, targets,
                                                           jobs, pool=pool)
            t_decode = time.time() - t0

            acc = _write_decoded(conn, locs, results, bundle_sha, loc, now,
                                 container_rows=crows, object_rows=orows)

            # --- kit 提取（P2 车1：六帧族；定包子集也全提——kit=卡不变结构，六件套；
            #     ally 帧随走查产 gems 域项） ---
            t0 = time.time()
            acc_kit = build_kits(conn, win, layout, tables, loc, now, dbf_ids,
                                 bundle_sha, jobs)
            t_kits = time.time() - t0

            # --- text 域（P2 车2：fontdefs+TTF 全域项；不进 plan_items） ---
            t0 = time.time()
            acc_text = build_text_items(conn, win, layout, tables, loc, now,
                                        bundle_sha, ctx=ctx)
            t_text = time.time() - t0

            # --- watermark 域（P2 车2：四级裁决→guid 去重解码→per-card items） ---
            t0 = time.time()
            acc_wm = build_watermarks(conn, win, layout, loc, now, bundle_sha,
                                      tables, jobs, pool=pool)
            t_wm = time.time() - t0

            # --- color 域（Phase 1 A4：switcher probe + 全纹理槽图集；probe
            #     per-card 挂接走 _link_color_probe，atlas=域级访问器不挂 plan；
            #     A5：atlas worker 顺带记每槽 mip 判定账——entry_for_ref seeded
            #     查找面的数据源） ---
            t0 = time.time()
            acc_color = build_color_items(conn, win, layout, tables, loc, now,
                                          bundle_sha, jobs, pool=pool)
            t_color = time.time() - t0

            # --- mip 域（Phase 1 A5：textures.mip_registry 全局项；per-card
            #     portrait_mip 链已随 decode worker 提取、_write_decoded 落账） ---
            t0 = time.time()
            acc_mip = build_mip_registry(conn, win, layout, loc, now, bundle_sha)
            t_mip = time.time() - t0

        finally:
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)

        # --- supplement 域（Phase 1 A6：live 提取 harness——独立子进程 route
        #     off；在 decode 池关闭后跑，worker 独占内存面；game_root=ctx 根
        #     ——resolve_context 语义，非 data_win） ---
        t0 = time.time()
        acc_supp = build_supplements(conn, win, layout, loc, now, bundle_sha,
                                     jobs,
                                     game_root=ctx.root if ctx is not None
                                     else None)
        t_supp = time.time() - t0

        # --- plan 挂接（P2 车2：kit/kit_play/gems 全 role 落 plan_items；
        #     A4：card_types 单读共享，color probe 同人口挂接；A6：trinket/
        #     anomaly harness kit 在位后挂接） ---
        t0 = time.time()
        from eidolon.core.supply_index.kit_extract import read_card_types_by_dbf
        card_types = read_card_types_by_dbf(win)
        acc_link = _link_shared_items(conn, win, loc, now,
                                      card_types=card_types)
        acc_color_link = _link_color_probe(conn, loc, card_types)
        t_link = time.time() - t0

        # --- plan status 重算（P0-1：expected-vs-built 单源语义——golden/
        #     kit/gems/watermark 与 portrait 同权；「complete=expected 全部
        #     built」） ---
        plan_status = S.recompute_plan_status(conn)

        n_items = int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])
        n_blobs = int(conn.execute("SELECT COUNT(*) FROM blobs").fetchone()[0])
        # --- 尾部 integrity（件7；发布前全量扫——0 bad 或 fail loud 不发布。
        #     扫在 commit 前跑：同一连接可见本事务行账；fail loud 时 .build 不发布） ---
        tail_guard = _tail_integrity_guard(conn, layout)
        # --- 尾部完整性段（P0-2 返工 R1：expected-vs-built 发布门——full 代任何
        #     expected 未 built=不发布；partial/sampled 代只挡显式 scope 内缺项，
        #     scope 外缺项列账不阻断（partial 代定义）） ---
        comp_guard = _tail_completeness_guard(conn, full=not partial,
                                              scope_cards=decode_set)
        conn.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", [
            ("counts_cards", str(n_cards)),
            ("counts_catalog", str(len(tables["catalog_pairs"]))),
            ("counts_variants", str(len(tables["variant_rows"]))),
            ("counts_bundles", str(len(all_bundles))),
            ("counts_locators", str(acc_loc["locators"] + acc_kit["kits"]
                                    + acc_text["text_items"] + acc_wm["wm_items"]
                                    + acc_color["color_probe"]
                                    + acc_color["color_atlas_items"]
                                    + acc_mip["chains"])),
            ("counts_locators_missing", str(acc_loc["missing"]
                                            + len(acc_kit["kit_errors"]))),
            ("counts_items", str(n_items)),
            ("counts_blobs", str(n_blobs)),
            ("counts_kit_items", str(int(conn.execute(
                "SELECT COUNT(*) FROM items WHERE domain=?",
                (S.DOMAIN_FRAMES,)).fetchone()[0]))),
            ("counts_gem_items", str(int(conn.execute(
                "SELECT COUNT(*) FROM items WHERE domain=?",
                (S.DOMAIN_GEMS,)).fetchone()[0]))),
            ("counts_wm_items", str(int(conn.execute(
                "SELECT COUNT(*) FROM items WHERE domain=?",
                (S.DOMAIN_WATERMARK,)).fetchone()[0]))),
            ("counts_text_items", str(int(conn.execute(
                "SELECT COUNT(*) FROM items WHERE domain=?",
                (S.DOMAIN_TEXT,)).fetchone()[0]))),
            ("counts_color_items", str(int(conn.execute(
                "SELECT COUNT(*) FROM items WHERE domain=?",
                (S.DOMAIN_COLOR,)).fetchone()[0]))),
            ("counts_mip_items", str(int(conn.execute(
                "SELECT COUNT(*) FROM items WHERE (domain=? AND item=?) OR "
                "domain=?",
                (S.DOMAIN, S.ITEM_PORTRAIT_MIP,
                 S.DOMAIN_TEXTURES)).fetchone()[0]))),
            ("counts_supplement_items", str(int(conn.execute(
                "SELECT COUNT(*) FROM items WHERE codec=? OR (domain=? AND "
                "item=?)",
                (S.SUPP_CODEC, S.DOMAIN_FRAMES,
                 S.ITEM_KIT_LIGHT)).fetchone()[0]))),
            ("counts_plan_items", str(int(conn.execute(
                "SELECT COUNT(*) FROM plan_items").fetchone()[0]))),
            ("counts_plans", str(int(conn.execute(
                "SELECT COUNT(*) FROM plans").fetchone()[0]))),
            ("counts_dbf_duplicates", str(dbf_dup)),
            ("blob_bytes", str(acc["blob_bytes_unique"] + acc_kit["kit_blob_bytes"]
                               + acc_wm["wm_blob_bytes"]
                               + acc_color["color_blob_bytes"]
                               + acc_mip["payload_size"])),
            # --- 完整性/错误账（Phase 5 返工 R1，P0-1/P0-2） ---
            ("completeness_json", S.cjson(
                {k: comp_guard[k] for k in
                 ("gate", "plans", "expectationless_cards", "missing_total",
                  "missing_in_scope", "missing_out_scope", "by_kind")})),
            ("decode_errors_json", S.cjson(
                {k: _capped_errors(v) for k, v in acc["decode_errors"].items()})),
            ("kit_errors_json", S.cjson(
                _capped_errors(acc_kit["kit_errors"]))),
            ("wm_errors_json", S.cjson(
                _capped_errors(acc_wm["wm_errors"]))),
            ("text_errors_json", S.cjson(
                _capped_errors(acc_text["errors"]))),
            ("color_errors_json", S.cjson(
                _capped_errors(acc_color["color_errors"]))),
            ("mip_unsupported_json", S.cjson(
                _capped_errors(acc["mip_unsupported"]))),
            ("blob_fresh", str(acc["blob_fresh"])),
            ("integrity_prebuild", "skipped(l1-rebuild)" if skip_prebuild_guard
                else ("skipped" if pre_guard is None
                      else f"ok rows={pre_guard['rows']}")),
            ("integrity_tail", f"ok rows={tail_guard['rows']}"),
            ("wall_manifest_s", f"{t_manifest:.2f}"),
            ("wall_catalog_s", f"{t_catalog:.2f}"),
            ("wall_dbf_s", f"{t_dbf:.2f}"),
            ("wall_bundles_s", f"{t_bundles:.2f}"),
            ("wall_preflow_s", f"{t_preflow:.2f}"),
            ("wall_locate_s", f"{t_locate:.2f}"),
            ("wall_decode_s", f"{t_decode:.2f}"),
            ("wall_kits_s", f"{t_kits:.2f}"),
            ("wall_text_s", f"{t_text:.2f}"),
            ("wall_wm_s", f"{t_wm:.2f}"),
            ("wall_color_s", f"{t_color:.2f}"),
            ("wall_mip_registry_s", f"{t_mip:.2f}"),
            ("wall_link_s", f"{t_link:.2f}"),
            ("wall_supplement_s", f"{t_supp:.2f}"),
            ("wall_total_s", f"{time.time() - t_start:.2f}"),
        ])
        conn.commit()
        conn.close()

        # --- 发布 ---
        _publish(layout, db_path, game_id, loc, ident, now, full=not partial)
    wall = time.time() - t_start
    return {"mode": "partial-init" if partial else "full",
            "game_id": game_id, "generation": f"gen-{game_id}",
            "cards": n_cards, "items": n_items, "blobs": n_blobs,
            "blob_fresh": acc["blob_fresh"],
            "blob_bytes": acc["blob_bytes_unique"] + acc_kit["kit_blob_bytes"]
                          + acc_wm["wm_blob_bytes"]
                          + acc_color["color_blob_bytes"]
                          + acc_mip["payload_size"],
            "locators": acc_loc["locators"] + acc_kit["kits"]
                        + acc_text["text_items"] + acc_wm["wm_items"]
                        + acc_color["color_probe"]
                        + acc_color["color_atlas_items"]
                        + acc_mip["chains"],
            "locator_missing": acc_loc["missing"] + len(acc_kit["kit_errors"]),
            "kits": {"extracted": acc_kit["kits"] - len(acc_kit["kit_errors"]),
                     "errors": acc_kit["kit_errors"],
                     "blob_bytes": acc_kit["kit_blob_bytes"]},
            "gems": {"items": acc_kit["gem_items"],
                     "issues": [e for e in acc_kit["kit_errors"]
                                if "gem_issue" in e]},
            "text": {"items": acc_text["text_items"], "ttfs": acc_text["ttfs"],
                     "ttf_mb": round(acc_text["ttf_bytes"] / 1e6, 2),
                     "errors": acc_text["errors"]},
            "watermark": {"items": acc_wm["wm_items"],
                          "cards_with_ref": acc_wm["wm_cards_with_ref"],
                          "unique_guids": acc_wm["wm_unique_guids"],
                          "errors": acc_wm["wm_errors"][:10],
                          "error_count": len(acc_wm["wm_errors"]),
                          "blob_bytes": acc_wm["wm_blob_bytes"]},
            "color": {"probe": acc_color["color_probe"],
                      "atlas_items": acc_color["color_atlas_items"],
                      "slots": acc_color["color_slots"],
                      "slots_empty": acc_color["color_slots_empty"],
                      "unique_guids": acc_color["color_unique_guids"],
                      "material_slots": acc_color["color_material_slots"],
                      "mipped_slots": acc_color["color_mipped_slots"],
                      "errors": acc_color["color_errors"][:10],
                      "error_count": len(acc_color["color_errors"]),
                      "blob_bytes": acc_color["color_blob_bytes"],
                      "link": acc_color_link},
            "mip": {"registry_chains": acc_mip["chains"],
                    "registry_arrays": acc_mip["arrays"],
                    "registry_payload_sha256": acc_mip["payload_sha256"],
                    "registry_payload_size": acc_mip["payload_size"],
                    "portrait_mip_blob_fresh": acc["mip_blob_fresh"],
                    "portrait_mip_sentinels": acc["mip_sentinels"],
                    "portrait_mip_unsupported": acc["mip_unsupported"]},
            "supplement": {"kit_items": acc_supp.get("kit_items", {})
                                                      .get("kits", 0),
                           "kit_light_items": acc_supp.get("kit_light_items", {})
                                                       .get("kits", 0),
                           "supp_items": acc_supp.get("supp_items", {})
                                                  .get("items", 0),
                           "blob_bytes": acc_supp.get("supp_items", {})
                                                  .get("blob_bytes", 0),
                           "injected": acc_supp.get("injected"),
                           "errors": acc_supp.get("supplement_errors"),
                           "wall_s": acc_supp.get("wall_supplement_s")},
            "plan_link": {"rows": acc_link["linked_rows"],
                          "family_card_counts": acc_link["family_card_counts"],
                          "out_of_scope": acc_link["out_of_scope"],
                          "expected_missing": acc_link["expected_missing"],
                          "cardtype_unknown": acc_link["cardtype_unknown"]},
            "plans": acc["plans"], "plan_status": plan_status,
            "completeness": {k: comp_guard[k] for k in
                             ("gate", "plans", "expectationless_cards",
                              "missing_total", "missing_in_scope",
                              "missing_out_scope", "by_kind")},
            "decode_errors": {k: _capped_errors(v)
                              for k, v in acc["decode_errors"].items()},
            "wall_s": round(wall, 2),
            "integrity": {"prebuild": pre_guard, "tail": tail_guard,
                          "completeness": comp_guard},
            "walls": {"manifest": round(t_manifest, 2), "catalog": round(t_catalog, 2),
                      "dbf": round(t_dbf, 2), "bundles": round(t_bundles, 2),
                      "preflow": round(t_preflow, 2),
                      "locate": round(t_locate, 2), "decode": round(t_decode, 2),
                      "kits": round(t_kits, 2), "text": round(t_text, 2),
                      "watermark": round(t_wm, 2), "color": round(t_color, 2),
                      "mip_registry": round(t_mip, 2),
                      "link": round(t_link, 2)},
            "decode_bundle_walls": {k: round(v, 2) for k, v in
                                    sorted(walls.items(), key=lambda kv: -kv[1])[:8]},
            "db": str(layout.gen_db(game_id))}


def _build_partial_init(layout: SupplyLayout, win: Path, loc: str, ident: dict,
                        jobs: int, cards: list[str] | None, sample: int | None,
                        t_start: float, ctx=None) -> dict:
    """部分代初始化：无代时的定向 build（全量表结构+全量 locate+子集 decode）。

    bundles 只 stat 不 hash（sha 记空串；cheap diff 如实记 sha-unrecorded→
    revalidate）。正式全量 build 重建整 DB 补齐 sha。"""
    tables = read_manifest_tables(win, loc)
    decode_set = _resolve_decode_set(tables["cards_map"], cards, sample)
    return _build_full(layout, win, loc, ident, ident["game_id"], jobs,
                       skip_bundle_hash=True, t_start=t_start,
                       decode_set=decode_set, ctx=ctx)


def _build_targeted_dbdriven(layout: SupplyLayout, jobs: int,
                             cards: list[str] | None, sample: int | None,
                             t_start: float, *, ident: dict) -> dict:
    """DB 驱动定向 decode：locator/cards 全在库，只解缺 item（零 manifest/dbf）。

    设计 §1「cold 定向单卡 p50<1s」达成路径；游戏换代（game_id 变）不归本路——
    全量 build 负责切代。

    Phase 5 返工 R1（P1-2/P1-10）：
    - **身份门**：先 compute_identity 比对 current 代 game_id（ident 由 build()
      主入口现算传入），不一致=游戏已换代 → 响亮报错要求全量重建（不写库）；
    - 待解目标 **(card, kind) 粒度**：locator-ok 且 (subject, kind) 无 item 才解
      （旧卡粒度会跳过「有 portrait 缺 golden」的补建卡）；decode 目标表=art 域
      portrait/portrait_golden——watermark/kit/fontdefs/font_ttf locator 非 decode
      目标 kind（域级项=全量 build 六件套），剔除出 want 面；
    - scope plans status 重算（expected-vs-built）+ meta counts 全量重算
      （counts_items/blobs/plan_items/plans/blob_bytes 从表现算）。"""
    cur = layout.read_current()
    assert cur is not None
    game_id = cur["game_id"]
    if ident.get("game_id") != game_id:
        # 身份门（P1-2）：响亮拒绝，不写库——换代后的 locator/item 账属于旧代
        raise RuntimeError(
            f"定向 build 拒绝：游戏身份已换代（current 代 {game_id[:12]}… ≠ 现算 "
            f"{ident.get('game_id', '')[:12]}…）——定向路不改写旧代账，请跑全量 "
            "重建（cold build 不带 --cards/--sample）切代后再定向补建")
    loc = cur.get("locale", "")
    db_path = layout.gen_db(game_id)
    conn_ro = S.connect(db_path, readonly=True)
    all_cards = {r["card_id"] for r in conn_ro.execute("SELECT card_id FROM cards")}
    if sample is not None:
        rng = random.Random(42)
        decode_set = set(rng.sample(sorted(all_cards), min(sample, len(all_cards))))
    else:
        assert cards, "--cards 与 --sample 至少给一个"
        decode_set = set(cards)
        unknown = decode_set - all_cards
        if unknown:
            raise KeyError(f"--cards 含库中未知卡 {len(unknown)} 个（先全量 build 同步 "
                           f"locator）：{sorted(unknown)[:5]}…")
    # 待解目标：decode_set 内、locator ok、且 **(card, kind) 尚无 item**（P1-2：
    # 旧卡粒度幂等会跳过「有 portrait 缺 golden」的补建卡）；decode 目标 kind=
    # art 域 portrait/portrait_golden（watermark 等非解码目标 kind 剔除——域级项
    # =全量 build 六件套，定向路不产）
    have_items = {(json.loads(r[0])["card_id"], json.loads(r[0])["kind"])
                  for r in conn_ro.execute(
                      "SELECT params_json FROM items WHERE domain='art'")}
    want = []
    for r in conn_ro.execute(
            "SELECT subject, kind, guid, bundle FROM locators "
            "WHERE status='ok' AND kind IN ('portrait','portrait_golden')"):
        if r["subject"] in decode_set and (r["subject"], r["kind"]) not in have_items:
            want.append(PortraitTarget(r["subject"], r["kind"], "", r["guid"],
                                       r["bundle"], loc))
    # scope 卡位视图（carddef 全字段在库；_write_decoded 需要 carddef 身份与 targets）
    carddef_rows = {r["card_id"]: r for r in conn_ro.execute(
        "SELECT card_id,carddef_ref,carddef_guid,carddef_bundle,carddef_cab,"
        "carddef_path_id,data_sha FROM cards "
        "WHERE card_id IN (%s)" % ",".join("?" * len(decode_set)), sorted(decode_set))}
    conn_ro.close()
    scope_locs: dict[str, CardLoc] = {}
    for cid, r in carddef_rows.items():
        cl = CardLoc(cid, {"ref": r["carddef_ref"], "guid": r["carddef_guid"],
                           "bundle": r["carddef_bundle"], "cab": r["carddef_cab"],
                           "path_id": r["carddef_path_id"],
                           "sha256": r["data_sha"] or ""}, [])
        for tg in want:
            if tg.card_id == cid:
                cl.targets.append(tg)
        scope_locs[cid] = cl

    with CacheLock(layout.lock_dir, purpose=f"decode-targeted gen-{game_id[:12]}"):
        now = int(time.time())
        t0 = time.time()
        results, crows, orows, _w = _decode_targets(_win_from_ctx(), layout, want, jobs)
        t_decode = time.time() - t0
        conn = S.connect(db_path)
        bundle_sha = {r[0]: r[1] for r in conn.execute("SELECT name,sha256 FROM bundles")}
        acc = _write_decoded(conn, scope_locs, results, bundle_sha, loc, now,
                             container_rows=crows, object_rows=orows)
        n_items = int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])
        n_blobs = int(conn.execute("SELECT COUNT(*) FROM blobs").fetchone()[0])
        # P1-10：meta counts 全量重算（从表现算——旧账只 patch counts_items/
        # blobs 会让 plan/blob_bytes 账漂移）
        n_plan_items = int(conn.execute(
            "SELECT COUNT(*) FROM plan_items").fetchone()[0])
        n_plans = int(conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0])
        blob_bytes_total = int(conn.execute(
            "SELECT COALESCE(SUM(size),0) FROM blobs").fetchone()[0])
        plan_status = S.recompute_plan_status(
            conn, [S.plan_key(card_id=cid, locale=loc,
                              card_data_sha=(r["data_sha"] or ""))
                   for cid, r in carddef_rows.items()])
        comp = S.expected_vs_built(conn, scope_cards=decode_set)
        comp["gate"] = "targeted-scope"     # 发布门词面（定向补建 scope 语义同 partial）
        decode_err = {k: _capped_errors(v)
                      for k, v in acc["decode_errors"].items()}
        conn.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", [
            ("counts_items", str(n_items)),
            ("counts_blobs", str(n_blobs)),
            ("counts_plan_items", str(n_plan_items)),
            ("counts_plans", str(n_plans)),
            ("blob_bytes", str(blob_bytes_total)),
            ("completeness_json", S.cjson(
                {k: comp[k] for k in ("gate", "plans", "expectationless_cards",
                                      "missing_total", "missing_in_scope",
                                      "missing_out_scope", "by_kind")})),
            ("decode_errors_json", S.cjson(decode_err)),
            ("wall_total_s", f"{time.time() - t_start:.2f}"),
            ("targeted_cards", str(len(decode_set))),
        ])
        if comp["missing_in_scope"]:
            conn.close()
            raise RuntimeError(
                "targeted build 完整性门：scope 内缺预期产物 "
                f"{comp['missing_in_scope']} 项（by_kind={comp.get('by_kind')}）"
                "——不发布 partial 代；先查 decode_errors/locator 输入")
        conn.commit()
        conn.close()
        prev = layout.read_current() or {}
        layout.write_current({**prev, "updated_at": now})
    wall = time.time() - t_start
    return {"mode": "targeted-db", "game_id": game_id,
            "generation": f"gen-{game_id}", "decode_cards": len(decode_set),
            "decode_targets": len(want), "items": acc["items"],
            "plan_status": plan_status,
            "decode_errors": decode_err,
            "blob_fresh": acc["blob_fresh"],
            "blob_bytes": acc["blob_bytes_unique"],
            "wall_s": round(wall, 2), "walls": {"decode": round(t_decode, 2)},
            "db": str(db_path)}


def _win_from_ctx() -> Path:
    from eidolon.core.infra import context

    return context.current().data_win


def _publish(layout: SupplyLayout, db_path: Path, game_id: str, loc: str,
             ident: dict, now: int, full: bool = True) -> None:
    """DB os.replace 发布 + current.json 原子切（Windows 只读句柄短重试）。

    journal 回 DELETE（checkpoint 收进主文件）再 replace——只读 warm 句柄无
    WAL sidecar 依赖（route.db journal_mode=delete 同判据）。"""
    from eidolon.core.supply_index.paths import _replace_with_retry

    conn = S.connect(db_path)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.close()
    final_db = layout.gen_db(game_id)
    _replace_with_retry(db_path, final_db)
    prev = layout.read_current() or {}
    layout.write_current({
        "game_id": game_id, "generation": f"gen-{game_id}",
        "locale": loc, "identity": ident["identity"], "full_build": bool(full),
        "updated_at": now,
        "previous_generation": prev.get("generation"),
    })
    # 健康 stamp（T2 warm-perf）：刚发布=本包事务性写出的新库，how="build"（保证
    # 强于 quick_check——新库带尾部 integrity 扫；warm open 据此免全扫）。写失败
    # 无害：下次 open 走 quick_check 全检并自写 stamp。
    layout.write_health_stamp(game_id, db_path=final_db, locale=loc, how="build")
