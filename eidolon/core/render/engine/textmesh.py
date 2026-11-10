"""textmesh — Unity TextGenerator 语义（无游戏类对应物，段 S7 几何面）。

对位 Unity TextGenerator：文字→顶点/UV 三角网格生成（字形光栅前的排版
几何半）——引擎侧 UberText 组件经它得文字 mesh；我方文字管线
（game/uber_text.py，S7）渲到内存 RT 再贴曲面网格，TextGenerator 语义
用于直排文字几何路径的等价复现。

配方面：字形度量经 game/font_service.py（S7）；TTF 字节经 recipes.text。
"""


def generate(text: str, fontdef: dict, settings) -> dict:
    """文字几何生成：TextGenerator 语义对位。

    text=文字串；fontdef=FontDef dict；settings=节点布局参数（字号/锚定/
    wrap）。返回顶点/UV/索引数组 dict。

    批24 立户判定=留+升格注（原注「S7 未生长」口径过时）：S7 已生长且语料
    渲染路径=RTT 曲面贴图（批19 排版管线+批22 render_text 执行面兑现）——
    TextGenerator 直排几何路径零消费面，独立消费方（直排文字几何）出现前
    立户响亮。
    """
    raise NotImplementedError(
        "TextGenerator 直排几何宿位（后续战役；S7 语料路径=RTT 曲面已由 "
        "uber_text.render_text 兑现——批24 立户判定注）")
