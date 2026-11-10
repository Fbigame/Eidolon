"""card_color_switcher — CardColorSwitcher 全族（段 S4 类色切换）。

游戏锚：CardColorSwitcher.GetCardColorTypeForClasses（CardColorSwitcher.cs:CardColorSwitcher.GetCardColorTypeForClasses
——null/空→GENERIC/1 类单色/2 类 DUALCLASS(12-22)/≥3 类 GENERIC(0)，:139-143）·
GetColorTypeForDualClass（:151-169，DREAM(11)→HUNTER_DUALCLASS(15)、default→
GENERIC）· GetColorTypeForClass（:171-189——TAG_CLASS→ColorType 枚举，枚举值=
序列化列表下标；DREAM→TYPE_HUNTER(4)、default→GENERIC）· GetTexture
（:226-272——按 TAG_CARDTYPE 选 12 族序列化列表，list.Count<=下标→null；INVALID/
BATTLEGROUND_QUEST_REWARD 直返 null :259-261；未知卡型 LogError+minion 兜底
:262-265）· 单例 Awake（:105-117 s_instance=this；链根=HearthstoneApplication.cs:HearthstoneApplication.QueueStartupJobs
内联 "CardColorSwitcher.prefab:b30c…"）· 消费链 Actor.UpdateCardColor（Actor.cs:Actor.UpdateCardColor
——单类腿 :6457-6462；IsMultiClass 覆写块 :6465-6477 GetCardColorTypeForClasses(
GetClasses())，IsGeneric 清色改 GetColorTypeForClass(GetClassMatchingHero())
:6469-6474）· Actor.SetMaterialWithTexture（:6729-6787 写点全集——cardMesh
[m_cardFrontMatIdx]._MainTex；SPELL∥BATTLEGROUND_SPELL∥(WEAPON∧单色 DK) 再写
portraitMesh[m_portraitFrameMatIdx] :6767；LOCATION No_Gem 尾段 :6782-6786）·
SetMaterialNormal 路由（:6709-6725——HERO_POWER/GAME_MODE_BUTTON/PET break 无
类色写点）· UpdateMulticlassRibbon（:6135-6145 SetActive(GetClasses().Count>2)）·
GetClasses（EntityBase.cs:EntityBase.GetClasses 掩码位升序解码）/IsMultiClass（:1131-1135
Count>1）/CardColorType（CardColorType.cs:CardColorType，colors 列表+IsGeneric）。

我方对位：class_color_pick（old_frames/scene_compiler.py:157——GetClasses[0]
判据，缎带同源 Actor.cs:Actor.UpdateMulticlassRibbon）· compile_plan 类色段（sc:263-280+四编译器
TEXTURE_FAMILY_BY_CARDTYPE——plan.class_color 全账 atlas_ref/img/apply）·
class_color_canonical（旧链 components/class_color.py:30——写点全集收敛，
**S11 组装段**）· multiclass 三支路（旧链 components/multiclass.py
:75/:135/:266——双职业 composite/GENERIC 框/右缘缎带）。

配方面：族表=recipes.color.probe（链根 ref 直 resolve+MonoBehaviour 直读，12 族
全量）；图集像素=recipes.color.atlas(family, ct)（消费方自取，本段只出 ref）。

批13 实现账（2026-10-14，S4 生长；两源=decomp 转写×旧实现还原，冲突以 decomp 为准）：

纪律面前置——本模块函数族经 recipes.color.probe 触供给配方（@item），
**消费须在 supply session 内**（入口层独占纪律，批12 actor_names 同款；
未来门驱动循环开 session 调本段，段内不开）。

签名修正清单（批11b 立壳形态推定→实现修正，批12 先例同权）：
  * get_card_color_type_for_classes 返回 `int`→`list[int]`——decomp 返回
    CardColorType 结构体（colors 列表，CardColorType.cs:CardColorType），写点消费 colors
    全集（_MainTex=colors[0]/_SecondTex=colors[1]）非单值；入参 None 腿=
    decomp classes==null（:125-129）同象。
  * get_texture 入参 `(family, color_type)`→`(card_type, color_type)`——
    decomp GetTexture(TAG_CARDTYPE, ColorType)（:226）的族选择=函数体 switch
    非入参；返回值=AssetReference 串（probe 表项）非图集本体（stub docstring
    「返回图集」系误推）。
新增函数（decomp 公共面立壳缺行）：get_color_type_for_dual_class（:151-169）；
我方表化/产物面（职责切分=判定+选族+结构化输出）：family_for_card_type、
class_color_segment（UpdateCardColor 离线形）、multiclass_segments（三支路
判定/引用核）。

decomp 分支的离线边界（记录的缺口，非静默丢弃）——
  * UpdateCardColor Lettuce caster 腿（:6420-6434，ColorType=23+premiumType——
    佣兵品阶轴）与 LETTUCE_ABILITY 腿（:6435-6452，ROLE 分岔）与 BG trinket
    side 腿（:6453-6456，FRIENDLY/OPPONENT=Player.Side 对局态）：门语料零命中
    （对拍 F grep 断言），不接线；缺省腿=GetColorTypeForClass 直落。
  * ≥3 类 hero-matching 腿（:6469-6474 GetClassMatchingHero :6346-6366——
    对局英雄/收藏管理器/竞技场类链）：对局态真值不入离线形（走查档 §0.4.6
    同款），离线 GetClassMatchingHero=INVALID→GetColorTypeForClass(INVALID)
    =GENERIC(0)，colors 原样 [0]——与旧 compile_multiclass_generic_color 直落
    GENERIC 同象（multiclass-neutral-frame 4e0382c 后实证），偏差=零行为记账。
  * GetClassColor（:6567 tint）/SetMaterialPremium（:6685 金卡缎带着色）：
    premium 轴写点，S11 面（语料全 NORMAL 零命中）。

与旧实现的两源对账（冲突以 decomp 为准，选型记账）——
  * 族映射不复制旧 FRAME_FAMILY_FOR_KEY/TEXTURE_FAMILY_BY_CARDTYPE：旧=按
    编译器分裂四表+hero 硬编码+sc BG 判式（frame_key 轴）；新表=decomp
    GetTexture switch 统一形（card_type 轴，CARDTYPE_TO_FAMILY 本模块自带），
    frame_key→族映射留 S11 新 registry（届时自本表同源派生）。逐卡两轴一致性
    由段级对拍 C 全量验证。
  * DUALCLASS 映射两源一致（旧 multiclass.DUAL_FOR_CLASS=本模块
    get_color_type_for_dual_class 同值 12-22+DREAM→15）；单类映射两源一致
    （旧 sc.COLOR_TYPE_FOR_CLASS_ENUM=decomp switch 同值，缺省 GENERIC）。
  * _CLASS_DISPLAY 显示串=旧 sc:131-137 同源复制（s_classNames 词汇；新包禁
    import 旧包——常量小、来源单一，出处随注）。批24 真值源查证=不可换轨留手抄
    （真值链 GameStrings.s_classNames→GLOBAL_CLASS_* 键→本地化串；enUS 词汇不在
    供给、zhCN 值异——判定与锚注见表处，12/15 键对应 drift probe 机制化互证）。

批24 值域机制化账（2026-10-15，零行为重构；2026-11-05 部分被 A 批收口取代）——
  * ColorType 枚举序机制化：本模块 ColorType IntEnum=decomp 直读立典
    （枚举嵌于 CardColorSwitcher.cs:CardColorSwitcher.ColorType，45 值原文序=序列化列表下标；
    CardColorType.cs 本体=colors 结构体+IsGeneric（:3-14），无枚举——HANDOFF
    「CardColorType.cs 直读」指认的枚举序正典在此）。
    【2026-11-05 收口】值域活表化（见下批账），decomp 原文直读双锚随表退役。
  * 值域裸 int → 枚举对枚举引用（批24 历史账）：单/双职业两映射表值域改
    ColorType 成员引用——两表已随 2026-11-05 收口退役（活 Invoke 取代，见下）。

class-axis-live-tables 收口账（2026-11-05，pythonnet-tables A 批；零行为重构）——
  * ColorType 值域活表化：45 值改 `enum_table("CardColorSwitcher+ColorType")`
    逐名供货（缺名导入即响、活表多名断言响；切换前一次性对拍 45 值全等）——
    decomp 手抄值退役，枚举序=活枚举序=序列化列表下标（构造上自洽）。
  * 单/双职业色型槽位=活 Invoke `CardColorSwitcher.GetColorTypeForClass/
    GetColorTypeForDualClass`（宿主直调，零平行代码；进程 memo）——
    旧单/双职业两手抄映射表退役。缺映射必红：
    非 default-leg 成员（INVALID/NEUTRAL/WHIZBANG=引擎 default 臂语义成员，
    见 _DEFAULT_LEG_CLASSES 成员注）活槽位为 GENERIC(0)=新职业无臂，装载即断言红
    （drift_probe E 面同判互证）。未知职业（CardClass 镜像外值）必抛 KeyError，
    不落 TYPE_GENERIC（旧 .get(..., TYPE_GENERIC) 静默回落退役）。
  * 类色 RGB 活读（Actor.cs 类色常量三族）：Actor..ctor IL 直读
    （ldc.r4×3+newobj Color+stfld 机械面）+ GetClassColor/GetDualClassColor/
    GetLocationClassColor switch 臂 IL 直读——旧类色/双职业缺省两手抄常量退役，
    ct−11 反查算术退役；lazy+进程 memo+臂数/值域/default 形状断言。
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from eidolon.core.infra.card import Card, CardClass, CardType
from eidolon.core.infra.dll_reflect import enum_table
from eidolon.core.recipes.color import probe
from eidolon.core.render._provenance import parallel  # noqa: F401 （族默认）

# ============================================================================
# 活表值域（枚举值=序列化列表下标，CardColorSwitcher.cs:CardColorSwitcher.ColorType；
# 2026-11-05 class-axis 收口：值=活表供货，decomp 手抄退役）
# ============================================================================

_COLOR_TYPE_LIVE = enum_table("CardColorSwitcher+ColorType")


def _ctv(name: str) -> int:
    """活枚举取值（缺名=成员定义行即响，ImportError 点名——值域镜像漂移）。"""
    try:
        return _COLOR_TYPE_LIVE[name]
    except KeyError:
        raise ImportError(
            f"CardColorSwitcher+ColorType.{name} 不在活枚举（{len(_COLOR_TYPE_LIVE)} 成员）"
            "——色型值域镜像漂移：客户端升级/改名，先核 Assembly-CSharp 再动成员") from None


@parallel
class ColorType(IntEnum):
    """CardColorSwitcher.ColorType 全镜像（活表 45 值，2026-11-05 class-axis 收口）。

    值=`enum_table("CardColorSwitcher+ColorType")` 逐名供货（缺名导入即响、活表
    多名下方断言响）；序=序列化 List<string> 族表下标（get_texture refs[ct] 消费轴），
    活枚举序==活表序构造自洽。切换前一次性对拍 45 值全等（class-axis-live-tables
    对拍账）；升版互证面=recipes.color.probe() 键序（12 族序列化字段声明序==活
    prefab 键序，drift_probe B3）。

    族账锚=CardColorSwitcher.cs（模块头注族账）。
    """
    TYPE_GENERIC = _ctv("TYPE_GENERIC")
    TYPE_DEATHKNIGHT = _ctv("TYPE_DEATHKNIGHT")
    TYPE_DEMONHUNTER = _ctv("TYPE_DEMONHUNTER")
    TYPE_DRUID = _ctv("TYPE_DRUID")
    TYPE_HUNTER = _ctv("TYPE_HUNTER")
    TYPE_MAGE = _ctv("TYPE_MAGE")
    TYPE_PALADIN = _ctv("TYPE_PALADIN")
    TYPE_PRIEST = _ctv("TYPE_PRIEST")
    TYPE_ROGUE = _ctv("TYPE_ROGUE")
    TYPE_SHAMAN = _ctv("TYPE_SHAMAN")
    TYPE_WARLOCK = _ctv("TYPE_WARLOCK")
    TYPE_WARRIOR = _ctv("TYPE_WARRIOR")
    TYPE_DEATHKNIGHT_DUALCLASS = _ctv("TYPE_DEATHKNIGHT_DUALCLASS")
    TYPE_DEMONHUNTER_DUALCLASS = _ctv("TYPE_DEMONHUNTER_DUALCLASS")
    TYPE_DRUID_DUALCLASS = _ctv("TYPE_DRUID_DUALCLASS")
    TYPE_HUNTER_DUALCLASS = _ctv("TYPE_HUNTER_DUALCLASS")
    TYPE_MAGE_DUALCLASS = _ctv("TYPE_MAGE_DUALCLASS")
    TYPE_PALADIN_DUALCLASS = _ctv("TYPE_PALADIN_DUALCLASS")
    TYPE_PRIEST_DUALCLASS = _ctv("TYPE_PRIEST_DUALCLASS")
    TYPE_ROGUE_DUALCLASS = _ctv("TYPE_ROGUE_DUALCLASS")
    TYPE_SHAMAN_DUALCLASS = _ctv("TYPE_SHAMAN_DUALCLASS")
    TYPE_WARLOCK_DUALCLASS = _ctv("TYPE_WARLOCK_DUALCLASS")
    TYPE_WARRIOR_DUALCLASS = _ctv("TYPE_WARRIOR_DUALCLASS")
    TYPE_MERCENARIES_CASTER_TIER_1 = _ctv("TYPE_MERCENARIES_CASTER_TIER_1")
    TYPE_MERCENARIES_CASTER_TIER_2 = _ctv("TYPE_MERCENARIES_CASTER_TIER_2")
    TYPE_MERCENARIES_CASTER_TIER_3 = _ctv("TYPE_MERCENARIES_CASTER_TIER_3")
    TYPE_MERCENARIES_FIGHTER_TIER_1 = _ctv("TYPE_MERCENARIES_FIGHTER_TIER_1")
    TYPE_MERCENARIES_FIGHTER_TIER_2 = _ctv("TYPE_MERCENARIES_FIGHTER_TIER_2")
    TYPE_MERCENARIES_FIGHTER_TIER_3 = _ctv("TYPE_MERCENARIES_FIGHTER_TIER_3")
    TYPE_MERCENARIES_TANK_TIER_1 = _ctv("TYPE_MERCENARIES_TANK_TIER_1")
    TYPE_MERCENARIES_TANK_TIER_2 = _ctv("TYPE_MERCENARIES_TANK_TIER_2")
    TYPE_MERCENARIES_TANK_TIER_3 = _ctv("TYPE_MERCENARIES_TANK_TIER_3")
    TYPE_MERCENARIES_NEUTRAL_TIER_1 = _ctv("TYPE_MERCENARIES_NEUTRAL_TIER_1")
    TYPE_MERCENARIES_NEUTRAL_TIER_2 = _ctv("TYPE_MERCENARIES_NEUTRAL_TIER_2")
    TYPE_MERCENARIES_NEUTRAL_TIER_3 = _ctv("TYPE_MERCENARIES_NEUTRAL_TIER_3")
    TYPE_MERCENARIES_ABILITY_CASTER_SPELL = _ctv("TYPE_MERCENARIES_ABILITY_CASTER_SPELL")
    TYPE_MERCENARIES_ABILITY_CASTER_MINION = _ctv("TYPE_MERCENARIES_ABILITY_CASTER_MINION")
    TYPE_MERCENARIES_ABILITY_FIGHTER_SPELL = _ctv("TYPE_MERCENARIES_ABILITY_FIGHTER_SPELL")
    TYPE_MERCENARIES_ABILITY_FIGHTER_MINION = _ctv("TYPE_MERCENARIES_ABILITY_FIGHTER_MINION")
    TYPE_MERCENARIES_ABILITY_TANK_SPELL = _ctv("TYPE_MERCENARIES_ABILITY_TANK_SPELL")
    TYPE_MERCENARIES_ABILITY_TANK_MINION = _ctv("TYPE_MERCENARIES_ABILITY_TANK_MINION")
    TYPE_MERCENARIES_ABILITY_NEUTRAL_SPELL = _ctv("TYPE_MERCENARIES_ABILITY_NEUTRAL_SPELL")
    TYPE_MERCENARIES_ABILITY_NEUTRAL_MINION = _ctv("TYPE_MERCENARIES_ABILITY_NEUTRAL_MINION")
    TYPE_BATTLEGROUNDS_TRINKET_FRIENDLY = _ctv("TYPE_BATTLEGROUNDS_TRINKET_FRIENDLY")
    TYPE_BATTLEGROUNDS_TRINKET_OPPONENT = _ctv("TYPE_BATTLEGROUNDS_TRINKET_OPPONENT")


# 活表多名断言（新色型先判消费语义——族槽/染色链——再入册；缺名已在成员行响）
_extra_ct = sorted(set(_COLOR_TYPE_LIVE) - {m.name for m in ColorType})
assert not _extra_ct, (
    f"CardColorSwitcher+ColorType 活表多出成员 {_extra_ct}——色型值域=活表全镜像"
    "（缺名导入即响、值随活表构造上相等），新成员先判消费语义再入册")


CLASS_NO_WRITE_CARDTYPES = (
    CardType.HERO_POWER, CardType.GAME_MODE_BUTTON, CardType.PET,
)
"""SetMaterialNormal break 组（Actor.cs:Actor.SetMaterialNormal）：无类色写点的卡型。"""

_NULL_FAMILY_CARDTYPES = frozenset(
    (int(CardType.INVALID), int(CardType.BATTLEGROUND_QUEST_REWARD)))
"""GetTexture 直返 null 腿（:259-261）。"""

_DEFAULT_LEG_CLASSES = frozenset(("INVALID", "NEUTRAL", "WHIZBANG"))
"""无 switch 臂的 TAG_CLASS 成员（引擎 default 臂语义=GENERIC）——新职业预检的
「映射存在」判据基准：非本集成员活槽位为 GENERIC(0)=新职业无臂，必须红
（drift_probe E 面同判互证；DREAM 有臂→HUNTER，不在本集）。"""

_slot_maps: tuple[dict[int, int], dict[int, int]] | None = None


def _class_color_type_maps() -> tuple[dict[int, int], dict[int, int]]:
    """活 Invoke 槽位表（进程 memo）：TAG_CLASS 值 → 单类/双职业 ColorType 槽位。

    槽位=宿主直调 `CardColorSwitcher.GetColorTypeForClass/GetColorTypeForDualClass`
    （CardColorSwitcher.cs:CardColorSwitcher.GetColorTypeForClass/:151-169；static 纯
    switch 无实例依赖）。缺映射必红：非 _DEFAULT_LEG_CLASSES 成员槽位==GENERIC
    （=引擎 default 臂落 0=新职业无臂）即 AssertionError——不得把回落 0 当成
    「映射存在」（新职业预检语义，装载期即响；drift_probe E 面同判互证）。
    """
    global _slot_maps
    if _slot_maps is None:
        from eidolon.core.infra import dll_reflect as dr   # noqa: PLC0415（进程一次）
        t = dr.type_("CardColorSwitcher")   # 先确保 coreclr 已装载（System 导入后置）
        from System import Enum             # noqa: PLC0415
        tag_class_t = dr.type_("TAG_CLASS")
        m_single = t.GetMethod("GetColorTypeForClass", (tag_class_t,))
        m_dual = t.GetMethod("GetColorTypeForDualClass", (tag_class_t,))
        assert m_single is not None and m_dual is not None, (
            "活程序集无 CardColorSwitcher.GetColorTypeForClass/GetColorTypeForDualClass"
            "（TAG_CLASS 入参）——static 方法面漂移，槽位直调失效")
        single, dual = {}, {}
        for m in CardClass:
            arg = Enum.ToObject(tag_class_t, int(m))
            single[int(m)] = int(m_single.Invoke(None, (arg,)))
            dual[int(m)] = int(m_dual.Invoke(None, (arg,)))
        gaps = [m.name for m in CardClass
                if m.name not in _DEFAULT_LEG_CLASSES
                and (single[int(m)] == int(ColorType.TYPE_GENERIC)
                     or dual[int(m)] == int(ColorType.TYPE_GENERIC))]
        assert not gaps, (
            f"新职业缺色型映射：{gaps}（非 default-leg 成员活槽位=GENERIC=引擎无臂）"
            "——客户端新增职业须先补消费语义（族槽/染色/显示名）再入册；缺映射必红，"
            "禁当映射存在")
        _slot_maps = (single, dual)
    return _slot_maps

CARDTYPE_TO_FAMILY = {
    # GetTexture 族分派 switch（:228-266）逐字（12 族序列化列表的纹理九族；
    # faction* 三材质族=GetMaterialIcon/GetMaterialBanner 消费，不在本 switch）
    CardType.MINION: "minionCardTextures",                        # :231-234
    CardType.BATTLEGROUND_HERO_BUDDY: "minionCardTextures",       # :232
    CardType.LOCATION: "locationCardTextures",                    # :235-237
    CardType.SPELL: "spellCardTextures",                          # :238-240
    CardType.HERO: "heroCardTextures",                            # :241-243
    CardType.WEAPON: "weaponCardTextures",                        # :244-246
    CardType.LETTUCE_ABILITY: "mercenariesAbilityCardTextures",   # :247-249
    CardType.BATTLEGROUND_SPELL: "battlegroundsSpellCardTextures",   # :250-252
    CardType.BATTLEGROUND_TRINKET: "battlegroundsTrinketCardTextures",  # :253-255
    CardType.BATTLEGROUND_ANOMALY: "battlegroundsAnomalyCardTextures",  # :256-258
}

_CLASS_DISPLAY = {
    # 真值源查证（批24）：游戏侧真值链=GameStrings.s_classNames（GameStrings.cs:GameStrings
    # Map<TAG_CLASS,string>）→ 值=GLOBAL_CLASS_* 本地化键（12 键：DK/DH/DRUID/HUNTER/
    # MAGE/PALADIN/PRIEST/ROGUE/SHAMAN/WARLOCK/WARRIOR/NEUTRAL）→ Get(key) 解析本地化
    # 串。判定=不可换轨留手抄：①供给仅 zhCN（data/Strings/zhCN/GLOBAL.txt:339-350），
    # 解析值（德鲁伊/法师…）≠本表英文词汇（词汇=旧链 sc:131-137 账面 verbatim 沿袭，
    # 换轨=账面串变轨破坏对拍全等）；②INVALID/DREAM/WHIZBANG 三键不在 s_classNames
    # （离线扩展）。12/15 键对应关系由 drift_probe_game_tables.py 机制化互证（升版重跑）。
    # 缺键语义（2026-11-05 live-constants 收口）：**响亮**——class_color_pick 对表外职业
    # （新职业裸 int=CardClass 镜像外值）assert 拒绝，禁回落 "Neutral" 静默冒充中立。
    CardClass.INVALID: "Neutral", CardClass.DEATHKNIGHT: "Death Knight",
    CardClass.DRUID: "Druid", CardClass.HUNTER: "Hunter", CardClass.MAGE: "Mage",
    CardClass.PALADIN: "Paladin", CardClass.PRIEST: "Priest", CardClass.ROGUE: "Rogue",
    CardClass.SHAMAN: "Shaman", CardClass.WARLOCK: "Warlock", CardClass.WARRIOR: "Warrior",
    CardClass.DREAM: "DREAM", CardClass.NEUTRAL: "Neutral", CardClass.WHIZBANG: "WHIZBANG",
    CardClass.DEMONHUNTER: "Demon Hunter"}


# ============================================================================
# GetColorTypeForClass / GetColorTypeForDualClass / GetCardColorTypeForClasses
# ============================================================================

@parallel
def get_color_type_for_class(tag_class: int) -> int:
    """单类色型：CardColorSwitcher.GetColorTypeForClass 宿主直调
    （CardColorSwitcher.cs:CardColorSwitcher.GetColorTypeForClass；进程 memo 槽位表）。

    tag_class=TAG_CLASS 值（CardClass 枚举域）；DREAM→TYPE_HUNTER；
    INVALID/NEUTRAL/WHIZBANG→TYPE_GENERIC（引擎 default 臂语义成员）。
    返回值=序列化列表下标。
    **未知职业必抛**（2026-11-05 class-axis 收口：CardClass 镜像外值 KeyError，
    旧 `.get(int(tag_class), TYPE_GENERIC)` 静默回落退役——未知不得当缺省；
    新职业先入册 CardClass（活表镜像断言）再取槽位）。
    """
    single, _ = _class_color_type_maps()
    v = int(tag_class)
    if v not in single:
        raise KeyError(
            f"职业 {v} 不在 CardClass 全镜像（{len(single)} 成员）——未知职业必抛"
            "（新职业先判消费语义入册，禁回落 GENERIC 冒充中立）")
    return single[v]


@parallel
def get_color_type_for_dual_class(tag_class: int) -> int:
    """双职业色型：CardColorSwitcher.GetColorTypeForDualClass 宿主直调
    （CardColorSwitcher.cs:CardColorSwitcher.GetColorTypeForDualClass；进程 memo 槽位表）。

    DUALCLASS 段；DREAM→HUNTER_DUALCLASS；INVALID/NEUTRAL/WHIZBANG→TYPE_GENERIC
    （引擎 default 臂语义成员）。未知职业必抛（同 get_color_type_for_class）。
    """
    _, dual = _class_color_type_maps()
    v = int(tag_class)
    if v not in dual:
        raise KeyError(
            f"职业 {v} 不在 CardClass 全镜像（{len(dual)} 成员）——未知职业必抛"
            "（新职业先判消费语义入册，禁回落 GENERIC 冒充中立）")
    return dual[v]


@parallel
def get_card_color_type_for_classes(classes) -> list[int]:
    """多类色型：GetCardColorTypeForClasses 对位（CardColorSwitcher.cs:CardColorSwitcher.GetCardColorTypeForClasses）。

    classes=TAG_CLASS 值列表（GetClasses() 升序形；None=decomp null 腿）。
    返回 colors 列表（CardColorType.colors，CardColorType.cs:CardColorType）：
    null/空→[GENERIC]（:125-134）/1 类→[GetColorTypeForClass(c0)]（:135-138，
    GetCardColorTypeForClass :191-197 单元素）/≥3 类→[GENERIC]（:139-143）/
    2 类→[DualClass(c0), DualClass(c1)]（:144-147）。
    """
    if classes is None or len(classes) == 0:                    # :125-134
        return [ColorType.TYPE_GENERIC]
    if len(classes) == 1:                                       # :135-138
        return [get_color_type_for_class(int(classes[0]))]
    if len(classes) >= 3:                                       # :139-143
        return [ColorType.TYPE_GENERIC]
    return [get_color_type_for_dual_class(int(c)) for c in classes]   # :144-147


# ============================================================================
# GetTexture（族分派+下标取 ref）
# ============================================================================

@parallel
def family_for_card_type(card_type: int) -> str:
    """族分派：GetTexture switch 表形（:228-266；我方表化，非游戏结构）。

    未知卡型**响亮拒绝**（2026-11-05 live-constants 收口：原
    `.get(..., "minionCardTextures")` 静默兜底退役）——decomp default 臂=LogError+
    minion 兜底（:262-265），离线无 LogError 面，照录兜底=未知卡型冒充随从渲；
    新卡型（活 TAG_CARDTYPE 多名→infra.card 镜像断言先响）先补族行（带 decomp 锚）
    或显式拒绝，禁当随从。INVALID/BATTLEGROUND_QUEST_REWARD 的 null 腿不在本表
    （get_texture :259-261 先于 switch 早退；段函数同序守卫）。

    族账锚=CardColorSwitcher.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    ct = int(card_type)
    if ct in _NULL_FAMILY_CARDTYPES:
        raise KeyError(
            f"卡型 {ct} 属 GetTexture null 早退腿（:259-261，族 switch 不可及=无族可选）"
            "——调用方先走 null 腿守卫（get_texture/段函数已内置），直取族=越腿")
    if ct not in CARDTYPE_TO_FAMILY:
        raise KeyError(
            f"卡型 {ct} 不在族分派表 CARDTYPE_TO_FAMILY"
            f"（开放位={sorted(int(k) for k in CARDTYPE_TO_FAMILY)}）——GetTexture default 臂"
            "（LogError+minion 兜底 :262-265）离线不照录：新卡型先补族行或显式拒绝，禁当随从兜底")
    return CARDTYPE_TO_FAMILY[ct]


@parallel
def get_texture(card_type: int, color_type: int) -> str | None:
    """类色图集 ref：GetTexture 对位（CardColorSwitcher.cs:CardColorSwitcher.GetTexture）。

    card_type=TAG_CARDTYPE 值；color_type=ColorType 枚举值（列表下标）。
    返回 probe 族表项 AssetReference 串（"名.ext:GUID"）；INVALID/QUEST_REWARD
    →None（:259-261）；list.Count<=下标→None（:267-270）；未知卡型→KeyError 响亮
    （family_for_card_type 拒绝腿，default 臂 LogError+minion 兜底不照录）。
    图集像素消费=recipes.color.atlas(family_for_card_type(card_type), color_type)。
    """
    card_type = int(card_type)
    if card_type in _NULL_FAMILY_CARDTYPES:                     # :259-261
        return None
    refs = probe()[family_for_card_type(card_type)]
    ct = int(color_type)
    if len(refs) <= ct:                                         # :267-270
        return None
    return refs[ct]


# ============================================================================
# compile 期 pick（GetClasses[0] 判据消费点）与 UpdateCardColor 离线形
# ============================================================================

@parallel
def class_color_pick(card: Card) -> tuple[int, str, int]:
    """类色三元组：class_color_pick 对位（old_frames/scene_compiler.py:157-163）。

    返回 (tag_class, class_name, color_type)；GetClasses[0] 判据（缎带同源
    Actor.cs:Actor.UpdateMulticlassRibbon）。注：本判据=compile 期单色 pick——多职业卡引擎实际走
    UpdateCardColor IsMultiClass 覆写块（:6465-6477，见 class_color_segment），
    旧链由组件段复指覆写（composite/GENERIC），本函数两源同形保真。
    """
    cls = card.classes[0]
    name = _CLASS_DISPLAY.get(int(cls))
    assert name is not None, (
        f"职业 {cls!r} 不在 _CLASS_DISPLAY（{len(_CLASS_DISPLAY)} 键=CardClass 全员"
        "+INVALID/DREAM/WHIZBANG 离线扩展）——表外职业=新职业未入册，响亮拒绝"
        "（禁回落 Neutral 冒充中立；活 s_classNames 键对应跑 drift_probe C 面后再补行）")
    return int(cls), name, get_color_type_for_class(int(cls))


def _engine_classes(card: Card) -> list[int]:
    """GetClasses() 引擎形（EntityBase.cs:EntityBase.GetClasses）：476 掩码位升序解码，
    无掩码→[CLASS tag]（!=INVALID 才入列表 :1107-1109）。infra Card.classes
    保留 INVALID 单元素（card.py:310-321 我方形态），此处按引擎过滤对齐。"""
    classes = [int(c) for c in card.classes]
    if len(classes) == 1 and classes[0] == int(CardClass.INVALID):
        return []
    return classes


@parallel
def class_color_segment(card: Card, card_type: int | None = None) -> dict:
    """类色段产物：UpdateCardColor 离线形（Actor.cs:Actor.UpdateCardColor 判定链）→结构化输出
    （sc compile_plan 类色段 sc:263-280 对位；判定+选族+图集引用，apply 写点
    语义属 S11 组装段本期不实现——见 class_color_canonical 立户）。

    分支（引擎序）：单类腿（:6457-6462，Lettuce/trinket 腿语料零命中不接线，
    模块 docstring 边界账）→IsMultiClass 覆写块（:6465-6477）：2 类=[DUALCLASS×2]
    （写点 _MainTex=colors[0]/_SecondTex=colors[1]，离线 composite 等价）；≥3 类
    GENERIC→hero-matching 腿离线 INVALID 同象（colors 恒 [0]，记账）。
    """
    card_type = int(card.cardtype if card_type is None else card_type)
    classes = _engine_classes(card)
    tag_class, class_name, picked_ct = class_color_pick(card)
    seg: dict = {
        "tag_class": tag_class, "class_name": class_name, "color_type": picked_ct,
        "card_type": card_type, "classes": classes,
        "atlas_table": "CardColorSwitcher 单例序列化表（recipes.color.probe 链根直读）",
        "apply": "SetMaterialWithTexture (Actor.cs:Actor.SetMaterialWithTexture)：cardMesh[cardFrontMatIdx]._MainTex；"
                 "SPELL/BG_SPELL 再写 portraitMesh[portraitFrameMatIdx]（:6767）；LOCATION "
                 "No_Gem 尾段 mainTexture（:6782-6786）——写点语义属 S11 组装段",
    }
    if card_type in CLASS_NO_WRITE_CARDTYPES:
        # SetMaterialNormal break（:6709-6725）：无类色写点（旧 hp_render.py:212-222
        # 同账——九职业英雄技能参照框色逐位相同实证）
        seg.update({"branch": "no_write", "colors": [], "family": None,
                    "atlas_ref": None,
                    "apply": "SetMaterialNormal (Actor.cs:Actor.SetMaterialNormal) 该卡型 break：帧保持 "
                             "prefab 序列化材质，无类色写点"})
        return seg
    if card_type in _NULL_FAMILY_CARDTYPES:
        # GetTexture null 早退（:259-261）先于族 switch：判定照跑、无族可选无写点
        # （2026-11-05 live-constants 收口：原静默落 minionCardTextures 族=账面错记）
        seg.update({"branch": "null_family", "colors": [picked_ct],
                    "color_type": picked_ct, "family": None, "atlas_ref": None,
                    "apply": "GetTexture null 早退（CardColorSwitcher.cs:259-261）→ "
                             "SetMaterialWithTexture null 分岔：帧保持序列化材质，无类色写点"})
        return seg

    is_multiclass = len(classes) > 1          # IsMultiClass（EntityBase.cs:EntityBase.IsMultiClass）
    if is_multiclass:                          # :6465-6477 覆写块
        colors = get_card_color_type_for_classes(classes)      # :6468
        if colors == [ColorType.TYPE_GENERIC]:  # CardColorType.IsGeneric()（≥3 腿）
            # :6469-6474 GetClassMatchingHero 对局态腿——离线 INVALID→GENERIC(0)
            # 同象（模块 docstring 偏差记账）
            color_type = ColorType.TYPE_GENERIC
            branch = "generic"
        else:
            color_type = colors[0]             # 写点主色 _MainTex=colors[0]
            branch = "dualclass" if len(colors) == 2 else "single"
    else:
        color_type = (get_color_type_for_class(classes[0]) if classes
                      else ColorType.TYPE_GENERIC)
        colors = [color_type]
        branch = "single"
    seg.update({"branch": branch, "colors": colors, "color_type": color_type,
                "family": family_for_card_type(card_type),
                "atlas_ref": get_texture(card_type, color_type)})
    return seg


@parallel
def multiclass_segments(card: Card, card_type: int | None = None) -> dict:
    """多职业三支路判定/引用核（旧链 components/multiclass.py 三函数对位；
    引擎=UpdateCardColor flag3 块 :6465-6477 + GetCardColorTypeForClasses
    :121-149 + UpdateMulticlassRibbon :6135-6145）。

    返回 {"dualclass": 账|None, "generic": 账|None, "ribbon": 判定}；不触发的
    支路=None（ribbon 恒有判定——SetActive 判式恒在）。composite 图像拼接/
    GENERIC 复指写点/缎带层级激活=离线注入面（S11）；本段只出判定与 ref。

    族账锚=CardColorSwitcher.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    card_type = int(card.cardtype if card_type is None else card_type)
    classes = _engine_classes(card)
    out: dict = {
        "dualclass": None,
        "generic": None,
        "ribbon": {"active": len(classes) > 2, "classes": classes,
                   "source": "Actor.cs:Actor.UpdateMulticlassRibbon UpdateMulticlassRibbon "
                             "SetActive(GetClasses().Count > 2)"},
    }
    if card_type in _NULL_FAMILY_CARDTYPES:
        return out            # GetTexture null 早退（:259-261）：族 switch 不可及，三支路全不触
    if card_type in CLASS_NO_WRITE_CARDTYPES:
        return out            # SetMaterialNormal break（:6709-6725）：无类色写点，三支路全不触
    family = family_for_card_type(card_type)
    if len(classes) == 2:
        # ① 双职业分裂（compile_dualclass_color 对位）：colors[0]=低值职业
        # （GetClasses 升序），UV.x<0.5 取 _MainTex
        cts = [get_color_type_for_dual_class(c) for c in classes]
        out["dualclass"] = {
            "classes": classes, "color_types": cts,
            "atlas_colors0_ref": get_texture(card_type, cts[0]),
            "atlas_colors1_ref": get_texture(card_type, cts[1]),
            "composite_ref": f"composite:{family}:{cts[0]:02d}+{cts[1]:02d}",
            "split": "图宽中心（UV.x=0.5=_MiddleValue 材质常量；dual-class-verify "
                     "best_x 244-258 跨帧族实证）",
            "no_gem_location": "LOCATION No_Gem 尾段写 colors[0] 单图集非 composite"
                               "（Actor.cs:Actor.SetMaterialWithTexture，S11 写点）",
            "source": "Actor.cs:Actor.UpdateCardColor + 6729-6787 + CardColorSwitcher.cs:"
                      "121-149/151-169",
        }
    if len(classes) > 2:
        # ② GENERIC 框（compile_multiclass_generic_color 对位）：槽=GENERIC(0)
        out["generic"] = {
            "classes": classes, "color_types": [ColorType.TYPE_GENERIC],
            "atlas_generic_ref": get_texture(card_type, ColorType.TYPE_GENERIC),
            "hero_matching_leg": "Actor.cs:Actor.UpdateCardColor GetClassMatchingHero 对局态腿——"
                                 "离线 INVALID→GENERIC(0) 同象（偏差记账）",
            "source": "CardColorSwitcher.cs:CardColorSwitcher.GetCardColorTypeForClasses（Count>=3→[TYPE_GENERIC]）+ "
                      "Actor.cs:Actor.SetMaterialWithTexture/6760（count==1 支路写点）",
        }
    return out


@parallel
def class_color_canonical(plan: dict, frame_key: str) -> dict:
    """写点全集收敛：class_color_canonical 对位（旧链 components/class_color.py:30
    逐字转写，批22 兑现）——把计划材质槽的 _MainTex_runtime 收敛到正典写点全集；
    返回变更账（槽级）。

    判定（结构化，atlas_ref 标记）：运行时槽 atlas_ref == plan.class_color.atlas_ref
    者，仅当命中结构写点才保留——cardMesh[cardFrontMatIdx]（恒写，Actor.cs:Actor.SetMaterialWithTexture）、
    portraitMesh[portraitFrameMatIdx]（SPELL :6767-6772；WEAPON 单色 DK 特支 :6767-6775，
    Count==1 守卫=引擎逐字）、No_Gem_Mesh（LOCATION 尾段 :6782-6786）；其余槽
    （legacy「共享实例连带」推断写过的）剥离回序列化默认。"""
    changed: list[dict] = []
    atlas_ref = (plan.get("class_color") or {}).get("atlas_ref")
    if not atlas_ref:
        return {"mode": "canonical", "changed": changed}
    binding = plan["actor_binding"]
    cf_idx, cf_path = binding.get("card_front_mat_idx"), binding.get("card_mesh_node")
    pf_idx, pf_path = binding.get("portrait_frame_mat_idx"), binding.get("portrait_mesh_node")
    spell_like = frame_key in ("Card_Hand_Ability", "Card_Hand_Ability_Premium")  # consumer-v2 改键
    # WEAPON 单色 DK 特支（Actor.cs:Actor.SetMaterialWithTexture）：portraitMesh[portraitFrameMatIdx] 追加写
    # ——weapon-class-atlas 修正支路（Count==1 守卫=引擎逐字：双职业 DK 武器不走）
    card = plan.get("_card_runtime")
    weapon_dk = (frame_key == "Card_Hand_Weapon"
                 and (plan.get("class_color") or {}).get("color_type") == 1
                 and card is not None and not card.is_dualclass)
    for c in plan["components"]:
        path = c.get("path")
        # 槽级（ability/ally/weapon/hero/location 通用读取位）
        for s in c.get("material_slots", []):
            rt = s.get("_MainTex_runtime") or {}
            if rt.get("atlas_ref") != atlas_ref:
                continue
            keep = (s.get("slot") == cf_idx and path == cf_path)
            if not keep and (spell_like or weapon_dk) and path == pf_path \
                    and s.get("slot") == pf_idx:
                keep = True
            if not keep:
                s.pop("_MainTex_runtime")
                changed.append({"path": path, "slot": s.get("slot"), "kind": "slot"})
        # 组件级（location No_Gem：写点本体，恒保留；其余组件级类色覆盖不存在）
        mo = c.get("material_override") or {}
        if mo.get("_MainTex_runtime", {}).get("atlas_ref") == atlas_ref \
                and not (frame_key == "Card_Hand_Location" and c.get("node") == "No_Gem_Mesh"):
            c.pop("material_override")
            changed.append({"path": path, "kind": "component"})
    return {"mode": "canonical", "changed": changed}


# ============================================================================
# 类色 RGB（Actor 类色常量三族，IL 直读——2026-11-05 class-axis 收口；
# premium 染色支消费——mechorse-golden 2026-10-21）
# ============================================================================

_actor_color_cache: dict[str, Any] | None = None


def _actor_color_tables() -> dict[str, Any]:
    """Actor 类色三族直读（lazy + 进程 memo；失败响亮）。

    机械面=eidolon.core.infra.il_tables（零游戏语义 extractor）：
      - 值=Actor..ctor 的「ldc.r4×3+newobj Color+stfld」初始化集
        （Actor.cs:Actor..ctor；readonly CLASS_COLOR_*/CLASS_COLOR_LOCATION_* 字段族，
        2026-11-05 实测 24 字段+GEM_COLOR_* 4）；
      - 槽位映射=GetClassColor/GetDualClassColor/GetLocationClassColor 三 switch 臂
        IL 直读（Actor.cs:Actor.GetClassColor/:GetDualClassColor/:GetLocationClassColor；
        实测各 11 臂，值域 1-11 / 12-22 / 1-11）。
    形状断言（臂数/值域/default 形状——任一红=IL 臂被删/错/改，响亮）：
      - 臂↔字段双射：三方法臂集各==ctor 非泛字段全集（删臂/错臂即断）；
      - 双职业臂字段==单类臂字段（GetDualClassColor 反查同族，引擎逐字）；
      - default 形状：GetClassColor/GetLocationClassColor=无新装载（result 留初值
        GENERIC/LOCATION_GENERIC，pre-switch init）；GetDualClassColor=Call
        Color::get_magenta（Color.magenta 属性直取）；
      - 值域：rgb 三分量有限且 ∈ [-0.001, 1.001]。
    """
    global _actor_color_cache
    if _actor_color_cache is not None:
        return _actor_color_cache
    from eidolon.core.infra import il_tables   # noqa: PLC0415（进程一次）

    fields = il_tables.ctor_object_fields("Actor", "Color", const_count=3)
    class_f = {k: v for k, v in fields.items()
               if k.startswith("CLASS_COLOR_") and not k.startswith("CLASS_COLOR_LOCATION_")}
    loc_f = {k: v for k, v in fields.items() if k.startswith("CLASS_COLOR_LOCATION_")}
    assert "CLASS_COLOR_GENERIC" in class_f and "CLASS_COLOR_LOCATION_GENERIC" in loc_f, (
        f"Actor..ctor 泛字段缺失（CLASS_COLOR_GENERIC/LOCATION）——字段族漂移，"
        f"实有 {sorted(class_f)} / {sorted(loc_f)}")
    arms_c, def_c = il_tables.switch_ldfld_arms("Actor", "GetClassColor")
    arms_d, def_d = il_tables.switch_ldfld_arms("Actor", "GetDualClassColor")
    arms_l, def_l = il_tables.switch_ldfld_arms("Actor", "GetLocationClassColor")
    _assert_color_family("GetClassColor", arms_c, def_c, class_f,
                         "CLASS_COLOR_GENERIC", expect_magenta=False)
    _assert_color_family("GetLocationClassColor", arms_l, def_l, loc_f,
                         "CLASS_COLOR_LOCATION_GENERIC", expect_magenta=False)
    # 双职业臂反查同族：字段与单类臂同集（GetDualClassColor 引擎逐字）
    _assert_color_family("GetDualClassColor", arms_d, def_d, class_f,
                         "CLASS_COLOR_GENERIC", expect_magenta=True)
    slot_rgb = lambda arms_, fld: {slot: fld[name]
                                   for slot, name in arms_.items()}  # noqa: E731
    _actor_color_cache = {
        "class": (slot_rgb(arms_c, class_f), class_f["CLASS_COLOR_GENERIC"]),
        "dual": (slot_rgb(arms_d, class_f), (1.0, 0.0, 1.0)),
        "location": (slot_rgb(arms_l, loc_f), loc_f["CLASS_COLOR_LOCATION_GENERIC"]),
        "fields": fields,
    }
    return _actor_color_cache


def _assert_color_family(method: str, arms: dict[int, str], default: dict,
                         fields: dict, generic_field: str, *,
                         expect_magenta: bool) -> None:
    """三族共用的形状断言（臂数/值域/default 形状——任一红=IL 臂删/错/改）。"""
    non_generic = {k: v for k, v in fields.items() if k != generic_field}
    assert set(arms.values()) == set(non_generic), (
        f"Actor.{method} 臂↔字段双射破（臂 {len(arms)} 枚引用 {sorted(set(arms.values()))}，"
        f"ctor 非泛字段 {len(non_generic)} 个 {sorted(non_generic)}）——删/错任一 IL 臂即此红")
    for slot, rgb in fields.items():
        assert len(rgb) == 3 and all(
            isinstance(c, float) and -0.001 <= c <= 1.001 for c in rgb), (
            f"{method} 字段 {slot} rgb={rgb} 值域越界——类色常量面漂移")
    if expect_magenta:
        assert default["ldfld"] == [] and any(
            "get_magenta" in (c or "") for c in default["call"]), (
            f"Actor.{method} default 腿非 Color.magenta（ldfld={default['ldfld']} "
            f"call={default['call']}）——default 形状漂移")
    else:
        assert default["ldfld"] == [] and default["call"] == [], (
            f"Actor.{method} default 腿有新装载（ldfld={default['ldfld']} "
            f"call={default['call']}）——正典 default=result 留 {generic_field} 初值，形状漂移")


@parallel
def class_color_rgb(color_type: int) -> tuple[float, float, float]:
    """ColorType 槽位 → 类色 RGB：GetClassColor 宿主 IL 直读（数据面零平行——值=
    Actor..ctor 字段初始化字节面，槽位映射=GetClassColor switch 臂 IL 直读；
    Actor.cs:Actor.GetClassColor）。

    缺槽位→CLASS_COLOR_GENERIC（引擎 default 臂同象：result 留初值）。
    IsLocation 分岔腿=引擎先判 IsLocation 走 GetLocationClassColor（离线对位=
    location_class_color_rgb；本函数=非地标腿）。
    消费=SetMaterialPremium 染色账（Actor.cs:Actor.SetMaterialPremium，唯一写点=
    premiumRibbon 槽 _Color）——普通链图集写点不经过本函数。

    族账锚=CardColorSwitcher.cs（模块头注族账）。
    """
    arms, default = _actor_color_tables()["class"]
    return arms.get(int(color_type), default)


@parallel
def dual_class_color_rgb(color_type: int) -> tuple[float, float, float]:
    """双职业色型槽位 → 类色 RGB：GetDualClassColor 宿主 IL 直读
    （Actor.cs:Actor.GetDualClassColor；臂=IL 直读，值=ctor 字段字节面）。

    TYPE_*_DUALCLASS 槽位 → CLASS_COLOR_*（引擎逐字：DEATHKNIGHT_DUALCLASS→
    DEATHKNIGHT …）；其余槽位（GENERIC 等）→ default 臂 Color.magenta（1,0,1，
    get_magenta 属性直取）。消费=SetMaterialPremium 双职业支 GetDualClassColors
    （Actor.cs:Actor.GetDualClassColors）——左右两色**同经本映射**（引擎逐字）。

    族账锚=CardColorSwitcher.cs（模块头注族账）。
    """
    arms, magenta = _actor_color_tables()["dual"]
    return arms.get(int(color_type), magenta)


@parallel
def location_class_color_rgb(color_type: int) -> tuple[float, float, float]:
    """地标类色槽位 → RGB：GetLocationClassColor 宿主 IL 直读
    （Actor.cs:Actor.GetLocationClassColor；引擎 GetClassColor 的 IsLocation 分岔腿，
    Actor.cs:Actor.GetClassColor 头两指令）。

    立壳件（2026-11-05 class-axis 收口随 IL 直读立户）：现役渲染链无调用方——
    premium location 语料零命中（SetMaterialPremium 地标支未接线，偏差记账同
    模块头注离线边界）；缺槽位→CLASS_COLOR_LOCATION_GENERIC（引擎 default 臂同象）。

    族账锚=CardColorSwitcher.cs（模块头注族账）。
    """
    arms, default = _actor_color_tables()["location"]
    return arms.get(int(color_type), default)
