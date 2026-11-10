"""frames — 帧实例化与场景装载（段 S3）。

游戏锚：AssetLoader.InstantiatePrefab(actorPath, cb)（Card.cs:Card.LoadActor——回调驱动，
走查档 §0.4.1 形态边界不复刻）· Card.OnActorLoaded → SetEntity/SetCardDef/
UpdateAllComponents（Card.cs:Card.OnActorLoaded 区段=组件装配入口）· prefab 序列化对象图
（Transform 层级/MeshFilter/MeshRenderer/UberText 组件=场景几何与材质槽真值）·
prefab 根位置=场景摆位残留（引擎区域布局覆写根位置；快照根位姿恒等覆写，
hero 帧=SnapshotCamera.PrepareObject（tools/alphatool/SnapshotCamera.cs——注入器源码，
非 decomp）无条件归零正典）。

我方对位（「实例化」=kit 提取+场景缓存，walk-skeleton §3）：
  * scene_for（old_frames/render_card.py:170-174；调用位 :329/:511/:646）——
    进程内每帧链一次缓存（模块级 _SCENE dict，键=FRAME_DESC 帧键）。
  * 七份 load_frame_scene*（scene_compiler.py:490〔spell/spell_dk 双链〕/
    scene_compiler_ally.py:530 / wf_render.py:467 / hero_render.py:519〔hand/play
    双链〕/ hp_render.py:388 / location_render.py:528 / hero_render_bacon.py:73）
    ——consumer-arch 卡第 1 类「共享编译引擎收敛」的副本网核心；七份逐行同构，
    公共形=`return kit.meta, kit.meta["hierarchy"], kit.arrays` 三元组（ability
    形字段名 recon_meta）。本模块=统一 scene 装配一份（收敛的自然兑现）。
  * kit_for（旧链 registry.py:138-149）——帧键→kit 域项路由（if 链形态）。
  * FRAME_SPECS（supply/frames/specs.py）——六帧族参数化差异表（uv1/color0/
    根归零模式/extra meshes/种族串/类色族等）；帧差异全部收表，新帧型=加 spec。

配方面：kit 族域项经 recipes.frames（kit/ability_kit/bacon_kit）；FRAME_SPECS
自批14 起经 recipes.frames 导出（配方面增补，转发态纯别名——选型记账：
配方面只走 recipes.frames 转发，避免跨层直连）。

批14 实现账（2026-10-14，S3 生长；两源=骨架 §3 走查×旧实现还原，旧实现为准——
本段无 decomp 对应物【引擎 prefab 实例化=回调驱动不进离线形】，收敛对象=旧
七份副本网自身）：

纪律面前置——本模块函数族经 recipes.frames 触供给配方（@item），**消费须在
supply session 内**（入口层独占纪律，批12 同款；未来门驱动循环开 session 调
本段，段内不开）。

七份旧实现差异账（逐行比对结论；FRAME_SPECS 归因——本段给 consumer-arch 卡
第 1 类的交付）——
  * 公共形（七份全同）：kit 对象 → (meta, meta["hierarchy"], arrays) 三元组；
    hierarchy 即 meta["hierarchy"] 同一对象（别名语义，消费方 :329/:646 依赖）。
  * 可参数化差异（FRAME_SPECS 已收）：六帧族 kit 提取的 uv1/color0/根归零/
    extra meshes/种族串/类色族/report+ubertext 文件名——全走 spec 行参数，
    不在 scene 装配层显形（逐行差异清单为空的正因）。
  * 帧键→kit 源路由（FRAME_SPECS 外，旧 kit_for if 链）：spell/spell_dk→
    ability_kit（ability.py 三件套独立管线）；hero_play_bacon→bacon_kit；
    其余六键→kit(key)，键集恰=FRAME_SPECS 键集（分派表 _KIT_SOURCE 的构造
    即此归因：六族自 FRAME_SPECS 键集派生，两特源显式列出）。
  * 字段名真差异（FRAME_SPECS 外）：AbilityKit.recon_meta vs Kit.meta——两
    kit 构建器对象形分歧；本模块 _kit_meta 归一读取（供给面不动）。
  * meta 产物结构真差异：Kit.meta 含 dbf_id/card_id/root_translation_neutralized
    三键；AbilityKit.recon_meta 无（ability.py 独立管线自组 recon dict）——
    scene 结构逐帧本就有别，不归一（段级对拍 A 账面实证）。
  * bacon spec 内联（bacon.py:169-172 字面 dict）未入 FRAME_SPECS 表——
    参数化收口的真实缺口，记账（收敛候选：bacon spec 行升表，非本批）。
  * hero 双链形参（hero_render.load_frame_scene(mode) "hand"/"play"）：旧单
    模块双链的形参化伪差异，帧键即参数，新形直用 frame_key。
  * 多对一：spell 与 spell_dk 共享同一 AbilityKit（旧 _SCENE 仍按帧键分格，
    两格三元组元素=同一对象）——本模块同语义（对拍 B 账面）。
"""

from __future__ import annotations

from eidolon.core.recipes.frames import (FRAME_SPECS, AbilityKit, ability_kit, bacon_kit,
                                    kit)

# ============================================================================
# 帧键 → kit 源路由（旧 kit_for if 链表化；六族键集=FRAME_SPECS，两特源显式）
# ============================================================================

from eidolon.core.render.scenes.specs import PREFAB_SPECS  # consumer-v2：kit 路由单一真值
from eidolon.core.render._provenance import invented  # noqa: F401 （族默认）

_KIT_SOURCE: dict[str, str] = {pk: row["kit"] for pk, row in PREFAB_SPECS.items()}
"""prefab→kit 域项源（consumer-v2：自 PREFAB_SPECS kit 列派生，单一真值；
"ability"/"bacon"=特源独立管线，余=FRAME_SPECS 六族 kit(key) 键——键名沿用
supply kit 命名空间，本模块不做 supply 改键）。开放位=PREFAB_SPECS 行成员，
未知键 assert 响亮（tripwire，per-prefab 粒度）。"""

SCENE_KEYS: tuple[str, ...] = tuple(sorted(_KIT_SOURCE))
"""帧链开放全集（prefab 口径；对拍/门抽样清单正典）。"""


@invented(reason="prefab→kit 域项路由表化：本函数只做表查，kit 提取与进程 memo 全在配方域项", counterpart=None)
def kit_for(key: str):
    """帧键 → kit 域项对象（旧链 registry.py:138-149 对位，表化）。

    spell/spell_dk→ability_kit（共享同一进程 memo 对象）、hero_play_bacon→
    bacon_kit、六帧族→kit(FRAME_SPECS 键)。kit 提取与 memo 语义全在配方域项
    （进程级，kit=卡不变游戏结构）；本函数只做帧键分派。
    """
    src = _KIT_SOURCE.get(key)   # key=prefab（consumer-v2 穿线翻转）
    assert src is not None, (
        f"未知 prefab {key!r}——_KIT_SOURCE 无此键（开放位={sorted(_KIT_SOURCE)}）")
    if src == "ability":
        return ability_kit()
    if src == "ability_premium":
        return ability_kit("premium")   # 金法术帧（capture-determinism 2026-10-30）
    if src == "bacon":
        return bacon_kit()
    return kit(src)   # consumer-v2：kit() 参数=kit 族名（FRAME_SPECS 命名空间），非 prefab


def _kit_meta(k):
    """kit → recon dict 统一读取（字段名真差异归一：Kit.meta /
    AbilityKit.recon_meta；读取别名归一，供给面对象形不动——模块 docstring
    差异账）。"""
    if isinstance(k, AbilityKit):
        return k.recon_meta
    return k.meta


# ============================================================================
# scene 元组装 + 每帧链进程缓存（旧 scene_for 语义）
# ============================================================================

_SCENES: dict[str, dict] = {}


@invented(reason="prefab 实例化离线等价：kit 提取+进程缓存替代运行时实例化", counterpart="AssetLoader.InstantiatePrefab")
def scene_for(key: str) -> dict:
    """帧链 scene 元组装（scene_for 对位，old_frames/render_card.py:170-174）。

    返回 {"meta":…, "hierarchy":…, "arrays":…, "report":…, "ubertext":…}——
    旧三元组 (meta, meta["hierarchy"], arrays) 加 report/ubertext 两面的统一
    元组装（五面全自同一 kit 域项对象：hierarchy 即 meta["hierarchy"] 别名，
    arrays/report/ubertext 即 kit 字段本体，零拷贝）。每帧键进程缓存一次
    （_SCENES，旧 _SCENE 同语义）：同帧键二次调用返回同一对象。
    """
    if key not in _SCENES:
        k = kit_for(key)
        meta = _kit_meta(k)
        _SCENES[key] = {"meta": meta, "hierarchy": meta["hierarchy"],
                        "arrays": k.arrays, "report": k.report,
                        "ubertext": k.ubertext}
    return _SCENES[key]
