"""glyph_supply — 字形供给 v3.1（引擎两级缺字回退 + 字体账；原卡已闭）。

口径正典：docs/notes/text-rendering-pipeline.md「字形栅格化口径」；机制账=
engine-font-fingerprint findings §4（引擎字体指纹实验，过程档在对应实验目录）。

本模块的四件事（全部**供给策略**，栅格化本身归 ft_unhinted）：

1. **两级缺字回退**（引擎写法照抄；`resolve_fallback`）：
   ① Font 自带名单 = 资产 `m_FallbackFonts`（运行时经 `recipes.text.font_asset_params` 从
      游戏 assets 直提，内容面=原 `data/fonts_zhcn/font_asset_params.json` 的
      `fonts.<fontObjectName>.fallback_object_names`；字形字节经 recipes.text 域项链
      `fontdefs()`→`font_ttf_bytes()` 映射；同字节孪生档（zhCN 名档）必然同样缺字，
      于是自然下沉到第二级）；
   ② UnityPlayer 内置 **11 项有序族名表**（`_FALLBACK_FAMILIES`，顺序=引擎构造序，
      勿改序）：每项要求「族名可解析 ∧ 该 face 有该字形」，首个命中即用；未命中按引擎
      语义拼 `" Bold"` 重试；全失败 → 尝试 U+FFFD（有则用），再失败 → advance 0 +
      响亮事件（不静默出 tofu）。
   **OS 只出字体文件**：目录=`install_font_dirs(dirs)` 注入（产品组合层在
   preflight/worker initializer、首次 `family_index()` 之前调用；未注入=回落
   `C:/Windows/Fonts` 产品兜底——**写死的政策常量**，不读 OS 目录变量）（扩展名
   ttf/ttc/otf），fontTools 读 name 表做族名精确匹配
   （nameID 1/16 为主，Windows 英文优先；nameID 4 全名 与 `family + " " + subfamily`
   仅作 `" Bold"` 重试的可解析别名）。栅格化仍是引擎口径 FT unhinted（ft_unhinted）。
   TTC **只用 face index 0**：驱动 `get_face` 固定 face 0（引擎侧不可判别：Microsoft
   YaHei 的 ttc face0/face1 对样本字逐位相同、face2 报错 → 按默认 0）；索引也只登记
   face 0 的族名，非 0 face 不参选（记录 `ttc_face` 恒 0，如实）。
   每命中记全账：`family / file / sha256 / ttc_face / version(name+version 串) /
   advance_px`（advance=回退字体自身 FT advance 的 `(x+32)>>6`；现有 oracle 样本
   （㐀/㐇/䲨/嗞/砮/鳛）全 CJK 全角，与「强制全宽=em」同值，故取前者并记账待判别）。

2. **资产参数**（`font_asset_params()`/`character_padding()`/`fallback_object_names()`）：
   图集格框留白 `m_CharacterPadding` 的唯一读法（GLEI=4、BGO=2；**禁写死**）。参数
   来源=运行时 supply 提取（`eidolon.core.recipes.text.font_asset_params`，游戏 assets 的
   Unity Font 对象直读）；原 `data/fonts_zhcn/font_asset_params.json` 降**对拍 oracle**
   （生产零读；渲染路径 data 依赖=0 收口）。未知 fontObjectName → 响亮 KeyError（不猜默认值）。

3. **字体字节 → 路径**（`materialize_ttf`）：驱动只吃文件路径，而游戏字体是
   Font.m_FontData 真内存字节。本函数把字节落成**内容寻址**（sha256 命名）的进程级
   缓存文件（`<cache_dir>/<sha>.ttf`；cache_dir=`install_font_dirs` 显式给出，缺省=
   `GameContext.cache_root / "fonts"`——**core 唯一在 out_dir 之外的写盘**；不再落
   系统 temp（上游的 temp 字体缓存目录随 env 面删除）；进程内 memo，跨进程同内容复用）。
   落盘**必须在树外**：树内新文件会改 gate 的 input_fingerprint（渲染输入指纹）。

4. **响亮账**：缺字/回退事件（`record_missing`/`drain_missing`）与渲染所用字体文件
   哈希账（`font_report`）——drain 位=components.render_with → gate_report。

消费面：`uber_text.FontMetrics`（char_info 缺字分支 = 布局与栅格化同判单源）与
`text_atlas`（格框 pad）。本模块不开 supply session（系统字体非游戏资产；
游戏字体字节经 recipes.text 域项（fontdefs→font_ttf_bytes）读取，本模块只在
回退映射里读 fontdefs 元数据）。
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from fontTools.ttLib import TTFont

from eidolon.core.infra import context   # 契约 D：glyph 缓存根=ctx.cache_root 显式流入
from eidolon.core.render.text import ft_unhinted as _ft  # consumer-v2 新包
from eidolon.core.render._provenance import fitted  # noqa: F401 （族默认）

logger = logging.getLogger(__name__)

__all__ = [
    "FALLBACK_FAMILIES",
    "character_padding",
    "drain_missing",
    "fallback_object_names",
    "font_asset_params",
    "font_dirs",
    "font_report",
    "family_index",
    "install_font_dirs",
    "materialize_ttf",
    "record_missing",
    "register_font",
    "register_font_bytes",
    "resolve_fallback",
]

# 引擎内置族名表（UnityPlayer 11 项有序 vector；**顺序=引擎构造序，勿改序**）。
# 证据=engine-font-fingerprint findings §4（惰性构造访问器 0xD95D50 按指令地址递增
# append），顺序证据=同实验 evidence/fallback/fallback_order.json。
FALLBACK_FAMILIES: tuple[str, ...] = (
    "Arial",
    "Arial Unicode MS",
    "Helvetica Neue",
    "Microsoft Sans Serif",
    "Microsoft YaHei",
    "Malgun Gothic",
    "Gulim",
    "MS Gothic",
    "Nirmala UI",
    "Segoe UI Emoji",
    "LastResort",
)
_BOLD_SUFFIX = " Bold"          # 引擎：族名未命中还拼 " Bold" 重试（findings §4）
_REPLACEMENT = "\ufffd"          # U+FFFD：两级全失败的引擎末级兜底

# ---------------------------------------------------------------------------
# 1) 资产参数（pad / 回退名单）——运行时 supply 提取，进程级 memo
# ---------------------------------------------------------------------------

_ASSET_PARAMS: dict | None = None


@fitted(kind="artifact")
def font_asset_params() -> dict:
    """Font 对象参数全表（运行时 supply 提取；进程级 memo）。

    结构：`{"fonts": {<fontObjectName>: {"m_CharacterPadding": int,
    "m_FontRenderingMode": int, "fallback_object_names": [str, ...]}}, ...}`。
    来源=`recipes.text.font_asset_params`（游戏 assets 的 Unity Font 对象直读）；
    `data/fonts_zhcn/font_asset_params.json` 仅作对拍 oracle（生产零读）。
    提取失败=响亮异常（供给口径没有退路：pad 写死=错位，回退名单缺=静默 tofu）。"""
    global _ASSET_PARAMS
    if _ASSET_PARAMS is None:
        from eidolon.core.recipes.text import font_asset_params as _supply
        _ASSET_PARAMS = _supply()
    return _ASSET_PARAMS


def _font_record(font_object: str) -> dict:
    rec = (font_asset_params().get("fonts") or {}).get(str(font_object))
    if rec is None:
        raise KeyError(
            f"字体资产参数无 {font_object!r} 条目"
            f"（开放位={sorted((font_asset_params().get('fonts') or {}))}）——"
            "格框留白 m_CharacterPadding 禁写死，未知字体响亮停")
    return rec


@fitted(kind="artifact")
def character_padding(font_object: str) -> int:
    """该 Font 对象的图集格框留白 `m_CharacterPadding`（GLEI=4、BGO=2）。"""
    rec = _font_record(font_object)
    if rec.get("m_CharacterPadding") is None:
        raise KeyError(f"字体资产参数 {font_object!r} 无 m_CharacterPadding 字段")
    return int(rec["m_CharacterPadding"])


@fitted(kind="artifact")
def fallback_object_names(font_object: str | None) -> tuple[str, ...]:
    """该 Font 对象自带的回退字体对象名（资产 `m_FallbackFonts`；无对象名=空表）。"""
    if not font_object:
        return ()
    rec = _font_record(font_object)
    return tuple(str(x) for x in (rec.get("fallback_object_names") or ()))


# ---------------------------------------------------------------------------
# 2) 字体目录注入 + 字体字节 → 内容寻址缓存文件（驱动只吃路径；落盘在树外，
#    保 input_fingerprint）
# ---------------------------------------------------------------------------

_FONT_DIRS: tuple[Path, ...] = ()    # install_font_dirs 注入（模块级；空=font_dirs 兜底）
_FACE_DIR: Path | None = None        # materialize_ttf 缓存根（显式给出或 ctx 缺省）
_FACE_PATH_BY_SHA: dict[str, Path] = {}
_SHA_BY_ID: dict[int, tuple[bytes, str]] = {}   # id(bytes) → (bytes 强引用, sha256)


def install_font_dirs(dirs: tuple[Path, ...], *, cache_dir: Path | None = None) -> None:
    """注入 OS 字体目录与字形缓存根（产品组合层在 preflight / worker initializer、
    首次 `family_index()` 之前调用；测试注入同口）。

    - `dirs`：字体搜索目录（渲染路径=OS 字体目录；空元组=`font_dirs()` 落产品
      兜底 `C:/Windows/Fonts`）。
    - `cache_dir`：`materialize_ttf` 的内容寻址缓存根；None=经
      `GameContext.cache_root / "fonts"`（首次落盘时按已装 ctx 解析；未安装=
      current() raise——库面不自行兜底路径）。这是 **core 唯一在 out_dir 之外的
      写盘**（渲染输出与 route.db 之外；docstring 第 3 件事的账）。
    - **重置** `_FAMILY_INDEX` / `_NAME_CACHE` / `_FACE_DIR`：同进程换目录/测试
      注入后索引不陈旧（族索引在下次 `family_index()` 按新目录重建）。"""
    global _FONT_DIRS, _FACE_DIR, _FAMILY_INDEX, _NAME_CACHE
    _FONT_DIRS = tuple(Path(d) for d in dirs)
    _FAMILY_INDEX = None
    _NAME_CACHE = {}
    _FACE_DIR = Path(cache_dir) if cache_dir is not None else None


def _face_cache_dir() -> Path:
    global _FACE_DIR
    if _FACE_DIR is None:
        # 契约 D：缓存根=GameContext 显式流入（render 路径已 install）；
        # 不落系统 temp（上游的 temp 字体缓存随 env 面删除）。
        _FACE_DIR = context.current().cache_root / "fonts"
    _FACE_DIR.mkdir(parents=True, exist_ok=True)
    return _FACE_DIR


def _sha256_bytes(data: bytes) -> str:
    """字节 sha256（同一 bytes 对象重复问只算一次：持强引用防 id 复用）。"""
    ent = _SHA_BY_ID.get(id(data))
    if ent is not None and ent[0] is data:
        return ent[1]
    sha = hashlib.sha256(data).hexdigest()
    _SHA_BY_ID[id(data)] = (data, sha)
    return sha


@fitted(kind="artifact")
def materialize_ttf(data: bytes, label: str = "") -> Path:
    """字体字节 → 进程级内容寻址文件（`<sha256>.ttf`，跨进程复用）。

    驱动 `ft_unhinted.get_face(path, ppem)` 只吃路径；游戏字体是真内存字节。文件名=
    内容 sha ⇒ 同内容天然同文件、无版本歧义；写用 pid 唯一临时名 + `os.replace`（并发
    worker 同内容写同一目标，replace 失败也无害：目标已是同内容）。"""
    data = bytes(data)
    sha = _sha256_bytes(data)
    hit = _FACE_PATH_BY_SHA.get(sha)
    if hit is not None and hit.is_file() and hit.stat().st_size == len(data):
        return hit
    p = _face_cache_dir() / f"{sha}.ttf"
    if not (p.is_file() and p.stat().st_size == len(data)):
        tmp = p.with_name(f"{sha}.{os.getpid()}.tmp")
        tmp.write_bytes(data)
        try:
            os.replace(tmp, p)
        except OSError:
            # 并发 worker 已落同内容，或目标被 FT 打开（Windows 同名替换拒写）——
            # 内容寻址下两者等价，只要目标已在且同长即可复用。
            if not (p.is_file() and p.stat().st_size == len(data)):
                raise
        finally:
            if tmp.exists():
                tmp.unlink()
    _FACE_PATH_BY_SHA[sha] = p
    return p


# ---------------------------------------------------------------------------
# 3) OS 字体解析（目录枚举 + fontTools name 表精确匹配 family）
# ---------------------------------------------------------------------------

_FONT_FILE_SUFFIXES = frozenset({".ttf", ".ttc", ".otf"})
_TTC_FACE_INDEX = 0        # 驱动的 face index 固定 0（findings §4：引擎不可判别，默认 0）


@fitted(kind="artifact")
def font_dirs() -> tuple[Path, ...]:
    """OS 字体目录（`install_font_dirs` 注入；未注入=产品兜底）。

    兜底 `(Path("C:/Windows/Fonts"),)` 是**产品政策写死的常量**（引擎实证的目录
    枚举形态），不是环境变量读取。"""
    return _FONT_DIRS or (Path("C:/Windows/Fonts"),)


def _pick_name(names, name_id: int) -> str | None:
    """name 表取一条文本：Windows(3,1) 优先 → Mac(1,0) → Unicode(0,*) → Windows 其它；
    同级内英文(0x409)优先、再按 language id 升序。

    字段名按 fontTools 4.x `NameRecord`（`nameID`/`platformID`/`platEncID`/`langID`）；
    旧别名（name_id 等）经 getattr 兜底，避免版本漂移。"""
    def _f(rec, *keys):
        for k in keys:
            v = getattr(rec, k, None)
            if v is not None:
                return int(v)
        return -1

    cands = [r for r in names if _f(r, "nameID", "name_id") == int(name_id)]
    if not cands:
        return None

    def rank(r):
        pid = _f(r, "platformID", "platform_id")
        eid = _f(r, "platEncID", "encodingID", "encoding_id")
        tier = 0 if (pid, eid) == (3, 1) else \
            1 if (pid, eid) == (1, 0) else \
            2 if pid == 0 else 3
        return (tier, _f(r, "langID", "language_id") != 0x409,
                _f(r, "langID", "language_id"))

    best = min(cands, key=rank)
    try:
        text = best.toUnicode()
    except Exception:      # 坏 name 记录（坏编码/截断）= 跳过该条，不猜
        return None
    text = (text or "").strip()
    return text or None


def _face_names(path: Path) -> dict | None:
    """一个字体文件的 face 0 名字面：{aliases, family, full_name, subfamily, version}。

    解析失败（坏字体/非 sfnt/权限）→ None（调用方跳过该文件，不猜）。"""
    try:
        tt = TTFont(str(path), fontNumber=_TTC_FACE_INDEX, lazy=True)
        names = tt["name"].names
        family1 = _pick_name(names, 1)
        family16 = _pick_name(names, 16)
        full4 = _pick_name(names, 4)
        sub2 = _pick_name(names, 2)
        ver5 = _pick_name(names, 5)
        family = family16 or family1 or full4
        if not family:
            return None
        aliases = {a for a in (family1, family16, full4) if a}
        if family1 and sub2:
            # 引擎 " Bold" 重试要按「族名 + 子族」也解析得到（name 表的族名只有
            # regular 一行；bold 面是同一 family 的另一个子族）
            aliases.add(f"{family1} {sub2}")
        ver = " — ".join(x for x in (full4 or family, ver5) if x)
        return {"aliases": aliases, "family": family,
                "full_name": full4, "subfamily": sub2, "version": ver}
    except Exception:
        return None


_NAME_CACHE: dict[str, dict | None] = {}
_FAMILY_INDEX: dict[str, list[str]] | None = None


def _index_one_font(p: Path) -> None:
    key = str(p)
    rec = _NAME_CACHE.get(key, "miss")
    if rec == "miss":
        rec = _face_names(p)
        _NAME_CACHE[key] = rec
        if rec is None:
            # B4 响亮化（跳过语义不变，docstring 同账）：后缀在字体域的文件解析
            # 失败（坏字体/非 sfnt/权限）=回退候选静默少一个——WARNING 一声
            # （进程一次；_NAME_CACHE memo 后不再重复）。缺字最终仍走两级
            # 回退账的响亮事件，此处只补「候选为什么少了」的来路。
            logger.warning(
                "family_index: 字体文件无法解析（坏字体/非 sfnt/权限），"
                "回退候选跳过: %s", p)
    if not rec:
        return
    for alias in rec["aliases"]:
        lst = _FAMILY_INDEX.setdefault(alias.casefold(), [])
        if key not in lst:
            lst.append(key)


@fitted(kind="artifact")
def family_index() -> dict[str, list[str]]:
    """族名 → 字体文件清单（进程级 memo；首次调用枚举两个 OS 字体目录）。

    只登记 face 0 的族名（驱动固定 face 0，见 `_TTC_FACE_INDEX`）；文件名排序保证
    同族多文件时**常规体优先**（如 `Microsoft YaHei` 的 regular 排在 bold/light 之前），
    与 oracle（regular 面）一致。"""
    global _FAMILY_INDEX
    if _FAMILY_INDEX is None:
        idx: dict[str, list[str]] = {}
        _FAMILY_INDEX = idx
        for d in font_dirs():
            if not d.is_dir():
                continue
            try:
                entries = sorted(d.iterdir(), key=lambda q: q.name.casefold())
            except OSError as exc:
                # B4 明确回退（不炸整卡）：单目录枚举失败（权限拒绝等）=该目录
                # 候选缺席，其余目录/游戏字体仍在；缺字最终仍有两级回退响亮账。
                # 原 OSError 会穿到逐卡分类落 render_failed（RENDER 1）——
                # 回退源降级不该按渲染实现失败计。
                logger.warning(
                    "family_index: 字体目录不可枚举，跳过该目录"
                    "（回退质量降级；缺字仍有响亮事件）: %s (%s: %s)",
                    d, type(exc).__name__, exc)
                continue
            for p in entries:
                if p.suffix.casefold() in _FONT_FILE_SUFFIXES and p.is_file():
                    _index_one_font(p)
    return _FAMILY_INDEX


def _family_files(family: str) -> list[str]:
    return list(family_index().get(str(family).casefold()) or ())


# ---------------------------------------------------------------------------
# 4) 两级回退解析
# ---------------------------------------------------------------------------

_OBJECT_BYTES: dict[str, bytes] | None = None


def _object_font_bytes() -> dict[str, bytes]:
    """Font 对象名 → TTF 字节（recipes.text 域项链：fontdefs 侧 → font_ttf_bytes）。

    zhCN 侧优先（离线冻结 locale）：同一 FontDef 的 zhCN/enus 侧是不同 Font 对象
    （如 Belwe↔GLEI00M_t），而 zhCN 渲染只消费 zhCN 侧对象名；`m_FallbackFonts`
    名单里的对象名全部落在本表键内。取字节失败的单侧跳过（不猜）。
    （font_service 薄壳未进本 Phase——其 `fontdefs`/`load_font_data` 是 recipes.text
    域项的纯直通，按 §8 消费方直取域项等价。）

    资产链不可用（不在 supply session / 无游戏安装）→ 返回空表且**不缓存**：
    第一级缺席时下沉第二级是正常路径，但空表一旦永久缓存，后续会话内调用就会
    静默丢失第一级（2026-10-22 实测：实验脚本先直调建成空表 → 会话内样本降级）。"""
    global _OBJECT_BYTES
    if _OBJECT_BYTES is not None:
        return _OBJECT_BYTES
    from eidolon.core.recipes import text as _recipes_text
    try:
        defs = _recipes_text.fontdefs()
    except Exception:
        return {}
    out: dict[str, bytes] = {}
    for def_name, rec in defs.items():
        for side_key in ("zhcn", "enus"):
            side = rec.get(side_key) or {}
            fo = side.get("font_object") or {}
            name = fo.get("m_FontName")
            if not name or name in out:
                continue
            try:
                out[name] = _recipes_text.font_ttf_bytes(def_name)
            except Exception:
                continue
    if out:
        _OBJECT_BYTES = out
    return out


def _game_face(object_name: str, ppem: int):
    """游戏 Font 对象名 → UnhintedFace（字节经 fontdefs 链 + 内容寻址落盘）。"""
    data = _object_font_bytes().get(str(object_name))
    if not data:
        return None, None
    register_font_bytes(f"game:{object_name}", data)
    path = materialize_ttf(data)
    try:
        return _ft.get_face(path, int(ppem)), data
    except Exception:
        return None, data


_FALLBACK_MEMO: dict[tuple, tuple] = {}
_MISSING: dict[tuple, dict] = {}     # (font,size,cp) -> 事件（count 累计，drain 清空）
_FONTS: dict[str, dict] = {}         # label -> {sha256, source, path, bytes, ...}（进程累计）


def _os_face(path: str, ppem: int):
    """OS 字体文件 → UnhintedFace（驱动 face 0）。

    栅格化失败（fontTools 能过 name 表、FT 打不开/坏面）→ None 跳过该候选
    （DEBUG 记账；索引期 WARNING 已响亮过一次，此处不重复）。"""
    try:
        return _ft.get_face(path, int(ppem))
    except Exception as exc:
        logger.debug("_os_face: 回退字体栅格化失败，跳过候选: %s@%d (%s: %s)",
                     path, ppem, type(exc).__name__, exc)
        return None


def _hit_event(ch: str, ppem: int, face, *, level: str, source: str,
               file: str, resolved_ch: str | None = None,
               bold_retry: bool = False, extra: dict | None = None) -> dict:
    """一次回退命中/失败的完整账（族名→文件→sha/版本/face + advance）。"""
    rch = resolved_ch if resolved_ch is not None else ch
    adv = 0
    if face is not None and face.has_glyph(rch):
        adv = _ft.advance_to_px(face.advance_26_6(rch))
    ev = {"level": level, "source": source, "file": file,
          "family": getattr(face, "family", "") if face is not None else "",
          "sha256": getattr(face, "sha256", "") if face is not None else "",
          "ttc_face": _TTC_FACE_INDEX, "advance_px": int(adv),
          "resolved_ch": rch if face is not None else None,
          "bold_retry": bool(bold_retry)}
    if extra:
        ev.update(extra)
    return ev


def _search(ch: str, ppem: int, font_object: str | None):
    """两级查找一次（ch 原字）：返回 (face|None, event|None)。"""
    # ① Font 自带名单（资产 m_FallbackFonts）
    for obj in fallback_object_names(font_object):
        face, _data = _game_face(obj, ppem)
        if face is None:
            continue
        if face.has_glyph(ch):
            rec = _NAME_CACHE.get(f"game:{obj}") or {}
            return face, _hit_event(
                ch, ppem, face, level="asset", source=f"game:{obj}@{ppem}",
                file=f"game:{obj}", extra={"version": rec.get("version")
                                           or f"{obj} (game asset)"})
    # ② 内置 11 项有序族名表
    for family in FALLBACK_FAMILIES:
        for fam_try, bold in ((family, False), (family + _BOLD_SUFFIX, True)):
            for path in _family_files(fam_try):
                face = _os_face(path, ppem)
                if face is None or not face.has_glyph(ch):
                    continue
                rec = _NAME_CACHE.get(path) or {}
                register_font(f"fallback:{fam_try}", face.sha256, "system", path,
                              Path(path).stat().st_size,
                              family=rec.get("family"), version=rec.get("version"),
                              ttc_face=_TTC_FACE_INDEX)
                return face, _hit_event(
                    ch, ppem, face, level="os", source=f"{fam_try}@{ppem}",
                    file=path, bold_retry=bold,
                    extra={"version": rec.get("version") or ""})
    return None, None


@fitted(kind="artifact")
def resolve_fallback(ch: str, ppem: int, font_object: str | None = None):
    """缺字回退解析（引擎两级查找）→ `(face | None, event)`。

    `ch` 为该 face 缺的字；`font_object` = 当前 Font 对象名（第一级名单键；
    None/空=跳过第一级直接下沉族名表）。`(font_object, ch, ppem)` 结果进程内 memo。

    event 恒含：`level / source / file / family / sha256 / ttc_face / advance_px /
    resolved_ch / bold_retry`（+ `version`）。全失败时 `face=None`、`advance_px=0`、
    `resolved_ch=None`——调用方据此出零宽/零掩码位并记响亮事件（不静默 tofu）。"""
    key = (str(font_object or ""), str(ch), int(ppem))
    hit = _FALLBACK_MEMO.get(key)
    if hit is not None:
        return hit[0], dict(hit[1])
    face, ev = _search(ch, ppem, font_object)
    if face is None:
        # 末级：U+FFFD（引擎全失败时的替换字；同一两级表里找）
        face_r, ev_r = _search(_REPLACEMENT, ppem, font_object)
        if face_r is not None:
            face, ev = face_r, dict(ev_r, resolved_ch=_REPLACEMENT,
                                    replacement=True)
    if face is None:
        ev = {"level": "none", "source": f"none@{ppem}", "file": "",
              "family": "", "sha256": "", "ttc_face": _TTC_FACE_INDEX,
              "advance_px": 0, "resolved_ch": None, "bold_retry": False,
              "version": ""}
    _FALLBACK_MEMO[key] = (face, dict(ev))
    return face, dict(ev)


# ---------------------------------------------------------------------------
# 5) 响亮账：缺字事件 + 字体哈希（drain 位=components.render_with → gate_report）
# ---------------------------------------------------------------------------

@fitted(kind="artifact")
def register_font(label: str, sha256: str, source: str,
                  path: str | None = None, nbytes: int | None = None,
                  **extra) -> None:
    """字体文件入账（`font_report` 出口；extra = family/version/ttc_face 等扩展字段）。"""
    rec = {"sha256": sha256, "source": source, "path": path, "bytes": nbytes}
    rec.update({k: v for k, v in extra.items() if v is not None})
    _FONTS[label] = rec


@fitted(kind="artifact")
def register_font_bytes(label: str, data: bytes, source: str = "game") -> None:
    """游戏 TTF（fontdef._ttf 真内存）哈希入账（drain 位同上）。"""
    if label in _FONTS:
        return
    register_font(label, hashlib.sha256(data).hexdigest(), source, None, len(data))


@fitted(kind="artifact")
def record_missing(font: str, size: int, ch: str, reason: str, source: str,
                   **extra) -> dict:
    """缺字/回退事件（同键累计 count；drain_missing 后入 gate_report）。

    `extra` = 回退事件字段（family/file/sha256/ttc_face/version/advance_px/...）——
    现役键（font/size/ch/cp/reason/source/count）一个不动，只做加法。"""
    key = (str(font), int(size), str(ch))
    ev = _MISSING.get(key)
    if ev is None:
        ev = {"font": key[0], "size": key[1], "ch": key[2], "cp": ord(ch),
              "reason": reason, "source": source, "count": 0}
        _MISSING[key] = ev
    ev["count"] += 1
    ev["reason"] = reason
    ev["source"] = source
    ev.update({k: v for k, v in extra.items() if k != "count"})
    return ev


@fitted(kind="artifact")
def drain_missing() -> list[dict]:
    """取走并清空本轮（逐卡）缺字事件（render_with 每渲一调）。"""
    out = sorted(_MISSING.values(), key=lambda e: (e["font"], e["size"], e["ch"]))
    _MISSING.clear()
    return out


@fitted(kind="artifact")
def font_report() -> dict:
    """渲染所用字体文件哈希账（进程累计快照；判据 4 漂移追溯位）。

    键=标签（`game:<Font对象名>` / `fallback:<族名>`），值含现役键
    `sha256/source/path/bytes` + 回退字体扩展键 `family/version/ttc_face`。"""
    return {k: dict(v) for k, v in sorted(_FONTS.items())}
