"""text — 文本域：字体链真内存提取（resources.assets FontTable→FontDefinition→Font）。

对照表（旧位 → 本域）：
  - font_table/fontdefs ← data/fonts_zhcn/fontdefs.json（tp1_extract_fonts.py 253 行
    提取链转写，逐字口径：FontTableData typetree 被引擎剥离→**裸字节 struct 解析**
    （m_Script PPtr 6813 锚）；enUS=base guid 原样、zhCN=locale_catalog 变体；
    FontDefinition 8 字段保留、Font.m_FontData 字节面）；既档 json=对拍 oracle
    （逐字段），随收编退役为参照。
  - font_ttf_bytes ← 游戏本体 Font.m_FontData 真内存（批10d：font_ttf 物化死槽+
    第二缓存根退役；原 data/fonts_zhcn/*.ttf 档案降对拍 oracle）。
  - font_asset_params ← Unity Font 对象参数（m_CharacterPadding/m_FontRenderingMode/
    m_FallbackFonts PPtr 名）从游戏 assets 直提；原 data/fonts_zhcn/font_asset_params.json
    降对拍 oracle（渲染路径 data 读=0 收口，2026-10-21 render-data-decouple）。
  - atlas 快照（fonts_zhcn/atlas/）=引擎注入快照（合法 data/ 参照资产，README 源锚
    alphatool -dumpfonts）——快照消费与 AtlasFontMetrics 晋升**随 frames 批**
    （其基类/消费方=uber_text，v3 text 收它=层方向违例，2026-10-10 修正前记）。
层注记：ta_npz/btf 随 frames 顺批（kit 依赖）。
"""
from __future__ import annotations

import logging
import os
import struct
from pathlib import Path
from typing import Any

from eidolon.core.infra.context import current   # 契约 D：游戏路径=ctx 流入
from eidolon.core.infra.errors import GameAssetMissing
from eidolon.core.supply.machine import core, item

logger = logging.getLogger(__name__)

_RESOURCES_LOAD_PATH = "ServiceData/FontTableData"   # FontLoader.cs:FontLoader.LoadFontTableData（游戏 Resources.Load 路径）


def _font_asset_sources() -> tuple[tuple[str, Path], ...]:
    """Font 对象所在三处资产（=engine-font-fingerprint 资产线清点面；其余
    语言/预包无 Font 对象）。resources.assets 直接 UnityPy.load；两 content 包走
    Resolver（fontdefs 同链已开的 bundle 复用，避免重复整包解析）。
    契约 D：父目录从 GameContext 流入（ctx.resources / ctx.data_win）；bundle 名
    essential_base_zhcn-content-0 是**游戏 bundle 命名事实**（zhcn 内容包），非路径默认。
    """
    ctx = current()
    return (
        ("resources.assets", ctx.resources),
        ("global-content-0", ctx.data_win / "essential_base_global-content-0.unity3d"),
        ("zhcn-content-0", ctx.data_win / "essential_base_zhcn-content-0.unity3d"),
    )
_FONTDEF_FIELDS = ("m_Name", "m_LineSpaceModifier", "m_SingleLineAdjustment",
                   "m_FontSizeModifier", "m_CharacterSizeModifier", "m_OutlineModifier",
                   "m_UnboundCharacterSizeModifier", "m_Font")


@item("text", "font_table")
def font_table() -> list[dict]:
    """FontTableData.m_Entries 全表（引擎寻址复刻 + payload 裸字节解析）。

    根=游戏自己的路径寻址（FontLoader.cs:FontLoader.LoadFontTableData Resources.Load）：globalgamemanagers
    ResourceManager.m_Container 按路径索引 → PPtr → resources.assets 对象。
    payload 的 typetree 被引擎剥离（引擎走原生脚本运行时，不需要）→ 裸字节 struct
    解析（GO PPtr(12)+enabled+align(4)+script PPtr(12)+cstring+align+count+entries
    {FontDefName,FontName,FontGuid}）。[tp1_extract_fonts.read_font_table 转写；
    根升级 2026-10-10：字节签名扫描（m_Script PPtr 6813，跨构建重排脆弱）→
    ResourceManager 路径索引=游戏自身词汇]

    typed 边界（设计 §5.3）：ResourceManager 索引无 FontTableData 路径项 →
    ``GameAssetMissing``（落点文件形态漂移仍 assert）。"""
    import UnityPy

    ctx = current()
    gge = UnityPy.load(str(ctx.globalgamemanagers))
    rm = next(o for o in gge.objects if o.type.name == "ResourceManager")
    cont = rm.read_typetree().get("m_Container") or []
    hit = next((v for k, v in cont if k.lower() == _RESOURCES_LOAD_PATH.lower()), None)
    if hit is None:
        raise GameAssetMissing(
            path=_RESOURCES_LOAD_PATH,
            message=f"asset_missing_in_game: ResourceManager 索引无 "
                    f"{_RESOURCES_LOAD_PATH} 路径项")
    sf = next(iter(gge.files.values()))
    ext = list(getattr(sf, "externals", []))
    ext_name = Path(ext[hit["m_FileID"] - 1].path).name.lower()
    assert "resources.assets" in ext_name, \
        f"FontTableData 落在外部文件 {ext_name!r}（预期 resources.assets）"

    env = UnityPy.load(str(ctx.resources))
    obj = next(o for o in env.objects if o.path_id == hit["m_PathID"])
    raw = obj.get_raw_data()
    off = 16   # m_GameObject PPtr(12) + m_Enabled+align(4)
    off += 12   # m_Script PPtr（路径寻址已定位对象，此处仅越过）
    nlen = struct.unpack("<i", raw[off : off + 4])[0]
    off += 4
    name = raw[off : off + nlen].decode("utf-8", "replace")
    off = (off + nlen + 3) & ~3
    count = struct.unpack("<i", raw[off : off + 4])[0]
    off += 4

    def rstr(buf: bytes, p: int) -> tuple[str, int]:
        l = struct.unpack("<i", buf[p : p + 4])[0]
        p += 4
        s = buf[p : p + l].decode("utf-8", "replace")
        return s, (p + l + 3) & ~3

    entries = []
    for _ in range(count):
        fd, off = rstr(raw, off)
        fn, off = rstr(raw, off)
        fg, off = rstr(raw, off)
        entries.append({"m_FontDefName": fd, "m_FontName": fn, "m_FontGuid": fg})
    return entries


@item("text", "fontdefs")
def fontdefs() -> dict[str, dict]:
    """字体定义全表（enUS/zhCN 双侧真内存）——fontdefs.json 的内容面。

    [tp1_extract_fonts.main 逐字去落盘：enUS=base guid 原样解析；zhCN=locale_catalog
    变体 GUID（无变体记 note 用 base）；FontDefinition 8 字段保留；Font.m_Font 字节
    面只记元数据（字节面=font_ttf_bytes 域项真内存）]"""
    r = core().res
    zhcat = r.locale_catalog("zhcn")
    out: dict[str, dict] = {}
    for e in font_table():
        base_guid = e["m_FontGuid"].lower()
        name = e["m_FontDefName"]
        rec: dict[str, Any] = {"m_FontName": e["m_FontName"], "m_FontDefName": name,
                               "base_guid": base_guid}
        for locale in ("enus", "zhcn"):
            side: dict[str, Any] = {}
            if locale == "enus":
                guid, bundle = base_guid, r.catalog.get(base_guid)
            else:
                var = zhcat.get(base_guid)
                if var is None:
                    rec["zhcn"] = {"variant": None, "note": "无 zhCN 变体，用 base"}
                    continue
                guid, bundle = var
            side["guid"] = guid
            side["bundle"] = bundle
            env = r.open_bundle(bundle)
            obj, _key = r.container_get(bundle, guid)
            fd = _read_fontdef(env, {"m_FileID": 0, "m_PathID": obj.path_id}, obj)
            if fd is None:
                fd = obj.read_typetree()
            side["fontdef"] = {k: v for k, v in fd.items() if k in _FONTDEF_FIELDS}
            fo = _deref_font(env, fd.get("m_Font"), obj, bundle, r)
            if fo is not None:
                ftt = fo.read_typetree()
                data = ftt.get("m_FontData")
                side["font_object"] = {
                    "m_FontName": ftt.get("m_FontName") or ftt.get("m_Name") or "?",
                    "m_AssetNames": ftt.get("m_AssetNames"),
                    "m_FontRenderingMode": ftt.get("m_FontRenderingMode"),
                    "m_CharacterRects": (len(ftt.get("m_CharacterRects") or [])
                                         if isinstance(ftt.get("m_CharacterRects"), list) else None),
                    "bytes": len(data) if data else 0,
                    "path_id": fo.path_id,
                }
            rec[locale] = side
        out[name] = rec
    return out


@item("text", "font_ttf_bytes")
def font_ttf_bytes(name: str) -> bytes:
    """Font.m_FontData 字节真内存（游戏直提；批10d：font_ttf 物化死槽+第二缓存根退役——
    PIL/fontTools 均 BytesIO 兼容，双字体 md5 逐字节对账见 2026-10-13 调查报告）。"""
    return _font_data(name)


@item("text", "font_asset_params")
def font_asset_params() -> dict:
    """Unity Font 对象参数表（pad/渲染模式/资产回退链）——游戏 assets 直提。

    内容面 = 原 `data/fonts_zhcn/font_asset_params.json`（**降对拍 oracle**，生产不读）：
    `{"fonts": {<Font.m_Name>: {"m_CharacterPadding": int,
    "m_FontRenderingMode": int, "fallback_object_names": [str, ...]}}, ...}`。

    读取链（=engine-font-fingerprint 资产线 F 号取证，逐字同口径）：三处资产的 Unity
    Font 对象全量 → `m_CharacterPadding` / `m_FontRenderingMode` 直读；`m_FallbackFonts`
    PPtr 数组 → 解析目标 Font 的 `m_Name`（空 PathID 槽跳过=BelweNumbers 的序列化空槽）。
    同名字体跨包（Belwe/Belwe_Outline/BlizzardGlobal）按 pad/mode 一致性自检，回退名单
    按首见序并集（口径=extract_font_asset_params.py）。未知/解析失败一律响亮（不猜默认：
    pad 写死=错位、回退名单缺=静默 tofu）。"""
    import UnityPy

    font_sources = _font_asset_sources()
    fonts: dict[str, dict] = {}
    sources: dict[str, list[str]] = {}
    for label, path in font_sources:
        if label == "resources.assets":
            env = UnityPy.load(str(path))
        else:
            env = core().res.open_bundle(path.name)
        for obj in env.objects:
            if obj.type.name != "Font":
                continue
            t = obj.read_typetree()
            name = t.get("m_Name")
            assert name, f"{label}: Font 对象无 m_Name（path_id={obj.path_id}）"
            pad = t.get("m_CharacterPadding")
            mode = t.get("m_FontRenderingMode")
            fbs: list[str] = []
            for ptr in (t.get("m_FallbackFonts") or []):
                hit = _pptr_font_name(obj, env, ptr)
                if hit and hit not in fbs:
                    fbs.append(hit)
            rec = fonts.setdefault(name, {"m_CharacterPadding": pad,
                                          "m_FontRenderingMode": mode,
                                          "fallback_object_names": []})
            # 同名字体跨包一致性自检（≠ 即停：两包给不同 pad/mode = 资产形态变了）
            for field, val in (("m_CharacterPadding", pad), ("m_FontRenderingMode", mode)):
                if val is None:
                    continue
                if rec[field] is None:
                    rec[field] = val
                elif rec[field] != val:
                    raise AssertionError(
                        f"{name}: {field} 跨包不一致 {rec[field]} vs {val}（{label}）——"
                        "字体资产形态变化，须重核口径")
            for fb in fbs:
                if fb not in rec["fallback_object_names"]:
                    rec["fallback_object_names"].append(fb)
            if label not in sources.setdefault(name, []):
                sources[name].append(label)
    assert fonts, f"字体资产参数为空：{font_sources}——pad/回退名单口径无输入"
    for name, rec in fonts.items():
        assert rec["m_CharacterPadding"] is not None, (
            f"{name}: m_CharacterPadding 缺失——格框留白禁写死/禁默认值")
        assert rec["m_FontRenderingMode"] is not None, (
            f"{name}: m_FontRenderingMode 缺失——渲染模式口径无输入")
    return {
        "fonts": dict(sorted(fonts.items())),
        "sources": {k: sources[k] for k in sorted(sources)},
        "source": {
            "files": [{"label": label, "path": str(path)}
                      for label, path in font_sources],
            "fields": ["m_CharacterPadding", "m_FontRenderingMode", "m_FallbackFonts"],
            "oracle": "data/fonts_zhcn/font_asset_params.json（对拍参照，生产零读）",
            "mechanism": "engine-font-fingerprint 资产线（Font 对象全量 typetree）",
        },
    }


# ---- 内部（转写件）----

def _iter_serialized(env):
    """环境内全部 SerializedFile（bundle 可含多 CAB；_read_fontdef 同款走查）。"""
    from UnityPy.files import SerializedFile

    def walk(f):
        if isinstance(f, SerializedFile):
            yield f
            return
        subs = getattr(f, "files", None)
        if isinstance(subs, dict):
            for s in subs.values():
                yield from walk(s)

    for f in env.files.values():
        yield from walk(f)


def _pptr_font_name(owner, env, pptr: dict) -> str | None:
    """Font PPtr → 目标 Font 的 m_Name（空槽=0 返回 None；解析不到=响亮，不静默丢名单）。

    fid=0 同 CAB 直查（本资产全部 m_FallbackFonts 实测如此）；fid>0 经 owner CAB 的
    externals 名在同环境 SerializedFile 里查（跨 CAB 形态兜底；跨包依赖不猜——missing
    即 AssertionError，待资产形态重核）。"""
    fid = int(pptr.get("m_FileID") or 0)
    pid = int(pptr.get("m_PathID") or 0)
    if not pid:
        return None
    if fid == 0:
        o = owner.assets_file.objects.get(pid)
    else:
        exts = list(getattr(owner.assets_file, "externals", []) or [])
        assert 1 <= fid <= len(exts), (
            f"m_FallbackFonts PPtr externals[{fid - 1}] 不存在"
            f"（owner={owner.assets_file.name!r}, path_id={pid}）")
        cab = Path(exts[fid - 1].path).name.lower()
        o = None
        for sf in _iter_serialized(env):
            if Path(str(getattr(sf, "name", ""))).name.lower() == cab and pid in sf.objects:
                o = sf.objects[pid]
                break
    assert o is not None, (
        f"m_FallbackFonts PPtr 未解析（owner={owner.assets_file.name!r}, "
        f"file_id={fid}, path_id={pid}）——回退名单不得静默丢弃")
    t = o.read_typetree()
    return t.get("m_Name") or t.get("m_FontName")


def _font_data(name: str) -> bytes:
    """FontDef 名 → zhCN 侧 Font.m_FontData 字节（无 zhCN 变体时跟随 base——tp1 语义）。

    typed 边界（设计 §5.3）：无该 fontdef / Font 对象未命中 / m_FontData 空 →
    ``GameAssetMissing``（无字体三型）。"""
    r = core().res
    zhcat = r.locale_catalog("zhcn")
    rec = fontdefs().get(name)
    if rec is None:
        raise GameAssetMissing(
            path=name,
            message=f"asset_missing_in_game: 字体定义表无 fontdef {name!r}")
    base_guid = rec["base_guid"]
    guid, bundle = (zhcat.get(base_guid) or (rec["enus"]["guid"], rec["enus"]["bundle"]))
    env = r.open_bundle(bundle)
    obj, _key = r.container_get(bundle, guid)
    fd = _read_fontdef(env, {"m_FileID": 0, "m_PathID": obj.path_id}, obj) or obj.read_typetree()
    fo = _deref_font(env, fd.get("m_Font"), obj, bundle, r)
    if fo is None:
        raise GameAssetMissing(
            path=name,
            message=f"asset_missing_in_game: {name}: Font 对象未命中")
    data = fo.read_typetree().get("m_FontData")
    if not data:
        raise GameAssetMissing(
            path=name,
            message=f"asset_missing_in_game: {name}: Font.m_FontData 空")
    return bytes(data)


def _read_fontdef(env, pptr: dict, owner_obj) -> dict | None:
    """FontDefinition typetree 全字段。[tp1.read_fontdef 逐字：同包直解/跨 CAB externals]"""
    fid, pid = pptr.get("m_FileID", 0), pptr.get("m_PathID", 0)
    if not pid:
        return None
    if fid == 0:
        o = owner_obj.assets_file.objects.get(pid)
    else:
        from UnityPy.files import SerializedFile

        def walk(f):
            if isinstance(f, SerializedFile):
                yield f
                return
            subs = getattr(f, "files", None)
            if isinstance(subs, dict):
                for s in subs.values():
                    yield from walk(s)

        ext = list(getattr(owner_obj.assets_file, "externals", []))
        cab = Path(ext[fid - 1].path).name.lower()
        o = None
        for f in walk(list(env.files.values())[0]):
            if Path(str(getattr(f, "name", ""))).name.lower() == cab and pid in f.objects:
                o = f.objects[pid]
                break
    if o is None or o.type.name != "MonoBehaviour":
        return None
    return o.read_typetree()


def _deref_font(env, pptr: dict | None, owner_obj, bundle: str, r) -> Any | None:
    """FontDefinition.m_Font（跨 CAB/跨包 PPtr）→ Font ObjectReader。
    [tp1.deref_font 逐字：同包→同 bundle 各 CAB→bundle_deps（resolve_pptr）]"""
    if not pptr:
        return None
    fid, pid = pptr.get("m_FileID", 0), pptr.get("m_PathID", 0)
    if not pid:
        return None
    if fid == 0:
        return owner_obj.assets_file.objects.get(pid)
    from UnityPy.files import SerializedFile

    def walk(f):
        if isinstance(f, SerializedFile):
            yield f
            return
        subs = getattr(f, "files", None)
        if isinstance(subs, dict):
            for s in subs.values():
                yield from walk(s)

    ext = list(getattr(owner_obj.assets_file, "externals", []))
    cab = Path(ext[fid - 1].path).name.lower()
    for f in walk(list(env.files.values())[0]):
        if Path(str(getattr(f, "name", ""))).name.lower() == cab and pid in f.objects:
            return f.objects[pid]
    try:
        o, _ = r.resolve_pptr(bundle, pptr, owner_obj)
        return o
    except Exception as ex:  # noqa: BLE001
        logger.warning(f"[text] deref_font miss cab={cab} pid={pid}: {ex}")
        return None
