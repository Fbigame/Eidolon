"""color — 类色域（switcher 表/类色图集；E1 类色切换机制域）。

域项：probe（真内存直读，12 族全量）、atlas（真内存，按族+槽位）。
对照表（旧位 → 本域）：
  - probe ← extract_switcher_probe（全 bundle 扫描→落 json→v3 桥接读回）：v3=**链根
    正形**——resolve("CardColorSwitcher.prefab:b30c…")（资产身份 guid，catalog 解析
    bundle 零字面量束）→ GO 组件直读；失效即红（窄扫回退已撤 2026-10-10，见
    _SWITCHER_REF 注）。**decomp 行为账（2026-10-10）**：游戏侧不"找"它——Awake 自注册
    （CardColorSwitcher.cs:CardColorSwitcher s_instance=this + HSDontDestroyOnLoad），消费方
    Actor.cs/Gameplay.cs/HearthstoneFactionBanner.cs 走 Get() 静态分发；宿主 GO 名=
    类名、catalog 成员=我们链根的依据。落盘与 actor 对账段退役（actor 表=game_dll）。
    12 族全量直出（旧 SWITCHER_KEYS 只认两族=识别谓词，数据面同源超集）。
  - atlas(family, ct) ← _extract_class_atlas/_atlas_ref_to_impl（probe ref→resolve→
    Texture2D.image；别名差容忍断言随收编带入，MechaJaraxxus 案例）。
  - DK 图集（B 档 bundle 字面量）← _extract_dk_atlas_bytes：**已溶解**——DK=
    spellCardTextures[1]，atlas("spellCardTextures","1") 走 resolve() 查 catalog，
    字面量消失（chain-coverage.md B 档收口）。
  - faction* 三族（factionIconMaterials/Signature/BannerMaterials）← probe 表直出；
    材质消费与网格/节点（extract_faction_ornaments 的 npz 段）归 frames 域。
atlas() 仅纹理族；faction* 为材质族（ref 可解析、reader 非 Texture2D），勿混用。
总路线注记（2026-10-10 补链）：本域 probe 曾是总路线唯一非链项（Card_Hand_Ally 层级
走查零命中），现经资产身份 guid 补链——总路线无例外：DLL 活表/manifest 登记面做根，
catalog→container→typetree 做遍历，pid 全程现场解。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from eidolon.core.infra.errors import GameAssetMissing
from eidolon.core.supply.machine import core, item
from eidolon.core.supply.textures import mip_probe, note_texture_ref

_SWITCHER_KEYS = {"minionCardTextures", "spellCardTextures"}   # switcher 本体识别谓词
# 链根=游戏自己的引导寻址：HearthstoneApplication.cs:HearthstoneApplication.QueueStartupJobs InstantiatePrefab 内联字面量
# "CardColorSwitcher.prefab:b30c…"（与本串逐字符同源）。**跨版本双 DLL 二进制实证**
# （2026-10-10：本机 8-9 月构建与 Event 1 测试服 7-24 冻结副本的 #US 堆各含同一
# UTF-16LE 完整 ref——该常量非仅类推稳定，逐点实证）。
# 反射边界账：该串=方法体内联 ldstr（非字段）——字段反射不可达，IL 提取属过度机械；
# 失效双层保护=E0 稳定档+对拍必红（**窄扫兜底已撤 2026-10-10 清账批**：回退成功=
# fail-silent 掩蔽链根漂移，违监视纪律——链根失效必须红）。宿主 GO 名=类名，Awake
# 自注册单例 [CardColorSwitcher.cs:CardColorSwitcher s_instance=this；消费方 Actor/Gameplay/
# HearthstoneFactionBanner 走 Get()]
_SWITCHER_REF = "CardColorSwitcher.prefab:b30c8322821f1524d9e08a59e78e2c85"

_probe_cache: dict[str, list[str]] | None = None   # 进程级（switcher 表=游戏直读数据卡不变；
# 形态语言=属性读进程级，dll_reflect.tables 同款；2026-10-11 ②壳实测：会话级 memo 使
# 冷缓存逐卡重走查（class_atlas 提取 25-32s/次）——升进程级后每进程一遍）


@item("color", "probe")
def probe() -> dict[str, list[str]]:
    """类色 switcher 表：{family: ["名.ext:GUID", …]}（12 族全量，MonoBehaviour 现场直读）。

    链根正形：resolve(_SWITCHER_REF)→container→GO 组件（catalog 解析 bundle，零字面量束）；
    失效即红（窄扫回退已撤，见 _SWITCHER_REF 注）。缓存=进程级（见 _probe_cache 注）。"""
    global _probe_cache
    if _probe_cache is None:
        _probe_cache = _probe_build()
    return _probe_cache


def _probe_build() -> dict[str, list[str]]:
    """switcher 表真内存构建（链根 resolve→GO 组件直读；probe 域项冷路径）。

    typed 边界（设计 §5.3）：链根 ref 无解析结果/无对象抛 ``GameAssetMissing``
    （resolve/container_get 同型 + 本域显式 if）。"""
    r = core().res
    res = r.resolve(_SWITCHER_REF)
    bundle = res["resolved"]["bundle"]
    guid = res["resolved"]["guid"]
    if not (bundle and guid):
        raise GameAssetMissing(
            path=_SWITCHER_REF,
            message=f"asset_missing_in_game: switcher 链根 ref 无解析结果"
                    f" {_SWITCHER_REF}")
    go, _ = r.container_get(bundle, guid)
    tt = go.read_typetree()
    for comp in tt.get("m_Component", []):
        p = comp.get("component") or {}
        if not p.get("m_PathID"):
            continue
        try:
            cobj, _cb = r.resolve_pptr(bundle, p, go)
            tree = cobj.read_typetree()
        except Exception:  # noqa: BLE001  组件级解析缺位→跳过（本体识别仍须命中）
            continue
        if isinstance(tree, dict) and _SWITCHER_KEYS & set(tree):
            return _families(tree)
    raise AssertionError("switcher 组件未命中（链根可解析但本体缺位——fail loud）")


def _families(tree: dict) -> dict[str, list[str]]:
    """族表直出：list 值族全量（空串占位槽原样保留——ColorType 下标对齐语义）。"""
    return {k: [x for x in v if isinstance(x, str)]
            for k, v in tree.items() if isinstance(v, list)}


@item("color", "atlas")
def atlas(family: str, ct: str | int) -> Image.Image:
    """类色图集，真内存式：probe 族表 ref → resolve → Texture2D.image。

    [旧 _atlas_ref_to_impl 同链去落盘，asset_resolver.py:372-384；别名差容忍断言
    （registration/type 须过、name-consistency 仅为别名账，2026-10-06
    TB_Thunderdome_MechaJaraxxus 案例）随收编逐字带入]

    消费点顺带登记 mip 地址（`note_texture_ref`，与 `supply/art.portrait` 同式）：
    这些图集在**运行期槽**已走按需链（`raster._slot_mip_entry` → `entry_for_ref`，
    2026-10-23 weapon-dk-frame），但静态内容指纹面（手工链）不含它们——不登记则
    `mip_probe` 按「带 mip 未注册」报点，把已在役的链误报成缺口（2026-10-29
    mip-q1-coverage：10 条 location 类色图集 + 1 条 DK 武器图集即此形）。登记只补名字面地址，像素零变化。

    typed 边界（设计 §5.3）：族表 ref 无解析结果/无对象抛 ``GameAssetMissing``
    （resolve/container_get 同型 + 本域显式 if；类型不符=形态漂移仍 assert）。"""
    ref = probe()[family][int(ct)]
    r = core().res
    res = r.resolve(ref)
    resolved = res.get("resolved") or {}
    if not (resolved.get("bundle") and resolved.get("guid")):
        raise GameAssetMissing(
            path=ref,
            message=f"asset_missing_in_game: 类色图集 ref 无解析结果 {ref}"
                    f"（family={family} ct={ct}）")
    got, _ = r.container_get(resolved["bundle"], resolved["guid"])
    assert got.type.name == "Texture2D", res["resolved"]
    tt = got.read_typetree()
    note_texture_ref(tt, res["resolved"]["bundle"], int(got.path_id))
    mip_probe(tt, source=f"color.atlas {family}[{ct}]")   # 批24⑤
    return got.read().image
