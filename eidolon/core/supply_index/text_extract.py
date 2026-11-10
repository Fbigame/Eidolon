"""text_extract — cold 侧 text 域提取（font_table/fontdefs/TTF；UnityPy 面）。

逐配方转写（参照只读，禁 import eidolon.core.supply / eidolon.core.render）：
- font_table：globalgamemanagers ResourceManager.m_Container 路径索引
  （FontLoader.cs:FontLoader.LoadFontTableData Resources.Load 路径）→ resources.assets
  FontTableData 对象 → **裸字节 struct 解析**（typetree 被引擎剥离；GO PPtr(12)+
  enabled+align(4)+script PPtr(12)+cstring+align+count+entries{FontDefName,FontName,
  FontGuid}）。[eidolon/core/supply/text.py:font_table 逐字 ← tp1_extract_fonts.
  read_font_table；根升级 2026-10-10=ResourceManager 路径索引（游戏自身词汇）]
- fontdefs：enUS=base guid 原样；zhCN=locale 变体（variant_rows 面，无变体记 note
  用 base）；FontDefinition 8 字段；Font 对象元数据。[text.py:fontdefs 逐字
  ← tp1_extract_fonts.main]
- TTF：locale 生效侧 Font.m_FontData 字节（zhcn 变体缺位跟 base——tp1 语义）。
  [text.py:_font_data]

PPtr 解析=_KitResolver（kit_extract 同款：externals CAB 定位+bundle_deps 闭包，
container 全原始 pairs）；bundle 开启经 resolver 缓存（一 bundle 一开）。
"""
from __future__ import annotations

import logging
import struct
from pathlib import Path

logger = logging.getLogger(__name__)

from eidolon.core.supply_index.kit_extract import _KitResolver
from eidolon.core.supply_index._unity import (
    container_pairs,
    iter_serialized,
    load_bundle,
)
from eidolon.core.supply_index import text_codec as TC

_RESOURCES_LOAD_PATH = "ServiceData/FontTableData"   # FontLoader.cs:FontLoader.LoadFontTableData


def read_font_table(gge_path: Path, resources_path: Path) -> list[dict]:
    """FontTableData.m_Entries 全表（引擎寻址复刻+payload 裸字节解析）。"""
    import UnityPy

    gge = UnityPy.load(str(gge_path))
    rm = next(o for o in gge.objects if o.type.name == "ResourceManager")
    cont = rm.read_typetree().get("m_Container") or []
    hit = next((v for k, v in cont if k.lower() == _RESOURCES_LOAD_PATH.lower()), None)
    if hit is None:
        raise KeyError(f"ResourceManager 索引无 {_RESOURCES_LOAD_PATH} 路径项")
    sf = next(iter(gge.files.values()))
    ext = list(getattr(sf, "externals", []))
    ext_name = Path(ext[hit["m_FileID"] - 1].path).name.lower()
    if "resources.assets" not in ext_name:
        raise AssertionError(
            f"FontTableData 落在外部文件 {ext_name!r}（预期 resources.assets）")

    env = UnityPy.load(str(resources_path))
    obj = next(o for o in env.objects if o.path_id == hit["m_PathID"])
    raw = obj.get_raw_data()
    off = 16   # m_GameObject PPtr(12) + m_Enabled+align(4)
    off += 12   # m_Script PPtr（路径寻址已定位对象，此处仅越过）
    nlen = struct.unpack("<i", raw[off:off + 4])[0]
    off += 4
    off = (off + nlen + 3) & ~3   # 表名 cstring（内容不入账——路径即身份）
    count = struct.unpack("<i", raw[off:off + 4])[0]
    off += 4

    def rstr(buf: bytes, p: int) -> tuple[str, int]:
        l = struct.unpack("<i", buf[p:p + 4])[0]
        p += 4
        s = buf[p:p + l].decode("utf-8", "replace")
        return s, (p + l + 3) & ~3

    entries = []
    for _ in range(count):
        fd, off = rstr(raw, off)
        fn, off = rstr(raw, off)
        fg, off = rstr(raw, off)
        entries.append({"m_FontDefName": fd, "m_FontName": fn, "m_FontGuid": fg})
    return entries


def _read_fontdef_env(env, pptr: dict, owner_obj) -> dict | None:
    """FontDefinition typetree 全字段。[text.py:_read_fontdef 逐字：同包直解/
    跨 CAB externals env 内走查]"""
    fid, pid = pptr.get("m_FileID", 0), pptr.get("m_PathID", 0)
    if not pid:
        return None
    if fid == 0:
        o = owner_obj.assets_file.objects.get(pid)
    else:
        from eidolon.core.supply_index._unity import iter_serialized as _it

        ext = list(getattr(owner_obj.assets_file, "externals", []))
        cab = Path(ext[fid - 1].path).name.lower()
        o = None
        for f in _it(env):
            if Path(str(getattr(f, "name", ""))).name.lower() == cab \
                    and pid in f.objects:
                o = f.objects[pid]
                break
    if o is None or o.type.name != "MonoBehaviour":
        return None
    return o.read_typetree()


def _deref_font_env(resolver: _KitResolver, env, pptr: dict | None, owner_obj,
                    bundle: str):
    """FontDefinition.m_Font（跨 CAB/跨包 PPtr）→ Font ObjectReader。
    [text.py:_deref_font 逐字：同包→同 bundle 各 CAB→resolver 闭包（resolve_pptr）]"""
    if not pptr:
        return None
    fid, pid = pptr.get("m_FileID", 0), pptr.get("m_PathID", 0)
    if not pid:
        return None
    if fid == 0:
        return owner_obj.assets_file.objects.get(pid)
    from eidolon.core.supply_index._unity import iter_serialized as _it

    ext = list(getattr(owner_obj.assets_file, "externals", []))
    cab = Path(ext[fid - 1].path).name.lower()
    for f in _it(env):
        if Path(str(getattr(f, "name", ""))).name.lower() == cab and pid in f.objects:
            return f.objects[pid]
    try:
        o, _b = resolver.resolve_pptr(bundle, pptr, owner_obj)
        return o
    except Exception as exc:  # noqa: BLE001  PPtrError 分类面同参照（miss 记账不炸）
        logger.warning("[text_extract] deref_font miss cab=%s pid=%s: %s",
                       cab, pid, exc)
        return None


def _font_object_meta(fo) -> dict | None:
    """Font 对象元数据（字节面只记元数据——字节本体=ttf 域项）。[text.py:fontdefs]"""
    if fo is None:
        return None
    ftt = fo.read_typetree()
    data = ftt.get("m_FontData")
    return {
        "m_FontName": ftt.get("m_FontName") or ftt.get("m_Name") or "?",
        "m_AssetNames": ftt.get("m_AssetNames"),
        "m_FontRenderingMode": ftt.get("m_FontRenderingMode"),
        "m_CharacterRects": (len(ftt.get("m_CharacterRects") or [])
                             if isinstance(ftt.get("m_CharacterRects"), list) else None),
        "bytes": len(data) if data else 0,
        "path_id": fo.path_id,
    }


def extract_fonts(win: Path, *, catalog: dict[str, str], zhcat: dict[str, tuple[str, str]],
                  bundle_deps: dict[str, list[str]],
                  gge_path: Path | None = None,
                  resources_path: Path | None = None) -> dict:
    """fontdefs 全表 + locale 生效侧 TTF 字节（单进程；5 字体量级）。

    gge_path/resources_path=契约 D 显式流入（ctx.globalgamemanagers/ctx.resources；
    缺省由 data_win 布局推——标准装 root/Hearthstone_Data/*，非标准装必须显式）。
    返回 {"fontdefs": {name: rec}, "ttfs": {name: bytes}, "errors": [{font, why}]}。
    表级失败（font_table 缺/解析炸）=结构错误 raise（build 炸响亮）；单字体 TTF
    失败=errors 记账+无 item（warm 缺项面响亮）。"""
    if gge_path is None:
        gge_path = win.parent.parent / "Hearthstone_Data" / "globalgamemanagers"
    if resources_path is None:
        resources_path = win.parent.parent / "Hearthstone_Data" / "resources.assets"
    entries = read_font_table(gge_path, resources_path)
    resolver = _KitResolver(win, bundle_deps)

    fontdefs: dict[str, dict] = {}
    ttfs: dict[str, bytes] = {}
    errors: list[dict] = []
    for e in entries:
        base_guid = e["m_FontGuid"].lower()
        name = e["m_FontDefName"]
        rec: dict = {"m_FontName": e["m_FontName"], "m_FontDefName": name,
                     "base_guid": base_guid}
        sides: dict[str, tuple[str, str | None]] = {}
        for locale in ("enus", "zhcn"):
            if locale == "enus":
                guid, bundle = base_guid, catalog.get(base_guid)
            else:
                var = zhcat.get(base_guid)
                if var is None:
                    rec["zhcn"] = {"variant": None, "note": "无 zhCN 变体，用 base"}
                    continue
                guid, bundle = var
            side: dict = {}
            if not bundle:
                rec[locale] = {**side, "error": "bundle-not-in-catalog"}
                errors.append({"font": name, "side": locale,
                               "why": "bundle-not-in-catalog"})
                continue
            side["guid"] = guid
            side["bundle"] = bundle
            try:
                env = resolver.open_bundle(bundle)
                obj = resolver.container_get(bundle, guid)
                if obj is None:
                    raise KeyError(f"guid {guid} 不在 {bundle} container")
                fd = _read_fontdef_env(env, {"m_FileID": 0, "m_PathID": obj.path_id},
                                       obj)
                if fd is None:
                    fd = obj.read_typetree()
                side["fontdef"] = {k: v for k, v in fd.items()
                                   if k in TC.FONTDEF_FIELDS}
                fo = _deref_font_env(resolver, env, fd.get("m_Font"), obj, bundle)
                side["font_object"] = _font_object_meta(fo)
                sides[locale] = (guid, bundle)
                if fo is not None:
                    side["_font_reader"] = fo      # TTF 提取复用（不出进程面）
            except Exception as exc:  # noqa: BLE001
                rec[locale] = {**side, "error": f"{type(exc).__name__}: {exc}"}
                errors.append({"font": name, "side": locale,
                               "why": f"{type(exc).__name__}: {exc}"})
                continue
            rec[locale] = side
        fontdefs[name] = rec

        # TTF：locale 生效侧（zhcn 变体缺位跟 base——tp1 语义）；参照 _font_data
        try:
            pick = rec.get("zhcn")
            if not isinstance(pick, dict) or "guid" not in pick:
                pick = rec.get("enus")
            if not isinstance(pick, dict) or "guid" not in pick:
                raise KeyError("无可用侧（enus/zhcn 均未解析）")
            fo = pick.get("_font_reader")
            if fo is None:
                env = resolver.open_bundle(pick["bundle"])
                obj = resolver.container_get(pick["bundle"], pick["guid"])
                fd = _read_fontdef_env(env, {"m_FileID": 0, "m_PathID": obj.path_id},
                                       obj) or obj.read_typetree()
                fo = _deref_font_env(resolver, env, fd.get("m_Font"), obj,
                                     pick["bundle"])
            if fo is None:
                raise KeyError("Font 对象未命中")
            data = fo.read_typetree().get("m_FontData")
            if not data:
                raise KeyError("Font.m_FontData 空")
            ttfs[name] = bytes(data)
        except Exception as exc:  # noqa: BLE001
            errors.append({"font": name, "side": "ttf",
                           "why": f"{type(exc).__name__}: {exc}"})
        finally:
            for side in (rec.get("enus"), rec.get("zhcn")):
                if isinstance(side, dict):
                    side.pop("_font_reader", None)   # ObjectReader 不可 JSON/pickle

    return {"fontdefs": fontdefs, "ttfs": ttfs, "errors": errors}
