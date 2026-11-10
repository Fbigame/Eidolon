"""seed — index → S1 memo 种子器（A3+A4+A5+A6；supply-source.md §2/§3.5/§3.7，
任务单 §4-§7）。

把 ``SupplyIndex.assemble_card(card_id)`` 的产物按 Phase 0 role→token 映射转换成
``machine.session`` memo 种子（S1 seam：预填既有 memo 缓存，不引入新协议）。
消费位=``api._render_one`` 的 ``seed_provider``（A2 落地，零参可调用）——组合层/
集成驱动按卡构造 ``provider_for_card(card_id)`` 注入；产品 0.1.0 路径不启用。

依赖方向（任务单 A3）：本模块顶层只 import ``warm`` 面（warm/schema/paths +
PIL 类型判别）——``cold`` / ``kit_extract`` / ``text_extract`` / ``wm_extract`` /
``supplement_extract``（UnityPy 面）与 ``render`` / ``supply`` / ``recipes``
一律不碰。**最小偏离（照 spike 解法）**：转换件需要 live 形状（``Kit`` /
``AbilityKit`` / ``_ArrayDict`` 等 live 类），这些 import 全部在函数体内
（``tests/phase0/phase0_spike_render.py`` 同款）——种子器只在 render 进程内
运行（UnityPy/live supply 已在内存），模块级 import 面保持 warm 纯净
（``test_supply_index_seed`` 有子进程机器证明）。

弃种语义（supply-source.md §3.6；性能语义下弃种=回退原因，不是用户可见失败，
**不产生新 Problem code、不构造 Problem**）：

- **整批弃种**：index 无 current.json / 代库缺 / DB 打不开 / locale 或 generation
  身份与 ctx 不同源 → ``CardSeeder.open`` 返回 None + WARNING（调用方拿到 None
  即纯 live；open 每批一次，WARN 一次）。
- **该卡弃种**：``assemble_card`` 严格门失败（``SupplyMissingError`` /
  ``SupplyBlobCorruptError`` / ``SupplyIndexCorruptError``）或任何转换异常 →
  ``seeds_for_*`` 返回 None + WARNING。
- **该 token 不种**：单 role 缺席/形状不符（如 watermark 无 ref 裁决值、kit 缺口
  面供给失败）→ 记账 skipped、其余 token 照种；未种 token 照旧 live（fallback
  天然）。

记账面：``SeedLedger``（seeded/skipped 清单 + INFO 日志，``-v`` 可见）；
``hit`` / ``live`` / ``unused`` 三计数是 render 期观察（哪个种子 token 被会话
请求），归消费侧驱动（e2e/A7 用 memo 观测件），种子器不越位进会话。

形状来源：role→token 映射与六面重组/font_table 派生逐字搬迁
``tests/phase0/phase0_spike_render.py``（Phase 0 Step 4 实证件，禁止重写）。
A6 起缺口面（races/mesh_refs）**换 index 面**（A3 的 live 派生件退役）：
``kit_races(frame)`` / ``kit_mesh_refs(frame)`` warm 访问器供货（races 帧族
缺面=kit token 不种——种缺 races 的 ally Kit 会在 GetRaceText 炸，比 live 兜底
更糟）；``kit_gap_faces`` 注入形保留（替身测试面），缺省=index 面。
A4 color 面（任务单 A4）：``color.probe`` ← bundle["color"]（12 族槽位表逐键
同形）；``color.atlas(family, ct)`` ← warm 逐槽解码——枚举=帧族全有效槽
（live 消费方遍历：kit 提取全槽扇出 + 类色写点单槽同族；frame 无族或无 kit
role → 不枚举），单槽缺席=该 token 不种回 live。

A5 mip 面（任务单 A5）：``textures.mip_registry`` ← warm ``mip_registry()``
（live 同形 raw dict 直透——lods=uint8 数组，消费方 raster._registry /
chain_for_name 自行包 LazyFloatChain）；``art.portrait_mip(card_id)`` ← warm
``portrait_mip(card_id)`` → ``LazyFloatChain(chain.lods)``（live 形状类函数体
import——种子值进 memo 后 render 链按 live 语义消费）。**非 @item 面接线**：
``textures.entry_for_ref`` 是普通函数（非 memo token），其 ref 解析步 live 会
开包——``AtlasEntrySeed`` 句柄经 ``supply.textures.set_entry_seed_lookup``
模块级注入位先行（类色图集 ref 的 mip 判定/链数据由 index 账面供给：
mips=1=已裁决 None、mips>1=registry 名（地址相等）走 memo-seeded
``chain_for_name``（live 注册表分支同构）或 index 全级链 NPZ；未覆盖 ref
（override/composite 等）=UNSET 落既有 live 路）。句柄生命周期=CardSeeder
open 装 / close 卸（close 仅卸自己在位者）；未安装=纯 live 逐位不变。
``chain_for_name(name, addr)`` 显式地址分支无需注入——其唯一调用方就是
``art.portrait_mip`` token 体本身（seeded 命中=函数体零执行）。

A6 补域（任务单 A6）：特源/附件 kit + races/mesh_refs + font_asset_params——
- **frames.kit(frame)**（全帧族×seed）：plan 帧族 kit 六面自 assemble 束，其余
  帧族经 warm ``kit(frame)`` 读回（卡不变域项——live 渲染链对 kit token 的
  请求含非本卡帧族，如 normal 卡请求 ``kit("ally_premium")``）；``bacon`` 帧
  的 live token=``frames.bacon_kit()``（特源域项），index 同 kit 六面件存储、
  seed 按 bacon_kit token 种。
- **frames.kit_light(frame)**×9：warm ``kit_light(frame)`` → live Kit 形
  （textures 空 dict=轻走查语义；races 恒 None=live kit_light 同形）。
- **frames.ability_kit(quality)**：warm supplement parts → ``AbilityKit`` 重组
  （obj_texts/fonts_bytes 不进种子形状——渲染链零消费的提取产物面）。
- **frames.badges_kit / btf_kit / ornaments_kit**：parts → ``BadgesKit`` /
  ``BtfKit`` / ``OrnamentsKit`` 重组。
- **frames.ta_supplement / material_state / portrait_uv1**：parts → dict /
  ndarray dict / 按名重组 dict（live 同形）。
- **text.font_asset_params**：parts["data"] 直种（json dict 同形）。
- 缺项/形状不符=该 token 不种回 live（fallback 天然）。

线程/进程：实例单线程使用；``--jobs`` 下每 worker 各开各的 ``CardSeeder``
（SQLite 只读句柄并发安全）。render 批内不跑 maintain（§3.4 操作约定）。
"""
from __future__ import annotations

import functools
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from eidolon.core.supply_index import schema as S
from eidolon.core.supply_index.warm import (
    SupplyBlobCorruptError,
    SupplyIndex,
    SupplyIndexCorruptError,
    SupplyMissingError,
)

__all__ = ["CardSeeder", "SeedLedger"]

logger = logging.getLogger(__name__)

# kit 缺口面（races/mesh_refs）的注入形状：(frame) → (races|None, mesh_refs)。
# 缺省=live 派生（_default_gap_faces，spike 形态）；派生失败 → kit token 不种。
GapFacesFn = Callable[[str], "tuple[dict | None, dict]"]


# ---------------------------------------------------------------------------
# role→token 转换件（spike 逐字搬迁；函数体内 live import=形状依赖的 spike 解法）
# ---------------------------------------------------------------------------

def _font_table_entries(fontdefs: dict) -> list[dict]:
    """font_table token 的无损派生（fontdefs 本由 font_table 逐 entry 构造）。
    [phase0_spike_render._font_table_entries 逐字]"""
    return [{"m_FontDefName": name, "m_FontName": rec["m_FontName"],
             "m_FontGuid": rec["base_guid"]}
            for name, rec in fontdefs.items()]


def _kit_from_index(frame: str, six: dict, races: "dict | None",
                    mesh_refs: dict):
    """index 六面 → live Kit 形状（scenes.scene_for / render 消费面同形）。

    frame_dir=live spec frame_dir（FRAME_SPECS 词面——A6 对账修正：ally=
    "ally_frame" 等；FRAME_SPECS 外的帧（bacon 特源）回退 frame 名——渲染链
    零消费字段，对账面显式记账）。meta={meta面, hierarchy:面, trinket_level_
    mats:setdefault None}——live meta 含 hierarchy 键与 trinket_level_mats
    （trinket 帧=外部材质账，A6 harness 捕获随存储面来；非 trinket 帧缺键
    setdefault None=live 非 trinket 同 None）；races/mesh_refs 由缺口面
    （A6=index 面；替身测试=注入形）赋值。
    [phase0_spike_render._kit_from_index 逐字 + A6 races/mesh_refs 参数化]"""
    from eidolon.core.supply.frames.kits import Kit, _ArrayDict
    from eidolon.core.supply.frames.specs import FRAME_SPECS

    meta = {**six["meta"], "hierarchy": six["hierarchy"]}
    meta.setdefault("trinket_level_mats", None)
    spec = FRAME_SPECS.get(frame) or {}
    return Kit(frame_dir=spec.get("frame_dir", frame), meta=meta,
               arrays=_ArrayDict(six["arrays"]), textures=six["textures"],
               report=six["report"], ubertext=six["ubertext"],
               races=races, mesh_refs=mesh_refs)


def _frame_family(frame: str) -> "str | None":
    """kit frame → 类色图集族（FRAME_SPECS[frame].family；live 形状 import
    函数体内——specs 是纯数据模块但属 supply 包，纪律同缺口面补件）。"""
    from eidolon.core.supply.frames.specs import FRAME_SPECS

    spec = FRAME_SPECS.get(frame)
    return spec.get("family") if spec else None


def _token_str(token: tuple) -> str:
    """token → 日志串形 ``domain.item(arg, ...)``（ledger/日志面）。"""
    domain, item, args = token
    return f"{domain}.{item}({', '.join(repr(a) for a in args)})"


# ---------------------------------------------------------------------------
# entry_for_ref 的 seeded 查找面（A5；supply.textures 模块级注入位的句柄实现）
# ---------------------------------------------------------------------------

class AtlasEntrySeed:
    """类色图集 ref → mip 链判定/条目（``entry_for_ref`` 的索引先行面）。

    数据源=supply_index 账面：color atlas item manifest 的 ``mip`` 段（cold
    期逐槽记 m_MipCount/name/filter/bias——mips=1=「无链」裁决值）+ 带链槽的
    全级 NPZ blob。判定契约（supply.textures.ENTRY_SEED_UNSET 语义）：
    - ref 不在索引账 / 句柄内部故障 → UNSET（live 解析路——override/composite/
      未知 ref，或账面读不动时落既有解析）；
    - mips<=1 → None（已裁决无链——live m_MipCount<=1 同判，降级 mip0 直采，
      不红）；
    - mips>1：注册表名且地址相等 → live ``chain_for_name(name)``（memo-seeded
      registry——live 注册表分支同构，零开包）；否则 index 全级链 →
      ``LazyFloatChain``（值面=cold 同解码器提取产物，与 live 解析逐位一致）。

    缓存：ref → 判定（进程级——live _REF_ENTRY 同形态；entry_for_ref 亦会把
    判定写进自己的 memo，双账一致性无害）。"""

    def __init__(self, index) -> None:
        self.index = index
        self._ref_slots: dict[str, str] | None = None   # ref → atlas item_key
        self._verdicts: dict[str, object] = {}
        self._warned: set[str] = set()

    def _slots(self) -> dict[str, str]:
        if self._ref_slots is None:
            slots: dict[str, str] = {}
            for r in self.index.conn.execute(
                    "SELECT item_key, manifest_json FROM items "
                    "WHERE domain=? AND item=?",
                    (S.DOMAIN_COLOR, S.ITEM_COLOR_ATLAS)):
                m = json.loads(r["manifest_json"])
                ref = m.get("ref")
                if ref and isinstance(m.get("mip"), dict):
                    slots[ref] = r["item_key"]
            self._ref_slots = slots
        return self._ref_slots

    def __call__(self, ref: str):
        from eidolon.core.supply.textures import ENTRY_SEED_UNSET

        try:
            ik = self._slots().get(ref)
        except Exception as exc:      # noqa: BLE001 —— 句柄故障 → live 兜底
            if "_slots" not in self._warned:
                self._warned.add("_slots")
                logger.warning("[seed] entry seed 槽位账构建失败，落 live：%s", exc)
            return ENTRY_SEED_UNSET
        if ik is None:
            return ENTRY_SEED_UNSET
        if ref in self._verdicts:
            return self._verdicts[ref]
        verdict = self._verdict_for(ik)
        self._verdicts[ref] = verdict
        return verdict

    def _verdict_for(self, item_key: str):
        from eidolon.core.supply_index import mip_codec as MC

        from eidolon.core.supply.textures import (
            ENTRY_SEED_UNSET,
            LazyFloatChain,
            _MIP_CHAIN_ADDR,
            chain_for_name,
        )

        try:
            row = self.index.conn.execute(
                "SELECT manifest_json FROM items WHERE item_key=?",
                (item_key,)).fetchone()
            if row is None:
                return None            # 防御面：账面缺行=降级（live 异常同象）
            m = json.loads(row["manifest_json"])
            mip = m.get("mip") or {}
            if mip.get("error") or not mip.get("count") or mip["count"] <= 1:
                return None            # 已裁决无链（或链账失败——降级不红）
            name = mip["name"]
            addr = (m.get("bundle"), int(m.get("path_id") or 0))
            reg_addr = _MIP_CHAIN_ADDR.get(name)
            if name in _MIP_CHAIN_ADDR and addr == reg_addr:
                # 注册表分支（live chain_for_name 同判据）：memo-seeded registry
                # 供货——本调用零开包（mip_registry token 已在 memo）
                return chain_for_name(name)
            r = self.index._item_blob_roles(item_key).get("mip_chain")
            if r is None:
                return None
            p = self.index.layout.blob_path(r["payload_sha256"], ext=".npz")
            data = p.read_bytes()
            if S.sha256_hex(data) != r["payload_sha256"]:
                raise ValueError("mip chain blob sha 失配")
            arrays = MC.decode_chain_npz(data)
            n = int(mip["count"])
            lods = [arrays[MC.level_key(i)] for i in range(n)]
            return {"name": name, "chain": LazyFloatChain(lods),
                    "filter": int(mip["filter"]), "bias": float(mip["bias"])}
        except Exception as exc:       # noqa: BLE001 ——句柄故障 → live 兜底
            if item_key not in self._warned:
                self._warned.add(item_key)
                logger.warning("[seed] entry seed %s 判定失败，落 live：%s",
                               item_key[:12], exc)
            return ENTRY_SEED_UNSET


# ---------------------------------------------------------------------------
# 记账面
# ---------------------------------------------------------------------------

@dataclass
class SeedLedger:
    """一张卡的种子记账（构造侧；``-v`` 可见）。

    ``seeded`` / ``skipped`` 为 token 串形（``_token_str``）；skipped 附原因。
    ``hit`` / ``live`` / ``unused`` 三计数是 render 期观察量，由消费侧驱动
    （memo 观测件）填——种子器不越位进会话。"""

    card_id: str
    seeded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    skipped_reasons: list[str] = field(default_factory=list)
    hit: int | None = None
    live: int | None = None
    unused: int | None = None

    def summary(self) -> str:
        head = (f"card={self.card_id} seeded={len(self.seeded)} "
                f"skipped={len(self.skipped)}")
        if self.hit is not None:
            head += f" hit={self.hit} live={self.live} unused={self.unused}"
        return head


# ---------------------------------------------------------------------------
# 种子器
# ---------------------------------------------------------------------------

class CardSeeder:
    """一代 supply index 的种子器（A3 库 API，无 CLI）。

    生命周期：每批/每 worker ``open`` 一次（句柄进程复用，SQLite 只读并发
    安全）→ 按卡 ``seeds_for_card`` / ``seeds_for_dbf``（或直接把
    ``provider_for_card(card_id)`` 塞给 ``api._render_one(seed_provider=)``）
    → 批末 ``close``。open 任何失败返回 None（整批弃种回 live，WARN 一次）；
    seeds_for 任何失败返回 None（该卡弃种回 live，WARN）——两层都不 raise，
    调用方零感知（性能语义 fallback 天然）。"""

    def __init__(self, index: SupplyIndex, *, ctx_locale: str,
                 ctx_identity: dict | None = None,
                 kit_gap_faces: GapFacesFn | None = None) -> None:
        self.index = index
        self.ctx_locale = ctx_locale
        self.ctx_identity = ctx_identity
        # 缺口面（races/mesh_refs）供给：A6 起缺省=index 面（_index_gap_faces）；
        # 注入形保留（替身测试面/特殊形态）。
        self.kit_gap_faces: GapFacesFn = kit_gap_faces or self._index_gap_faces
        self.last_ledger: SeedLedger | None = None
        self._gap_cache: dict[str, "tuple[dict | None, dict]"] = {}

    # ---- open（整批弃种判据；WARN 一次） ----

    @classmethod
    def open(cls, cache_root: Path | str, *, ctx_locale: str,
             ctx_identity: dict | None = None,
             kit_gap_faces: GapFacesFn | None = None) -> "CardSeeder | None":
        """打开 index 并校验 locale / generation 身份同源；失败 → None + WARN。

        校验面（§3.3/§3.4，以 warm 提供的身份面为准）：
        - ``index.locale == ctx_locale``（live memo token 不含 locale 维度，
          index 绑代自带 locale——不一致=旧代串图风险，整批弃种）；
        - ``ctx_identity``（调用方经 cold.compute_identity 从 ctx 游戏安装现算，
          组合层注入）与 current.json ``identity`` 逐键相等 + 由 identity 重推
          ``game_id``（schema.cjson 单射）与代库绑定一致。

        任何异常（无 index / DB 打不开 / 校验失败）→ WARN 一次 + None，
        不 raise（调用方拿 None 即纯 live，逐位不变）。"""
        try:
            idx = SupplyIndex(Path(cache_root))
        except Exception as exc:                      # noqa: BLE001 —— 弃种=纯 live
            logger.warning("[seed] supply index 不可用，整批弃种回 live（%s: %s）",
                           type(exc).__name__, exc)
            return None
        try:
            if (idx.locale or "") != (ctx_locale or ""):
                logger.warning(
                    "[seed] index locale 与 ctx 不一致（index=%r ctx=%r）——"
                    "整批弃种回 live", idx.locale, ctx_locale)
                idx.close()
                return None
            cur = idx.layout.read_current() or {}
            if ctx_identity is not None:
                cur_ident = cur.get("identity")
                if not isinstance(cur_ident, dict):
                    logger.warning(
                        "[seed] index current.json 无 identity 账，无法核同源"
                        "——整批弃种回 live")
                    idx.close()
                    return None
                if cur_ident != ctx_identity:
                    logger.warning(
                        "[seed] index generation 身份与 ctx 游戏安装不同源"
                        "（game manifest/build/dll 漂移）——整批弃种回 live")
                    idx.close()
                    return None
                if S.sha256_hex(S.cjson(cur_ident).encode("utf-8")) != idx.game_id:
                    logger.warning(
                        "[seed] current.json identity 与代库 game_id 不一致"
                        "（账面损坏）——整批弃种回 live")
                    idx.close()
                    return None
        except Exception as exc:                      # noqa: BLE001
            logger.warning("[seed] index 校验失败，整批弃种回 live（%s: %s）",
                           type(exc).__name__, exc)
            idx.close()
            return None
        logger.info("[seed] index 就绪：generation=%s locale=%s",
                    idx.generation, idx.locale)
        seeder = cls(idx, ctx_locale=ctx_locale, ctx_identity=ctx_identity,
                     kit_gap_faces=kit_gap_faces)
        seeder._install_entry_seed()
        return seeder

    # ---- entry seed 句柄生命周期（A5；supply.textures 模块级注入位） ----

    def _install_entry_seed(self) -> None:
        """``AtlasEntrySeed`` 安装进 supply.textures（entry_for_ref 先行面）。

        句柄值面=live 解析产物逐位一致（index 链=cold 同解码器提取、判定=mip
        判定账），未覆盖 ref 落 live——安装与否只改数据源不改行为；未安装=
        纯 live 逐位不变。"""
        from eidolon.core.supply.textures import set_entry_seed_lookup

        self._entry_seed = AtlasEntrySeed(self.index)
        set_entry_seed_lookup(self._entry_seed)

    def _uninstall_entry_seed(self) -> None:
        from eidolon.core.supply.textures import clear_entry_seed_lookup

        seed = getattr(self, "_entry_seed", None)
        if seed is not None:
            clear_entry_seed_lookup(seed)
            self._entry_seed = None

    # ---- 关闭 ----

    def close(self) -> None:
        self._uninstall_entry_seed()
        self.index.close()

    def __enter__(self) -> "CardSeeder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- provider（A2 seam 注入位；零参可调用） ----

    def provider_for_card(self, card_id: str) -> Callable[[], dict | None]:
        """``api._render_one(seed_provider=)`` 注入形（零参；内部弃种自兜）。"""
        return functools.partial(self.seeds_for_card, card_id)

    def provider_for_dbf(self, dbf_id: int) -> Callable[[], dict | None]:
        return functools.partial(self.seeds_for_dbf, dbf_id)

    # ---- 按卡种子 ----

    def seeds_for_card(self, card_id: str) -> dict | None:
        """card_id（m_noteMiniGuid）→ memo 种子 dict；失败 → None（该卡弃种）。"""
        return self._seeds(card_id=card_id)

    def seeds_for_dbf(self, dbf_id: int) -> dict | None:
        """dbf_id → 卡（index cards 表首行账）→ memo 种子 dict；查无/失败 → None。

        dbf 复行（counts_dbf_duplicates 账面）取 card_id 排序首行——与 live 取
        行不同源时种子 token args 不匹配 → unused → live 兜底（fail-safe）。"""
        return self._seeds(dbf_id=dbf_id)

    def _seeds(self, *, card_id: str | None = None,
               dbf_id: int | None = None) -> dict | None:
        try:
            if card_id is None:
                row = self.index.conn.execute(
                    "SELECT card_id FROM cards WHERE dbf_id=? "
                    "ORDER BY card_id LIMIT 1", (int(dbf_id),)).fetchone()
                if row is None:
                    logger.warning("[seed] dbf %s 不在 index cards 表——该卡弃种回 live",
                                   dbf_id)
                    return None
                card_id = row["card_id"]
            plan = self.index.plan(card_id)
            if plan is None:
                logger.warning("[seed] %s 不在 index cards 表——该卡弃种回 live",
                               card_id)
                return None
            bundle = self.index.assemble_card(card_id)     # 严格门（缺项 fail loud）
        except (SupplyMissingError, SupplyBlobCorruptError,
                SupplyIndexCorruptError) as exc:
            logger.warning("[seed] %s assemble 失败，该卡弃种回 live：%s", card_id, exc)
            return None
        except Exception as exc:                          # noqa: BLE001 —— fail-safe
            logger.warning("[seed] %s assemble 异常，该卡弃种回 live（%s: %s）",
                           card_id, type(exc).__name__, exc)
            return None
        try:
            seeds, ledger = self._convert(card_id, plan, bundle)
        except Exception as exc:                          # noqa: BLE001 —— fail-safe
            logger.warning("[seed] %s 转换异常，该卡弃种回 live（%s: %s）",
                           card_id, type(exc).__name__, exc)
            return None
        self.last_ledger = ledger
        if not seeds:
            logger.warning("[seed] %s 零可种 token（skipped=%d）——该卡弃种回 live",
                           card_id, len(ledger.skipped))
            return None
        logger.info("[seed] %s", ledger.summary())
        for reason in ledger.skipped_reasons:
            logger.info("[seed]   %s", reason)
        return seeds

    # ---- role→token 映射（转换器本体；缺项/形状不符=该 token 不种） ----

    def _convert(self, card_id: str, plan, bundle: dict
                 ) -> "tuple[dict, SeedLedger]":
        """assemble 束 + plan → (memo 种子 dict, ledger)。

        映射表（Phase 0 §1 B 类 + A3-A6 任务单）：
        - ``art.portrait(card_id)``        ← bundle["portrait"]（PIL 同形）；
        - ``frames.kit(frame)``            ← bundle["kit"]（plan 帧族）+ warm
          ``kit(frame)``（其余已建帧族——卡不变域项）六面重组 + 缺口面（A6=
          index races/mesh_refs 面；任一失败该 kit token 不种）；
        - ``frames.bacon_kit()``           ← warm ``kit("bacon")`` 六面重组
          （特源帧=kit 六面件存储、bacon_kit token 种——live 域项名词面）；
        - ``frames.kit_light(frame)``      ← warm ``kit_light(frame)`` 六面重组
          （races 恒 None=live kit_light 同形；textures 空 dict=轻走查语义）；
        - ``frames.ability_kit(q)``        ← warm supplement parts → AbilityKit；
        - ``frames.badges_kit()``          ← parts → BadgesKit；
        - ``frames.btf_kit()``             ← parts → BtfKit；
        - ``frames.ornaments_kit()``       ← parts → OrnamentsKit；
        - ``frames.ta_supplement()``       ← parts["arrays"]（ndarray dict）；
        - ``frames.material_state()``      ← parts["data"]（dict）；
        - ``frames.portrait_uv1()``        ← parts["meshes"] 按名重组；
        - ``text.fontdefs()``              ← bundle["text"]["fontdefs"]（逐键同形）；
        - ``text.font_table()``            ← fontdefs 无损派生 entries；
        - ``text.font_ttf_bytes(name)``    ← bundle["text"]["fonts"][name]（bytes）；
        - ``text.font_asset_params()``     ← warm supplement parts["data"]（dict）；
        - ``watermarks.texture(ref)``      ← bundle["watermark"]，ref=index
          manifest 裁决值（card_id→ref 预解析；ref 与 live 裁决不同源时种子
          unused → live 兜底）；
        - ``color.probe()``                ← bundle["color"]（12 族槽位表逐键同形，
          A4）；
        - ``color.atlas(family, ct)``      ← warm 图集解码（PIL 同形），枚举=帧族
          全有效槽（live 消费方遍历：kit 提取按帧族全槽扇出 + 类色写点单槽同族——
          frame 无族（ally_premium/heropower）或 plan 无 kit role → 不枚举）。
        - ``textures.mip_registry()``      ← warm.mip_registry()（live 同形 raw
          dict 直透，A5）；
        - ``art.portrait_mip(card_id)``    ← warm.portrait_mip(card_id) →
          LazyFloatChain（live 形状类，A5）。
        kit_play / gem:* 不在 A3-A6 映射（任务单另案）。"""
        seeds: dict = {}
        ledger = SeedLedger(card_id=card_id)

        img = bundle.get("portrait")
        if isinstance(img, Image.Image):
            seeds[("art", "portrait", (card_id,))] = img
            ledger.seeded.append(_token_str(("art", "portrait", (card_id,))))
        else:
            _skip(ledger, ("art", "portrait", (card_id,)),
                  f"portrait 缺席或形状不符（{type(img).__name__}）")

        kit_item = next((i for i in plan.items if i.role == "kit"), None)
        frame = kit_item.manifest.get("frame") if kit_item is not None else None
        self._convert_kit(frame, bundle, seeds, ledger)
        self._convert_bacon(seeds, ledger)
        self._convert_kit_light(seeds, ledger)
        self._convert_supplements(seeds, ledger)
        self._convert_text(bundle, seeds, ledger)
        self._convert_watermark(card_id, plan, bundle, seeds, ledger)
        self._convert_color(frame, bundle, seeds, ledger)
        self._convert_mip(card_id, seeds, ledger)
        return seeds, ledger

    def _convert_kit(self, plan_frame: str | None, bundle: dict,
                     seeds: dict, ledger: SeedLedger) -> None:
        """frames.kit(frame)：plan 帧族（六面自 assemble 束）+ 其余已建帧族
        （warm 读回——卡不变域项，live 请求面含非本卡帧族如 kit("ally_premium")）。

        缺口面（races/mesh_refs）供给失败=该 kit token 不种（种缺 races 的
        ally Kit 会在渲染链炸——比 live 兜底更糟，§3.1）。"""
        six = bundle.get("kit")
        if plan_frame and isinstance(six, dict):
            self._seed_kit_token(plan_frame, six, seeds, ledger)
        else:
            _skip(ledger, ("frames", "kit", (plan_frame,) if plan_frame else None),
                  "plan 无 kit role/manifest 无 frame 账或 kit 束形状不符")
        for frame in self.index.kit_frames():
            if frame == plan_frame or frame == "bacon":
                continue            # plan 帧已种 / bacon=bacon_kit token（特源）
            try:
                other = self.index.kit(frame)
                if not isinstance(other, dict):
                    raise TypeError(f"warm kit 形状不符（{type(other).__name__}）")
            except Exception as exc:  # noqa: BLE001 —— 该 token 不种回 live
                _skip(ledger, ("frames", "kit", (frame,)),
                      f"warm kit 供给失败：{type(exc).__name__}: {exc}")
                continue
            self._seed_kit_token(frame, other, seeds, ledger)

    def _seed_kit_token(self, frame: str, six: dict, seeds: dict,
                        ledger: SeedLedger) -> None:
        token = ("frames", "kit", (frame,))
        try:
            races, mesh_refs = self._gap_faces(frame)
            kit = _kit_from_index(frame, six, races, mesh_refs)
        except Exception as exc:          # noqa: BLE001 —— 缺口面失败→不种
            _skip(ledger, token, f"kit 缺口面（races/mesh_refs）供给失败："
                                 f"{type(exc).__name__}: {exc}")
            return
        seeds[token] = kit
        ledger.seeded.append(_token_str(token))

    def _convert_bacon(self, seeds: dict, ledger: SeedLedger) -> None:
        """frames.bacon_kit()：bacon 特源帧（index 同 kit 六面件存储——live 域项
        名=bacon_kit，seed 按 live token 词面种）。"""
        token = ("frames", "bacon_kit", ())
        try:
            six = self.index.kit("bacon")
            if not isinstance(six, dict):
                raise TypeError(f"warm kit(bacon) 形状不符（{type(six).__name__}）")
            races, mesh_refs = self._gap_faces("bacon")
            kit = _kit_from_index("bacon", six, races, mesh_refs)
        except Exception as exc:          # noqa: BLE001 —— 该 token 不种回 live
            _skip(ledger, token, f"bacon kit 供给失败：{type(exc).__name__}: {exc}")
            return
        seeds[token] = kit
        ledger.seeded.append(_token_str(token))

    def _convert_kit_light(self, seeds: dict, ledger: SeedLedger) -> None:
        """frames.kit_light(frame)×9：轻走查 kit（races 恒 None=live kit_light
        同形；mesh_refs 面=portrait_uv1 消费位（material_state seeded 时该面
        不被请求——unused 无害）。"""
        for frame in self.index.kit_light_frames():
            token = ("frames", "kit_light", (frame,))
            try:
                six = self.index.kit_light(frame)
                if not isinstance(six, dict):
                    raise TypeError(f"warm kit_light 形状不符（{type(six).__name__}）")
                mesh_refs = self.index.kit_mesh_refs(frame)
                if not isinstance(mesh_refs, dict):
                    raise SupplyMissingError(
                        [f"kit_light {frame}: mesh_refs 面缺席"])
            except Exception as exc:  # noqa: BLE001 —— 该 token 不种回 live
                _skip(ledger, token, f"kit_light 供给失败："
                                     f"{type(exc).__name__}: {exc}")
                continue
            seeds[token] = _kit_from_index(frame, six, None, mesh_refs)
            ledger.seeded.append(_token_str(token))

    def _convert_supplements(self, seeds: dict, ledger: SeedLedger) -> None:
        """特源/附件 kit + font_asset_params（A6 任务单清单；单 token 失败不种）。

        形状契约=supplement_extract._supp_value / _ability_value 的存储表两半
        （两处同步改——单测钉死）。"""
        for q in ("normal", "premium"):
            token = ("frames", "ability_kit", (q,))
            try:
                parts = self.index.supplement_parts(
                    S.DOMAIN_FRAMES, S.ITEM_ABILITY_KIT, {"quality": q})
                from eidolon.core.supply.frames.ability import AbilityKit
                from eidolon.core.supply.frames.kits import _ArrayDict

                kit = AbilityKit(
                    recon_meta={**parts["recon_meta"],
                                "hierarchy": parts["hierarchy"]},
                    arrays=_ArrayDict(parts["arrays"]),
                    textures=parts["textures"],
                    portrait=parts["portrait"].get("portrait.png"),
                    portrait_meta=parts.get("portrait_meta") or {},
                    report=parts["report"],
                    obj_texts={},           # 不进种子形状（渲染链零消费）
                    fonts_bytes={},         # 同上
                    ubertext=parts["ubertext"],
                    mesh_refs={k: (v[0], int(v[1]))
                               for k, v in parts["mesh_refs"].items()})
            except Exception as exc:      # noqa: BLE001 —— 该 token 不种回 live
                _skip(ledger, token, f"ability_kit({q}) 供给/重组失败："
                                     f"{type(exc).__name__}: {exc}")
                continue
            seeds[token] = kit
            ledger.seeded.append(_token_str(token))

        for item, cls, fields in (
                ("badges_kit", "BadgesKit",
                 (("report", "report"), ("arrays", "arrays"),
                  ("textures", "textures"))),
                ("btf_kit", "BtfKit",
                 (("report", "report"), ("arrays", "arrays"),
                  ("textures", "textures"), ("card_race", "card_race"))),
                ("ornaments_kit", "OrnamentsKit",
                 (("report", "report"), ("arrays", "arrays"),
                  ("textures", "textures")))):
            token = ("frames", item, ())
            try:
                parts = self.index.supplement_parts(S.DOMAIN_FRAMES, item, {})
                module = __import__(
                    "eidolon.core.supply.frames."
                    + {"BadgesKit": "badges", "BtfKit": "btf",
                       "OrnamentsKit": "ornaments"}[cls],
                    fromlist=[cls])
                obj = getattr(module, cls)(
                    **{field: parts[part] for part, field in fields})
            except Exception as exc:      # noqa: BLE001 —— 该 token 不种回 live
                _skip(ledger, token, f"{item} 供给/重组失败："
                                     f"{type(exc).__name__}: {exc}")
                continue
            seeds[token] = obj
            ledger.seeded.append(_token_str(token))

        for item, part, token in (
                ("ta_supplement", "arrays", ("frames", "ta_supplement", ())),
                ("material_state", "data", ("frames", "material_state", ()))):
            try:
                parts = self.index.supplement_parts(S.DOMAIN_FRAMES, item, {})
                value = parts[part]
                if item == "ta_supplement" and \
                        not all(hasattr(v, "shape") for v in value.values()):
                    raise TypeError("ta_supplement 形状不符（非 ndarray dict）")
            except Exception as exc:      # noqa: BLE001 —— 该 token 不种回 live
                _skip(ledger, token, f"{item} 供给失败："
                                     f"{type(exc).__name__}: {exc}")
                continue
            seeds[token] = value
            ledger.seeded.append(_token_str(token))

        token = ("frames", "portrait_uv1", ())
        try:
            parts = self.index.supplement_parts(
                S.DOMAIN_FRAMES, S.ITEM_PORTRAIT_UV1, {})
            meshes: dict = {}
            for key, arr in parts["meshes"].items():
                name, field = key.rsplit("/", 1)
                meshes.setdefault(name, {})[field] = arr
            if not meshes:
                raise TypeError("portrait_uv1 meshes 空")
        except Exception as exc:          # noqa: BLE001 —— 该 token 不种回 live
            _skip(ledger, token, f"portrait_uv1 供给失败："
                                 f"{type(exc).__name__}: {exc}")
        else:
            seeds[token] = meshes
            ledger.seeded.append(_token_str(token))

        token = ("text", "font_asset_params", ())
        try:
            parts = self.index.supplement_parts(
                S.DOMAIN_TEXT, S.ITEM_FONT_ASSET_PARAMS, {})
            value = parts["data"]
            if not isinstance(value, dict) or not value.get("fonts"):
                raise TypeError("font_asset_params 形状不符")
        except Exception as exc:          # noqa: BLE001 —— 该 token 不种回 live
            _skip(ledger, token, f"font_asset_params 供给失败："
                                 f"{type(exc).__name__}: {exc}")
        else:
            seeds[token] = value
            ledger.seeded.append(_token_str(token))

    def _index_gap_faces(self, frame: str) -> "tuple[dict | None, dict]":
        """缺口面 index 形（A6 缺省）：races 只对 live races=True 帧族供面
        （S.KIT_RACE_FRAMES 词面——缺面=SupplyMissingError，kit token 整个不种
        ——种缺 races 的 ally Kit 会在 GetRaceText 炸）；mesh_refs 恒供（缺面
        同响亮）。"""
        mesh_refs = self.index.kit_mesh_refs(frame)
        if not isinstance(mesh_refs, dict):
            raise SupplyMissingError([f"kit {frame}: mesh_refs 面缺席"])
        races = None
        if frame in S.KIT_RACE_FRAMES:
            races = self.index.kit_races(frame)
            if not (isinstance(races, dict)
                    and isinstance(races.get("strings"), dict)):
                raise SupplyMissingError(
                    [f"kit {frame}: races 面缺席（races=True 帧族）"])
        return races, mesh_refs

    def _gap_faces(self, frame: str) -> "tuple[dict | None, dict]":
        """缺口面（races/mesh_refs）按帧缓存供给；``kit_gap_faces`` 可注入替身
        （单测零游戏形；缺省=index 面）。供给失败=异常上抛（kit token
        整个不种，调用方记账）。"""
        if frame not in self._gap_cache:
            self._gap_cache[frame] = self.kit_gap_faces(frame)
        return self._gap_cache[frame]

    def _convert_text(self, bundle: dict, seeds: dict,
                      ledger: SeedLedger) -> None:
        """text 全域段（卡不变；warm text() 随 assemble_card 附带）。"""
        text = bundle.get("text")
        fontdefs = text.get("fontdefs") if isinstance(text, dict) else None
        if not isinstance(fontdefs, dict) or not fontdefs:
            _skip(ledger, ("text", "fontdefs", ()), "text 束缺席或 fontdefs 空表")
            return
        seeds[("text", "fontdefs", ())] = fontdefs
        ledger.seeded.append(_token_str(("text", "fontdefs", ())))
        entries = _font_table_entries(fontdefs)
        if entries:
            seeds[("text", "font_table", ())] = entries
            ledger.seeded.append(_token_str(("text", "font_table", ())))
        else:
            _skip(ledger, ("text", "font_table", ()), "font_table 派生空表")
        fonts = text.get("fonts")
        if isinstance(fonts, dict):
            for name, ttf in sorted(fonts.items()):
                token = ("text", "font_ttf_bytes", (name,))
                if isinstance(ttf, (bytes, bytearray)) and ttf:
                    seeds[token] = bytes(ttf)
                    ledger.seeded.append(_token_str(token))
                else:
                    _skip(ledger, token, f"ttf 字节缺席或形状不符（{name}）")

    def _convert_watermark(self, card_id: str, plan, bundle: dict,
                           seeds: dict, ledger: SeedLedger) -> None:
        """watermarks.texture(ref)：ref=index manifest 裁决值（card_id→ref 预解析）。"""
        token = ("watermarks", "texture", None)
        wm = bundle.get("watermark")
        wm_item = next((i for i in plan.items if i.role == "watermark"), None)
        ref = wm_item.manifest.get("ref") if wm_item is not None else None
        if not isinstance(wm, Image.Image):
            _skip(ledger, token, "watermark 缺席（无水印裁决=合法缺席）或形状不符")
            return
        if not ref:
            _skip(ledger, token, "watermark item manifest 无 ref 账")
            return
        token = ("watermarks", "texture", (ref,))
        seeds[token] = wm
        ledger.seeded.append(_token_str(token))

    def _convert_color(self, frame: str | None, bundle: dict,
                       seeds: dict, ledger: SeedLedger) -> None:
        """color.probe() + color.atlas(family, ct)（A4 两 token）。

        probe：bundle["color"]（12 族槽位表逐键同形）——缺席（旧代/未知卡型卡
        无 color 挂接）→ token 不种回 live。
        atlas：**帧族全有效槽枚举**（live 消费方遍历=kit 提取按帧族全槽扇出
        [kits.py:300-309] + 类色写点单槽同族 [compiler._class_color]）——
        warm.color_atlas 逐槽解码种 PIL；单槽缺席（材质族/空占位/解码失败）=
        该 token 不种。frame 无族（ally_premium/heropower——金卡/英雄技能帧
        类色=染色不换图集，specs.py 账）或 plan 无 kit role → 不枚举。
        memory 账：帧族 23-35 槽 1024² RGBA（每槽 ~4MB 解码态）与 live kit
        提取的 kit.textures 全槽驻留同量级（非额外膨胀）。"""
        probe = bundle.get("color")
        token_p = ("color", "probe", ())
        if not isinstance(probe, dict) or not probe:
            _skip(ledger, token_p, "color 束缺席（旧代/未知卡型卡无 color 挂接）"
                                   "或形状不符")
            return
        seeds[token_p] = probe
        ledger.seeded.append(_token_str(token_p))
        if not frame:
            return                      # 帧族无从取（atlas 枚举缺位=合法形态）
        family = _frame_family(frame)
        if not family:
            return                      # frame 无类色图集族（specs.py family=None）
        for ct, ref in enumerate(probe.get(family, [])):
            if not (isinstance(ref, str) and ":" in ref):
                continue                # 空占位槽（live kit 提取同判跳过）
            token = ("color", "atlas", (family, ct))
            try:
                img = self.index.color_atlas(family, ct)
                if not isinstance(img, Image.Image):
                    raise TypeError(f"warm atlas 形状不符（{type(img).__name__}）")
            except Exception as exc:    # noqa: BLE001 —— 该 token 不种回 live
                _skip(ledger, token, f"atlas 槽供给失败：{type(exc).__name__}: {exc}")
                continue
            seeds[token] = img
            ledger.seeded.append(_token_str(token))

    def _convert_mip(self, card_id: str, seeds: dict, ledger: SeedLedger) -> None:
        """textures.mip_registry() + art.portrait_mip(card_id)（A5 两 token）。

        registry：warm ``mip_registry()`` live 同形 raw dict **直透**（lods=
        uint8 数组——消费方 raster._registry / chain_for_name 自行包
        LazyFloatChain；值面=cold 同解码器提取产物）。缺席（旧代）→ token 不种
        回 live（live 首渲染照旧解码注册表）。
        portrait_mip：warm ``portrait_mip(card_id)`` → ``LazyFloatChain(
        chain.lods)``（live 形状类函数体 import——种子值进 memo 后 render 链
        按 live 语义消费；uint8 层与 warm 链共享引用，float 转换惰性=live
        LazyFloatChain 同款）。"""
        token_r = ("textures", "mip_registry", ())
        try:
            reg = self.index.mip_registry()
            if not isinstance(reg, dict) or not reg:
                raise TypeError(f"warm registry 形状不符（{type(reg).__name__}）")
        except Exception as exc:        # noqa: BLE001 —— 该 token 不种回 live
            _skip(ledger, token_r, f"mip registry 供给失败："
                                   f"{type(exc).__name__}: {exc}")
        else:
            seeds[token_r] = reg
            ledger.seeded.append(_token_str(token_r))
        token = ("art", "portrait_mip", (card_id,))
        try:
            ent = self.index.portrait_mip(card_id)
            if not (isinstance(ent, dict) and ent.get("chain") is not None):
                raise TypeError(f"warm portrait_mip 形状不符（{type(ent).__name__}）")
        except Exception as exc:        # noqa: BLE001 —— 该 token 不种回 live
            _skip(ledger, token, f"portrait_mip 供给失败："
                                 f"{type(exc).__name__}: {exc}")
            return
        from eidolon.core.supply.textures import LazyFloatChain

        seeds[token] = {"name": ent["name"],
                        "chain": LazyFloatChain(ent["chain"].lods),
                        "filter": ent["filter"], "bias": float(ent["bias"])}
        ledger.seeded.append(_token_str(token))


def _skip(ledger: SeedLedger, token: tuple, reason: str) -> None:
    """token 不种记账（skipped 清单 + 原因；INFO 面随 ledger.summary 落日志）。"""
    ledger.skipped.append(_token_str(token) if token[2] is not None
                          else f"{token[0]}.{token[1]}(?)")
    ledger.skipped_reasons.append(f"skip {ledger.skipped[-1]}：{reason}")
