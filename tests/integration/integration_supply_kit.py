"""integration_supply_kit — A6 kit 域 e2e（显式跑；需游戏安装 + A6 index）。

判据面（任务单 A6 判据 1-3 + seed 记账 + 开包分面）：

  * **判据 2（种子 Kit 与 live Kit 逐项同形）**：三张对账——
    1) ally kit（标准帧族，kit_extract 转写域）：live ``kit("ally")`` vs warm
       六面 + ``kit_races``/``kit_mesh_refs``——arrays 逐键内容 sha、textures
       逐文件像素 sha、races/mesh_refs 全等、hierarchy 逐节点消费字段
       （name/local/world/mesh_stats/ubertext/renderer 材质名+槽纹理名）、
       report 消费面（actor_components object_refs/scalars + nodes 渲染器槽 +
       fonts）、ubertext canonical、meta 消费键（dbf_id str 归一=记账面）；
    2) 同一对账跑 **seeded Kit**（CardSeeder 种子 token 值）——种子对象与
       live Kit 逐项同形（races/mesh_refs 走 index 面=A3 注入位换面实证）；
    3) **特源 kit**（``ability_kit("normal")``，harness 域）：live 对象 vs
       种子 AbilityKit——harness 捕获=构造性 live 值，recon_meta/hierarchy/
       report/ubertext canonical 全等、arrays 内容 sha、textures 像素 sha、
       portrait 像素 sha、portrait_meta/mesh_refs 全等；obj_texts/fonts_bytes
       不进种子形状（渲染链零消费的提取产物面，显式记账断言）。
  * **判据 1（同 sha，ally 帧卡不炸）**：normal=EX1_350（live sha 冻结值
    671e19a2…，informational）+ golden=BG27_822_G（历史对照 golden 卡
    首行，chain=ally 金随从）——live 渲一次冻 sha → seeded 渲一次 → 逐位一致；
  * **kit 域 token 记账**：seeded 会话请求的 kit/kit_light/ability_kit/
    bacon_kit/badges/btf/ornaments/ta_supplement/material_state/portrait_uv1/
    text.font_asset_params 全部命中（kit 域 live 兜底=0）；
  * **开包分面（A6 目标：kit 域=0）**：seeded 渲染进程内 builtins.open 探针
    ——kit 面函数栈上的游戏文件开包=0；剩余分面（actor_ref 活表读/portrait_
    source/route used-hash md5 等）如实列账不判红（A7 正式判据收口）；
  * **blocker 子进程**：warm A6 读面（kit_races/kit_mesh_refs/kit_light 全帧 +
    supplement 全 item 解码）在 import+open 拦截同窗跑通=零 UnityPy 零游戏
    文件机器证明。

seeded-first 顺序（A4/A5 e2e 同款）：seeded 在净进程先跑（记账不被 live 渲染
的进程级缓存污染）；live 只取 sha 判据与对账基准。**live 渲染必须在
seeder.close() 之后**（entry seed 句柄已卸——live 路径零 index 参与）。

用法（route 缓存暖；index 先建：``python -m eidolon.core.supply_index build
--game <root> --cache-root build/phase1/index-cache --locale zhcn --jobs 4``）::

    set EIDOLON_TEST_GAME=D:\\game\\Hearthstone
    .venv-release\\Scripts\\python.exe -m unittest discover -s tests/integration -p integration_supply_kit.py -t . -v

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

OUT_DIR = REPO / "build" / "a6-kit"

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
# A2-A5 冻结的 EX1_350 live sha（对拍参照；游戏换代则本断言改 informational）
FROZEN_LIVE_SHA = "671e19a2188f7126d0627b5a7b2c647cbe53106c49f9916e384213d88892186e"
# golden（历史对照 golden 卡 首行 BG27_822_G / dbf 103592；chain=ally
# 金随从=A6 ally 帧金卡判据卡；A4/A5 同卡顺带验）
GOLDEN_CARD = "BG27_822_G"
GOLDEN_DBF = 103592

# kit 域面函数名集（开包分面归因；kit 面=0 为 A6 判据，其余=残面列账）
KIT_FACE_FRAMES = frozenset({
    "kit", "kit_light", "ability_kit", "bacon_kit", "badges_kit", "btf_kit",
    "ornaments_kit", "ta_supplement", "material_state", "portrait_uv1",
    "font_asset_params", "_extract_kit", "_recon_walk", "_walk_badge",
    "_walk_spell", "_walk_banner", "scene_for", "kit_for", "font_table",
    "fontdefs", "_font_data",
})
_OPEN_BLOCK_GAME_FILES = ("*.unity3d", "globalgamemanagers*",
                          "resources.assets*", "*.dll")


def _is_game_file(name: str) -> bool:
    from fnmatch import fnmatch

    low = os.path.basename(str(name)).lower()
    return any(fnmatch(low, pat) for pat in _OPEN_BLOCK_GAME_FILES)


class _OpenProbe:
    """builtins.open 探针：游戏文件族开包记账 + 调用栈分面（kit 面=0 判据）。"""

    def __init__(self) -> None:
        self.opens: list[tuple[str, list[tuple[str, str]]]] = []

    def __enter__(self) -> "_OpenProbe":
        self._orig = builtins.open

        def guard(file, *a, **kw):
            if _is_game_file(str(file)):
                stack = [(fr.filename.replace("\\", "/").split("/eidolon/")[-1],
                          fr.name)
                         for fr in traceback.extract_stack()[-12:-1]]
                self.opens.append((str(file), stack))
            return self._orig(file, *a, **kw)

        self._guard = guard
        builtins.open = guard
        return self

    def __exit__(self, *exc) -> None:
        builtins.open = self._orig

    def face_breakdown(self) -> dict[str, int]:
        """开包按面归因：kit 面 / 其余 face（取栈内最内层已知 face）。"""
        out: dict[str, int] = {}
        for _file, stack in self.opens:
            face = "unknown"
            for _fname, fn_name in reversed(stack):
                if fn_name in KIT_FACE_FRAMES:
                    face = f"kit:{fn_name}"
                    break
                if face == "unknown":
                    face = f"other:{fn_name}"
            out[face] = out.get(face, 0) + 1
        return out

    def kit_opens(self) -> list[tuple[str, list[tuple[str, str]]]]:
        return [(f, st) for f, st in self.opens
                if any(n in KIT_FACE_FRAMES for _f, n in st)]


# ---------------------------------------------------------------------------
# 对账件（消费面逐字段；hierarchy 逐节点走查）
# ---------------------------------------------------------------------------

def _arr_shas(arrays: dict) -> dict[str, str]:
    from eidolon.core.supply_index.kit_codec import array_content_sha

    return {k: array_content_sha(k, v) for k, v in arrays.items()}


def _pixel_shas(textures: dict) -> dict[str, str]:
    from eidolon.core.supply_index.schema import sha256_hex

    return {k: sha256_hex(v.tobytes()) for k, v in textures.items()}


def _walk_nodes(node, path: str = ""):
    p = f"{path}/{node.get('name', '')}" if path else node.get("name", "")
    yield node
    for ch in node.get("children") or []:
        yield from _walk_nodes(ch, p)


def _atlas_names(idx, family: str) -> frozenset[str]:
    """帧族类色图集文件名全集（live kit 提取全槽扇出命名式逐字：f"{stem}_{guid8}.png"
    ——index kit 面=EXCLUDED_FACES 排除域，live-only 纹理的精确对账集）。"""
    from pathlib import Path as _P

    probe = idx.color_probe()
    out: set[str] = set()
    for ref in probe.get(family) or []:
        if not (isinstance(ref, str) and ":" in ref):
            continue
        stem, guid = ref.rsplit(":", 1)
        out.add(f"{_P(stem).stem}_{guid[:8]}.png")
    return frozenset(out)


def _node_consumer_fields(n: dict) -> dict:
    """hierarchy 节点的渲染消费字段面（帧编译器/raster/watermark 读什么比什么）。"""
    mats = []
    for r in n.get("renderers") or []:
        for m in r.get("materials") or []:
            if m is None:
                mats.append(None)
                continue
            texs = {}
            for prop, t in (m.get("tex") or {}).items():
                tinfo = t.get("texture") or {}
                texs[prop] = {"name": tinfo.get("name"),
                              "bundle": tinfo.get("bundle")}
            mats.append({"name": m.get("name"), "shader": m.get("shader"),
                         "tex": texs,
                         "colors": m.get("colors"), "floats": m.get("floats")})
    ub = n.get("ubertext")
    return {
        "name": n.get("name"),
        "local": n.get("local"),
        "world": n.get("world"),
        "npz_key": n.get("npz_key"),
        "mesh_stats": n.get("mesh_stats"),
        "active_self": n.get("active_self"),
        "active_in_hierarchy": n.get("active_in_hierarchy"),
        "ubertext": ({"path_id": ub.get("path_id"), "fields": ub.get("fields"),
                      "font_pptr": ub.get("font_pptr"),
                      "font_name": ub.get("font_name"),
                      "font_bundle": ub.get("font_bundle")} if ub else None),
        "renderers": [{"enabled": r.get("enabled"), "materials": mats_i,
                       "renderer_path_id": r.get("renderer_path_id")}
                      for r, mats_i in zip(n.get("renderers") or [],
                                           [mats] * len(n.get("renderers") or []))],
    }


def _hierarchy_diff(live_h: dict, idx_h: dict) -> list[str]:
    """两棵 hierarchy 的消费字段逐节点对账（键面差=列账）。"""
    bad: list[str] = []
    ln = list(_walk_nodes(live_h))
    wn = list(_walk_nodes(idx_h))
    if len(ln) != len(wn):
        return [f"节点数失配 live={len(ln)} index={len(wn)}"]
    for i, (a, b) in enumerate(zip(ln, wn)):
        fa, fb = _node_consumer_fields(a), _node_consumer_fields(b)
        if json.dumps(fa, sort_keys=True, default=str) != \
                json.dumps(fb, sort_keys=True, default=str):
            bad.append(f"节点[{i}] {a.get('name')} 消费字段失配")
    return bad


def _report_diff(live_report: dict, idx_report: dict) -> list[str]:
    """report 消费面逐字段对账（compiler 读 object_refs/scalars/nodes 渲染器槽
    /fonts；textures 账与 class_atlas 注记=提取账面差异不进对拍）。"""
    bad: list[str] = []
    la = (live_report.get("actor_components") or [{}])[0]
    wa = (idx_report.get("actor_components") or [{}])[0]
    if json.dumps(la.get("object_refs"), sort_keys=True, default=str) != \
            json.dumps(wa.get("object_refs"), sort_keys=True, default=str):
        bad.append("actor_components[0].object_refs 失配")
    if json.dumps(la.get("scalars"), sort_keys=True, default=str) != \
            json.dumps(wa.get("scalars"), sort_keys=True, default=str):
        bad.append("actor_components[0].scalars 失配")
    ln = {n.get("path"): n for n in live_report.get("nodes") or []}
    wn = {n.get("path"): n for n in idx_report.get("nodes") or []}
    if set(ln) != set(wn):
        bad.append(f"nodes path 集失配（差 {sorted(set(ln) ^ set(wn))[:4]}）")
    for p in sorted(set(ln) & set(wn)):
        if json.dumps(ln[p].get("components"), sort_keys=True, default=str) != \
                json.dumps(wn[p].get("components"), sort_keys=True, default=str):
            bad.append(f"nodes[{p}].components 失配")
    if json.dumps(live_report.get("fonts"), sort_keys=True, default=str) != \
            json.dumps(idx_report.get("fonts"), sort_keys=True, default=str):
        bad.append("fonts 失配")
    return bad


def _kit_diff(live_kit, six: dict, races, mesh_refs, *, frame: str,
              frame_dir: str | None = None,
              atlas_names: frozenset[str] = frozenset()) -> list[str]:
    """live Kit vs （warm 六面+races/mesh_refs）逐项消费面对账。

    atlas_names=该帧族类色图集文件名全集（live kit 提取全槽扇出进 kit.textures
    ——index 面=EXCLUDED_FACES 记账排除域，图集经 color.atlas token 供给；
    live-only 纹理减 atlas 名集后须为空=排除域精确对账）。"""
    from eidolon.core.supply_index.schema import sha256_hex

    bad: list[str] = []
    live_meta = {k: v for k, v in live_kit.meta.items() if k != "hierarchy"}
    idx_meta = dict(six["meta"])
    for key in ("prefab_ref", "bundle", "guid", "extra_meshes",
                "actor_alt_cost_pos", "root_translation_neutralized"):
        if json.dumps(live_meta.get(key), sort_keys=True, default=str) != \
                json.dumps(idx_meta.get(key), sort_keys=True, default=str):
            bad.append(f"meta.{key} 失配")
    if str(live_meta.get("dbf_id")) != str(idx_meta.get("dbf_id")):
        bad.append(f"meta.dbf_id 失配（{live_meta.get('dbf_id')} vs "
                   f"{idx_meta.get('dbf_id')}——str 归一后仍不等）")
    bad += _hierarchy_diff(live_kit.meta["hierarchy"], six["hierarchy"])
    la, wa = _arr_shas(dict(live_kit.arrays)), _arr_shas(six["arrays"])
    if la != wa:
        only_l = sorted(set(la) - set(wa))[:4]
        only_w = sorted(set(wa) - set(la))[:4]
        bad.append(f"arrays 失配（live-only {only_l} index-only {only_w}）")
    lt, wt = _pixel_shas(live_kit.textures), _pixel_shas(six["textures"])
    live_only = sorted(set(lt) - set(wt) - set(atlas_names))
    warm_only = sorted(set(wt) - set(lt))
    if live_only or warm_only:
        bad.append(f"textures 失配（live-only 非图集 {live_only[:4]} / "
                   f"index-only {warm_only[:4]}；atlas 排除域 "
                   f"{len(set(lt) - set(wt) & atlas_names)} 件=live 全槽扇出）")
    if json.dumps(live_kit.races, sort_keys=True, default=str) != \
            json.dumps(races, sort_keys=True, default=str):
        bad.append("races 失配")
    lm = {k: tuple(v) for k, v in (live_kit.mesh_refs or {}).items()}
    wm = {k: tuple(v) for k, v in (mesh_refs or {}).items()}
    if lm != wm:
        only_l = sorted(set(lm) - set(wm))[:4]
        only_w = sorted(set(wm) - set(lm))[:4]
        bad.append(f"mesh_refs 失配（live-only {only_l} index-only {only_w}）")
    bad += _report_diff(live_kit.report, six["report"])
    if sha256_hex(json.dumps(live_kit.ubertext, sort_keys=True, default=str)
                  .encode()) != sha256_hex(
        json.dumps(six["ubertext"], sort_keys=True, default=str).encode()):
        bad.append("ubertext 失配")
    want_fd = frame_dir if frame_dir is not None else frame
    if live_kit.frame_dir != want_fd:
        bad.append(f"frame_dir 失配（{live_kit.frame_dir} vs {want_fd}）")
    return bad


@unittest.skipUnless(GAME_ROOT and GAME_ROOT.exists(),
                     "本机未设 EIDOLON_TEST_GAME 或路径不存在")
class SupplyKitIntegration(unittest.TestCase):
    """A6 kit 域判据（逐项同形 / 同 sha / 记账 / kit 面零开包 / blocker）。"""

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

    # ---- 判据 2a：ally kit 对账（live vs warm 面） ----

    def test_1_ally_kit_parity_live_vs_warm(self) -> None:
        from eidolon.core.recipes.frames import kit as live_kit
        from eidolon.core.supply import machine
        from eidolon.core.supply_index.warm import SupplyIndex

        with machine.session():
            live = live_kit("ally")
        with SupplyIndex(INDEX_ROOT) as idx:
            six = idx.kit("ally")
            races = idx.kit_races("ally")
            mesh_refs = idx.kit_mesh_refs("ally")
            atlas_names = _atlas_names(idx, "minionCardTextures")
        bad = _kit_diff(live, six, races, mesh_refs, frame="ally",
                        frame_dir="ally_frame", atlas_names=atlas_names)
        self.assertEqual(bad, [], f"ally kit 消费面对账失配：{bad[:8]}")
        n_mesh = len(mesh_refs or {})
        n_race = len((races or {}).get("strings", {}))
        print(f"[a6-kit] ally kit 对账：arrays {len(live.arrays)} 键/"
              f"textures {len(live.textures)}-{'atlas 排除 ' + str(len(set(live.textures) - set(six['textures'])))} 件/"
              f"节点 {sum(1 for _ in _walk_nodes(live.meta['hierarchy']))}/"
              f"mesh_refs {n_mesh}/races strings {n_race} 逐项全等（消费面）")

    # ---- 判据 2b/2c：seeded Kit 与特源 kit 对账（种子值=live 形状） ----

    def _seeds_for(self, card_id: str) -> dict:
        from eidolon.core.supply_index.seed import CardSeeder

        seeder = CardSeeder.open(INDEX_ROOT, ctx_locale=self.ctx.locale,
                                 ctx_identity=self.ident["identity"])
        self.assertIsNotNone(seeder, f"index 打不开/身份不同源：{INDEX_ROOT}")
        self.addCleanup(seeder.close)
        seeds = seeder.seeds_for_card(card_id)
        self.assertIsNotNone(seeds, "该卡弃种（严格门/转换失败）——见 WARN")
        return seeds

    def test_2_seeded_ally_kit_parity(self) -> None:
        from eidolon.core.recipes.frames import kit as live_kit
        from eidolon.core.supply import machine
        from eidolon.core.supply_index.warm import SupplyIndex

        seeds = self._seeds_for(NORMAL_CARD)
        kit = seeds.get(("frames", "kit", ("ally",)))
        self.assertIsNotNone(kit, "种子缺 kit(ally) token——races/mesh_refs "
                                  "面缺席或 warm kit 失败（见 WARN）")
        with machine.session():
            live = live_kit("ally")
        with SupplyIndex(INDEX_ROOT) as idx:
            atlas_names = _atlas_names(idx, "minionCardTextures")
        six = {"meta": {k: v for k, v in kit.meta.items() if k != "hierarchy"},
               "hierarchy": kit.meta["hierarchy"], "arrays": dict(kit.arrays),
               "textures": kit.textures, "report": kit.report,
               "ubertext": kit.ubertext}
        bad = _kit_diff(live, six, kit.races, kit.mesh_refs, frame="ally",
                        frame_dir="ally_frame", atlas_names=atlas_names)
        self.assertEqual(bad, [], f"seeded ally kit 对账失配：{bad[:8]}")
        self.assertIsNotNone(kit.races, "seeded Kit.races 必带（GetRaceText "
                                        "无条件消费——A3 注入位换 index 面）")
        self.assertEqual(kit.frame_dir, "ally_frame",
                         "frame_dir=live spec 形（A6 对账修正）")

    def test_3_ability_kit_parity_live_vs_seeded(self) -> None:
        from eidolon.core.recipes.frames import ability_kit as live_ability
        from eidolon.core.supply import machine
        from eidolon.core.supply_index.schema import sha256_hex

        seeds = self._seeds_for(NORMAL_CARD)
        seeded = seeds.get(("frames", "ability_kit", ("normal",)))
        self.assertIsNotNone(seeded, "种子缺 ability_kit(normal) token")
        with machine.session():
            live = live_ability("normal")
        self.assertEqual(
            json.dumps({k: v for k, v in live.recon_meta.items()
                        if k != "hierarchy"}, sort_keys=True, default=str),
            json.dumps({k: v for k, v in seeded.recon_meta.items()
                        if k != "hierarchy"}, sort_keys=True, default=str),
            "recon_meta（拆 hierarchy 面）canonical 全等")
        self.assertEqual(
            sha256_hex(json.dumps(live.recon_meta["hierarchy"], sort_keys=True,
                                  default=str).encode()),
            sha256_hex(json.dumps(seeded.recon_meta["hierarchy"], sort_keys=True,
                                  default=str).encode()),
            "hierarchy canonical 全等")
        self.assertEqual(_arr_shas(dict(live.arrays)), _arr_shas(dict(seeded.arrays)),
                         "arrays 逐键内容 sha 全等")
        self.assertEqual(_pixel_shas(live.textures), _pixel_shas(seeded.textures),
                         "textures 逐文件像素 sha 全等")
        if live.portrait is not None:
            self.assertEqual(sha256_hex(live.portrait.tobytes()),
                             sha256_hex(seeded.portrait.tobytes()),
                             "portrait 像素 sha 全等")
        self.assertEqual(live.portrait_meta, seeded.portrait_meta)
        self.assertEqual(
            sha256_hex(json.dumps(live.report, sort_keys=True,
                                  default=str).encode()),
            sha256_hex(json.dumps(seeded.report, sort_keys=True,
                                  default=str).encode()),
            "report canonical 全等（harness 捕获=live 值构造性）")
        self.assertEqual(
            sha256_hex(json.dumps(live.ubertext, sort_keys=True,
                                  default=str).encode()),
            sha256_hex(json.dumps(seeded.ubertext, sort_keys=True,
                                  default=str).encode()),
            "ubertext canonical 全等")
        self.assertEqual({k: tuple(v) for k, v in live.mesh_refs.items()},
                         {k: tuple(v) for k, v in seeded.mesh_refs.items()})
        # 显式账：obj_texts/fonts_bytes 不进种子形状（渲染链零消费提取产物面）
        self.assertEqual(seeded.obj_texts, {})
        self.assertEqual(seeded.fonts_bytes, {})
        print(f"[a6-kit] ability_kit(normal) 对账：recon_meta/hierarchy/report/"
              f"ubertext canonical + arrays {len(live.arrays)}/textures "
              f"{len(live.textures)}/mesh_refs {len(live.mesh_refs)} 全等；"
              "obj_texts/fonts_bytes=种子形状外（记账）")

    # ---- 判据 1 + 记账 + kit 面零开包 ----

    def _seed_and_render(self, name: str, card_id: str, dbf: int,
                         *, bg_style: bool = False):
        import eidolon.core.supply.machine as machine
        from eidolon.core.supply_index.seed import CardSeeder

        seeder = CardSeeder.open(INDEX_ROOT, ctx_locale=self.ctx.locale,
                                 ctx_identity=self.ident["identity"])
        self.assertIsNotNone(seeder, f"index 打不开/身份不同源：{INDEX_ROOT}")
        with seeder:
            seeds = seeder.seeds_for_card(card_id)
            self.assertIsNotNone(seeds, "该卡弃种（严格门/转换失败）——见 WARN")
            ledger = seeder.last_ledger
            print(f"[a6-kit] {name} {ledger.summary()}")

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
        kit_domains = {"frames", "text"}
        kit_items = {"kit", "kit_light", "ability_kit", "bacon_kit",
                     "badges_kit", "btf_kit", "ornaments_kit", "ta_supplement",
                     "material_state", "portrait_uv1", "font_asset_params"}
        kit_live = [t for t in live
                    if (t[0] in kit_domains and t[1] in kit_items)]
        kit_hit = [t for t in hit if (t[0] in kit_domains
                                      and t[1] in kit_items)]
        breakdown = probe.face_breakdown()
        print(f"[a6-kit] {name} seeded sha={sha_seed} render={t_seed:.1f}s")
        print(f"[a6-kit] {name} 记账 hit={len(set(hit))} live={len(set(live))} "
              f"unused={len(set(unused))}")
        print(f"[a6-kit] {name} kit 域 token hit={len(set(kit_hit))} "
              f"live={len(set(kit_live))}（{sorted({repr(t) for t in kit_hit + kit_live})}）")
        print(f"[a6-kit] {name} 开包分面：{json.dumps(breakdown, ensure_ascii=False)}")
        return sha_seed, (kit_hit, kit_live), probe

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

    def test_4_normal_ex1_350_same_sha_kit_domain_closed(self) -> None:
        sha_seed, (kit_hit, kit_live), probe = \
            self._seed_and_render("normal", NORMAL_CARD, NORMAL_DBF)
        self.assertEqual(kit_live, [],
                         f"kit 域 token 不得 live 兜底：{kit_live}")
        self.assertTrue(kit_hit, "kit 域 token 应有命中")
        kit_open = probe.kit_opens()
        self.assertEqual(kit_open, [],
                         f"seeded 渲染 kit 面开包：{kit_open[:3]}")
        sha_live = self._render_live("normal", NORMAL_DBF)
        print(f"[a6-kit] normal live  sha={sha_live}")
        self.assertEqual(sha_seed, sha_live, "EX1_350 seeded sha 与 live 逐位一致")
        if sha_live != FROZEN_LIVE_SHA:
            print(f"[a6-kit] WARN: live sha 与 A2 冻结值不同（游戏换代/语料漂移）"
                  f"——本判据以同会话 live 为准")

    def test_5_golden_bg27_822_same_sha(self) -> None:
        sha_seed, (kit_hit, kit_live), probe = \
            self._seed_and_render("golden", GOLDEN_CARD, GOLDEN_DBF,
                                  bg_style=True)
        self.assertEqual(kit_live, [])
        self.assertEqual(probe.kit_opens(), [])
        sha_live = self._render_live("golden", GOLDEN_DBF, bg_style=True)
        print(f"[a6-kit] golden live  sha={sha_live}")
        self.assertEqual(sha_seed, sha_live,
                         f"{GOLDEN_CARD}（历史对照 golden ally 帧）seeded sha "
                         "与 live 逐位一致")

    # ---- blocker 子进程（warm A6 读面零游戏文件） ----

    def test_6_warm_kit_blocker_subprocess(self) -> None:
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
               "eidolon.core.supply_index.mip_extract",
               "eidolon.core.supply_index.supplement_extract"]
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
kit_frames = idx.kit_frames()
races = {f: idx.kit_races(f) for f in kit_frames}
mesh = {f: len(idx.kit_mesh_refs(f) or {}) for f in kit_frames}
light = {f: len(idx.kit_light(f)["hierarchy"].get("children", []))
         for f in idx.kit_light_frames()}
n_supp = 0
for r in idx.conn.execute(
        "SELECT domain, item, params_json FROM items WHERE codec='supp'"):
    parts = idx.supplement_parts(r["domain"], r["item"],
                                 __import__("json").loads(r["params_json"]))
    n_supp += len(parts)
race_frames = [f for f, v in races.items()
               if isinstance(v, dict) and isinstance(v.get("strings"), dict)]
print(json.dumps({"kit_frames": len(kit_frames),
                  "race_frames": race_frames,
                  "mesh_refs_total": sum(mesh.values()),
                  "kit_light_frames": len(light),
                  "supp_parts": n_supp, "opens": 0}))
'''
        p = subprocess.run([sys.executable, "-c", child, str(INDEX_ROOT)],
                           capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(p.returncode, 0,
                         f"blocker 子进程失败：{p.stderr.strip()[-800:]}")
        doc = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertGreater(doc["kit_frames"], 0)
        self.assertIn("ally", doc["race_frames"],
                      "races 帧族面缺席（ally）——GetRaceText 硬缺口未闭合")
        self.assertGreater(doc["mesh_refs_total"], 0)
        self.assertGreaterEqual(doc["kit_light_frames"], 9)
        self.assertGreaterEqual(doc["supp_parts"], 8)
        print(f"[a6-kit] blocker 子进程：kit {doc['kit_frames']} 帧（races 帧 "
              f"{doc['race_frames']}）+ mesh_refs {doc['mesh_refs_total']} 条"
              f"+ kit_light {doc['kit_light_frames']} 帧 + supplement "
              f"{doc['supp_parts']} parts 全程零游戏文件读取"
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
