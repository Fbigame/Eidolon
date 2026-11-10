"""frames.specs — 帧规格表（纯数据；差异全部收进 FrameSpec 参数：
uv1/color0 模式、根位姿归零模式、atlas 槽、extra meshes、种族串）。
[ally_recon:37-56 / weapon_recon:32-37 / hp_recon:35-37 / location_recon:35-38 /
hero_recon:46-53；hero 双帧拆 hero_hand/hero_play 两 spec]"""

FRAME_SPECS: dict[str, dict] = {
    # key → actor_slot / 采样 dbf / atlas 槽 / uv1 模式 / color0 / 根归零模式 / extra meshes / 种族串
    "ally":      dict(slot="HAND_MINION", dbf="9", uv1=None, color0=False, root="pos",
                      extra_meshes=True, races=True, report="prefab_report_ally.json",
                      ubertext="prefab_ubertext_ally.json", frame_dir="ally_frame",
                      family="minionCardTextures", sample_ct=7),
    # 金卡档（mechorse-golden 2026-10-21）：同 HAND_MINION 槽、quality="premium"
    # 三表金表（s_premiumActorAssets ActorNames.cs:176 → Card_Hand_Ally_Premium）。
    # family=None：金卡类色=SetMaterialPremium 染色不换图集（Actor.cs:6757-6779
    # 唯一写点=premiumRibbon 槽 _Color/_SecondColor），无类色图集族可提。
    # dbf 采样行沿 e10 先例（2026-10-07-e10-golden 实验 extract spec 同形——
    # kit=卡不变游戏结构，dbf 只进 meta 记账）。
    "ally_premium": dict(slot="HAND_MINION", dbf="9", uv1=None, color0=False, root="pos",
                         extra_meshes=True, races=True, quality="premium",
                         report="prefab_report_ally_premium.json",
                         ubertext="prefab_ubertext_ally_premium.json",
                         frame_dir="ally_premium_frame",
                         family=None, sample_ct=None),
    "weapon":    dict(slot="HAND_WEAPON", dbf="1662", uv1="uv0copy", color0=False, root="pos",
                      extra_meshes=True, races=False, report="prefab_report_weapon.json",
                      ubertext="prefab_ubertext_weapon.json", frame_dir="weapon_frame",
                      family="weaponCardTextures", sample_ct=4),
    "heropower": dict(slot="HISTORY_HERO_POWER", dbf="229", uv1="uv0copy", color0=True, root="pos",
                      extra_meshes=False, races=False, report="prefab_report_heropower.json",
                      ubertext="prefab_ubertext_heropower.json", frame_dir="heropower_frame",
                      family=None, sample_ct=None),
    "location":  dict(slot="HAND_LOCATION", dbf="76981", uv1="uv0copy", color0=False, root="pos",
                      extra_meshes=True, races=False, report="prefab_report_location.json",
                      ubertext="prefab_ubertext_location.json", frame_dir="location_frame",
                      family="locationCardTextures", sample_ct=9),
    # hero 双帧 [hero_recon 相对 ally 的增量：uv1=zeros/color0/根位姿全恒等归零]
    "hero_hand": dict(slot="HAND_HERO", dbf="7", uv1="zeros", color0=True, root="full",
                      extra_meshes=False, races=False, report="prefab_report.json",
                      ubertext="prefab_ubertext.json", frame_dir="hero_hand_frame",
                      family="heroCardTextures", sample_ct=11),
    "hero_play": dict(slot="PLAY_HERO", dbf="7", uv1="zeros", color0=True, root="full",
                      extra_meshes=False, races=False, report="prefab_report.json",
                      ubertext="prefab_ubertext.json", frame_dir="hero_play_frame",
                      family="heroCardTextures", sample_ct=11),
    # 饰品 big-card 帧（bg-ct40-43-44-routing 2026-10-24；ActorNames.cs:568-569
    # BATTLEGROUND_TRINKET→BIG_CARD_BG_TRINKET）。采样 dbf=116510（BG30_Trinket_1st，
    # 本批目标卡；kit=卡不变游戏结构，dbf 只进 meta 记账——ally_premium 先例同注）。
    # uv1="uv0copy"：Mesh 主网格真 uv1 在库（probe 实测 uv1≠uv0，肖像公式层 _SecondTex
    # 采样通道）→ 真通道入 npz；缺通道网格 uv0 回填=引擎缺 UV1 网格有效 TEXCOORD1=uv0
    # 语义（sc-hero-furniture 正典）。
    # family=None：类色族 battlegroundsTrinketCardTextures 的 idx44 写点=Trinket_Hand_
    # BigCard_Player（probe/color probe 实测）——与材质序列化 _MainTex 同纹理，写点
    # 幂等，无图集族可提（SetMaterialWithTexture ct44 由帧链编译器记账不落图集）。
    # races=True：trinket 族学区（RacePlate/Multi_RacePlate）文本用种族串。
    # trinket_level_mats=True：Actor 序列化 m_lesser/greaterTrinketMaterial 双外部材质
    # 解引用（UpdateBaconTrinketComponents Actor.cs:5460-5483 消费，章环章面换装）。
    "trinket":   dict(slot="BIG_CARD_BG_TRINKET", dbf="116510", uv1="uv0copy", color0=False, root="pos",
                      extra_meshes=True, races=True, trinket_level_mats=True,
                      report="prefab_report_trinket.json",
                      ubertext="prefab_ubertext_trinket.json", frame_dir="trinket_frame",
                      family=None, sample_ct=None),
    # 畸变 big-card 帧（bg-ct40-43-44-routing 2026-10-24 ct43 轮；ActorNames.cs:570-571
    # BATTLEGROUND_ANOMALY→BIG_CARD_BG_ANOMALY）。采样 dbf=101954（BG27_Anomaly_000 金钱大战，
    # 本批目标卡；kit=卡不变游戏结构，dbf 只进 meta 记账——trinket 行同注）。
    # 帧=Card_Hand_Ability 族变体（prefab probe 实测：Description_mesh 序列化网格=
    # Card_InHand_Ability_Description_Neutral_mesh、PortraitFrame_mesh=
    # Card_InHand_Ability_Portrait_mesh、SpellTable=m_spellTablePrefab ability 表——
    # 与 Card_Hand_Ability 同资产；差异=主网格材质 Card_Inhand_Ability_Anomaly/
    # CostObject 序列化失活（费用无数字位）/Card_Play_BG_Anomaly_Highlight 光环子树）。
    # uv1="uv0copy"：Description_mesh/PortraitFrame_mesh/Quest 盘真 uv1 在库 ≠uv0
    # （probe 实测；trinket 同款——真通道入 npz，缺通道网格 uv0 回填=引擎 TEXCOORD1 语义）。
    # family=None：类色族 battlegroundsAnomalyCardTextures 全 45 槽=Card_Inhand_Ability_
    # Anomaly.tif 同一纹理（color probe 实测）——与 cardMesh[0] 序列化 _MainTex 同资产，
    # SetMaterialWithTexture 写点幂等，无图集族可提。
    # races=False：ct43 无族学面（UpdateRace flag7/flag2/flag5 全 false→无族板/无学派
    # 网格替换，RaceUberText num2==0 SetActive(false)——Actor.cs:UpdateRace）。
    # extra_meshes=False：无外部网格消费位（学派网格替换不触发 ct43；金币件不注入）。
    "anomaly":  dict(slot="BIG_CARD_BG_ANOMALY", dbf="101954", uv1="uv0copy", color0=False, root="pos",
                      extra_meshes=False, races=False,
                      report="prefab_report_anomaly.json",
                      ubertext="prefab_ubertext_anomaly.json", frame_dir="anomaly_frame",
                      family=None, sample_ct=None),
}
