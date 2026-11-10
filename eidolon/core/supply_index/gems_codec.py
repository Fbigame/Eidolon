"""gems_codec — gems 域 codec + 选择器（本包 UnityPy-free 面；P2 车2）。

域定性：gems=手牌随从帧 prefab（ally，ActorNames 槽 HAND_MINION）宝石材质纹理——
**卡不变游戏结构**（同 kit：item 键无 card_id，per-card 消费=plan 装配层）。

配方转写锚（渲染铁律：file:Class 函数位；参照只读，禁 import eidolon.core.supply）：
- 选择器=eidolon/core/supply/gems.py mana_albedo/clouds/rarity_atlas——
  节点路径 endswith + 材质槽名相等，walk 序首中；遍历序=ally_recon 走查 DFS 先序
  （kit_extract.KitRecon.walk 同源），槽清单=材质 m_TexEnvs 序。
  [gem-chain-walk.md [5]-[6] 跳七跳端到端实证]
- gems 不另起走查：ally kit 提取（kit_extract）已遍历同 prefab 全材质槽——gem
  纹理=kit 层级 renderers 槽的 file 名 → kit textures 面查图。单走查单源，防两份
  走查漂移。

内容身份（车1 原则）：gem 值=纹理解码像素 sha（img.tobytes()）；blob=PNG
（payload sha 寻址，跨 kit 纹理内容寻址去重）。
"""
from __future__ import annotations

from PIL import Image

from eidolon.core.supply_index import schema as S

GEM_CODEC_VERSION = 1

# 选择器表（gems.py :101-125 逐条转写；node_suffix+slot 对）
GEMS: dict[str, dict] = {
    "mana_albedo": {"node_suffix": "CostObject/Gem_Mana", "slot": "_MainTex"},
    "clouds": {"node_suffix": "CostObject/Gem_Mana", "slot": "_ScrollingTex"},
    "rarity_atlas": {"node_suffix": "RarityGemFrame/RarityGem", "slot": "_MainTex"},
}


def _iter_nodes(node):
    """DFS 先序（kit_extract._iter_nodes 同序——选择器「首中」语义依赖遍历序）。"""
    yield node
    for c in node.get("children", []):
        yield from _iter_nodes(c)


def select_gems(hierarchy: dict, textures: dict[str, Image.Image]) -> tuple[dict, list[str]]:
    """ally kit 层级 + 纹理面 → {gem: {img,node,slot,fname}} + issues。

    首中语义：按 DFS 先序遍历节点，节点 renderers→materials→tex 槽序内找
    (node_path endswith suffix, slot 相等) 第一处；纹理图=textures[file]
    （kit 走查 save_texture 的落画面）。缺选/缺图=issue 记账（该 gem 无 item，
    warm 缺项面响亮），禁静默默认图。"""
    found: dict[str, dict] = {}
    issues: list[str] = []
    for n in _iter_nodes(hierarchy):
        npath = n.get("path") or ""
        for r in n.get("renderers") or []:
            for m in r.get("materials") or []:
                if not m:
                    continue
                for prop, sec in (m.get("tex") or {}).items():
                    for gem, spec in GEMS.items():
                        if gem in found:
                            continue
                        if npath.endswith(spec["node_suffix"]) and prop == spec["slot"]:
                            tex = (sec or {}).get("texture") or {}
                            fname = tex.get("file")
                            img = textures.get(fname) if fname else None
                            if img is None:
                                issues.append(
                                    f"{gem}: 槽命中但纹理缺图（file={fname!r} "
                                    f"node={npath}）")
                                continue
                            found[gem] = {"img": img, "node": npath,
                                          "slot": prop, "fname": fname}
    for gem in GEMS:
        if gem not in found and not any(i.startswith(f"{gem}:") for i in issues):
            issues.append(f"{gem}: 选择器未命中（node={GEMS[gem]['node_suffix']} "
                          f"slot={GEMS[gem]['slot']}）")
    return found, issues


def gem_accounts(found: dict) -> dict[str, dict]:
    """选中 gem → 内容账（pixel sha 主键面；JSON 可序列化——出进程/落 manifest 形）。"""
    out: dict[str, dict] = {}
    for gem, sel in found.items():
        img: Image.Image = sel["img"]
        out[gem] = {
            "pixel_sha256": S.sha256_hex(img.tobytes()),
            "width": img.width, "height": img.height, "mode": img.mode,
            "node": sel["node"], "slot": sel["slot"], "fname": sel["fname"],
        }
    return out


def compare_gems(cold_accounts: dict, warm_pixel_shas: dict) -> dict:
    """cold 提取账 vs warm blob 解码像素 sha 逐域比对（冷暖一致判据 gems 面）。"""
    bad: list[str] = []
    for gem in sorted(GEMS):
        c = cold_accounts.get(gem)
        w = warm_pixel_shas.get(gem)
        if c is None and w is None:
            continue                      # 双侧缺席=域账一致（数据缺席）
        if c is None or w is None:
            bad.append(f"{gem}: 单侧缺席（cold={'有' if c else '无'} "
                       f"warm={'有' if w else '无'}）")
        elif c["pixel_sha256"] != w:
            bad.append(f"{gem}: 像素 sha mismatch")
    return {"ok": not bad, "mismatches": bad,
            "gems": sorted(GEMS), "compared": len(GEMS)}
