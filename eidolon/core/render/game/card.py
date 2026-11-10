"""consumer-v2 装配体（完成态）：assemble 的 S2 分发步=新镜像 resolve_prefab（产出 prefab 身份），S3-S10 计划函数全走新包（段4 内部化收口），旧链已退役（tag old-render-freeze-20261029 保留 oracle）。本文件主体=old card.py 逐字副本+新分发补丁（diff 可 grep "consumer-v2 段1"）。

card — 卡装载链离线编排层（段 S1：LoadActor→OnActorLoaded 装配段）。

游戏锚（walk-skeleton §1 + §0.1 双侧链对位 Step1/2/4/5）：
  Card.UpdateActor（Card.cs:Card.UpdateActor 实体进区触发）→ Card.LoadActor（:6021）→
  AssetLoader.InstantiatePrefab(actorPath, OnActorLoaded)（:6032——回调驱动，
  骨架 §0.4.1 形态边界不复刻，我方同步线性）→ Card.OnActorLoaded（:6180 区段）
  → SetEntity/SetCardDef/UpdateAllComponents（组件装配入口）。

段实质（批21 统筹裁定）：数据真值=infra/card.py+dbf.py+text_shim.py
（在役共享地基直接用——骨架 §1 既定「本段纯 DBF/CLR 归 infra 不入配方包」：
游戏数据归 infra、recipes=纯资产）。本模块=装载链**离线编排层**：从 dbf_id 到
「卡对象+帧分发+各段计划框架就绪」的装配输出——S11 组装段的输入准备半边；
执行/像素面（compile_plan*/prep_plan 换轨、光栅、文字执行、注入接线、垫图
V-pass）归 S11 不碰（立户件挂接位见 ASSEMBLY_HOOKS 账与段级对拍探针）。

两入口：
  load_card(dbf_id)——卡语义面：infra Card.from_dbf 门面消费（类型同源，不复制
    tag 语义）+身份轴编排（dbf_id=数字 id 正典轴 vs card_id=m_noteMiniGuid 原画
    寻址轴，异名不混用——批12 S2 坑账先例）+语境轴（is_bacon_hero=CARD_HERO
    表查 infra :294 / cost_hidden_reason 显隐数据腿 infra :476）。
  assemble(dbf_id, zone, ...)——装配计划框架：编排引用 S2-S10 九段已各自对拍
    函数（引用清单=ASSEMBLY_HOOKS，段级对拍全账面），产出结构化装配账（哪段
    函数被调用/输入输出挂接位）——只编排不执行。旧实现参照=old_frames/
    render_card.py:556 render_card/:586 render_with 前置编排段（resolve_frame_key
    →语境 mode→compile→prep 的调用序）——全链执行序归 S11，本段只对齐「卡
    语义准备+编排引用框架」。

与 infra.card 分工：彼处=DBF tag 数据真值（Card 门面/from_dbf/tag 枚举）；
此处=装载编排（身份轴/语境轴/帧分发/九段计划框架引用）。

配方面：原画/水印纹理/帧 kit 经各段已对拍函数触 recipes（本模块不直呼 recipes
域项——S5 plan_portrait/S8 update_watermark/S3 scene_for 的引用即配方面）；
DBF 直读恒经 infra（Card.from_dbf）。

纪律面前置——assemble 经 S3/S5/S8/S10 引用触供给配方（@item），**消费须在
supply session 内**（入口层独占纪律，批12-20 同款；未来门驱动循环开 session
调本段，段内不开）；load_card 纯 infra（DBF 直读），session 外可用。

离线边界（宁薄勿越，非静默丢弃）——
  * S7 text_layer_plan=前向钩（ASSEMBLY_HOOKS mode="forward"）：其入参
    plan["texts"] 是 S11 compile 产物，新包尚无该面——本段记录函数引用与
    输入输出契约，不调用（衔接探针以旧链 compile 产物喂挂验证）。
  * with_race_for（S8 offset 规则腿）吃 plan 文本内容（notext 变体敏感）=
    prep 后语义——装配账 wm 产物恒 with_race=None 腿（offset 保留序列化），
    规则腿挂 S11 接线位。
  * 变体轴（notext/textonly）/t 相位注入=prep_plan 面（S11），装配账不含。
  * S4/S6/S10 的完整判定面（class_color_segment/multiclass_segments/plan_gem/
    plan_portrait_render 等）=S11 compile 接线消费位（批13/15/16 产物）——
    本段只引用统筹清单九段函数，多引=越界。
  * SIGNATURE 帧（get_signature_actor 批12 立户）立户保留，随品质扩展批生长；
    def_loader CardDef prefab 字段面已删（2026-10-29 死代码收口——cards_map
    数据面已被 recipes.art.portrait NORMAL 腿内联吸收，零独立消费者）。
"""

from __future__ import annotations

from eidolon.core.infra.card import Card
from eidolon.core.render.game import actor_names as _actor_names  # 新镜像（本役真分发）
from eidolon.core.render.game import card_color_switcher as _switcher   # consumer-v2 段4
from eidolon.core.render.scenes import scenes as _frames   # consumer-v2 段4（prefab 键）
from eidolon.core.render.text import uber_text as _uber_text   # consumer-v2 段3
from eidolon.core.render.game.actor import gems as _gems   # consumer-v2 段4
from eidolon.core.render.game.actor import injectors as _injectors   # consumer-v2 段4
from eidolon.core.render.game.actor import portrait as _portrait   # consumer-v2 段4
from eidolon.core.render.game.actor import watermark as _watermark   # consumer-v2 段4
from eidolon.core.render._provenance import fitted, invented  # noqa: F401 （按需）
from eidolon.core.render._provenance import parallel  # noqa: F401 （族默认）

# ============================================================================
# 编排引用清单（九段函数账——S11 组装段的挂接总账；段级对拍全账面）
# ============================================================================

ASSEMBLY_HOOKS: tuple[dict, ...] = (
    # 序=骨架段号编排序（S2→S10，S7 前向钩收尾），非旧 render_with 执行序
    # （:604-650 执行序归 S11——编排≠执行序）。
    {"segment": "S2", "fn": "actor_names.resolve_frame_key", "mode": "invoke",
     "consumes": "Card|dbf_id, zone", "produces": "(frame_key, card)——帧分发正典+卡对象单流",
     "ref": "骨架 §2 / old_frames/render_card.py:604（render_with 首跳）/ 批12"},
    {"segment": "S10", "fn": "actor.injectors.resolve_bg_mode", "mode": "invoke",
     "consumes": "card, use_bg_style（cfg 三态）", "produces": "语境 mode|None（bacon/constructed）",
     "ref": "old_frames/render_card.py:612-613（前置编排段本体）/ AlphaTool.Pipeline.cs:AlphaTool.ImportJsonSelectAndRun / 批20"},
    {"segment": "S3", "fn": "frames.scene_for", "mode": "invoke",
     "consumes": "frame_key", "produces": "scene 五面（meta/hierarchy/arrays/report/ubertext）",
     "ref": "骨架 §3 / old :329/:646（scene 挂接位）/ 批14"},
    {"segment": "S4", "fn": "card_color_switcher.class_color_pick", "mode": "invoke",
     "consumes": "card", "produces": "(tag_class, class_name, color_type) 三元组",
     "ref": "骨架 §4 / old_frames/scene_compiler.py:157-163 / 批13"},
    {"segment": "S5", "fn": "actor.portrait.plan_portrait", "mode": "invoke",
     "consumes": "card_id（m_noteMiniGuid 寻址轴）, frame_key",
     "produces": "plan.portrait 键构（card_id/source/apply/img）",
     "ref": "骨架 §5 / old 六编译器 portrait 段（sc:294-297 等）/ 批15"},
    {"segment": "S6", "fn": "actor.gems.plan_rarity_gem", "mode": "invoke",
     "consumes": "card", "produces": "plan.rarity_gem 七键",
     "ref": "骨架 §6 / old_frames/scene_compiler.py:207-226 / 批16"},
    {"segment": "S6", "fn": "actor.gems.cost_text_semantics", "mode": "invoke",
     "consumes": "card, bg_style（语境 mode）", "produces": "费用显隐+铸币位移账|None",
     "ref": "骨架 §6 / old_plan/prep_plan.py:54-88 / 批16"},
    {"segment": "S8", "fn": "actor.watermark.desc_frame_for", "mode": "invoke",
     "consumes": "frame_key", "produces": "desc 帧键|None（update_watermark frame 参数供给）",
     "ref": "批17 _DESC_FRAME（FRAME_DESC desc_frame 九行平行表）"},
    {"segment": "S8", "fn": "actor.watermark.update_watermark", "mode": "invoke",
     "consumes": "card, desc_frame（with_race=None 腿——规则腿挂 S11）",
     "produces": "wm dict 十四键|None（无 desc 面）",
     "ref": "骨架 §8 / old_frames/ta_watermark.py:110 / 批17"},
    {"segment": "S10", "fn": "actor.injectors.compile_badges", "mode": "invoke",
     "consumes": "card, frame_key", "produces": "徽章三件挂接清单|None",
     "ref": "骨架 §10 / old_frames/render_card.py:357-364（注入四件段①）/ 批20"},
    {"segment": "S10", "fn": "actor.injectors.compile_faction_banner", "mode": "invoke",
     "consumes": "card, frame_key", "produces": "派系饰件挂接清单|None",
     "ref": "old_frames/render_card.py:366-371（注入四件段②）/ 批20"},
    {"segment": "S10", "fn": "actor.injectors.compile_tier_spell", "mode": "invoke",
     "consumes": "card, frame_key, bg_style", "produces": "BG 盾徽+金币件挂接清单|None",
     "ref": "old_frames/render_card.py:373-379（注入四件段③）/ 批20"},
    {"segment": "S10", "fn": "actor.injectors.compile_bacon_hero_frame", "mode": "invoke",
     "consumes": "frame_key", "produces": "BG 英雄帧 rig 挂接清单|None（bacon 键专用）",
     "ref": "old_frames/render_card.py:381-386（注入四件段④）/ 批20"},
    {"segment": "S10", "fn": "actor.injectors.compile_rune_banner", "mode": "invoke",
     "consumes": "card, frame_key（帧键门 RUNE_BANNER_ROOTS 在编排位——old :644 同构）",
     "produces": "符文横幅挂接清单（非符文卡终点=Hide 记账）|None（play/heropower 无挂点）",
     "ref": "old_frames/render_card.py:639-645（接线段）/ 批20"},
    {"segment": "S7", "fn": "uber_text.text_layer_plan", "mode": "forward",
     "consumes": "frame_key, plan 文字节（S11 compile 产物）",
     "produces": "文字层 plan（nodes/curved/entries）→ S11 render_text 执行面",
     "ref": "骨架 §7 / old_frames/render_card.py:296-319 消费半 / 批19——前向钩：本段不调用"},
)
"""九段编排引用清单（15 invoke+1 forward）。段覆盖=S2/S3/S4/S5/S6/S7/S8/S10
（S1 本段自体；S9/S11 立户件——光栅/文字执行/注入接线/垫图 pass/写点收敛——
不编排，挂接位由各段立户注与段级对拍探针锁定）。清单纪律：缺引=漏段、
多引=越界（对拍 B 段两侧全账）。"""


def _hook(segment: str, fn, mode: str = "invoke") -> dict:
    """运行时钩账条目（段/函数限定名/调用形态）——与 ASSEMBLY_HOOKS 同序同键
    （对拍断言两侧零漂移）。"""
    mod = fn.__module__
    if mod.startswith("eidolon.core.render.game."):
        mod = mod[len("eidolon.core.render.game."):]
    return {"segment": segment, "fn": f"{mod}.{fn.__name__}", "mode": mode}


def _card_face(card: Card) -> dict:
    """卡语义面（load_card/assemble 共用形）：infra 门面读数+身份轴+语境轴。

    card=infra Card 本尊（类型同源——tag 消费经其 tags 容器/枚举属性，不复制）；
    dbf_id=数字正典轴 / card_id=m_noteMiniGuid 原画寻址轴（批12 异名账）；
    bacon_hero=CARD_HERO.hero_type==3 表查（infra :294）；
    cost_hidden_reason=HIDE_STATS→HIDE_COST→DORMANT 三锚链（infra :476）。"""
    return {
        "card": card,
        "dbf_id": int(card.dbf_id),
        "card_id": card.card_id,
        "cardtype": card.cardtype,
        "premium": card.premium,
        "rarity": card.rarity,
        "set_id": card.set_id,
        "bacon_hero": bool(card.is_bacon_hero),
        "cost_hidden_reason": card.cost_hidden_reason,
    }


# ============================================================================
# 卡装载（Card.LoadActor 离线等价——语义面）
# ============================================================================


@parallel
def load_card(dbf_id) -> dict:
    """卡装载：infra Card.from_dbf 门面消费+身份轴/语境轴编排。

    游戏对位=Card.LoadActor（Card.cs:Card.LoadActor）的语义装载半边（SetEntity/SetCardDef
    的离线语义面——CardDef 视觉字段装配在 assemble 的 S5 引用处兑现，prefab
    字段面=已删的 def_loader 立户位（2026-10-29 死代码收口，零独立消费者））。
    dbf 装载经 infra 单源（default_dbf 进程单例，
    from_dbf 每调新构 Card 对象——无 memo，调用方持账内 card 引用即单流）。

    返回卡语义账 dict（_card_face 形）：card/dbf_id/card_id/cardtype/premium/
    rarity/set_id/bacon_hero/cost_hidden_reason。纯 infra（DBF 直读），session 外
    可用。"""
    return _card_face(Card.from_dbf(int(dbf_id)))


# ============================================================================
# 装配计划框架（Card.OnActorLoaded :6180 区段离线等价——只编排不执行）
# ============================================================================


@invented(reason="装配计划框架=同步线性编排离线等价（OnActorLoaded 回调链不复刻，形态边界 §0.4）", counterpart="Card.cs OnActorLoaded→UpdateAllComponents")
def assemble(card_or_dbf, zone: str = "HAND", *, premium: int | None = None,
             use_bg_style=None) -> dict:
    """装配计划框架：OnActorLoaded→SetEntity/SetCardDef/UpdateAllComponents
    （Card.cs:Card.OnActorLoaded 区段）的离线编排等价——S2-S10 九段已对拍函数的引用/挂接，
    产出结构化装配账（S11 组装段的输入准备半边；执行序与像素面归 S11）。

    card_or_dbf=Card 门面实例（contract C 判据 1 四入口收 Card，2026-11-06；传 Card
    时整链零 from_dbf——S2 resolve_prefab 复用本对象，Card 对象自此单流全链）|
    数字 dbf id（旧路径零变化，S2 照旧单点装载）；zone ∈ HAND/PLAY（PLAY 区仅
    HERO，bacon 分岔=is_bacon_hero——S2 resolve_frame_key tripwire 同旧轨）；
    premium=品质覆写轴（TAG_PREMIUM int，None=card.premium 数据轴）——S1 仅记账进
    dispatch 账（资产品质选择=S2 名字分派层+S11 actor_ref(quality, slot) 消费位，
    九段判定面全吃 card 数据轴）；use_bg_style=语境三态（True/False 显式覆写=
    对拍位，None=数据推导——old render_with :612 同构，source 账随行）。

    返回装配账 dict：
      dbf_id / identity（_card_face 卡语义面，card 对象=全链单流）/ dispatch
      {zone, premium} / prefab（S2 产物=新真值）/ frame_key（过渡委托列，段5 消亡）/ bg_mode {mode, source}（S10 语境
      轴）/ scene（S3 五面，进程缓存同对象）/ plan_frame（各段计划框架产物：
      class_color_pick/portrait/rarity_gem/cost/desc_frame/watermark/injections
      五件挂接清单）/ hooks（运行时钩账——ASSEMBLY_HOOKS 同序同键）。

    消费须在 supply session 内（入口层独占纪律——S3/S5/S8/S10 触供给配方；
    段内不开）。"""
    hooks: list[dict] = []

    # S2 帧分发（old :604 首跳）——卡对象自此单流全链
    prefab, card = _actor_names.resolve_prefab(card_or_dbf, zone)   # consumer-v2：穿线=prefab
    hooks.append(_hook("S2", _actor_names.resolve_prefab))

    face = _card_face(card)

    # S10 语境 mode 轴（old :612-613 前置编排段本体）
    mode = _injectors.resolve_bg_mode(card, use_bg_style)
    hooks.append(_hook("S10", _injectors.resolve_bg_mode))

    # S3 scene 元组装（进程缓存，同帧键同对象）
    scene = _frames.scene_for(prefab)
    hooks.append(_hook("S3", _frames.scene_for))

    # S4 类色 pick 三元组（compile 期单色 pick；完整判定面=S11 compile 接线）
    pick = _switcher.class_color_pick(card)
    hooks.append(_hook("S4", _switcher.class_color_pick))

    # S5 肖像 plan 键构（card_id=m_noteMiniGuid 寻址轴——异名不混用）
    plan_portrait = _portrait.plan_portrait(face["card_id"], prefab)
    hooks.append(_hook("S5", _portrait.plan_portrait))

    # S6 宝石判定/费用语义（语境 mode 腿显式穿线）
    rarity_gem = _gems.plan_rarity_gem(card)
    hooks.append(_hook("S6", _gems.plan_rarity_gem))
    cost = _gems.cost_text_semantics(card, bg_style=mode)
    hooks.append(_hook("S6", _gems.cost_text_semantics))

    # S8 水印判定/键构（with_race=None 腿——规则腿=with_race_for(plan, frame)
    # 挂 S11 接线位；无 desc 面→desc_frame/wm 双 None）
    desc_frame = _watermark.desc_frame_for(prefab)
    hooks.append(_hook("S8", _watermark.desc_frame_for))
    wm = None if desc_frame is None else _watermark.update_watermark(card, desc_frame)
    hooks.append(_hook("S8", _watermark.update_watermark))

    # S10 注入五件挂接清单（执行序 badges→faction→tier→rig=old :357-388，
    # rune 帧键门=old :644 同构；接线变异=MergedNpz/plan 挂接归 S11
    # apply_injections）
    injections = {
        "badges": _injectors.compile_badges(card, prefab),
        "faction_banner": _injectors.compile_faction_banner(card, prefab),
        "tier_spell": _injectors.compile_tier_spell(card, prefab, bg_style=mode),
        "frame_rig": _injectors.compile_bacon_hero_frame(prefab),
        "rune_banner": (_injectors.compile_rune_banner(card, prefab)
                        if prefab in _injectors.RUNE_BANNER_ROOTS else None),
    }
    hooks.append(_hook("S10", _injectors.compile_badges))
    hooks.append(_hook("S10", _injectors.compile_faction_banner))
    hooks.append(_hook("S10", _injectors.compile_tier_spell))
    hooks.append(_hook("S10", _injectors.compile_bacon_hero_frame))
    hooks.append(_hook("S10", _injectors.compile_rune_banner))

    # S7 文字层 plan——前向钩（入参 plan["texts"]=S11 compile 产物，本段不调用）
    hooks.append(_hook("S7", _uber_text.text_layer_plan, mode="forward"))

    return {
        "dbf_id": int(face["dbf_id"]),
        "identity": face,
        "dispatch": {"zone": zone,
                     "premium": int(premium) if premium is not None else int(card.premium)},
        "prefab": prefab,
        "prefab": prefab,
        "bg_mode": {"mode": mode,
                    "source": "cfg:explicit" if use_bg_style is not None else "derived"},
        "scene": scene,
        "plan_frame": {
            "class_color_pick": pick,
            "portrait": plan_portrait,
            "rarity_gem": rarity_gem,
            "cost": cost,
            "desc_frame": desc_frame,
            "watermark": wm,
            "injections": injections,
        },
        "hooks": hooks,
    }
