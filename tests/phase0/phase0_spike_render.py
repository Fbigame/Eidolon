"""phase0_spike_render — Phase 0 Step 4：index 种子渲染单卡 vs live 对拍。

S1 seam 演练形态：把 ``SupplyIndex.assemble_card(card_id)`` 的产物按 token
预置进 ``Session.memo``（render 域函数不执行，取种子值），统计：
  * PNG sha 与 live 逐位比较；
  * warm 路径剩余 live 调用清单（按域/解码成本注记）；
  * 是否仍 import UnityPy（渲染前 sys.modules 无 UnityPy 的冷进程内断言）；
  * 首卡耗时（assemble + render；冷进程、route 缓存暖）。

种子面（index 可供 → A/B 类）：
  art.portrait(card_id)          → bundle["portrait"]
  frames.kit(family)             → Kit 六面重组（meta+hierarchy 合并、
                                    trinket_level_mats=None、races=None、
                                    arrays→_ArrayDict、mesh_refs={}）
  text.fontdefs()                → bundle["text"]["fontdefs"]
  text.font_ttf_bytes(def_name)  → bundle["text"]["fonts"][def_name]
  text.font_table()              → 从 fontdefs 派生 entries（无损）
其余 token 照旧 live（缺口面如实留在 live 账上）。

用法（两进程对拍；各自冷进程、route 缓存共享暖）：
  python -m tests.phase0.phase0_spike_render --game <root> \
      --cache-root <route-cache> --index-root <supply-index> \
      --dbf 9 --card-id EX1_350 --mode live --out build/phase0/spike_live.json
  python -m tests.phase0.phase0_spike_render ... --mode seed --out build/phase0/spike_seed.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from eidolon.contracts import CardRef  # noqa: E402
from tests.phase0.phase0_supply_spy import (  # noqa: E402
    SessionSpy,
    dump_json,
    render_one_card,
    setup_game,
    token_tuple,
)


def _font_table_entries(fontdefs: dict) -> list[dict]:
    """font_table token 的无损派生（fontdefs 本由 font_table 逐 entry 构造）。"""
    return [{"m_FontDefName": name, "m_FontName": rec["m_FontName"],
             "m_FontGuid": rec["base_guid"]}
            for name, rec in fontdefs.items()]


def _kit_from_index(frame: str, six: dict):
    """index 六面 → live Kit 形状（scenes.scene_for / render 消费面同形）。

    meta={meta面, hierarchy:面, trinket_level_mats:None}——live meta 含 hierarchy
    键与非 trinket 帧恒 None 的 trinket_level_mats；races=None（index 排除域，
    消费点=GetRaceText，卡有种族时是真实缺口——spike 卡无种族则不触达）；
    mesh_refs={}（渲染零消费，grep 实证）。"""
    from eidolon.core.supply.frames.kits import Kit, _ArrayDict

    meta = {**six["meta"], "hierarchy": six["hierarchy"],
            "trinket_level_mats": None}
    return Kit(frame_dir=frame, meta=meta,
               arrays=_ArrayDict(six["arrays"]), textures=six["textures"],
               report=six["report"], ubertext=six["ubertext"],
               races=None, mesh_refs={})


def _races_face_live():
    """kit races 面（index 排除域）的 live 派生——spike 的 gap-face 补件。

    compiler.GetRaceText 无条件消费 ``kit("ally").races["strings"]``
    （compiler.py:598，spike 实证炸点）；index kit 未建该面（车1 排除域）。
    形状照抄 live `_extract_kit` races 段（消费点只读 ["strings"]）。"""
    from eidolon.core.supply.frames.engine import extract_race_strings, global_strings_path

    return {"source": str(global_strings_path()),
            "provenance": "phase0-spike：live 派生（index 缺口面；Phase 1 须补 kit races 域）",
            "strings": extract_race_strings()}


def _mesh_refs_live(frame: str) -> dict:
    """kit mesh_refs 面（index 无 PPtr 账）的 live 派生——gap-face 补件 #2。

    消费点=``frames.portrait_uv1``（supply 域函数内部 `_kit(frame).mesh_refs[name]`，
    supplements.py:336；spike 实证炸点二：种子 kit mesh_refs={} → KeyError）。
    kit_light 与 kit 同走 Recon.walk（mesh_jobs 在 walk 期捕获，engine.py:332），
    无纹理/网格解码——秒级轻量；portrait_uv1 本体仍 live（网格解码面）。
    直调内部 `_extract_kit(light=True)`（spike 种子构建在 session 外，不经
    @item memo；kit_light 域项未入 recipes 导出面）。"""
    from eidolon.core.supply.frames.kits import FRAME_SPECS, _extract_kit

    return dict(_extract_kit(FRAME_SPECS[frame], None, light=True).mesh_refs)


def build_seeds(index_root: str, card_id: str, kit_family: str) -> tuple[dict, float]:
    """assemble_card → memo 种子（token → 产物）。返回 (seeds, assemble 耗时 s)。

    gap face 如实记账：kit.races / kit.mesh_refs 由 live 派生（见上两件），
    其余六面全自 index。"""
    from eidolon.core.supply_index.warm import SupplyIndex

    t0 = time.perf_counter()
    idx = SupplyIndex(index_root, health_policy="stamp")
    bundle = idx.assemble_card(card_id)
    elapsed = time.perf_counter() - t0
    idx.close()

    seeds: dict = {}
    seeds[("art", "portrait", (card_id,))] = bundle["portrait"]
    text = bundle["text"]
    seeds[("text", "fontdefs", ())] = text["fontdefs"]
    for def_name, ttf in text["fonts"].items():
        seeds[("text", "font_ttf_bytes", (def_name,))] = ttf
    seeds[("text", "font_table", ())] = _font_table_entries(text["fontdefs"])
    kit = _kit_from_index(kit_family, bundle["kit"])
    kit.races = _races_face_live()              # gap face #1（Phase 1 须补 index 域）
    kit.mesh_refs = _mesh_refs_live(kit_family)  # gap face #2（同上）
    seeds[("frames", "kit", (kit_family,))] = kit
    return seeds, elapsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--cache-root", required=True)
    ap.add_argument("--index-root", required=True)
    ap.add_argument("--dbf", type=int, required=True)
    ap.add_argument("--card-id", required=True, help="m_noteMiniGuid（index cards 键）")
    ap.add_argument("--kit-family", default="ally")
    ap.add_argument("--mode", choices=("live", "seed"), required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    unitypy_before = "UnityPy" in sys.modules
    setup_game(args.game, args.cache_root)

    from eidolon.core.infra.dbf import default_dbf  # card_id → dbf 换算防呆

    dbf_id = args.dbf
    got = default_dbf().card_id_to_dbf.get(args.card_id.casefold())
    assert got == dbf_id, f"dbf/{args.card_id} 不配对：{got} != {dbf_id}"

    seeds, t_assemble = (None, 0.0)
    if args.mode == "seed":
        seeds, t_assemble = build_seeds(args.index_root, args.card_id,
                                        args.kit_family)

    spy = SessionSpy()
    spy.install(seeds)          # live 模式 seeds=None（纯记账）；seed 模式预填 memo
    try:
        out_png = Path(args.out).parent / f"spike-{args.mode}.png"
        doc = render_one_card(
            __import__("tests.phase0.phase0_supply_spy", fromlist=["SpikeCard"])
            .SpikeCard(args.mode, CardRef("dbf", dbf_id), "plain"),
            out_png)
    finally:
        spy.uninstall()
    unitypy_after = "UnityPy" in sys.modules

    doc.update({
        "mode": args.mode,
        "card_id": args.card_id,
        "dbf": dbf_id,
        "assemble_s": round(t_assemble, 3),
        "unitypy_imported_by_render": unitypy_after and not unitypy_before,
        "tokens": [token_tuple(t) for t in spy.requested],
        "token_count": len(spy.requested),
    })
    if args.mode == "seed":
        live = spy.live
        doc["live_tokens"] = [token_tuple(t) for t in live]
        doc["live_count"] = len(live)
        doc["hit_count"] = len(spy.hit)
        doc["unused_seeds"] = [token_tuple(t) for t in spy.unused]
    dump_json(Path(args.out), doc)
    print(f"[phase0:{args.mode}] sha={doc['sha256'][:12]} render={doc['elapsed_ms']}ms "
          f"assemble={doc['assemble_s']}s tokens={doc['token_count']}"
          + (f" live={doc.get('live_count')}" if args.mode == "seed" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
