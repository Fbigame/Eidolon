"""eidolon.core.render — 渲染机制层（按游戏本体组织消费面）。

定位：消费面按游戏本体组织，子包划分——

    game/    Assembly-CSharp 类镜像（actor/ 方法族、card、actor_names、
             card_color_switcher、compiler）
    text/    文字栈镜像（Blizzard.T5.UberText.Runtime + FontService 两个 DLL：
             uber_text/text_atlas/glyph_supply/font_service/ft_unhinted）
    engine/  引擎行为镜像（raster/shaders/textmesh——无游戏类对应物）
    scenes/  prefab 维度（PREFAB_SPECS 全集清单+kit 路由+scene 装载缓存）
    batch.py params.py  我方管线（批量编排/参数常量——游戏无对应物）

**import 轻面纪律**（core-integration §6.5/§16.1）：本 ``__init__`` 不 import
任何子模块。CLR-at-import 模块（game.card / game.compiler / game.actor.* /
batch 等，§6.5 清单）只能在 ``context.install(ctx)`` + ``dbf.install_default(...)``
之后 import；产品入口（adapters / api / preflight）一律函数体内延迟引入。
Phase 3a 为机械移植段：api.py / preflight.py（Phase 0 空壳）/ constants.py /
card_overrides.py / assets.py 属 Phase 3b；产品端口已接线（Phase 3c 起，组合层
``eidolon/adapters.py::CoreRenderPort`` 经本包 api/preflight 驱动渲染），
本 ``__init__`` 仍不 import 任何子模块。
"""
