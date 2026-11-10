"""components — Actor.UpdateAllComponents 族（段 S11 走查与组装顺序对位）。

consumer-v2 段2 全量移植：本文件=old components 逐字副本+五处补丁——import 换面（_raster→新 engine/_card→新 card/+委托期翻译器）、own 六小表改键 canonical prefab（spell_dk 行消亡）、frame_desc_for 双键穿线（own 表+新 raster 吃 prefab，old 件 portrait/watermark 吃旧键）、render_with result 补 prefab、本头注。diff 可 grep "consumer-v2"。compiler/frames/switcher/injectors/portrait/gems/watermark/uber_text 已于段3/4/5 全部换真身（委托期结束）。

游戏锚：Actor.UpdateAllComponents（Actor.cs:Actor.OnEnable/:1743/:2054 调用点；组件序
render-pipeline.md Step5，见包 __init__ 全序）——UpdateMeshComponents 子序
Actor.cs:Actor.UpdateMeshComponents（Rarity→Description→Elite→Premium→CardColor→ManaGemOffset→
ManaGem→MercRole→RuneBanner→MulticlassRibbon）。

我方对位（走查档 §11 顺序语义表）：execute_plan_unified
（old_frames/render_card.py:326-458）+ render_with 接线序（:586-688）的 11 步——
resolve_frame_key→compile→prep_plan→组件接线→注入四件→build_render_list→
光栅→肖像+透明延期→宝石族→文字层（引擎 RenderQueue 51 最后位）→水印 V-pass。
顺序不变量：文字层最后、肖像在透明件延期后、水印 post 差分。

批22 实现账（2026-10-14，S11 生长——战役最后一段，新包首次全链出图）：
三 stub（update_all_components/build_render_list/render_text_layer）转正+
执行面支撑件兑现——
  * build_render_list（:181-214 四过滤+学派网格替换逐字）；
  * update_all_components（execute_plan_unified :326-458 逐字：肖像 sub 清空→
    注入四件〔批20 apply_injections 兑现消费〕→清单→光栅桶〔批18〕→肖像公式层
    〔批15 兑现〕→宝石族〔批16 兑现〕→文字层〔批19 兑现〕）；
  * render_text_layer（:296-319 逐字——text_layer_plan 前向钩兑现消费）；
  * render_with（:586-688 组装总入口：S1 装配账〔批21 card.assemble〕消费→
    compile〔game/compiler.py 统一编译器〕→prep→接线七件〔bacon patch/类色
    canonical〔批13 兑现〕/双职业/GENERIC/符文〔批20 原位应用〕/压制/缎带〕→
    execute→V-pass〔批17 兑现〕）——会话=入口层独占（old _in_session 同形）；
  * 执行面支撑件（ur_core 留旧面六件的本段兑现）：walk_with_key/blank_sub/
    MergedNpz/comp_of + 帧链描述符 _DESC（批15/17/18 平行表收口装配）+
    RenderConfig（旧面旋钮语义继承位）+ 接线族（bacon_plan_patch/dualclass/
    generic/ribbon/suppress——old_render/components 同名件行为面转写）。

签名修正清单（批11b 立壳→实现，批12-20 先例同权）：
  * render_text (uber_text) 增执行面参数 scene/node_px_offset/curved_mesh/
    supersample/cost_phase（S1 探针 C6 四位置参兼容，全带缺省）——见该函数注。
  * update_all_components/build_render_list/render_text_layer 三 stub 签名不动。

偏差账（行为面零差为判据，账面串不保真）——
  * result 不携 plan 整体（PIL 像素重载荷；旧 result["plan"] 诊断面，收口批随
    RenderConfig 旋钮面同议）；checklist_report 历史修复诊断面不入新面（行为
    零消费）。
  * 注入 logs 键写位经批20 compile 产物 verbatim 透传（旧 execute log 键
    badges/faction_banner/tier_spell/frame_rig 同名保真）。
  * apply_rune_banner 独立腿（批20 立户注的符文原位应用兑现形态——products
    形态不含 rune 产物，:644-645 对位独立函数）。

配方面：帧 kit 经 recipes.frames（经 game/frames）；类色暖 memo 经
recipes.color.atlas（接线族消费）；材质态/纹理/mip 全经 engine/raster。
"""

from __future__ import annotations

import functools
import hashlib
from dataclasses import dataclass
from typing import Literal

import numpy as np
from PIL import Image

from eidolon.core.infra.card import BG_MINION_CARDTYPE as _BG_MINION_CARDTYPE
from eidolon.core.infra.card import BG_SPELL_CARDTYPE as _BG_SPELL_CARDTYPE
from eidolon.core.infra.card import Card, CardClass, CardType, GameTag, as_card_or_dbf
from eidolon.core.recipes import color as _color
from eidolon.core.recipes.frames import ability_kit
from eidolon.core.supply import overrides as _ovr   # contract E：覆盖装载域项（会话 memo）
from eidolon.core.render.engine import raster as _raster          # consumer-v2 新 engine（prefab 键）
from eidolon.core.render.engine.raster import PX_PER_UNIT, HALF_H, HALF_W, SIZE
from eidolon.core.render.game import card as _card                # 新 assemble（prefab 分发）
from eidolon.core.render.game import card_color_switcher as _switcher   # consumer-v2 段4
from eidolon.core.render.game import compiler as _compiler   # consumer-v2 段4
from eidolon.core.render.scenes import scenes as _frames   # consumer-v2 段4（prefab 键）
from eidolon.core.render.text import uber_text as _uber_text   # consumer-v2 新包（段3）
from eidolon.core.render.game.actor import frame_reflection as _refl   # consumer-v2 段4
from eidolon.core.render.game.actor import gems as _gems   # consumer-v2 段4
from eidolon.core.render.game.actor import injectors as _injectors   # consumer-v2 段4
from eidolon.core.render.game.actor import portrait as _portrait   # consumer-v2 段4
from eidolon.core.render.game.actor import watermark as _watermark   # consumer-v2 段4
from eidolon.core.render._provenance import invented, parallel


# ============================================================================
# 通用节点遍历 / npz 视图包装（ur_core 留旧面三件的本段兑现）
# ============================================================================
@invented(reason="执行面节点 DFS 走查工具（全路径键链）：我方执行面单源，游戏侧无同名走查方法可转写", counterpart=None)
def walk_with_key(node, key="root", path=""):
    """层级走查器（ur_core.walk_with_key :1012 逐字；全路径=根名起斜杠链，
    npz 键=DFS 序点链）——S11 执行面单源（gems/portrait/injectors 晚引消费）。

    族账锚=Actor.cs（模块族账；本件发明——reason/counterpart 见装饰器）。
    """
    p = f"{path}/{node['name']}" if path else node["name"]
    yield node, key, p
    for i, c in enumerate(node.get("children", [])):
        yield from walk_with_key(c, f"{key}.{i}", p)

@invented(reason="npz 只读 sub 清空包装（肖像走公式层）：离线数组视图适配，游戏侧无对应方法", counterpart=None)
def blank_sub(npz, blank_prefix: str, blank_sub_idx: int):
    """npz 只读包装：指定 sub 清空（肖像走公式层），其余透传（ur_core.blank_sub
    :968 逐字；wf/hp/hero/loc NpzBlankSub 同构）。

    族账锚=Actor.cs（模块族账；本件发明——reason/counterpart 见装饰器）。
    """
    class _Blank:
        def __init__(self, npz_, prefix, sub):
            self.npz = npz_
            self.blank_prefix = prefix
            self.blank_sub = sub

        @property
        def files(self):
            return self.npz.files

        def __getitem__(self, k):
            if k == f"{self.blank_prefix}/sub{self.blank_sub}":
                return np.zeros((0, 3), dtype=np.int64)
            return self.npz[k]
    return _Blank(npz, blank_prefix, blank_sub_idx)

@invented(reason="帧 npz+附加数组的只读合并视图（注入网格并入 mesh_data 命名空间）：离线数组适配层，游戏侧无对应对象", counterpart=None)
class MergedNpz:
    """帧 npz（或 blank 包装）+ 附加数组的只读合并视图（ur_core.MergedNpz :987
    逐字；注入 NestedPrefab 网格以 walk key 并入帧 mesh_data 命名空间——
    .files / __getitem__ 两成员只读包装协议）。

    族账锚=Actor.cs（模块族账；本件发明——reason/counterpart 见装饰器）。
    """

    def __init__(self, base, extra: dict):
        self._base = base
        self._extra = extra

    @property
    def files(self):
        base_files = list(self._base.files)
        have = set(base_files)
        return base_files + [k for k in self._extra if k not in have]

    def __getitem__(self, k):
        if k in self._extra:
            return self._extra[k]
        return self._base[k]

@invented(reason="RGBA→黑底合成 RGB 的交付面转换（V-pass 三渲差分消费位）：我方输出口径，游戏侧由快照相机直出", counterpart=None)
def comp_of(img: Image.Image) -> Image.Image:
    """RGBA → 黑底合成 RGB（ur_core.comp_of :1029 逐字；V-pass 三渲差分消费位）。

    族账锚=Actor.cs（模块族账；本件发明——reason/counterpart 见装饰器）。
    """
    return Image.alpha_composite(Image.new("RGBA", SIZE, (0, 0, 0, 255)), img).convert("RGB")


# ============================================================================
# 计划纹理解析（kit 内存名单源——路径语义已封死）
# ============================================================================


def _kit_texture(name: str, kit_tex: dict, key: str) -> Image.Image:
    """计划纹理名 → kit 内存面 RGBA（唯一合法形态）。

    2026-10-21 render-data-decouple：`get_tex` 的盘符分支（`D:/C:` + `Path.exists()`
    → `Image.open`）**删除**——「路径即资源」的 `assets_dir` 语义退役，渲染只认 kit
    内存名。路径形名字（绝对路径/盘符/UNC）自然落 KeyError，消息点名退役语义；
    不读盘、不静默回退。"""
    if name in kit_tex:
        return kit_tex[name].convert("RGBA")   # 模式归一
    raise KeyError(
        f"纹理 {name!r} 不在 {key} kit 内存面（{len(kit_tex)} 张）——绝对路径/盘符名"
        "=已退役的 assets_dir 语义（计划纹理只接受 kit 内存名，路径不得直读盘）")


# ============================================================================
# 帧链描述符（FRAME_DESC 行的收口装配——批15/17/18 平行表 + 本段残余行）
# ============================================================================

_SLOT_FOR_KEY = {  # consumer-v2 改键 canonical prefab；spell_dk 行消亡（同 spell）
    "Card_Hand_Ability": "HAND_SPELL", "Card_Hand_Ally": "HAND_MINION",
    "Card_Hand_Ally_Premium": "HAND_MINION",
    "Card_Hand_Ability_Premium": "HAND_SPELL",   # 金法术（2026-10-30；s_premiumActorAssets[HAND_SPELL]）
    "Card_Hand_Weapon": "HAND_WEAPON", "Card_Hand_Hero": "HAND_HERO",
    "Card_Play_Hero": "PLAY_HERO",
    "Card_Play_Bacon_Hero": "PLAY_HERO", "History_HeroPower": "HISTORY_HERO_POWER",
    "Card_Hand_Location": "HAND_LOCATION",
    "Card_Hand_BG_Trinket": "BIG_CARD_BG_TRINKET",   # ct44 帧链（2026-10-24；ActorNames.cs:568-569 槽位）
    "Card_Hand_BG_Anomaly": "BIG_CARD_BG_ANOMALY",   # ct43 帧链（2026-10-24；ActorNames.cs:570-571 槽位）
}
"""帧键→slot（ActorNames.GetHandActor 槽位；FRAME_DESC "slot" 行平行）。

覆盖账（2026-11-05 策略表审计，live-constants-followups）：12/16 SCENE_KEYS——
缺 4 行=premium 变体（Card_Hand_Weapon_Premium / Card_Hand_Hero_Premium /
Card_Hand_Location_Premium / History_HeroPower_Premium；ally/ability 两 premium
已覆盖）。未验证链禁静默放行=frame_desc_for 断言响亮（tripwire 同款）；开放=
补行，须 ActorNames 活表槽位锚+帧链验证。余六表（suppress/list_enabled_skip/
school_mesh_swap/school_desc_key/rarity_gem_off/rarity_clouds_lineage）的
`.get(default)` 全部住 frame_desc_for 单处、受其 SCENE_KEYS 断言前置覆盖——
缺行=记载语义缺省（「余帧 False/True」），非未知键静默回落（未知键进不来）。"""

_SUPPRESS_FOR_KEY = {"Card_Hand_Ability": True,  # consumer-v2 改键（spell_dk 消亡）
                     "Card_Hand_Ability_Premium": True}  # 金法术同构（2026-10-30，结构镜像 ability）
"""FRAME_DESC "suppress" 行（renderer.enabled 压制段——ability 链 elite 龙影
enabled 语义；余帧 False）。"""

_LIST_ENABLED_SKIP = {  # consumer-v2 改键
    "Card_Hand_Ally": False, "Card_Hand_Weapon": False, "Card_Hand_Ally_Premium": False,
}
"""FRAME_DESC "list_enabled_skip" 行（renderer.enabled=false 清单跳过——ally/
weapon 靠 plan visible 直渲=引擎运行时开启语义；余帧 True）。"""

_SCHOOL_MESH_SWAP = {"Card_Hand_Ability": True,  # consumer-v2 改键（spell_dk 消亡）
                     "Card_Hand_Ability_Premium": True}  # 金法术（2026-10-30，学派板同构）
"""FRAME_DESC "school_mesh_swap" 行（ability 学派 Description 网格替换）。"""

_SCHOOL_DESC_KEY = {"Card_Hand_Ability": "extra/school_desc",           # consumer-v2 改键（spell_dk 消亡）
                    "Card_Hand_Ability_Premium": "extra/school_desc_premium"}
"""FRAME_DESC "school_desc_key" 行（school_mesh_swap 替换数组键，按帧键择键）。
normal 键=豁免行名字谓词产物（键名与值零扰动，硬判据）；premium 键=金法术帧
自有 prefab 序列化网格（kit report m_spellDescriptionMeshSchool PPtr 现场解，
2026-11-04 金法术 98918 网格错配修复——premium 帧吃 normal 帧 A 网格=拱边整板
2.3px 错位根源；A 住 essential_base_global-mesh-0、B 住 initial_base_global-
910a3655-mesh-0，A 对 B 整体 local z −0.0126）。swap=True 而 pk 缺行=KeyError
响亮（tripwire，_SCHOOL_MESH_SWAP 同款）。"""

_RARITY_GEM_OFF = ("Card_Play_Bacon_Hero", "History_HeroPower")  # consumer-v2 改键
"""FRAME_DESC "rarity_gem": False 行（prefab 无 RarityGem 渲染节点——悬空引用
=引擎 (bool)m_rarityGemMesh 门关；余帧缺省 True）。"""

_RARITY_CLOUDS_LINEAGE = ("Card_Play_Hero", "Card_Play_Bacon_Hero")  # consumer-v2 改键
"""FRAME_DESC "rarity_clouds_lineage": True 行（E8 云层修正未回迁的 sca wrap
谱系漂移实例——lineage 镜像模式；余帧 False）。

`location` 已 A/B 归 canonical 移出（2026-10-20 location-rarity-clouds）：
115631/122772 帧键=location × 传说 offset(0.5,0.5)，A/B 云层吃图集 offset→
z_rarity_gem 12.129→8.300、body 20.60→12.95（t=corpus_t；再叠相位后 z→3.19）。
E8 VS 字节码判式=云层裸 UV（main UV 才吃 _MainTex_ST，gem-and-flat-card-assets
§稀有度宝石），与 weapon/ally/hero_hand 已翻 canonical 同族。"""

_GEM = "stat"
"""FRAME_DESC "gem" 行全集=stat（E9 ③宝石单实现归一——render_gem 桶链退役）。"""

@invented(reason="帧链描述符表化归集（FRAME_DESC 对位）：游戏侧差异分散在各组件运行时判式，我方收成单表查", counterpart="Actor.UpdateAllComponents 帧型差异面")
def frame_desc_for(pk: str) -> dict:
    """帧键 → 帧链描述符（FRAME_DESC[key] 对位的收口装配）：slot/gem/suppress/
    list_enabled_skip/school_mesh_swap/rarity_gem/rarity_clouds_lineage（本段
    残余行）+ portrait（批15 _PORTRAIT_PARAMS）/desc_frame（批17 _DESC_FRAME）/
    zbuf_policy（批18 _ZBUF_POLICY 经 zbuf_policy_for 副本）。未知帧键 assert
    响亮（tripwire 纪律）。

    族账锚=Actor.cs（模块族账；本件发明——reason/counterpart 见装饰器）。
    """
    assert pk in _frames.SCENE_KEYS, (
        f"未知 prefab {pk!r}——_KIT_SOURCE/SCENE_KEYS 无此键（开放位={_frames.SCENE_KEYS}）")
    assert pk in _SLOT_FOR_KEY, (
        f"prefab {pk!r} 无 _SLOT_FOR_KEY 槽位行（已覆盖 {sorted(_SLOT_FOR_KEY)}）——"
        "premium 变体帧链未验证不开放（tripwire；开放=补行，须 ActorNames 活表槽位锚+帧链验证）")
    return {
        "slot": _SLOT_FOR_KEY[pk],
        "gem": _GEM,
        "suppress": _SUPPRESS_FOR_KEY.get(pk, False),
        "list_enabled_skip": _LIST_ENABLED_SKIP.get(pk, True),
        "school_mesh_swap": _SCHOOL_MESH_SWAP.get(pk, False),
        "school_desc_key": _SCHOOL_DESC_KEY[pk] if _SCHOOL_MESH_SWAP.get(pk, False) else "",
        "rarity_gem": pk not in _RARITY_GEM_OFF,
        "rarity_clouds_lineage": pk in _RARITY_CLOUDS_LINEAGE,
        "portrait": _portrait.portrait_params(pk),
        "desc_frame": _watermark.desc_frame_for(pk),
        "zbuf_policy": _raster.zbuf_policy_for(pk),
    }


# ============================================================================
# 渲染配置（旧面 RenderConfig 语义继承位——收口批旋钮面演化异形的预留形）
# ============================================================================


@invented(reason="渲染旋钮容器（我方执行面配置）：游戏侧无配置对象，旋钮散在调用点常量与序列化面", counterpart=None)
@dataclass
class RenderConfig:
    """渲染配置（old_frames/render_card.py:87 RenderConfig 语义继承；canonical
    shell 缺省=正典旋钮解析值）。apply()=公式层 mip 勾替位（批18 set_mip_hooks）。

    `portrait_mip`（2026-10-20 portrait-mip-lod）：肖像公式层 _MainTex 真 mip 链
    LOD 采样**窄开关**。与 `mip` 正交——`mip` 管光栅桶/desc pass 的全局 mip 勾替位
    （会动 16 条符文/水印/文字链），`portrait_mip` 只管肖像公式层一层，art 区外结构性
    零影响（覆盖域外逐位不变已证）。**缺省 False**：机制 A/B 实测 120/127 语料卡
    mae 改善、目标卡达判据（117716 z_art 4.008→1.437 / mae 2.434→1.524），但 full 门
    红 18 行（117/126 origin 行通过）——7 卡=2026-10-19 37.0.0 局部换装参照落在 mip0
    态（v4 正典是 q1 链激活态，参照态分裂家族），2 卡=z_cost 区与肖像窗重叠的舍入级
    +0.002/+0.004。全绿纪律下缺省关，数据面重采/口径裁决后置 True 即生效
    （证据=本卡分支实验档）。

    `cull_non_dk_spell` 缺省 **True**（2026-10-16 用户裁决 + 验证）：材质表 CullMode 是
    引擎恒常语义（九链同规则），非"链选择"——旧缺省 False（非 DK 法术无剔除）是旧链
    基线镜像，导致 spell 帧多画卡背壳金边（三态语料 133 卡验证：零劣化、改善 25 卡、
    轮廓外 1 环 8.129→0.000）。置 False 仅作 A/B 回归通路（须显式记账）。

    族账锚=Actor.cs（模块族账；本件发明——reason/counterpart 见装饰器）。
    """
    name: str = "default"
    mip: bool = False
    portrait_mip: bool = False
    class_color: str = "canonical"
    watermark: bool = False
    cull_non_dk_spell: bool = True
    rarity_gem_mode: str = "lineage"
    use_bg_style: bool | None = None
    # 金框反射层（2026-10-23 gold-frame-phase）：`reflection`=渲不渲反射项。
    # **正式渲法=False（无反射）**——语料 `origin/` 是无反射版本（KillReflect 采集配方，
    # 2026-11-03 换代），判据轴即此态。**True=有反射**（可选层）：只用于对
    # `oracle/reflection/`（有反射真值）做对照，精度暂不追。命中面=序列化带
    # _SpecTex+_ReflTex 的材质（金框/名牌/种族板/龙影），其余帧结构性零变化。
    # `reflection_time`=诊断覆写位（_Time.x；None=用 plan["_shader_time"] 逐代数据值），
    # 扫描/对赌用，渲染链恒 None。
    reflection: bool = False
    reflection_time: float | None = None
    # 金卡（premium 帧）反射项：由 `reflection` 单一布尔控制（2026-11-04 口径收敛——
    # 正式渲法=无反射；旧临时闸 `golden_reflect` 的「对 B 语料对齐」语义已被
    # reflection=False 吸收，闸删除）。
    # 宝石族深度影子（gem-zbuf 2026-11-02 路线 A）：stat 宝石几何 depth-only 写进
    # zbuf（RGB 零接触——zbuf 在宝石覆盖之后无色彩消费者）。服务对象=desc 直接合成
    # 的深度门控（V-pass 三渲消除的闭合件，G 探针 gem 类缺口）；False=A/B 回归
    # 通路（须显式记账，正典恒 True）。
    gem_depth_shadow: bool = True
    # desc 垫图 V-pass 直合（vpass-direct 2026-11-03）：True=深度门控直合（单渲 +
    # W′=cov∩(z_desc==zbuf_final) 写域替换 d_rgb，跳过 hidden/magenta 两变体渲）；
    # False=三渲差分回退通路（full/magenta/nodesc，须显式记账）。等价性前提=
    # gem_depth_shadow（宝石族 PIL 合成不写 zbuf，影子先声明深度）——两旋钮须同开。
    # 缺省 True（2026-11-03 夜班首轮数字裁决）：35/35 applied 卡直合 vs 三渲 final
    # max|Δ|=0 逐位、双路 vs 发布位逐位、full 门 53/0 + corpus 无回归、35 卡渲时
    # 187.6s→74.8s（-60%）——判据账=vpass-direct 实验档（2026-11-03）。
    vpass_direct: bool = True
    # 4x 覆盖超采样几何 AA（geometry-aa-4x 2026-11-04 实现；2026-11-05 render-vnext
    # 转**默认渲染语义**）：4=按 D3D 4x 的**覆盖样本**渲 4 遍、预乘平均。
    # 关键：只移 inside/z 的样本位置，颜色/UV 仍按像素中心求值——整帧 SSAA
    # 会把纹理一起平均糊（实测 mae 反向变差），覆盖超采样才是 MSAA 同阶。
    # 只作用于 update_all_components 的图层（几何/肖像/宝石/框反射/主 desc
    # 光栅）；文字层已有自身 4x 超采样，不重复；watermark.py 的 desc 腿未纳入。
    # 逐位不承诺。**缺省 4**——baseline/gate/publish 的判决态一律 4x（A/B 账：
    # 6/6 代表卡 mae 降 0.21–0.34、golden 16/16 降、无 >0.05 分区回归；
    # geometry-aa-4x 2026-11-04）。
    # **1 = 快速计算路径**（显式设定，入口=上游 tools/render_fast.py）：迭代/
    # 定位用，单卡约 1/3 成本；1x 输出不得进 baseline/信任链、不得当默认渲染语义。
    supersample: int = 4

    def apply(self) -> None:
        _raster.set_mip_hooks(self.mip)

@invented(reason="正典旋钮组选择（我方缺省策略）：游戏侧无「正典配置」对象可转写", counterpart=None)
def canonical_cfg() -> RenderConfig:
    """正典薄壳旋钮（old _knobs_for :146 对位）：**mip=True=链激活态**（光栅桶内容
    指纹派发面 + 公式层 mip hooks 同时开；面板上多数采样 LOD≤0 落 mip0，故为静默面，
    见 RenderConfig 注）、类色 canonical=写点全集、watermark=True=垫图 V-pass 正典、
    rarity lineage=E8 全谱收敛前正典、use_bg_style=None=数据推导；portrait_mip=True=
    肖像 mip 真链 LOD（2026-10-20 7 卡 q1 重采后启用；见 RenderConfig 注）。

    **mip 口径（2026-10-29 翻转，原 mip=False=corpus 缺省已废）**：参照态=oracle 单代
    q1 的**链激活态**（`docs/notes/mip-chain.md`），mip0 与参照不同源——缺省落 mip0 是把
    参照差异记成我方误差。翻转依据=A/B 账（同树分支实验档：132 卡 full 门 pass/0 fail，
    127 卡逐位不变、5 卡改善、0 卡变差；hooks-only 变体只 1 卡变化、无独立价值）。

    **4x 覆盖超采样=默认渲染语义（2026-11-05 render-vnext）**：本壳显式
    `supersample=4`（=RenderConfig 缺省），gate/batch/publish 的公告判决态因此一律
    4x。**快速计算路径 = 显式 `replace(canonical_cfg(), supersample=1)`**（入口
    上游 tools/render_fast.py）：只用于迭代/定位，输出不进 baseline/信任链、
    不参与门判决（门恒吃本壳缺省）。

    族账锚=Actor.cs（模块族账；本件发明——reason/counterpart 见装饰器）。
    """
    return RenderConfig(name="canonical_shell", mip=True, portrait_mip=True,
                        class_color="canonical", watermark=True,
                        rarity_gem_mode="lineage", use_bg_style=None,
                        supersample=4)


# ============================================================================
# 通用渲染清单构建（build_render_list_unified :181-214 逐字）
# ============================================================================

@parallel
def build_render_list(hierarchy, npz, plan: dict, desc: dict) -> tuple[list, list]:
    """可见/raster/宝石节点/enabled 四过滤 + ability 学派 Description 网格替换
    （各帧 build_render_list 的统一体；差异点：gem 节点名集合与 school_mesh_swap
    走描述符）。返回 (不透明清单, 跳过账)。

    缺网格记账（2026-11-01 mesh-skip-accounting；行为面零差偏差，本转写唯一处）：
    带 renderer 而 mesh_stats 缺席的节点入跳过账 `{path}(缺网格)` 后照旧 continue
    ——游戏原形此处无账面语义可对位（缺网格件引擎侧本就不产绘制），跳过账是我方
    执行面诊断通道（log["skipped"]）。逐条理由见循环内注。

    族账锚=Actor.cs（模块头注族账；逐字转写件）。
    """
    gem_nodes = {"Gem_Mana"} if desc["gem"] != "stat" or desc["slot"] != "HAND_MINION" \
        else {"Gem_Mana", "Gem_Attack", "Gem_Health"}
    visible = {c["path"]: c for c in plan["components"] if c.get("visible")}
    nodes, skipped = [], []
    for n, key, path in walk_with_key(hierarchy):
        if not n.get("mesh_stats"):
            if n.get("renderers"):
                # 缺网格缺席（2026-11-01 mesh-skip-accounting）：同 GO 挂 MeshRenderer
                # 而 mesh_stats 缺席=MeshFilter.m_Mesh 未解析成功（引擎内建引用/空引用
                # 两形态，kit 装载期 PPtr miss，节点无网格数组；缺网格普查 16 键 48 节点
                # 全数此形态）。原形静默 continue（不进 error 不进 skipped），门 0 fail
                # 反证不了 0 缺网格。本账只记账零行为差：该节点照样不进渲染清单。
                # 判定=层级节点自身 renderers（MeshFilter 解析失败不落节点字典，
                # 同 GO renderer 是它在账的旁证），零新增束读取；无 renderer 的结构
                # 节点（transform 等，16 键 925 节点）非渲染物，维持不记账。
                # 字符串用全路径——同名件（BGRewardVFX CardBackGlow/Orange_Fill_*）
                # 会被上游 sorted(set()) 在名字面上吞账。
                skipped.append(f"{path}(缺网格)")
            continue
        rr = n.get("renderers") or []
        comp = visible.get(path)
        if not rr or not rr[0].get("materials"):
            continue
        if comp is None:
            skipped.append(f"{n['name']}(计划隐藏)")
            continue
        if comp.get("raster") is False:
            skipped.append(f"{n['name']}(文字载体/无材质光栅)")
            continue
        if n["name"] in gem_nodes:
            skipped.append(f"{n['name']}(→宝石族 shader 公式)")
            continue
        if comp.get("raster") is False:
            skipped.append(f"{n['name']}(几何级排除：材质无可见展示态)")
            continue
        if (desc.get("list_enabled_skip", True) and not rr[0].get("enabled", True)
                and not comp.get("enabled_override")):
            skipped.append(f"{n['name']}(renderer.enabled=false)")
            continue
        arr_key = key
        mesh_info = comp.get("mesh") or {}
        # 学派网格替换按帧键择键（school_desc_key 行）：normal=extra/school_desc
        # （键名与值零扰动），premium=extra/school_desc_premium（帧自有 prefab
        # 序列化网格——UpdateRace 写 meshFilter.sharedMesh 的 per-prefab 引用面）。
        school_key = desc.get("school_desc_key")
        if desc.get("school_mesh_swap") and n["name"] == "Description_mesh" \
                and mesh_info.get("runtime") == "school" and school_key \
                and f"{school_key}/verts" in npz.files:
            arr_key = school_key
        nodes.append((n["name"], arr_key, rr[0]["materials"], np.array(n["world"]), comp))
    return nodes, skipped


# ============================================================================
# 文字层挂接（:296-319 逐字；text_layer_plan 前向钩兑现消费）
# ============================================================================


def _text_layers(meta, plan: dict, pk: str) -> tuple[list, np.ndarray]:
    """文字层逐 entry 渲染（RenderQueue 51）：text_layer_plan（批19 前向钩）产物
    逐 entry 喂 render_text（批19 立户→批22 兑现：FreeType supersample 链+RTT 曲面）。

    单一渲染点：`render_text_layer`（常规合成面）与 `render_with` 的延后合成
    （`plan["_defer_text"]`：V-pass 之后最后贴字，引擎序）共用——文字只渲一遍。
    返回 (layers, alpha)：layers=按 plan 序的 RGBA 层；alpha=合并 α>0 掩码
    （bool H×W，诊断位）。"""
    scene = _uber_text.Scene(
        world_by_path={p: np.array(n["world"], dtype=float)
                       for p, _, n in _uber_text._walk(meta) if n.get("world") is not None},
        s=PX_PER_UNIT, wx0=-HALF_W, wz1=HALF_H, ox=0.0, oy=0.0, canvas=SIZE)
    tlp = _uber_text.text_layer_plan(pk, plan)
    alpha = np.zeros((SIZE[1], SIZE[0]), bool)
    layers = []
    for entry in tlp["entries"]:
        layer = _uber_text.render_text(entry["text"], entry["role"], entry["fontdef"],
                                       entry["ns"], scene,
                                       node_px_offset=(0.0, 0.0),
                                       curved_mesh=tlp["curved"] if entry["curved_used"] else None,
                                       cost_phase=entry["phase"])
        layers.append(layer)
        alpha |= np.asarray(layer)[..., 3] > 0
    return layers, alpha

@parallel
def render_text_layer(base: Image.Image, meta, plan: dict, pk: str) -> Image.Image:
    """文字层贴底图（常规调用面：UnifiedUpdateAllComponents 末尾，用于 notext/textonly
    与任何未延后的渲）：`_text_layers` 逐层 alpha_composite 收底图（按 plan 序）。

    副产物 `plan["_text_alpha"]` = 合并 α>0 掩码（bool H×W；诊断位，V-pass 不再消费）。

    origin 正典链（`plan["_defer_text"]`，render_with 写入）不在本函数贴字：文字层
    延后到 desc 垫图 V-pass **之后**最后合成——引擎序=水印写 desc 材质（同一
    material pass）先、文字独立 mesh（renderQueue 后移）后，
    Actor.cs:Actor.UpdateWatermark × UberText.cs:UberText.UpdateRenderQueue。

    族账锚=Actor.cs（模块头注族账；逐字转写件）。
    """
    layers, alpha = _text_layers(meta, plan, pk)
    for layer in layers:
        base.alpha_composite(layer)
    plan["_text_alpha"] = alpha
    return base


# ============================================================================
# 肖像 sub 补标（attach_portrait_component 对位——批15 portrait_binding 消费形）
# ============================================================================


def _attach_portrait_component(plan: dict, frame_key: str) -> dict | None:
    """spell/ally 计划补 portrait_submesh 标记（wf/hero/hp/loc/bacon 编译期自带，
    此调用对它们 no-op）；结构化绑定=portrait.portrait_binding（kit report 直读，
    帧相关不可硬编码）。返回带标记的组件（无肖像网格的帧 None——九开放帧链不存在的
    形态，portrait_binding assert 响亮）。"""
    if any(c.get("portrait_submesh") for c in plan["components"]):
        return None
    binding = _portrait.portrait_binding(frame_key)
    comp = next((c for c in plan["components"] if c.get("path") == binding["node"]), None)
    if comp is None:
        return None
    comp["portrait_submesh"] = {
        "sub": binding["sub"],
        "source": f"actor_binding.m_portraitMesh/m_portraitMatIdx（{frame_key} 帧）",
    }
    return comp


# ============================================================================
# 统一执行器（execute_plan_unified :326-458 逐字；注入四件=批20 apply_injections）
# ============================================================================

@parallel
def _update_all_components_once(plan: dict, pk: str, cfg,
                                out_zbuf: list | None = None) -> tuple:
    """S11 组装入口：UpdateAllComponents 顺序对位（execute 五至十步）。

    plan=编译计划 dict（compiler.compile_plan 产物+prep 增补+接线七件后态）；
    pk=prefab（consumer-v2 穿线）；cfg=RenderConfig。返回 (渲染图, 报告 dict)。

    out_zbuf（vpass-direct 2026-11-03）：单元素 list 出参——非 None 时把 final
    zbuf **引用** append 进去（zbuf 全链原地写：主光栅/反射/肖像/延期透明/宝石
    深度影子，函数尾=终态；gem-zbuf 实证「引用即终态」）。服务对象=render_with
    直合路径的深度门控写域；零拷贝（禁 copy 大数组）。调用方消费后不留存于
    log/payload——gate 报告 json.dumps 不能序列化大数组。

    族账锚=Actor.cs（模块头注族账；逐字转写件）。
    """
    desc = frame_desc_for(pk)
    textonly = bool(plan.get("_textonly"))   # prep textonly_plan 写入（plan 级消费口）
    scene = _frames.scene_for(pk)
    meta, hierarchy, npz = scene["meta"], scene["hierarchy"], scene["arrays"]
    _kit_tex = _frames.kit_for(pk).textures
    _tex_memo: dict = {}

    def get_tex(name: str):
        if name not in _tex_memo:
            _tex_memo[name] = _kit_texture(name, _kit_tex, pk)
        return _tex_memo[name]
    log: dict = {}

    # ---- 肖像 sub 清空（肖像走公式层）----
    # 并链（portrait-chain 正典）：sc/sca 计划无 portrait_submesh 标记，从绑定结构化
    # 补标（wf/hero/hp/loc/bacon 编译期自带，此调用对它们 no-op）；pcomp=计划扫描
    # （:350 同法——补标返回值不承载编译期已标计划）。
    _attach_portrait_component(plan, pk)
    pcomp = next((c for c in plan["components"] if c.get("portrait_submesh")), None)
    npz_render = npz
    if pcomp is not None:
        pkey = next(key_ for n, key_, path in walk_with_key(hierarchy)
                    if n.get("mesh_stats") and path == pcomp["path"])
        npz_render = blank_sub(npz, pkey, pcomp["portrait_submesh"]["sub"])

    # ---- 运行时注入器四件（批20 apply_injections 兑现消费；:357-388 执行序）----
    # textonly（triple-report）整段跳过：注入件全为非文字 painter，且注入伴随资产
    # 解析；层级/npz 原样透传。
    hierarchy_r, npz_final = hierarchy, npz_render
    if not textonly:
        products = plan.get("_injection_products") or []
        # 金币件子树含 Gem_Health（spell/trinket prefab 真名）——注入前按【注入前】层级收齐
        # 帧自身宝石账，防 execute 期 collect_stat_gems 名匹配吃到注入节点（其材质无
        # 宝石族 _tint 账必崩；old tier_spell :249-252 同判同层级）。
        for prod in products:
            lg = (prod or {}).get("log") or {}
            if (lg.get("coin") or lg.get("coin_std") or lg.get("coin_trinket")
                    or lg.get("coin_quest_reward")) \
                    and "stat_gems" not in plan:
                plan["stat_gems"] = _gems.collect_stat_gems(hierarchy, plan, walk_with_key)
                break
        hierarchy_r, npz_final, _inj_logs = _injectors.apply_injections(
            plan, pk, products, hierarchy, npz_render, walk_with_key)
        for lg in ("badges", "faction_banner", "tier_spell", "frame_rig"):
            if plan.get(lg):
                log[lg] = plan[lg]
        if plan.get("frame_rig", {}).get("applied"):
            log["frame_rig"] = plan["frame_rig"]["applied"]
    else:
        log["textonly"] = "非文字 painter 全关（组件光栅/宝石/肖像/注入器；texts 原样保留）"

    if textonly:
        nodes, skipped = [], []   # textonly：组件全被 textonly_plan 关闭，光栅清单恒空
    else:
        nodes, skipped = build_render_list(hierarchy_r, npz_final, plan, desc)
    log["skipped"] = sorted(set(skipped))
    log["raster_nodes"] = [n[0] for n in nodes]

    # ---- stat 宝石参数收集（gem=stat 而计划无 stat_gems 的链：ability 帧——
    #      ally 等编译期已收的链不重收）----
    if desc["gem"] == "stat" and "stat_gems" not in plan:
        plan["stat_gems"] = _gems.collect_stat_gems(hierarchy_r, plan, walk_with_key)
        log["stat_gems_source"] = "execute 期收集（ability 帧无编译期收集位）"

    W, H = SIZE
    canvas = np.zeros((H, W, 4))
    zbuf = np.full((H, W), -np.inf)
    policy = dict(desc["zbuf_policy"])
    # cull 旋钮=**权威覆写**（2026-10-16）：`cull_non_dk_spell` 缺省 True（材质表 CullMode
    # 正典），显式置 False 则 spell 链整体关剔除（A/B 回归通路，须记账）。用赋值而非 `or`——
    # 旧形 `policy["cull"] or (...)` 在 spell 行改 True 后会**吞掉** False 覆写（实测：旋钮
    # 关着仍然剔，A/B 通路静默失效），故此处单源判定。
    if pk == "Card_Hand_Ability":
        policy["cull"] = bool(cfg.cull_non_dk_spell)
    # 透明队列件延期（引擎队列序：不透明几何 → 肖像 → 透明）：**结构性条件**——有肖像
    # 公式层且非 textonly（2026-10-31 zbuf-table-driven：逐链 zwrite_from_table 键退役，
    # 决定源=材质态表直读；键时代 ally 链漏键=79480 符文挡肖像根因）。
    # 唯一链级出口=**显式豁免位** `zbuf_inline_reason`（非空说明串，语义=「本链故意不延期」，
    # 须记账；默认零条，zbuf_audit 冻结集合核）。
    _inline_why = desc["zbuf_policy"].get("zbuf_inline_reason")
    if _inline_why is not None:
        assert isinstance(_inline_why, str) and _inline_why.strip(), (
            "zbuf_inline_reason 必须是非空说明串（豁免位记账不可静默）")
        log["zbuf_inline_reason"] = _inline_why
    defer_transparent = [] if (_inline_why is None and pcomp is not None
                               and desc.get("portrait") and not textonly) else None
    if textonly:
        cull_log = []   # 无 raster（画布保持透明底；统计账=空）
    else:
        # 几何级排除集（compile_plan 计划级单源）：子网格按材质名跳过（卡背壳等）
        _skip_mats = frozenset(plan.get("_raster_skip_materials") or ())
        cull_log = _raster.raster_bucket_zbuf_unified(nodes, npz_final, canvas, zbuf, get_tex,
                                                      mip=cfg.mip,
                                                      defer_transparent=defer_transparent,
                                                      skip_materials=_skip_mats,
                                                      **policy)
    log["culled_tris"] = cull_log
    if plan.get("non_raster_excluded"):
        log["non_raster_excluded"] = plan["non_raster_excluded"]

    # ---- 金框反射层（2026-10-23 gold-frame-phase；引擎队列序：框体画完、肖像之前）----
    # Custom/Card/UnlitTextureReflection（GenFX_Card_Inhand_Premium / …BannerAtlas_Premium
    # 三处：框体 sub0 / 名牌 / 种族板）。asm 直译见 frame_reflection 模块头注；时间项
    # = 会话冻结时刻/20（_Time.x，逐代数据读；不是 manifest 的 t=(P/20)%0.2）。
    if not textonly and cfg.reflection:
        t_reflect = cfg.reflection_time
        if t_reflect is None:
            t_reflect = plan.get("_shader_time")
        if t_reflect is not None:
            _refl.apply_reflection(canvas, zbuf, nodes, npz_final, get_tex,
                                   float(t_reflect), log=log)
        else:
            log["reflection"] = {"skipped": "无会话时间（_shader_time/reflection_time）"}

    base = Image.fromarray(np.rint(np.clip(canvas, 0, 1) * 255).astype(np.uint8), "RGBA")

    # ---- 肖像公式层（同一 canvas/zbuf；批15 update_portrait_texture 兑现）----
    if pcomp is not None and desc.get("portrait") and not textonly:
        pol = desc["portrait"]
        st = bi = None
        if pol.get("from_plan"):
            pr = plan["portrait_render"]
            st, bi = np.array(pr["second_tint"]), float(pr["blend_intensity"])
        # 肖像 _MainTex 真 mip 链（plan.portrait.card_id → 按需 (bundle,path_id) 链）：
        # 只作用于肖像窗，_SecondTex/其余层不参与（art 区外结构性零影响）。
        # portrait 覆盖在场（contract E）→ 跳链（覆盖内容与 CardDef 链必然不同源，
        # _entry_matches 恒弃链落 mip0——跳过=免整链白装载，语义同弃链）。
        pcard = (plan.get("portrait") or {}).get("card_id")
        p_mip = None if (plan.get("portrait") or {}).get("override") else \
            (_portrait.portrait_mip_entry(pcard)
             if (cfg.portrait_mip and pcard) else None)
        log["portrait"] = _portrait.update_portrait_texture(
            canvas, zbuf, hierarchy_r, npz, pcomp, get_tex, walk_with_key,
            second_tex_name=pol.get("second"), second_tint=st, blend_intensity=bi,
            wrap_tile=pol.get("wrap_tile", False), mip_entry=p_mip,
            asset=(plan.get("portrait") or {}).get("asset"))
        if defer_transparent:
            _raster.draw_transparent_deferred(defer_transparent, canvas, zbuf, mip=cfg.mip)
        base = Image.fromarray(np.rint(np.clip(canvas, 0, 1) * 255).astype(np.uint8), "RGBA")

    # ---- 宝石族（批16 三件兑现；textonly 计划级关闭不加条件——镜像 --notext 精神）----
    if desc["gem"] == "stat":
        # 深度影子（gem-zbuf 2026-11-02 路线 A）：宝石几何 depth-only 写进 zbuf、
        # RGB 零接触——时点在透明延期队补画之后（zbuf 此后无色彩消费者=逐位不变
        # 的结构性保证）；desc 直接合成的深度门控据此看见宝石遮挡（G 探针 gem 类
        # 45,707 px 唯一缺口的闭合件）。门控/三角面集镜像 render_stat_gems。
        if cfg.gem_depth_shadow:
            log["gem_depth_shadow"] = _gems.gem_depth_shadow(
                zbuf, plan, hierarchy_r, npz_final, walk_with_key)
        base = _gems.render_stat_gems(base, plan, hierarchy_r, npz_final, get_tex,
                                      walk_with_key)
    if desc.get("rarity_gem", True) and plan["rarity_gem"]["visible"]:
        clouds_offset = (cfg.rarity_gem_mode == "lineage"
                         and desc.get("rarity_clouds_lineage", False))
        base = _gems.composite_rarity_gem(base, plan, npz_final, hierarchy_r, get_tex,
                                          mode="lineage" if clouds_offset else "canonical")

    # ---- 文字层（RenderQueue 51）----
    # 延后位（plan["_defer_text"]，render_with 的 origin 链写入）：跳过此处合成、返回
    # **无字底图**，文字层改由 render_with 在 ⑪ desc 垫图 V-pass 之后最后合成（引擎序：
    # 水印写 desc 材质先、文字 mesh 后）。V-pass 的 hidden/magenta 变体经 _desc_mutate
    # deepcopy 继承本旗标 ⇒ 三变体同为无字图（V-pass 写域不再吃到文字像素）。
    # notext（无字）/textonly（文字即输出、无 V-pass）不置位，逐位沿原路径。
    if (any(e.get("render") for e in plan["texts"])
            and not plan.get("_defer_text")):
        base = render_text_layer(base, meta, plan, pk)
    if out_zbuf is not None:
        out_zbuf.append(zbuf)   # 引用即终态（zbuf 全链原地写；vpass-direct 深度门控消费）
    return base, log


# 覆盖样本偏移单一事实源=raster.AA_COVERAGE_OFFSETS（watermark 的 V-pass 逐样本
# 门控必须吃同一张表；本处只留引用名，禁第二份常量）。
_AA_OFFSETS: tuple[tuple[float, float], ...] = _raster.AA_COVERAGE_OFFSETS


def _average_aa_images(images: list[Image.Image]) -> Image.Image:
    """4 遍 RGBA 的预乘平均（straight→premul→mean→unpremul）。

    直接平均直通 RGB 会把透明边缘压黑；预乘先乘 α 再平均，等价于 MSAA resolve
    的颜色加权。返回 8-bit RGBA（原型用；进正典前若需要可在 float canvas 层平均）。
    """
    n = len(images)
    w, h = images[0].size
    acc = np.zeros((h, w, 4), dtype=np.float64)
    for im in images:
        a = np.asarray(im.convert("RGBA"), dtype=np.float64) / 255.0
        acc[..., :3] += a[..., :3] * a[..., 3:4]
        acc[..., 3] += a[..., 3]
    alpha = acc[..., 3] / n
    denom = np.maximum(acc[..., 3:4], 1e-8)
    rgb = np.where(acc[..., 3:4] > 1e-8, acc[..., :3] / denom, 0.0)
    out = np.concatenate([rgb, alpha[..., None]], axis=-1)
    # 末级量化 round 化（quant-ab 2026-11-05）：AA 平均出口 trunc→round-to-nearest。
    # 注：4 遍各自 8-bit 量化后再平均的结构未动（float canvas 累加=geometry-aa-4x
    # 未闭合项，另行立案）；本行只改取整规则。
    return Image.fromarray(np.rint(np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")


@parallel
def update_all_components(plan: dict, pk: str, cfg,
                          out_zbuf: list | None = None) -> tuple:
    """S11 组装入口（geometry-aa-4x 外包层）：`cfg.supersample=1` = 逐位旧行为
    （快速路径，非默认）；`=4`（缺省）时按 4 个 D3D 4x **覆盖样本**各渲一遍完整图层，
    再预乘平均。

    每遍独立 canvas/zbuf（`_update_all_components_once` 内新建），故 z-test/混合/
    透明队列/肖像/宝石全部按样本独立求值——这正是相对“逐三角解析覆盖”不需要
    引入 coverage buffer / 逐样本 z 的原因。着色不随样本移：各光栅函数的
    inside/z 用覆盖偏移，颜色/UV 仍用像素中心——否则 4 遍平均会把纹理一起糊
    （2026-11-04 A/B：整帧 SSAA mae 1.39→2.37，覆盖超采样 1.39→1.06）。
    文字层在 origin 链由 render_with 延后合成一次（层已有自身 4x 超采样），
    不重复 4 遍。

    `out_zbuf`（vpass-direct 深度门）：1x 收 1 个 zbuf；4x 收 **4 个**（逐样本），
    V-pass 按同样本逐遍求 desc z 后取交（见 watermark.apply_desc_watermark）。
    """
    n = int(getattr(cfg, "supersample", 4))
    if n == 1:
        return _update_all_components_once(plan, pk, cfg, out_zbuf=out_zbuf)
    if n != 4:
        raise ValueError(f"supersample 只支持 1 或 4（收到 {n!r}）")
    images: list[Image.Image] = []
    logs: list[dict] = []
    try:
        for i, (dx, dy) in enumerate(_AA_OFFSETS):
            _raster.set_coverage_offset(dx, dy)
            # out_zbuf：4x 下**每遍都交引用**（list 追加 4 个 zbuf）。V-pass 直合的
            # 深度门必须与平均图同样本——只留 pass0 会让 `z_desc == zbuf` 中心 vs
            # 样本错位、写域塌成 0（2026-11-04 114363 desc 病灶）。
            img, log = _update_all_components_once(
                plan, pk, cfg, out_zbuf=out_zbuf)
            images.append(img)
            logs.append(log)
    finally:
        _raster.set_coverage_offset(0.0, 0.0)
    log = logs[0]
    # 诊断位：只记 n 与偏移；不改变任何判据键。
    log["supersample"] = {"n": n, "offsets": _AA_OFFSETS}
    return _average_aa_images(images), log


# ============================================================================
# 接线七件（render_with :632-650 接线段；old_render/components 行为面转写）
# ============================================================================

_MULTICLASS_FAMILY_BY_KEY = {  # consumer-v2 改键（spell_dk 行消亡）
    "Card_Hand_Ally": "minionCardTextures", "Card_Hand_Ability": "spellCardTextures",
    "Card_Hand_Weapon": "weaponCardTextures",
    "Card_Hand_Hero": "heroCardTextures", "Card_Hand_Location": "locationCardTextures",
    # ally_premium 无行（.get→None 腿）：金卡类色=SetMaterialPremium 染色无图集写点，
    # 双职业 composite 无写点可改写（Actor.cs:6757-6779；mechorse-golden 2026-10-21）
}
"""帧键→多职业类色图集族（GetTexture 按 cardtype 选族的帧侧镜像——卡型内在轴）。"""

_FAMILY_NO_SURFACE = frozenset({
    "Card_Hand_Ally_Premium", "Card_Hand_Ability_Premium",
    "Card_Hand_Weapon_Premium", "Card_Hand_Hero_Premium",
    "Card_Hand_Location_Premium",
    "History_HeroPower", "History_HeroPower_Premium",
    "Card_Play_Hero", "Card_Play_Bacon_Hero",
    "Card_Hand_BG_Trinket", "Card_Hand_BG_Anomaly",
})
"""多职业图集复指的**显式无写点面**（residual-silent-fallbacks 2026-11-05 收口：
SCENE_KEYS 16 键对 _MULTICLASS_FAMILY_BY_KEY 5 行之外的全员分类——缺行不再静默
`None`）。逐帧引擎锚：
  * 五 premium 变体：金卡类色=SetMaterialPremium 染色（Actor.cs:6757-6779，
    SetMaterial :6609 GOLDEN 分岔），无图集写点可复指（ally_premium 既有注释账
    推及全 premium——_premium_class_color 同构）；
  * heropower 双链：SetMaterialNormal HERO_POWER break（Actor.cs:6709-6725，
    no_write——compiler._class_color family=None 账）；
  * Card_Play_Hero：play 帧 m_cardFrontMatIdx=-1 守卫（SetMaterialWithTexture
    跳过，applied=False——无类色槽写点可复指）；
  * Card_Play_Bacon_Hero：BG 英雄全 CLASS=12 NEUTRAL 无类色面（family=None）；
  * BG_Trinket/BG_Anomaly：ct44/ct43 GetTexture==序列化纹理幂等写点（离线不落
    图集写点，帧保持序列化——compiler 两帧 apply_note 账）。"""

_MULTICLASS_RIBBON_BASE_BY_KEY = {  # consumer-v2 改键（spell_dk 行消亡）
    "Card_Hand_Ally": "Card_Hand_Ally/RootObject/Multiclass_Ribbon",
    "Card_Hand_Ally_Premium": "Card_Hand_Ally_Premium/RootObject/Multiclass_Ribbon",
    "Card_Hand_Ability": "Card_Hand_Ability/RootObject/MulticlassRibbon",
    "Card_Hand_Weapon": "Card_Hand_Weapon/RootObject/Multiclass_Ribbon",
    "Card_Hand_Location": "Card_Hand_Location/RootObject/MulticlassRibbon",
    "Card_Hand_Hero": "Card_Hand_Hero/RootObject/MulticlassRibbon",
}
"""帧键→缎带挂点（underscore 差异=prefab 实测；Multiclass_Ribbon_Shadow_mesh
尾随空格=序列化实测）。"""

_RIBBON_NO_SURFACE = frozenset({
    "Card_Play_Hero", "Card_Play_Bacon_Hero",
    "History_HeroPower", "History_HeroPower_Premium",
    "Card_Hand_BG_Trinket", "Card_Hand_BG_Anomaly",
})
"""缎带**显式无挂点面**（prefab 无 m_multiclassRibbon GO——2026-11-05 全 16 链
层级走查实证：六帧 Multiclass 命中仅 BG 大卡的 MulticlassBannerContainer 注入
容器，无 UpdateMulticlassRibbon 缎带子树）。引擎该态=(bool)m_multiclassRibbon
门关（UpdateMulticlassRibbon 空引用 SetActive 同象，injectors FACTION_CONTAINER
缺帧账同款）——合法不激活，显式记账非静默缺行。evidence=prefab 探针 json
（本任务实验档）。四 premium 变体（ability/hero/location/weapon_premium）prefab
有缎带 GO 而无行=未开放帧链（compile_plan/_SLOT_FOR_KEY tripwire 另有响亮位），
**不入本分类**——若将来接线而未补行，3+ 类卡在此响亮。"""


def _multiclass_family_for(pk: str) -> str | None:
    """多职业图集族解析（residual-silent-fallbacks 2026-11-05 收口——旧裸
    `_MULTICLASS_FAMILY_BY_KEY.get(pk)`→None 静默丢双职业/GENERIC 退役）。

    三态：族行→族名；`_FAMILY_NO_SURFACE` 成员→None（显式无写点面，锚见表注）；
    其余 SCENE_KEYS 成员→AssertionError 响亮（新帧型缺行=不得静默丢双职业/
    GENERIC 复指；开放=补族行或补分类，带引擎锚）。调用方须先过双职业/3+ 类
    前置守卫（本解析只在该语义在场时触达）。"""
    assert pk in _frames.SCENE_KEYS, (
        f"未知 prefab {pk!r}——SCENE_KEYS 无此键（开放位={list(_frames.SCENE_KEYS)}）")
    if pk in _MULTICLASS_FAMILY_BY_KEY:
        return _MULTICLASS_FAMILY_BY_KEY[pk]
    if pk in _FAMILY_NO_SURFACE:
        return None
    raise AssertionError(
        f"prefab {pk!r} 无 multiclass 族行且不在 _FAMILY_NO_SURFACE——新帧型缺行"
        "不得静默丢双职业/GENERIC 复指（residual-silent-fallbacks 2026-11-05；"
        f"开放=补 _MULTICLASS_FAMILY_BY_KEY 行或补无写点分类，带引擎锚；"
        f"现役族行={sorted(_MULTICLASS_FAMILY_BY_KEY)}）")


def _multiclass_ribbon_base_for(pk: str) -> str | None:
    """缎带挂点解析（residual-silent-fallbacks 2026-11-05 收口——旧裸
    `_MULTICLASS_RIBBON_BASE_BY_KEY.get(pk)`→None 静默丢缎带退役）。

    三态：挂点行→路径；`_RIBBON_NO_SURFACE` 成员→None（prefab 无缎带 GO=
    引擎 (bool)m_multiclassRibbon 门关，probe 实证）；其余 SCENE_KEYS 成员
    →AssertionError 响亮（prefab 有缎带 GO 而无行=新帧型缺行，3+ 类卡不得
    静默丢缎带）。调用方须先过 3+ 类前置守卫。"""
    assert pk in _frames.SCENE_KEYS, (
        f"未知 prefab {pk!r}——SCENE_KEYS 无此键（开放位={list(_frames.SCENE_KEYS)}）")
    if pk in _MULTICLASS_RIBBON_BASE_BY_KEY:
        return _MULTICLASS_RIBBON_BASE_BY_KEY[pk]
    if pk in _RIBBON_NO_SURFACE:
        return None
    raise AssertionError(
        f"prefab {pk!r} 无缎带挂点行且不在 _RIBBON_NO_SURFACE——prefab 层级含缎带 "
        "GO 而表缺行，3+ 类卡不得静默丢缎带（residual-silent-fallbacks "
        f"2026-11-05；开放=补 _MULTICLASS_RIBBON_BASE_BY_KEY 行，带 prefab 实测锚；"
        f"现役挂点行={sorted(_MULTICLASS_RIBBON_BASE_BY_KEY)}）")

_RIBBON_MESH_REL = "Ribbon_Root/Multiclass_Ribbon_mesh"
_RIBBON_SHADOW_REL = "Ribbon_Root/Multiclass_Ribbon_mesh/Multiclass_Ribbon_Shadow_mesh "
_RIBBON_TEX_NAME = "Card_Inhand_Multiclass_Ribbon"

_COMPOSITE_MEMO: dict = {}
_UVT_MEMO: dict = {}


def _bacon_plan_patch(plan: dict, card, frame_key: str) -> dict | None:
    """酒馆卡最小接线（old_render/components/bacon.py:50 行为面转写）：盾徽/金币
    替水晶的语境行为（mode=bacon 显式替代游戏实体 tag 门）+ 42 desc 网格/随从
    多种族板等卡型内在行为。非 bacon 卡返回 None（零改动）。"""
    mode = plan.get("_bg_style")
    if mode is None:
        mode = _injectors.derive_bg_mode(card)   # 直调兜底
    cardtype = int(card.cardtype)
    is_bg_spell = cardtype == _BG_SPELL_CARDTYPE
    tech_level = card.tech_level
    in_bacon = mode == "bacon"
    tech_gem = (in_bacon and tech_level > 0
                and (cardtype == _BG_MINION_CARDTYPE or is_bg_spell
                     or cardtype == int(CardType.SPELL)))
    # premium ct5 TL0 水晶保持显示（golden 98918 2026-11-04，与 injectors want_coin_std
    # premium 门同判同据）：premium>0 的 TL0 法术不注金币件（采集结果=蓝 Gem_Mana
    # 可见，Actor.cs:Actor.UpdateManaGemComponent gem 显隐只吃 DISABLE_SPELL_MANA_GEM
    # 选项）→ 水晶不关；非 premium ct5 TL0 行为不变（金币替水晶）。
    coin_gem = (in_bacon and tech_level == 0
                and (is_bg_spell or (cardtype == int(CardType.SPELL)
                                     and not card.premium)))
    # BG 英雄能力金币面（bacon-hero-power-frames 2026-10-07 patch 提案 P1）：ct10
    # 落在盾徽/金币判式外（UseTechLevelManaGem flag2=IsBaconSpell∨IsSpell 结构性排除
    # ct10；heropower SpellTable 无 156/308 槽）——藏水晶腿单独开（引擎卡侧无条件：
    # UpdateManaGemComponent flag4 UseCoinManaGem leg :5217-5231/:6839-6841；采集链
    # AlphaTool.Renderer.cs:190-201 IsHeroPower 同腿）。
    hero_power_coin = (in_bacon and frame_key == "History_HeroPower"
                       and cardtype == int(CardType.HERO_POWER))
    # 饰品金币面（bg-ct40-43-44-routing 2026-10-24）：mode=bacon ∧ ct44 → 金币件
    # （SpellTable 槽 145 专用件注入，injectors want_coin_trinket 腿）替水晶展示。
    # 采集链 trinket leg（AlphaTool.Renderer.cs:191-201 HideCoinManaGem→GetSpell(
    # COIN_MANA_GEM).ActivateState(BIRTH)）净态=币面显示、水晶不显（参照 116510/133060
    # notext 实证无蓝水晶）；本仓渲染链宝石公式层在光栅桶之后合成（层级与引擎队列
    # 序相反），水晶不关会盖住注入金币—— spell coin_gem 腿同形。
    coin_gem_trinket = (in_bacon and cardtype == int(CardType.BATTLEGROUND_TRINKET))
    # 任务奖励金币面（bg-ct40-43-44-routing 2026-10-24）：mode=bacon ∧ ct40 → 标准
    # 金币件 145（injectors want_coin_quest_reward 腿，与 TL0 法术同件）替水晶展示。
    # 采集链 IsBattlegroundQuestReward leg（AlphaTool.Renderer.cs:190-201 标准金币腿
    # HideCoinManaGem→GetSpell(COIN_MANA_GEM).ActivateState(BIRTH)）；藏水晶同
    # UpdateManaGemComponent flag4 UseCoinManaGem leg（Actor.cs:5217-5231/:6839-6841）
    # ——spell coin_gem 腿同形（水晶不关会盖住注入金币，光栅序与引擎相反）。
    coin_gem_quest_reward = (in_bacon
                             and cardtype == int(CardType.BATTLEGROUND_QUEST_REWARD))
    account: dict = {"cardtype": cardtype, "frame_key": frame_key, "tech_level": tech_level,
                     "bg_style_mode": mode}
    if not (is_bg_spell or cardtype == _BG_MINION_CARDTYPE or tech_gem or coin_gem
            or hero_power_coin or coin_gem_trinket or coin_gem_quest_reward):
        return None
    if is_bg_spell:
        if tech_gem or coin_gem:
            plan["gem"]["enabled"] = False
            account["gem"] = (
                "spell stat 路径 disabled（"
                + ("盾徽替水晶，Actor.cs:Actor.UpdateManaGemComponent/:6812-6837" if tech_gem
                   else "金币替水晶（TL0 法术面），UseCoinManaGem leg :6839-6841")
                + "）")
        # desc 网格 school/neutral 切换对 BG 法术同效（Actor.cs:Actor.UpdateRace flag2）——
        # 按 plan 文本内容（plate=TAG_SPELL_SCHOOL zhCN）镜像引擎判据。
        plate_text = next((e.get("text", "") for e in plan["texts"] if e.get("role") == "plate"), "")
        comp = next((c for c in plan["components"] if c["path"].endswith("Mesh/Description_mesh")), None)
        if comp is not None:
            want = "school" if plate_text else "neutral"
            if (comp.get("mesh") or {}).get("runtime") != want:
                comp.setdefault("mesh", {})["runtime"] = want
                account["desc_mesh"] = (f"neutral→{want}（plate_text={plate_text!r}）")
            else:
                account["desc_mesh"] = f"already {want}"
    elif cardtype == _BG_MINION_CARDTYPE and tech_level > 0:
        # 多种种族种族板切换（UpdateRace Actor.cs:Actor.UpdateRace）；races=Card.races 正典。
        # Eidolon 覆盖座位（core-integration §7.5，消费点 3/3）：races_text_override
        # 非 None 时板计数跟 override（与 compiler 文本计数同源）——否则会出现
        # "文本 1 种族、板是双种族"或空覆盖不隐藏板。
        if card.races_text_override is not None:
            race_count = len(card.races_text_override)
            account["races"] = list(card.races_text_override)
        else:
            race_count = len(card.races)
            account["races"] = list(card.races)
        if race_count > 1:
            single = next((c for c in plan["components"]
                           if c.get("path", "").endswith("RootObject/RacePlate_mesh")), None)
            multi = next((c for c in plan["components"]
                          if c.get("path", "").endswith("RootObject/Multi_RacePlate_mesh")), None)
            if single is not None:
                single["visible"] = False
            if multi is not None:
                multi["visible"] = True
            account["race_plate"] = "single→off/multi→on（Actor.cs:Actor.UpdateRace）"
        if tech_gem:
            before = len(plan.get("stat_gems", []))
            plan["stat_gems"] = [g for g in plan.get("stat_gems", []) if g["node"] != "Gem_Mana"]
            account["gem"] = (f"ally stat_gems 滤 Gem_Mana（{before}->{len(plan['stat_gems'])}；"
                              "攻/血保留；Actor.cs:Actor.UseTechLevelManaGem 随从分支×mode=bacon）")
    elif tech_gem:   # ct=5 普通法术 × bacon 语境（IsSpell leg）
        plan["gem"]["enabled"] = False
        account["gem"] = "spell stat 路径 disabled（盾徽替水晶，IsSpell leg）"
    elif coin_gem:   # ct=5 普通法术 × bacon × TL0（标准金币件 145 面）
        plan["gem"]["enabled"] = False
        account["gem"] = "spell stat 路径 disabled（金币替水晶，UseCoinManaGem leg）"
    elif hero_power_coin:   # ct10 英雄能力 × bacon：金币替水晶（P1，金币件注入=compile_tier_spell want_coin_hp 腿）
        plan["gem"]["enabled"] = False
        account["gem"] = ("heropower stat 路径 disabled（金币替水晶，UseCoinManaGem leg "
                          "Actor.cs:5217-5231/:6839-6841 卡侧无条件；采集链 AlphaTool."
                          "Renderer.cs:190-201 IsHeroPower leg）")
    elif coin_gem_trinket:   # ct44 饰品 × bacon：金币件替水晶（ SpellTable 槽 145 注入）
        plan["gem"]["enabled"] = False
        account["gem"] = ("trinket stat 路径 disabled（金币件替水晶展示，SpellTable 槽 145 "
                          "注入=compile_tier_spell want_coin_trinket 腿；采集链 AlphaTool."
                          "Renderer.cs:191-201 IsBattlegroundTrinket leg，参照币面无水晶实证）")
    elif coin_gem_quest_reward:   # ct40 任务奖励 × bacon：标准金币件 145 替水晶
        plan["gem"]["enabled"] = False
        account["gem"] = ("quest_reward stat 路径 disabled（金币件替水晶展示，标准件 145 "
                          "注入=compile_tier_spell want_coin_quest_reward 腿；采集链 "
                          "AlphaTool.Renderer.cs:190-201 IsBattlegroundQuestReward leg；"
                          "藏水晶=UpdateManaGemComponent flag4 UseCoinManaGem leg "
                          "Actor.cs:5217-5231/:6839-6841）")
    return account


def _img_fp(img) -> str:
    """图内容指纹（sha256(RGBA 字节) 前 16 hex）——memo 键内容位（contract E）。

    缓存键面账（外审 E 行）：_COMPOSITE_MEMO 旧键 (family, ct0, ct1, split) 不含图
    内容——同 key 不同图第二次直接返回第一张对象（覆盖轴同键异图=串图位）。内容
    指纹入键后，键与像素一一对应（数据轴 atlas 同族同 ct 恒同内容=指纹恒同=命中
    语义不变；覆盖轴异内容=异键=禁串）。"""
    return hashlib.sha256(
        np.asarray(img.convert("RGBA"), dtype=np.uint8).tobytes()).hexdigest()[:16]


def _dualclass_composite(family: str, ct0: int, ct1: int, img0, img1, split: float = 0.5):
    """composite 图集（内存面）：左半 colors[0] / 右半 colors[1]，分割列=
    `round(w × _MiddleValue)`。

    机制锚（2026-10-31 location-dualclass-band，shader 反汇编）：
    `Custom/Card/UnlitTextureDualClass` 的 PS 判式 =
    `(uv0.x·_MainTex_ST.x + _ST.z <= _MiddleValue) ? _MainTex(uv)·COLOR0 : _SecondTex(uv)·_EnableDualClass·COLOR0`
    ——**硬 step、坐标=原始 uv0.x、分割=材质序列化常量 `_MiddleValue`**
    （地标材质 0.32499998807907104；minion/spell/weapon/hero 材质 0.5）。
    故「纹理空间按 w×split 拼」与引擎逐像素等价（无掩码/无软边/无 alpha test）；
    旧实现写死 0.5=拟合，地标图集 UV 矩形不以 0.5 居中才暴露（过程账=实验档案，slug 可检索）。
    进程 memo 键 (family, ct0, ct1, split, fp0, fp1)——**内容指纹位（contract E，
    2026-11-06）**：键含两源图 sha 指纹，同键异图串图位闭合（覆盖轴拼图源=覆盖图，
    见 _compile_dualclass_color；composite(ov,ov)=ov 逐位）。

    判式含等号（`<=` 取 _MainTex）⇒ 右半起点=ceil(w×split)。"""
    key = (family, ct0, ct1, round(float(split), 6), _img_fp(img0), _img_fp(img1))
    if key in _COMPOSITE_MEMO:
        return _COMPOSITE_MEMO[key]
    img0 = img0.convert("RGBA")
    img1 = img1.convert("RGBA")
    assert img0.size == img1.size, (family, ct0, ct1, img0.size, img1.size)
    x_split = int(np.ceil(img0.size[0] * float(split)))
    img0.paste(img1.crop((x_split, 0, img1.size[0], img1.size[1])), (x_split, 0))
    _COMPOSITE_MEMO[key] = img0
    return img0


def _middle_value_for(plan: dict, hierarchy: dict, *, default: float = 0.5) -> tuple[float, str]:
    """card front 材质的 `_MiddleValue`（D 层直读：kit 走查的序列化 m_Floats）。

    取位=actor_binding.card_mesh_node + card_front_mat_idx 的槽材质名 → 层级 renderer
    材质同名项 → `floats["_MiddleValue"]`。缺位回落 shader 属性默认 0.5，并在账上标明
    来路（避免把「没读到」冒充成「读到了 0.5」；silent-loss 纪律）。"""
    b = plan.get("actor_binding") or {}
    node_path, slot_idx = b.get("card_mesh_node"), b.get("card_front_mat_idx")
    mat_name = None
    for c in plan["components"]:
        if c.get("path") != node_path:
            continue
        for s in c.get("material_slots", []):
            if s.get("slot") == slot_idx:
                mat_name = s.get("material")
    if not mat_name:
        return default, "default（无 card front 槽）"
    for n, _key, path in walk_with_key(hierarchy):
        if path != node_path:
            continue
        for rr in n.get("renderers") or []:
            for m in rr.get("materials") or []:
                if m.get("name") != mat_name:
                    continue
                v = (m.get("floats") or {}).get("_MiddleValue")
                if v is not None:
                    return float(v), f"material:{mat_name}._MiddleValue"
    return default, f"default（{mat_name} 未带 _MiddleValue）"


def _compile_dualclass_color(plan: dict, card, pk: str) -> dict | None:
    """① 双职业分裂帧（old_render/components/multiclass.py:75 行为面转写）：
    2 职业卡 composite 图集复指正典写点槽（调用位=class_color_canonical 之后——
    canonical 以 atlas_ref 相等判写点，composite 改写破坏其判定故放后）。
    LOCATION No_Gem 仅 colors[0] 单图集（Actor.cs:Actor.SetMaterialWithTexture）。非 2 职业卡 None。

    `atlas_ref` 分轴（2026-10-29 dualclass-no-gem-ref）：**No_Gem 槽保留真 ref**——引擎
    该槽写入的就是 colors[0] 的 `_DualClass` 图集本体（同一 Texture2D，`.cs:6860-6863`），
    其资产 ref 正是 `old_ref`（`class_color.atlas_ref` = `get_texture(card_type, colors[0])`，
    双职业时 colors[0]=`DualClass(c0)`），故这里不动它；改写成 composite 假 ref 只断
    身份链（`entry_for_ref` 解析不到 → 静默落 mip0，将来该图集升链即失守）。非 No_Gem 槽
    维持 composite 假 ref：dual-class 源图集 mips=1，引擎在该槽也无链可采（decomp 结论），
    `composite:` 与真 ref 在 mip 轴等价、且这是我方内存拼接的唯一标识。"""
    mask = card.tags[GameTag.MULTIPLE_CLASSES]
    if mask <= 0:
        return None
    family = _multiclass_family_for(pk)   # 双职业 tag 在场才解析（缺行在此响亮）
    if family is None:
        return None   # 显式无图集写点面（_FAMILY_NO_SURFACE 分类账）
    classes = [int(c) for c in card.classes]   # GetClasses 升序
    if len(classes) != 2:
        return {"applied": False, "reason": f"classes={len(classes)}（≥3→[GENERIC]）"}
    cts = [_switcher.get_color_type_for_dual_class(c) for c in classes]
    # frame 覆盖轴（contract E，2026-11-06）：覆盖在场=拼图源整体换覆盖图——
    # 数据轴两图集解码短路（覆盖=整帧纹理，用户给的不是半幅图集）；composite(ov,ov)
    # 恒等（右半 paste 自身），memo 键含覆盖内容指纹（_dualclass_composite）→ 同
    # family/ct 键异覆盖内容不串图（外审「同进程不同 frame 覆盖会串图」闭合）。
    fov = _ovr.frame_of(card)
    if fov is not None:
        atlas0 = atlas1 = fov["img"]
    else:
        atlas0 = _color.atlas(family, cts[0])
        atlas1 = _color.atlas(family, cts[1])
    # 拼缝=_MiddleValue（材质序列化常量；shader Custom/Card/UnlitTextureDualClass 直读）
    hierarchy = _frames.scene_for(pk)["hierarchy"]
    middle_value, mv_source = _middle_value_for(plan, hierarchy)
    composite = _dualclass_composite(family, cts[0], cts[1], atlas0, atlas1, middle_value)
    old_ref = (plan.get("class_color") or {}).get("atlas_ref")
    composite_ref = fov["ref"] if fov is not None \
        else f"composite:{family}:{cts[0]:02d}+{cts[1]:02d}"
    touched: list[str] = []
    for c in plan["components"]:
        is_no_gem = pk == "Card_Hand_Location" and c.get("node") == "No_Gem_Mesh"
        for s in c.get("material_slots", []):
            rt = s.get("_MainTex_runtime")
            if rt and old_ref and rt.get("atlas_ref") == old_ref:
                if is_no_gem:
                    rt["image"] = atlas0   # LOCATION No_Gem 尾段写 colors[0]；atlas_ref 留真 ref
                else:
                    rt["image"] = composite
                    rt["atlas_ref"] = composite_ref
                touched.append(f"{c['path']}[{s.get('slot')}]")
        mo = c.get("material_override") or {}
        if mo.get("_MainTex_runtime", {}).get("atlas_ref") == old_ref:
            mo["_MainTex_runtime"]["image"] = atlas0 if is_no_gem else composite
            if not is_no_gem:
                mo["_MainTex_runtime"]["atlas_ref"] = composite_ref
            touched.append(f"{c['path']}(mo)")
    cc = plan.setdefault("class_color", {})
    account = {
        "applied": True,
        "classes": classes, "color_types": cts,
        "atlas_colors0": fov["ref"] if fov is not None else str(atlas0),
        "atlas_colors1": fov["ref"] if fov is not None else str(atlas1),
        "atlas_composite": (f"frame 覆盖整帧（{fov['ref']}；composite(ov,ov)=ov 逐位）"
                            if fov is not None else
                            f"内存 composite {family} {cts[0]:02d}+{cts[1]:02d}"),
        "split": f"x=ceil(w×{middle_value:.6f})（_MiddleValue 直读；"
                 f"shader Custom/Card/UnlitTextureDualClass 硬 step）",
        "middle_value": middle_value, "middle_value_source": mv_source,
        "touched": touched,
        "source": "Actor.cs:Actor.UpdateCardColor 多职业分支 + 6729-6787 写点 + CardColorSwitcher.cs:"
                  "121-149/151-169",
    }
    if fov is not None:
        account["frame_override"] = {"ref": fov["ref"], "sha256": fov["sha256"],
                                     "path": fov["path"]}
    cc["dualclass"] = account
    return account


def _compile_multiclass_generic_color(plan: dict, card, pk: str) -> dict | None:
    """② ≥3 类 GENERIC 框（old multiclass.py:134 行为面转写）：GENERIC 单图集复指
    正典写点槽（CardColorSwitcher.cs:CardColorSwitcher.GetCardColorTypeForClasses count==1 支路：_EnableDualClass=0、
    无 _SecondTex——写点全集与单职业同）。与 2 类分裂支路互斥。"""
    if not card.has_three_or_more_classes:
        return None
    family = _multiclass_family_for(pk)   # 3+ 类在场才解析（缺行在此响亮）
    if family is None:
        return None   # 显式无图集写点面（_FAMILY_NO_SURFACE 分类账）
    generic_ct = _switcher.get_color_type_for_class(int(CardClass.NEUTRAL))
    """GENERIC 槽=活值（class-axis 收口 2026-11-05：裸 0 手抄退役——引擎语义即
    GetColorTypeForClass(NEUTRAL)=GENERIC，槽位随活表供货不硬编码）。
    CardColorSwitcher.cs:CardColorSwitcher.GetColorTypeForClass default 臂。"""
    # frame 覆盖轴（contract E）：覆盖在场=GENERIC 写点同换覆盖图（覆盖全分支一致——
    # 3+ 职业分支不再被数据轴 GENERIC 图集覆盖）。
    fov = _ovr.frame_of(card)
    if fov is not None:
        generic_img = fov["img"]
        generic_ref = fov["ref"]
    else:
        generic_img = _color.atlas(family, generic_ct)
        generic_ref = _color.probe()[family][generic_ct]
    old_ref = (plan.get("class_color") or {}).get("atlas_ref")
    touched: list[str] = []
    for c in plan["components"]:
        for s in c.get("material_slots", []):
            rt = s.get("_MainTex_runtime")
            if rt and old_ref and rt.get("atlas_ref") == old_ref:
                rt["image"] = generic_img
                rt["atlas_ref"] = generic_ref
                touched.append(f"{c['path']}[{s.get('slot')}]→GENERIC")
        mo = c.get("material_override") or {}
        if mo.get("_MainTex_runtime", {}).get("atlas_ref") == old_ref:
            mo["_MainTex_runtime"]["image"] = generic_img
            mo["_MainTex_runtime"]["atlas_ref"] = generic_ref
            touched.append(f"{c['path']}(mo)→GENERIC")
    cc = plan.setdefault("class_color", {})
    account = {
        "applied": True,
        "classes": [int(c) for c in card.classes],
        "color_types": [generic_ct],
        "atlas_generic": generic_ref,
        "touched": touched,
        "source": "CardColorSwitcher.cs:CardColorSwitcher.GetCardColorTypeForClasses（Count>=3→[TYPE_GENERIC]）+ Actor.cs:"
                  "6729-6731/6735/6760/6767/6790（count==1 支路写点）",
    }
    if fov is not None:
        account["frame_override"] = {"ref": fov["ref"], "sha256": fov["sha256"],
                                     "path": fov["path"]}
    cc["multiclass_generic"] = account
    return account


def _bake_uv_transform(src, scale: list, offset: list):
    """ST 烘焙（内存面）：dst(uv0)=src(uv0·scale+offset)（wrap 重复），双线性采样
    保持软边（old multiclass._bake_uv_transform :227 逐字；进程 memo）。

    memo 键内容位（contract E，2026-11-06）：旧键 `f"{src_name}-{scale}-{offset}"`
    在 src 为纯内存对象时退化为 `"mem-…"`——不同内存源同 scale/offset 共享一格
    （比外审 _COMPOSITE_MEMO 项更宽的串图位）。"mem" 回落位现补内容指纹
    （`mem-<sha16>`），键与像素一一对应；文件身份位（stem/filename）语义不变
    （同文件同内容=进程内约定，键面照旧）。"""
    src_name = getattr(src, "stem", None) or getattr(src, "filename", "") or "mem"
    if src_name == "mem":
        src_name = f"mem-{_img_fp(src)}"   # 纯内存源无文件身份 → 内容指纹入键
    mkey = f"{src_name}-{scale}-{offset}".replace(" ", "")
    if mkey in _UVT_MEMO:
        return _UVT_MEMO[mkey]
    img = (src if isinstance(src, Image.Image) else Image.open(src).convert("RGBA"))
    img = np.asarray(img.convert("RGBA"), dtype=np.float64)
    H, W = img.shape[:2]
    sx, sy = float(scale[0]), float(scale[1])
    ox, oy = float(offset[0]), float(offset[1])
    u_src = (np.arange(W) + 0.5) / W * sx + ox
    v_src = (np.arange(H) + 0.5) / H * sy + oy
    col = u_src * W - 0.5
    row = (1.0 - v_src) * H - 0.5
    c0 = np.floor(col).astype(np.int64)
    r0 = np.floor(row).astype(np.int64)
    fx = col - c0
    fy = row - r0
    c0w = c0 % W
    c1w = (c0 + 1) % W
    r0w = r0 % H
    r1w = (r0 + 1) % H
    fx = fx[None, :, None]
    fy = fy[:, None, None]
    out = (img[np.ix_(r0w, c0w)] * (1 - fx) * (1 - fy)
           + img[np.ix_(r0w, c1w)] * fx * (1 - fy)
           + img[np.ix_(r1w, c0w)] * (1 - fx) * fy
           + img[np.ix_(r1w, c1w)] * fx * fy)
    out_img = Image.fromarray(np.rint(np.clip(out, 0, 255)).astype(np.uint8))
    _UVT_MEMO[mkey] = out_img
    return out_img


def _compile_multiclass_ribbon(plan: dict, card, pk: str, hierarchy: dict) -> dict | None:
    """② ≥3 职业右缘缎带（old multiclass.py:265 行为面转写；UpdateMulticlassRibbon
    Actor.cs:Actor.UpdateMulticlassRibbon 激活式——帧 prefab 内置 GO SetActive，compile_rune_banner
    同族翻转语义）。激活面 = Mesh+Shadow（Signature 变体 activeSelf=false 不激活）。"""
    classes = [int(c) for c in card.classes]
    if not card.has_three_or_more_classes:
        return None
    base = _multiclass_ribbon_base_for(pk)   # 3+ 类在场才解析（缺行在此响亮）
    if base is None:
        return None   # prefab 无缎带 GO=引擎 (bool)m_multiclassRibbon 门关（分类账）
    nodes_by_path = {}
    for n, _wk, p in walk_with_key(hierarchy):
        nodes_by_path[p] = n
    tex_img = ability_kit().textures[f"{_RIBBON_TEX_NAME}.png"]
    activated: list[str] = []
    for rel in (_RIBBON_MESH_REL, _RIBBON_SHADOW_REL):
        p = f"{base}/{rel}"
        nd = nodes_by_path.get(p)
        assert nd is not None, f"{pk}: 帧层级无缎带节点 {p!r}（recon 口径不符）"
        rr = (nd.get("renderers") or [{}])[0]
        mat0 = (rr.get("materials") or [{}])[0]
        is_shadow = rel == _RIBBON_SHADOW_REL
        slot = {"slot": 0, "material": mat0.get("name") or
                ("Multiclass_Ribbon_shadow" if is_shadow else "Multiclass_Ribbon")}
        st = ((mat0.get("tex") or {}).get("_MainTex") or {})
        sc_, of_ = st.get("scale"), st.get("offset")
        if is_shadow and sc_ and of_ and (list(sc_), list(of_)) != ([1.0, 1.0], [0.0, 0.0]):
            slot["_MainTex_runtime"] = {
                "image": _bake_uv_transform(tex_img, list(sc_), list(of_)),
                "source": f"{slot['material']} _MainTex ST={sc_}/{of_} 烘焙（内存面）"}
        else:
            slot["_MainTex_runtime"] = {
                "image": tex_img,
                "source": "帧 recon 材质 _MainTex（ST 恒等）"}
        comp = {"path": p, "node": p.split("/")[-1],
                "visible": True, "raster": True,
                "material_slots": [slot],
                "visibility_rule": {
                    "rule": "GetClasses().Count > 2 → m_multiclassRibbon SetActive",
                    "source": "Actor.cs:Actor.UpdateMulticlassRibbon UpdateMulticlassRibbon（调用位 :4921）",
                    "tags_used": [int(GameTag.MULTIPLE_CLASSES)]},
                "material_override": ({"blend": "multiply",
                                       "_tint_rgb": [1.0, 1.0, 1.0],
                                       "source": "Multiclass_Ribbon_shadow 主色 pass（材质态表）"}
                                      if is_shadow
                                      else {"_tint_rgb": [1.0, 1.0, 1.0],
                                            "source": "序列化 _Color 纯红系美编遗留，shader"
                                                      "（PS o0=tex×顶点色）不消费 _Color"})}
        if comp["material_override"] is None:
            comp.pop("material_override")
        existing = next((c for c in plan["components"] if c["path"] == p), None)
        if existing is not None:
            # compile 已收该节点（序列化隐藏态）——SetActive 语义 = 翻转可见性，材质账以
            # 序列化 recon 为准不覆写（_MainTex_runtime 仅既有槽缺 file 时补）
            existing["visible"] = True
            existing["raster"] = True
            existing["visibility_rule"] = comp["visibility_rule"]
            for s in existing.get("material_slots", []):
                if not (s.get("_MainTex_runtime") or {}).get("file"):
                    s["_MainTex_runtime"] = dict(slot["_MainTex_runtime"])
            if is_shadow:
                existing.setdefault("material_override", {}).setdefault(
                    "blend", comp["material_override"]["blend"])
            existing.setdefault("material_override", {})["_tint_rgb"] = [1.0, 1.0, 1.0]
            existing["material_override"].setdefault("source", comp["material_override"]["source"])
        else:
            plan["components"].append(comp)
        activated.append(p)
    account = {"applied": True, "classes": classes, "base": base,
               "activated": activated, "signature_variants": "activeSelf=false 不激活（NORMAL）",
               "source": "compile_multiclass_ribbon（multiclass-render 2026-10-05；"
                         "Actor.cs:Actor.UpdateMulticlassRibbon）"}
    plan["multiclass_ribbon"] = account
    return account


def _suppress_disabled(plan: dict, hierarchy) -> int:
    """renderer.enabled=false 压制（old_render/components/portrait.py:56 行为面
    转写；dk_render :351-364 同式——ability 链既有语义，统一入口对全部帧型施加）。

    `enabled_override` 豁免（elite-dragon-shadow 2026-10-24）：m_eliteObject 子树
    （龙/龙影）展示态由 Actor.UpdateEliteComponent → RenderUtils.EnableRenderers
    (includeInactive:true) 运行时无条件覆写——序列化 enabled 不是展示态，计划
    visible 已按 IsElite() 门控，压制段跳过（否则 ELITE 影子件被序列化值误杀）。"""
    enabled = {}
    for n, _key, p in walk_with_key(hierarchy):
        rr = n.get("renderers") or []
        if rr:
            enabled[p] = bool(rr[0].get("enabled", True))
    n_sup = 0
    for c in plan["components"]:
        if c.get("enabled_override"):
            continue
        if enabled.get(c["path"]) is False and c.get("visible"):
            c["visible"] = False
            c["raster"] = False
            n_sup += 1
    return n_sup


# ============================================================================
# 组装总入口（render_with :586-688；S1 装配账消费→compile→prep→接线→execute→V-pass）
# ============================================================================


def _in_session(fn):
    """会话=入口层独占（卡：gate/render_card 驱动循环）——每渲一 session（supply
    @item memo 作用域，解码物不跨卡；old render_card._in_session 同形）。"""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        from eidolon.core.supply.machine import session

        with session():
            return fn(*args, **kwargs)

    return wrapper


@invented(reason="公开资产覆盖接缝（contract E）：Card 覆盖座位→plan 就地落位的复写/守卫步——引擎无离线覆盖对位（覆盖=卡级渲染输入，D 不变量）", counterpart=None)
def _apply_asset_overrides(plan: dict, card: Card, pk: str) -> dict | None:
    """资产覆盖落 plan（contract E，2026-11-06；render_with 内联步，compile 后即刻）：

    * **frame**：compile 期已把覆盖嵌入 class_color（compiler._class_color——写点槽
      image/ref 即覆盖）；本步守卫写点面——`class_color.applied=False`（premium 染色
      帧/HERO_POWER/play 无写点组）=覆盖无消费位，**响亮**（禁静默 no-op，外审
      「覆盖会静默无效」病灶）。scene/kit 缓存零触碰（plan 每卡新构）。
    * **portrait**：compile 期槽位 image=数据轴 img 对象（_slot_write 直写引用）；
      本步按**对象身份**把命中运行时槽复写为覆盖图（frame 双职业/3+ 分支只动
      atlas_ref 命中槽，与肖像槽不相交），plan.portrait.img 同步换覆盖+`override`
      账（execute 期肖像 mip 链按此跳过——覆盖内容与 CardDef 链必然不同源）。
      零命中=响亮（无肖像槽帧收覆盖座=意图无落地）。
    * **watermark**：无早落位——覆盖/强制经 update_watermark 流入 V-pass
      （watermark.py），无 desc 层的响亮拒绝在 render_with 主体（本步后方，
      acc["plan_frame"]["desc_frame"] 判定）。

    返回覆盖账 dict（result["asset_overrides"] 消费；无覆盖=None，零新键零行为
    ——opt-in 判据面）。"""
    acc: dict = {}
    fov = _ovr.frame_of(card)
    if fov is not None:
        cc = plan.get("class_color") or {}
        if not cc.get("applied"):
            raise ValueError(
                f"frame 覆盖无落地写点面（pk={pk} class_color.applied=False："
                f"{cc.get('apply') or 'premium/无图集写点帧'}）——覆盖轴=类色图集写点"
                "平面（SetMaterialWithTexture 写点），premium 染色/无写点帧无消费位，"
                "禁静默 no-op（contract E 响亮校验）")
        acc["frame"] = {"ref": fov["ref"], "sha256": fov["sha256"], "path": fov["path"]}
    pov = _ovr.portrait_of(card)
    if pov is not None:
        port = plan.get("portrait") or {}
        old = port.get("img")
        n = 0
        for c in plan["components"]:
            for s in c.get("material_slots", []):
                rt = s.get("_MainTex_runtime")
                if rt and rt.get("image") is old:
                    rt["image"] = pov["img"]
                    n += 1
            mo = c.get("material_override")
            rt = mo.get("_MainTex_runtime") if isinstance(mo, dict) else None
            if rt and rt.get("image") is old:
                rt["image"] = pov["img"]
                n += 1
        if n == 0 or old is None:
            raise ValueError(
                f"portrait 覆盖无落地槽位（pk={pk}：plan 运行时槽零 image 身份命中）"
                "——覆盖意图无消费位，禁静默 no-op（contract E 响亮校验）")
        port["img"] = pov["img"]
        port["override"] = {"ref": pov["ref"], "sha256": pov["sha256"],
                            "path": pov["path"], "slots_rewritten": n}
        acc["portrait"] = dict(port["override"])
    return acc or None


@invented(reason="同步线性编排离线等价（OnActorLoaded 回调链不复刻，形态边界 §0.4）", counterpart="Card.cs OnActorLoaded→UpdateAllComponents")
@_in_session
def render_with(card_or_dbf, cfg: RenderConfig, t_phase: float, *,
                zone: str = "HAND", notext: bool = True, textonly: bool = False,
                out_png=None, session_time: float | None = None) -> dict:
    """S11 组装总入口（consumer-v2 段2 全量移植已完成：执行半与 compile/prep/
    frames/switcher/injectors/portrait/gems/watermark/uber_text 全部住本包，
    old_render 已退役（tag old-render-freeze-20261029 保留 oracle）；own 六小表+
    新 raster 已改键 prefab，穿线见
    frame_desc_for）。
    形态锚=old render_with :586（编排形态对位——OnActorLoaded 回调链不复刻，
    见形态边界 §0.4）；正典消费=canonical_cfg 缺省。十一=骨架 §11 表逐行：
    ①resolve（S1 assemble 消费）→②compile→③prep→④接线七件→
    ⑤-⑩update_all_components→⑪V-pass。

    card_or_dbf=Card 门面实例（contract C 判据 1/2 四入口收 Card，2026-11-06：
    传 Card 时整链零 from_dbf——assemble→resolve_prefab→compile_plan 全程复用
    本对象，desc/assets/tag 覆盖就地生效）|数字 dbf id（旧路径零变化，内部装载
    点照旧单点装载）；结果账 dbf 键=canonical 数字串（int(card.dbf_id)）。

    t_phase **必填**（text-default-phase 2026-10-22）：会话相位是逐卡参考量
    （manifest 行 t，schema v3；历史语料分布 0.1472–0.2050），不是全局常数——本层不设缺省，
    漏传立刻 TypeError。无参考相位的卡（legacy 桥代 t=null）由调用方显式传
    eidolon.core.render.params.DEFAULT_SESSION_T。

    session_time（2026-10-23 gold-frame-phase）=**会话冻结时刻/20**（Unity `_Time.x`
    全量值，非 t=(P/20)%0.2 的余数）；只喂 shader 时间项（现役消费者=金框反射层）。
    None → 降级用 t_phase 并在 log 记账（旧调用方行为面；37.0 语料真实值见
    data/card-image/<代>/capture.json sessions[].frozen_p / 20）。

    族账锚=Actor.cs（模块族账；本件发明——编排形态见装饰器 reason/counterpart）。
    """
    assert not (notext and textonly), \
        "notext ∧ textonly 同开=零绘制（引擎注入器同款互斥，AlphaTool.Renderer.cs:AlphaTool.RenderAndSaveImpl）"
    _card_arg, dbf_id = as_card_or_dbf(card_or_dbf)   # dbf 键归一（card 轴=canonical 数字串）
    cfg.apply()
    _raster.reset_memo()   # 每渲必 Reset（tex 数组 id 可被复用，防跨渲污染）
    # ---- ①S1 装配账消费（批21 card.assemble：resolve/语境 mode/scene/注入产物单流）----
    acc = _card.assemble(card_or_dbf, zone, use_bg_style=cfg.use_bg_style)
    pk = acc["prefab"]   # consumer-v2：穿线=prefab（frame_key 层消亡）
    card = acc["identity"]["card"]
    bg_mode = acc["bg_mode"]["mode"]

    # ---- ②compile（game/compiler.py 统一编译器）+ ③prep（S6 相位/费用语义注入）----
    plan = _compiler.compile_plan(pk, dbf_id, card)
    plan["_card_runtime"] = card   # compile 家族消费（badges/class_color canonical）；非正典账面字段
    plan["_bg_style"] = bg_mode    # 语境 mode 消费口
    # ---- 资产覆盖接缝（contract E，2026-11-06）：Card 覆盖座位落 plan（frame 写点面
    #      守卫/portrait 槽复写）+ watermark 无 desc 层早响亮（渲染成本前置拒绝）。
    #      无覆盖=全段 no-op 零新键（opt-in；dbf 旧路径座位恒缺省 None/False）----
    _asset_overrides = _apply_asset_overrides(plan, card, pk)
    if (card.watermark_asset is not None or card.watermark_force) \
            and acc["plan_frame"]["desc_frame"] is None:
        raise ValueError(
            f"watermark 覆盖/强制无 desc 层（pk={pk} desc_frame=None）——垫图 V-pass "
            "无消费位，禁静默 skip（contract E 响亮校验；HIDE_WATERMARK 忽略="
            "Card.watermark_force，alpha 两档 0/99-128 保真语义见 watermark.py）")
    _compiler.prep_plan(plan, t_phase=t_phase, notext=notext, frame_key=pk,
                        textonly=textonly, card=card, session_time=session_time)
    # 会话冻结时刻/20（_Time.x 全量；金框反射层时间项唯一来源）
    plan["_shader_time"] = (float(session_time) if session_time is not None
                            else float(t_phase))
    plan["_shader_time_source"] = ("capture frozen_p/20" if session_time is not None
                                   else "t_phase（降级：代级冻结时刻缺失）")

    # ---- ④接线七件（:632-650 执行序：bacon→类色 canonical→双职业→GENERIC→符文→
    #      压制→缎带；符文原位应用=批20 apply_rune_banner）----
    bacon = None if textonly else _bacon_plan_patch(plan, card, pk)
    cc = {"mode": "skip"}
    if cfg.class_color == "canonical" and not textonly:
        cc = _switcher.class_color_canonical(plan, pk)
    dual = None if textonly else _compile_dualclass_color(plan, card, pk)
    multi_gen = None if textonly else _compile_multiclass_generic_color(plan, card, pk)
    rune_product = acc["plan_frame"]["injections"]["rune_banner"]
    if rune_product is not None and not textonly:
        _injectors.apply_rune_banner(plan, rune_product)
    hierarchy = _frames.scene_for(pk)["hierarchy"]
    if frame_desc_for(pk).get("suppress") and not textonly:
        _suppress_disabled(plan, hierarchy)
    ribbon = None if textonly else _compile_multiclass_ribbon(plan, card, pk, hierarchy)

    # execute 入参穿线：注入四件产物（:357-388 执行序；textonly 由 execute 跳过）
    plan["_injection_products"] = [
        acc["plan_frame"]["injections"][k]
        for k in ("badges", "faction_banner", "tier_spell", "frame_rig")
        if acc["plan_frame"]["injections"][k] is not None]

    # ---- 文字延后位（origin 组合序修正 2026-10-20）----
    # 引擎序=desc 材质（含水印）pass 先、文字独立 mesh（renderQueue 后移）后
    # （Actor.cs:Actor.UpdateWatermark × UberText.cs:UberText.UpdateRenderQueue）：
    # origin 链把文字层延后到 ⑪V-pass 之后最后合成。notext/textonly 不置位、走原
    # 路径（notext 无字；textonly 文字即输出、无 V-pass），输出逐位不变。
    defer_text = (not notext) and (not textonly)
    if defer_text:
        plan["_defer_text"] = True

    # ---- ⑤-⑩execute ----
    # 直合需要 full 渲的 final zbuf（⑪深度门控写域）：单元素 list 出参捕引用，
    # 零拷贝；仅在直合路径确实会跑（⑪四条件）时请求。
    _zbuf_cap = ([] if (out_png is not None and cfg.watermark and not textonly
                        and getattr(cfg, "vpass_direct", False)) else None)
    img, log = update_all_components(plan, pk, cfg, out_zbuf=_zbuf_cap)
    result = {"dbf": str(dbf_id), "prefab": pk,
              "zone": zone, "t": t_phase,
              "config": cfg.name, "image": img, "log": log, "class_color": cc,
              "bg_style": {"mode": bg_mode, "source": acc["bg_mode"]["source"],
                           "set_id": card.set_id, "tech_level": card.tech_level}}
    if _asset_overrides is not None:
        result["asset_overrides"] = _asset_overrides   # contract E 覆盖账（无覆盖零新键）
    if bacon is not None:
        result["bacon_patch"] = bacon
    if dual is not None:
        result["dualclass"] = dual
    if multi_gen is not None:
        result["multiclass_generic"] = multi_gen
    if ribbon is not None:
        result["multiclass_ribbon"] = ribbon
    # ---- ⑪V-pass（批17 apply_desc_watermark 兑现；post 差分）----
    # 延后链下本段跑在**无字底图**上：写域不再需要排除文字像素（text_cov 退役），
    # desc 面全体参与替换；文字层随后最后合成（下一段）。
    if out_png is not None:
        out_png.parent.mkdir(parents=True, exist_ok=True)
        comp = comp_of(img)          # RGB = 黑底合成（正典交付面）
        # α 面（2026-10-16）：引擎契约 = 带剪影 α 的 RGBA（SnapshotCamera 三遍差分求 α，
        # tools/alphatool/SnapshotCamera.cs:SnapshotCamera.TakeSnapshotSimple）。RGB 保持黑底合成不变——按 RGB 读取的
        # 消费面（report 直取 RGB、gate 的 cand RGB）逐位不变，仅新增 α 通道。
        out_img = comp.convert("RGBA")
        out_img.putalpha(img.convert("RGBA").getchannel("A"))
        out_img.save(out_png)
        if cfg.watermark and not textonly:
            def _render_variant(p):
                _raster.reset_memo()   # 变体渲同样逐次 Reset（id 复用防污染）
                img2, log2 = update_all_components(p, pk, cfg)
                return p, img2, log2
            result["watermark"] = _watermark.apply_desc_watermark(
                out_png, plan, pk, str(dbf_id), cfg, render_fn=_render_variant,
                card=card, full_img=comp,
                # 传**列表**：1x 收 1 个 zbuf、4x 收 4 个逐样本 zbuf，由 V-pass 按
                # cfg.supersample 归一（per-sample 深度门；接线单点）。
                zbuf_final=_zbuf_cap)
        elif cfg.watermark and textonly:
            if card.watermark_asset is not None or card.watermark_force:
                raise ValueError(
                    f"watermark 覆盖/强制 × textonly（pk={pk}）——textonly 渲染无垫图 "
                    "V-pass 消费位，禁静默 skip（contract E 响亮校验）")
            result["watermark"] = {"pass": "skipped (textonly：无 desc 面，垫图 V-pass 无消费位)"}

    # ---- 文字层最后合成（引擎序：⑪V-pass 之后；仅 origin 延后链）----
    if defer_text:
        # 无 render=True 文字条目的帧（如 hero_play_bacon：_TEXT_SETUP 无此键）不建层
        # ——与 update_all_components 末尾同守卫，避免对无文字帧白调 text_setup_for。
        layers, text_alpha = [], None
        if any(e.get("render") for e in plan["texts"]):
            layers, text_alpha = _text_layers(_frames.scene_for(pk)["meta"], plan, pk)
            plan["_text_alpha"] = text_alpha   # 诊断位（V-pass 不再消费）
        for layer in layers:
            img.alpha_composite(layer)     # result["image"] 仍=带字底图（旧语义）
        if out_png is not None:
            if (result.get("watermark") or {}).get("pass") == "applied":
                # V-pass applied：out_png 已被写成**保留剪影 α 的 RGBA** 无字终图。
                # 贴字在 α=255 的工作面上做（RGB=黑底合成，保持交付 RGB 语义与文字
                # 最后合成的直式 T·αt + P·(1−αt)）；α 必须是**文字层 source-over
                # 底图剪影**——数字角色 fit=0 天然外溢（S1/S2），直接盖回剪影会把
                # 溢出卡面剪影的像素 α 清零（RGB 仍正确，报告按 RGBA 贴深色底时表现
                # 为数字被切）。存回 RGBA——V-pass 写点不再把 α 冲掉。
                final = Image.open(out_png).convert("RGBA")
                base_alpha = final.getchannel("A").copy()
                work = final.convert("RGB").convert("RGBA")
                # α = 文字层 source-over 底图剪影（数字溢出剪影时 α 必须保留）。
                alpha_work = Image.new("RGBA", work.size, (0, 0, 0, 0))
                alpha_work.putalpha(base_alpha)
                for layer in layers:
                    work.alpha_composite(layer)
                    alpha_work.alpha_composite(layer)
                work.putalpha(alpha_work.getchannel("A"))
                work.save(out_png)
            else:
                # V-pass skipped（无 desc 面/wm None/alpha0）：out_png 仍是初始 RGBA
                # 无字图；按旧式（黑底合成 + 剪影 α）重写为带字 RGBA——无 V-pass
                # 路径的「延后+回贴无损」判据=与旧行为逐位一致。
                comp2 = comp_of(img)
                out_img2 = comp2.convert("RGBA")
                out_img2.putalpha(img.convert("RGBA").getchannel("A"))
                out_img2.save(out_png)

    # ---- 字形供给 v3 响亮账（glyph-supply-v3 判据 2/4；每渲一 drain，不跨卡）----
    # 缺字/供给分歧事件 → log["missing_glyphs"]（gate_report 逐卡缺字清单）；
    # 字体哈希 → log["fonts"]（gate_report 漂移追溯位；进程累计快照）。
    from eidolon.core.render.text import glyph_supply as _glyph_supply
    _missing = _glyph_supply.drain_missing()
    if _missing:
        log["missing_glyphs"] = _missing
    log["fonts"] = _glyph_supply.font_report()
    return result

# ============================================================================
# form 轴（批量面形态词表：三态；2026-10-30 render-form-axis）
# ============================================================================

RenderForm = Literal["plain", "bg", "hero"]
"""形态词表（=gate `zone_when.stem_form(stem, None)` 返回值域，同一词表两 face 消费）：
bg=酒馆非英雄（bgs 装饰真生效，新账显式名）/ hero=英雄采集位（play）/ plain=裸 stem
——**旧账兼容歧义形态**（constructed 手牌，或 10-28 前旧账裸名的 bacon 行别名，如
120259/98918 set=1453 裸名），故 plain 解码走数据推导。hero_bg 类型层不可表达——
HERO 卡 bgs 惰性（2026-10-30 用户裁定，机制与逐字节实测账=
docs/notes/corpus-stem-naming.md），名字面三态词表已把该组合吸收。"""

_FORM_DECODE = {"plain": (None, "HAND"), "bg": (True, "HAND"), "hero": (False, "PLAY")}
"""form → (use_bg_style, zone) 解码表。plain=None（数据推导）：裸名歧义（旧账 bacon
别名存在），显式 constructed 会被 full 门证伪（120259/98918 z_cost_bg 1.67→81.8，
2026-10-31 render-form-axis 实测）——推导危险面已被词表归位拆除（新账 bacon 全带
_bg 显式名；105108 五卡课=bacon 卡必须 _bg 命名，账=docs/notes/corpus-stem-naming.md）。
hero=显式 False：_hero 名无歧义（⟺ HERO 卡），mode 轴对 HERO 惰性（已证）。"""


@invented(reason="form 三态解码单点（我方形态词表消费形）：游戏侧无 form 入口形态——对拍原始轴=render_with 的 zone+cfg.use_bg_style 显式覆写", counterpart=None)
def resolve_form(card_or_dbf, form: str) -> tuple["bool | None", str]:
    """form 三态 → (use_bg_style, zone)，HERO×bg 守卫（批量门面与薄壳共用单点）。

    card_or_dbf=Card 门面实例（contract C 判据 1/2，2026-11-06：守卫吃 card.cardtype，
    整链零 from_dbf）|数字 dbf id（旧路径零变化，守卫照旧单点装载）。
    bg（显式开盾徽语境）只对非英雄 bacon 卡是真态——HERO 卡收 bg=请求一个不存在的
    独立态（游戏侧 bgs 装饰分支按 cardtype 分派，HERO 一个都不命中；逐字节实测
    见 docs/notes/corpus-stem-naming.md），响亮拒绝而非静默渲出重复图。非英雄收
    hero 不在此拒：PLAY 区非英雄=未实现（resolve_prefab 的 PREFAB_SPECS 行成员
    tripwire 深层响亮）——非法与未实现分治。
    """
    card, dbf_id = as_card_or_dbf(card_or_dbf)
    decode = _FORM_DECODE.get(form)
    if decode is None:
        raise ValueError(f"form 非法：{form!r}（词表三态 plain/bg/hero）")
    if form == "bg":
        cardtype = int(card.cardtype) if card is not None \
            else int(Card.from_dbf(int(dbf_id)).cardtype)
        if cardtype == int(CardType.HERO):
            raise ValueError(
                f"dbf={dbf_id} 是 HERO 卡，form='bg' 非法——HERO 卡 bgs 惰性，"
                "hero 与 bg 不可同真（见 docs/notes/corpus-stem-naming.md；"
                "对拍原始轴请走 render_with 显式 cfg.use_bg_style）")
    return decode


@invented(reason="variant/form 薄壳消费形（我方诊断轴 notext/textonly+调用面）：游戏侧无此入口形态", counterpart=None)
def render_card(dbf_id: str, *, variant: str = "origin", form: RenderForm,
                t: float, out_png=None, session_time: float | None = None) -> dict:
    """正典薄壳消费形（old render_card :556 对位；variant/form 串面=旧 StrEnum
    语义继承位；form 解码与守卫单点=resolve_form，style 混轴枚举已退役
    （2026-10-30 render-form-axis））。

    t **必填**（text-default-phase 2026-10-22）：逐卡会话相位，漏传立刻 TypeError；
    无参考卡显式传 eidolon.core.render.params.DEFAULT_SESSION_T。

    族账锚=Actor.cs（模块族账；本件发明——薄壳包装见装饰器 reason）。
    """
    flags = {"origin": (False, False), "notext": (True, False), "textonly": (False, True)}
    notext, textonly = flags[variant]
    use_bg_style, zone = resolve_form(dbf_id, form)
    cfg = canonical_cfg()
    cfg.use_bg_style = use_bg_style
    return render_with(dbf_id, cfg, t_phase=t, zone=zone,
                       notext=notext, textonly=textonly, out_png=out_png,
                       session_time=session_time)
