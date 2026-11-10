"""warm — 暖侧只读供给（无 UnityPy、不开游戏 *.unity3d；机器证明见 audit.py）。

读路径：current.json → gen-<id>/index.sqlite（只读 mmap）→ plan_items → items →
item_blobs → blobs → blob 文件（内容寻址）→ 内存产物。消费者拿内存对象——blob 是
supply 内部持久形态，不是消费 API（render-cache-map §②：不重开 materialize 的
Path 逃生口）。

P2 车2 全卡装配面：plan_items 落位=portrait/portrait_golden/kit/kit_play/
gem:*/watermark（per-card 消费面）；assemble 按 item codec 分发（png→Image、
kit→六面 dict、json→dict、ttf→bytes）。**text 域=卡不变全域供给**（26MB 级
TTF 面不 per-card 挂 plan）——域访问器 text() 供货、进程内缓存一次；assemble_card
= plan 装配束 + text 全域段。

Phase 1 A4 color 域：probe item per-card 挂 plan（role='color'，已知卡型卡
kit 挂接同人口——assemble_card 束随卡带 probe 表）；atlas=按 (family, ct) 的
域级项**不挂 plan**（212 纹理槽 per-card 重复挂接=架构错位，text 同款记账）
——``color_probe()`` / ``color_atlas(family, ct)`` 域访问器供货（同 live 形：
dict[str, list[str]] / PIL Image），图集解码入共享域 LRU。缺项 fail loud 与
全域缺项语义同一报错面（SupplyMissingError）。

共享项缓存（设计 §5.1 进程内热层）：域 frames/gems 的解码产物进程内 LRU（键=
item_key；kit 六面 ~30MB/件，界=8）——卡不变项每卡重解码会吃穿吞吐预算。**缓存
对象按引用返回，消费契约=禁 mutate**（portrait/watermark 每卡独立解码不受此限）。

缺项语义（fail loud）：卡不在 cards / plan 缺 / item 缺 / blob 行缺 / blob 文件缺 /
blob sha 不匹配 → SupplyMissingError 带完整缺项清单（--mode require-cache/offline
审计形态同一报错面）。portrait 缺席分两态：locator 在而 item 缺=decode 缺口（缺项）；
locator 全无=数据缺席（卡无 portrait 字段，合法——check 记账不报缺）。

expected-vs-built 完整性门（Phase 5 返工 R1，P0-1；判据单源=schema
expected_vs_built/recompute_plan_status 同一账面）：**golden/kit/gems/watermark
属「完整供给」必须项**——plan() 逐卡算期望集：
- locators 表 status='ok' 的 card 级 kind（portrait/portrait_golden/watermark）
  即「应有」（期望权威面=cold 期 locate 行账）；
- kit/kit_play/gems 的「期望但未建」由 cold plan 挂接段落成显式哨兵行
  （plan_items.item_key=expect::* 前缀——schema.expected_item_key）；
期望∩已实现 role 词汇表中有而 plan 无对应 item/blob → 逐项点名 kind 入
plan.missing；**plan.complete 语义=expected 全部 built**（assemble_card 缺项
fail loud；allow_partial=True 是显式豁免口——产品路径不传，测试/审计 partial
代专用）。

缺席归因面（Phase 5 返工 R2）：`account_for_cards(conn, card_ids)` 把卡集
四分类——ok / missing_gap（有期望未满足，**full 代红判据只看它**）/
absent_locator_missing / absent_expectationless（两类可归因数据缺席）+ anomaly
单列；**缺席可归因 ≠ 失败**（与 build 发布门 expected-vs-built 同口径），
audit/verify/bench 门共此判据。

自愈面（2026-11-07 自愈车；T2 warm-perf 起懒检分档）：
- open 自检：SupplyIndex 构造时代库自检（health_policy 三档）——
  * stamp（缺省，产品 require-cache/offline 面）：健康 stamp sidecar
    (db_size, db_mtime_ns) 身份匹配+24h 未超窗+无 -wal 残留 → **跳过 quick_check
    全扫**（locale 走 stamp 账；小进程产品形态的 open 成本从 ~0.42s 降到 ~ms）；
    stamp 缺/失配/超窗 → quick_check 全检一回并 best-effort 刷新 stamp。
  * full（selfheal.ensure_index=auto 重建编排专用）：**恒 quick_check**——L1 检测
    语义零弱化（含 bit rot 不改 mtime 的形态）。
  * skip：只开连接读 meta.locale（测量对照面）。
  DB 打不开形态照旧归损坏面（conn 触达即 SupplyIndexCorruptError 响亮；auto 模式
  重建编排在 selfheal/cli 层——本模块不 import UnityPy 面）。
  **残余风险（决策账，T2）**：物理 bit rot 不改 (size, mtime_ns) 且未超 24h 窗时，
  stamp 档 open 不检—— corruption 靠 L2 blob 文件 sha 校验与读错误兜底响亮
  （任务书明确接受此残险）；auto/full 档不受影响；页级损坏若在触达页上，只读连接
  抛 sqlite3.DatabaseError 响亮。写面（build 定向补卡/integrity 留账等）改动 DB
  文件即 mtime 翻新 → stamp 构造性失效，下次 open 重检。
- blob sha 不匹配=SupplyBlobCorruptError（SupplyMissingError 子类，fail loud 语义
  不变；auto 模式单次重推导自愈同样在 selfheal/cli 层接线）——require-cache/offline
  恒响亮不自愈，纯 warm 机器证明不退化。

T3 warm-perf：kit 首装配两刀（profile 实测 ally：总 122.8ms=PNG 解码 87.5+像素
sha 27.3+NPZ 11.5+读 7.5+JSON 2.7+内容 sha 复推导 4）：
1. decode_kit(verify_content=False)——warm 侧只保留**blob 文件字节 sha 校验**
   （=L2 介质损坏检测面，逐次读取都过）；decode_kit 内的内容 sha 复推导（JSON
   canonical/数组内容/纹理像素 sha）不再在 warm 逐次执行：文件字节 sha 相等 ⇒
   字节与 build 时一致 ⇒ 解码确定 ⇒ 内容恒等（复推导只可能检出「解码器漂移」，
   该语义归 verify 面所有——verify/单测仍走 verify_content=True 与 compare_kit
   全量比对）。
2. decode_threads=4——纹理面 PNG 解码并行（PIL 解码 C 层放 GIL：28 纹理
   68→22ms@4 线程；ex.map 保序，逐字段一致面不变）。
kit 重组逐字段一致由 tests/test_kit_reassembly.py+verify 保证；raw 全量 tier
不重开（P3 否决账不动）。

本模块 import 面（audit 静态+机器双证）：stdlib + PIL + 本包 schema/paths/
kit_codec/text_codec/mip_codec/supp_codec——**禁 UnityPy / texture2ddecoder /
eidolon.core.render / eidolon.core.supply / eidolon.core.recipes / kit_extract /
text_extract / wm_extract / cold / mip_extract / supplement_extract**（后四者=
UnityPy 面；gems 重组=png 通用解码路径，无需专属 codec import）。

Phase 1 A5 mip 面：``mip_registry()``（textures 域全局项，23 条静态链全级
NPZ → live 同形 name → {lods,filter,bias}）/ ``portrait_mip(card_id)``
（per-card 肖像真链，live art.portrait_mip 同形 {name,chain,filter,bias}——
chain=``WarmChain``（live LazyFloatChain 同协议 len/getitem/peek/shape0 +
``.lods`` 原始 uint8 访问，seed 侧 LazyFloatChain(lods) 直构））。链 blob
NPZ 解码 + blob 文件字节 sha 逐次校验；缺项 SupplyMissingError（现有语义）。
**warm mip 读取零开包**（audit import/open blocker 同窗机器证明）。
"""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from eidolon.core.supply_index import kit_codec as KC
from eidolon.core.supply_index import mip_codec as MC
from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index import supp_codec as SC
from eidolon.core.supply_index import text_codec as TC
from eidolon.core.supply_index.paths import SupplyLayout

# 解码 LRU 界（kit 六面 dict 大件；gems/color 图集小件同池）。A6：8→16——
# seeded 路径全帧族 kit（10 full + 9 light）常驻=live _KIT_CACHE 进程 memo
# 同形（跨卡共享单实例）；10 full kit ~300MB 在界内（界 16 容 ~480MB）。
_SHARED_CACHE_MAX = 16
# 共享域（卡不变项→解码缓存池）；art/watermark=per-card 项不缓存
_SHARED_DOMAINS = frozenset({"frames", "gems", "color"})
# 健康 stamp 复检窗（T2：quick_check 全检间隔；身份失配/-wal 帧残留不受此窗豁免）
HEALTH_STAMP_TTL_S = 86400
# kit 纹理面并行解码线程数（T3：PIL 解码放 GIL，28 纹理 68→22ms@4；>8 边际趋零）
_KIT_DECODE_THREADS = 4
_HEALTH_POLICIES = ("stamp", "full", "skip")


class WarmChain:
    """warm 链视图（A5）：live ``supply.textures.LazyFloatChain`` 同协议——
    ``__len__`` / ``__getitem__`` / ``peek`` / ``shape0`` + ``.lods`` 原始 uint8
    访问（seed 侧 ``LazyFloatChain(chain.lods)`` 直构 live 形；audit/对账测试
    消费同一协议面）。

    uint8 层构造时已在手（npz 解码产物——live ``_extract_chain`` 同为全级
    uint8 在手后惰性转 float）；float64 转换逐层惰性（同一 astype/255 表达式，
    值面逐位一致）。``.lods`` 按引用返回禁 mutate（共享项缓存契约同款）。"""

    __slots__ = ("_lods", "_cache")

    def __init__(self, lods) -> None:
        self._lods = list(lods)
        self._cache: dict[int, np.ndarray] = {}

    @property
    def lods(self) -> list:
        """原始 uint8 层（按引用；禁 mutate）。"""
        return self._lods

    def __len__(self) -> int:
        return len(self._lods)

    def peek(self, i: int) -> np.ndarray:
        """物化第 i 层但**不入缓存**（值面与 ``self[i]`` 逐位相同）。"""
        return self._lods[i].astype(np.float64) / 255.0

    def __getitem__(self, i: int) -> np.ndarray:
        lev = self._cache.get(i)
        if lev is None:
            lev = self.peek(i)
            self._cache[i] = lev
        return lev

    def shape0(self) -> tuple[int, int]:
        """链 L0 的 (h, w)——结构守卫用，零物化。"""
        return tuple(self._lods[0].shape[:2])


class SupplyMissingError(RuntimeError):
    """缺项 fail loud（message 内带逐项清单）。"""

    def __init__(self, missing: list[str]):
        self.missing = missing
        head = missing[0] if missing else ""
        more = f"（另 {len(missing)-1} 项）" if len(missing) > 1 else ""
        super().__init__(f"supply 缓存缺项 {len(missing)} 项：{head}{more}"
                         "——先跑 cold build（缺项清单见 .missing）")


class SupplyIndexCorruptError(RuntimeError):
    """代库索引损坏（quick_check 失败 / DB 打不开）——auto 重建或人工重建（响亮）。"""


class SupplyBlobCorruptError(SupplyMissingError):
    """blob 文件字节 sha ≠ 行账（介质/内容损坏面）。

    仍属缺项 fail loud 家族（is-a SupplyMissingError——审计/CLI 的响亮面同一报错
    语义）；附 path/payload_sha 供 auto 模式 L2 单次重推导定位。require-cache/
    offline 恒响亮不自愈（提示 integrity --repair），auto 由 selfheal 编排。"""

    def __init__(self, path: Path, want_sha: str, ctx: str = ""):
        self.path = path
        self.payload_sha = want_sha
        self.ctx = ctx
        self.missing = [f"{ctx}: blob sha 不匹配 {path.name}"]
        super(SupplyMissingError, self).__init__(
            f"{ctx}: blob sha 不匹配 {path.name}（行账 {want_sha[:12]}…）"
            "——require-cache/offline 不自愈：先 integrity --repair；"
            "auto 模式单次重推导自愈")


@dataclass
class WarmItem:
    item_key: str
    role: str
    status: str
    domain: str
    codec: str
    _manifest_json: str | None
    blob_path: Path | None       # kit 多 blob 项=None（blob 面归 kit 解码自取）
    payload_sha256: str | None
    payload_size: int
    _manifest: dict | None = None
    _manifest_loader: object | None = None   # kit 项懒取（plan 查询零 manifest 搬运）

    @property
    def manifest(self) -> dict:
        """manifest 懒解析（plan 热路径不解析——kit manifest ~百 KB，逐卡解析
        曾占查询贴线半壁，实测判例；消费点（verify/装配）随取随解）。

        P3 件4 查询形状：kit 项 manifest 不进 plan 查询（每卡 ~20KB 纯搬运，
        实测占查询贴线 ~4 成——LRU 命中面零搬运零解析；miss 面走 loader 单查），
        非 kit 项仍随行携带（量小，省一次单查）。"""
        if self._manifest is None:
            if self._manifest_json is None:
                if self._manifest_loader is None:
                    raise RuntimeError(
                        f"manifest 缺失且无 loader（item {self.item_key[:12]}…）")
                self._manifest_json = self._manifest_loader()
            self._manifest = json.loads(self._manifest_json)
        return self._manifest


@dataclass
class WarmPlan:
    """一张卡的装配计划。

    ``status`` 语义（Phase 5 审计 P2 明确）：``complete`` = **期望集全部 built**
    ——``expected`` 为空集时 ``complete`` 恒成立（expectationless 卡=数据无美术
    的合法缺席形态，不是缺口；assemble_card 照常返回零 items + text 段且不
    raise）。``partial`` = 至少一项期望未 built（见 ``missing``）。
    """
    plan_key: str
    card_id: str
    status: str
    items: list[WarmItem] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)   # 期望 role 集（排序账）


class SupplyIndex:
    """一代缓存的只读句柄。构造即绑代（current.json；gen= 显式绑代=演练/测试面）；
    切代需重建句柄。"""

    def __init__(self, cache_root: Path | str, *, locale: str | None = None,
                 gen: str | None = None, health_policy: str = "stamp"):
        if health_policy not in _HEALTH_POLICIES:
            raise ValueError(
                f"health_policy 非法：{health_policy!r}（合法 {_HEALTH_POLICIES}）")
        self.health_policy = health_policy
        self.probe: dict = {}
        self.layout = SupplyLayout(cache_root)
        cur = self.layout.read_current()
        if gen is not None:
            # 演练/测试面（五态演练 warm 复验）：绑指定代，不读 current.json 绑定；
            # 产品路径恒 current。
            gid = gen[4:] if gen.startswith("gen-") else gen
            db = self.layout.gen_db(gid)
            if not db.is_file():
                raise FileNotFoundError(f"gen 代库缺失：{db}")
            self.game_id: str = gid
            self.generation: str = f"gen-{gid}"
            gen_locale = None          # 缺省从代库 meta 读
        else:
            if cur is None:
                raise FileNotFoundError(
                    f"supply 缓存无 current.json：{self.layout.root}——先跑 cold build")
            self.game_id = cur["game_id"]
            self.generation = cur["generation"]
            db = self.layout.gen_db(self.game_id)
            if not db.is_file():
                raise FileNotFoundError(f"current 指代的代库缺失：{db}")
            gen_locale = cur.get("locale")
        self.db_path = db
        meta_locale, self.health_error = self._probe_db()
        self.locale: str = locale or gen_locale or meta_locale or ""
        self._conn: sqlite3.Connection | None = None
        self._shared: OrderedDict[str, object] = OrderedDict()   # 共享域解码 LRU
        self._text_cache: dict | None = None
        self._kit_keys: dict[str, str] | None = None             # frame→item_key memo
        self._kit_light_keys: dict[str, str] | None = None       # frame→item_key memo（kit_light）
        self._color_probe_cache: dict | None = None              # color 全域段缓存
        self._color_atlas_keys: dict[tuple[str, int], str] | None = None
        self._mip_registry_cache: dict | None = None             # mip 全域段缓存
        self._supp_keys: dict[tuple[str, str, str], str] | None = None  # (domain,item,params_json)→item_key
        self._supp_cache: dict[str, dict] = {}                   # supplement parts 解码缓存（按 item_key）

    def _probe_db(self) -> tuple[str, str | None]:
        """open 自检（自愈车 L1；T2 warm-perf 起 stamp 懒检分档，见模块头）。

        probe 留账（self.probe，bench 报告消费）：policy / quick_check
        (ok|failed|skipped_stamp|skipped_policy) / quick_check_ms / stamp
        (hit|miss|bad_version|identity_mismatch|wal_frames|stale)。
        含 DB 打不开形态（连接/首查询 sqlite3.Error 同归损坏面）。health_error 非
        None=索引损坏：conn 触达即 SupplyIndexCorruptError 响亮；auto 模式重建编排
        在 selfheal 层消费本面（本模块零 UnityPy）。"""
        self.probe = {"policy": self.health_policy, "quick_check": None,
                      "quick_check_ms": None, "stamp": None}
        try:
            st = self.db_path.stat()
        except OSError as exc:
            return "", f"DB stat 失败：{type(exc).__name__}: {exc}"
        if self.health_policy == "stamp":
            stamp_status, stamp_locale = self._stamp_probe(st)
            self.probe["stamp"] = stamp_status
            if stamp_status == "hit":
                self.probe["quick_check"] = "skipped_stamp"
                return stamp_locale, None
        try:
            conn = S.connect(self.db_path, readonly=True)
        except sqlite3.Error as exc:
            return "", f"DB 打不开：{type(exc).__name__}: {exc}"
        try:
            locale = ""
            if self.health_policy != "skip":
                t_qc = time.perf_counter()
                try:
                    qc = conn.execute("PRAGMA quick_check(8)").fetchall()
                except sqlite3.Error as exc:
                    return "", f"quick_check 异常：{type(exc).__name__}: {exc}"
                self.probe["quick_check_ms"] = round(
                    (time.perf_counter() - t_qc) * 1000, 2)
                if not (len(qc) == 1 and qc[0][0] == "ok"):
                    self.probe["quick_check"] = "failed"
                    return locale, "quick_check: " + "; ".join(
                        r[0] for r in qc[:8])
                self.probe["quick_check"] = "ok"
            else:
                self.probe["quick_check"] = "skipped_policy"
            try:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key='locale'").fetchone()
                locale = row["value"] if row else ""
            except sqlite3.Error:
                pass    # locale 回退失败不掩盖损坏面（qc 已记）
            if self.probe["quick_check"] == "ok":
                # 全检通过 → best-effort 刷新 stamp（写失败=下次 open 重检，不响亮）
                self.layout.write_health_stamp(
                    self.game_id, db_path=self.db_path, locale=locale,
                    how="quick_check")
            return locale, None
        finally:
            conn.close()

    def _stamp_probe(self, st: object) -> tuple[str, str]:
        """健康 stamp 有效性裁决（T2）：返回 (状态, locale)。

        hit 条件=版本匹配+(db_size, db_mtime_ns) 身份匹配+**-wal 无未 checkpoint
        帧**（空/缺=正常态——发布面 journal_mode=DELETE 或 WAL 稳态 0 字节残留
        （integrity 写连接翻 WAL 的已知无害账，P3 记账）都不算异常；**非空=有
        未 checkpoint 帧**（写者崩溃/在写）→ 重检）+未超 HEALTH_STAMP_TTL_S 窗。
        任一不满足即重检（quick_check 后刷新）。"""
        doc = self.layout.read_health_stamp(self.game_id)
        if doc is None:
            return "miss", ""
        if doc.get("v") != 1:
            return "bad_version", ""
        if doc.get("db_size") != getattr(st, "st_size") or \
                doc.get("db_mtime_ns") != getattr(st, "st_mtime_ns"):
            return "identity_mismatch", ""
        wal = Path(str(self.db_path) + "-wal")
        try:
            if wal.exists() and wal.stat().st_size > 0:
                return "wal_frames", ""    # 未 checkpoint 帧=异常态，恒重检
        except OSError:
            pass
        age = int(time.time()) - int(doc.get("checked_at", 0) or 0)
        if age < 0 or age > HEALTH_STAMP_TTL_S:
            return "stale", ""
        return "hit", str(doc.get("locale", ""))

    def _kit_manifest_loader(self, item_key: str):
        """kit manifest 懒取（P3 件4：plan 查询零 manifest 搬运；LRU miss 面单查）。"""
        def load() -> str:
            row = self.conn.execute(
                "SELECT manifest_json FROM items WHERE item_key=?",
                (item_key,)).fetchone()
            if row is None:
                raise SupplyMissingError(
                    [f"kit item {item_key[:12]}…: manifest 行缺失"])
            return row["manifest_json"]
        return load

    # ---- 连接（只读 + mmap；懒开） ----

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            if self.health_error:
                raise SupplyIndexCorruptError(
                    f"supply 索引损坏需重建（generation={self.generation}，"
                    f"db={self.db_path}，{self.health_error}）——auto 模式自动重建"
                    "（selfheal.ensure_index），require-cache/offline 人工重建"
                    "（cold build 全量）")
            try:
                self._conn = S.connect(self.db_path, readonly=True)
                # 页 1 触达（schema_version 只读文件头）：垃圾化 DB（stamp 身份
                # 被伪造时可能的残险面）在句柄创建即响亮，不留到首查询。
                self._conn.execute("PRAGMA schema_version").fetchone()
            except sqlite3.Error as exc:
                raise SupplyIndexCorruptError(
                    f"supply 索引损坏需重建（DB 打不开：{type(exc).__name__}: "
                    f"{exc}；db={self.db_path}）——cold build 全量重建") from exc
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- 面（全卡装配的卡集轴） ----

    def card_ids(self) -> list[str]:
        """本代 cards 表全卡（全卡装配/审计轴）。"""
        return [r["card_id"] for r in
                self.conn.execute("SELECT card_id FROM cards ORDER BY card_id")]

    # ---- plan（热路径；每卡 3 次索引查询） ----

    def plan(self, card_id: str) -> WarmPlan | None:
        """plan + item + blob 解析（缺项记入 plan.missing，不抛——批量审计用）。

        expected-vs-built（Phase 5 返工 R1，P0-1）：期望集 = locators 表
        status='ok' 的 card 级 kind（portrait/portrait_golden/watermark）∪
        plan_items 哨兵行（expect::*——kit/kit_play/gems 期望落账）；期望 role
        无对应已建 item → plan.missing 逐项点名 kind。status 语义=「expected
        全部 built」：缺项时 complete 降级 partial（DB 行陈旧账不掩盖缺项面）。

        热路径查询（P2 车2 面：kit 项多 blob 行不进 plan 查询；P3 件4 kit 项
        manifest_json 出查询——CASE 短路为 NULL，miss 面走 _kit_manifest_loader
        单查，LRU 命中面零搬运）；R1 增第 4 查：locators 卡级期望（kind IN 前缀
        命中 UNIQUE(kind,subject,locale,premium) 索引，3 探针量级）。"""
        cur = self.conn.execute(
            "SELECT card_id,data_sha FROM cards WHERE card_id=?", (card_id,))
        row = cur.fetchone()
        if row is None:
            return None
        pk = S.plan_key(card_id=card_id, locale=self.locale,
                        card_data_sha=row["data_sha"] or "")
        prow = self.conn.execute(
            "SELECT status FROM plans WHERE plan_key=?", (pk,)).fetchone()
        plan = WarmPlan(plan_key=pk, card_id=card_id,
                        status=prow["status"] if prow else "missing")
        irows = self.conn.execute(
            "SELECT pi.item_key AS item_key, pi.role AS role, i.status AS status, "
            "i.domain AS domain, i.codec AS codec, "
            "CASE WHEN i.codec='kit' THEN NULL ELSE i.manifest_json END "
            "AS manifest_json "
            "FROM plan_items pi "
            "LEFT JOIN items i ON i.item_key=pi.item_key "
            "WHERE pi.plan_key=?", (pk,)).fetchall()
        items: list[WarmItem] = []
        single: list[WarmItem] = []
        built_roles: set[str] = set()
        sentinel_roles: list[str] = []
        for ir in irows:
            if ir["status"] is None:
                ik = ir["item_key"]
                if ik.startswith(S.EXPECTED_KEY_PREFIX):
                    # 「期望但未建」哨兵行（cold plan 挂接段落的账）——点名 role
                    sentinel_roles.append(ir["role"] or ik)
                    plan.expected.append(ir["role"] or ik)
                    continue
                plan.missing.append(f"{card_id}: item 缺失 {ik[:16]}…")
                continue
            is_kit = (ir["codec"] or "") == "kit"
            it = WarmItem(
                item_key=ir["item_key"], role=ir["role"], status=ir["status"],
                domain=ir["domain"] or "", codec=ir["codec"] or "",
                _manifest_json=None if is_kit else ir["manifest_json"],
                blob_path=None, payload_sha256=None, payload_size=0,
                _manifest_loader=self._kit_manifest_loader(ir["item_key"])
                if is_kit else None)
            items.append(it)
            built_roles.add(it.role)
            if not is_kit:
                single.append(it)
        if single:
            keys = [it.item_key for it in single]
            q = ",".join("?" * len(keys))
            brows = self.conn.execute(
                "SELECT ib.item_key AS item_key, b.payload_sha256 AS payload_sha256, "
                "b.size AS size, b.codec AS codec "
                "FROM item_blobs ib JOIN blobs b ON b.blob_key=ib.blob_key "
                f"WHERE ib.item_key IN ({q})", keys).fetchall()
            bmap: dict[str, sqlite3.Row] = {}
            for br in brows:
                bmap.setdefault(br["item_key"], br)
            for it in single:
                br = bmap.get(it.item_key)
                if br is None:
                    plan.missing.append(f"{card_id}: blob 行缺失 {it.item_key[:16]}…")
                    continue
                bp = self.layout.blob_path(
                    br["payload_sha256"],
                    ext=KC.BLOB_CODEC_EXT.get(br["codec"] or "png", ".png"))
                if not bp.is_file():
                    plan.missing.append(f"{card_id}: blob 文件缺失 {bp.name}")
                    continue
                it.blob_path = bp
                it.payload_sha256 = br["payload_sha256"]
                it.payload_size = br["size"]
        # ---- expected-vs-built（P0-1）：locator-ok card 级期望 ----
        ph = ",".join("?" * len(S.CARD_LOCATOR_KINDS))
        for lr in self.conn.execute(
                f"SELECT kind FROM locators WHERE subject=? AND status='ok' "
                f"AND kind IN ({ph})", (card_id, *S.CARD_LOCATOR_KINDS)):
            kind = lr["kind"]
            if kind not in plan.expected:
                plan.expected.append(kind)
        for role in sorted(set(sentinel_roles)):
            if role not in built_roles and role not in plan.missing:
                plan.missing.append(f"{card_id}: 缺预期产物: {role}")
        for kind in sorted(set(plan.expected) - built_roles):
            msg = f"{card_id}: 缺预期产物: {kind}"
            if msg not in plan.missing:
                plan.missing.append(msg)
        plan.expected.sort()
        plan.items = items
        if plan.missing and plan.status == "complete":
            plan.status = "partial"     # expected-vs-built 语义（陈旧 complete 不掩盖）
        return plan

    # ---- assemble（供给出口：内存对象；按 codec 分发） ----

    def assemble(self, plan: WarmPlan, *, allow_partial: bool = False) -> dict:
        """plan → {role: 产物}（png→PIL、kit→六面 dict、json→dict、ttf→bytes；
        npz=mip 链项不入通用束——专属访问器 portrait_mip() 装配）。

        任何缺项=SupplyMissingError（fail loud 清单）；allow_partial=True 显式
        豁免（装配已完整解析的子集——blob 行/文件缺失的项不进产物；产品路径不传，
        partial 代审计/演练专用）。blob 完整性校验在装配步（文件字节 sha==账面
        payload sha——派生物可删重建但不许坏）；共享域（frames/gems）解码产物走
        进程内 LRU（按引用返回，禁 mutate）。"""
        if plan.missing and not allow_partial:
            raise SupplyMissingError(list(plan.missing))
        out: dict = {}
        for it in plan.items:
            if not (it.codec == "kit" or it.blob_path is not None):
                continue          # allow_partial 面：未解析完整的项不进产物
            if it.codec == "kit":
                out[it.role] = self._decode_item_kit(
                    it.item_key, lambda it=it: it.manifest)
            elif it.codec == "png":
                out[it.role] = self._decode_png_item(it)
            elif it.codec == "json":
                data = self._read_verified_blob(it.blob_path, it.payload_sha256,
                                                plan.card_id)
                out[it.role] = json.loads(data.decode("utf-8"))
            elif it.codec == "ttf":
                data = self._read_verified_blob(it.blob_path, it.payload_sha256,
                                                plan.card_id)
                out[it.role] = data
            elif it.codec == "npz":
                # A5 mip 面（portrait_mip 项）：**不入通用束**——链数组由专属
                # 访问器 portrait_mip() 装配（28.9k 卡全走查时逐卡解 ~150KB NPZ
                # 是白付；期望账仍随 plan——role 在 plan_items + item/blob 行在
                # =built，expected-vs-built 门不受影响）
                continue
            else:
                raise SupplyMissingError(
                    [f"{plan.card_id}: 未知 blob codec {it.codec!r}（item "
                     f"{it.item_key[:16]}…）"])
        return out

    def _decode_png_item(self, it: WarmItem) -> Image.Image:
        """png 项解码（共享域走 LRU；per-card 项现解）。"""
        if it.domain in _SHARED_DOMAINS and it.item_key in self._shared:
            self._shared.move_to_end(it.item_key)
            return self._shared[it.item_key]
        if it.blob_path is None or it.payload_sha256 is None:
            raise SupplyMissingError([f"png item {it.item_key[:16]}…: blob 缺"])
        data = self._read_verified_blob(it.blob_path, it.payload_sha256,
                                        f"png item {it.item_key[:16]}…")
        img = Image.open(io.BytesIO(data))
        img.load()
        if it.domain in _SHARED_DOMAINS:
            self._shared[it.item_key] = img
            while len(self._shared) > _SHARED_CACHE_MAX:
                self._shared.popitem(last=False)
        return img

    def _read_verified_blob(self, path: Path, want_sha: str, ctx: str) -> bytes:
        data = path.read_bytes()
        if _sha_bytes(data) != want_sha:
            raise SupplyBlobCorruptError(path, want_sha, ctx)
        return data

    def assemble_portrait(self, card_id: str) -> Image.Image:
        """单卡 portrait 便捷口（role='portrait'；不拉 text 全域段）。"""
        plan = self.plan(card_id)
        if plan is None:
            raise SupplyMissingError([f"{card_id}: 卡不在 cards 表"])
        imgs = self.assemble(plan)
        if "portrait" not in imgs:
            raise SupplyMissingError([f"{card_id}: plan 无 portrait item"
                                      f"（status={plan.status}）"])
        return imgs["portrait"]

    def assemble_card(self, card_id: str, *, allow_partial: bool = False) -> dict:
        """全卡装配：plan 束（portrait/golden/kit/kit_play/gem:*/watermark）
        + text 全域段。

        expected-vs-built 门（P0-1）：plan 非 complete（缺预期产物——golden/kit/
        gems/watermark 与 portrait 同权）→ SupplyMissingError 点名缺的 role。
        allow_partial=True 显式豁免（装配已建子集 + text 段；**产品路径不传**——
        产品缺项必须 fail loud；partial 代审计/演练面专用）。"""
        plan = self.plan(card_id)
        if plan is None:
            raise SupplyMissingError([f"{card_id}: 卡不在 cards 表"])
        bundle = self.assemble(plan, allow_partial=allow_partial)
        bundle["text"] = self.text()
        return bundle

    # ---- kit 供给（六面重组；domain='frames' 域寻址） ----

    def kit_item_key(self, frame: str) -> str | None:
        """frame → kit item_key（缺=item 未建，返回 None——缺项面由 kit() 报）。

        帧族键面进程内 memo（6 行小面；items 表无 (domain,item,params) 索引，
        逐查=全表扫 ~6ms——热路径贴线判例）。"""
        if self._kit_keys is None:
            self._kit_keys = {
                json.loads(r["params_json"])["frame"]: r["item_key"]
                for r in self.conn.execute(
                    "SELECT item_key, params_json FROM items "
                    "WHERE domain=? AND item=?", (S.DOMAIN_FRAMES, S.ITEM_KIT))}
        return self._kit_keys.get(frame)

    def kit_frames(self) -> list[str]:
        """本代已建 kit 帧族清单（items.domain='frames'）。"""
        if self._kit_keys is None:
            self.kit_item_key("__warm_probe__")
        return sorted(self._kit_keys or {})

    def kit(self, frame: str) -> dict:
        """frame kit 六面供给：{meta, hierarchy, report, ubertext, arrays, textures}。

        重组=kit_codec.decode_kit（blob 文件字节 sha 逐块校验=L2 完整性面；内容
        sha 复推导不在 warm 逐次执行——T3 决策账见模块头与 _decode_item_kit；
        全量内容比对在 verify 面）。缺 item/blob=SupplyMissingError fail loud。
        进程内 LRU（卡不变项；按引用返回禁 mutate；命中面免 manifest 查询/解析
        ——热路径 ~0.1ms）。"""
        ik = self.kit_item_key(frame)
        if ik is None:
            raise SupplyMissingError([f"kit {frame}: item 缺失（先跑全量 cold build）"])
        return self._decode_item_kit(
            ik, lambda: json.loads(self.conn.execute(
                "SELECT manifest_json FROM items WHERE item_key=?",
                (ik,)).fetchone()["manifest_json"]))

    def _decode_item_kit(self, item_key: str, manifest_loader) -> dict:
        """kit item 六面解码（kit()/assemble 共用；LRU 共享池；manifest 懒取
        ——命中面零解析）。"""
        cached = self._shared.get(item_key)
        if cached is not None:
            self._shared.move_to_end(item_key)
            return cached
        manifest = manifest_loader()
        role_map = self._item_blob_roles(item_key)

        def blob_bytes(role: str) -> bytes:
            r = role_map.get(role)
            if r is None:
                raise SupplyMissingError(
                    [f"kit {manifest.get('frame')}: blob 行缺失 role={role}"])
            p = self.layout.blob_path(
                r["payload_sha256"],
                ext=KC.BLOB_CODEC_EXT.get(r["codec"] or "png", ".png"))
            if not p.is_file():
                raise SupplyMissingError(
                    [f"kit {manifest.get('frame')}: blob 文件缺失 {p.name}"])
            data = p.read_bytes()
            if _sha_bytes(data) != r["payload_sha256"]:
                raise SupplyBlobCorruptError(
                    p, r["payload_sha256"], f"kit {manifest.get('frame')}")
            return data

        try:
            # T3 warm-perf：verify_content=False——blob 文件字节 sha 已在 blob_bytes
            # 逐块校验（=L2 介质检测面，不弱化）；decode_kit 内的内容 sha 复推导
            # （JSON canonical/数组内容/纹理像素）是 build 时键面身份的重复推导，
            # warm 逐次执行白付（ally 实测 −31ms/kit）。文件字节相等 ⇒ 解码确定
            # ⇒ 内容恒等；解码器漂移检测归 verify 面（verify.py 走冷提对照+
            # compare_kit 全量比对，语义不丢）。
            # decode_threads=4：纹理面 PNG 解码并行（profile 实测大头=PNG 解码
            # 87.5ms/kit 串行——放 GIL，4 线程 68→22ms）。
            kit = KC.decode_kit(manifest, blob_bytes, verify_content=False,
                                decode_threads=_KIT_DECODE_THREADS)
        except KC.KitContentError as exc:
            raise SupplyMissingError(
                [f"kit {manifest.get('frame')}: {exc}"]) from exc
        self._shared[item_key] = kit
        while len(self._shared) > _SHARED_CACHE_MAX:
            self._shared.popitem(last=False)
        return kit

    def _item_blob_roles(self, item_key: str) -> dict[str, dict]:
        rows = self.conn.execute(
            "SELECT ib.role AS role, b.payload_sha256 AS payload_sha256, "
            "b.codec AS codec FROM item_blobs ib "
            "JOIN blobs b ON b.blob_key=ib.blob_key WHERE ib.item_key=?",
            (item_key,)).fetchall()
        return {r["role"]: {"payload_sha256": r["payload_sha256"],
                            "codec": r["codec"]} for r in rows}

    # ---- kit 扩展面 + kit_light（Phase 1 A6） ----

    def _kit_face_json(self, frame: str, face: str, *, item: str = S.ITEM_KIT
                       ) -> "object | None":
        """kit item 扩展 JSON 面（races/mesh_refs）读回：缺面=None（缺席是
        计划内形态——非 races 帧族无 races 面）；blob 文件字节 sha 逐次校验。"""
        ik = self.kit_item_key(frame) if item == S.ITEM_KIT \
            else self.kit_light_item_key(frame)
        if ik is None:
            raise SupplyMissingError(
                [f"kit {frame}: item 缺失（先跑全量 cold build）"])
        roles = self._item_blob_roles(ik)
        r = roles.get(face)
        if r is None:
            return None
        p = self.layout.blob_path(
            r["payload_sha256"], ext=KC.BLOB_CODEC_EXT.get(r["codec"], ".json"))
        data = self._read_verified_blob(p, r["payload_sha256"],
                                        f"kit {frame} face {face}")
        return json.loads(data.decode("utf-8"))

    def kit_races(self, frame: str) -> "dict | None":
        """kit races 面供给：live ``Kit.races`` 同形（{"source","provenance",
        "strings"}；非 races 帧族=live Kit.races None 同形返回 None）。缺 item
        fail loud；races 面缺席（旧代/非 races 帧）=None。"""
        return self._kit_face_json(frame, "races")

    def kit_mesh_refs(self, frame: str) -> "dict | None":
        """kit mesh_refs 面供给：live ``Kit.mesh_refs`` 同形（{网格名: (bundle,
        path_id)}——JSON 复原后 list 变 tuple 的种子重组面）；缺面=None。"""
        raw = self._kit_face_json(frame, "mesh_refs")
        if raw is None:
            return None
        return {k: (v[0], int(v[1])) for k, v in raw.items()}

    def kit_light_item_key(self, frame: str) -> str | None:
        """frame → kit_light item_key（缺=None——kit_light 帧族面进程 memo）。"""
        if self._kit_light_keys is None:
            self._kit_light_keys = {
                json.loads(r["params_json"])["frame"]: r["item_key"]
                for r in self.conn.execute(
                    "SELECT item_key, params_json FROM items "
                    "WHERE domain=? AND item=?",
                    (S.DOMAIN_FRAMES, S.ITEM_KIT_LIGHT))}
        return self._kit_light_keys.get(frame)

    def kit_light_frames(self) -> list[str]:
        """本代已建 kit_light 帧族清单（审计/种子枚举轴）。"""
        if self._kit_light_keys is None:
            self.kit_light_item_key("__warm_probe__")
        return sorted(self._kit_light_keys or {})

    def kit_light(self, frame: str) -> dict:
        """轻走查 kit 六面供给（live ``frames.kit_light(frame)`` 值面的 index 形
        ——六面同 kit codec；textures 空 dict=轻走查语义）。缺 item/blob=
        SupplyMissingError fail loud；进程内共享 LRU。"""
        ik = self.kit_light_item_key(frame)
        if ik is None:
            raise SupplyMissingError(
                [f"kit_light {frame}: item 缺失（先跑全量 cold build——A6 起"
                 "的代才带 kit_light 域）"])
        return self._decode_item_kit(
            ik, lambda: json.loads(self.conn.execute(
                "SELECT manifest_json FROM items WHERE item_key=?",
                (ik,)).fetchone()["manifest_json"]))

    # ---- supplement 供给（Phase 1 A6：特源/附件 kit + font_asset_params） ----

    def supplement_parts(self, domain: str, item: str, params: dict) -> dict:
        """supplement item parts 束供给（live 域函数值面的 index 存储形——
        {part: 内存产物}；live 对象形状重组归 seed 转换件，warm 面不 import
        supply 包）。进程内缓存一次/项（按引用返回禁 mutate——seed 种子值即
        本对象）；blob 文件字节 sha 逐次校验（L2 介质面）；缺 item/blob fail
        loud（SupplyMissingError）。"""
        params_json = S.cjson(params)
        key = (domain, item, params_json)
        if self._supp_keys is None:
            self._supp_keys = {}
            for r in self.conn.execute(
                    "SELECT item_key, domain, item, params_json FROM items "
                    "WHERE codec=?", (SC.SUPP_CODEC,)):
                self._supp_keys[(r["domain"], r["item"],
                                 r["params_json"])] = r["item_key"]
        ik = self._supp_keys.get(key)
        if ik is None:
            raise SupplyMissingError(
                [f"{domain}.{item}{params}: supplement item 缺失（先跑全量 "
                 "cold build——A6 起的代才带 supplement 域）"])
        cached = self._supp_cache.get(ik)
        if cached is not None:
            return cached
        row = self.conn.execute(
            "SELECT manifest_json FROM items WHERE item_key=?", (ik,)).fetchone()
        manifest = json.loads(row["manifest_json"])

        def blob_bytes(role: str) -> bytes:
            roles = self._item_blob_roles(ik)
            r = roles.get(role)
            if r is None:
                raise SupplyMissingError(
                    [f"{domain}.{item}: blob 行缺失 role={role}"])
            p = self.layout.blob_path(
                r["payload_sha256"],
                ext=KC.BLOB_CODEC_EXT.get(r["codec"] or "png", ".png"))
            return self._read_verified_blob(p, r["payload_sha256"],
                                            f"{domain}.{item} part {role}")

        parts = SC.decode_parts(manifest, blob_bytes, verify_content=False)
        self._supp_cache[ik] = parts
        return parts

    # ---- text 供给（全域项；进程缓存一次） ----

    def text(self) -> dict:
        """text 全域供给：{"fontdefs": dict, "fonts": {fontdef 名: TTF bytes}}。

        卡不变全域项（domain='text'；不进 plan_items——build_text_items 头注同账）。
        canonical JSON sha + TTF 文件 sha 逐件校验（内容身份面）；缺项 fail loud。
        进程内缓存一次（~26MB；按引用返回禁 mutate）。"""
        if self._text_cache is not None:
            return self._text_cache
        row = self.conn.execute(
            "SELECT item_key, manifest_json FROM items WHERE domain=? AND item=?",
            (S.DOMAIN_TEXT, S.ITEM_FONTDEFS)).fetchone()
        if row is None:
            raise SupplyMissingError(
                ["text: fontdefs item 缺失（先跑全量 cold build）"])
        manifest = json.loads(row["manifest_json"])
        data = self._read_role_blob(row["item_key"], TC.ROLE_FONTDEFS, "fontdefs")
        fontdefs = TC.decode_fontdefs(data, want_sha=manifest["payload_sha256"])
        fonts: dict[str, bytes] = {}
        for r in self.conn.execute(
                "SELECT item_key, params_json, manifest_json FROM items "
                "WHERE domain=? AND item=? ORDER BY params_json",
                (S.DOMAIN_TEXT, S.ITEM_FONT_TTF)):
            m = json.loads(r["manifest_json"])
            fname = json.loads(r["params_json"])["font"]
            raw = self._read_role_blob(r["item_key"], TC.ROLE_TTF, f"ttf {fname}")
            fonts[fname] = TC.decode_ttf(raw, want_sha=m["payload_sha256"])
        self._text_cache = {"fontdefs": fontdefs, "fonts": fonts}
        return self._text_cache

    def _read_role_blob(self, item_key: str, role: str, label: str) -> bytes:
        r = self._item_blob_roles(item_key).get(role)
        if r is None:
            raise SupplyMissingError([f"{label}: blob 行缺失 role={role}"])
        p = self.layout.blob_path(
            r["payload_sha256"],
            ext=KC.BLOB_CODEC_EXT.get(r["codec"] or "png", ".png"))
        if not p.is_file():
            raise SupplyMissingError([f"{label}: blob 文件缺失 {p.name}"])
        data = p.read_bytes()
        if _sha_bytes(data) != r["payload_sha256"]:
            raise SupplyBlobCorruptError(p, r["payload_sha256"], label)
        return data

    # ---- color 供给（Phase 1 A4：probe 全域段 + per-(family, ct) 图集） ----

    def color_probe(self) -> dict[str, list[str]]:
        """color 全域 probe 供给：{family: ["名.ext:GUID", …]}（12 族 switcher 表）。

        live 同形（supply.color.probe 返回值逐键逐槽相等——A4 判据 1 对账面）；
        卡不变全域项（domain='color' item='probe'，json blob 落盘保序），进程内
        缓存一次；payload sha 对 manifest 复核（媒体损坏面响亮）。缺项 fail loud
        （SupplyMissingError 家族——旧代无 color 域同此报错面）。"""
        if self._color_probe_cache is not None:
            return self._color_probe_cache
        row = self.conn.execute(
            "SELECT item_key, manifest_json FROM items WHERE domain=? AND item=?",
            (S.DOMAIN_COLOR, S.ITEM_COLOR_PROBE)).fetchone()
        if row is None:
            raise SupplyMissingError(
                ["color: probe item 缺失（先跑全量 cold build——A4 起的代才带 "
                 "color 域）"])
        manifest = json.loads(row["manifest_json"])
        data = self._read_role_blob(row["item_key"], "probe", "color probe")
        if _sha_bytes(data) != manifest.get("payload_sha256", ""):
            raise SupplyBlobCorruptError(
                self.layout.blob_path(manifest.get("payload_sha256", ""),
                                      ext=".json"),
                manifest.get("payload_sha256", ""), "color probe")
        probe = json.loads(data.decode("utf-8"))
        self._color_probe_cache = probe
        return probe

    def color_atlas(self, family: str, ct: int) -> Image.Image:
        """类色图集供给：live 同形 PIL Image（supply.color.atlas 返回值同图）。

        按 (family, ct) 寻址（params_json 槽位账，进程内 memo 一张全槽键表——
        items 表无 (domain,item,params) 索引，逐查=全表扫判例）；解码走共享域
        LRU（color 入 _SHARED_DOMAINS，按引用返回禁 mutate）；blob 文件字节 sha
        逐次校验（L2 介质面）。缺 item / 缺槽（材质族、空占位、解码失败——cold
        不落行）=SupplyMissingError fail loud。"""
        ct = int(ct)
        if self._color_atlas_keys is None:
            self._color_atlas_keys = {}
            for r in self.conn.execute(
                    "SELECT item_key, params_json FROM items "
                    "WHERE domain=? AND item=?",
                    (S.DOMAIN_COLOR, S.ITEM_COLOR_ATLAS)):
                p = json.loads(r["params_json"])
                self._color_atlas_keys[(p["family"], int(p["ct"]))] = r["item_key"]
        ik = self._color_atlas_keys.get((family, ct))
        if ik is None:
            raise SupplyMissingError(
                [f"color.atlas {family}[{ct}]: item 缺失（槽位=材质族/空占位/"
                 f"解码失败或缺 color 域——先跑全量 cold build）"])
        cached = self._shared.get(ik)
        if cached is not None:
            self._shared.move_to_end(ik)
            return cached
        data = self._read_role_blob(ik, "atlas", f"color.atlas {family}[{ct}]")
        img = Image.open(io.BytesIO(data))
        img.load()
        self._shared[ik] = img
        while len(self._shared) > _SHARED_CACHE_MAX:
            self._shared.popitem(last=False)
        return img

    def color_atlas_slots(self) -> list[tuple[str, int]]:
        """本代已建 atlas 槽位全集（审计/对账轴；(family, ct) 升序）。"""
        if self._color_atlas_keys is None:
            self._color_atlas_keys = {}
            for r in self.conn.execute(
                    "SELECT item_key, params_json FROM items "
                    "WHERE domain=? AND item=?",
                    (S.DOMAIN_COLOR, S.ITEM_COLOR_ATLAS)):
                p = json.loads(r["params_json"])
                self._color_atlas_keys[(p["family"], int(p["ct"]))] = r["item_key"]
        return sorted(self._color_atlas_keys or {})

    # ---- mip 供给（Phase 1 A5：registry 全局项 + per-card 肖像真链） ----

    def mip_registry(self) -> dict[str, dict]:
        """mip 链注册表供给：live 同形 ``name → {"lods","filter","bias"}``
        （textures 域全局项——content-fingerprint 派发面 + chain_for_name 注册
        表分支的单一数据源；23 条静态链全级 uint8 数组）。

        NPZ 单 blob（chain/<name>/<i> 数组键），payload sha 对 manifest 复核
        （媒体损坏面响亮）；进程内缓存一次（~35MB 原始数组；按引用返回禁
        mutate）。缺项 fail loud（SupplyMissingError——A5 之前的旧代同此报错
        面）。**warm 读取零开包**（audit import/open blocker 同窗机器证明）。"""
        if self._mip_registry_cache is not None:
            return self._mip_registry_cache
        row = self.conn.execute(
            "SELECT item_key, manifest_json FROM items WHERE domain=? AND item=?",
            (S.DOMAIN_TEXTURES, S.ITEM_MIP_REGISTRY)).fetchone()
        if row is None:
            raise SupplyMissingError(
                ["textures: mip_registry item 缺失（先跑全量 cold build——A5 "
                 "起的代才带 mip 域）"])
        manifest = json.loads(row["manifest_json"])
        data = self._read_role_blob(row["item_key"], "registry", "mip registry")
        if _sha_bytes(data) != manifest.get("payload_sha256", ""):
            raise SupplyBlobCorruptError(
                self.layout.blob_path(manifest.get("payload_sha256", ""),
                                      ext=".npz"),
                manifest.get("payload_sha256", ""), "mip registry")
        arrays = MC.decode_chain_npz(data)
        out: dict[str, dict] = {}
        for name, m in manifest["chains"].items():
            lods = [arrays[MC.registry_chain_key(name, i)]
                    for i in range(int(m["mip_count"]))]
            out[name] = {"lods": lods, "filter": int(m["filter"]),
                         "bias": float(m["bias"])}
        self._mip_registry_cache = out
        return out

    def portrait_mip(self, card_id: str) -> dict:
        """肖像真 mip 链供给：live ``art.portrait_mip(card_id)`` 同形
        ``{"name","chain","filter","bias"}``（chain=WarmChain——len/getitem/
        peek/shape0 协议与 live LazyFloatChain 一致）。

        装配三源（cold manifest "source" 字段裁决）：
        - ``registry``：链名在注册表且地址相等（live chain_for_name 注册表分支
          同判据）——lods 从 ``mip_registry()`` 派生（同源单链，零自有 blob）；
        - ``portrait``（mips<=1）：单级链，L0=portrait PNG（cold 已验证位等）；
        - ``chain``（mips>1）：blob NPZ 第 1..n-1 级 + L0 派生（``l0=explicit``
          时 0..n-1 全级在位——cold 期 UnityPy/链双解码失配的显式兜底）。
        缺项 fail loud；npz/肖像 blob 文件字节 sha 逐次校验（L2 介质面）。"""
        plan = self.plan(card_id)
        if plan is None:
            raise SupplyMissingError([f"{card_id}: 卡不在 cards 表"])
        item = next((i for i in plan.items if i.role == "portrait_mip"), None)
        if item is None:
            raise SupplyMissingError(
                [f"{card_id}: plan 无 portrait_mip item（status={plan.status}"
                 "——portrait 卡=期望项，先跑全量 cold build）"])
        m = item.manifest
        n = int(m["mip_count"])
        if m["source"] == "registry":
            # 注册表源：零自有链数据（blob=meta 标记不读——warm registry 项
            # 供货，live chain_for_name 注册表分支同源单链）
            reg = self.mip_registry()
            ent = reg.get(m["name"])
            if ent is None:
                raise SupplyMissingError(
                    [f"portrait_mip {card_id}: 注册表无链 {m['name']!r}"])
            lods = list(ent["lods"])
        else:
            data = self._read_role_blob(item.item_key, "chain",
                                        f"portrait_mip {card_id}")
            arrays = MC.decode_chain_npz(data)
            if m.get("l0") == "explicit":
                # cold 期双解码失配的显式兜底：0..n-1 全级在位
                lods = [arrays[MC.level_key(i)] for i in range(n)]
            else:
                # L0 = 肖像 PNG 像素（cold 期逐纹理验证 UnityPy==链解码位等）
                l0 = self._portrait_l0(card_id, plan)
                lods = [l0] + [arrays[MC.level_key(i)] for i in range(1, n)]
        return {"name": m["name"], "chain": WarmChain(lods),
                "filter": int(m["filter"]), "bias": float(m["bias"])}

    def _portrait_l0(self, card_id: str, plan) -> "np.ndarray":
        """链 L0 = 肖像 PNG 像素（live「mip0 双解码器逐位一致」的 warm 落地面；
        cold 期逐纹理验证 UnityPy 解码 == 链解码 L0，失配落 explicit 全级）。"""
        item = next((i for i in plan.items if i.role == "portrait"), None)
        if item is None:
            raise SupplyMissingError(
                [f"{card_id}: plan 无 portrait item（L0 派生源缺失）"])
        img = self._decode_png_item(item)
        return np.asarray(img.convert("RGBA"), dtype=np.uint8)

    # ---- 批量审计 ----

    def check(self, card_ids: list[str]) -> dict:
        """批量缺项审计（不装配图像）：命中/缺项账，供 --mode require-cache/offline。

        expected-vs-built（Phase 5 返工 R1，P0-1）：缺项账来自 plan.missing——
        golden/kit/gems/watermark 与 portrait 同权点名（locator-ok 期望无产物、
        哨兵行期望未建）。portrait 缺席两态保持：locator-ok 在而 item 缺=期望
        缺口（plan.missing 已点名）；locator 全无=数据缺席（合法，记
        absent_portrait 账不算缺）；locator 行在而 status≠ok（ref 不可解）且无
        产物=locator 缺口（缺项报——不可补，账面 counts_locators_missing 同源）。"""
        hit, miss_card, miss_item = 0, [], []
        loc_any = {r["subject"]: r["status"] for r in self.conn.execute(
            "SELECT subject, status FROM locators WHERE kind='portrait'")}
        absent_portrait = 0
        for cid in card_ids:
            plan = self.plan(cid)
            if plan is None:
                miss_card.append(f"{cid}: 卡不在 cards 表")
                continue
            if plan.missing:
                miss_item.extend(plan.missing)
                continue
            if not any(i.role == "portrait" for i in plan.items):
                st = loc_any.get(cid)
                if st is not None and st != "ok":
                    miss_item.append(
                        f"{cid}: portrait locator 无产物（status={st}——ref 不可解，"
                        "cold 账面 locator_missing 同源）")
                    continue
                if st == "ok":
                    # 防御面：locator-ok 必已入 plan.missing（expected 集合），走不到
                    miss_item.append(f"{cid}: 缺预期产物: portrait")
                    continue
                absent_portrait += 1     # 数据缺席（合法）
            hit += 1
        return {"total": len(card_ids), "hit": hit,
                "absent_portrait": absent_portrait,
                "missing_cards": miss_card, "missing_items": miss_item,
                "miss": len(miss_card) + len(miss_item)}

    def fillable_missing(self, card_ids: list[str]) -> dict:
        """缺项卡分拣（auto 冷补面）：portrait locator-ok 而无 item=可定向冷补；
        locator 缺失/missing=不可补（响应亮清单）。"""
        rep = self.check(card_ids)
        bad_cards = {m.split(":")[0] for m in rep["missing_cards"]}
        bad_cards |= {m.split(":")[0] for m in rep["missing_items"]}
        loc_ok: dict[str, int] = {}
        for r in self.conn.execute(
                "SELECT subject, COUNT(*) AS n FROM locators "
                "WHERE kind IN ('portrait','portrait_golden') AND status='ok' "
                "GROUP BY subject"):
            loc_ok[r["subject"]] = r["n"]
        fillable = sorted(c for c in bad_cards if c in loc_ok)
        unfillable = sorted(c for c in bad_cards if c not in loc_ok)
        return {**rep, "fillable": fillable, "unfillable": unfillable}


# ---------------------------------------------------------------------------
# 缺席归因四分类（Phase 5 返工 R2；audit full 门 / verify gate 判定 / bench
# 分母共用同一判据——与 expected-vs-built 单源账面对齐）
# ---------------------------------------------------------------------------

_ACCOUNT_CATS = ("ok", "missing_gap", "absent_expectationless",
                 "absent_locator_missing")


def account_for_cards(conn: sqlite3.Connection,
                      card_ids) -> dict:
    """给定卡集的缺席归因四分类（纯函数；conn 只读，零 I/O 副作用）。

    判据与 warm.plan()/schema.expected_vs_built 同一账面（期望=locators
    status='ok' 的 card 级 kind（CARD_LOCATOR_KINDS）∪ plan_items 哨兵行
    expect::*；built=plan_items 中 items 行存在**且至少一条 item_blobs 行**存在
    的 role——只查 items 会漏「item 行在而 blob 链断」的不可装配坏账）：

    - ``ok``：期望全 built（有真 item ≥1 且无未满足期望）——正常供给卡；
    - ``missing_gap``：**有期望**（ok locator 或哨兵）而未满足（plan.missing
      非空同源，含 plan_items 引用 items 行缺失的坏账）——**真缺口，full 代
      红判据只看它**；
    - ``absent_locator_missing``：零期望（无 ok locator、无哨兵、无 item）且
      locator 行存在而 status≠ok（ref 不可解——数据引用了做不出的美术）；
    - ``absent_expectationless``：零期望且无任何 card 级 locator 行（dbf 无
      卡面纹理行：locale/variant 后缀、Story_*/BOSS/pet 等走 carddef prefab
      的卡）——数据无美术的合法缺席；
    - ``anomaly``：其他异常单列（card_id 不在 cards 表等）——unaccountable。

    **缺席可归因（absent 两类）≠ 失败**（与 cold 尾部发布门 expected-vs-built
    同口径：不可归因缺口才红）。返回 dict：四类全量名单 + anomaly 分因名单 +
    counts + samples（各类截断样例，样例上限 20）。批量实现（一趟装载
    plans/plan_items/locators 映射再分类），全代 36k 卡秒级。"""
    ids = list(card_ids)
    card_rows = {r["card_id"] for r in
                 conn.execute("SELECT card_id FROM cards")}
    plan_of: dict[str, str] = {r["card_id"]: r["plan_key"] for r in
                               conn.execute(
                                   "SELECT card_id, plan_key FROM plans")}
    sent: dict[str, set[str]] = {}       # 哨兵行（期望未建落账）
    broken: dict[str, set[str]] = {}     # 非哨兵 plan_items 行而 items 行缺失
    built: dict[str, set[str]] = {}
    for r in conn.execute(
            "SELECT pi.plan_key AS pk, pi.item_key AS ik, pi.role AS role, "
            "i.item_key AS iik, "
            "EXISTS (SELECT 1 FROM item_blobs ib WHERE ib.item_key=pi.item_key) "
            "AS has_blob FROM plan_items pi "
            "LEFT JOIN items i ON i.item_key=pi.item_key"):
        role = r["role"] or ""
        if not role:
            continue
        if (r["ik"] or "").startswith(S.EXPECTED_KEY_PREFIX):
            sent.setdefault(r["pk"], set()).add(role)
        elif r["iik"] is None:
            broken.setdefault(r["pk"], set()).add(role)
        elif not r["has_blob"]:
            # items 行在而 item_blobs 链断（P2 审计：不可装配=缺口，与无 items
            # 行同判；只查 items 行会让坏账静默通过完整性门）
            broken.setdefault(r["pk"], set()).add(role)
        else:
            built.setdefault(r["pk"], set()).add(role)
    loc_ok: dict[str, set[str]] = {}
    loc_any: dict[str, set[str]] = {}
    ph = ",".join("?" * len(S.CARD_LOCATOR_KINDS))
    for r in conn.execute(
            f"SELECT subject, kind, status FROM locators "
            f"WHERE kind IN ({ph})", S.CARD_LOCATOR_KINDS):
        loc_any.setdefault(r["subject"], set()).add(r["kind"])
        if r["status"] == "ok":
            loc_ok.setdefault(r["subject"], set()).add(r["kind"])
    out: dict = {cat: [] for cat in _ACCOUNT_CATS}
    anomaly: dict[str, list[str]] = {}
    for cid in ids:
        if cid not in card_rows:
            anomaly.setdefault("not_in_cards", []).append(cid)
            continue
        pk = plan_of.get(cid)
        expected = set(loc_ok.get(cid) or ())
        if pk is not None:
            expected |= sent.get(pk, set())
        blt = built.get(pk, set()) if pk is not None else set()
        brk = broken.get(pk, set()) if pk is not None else set()
        if (expected - blt) or brk:
            out["missing_gap"].append(cid)
        elif blt:
            out["ok"].append(cid)
        elif loc_any.get(cid):
            out["absent_locator_missing"].append(cid)
        else:
            out["absent_expectationless"].append(cid)
    for cat in _ACCOUNT_CATS:
        out[cat].sort()
    for reason in anomaly:
        anomaly[reason].sort()
    out["anomaly"] = anomaly
    out["counts"] = {
        **{cat: len(out[cat]) for cat in _ACCOUNT_CATS},
        "anomaly_total": sum(len(v) for v in anomaly.values())}
    out["samples"] = {
        cat: out[cat][:20] for cat in _ACCOUNT_CATS}
    out["samples"]["anomaly"] = [c for v in anomaly.values() for c in v][:20]
    return out


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
