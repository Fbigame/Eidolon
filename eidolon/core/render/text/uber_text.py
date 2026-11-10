"""uber_text — Blizzard.T5.UberText.Runtime 平行（段 S7 文字管线）。

游戏锚：UberText 组件（data/full_cs/Blizzard.T5.UberText.Runtime/UberText.cs:UberText
类声明，m_Font :31——跨包 PPtr）· UberText.SetFont（:2101——FontTable.GetFontDef
(m_Font.name)→本地化换装，font_service.get_font_def 消费形）·
UberText.SetupTextMeshAlignment（:1911，switch 九臂 :1918-1976 + GetAlignmentOffset
:1979-1985——cost 相位账 S6 已立，本段对齐轴）· 排版语义（wrap/resizeToFit/bold/
描边——text-rendering-pipeline.md 布局算法规格+富文本与描边节，UB 行号锚在该正典：
UberText.cs:UberText.m_CharacterSize CharacterSize、UB ReduceText_CharSize:2423、UB Bold:2690、UB Wrap:3612-3747、
CanWrapBetween:3949-4107、GetUnderwearBounds:4109-4128、GetFinalContainerWidth:
4171-4186、IsUnderwearNeeded:4188-4216、AdjustUnderwearForLocale:2573-2599、
BreakStringIntoWords:3804-3899、SetText '\n' 硬换行 :6397）。

我方对位（批19 2026-10-14 转写 old_frames/uber_text.py 管线本体——转写偏差零
容忍；正典出处=其头注，全部公式溯源反编译 C#/prefab 序列化/TTF 度量，无参照
拟合常量）：constants :43-47 / can_wrap_between :71 / wrap_lines :480 /
wrap_text_hard_lines :571 / layout_text :602 / make_font_metrics :793
（FontMetrics=FreeType CharacterInfo 语义类）· 节点装载=text_setup_for
（old_frames/render_card.py:221-241 分派 + 七份 load_node_settings* 副本收敛：
sc.ut:252 load_node_settings_mem〔ability PPtr 表〕/sca:103/wf:91/hero:119/
hp:95/loc:100——统一装载器+帧差异表 _TEXT_SETUP）· 文字层 plan 键构=
text_layer_plan（render_card.py:296-319 render_text_layer 的消费/装载/参数半）
· 对齐=set_alignment（SetupTextMeshAlignment 离线形）。渲染执行（render_text
的 RTT 曲面/平面/描边 9-tap/glyph 合成——old :699-1089）立户 engine/S11。

通用管线零逐卡特调（正典守则）。坐标链：字体像素 --(×cs×0.1)--> TextMesh
local --(×节点 lossyScale)--> 世界 --(fit 正交投影)--> canvas 像素；换行容器宽
=m_Width（TextMesh local，Wrap 期间 TextMesh GO 被摘出置 scale=1，渲染时才乘
节点 scale——头注原文）。名字弧面=引擎 RTT，我方渲到内存 RT 再贴曲面网格
（离线同构、无 RT 池）——执行半 S11。

配方面：FontDef 链经 game/font_service（recipes.text：font_table/fontdefs/
font_ttf_bytes）；场景五面经 game/frames.scene_for（recipes.frames kit 族）。
两处皆 @item 供给配方——**消费须在入口层 supply session 内**（批12-18 纪律；
本模块不开 session）。

离线边界记账：Underwear ellipsis 截断支（UberText.cs:UberText.ReduceText_CharSize，resize 触底才走）未转写
（语料未及，旧账如实承袭）；`[x]` 手动段按 `manual_at` 只关断标记**之后**的 CanWrapBetween
（前缀正常分词；UberTextLineWrapper.cs:UberTextLineWrapper.BreakStringIntoWords 的局部 flag2）；
`[b]` 词界保留 `_WORD_BREAK` 占位到 wrap 之后（标记后强制词界、零宽、**不补 '-'**，最终剥除）；
`[d]` 软连字符保留 `_SOFT_HYPHEN` 占位、自动断行处行尾补 '-'；`_` 改为 wrap 期原字符（下划线
advance、不产生断点）、wrap 后换 NBSP（UberText.RemoveLineBreakTagsHardSpace）——2026-10-19
四修（A 批三修 + 本批 `[b]`），机制账=docs/notes/text-rendering-pipeline.md。2026-10-23
**切词改 tag 感知**：`break_into_words` 按引擎 `BreakStringIntoWords` 走**原始文本**（tag
零宽、tag 字符留在当前 word、`lastChar` 取原文 ⇒ tag 的 '>' 进 CanWrapBetween），
`wrap_lines` 的角箱量宽按 `GetFinalContainerWidth(s_newText)` 的**已放置原始文本**口径
（`tw` = 可见行宽 + 尾部未闭合 run 的 tag 字面宽；撤掉旧 `tw=max(已放置, 本候选行)` 的
现象级拟合）——见两函数文档串。另外
`can_wrap_between`/`break_into_words`/`wrap_lines`/`wrap_text_hard_lines`/`layout_text` 均带
可选 `locale`（缺省 None=zhCN 逐位不变；只开 frFR/deDE 的宽空白前禁断分支——decomp
`UberTextLineWrapper.CanWrapBetween` 的 `Localization.GetLocale()` 特例的离线显式形，
生产调用方不传）。UB resize 收敛第二序误差不可达
（text-rendering-pipeline「已知精度限」：124073/76981 窗口空集，名义 LH box 判据
被像素裁决否决——正典 uber_text 零改动，本转写承其终态）；富文本 Bold=偏移二次
绘制/Italic=图集风格键变体属材质与图集线（渲染执行半 S11 消费面）。
"""
from __future__ import annotations

import dataclasses
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image
from scipy import ndimage as _ndi

from eidolon.core.render.text import font_service as _font_service  # consumer-v2 新包（S7 邻件）
from eidolon.core.render.text import ft_unhinted as _ft              # consumer-v2 新包（单源）
from eidolon.core.render.scenes import scenes as _frames              # consumer-v2 段4（prefab 键）
from eidolon.core.render.text import text_atlas as _text_atlas      # consumer-v2 新包
from eidolon.core.render._provenance import invented, parallel

# ---- 代码常量（反编译出处；old_frames/uber_text.py:43-47 逐字） ----
CHARACTER_SIZE_SCALE = 0.01   # UberText.cs:UberText.m_CharacterSize
RESIZE_SHRINK = 0.95          # UB ReduceText_CharSize:2423
RESIZE_MAX_ITERS = 40         # UberText.cs:UberText.ReduceText_CharSize
BOLD_SIZE_CAP = 10.0          # UB Bold():2690
LOCALE_ZHCN = 9               # Blizzard.T5.Localization Locale 枚举（zhCN=9）

# CanWrapBetween（UberTextLineWrapper.cs:UberTextLineWrapper.CanWrapBetween）zhCN 生效分支；koKR/frFR/deDE 特例按 locale 不触发。
_WRAP_AFTER_FORBIDDEN = (  # lastChar：其后禁断（开括号/开引号）
    36, 40, 91, 92, 123, 8216, 8220, 8245,
    12296, 12298, 12300, 12302, 12304, 12308, 12317,
    65113, 65115, 65117, 65284, 65288, 65339, 65371, 65505, 65509, 65510,
)
_WRAP_BEFORE_FORBIDDEN = (  # wideChar：其前禁断（闭标点）
    33, 37, 41, 44, 46, 58, 59, 63, 93, 125, 176, 183,
    8211, 8212, 8217, 8221, 8226, 8230, 8231, 8242, 8243, 8451,
    12289, 12290, 12297, 12299, 12301, 12303, 12305, 12309, 12318, 12540,
    65072, 65104, 65105, 65106, 65108, 65109, 65110, 65111,
    65114, 65116, 65118, 65281, 65285, 65289, 65292, 65294,
    65306, 65307, 65311, 65341, 65373, 65392, 65438, 65439, 65504,
)
_WRAP_CJK_RANGES = ((4352, 4607), (12288, 55215), (63744, 64255),
                    (65280, 65439), (65440, 65500))


def _is_cjk(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _WRAP_CJK_RANGES)

@parallel

def can_wrap_between(last_cp: int, wide_cp: int, next_cp: int,
                     locale: str | None = None) -> bool:
    """UB `UberTextLineWrapper.cs:UberTextLineWrapper.CanWrapBetween`（逐 case）。

    `locale`（可选，缺省 None）只开 frFR/deDE 的**宽空白前**禁断分支（decomp 该分支
    在通用 switch 之前、且以 `char.IsWhiteSpace(wideChar)` 为守卫）：
      * wideChar 为空白且 nextChar ∈ `! . : ; ? « »`（33/46/58/59/63/171/187）→ False；
      * 同守卫下 lastChar=='«'（171）→ False。
    缺省 None ⇒ 该分支不触发，逐位同改动前（zhCN 生产路径不传；`Localization.GetLocale()`
    在离线链无客户端态，故做成显式参数而非全局读取）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    if locale in ("frFR", "deDE") and chr(wide_cp).isspace():
        if next_cp in (33, 46, 58, 59, 63, 171, 187):
            return False
        if last_cp == 171:
            return False
    if last_cp == 45:                      # '-'：数字前不可断
        return not (48 <= wide_cp <= 57)
    if last_cp == 59:                      # ';'
        return True
    if wide_cp == 124:                     # '|'
        return True
    if chr(last_cp).isspace():
        return False
    if chr(wide_cp).isspace():
        return True
    if last_cp in _WRAP_AFTER_FORBIDDEN:
        return False
    if wide_cp in _WRAP_BEFORE_FORBIDDEN:
        return False
    if last_cp in (12290, 65292):          # 。。，之后必可断
        return True
    return _is_cjk(wide_cp)                # CJK 逐字可断


# ---------------------------------------------------------------------------
# FontDef / 节点字段（旧 :92-132 面的内存形）
# ---------------------------------------------------------------------------
@parallel

def locale_adjustment(fields: dict, locale: int = LOCALE_ZHCN) -> dict:
    """m_LocalizedSettings 中该 locale 条目（UB UberTextLocalization.Get*：缺失=无修饰）。
    zhCN(9) 在本帧 prefab 无条目（只有 koKR=4/thTH=15）→ 返回 {}。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    for adj in fields.get("m_LocalizedSettings", {}).get("m_LocaleAdjustments", []):
        if adj.get("m_Locale") == locale:
            return adj
    return {}


@dataclass
@parallel
class NodeSettings:
    """一个 UberText 节点：序列化字段 + 节点世界信息（prefab dump / frame_recon 直读）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    text_fields: dict
    world_pos: tuple                 # 世界平移 (x,y,z)
    local_scale: float               # 节点 lossyScale（世界矩阵列范数均值；weapon=面内轴）
    fontdef_name: str                # FontTable 链映射后的 FontDef 名
    rot_deg: float = 0.0             # 面内旋转（度）：世界矩阵 x-z 面内 X 轴角（图集路径消费）
    world_cols: tuple = (1.0, 1.0, 1.0)  # 世界矩阵列范数（文字平面轴 X/Y 的真实缩放；
                                     # RTT 平面 fallback 的矩形尺寸用，曲面 RTT 不消费）

    def f(self, key, default=None):
        return self.text_fields.get(key, default)


# ---------------------------------------------------------------------------
# 富文本与布局标记（ProcessText / BreakStringIntoWords 词法面）
# ---------------------------------------------------------------------------
@parallel

def split_rich(text: str) -> tuple[str, list[bool]]:
    """<b></b> → 纯文本 + 逐字 bold 标记；其余标签（ProcessText 的 <material=1> 等）剥离。

    Bold 消费语义（text-rendering-pipeline「富文本与描边」）：Bold=独立第二绘制
    （材质层 Hidden/Text_Bold + 子网格；UberText.cs:UberText.UpdateTexelSize UpdateTexelSize→SetBoldOffset，
    :2667-2679 Bold；shader=8 tap×0.23 求和，见 text_atlas._bold_offsets 抓帧账），
    本函数只产出逐字标记；绘制半属 S11。
    Italic=图集风格键变体（游戏自身预热 UberTextMgr.cs:UberTextMgr.ForceEnglishCharactersInAtlas 同时请求
    FontStyle.Normal/Italic）——<i> 标签的逐字标志由 italic_flags 承载。
    返回的 flags 与 `plain` 中**非 '\\n' 字符**逐位对齐（调用方按行消费字符；
    '\\n' 已被换行剥离，带 flags 会造成换行后整段错位——2026-10-18 实证修正）。

    嵌套语义（2026-10-19 富文本嵌套修复）：`<b>`/`<i>` 各用**独立深度计数**：
    open +1、close max(0,−1)、每字符 flag=depth>0——内层 `</b>` 不会提前关闭外层 span
    （旧布尔开关的 bug：`<b><b>连击</b>：</b>` 的外层「：」被去粗）。游戏侧**没有**
    double-bold：ProcessText 把每个 `<b>` 改写成 `<material=1>`、`Bold()` 是幂等 set
    （UberText.cs:UberText.Bold `if (!m_HasBoldText)` 才 SetBoldOffset），整个 TextMesh 只有
    1 个 bold 材质槽 ⇒ 本函数只产出「是否粗体」的逐字布尔，**不产出层数、不触发二次绘制**；
    深度只用于状态机配对，粗体数学仍在 text_atlas（单层 8 tap×0.23）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    chars: list[str] = []
    bold: list[bool] = []
    italic: list[bool] = []
    b_depth = 0
    i_depth = 0
    i = 0
    while i < len(text):
        if text.startswith("<b>", i):
            b_depth += 1
            i += 3
            continue
        if text.startswith("</b>", i):
            b_depth = max(0, b_depth - 1)
            i += 4
            continue
        if text.startswith("<i>", i):
            i_depth += 1
            i += 3
            continue
        if text.startswith("</i>", i):
            i_depth = max(0, i_depth - 1)
            i += 4
            continue
        if text[i] == "<":
            j = text.find(">", i)
            if j != -1:
                i = j + 1
                continue
        if text[i] != "\n":
            bold.append(b_depth > 0)
            italic.append(i_depth > 0)
        chars.append(text[i])
        i += 1
    return "".join(chars), bold, italic


_VALID_SQUARE_BRACKET_TAGS = ("b", "d", "x")   # UB IsValidSquareBracketTag:3002-3009

# `[d]`（软连字符）占位符：wrap 期保留位置、零 advance、测量时剥除（=引擎
# RemoveTagsFromWord 剥 [b|d|x]）；自动断行且行尾是它 → 换成 '-'（UberTextLineWrapper.Wrap
# `EndsWith(s_newText,"[d]")` 分支）。硬换行/末行只剥不补。'\x00' 不在任何字体 cmap，
# FontMetrics.char_info 显式给零掩码（见其分支）。
_SOFT_HYPHEN = "\x00"
# `[b]`（词界）占位符：`BreakStringIntoWords` 对 `[b]`/`[d]` 都是「追加记号后立即切词
# 出列」——词界在**标记之后**、记号零宽、最终文本剥除。与 `[d]` 的唯一差别是 `Wrap`
# 只对 `EndsWith("[d]")` 补 '-'，`[b]` **永不补**。'\x01' 不在任何字体 cmap，
# FontMetrics.char_info 显式给零掩码（见其分支）；逐字布局消费一个 bold/italic flag 位
# （与 plain 字符序 1:1，见 layout_text）。
_WORD_BREAK = "\x01"
# `_` 的 wrap 后替身（UberText.RemoveLineBreakTagsHardSpace:2940-2943）：NBSP 无断点、
# advance=空格（字体 cmap 有 U+00A0 时取之，否则回退 ' '）。
_NBSP = "\u00a0"

@parallel

def strip_layout_markers(text: str) -> tuple[str, int | None]:
    """方括号布局标记剥除 → (纯文本, `[x]` 在纯文本中的字符下标 / None)。

    出处（UB 字符级解析，程序集无 "[x]" 字面量）：
    - `[x]`：BreakStringIntoWords 置**局部** flag2（UberTextLineWrapper.cs:
      UberTextLineWrapper.BreakStringIntoWords `[x]` 分支）→ 此后 `!flag2 &&
      CanWrapBetween(...)` 才断词 ⇒ 只关断**标记之后**的自动断点（前缀正常分词），且
      flag2 持续到本次 Wrap 全文结束（跨硬换行段）。记号本身由 RemoveTagsFromWord /
      RemoveLineBreakTagsHardSpace 剥除。本函数返回标记**后**首字符在纯文本中的下标
      （=已输出字符数）；None=无 `[x]`。`manual_at==0`（行首 `[x]`，42700 形态）=全文手动。
    - `[b]`/`[d]`：词界标记（BreakStringIntoWords 追加记号后立即切词出列）。渲染文本中
      剥除（同上两处），但都保留为零宽占位到 wrap 之后：`[d]` → `_SOFT_HYPHEN`（自动
      断行处补 '-'），`[b]` → `_WORD_BREAK`（**不补** '-'）。`[b]` 占位让词界生效于
      `break_into_words`（引擎词界语义），最终行文本再由 `_line_final_text` 剥除。
      机制账=docs/notes/text-rendering-pipeline.md（四修节）。
    - `_`：**不替换**（引擎 Wrap 期按原字符量宽/断词，'_' 本身不产生断点；wrap 完成后
      才换 NBSP，见 layout_text 的逐行收尾）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    out: list[str] = []
    manual_at: int | None = None
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "[" and i + 2 < n and text[i + 2] == "]" \
                and text[i + 1] in _VALID_SQUARE_BRACKET_TAGS:
            tag = text[i + 1]
            if tag == "x":
                if manual_at is None:
                    manual_at = len(out)
            elif tag == "d":
                out.append(_SOFT_HYPHEN)
            elif tag == "b":
                out.append(_WORD_BREAK)
            i += 3
            continue
        out.append(text[i])
        i += 1
    return "".join(out), manual_at


def _strip_sentinels(text: str) -> str:
    """测量/出图用：剥 `[b]`/`[d]` 占位符（=引擎 RemoveTagsFromWord 剥 [b|d|x]）。"""
    if _SOFT_HYPHEN not in text and _WORD_BREAK not in text:
        return text
    return text.replace(_SOFT_HYPHEN, "").replace(_WORD_BREAK, "")


def _manual_index_after_tags(raw: str, raw_idx: int) -> int:
    """raw 下标 → split_rich 后纯文本下标（剥 `<...>` 标签后的字符计数）。

    strip_layout_markers 在 split_rich **之前**跑（方括号标记可在 <b> 域外，顺序反了
    bold_flags 索引错位）；其 manual_at 是含 `<b>` 等标签的 raw 坐标，须换算成纯文本
    坐标后才能给 break_into_words 的边界判定用。"""
    if raw_idx <= 0:
        return 0
    return len(re.sub(r"<[^>]*>", "", raw[:raw_idx]))


def _line_final_text(line: str, auto_break: bool) -> str:
    """wrap 产物行 → 最终行文本（引擎 RemoveLineBreakTagsHardSpace + ReplaceUnderscoredAngleBrackets）。

    * `[d]` 占位符：自动断行（auto_break=True）且行尾是它 → 行尾补 '-'（引擎在追加
      '\\n' 前 `EndsWith("[d]")` → Append('-')，随后剥标记 ⇒ 净效果=行尾 '-'）；硬换行/
      末行只剥除、不补。
    * `[b]` 占位符：**永不补 '-'**（引擎 `EndsWith("[d]")` 不命中 `[b]`）——自动断行处
      行尾若有 `[b]` 直接剥除。
    * `_` → NBSP（Wrap **之后**才替换；wrap 期按下划线字形量宽、不给断点）。
    * ReplaceUnderscoredAngleBrackets（`<_`→`< `/`_>`→` >`）在 richText 路径**是空操作**：
      引擎先做 NBSP 替换（'_' 已不存在），再 Replace；现行帧全 richText（本仓 split_rich
      已先剥 `<...>`），故不额外改写。"""
    text = line
    if auto_break and text.endswith(_SOFT_HYPHEN):
        text = text.rstrip(_SOFT_HYPHEN)
        text = text.replace(_WORD_BREAK, "") + "-"
    else:
        text = _strip_sentinels(text)
    if "_" in text:
        text = text.replace("_", _NBSP)
    return text


# ---------------------------------------------------------------------------
# 布局引擎（TextMesh local 单位；UB 语义）
# ---------------------------------------------------------------------------
@parallel

def break_into_words(text: str, fm: "FontMetrics", k: float,
                     manual_at: int | None = None,
                     locale: str | None = None) -> list[dict]:
    """UB BreakStringIntoWords（UberTextLineWrapper.cs:UberTextLineWrapper.BreakStringIntoWords）。

    **tag 感知**（2026-10-23 转写）：`<...>` 标签字符零宽，但**字符留在当前 word 里**
    （引擎 `s_wordBuilder` 对 tag 只 append、不切词），且 `lastChar`/`nextChar` 取
    **原始字符**——引擎 `char lastChar = text[i-1]` 用的是原文下标，tag 的 `'>'` 因此
    可能成为 `CanWrapBetween` 的 lastChar，**tag 边界直接接入断点判定**；我们旧版先
    剥 tag 再用纯文本逐字断，丢掉了这个边界（`' '→'<tag>'→'额'` 这类边界上引擎可断、
    纯文本不可断）。`num`（Σadvance）只服务 `ForceWrapLargeWords` 分支，zhCN（m_ResizeToFit
    ⇒ `!ResizeToFit || Ellipsized` 与 ForceWrapLargeWords=0 均不成立）不消费，故不记。

    每个 word 返回 dict：
      * `disp`：去 tag 文本（= `UberText.RemoveTagsFromWord` 结果，量宽/落行的口径）；
      * `open`：该词结束时是否**停在未闭合样式 run 内**（tag 栈非空）；
      * `tail_w`：未闭合 run 的 tag **字面字宽**之和（`wrap_lines` 的角箱量宽口径用：
        TextMesh 对尾部未闭合 run 不按富文本解析 tag，tag 字符按字面 glyph 计——见
        `wrap_lines` 注释）（机制账待晋升 docs/notes/text-rendering-pipeline.md）。

    `[b]`/`[d]` 哨兵：引擎词界分支「追加标记后立即切词出列」（占位符留在词尾，量宽时由
    `line_mesh_width` 剥除）。`[x]` 手动段：边界下标 `< manual_at` 才查 CanWrapBetween
    （引擎 `!flag2 && ...`，flag2 从 `[x]` 起持续到本次 Wrap 全文结束）；`manual_at` 是
    **去 tag 显示文本**下标。`locale` 透传给 `can_wrap_between`（缺省 None=zhCN 逐位行为）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    words: list[dict] = []
    buf: list[str] = []
    stack: list[float] = []          # 未闭合样式 run 的 tag 字面宽栈
    manual = manual_at is not None
    disp_i = 0
    prev_last: str | None = None     # 引擎 lastChar = text[i-1]（原始字符）
    first = True

    def emit() -> None:
        words.append({"disp": "".join(buf), "open": bool(stack),
                      "tail_w": sum(stack)})
        buf.clear()

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "<":
            j = text.find(">", i)
            if j != -1:
                tag = text[i:j + 1]
                if tag.startswith("</"):
                    if stack:
                        stack.pop()
                else:
                    stack.append(line_mesh_width(tag, fm, k))
                prev_last = ">"
                first = False
                i = j + 1
                continue
        if first:                    # 引擎：text[0] 直接进 s_wordBuilder、不查断点
            buf.append(ch)
            disp_i += 1
            prev_last = ch
            first = False
            i += 1
            continue
        if ch in (_SOFT_HYPHEN, _WORD_BREAK):
            buf.append(ch)           # 引擎 `[b]`/`[d]` 分支：追加标记后立即切词出列
            disp_i += 1
            emit()
            prev_last = ch
            i += 1
            continue
        allow = (not manual) or (disp_i < manual_at)
        if allow and can_wrap_between(ord(prev_last), ord(ch), 0, locale=locale):
            emit()
            buf.append(ch)
        else:
            buf.append(ch)
        disp_i += 1
        prev_last = ch
        i += 1
    emit()
    return words

@parallel

def line_mesh_width(line: str, fm: "FontMetrics", k: float) -> float:
    """TextMesh bounds x = minX₀ + (n−1)×adv + maxX_last（UB Wrap 的实测口径）。
    `[b]`/`[d]` 占位符零宽且不计入（=引擎 RemoveTagsFromWord 剥标记后再测）。
    `minX/maxX` 取 `FontMetrics.measure_box`（advance 盒 ∪ 墨盒；见其文档串——
    与栅格化摆位的墨迹 bearings 是两个口径，别混用）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    line = _strip_sentinels(line)
    if not line:
        return 0.0
    i0 = fm.measure_box(line[0])
    il = fm.measure_box(line[-1])
    inner = sum(fm.advance(c) for c in line[:-1])   # 除末字外全部 advance（含首字）
    return (i0[0] + inner + il[1]) * k

@parallel

def line_advance_width(line: str, fm: "FontMetrics", k: float) -> float:
    """行内逐字 advance 累计（哨兵剥除后 Σfm.advance×k；UB Wrap 量宽口径）

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    return sum(fm.advance(c) for c in _strip_sentinels(line)) * k

@parallel

def wrap_lines(words: list[dict], fm: "FontMetrics", k: float, width: float, height: float,
               line_spacing: float, underwear: dict | None,
               placed_lines: int = 0, placed_max_w: float = 0.0,
               placed_tail_w: float = 0.0,
               narrow_on: bool = False) -> tuple[list[tuple[str, bool]], int, float, float]:
    """UB UberTextLineWrapper.Wrap（UberTextLineWrapper.cs:UberTextLineWrapper.Wrap）主循环。

    `words` 来自 `break_into_words`（tag 感知词表，见其文档串）。

    每词容器宽重算（`GetFinalContainerWidth(s_newText, …)`，`s_newText` = **已放置原始
    文本**，含 tag）：
    - Flip=1：`y − (Height−y)×0.2 < UnderwearHeightLocaleAdjustment` → 收窄
      （y = 已放置文本顶点行框高 (n−1)×LH×sp + LH，TextGenerator 行槽语义，同垂直模型）；
    - Flip=0：已放置文本 TextMesh bounds 与 GetUnderwearBounds 双箱相交 → 收窄。
      测量态 = PrepareTextForUnderwear 把 TextMesh 摘到 (0, 0.25H) scale1 +
      SetTextAnchor(UpperCenter) → 文本 bounds x∈[−tw/2, tw/2]、y∈[0.25H−ys, 0.25H]；
      tw/ys 取已放置文本（跨硬换行段累计，由 placed_lines/placed_max_w/placed_tail_w 线程传入）。
      **tw = 已放置可见行宽 + 尾部未闭合 run 的 tag 字面宽**：`s_newText` 是**带 tag**的
      原始串，tag 在**闭合的**文本里零宽（25 卡引擎 `renderer.localBounds.size.x` 与本
      文件 `line_mesh_width` 逐值相同到 1e-6，含行内含 tag 的样本），但**尾部停在未闭合
      样式 run 内**时 TextMesh 不按富文本解析该 run，tag 字符按字面 glyph 计入 bounds
      ——即 `tw = placed_max_w + placed_tail_w`。判别证据=113242 合成文本四变体：断点处
      有 tag（粗体/白色 color）⇒ 角箱命中、断在 tag 前；去 tag 或空 tag 对 ⇒ 只按可见宽
      判、断在「额」后（几何：收窄门槛 = W×(1−uw) = 1.4625，已放置 1.3628 < 1.4625 ≤
      1.3628 + 0.3069（`<b>` 字面宽）= 1.670）。机制账待晋升 docs/notes/text-rendering-pipeline.md。
    - 收窄宽 = UnderwearWidthLocaleAdjustment = W×(1−uw_locale)（AdjustUnderwearForLocale），
      箱几何用序列化原始值（GetUnderwearBounds，非 locale 调整值）。
    - 几何等价：角箱内缘 = W×(1−uw)/2 ⇒ 在 y 相交的前提下「相交 ⟺ tw ≥ 收窄宽」。

    placed_lines/placed_max_w/placed_tail_w：先置硬换行段已放置的行槽数、最宽行（可见宽）
    与尾部未闭合 run 字面宽（引擎单次 Wrap 看全文，我方按段拆分后的等价线程态）；
    narrow_on = IsUnderwearNeeded 全文判定（wrap_text_hard_lines）。
    返回 ([(行文本, 是否自动断行)], 累计行槽数, 累计最宽行, 尾部字面宽)。行文本仍含
    `[b]`/`[d]` 占位符，自动断行行尾的 `[d]` 占位符由 `_line_final_text` 在逐字布局前
    换成 '-'（`[b]` 不补）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    boxes = None
    if underwear and narrow_on:
        boxes = _underwear_boxes(width, height, underwear)   # UberTextLineWrapper.cs:UberTextLineWrapper.GetUnderwearBounds（UseUnderwear 且 flag）
    lines: list[tuple[str, bool]] = []
    cur = ""
    for i, wd in enumerate(words):
        w = wd["disp"]
        cand = cur + w
        x = line_mesh_width(cand, fm, k)
        container = width
        if boxes is not None:
            # s_newText 行槽数：word 0 未放置（硬 '\n' 在其词首）→ 先置行槽数；
            # i>0 → 先置 + 本段完成行 + 当前行（UberTextLineWrapper.cs:UberTextLineWrapper.Wrap 放置语义）
            n_slots = placed_lines if i == 0 else placed_lines + len(lines) + 1
            # y = 已放置文本顶点行框高（n−1）×pitch + LH：与垂直模型 v2 同用**浮点 span**
            #（TextGenerator 顶点语义；整型 line_height 会把收窄边界提前一整行）。
            ys = ((n_slots - 1) * fm.line_height_float * line_spacing
                  + fm.line_height_float) * k if n_slots else 0.0
            if underwear["flip"]:
                if ys - (height - ys) * 0.2 < underwear["h_adj"]:     # UberTextLineWrapper.cs:UberTextLineWrapper.GetFinalContainerWidth
                    container = underwear["narrow_w"]
            else:
                # UberTextLineWrapper.cs:UberTextLineWrapper.GetFinalContainerWidth：textMeshBounds.Intersects(underwearLeft||Right)（闭区间——R1-1 正典措辞修正 2026-10-22；实现与 Unity 同为闭区间）。
                # tw = 已放置**原始**文本（含 tag）的 bounds x：可见行宽 + 尾部未闭合 run 的
                # tag 字面宽（tag 在闭合文本里零宽、未闭合 run 尾按字面 glyph 计——见文档串）。
                left, right, half = boxes
                tw = placed_max_w + placed_tail_w
                if (_bounds_intersect(tw, ys, height, left[0], left[1], half)
                        or _bounds_intersect(tw, ys, height, right[0], right[1], half)):
                    container = underwear["narrow_w"]
        if x < container:
            cur = cand
            placed_max_w = max(placed_max_w, line_mesh_width(cur, fm, k))
            placed_tail_w = wd["tail_w"]
        else:
            # 自动断行：行尾留给 _line_final_text 判 `[d]` → '-'（硬换行行由段边界标记 False）。
            # 引擎 UberTextLineWrapper.Wrap 只在 `s_newText.Length > 0` 时补 '\\n'：行首第一个
            # 词就超容器（长词/手动段独占）时不产生空行——`if cur` 即该判据。
            # 行首占位符（文本以 `[b]`/`[d]` 开头）**不构成一行**：引擎 BreakStringIntoWords
            # 的循环从 i=1 起，行首标记不识别为切词（与后词同词）；我方把哨兵并进首词，
            # 既不给空行也不丢 flag 位（哨兵仍在行文本里被逐字循环消费）。
            # 行首 tag-only 词（disp=''）同法：`cur` 仍为空串 ⇒ 并入下一词、不产空行。
            if cur and cur.strip(_SOFT_HYPHEN + _WORD_BREAK):
                lines.append((cur, True))
                cur = w
            else:
                cur += w
            placed_max_w = max(placed_max_w, line_mesh_width(cur, fm, k))
            placed_tail_w = wd["tail_w"]
    if cur:
        lines.append((cur, False))
    return lines, placed_lines + len(lines), placed_max_w, placed_tail_w


def _underwear_boxes(width: float, height: float, underwear: dict):
    """UB GetUnderwearBounds:4109-4128 转写：双箱 center/half（z 恒含文本，size.z=1）。"""
    uw, uh = underwear["uw_raw"], underwear["uh_raw"]   # 箱几何 = 序列化原始值（非 locale 值）
    half = (width * uw * 0.25, height * uh * 0.25)      # size=(W×uw×0.5, H×uh×0.5) 之半
    cy = (height * 0.5 - height * uh * 0.5) if underwear["flip"] \
        else (-height * 0.5 + height * uh * 0.5)        # UberTextLineWrapper.cs:UberTextLineWrapper.GetUnderwearBounds
    return (width * 0.5 - width * uw * 0.25, cy), \
           (-width * 0.5 + width * uw * 0.25, cy), half  # UberTextLineWrapper.cs:UberTextLineWrapper.GetUnderwearBounds / :4124


def _bounds_intersect(tw: float, ys: float, height: float,
                      cx: float, cy: float, half: tuple) -> bool:
    """Unity Bounds.Intersects（闭区间——R1-1 正典措辞修正 2026-10-22；实现与 Unity 同为闭区间）转写。文本 bounds：UpperCenter 锚挂
    PrepareTextForUnderwear 位置 (0, 0.25H)（UberTextLineWrapper.cs:UberTextLineWrapper.PrepareTextForUnderwear+3630）→ x∈[−tw/2,tw/2]、
    y∈[0.25H−ys, 0.25H]；z 向箱 [−0.5,0.5]（UberTextLineWrapper.cs:UberTextLineWrapper.GetUnderwearBounds size.z=1）恒含文本 z≈0 → 不判。"""
    tmin_x, tmax_x = -tw / 2.0, tw / 2.0
    tmin_y, tmax_y = height * 0.25 - ys, height * 0.25
    bmin_x, bmax_x = cx - half[0], cx + half[0]
    bmin_y, bmax_y = cy - half[1], cy + half[1]
    return not (bmax_x < tmin_x or bmin_x > tmax_x or bmax_y < tmin_y or bmin_y > tmax_y)


def _underwear_needed_flip1(text: str, fm: "FontMetrics", k: float, width: float,
                            locale: str | None = None) -> bool:
    """UB IsUnderwearNeeded:4188-4216 的 Flip=1 支（Flip=0 恒真 :4190，不进本函数）：
    逐词累计去标签串的 mesh 宽，首个 ≥orgWidth 即真（:4202-4208；累计单调 ⟺ 全文达标）；
    或累计词含 '\\n'（:4210-4213——溢出后才出现的 '\\n' 已由上一条判真，故查全文等价）。
    `locale` 透传（词界与 Wrap 同源；缺省 None=zhCN 逐位行为）。"""
    acc = ""
    for wd in break_into_words(text, fm, k, locale=locale):
        acc += wd["disp"]
        if line_mesh_width(acc, fm, k) >= width:
            return True
    return "\n" in acc

@parallel

def wrap_text_hard_lines(raw: str, fm: "FontMetrics", k: float, width: float, height: float,
                         line_spacing: float, underwear: dict | None,
                         manual_at: int | None = None,
                         locale: str | None = None) -> list[tuple[str, bool]]:
    """硬换行 '\\n' 逐段 wrap（UberText.cs:UberText.SetText SetText → TextMesh 原生语义：'\\n' 即硬换行，
    word wrap 只在硬行内生效；空段=空行占一行）。

    入参 `raw` = **仍含 `<...>` tag** 的文本（strip_layout_markers 之后、`[b]/[d]` 已换哨兵）：
    引擎单次 Wrap 吃的是 ProcessText 后的带 tag 原文，切词状态机要按原始字符走（见
    `break_into_words`）；落行/量宽仍用去 tag 的 `disp`。

    IsUnderwearNeeded（UberTextLineWrapper.cs:UberTextLineWrapper.IsUnderwearNeeded）看的是全文（引擎单次 Wrap）：Flip=1 = 累计词宽达容器
    或含 '\\n'；Flip=0 恒真。

    `manual_at`：`[x]` 后首字符在**去 tag 显示文本**（含 '\\n'）中的下标；按段换算成段内
    相对下标（flag2 跨硬换行段持续）。`locale` 透传（缺省 None=zhCN 逐位行为）。
    返回 [(行文本, 是否自动断行)]——段内非末行=自动断行（行尾 `[d]` 占位符要补 '-'，
    `[b]` 不补），段末行/末行为硬换行或全文末行（只剥不补）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    out: list[tuple[str, bool]] = []
    narrow_on = False
    if underwear:
        narrow_on = True if not underwear["flip"] \
            else ("\n" in raw or _underwear_needed_flip1(raw, fm, k, width, locale=locale))
    placed = 0            # 已放置行槽（跨段累计 = 引擎 s_newText 行数）
    placed_max_w = 0.0    # 已放置最宽行（TextMesh bounds x 的可见宽口径）
    placed_tail_w = 0.0   # 已放置文本尾部未闭合 run 的 tag 字面宽（bounds x 的另一项）
    start = 0
    for seg in raw.split("\n"):
        if seg:
            seg_manual = None
            if manual_at is not None:
                rel = manual_at - start
                # rel<=0：本段开头即已进入手动段；rel>=len(seg)：标记在本段之后（本段无影响）
                seg_len = len(re.sub(r"<[^>]*>", "", seg))
                seg_manual = 0 if rel <= 0 else (None if rel >= seg_len else rel)
            words = break_into_words(seg, fm, k, manual_at=seg_manual, locale=locale)
            seg_lines, placed, placed_max_w, placed_tail_w = wrap_lines(
                words, fm, k, width, height, line_spacing, underwear,
                placed_lines=placed, placed_max_w=placed_max_w,
                placed_tail_w=placed_tail_w, narrow_on=narrow_on)
            out.extend(seg_lines)
        else:
            out.append(("", False))
            placed += 1
        start += len(re.sub(r"<[^>]*>", "", seg)) + 1
    return out

@parallel

def layout_text(text: str, ns: NodeSettings, fd: dict, fm: "FontMetrics",
                line_gap: bool = False, locale: str | None = None) -> dict:
    """排版：layout_text 对位（old_frames/uber_text.py:602；规格 §2a/§2b/§2c——
    字号→charSize→换行→resizeToFit→逐字 pen，local 单位）。

    locale 自 ns.text_fields 现取（旧第 5 参=render_text 预取的同一 locale_adjustment
    产物，内部化等价）。返回行装配 dict（旧 Layout dataclass 字段同名：
    lines=[[{ch,pen_x,line,bold}]]/line_widths/pitch/box_h/fs/k/line_height_px）。
    `locale`=**可选的换行 locale 语义位**（"frFR"/"deDE" 才开 CanWrapBetween 的宽空白前
    禁断分支；缺省 None=zhCN 逐位行为，生产调用方不传）。注意与 `locale_adjustment`
    （prefab 的 m_LocalizedSettings 定制，函数内取）是两个不同概念：前者是进程级
    `Localization.GetLocale()` 的离线显式形。
    line_gap=True → 行高用 FreeType `metrics.height`（hhea asc−desc+**lineGap**），
    即引擎 TextMesh 的行高语义（抓帧实证见 FontMetrics.line_height_gap_float）；
    仅 `_LINE_GAP_ROLES`（race/race_multi/name/plate）走，其余角色保持 asc−desc 逐位行为
    ——数字角色（cost/attack/health/durability，fit=0、不消费 TextMesh bounds）的引擎实测
    就是 asc−desc 盒（第六轮 A/B：改 metrics.height 反而 αMAE 0.055–0.106 → 2.1–4.0）；
    plate 是 fit=1+grow=1 的共 prefab 盒对照，第七轮 A/B 改善 26/26 而加入（见
    `_LINE_GAP_ROLES` 注）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    lh_f = fm.line_height_gap_float if line_gap else fm.line_height_float
    loc_adj = locale_adjustment(ns.text_fields)
    fs = int(fd["m_FontSizeModifier"] * loc_adj.get("m_FontSizeModifier", 1.0) * ns.f("m_FontSize"))
    cs = ns.f("m_CharacterSize") * fd["m_CharacterSizeModifier"] * CHARACTER_SIZE_SCALE
    cs *= fd.get("m_UnboundCharacterSizeModifier", 1.0) * loc_adj.get("m_UnboundCharacterSizeModifier", 1.0)
    k = cs * 0.1
    width = ns.f("m_Width")
    height = ns.f("m_Height")
    word_wrap = bool(ns.f("m_WordWrap"))
    # [x] 手动段（UB BreakStringIntoWords `[x]` 分支置局部 flag2 → 此后 `!flag2 &&
    # CanWrapBetween(...)` 才断词）：只关断标记**之后**的自动断点，前缀正常分词；不再把
    # 整个节点置 word_wrap=False（旧实现整段关断 + 改走单行/多行行距支 + resize 支）。
    # 先剥布局标记再拆 rich（bold_flags 与 plain 逐位对齐的硬要求——方括号标记可出现在
    # <b> 域外，顺序反了索引错位）；manual_at 由 raw 坐标换算成 split_rich 后的纯文本坐标。
    plain0, manual_raw = strip_layout_markers(text)
    plain, bold_flags, italic_flags = split_rich(plain0)
    manual_at = None if manual_raw is None else _manual_index_after_tags(plain0, manual_raw)

    sp_single = ns.f("m_LineSpacing") + ns.f("m_SingleLineAdjustment", 0.0) \
        + loc_adj.get("m_SingleLineAdjustment", 0.0)
    sp_multi = ns.f("m_LineSpacing") * (fd["m_LineSpaceModifier"] * loc_adj.get("m_LineSpaceModifier", 1.0))

    underwear = None
    if word_wrap and ns.f("m_Underwear"):
        # AdjustUnderwearForLocale（UberText.cs:UberText.AdjustUnderwearForLocale）：locale 条目值 >0 才覆写序列化值；
        # zhCN(9) 在六帧 prefab 的 m_LocaleAdjustments 均无条目（游戏直读）→ 恒走回落支。
        uw_s = float(ns.f("m_UnderwearWidth"))
        uh_s = float(ns.f("m_UnderwearHeight"))
        uw_l = float(loc_adj.get("m_UnderwearWidth") or 0.0)
        uh_l = float(loc_adj.get("m_UnderwearHeight") or 0.0)
        uw = uw_l if uw_l > 0.0 else uw_s
        uh = uh_l if uh_l > 0.0 else uh_s
        flip = bool(ns.f("m_UnderwearFlip"))
        underwear = {
            "flip": flip,
            "narrow_w": width * (1.0 - uw),                         # UnderwearWidthLocaleAdjustment（:2598）
            "h_adj": height * uh if flip else height * (1.0 - uh),  # UnderwearHeightLocaleAdjustment（:2592/:2596）
            "uw_raw": uw_s, "uh_raw": uh_s,                         # GetUnderwearBounds 箱几何（:4115-4124）
        }

    def build_items(kk):
        """wrap 产物 [(行文本(含 [b]/[d] 占位符), 是否自动断行)]；非 wordwrap = 逐个硬行。

        wordwrap 输入是**带 tag 的 `plain0`**（不是 `plain`）：切词状态机按原始字符走
        （`break_into_words` 的 tag 零宽/词内保留/'lastChar' 取原文），落行仍是去 tag 的
        显示字符——两者字符序一一对应，故 `plain`/`bold_flags` 的逐字下标消费不变。"""
        if word_wrap:
            return wrap_text_hard_lines(plain0, fm, kk, width, height, sp_multi, underwear,
                                        manual_at=manual_at, locale=locale)
        return [(seg, False) for seg in plain.split("\n")]

    def finalize(items):
        """wrap 后收尾：`[d]`→自动断行补 '-'/其余剥除，'_'→NBSP（wrap 之后才换）。"""
        return [_line_final_text(t, a) for t, a in items]

    line_items = build_items(k)
    line_texts = finalize(line_items)
    sp_eff = sp_multi if word_wrap else (sp_single if len(line_texts) == 1 else sp_multi)

    # resizeToFit（UberText.cs:UberText.SetText `if (m_ResizeToFit) ResizeTextToFit(text)`；两支互斥）：
    #   * m_ResizeToFitAndGrow=1 → ResizeToFitBounds_CharSize（UberText.cs:UberText.ResizeToFitBounds_CharSize）：非 wordwrap
    #     支一次到位 `characterSize *= min(GetHeight()/bounds.y, GetWidth()/bounds.x)`
    #     ——只改 characterSize（world=CharacterInfo(px)×cs×0.1），**字号/图集键不变**。
    #     bounds=TextMesh renderer bounds（ResizeTextToFit 先把 mesh 摘父、localScale=1，
    #     故=局部单位）：单行 y=裸 LH·k、x=advance 和（l_i 行取最宽）。全帧审计里
    #     grow=1 只有 race/RaceUberText（ally 随从族）与 spell 帧 plate/RaceUberText
    #     （学派名，同一 prefab 盒 0.85×0.17）；多 race 卡 actor 侧只关单 race 节点
    #     （Actor.cs:Actor.UpdateRace 不含 m_multiRaceTextMesh），grow 仍生效。
    #   * 否则 → ReduceText_CharSize（UberText.cs:UberText.ReduceText_CharSize）0.95 收缩循环（既有实现，desc/name 等）。
    # 注意：resize 的量测对象是**已收尾文本**（引擎 ReduceText_CharSize 里 WordWrapString 返回
    # 的就是 RemoveLineBreakTagsHardSpace 之后带 NBSP/'-' 的文本），重 wrap 仍从原始 plain
    # （含 [d] 占位符与 '_'）起算并带同一 manual_at。
    if ns.f("m_ResizeToFit") and ns.f("m_ResizeToFitAndGrow") and not word_wrap:
        # bounds.y = **裸盒高**（TextMesh renderer bounds = (n−1)×pitch + LH×k；grow 支
        # 不扣 intra-line——扣 intra 的是 ReduceText_CharSize，两支语义不同：
        # 2 行 race_multi（H=0.24、pitch=0.85LH）裸盒 0.291 → 收 0.824；扣 intra
        # 会误成 2LH=0.315 → 0.762（偏小 7%）。
        LHk = lh_f * k
        y = (len(line_texts) - 1) * (lh_f * k * sp_eff) + LHk
        x = max(line_mesh_width(t, fm, k) for t in line_texts) if line_texts else 0.0
        # 引擎判据（UberText.cs:UberText.ResizeToFitBounds_CharSize）：文字宽与盒宽差 >1% 才进缩放支；grow 只由 y 定
        if x > 0.0 and y > 0.0 and (x - x * 0.01 < width or x + x * 0.01 > width):
            scale = min(height / y, width / x)
            if scale > 0.0:
                cs *= scale
                k = cs * 0.1
    elif ns.f("m_ResizeToFit"):
        # ReduceText_CharSize（UberText.cs:UberText.ReduceText_CharSize）：入口那次量测与
        # 循环体内量测**不同口径**——入口（:2385-2397）先按 `IsMultiLine()`（=m_LineCount>1）
        # 定 line spacing（多行 → `SetLineSpacing(m_LineSpacing)`，否则 `SetLineSpacing(0f)`；
        # :2221-2225 的入参再按**调用时刻**文本行数分臂），把该值冻结进 TextMesh，再
        # `y -= Measure_IntraLine_Height()`（:2369-2378：临设 "|" / "|\n|" 两次读 bounds，
        # 返回 pitch_meas − 单行盒）。两处行数口径的关键：**Wrap 会按引用改写 m_LineCount**
        # （:2585 `WordWrapString(..., ref m_LineCount, ...)`），故 wordwrap 节点进入本函数时
        # IsMultiLine() 看的是**wrap 后**行数，与当前 TextMesh 文本行数一致。
        # ⇒ 入口 spacing = 单行时 `0 + m_SingleLineAdjustment(+locale)`、多行时 sp_multi：
        #   * 单行（六帧 name 节点：adj=0）⇒ spacing=0 ⇒ 「|\n|」两行 pitch=0（同一基线），
        #     intra = 单行盒 − 2×单行盒 = **−单行盒** ⇒ **首次判据 y = 2×单行盒**。name 帧
        #     2×LHk ≈ 0.36–0.45 > 盒高 0.25/0.28/0.30 ⇒ 引擎对每个单行 fit 节点**至少缩一步**
        #     0.95（第三步活 oracle「10/10 name 节点 cs/(mCS×0.01)=0.950000」= 此机制；本批
        #     9 卡 oracle 全数吻合：67803 类 3 步 / 128044 2 步 = 首次免费步之后仍由 x 驱动
        #     的宽度步数，129851/8/76981 恰 1 步）。
        #   * 多行 ⇒ spacing = sp_multi ⇒ intra = 单行盒×(sp_multi−1)，首次判据 = 盒高 + 该项
        #     （desc 等多行 fit 节点；其后续步进仍由 x/盒高驱动）。
        # 循环体内（:2430-2441）每次重测只取 size.x/size.y，**不再扣 intra**，且按当前文本
        # 行数重设 spacing。故：首轮用入口口径，其后用循环口径。
        adj_sp = (ns.f("m_SingleLineAdjustment", 0.0)
                  + loc_adj.get("m_SingleLineAdjustment", 0.0))
        sp_entry = adj_sp if len(line_texts) == 1 else sp_multi
        for it in range(RESIZE_MAX_ITERS):
            LHk = lh_f * k
            n_lines = len(line_texts)
            # 循环体内量测 = **裸盒** `(n−1)·pitch + LHk`（多行）/ `LHk`（单行）——引擎循环
            # 每次 `SetText` 后只取 `GetTextMeshBounds()` 的 size.x/size.y（ReduceText_CharSize
            # 循环体），**不再扣 intra**；intra 只在入口减一次（见下 it==0 支）。
            # 旧式的两种口径写反了：循环用 `(n−2)p+2L`（入口扣过 intra 的形状，偏大 `L−p`）
            # ⇒ 阈值边缘多缩一步 0.95。实证（5 张 heropower 卡：cs 0.042761578 vs 引擎
            # 0.045012183 = 20/19 一整步）：4 行文本 at cs=0.0450122 裸盒
            # `(4−1)·0.9375L+L=3.8125L=0.8244 ≤ H=0.83`（引擎接受），旧式 3.875L=0.838>0.83。
            # 单行 n=1 两支同值（LHk）⇒ name 支逐位不变。
            y = ((n_lines - 1) * (lh_f * k * sp_eff) + LHk) if n_lines > 1 else LHk
            if it == 0:
                # 入口量测（`ReduceText_CharSize`：`y -= Measure_IntraLine_Height()`）：
                # **y = bounds − intra**，bounds 用入口冻结 spacing 的裸盒
                # `(n−1)·pitch_entry + LHk`（n=1 退化为 LHk）、`intra = pitch_entry − LHk`
                # ⇒ 多行入口 `y = (n−2)·pitch_entry + 2·LHk`；单行（adj=0 ⇒ pitch=0）
                # 退化为 `2·LHk`（name「至少缩一步」的机制，见 _NAME_RTT 注）。
                # 旧式在**多行**入口把 intra 扣了两次（`(n−2)p+2L − (p−L)`），入口判据
                # 偏小 `L−p`——与循环口径的错误方向相反、在入口这一步互相掩盖。
                # 单行支与旧式逐位相同，name 行为不变。
                # 实验账与逐卡数字留实验记录（layer_guard 禁本文件出现实验路径）。
                pitch_entry = LHk * sp_entry
                bounds_entry = (((n_lines - 1) * pitch_entry + LHk)
                                if n_lines > 1 else LHk)
                y = bounds_entry - (pitch_entry - LHk)
            x = max(line_mesh_width(t, fm, k) for t in line_texts)
            if y <= height and x <= width:
                break
            cs *= RESIZE_SHRINK
            floor_cs = ns.f("m_MinCharacterSize") * CHARACTER_SIZE_SCALE
            if cs <= floor_cs:
                cs = floor_cs
                k = cs * 0.1
                if word_wrap:
                    line_items = build_items(k)
                    line_texts = finalize(line_items)
                break
            k = cs * 0.1
            if word_wrap:
                line_items = build_items(k)
                line_texts = finalize(line_items)

    # 垂直模型 v2（42700 desc 行位亚像素标定 + 字体度量出处）：pitch = 浮点 span
    #（hhea asc−desc 缩放）×k×sp_eff；盒 = (n−1)×pitch + 裸 LH×k（TextGenerator 顶点
    # 语义：行距只作用在行间，末行保持原始 LH）；基线 = 盒顶 + li×pitch + round(asc)×k。
    pitch = lh_f * k * sp_eff
    lines: list[list[dict]] = []
    line_widths: list[float] = []
    gi = 0
    for li, (lt, auto) in enumerate(line_items):
        row: list[dict] = []
        pen = 0.0
        # 行尾 `[d]` 占位符 run：自动断行 → 首占位符出 '-'（引擎 Append('-') 后剥标记），
        # 其余剥除；`[b]` 占位符**永不**出 '-'（引擎 EndsWith("[d]") 不命中 `[b]`）。
        # bold/italic 逐字标志按 plain 字符序消费（占位符也占一个 flag 位，保证 flags
        # 与行文本一一对应不错位）。
        n_trail = (len(lt) - len(lt.rstrip(_SOFT_HYPHEN))) if (auto and lt.endswith(_SOFT_HYPHEN)) else 0
        for pos, ch in enumerate(lt):
            if ch == _WORD_BREAK:
                gi += 1          # 消费一个 flag 位（与 `[d]` 非行尾同法），零可见字/零 advance
                continue
            if ch == _SOFT_HYPHEN:
                flag_i = gi
                gi += 1
                if n_trail and pos == len(lt) - n_trail:
                    vis = "-"
                else:
                    continue
            else:
                flag_i = gi
                gi += 1
                vis = _NBSP if ch == "_" else ch
            row.append({"ch": vis, "pen_x": pen, "line": li,
                        "bold": bold_flags[flag_i] if flag_i < len(bold_flags) else False,
                        "italic": italic_flags[flag_i] if flag_i < len(italic_flags) else False})
            pen += fm.advance(vis) * k
        lines.append(row)
        line_widths.append(line_advance_width(line_texts[li], fm, k))
    box_h = (len(line_texts) - 1) * pitch + lh_f * k
    return {"lines": lines, "line_widths": line_widths, "pitch": pitch,
            "box_h": box_h, "fs": fm.size, "k": k, "line_height_px": fm.line_height}


# ---------------------------------------------------------------------------
# FreeType 度量（Unity CharacterInfo 整型像素语义；old :279-354 类本体）
# ---------------------------------------------------------------------------

@dataclass
@parallel
class CharInfo:
    """单个字形的整型像素度量（Unity CharacterInfo 语义：advance/minX/maxX/minY/maxY）

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    advance: int
    minX: int
    maxX: int
    minY: int
    maxY: int


@parallel
class FontMetrics:
    """CharacterInfo 取**引擎口径** FreeType 位图语义（ft_unhinted 驱动单源）：
    minX=bitmap_left, maxX=minX+width, maxY=bitmap_top, minY=maxY−rows；
    advance=`Glyph.advance_px`=`(advance_26_6+32)>>6`（round half up —— v3.1 修正：
    旧 `int(round(hmtx×fs/upem))` 是 Python 半偶舍入，@36 的 S/X/Y 得 22 而引擎=23）。
    行高按规格公式（FreeType 线性度量取整）：ceil(ascent) − floor(descent)。
    垂直模型 v2：pitch 用浮点 span、基线 round(asc)（layout_text 内注释有出处）。

    栅格化口径（v3.1）：FT_LOAD_NO_HINTING（正典 docs/notes/text-rendering-pipeline.md
    §字形栅格化口径）。PIL 的 hinted 字体对象已退役——它无 load flags、永远 hinted，正是
    「GLEI 与引擎差 0.94」的历史主因。

    缺字兜底（v3.1）：cmap 前置判定——本字体 cmap 缺字符 → `glyph_supply.
    resolve_fallback` 的引擎两级查找（资产 m_FallbackFonts → 内置 11 项有序族名表 →
    U+FFFD）。位图与 advance **同源**（同一回退 face 的 unhinted 位图 + 该 face 自身
    FT advance 取整），事件（族名/文件/sha/版本/face/advance）进 glyph_supply 响亮账。
    布局与栅格化同经 char_info 单源（layout 期一次定案、栅格化期同判）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """

    def __init__(self, ttf, font_size: int, font_name: str = ""):
        # ttf: 路径（文件面，诊断直调兼容）或 bytes（供给真内存——font_service.get_font_def
        # 的 _ttf 槽）。字节面经 glyph_supply.materialize_ttf 落成内容寻址文件（驱动只吃
        # 路径）；fontTools 只留 hhea/head（垂直度量需要），hmtx/cmap 不再消费。
        import io
        self.size = int(font_size)
        self.font_name = str(font_name)
        if isinstance(ttf, (bytes, bytearray)):
            from eidolon.core.render.text import glyph_supply as _gs
            _gs.register_font_bytes(f"game:{self.font_name or '<unnamed>'}", bytes(ttf))
            self.path = "<memory>"
            self._tt = TTFont(io.BytesIO(ttf))
            self._face_path = _gs.materialize_ttf(bytes(ttf))
        else:
            self.path = str(ttf)
            self._tt = TTFont(self.path)
            self._face_path = Path(self.path)
        upem = self._tt["head"].unitsPerEm
        hhea = self._tt["hhea"]
        self.ascent = math.ceil(hhea.ascent * self.size / upem)
        self.descent = math.floor(hhea.descent * self.size / upem)   # ≤0
        self.line_height = self.ascent - self.descent
        # 垂直模型 v2：FT 逐度量 round 的 asc/desc 与浮点 span（42700 desc 行位亚像素标定）。
        self.ascent_f = hhea.ascent * self.size / upem
        self.descent_f = hhea.descent * self.size / upem
        self.line_height_float = self.ascent_f - self.descent_f
        # 引擎行高 = FreeType `metrics.height` = (hhea.asc − hhea.desc + hhea.lineGap)
        # × fs/upem（Unity TextMesh 的 line height / renderer bounds 语义）。
        # 抓帧实证（2026-10-18 第五轮）：Belwe 45 (upem 1024, asc 900, desc −124, gap 6)
        # → 45.26367 字体 px；104524 race 的 TextMesh.characterSize 反解 = 1.073077
        # = 0.17/0.158423（0.158423 = 45.26367×0.0035），121058 两行 baseline 间距
        # = 38.474 字体 px = 45.26367×0.85 逐位吻合。见 `_LINE_GAP_ROLES`。
        self.line_gap_float = hhea.lineGap * self.size / upem
        self.line_height_gap_float = self.line_height_float + self.line_gap_float
        self.ascent_round = int(round(self.ascent_f))
        self.descent_round = int(round(self.descent_f))
        self._face = _ft.get_face(self._face_path, self.size)   # 进程 memo，勿 close
        self._cache: dict[tuple[str, int], tuple[CharInfo, np.ndarray]] = {}

    def char_info(self, ch: str, shear_xy: int = 0) -> tuple[CharInfo, np.ndarray]:
        """单字 → (CharInfo, uint8 位图 (rows,width) top-down)。

        `shear_xy`：0=正体；0x4000=引擎斜体合成斜切（`<i>`，见 text_atlas.glyph_quad）。
        斜切不改 x advance（xy 只乘 y 分量），但会改 bearings/位图，故缓存键含 shear。
        位图是**未补边**的紧墨位图、minX/maxX 是**墨迹** bearings（text_atlas 再加资产
        pad p 得引擎格框 vert）；**排版量宽不吃这里**——wrap/resize 用量宽盒
        `measure_box`（见其文档串，两者口径不同，禁止互替）。"""
        key = (ch, int(shear_xy))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        if ch == _NBSP:
            # `_` 的 wrap 后替身：必须给**空格 advance**（引擎 TextMesh 按字体 NBSP 字形
            # 量宽，zhCN 三字体 cmap 的 U+00A0 advance 均 = ' '），且不画字形（NBSP 无
            # 轮廓）。字体 cmap 缺 U+00A0 时显式回退 ' ' 的 advance（不落 0，否则行宽/
            # 居中偏窄）；不走缺字回退（NBSP 不是「缺字」，不该记回退事件）。
            if self._face.has_glyph(_NBSP):
                advance = _ft.advance_to_px(self._face.advance_26_6(_NBSP))
            else:
                advance = self.advance(" ")
            info = CharInfo(advance, 0, 0, 0, 0)
            arr = np.zeros((0, 0), dtype=np.uint8)
            self._cache[key] = (info, arr)
            return info, arr
        if ch == _SOFT_HYPHEN or ch == _WORD_BREAK:
            # `[d]`/`[b]` 占位符：零宽、零掩码（从不进入最终行文本；测量期也不会被画）。
            info = CharInfo(0, 0, 0, 0, 0)
            arr = np.zeros((0, 0), dtype=np.uint8)
            self._cache[key] = (info, arr)
            return info, arr
        if not self._face.has_glyph(ch):
            return self._fallback_char_info(ch, int(shear_xy))
        g = self._face.glyph(ch, int(shear_xy))
        info = CharInfo(g.advance_px, g.left, g.left + g.width,
                        g.top - g.rows, g.top)
        self._cache[key] = (info, g.bitmap)
        return info, g.bitmap

    def _fallback_char_info(self, ch: str,
                            shear_xy: int = 0) -> tuple[CharInfo, np.ndarray]:
        """缺字兜底字形（v3.1）：引擎两级查找的命中 face 的 unhinted 位图 + 该 face 的
        FT advance（`(x+32)>>6`）；全失败 → 零宽 + 零掩码 + 响亮事件。

        advance 口径：取**回退字体自身** FT advance 取整（findings §4 未决项的现选支：
        现有 oracle 样本 㐀/㐇/䲨/嗞/砮/鳛 全 CJK 全角，与「强制全宽=em」同值；
        非全宽缺字样本（€/ß）待 dump 判别，事件里如实记 `advance_px`）。
        字形与 advance 单源本缓存——layout（wrap/居中）与栅格化同判（判据「layout 期
        一次定案、栅格化期同判」）。"""
        from eidolon.core.render.text import glyph_supply as _gs
        face, ev = _gs.resolve_fallback(ch, self.size, font_object=self.font_name)
        reason = "cmap-miss-fallback" if face is not None else "cmap-miss-both"
        _gs.record_missing(self.font_name, self.size, ch, reason,
                           str(ev.get("source") or "?"),
                           **{k: v for k, v in ev.items() if k != "source"})
        if face is None:
            info = CharInfo(0, 0, 0, 0, 0)
            arr = np.zeros((0, 0), dtype=np.uint8)
        else:
            rch = ev.get("resolved_ch") or ch
            g = face.glyph(rch, int(shear_xy))
            info = CharInfo(g.advance_px, g.left, g.left + g.width,
                            g.top - g.rows, g.top)
            arr = g.bitmap
        self._cache[(ch, int(shear_xy))] = (info, arr)
        return info, arr

    def has_glyph(self, ch: str) -> bool:
        """显式 cmap 成员判定（判据前置判定；布局/供给分路读）。"""
        return bool(self._face.has_glyph(ch))

    def measure_box(self, ch: str) -> tuple[int, int]:
        """排版量宽盒 `(minX, maxX)`（= UB Wrap 的 TextMesh bounds 口径，**正体**口径）。

        定义：`advance 盒 ∪ 墨盒` = `(min(0, bitmap_left), max(advance, left+width))`。
        为什么不是裸墨盒：wrap/resizeToFit 的判据是 TextMesh bounds 实测口径，v3 前以
        PIL 全宽掩码标定（= advance 盒 ∪ 墨迹溢出；`maxX=max(advance,left+width)`——
        非斜体也会右溢，GLEI45 实测 12/515 字，不是只有斜体）。v3.1 换栅格驱动后
        **显式化**此式以保 wrap/resize
        判据逐位不变——裸墨盒会改行宽（97532 实证：desc 末行墨盒 39 vs advance 40 使
        resizeToFit 少走一步 0.95 收缩，整段换行位移，z_desc 0.85→19.3）。
        恒定取正体度量（斜体行仍按正体量宽，与 v3 前一致）。"""
        info = self.char_info(ch)[0]
        return min(0, info.minX), max(info.advance, info.maxX)

    def advance(self, ch: str) -> int:
        return self.char_info(ch)[0].advance

@parallel

def make_font_metrics(fontdef: dict, font_size: int) -> FontMetrics:
    """字体度量：make_font_metrics 对位（old_frames/uber_text.py:793）——FreeType
    FontMetrics（零资产依赖，TTF 字节经 fontdef["_ttf"]=font_service.get_font_def
    供给面）。返回 FontMetrics（字形掩码缓存/char_info 是渲染执行半 S11 消费前提；
    font_name=缺字事件账的字体标签）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    return FontMetrics(fontdef["_ttf"], int(font_size),
                       font_name=str(fontdef.get("_font_object_name", "")))


# ---------------------------------------------------------------------------
# 对齐（SetupTextMeshAlignment 离线形；数字角色相位账=本模块 _numeric_phase_y 闭算）
# ---------------------------------------------------------------------------

# SetupTextMeshAlignment switch 表（UberText.cs:UberText.SetupTextMeshAlignment 逐臂）：
# (AlignmentOptions, AnchorOptions) → (GetAlignmentOffset 入参比例 (fx, fy), TextAnchor)。
# AlignmentOptions：Left=0/Center=1/Right=2（UberText.cs:UberText.AlignmentOptions）；AnchorOptions：
# Upper=0/Middle=1/Lower=2（:58-63）。Center/Middle 臂不调 GetAlignmentOffset（None=
# 恒零偏移）——锚定语义落 TextMesh 原生垂直锚（SetTextAnchor→TextMesh.anchor），
# 数字角色亚像素相位由此闭算（_numeric_phase_y，2026-11-01 cost-phase-closure；
# 旧「明标未闭」账随之关闭，gems.COST_PHASE 降级为验算账）。
_TEXT_ANCHOR_TABLE: dict[tuple[int, int], tuple[tuple[float, float] | None, str]] = {
    (1, 0): ((0.0, 0.5), "UpperCenter"),
    (1, 1): (None, "MiddleCenter"),
    (1, 2): ((0.0, -0.5), "LowerCenter"),
    (0, 0): ((-0.5, 0.5), "UpperLeft"),
    (0, 1): ((-0.5, 0.0), "MiddleLeft"),
    (0, 2): ((-0.5, -0.5), "LowerLeft"),
    (2, 0): ((0.5, 0.5), "UpperRight"),
    (2, 1): ((0.5, 0.0), "MiddleRight"),
    (2, 2): ((0.5, -0.5), "LowerRight"),
}


def _get_width(ns: NodeSettings) -> float:
    """GetWidth 离线形（UberText.cs:UberText.GetWidth）：m_Width；locale 条目 m_Width>0 覆写。
    widget 支（IsPartOfWidget→m_widgetTransform.Rect.width）=运行时组件态不接线。"""
    width = float(ns.f("m_Width"))
    loc_adj = locale_adjustment(ns.text_fields)
    if loc_adj and float(loc_adj.get("m_Width") or 0.0) > 0.0:
        width = float(loc_adj["m_Width"])
    return width


def _get_height(ns: NodeSettings) -> float:
    """GetHeight 离线形（UberText.cs:UberText.GetWidth 起，GetWidth 镜像：locale m_Height>0 覆写）。"""
    height = float(ns.f("m_Height"))
    loc_adj = locale_adjustment(ns.text_fields)
    if loc_adj and float(loc_adj.get("m_Height") or 0.0) > 0.0:
        height = float(loc_adj["m_Height"])
    return height

@parallel

def set_alignment(ns: NodeSettings, align: tuple[int, int],
                  *, is_part_of_widget: bool = False) -> dict:
    """锚定：SetupTextMeshAlignment 对位（UberText.cs:UberText.SetupTextMeshAlignment + GetAlignmentOffset
    :1979-1985）。align=(m_Alignment, m_Anchor) 序列化枚举值（0=Left/1=Center/2=Right
    × 0=Upper/1=Middle/2=Lower）。返回锚定参数 dict：
      offset=GetAlignmentOffset 产物 (dx,dy,dz)——widget 轴离线恒 False→(dx,dy,0)，
        is_part_of_widget=True→(dx,0,dy) 轴交换（:1981-1985 闭式，纯函数面保留）；
      text_anchor=switch 臂的 TextAnchor（Unity TextAnchor 名）；
      position_offset=UberTextLocalization.GetPositionOffset（:1936-1937 链——
        m_LocalizedSettings zhCN 条目 m_PositionOffset，heropower desc (0,−0.05,0) 实测锚）。
    数字角色相位账（闭算读值 _numeric_phase_y 唯一路由；延旧守卫 2026-11-02
    ability-premium-phase 清零，验算账=同名任务实验档）不在本函数返回面——
    消费位=text_layer_plan。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    alignment, anchor = int(align[0]), int(align[1])
    key = (alignment, anchor)
    assert key in _TEXT_ANCHOR_TABLE, (
        f"未知 (m_Alignment, m_Anchor) {key!r}——_TEXT_ANCHOR_TABLE 九臂外"
        f"（开放位={sorted(_TEXT_ANCHOR_TABLE)}）")
    ratio, text_anchor = _TEXT_ANCHOR_TABLE[key]
    if ratio is None:   # Center/Middle 臂：引擎不调 GetAlignmentOffset（恒零偏移）
        offset = (0.0, 0.0, 0.0)
    else:
        dx, dy = ratio[0] * _get_width(ns), ratio[1] * _get_height(ns)
        offset = (dx, 0.0, dy) if is_part_of_widget else (dx, dy, 0.0)
    po = locale_adjustment(ns.text_fields).get("m_PositionOffset") or {}
    position_offset = (float(po.get("x", 0.0)), float(po.get("y", 0.0)),
                       float(po.get("z", 0.0)))
    return {"alignment": alignment, "anchor": anchor, "offset": offset,
            "text_anchor": text_anchor, "position_offset": position_offset}


# ---------------------------------------------------------------------------
# 帧文字节点装载（七份 load_node_settings* 副本收敛：统一装载器+帧差异表）
# ---------------------------------------------------------------------------

def _walk(recon: dict):
    """yield (path, key, node)——key 为 mesh_data.npz 的数组键（旧 :161-170 逐字）。"""

    def rec(node, key="root", path=""):
        p = f"{path}/{node['name']}" if path else node["name"]
        yield p, key, node
        for i, c in enumerate(node["children"]):
            yield from rec(c, f"{key}.{i}", p)

    yield from rec(recon["hierarchy"], "root", "")


_FONT_PPTR_TO_DEF = {  # FontTable 链映射（ability 帧 dump 的 m_Font PPtr→FontDef 名，prefab 已验证）
    "4766376857981636630": "Belwe_Outline",
    "-3530185850595028133": "FranklinGothic",
}
_ROLE_PATHS_ABILITY = {  # 四区映射（spec §0.5；ability 帧=Actor m_*TextMesh 绑定按节点名落位）
    "cost": "RootObject/NonQuestObjects/CostObject/CostUberText",
    "name": "RootObject/NonQuestObjects/Mesh/NameBanner_mesh/NameUberText",
    "desc": "RootObject/NonQuestObjects/Mesh/Description_mesh/PowersUberText",
    "plate": "RootObject/NonQuestObjects/Mesh/Description_mesh/RaceUberText",
}
_ROLE_PATHS_ABILITY_PREMIUM = {  # 金法术（capture-determinism 2026-10-30）：premium prefab
    # 无 NonQuestObjects 层（ubertext dump 实证：CostObject/Mesh 直挂 RootObject，
    # 且无 quest/trinket 托盘）——四区同构、层级少一层
    "cost": "RootObject/CostObject/CostUberText",
    "name": "RootObject/Mesh/NameBanner_mesh/NameUberText",
    "desc": "RootObject/Mesh/Description_mesh/PowersUberText",
    "plate": "RootObject/Mesh/Description_mesh/RaceUberText",
}
_ROLE_PATHS_ALLY = {  # Actor 绑定 m_attackTextMesh/m_healthTextMesh/m_raceTextMesh 按 dump 落位；
    # race_multi=m_multiRaceTextMesh（Actor.cs:Actor）——多种族时引擎把同一文本写宽板自己的
    # UberText（UpdateRace Actor.cs:Actor.UpdateRace），字体/排版随该节点序列化值
    "cost": "RootObject/CostObject/CostUberText",
    "name": "RootObject/Mesh/NameBanner_mesh/NameUberText",
    "desc": "RootObject/Mesh/Description_mesh/PowersUberText",
    "race": "RootObject/RacePlate_mesh/RaceUberText",
    "race_multi": "RootObject/Multi_RacePlate_mesh/Multi_RaceUberText",
    "attack": "RootObject/AttackObject/AttackUberText",
    "health": "RootObject/HealthObject/HealthUberText",
}
_ROLE_PATHS_WEAPON = {  # Actor 绑定按 dump 落位；durability=HealthUberText 新角色
    "cost": "RootObject/CostObject/CostUberText",
    "name": "RootObject/Mesh/NameBanner_mesh/NameUberText",
    "desc": "RootObject/Mesh/Description_mesh/PowersUberText",
    "attack": "RootObject/Wep_Swords/AttackUberText",
    "durability": "RootObject/Wep_SheildBroken/HealthUberText",
}
_ROLE_PATHS_HERO_HAND = {
    "cost": "RootObject/CostObject/CostUberText",
    "name": "RootObject/Mesh/NameBanner_mesh/NameUberText",
    "desc": "RootObject/Mesh/Description_mesh/PowersUberText",
    "attack": "RootObject/AttackObject/AttackUberText",
    "armor": "RootObject/ArmorObject/ArmorUberText",
}
_ROLE_PATHS_HERO_PLAY = {
    "attack": "RootObject/DecorationRoot/AttackObject/AttackUberText",
    "health": "RootObject/DecorationRoot/HealthObject/HealthUberText",
}
_ROLE_PATHS_HEROPOWER = {  # 三节点直挂 RootObject（prefab dump 实测）
    "cost": "RootObject/CostUberText",
    "name": "RootObject/NameUberText",
    "desc": "RootObject/PowersUberText",
}
_ROLE_PATHS_LOCATION = {  # m_healthTextMesh→Wep_SheildBroken/HealthUberText；
    # 无 m_attackTextMesh 绑定 → 无 attack 角色
    "cost": "RootObject/CostObject/CostUberText",
    "name": "RootObject/Mesh/NameBanner_mesh/NameUberText",
    "desc": "RootObject/Mesh/Description_mesh/PowersUberText",
    "durability": "RootObject/Wep_SheildBroken/HealthUberText",
}
_ROLE_PATHS_TRINKET = {  # ct44 饰品帧（2026-10-24；probe 实测活性子树落位——
    # 文字区定案=feature-corpus TRINKET_MASK 四矩形：硬币费用数字/名牌/desc/族学牌。
    # 名/desc 走 NonQuestObjects/Mesh 活性子树；"Mesh Old (From Card_Hand_Ability)"
    # 复制子树（含 NameBanner_mesh/Description_mesh）全序列化失活不落位；
    # Quest 文字盘（Card_Hand_BG_Quest_Text_Tray_Mesh 内 3 节点）序列化失活不落位。
    "cost": "RootObject/NonQuestObjects/CostObject/CostUberText",
    "name": "RootObject/NonQuestObjects/Mesh/NameUberText",
    "desc": "RootObject/NonQuestObjects/Mesh/PowersUberText",
    "race": "RootObject/NonQuestObjects/RacePlate_mesh/RaceUberText",
    "race_multi": "RootObject/NonQuestObjects/Multi_RacePlate_mesh/Multi_RaceUberText",
}
_ROLE_PATHS_ANOMALY = {  # ct43 畸变帧（bg-ct40-43-44-routing 2026-10-24；probe 实测
    # 落位=ability 帧同路径——NonQuestObjects/Mesh 活性子树 NameBanner/Description；
    # Quest 文字盘（Card_Hand_BG_Quest_Text_Tray_Mesh 内 RaceUberText/PowersUberText/
    # Quest_Text）序列化失活不落位；cost 节点在 CostObject 失活子树内（映射保留供
    # 角色装载，plan 恒 render=False——引擎 CostObject 序列化失活=展示态，费用无数字位）。
    "cost": "RootObject/NonQuestObjects/CostObject/CostUberText",
    "name": "RootObject/NonQuestObjects/Mesh/NameBanner_mesh/NameUberText",
    "desc": "RootObject/NonQuestObjects/Mesh/Description_mesh/PowersUberText",
    "plate": "RootObject/NonQuestObjects/Mesh/Description_mesh/RaceUberText",
}

_UNDERWEAR_NOTE = ("underwear Flip={flip} uw={uw} uh={uh} 字段透传 → uber_text.wrap_lines 转写"
                   "（UB Wrap:3612-3747 / GetUnderwearBounds:4109-4128 / GetFinalContainerWidth:4171-4186；"
                   "2026-10-06 desc-wrap-width 勘误旧置 0 规则）")

# 帧差异表（旧七份 load_node_settings* 的参数化收敛——FRAME_DESC 行平行表，批15/16/17
# 选型账同形，本模块自带；开放位=八帧键（hero_play_bacon 不在：其 plan texts 恒
# render=False，旧 render_text_layer 调用位 any(render) 守卫 old_frames/render_card.py:456
# 使装载器不被触达——执行半 S11），未知键 assert 响亮）：
#   root=世界矩阵查找前缀 / scale=lossyScale 取法（mean3=三列范数均值〔非均匀帧把面内轴
#   稀释 16-19%〕、face2=面内两轴〔weapon/location 修正，42700 desc/76981 durability 实测〕）/ font=FontDef 名
#   来源（pptr=ability PPtr 表〔交叉校验位〕、name=dump 的 Font 对象名——FontTable 链
#   m_FontName→m_FontDefName 恒等映射）/ rtt_null=m_RenderToTexture=1 且 m_RenderOnObject=
#   NULL 的帧内处置（keep=保留走 SetupRenderOnPlane 平面 fallback〔UberText.cs:UberText.SetupRenderOnPlane，执行半
#   S11；heropower name 亦走此支——prefab dump NameUberText RTT=1/ROO=NULL〕、zero=置 0 等价居中直渲
#   〔hero 两帧旧面处置〕）/
#   posoff=逐 locale m_PositionOffset 世界平移注入（UberText.cs:UberText.SetupTextMeshAlignment，heropower zhCN 实测）/
#   curved=名称 RTT 载体网格名（None=无弧面）。
_TEXT_SETUP: dict[str, dict] = {
    "Card_Hand_Ability": dict(root="Card_Hand_Ability", roles=_ROLE_PATHS_ABILITY, scale="mean3",
                  font="pptr", rtt_null="keep", posoff=False,
                  curved="AbilityCardCurvedText"),
    # 金法术档（capture-determinism 2026-10-30）：premium prefab 层级少 NonQuestObjects
    # 一层（ubertext dump 实证），roles=_ROLE_PATHS_ABILITY_PREMIUM；curved 同名资产假设
    # 2026-11-04：desc/plate 节点世界矩阵非均匀（desc cols=[0.8,0.8,0.67866]、
    # plate=[1.0608,1.0608,0.8999]，TextMesh local X/Y=文字平面、Z=面法向不参与排版），
    # mean3 把面内稀释 5.06%/5.05%（location durability 同族）→ 该两角色走 face2
    # （cost/name 节点均匀，mean3==face2 恒等不在列）。
    "Card_Hand_Ability_Premium": dict(root="Card_Hand_Ability_Premium", roles=_ROLE_PATHS_ABILITY_PREMIUM,
                           scale="mean3", font="pptr", rtt_null="keep", posoff=False,
                           scale_face2_roles=("desc", "plate"),
                           curved="AbilityCardCurvedText"),
    "Card_Hand_Ally": dict(root="Card_Hand_Ally", roles=_ROLE_PATHS_ALLY, scale="mean3",
                 font="name", rtt_null="keep", posoff=False,
                 curved="CardAllyCurvedText"),
    # 金卡档（mechorse-golden 2026-10-21）：premium prefab ubertext 节点相对路径与
    # ally 全同构（prefab_ubertext_ally_premium dump 实证：cost/name/desc/race/
    # race_multi/attack/health 七角色同位），curved 载体=同名网格资产
    "Card_Hand_Ally_Premium": dict(root="Card_Hand_Ally_Premium", roles=_ROLE_PATHS_ALLY, scale="mean3",
                         font="name", rtt_null="keep", posoff=False,
                         curved="CardAllyCurvedText"),
    "Card_Hand_Weapon": dict(root="Card_Hand_Weapon", roles=_ROLE_PATHS_WEAPON, scale="face2",
                   font="name", rtt_null="keep", posoff=False, curved=None),
    "Card_Hand_Hero": dict(root="Card_Hand_Hero", roles=_ROLE_PATHS_HERO_HAND, scale="mean3",
                      font="name", rtt_null="zero", posoff=False,
                      curved="HeroCard_InHand_BendTextShape"),
    "Card_Play_Hero": dict(root="Card_Play_Hero", roles=_ROLE_PATHS_HERO_PLAY, scale="mean3",
                      font="name", rtt_null="zero", posoff=False, curved=None),
    "History_HeroPower": dict(root="History_HeroPower", roles=_ROLE_PATHS_HEROPOWER, scale="mean3",
                      font="name", rtt_null="keep", posoff=True, curved=None),
    "Card_Hand_Location": dict(root="Card_Hand_Location", roles=_ROLE_PATHS_LOCATION, scale="mean3",
                     scale_face2_roles=("durability",),
                     font="name", rtt_null="keep", posoff=False,
                     curved="UberText_Location_InHand_Premium_Mesh"),
    # ct44 饰品帧（bg-ct40-43-44-routing 2026-10-24）：probe 实测 13 UberText 全
    # m_RenderToTexture=NULL（无 RTT/无弧面），字体走 dump font_name（Belwe_Outline/
    # FranklinGothic——cost/name/race=Belwe、desc=FranklinGothic）。
    # race/race_multi 面内轴覆写（133060 轮）：两族板 UberText 世界矩阵列
    # [0.9277,0.9277,0.5797] 非均匀——mean3=0.8117 把字形稀释 12.5%（对拍实证：
    # 「恶魔」宽 70px vs ref 80px，比值 0.875=mean3/face2 逐位吻合）；local Z=面法向
    # 不参与排版（location durability 2026-10-18 同款），cost/name/desc 节点均匀
    # （[1,1,1]/[0.8,0.8,0.8]）两法同值零影响。
    "Card_Hand_BG_Trinket": dict(root="Card_Hand_BG_Trinket", roles=_ROLE_PATHS_TRINKET, scale="mean3",
                    scale_face2_roles=("race", "race_multi"),
                    font="name", rtt_null="keep", posoff=False, curved=None),
    # ct43 畸变帧（bg-ct40-43-44-routing 2026-10-24）：probe 实测活性 UberText=
    # name（RTT=1/ROO=null）/desc/race 三节点 + 失活 cost；字体=Belwe_Outline
    # （name/race/cost）/FranklinGothic（desc），走 dump font_name（trinket 同款）。
    # 文字节点世界矩阵全均匀（probe 实测 name=[1,1,1]/desc=[0.8³]/race=[1.0608³]
    # ——mean3 稀释坑预查过，无需 scale_face2_roles）；Quest 盘 Quest_Text 节点
    # [0.6085,0.6085,0.5311] 非均匀但在序列化失活子树内永不渲。
    # curved="AbilityCardCurvedText"：name RTT 载体网格资产名与 ability 帧同
    # （GO 名 Card_InHand_Ally_CurvedText，mesh 资产名 AbilityCardCurvedText，
    # probe 实测——spell 链同资产同法）。
    "Card_Hand_BG_Anomaly": dict(root="Card_Hand_BG_Anomaly", roles=_ROLE_PATHS_ANOMALY, scale="mean3",
                    font="name", rtt_null="keep", posoff=False,
                    curved="AbilityCardCurvedText"),
}

_WEAPON_RTT_NOTE = ("RTT=1 且 m_RenderOnObject=NULL（dump）→ SetupRenderOnPlane "
                    "平面 fallback（UberText.cs:UberText.SetupRenderOnPlane）：m_Resolution RT 中转 + 贴屏双线性，"
                    "_render_rtt_plane 引擎链复刻")
_HERO_RTT_NOTE = ("RTT=1 但 m_RenderOnObject=NULL → UB SetupRenderOnPlane 平面 fallback"
                  "（UberText.cs:UberText.SetupRenderOnPlane）")
_HP_RTT_NOTE = ("RTT=1 但 m_RenderOnObject=NULL（prefab dump NameUberText）→ "
                "UberText.SetupRenderToTexture 走 SetupRenderOnPlane 平面 fallback"
                "（UberText.cs:UberText.SetupRenderToTexture / UberText.SetupRenderOnPlane："
                "CreateMesh 4 顶点 ±size/2 + DoPlaneRotate(−90°X)，"
                "UberTextRenderToTexture.cs:UberTextRenderToTexture.CreateMesh）→ "
                "_render_rtt_plane 引擎链复刻（m_Resolution RT 中转 + 贴屏双线性）")

@parallel

def load_curved_mesh(recon: dict, arrays, name: str) -> dict:
    """名称 RTT 载体网格 + 世界矩阵（旧 load_curved_mesh_mem :206-228 统一形：
    载体按 mesh_stats.name 查找；arrays=frames.scene_for(key)["arrays"]，键同 npz）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    key = path = None
    for p, k, n in _walk(recon):
        ms = n.get("mesh_stats")
        if ms and ms["name"] == name:
            key, path = k, p
    assert key, f"CurvedText mesh 节点未找到（{name}）"
    verts = arrays[f"{key}/verts"]
    uv0 = arrays[f"{key}/uv0"]
    tris = arrays[f"{key}/sub0"]
    world = np.array(next(n["world"] for p, _, n in _walk(recon) if p == path), dtype=float)
    return {"verts": verts, "uv0": uv0, "tris": tris, "world": world}

@invented(reason="帧文字节点装载表化（七份 load_node_settings 副本收敛；字段=prefab 序列化直读）", counterpart="UberText.SetFont/SetText 节点装载面")

def text_setup_for(key: str) -> tuple[dict[str, NodeSettings], dict | None]:
    """帧文字节点装载（old_frames/render_card.py:221-241 text_setup_for 对位——七份
    load_node_settings* 副本收敛为统一装载器+_TEXT_SETUP 帧差异表）。

    返回 ({role: NodeSettings}, curved_mesh|None)。notes 账面（_underwear_notes/
    _rtt_notes/_posoff_notes/_notes）随各帧旧面键位原样透传（记载=元数据非行为）。
    供给消费：frames.scene_for(key) 触 recipes.frames kit 族 @item——须在
    supply session 内（头注纪律）。

    我方机制：游戏侧无装载器/表方法（只有 UberText.SetFont/SetText 的组件写点），
    本件是七份旧副本的收口表，故 invented（见装饰器 reason/counterpart）。

    族账锚=UberText.cs（模块族账；本件发明——装载表化，reason/counterpart 见装饰器）。
    """
    spec = _TEXT_SETUP.get(key)   # consumer-v2：表键=prefab（穿线已翻转）
    assert spec is not None, (
        f"未知帧键 {key!r}——_TEXT_SETUP 无此键（开放位={sorted(_TEXT_SETUP)}）")
    scene = _frames.scene_for(key)
    data, recon, arrays = scene["ubertext"], scene["meta"], scene["arrays"]
    world_by_path = {p: np.array(n["world"], dtype=float)
                     for p, _, n in _walk(recon) if n.get("world") is not None}
    out: dict[str, NodeSettings] = {}
    rtt_notes: dict[str, str] = {}
    underwear_notes: dict[str, str] = {}
    posoff_notes: dict[str, str] = {}
    for role, suffix in spec["roles"].items():
        node = next(n for n in data["nodes"] if n["path"].endswith(suffix))
        w = world_by_path[f"{spec['root']}/{suffix}"]
        # 文字缩放取法：spec["scale"]="face2"（整帧面内轴）或 role 在
        # spec["scale_face2_roles"] 内（逐角色面内轴覆写）。
        # 2026-10-02 font-pipeline 修正：TextMesh local X/Y 是文字平面，local Z 是面法向
        # 不参与排版（weapon 非均匀节点旧 mean3 稀释 16-19% 实证；均匀节点两法同值）。
        # 2026-10-18：location durability 节点 cols=[1.16,1.16,0.7685]，mean3=1.0295 把
        # 字形缩小 11%（α 比 0.79）→ 该角色改用面内轴 1.16；同帧 name/desc 保持旧
        # 取法不动（name RTT 本轮不在射程、且整帧切 face2 会动 rarity_gem 分区基线）。
        if spec["scale"] == "face2" or role in spec.get("scale_face2_roles", ()):
            vx, vy = w[:3, 0], w[:3, 1]
            sx = float(np.hypot(vx[0], vx[2]))
            sy = float(np.hypot(vy[0], vy[2]))
            scale = (sx + sy) / 2.0
        else:
            cols = np.linalg.norm(w[:3, :3], axis=0)
            scale = float(cols.mean())
        # 面内旋转：世界矩阵 x-z 面内 local X 轴的屏幕角。TextMesh 的 quad 随节点矩阵
        # 旋转（129851 抓帧 ev373 cb1 = [1.158966,−0.023277; +0.023277,1.158966]，即
        # ally attack 节点 +1.151°；cost/health/durability 均为 0）。图集路径按此
        # 逆向旋转采样坐标（text_atlas._rot_coords）。
        rot_deg = float(np.degrees(np.arctan2(-w[2, 0], w[0, 0])))
        if abs(rot_deg) < 1e-3:
            rot_deg = 0.0      # 浮点噪声（cos≈1 的微小非正交分量）不构成旋转
        if spec["font"] == "pptr":
            fontdef_name = _FONT_PPTR_TO_DEF[f"{node['fields']['m_Font']['m_PathID']}"]
        else:
            fontdef_name = node.get("font_name")
            assert fontdef_name, f"{role}: m_Font 未解析（recon dump 缺 font_name）"
        fields = dict(node["fields"])
        wpos = (float(w[0, 3]), float(w[1, 3]), float(w[2, 3]))
        if spec["posoff"]:
            # 逐 locale 位置偏移（serialized 出处）：UberText.cs:UberText.SetupTextMeshAlignment
            # SetTextMeshGameObjectLocalPositionOffset(GetAlignmentOffset(...))
            # + UberTextLocalization.GetPositionOffset(m_LocalizedSettings)；
            # node-local 平移 → world：M 线性部分（NodeSettings.world_pos 只吃世界平移）。
            adj = locale_adjustment(fields)
            po = adj.get("m_PositionOffset") or {}
            off_local = np.array([po.get("x", 0.0), po.get("y", 0.0), po.get("z", 0.0)])
            off_world = w[:3, :3] @ off_local
            if off_local.any():
                posoff_notes[role] = (
                    f"zhCN m_PositionOffset={off_local.tolist()}（m_LocalizedSettings dump）→ world "
                    f"Δ=({off_world[0]:+.4f},{off_world[1]:+.4f},{off_world[2]:+.4f})"
                    "（UberText.cs:UberText.SetupTextMeshAlignment GetPositionOffset 链）")
            wpos = (float(w[0, 3]) + float(off_world[0]),
                    float(w[1, 3]) + float(off_world[1]),
                    float(w[2, 3]) + float(off_world[2]))
        if fields.get("m_RenderToTexture") and not fields.get("m_RenderOnObject", {}).get("m_PathID"):
            if spec["rtt_null"] == "zero":
                fields["m_RenderToTexture"] = 0
                rtt_notes[role] = (_HERO_RTT_NOTE if key in ("Card_Hand_Hero", "Card_Play_Hero")
                                   else _HP_RTT_NOTE)
            else:
                rtt_notes[role] = (_HP_RTT_NOTE if key == "History_HeroPower"
                                   else _WEAPON_RTT_NOTE)
        if fields.get("m_Underwear"):
            underwear_notes[role] = _UNDERWEAR_NOTE.format(
                flip=fields.get("m_UnderwearFlip"), uw=fields.get("m_UnderwearWidth"),
                uh=fields.get("m_UnderwearHeight"))
        out[role] = NodeSettings(
            text_fields=fields,
            world_pos=wpos,
            local_scale=scale,
            fontdef_name=fontdef_name,
            rot_deg=rot_deg,
            world_cols=tuple(float(x) for x in np.linalg.norm(w[:3, :3], axis=0)),
        )
    if key == "Card_Hand_Weapon":
        out["_rtt_notes"] = rtt_notes          # type: ignore[assignment]
        out["_underwear_notes"] = underwear_notes  # type: ignore[assignment]
    elif key == "History_HeroPower":
        out["_rtt_notes"] = rtt_notes          # type: ignore[assignment]
        out["_underwear_notes"] = underwear_notes  # type: ignore[assignment]
        out["_posoff_notes"] = posoff_notes    # type: ignore[assignment]
    elif key in ("Card_Hand_Hero", "Card_Play_Hero"):
        out["_notes"] = {**rtt_notes, **underwear_notes}  # type: ignore[assignment]
    elif key == "Card_Hand_Ally" or key == "Card_Hand_Location":
        out["_underwear_notes"] = underwear_notes  # type: ignore[assignment]
    curved = load_curved_mesh(recon, arrays, spec["curved"]) if spec["curved"] else None
    return out, curved


# ---------------------------------------------------------------------------
# 文字层 plan 键构（render_text_layer 的消费/装载/参数半；执行半 S11）
# ---------------------------------------------------------------------------

def _cost_alt_node_settings(ns: NodeSettings, meta: dict, alt: dict) -> NodeSettings:
    """cost 节点世界平移覆写（bg-cost-anchor 2026-10-08）：引擎 UpdateManaGemOffset
    （Actor.cs:Actor.UpdateManaGemOffset）把 cost 文本 localPosition 强制为 m_alternateCostTextLocalPos；
    离线等价 = 以父节点 world 矩阵变换 alt["local"] 得新世界平移（父旋转/缩放携带——
    R·t+父平移；节点自身旋转/缩放不改，本管线只消费平移与 lossyScale，语义精确）。
    父路径按后缀匹配（spell/spell_dk 同为 Card_Hand_Ability/…/CostObject）。

    帧族路径差回退（timewarped-cost-base 2026-10-31）：手牌 Ally/Weapon/Hero/Location 帧的
    父节点是 `RootObject/CostObject`（无 NonQuestObjects 中间段），只有 Ability 系帧带
    `NonQuestObjects/`（逐帧实测 SCENE_KEYS 全扫：每帧 CostObject 唯一，故裸名后缀回退
    无歧义）。引擎侧这个前缀只是 prefab 层级记账，位移语义=「该文本父节点」，故回退不改语义。

    位移取值面（golden-alt-cost-pos 2026-11-04）：引擎写的是**该 prefab Actor 序列化**的
    m_alternateCostTextLocalPos（Unity 反序列化覆盖 Actor.cs 字段默认值 −0.01/0.003/−0.58），
    逐 prefab 不同——Card_Hand_Ally=−0.01、Card_Hand_Ally_Premium=**+0.025**（金随从帧数字
    整字偏左 6.15px 的根因）。故帧数据（kit meta actor_alt_cost_pos）优先，alt["local"]
    （C# 字段默认）仅作缺字段回退。"""
    nodes_world = {p: np.array(n["world"], dtype=float)
                   for p, _, n in _walk(meta) if n.get("world") is not None}
    parent = next((w for p, w in nodes_world.items()
                   if p.endswith(alt["parent_suffix"])), None)
    if parent is None:
        parent = next((w for p, w in nodes_world.items()
                       if p.endswith("/CostObject")), None)
    assert parent is not None, f"cost 父节点缺失: {alt['parent_suffix']}"
    local = meta.get("actor_alt_cost_pos") or alt["local"]
    t = parent[:3, :3] @ np.asarray(local, dtype=float) + parent[:3, 3]
    return dataclasses.replace(ns, world_pos=(float(t[0]), float(t[1]), float(t[2])))

def _numeric_phase_y(text: str, ns: NodeSettings, fd: dict) -> float:
    """数字角色相位闭算读值（卡面 px，y；2026-11-01 cost-phase-closure）。

    引擎锚（decomp）：UberText.cs:UberText.SetupTextMeshAlignment 的 Center/Middle
    臂**不调 GetAlignmentOffset**（恒零 C# 偏移），亚像素来源在 TextMesh 原生垂直
    锚（UberTextRendering.SetTextAnchor→TextMesh.anchor）：单行 MiddleCenter=行盒
    （FreeType metrics.height=hhea asc−desc+lineGap 缩放）盒心对 pivot、基线=盒顶+
    浮点 ascent ⇒
      baseline_img = pivot + ((hhea.asc+hhea.desc−hhea.gap)/2)·fs/upem·K
    （Belwe_Outline 74：385×74/1024=27.822266 字体 px）。我方现链（text_atlas
    render_atlas_text 数字角色）= pivot + (asc_round−(asc_f−desc_f)/2)·K，故
      phase_y = [(asc_f−asc_round)−gap_f/2]·k·local_scale·s（Belwe 74 C=−0.177734 字体 px）。
    反解锚=d1 诊断：K=1.414 与 K=1.148875 两帧族组反解出**同一**字体 px 基线（=385
    单位）；逐实例验算 7 帧族 13 实例 + ally_premium 3 实例全部 ≤1/64px 判等
    （逐值验算=d2/d3 诊断 JSON，存本任务实验档 evidence/；gems.COST_PHASE 历史
    拟合值=本式 1/64 网格快照）。与 desc 路已验引擎模型同构（float_ascent+
    line_gap 盒、零相位——text-rendering-pipeline「desc 图集路径」：两件曾拆开
    各改一半致 lineGap A/B 伪阴性，见该档 §linegap-promotion）。k 单源=layout_text
    （与渲染同一 k 链）；m_ResizeToFit/单行前提断言（数字角色 fit=0，探针
    evidence/d3 json 全 fit=0/wrap=0/单行/Center-Middle）。
    """
    from eidolon.core.render.engine.raster import PX_PER_UNIT  # 函数内引（避环；Scene.s 同源常数）
    loc_adj = locale_adjustment(ns.text_fields)
    fs = int(fd["m_FontSizeModifier"] * loc_adj.get("m_FontSizeModifier", 1.0)
             * ns.f("m_FontSize"))
    fm = make_font_metrics(fd, fs)
    layout = layout_text(text, ns, fd, fm)
    assert not ns.f("m_ResizeToFit") and len(layout["lines"]) == 1, (
        "数字角色相位闭算前提破坏（m_ResizeToFit=0/单行）——节点序列化或字号链"
        "变更，重跑 cost-phase-closure 诊断（d1/d2/d3）再定相位来源")
    c = (fm.ascent_f - fm.ascent_round) - fm.line_gap_float / 2.0
    return c * layout["k"] * ns.local_scale * PX_PER_UNIT


@invented(reason="文字层 plan 键构/适配（plan['texts']→渲染 entry；plan 是我方 compile 期对象，游戏侧无 plan 键构）", counterpart="UberText.UpdateText/UpdateRenderQueue 文字更新面")

def text_layer_plan(key: str, plan: dict) -> dict:
    """文字层 plan 键构（old_frames/render_card.py:296-319 render_text_layer 的
    消费/装载/参数半）：plan["texts"] 逐 entry → {role, text, ns, fontdef, phase,
    curved_used}（render=True 条目按 plan 序）+ 节点面/载体网格。

    消费面=old 同构：cost 铸币位移旗（plan._cost_alt_pos，prep_plan 写入）覆写
    cost 节点世界平移；每文字节点 FontDef 解析=font_service.get_font_def（旧
    load_fontdef_mem 挂点）；数字角色相位=闭算读值 _numeric_phase_y（唯一路由；
    2026-11-02 cost-phase-untested 反转为缺省+延旧集守卫，同日
    ability-premium-phase 98918 锐扫 argmin=闭算值（δ=0 ≤1/64）后清零）；
    curved 载体仅 name 角色消费。渲染执行（render_text+alpha_composite）立户
    engine/S11——本函数产物即其入参面。

    我方机制：游戏侧无 plan 对象/键构函数（UberText.UpdateText/UpdateRenderQueue
    直接吃组件字段）；本件把 compile 期 plan 适配成渲染 entry，故 invented。

    族账锚=UberText.cs（模块族账；本件发明——plan 键构/适配，reason/counterpart 见装饰器）。
    """
    scene_meta = _frames.scene_for(key)["meta"]
    nodes_txt, curved = text_setup_for(key)
    alt = plan.get("_cost_alt_pos")
    entries = []
    for entry in plan["texts"]:
        if not entry.get("render"):
            continue
        role = entry["role"]
        ns = nodes_txt[role]
        if alt is not None and role == "cost":
            ns = _cost_alt_node_settings(ns, scene_meta, alt)
        fd = _font_service.get_font_def(ns.fontdef_name)
        # 图集数字角色亚像素相位=闭算读值（唯一路由；2026-11-02 cost-phase-untested
        # 反转为缺省：2026-11-01 cost-phase-closure 只对 gems.COST_PHASE 注册表键开
        # 闭算、未测键落零相位旧表路径，本轮取证未测键全部零数字墨——反转对其零行为，
        # 逐位对拍=cost-phase-untested 实验档 evidence/ab_*/manifest.json）。延旧集
        # （唯一成员 Card_Hand_Ability_Premium，golden 98918 活欠账）同日
        # ability-premium-phase 1/64 锐扫验证（argmin=闭算值 −0.251316，δ=0
        # ≤1/64；z_cost MAE 16.302→14.828；golden 门绿+blessed golden 重锚）后
        # 删除——残量三字段账=docs/notes/text-rendering-pipeline.md「数字角色
        # 相位」条与同名任务实验档。armor 与 health 同帧同字体同字号
        # 同描边（hero_hand m_armorTextMesh，Belwe_Outline 74px 9-tap），同族同式；
        # 非数字角色仍为零相位。
        phase = (0.0, 0.0)
        if role in ("cost", "attack", "health", "durability", "armor"):
            phase = (0.0, _numeric_phase_y(entry["text"], ns, fd))
        entries.append({"role": role, "text": entry["text"], "ns": ns,
                        "fontdef": fd, "phase": phase,
                        "curved_used": bool(curved is not None and role == "name")})
    return {"nodes": nodes_txt, "curved": curved, "entries": entries}


# ---------------------------------------------------------------------------
# 场景几何（Scene；old uber_text.py:146 逐字——正交投影上下文，S11 render_text_layer 消费形）
# ---------------------------------------------------------------------------

@dataclass
@invented(reason="正交投影参数包（我方离线相机层：s/wx0/wz1/ox/oy 自帧网格 bbox 映射到 canvas）；游戏侧投影由 Unity Camera 持有，无同名可转写方法", counterpart="SnapshotCamera 正交投影")
class Scene:
    """正交投影上下文（rc2_render.compute_fit 同式，锚点=帧网格世界 bbox；
    S11 组装段以 s=PX_PER_UNIT/wx0=-HALF_W/wz1=HALF_H/ox=oy=0 自然映射构造）。

    族账锚=UberText.cs（模块族账；本件发明——投影参数包，见装饰器 reason/counterpart）。
    """
    world_by_path: dict
    s: float
    wx0: float
    wz1: float
    ox: float
    oy: float
    canvas: tuple

    def project(self, wx: float, wz: float) -> tuple[float, float]:
        return (wx - self.wx0) * self.s + self.ox, (self.wz1 - wz) * self.s + self.oy


# ---------------------------------------------------------------------------
# 渲染执行（批22 兑现：描边/粗体双 pass 语义+RTT 曲面/平面；old :699-1089 面。
# v3：字形光栅半迁 text_atlas.glyph_quad 单入口，FreeType 超采样链/_dilate/_shift1/
# _resample/glyph_rgba/_composite 随静默回退链退役）
# ---------------------------------------------------------------------------

def _composite_masked(layer: np.ndarray, src: np.ndarray, inside: np.ndarray,
                      ymin: int, ymax: int, xmin: int, xmax: int) -> None:
    sub = layer[ymin:ymax + 1, xmin:xmax + 1]
    sa = src[..., 3:4]
    da = sub[..., 3:4]
    out_a = sa + da * (1 - sa)
    safe = np.where(out_a > 1e-6, out_a, 1.0)
    rgb = (src[..., :3] * sa + sub[..., :3] * da * (1 - sa)) / safe
    m3 = inside[..., None]
    sub[..., :3] = np.where(m3, rgb, sub[..., :3])
    sub[..., 3:4] = np.where(inside[..., None], out_a, da)


def _color(c: dict) -> tuple:
    return (c["r"], c["g"], c["b"], c.get("a", 1.0))


# ---------------------------------------------------------------------------
# 引擎图集文字路径（2026-10-18 A 段正典化；cost 临时桥泛化）
#
# 来源账：docs/notes/text-rendering-pipeline.md「引擎图集文字路径」（cost 图集 +
#   目标分辨率 9-tap + COST_PHASE → textonly 层 αMAE 0.028/255；attack/health/
#   durability 泛化 A/B 同文引用链）。
# 供给：data/fonts_zhcn/atlas/<fontObjectName>_<size>.{json,png}（FontDef 的
#   `_font_object_name` × 有效字号；语义与标定=eidolon/core/render/game/text_atlas.py）。
# 角色边界：
#   * 数字角色（cost/attack/health/durability，Belwe_Outline 74px）= 有描边 →
#     目标分辨率 9-tap；图集缺字/advance 不符 → 逐字回退 FreeType（cost 例外：
#     缺字/翻转字形整层回退，保持 2026-10-18 cost 桥的逐位行为）。**armor**（英雄手牌
#     RootObject/ArmorObject/ArmorUberText，同一 Belwe_Outline 74px 描边 2.5 节点）与本族
#     同路：Actor.cs:Actor.UpdateArmorTextMesh 只做 Convert.ToString(armor) + UpdateNumberText
#     （与 health 同一数字文本写入；显隐由 m_armorObject.SetActive 管），故字形路径必须与
#     health 同族，不走 FreeType `_dilate`。
#   * desc（FranklinGothic→BlizzardGlobal 40px，无描边）= 单次 center 双线性
#     （text_atlas 的 center 支路）+ **浮点基线 ascent_f**（引擎基线来自浮点
#     ascent；FT 的 ascent_round=39 vs ascent_f=39.21875，卡面 ≈0.175 px 是 desc
#     主残差，2026-10-18 D 段账）+ `<b>` 独立第二 pass（8-tap×0.23，Hidden/Text_Bold）
#     + `<i>` 第二 style 图集（FontStyle.Italic 字形变体）。
#   * race/race_multi（Belwe_Outline 45px，有描边 r=3.0）= 与数字角色同 shader 的
#     目标分辨率 9-tap + **浮点基线 ascent_f**。旧链 FreeType `_dilate` 的 α 比
#     0.888/RGB ~60 已定位为「未消费节点 `m_ResizeToFitAndGrow` 的字符尺度」（layout_text
#     的 grow 支）+ 非图集采样核，颜色链/材质 tint/第二绘制均被序列化+像素对账排除
#     （机制账待晋升 docs/notes/text-rendering-pipeline.md）。
#   * **plate**（spell 学派名，Belwe_Outline 45px，有描边 r=3.0、同 `Hidden/TextOutline_
#     Unlit`、同 race 的 grow 盒）= 与 race 完全同一条图集路径（第八轮落地，2026-10-18）：
#     FreeType 旧链的 αMAE 22.5 / α比 1.0176–1.0944 / RGB 22.75 是 `_dilate` 8-tap +
#     整型 ascent + trunc 三项既有差；接入 9-tap（含 center）+ ascent_f + 图集后
#     26 张可测 spell 卡 αMAE **0.0675–0.0956（均值 0.0813）**、max 2、α比 0.9993–0.9996、
#     RGB 0.76–0.81（= race 级）。账=findings/plate-atlas-canon.md。
#   * RTT 角色（name 曲面/平面）：不进本图集分支——走 RT 链（`_render_rtt`/
#     `_render_rtt_plane`，RT 内容复用 text_atlas.render_rt_content 的 9-tap），
#     机制与判据账见 docs/notes/text-rendering-pipeline.md「name 曲面 RTT」。
# ---------------------------------------------------------------------------

_ATLAS_ROLES = frozenset({"cost", "attack", "health", "durability", "armor", "desc",
                          "race", "race_multi", "plate"})
# 允许 `<b>` 第二 pass 的图集角色（desc；数字角色粗体未取证，保持整层回退）
_ATLAS_BOLD_ROLES = frozenset({"desc"})
# 浮点基线角色（desc/race/plate：引擎 TextMesh 基线来自浮点 ascent，FT 整型 round 在
# 45px 档差 0.449 字体 px≈0.33 卡面 px，是 race 层账 αMAE 8.5→2.8 的第一主因；plate
# 同字体同字号同盒，消融实测 αMAE 0.083→6.93、max 2→163（= plate 的第一主因）；
# 数字角色保持 ascent_round 以维持 cost 桥逐位验收口径）。**name 2026-10-24 入集**：
# trinket 平面 name（45px）textonly 对拍 ascent_round→ascent_f 使 max 71→2、>8 11→0
# （116510/133060；机制=同一 TextMesh 浮点基线，非帧特例）。
_FLOAT_ASCENT_ROLES = frozenset({"desc", "race", "race_multi", "plate", "name"})
# 行高用 FreeType `metrics.height`（hhea asc−desc+**lineGap**）的角色 = 引擎 TextMesh 语义。
# 抓帧实证（2026-10-18 第五轮 race 抓帧）：Belwe/GLEI 45px 的 hhea lineGap=6/1024 →
# 行高 45.26367 字体 px（asc−desc 只有 45.0）。104524 race 的 TextMesh.characterSize
# 反解 = 0.03755771 = 0.035×1.073077 = 0.035×(0.17/(45.26367×0.0035))；121058 两行
# baseline 间距 = 45.26367×0.85×k 逐位吻合；我方旧值 45.0 使 grow 因子高 0.586%
# （字形整体大 0.586%，= 层账 α +1%、描边外缘带 +8/255 的来源）。
# 作用域 = race/race_multi（第五轮）+ **name**（第六轮 A/B）+ **plate**（第七轮 A/B；见下）。desc 字体
# （FranklinGothic/BlizzardGlobal，upem 512 asc 502 desc −113）**hhea lineGap=0** ⇒
# desc 开/关逐位相同（18 卡 desc 层 n_diff=0，纯 no-op，故不加入）。数字角色（cost/attack/
# health/durability，Belwe 74px gap 0.4336）实测引擎不吃 lineGap：单行盒中心位移
# +0.31–0.36 卡面 px，αMAE 0.055–0.106 → 2.1–4.0、max 2–5 → 65–111（17 卡 / 47 个
# 数字层实例全回退）⇒ 保持 asc−desc。name（Belwe 45/36，gap 0.2637/0.2109）在 RT 内容基线里用
# metrics.height：RT 级 3 帧 αMAE 3.81/2.88/4.39 → 0.81/0.66/0.91（该轮 content_scale
# 仍取 0.95 补丁值；2026-10-22 fit 修好后归 1.0，同一对拍口径见 _NAME_RTT 注；0.945/0.955/0.96 当时全更差）；卡面 7 卡 1.17–2.12 → 0.35–0.64，
# 18 张 name 卡全部改善（RGB 同步 2.9–6.0 → 0.84–1.69）。账=findings/
# linegap-promotion.md §2。
# **plate**（第七轮 A/B）：spell 学派名（Mesh/Description_mesh/RaceUberText，Belwe 45、
# fit=1+grow=1、与 race 同 prefab 盒 0.85×0.17）。引擎 grow 由
# `ResizeToFitBounds_CharSize`（UberText.cs:UberText.ResizeToFitBounds_CharSize，经 fit 门 :1884-1887/:2299-2302）
# 读 `GetTextMeshBounds()`=renderer.bounds（UberTextRendering.cs:UberTextRendering.GetTextMeshBounds）算，bounds 行盒
# = metrics.height（活 oracle dbf8 plate：characterSize=0.03755771 = 0.35×0.17/(45.263672
# ×0.0035)，bounds.size.y/k=45.26367）⇒ 旧值 45.0 使 plate 字形大 0.586%。
# A/B（60 张 spell 卡，其中 26 张有学派文本可测；textonly type_row 区）：αMAE 均值
# 24.61→22.50（26/26 改善，Δ −1.43..−2.61）、α比 1.0639→1.0496、RGB 29.1→22.8；
# origin z_type_row 26/26 改善（Δmean −0.679、worse 0）；非 plate 层 104 实例逐位不变。
# 剩余 αMAE 22.5 属 plate 既有 8-tap dilate / 整型 ascent 未校准（不是行高；判据
# αMAE≤0.05、α比 0.995–1.005 未达，如实记）。账=findings/linegap-promotion.md §10。
_LINE_GAP_ROLES = frozenset({"race", "race_multi", "name", "plate"})
# 平面图集路径补引擎 PS 第 9 次 sample（center）的角色。`Hidden/TextOutline_Unlit` 的
# PS 是 9 次 sample 等权求和后 `add_sat`（抓帧 104524 ev344 反汇编 :18）：8 外 tap 只
# 在描边外缘未饱和处差分（实测 9-tap vs 8-tap：αMAE 0.0657 vs 0.1487、max 1 vs 92、
# α比 0.99957 vs 0.99893）。数字角色保持 8-tap（cost 桥逐位验收口径），只开 race/plate
# （plate 消融：center 关 → αMAE 0.0834→0.0871、max 2→8；同一 shader 同一核）。
# **name 2026-10-24 入集**：trinket 平面 name textonly 对拍 8-tap→9-tap 使 max 71→2、
# >8 11→0（与 ascent_f 同开才归零；机制=同一 TextOutline_Unlit PS，非帧特例）。
_CENTER_TAP_ROLES = frozenset({"race", "race_multi", "plate", "name"})
# 浮点层→8-bit 用 round 的角色（desc：引擎 RT 写入=GPU float→UNORM round-to-nearest；
# 数字角色历史上保持 trunc——cost 桥按 trunc 逐位验收，见 text_atlas.render_atlas_text 注）。
# **惰性已闭（quant-ab 2026-11-05）**：平面**有描边**支（render_atlas_text，race/plate 走
# 这条）的出口原硬编码 `astype(np.uint8)`（=trunc）；末级量化 round 化后三处文字出口
# 统一 `np.rint`（text_atlas 418/554/670、uber_text 2053/2093），本集合失去区分作用，
# 保留作历史账。race/plate 层随本轮 A/B（114363 Δmae=−0.361）与 full 门重验
# （证据与出口枚举账归任务 NOTES，不入本层注释）。
_ROUND_QUANT_ROLES = frozenset({"desc", "race", "race_multi", "plate"})
# （v3 退役：`_DEGRADED_PLACEHOLDER` 降级占位符守卫删除——text_shim 的静默降级
# 产出路径已删（text_shim.py 头注「degraded 恒 False」），语料无 `{n}` 文本，
# 守卫恒不触发=死码；若未来再现占位符文本，属 text-builder 域事故，非渲染层回退。）

# （2026-11-02 ability-premium-phase 退役：`_NUMERIC_PHASE_DY`（非 cost 数字腿
# +1/64 守卫值）与 `_NUMERIC_PHASE_LEGACY_KEYS`（数字角色相位延旧集，唯一成员
# Card_Hand_Ability_Premium）删除——闭算路由 `_numeric_phase_y` 成唯一路由。
# 锐扫验证=98918 cost φy∈[−0.5,0]×1/64（+argmin 邻域 1/256）对 oracle golden
# z_cost 区 display-space argmin=闭算复算值 −0.251316（δ=0 ≤1/64；z_cost MAE
# 16.302→14.828）；golden 门绿后 blessed golden 重锚（baseline 仓提交留痕）。
# 账=docs/notes/text-rendering-pipeline.md「数字角色相位」条与同名任务实验档；
# 其余未测键（BG_Anomaly/Play_Hero/Play_Bacon_Hero）数字角色零墨取证=
# cost-phase-untested 实验档 evidence/p1_consumption_map.json。）


def _render_atlas_role(layout: dict, fm: "FontMetrics", ns: NodeSettings, scene: Scene,
                       fill: tuple, outline: dict | None,
                       phase: tuple[float, float],
                       node_px_offset: tuple[float, float],
                       font: str, role: str = "",
                       bold_px: float = 0.0,
                       bold_taps: str = "shader8") -> Image.Image | None:
    """文字层（指定角色形态）；字形供给=text_atlas.glyph_quad（v3 单入口）。

    v3 退役：`allow_flipped`（cost 禁翻转位）与 `freetype_fallback`（逐字回退闭包）
    删除——翻转字形=快照存储形态（glyph_quad 内统一处理），缺字/advance 分歧=
    cmap 前置判定显式回退 + 响亮事件。cost 与其他数字角色同路（快照命中=位级逐位
    不变；2026-10-18 桥的「缺字/翻转整层回退」静默分支退役）。desc：浮点基线 +
    `<b>` 第二 pass（见 text_atlas 头注）。"""
    return _text_atlas.render_atlas_text(
        layout, fm, ns, scene, fill, outline, phase, font,
        node_px_offset=node_px_offset,
        rotation_deg=ns.rot_deg,
        float_ascent=(role in _FLOAT_ASCENT_ROLES),
        bold_px=bold_px, bold_taps=bold_taps,
        center_tap=(role in _CENTER_TAP_ROLES),
        quantize=("round" if role in _ROUND_QUANT_ROLES else "trunc"))

@parallel

def render_text(text: str, role: str, fontdef: dict, node_settings: NodeSettings,
                scene: Scene, node_px_offset: tuple[float, float] = (0.0, 0.0),
                curved_mesh: dict | None = None, supersample: int = 4,
                cost_phase: tuple[float, float] = (0.0, 0.0)) -> Image.Image:
    """渲染一个 UberText 节点的文字层（canvas 尺寸 RGBA；old uber_text.py:798 转写，
    批22 兑现——S11 render_text_layer 消费形）。

    text: 本地化文本（<b> 按 ProcessText/Bold 语义处理；其余标签剥离）
    role: 诊断标签（cost/name/desc/plate/attack/health/durability/armor/race）；RTT 路径由
        m_RenderToTexture 字段驱动
    fontdef: font_service.get_font_def（zhCN FontDef：修饰字段 + _ttf + _font_object_name）
    node_settings: prefab 序列化字段 + 节点世界信息（text_setup_for）
    node_px_offset: 节点所属帧子树的渲染校准（基座渲染器家族常量；S11 恒 (0,0)）
    curved_mesh: RTT 路径必传（load_curved_mesh）
    cost_phase: 图集角色摆位亚像素相位（卡面 px；现役仅 cost 有帧族表）。
        数字角色（cost/attack/health/durability/armor）经引擎图集路径消费
        （_render_atlas_role → text_atlas.render_atlas_text）；FreeType 路径不消费。
        图集路径的角色边界与回退规则见 `_ATLAS_ROLES` 上方注释块。

    签名修正（批11b 立壳→实现，批12-18 先例同权）：stub 四参系缺执行面参数——
    按旧 render_text 形补 scene/node_px_offset/curved_mesh/supersample/cost_phase
    （S1 探针 C6 四位置参喂挂兼容——新增参全带缺省）。
    偏差记账：图集直采分支不转写（old 2026-10-13 批10d 退役——新 FontMetrics 无
    atlas 属性，`getattr(fm,"atlas",None)` 恒 None 的死分支按退役记账剥离；RTT
    平面 fallback 同属该死链）。layout dict 消费形=批19 layout_text 产物
    （lines[行][字]={"ch","pen_x","line","bold"}/line_widths/pitch/box_h/k）。
    v3（glyph-supply-v3）：字形供给=text_atlas.glyph_quad 单入口（按需 hinted FT
    位级集 + 采集快照参照字形 + cmap 前置缺字兜底）；**静默回退链全退役**（判据 3）：
    RTT 走不到底的形态（粗体名牌/无描边）=硬错误；FreeType 超采样主链（ss+LANCZOS+
    `_dilate` 烘焙）与 `_render_rtt_legacy` 删除；数字角色粗体=硬错误（引擎取证缺席）；
    text_shim 降级占位符守卫删除（占位符产出路径已于 text_shim 退役，恒不触发）。

    族账锚=UberText.cs（模块头注族账；逐字转写件）。
    """
    W, H = scene.canvas
    loc_adj = locale_adjustment(node_settings.text_fields)
    fs = int(fontdef["m_FontSizeModifier"] * loc_adj.get("m_FontSizeModifier", 1.0)
             * node_settings.f("m_FontSize"))
    font_name = fontdef.get("_font_object_name", "")
    if node_settings.f("m_RenderToTexture") and curved_mesh is not None:
        # 曲面 RTT（CurvedText mesh 贴回）：直采字形经本链的 RT/网格重采样近似反而劣化
        # （MC banner 残差归因账），暂用 FreeType 链；垂直模型 v2 同用。
        fm = FontMetrics(fontdef["_ttf"], fs, font_name=font_name)
    else:
        fm = make_font_metrics(fontdef, fs)
    layout = layout_text(text, node_settings, fm=fm, fd=fontdef,
                         line_gap=(role in _LINE_GAP_ROLES))

    # 颜色统一 0..1 域（prefab 序列化色即 0..1 linear 存储值；×255 与实测吻合）
    fill = tuple(float(c) for c in _color(node_settings.f("m_TextColor")))
    outline = None
    if node_settings.f("m_Outline"):
        r = (node_settings.f("m_OutlineSize") * fontdef["m_OutlineModifier"]
             * loc_adj.get("m_OutlineModifier", 1.0))
        outline = {"r": float(r),
                   "color": tuple(float(c) for c in _color(node_settings.f("m_OutlineColor")))}
    has_bold = any(g["bold"] for row in layout["lines"] for g in row)
    bold_px = min(node_settings.f("m_BoldSize"), BOLD_SIZE_CAP) if has_bold else 0.0

    if node_settings.f("m_RenderToTexture"):
        if curved_mesh is not None:
            rtt = _render_rtt(layout, fm, node_settings, scene, fill, outline, bold_px,
                              curved_mesh, node_px_offset, font=font_name)
        else:
            # m_RenderOnObject=NULL → UB SetupRenderOnPlane:2245-2257（平面 RTT）
            rtt = _render_rtt_plane(layout, fm, node_settings, scene, fill, outline,
                                    bold_px, node_px_offset, font=font_name)
        if rtt is not None:
            return rtt
        # v3 硬错误（判据 3：旧「图集缺失/不支持形态→legacy 链」静默回退退役）。
        # 可达形态仅：粗体名牌（引擎 Bold 名牌取证缺席）/无描边名牌/空 font 名。
        raise AssertionError(
            f"RTT 文字层无法渲染（role={role} bold_px={bold_px} "
            f"outline={'有' if outline is not None else '无'} font={font_name!r}）"
            "——v3 legacy 回退链已退役，该形态属引擎语义未取证位（响亮，不静默）")

    # 数字角色粗体=硬错误（引擎 Bold 数字角色取证缺席；旧链静默画非粗体已退役）
    if has_bold and role not in _ATLAS_BOLD_ROLES:
        raise AssertionError(
            f"角色 {role} 出现 <b> 粗体（bold_px={bold_px}）——引擎 Bold 数字角色/"
            f"种族板语义未取证（_ATLAS_BOLD_ROLES={sorted(_ATLAS_BOLD_ROLES)}），"
            "v3 静默降粗退役，响亮停")

    # 文字层（v3 供给单路）：全部角色走 glyph_quad 供给 + 角色 shader 语义表
    # （_FLOAT_ASCENT_ROLES/_CENTER_TAP_ROLES/_ROUND_QUANT_ROLES/_ATLAS_BOLD_ROLES）。
    return _render_atlas_role(
        layout, fm, node_settings, scene, fill, outline, cost_phase,
        node_px_offset, font_name, role=role,
        bold_px=(bold_px if role in _ATLAS_BOLD_ROLES else 0.0))


# ---------------------------------------------------------------------------
# name 曲面 RTT（UB RenderToTexture：UberText.cs:UberText.SetupRenderToTexture / 5909-5934 / CalcTextureSize:2805-2826）
#
# 引擎链（2026-10-18 抓帧实证；过程账=docs/notes/text-rendering-pipeline.md「name 曲面 RTT」）：
#   1) RT 尺寸 = CalcTextureSize：int 截断（m_Resolution × 盒纵横比），抓帧三档逐位吻合
#      （dbf8 300×44、129851 300×47、76981 300×42）。
#   2) RT 内容（TextOutline_Unlit，与平面同 shader）：clear = m_OutlineColor 且 A=0
#      （UberText.cs:UberText.SetupCamera + UberTextRenderToTexture.cs:UberTextRenderToTexture.SetTargetClearColor），字形 α=saturate(Σ9-tap)、
#      RGB=lerp(outline, fill, center)。抓帧 RT 纹理 `src_ResourceId_3200.png` 实证：
#      α=255 的像素里 2440/3047 带 outline 色 RGB → RT **内**有描边（旧账「RT 内无描边」
#      被反证；描边不是合成阶段造出来的）。
#   3) 合成（CurvedText mesh 的 material）：抓帧 caps4 反汇编（PS hash
#      080b54f5-238ca572-ff1022f7-8bb3fb06）=
#          α = saturate(Σ4 taps) × cb1[2].z ,  RGB = center tap ,  × 顶点色
#      4 个 tap = center ± cb2[2].xy（UV 域）；实测 cb2[2].xy = (0.5/rt_w, 0.5/rt_h)、
#      .z = 0.5（三档 RT 一致：300×44 → 1/600,1/88；300×47 → 1/88? 见 findings）→
#      **半 texel 对角** ±0.5、edge 权重 0.5（9-texel 核：center 0.5 / 边 0.25 / 角 0.125，
#      后 saturate）。material = `Hidden/TextAntialiasing`（AntiAlisaingMaterialQuery 的
#      _OffsetX/_OffsetY/_Edge 与 cb 布局逐一对应；UberTextRenderToTexture.cs:UberTextRenderToTexture.SetAntialiasOffset
#      SetAntialiasOffset = rt.texelSize × m_AntiAliasAmount）。顶点色实测白色
#      （name vb1 = ff ff ff ff）→ 颜色全在 RT 内容里，合成阶段只做 α 扩张。
#   4) RT 内容尺度 = **rt_w/m_Width（× k，不乘 local_scale、无额外系数）**：引擎 RT 里
#      glyph 的局部坐标 = CharacterInfo(px)×k（k=TextMesh.characterSize×0.1），相机正交
#      覆盖 = m_Width×m_Height，故内容尺度只由 characterSize 定。旧账的 0.95 是
#      **fit 侧缺一步的补丁**（`ReduceText_CharSize` 入口 intra 项；见 layout_text 该支
#      注释），2026-10-22 修 fit 后 content_scale 归 1.0，逐卡 RT 内容与引擎 PNG
#      αMAE ≤0.03/255（9/9 卡两态对拍；账见 docs/notes/text-rendering-pipeline.md
#      「name 曲面 RTT」节）。
#      local_scale 恒不入内容（引擎文本 mesh 的 lossyScale 不进 RT）。
#   5) 基线用浮点 ascent（Belwe 45：ascent_f=39.55078125 vs ascent_round=40，
#      差 −0.449 字体 px；36px 档 31.640625 vs 32）。
#   6) RT 内容 pass blend = `SrcAlpha/OneMinusSrcAlpha`（m_State src=5/dst=10；
#      出处=cost-glyph-bitwise 实验 NOTES.md:40 + 反汇编 sidecar 同目录）。
#      固定功能混合对 **α 通道同样**用 srcAlpha 因子，clear A=0 ⇒ RT 存的是
#      `out.a = s²`（s=shader α=saturate(Σ9)s）。2026-10-18 第四轮实测：补上这个平方后
#      RT 级最优半径=3.000（=m_OutlineSize，10/10 卡），卡面 7 卡 αMAE 全部下降
#      （2.09–3.16 → 1.17–2.12）；旧 `outline_scale=0.90` 正是缺平方时的等效补偿。
#      账=findings/name-rtt-canon.md §13。
# ---------------------------------------------------------------------------
_NAME_RTT = {
    "float_ascent": True,  # RT 内容基线取 ascent_f
    "tap4": True,          # 合成阶段 4 对角 tap；False → 单次中心 bilinear
    # RT 内容尺度（RT px / 局部单位 × k）。**机制值=1.0**：内容尺度只由
    # TextMesh.characterSize 定（k=cs×0.1，相机覆盖 m_Width×m_Height），无第二因子。
    # 旧值 0.95 是 fit 侧缺步的补丁（`ReduceText_CharSize` 入口 intra 项，见
    # layout_text 该支注释）：短名卡 cs=0.05 vs 引擎 0.0475 时 0.95 恰好抵消，长名卡
    # (cs 与引擎逐值相同) 被重复缩 5%。2026-10-22 修 fit 后归 1.0：9 卡 oracle RT PNG
    # 逐像素对拍 αMAE ≤0.03/255（content_scale=1.0；0.95 时 39/11/7 量级）。
    # 失效条件：若再现「RT 内容整体尺度差一个固定因子而 fit cs 与引擎相同」，先查
    # 该节点的 m_Resolution/相机覆盖，不要回填常数。
    "content_scale": 1.0,
    "apply_local_scale": False,  # RT 内容 q 是否乘 local_scale（引擎=否，A/B 用）
    # RT 内容描边半径系数（乘在 m_OutlineSize=3.0 上）。**机制值=1.0**（第四轮已闭）：
    # 引擎材质 _OutlineOffset = m_OutlineSize×_TexelSize = 3 texel；旧 0.90 的实测内容
    # = 缺 α 通道平方（blend SrcAlpha）造成的 fringe 过肥，被 0.90 反向抵消。
    # 补上 alpha_blend="gpu" + center_tap=True 后，RT 级最优半径=3.000（0.86–1.06 扫描，
    # 10/10 卡），见 findings §13。保留开关=1.0 供 A/B，不再有逐卡常数。
    "outline_scale": 1.0,
    # RT 内容 pass blend 语义：引擎 pass blend = SrcAlpha/OneMinusSrcAlpha
    # （m_State src=5/dst=10），α 通道也乘 srcAlpha ⇒ clear A=0 时 out.a=s²。
    # 详见 text_atlas.render_rt_content 文档串与 findings §13。
    "alpha_blend": "gpu",       # "srcover"=旧 straight source-over / "gpu"=引擎混合
    "center_tap": True,         # 补引擎 PS 第 9 次 sample（center）
    # ---- 第十轮 A/B 开关（默认=现役行为；证明后才翻默认）----
    # 引擎 RT=ARGB32：4 个 glyph 是 4 个 draw，每次写回都过 8-bit UNORM。
    "per_glyph_round": False,   # True → 每 glyph 混合后整张 RT 8-bit round（含 clear）
    # 双线性权重定点栅格（D3D11 采样器子纹素精度，见 text_atlas._sample_bilinear）。
    "subtexel_bits": 0,         # 0=现役 float 采样；8=1/256 权重栅格
    "subtexel_round": "nearest",  # 权重定点化的取整方向（nearest/trunc）
    "quad_clip": False,         # True → 只写 quad 覆盖的像素中心
    "phase_rt": (0.0, 0.0),     # 逐 glyph 整体 RT px 平移（A/B 相位探针）
    # 引擎 VS 的 float32 位置链：把每个 glyph quad 角点过 `world=local±3000` →
    # `clip=w·s+fl(±s·3000)` 的 float32 运算（逐顶点 ulp 量化 ≈0.01–0.03 RT px）。
    # 第十三轮：引擎原始 DXBC 重放与抓帧 RT **逐位相同**（3/3），而 float64 精确 VP 的
    # 同数据 CPU 模型差 0.43–0.66；换成该链后 RT 0.0751–0.0994、卡面 true 0.476→0.102。
    "vs_f32": True,
    # 合成阶段（TextAntialiasing 4-tap）读 RT 时的子纹素权重栅格（同 D3D11 语义）。
    "subtexel_bits_composite": 0,
    # 单 tap 过滤结果的定点化（UNORM8 过滤精度 implementation-defined；见 _tap_quant）。
    "tap_quant": "",
    # 双线性内部一维 lerp 的定点化（硬件定点累加器；见 _sample_bilinear）。
    "lerp_quant": "",
}


def _rtt_size(ns) -> tuple[int, int]:
    """UB.CalcTextureSize:2805-2826（int 截断；Low 质量 ×0.75 属画质档，离线不复刻）。"""
    res = float(ns.f("m_Resolution"))
    w_box, h_box = float(ns.f("m_Width")), float(ns.f("m_Height"))
    if w_box > h_box:
        return int(res), int(res * (h_box / w_box))
    return int(res * (w_box / h_box)), int(res)


def _bilinear(rt_arr, x, y, subtexel_bits=0, subtexel_round="nearest"):
    """RT texel 坐标（texel 中心=整数）双线性采样；越界 clamp（引擎 sampler clamp）。

    `subtexel_bits>0` → 采样坐标小数按 2^-bits 定点量化（D3D11 采样器子纹素精度；
    与 `text_atlas._sample_bilinear` 同式，A/B 用）。"""
    h, w = rt_arr.shape[:2]
    x = np.clip(x, 0, w - 1)
    y = np.clip(y, 0, h - 1)
    if subtexel_bits:
        q = float(1 << int(subtexel_bits))
        def _quant(c):
            f = np.floor(c)
            frac = c - f
            frac = (np.floor(frac * q + 0.5) if subtexel_round == "nearest"
                    else np.floor(frac * q))
            return f + frac / q
        x, y = _quant(x), _quant(y)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    return (rt_arr[y0, x0] * (1 - fx) * (1 - fy) + rt_arr[y0, x1] * fx * (1 - fy)
            + rt_arr[y1, x0] * (1 - fx) * fy + rt_arr[y1, x1] * fx * fy)


def _rtt_rt_content(layout, fm, ns, scene, fill, outline, font, glyph_log=None):
    """RT 内容（两路共用）：返回 (rt_h, rt_w) 浮点 RGBA 0..1。

    v3：`_NAME_RTT["atlas"]` A/B 支与 FreeType fallback 闭包退役——RT 内容单路
    glyph_quad 供给（9-tap 描边语义不变）。"""
    rt_w, rt_h = _rtt_size(ns)
    qx = rt_w / float(ns.f("m_Width"))
    qy = rt_h / float(ns.f("m_Height"))
    if _NAME_RTT["apply_local_scale"]:
        qx *= ns.local_scale
        qy *= ns.local_scale
    qx *= _NAME_RTT["content_scale"]
    qy *= _NAME_RTT["content_scale"]
    ol = dict(outline)
    ol["r"] = float(outline["r"]) * _NAME_RTT["outline_scale"]
    vs_f32 = None
    if _NAME_RTT.get("vs_f32", False):
        # 引擎正交相机：sx=+2/m_Width、sy=−2/m_Height（抓帧 cb0[79].x / cb0[80].y
        # 逐帧实测；float32 参与 VS 的 float32 运算）。
        mw = float(ns.f("m_Width"))
        mh = float(ns.f("m_Height"))
        vs_f32 = (float(np.float32(2.0 / np.float32(mw))),
                  float(-np.float32(2.0 / np.float32(mh))))
    rt8 = _text_atlas.render_rt_content(
        layout, fm, font, fill, ol, rt_w, rt_h, qx, qy,
        float_ascent=_NAME_RTT["float_ascent"], quantize="round",
        center_tap=_NAME_RTT.get("center_tap", False),
        alpha_blend=_NAME_RTT.get("alpha_blend", "srcover"),
        subtexel_bits=_NAME_RTT.get("subtexel_bits", 0),
        subtexel_round=_NAME_RTT.get("subtexel_round", "nearest"),
        per_glyph_round=_NAME_RTT.get("per_glyph_round", False),
        quad_clip=_NAME_RTT.get("quad_clip", False),
        phase_rt=_NAME_RTT.get("phase_rt", (0.0, 0.0)),
        glyph_log=glyph_log,
        tap_quant=_NAME_RTT.get("tap_quant", ""),
        lerp_quant=_NAME_RTT.get("lerp_quant", ""),
        vs_f32=vs_f32)
    return rt8.astype(np.float64) / 255.0


def _rtt_aa(ns) -> tuple[float, float]:
    """合成阶段 4 对角 tap 参数：UberTextRenderToTexture.cs:UberTextRenderToTexture.SetAntialiasOffset SetAntialiasOffset(rt.texelSize ×
    m_AntiAliasAmount) / SetAntialiasEdge(m_AntiAliasEdge)。抓帧 cb2[2] 三档=0.5/0.5
    （name 节点序列化 m_AntiAliasAmount/Edge=0.5）；weapon 帧=0.35/0.585。"""
    return float(ns.f("m_AntiAliasAmount", 0.5) or 0.5), float(ns.f("m_AntiAliasEdge", 0.5) or 0.5)


def _rtt_composite_taps(rt_arr, col, rw, ns):
    """中心 sample + 4 对角 tap（±amount texel，Σ×edge 后 saturate）。"""
    sb = _NAME_RTT.get("subtexel_bits_composite", 0)
    sr = _NAME_RTT.get("subtexel_round", "nearest")
    src = _bilinear(rt_arr, col, rw, sb, sr)
    amount, edge = _rtt_aa(ns)
    if not _NAME_RTT["tap4"] or amount <= 0.0:
        return src
    acc = np.zeros(src.shape[:2])
    for tx, ty in ((-amount, -amount), (-amount, amount),
                   (amount, -amount), (amount, amount)):
        acc += _bilinear(rt_arr, col + tx, rw + ty, sb, sr)[..., 3]
    src = src.copy()
    src[..., 3] = np.clip(acc * edge, 0.0, 1.0)
    return src


def _render_rtt(layout, fm, ns, scene, fill, outline, bold_px, mesh, off,
                font: str = "") -> Image.Image | None:
    """name 曲面 RTT 引擎链；不支持形态（粗体/无描边/无 font 名）→ None（调用方硬错误）。

    RT 内文字零弯曲（弧=网格顶点）；mesh 采样 v 翻转（v=1=RT 顶=文字顶，抓帧
    name vb 的 uv0 与 mesh z/py 关系数值验证）。
    （v3：`_NAME_RTT["engine"]` False 支退役——legacy 链已删，engine 恒真。）"""
    if bold_px > 0.0 or outline is None or not font:
        return None
    rt_arr = _rtt_rt_content(layout, fm, ns, scene, fill, outline, font)
    if rt_arr is None:
        return None
    rt_h, rt_w = rt_arr.shape[:2]
    W, H = scene.canvas
    layer = np.zeros((H, W, 4))
    M = mesh["world"]
    vw = (M[:3, :3] @ mesh["verts"].T).T + M[:3, 3]
    pxs = (vw[:, 0] - scene.wx0) * scene.s + scene.ox + off[0]
    pys = (scene.wz1 - vw[:, 2]) * scene.s + scene.oy + off[1]
    uv = mesh["uv0"]
    for tri in mesh["tris"]:
        xs, ys = pxs[tri], pys[tri]
        xmin = max(int(np.floor(xs.min())), 0)
        xmax = min(int(np.ceil(xs.max())), W - 1)
        ymin = max(int(np.floor(ys.min())), 0)
        ymax = min(int(np.ceil(ys.max())), H - 1)
        if xmin > xmax or ymin > ymax:
            continue
        gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5,
                             np.arange(ymin, ymax + 1) + 0.5)
        d = ((xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0]))
        if abs(d) < 1e-12:
            continue
        l1 = ((gx - xs[0]) * (ys[2] - ys[0]) - (gy - ys[0]) * (xs[2] - xs[0])) / d
        l2 = ((xs[1] - xs[0]) * (gy - ys[0]) - (ys[1] - ys[0]) * (gx - xs[0])) / d
        l0 = 1.0 - l1 - l2
        inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not inside.any():
            continue
        u = l0 * uv[tri[0], 0] + l1 * uv[tri[1], 0] + l2 * uv[tri[2], 0]
        v = l0 * uv[tri[0], 1] + l1 * uv[tri[1], 1] + l2 * uv[tri[2], 1]
        col = u * rt_w - 0.5
        rw = (1.0 - v) * rt_h - 0.5
        src = _rtt_composite_taps(rt_arr, col, rw, ns)
        _composite_masked(layer, src, inside, ymin, ymax, xmin, xmax)
    # 末级量化 round 化（quant-ab 2026-11-05）：RTT 出口 trunc→round-to-nearest。
    return Image.fromarray(np.rint(np.clip(layer, 0, 1) * 255).astype(np.uint8), "RGBA")


def _render_rtt_plane(layout, fm, ns, scene, fill, outline, bold_px, off,
                      font: str = "") -> Image.Image | None:
    """name 平面 RTT fallback（m_RenderOnObject=NULL → UB SetupRenderOnPlane:2245-2257；
    weapon / heropower 帧 name 节点同此支）。

    平面 quad = 盒 (m_Width × m_Height) 节点局部居中（UberTextRenderToTexture.cs:UberTextRenderToTexture.CreateMesh
    的 4 顶点 ±size/2 + DoPlaneRotate(-90°X) → 文字平面），世界缩放取节点列范数
    （weapon 帧 name 节点 anisotropic：cols[0]≠cols[1]；heropower 帧三列同值）。采样与合成与曲面链同
    （中心 + 4 对角 tap，AA 参数取节点 m_AntiAlias*）。
    （v3：`_NAME_RTT["engine"]`/`plane` False 支随 legacy 链退役。）"""
    if bold_px > 0.0 or outline is None or not font:
        return None
    rt_arr = _rtt_rt_content(layout, fm, ns, scene, fill, outline, font)
    if rt_arr is None:
        return None
    rt_h, rt_w = rt_arr.shape[:2]
    W, H = scene.canvas
    layer = np.zeros((H, W, 4))
    cols = getattr(ns, "world_cols", (1.0, 1.0, 1.0))
    w_px = float(ns.f("m_Width")) * float(cols[0]) * scene.s
    h_px = float(ns.f("m_Height")) * float(cols[1]) * scene.s
    cx = scene.project(*ns.world_pos[::2])[0] + off[0]
    cy = scene.project(*ns.world_pos[::2])[1] + off[1]
    x0c, y0c = cx - w_px / 2.0, cy - h_px / 2.0
    xmin = max(int(np.floor(x0c)), 0)
    xmax = min(int(np.ceil(x0c + w_px)), W - 1)
    ymin = max(int(np.floor(y0c)), 0)
    ymax = min(int(np.ceil(y0c + h_px)), H - 1)
    if xmin > xmax or ymin > ymax or w_px <= 0 or h_px <= 0:
        return None
    gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5,
                         np.arange(ymin, ymax + 1) + 0.5)
    col = (gx - x0c) / w_px * rt_w - 0.5
    rw = (gy - y0c) / h_px * rt_h - 0.5
    inside = np.ones(col.shape, bool)
    src = _rtt_composite_taps(rt_arr, col, rw, ns)
    _composite_masked(layer, src, inside, ymin, ymax, xmin, xmax)
    # 末级量化 round 化（quant-ab 2026-11-05）：RTT 出口 trunc→round-to-nearest。
    return Image.fromarray(np.rint(np.clip(layer, 0, 1) * 255).astype(np.uint8), "RGBA")
