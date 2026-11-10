"""params — 渲染参数常量正典（跨层共享值的单一事实源）。

只装**参数性常量**，不放渲染状态/副作用；消费方一律 `from eidolon.core.render.params
import ...`，禁在各自模块内复制取值（2026-10-22 text-default-phase：三份
DEFAULT_T=0.15285 收敛到本件）。新增常量必须带三字段注释——层 / 来路 / 失效。
"""
from __future__ import annotations

PRODUCT_SESSION_T = 0.0
"""产品 tzero 相位（Eidolon 设计 §7.6）。

层=R（会话相位，运行时量：Actor 云层材质 cb[15].x=_Time.x 的冻结时刻）。
来路=产品固定相位裁定（core-integration §7.6）：当前 oracle corpus 的 canon 是
    tzero=true（manifest 每行 t=0.0、msaa_level=4），产品无 CLI/TOML 相位输入，
    core 默认相位取 0.0（tzero）而非 legacy DEFAULT_SESSION_T。
失效=若产品将来开放相位输入（CLI/TOML），本常量退为缺省初值；oracle harness
    逐行 t 值优先（RenderCard.session_t 显式覆盖），不经过本常量。
"""

DEFAULT_SESSION_T = 0.15285
"""无参考相位卡的缺省会话相位（上游 legacy 值，全仓唯一副本；门/报告/铸造三面共同 import）。

Eidolon 产品面不用本常量（产品 tzero=PRODUCT_SESSION_T=0.0）；只保留给
    legacy harness「manifest 行 t=null」显式使用（core-integration §7.6）。

层=R（会话相位，运行时量：Actor 云层材质 cb[15].x=_Time.x 的冻结时刻，
    随采集批次变，不是全局常数）。
来路=textless-ref P=3.057 换算（t=(P/20)%0.2 → 0.15285；textless-ref §7.5 冻结
    采集裁定）——**仅用于 manifest v2 行 t=null 的卡**（只可能出现在 legacy 桥代：
    旧语料无相位行）。
失效=凡行有 t 必须用逐行值（历史语料分布 0.1472–0.2050；未来采集代=代级定向冻结
    target_t），不得用本常量；渲染入口 render_with/render_card 的 t 是必填参数，
    本常量只在调用方确实解析不到参考相位时显式传入（门内禁止靠缺省——
    gate_impl._require_t fail-loud）。
"""
