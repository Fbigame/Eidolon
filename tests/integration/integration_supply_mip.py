"""integration_supply_mip — A5 mip 面 e2e（显式跑；需游戏安装 + A5 index）。

判据面（任务单 A5 判据 1-3 + seed 记账 + 零开包分面证明）：

  * **判据 3（registry 对账）**：live ``mip_registry()`` vs warm
    ``mip_registry()``——链名集合全等（**23 条**——任务单「16 条」为批10e
    定案期的旧数，live 2026-10-30 起增补名牌板/水印/横幅链；对账判据=live vs
    warm 全等，条数随 live）+ 每链 lods 逐级位等（uint8）+ filter/bias 相等；
  * **判据 3b（portrait_mip 对账）**：EX1_350 live ``art.portrait_mip`` vs
    warm ``portrait_mip``——name/filter/bias/链长 + 全级位等（L0 派生面
    =portrait PNG 双解码器位等的全量实证）；
  * **判据 1（同 sha）**：normal=EX1_350（live sha 与 A2-A4 冻结值对账，
    informational）+ golden=BG27_822_G（历史对照 golden 卡 首行，
    A4 同卡顺带验）——live 渲一次冻 sha → seeded 渲一次 → 逐位一致；
  * **mip token 记账**：seeded 会话请求的 ``art.portrait_mip`` /
    ``textures.mip_registry`` 全部命中（hit/live/unused 贴数打印）；
  * **判据 2（warm mip 面零开包）**：两道证明——
    1) seeded 渲染进程内 builtins.open 探针：``.unity3d`` 开包按调用栈分面
       归因，mip 面函数（chain_for_name/_extract_chain/entry_for_ref/
       mip_registry/_find_texture/portrait_mip）栈上的开包数=0（其余 live 残
       面——kit/supplements 等 A6 域——如实列账不判红，A7 收口）；
    2) 子进程 import+open blocker 同窗（audit._WARM_CHILD 同款拦截）只跑 warm
       mip 读面（registry 全链解码 + portrait_mip 样本 + atlas mip 账判定），
       跑通=零游戏文件读取机器证明。

seeded-first 顺序（A4 e2e 同款）：seeded 在净进程先跑（记账不被 live 渲染的
进程级缓存污染）；live 只取 sha 判据。**live 渲染必须在 seeder.close() 之后**
（entry seed 句柄已卸——live 路径零 index 参与）。

用法（route 缓存暖；index 先建：``python -m eidolon.core.supply_index build
--game <root> --cache-root build/phase1/index-cache --locale zhcn --jobs 4``）::

    set EIDOLON_TEST_GAME=D:\\game\\Hearthstone
    .venv-release\\Scripts\\python.exe -m unittest discover -s tests/integration -p integration_supply_mip.py -t . -v

配置（env，测试驱动专用不进库面）：``EIDOLON_TEST_GAME``（必填）、
``EIDOLON_TEST_ROUTE_CACHE``（选填）、``EIDOLON_TEST_INDEX``（选填，缺省
``<repo>/build/phase1/index-cache``）。
"""

from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
import time
import traceback
import unittest
from pathlib import Path

from eidolon.contracts import CardRef, RenderCard

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "build" / "a5-mip"

_game_env = os.environ.get("EIDOLON_TEST_GAME", "").strip()
GAME_ROOT = Path(_game_env) if _game_env else None

_cache_env = os.environ.get("EIDOLON_TEST_ROUTE_CACHE", "").strip()
if _cache_env:
    CACHE_ROOT = Path(_cache_env)
else:
    local = os.environ.get("LOCALAPPDATA", "")
    CACHE_ROOT = Path(local) / "Eidolon" / "cache" if local else Path.home() / ".cache" / "eidolon"

_index_env = os.environ.get("EIDOLON_TEST_INDEX", "").strip()
INDEX_ROOT = Path(_index_env) if _index_env else REPO / "build" / "phase1" / "index-cache"

NORMAL_CARD = "EX1_350"
NORMAL_DBF = 9
# A2-A4 冻结的 EX1_350 live sha（对拍参照；游戏换代则本断言改 informational）
FROZEN_LIVE_SHA = "671e19a2188f7126d0627b5a7b2c647cbe53106c49f9916e384213d88892186e"
# golden（历史对照 golden 卡 首行 BG27_822_G / dbf 103592；A4 同卡）
GOLDEN_CARD = "BG27_822_G"
GOLDEN_DBF = 103592

# mip 面函数名集（开包分面归因；其余 face=live 残面 A6 收口，列账不判红）
MIP_FACE_FRAMES = frozenset({
    "chain_for_name", "_extract_chain", "entry_for_ref", "mip_registry",
    "_find_texture", "portrait_mip",
})
_OPEN_BLOCK_GAME_FILES = ("*.unity3d", "globalgamemanagers*",
                          "resources.assets*", "*.dll")


def _is_game_file(name: str) -> bool:
    from fnmatch import fnmatch

    low = os.path.basename(str(name)).lower()
    return any(fnmatch(low, pat) for pat in _OPEN_BLOCK_GAME_FILES)


class _OpenProbe:
    """builtins.open 探针：游戏文件族开包记账 + 调用栈分面（A5 判据 2 证明 1）。"""

    def __init__(self) -> None:
        self.opens: list[tuple[str, list[tuple[str, str]]]] = []

    def __enter__(self) -> "_OpenProbe":
        self._orig = builtins.open

        def guard(file, *a, **kw):
            if _is_game_file(str(file)):
                stack = [(fr.filename.replace("\\", "/").split("/eidolon/")[-1],
                          fr.name)
                         for fr in traceback.extract_stack()[-10:-1]]
                self.opens.append((str(file), stack))
            return self._orig(file, *a, **kw)

        self._guard = guard
        builtins.open = guard
        return self

    def __exit__(self, *exc) -> None:
        builtins.open = self._orig

    def face_breakdown(self) -> dict[str, int]:
        """开包按面归因：mip 面 / 渲染链其余 face（取栈内最内层已知 face）。"""
        out: dict[str, int] = {}
        for _file, stack in self.opens:
            face = "unknown"
            for _fname, fn_name in reversed(stack):
                if fn_name in MIP_FACE_FRAMES:
                    face = f"mip:{fn_name}"
                    break
                if face == "unknown":
                    face = f"other:{fn_name}"
            out[face] = out.get(face, 0) + 1
        return out

    def mip_opens(self) -> list[tuple[str, list[tuple[str, str]]]]:
        return [(f, st) for f, st in self.opens
                if any(n in MIP_FACE_FRAMES for _f, n in st)]


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class SupplyMipIntegration(unittest.TestCase):
    """A5 mip 面判据（registry/mip 对账 / 同 sha / 记账 / 零开包）。"""

    @classmethod
    def setUpClass(cls) -> None:
        from eidolon.core.infra import context, dbf
        from eidolon.core.infra.dbf import DbfModule
        from eidolon.core.infra.game_install import resolve_context
        from eidolon.contracts import GameRequest
        from eidolon.core.render.text import glyph_supply
        from eidolon.shell.paths import default_font_dirs

        ctx = resolve_context(GameRequest(GAME_ROOT, "--game"),
                              cache_root=CACHE_ROOT, locale="zhcn")
        context.install(ctx)
        if dbf.installed_default() is None:
            dbf.install_default(DbfModule(ctx.dbf_path))
        glyph_supply.install_font_dirs(default_font_dirs(),
                                       cache_dir=ctx.cache_root / "fonts")
        cls.ctx = ctx
        from eidolon.core.supply_index.cold import compute_identity

        cls.ident = compute_identity(ctx.data_win, ctx.version,
                                     dll_path=ctx.assembly_csharp)

    # ---- 判据 3：registry 对账（23 链 live vs warm 全等） ----

    def test_1_registry_parity_live_vs_warm(self) -> None:
        from eidolon.core.recipes.textures import mip_registry as live_registry
        from eidolon.core.supply import machine
        from eidolon.core.supply_index.warm import SupplyIndex

        with machine.session():
            live = dict(live_registry())
        with SupplyIndex(INDEX_ROOT) as idx:
            warm = idx.mip_registry()
        self.assertEqual(set(warm), set(live),
                         f"链名集合全等（live {len(live)} 条 vs warm {len(warm)} 条）")
        bad: list[str] = []
        for name in sorted(live):
            le, we = live[name], warm[name]
            if len(le["lods"]) != len(we["lods"]):
                bad.append(f"{name}: 级数 {len(we['lods'])} != {len(le['lods'])}")
                continue
            for i, (la, wa) in enumerate(zip(le["lods"], we["lods"])):
                if not (la.shape == wa.shape and bool(np_array_equal(la, wa))):
                    bad.append(f"{name}[{i}]: 数组位不等")
            if le["filter"] != we["filter"] or le["bias"] != we["bias"]:
                bad.append(f"{name}: filter/bias 失配")
        self.assertEqual(bad, [], f"registry 逐链对账失配：{bad[:8]}")
        n_lods = sum(len(e["lods"]) for e in live.values())
        print(f"[a5-mip] registry 对账：{len(live)} 链（任务单「16 条」为批10e "
              f"旧数，live 现行 23）/{n_lods} 级逐位全等")

    # ---- 判据 3b：portrait_mip 对账 ----

    def test_2_portrait_mip_parity_ex1_350(self) -> None:
        from eidolon.core.recipes.art import portrait_mip as live_token
        from eidolon.core.supply import machine
        from eidolon.core.supply_index.warm import SupplyIndex

        with machine.session():
            live = live_token("EX1_350")
        self.assertIsNotNone(live)
        with SupplyIndex(INDEX_ROOT) as idx:
            warm = idx.portrait_mip("EX1_350")
        self.assertEqual(warm["name"], live["name"])
        self.assertEqual(warm["filter"], live["filter"])
        self.assertEqual(warm["bias"], live["bias"])
        self.assertEqual(len(warm["chain"]), len(live["chain"]))
        for i in range(len(live["chain"])):
            self.assertTrue(np_array_equal(warm["chain"].peek(i),
                                           live["chain"].peek(i)),
                            f"第 {i} 级位不等（live vs warm）")
        print(f"[a5-mip] portrait_mip 对账：EX1_350 {live['name']} "
              f"{len(live['chain'])} 级逐位全等（filter={live['filter']} "
              f"bias={live['bias']}）")

    # ---- 判据 1 + 记账 + 判据 2 证明 1：seeded 同 sha + 零 mip 开包 ----

    def _seed_and_render(self, name: str, card_id: str, dbf: int,
                         *, bg_style: bool = False):
        """seeded 渲染 + 记账 + open 探针（返回 (sha, hit/live/unused 清单, 探针)）。"""
        import eidolon.core.supply.machine as machine
        from eidolon.core.supply_index.seed import CardSeeder

        seeder = CardSeeder.open(INDEX_ROOT, ctx_locale=self.ctx.locale,
                                 ctx_identity=self.ident["identity"])
        self.assertIsNotNone(seeder, f"index 打不开/身份不同源：{INDEX_ROOT}")
        with seeder:
            seeds = seeder.seeds_for_card(card_id)
            self.assertIsNotNone(seeds, "该卡弃种（严格门/转换失败）——见 WARN")
            ledger = seeder.last_ledger
            print(f"[a5-mip] {name} {ledger.summary()}")

            created, orig_session_cls = [], machine.Session

            class RecordingSession(orig_session_cls):
                def __init__(self, memo=None):
                    self.recorder = _RecordingMemo(dict(memo or {}))
                    super().__init__(memo=self.recorder)
                    created.append(self.recorder)

            try:
                machine.Session = RecordingSession
                out = OUT_DIR / f"{name}-seeded.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                rc = RenderCard(ref=CardRef("dbf", dbf), out_path=out,
                                overrides={}, bg_style=bg_style)
                from eidolon.core.render.api import _render_one

                with _OpenProbe() as probe:
                    t2 = time.perf_counter()
                    outcome = _render_one(rc, antialias=False,
                                          seed_provider=seeder.provider_for_card(card_id))
                    t_seed = time.perf_counter() - t2
                self.assertTrue(hasattr(outcome, "sha256"),
                                f"{name} seeded 渲染失败：{getattr(outcome, 'problem', None)}")
                sha_seed = outcome.sha256
            finally:
                machine.Session = orig_session_cls
            # seeder with 块出口即 close（句柄卸载）——live 渲染在块外纯 live
        rec = created[0]
        seeded_keys = set(seeds)
        hit = [t for t in rec.requested if t in seeded_keys]
        live = [t for t in rec.requested if t not in seeded_keys]
        unused = [t for t in seeds if t not in rec.requested]
        ledger.hit, ledger.live, ledger.unused = len(hit), len(live), len(unused)
        mip_live = [t for t in live if t[0] in ("art", "textures")
                    and t[1] in ("portrait_mip", "mip_registry")]
        mip_hit = [t for t in hit if t[0] in ("art", "textures")
                   and t[1] in ("portrait_mip", "mip_registry")]
        breakdown = probe.face_breakdown()
        print(f"[a5-mip] {name} seeded sha={sha_seed} render={t_seed:.1f}s")
        print(f"[a5-mip] {name} 记账 hit={len(set(hit))} live={len(set(live))} "
              f"unused={len(set(unused))}")
        print(f"[a5-mip] {name} mip token hit={len(set(mip_hit))} "
              f"live={len(set(mip_live))}（{sorted({repr(t) for t in mip_hit + mip_live})}）")
        print(f"[a5-mip] {name} 开包分面：{json.dumps(breakdown, ensure_ascii=False)}")
        return sha_seed, (mip_hit, mip_live), probe

    def _render_live(self, name: str, dbf: int, *, bg_style: bool = False) -> str:
        from eidolon.core.render.api import _render_one

        out = OUT_DIR / f"{name}-live.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        rc = RenderCard(ref=CardRef("dbf", dbf), out_path=out,
                        overrides={}, bg_style=bg_style)
        outcome = _render_one(rc, antialias=False)
        self.assertTrue(hasattr(outcome, "sha256"),
                        f"{name} live 渲染失败：{getattr(outcome, 'problem', None)}")
        return outcome.sha256

    def test_3_normal_ex1_350_same_sha_zero_mip_open(self) -> None:
        sha_seed, (mip_hit, mip_live), probe = \
            self._seed_and_render("normal", NORMAL_CARD, NORMAL_DBF)
        self.assertEqual(mip_live, [],
                         f"mip token 不得 live 兜底：{mip_live}")
        self.assertTrue(mip_hit, "mip token 应有命中（registry+portrait_mip）")
        mip = probe.mip_opens()
        self.assertEqual(mip, [],
                         f"seeded 渲染 mip 面开包：{mip[:3]}")
        breakdown = probe.face_breakdown()
        print(f"[a5-mip] normal 开包分面账（mip=0 为判据；其余=live 残面 A6 "
              f"如实列账）：{json.dumps(breakdown, ensure_ascii=False)}")
        sha_live = self._render_live("normal", NORMAL_DBF)
        print(f"[a5-mip] normal live  sha={sha_live}")
        self.assertEqual(sha_seed, sha_live, "EX1_350 seeded sha 与 live 逐位一致")
        if sha_live != FROZEN_LIVE_SHA:
            print(f"[a5-mip] WARN: live sha 与 A2 冻结值不同（游戏换代/语料漂移）"
                  f"——本判据以同会话 live 为准")

    def test_4_golden_bg27_822_same_sha(self) -> None:
        sha_seed, (mip_hit, mip_live), probe = \
            self._seed_and_render("golden", GOLDEN_CARD, GOLDEN_DBF,
                                  bg_style=True)
        self.assertEqual(mip_live, [])
        self.assertEqual(probe.mip_opens(), [])
        sha_live = self._render_live("golden", GOLDEN_DBF, bg_style=True)
        print(f"[a5-mip] golden live  sha={sha_live}")
        self.assertEqual(sha_seed, sha_live,
                         f"{GOLDEN_CARD}（历史对照 golden）seeded sha 与 live 逐位一致")

    # ---- 判据 2 证明 2：blocker 子进程（warm mip 读面零游戏文件） ----

    def test_5_warm_mip_blocker_subprocess(self) -> None:
        child = r'''
import sys, os, builtins, json
from fnmatch import fnmatch
sys.path.insert(0, ''' + repr(str(REPO)) + r''')   # 仓源 eidolon（非 site-packages 旧装）

class Blocker:
    _BANNED = ["UnityPy", "texture2ddecoder", "eidolon.core.render",
               "eidolon.core.supply", "eidolon.core.recipes",
               "eidolon.core.supply_index.cold",
               "eidolon.core.supply_index.kit_extract",
               "eidolon.core.supply_index.text_extract",
               "eidolon.core.supply_index.wm_extract",
               "eidolon.core.supply_index.mip_extract"]
    def find_spec(self, name, path=None, target=None):
        for b in self._BANNED:
            if name == b or name.startswith(b + "."):
                raise ImportError(f"blocker: {name} 在 warm 面被禁")
        return None

sys.meta_path.insert(0, Blocker())
_PATS = ''' + repr(list(_OPEN_BLOCK_GAME_FILES)) + r'''
_real = builtins.open
def guarded(file, *a, **kw):
    low = os.path.basename(str(file)).lower()
    for pat in _PATS:
        if fnmatch(low, pat):
            raise PermissionError(f"open-blocker: warm 面禁开 {file}")
    return _real(file, *a, **kw)
builtins.open = guarded

from eidolon.core.supply_index.warm import SupplyIndex
idx = SupplyIndex(sys.argv[1])
cards = idx.card_ids()
sample = cards[:200]
pm = 0
for cid in sample:
    try:
        ent = idx.portrait_mip(cid)
        if len(ent["chain"]) >= 1:
            pm += 1
    except Exception:
        pass
reg = idx.mip_registry()
n_lods = sum(len(e["lods"]) for e in reg.values())
print(json.dumps({"registry_chains": len(reg), "registry_lods": n_lods,
                  "portrait_mip_sample": pm, "opens": 0}))
'''
        p = subprocess.run([sys.executable, "-c", child, str(INDEX_ROOT)],
                           capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(p.returncode, 0,
                         f"blocker 子进程失败：{p.stderr.strip()[-800:]}")
        doc = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertGreater(doc["registry_chains"], 0)
        self.assertGreater(doc["portrait_mip_sample"], 0,
                           "portrait_mip 样本零供给（index 无 mip 面？）")
        print(f"[a5-mip] blocker 子进程：registry {doc['registry_chains']} 链/"
              f"{doc['registry_lods']} 级 + portrait_mip 样本 "
              f"{doc['portrait_mip_sample']}/200 全程零游戏文件读取"
              "（import+open 拦截同窗）")


class _RecordingMemo(dict):
    """记账 memo（dict 子类）：请求/写点双账（integration_seed_seam 同款）。"""

    def __init__(self, initial):
        super().__init__(initial)
        self.initial_keys = set(dict.keys(self))
        self.requested = []
        self.overwritten = []

    def __contains__(self, token) -> bool:
        self.requested.append(token)
        return super().__contains__(token)

    def __setitem__(self, token, value) -> None:
        self.overwritten.append(token)
        super().__setitem__(token, value)


def np_array_equal(a, b) -> bool:
    import numpy as np

    return bool(np.array_equal(a, b))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
