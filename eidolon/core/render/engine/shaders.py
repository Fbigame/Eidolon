"""shaders — DXBC 直译件宿位（无独立段号，随首消费段生长）。

定位：shader 反汇编直译件的宿位——宝石 shader DXBC 10 指令
（rgb = albedo.rgb + cloud.x·_tint.rgb·albedo.a·1.5·_Intensity，相位
t=(P/20)%0.2；首消费段=S6）、正典描边 shader（Bold=偏移二次绘制/
TextOutline 9-tap，消费段=S7）、Blend 光栅式（消费段=S9）。

将来 d3d_backend 原机执行接此（宿位即接线点）；现阶段直译件以 python
像素写回式等价（engine/raster.py）。出处只留 decomp/反汇编锚（分层守护
字符串面晋升层零容忍）。
"""


def translate(name: str, dxbc: bytes) -> dict:
    """DXBC→直译件装载宿位（d3d_backend 原机执行接线点）。

    name=shader 名；dxbc=字节码。返回直译件 dict（指令表/常量槽位）。

    批24 立户判定=留+升格注（原注「S6 未生长」口径过时）：S6 已生长且择形
    python 像素写回式直译等价（actor/gems.py DXBC 直译，批16/22；光栅面
    engine/raster.py）——本宿位的服务对象=后续战役 d3d_backend 原机执行面，
    非任何在役段；独立消费方出现前立户响亮。
    """
    raise NotImplementedError(
        "DXBC 宿位=d3d_backend 原机执行接线点（后续战役；S6 直译等价已由 "
        "actor/gems.py+engine/raster.py 承担——批24 立户判定注）")
