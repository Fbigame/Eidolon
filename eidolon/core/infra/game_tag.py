"""game_tag — 渲染消费词汇表（白名单手维护 × 值活取）。

定性（上游裁决）：**非引擎全量镜像**——成员集只收
渲染链实际消费的 tag，要多少搬多少；未入册的 tag 在 dbf 数据里保持裸 int（_TagDict
int 键 + __missing__=0 承载 GetTag 缺省语义，与枚举解耦），渲染代码不读即不存在。
**值**一律活取 `dll_reflect.enum_table("GAME_TAG")`（上游收口：原手抄值与活表的
逐值相等无人看护——改活取后漂移在构造上不可能；切换前已一次性对拍全等）。

响亮面：白名单成员不在活 GAME_TAG 枚举 → 导入期 ImportError 点名成员（客户端降级/
成员改名=先核 Assembly-CSharp 再动白名单）。活表新增成员**不**响——成员集=我方
消费面，不随版本全量再生（新 tag 走 _dec 降级裸 int 的既有语义，消费扩容时才入册）。

维护纪律：新成员入册只需名字+消费点注释（值由活表供货后不再手抄，decomp 值锚随
手抄值退役）。导入即装载 coreclr（首读 ~0.9 s，zone_when 先例；渲染链本来就吃
dll_reflect 活表，不新增依赖类别）。
"""
from __future__ import annotations

from enum import IntEnum

from eidolon.core.infra.dll_reflect import enum_table

_LIVE_GAME_TAG = enum_table("GAME_TAG")
"""活 GAME_TAG 名册（name → id；导入期装载=白名单成员的唯一值源）。"""


def _live(name: str) -> int:
    """白名单成员取活值（活表缺名 → 响亮，消息点名成员与名册规模）。"""
    try:
        return _LIVE_GAME_TAG[name]
    except KeyError:
        raise ImportError(
            f"GameTag.{name} 不在活 GAME_TAG 枚举（{len(_LIVE_GAME_TAG)} 成员）——"
            "白名单与活枚举漂移：先核 Assembly-CSharp 版本，再动本白名单") from None


class GameTag(IntEnum):
    """渲染消费 GAME_TAG 子集（成员集=手维护白名单；值=活表 `_live` 逐名供货）。"""

    TAG_SCRIPT_DATA_NUM_1 = _live("TAG_SCRIPT_DATA_NUM_1")  # infra/text_shim.py（builder 40/45 Python 静态路由的 TryFormat 槽 1，BattlegroundsTavernSpellCardTextBuilder.BuildCardTextInHand(EntityDef)）
    TAG_SCRIPT_DATA_NUM_2 = _live("TAG_SCRIPT_DATA_NUM_2")  # infra/text_shim.py（同上 TryFormat 槽 2，40/45 共用）
    PREMIUM = _live("PREMIUM")  # hero_render, hero_render_bacon, hp_render, infra/card.py, location_render, scene_compiler, scene_compiler_ally, wf_render
    TRIGGER_VISUAL = _live("TRIGGER_VISUAL")  # infra/card.py（HasTriggerVisual + 费用文本 CardButton 腿）、render.game.actor.gems（cost_text_semantics）
    HEALTH = _live("HEALTH")  # hero_render, hero_render_bacon, location_render, scene_compiler_ally, wf_render
    ATK = _live("ATK")  # hero_render, hero_render_bacon, location_render, scene_compiler_ally, wf_render
    COST = _live("COST")  # hero_render, hero_render_bacon, hp_render, infra/card.py, location_render, scene_compiler, scene_compiler_ally, wf_render
    ELITE = _live("ELITE")  # hero_render, hero_render_bacon, hp_render, infra/card.py, location_render, scene_compiler, scene_compiler_ally, wf_render
    CARD_SET = _live("CARD_SET")  # scene_compiler
    CLASS = _live("CLASS")  # hero_render, hero_render_bacon, hp_render, infra/card.py, location_render, render_card, scene_compiler, scene_compiler_ally, wf_render
    CARDRACE = _live("CARDRACE")  # infra/card.py, scene_compiler_ally
    FACTION = _live("FACTION")  # hp_render
    CARDTYPE = _live("CARDTYPE")  # hero_render, hero_render_bacon, hp_render, infra/card.py, location_render, scene_compiler, scene_compiler_ally, wf_render
    RARITY = _live("RARITY")  # hero_render, hero_render_bacon, hp_render, infra/card.py, location_render, scene_compiler, scene_compiler_ally, wf_render
    ARMOR = _live("ARMOR")  # hero_render, hero_render_bacon
    HIDE_STATS = _live("HIDE_STATS")  # location_render, scene_compiler_ally, ur_frames, wf_render
    QUEST = _live("QUEST")  # scene_compiler
    QUEST_PROGRESS_TOTAL = _live("QUEST_PROGRESS_TOTAL")  # infra/text_shim.py（builder 32 BG_QUEST Python 静态路由 TryFormat 槽 1 + 种族名 BG/普通分岔，BGQuestCardTextBuilder.BuildText(Entity)）
    MULTIPLE_CLASSES = _live("MULTIPLE_CLASSES")  # infra/card.py, ur_frames
    GRIMY_GOONS = _live("GRIMY_GOONS")  # infra/card.py
    JADE_LOTUS = _live("JADE_LOTUS")  # infra/card.py
    KABAL = _live("KABAL")  # infra/card.py
    HIDE_HEALTH = _live("HIDE_HEALTH")  # location_render, scene_compiler_ally, wf_render
    HIDE_ATTACK = _live("HIDE_ATTACK")  # scene_compiler_ally, wf_render
    HIDE_COST = _live("HIDE_COST")  # hero_render, ur_frames
    OVERRIDECARDTEXTBUILDER = _live("OVERRIDECARDTEXTBUILDER")  # infra/card.py（Card.text_builder_type 有效型覆盖，EntityDef.cs:EntityDef.GetCardTextBuilder 派发）
    QUEST_REWARD_DATABASE_ID = _live("QUEST_REWARD_DATABASE_ID")  # infra/text_shim.py（builder 32 BG_QUEST Python 静态路由：奖励 DBID→卡名 TryFormat 槽 2，BGQuestCardTextBuilder.BuildText(Entity)）
    HIDE_WATERMARK = _live("HIDE_WATERMARK")  # ta_watermark
    BACON_IS_KEL_THUZAD = _live("BACON_IS_KEL_THUZAD")  # render.game.actor_names（GetPlayActorByTags BG 英雄分岔，ActorNames.cs:ActorNames.GetPlayActorByTags）
    TECH_LEVEL = _live("TECH_LEVEL")  # infra/card.py
    DORMANT = _live("DORMANT")  # ur_frames
    SPELL_SCHOOL = _live("SPELL_SCHOOL")  # infra/card.py, scene_compiler, scene_compiler_ally
    BACON_PLAYER_RESULTS_HERO_OVERRIDE = _live("BACON_PLAYER_RESULTS_HERO_OVERRIDE")  # render.game.actor_names（GetPlayActorByTags BG 英雄分岔，ActorNames.cs:ActorNames.GetPlayActorByTags）
    LETTUCE_MERCENARY = _live("LETTUCE_MERCENARY")  # render.game.actor_names（GetHand/PlayActorByTags 佣兵判式，EntityBase.cs:EntityBase.IsLettuceMercenary）
    LETTUCE_ABILITY_SUMMONED_MINION = _live("LETTUCE_ABILITY_SUMMONED_MINION")  # render.game.actor_names（Lettuce 技能召唤随从腿，EntityBase.cs:EntityBase.IsLettuceAbilityMinionSummoning）
    TRADEABLE = _live("TRADEABLE")  # infra/card.py, ur_frames
    LETTUCE_IS_EQUPIMENT = _live("LETTUCE_IS_EQUPIMENT")  # render.game.actor_names（Lettuce 装备判式，EntityBase.cs:EntityBase.IsLettuceEquipment；活表拼写即 EQUPIMENT）
    COST_BLOOD = _live("COST_BLOOD")  # infra/card.py, ur_frames
    COST_FROST = _live("COST_FROST")  # infra/card.py, ur_frames
    COST_UNHOLY = _live("COST_UNHOLY")  # infra/card.py, ur_frames
    FORGE = _live("FORGE")  # infra/card.py
    HAS_ACTIVATE_POWER = _live("HAS_ACTIVATE_POWER")  # infra/card.py（费用文本 CardButton 腿的 BG 分岔）、render.game.actor.gems（cost_text_semantics）
    TAG_SCRIPT_DATA_NUM_3 = _live("TAG_SCRIPT_DATA_NUM_3")  # infra/text_shim.py（builder 40 TryFormat 槽 3）
    TAG_SCRIPT_DATA_NUM_4 = _live("TAG_SCRIPT_DATA_NUM_4")  # infra/text_shim.py（builder 40 TryFormat 槽 4）
    ZERG = _live("ZERG")  # infra/card.py
    TERRAN = _live("TERRAN")  # infra/card.py
    PROTOSS = _live("PROTOSS")  # infra/card.py
    HIDE_HEALTH_NUMBER = _live("HIDE_HEALTH_NUMBER")  # location_render, scene_compiler_ally, wf_render
    HIDE_ATTACK_NUMBER = _live("HIDE_ATTACK_NUMBER")  # scene_compiler_ally, wf_render
    PREPARE = _live("PREPARE")  # infra/card.py
    BACON_TIMEWARPED = _live("BACON_TIMEWARPED")  # infra/card.py
    # —— BACON_SUBSET_* 13 对（饰品族学区布尔 tag；GetRacesForTrinket 消费，
    #    infra/card.py Card.races trinket 分支 2026-10-24 入册；值域=活表供货，
    #    s_raceSubsetToRaceTable 键序=EntityBase.cs:25-79 初始化器序）——
    BACON_SUBSET_DRAGON = _live("BACON_SUBSET_DRAGON")  # infra/card.py
    BACON_SUBSET_MURLOC = _live("BACON_SUBSET_MURLOC")  # infra/card.py
    BACON_SUBSET_DEMON = _live("BACON_SUBSET_DEMON")  # infra/card.py
    BACON_SUBSET_BEAST = _live("BACON_SUBSET_BEAST")  # infra/card.py
    BACON_SUBSET_MECH = _live("BACON_SUBSET_MECH")  # infra/card.py
    BACON_SUBSET_PIRATE = _live("BACON_SUBSET_PIRATE")  # infra/card.py
    BACON_SUBSET_ELEMENTALS = _live("BACON_SUBSET_ELEMENTALS")  # infra/card.py
    BACON_SUBSET_QUILLBOAR = _live("BACON_SUBSET_QUILLBOAR")  # infra/card.py
    BACON_SUBSET_NAGA = _live("BACON_SUBSET_NAGA")  # infra/card.py
    BACON_SUBSET_UNDEAD = _live("BACON_SUBSET_UNDEAD")  # infra/card.py
    BACON_SUBSET_TOTEM = _live("BACON_SUBSET_TOTEM")  # infra/card.py
    BACON_SUBSET_ALL = _live("BACON_SUBSET_ALL")  # infra/card.py
    BACON_SUBSET_ABERRATION = _live("BACON_SUBSET_ABERRATION")  # infra/card.py
