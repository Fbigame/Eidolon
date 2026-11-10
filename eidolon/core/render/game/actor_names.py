"""actor_names — ActorNames 分发镜像（consumer-v2：名字分派层=唯一分发权威）。

对位 ActorNames.cs（Assembly-CSharp）：GetHandActor(:550 表驱动体)/
GetHandActorByTags(:475 Lettuce 优先)/GetPlayActorByTags(:659 BG 英雄分岔)/
GetNameWithPremiumType(:838 三表贯穿链)/GetSignatureActor(:910 stub)——
decomp 全分支转写（consumer-arch 批12 两源对账账随镜像体保留），返回
"名.prefab:GUID" 全 ref。

本役变化（consumer-v2 定案）：**帧链分派层废除**——SLOT_TO_FRAME 命名层与
spell_dk/ally_premium 手工业务分支删除（spell 与 spell_dk 八策略表行旧链逐字段
全等=纯冗余；DK 视觉差异走类色/符文 tag 组件通路，与游戏同构）。分发终点=
prefab 身份：resolve_prefab 产出 (prefab 名, 旧帧键, Card)——prefab=新真值，
旧帧键=过渡委托列（PREFAB_SPECS，scenes 域；内部化完成后消亡）。

tripwire 换座：开放位=scenes.PREFAB_SPECS 行成员（缺行 assert 响亮，引 decomp
分支锚）——游戏可路由任何 prefab 因其全验证，我方只开放有策略行的 prefab。
品质/premium 分派全走三活表（ GetNameWithPremiumType 贯穿链），金卡随从
Card_Hand_Ally_Premium 由表名自然分叉（不再手工分支）。

配方面：三表直取经 recipes.frames.actor_ref（背书=infra.dll_reflect 三活表
反射，与 decomp 逐槽相等）；SIGNATURE 腿 stub 同旧轨（NotImplementedError 响亮）。
消费须在 supply session 内（入口层独占纪律）。
"""

from __future__ import annotations

from eidolon.core.infra.card import Card, CardClass, CardType, GameTag, Premium, as_card_or_dbf
from eidolon.core.infra.errors import GameAssetMissing
from eidolon.core.recipes.frames import actor_ref
from eidolon.core.render._provenance import parallel  # noqa: F401 （族默认）

# ============================================================================
# decomp 硬编码字面量（表外常量，ActorNames.cs 各分支内联串）
# ============================================================================

CARD_HIDDEN = "Card_Hidden.prefab:1a94649d257bc284ca6e2962f634a8b9"
"""分派兜底（GetHandActor default :575、GetPlayActorByTags default :722、
GetZoneActor 警告返回 :509-510 同串）。"""

CARD_INVISIBLE = "Card_Invisible.prefab:579b3b9a80234754593f24582f9cb93b"
"""PLAY 区法术不可见帧（GetPlayActorByTags SPELL 支 :677；ZonePlay 无卡面本体）。"""

PLAY_ENCHANTMENT = "Card_Play_Enchantment.prefab:cc1eafed24951ee4c92ad007507b1b69"
"""附魔帧（GetPlayActorByTags ENCHANTMENT 支 :696）。"""

BACON_HERO = "Card_Play_Bacon_Hero.prefab:227eb40f91281fa429c48c8a730c982f"
"""酒馆英雄对局帧（GetPlayActorByTags HERO 支 :685/:689；our hero_play_bacon 链）。"""

BACON_GUIDE = "Card_Play_Bacon_Guide.prefab:6cf6c56b1ef6f4c4db7210533b95f4ac"
"""酒馆向导帧（GetPlayActorByTags HERO 支 :690，HeroType==4；未开帧链，仅名字面）。"""

# CardHero.HeroType 值域（CardHero.cs:CardHero.HeroType：UNKNOWN=0 VANILLA=1 HONORED=2
# BATTLEGROUNDS_HERO=3 BATTLEGROUNDS_GUIDE=4）——GetPlayActorByTags BG 分岔消费
_HERO_TYPE_BATTLEGROUNDS_HERO = 3
_HERO_TYPE_BATTLEGROUNDS_GUIDE = 4

# ============================================================================
# 分派表
# ============================================================================

_HAND_SLOT_BY_CARDTYPE = {
    # GetHandActor 表驱动体（ActorNames.cs:ActorNames.GetHandActor）全分支转写——名字分派层
    CardType.MINION: "HAND_MINION",                       # :550-551
    CardType.WEAPON: "HAND_WEAPON",                       # :552-553
    CardType.SPELL: "HAND_SPELL",                         # :554/:557
    CardType.BATTLEGROUND_QUEST_REWARD: "HAND_SPELL",     # :555
    CardType.BATTLEGROUND_SPELL: "HAND_SPELL",            # :556（42，TAG_CARDTYPE.cs:TAG_CARDTYPE.BATTLEGROUND_SPELL）
    CardType.HERO: "HAND_HERO",                           # :558-559
    CardType.HERO_POWER: "HISTORY_HERO_POWER",            # :560-561（10 勘误行）
    CardType.BATTLEGROUND_HERO_BUDDY: "HAND_MINION",      # :562-563
    CardType.LOCATION: "HAND_LOCATION",                   # :564-565（39 勘误行）
    CardType.BATTLEGROUND_ANOMALY: "BIG_CARD_BG_ANOMALY",     # :566-567
    CardType.BATTLEGROUND_TRINKET: "BIG_CARD_BG_TRINKET",     # :568-569
    CardType.PET: "COSMETIC_PET_PREVIEW",                 # :570-571
    CardType.GAME_MODE_BUTTON: "HAND_GAME_MODE_BUTTON",   # :572-573
}
"""名字分派层：GetHandActor 全分支（缺键→CARD_HIDDEN，:574-575）。"""


def _table_ref(quality: str, slot: str) -> str | None:
    """三活表软查：decomp TryGetValue 语义（:881/:897/:903）——recipes.frames.
    actor_ref 是 KeyError 响亮面（供给配方纪律），此处捕为 None 供贯穿链消费。

    软回退契约（Rework D 2026-11-08 定案）：捕 ``(KeyError, GameAssetMissing)``
    是 decomp TryGetValue 贯穿链的 Python 等价——变体槽位缺失（金/钻活表无该
    slot 行，supply.kits.actor_ref 按 §5.3 typed 化抛 ``GameAssetMissing``）=
    软回退（DIAMOND/GOLDEN→normal 品质链），非资产缺失错误，不上抛归 ENV 3；
    typed 边界留在 supply.kits.actor_ref 供直接消费方（render 贯穿链此处吃掉）。
    """
    try:
        return actor_ref(quality, slot)
    except (KeyError, GameAssetMissing):
        return None


def _tag(tags, tag_id: int) -> int:
    """GetTag 语义（EntityBase 查不到即 0）：tags=映射面（Card.tags 同构可直传）。"""
    return int(tags.get(int(tag_id), 0))


def _card_hero_type(dbf_id) -> int:
    """CARD_HERO.m_heroType 表查（GameUtils.GetHeroType 终点=CardHeroDbfRecord.
    HeroType，GameUtils.cs:GameUtils；infra card.is_bacon_hero 同表同语义）。
    dbf_id=None 或查无→0（UNKNOWN，decomp switch default 同象）。"""
    if dbf_id is None:
        return 0
    from eidolon.core.infra import dbf   # 惰性：防 import 环（card.py 同款）
    return dbf.default_dbf().card_hero.get(int(dbf_id), {}).get("m_heroType") or 0


# ============================================================================
# 名字分派层（ActorNames 六函数之四 + 签名 stub）
# ============================================================================

@parallel
def get_hand_actor(card_type: int, premium: int, card_id: str | None = None) -> str:
    """HAND 区 actor 名：GetHandActor 对位（ActorNames.cs:ActorNames.GetHandActor 表驱动体）。

    card_type=TAG_CARDTYPE 值；premium=TAG_PREMIUM 值（0 NORMAL/1 GOLDEN/
    2 DIAMOND/3 SIGNATURE）；card_id 引擎串 id 轴不入离线形（模块 docstring
    边界账）——仅 SIGNATURE 腿需要，现役 stub 下传 None 即纯表分派。
    返回 "名.prefab:GUID" 全 ref；未知卡型→CARD_HIDDEN（:574-575）。
    """
    slot = _HAND_SLOT_BY_CARDTYPE.get(int(card_type))
    if slot is None:
        return CARD_HIDDEN
    return get_name_with_premium_type(slot, premium, card_id)


@parallel
def get_hand_actor_by_tags(tags, premium: int, card_id: str | None = None) -> str:
    """HAND 区入口（tag 判式版）：GetHandActorByTags 对位（ActorNames.cs:ActorNames.GetHandActorByTags，
    Lettuce 优先）。tags=GAME_TAG 值映射（int 键；Card.tags 可直传）。

    判式链：IsLettuceMercenary（GetTag(LETTUCE_MERCENARY)>0，EntityBase.cs:EntityBase.IsLettuceMercenary）
    → IsLettuceEquipment（CARDTYPE==23 ∧ HasTag(LETTUCE_IS_EQUPIMENT)——decomp
    拼写即 EQUPIMENT，:474-480）→ IsLettuceAbility 分岔（召唤随从腿
    LETTUCE_ABILITY_SUMMONED_MINION，:485-499/:591-595）→ GetHandActor(cardtype)。
    """
    if _tag(tags, GameTag.LETTUCE_MERCENARY) > 0:
        return get_name_with_premium_type("HAND_MERCENARY", premium, card_id)
    if _tag(tags, GameTag.CARDTYPE) == int(CardType.LETTUCE_ABILITY):
        if _tag(tags, GameTag.LETTUCE_IS_EQUPIMENT):
            return get_name_with_premium_type("BIG_CARD_LETTUCE_EQUIPMENT", premium, card_id)
        if _tag(tags, GameTag.LETTUCE_ABILITY_SUMMONED_MINION):
            return get_name_with_premium_type("BIG_CARD_LETTUCE_ABILITY_MINION", premium, card_id)
        return get_name_with_premium_type("BIG_CARD_LETTUCE_ABILITY_SPELL", premium, card_id)
    return get_hand_actor(_tag(tags, GameTag.CARDTYPE), premium, card_id)


@parallel
def get_play_actor_by_tags(tags, premium: int, dbf_id=None) -> str:
    """PLAY 区 actor 名：GetPlayActorByTags 对位（ActorNames.cs:ActorNames.GetPlayActorByTags）。

    BG 英雄分岔（:682-692）：HasTag(BACON_IS_KEL_THUZAD=1423)∨HasTag(
    BACON_PLAYER_RESULTS_HERO_OVERRIDE=1649)→BACON_HERO；否则 CARD_HERO 表
    HeroType==3→BACON_HERO、==4→BACON_GUIDE、余→PLAY_HERO（dbf_id 缺省/查无
    →非 BG 同 PLAY_HERO 落）。player corner 腿不接线（模块 docstring 边界账）。
    tags=GAME_TAG 值映射；dbf_id=CARD_HERO 表查键（数字 id）。
    """
    ct = _tag(tags, GameTag.CARDTYPE)
    if ct == int(CardType.MINION):
        if _tag(tags, GameTag.LETTUCE_MERCENARY) > 0:            # :669-672
            return get_name_with_premium_type("PLAY_MERCENARY", premium)
        return get_name_with_premium_type("PLAY_MINION", premium)   # :673
    if ct == int(CardType.WEAPON):
        return get_name_with_premium_type("PLAY_WEAPON", premium)   # :674-675
    if ct == int(CardType.SPELL):
        return CARD_INVISIBLE                                       # :676-677
    if ct == int(CardType.BATTLEGROUND_SPELL):
        return get_name_with_premium_type("PLAY_BATTLEGROUND_SPELL", premium)   # :678-679
    if ct == int(CardType.BATTLEGROUND_TRINKET):
        return get_name_with_premium_type("PLAY_BATTLEGROUND_TRINKET", premium)  # :680-681
    if ct == int(CardType.HERO):
        if _tag(tags, GameTag.BACON_IS_KEL_THUZAD) or \
                _tag(tags, GameTag.BACON_PLAYER_RESULTS_HERO_OVERRIDE):
            return BACON_HERO                                       # :683-685
        hero_type = _card_hero_type(dbf_id)
        if hero_type == _HERO_TYPE_BATTLEGROUNDS_HERO:
            return BACON_HERO                                       # :689
        if hero_type == _HERO_TYPE_BATTLEGROUNDS_GUIDE:
            return BACON_GUIDE                                      # :690
        return get_name_with_premium_type("PLAY_HERO", premium)     # :691
    if ct == int(CardType.HERO_POWER):
        return get_name_with_premium_type("PLAY_HERO_POWER", premium)   # :693-694（cardId=null 同）
    if ct == int(CardType.ENCHANTMENT):
        return PLAY_ENCHANTMENT                                     # :695-696
    if ct == int(CardType.GAME_MODE_BUTTON):
        return get_name_with_premium_type("PLAY_GAME_MODE_BUTTON", premium)   # :697-698
    if ct == int(CardType.MOVE_MINION_HOVER_TARGET):
        return get_name_with_premium_type("PLAY_MOVE_MINION_HOVER_TARGET", premium)  # :699-700
    if ct == int(CardType.BATTLEGROUND_HERO_BUDDY):
        return get_name_with_premium_type("PLAY_BATTLEGROUND_HERO_BUDDY", premium)   # :701-702
    if ct == int(CardType.BATTLEGROUND_ANOMALY):
        return get_name_with_premium_type("PLAY_BATTLEGROUND_ANOMALY", premium)      # :703-704
    if ct == int(CardType.BATTLEGROUND_QUEST_REWARD):
        # :705-706
        return get_name_with_premium_type("PLAY_BATTLEGROUND_QUEST_REWARD", premium)
    if ct == int(CardType.LETTUCE_ABILITY):
        if _tag(tags, GameTag.LETTUCE_IS_EQUPIMENT):
            return get_name_with_premium_type("PLAY_LETTUCE_EQUIPMENT", premium)     # :708-710
        if _tag(tags, GameTag.LETTUCE_ABILITY_SUMMONED_MINION):
            return get_name_with_premium_type("PLAY_LETTUCE_ABILITY_MINION", premium)  # :712-714
        return get_name_with_premium_type("PLAY_LETTUCE_ABILITY_SPELL", premium)     # :716
    if ct == int(CardType.LOCATION):
        return get_name_with_premium_type("PLAY_LOCATION", premium)     # :717-718
    if ct == int(CardType.PET):
        return get_name_with_premium_type("COSMETIC_PET_GAMEPLAY", premium)  # :719-720
    return CARD_HIDDEN                                                  # :721-722


@parallel
def get_name_with_premium_type(actor_slot: str, premium: int,
                               card_id: str | None = None) -> str | None:
    """品质分派：GetNameWithPremiumType 对位（ActorNames.cs:ActorNames.GetNameWithPremiumType 三表贯穿链）。

    actor_slot=ACTOR_ASSET 槽位名（表键，非基础 prefab 名——批11b stub 注
    「base=基础 prefab 名」系形态误推，已修正）；premium=TAG_PREMIUM 值。
    贯穿链（:878-907 goto 形态）：DIAMOND 钻表未中→SIGNATURE→GOLDEN；SIGNATURE
    （带 card_id）→签名帧未中→GOLDEN；GOLDEN 金表未中→break；终底=普通表，
    查无→None（decomp 返 null 同象）。corner-replacement/game-mode-button 腿
    （:841-877）不接线（模块 docstring 边界账）。SIGNATURE 腿现役 stub——带
    card_id 时 NotImplementedError 响亮（签名立户声明）。
    """
    premium = int(premium)
    if premium == int(Premium.DIAMOND):                    # :880-885
        ref = _table_ref("diamond", actor_slot)
        if ref is not None:
            return ref
        premium = int(Premium.SIGNATURE)                   # goto SIGNATURE（:885）
    if premium == int(Premium.SIGNATURE):                  # :886-895
        if card_id is not None:
            signature = get_signature_actor(card_id, actor_slot)
            if signature:
                return signature
        premium = int(Premium.GOLDEN)                      # 贯穿（:895）
    if premium == int(Premium.GOLDEN):                     # :896-901
        ref = _table_ref("premium", actor_slot)
        if ref is not None:
            return ref
        # break → 终底
    return _table_ref("normal", actor_slot)                # :903-907（查无→None）


@parallel
def get_signature_actor(card_id: str, actor_slot: str) -> str:
    """SIGNATURE 特化：GetSignatureActor 对位（ActorNames.cs:ActorNames.GetSignatureActor，私有双参
    形——card_id 经 SignatureFrames（cardId→frame id）→按 actor_slot 族落
    SignatureHand/SignaturePlay（Initialize :973-1010 = GameDbf.SignatureFrame
    DBF 水合）。

    **批24 立户判定=留+升格注**：GameDbf.SignatureFrame DBF 解析=新配方（属
    后续语料外批次；触发条件=SIGNATURE 品质卡进入渲染集——门语料 premium 全
    NORMAL（duipai_s2 D 断言 pin），无对拍面故不可立配方）——函数体
    NotImplementedError 响亮占位（签名立户，批12；批24 判定维持）。
    """
    raise NotImplementedError(
        "SIGNATURE 走 GameDbf.SignatureFrame DBF——解析新配方随语料外批次兑现"
        "（签名立户，批12；批24 判定=留，触发条件=SIGNATURE 品质卡入渲染集）")




# ============================================================================
# 分发入口（consumer-v2：prefab 身份；帧链分派层已废除）
# ============================================================================

@parallel
def resolve_prefab(card_or_dbf, zone: str = "HAND") -> tuple[str, Card]:
    """组装入口：镜像查表产出 prefab 身份（游戏分发语义的直接转写）。

    card_or_dbf=Card 门面实例（contract C 判据 1 四入口收 Card，2026-11-06；
    传 Card 时本函数零 from_dbf——对象单流全链）|数字 dbf id（旧路径零变化，
    内部照旧 from_dbf 单源装载）。HAND 区=GetHandActorByTags（Lettuce 判式链→
    GetHandActor 表驱动体，全分支）；PLAY 区=GetPlayActorByTags（BG 英雄分岔含
    CARD_HERO HeroType 表查）。返回 (prefab 名, Card)：prefab=ref 去
    ".prefab:GUID" 后缀（游戏资产名）。本函数零业务分支，DK/金卡差异全由表名与
    tag 组件承载（与游戏同构）。

    tripwire=PREFAB_SPECS 行成员（缺行 assert 响亮）：未开放 prefab（PLAY 区
    随从/武器/ENGINE 串 id 轴等离线未验证链）响亮拒绝——开放纪律自旧轨换座，
    粒度=per-prefab（更细于旧 per-chain）。

    族账锚=ActorNames.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    from eidolon.core.render.scenes.specs import open_prefab
    card, dbf_id = as_card_or_dbf(card_or_dbf)
    if card is None:
        card = Card.from_dbf(int(dbf_id))
    if zone == "PLAY":
        ref = get_play_actor_by_tags(card.tags, int(card.premium), int(dbf_id))
    elif zone == "HAND":
        ref = get_hand_actor_by_tags(card.tags, int(card.premium))
    else:
        raise AssertionError(f"未知 zone：{zone!r}（HAND/PLAY）")
    assert ref, f"镜像查表返 None（dbf={dbf_id} zone={zone}）——三表查无且非 CARD_HIDDEN"
    prefab = ref.split(".prefab:", 1)[0]
    open_prefab(prefab)
    return prefab, card


@parallel
def frame_family(dbf_id, zone: str = "HAND") -> str | None:
    """帧族查询（family-routing-debt 2026-10-21 沿袭）：resolve_prefab 非抛封装
    ——镜像可路由返 prefab 名，不可路由（PREFAB_SPECS 缺行/未开放卡型/三表查无/
    session 闸）→ 显式 None。

    两态分治（residual-silent-fallbacks 2026-11-05 收口——旧形
    `except (AssertionError, KeyError): return None` 把「未知 dbf」与「不可路由」
    混归 None，退役）：
      * **未知输入=响亮**：dbf CARD 表查无（KeyError）与未知 zone 在捕获外
        显式抛——数据面未知禁吞（fail-closed）；
      * **合法但不可路由=显式记账+显式返回**：捕获内只剩 AssertionError——
        开放位 tripwire（resolve_prefab.open_prefab）/镜像三表查无（assert ref）/
        session 闸（供给访问越层），语义=帧族不可判，非「未知卡」。

    **须在 supply session 内**（resolve_prefab→Card.from_dbf 触供给 @item）：入口层
    （gate/report）负责开；session 外调用被供给闸拦成 AssertionError→None（语义=
    帧族不可判，非"未知卡"）——render/消费层不得代开 session。

    语料展示/聚合面（报告 family 列、家族榜、--family 过滤）的唯一帧族推导入口
    （consumer-v2 起 family=prefab 身份；manifest 无 family 列，消费面禁散写
    CARDTYPE 判式）。

    族账锚=ActorNames.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    if zone not in ("HAND", "PLAY"):
        raise AssertionError(f"未知 zone：{zone!r}（HAND/PLAY）——frame_family "
                             "不吞调用方错误（residual-silent-fallbacks 2026-11-05）")
    try:
        Card.from_dbf(int(dbf_id))
    except KeyError:
        raise KeyError(
            f"未知 dbf id {dbf_id}——dbf CARD 表查无：帧族判定 fail-closed，禁与"
            "「不可路由」混归 None（residual-silent-fallbacks 2026-11-05 收口）") from None
    try:
        prefab, _card = resolve_prefab(dbf_id, zone)
    except AssertionError:
        return None   # 不可路由（开放位 tripwire/三表查无/session 闸）——显式返回
    return prefab
