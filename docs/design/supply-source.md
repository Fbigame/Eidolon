# supply source：supply-index 接 render 的 seam 设计（Phase 0 选型账）

> 状态：Phase 0 设计稿（2026-11-09），等 review 后再开 Phase 1 实施。
> 实证基础：`tests/phase0/` 四件套（token 清点 / index 覆盖对照 / 单卡 spike）+
> 本机全量 index 代 `gen-f6d4…63f29`（37.0.2，full 代，零缺口，36373 卡）。
> 数字均出自 2026-11-09 本机实跑（`build/phase0/*.json`；build/ 不入库）。

## 0. 问题

render 走 live supply：域函数经 `core().res`（Resolver(current().data_win)）现场用
UnityPy 开包解码，冷进程首卡数百秒（本机实测 343–448s，含 route 扫描/kit 提取/
图集扇出/mip 链），每个 worker 进程重付。supply_index 已有 cold/warm：
`SupplyIndex.assemble_card(card_id)` 返回一张卡的 plan 束
（portrait / portrait_golden / kit / kit_play / gem:* / watermark + text），
零 UnityPy、零游戏包访问。缺的是把 index 供给接进 render 的 seam。

## 1. 实证：render 到底请求什么（Step 1/2 结果）

4 张代表卡（普通随从 EX1_350 / 英雄 HERO_01 / BG 随从 105108 / 金卡 EX1_350+GOLDEN）
live 渲染，session 间谍记录 `session.memo` 请求的 (domain, item, args) 全集：

- union **150 token**（normal=67 / hero=33 / bg=67 / golden=14）；
- 域分布：color=105（atlas 按 family×ct 扇出）、frames=29、art=9、text=5、
  textures=1、watermarks=1；
- **gems 域零请求**（render 的宝石纹理走 kit.textures 内存名，`recipes.gems` 无渲染消费点）；
- **art.golden_portrait / index portrait_golden 零请求**（render 链不消费金像三件；
  premium 卡的肖像=同一 `art.portrait(card_id)`）；
- 进程级缓存（`_KIT_CACHE`/`_SCENES`/`_probe_cache`/`_MIP_REGISTRY`）叠在 token 之下：
  token 集=请求形状，首卡付解码、后续卡付 memo 查询。

index 覆盖三分类（对照 `gen-f6d4…`）：

| 类 | 数量 | 内容 |
| --- | --- | --- |
| A 可直接供给 | 6 | `art.portrait(card_id)`（role=portrait，PIL 同形）；`text.fontdefs()`（逐键同形）；`text.font_ttf_bytes(def_name)`（bytes 同形） |
| B 需要形状转换 | 6 | `frames.kit(family)`（六面重组 Kit：meta+hierarchy 合并、trinket_level_mats=None、arrays→_ArrayDict、races=None、mesh_refs={}）；`text.font_table()`（从 fontdefs 无损派生 entries）；`watermarks.texture(ref)`（token 参数=ref，种子需 card_id→ref 预解析，index manifest.ref 即裁决值） |
| C index 没有 | 138 | **color**：`probe()` + `atlas(family, ct)`×104（105/150 token，最大单点缺口；进程 memo 后每 family×ct 一次）。**art**：`portrait_mip(card_id)`（肖像真链，正典 portrait_mip=True 在役）、`portrait_source(card_id)`（记账面）。**frames**：特源/附件 kit（ability_kit normal/premium、bacon、ally_premium、trinket、anomaly、kit_light×9、badges/btf/ornaments/ta_supplement/material_state/portrait_uv1）+ 活表读（actor_ref/spell_school_names，零解码）。**text**：`font_asset_params()`（glyph 回退+padding，像素相关）。**textures**：`mip_registry()`（16 静态链）+ `entry_for_ref`/`chain_for_name`（非 @item 的 UnityPy 面） |

按域聚合的缺口清单（Phase 1 需 index 补齐的域）见 §6。

## 2. 选型：S1 memo 种子 vs S2 SupplySource 协议

### S1 — `session(memo_seed=...)`：把 index 结果按 token 预填 Session.memo

域函数不执行（`machine.item` 的 served 命中 memo 直接返回），消费方零感知。

- **产品改动面**：`machine.session()` 加可选种子参数（或入口种子器在
  `session()` 后 `memo.update(seeds)`）+ render 入口一个装配点。域函数、
  recipes、投影、render 链全不动。
- **fallback 天然**：种子没命中 = served 照旧执行域函数 = live 逐项退化。
  补一个 index 域就多种一个 token，不需要逐域开关。
- **覆盖天然**：`overrides.asset` 是用户文件装载，种子面不含它，天然 live。
- **风险**：种子构造方必须逐 token 复刻 live 返回形状（Kit 重组、font_table
  派生、watermark ref 预解析）——形状漂移=串图或炸；判据=Phase 1 的
  live vs index 同 sha 对拍 + 转换器单测。
- **风险（低）**：memo token 的 args 序=域函数签名（隐式契约）；签名变更→
  种子 miss→退 live（fail-safe 方向：正确性不破，只退化性能）。miss 可观测
  （种子器记账 unused/live 计数，`-v` 可见）。

### S2 — SupplySource 协议：域函数拆 locate/decode，IndexSource 直接返回

- **改动面**：art/frames/text/watermarks/color 全部域函数拆「寻址」与「解码」
  两层，引入协议 + 双实现（BundleSource / IndexSource）；recipes/会话纪律/
  投影报错语义随动。15+ 域项的机械拆分，Phase 1 工期数倍。
- **形状责任不减**：IndexSource 返回的仍是 Kit dict/PIL——「index 素材 →
  live 值形状」的对齐工作与 S1 完全相同，协议不免除它。
- **收益**：源抽象一等化（未来其他源可插）、类型可守。在只有两个源
  （live bundle / index）的现状下，这是过度设计。

### 拍板：S1

1. Phase 1 验收是行为判据（53 normal + 16 golden 同 sha、warm 零 UnityPy），
   S1 以最小改动面达成；
2. fallback/覆盖语义天然正确，渐进补域不动产品代码；
3. 系统设计元层：约定先行——S1 是「预填既有 memo 缓存」，不引入新协议；
   显式触发器（require-cache 产品化、第三种源、域函数面重构需求）出现时
   再评估升 S2，本设计不预设。
4. S2 的拆分方向与 kit 重组器等转换件不冲突：转换器按 S1 落在种子器内，
   将来升 S2 时原样搬进 IndexSource（转换件是资产，不是负债）。

## 3. 语义七点

### 3.1 fallback（缺项 live 还是 fail loud）

- **产品形态（Phase 1）= 缺项退 live**：种子缺失/token 未命中 → served 照旧
  执行 live 域函数。语义=性能优化，正确性与 live 逐位一致。
- **require-cache / offline 模式后置**（审计形态）：session 加模式旗，
  served 未命中种子即抛（报错面=warm `SupplyMissingError` 清单原样）。
  Phase 1 不做，触发器=「index 完整性门与 render 集成」另案。
- 弃种判据：种子器构造失败（`SupplyMissingError` / `SupplyBlobCorruptError` /
  `SupplyIndexCorruptError`）→ 该卡弃种回 live + WARNING 日志（`-v` 可见），
  不阻塞批次。

### 3.2 覆盖（frame / portrait / watermark）

覆盖三座位不经 supply token 种子面：

- **frame**：compile 期嵌 class_color 写点（`compiler._class_color`），不动 supply；
- **portrait**：`_apply_asset_overrides` 按**对象身份**复写运行时槽——种子换了
  `plan.portrait.img`（数据轴图），覆盖装载（`overrides.asset`，天然 live）后
  仍按身份命中复写，`override` 账与 mip 跳链照旧；
- **watermark**：V-pass 从 card 重算，`watermarks.texture` 种子只供数据轴纹理，
  覆盖腿经 `card.watermark_asset` 走 `overrides.asset`，不相交。
- 种子值=数据轴产物；覆盖=卡级渲染输入（contract E），两者在 plan/V-pass
  汇合点分层，互不越位。输出缓存 key 必须含覆盖项与资产 sha（§10.3 记录面）。

### 3.3 locale / text

- live memo token **不含 locale 维度**（locale 从 ctx 流入域函数内部）；index
  绑代自带 locale（gen meta.locale）。**种子器必须校验 `index.locale == ctx.locale`**，
  不一致→整批弃种回 live（fail loud 也合理，但性能语义下先 WARN 回退，strict 后置）。
- text 域：fontdefs 是 enus/zhcn 双侧同 item，zhCN 侧走代 locale（build 期已按
  locale 落账）；`font_ttf_bytes` 的 zhCN 变体跟随语义在 live 域项内——index 的
  fonts 账即 build 时的跟随结果，同 locale 下等值。
- v1 locale 固定 `zhcn`（产品缺省），实际自由度大于需求。

### 3.4 generation 失效

- `SupplyIndex` 构造即绑 `current.json` 代；种子器在 render 前打开一次
  （进程复用句柄，`--jobs` 时每 worker 各开只读句柄——SQLite 只读并发安全）。
- **代身份校验**：种子器开句柄后比对 `gen identity`（game_id / dll_stamp /
  manifest_stamp）与 ctx 游戏安装同源（复用 cold `resolve_context` 同源身份逻辑），
  不一致→弃种回 live（防旧代串图）。
- render 期间代被 prune/重建（maintain/revalidate）：只读句柄的 blob 文件被删 →
  构造期已过 sha 校验的种子值已在 memo，渲染不受影响；**每卡 assemble 期**触达
  缺文件 → `SupplyMissingError` → 该卡弃种回 live。操作约定：render 批内不跑
  maintain（文档化，不做进程间锁）。

### 3.5 缓存 key

- **memo 键**：`session.memo` 的 `(domain, item, args)` 天然键——种子器按
  「index item_key → memo token」映射装配（portrait: card_id+kind；kit: frame；
  watermark: card_id→ref 预解析；text: 全域项）。映射表=转换器单测的账面。
- **种子构造内部**：走 warm 既有校验（blob 文件字节 sha==行账），种子值进
  memo 即不可变产物（禁 mutate 纪律沿用 warm 契约）。
- **输出缓存**（未来）：key 须含 index game_id/代 + 覆盖项 sha（§10.3 已记录，
  不在 Phase 1 实现）。

### 3.6 错误面

| 形态 | 判据 | 处置 |
| --- | --- | --- |
| index 无 current.json / 代库缺 | 开句柄即现 | 整批弃种回 live，WARN（首跑=无缓存，正常路径） |
| `SupplyMissingError`（卡缺项） | per-card assemble | 该卡弃种回 live，WARN；清单留给 `-v` |
| `SupplyBlobCorruptError` | assemble 校验 | 同上（integrity --repair 的提示面已在错误文本内） |
| `SupplyIndexCorruptError` | open 自检 | 整批弃种回 live，WARN（重建归 selfheal 另案） |
| locale / 代身份不一致 | 种子器校验 | 整批弃种回 live，WARN（strict 模式后置改 fail loud） |
| require-cache（后置） | served 未命中种子 | 抛 `SupplyMissingError`（fail loud 清单原样） |

产品 Problem 分类不受影响：弃种回 live 后的错误=live 错误（现有
`asset_missing_in_game` / `render_failed` 面）；index 自身缺项**不产生新
Problem code**（性能语义下它是回退原因，不是用户可见失败）。

### 3.7 接线位（Phase 1 实施草图）

- `machine.session(...)` 加 `seed: dict | None = None`（或独立
  `session_seeded(seeds)` contextmanager——选后者，签名面零扩散）；
- `components._in_session` 不动（消费方纪律不变）；种子装配在
  `api._render_one` 的 render_fn 包装层（组合层 factory 缺省=live，
  index 种子器是可选 factory 注入——测试/`--supply-cache` 开关后置到产品
  CLI 议题）；
- 转换器（Kit 重组 / font_table 派生 / watermark ref 预解析）住
  `core/supply_index/seed.py`（依赖方向：render 不 import supply_index，
  种子器由组合层注入——supply_index 现有「不接 render」边界改为
  「render 可经组合层消费 warm 面」，cold/UnityPy 面边界不动）。

**A2 落地（2026-11-09，`feat/supply-index-phase1`；任务单 A2=S1 生产 seam）**：

- `machine`：`_pending_seed`（ContextVar[dict | None]）+ `seed_session(seeds)`
  contextmanager（进入 set / 出口 token reset=栈式遮蔽：嵌套时内层遮蔽外层、
  内层出口后外层恢复可见）；`session()` 进入即一次性消费 pending
  （`set(None)`——同一 pending 只种首个会话，重复 `session()` 不重种），有种子
  则 `Session(memo=dict(seeds))` 预填（浅拷贝，会话写面不回流种子 dict）；无
  pending 时逐位不变，`in_session()` 语义不变（只认 `_s_current`）。
- `api._render_one` 增可选 `seed_provider`（零参可调用，默认 None=产品 0.1.0
  不启用）：`_seed_scope` 把非空 seeds 包成 `seed_session` 上下文、在
  `_atomic_render`（即 render_fn 调用）外层挂上；None/空 → `nullcontext` 纯
  live。seed import 留函数体（§7.1.1 纪律）；provider 异常不在 api 层兜底
  （种子器按 §3.6 自行弃种回 live）。签名面零扩散：components / render_with /
  `in_session` 全部未动。
- 判据账：泄漏单测 `tests/core/test_supply_seed.py`（12 例，零游戏进默认
  discover：嵌套/重复/异常/未消费 pending 均消费或清除 + `machine.item`
  计数器证明命中 memo 不执行域函数）；e2e `tests/integration/integration_seed_seam.py`
  （显式跑，EX1_350 缺省：live 手取 `art.portrait` token → 种 1/67 token →
  `_render_one(seed_provider=...)` 渲染，RecordingMemo 双账（请求/未被 live
  重写 + 终值 is 种子对象）证 memo 命中=域函数体零执行，PNG sha 与 live 逐位
  一致=其余 token 照旧 live 的 fallback 实证；provider None/{} → 纯 live 同
  sha）。

**A3 落地（2026-11-10，`feat/supply-index-phase1`；任务单 A3=种子器+转换器）**：

- `core/supply_index/seed.py`（库 API，无 CLI）：`CardSeeder.open(cache_root,
  ctx_locale, ctx_identity, kit_gap_faces=None)` 打开 `SupplyIndex` 并校验
  locale + generation 身份同源（identity 与 current.json 逐键相等 + identity
  经 `schema.cjson` 重推 game_id 与代库绑定一致；`ctx_identity` 由组合层经
  `cold.compute_identity` 从 ctx 现算注入——seed.py 自身不 import cold）；
  `seeds_for_card(card_id)` / `seeds_for_dbf(dbf_id)`（index cards 表首行账）
  = `assemble_card` 严格门 → role→token 转换 → memo 种子 dict；
  `provider_for_card(card_id)` 返回零参可调用（A2 seam 注入形，api 零改动）。
- 转换件逐字搬迁 `phase0_spike_render`（`_font_table_entries` /
  `_kit_from_index` / races/mesh_refs live 派生件）；**缺口面注入化**：
  `kit_gap_faces(frame) → (races|None, mesh_refs)` 缺省=live 派生（spike
  形态，A6 补 index races/mesh_refs 域后换面），替身注入=零游戏单测可测
  转换形状。
- 弃种三层（§3.6 全落地，**不构造 Problem**——AST+子进程机器证明）：整批
  （index 不可用/locale/身份失配 → `open` 返回 None + WARN 一次）；该卡
  （严格门缺项/转换异常 → None + WARN）；该 token（单 role 缺席/形状不符/
  缺口面派生失败 → skipped 记账、kit 缺口面失败时 kit 整个不种——种缺
  races 的 ally Kit 会在 GetRaceText 炸，比 live 兜底更糟）。记账
  `SeedLedger`（seeded/skipped + INFO `-v` 可见）；hit/live/unused 是 render
  期观察量，由消费侧 memo 观测件填（种子器不越位进会话）。
- 依赖方向：顶层 import=warm 面（schema/paths/warm+PIL）+ stdlib；转换件的
  live 形状 import（`Kit`/`_ArrayDict`/`FRAME_SPECS`/engine）全在函数体内
  （spike 同款解法——最小偏离已在此记账）；`tests/core/test_supply_index_seed.py`
  23 例进默认 discover（含顶层 import 面子进程机器证明 + tearDownModule
  清 UnityPy 纪律，同 test_route_cabs）；e2e
  `tests/integration/integration_supply_seed_one.py`（显式跑）：EX1_350
  seeded-first 净进程对拍，seeded sha == live sha == A2 冻结 sha 逐位
  （A3 硬停点闭合），去重记账 hit=6 / live=27 / unused=3 与 Phase 0 spike
  逐项同构。

**A4 落地（2026-11-10，`feat/supply-index-phase1`；任务单 A4=index 补域 color）**：

- **域定性**（§1 C 类第一优先的收口）：`color.probe`=switcher 表（12 族槽位
  dict，卡不变全域项）+ `color.atlas(family, ct)`=类色图集（probe 族表槽位寻
  址的域级项，本机 37.0.2 语料 313 槽=212 纹理槽（5 纹理族 spell/minion/hero/
  weapon/location + mercenaries/BG 三族）+ 83 空占位槽 + 18 材质族槽
  （faction* 三族——color.atlas 参数域外，live assert Texture2D 同边界））。
- **cold**（`build_color_items` + `color_extract.py` 单点）：链根 ref
  （`_SWITCHER_REF` 与 live 逐字符同源）→ catalog/变体 → GO 组件直读（表读取
  失败=raise 响亮，live「失效即红」同纪律）→ probe item（json 落盘**保序**
  ——键序=typetree 序，drift_probe B3 升版互证面；content_inputs={ref, probe
  canonical sha}）+ atlas items（全槽枚举→变体解析→**guid 去重**解码
  （153 件唯一纹理），材质槽记账跳过、空槽无行、解码失败=color_errors）。
  实测 color 段 wall ~7s@jobs2（partial 冒烟）。
- **期望账（probe 入门、atlas 不入）**：probe item per-card 挂 plan_items
  （role='color'，`_link_color_probe`，与 kit/gems 同款「卡不变域项 per-card
  挂接」）——期望人口=**已知卡型卡**（kit 挂接同一人口：compile 对这些卡经
  kit 提取/类色 pick 无条件读 probe；cardtype 未知卡不挂——R2 absent 归因
  语义不变）；**PLAN_VERSION 2→3**（plan 内容变了版本随动——v2 代 plan_key
  构造性失效→warm plan missing→assemble fail loud→种子器整卡弃种回 live，
  全量重建切代，旧 index 不兼容属预期）。atlas **不挂 plan**（212 槽 per-card
  重复挂接=架构错位，text 域同款记账）——warm `color_atlas` 域访问器 fail
  loud + audit child color 段（全槽 warm 解码+manifest 像素 sha 对账）作域级
  完整性面；blob 坏块走 integrity `--repair`（atlas=asset 同路重解码、probe=
  响亮须全量重建）。
- **warm**（`color_probe()` / `color_atlas(family, ct)`，live 同形契约）：
  probe=进程缓存一次（json 保序复原=live 键序）；atlas=(family, ct)→params 账
  进程内 memo + 解码入共享域 LRU（color 入 `_SHARED_DOMAINS`）；blob 文件字节
  sha 逐次校验；缺项=SupplyMissingError（现有语义，不发明新错误）。**warm
  color 读取零开包**（audit import/open blocker 同窗机器证明）。
- **seed**（`_convert_color`）：`("color","probe",())`←bundle["color"]；
  `("color","atlas",(family, ct))`←warm 逐槽解码——**枚举=帧族全有效槽**
  （live 消费方遍历：kit 提取按帧族全槽扇出 kits.py:300-309 + 类色写点单槽
  同族 compiler._class_color；frame 无族（ally_premium/heropower——金卡/英雄
  技能类色=染色不换图集）或 plan 无 kit role → 不枚举）。memory 账：帧族
  23-35 槽 1024² RGBA 与 live kit.textures 全槽驻留同量级（非额外膨胀）；
  单槽缺席=该 token 不种回 live。
- **实测**（数字 A8 统一收口，此处记形态）：EX1_350 seeded color token 从
  A3 的 live（probe+atlas[7]）降为 0 live（probe+帧族 35 槽全种）；判据面=
  `tests/integration/integration_supply_color.py`（显式跑：probe 键集合+每键
  list 对账 / EX1_350+golden 同 sha / color 记账）。

**A5 落地（2026-11-10，`feat/supply-index-phase1`；任务单 A5=index 补域 mip）**：

- **域定性**：mip 面=「真链数据面」，三件——`textures.mip_registry`（静态
  注册表，live 手工链表 **23 条**——任务单「16 条」为批10e 定案期旧数，
  2026-10-30 起增补名牌板/水印/横幅链；全局项，卡不变，不挂 plan——text/
  color.atlas 同款记账）、`art.portrait_mip`（per-card 肖像真链，portrait
  locator-ok 卡=期望人口挂 plan_items role='portrait_mip'，期望但未建=哨兵行
  expect::portrait_mip）、**atlas 链账**（entry_for_ref 的数据源：color atlas
  item manifest 扩 `mip` 段记每槽 m_MipCount/name/filter/bias 判定，带 mip 图
  集全级 NPZ——本机 37.0.2 语料 12 条带链图集：weapon DK + location 11 族，
  其余 200 纹理槽 mips=1=「无链」裁决值）。
- **存储形**：链=NPZ 级数组（确定性 deflate——ZIP_STORED 会把 ~16.8k 条
  512² 肖像链落 ~6GB）。portrait_mip 三源（manifest `source` 裁决）：
  `registry`（链名在注册表且地址相等——live chain_for_name 注册表分支同判，
  零自有 blob）、`portrait`（mips≤1，单级链）、`chain`（mips>1，存第
  1..n-1 级，**L0 由 portrait PNG 派生**——cold 期逐纹理验证 UnityPy 解码与
  texture2ddecoder 解码位等（fmt 10/12 实测 8/8 逐位），失配落显式 L0 级
  （manifest `l0=explicit`）——结构化保证而非假设）。registry/atlas 全级
  0..n-1 在位（无派生面）。PLAN_VERSION 3→4。
- **cold**：链提取 fold 进既有 decode worker（portrait 任务同包顺带提取，
  per-worker guid 去重——免二次开包）；registry=独立单进程段（23 链 16 包秒
  级）；atlas 账 fold 进 color atlas worker。提取失败≠portrait 失败（行级
  mip.error 记账、哨兵行显式落缺口——fail loud 归 expected-vs-built 门）。
- **warm**（`mip_registry()` / `portrait_mip(card_id)`，live 同形契约）：
  registry 进程缓存一次；portrait_mip 按 manifest source 装配
  （WarmChain=live LazyFloatChain 同协议 len/getitem/peek/shape0 + `.lods`）；
  npz 项不入 assemble 通用束（28.9k 卡走查逐卡解 NPZ 白付——专属访问器供货，
  期望账不受影响）。**warm mip 读取零开包**（audit import/open blocker 同窗
  机器证明；audit child 增 mip 段=registry 聚合 sha/链数/级数/filter-bias
  对账 + portrait_mip 样本走查）。
- **seed**（`_convert_mip`）：`("textures","mip_registry",())`←warm raw dict
  直透（消费方 raster._registry/chain_for_name 自行包 LazyFloatChain）；
  `("art","portrait_mip",(card_id,))`←warm 链 → `LazyFloatChain(chain.lods)`
  （live 形状类函数体 import）。**非 @item 面接线**：`entry_for_ref` 经
  `supply.textures.set_entry_seed_lookup` 模块级注入位先行（本模块已是模块级
  registry 模式——顺着接）：covered ref（类色图集）=mips≤1 判 None / registry
  名走 memo-seeded `chain_for_name`（live 注册表分支同构）/ 其余=index 全级链
  LazyFloatChain（值面=cold 同解码器提取产物）；UNSET（override/composite/
  未知 ref）落 live 逐位不变。`chain_for_name(name, addr)` 显式地址分支无需
  注入——其唯一调用方就是 `art.portrait_mip` token 体本身（seeded 命中=函数
  体零执行）。句柄生命周期=CardSeeder open 装 / close 卸（fn 身份判据防晚开
  误卸）。**live 路径未安装句柄=逐位不变**。
- 判据面=`tests/integration/integration_supply_mip.py`（显式跑：registry
  23 链逐级位等 / portrait_mip 对账 / EX1_350+golden 同 sha / mip token 记账
  / 开包分面归因（mip 面=0，其余 live 残面 A6 列账）/ blocker 子进程）。

**A6 落地（2026-11-10，`feat/supply-index-phase1`；任务单 A6=index 补域 kits
含 races/mesh_refs）**：

- **域定性**：§6 清单 4/5/6 三项一次收口——特源/附件 kit（`ability_kit`
  normal/premium、`bacon_kit`、`ally_premium`/`trinket`/`anomaly` 全 kit、
  `kit_light`×9、`badges_kit`/`btf_kit`/`ornaments_kit`、`ta_supplement`、
  `material_state`、`portrait_uv1`）+ **races/mesh_refs 两张硬缺口面**
  （`compiler.GetRaceText` 无条件 `kit("ally").races["strings"]`（spike 炸点
  一）、`portrait_uv1` 内部 `_kit(frame).mesh_refs[name]`（炸点二））+
  `text.font_asset_params`（glyph 回退名单+padding）。全部=**卡不变全局项**
  （items 落库不挂 plan——text/color.atlas/mip_registry 同款记账）。
- **cold 双轨**（§5 包边界修订记账）：① 标准六帧族 kit 仍走 kit_extract
  转写域，**races 面**（ally——GLOBAL.txt 正则提取，`engine.
  extract_race_strings` 逐字转写、零 UnityPy）与 **mesh_refs 面**（walk 期
  mesh_jobs 捕获，live `Kit.mesh_refs` 同式）两面随 kit item 落库（kit_codec
  KIT_CODEC_VERSION 1→2；两面 content sha 并入 kit_content_sha 聚合——缺席=
  空串进键，「无面」与「面内容 X」构造性不同键）。② 特源/附件面走 **live
  提取 harness**（新模块 `supplement_extract`）：独立子进程 install ctx
  （**route_mode="off"**——cold 不进 route 航线库，原「供给面禁入」的实质
  边界保持）+ session，逐字调用 live 域函数（ability_kit/bacon_kit/kit(
  ally_premium/trinket/anomaly)/kit_light×9/badges/btf/ornaments/ta/
  material_state/portrait_uv1/font_asset_params），产物编码 content 寻址
  blob。转写=数千行且形状漂移风险面大，harness 值面**构造性=live 值**（零
  转写漂移）；container/object 证据账不入（item source_json 记 harness
  来路）。KitRecon 六帧族 kit faces 读回注入 worker 进程 memo（ta/
  portrait_uv1 的 kit 依赖面免重走查；A3 e2e 已钉 cold 六面=live 逐位）。
- **存储形**：kit 六面件同 codec（ally_premium/trinket/anomaly/bacon=ITEM_KIT、
  kit_light×9=ITEM_KIT_LIGHT——同 codec 两 item 名，`kit_item_key` 的
  frame→key memo 以 item 过滤不撞键）；supp 件=新 codec `supp`（supp_codec：
  命名 parts 束四 kind——json/npz/png/bin，content=parts 内容聚合 sha）。seed
  侧 `_supp_value`/`_convert_supplements` 是一张表的两半（单测钉死）。
- **warm**：`kit_races(frame)`/`kit_mesh_refs(frame)`（扩展面专属访问器；缺
  面=None——非 races 帧族 live Kit.races None 同形）、`kit_light(frame)`、
  `supplement_parts(domain, item, params)`（parts 束供货；**live 对象形状
  重组归 seed 转换件**——warm 禁 import supply 包，audit blocker 通过面）；
  共享 LRU 8→16（全帧族 kit 常驻=live `_KIT_CACHE` 进程 memo 同形）。
- **seed**：A3 注入位换 index 面——`kit_gap_faces` 缺省=`_index_gap_faces`
  （races 只对 `S.KIT_RACE_FRAMES`（ally/ally_premium/trinket=live spec
  races=True 词面）供面、缺面=SupplyMissingError→kit token 整个不种——种缺
  races 的 ally Kit 会在 GetRaceText 炸，比 live 兜底更糟；注入形保留=替身
  测试面，A3 的 live 派生件退役）；kit token 种全帧族（plan 帧族+其余已建
  帧族——live 请求面含非本卡帧族如 normal 卡请求 `kit("ally_premium")`）+
  `bacon_kit` token（特源帧=kit 六面件存储、live 域项名词面）+ kit_light×9 +
  特源/附件七件（AbilityKit/BadgesKit/BtfKit/OrnamentsKit 重组、ta/
  material_state/portrait_uv1 dict 重组、font_asset_params 直种）。
  **AbilityKit 种子形状显式账**：obj_texts/fonts_bytes 不进种子形状（渲染链
  零消费的提取产物面）。PLAN_VERSION 4→5（kit 键换 + supplement 域）。
- **期望账/审计**：A6 域无 per-card 期望（卡不变全局项不挂 plan——哨兵面
  不适用）；完整性面=audit child supp 段（kit 扩展面全帧校验 + kit_light 全
  帧六面 + supp 全 item parts 解码，blocker 同窗机器证明）+ build 发布门；
  integrity repair：supp/kit_light/harness 帧=响亮「须全量重建」（live
  harness 提取非单 blob 重推导面），标准六帧族 kit 重提取带 strings_txt 面
  （聚合 sha 含 races/mesh_refs——verify/diff 重提取同参对齐）。
- 实测（数字 A8 统一收口）：EX1_350 seeded color/mip 之外新种 kit 域 token
  全集；判据面=`tests/integration/integration_supply_kit.py`（显式跑：ally
  kit live-vs-warm 逐字段对账（六面+races+mesh_refs）/ ability_kit 特源对账
  / EX1_350 normal+golden 同 sha / token 记账 / 开包分面（kit 域=0 目标）/
  blocker 子进程）。

## 4. spike 实证（Step 4）

EX1_350（dbf 9，normal，1x）双进程对拍（route 缓存暖、进程冷、OS 盘缓存暖）：

| 指标 | live | seed（index 种子 9 token） |
| --- | --- | --- |
| PNG sha256 | `671e19a2…2186e` | **逐位一致**（与 Step 1 live 同设四跑全同） |
| render 耗时 | 31.4s（冷盘 447.7s） | **22.1s** + assemble 0.124s |
| 请求 token | 67 | 33（kit 全量提取+图集扇出 35 token 随种子消失） |
| 命中/剩余 | — | hit=6（portrait/kit(ally)/fontdefs/font_table/2×ttf）；live=27 |
| UnityPy import | 是 | **仍是**（缺口域未补齐的如实账） |

- 3 个未用种子（Belwe/BelweNumbers/BlizzardGlobal TTF）：该卡不消费，预置无害。
- 剩余 live=27 的构成=§2 C 类清单的实证：`mip_registry`/`portrait_mip`
  （mip 面）、`color.probe+atlas[7]`（该卡类色写点仍需 1 件图集）、
  特源/附件 kit（`ability_kit`×2/`bacon_kit`/`kit_light`×9/`badges`/`btf`/
  `ornaments`/`material_state`）、`portrait_uv1`、`font_asset_params`、
  `actor_ref`×3（活表读）、`portrait_source`（记账）、`kit(ally_premium)`
  （种子只覆盖 ally 族）。
- **两个实证炸点（Phase 1 硬缺口）**：种子 kit `races=None` →
  `compiler.GetRaceText` 无条件 `kit("ally").races["strings"]` 炸
  （compiler.py:598，**任意 ally 帧卡**）；`mesh_refs={}` →
  `portrait_uv1` 域函数内部 `_kit(frame).mesh_refs[name]` KeyError
  （supplements.py:336）。spike 以 live 派生件补这两面（races=全局串提取、
  mesh_refs=kit_light 轻量 walk），渲染即通——证明 seam 机制成立，同时把
  index 需补域从「推测」升「实证」。
- 「kit.textures 无类色图集」疑点被 spike 反证：种子 kit 缺图集面渲染仍逐位
  一致——plan 纹理引用不触达 kit.textures 里的类色图集（类色走运行期槽
  color.atlas 直写），kit textures 面按 index 六面原样供给是安全的。

（原始账：`build/phase0/spike_live.json` / `spike_seed.json`；build/ 不入库。）

**收口注（A8，2026-11-10）**：本节是 Phase 0 spike 历史账——表中「live 31.4s（冷盘
447.7s）/ seed 22.1s」与「UnityPy import 仍是」为 Phase 0 时点实测，已被 Phase 1
取代：live 首卡 A7 实测 **17.28s**（route 暖态差异，以实测为准；任务单 §8 参考
31.4s 同此更正）；A4–A6 补域落地后 seeded 供给面零开包（A7 双层口径见 §7.2——
读面 blocker 达标，渲染进程 sys.modules 字面零不成立如实记账）。Phase 1 权威数字
统一收口在 §7.2，与本节冲突处以 §7.2 为准。

## 5. 边界与不变量

- 不改 `core/infra/route.py` / `resolve_asset_ref.py`（route v6 在途）；
- 不加产品 CLI、不改 README/AGENTS/schema、不改渲染或覆盖语义（Phase 0 约束）；
- warm 面纪律不退化：种子器只 import `SupplyIndex`（warm），不 import cold/
  UnityPy 面；import 卫生由 `test_supply_index_warm` 的机器证明延续；
- `supply_index` 不新增产品面（无 CLI、无 README）——种子器是库 API。
- **A6 包边界修订**：cold 侧「零 import 参照族」纪律收窄为转写域
  （kit_extract/text_extract/wm_extract/mip_extract）；supplement 域走 live
  提取 harness（supplement_extract——独立子进程 route off + session 调 live
  域函数）。原纪律的实质=「cold 不进 route 航线库、不走 render 消费面」，
  harness 以 route_mode="off" 保持该实质；值面构造性=live 值的收益（零转写
  漂移）大于转写成本（数千行+形状漂移风险）。warm/seed 两侧禁 import
  supplement_extract（UnityPy 面），机器证明面不变。

## 6. Phase 1 前需要 index 补的域（优先级序）

> **A8 收口：六项已全部落地**（1→A4、2/3→A5、4/5/6→A6）。以下为 Phase 0 规划
> 原文，旧估算数字按 A4/A5 实测就地更正（更正处加括号注）；实测权威口径见 §7.2。

1. **color.atlas + probe**（12 族×ct 图集 ~104 件 + switcher 表；A4 实测：全帧族
   槽枚举=**212 纹理槽**，313 槽=212 纹理+83 空+18 材质——~104 件是 Phase 0 按
   4 代表卡 token union 的半量估算）：105/150
   token 的最大单点；补齐后 normal/golden warm 面大半闭合。
2. **art.portrait_mip**（per-card 肖像真链）：正典 portrait_mip=True 在役，
   不补则 warm 路径每卡仍开包（UnityPy 不出 worker）。
3. **textures.mip_registry**（16 静态链；A5 按 live 对账更正：live 现行 **23 链
   223 级**——16 条为批10e 定案期旧数，2026-10-30 增补名牌板/水印/横幅链）：
   同上，内容指纹派发面。
4. **frames 特源/附件 kit**：ability_kit(normal/premium)、ally_premium、
   trinket、anomaly、bacon、badges/btf/ornaments/ta_supplement/
   material_state/portrait_uv1/kit_light。
5. **kit races / mesh_refs 面**（**实证硬缺口，无条件消费**）：races——
   `compiler.GetRaceText` 对任意 ally 帧卡无条件 `kit("ally").races["strings"]`
   （compiler.py:598，spike 炸点一）；mesh_refs——`portrait_uv1` 域函数内部
   消费 `_kit(frame).mesh_refs[name]`（supplements.py:336，spike 炸点二；
   index hierarchy 面无 mesh PPtr 账，需 cold 期捕获入库）。不补则种子器必须
   附 live 派生件（spike 形态：全局串提取 + kit_light 轻量 walk，秒级）。
6. **text.font_asset_params**（glyph 回退名单+padding）。

## 7. 工期与风险（Phase 1）

- 工期估算：S1 接线 + 种子器/转换器 + 单测 ≈ 3 人日；53+16 对拍与归因
  ≈ 2 人日（视缺口补齐速度浮动）；index 补域（§6 全单）≈ 3–5 人日。
  合计约 1.5–2 周。
- 风险：
  - kit 重组形状漂移（meta/hierarchy/trinket_level_mats 合并）→ 转换器单测 +
    同 sha 对拍守；「textures 面无类色图集」已被 spike 反证为安全（§4）；
  - races/mesh_refs 是无条件消费的硬缺口（§6.5）——不补 index 就得让种子器
    附 live 派生件（spike 已验证可行，但 warm 零 UnityPy 判据下两者也须入库）；
  - mip 面不补则「零 UnityPy」判据不成立（§6 优先级 2/3 的硬理由；
    spike 的 UnityPy import=是 即此账）；
  - 代失效窗口 → 操作约定（render 批内不跑 maintain）先行，进程间锁后置。

### 7.1 A7 实测草稿（2026-11-10；A8 统一收口，数字以 `build/phase1/seed-a7/` 落盘件为准）

- **canonical 一次成形**（scratch 全清后重跑，gen-50ac6863 / zhcn / --jobs 4）：
  wall **1343.55s**（分段：locate 4.28 + decode 356.17 + kits 32.53 + text 1.15
  + watermark 1.67 + color 3.87 + mip_registry 1.62 + link 3.51 +
  supplement **785.8**）；plan **36,373 complete / partial 0**，gate=full、
  missing_total=0；decode_errors 全 0。audit 全绿（import+open blocker 同窗
  + 全卡 offline 装配 + require-cache 负探针）。
- **53+16 同 sha**：历史对照卡集（normal 53 + golden 16）live 与
  seeded 独立子进程各渲一次（antialias 4x 同参）→ **69/69 逐字节一致**
  （mismatch=0）；seeded 全卡有种子命中（hit 均值 10.5 token/卡，弃种 0，
  观测件口径 requests/hit/live/unused 逐卡落 `results-seeded.json`）。
- **--jobs 4**：每 worker 各开 CardSeeder（SQLite 只读并发安全），69 行
  全 ok 且逐卡 sha 与串行全等（bad=0）。
- **零 UnityPy 双层口径**（如实，不声称渲染进程字面达标）：
  - 层②读面 blocker（判据本体）：audit 全绿 + seeded 读面（CardSeeder
    open + 69 卡 assemble+转换）open-blocker 同窗 **game_file_opens=0**。
  - 层①渲染子进程如实账：UnityPy 在 sys.modules（71 模块；传递 import
    来源=`infra/dbf.py` 模块级 import（用点全在函数体内）+ `supply/textures.py`
    （texture2ddecoder）+ `machine → infra/resolve_asset_ref（模块级 import
    UnityPy + import 时 config 赋值）→ infra/route（SerializedFileShim
    类定义期继承 `_RealSerializedFile`）`；route.py 属 A1 行为契约面，
    小型 lazy 化不可达 → 按任务单「大改就停」如实报告，未修复。
  - seeded 渲染开包残面（69 卡共 259 次 ≈ 3.75/卡）：route used-hash md5
    行校验（route.py `_md5_file`）144 + resolver manifest 懒装载
    （bundle_lazy `__init__`）115 + dbf.unity3d 会话首读 1；kit/texture/
    color/mip/text/watermark 供给面开包=0。
- **perf**（对照表；`perf.json` 不入库）：

  | 口径 | live | seeded（净跑，无观测件） | Δ |
  |---|---|---|---|
  | 首卡（含 ctx/dbf/font init） | 17.28s | 14.78s | **-2.50s** |
  | 稳态均值（2..N） | 7.73s | 8.18s | +0.45s（seeded 慢） |
  | 稳态中位 | 7.52s | 7.60s | +0.08s |
  | 峰值内存（子进程 PeakWorkingSet） | 5290.5MB | 3399.8MB | **-1890.7MB（-35.7%）** |
  | 69 卡 wall | 544.6s | 572.3s | +27.7s |

  稳态解释（如实）：对照环境 route.db 暖 + bundle 缓存跨卡摊销，live 每
  卡 decode 边际≈0；seeded 每卡付 assemble+转换（观测口径 0.5–1.5s/卡，
  warm 解码 LRU 16 项=live `_KIT_CACHE` 同形常驻 ~480MB 界内）——收益
  表现在**首卡（无 bundle 解码）与内存（bundle 缓存不驻留）**；冷 route/
  冷启动场景预期稳态反超，未在本轮实测口径内。
- **默认全量**：778 tests 全绿 skip 0（A6 基线不变；本 harness 文件名不匹配
  `test*.py` 不进 discover）。CS2_182 哨兵 sha `89306531…7577d0ba` 不变。

### 7.2 A8 收口：Phase 1 实测数字权威口径（2026-11-10）

单源声明：Phase 1 实测数字以本节为准；§3 各轮落地段与 §7.1 是过程账，与本节
冲突处以本节为准。落盘件=`build/phase1/`（cold-build*.log + 各轮 index 报告）
与 `build/phase1/seed-a7/`（cold-build.json / compare.json / readface.json /
results-seeded.json / perf.json；build/ 不入库）。

- **cold build 演进**（build 报告 wall_s 口径）：A3 首建 **421.76s**（CLI real
  7m6.9s；decode 275.29s）→ A4（color）**441.27s**（color 段 3.76s）→
  A5（mip）**553.7s** → A6（kits）**1103.66s**（supplement harness 545.16s）→
  **A7 canonical 一次成形 1343.55s**（supplement 785.8 / decode 356.17 /
  kits 32.53 / color 3.87 / mip_registry 1.62 / locate 4.28；plan **36,373
  complete / partial 0**；gate=full missing_total=0；decode_errors 全 0；
  gen-50ac6863）。
- **规模演进**：items 37,899（A3）→ 38,112（A4）→ 67,051（A5，mip 28,939）→
  **67,073**（A6/A7 代同量级）；blobs 22,678（A3）→ 22,817（A4）→ **39,549**
  （A6/A7）；payload 5.78GB（A3）→ **7.216GB**（A5 mip 链 +1.478GB；A6/A7 持平）。
- **种子面（§6 三域补齐）**：color——probe 12 族（json 保序）+ atlas **212
  纹理槽**；mip——registry **23 链 223 级** + portrait_mip per-card（NPZ 链，
  L0 由 portrait PNG 派生）；kit——特源/附件全清单（ability_kit normal/premium、
  bacon、ally_premium/trinket/anomaly、kit_light×9、badges/btf/ornaments/
  ta_supplement、material_state、portrait_uv1）+ races + mesh_refs +
  font_asset_params。
- **对拍（判据本体）**：**69/69 同 sha**（历史对照卡集：normal 53 + golden 16；
  live 与 seeded 独立子进程各渲一次，antialias 4x 同参，逐字节一致
  mismatch=0）；hit 均值 **10.5 token/卡**（722/69）、弃种 0、seeded 全卡有种子
  命中。
- **perf**（69 卡，antialias 4x）：

  | 口径 | live | seeded（净跑，无观测件） | Δ |
  |---|---|---|---|
  | 首卡（含 ctx/dbf/font init） | 17.28s | 14.78s | **-2.50s** |
  | 稳态均值 | 7.73s | 8.18s | +0.45s（seeded 慢；暖 route 对照归因见 §7.1） |
  | 稳态中位 | 7.52s | 7.60s | +0.08s |
  | 峰值内存（子进程 PeakWorkingSet） | 5290.5MB | 3399.8MB | **-35.7%** |
  | 69 卡 wall | 544.6s | 572.3s | +27.7s |

  `--jobs 4`：69 行全 ok，逐卡 sha 与串行全等（wall 254.7s）。
- **零 UnityPy 双层口径（如实账）**：
  - 层②读面 blocker（判据本体，**达标**）：audit 全绿 + seeded 读面
    open-blocker 同窗 `game_file_opens=0` / **3,886 种子**（69 卡 assemble+转换）；
  - 层①渲染进程 sys.modules 字面零不成立（**如实，未修另案**）：UnityPy 经
    `infra/dbf`（模块级 import，用点全在函数体内）+ `supply/textures`
    （texture2ddecoder）+ `machine → infra/resolve_asset_ref（模块级）→
    infra/route（SerializedFileShim 类定义期继承）`链传递进入 sys.modules
    （71 模块）；route.py 属 A1 行为契约面，小型 lazy 化不可达，按任务单
    「大改就停」未动、不声称达标；
  - seeded 渲染开包残面（69 卡共 259 次）：route used-hash md5 行校验 144 +
    resolver manifest 懒装载 115 + dbf 会话首读 1；**kit/texture/color/mip/
    text/watermark 供给面开包=0**。
  - 判据口径在**读面**、不在 import 面：seeded 渲染进程 sys.modules 含
    UnityPy（上列模块级 import 传递）只是 import 面事实；warm 读面零游戏
    文件打开已由层② blocker 实证，两层账不互相否定。
- **与任务单的偏差（记账）**：
  1. `mip_registry` 任务单写 16 条，live 现行 **23 条**（2026-10-30 增补名牌
     板/水印/横幅链）——按 live 对账（§6.3 已就地更正）；
  2. BC7 肖像 1 张（DMF_254t5）live `portrait_mip` 本就 raise——缺席可归因
     不期望、不哨兵，种子不种回 live 失败模式一致；
  3. A7 live 首卡实测 **17.28s** vs 任务单参考 31.4s（§4 spike 口径）——route
     暖态差异，以实测为准；
  4. A3 首建落盘报告 wall=**421.76s**（任务单 A8 权威清单写 419.02s，与落盘
     件 421.76s / CLI 7m6.9s 不符——按落盘件记账）。
- **收尾核对（A8，2026-11-10）**：默认全量 `python -m unittest discover
  -s tests -t . -v` → **778 tests OK skip 0**（30.2s）；CS2_182 哨兵 sha
  `89306531…7577d0ba` 不变；分支 `feat/supply-index-phase1` 文档 commit 即本
  节所在提交（不合并 main、不打 tag、不 push）。
