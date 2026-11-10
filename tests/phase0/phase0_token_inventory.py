"""phase0_token_inventory — Phase 0 Step 1：render 期间 supply token 清点。

对 4 张代表卡（普通随从/英雄/BG/金卡）真实渲染，经 session 间谍记录
``session.memo`` 实际请求的 (domain, item, args) 全集（decode-once 账）。
零产品行为改动：hook=monkeypatch machine.session，脚本退出即还原。

用法（显式运行；不进默认 discover）：
  python -m tests.phase0.phase0_token_inventory \
      --game <game-install-root> --cache-root %LOCALAPPDATA%/Eidolon/cache \
      --out build/phase0/tokens.json
"""
from __future__ import annotations

import sys
import time

from tests.phase0.phase0_supply_spy import (
    CARD_SET,
    SessionSpy,
    base_parser,
    dump_json,
    render_one_card,
    setup_game,
    token_tuple,
)


def main() -> int:
    args = base_parser().parse_args()
    out_png_dir = args.out.rsplit("/", 1)[0] if "/" in args.out else "build/phase0"
    from pathlib import Path

    out_dir = Path(out_png_dir)
    t_setup0 = time.perf_counter()
    setup_game(args.game, args.cache_root)
    t_setup = time.perf_counter() - t_setup0

    spy = SessionSpy()
    cards_doc = []
    for card in CARD_SET:
        out_png = out_dir / f"token-{card.name}.png"
        with spy:                       # 每卡一个会话（_in_session 同形）
            doc = render_one_card(card, out_png)
        doc["tokens"] = [token_tuple(t) for t in spy.requested]
        doc["token_count"] = len(spy.requested)
        cards_doc.append(doc)
        print(f"[phase0] {card.name}: sha={doc['sha256'][:12]} "
              f"{doc['elapsed_ms']}ms tokens={doc['token_count']}")

    union: dict[str, dict] = {}
    for doc in cards_doc:
        for t in doc["tokens"]:
            key = f"{t['domain']}.{t['item']}({t['args']})"
            union.setdefault(key, {"domain": t["domain"], "item": t["item"],
                                   "args": t["args"], "cards": []})
            if doc["name"] not in union[key]["cards"]:
                union[key]["cards"].append(doc["name"])

    dump_json(Path(args.out), {
        "purpose": "phase0 step1 token inventory（session.memo decode-once 全集）",
        "setup_s": round(t_setup, 2),
        "cards": cards_doc,
        "union": [union[k] for k in sorted(union)],
        "union_count": len(union),
        "per_domain_counts": _by_domain([union[k] for k in sorted(union)]),
    })
    return 0


def _by_domain(union: list[dict]) -> dict:
    out: dict[str, int] = {}
    for t in union:
        out[t["domain"]] = out.get(t["domain"], 0) + 1
    return out


if __name__ == "__main__":
    sys.exit(main())
