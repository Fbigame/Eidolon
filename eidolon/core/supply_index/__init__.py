"""supply_index — 产品供给落盘索引（portrait/kit/gems/watermark/text/color 六域；设计 §14 Phase 5 + Phase 1 A4）。

定性：跨进程/跨运行复用物化值的供给索引。冷侧（cold.py，UnityPy）建库：catalog 导入
+ 定向 locator resolve + 纹理解码 → PNG blob 内容寻址落盘 + per-gen SQLite；暖侧
（warm.py）只读 DB+blob 出 PIL Image——**不 import UnityPy、不开游戏 *.unity3d**
（audit.py 有 import blocker + open 拦截的机器证明）。

「必须保留」条款在本包的落位（逐条）：

1. warm 无 UnityPy/无游戏文件        → warm.py 零 UnityPy import；audit.import_blocker
                                        子进程 meta_path 拦截 + open(*.unity3d) 拦截跑通
                                        warm 全量装配；--offline 形态接受 --game 且不触。
2. 冷侧 container 读 f.container.container 原始 pairs、禁 env.container
                                    → cold/_unity.py 与 worker 全走
                                        SerializedFile.container.container 原始 pairs
                                        （225s parse_preload_table 首触判例）。
3. 每代 DB + 跨代共享内容寻址 blobs   → gen-<game_id>/index.sqlite + blobs/<2>/<2>/
                                        <payload_sha256>.png；同 payload 跨代/跨卡去重，
                                        版本升级不重写旧 blob。
4. 版本报告五态 reused/revalidate/stale/missing/orphan（revalidate≠不能用）
                                    → diff.py 迁移判定 + revalidate --exact 升格
                                        reused/stale；migration_report 表逐行记账。
5. 存储代价实测收口、无运行时预算/告警/自动 GC → bench/measure 一次性输出，库面零
                                        预算子系统。
6. plan/item 键含全部内容输入（codec 版本在内）→ schema.item_key/plan_key 派生式：
                                        item_key=sha256(域|项|params|locale|premium|
                                        codec|codec_version|content_inputs_json)，
                                        content_inputs 含 portrait 像素 sha 与
                                        carddef 对象 sha；缺内容维度即静默串图的设计
                                        缺陷在键面构造性排除。

架构边界（Phase 5 移植定案）：本包自包含；禁 import eidolon.core.render /
eidolon.core.supply / eidolon.core.recipes（供给独立）；允许复用 eidolon.core.infra
（context/game_install/dll_reflect/game_tag）；不复用 infra/route（本包有自己的
per-gen index，不是 route.db 变体）；warm 模块禁 import UnityPy。
**cache_root 全显式**：调用方（CLI/组合层）构造传入，库面零 repo/env/默认值解析
（paths.py 无 default_cache_root——上游容器直属默认不搬）。
"""
