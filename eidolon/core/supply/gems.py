"""gems — 稀有度/宝石域：走链配方（零硬编码 pid）。

链式样：活表（game.actor_slots）→ catalog（res.resolve）→ container（层级根）→
层级遍历 → 材质（跨包 resolve_pptr 现场解）→ 槽名 → 纹理。寻址谓词=游戏语义常量
（节点路径/纹理名），pid 全程现场解出——链依据=gem-chain-walk.md 七跳端到端实证
（asset-addressing 实验档；每会话遍历一次，槽清单会话 memo 共享）。

对照表（旧位 → 本域）：
  - mana_albedo ← 旧 ui_sprites pid 硬编码（essential_base_global-texture-2 /
    8316986825969224176 / GenFX_Gem_Mana_D.png，old_supply/asset_resolver.py:506-508）：
    链 = Card_Hand_Ally → RootObject/CostObject/Gem_Mana ← Gem_Mana_Blue ← _MainTex
    [gem-chain-walk.md [5]-[6] 跳]
  - clouds ← 同上材质的云层槽（_ScrollingTex 槽名判定=档位①；着色公式=
    gem-shader-recon 正典，属 paint 层不归供给）
  - rarity_atlas ← RarityGemFrame/RarityGem 节点 _MainTex 槽（结构路径+schema 槽名；
    运行时图集偏移 + tint=Actor.cs:Actor 常量属 paint 层）
    [clouds/rarity 旧纹理名谓词退役 2026-10-10 audit §3.4 链化]

退役随行（非本域配方，阶段②旧面工序）：Diamond_Frame_Gem / Gem_Mana_Large_phone_NAX
（消费面死候选，chain-coverage.md E0e 实证）；gem_clouds 悬空过渡键；gem_obj（待
ability kit npz 覆盖核验后退役，render_gem 改读 npz）。
"""
from __future__ import annotations

from typing import Any, Iterator

from PIL import Image

from eidolon.core.infra.dll_reflect import tables
from eidolon.core.infra.resolve_asset_ref import Resolver
from eidolon.core.supply._projection import as_pairs
from eidolon.core.supply.machine import core, item


def _slots(r: Resolver, bundle: str, go_reader, path: str = "") -> Iterator[dict]:
    """层级遍历产出材质纹理槽 {节点路径, 材质名, 槽名, 纹理名, 纹理 reader}。

    [遍历式样=gem_chain_walk.py [4]-[6]；跨包引用 resolve_pptr 现场解，pid 零硬编码]"""
    tt = go_reader.read_typetree()
    node_path = f"{path}/{tt['m_Name']}" if path else tt["m_Name"]
    transform = None
    for comp in tt.get("m_Component", []):
        ptr = comp.get("component") or {}
        if not ptr.get("m_PathID"):
            continue
        try:
            cobj, _cb = r.resolve_pptr(bundle, ptr, go_reader)
        except Exception:  # noqa: BLE001  PPtrError/解析缺位→槽位缺席记，不走查（对照表注）
            continue
        if cobj is None:
            continue
        if cobj.type.name == "Transform":
            transform = cobj
        elif cobj.type.name == "MeshRenderer":
            ctree = cobj.read_typetree()
            for mp in ctree.get("m_Materials", []):
                if not isinstance(mp, dict) or not mp.get("m_PathID"):
                    continue
                try:
                    mobj, mb = r.resolve_pptr(bundle, mp, cobj)
                    mt = mobj.read_typetree()
                except Exception:  # noqa: BLE001
                    continue
                texenvs = as_pairs((mt.get("m_SavedProperties") or {}).get("m_TexEnvs"),
                                   what="m_TexEnvs")
                for slot, sec in texenvs.items():
                    tp = (sec or {}).get("m_Texture") or {}
                    if not tp.get("m_PathID"):
                        continue
                    try:
                        tobj, _tb = r.resolve_pptr(mb or bundle, tp, mobj)
                        yield {"node": node_path, "mat": mt.get("m_Name"), "slot": slot,
                               "tex": tobj.read_typetree().get("m_Name"), "reader": tobj}
                    except Exception:  # noqa: BLE001
                        continue
    if transform is not None:
        for ch in (transform.read_typetree().get("m_Children") or []):
            if not isinstance(ch, dict) or not ch.get("m_PathID"):
                continue
            try:
                tr_obj, _tb = r.resolve_pptr(bundle, ch, transform)
                go_ptr = tr_obj.read_typetree().get("m_GameObject") or {}
                go_obj, _gb = r.resolve_pptr(bundle, go_ptr, tr_obj)
            except Exception:  # noqa: BLE001
                continue
            yield from _slots(r, bundle, go_obj, node_path)


@item("gems", "hand_ally_slots")
def _hand_ally_slot_list() -> list[dict[str, Any]]:
    """手牌随从帧 prefab 全纹理槽清单（会话 memo：一遍遍历三配方共享）。"""
    ref = tables.actor_slots["HAND_MINION"]
    r = core().res
    res = r.resolve(ref)
    assert res["ok"], res["checks"]
    bundle = res["resolved"]["bundle"]
    root, _ = r.container_get(bundle, res["resolved"]["guid"])
    return list(_slots(r, bundle, root))


@item("gems", "mana_albedo")
def mana_albedo() -> Image.Image:
    """费用宝石 albedo（GenFX_Gem_Mana_D）。链见模块 docstring 对照表。"""
    e = next(s for s in _hand_ally_slot_list()
             if s["node"].endswith("CostObject/Gem_Mana") and s["slot"] == "_MainTex")
    return e["reader"].read().image


@item("gems", "clouds")
def clouds() -> Image.Image:
    """宝石流云内纹（Gem_Mana 材质 _ScrollingTex 槽——m_TexEnvs 序列化键=档位①；
    2026-10-10 audit §3.4 链化：纹理名谓词退役，探针实证 _ScrollingTex=GenFX_clouds03
    于 Gem_Mana 材质唯一载体）。"""
    e = next(s for s in _hand_ally_slot_list()
             if s["node"].endswith("CostObject/Gem_Mana") and s["slot"] == "_ScrollingTex")
    return e["reader"].read().image


@item("gems", "rarity_atlas")
def rarity_atlas() -> Image.Image:
    """稀有度宝石图集（RarityGemFrame/RarityGem 节点 _MainTex 槽——结构路径+schema
    槽名；2026-10-10 audit §3.4 链化：纹理名谓词退役，探针实证载体唯一）。"""
    e = next(s for s in _hand_ally_slot_list()
             if s["node"].endswith("RarityGemFrame/RarityGem") and s["slot"] == "_MainTex")
    return e["reader"].read().image
