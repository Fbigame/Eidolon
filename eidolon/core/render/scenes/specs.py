"""specs — PREFAB_SPECS：prefab 全集清单（kit 族路由+tripwire）。

prefab 名=游戏资产名（ActorNames 三活表值，2026-10-29 活表探针逐槽实测：
HAND_SPELL=Card_Hand_Ability / HAND_MINION=Card_Hand_Ally / 金表分叉
*_Premium / HISTORY_HERO_POWER=History_HeroPower / PLAY_HERO=Card_Play_Hero
等——decomp 硬编码表与 dll_reflect 反射逐槽相等，背书=actor_names 头注）。

行结构：prefab 名 → dict(kit=kit 族参数（FRAME_SPECS/kit() 命名空间：ability/
bacon 特源 + 六族 kit(key) 键）)。**开放位纪律（tripwire）**：游戏可路由任何
prefab（其全验证），我方只开放本表行——actor_names.resolve_prefab 查无行即
assert 响亮；新帧型开放=加行（须 decomp 锚+帧链验证），与游戏的扩表动作同构。
scenes._KIT_SOURCE 自本表派生（kit 路由单一真值）。

"我们缺什么"=游戏 prefab 全集（ActorNames 表+decomp 分支导出）减本表行，
机械对账可导（对账面=tools 侧，不进本包）。
"""
from __future__ import annotations

from eidolon.core.render._provenance import invented

PREFAB_SPECS: dict[str, dict] = {
    # 法术（Card_Hand_Ability）：DK 法术同 prefab（游戏 GetHandActor 无 CLASS
    # 分支，ActorNames.cs:554-557）——spell_dk 键在此消亡，符文/类色差异归
    # S4/S10 tag 组件（UpdateCardColor :6443/UpdateCardRuneBannerComponent :6188）。
    "Card_Hand_Ability": dict(kit="ability"),
    # 随从（Card_Hand_Ally）+金卡族（金表 HAND_MINION 直名分叉）
    "Card_Hand_Ally": dict(kit="ally"),
    "Card_Hand_Ally_Premium": dict(kit="ally_premium"),
    # 武器/英雄手牌（FRAME_SPECS 键名继承）
    "Card_Hand_Weapon": dict(kit="weapon"),
    "Card_Hand_Hero": dict(kit="hero_hand"),
    "Card_Hand_Weapon_Premium": dict(kit="weapon"),
    "Card_Hand_Hero_Premium": dict(kit="hero_hand"),
    # 英雄技能（History_HeroPower）
    "History_HeroPower": dict(kit="heropower"),
    "History_HeroPower_Premium": dict(kit="heropower"),
    # 地标（Card_Hand_Location）
    "Card_Hand_Location": dict(kit="location"),
    "Card_Hand_Location_Premium": dict(kit="location"),
    # BG 大卡两型（bg-ct40-43-44-routing 2026-10-24；premium 表无行=普通表贯穿同象）
    "Card_Hand_BG_Trinket": dict(kit="trinket"),
    "Card_Hand_BG_Anomaly": dict(kit="anomaly"),
    # 英雄打出两链（PLAY 区仅 HERO 开放，旧轨同；BG 英雄对局帧=CARD_HERO 表查）
    "Card_Play_Hero": dict(kit="hero_play"),
    "Card_Play_Bacon_Hero": dict(kit="bacon"),
    # 金卡法术（capture-determinism 2026-10-30，98918 首例）：金框美术与普通法术帧
    # 全异（金框/金名牌/金学派板/金描述框，真值图实证）——独立 premium kit
    # （ability_kit("premium")，s_premiumActorAssets[HAND_SPELL] 活表锚）。
    # 旧「kit=ability 帧键不分支」行为在语料零 premium 时代未真验，作废。
    "Card_Hand_Ability_Premium": dict(kit="ability_premium"),
}


@invented(reason="开放位 tripwire 宿位：游戏可路由任何 prefab（其全验证），我方"
                 "只开放有策略行的 prefab——缺行 assert 响亮，防统一入口静默路由进"
                 "未验证链（旧轨 tripwire 纪律的 per-prefab 换座）",
          counterpart="无——旧 CARDTYPE_TO_SLOT 开放位表的接替")
def open_prefab(prefab: str) -> dict:
    """prefab 行取用（tripwire：缺行 assert 响亮）。"""
    row = PREFAB_SPECS.get(prefab)
    assert row is not None, (
        f"prefab {prefab!r} 无 PREFAB_SPECS 行——未开放帧链（开放=加行，须 decomp 锚+"
        f"帧链验证；已开放={sorted(PREFAB_SPECS)}）")
    return row


__all__ = ["PREFAB_SPECS", "open_prefab"]
