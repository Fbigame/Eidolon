"""phase0_supply_spy — Phase 0 共用件：session 间谍 + 渲染驱动（spike 专用）。

**零产品改动**：机器面 hook 只 monkeypatch ``eidolon.core.supply.machine.session``
（模块属性；``components._in_session`` 每次调用点 ``from … import session`` 取新值，
patch 生效；不 patch 时产品行为逐位不变）。默认路径零开销——hook 只在本目录
脚本显式进入时安装。

会话语义逐字保持：新建 ``Session`` → set contextvar → yield → reset；
间谍侧在 reset 后抓 ``memo`` 键集（(domain, item, args) 全集=decode-once 账）。

渲染驱动=产品串行分支同序（ctx → dbf → font_dirs → ``_render_one``）；
``_render_one`` 全参缺省（默认 factory=真实渲染链）。卡集四张代表卡：
普通随从 / 英雄（play）/ BG 随从（盾徽语境）/ 金卡（premium 覆盖）。
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from eidolon.contracts import CardRef, GameContext, Problem, ProblemKind, RenderCard  # noqa: E402

# ---------------------------------------------------------------------------
# 代表卡集（任务书：普通/英雄/bg/金卡）
# ---------------------------------------------------------------------------

NORMAL_DBF = 9          # 随从（FRAME_SPECS ally 采样 dbf；帧 Card_Hand_Ally）
BG_DBF = 105108         # BG 随从（fixture 同款；盾徽语境 form=bg）
GOLDEN_DBF = 9          # 金卡=同随从 + premium GOLDEN 覆盖（帧 Card_Hand_Ally_Premium）
HERO_CARD_ID = "HERO_01"  # 英雄（form=hero → PLAY 区 Card_Play_Hero）


@dataclass(frozen=True)
class SpikeCard:
    name: str
    ref: CardRef
    form: str                      # plain / bg / hero
    overrides: tuple[tuple[str, object], ...] = ()


CARD_SET: tuple[SpikeCard, ...] = (
    SpikeCard("normal", CardRef("dbf", NORMAL_DBF), "plain"),
    SpikeCard("hero", CardRef("card", HERO_CARD_ID), "hero"),
    SpikeCard("bg", CardRef("dbf", BG_DBF), "bg"),
    SpikeCard("golden", CardRef("dbf", GOLDEN_DBF),
              "plain", (("premium", "GOLDEN"),)),
)


# ---------------------------------------------------------------------------
# session 间谍（S1 seam 的演练形态：memo_seed 预置 + 请求记账）
# ---------------------------------------------------------------------------

class SeedMemo(dict):
    """记账 memo（dict 子类）：``__contains__`` 即 served 的查键点——所有请求
    （命中种子与未命中）都被记录；写面照常（live 解码产物落 memo）。"""

    def __init__(self, seeds: dict | None = None) -> None:
        super().__init__(seeds or {})
        self.requested: list[tuple] = []   # 按首请求序

    def __contains__(self, token) -> bool:
        if token not in self.requested:
            self.requested.append(token)
        return super().__contains__(token)


class SessionSpy:
    """machine.session 替身工厂（S1 seam 的演练形态）。

    * 记账模式（Step 1）：不预置，抓 ``requested`` = 本次渲染请求的 token 全集；
    * 种子模式（Step 4）：预置 ``seeds``（token → 产物），分拣
      hit（请求且命中种子）/ live（请求未命中=走了真解码）/ unused（没人要）。
    """

    def __init__(self) -> None:
        self.requested: list[tuple] = []
        self.seeds: dict = {}
        self._patched = False

    def install(self, seeds: dict | None = None) -> None:
        import eidolon.core.supply.machine as machine

        self.seeds = dict(seeds or {})
        self.requested = []
        spy = self
        real_session = machine.session

        @contextlib.contextmanager
        def session_with_spy():
            s = machine.Session()
            s.memo = SeedMemo(spy.seeds)     # 替换 memo（保留 Session 形）
            tok = machine._s_current.set(s)
            try:
                yield
            finally:
                machine._s_current.reset(tok)
                spy.requested = list(s.memo.requested)

        machine.session = session_with_spy
        self._patched = True
        self._machine = machine
        self._real_session = real_session

    def uninstall(self) -> None:
        if self._patched:
            self._machine.session = self._real_session
            self._patched = False

    # ---- 分拣（种子模式语义） ----

    @property
    def hit(self) -> list[tuple]:
        return [t for t in self.requested if t in self.seeds]

    @property
    def live(self) -> list[tuple]:
        return [t for t in self.requested if t not in self.seeds]

    @property
    def unused(self) -> list[tuple]:
        return [t for t in self.seeds if t not in self.requested]

    def __enter__(self) -> "SessionSpy":
        self.install()
        return self

    def __exit__(self, *exc) -> None:
        self.uninstall()


def token_tuple(t: tuple) -> dict:
    """token → JSON 形（args 尽量结构化；不可序列化项 repr）。"""
    domain, item, args = t
    out_args = []
    for a in args:
        try:
            json.dumps(a)
            out_args.append(a)
        except (TypeError, ValueError):
            out_args.append(repr(a))
    return {"domain": domain, "item": item, "args": out_args}


# ---------------------------------------------------------------------------
# 渲染驱动（产品串行分支同序；_render_one 默认 factory=真实链）
# ---------------------------------------------------------------------------

def setup_game(game_root: Path, cache_root: Path) -> None:
    """进程身份装一次（ctx → dbf 会话 → 字体目录；§7.2 顺序）。"""
    from eidolon.core.infra import context, dbf
    from eidolon.core.infra.dbf import DbfModule
    from eidolon.core.render.text import glyph_supply
    from eidolon.shell.paths import default_font_dirs

    ctx = GameContext(root=Path(game_root), cache_root=Path(cache_root),
                      locale="zhcn", root_source="phase0-spike")
    context.install(ctx)
    if dbf.installed_default() is None:
        dbf.install_default(DbfModule(ctx.dbf_path))
    glyph_supply.install_font_dirs(default_font_dirs(),
                                   cache_dir=ctx.cache_root / "fonts")


def render_one_card(card: SpikeCard, out_png: Path, *, antialias: bool = False,
                    spy: SessionSpy | None = None) -> dict:
    """单卡渲染（串行分支同构；返回 RenderedCard 形 dict）。

    antialias=False（1x 快速路径）为 Phase 0 spike 缺省——token 集与 supersample
    无关，sha 对拍两侧同设即可；4x 判决态归 Phase 1 对照面。"""
    from eidolon.core.render.api import _render_one

    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    rc = RenderCard(ref=card.ref, out_path=out_png,
                    overrides=dict(card.overrides))
    cm = spy if spy is not None else contextlib.nullcontext()
    t0 = time.perf_counter()
    with cm:
        outcome = _render_one(rc, antialias=antialias)
    elapsed = time.perf_counter() - t0
    if not hasattr(outcome, "sha256"):
        # RenderFailure：把 Problem 摊开（spike 不吞错）
        problem = getattr(outcome, "problem", None)
        raise RuntimeError(f"render 失败 {card.name}: {problem}")
    return {"name": card.name, "ref": [card.ref.kind, str(card.ref.value)],
            "sha256": outcome.sha256, "elapsed_ms": int(elapsed * 1000),
            "warnings": list(outcome.warnings)}


# ---------------------------------------------------------------------------
# CLI 底座
# ---------------------------------------------------------------------------

def base_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--game", required=True, help="游戏安装根（含 Hearthstone.exe）")
    p.add_argument("--cache-root", required=True,
                   help="route 缓存根（route.db 所在；显式，不读 env）")
    p.add_argument("--out", required=True, help="结果 JSON 落盘位")
    return p


def dump_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"[phase0] 已写 {path}")
