"""frames.dk — DK 符文图集（dk_assets 键收编）+ rs_assets 溶解账（Batch C）。

对照表（旧位 → 本域，预审 2026-10-10）：
  - CardRunes_DeathKnight_sm ← **E4 走链落地**（旧=bundle+硬 pid"asset_index 实录"，
    正典 asset-addressing-chain E0e 判走链替换候选）：tables.actor_slots["PLAY_HERO"]
    → 结构键下钻 RootObject/DecorationRoot/DeckRunesContainer → 子树寻 DeckTray_Runes
    → 首个 MeshRenderer mat0 _MainTex。探针实证（2026-10-10）：Rune_Frost_sm→
    CardRunes_DeathKnight_sm，pid 与旧硬编码同值（-7217558262942142559）=殊途同归。
    节点路径/材质名=个体资产名档位（游戏自身 transform 导航锚），挂对拍监视（E0 纪律：
    DeckRunes_HeroPortrait/Quad 的 DeckBanner 渲染器在子树先于符文，锚 DeckTray_Runes
    子树为必要结构键）
  - Card_Inhand_Ability_DK 图集 ← **已溶解 color.atlas("spellCardTextures",1)**（color
    批次 B 档溶解：bundle 字面量随 catalog 解析消失）——不另开配方
  - portrait_ETC_210 ← **已溶解 art.portrait**（CardDef 链同构逐字）——不另开配方
  - rs_assets 键 ← **纯溶解账**（9×art.portrait(RLK_*) + color.atlas(spellCardTextures,1)
    零新配方）——键退役随阶段②
对拍=duipai_frames.py check_dk（符文/图集/10 肖像像素逐位 vs 既档 dk/assets+rs_assets）。
"""
from __future__ import annotations

from PIL import Image

from eidolon.core.infra.dll_reflect import tables
from eidolon.core.supply._projection import as_pairs
from eidolon.core.supply.frames.engine import ptr_dict
from eidolon.core.supply.machine import core, item

_RUNE_SPINE = ("RootObject", "DecorationRoot", "DeckRunesContainer")
_RUNE_TRAY = "DeckTray_Runes"


def _child_by_name(r, bundle: str, go_reader, name: str):
    """transform 子节点按实名取 GO（结构键下钻一步）。"""
    tt = go_reader.read_typetree()
    for comp in tt.get("m_Component", []):
        cobj, _cb = r.resolve_pptr(bundle, ptr_dict(comp["component"]), go_reader)
        if cobj.type.name != "Transform":
            continue
        for ch in cobj.read_typetree().get("m_Children", []):
            tr, _ = r.resolve_pptr(bundle, ptr_dict(ch), cobj)
            gop = ptr_dict(tr.read_typetree().get("m_GameObject") or {})
            go2, _2 = r.resolve_pptr(bundle, gop, tr)
            if go2.read_typetree().get("m_Name") == name:
                return go2
    return None


def _find_descendant(r, bundle: str, go_reader, name: str):
    """子树任意深度寻名（DeckTray_Runes 挂 DeckRunes_HeroPortrait 之下）。"""
    tt = go_reader.read_typetree()
    for comp in tt.get("m_Component", []):
        cobj, _cb = r.resolve_pptr(bundle, ptr_dict(comp["component"]), go_reader)
        if cobj.type.name != "Transform":
            continue
        for ch in cobj.read_typetree().get("m_Children", []):
            tr, _ = r.resolve_pptr(bundle, ptr_dict(ch), cobj)
            gop = ptr_dict(tr.read_typetree().get("m_GameObject") or {})
            go2, _2 = r.resolve_pptr(bundle, gop, tr)
            if go2.read_typetree().get("m_Name") == name:
                return go2
            hit = _find_descendant(r, bundle, go2, name)
            if hit is not None:
                return hit
    return None


def _first_main_tex(r, bundle: str, go_reader):
    """子树 DFS 首个 MeshRenderer mat0 _MainTex → (tex_reader, bundle, 材质名)。"""
    tt = go_reader.read_typetree()
    for comp in tt.get("m_Component", []):
        cobj, _cb = r.resolve_pptr(bundle, ptr_dict(comp["component"]), go_reader)
        if cobj.type.name != "MeshRenderer":
            continue
        ctree = cobj.read_typetree()
        mats = ctree.get("m_Materials") or []
        if not mats:
            continue
        pd = ptr_dict(mats[0])
        if not pd["m_PathID"]:
            continue
        mobj, mb = r.resolve_pptr(bundle, pd, cobj)
        mt = mobj.read_typetree()
        texenvs = as_pairs((mt.get("m_SavedProperties") or {}).get("m_TexEnvs"),
                           what="m_TexEnvs")
        for first, sec in texenvs.items():
            sec = sec or {}
            if first != "_MainTex":
                continue
            tp = ptr_dict(sec.get("m_Texture") or {})
            if not tp["m_PathID"]:
                continue
            tobj, tb = r.resolve_pptr(mb, tp, mobj)
            if tobj.type.name == "Texture2D":
                return tobj, tb, mt.get("m_Name")
    for comp in tt.get("m_Component", []):
        cobj, _cb = r.resolve_pptr(bundle, ptr_dict(comp["component"]), go_reader)
        if cobj.type.name != "Transform":
            continue
        for ch in cobj.read_typetree().get("m_Children", []):
            tr, _ = r.resolve_pptr(bundle, ptr_dict(ch), cobj)
            gop = ptr_dict(tr.read_typetree().get("m_GameObject") or {})
            go2, _2 = r.resolve_pptr(bundle, gop, tr)
            hit = _first_main_tex(r, bundle, go2)
            if hit is not None:
                return hit
    return None


@item("frames", "rune_atlas")
def rune_atlas() -> Image.Image:
    """DK 符文图集 CardRunes_DeathKnight_sm（PLAY_HERO→DeckTray_Runes 走链）。
    [dk_extract_runes_sm 收编；E4 走链替换，旧 bundle+硬 pid 撤除]"""
    r = core().res
    ref = tables.actor_slots["PLAY_HERO"]
    res = r.resolve(ref)
    assert res["ok"], res.get("checks")
    bundle = res["resolved"]["bundle"]
    node, _ = r.container_get(bundle, res["resolved"]["guid"])
    for nm in _RUNE_SPINE:
        nxt = _child_by_name(r, bundle, node, nm)
        assert nxt is not None, f"符文链 {'/'.join(_RUNE_SPINE)} 断于 {nm}"
        node = nxt
    tray = _find_descendant(r, bundle, node, _RUNE_TRAY)
    assert tray is not None, f"子树无 {_RUNE_TRAY}"
    hit = _first_main_tex(r, bundle, tray)
    assert hit is not None, "DeckTray_Runes 子树无 _MainTex 渲染器"
    tobj, _tb, mat_name = hit
    tname = tobj.read_typetree().get("m_Name")
    # 名字谓词=E0 监视制：断言+对拍像素逐位双保险（漂移即红）
    assert tname == "CardRunes_DeathKnight_sm", (tname, mat_name)
    return tobj.read().image
