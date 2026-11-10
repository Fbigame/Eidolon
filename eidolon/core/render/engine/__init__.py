"""engine — Unity 引擎行为镜像（无游戏类对应物，离线等价层）。

对位引擎机制而非游戏类：光栅核心与 Blend 状态（raster.py——策略表按 prefab 名
改键）、shader DXBC 直译宿位（shaders.py，d3d_backend 原机执行接此）、
TextGenerator 文字几何语义（textmesh.py）。

形态边界：渲染队列序离线等价为透明延期；RTT 实时性/后处理全局管线不复刻。
配方面：材质状态表/mip 链注册经 recipes。
"""
