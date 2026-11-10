"""font_service — FontLoader/FontTable/FontDefinition 链（段 S7 字体服务）。

游戏锚：FontLoader.LoadFontTableData（Assembly-CSharp/FontLoader.cs:FontLoader.LoadFontTableData——
Resources.Load "ServiceData/FontTableData"；IUnreliableJobDependency 作业依赖
不复刻，我方同步线性）· FontTable.GetFontDef（Blizzard.T5.FontService/
Blizzard.T5.Fonts/FontTable.cs:FontTable.GetFontDef——GetFontDef(Font) 两跳 = GetFontDefName
（:88-98 按 m_FontName 线性查 m_Entries→m_FontDefName）→ GetFontDef(string)
（:51-58 空名/未命中→null））；FontDefinition（FontDefinition.cs:FontDefinition——8 字段：
m_Font/m_LineSpaceModifier/m_SingleLineAdjustment/m_FontSizeModifier/
m_CharacterSizeModifier/m_OutlineModifier/m_UnboundCharacterSizeModifier/
m_Name——行距/字号/描边系数）· 消费形=UberText.SetFont（UberText.cs:UberText.SetFont：
fontDef 七修饰字段写入组件 → m_LocalizedFont 换装）。

我方对位（批19 2026-10-14 转写 old_frames/uber_text.load_fontdef_mem + 旧
render_card.render_text_layer :312 每文字节点 FontDef 解析挂点）：
  * load_font_table_data = recipes.text.font_table（typetree 剥离→裸字节
    struct 解析，globalgamemanagers ResourceManager.m_Container 按路径索引，
    FontLoader.cs:FontLoader.LoadFontTableData 路径寻址复刻）。
  * fontdefs = recipes.text.fontdefs（enUS/zhCN 双侧真内存：FontDefinition
    8 字段 + locale_catalog zhCN 变体；Font.m_Font 字节面归 font_ttf_bytes）。
  * get_font_def = m_FontName→m_FontDefName→本地化（离线 zhCN 冻结）FontDef
    dict + _font_object_name + _ttf 真内存字节——旧 load_fontdef_mem 产物
    同构（渲染消费面：FontMetrics 按它取 TTF，uber_text.text_layer_plan
    每文字节点解析）。
  * load_font_data = recipes.text.font_ttf_bytes（Font.m_FontData 游戏直提）。

配方面：全经 recipes.text（font_table/fontdefs/font_ttf_bytes 三口）——
@item 供给配方，**消费须在入口层 supply session 内**（批12-18 纪律；本模块
不开 session）。离线边界：引擎 SetFont 的 fontDef==null 腔（:2113-2118
LogError+保序列化修饰）离线对应=无 zhCN 变体字体（BlizzardGlobal/BelweNumbers）
回落 base 侧（供给 tp1 语义；语料帧链挂载字体 Belwe_Outline/FranklinGothic
双侧俱全，回落支零行为）。
"""
from __future__ import annotations
from eidolon.core.render._provenance import parallel  # noqa: F401 （族默认）

# 离线冻结 locale（渲染语料口径 zhCN；UberText 侧枚举锚=uber_text.LOCALE_ZHCN=9）
_LOCALE = "zhcn"


@parallel
def load_font_table_data() -> list[dict]:
    """FontTableData.m_Entries 全表：FontLoader.LoadFontTableData 对位
    （FontLoader.cs:FontLoader.LoadFontTableData；Resources.Load 路径寻址+裸字节解析在配方域项）。

    返回 entry list（m_FontDefName/m_FontName/m_FontGuid 三键；资产经
    recipes.text.font_table）。"""
    from eidolon.core.recipes.text import font_table
    return font_table()


@parallel
def fontdefs() -> dict:
    """FontDef 全表（enUS/zhCN 双侧）：recipes.text.fontdefs 域项直通。

    返回 {FontDefName: {"m_FontName", "m_FontDefName", "base_guid",
    "enus": {guid/bundle/fontdef/font_object}, "zhcn": 同|{"variant": None}}}
    （FontDefinition 8 字段在 fontdef 子 dict；资产经 recipes.text.fontdefs）。

    族账锚=FontTable.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    from eidolon.core.recipes.text import fontdefs as _fontdefs
    return _fontdefs()


@parallel
def get_font_def(font_name: str, table: list[dict] | None = None) -> dict | None:
    """按名解析：FontTable.GetFontDef(Font) 对位（FontTable.cs:FontTable.GetFontDef 两跳）+ 旧面
    load_fontdef_mem 产物形（old_frames/uber_text.py:114-122）。

    两跳：GetFontDefName（m_FontName→m_FontDefName 线性查，:88-98）→
    GetFontDef(string)（空/未命中→None，:51-58）→ 本地化（离线 zhCN 冻结；
    无 zhCN 变体跟随 base=供给 tp1 语义，见头注离线边界）→ FontDef dict
    （8 修饰字段 + _font_object_name + _ttf=TTF 字节真内存）。
    table=调用方持有的 m_Entries（None=域项现取；每文字节点解析挂点——
    uber_text.text_layer_plan 消费）。"""
    entries = load_font_table_data() if table is None else table
    def_name = next((e["m_FontDefName"] for e in entries
                     if e["m_FontName"] == font_name), None)
    if not def_name:
        return None
    rec = fontdefs()[def_name]
    side = rec.get(_LOCALE) or {}
    if "fontdef" not in side:
        side = rec["enus"]
    fd = dict(side["fontdef"])
    fd["_font_object_name"] = side["font_object"]["m_FontName"]
    from eidolon.core.recipes.text import font_ttf_bytes
    fd["_ttf"] = font_ttf_bytes(def_name)
    return fd


@parallel
def load_font_data(font_name: str) -> bytes:
    """TTF 字节：Font.m_FontData 对位（游戏直提；资产经
    recipes.text.font_ttf_bytes，zhCN 变体跟随语义在配方域项）。返回字节串。

    族账锚=FontTable.cs（模块头注族账；逐字转写件——2026-10-29 挂牌域收口）。
    """
    from eidolon.core.recipes.text import font_ttf_bytes
    return font_ttf_bytes(font_name)
