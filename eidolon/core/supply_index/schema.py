"""schema — per-gen index.sqlite 表结构 + 键派生单源。

表结构对照 v4 设计 §4 的差异（表名/列名可改，键面「必须保留」条款不动）：
- objects/containers 只存**本代触达对象**（carddef+portrait），不存全语料——本包
  不是 route.db 变体（设计「供给独立」+ 全量对象面归航线库）；
- locators 增 premium 列（v4 已有）并把 kind 收敛为 carddef/portrait/portrait_golden
  三个 P1 值；absent（卡无 golden 字段）不落行（缺席是计划内事实，不是 locator 失败）；
  P2 车2 增 kind='kit'（帧族）/'watermark'（卡级水印）；
- items.manifest_json 内嵌完整消费账（payload sha/尺寸/来源地址），warm 单查询即可
  供货；item_blobs.role 区分多 blob 项（P1 只有 'portrait'；P2 kit 六面、text 域
  fontdefs/ttf）；
- plans 保留 v4 形态（plan_key 含 card_data_sha=carddef 对象 sha）；P2 车2
  plan_items 落位=portrait/golden/kit/kit_play/gems/watermark（text=全域项走域
  访问器，不 per-card 挂接——26MB TTF 面 per-card 重复拖运=架构错位，记账显式）；
  Phase 5 返工 R1 起 plan_items 增「期望但未建」哨兵行形态（item_key=expect::*
  前缀、role 带真实 role——kit/gems 无 per-card locator 行时的期望落账，
  expected_item_key/expected_vs_built/recompute_plan_status 单源）。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

SCHEMA_VERSION = "1"
# PLAN_VERSION 5（Phase 1 A6）：kit 域扩 races/mesh_refs 两面（kit 内容聚合 sha
# 变 → kit item 键变，plan_items 的 kit 引用随之换键）+ supplement 域落库
# （特源/附件 kit：ability_kit/badges_kit/btf_kit/ornaments_kit/ta_supplement/
# material_state/portrait_uv1 + text.font_asset_params——全部卡不变全局项，
# warm 域访问器供给不挂 plan，text/color.atlas/mip_registry 同款记账）——
# plan 引用面变了，版本随动（v4 代 plan_key 构造性失效 → warm plan() missing →
# assemble fail loud → 种子器整卡弃种回 live，全量重建切代）。
PLAN_VERSION = 5
CODEC = "png"
CODEC_VERSION = 1

# 键面域词（v4：item_key=sha256(domain|item|params|locale|style|premium|codec|
# codec_version|content_inputs_json)；P1 style 恒空串）
DOMAIN = "art"
ITEM_PORTRAIT = "portrait"
DOMAIN_FRAMES = "frames"
ITEM_KIT = "kit"
DOMAIN_GEMS = "gems"
DOMAIN_WATERMARK = "watermark"
ITEM_WATERMARK = "watermark"
DOMAIN_TEXT = "text"
ITEM_FONTDEFS = "fontdefs"
ITEM_FONT_TTF = "font_ttf"
# color 域（Phase 1 A4）：probe=switcher 表（卡不变全域项，per-card plan 挂接
# role='color'——已知卡型卡的 compile 无条件读 probe）；atlas=类色图集（按
# (family, ct) 的域级项，warm 访问器供给不挂 plan——212 槽 per-card 重复挂接
# =架构错位，text 域同款记账）。
DOMAIN_COLOR = "color"
ITEM_COLOR_PROBE = "probe"
ITEM_COLOR_ATLAS = "atlas"
# mip 面（Phase 1 A5）：portrait_mip=per-card 肖像真 mip 链（live art.portrait_mip
# 同形 {"name","chain","filter","bias"}；blob=NPZ 第 1..n-1 级，L0 由 portrait PNG
# 派生——cold 期逐纹理验证位等，失配落显式 L0）；mip_registry=textures 域全局项
# （live 23 条静态链，卡不变全域项，warm 访问器供给不挂 plan——text 域同款）。
DOMAIN_ART = DOMAIN
ITEM_PORTRAIT_MIP = "portrait_mip"
DOMAIN_TEXTURES = "textures"
ITEM_MIP_REGISTRY = "mip_registry"

# supplement 域（Phase 1 A6）：特源/附件 kit + 字体资产参数——**卡不变全局项**
# （live 域函数零参数或枚举参数；值面=live 提取产物内存对象），warm 域访问器
# 供给、seed 侧按 shape 重组 live 对象；不挂 plan_items（text/color.atlas/
# mip_registry 同款记账——per-card 重复挂接=架构错位）。kit_light=轻走查 kit
# （同 kit 六面 codec 的独立 item，item 名区分防 kit_item_key memo 撞键）。
SUPP_CODEC = "supp"
SUPP_CODEC_VERSION = 1
ITEM_KIT_LIGHT = "kit_light"
ITEM_ABILITY_KIT = "ability_kit"
ITEM_BADGES_KIT = "badges_kit"
ITEM_BTF_KIT = "btf_kit"
ITEM_ORNAMENTS_KIT = "ornaments_kit"
ITEM_TA_SUPPLEMENT = "ta_supplement"
ITEM_MATERIAL_STATE = "material_state"
ITEM_PORTRAIT_UV1 = "portrait_uv1"
ITEM_FONT_ASSET_PARAMS = "font_asset_params"
# live FRAME_SPECS races=True 帧族词面（kit races 面的期望人口；缺面=kit token
# 不种——种缺 races 的 ally Kit 会在 GetRaceText 炸，A3 纪律）。
KIT_RACE_FRAMES = ("ally", "ally_premium", "trinket")

# 期望落账（Phase 5 返工 R1，P0-1）：expected-vs-built 完整性门的单源词面。
# - card 级期望（locators 表 status='ok' 的行即「应有」）：kinds 限下面三值
#   （p5-smoke2 实测 locators kind 集合=portrait/portrait_golden/watermark/kit/
#   fontdefs/font_ttf；后三者是域级/帧级行——kit subject=frame 名、fontdefs/
#   font_ttf subject=表/字体名，不进 per-card 期望面）；
# - kit/kit_play/gems 无 per-card locator 行 → cold 在 plan 挂接段把「期望但未建」
#   落成显式哨兵行（plan_items.item_key=expect::* 前缀，role 列带真实 role；
#   内容派生键恒 sha256 hex，前缀形态构造性无撞键）。
CARD_LOCATOR_KINDS = ("portrait", "portrait_golden", "watermark")
EXPECTED_KEY_PREFIX = "expect::"


def expected_item_key(tag: str) -> str:
    """「期望但未建」哨兵 plan_items 行的 item_key（role 列带真实 role）。

    形态 expect::<role-tag>（如 expect::kit:violet / expect::gem:clouds）——
    非 sha256 hex，与内容派生键空间不相交；warm.plan() 据前缀识别为期望缺口
    （缺项清单点名 role），integrity/blob 面零影响（无 items/item_blobs 行）。"""
    return f"{EXPECTED_KEY_PREFIX}{tag}"

DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE asset_catalog (
  guid TEXT NOT NULL, bundle TEXT NOT NULL,
  PRIMARY KEY (guid, bundle)
) WITHOUT ROWID;

CREATE TABLE asset_variants (
  base_guid TEXT NOT NULL, layer TEXT NOT NULL, locale TEXT NOT NULL DEFAULT '',
  guid TEXT NOT NULL, bundle TEXT NOT NULL,
  PRIMARY KEY (base_guid, layer, locale)
) WITHOUT ROWID;

CREATE TABLE cards (
  card_id TEXT PRIMARY KEY,
  dbf_id INTEGER,
  carddef_ref TEXT NOT NULL,
  carddef_guid TEXT NOT NULL,
  carddef_bundle TEXT NOT NULL,
  carddef_cab TEXT NOT NULL DEFAULT '',
  carddef_path_id INTEGER NOT NULL DEFAULT 0,
  data_sha TEXT
) WITHOUT ROWID;

CREATE TABLE bundles (
  name TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
  sha256 TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE containers (
  bundle TEXT NOT NULL, key TEXT NOT NULL, path_id INTEGER NOT NULL,
  ord INTEGER NOT NULL,
  PRIMARY KEY (bundle, key, ord)
) WITHOUT ROWID;

CREATE TABLE objects (
  bundle TEXT NOT NULL, cab TEXT NOT NULL, path_id INTEGER NOT NULL,
  class_id INTEGER NOT NULL, byte_start INTEGER NOT NULL, byte_size INTEGER NOT NULL,
  PRIMARY KEY (bundle, cab, path_id)
) WITHOUT ROWID;

CREATE TABLE locators (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  subject TEXT NOT NULL,
  locale TEXT NOT NULL DEFAULT '',
  premium TEXT NOT NULL DEFAULT '',
  ref TEXT, guid TEXT,
  bundle TEXT NOT NULL, cab TEXT NOT NULL, path_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'ok', source_json TEXT NOT NULL,
  UNIQUE (kind, subject, locale, premium)
);

CREATE TABLE locator_inputs (
  locator_id INTEGER NOT NULL, bundle TEXT NOT NULL, cab TEXT NOT NULL,
  path_id INTEGER NOT NULL, bundle_sha256 TEXT NOT NULL, object_sha256 TEXT NOT NULL,
  PRIMARY KEY (locator_id, bundle, cab, path_id)
) WITHOUT ROWID;

CREATE TABLE plans (
  plan_key TEXT PRIMARY KEY,
  card_id TEXT NOT NULL,
  options_json TEXT NOT NULL,
  status TEXT NOT NULL,
  plan_version INTEGER NOT NULL,
  card_data_sha TEXT NOT NULL,
  created_at INTEGER NOT NULL
) WITHOUT ROWID;

CREATE TABLE plan_items (
  plan_key TEXT NOT NULL,
  item_key TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (plan_key, item_key)
) WITHOUT ROWID;

CREATE TABLE items (
  item_key TEXT PRIMARY KEY,
  domain TEXT NOT NULL, item TEXT NOT NULL, params_json TEXT NOT NULL,
  codec TEXT NOT NULL, codec_version INTEGER NOT NULL,
  manifest_json TEXT NOT NULL, status TEXT NOT NULL,
  source_kind TEXT NOT NULL, source_json TEXT NOT NULL,
  content_inputs_json TEXT NOT NULL,
  created_at INTEGER NOT NULL
) WITHOUT ROWID;

CREATE TABLE item_blobs (
  item_key TEXT NOT NULL, blob_key TEXT NOT NULL, role TEXT NOT NULL,
  PRIMARY KEY (item_key, blob_key, role)
) WITHOUT ROWID;

CREATE TABLE blobs (
  blob_key TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL, size INTEGER NOT NULL,
  codec TEXT NOT NULL, codec_version INTEGER NOT NULL,
  last_used INTEGER NOT NULL, created_at INTEGER NOT NULL
) WITHOUT ROWID;

CREATE TABLE migration_report (
  game_id TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL,
  status TEXT NOT NULL, reason TEXT NOT NULL, detail_json TEXT,
  PRIMARY KEY (game_id, kind, key)
) WITHOUT ROWID;
"""


def connect(path, *, readonly: bool = False) -> sqlite3.Connection:
    """打开代 DB。readonly=URI 只读 + mmap（warm 热路径；缺库=FileNotFoundError）。"""
    if readonly:
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA mmap_size=268435456")   # 256MB 热路径 mmap
    else:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)


# ---------------------------------------------------------------------------
# 键派生（单源；canonical JSON=sort_keys+紧凑分隔符）
# ---------------------------------------------------------------------------

def cjson(obj) -> str:
    """canonical JSON（键派生与 content_inputs 落盘统一形态）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def item_key(*, card_id: str, kind: str, locale: str, premium: str,
             content_inputs: dict) -> str:
    """item 内容派生键（必须保留 #6：全部内容输入进键）。

    domain/item/params/locale/premium/codec/codec_version + content_inputs_json
    （portrait 像素 sha + carddef 对象 sha）——任何影响 item 值的输入缺位即静默串图，
    在派生式上构造性排除。"""
    payload = {
        "domain": DOMAIN,
        "item": ITEM_PORTRAIT,
        "params": {"card_id": card_id, "kind": kind},
        "locale": locale,
        "style": "",
        "premium": premium,
        "codec": CODEC,
        "codec_version": CODEC_VERSION,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def blob_key(*, portrait_content_sha: str) -> str:
    """blob_key = sha256(object_content | codec | codec_version | params)（v4 §4.2）。

    P1 portrait 面专用形（domain 词='portrait'）；P2 车起新域走 blob_key_generic
    （同公式，域词区分）——本函数字节面不动（P1 键面兼容）。"""
    return blob_key_generic(domain="portrait", content_sha=portrait_content_sha,
                            codec=CODEC)


def blob_key_generic(*, domain: str, content_sha: str, codec: str,
                     codec_version: int = CODEC_VERSION) -> str:
    """泛化 blob_key = sha256(domain | content_sha | codec | version |)（v4 §4.2 公式）。

    content_sha=该 blob 的**内容身份**（PNG=像素 sha、JSON=canonical 字节 sha、
    TTF=文件字节 sha——文件即产物，不踩 resS 假身份坑）。域词进键：同内容跨域
    不共 blob 行（文件层仍按 payload_sha 去重）。"""
    return sha256_hex("|".join([
        domain, content_sha, codec, str(codec_version), "",
    ]).encode("utf-8"))


def kit_item_key(*, frame: str, locale: str, content_inputs: dict) -> str:
    """kit item 内容派生键（必须保留 #6 的结构物实现；kit=卡不变游戏结构，键无
    card_id——per-card 供 给 面=plan 装配层（车2））。

    content_inputs={actor_ref（活表串）, guid（resolved）, kit（六面内容聚合 sha，
    kit_codec.kit_content_sha——A6 起 races/mesh_refs 两面并入聚合）}——全部
    **解析后产物 sha**（m_StreamData 判例：prefab/mesh/纹理的 raw 序列化字节是
    假内容身份）。codec_version=kit_codec.KIT_CODEC_VERSION（A6=2；schema 不
    import kit_codec 防循环——字面量同步改，单测钉死两处相等）。"""
    payload = {
        "domain": DOMAIN_FRAMES,
        "item": ITEM_KIT,
        "params": {"frame": frame},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": "kit",
        "codec_version": 2,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def kit_light_item_key(*, frame: str, locale: str, content_inputs: dict) -> str:
    """kit_light item 键（Phase 1 A6；轻走查 kit——同 kit 六面 codec，item 名
    区分防 kit_item_key 的 frame→key memo 撞键；键无 card_id，卡不变全局项）。

    content_inputs 同 kit（actor_ref/guid/六面聚合 sha）。"""
    payload = {
        "domain": DOMAIN_FRAMES,
        "item": ITEM_KIT_LIGHT,
        "params": {"frame": frame},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": "kit",
        "codec_version": 2,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def supplement_item_key(*, domain: str, item: str, params: dict, locale: str,
                        content_inputs: dict) -> str:
    """supplement 域 item 键（Phase 1 A6；特源/附件 kit + font_asset_params——
    卡不变全局项，键无 card_id；codec=SUPP_CODEC，parts 内容聚合 sha 进键
    ——必须保留 #6：任何 part 内容变化即换键）。"""
    payload = {
        "domain": domain,
        "item": item,
        "params": params,
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": SUPP_CODEC,
        "codec_version": SUPP_CODEC_VERSION,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def gem_item_key(*, gem: str, locale: str, content_inputs: dict) -> str:
    """gems 域 item 键（P2 车2）。gems=手牌随从帧 prefab（ally）宝石材质纹理——
    卡不变游戏结构（gems.py 域配方：node 路径+槽名选择器），键无 card_id；
    per-card 消费面=plan 装配层。

    content_inputs={"kit": ally kit 六面聚合 sha（prefab 状态身份——gem 纹理变化
    必经 kit 内容变化）, "pixel": 纹理解码像素 sha（值身份）}——解析后产物 sha。"""
    payload = {
        "domain": DOMAIN_GEMS,
        "item": gem,
        "params": {},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": CODEC,
        "codec_version": CODEC_VERSION,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def watermark_item_key(*, card_id: str, locale: str, content_inputs: dict) -> str:
    """watermark 域 item 键（P2 车2；per-card：哪张水印=卡级裁决）。

    content_inputs={"carddef": carddef 对象 sha, "ref": 水印 ref（四级裁决值——
    ref 变=换图）, "watermark": 纹理解码像素 sha}——ref/pixel 都是值输入，全进键
    （必须保留 #6）。"""
    payload = {
        "domain": DOMAIN_WATERMARK,
        "item": ITEM_WATERMARK,
        "params": {"card_id": card_id},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": CODEC,
        "codec_version": CODEC_VERSION,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def fontdefs_item_key(*, locale: str, content_inputs: dict) -> str:
    """text 域 fontdefs item 键（P2 车2；全域项=卡不变，键无 card_id）。

    content_inputs={"fontdefs": canonical 字节 sha（值身份）}。"""
    payload = {
        "domain": DOMAIN_TEXT,
        "item": ITEM_FONTDEFS,
        "params": {},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": "json",
        "codec_version": CODEC_VERSION,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def font_ttf_item_key(*, font: str, locale: str, content_inputs: dict) -> str:
    """text 域字体 TTF item 键（P2 车2；params.font=FontDef 名——locale 生效侧）。

    content_inputs={"ttf": 文件字节 sha}——TTF 文件字节即产物，文件 sha=内容身份
    （任务书口径：不踩 resS 坑）。"""
    payload = {
        "domain": DOMAIN_TEXT,
        "item": ITEM_FONT_TTF,
        "params": {"font": font},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": "ttf",
        "codec_version": CODEC_VERSION,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def color_probe_item_key(*, locale: str, content_inputs: dict) -> str:
    """color 域 switcher 表 item 键（Phase 1 A4；全域项=卡不变，键无 card_id）。

    content_inputs={"probe": canonical 字节 sha（值身份——12 族槽位表）,
                    "ref": 链根 ref（资产身份——链根换=表换）}——ref/probe 都是
    值输入，全进键（必须保留 #6）。"""
    payload = {
        "domain": DOMAIN_COLOR,
        "item": ITEM_COLOR_PROBE,
        "params": {},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": "json",
        "codec_version": CODEC_VERSION,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def color_atlas_item_key(*, family: str, ct: int, locale: str,
                         content_inputs: dict) -> str:
    """color 域类色图集 item 键（Phase 1 A4；params={family, ct}——probe 族表
    槽位寻址，卡不变域，键无 card_id；per-card 消费面=plan 装配层不挂接）。

    content_inputs={"ref": probe 表槽位 ref（值选择器——ref 变=换图）,
                    "guid": 解析后 guid（变体叠加产物——locale 生效侧）,
                    "pixel": 纹理解码像素 sha（值身份）}——解析后产物 sha
    （m_StreamData 判例：raw 序列化字节是假内容身份）。"""
    payload = {
        "domain": DOMAIN_COLOR,
        "item": ITEM_COLOR_ATLAS,
        "params": {"family": family, "ct": int(ct)},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": CODEC,
        "codec_version": CODEC_VERSION,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def portrait_mip_item_key(*, card_id: str, locale: str, content_inputs: dict) -> str:
    """art 域肖像真 mip 链 item 键（Phase 1 A5；per-card=消费 token 是
    art.portrait_mip(card_id)，blob=同纹理去重（内容寻址天然合并——16.8k 纹理
    /28.9k 卡））。

    codec='npz'（链第 1..n-1 级数组；L0 由 portrait PNG 派生——cold 期逐纹理
    验证位等，失配落显式 L0 级）。content_inputs={"carddef": carddef 对象 sha,
    "portrait": 肖像像素 sha（L0 派生源身份）, "chain": 存储级数组内容聚合 sha,
    "meta": {name,filter,bias,mip_count,source} canonical sha（采样器语义输入，
    全进键——必须保留 #6）}。"""
    payload = {
        "domain": DOMAIN_ART,
        "item": ITEM_PORTRAIT_MIP,
        "params": {"card_id": card_id, "kind": ITEM_PORTRAIT_MIP},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": "npz",
        "codec_version": 1,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def mip_registry_item_key(*, locale: str, content_inputs: dict) -> str:
    """textures 域 mip 链注册表 item 键（Phase 1 A5；全局项=卡不变，键无
    card_id，不挂 plan_items——text/color.atlas 同款记账）。

    content_inputs={"chains": 23 链全部级别数组内容聚合 sha, "table": 链表
    (name,bundle,path_id) canonical sha（寻址面契约——live _MIP_CHAINS 逐字
    同源表，表变=链面变）}。"""
    payload = {
        "domain": DOMAIN_TEXTURES,
        "item": ITEM_MIP_REGISTRY,
        "params": {},
        "locale": locale,
        "style": "",
        "premium": "",
        "codec": "npz",
        "codec_version": 1,
        "content_inputs": content_inputs,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


def plan_key(*, card_id: str, locale: str, card_data_sha: str,
             options: dict | None = None) -> str:
    """plan_key = sha256(plan_version | card_ref | options | locale | card_data_sha)。

    P1 无覆盖（overrides_hash 缺位=空串）；card_data_sha=carddef 对象 sha
    （cards.data_sha）——carddef 内容变化即 plan 失效（v4 §7.3）。"""
    payload = {
        "plan_version": PLAN_VERSION,
        "card_id": card_id,
        "options": options or {},
        "overrides_hash": "",
        "locale": locale,
        "card_data_sha": card_data_sha,
    }
    return sha256_hex(cjson(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# expected-vs-built 完整性账（Phase 5 返工 R1，P0-1/P0-2 单源；纯函数零 I/O——
# conn 由调用方给。消费方：cold 尾部发布门 / audit full 门 / warm 缺项面同判据）
# ---------------------------------------------------------------------------

def _role_bucket(role: str) -> str:
    """plan role → 完整性分域桶（portrait/portrait_golden/watermark 原名；
    gem:X → gems 聚合桶）。"""
    if role.startswith("gem:"):
        return "gems"
    return role


def _expected_built_maps(conn: sqlite3.Connection) -> tuple[
        dict[str, str], dict[str, set[str]], dict[str, set[str]]]:
    """一趟装载 (card→plan_key, expected per plan, built per plan)。

    expected = plan_items 全部 role（含 expect::* 哨兵行——kit/kit_play/gems 的
    「期望但未建」落账）∪ locators 表 status='ok' 的 card 级 kind
    （CARD_LOCATOR_KINDS）；built = plan_items 中 **items 行存在且至少有一条
    item_blobs 行**的 role（Phase 5 审计 P2：只有 items 行而 item_blobs 链断
    =不可装配，必须与「无 items 行」同判缺口；否则 expected_vs_built 会漏账）。
    空 role（''）不入账（列缺省值，无语义）。"""
    card_plan: dict[str, str] = {}
    expected: dict[str, set[str]] = {}
    built: dict[str, set[str]] = {}
    for r in conn.execute("SELECT plan_key, card_id FROM plans"):
        card_plan[r["card_id"]] = r["plan_key"]
    for r in conn.execute("SELECT plan_key, role FROM plan_items"):
        role = r["role"] or ""
        if role:
            expected.setdefault(r["plan_key"], set()).add(role)
    for r in conn.execute(
            "SELECT pi.plan_key AS plan_key, pi.role AS role FROM plan_items pi "
            "JOIN items i ON i.item_key=pi.item_key "
            "WHERE EXISTS (SELECT 1 FROM item_blobs ib "
            "              WHERE ib.item_key=pi.item_key)"):
        role = r["role"] or ""
        if role:
            built.setdefault(r["plan_key"], set()).add(role)
    ph = ",".join("?" * len(CARD_LOCATOR_KINDS))
    for r in conn.execute(
            f"SELECT subject, kind FROM locators "
            f"WHERE status='ok' AND kind IN ({ph})", CARD_LOCATOR_KINDS):
        pk = card_plan.get(r["subject"])
        if pk is not None:
            expected.setdefault(pk, set()).add(r["kind"])
    return card_plan, expected, built


def expected_vs_built(conn: sqlite3.Connection, *,
                      scope_cards: set[str] | None = None) -> dict:
    """全库 expected-vs-built 完整性账（发布门/audit 门的判据函数）。

    缺项判定与 warm 逐卡面同一判据：期望（locator-ok card 级 kind + plan_items
    哨兵/实体 role）⊆ built（items 行存在且 item_blobs 链在的 role）。scope_cards=
    None（全量代），给定（partial/sampled 代）时缺项分 in-scope（--cards/--sample
    期望集内，发布门阻断）/ out-of-scope（scope 外 expected 静默缺失——partial 代
    定义如此，只列账不阻断）。返回 dict：by_kind 分桶账 + 缺项样例 +
    expectationless 卡数（零期望卡=数据缺席合法形态，单独计数不进缺项；
    **这类卡的 plan.status 为 complete**——期望空集 ⊆ built 恒真，与
    recompute_plan_status 同一实现）。"""
    card_plan, expected, built = _expected_built_maps(conn)
    # plan→card 反查表（一次）
    pk_card = {pk: cid for cid, pk in card_plan.items()}
    missing_pairs: list[tuple[str, str, str]] = []   # (card_id, role, bucket)
    for pk, roles in expected.items():
        miss = roles - built.get(pk, set())
        if not miss:
            continue
        cid = pk_card.get(pk, pk)
        for role in sorted(miss):
            missing_pairs.append((cid, role, _role_bucket(role)))
    missing_pairs.sort()
    missing_pairs.sort()
    in_scope = out_scope = 0
    for cid, _role, _bucket in missing_pairs:
        if scope_cards is None or cid in scope_cards:
            in_scope += 1
        else:
            out_scope += 1
    by_kind: dict[str, dict] = {}
    exp_buckets: dict[str, set[str]] = {}
    for pk, roles in expected.items():
        for role in roles:
            exp_buckets.setdefault(_role_bucket(role), set()).add(pk)
    miss_by_bucket: dict[str, set[str]] = {}
    miss_roles_by_bucket: dict[str, int] = {}
    for cid, role, bucket in missing_pairs:
        pk = card_plan.get(cid)
        miss_by_bucket.setdefault(bucket, set()).add(cid)
        miss_roles_by_bucket[bucket] = miss_roles_by_bucket.get(bucket, 0) + 1
    for bucket, pks in sorted(exp_buckets.items()):
        by_kind[bucket] = {
            "expected_cards": len(pks),
            "missing_cards": len(miss_by_bucket.get(bucket, set())),
            "missing_roles_total": miss_roles_by_bucket.get(bucket, 0),
        }
    return {
        "plans": len(card_plan),
        "expectationless_cards": sum(1 for pk in card_plan.values()
                                     if not expected.get(pk)),
        "missing_total": len(missing_pairs),
        "missing_in_scope": in_scope,
        "missing_out_scope": out_scope,
        "by_kind": by_kind,
        "missing_sample": [{"card_id": cid, "role": role}
                           for cid, role, _b in missing_pairs[:20]],
    }


def recompute_plan_status(conn: sqlite3.Connection,
                          plan_keys: list[str] | None = None) -> dict:
    """plans.status ← expected-vs-built（「complete=expected 全部 built」单源实现）。

    零期望卡（expectationless，数据无美术的合法缺席）：expected 空集 − built =
    空集 → ``complete``——这是「complete ≠ 必须有产物」的明确 API 语义。
    plan_keys=None 全表重算（build 尾部一次）；给子集（定向补建 scope）只动
    指定行。UPDATE 后返回 {complete, partial} 计数。"""
    _card_plan, expected, built = _expected_built_maps(conn)
    targets = plan_keys
    if targets is None:
        targets = [r["plan_key"] for r in conn.execute("SELECT plan_key FROM plans")]
    rows = []
    n_complete = n_partial = 0
    for pk in targets:
        miss = expected.get(pk, set()) - built.get(pk, set())
        status = "complete" if not miss else "partial"
        rows.append((status, pk))
        if status == "complete":
            n_complete += 1
        else:
            n_partial += 1
    conn.executemany("UPDATE plans SET status=? WHERE plan_key=?", rows)
    return {"complete": n_complete, "partial": n_partial}
