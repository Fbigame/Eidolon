"""scenes — prefab 维度（consumer-v2 新增，帧键层接替者）。

prefab 是游戏侧真实资产名（ActorNames 三表值）；本包按 prefab 组织消费面：
PREFAB_SPECS=prefab 全集清单+kit 族路由（tripwire 宿位：缺行 assert 响亮——
游戏可路由到任何 prefab 因其全验证，我方只开放有策略行的 prefab）、scene
装载缓存（实例化离线等价）、帧差异参数化表宿位。

"我们缺什么"=游戏 prefab 全集（ActorNames 表+decomp 分支导出）减本包清单行，
机械对账可导（对账面=tools 侧，不进本包）。
"""
