"""phase0_index_map — Phase 0 Step 2：token → index role/item 覆盖对照。

读 Step 1 的 tokens.json + 一代 supply index（SupplyIndex 只读），把每个
(domain, item) token 分三类：
  A 可直接供给      —— index 已有同素材，值形状同或仅薄包装；
  B 需要形状转换    —— index 有素材但要转换/派生（kit 重组、font_table 派生、
                       watermark ref 预解析）；
  C index 没有      —— 缺口（按域聚合；附「live 保留成本」注记：零解码活表读
                       vs UnityPy 解码）。

用法：
  python -m tests.phase0.phase0_index_map --tokens build/phase0/tokens.json \
      --cache-root build/p5-full --out build/phase0/coverage.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from eidolon.core.supply_index.warm import SupplyIndex  # noqa: E402

# index kit 六族（meta counts_kit_items=6；FRAME_SPECS 九族中的车1 全集）
INDEX_KIT_FAMILIES = frozenset(
    {"ally", "weapon", "heropower", "location", "hero_hand", "hero_play"})

# C 类注记：live 保留的成本轴（零解码=活表/纯内存；unitypy=开包解码；user=用户文件）
_LIVE_COST = {
    "color.probe": "unitypy（链根 resolve+组件直读；进程 memo 一次）",
    "color.atlas": "unitypy（每 family×ct 一次；进程 memo；105/150 token 最大缺口）",
    "art.portrait_mip": "unitypy（per-card 真链 DXT 解码；portrait_mip=True 正典在役）",
    "art.portrait_source": "unitypy（与 portrait 同链；记账面非像素面）",
    "textures.mip_registry": "unitypy（16 链静态解码；进程 memo 一次）",
    "text.font_asset_params": "unitypy（三资产 Font 全量 typetree；进程 memo 一次）",
    "frames.actor_ref": "零解码（dll 活表内存读；非资产面）",
    "frames.spell_school_names": "零解码（活表+strings 内存派生）",
    "frames.rune_atlas": "unitypy（DK 符文图集）",
    "overrides.asset": "user（用户文件装载；天然 live——不在 index 语义内）",
}

# B 类转换注记
_CONVERSION = {
    "frames.kit": "六面重组 Kit：meta={meta面, hierarchy:面, trinket_level_mats:None}、"
                  "arrays→_ArrayDict、races=None（缺口，见 C 注）、mesh_refs={}（零消费）；"
                  "textures 面无类色图集（EXCLUDED atlas——消费面是否触达归 spike 验证）",
    "text.font_table": "从 index fontdefs 派生 entries"
                       "（{m_FontDefName, m_FontName, m_FontGuid=base_guid}；"
                       "fontdefs 本由 font_table 逐 entry 构造——无损派生）",
    "watermarks.texture": "token 参数=ref（非 card_id）；种子需 card_id→ref 预解析"
                          "（index watermark manifest.ref 即四级裁决值）",
}

# C 类的 index 无此素材但有近似账面注记
_PARTIAL = {
    "art.portrait_source": "index locators 行有 bundle/guid/path_id/locale（partial 账可拼；"
                           "变体/base 字段缺）",
}


def classify(domain: str, item: str, kit_families: frozenset) -> tuple[str, str]:
    key = f"{domain}.{item}"
    if domain == "art" and item == "portrait":
        return "A", "role=portrait（PIL Image 直供；token 参数=card_id 同形）"
    if domain == "text" and item == "fontdefs":
        return "A", "text() fontdefs（逐键同形：base_guid/enus|zhcn/fontdef/font_object）"
    if domain == "text" and item == "font_ttf_bytes":
        return "A", "text() fonts[def_name]（TTF bytes；键空间=fontdefs 名单）"
    if domain == "frames" and item == "kit":
        return ("B", _CONVERSION["frames.kit"])       # 族在参数里；族缺口单列 C
    if domain == "text" and item == "font_table":
        return "B", _CONVERSION["text.font_table"]
    if domain == "watermarks" and item == "texture":
        return "B", _CONVERSION["watermarks.texture"]
    if key in _LIVE_COST:
        return "C", _LIVE_COST[key]
    # frames 域特源/附件 kit（ability/bacon/trinket/anomaly/ally_premium/kit_light/
    # badges/btf/ornaments/ta_supplement/material_state/portrait_uv1/...）
    return "C", "unitypy（index 未建此域项——缺口）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", required=True)
    ap.add_argument("--cache-root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tokens_doc = json.loads(Path(args.tokens).read_text(encoding="utf-8"))
    idx = SupplyIndex(args.cache_root, health_policy="skip")
    kit_families = frozenset(idx.kit_frames())
    idx.close()

    rows = []
    for t in tokens_doc["union"]:
        # kit token 按族成员分拆（ally_premium/trinket/anomaly=index 未建族→C）
        if t["domain"] == "frames" and t["item"] in ("kit", "kit_light"):
            for fam in t["args"]:
                if fam in kit_families and t["item"] == "kit":
                    rows.append({**t, "args": [fam], "class": "B",
                                 "note": _CONVERSION["frames.kit"]})
                else:
                    rows.append({**t, "args": [fam], "class": "C",
                                 "note": "unitypy（kit 族/形态 index 未建——六族外或"
                                         "kit_light 形态未建）"})
            continue
        cat, note = classify(t["domain"], t["item"], kit_families)
        rows.append({**t, "class": cat, "note": note})

    a = [r for r in rows if r["class"] == "A"]
    b = [r for r in rows if r["class"] == "B"]
    c = [r for r in rows if r["class"] == "C"]
    by_domain_c: dict[str, list] = {}
    for r in c:
        by_domain_c.setdefault(r["domain"], []).append(f"{r['item']}{tuple(r['args'])}")

    doc = {
        "purpose": "phase0 step2 token→index 覆盖三分类",
        "token_union": len(tokens_doc["union"]),
        "counts": {"A_direct": len(a), "B_convert": len(b), "C_gap": len(c)},
        "A": a, "B": b, "C": c,
        "C_by_domain": {k: sorted(v) for k, v in sorted(by_domain_c.items())},
        "index_kit_families": sorted(kit_families),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[phase0] A={len(a)} B={len(b)} C={len(c)} → 已写 {out}")
    for d, items in sorted(by_domain_c.items()):
        print(f"  C[{d}]: {len(items)} 项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
