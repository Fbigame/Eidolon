# 架构

> 状态：目标结构（2026-11-08 rev4，三轮审稿合并）。rev4 搬迁与 core 接入（Phase 0-4）均已落地，本文按现状同步。

## 1. 约束

Eidolon 是离线炉石卡牌渲染器：输入 CLI / TOML，输出 PNG 与 manifest；运行时不依赖游戏客户端运行。

- 运行时读用户本机游戏安装；仓库不分发资产、字体或客户端提取物。
- 不读**游戏输入**环境变量，不保留硬编码游戏路径：显式 `--game` / TOML `game_dir` > 战网 product.db 探测 > 报错。OS 级目录变量（`LOCALAPPDATA` / `XDG_CACHE_HOME` / `HOME`）只允许用于算默认缓存根。
- `shell/` 与 `contracts.py` 只用标准库；UnityPy / pythonnet 等重依赖只允许出现在 `core/`。
- 错误提示优先于退出码：主契约是 `Problem(kind/code/path/hint/cause)`；退出码只是粗分类。

## 2. 分层

```text
eidolon/
  __init__.py        # 公开 API re-export（不 import core）
  __main__.py        # python -m eidolon → entry.main
  version.py         # __version__（manifest 用，避免 __init__ 循环）
  entry.py           # 组合根：装配 provider / port / logging
  adapters.py        # 组合层适配器（RenderSpec → RenderRequest；可选拆出）
  contracts.py       # 共享契约：纯数据 / Protocol / Problem（stdlib only）
  shell/             # 壳：输入政策
    cli.py           # argparse + run(args, provider_factory, port_factory, cwd)
    input.py         # CLI / TOML → InputDraft（不碰游戏数据）
    spec.py          # InputDraft + CatalogBinding → RenderSpec
    manifest.py      # RenderSpec → JSON；结果 manifest 格式化
    catalog.py       # NullCatalog / JsonCatalog（开发与测试）
    paths.py         # 默认 cache root（唯一允许读 OS 目录变量处）
    errors.py        # SpecErrors / CODES / format_problem（Problem 在 contracts）
    ports.py         # RenderPort 协议（只放协议）
    toml_io.py       # TOML 读取与结构校验
  core/              # 核：机制（从 Angelía 蒸馏）
    infra/           # game_install / dbf / facts / catalog / layout / card
    supply/          # 资源解析与会话
    supply_index/    # 内部派生缓存（cold 建 / warm 供；不接 render）
    recipes/         # 配方门面
    render/          # game / engine / scenes / text
    gate/            # 回归门（开发用）
tests/
  shell/  core/  entry/  architecture/  integration/  fixtures/
docs/                # schema、architecture
examples/            # 批量 TOML 示例
```

### 2.1 依赖规则

```text
组合层（entry.py / adapters.py）
  ├──> shell ──> contracts
  └──> core  ──> contracts
```

- **组合层**（`eidolon/entry.py`，必要时 `eidolon/adapters.py`）是唯一允许同时 import `shell` 与 `core` 的模块集合；不做字段校验、不解析 TOML、不定义 manifest 格式。
- `shell/` 只 import 标准库、`eidolon.contracts`、`eidolon.shell.*`、`eidolon.version`（纯数据）；**不得出现 `eidolon.core`**。
- `core/` 只 import 标准库、`eidolon.contracts`、第三方依赖、`eidolon.core.*`；**不得出现 `eidolon.shell`**。
- `contracts.py` 只 import 标准库；放 frozen dataclass、`Protocol`、携带 `Problem` 的异常；不放 I/O、不放业务函数。
- `eidolon/__init__.py` 不 import `core`，保证 `import eidolon` 不加载游戏依赖。
- 以上规则用 import-graph 测试钉死（第 11 节）；`shell` / `core` 内部的相对 import 不算跨层。

### 2.2 为什么不是“公共 infra”

shell 需要通过 dbf 判定卡牌存在性，但这是一项**事实查询**，不是渲染。把 dbf 做成谁都能 import 的公共层，会同时失去四样东西：

- **边界**：shell 能 import `infra`，就能顺手 import `game_context`、`asset`、`route`；依赖方向从机制保证退化成自觉。
- **失败域**：dbf 读不到是环境错误，不是输入错误；混进 shell 后退出码语义会坏。
- **启动与测试**：`--help`、TOML 语法错误不该加载 UnityPy；壳测试不该需要游戏安装。
- **可替换性**：shell 要的是“存在吗 / 是什么类型”，core 要的是完整记录 / tag / 资产；共享的是词汇，不是读取实现。

依赖倒置已经够用：`contracts` 定义 `CardCatalog`，`core/infra` 实现 `DbfCatalog`，`entry` 注入。

### 2.3 supply-index（内部派生缓存）

`eidolon/core/supply_index/`（Phase 5 落位）是**内部派生缓存**，不是输入/输出契约：把游戏包里可静态提取的供给面（portrait/golden、kit 六面、gems、text 字体、watermark）一次性解码落盘为 per-generation SQLite 索引 + 内容寻址 blob 库，供暖路径只读装配。

- **cold 面**（`cold.py`——合法用 UnityPy 的唯一路径）：全量/定向建库。全量表（manifest/catalog/dbf）+ 全量 locate + 逐卡 decode；per-gen DB 经 CacheLock 原子发布，`current.json` 原子切代；无代时的定向 build = partial-init（bundles sha 记空串，cheap diff 如实记 revalidate）。
- **warm 面**（`warm.py`）：`SupplyIndex` 只读句柄——plan/assemble/assemble_card/kit/text/check，**零 UnityPy、零游戏文件访问**；缺项语义=expected-vs-built（locators-ok 与 plan 哨兵账即「应有」——golden/kit/gems/watermark 与 portrait 同权 fail loud；`assemble_card(allow_partial=True)` 为显式豁免口，产品不传）。缺席归因面（`account_for_cards`，R2）：卡集四分类 ok / missing_gap（有期望未满足）/ absent_locator_missing / absent_expectationless（数据缺席），audit/verify/bench 门共用此判据。隔离不是约定而是机器证明：`audit.py` 在同一子进程里叠三道拦截（不存在 `--game` + `sys.meta_path` import blocker + 内建 open 对游戏文件族 `*.unity3d`/`globalgamemanagers*`/`resources.assets*`/`*.dll` 抛错）跑**全卡 API 走查**（按缺席归因分道：ok 卡严格装配、数据缺席卡跳过计账；full 代 gap/anomaly 走查尾响亮、partial 代 scope 外可缺并显式标注 `partial: true`）。**门语义（R2）**：full 代完整性 = expected-vs-built 零缺口（missing_gap==0）；数据缺席（无美术 locator 的 dbf 行 / locator status≠ok）可归因单列（`accounted_absent`），不判失败——与 build 尾部发布门同口径。
- **版本失效**（`diff.py`）：五态 cheap diff（reused / revalidate / stale / missing / orphan；bundle sha 对表、不开包）+ `revalidate --exact` 按需开包重读闭环（reused 槽位 item 面/blob 跨代复用，重读失败保持 revalidate 记因——禁静默丢槽位）。范围（Phase 5 审计 P2 修复）：五态迁移覆盖**全供给域**——art（portrait/portrait_golden）、watermark（per-card）、frames（kit，卡不变域）、gems（ally kit 派生域）、text（fontdefs/TTF 全域项）；卡不变域无 orphan 语义，其余四态照判。exact 重推导按域分派：art/watermark 走来源包解码，kit/gems 走 kit 重提取，text 走字体重提取；gems 的 source 无 bundle 地址时 cheap 面保守判 revalidate（不冒充 missing）。
- **运维面**：`selfheal`（L1 索引坏自动重建 / L2 blob 失配单次重推导 / L3 源坏分级）、`verify`（冷暖 payload+像素逐字节对拍 + kit/gems/text/watermark 分段；**两档抽样**——默认 `--sample/--golden-sample` + 200 wm 抽样为秒级收口档，`--all` 为 art 两 kind 全集 + watermark 全集的全量档，耗时随语料线性增长）、`bench` / `bench-process`（性能收口；partial 代只报实测并标 `partial`，不做外推）、`integrity`（全量 blob 扫 + `--repair` 定点重推导）、`maintain`（旧代 prune）。
- **边界**：**不接 render**（产品渲染链仍走 `core/supply` 会话面；供给消费接入另案）；**无公开面**（不进 README、无 console script）；**无产品 CLI**——唯一入口是内部工具 `python -m eidolon.core.supply_index <cmd>`（build/warm/diff/revalidate/verify/bench/bench-process/audit/measure/integrity/maintain），不进 `eidolon` 产品命令矩阵；`--cache-root` 全显式（缺省即参数错误，不读 env、不 import shell 默认根派生）；`cache_root` 兼作 `GameContext.cache_root`（cold/verify/revalidate/integrity 经 `resolve_context` 与产品同源身份；warm 只读 cache_root，不构造 GameContext）。

## 3. contracts

```python
class ProblemKind(StrEnum):
    INPUT = "input"
    ENVIRONMENT = "environment"
    RENDER = "render"
    INTERNAL = "internal"

@dataclass(frozen=True, slots=True)
class Problem:
    kind: ProblemKind
    code: str
    path: str          # 输入定位 / 文件路径 / argv / env:* 哨兵 / eidolon
    message: str
    hint: str = ""     # 覆盖 CODES 默认；空则用注册表
    cause: str = ""

class EnvironmentUnavailable(Exception):
    problem: Problem   # kind 必须为 ENVIRONMENT

@dataclass(frozen=True, slots=True)
class CardRef:
    kind: Literal["dbf", "card"]
    value: int | str

@dataclass(frozen=True, slots=True)
class CardFacts:
    cardtype: str

@runtime_checkable
class CardCatalog(Protocol):
    complete: bool
    known_classes: tuple[str, ...]
    known_cardtypes: tuple[str, ...]
    known_rarities: tuple[str, ...]
    known_spell_schools: tuple[str, ...]

    def lookup(self, ref: CardRef) -> CardFacts | None: ...

@dataclass(frozen=True, slots=True)
class GameRequest:
    game_dir: Path | None
    source: Literal["--game", "toml game_dir", ""] = ""

@dataclass(frozen=True, slots=True)
class GameContext:
    root: Path
    cache_root: Path
    locale: str = "zhcn"
    version: str | None = None
    version_source: str = ""
    root_source: str = ""
    route_mode: str = "auto"        # 渲染开关；v1 固定 auto
    version_strict: bool = False    # 渲染开关；v1 固定 False

@dataclass(frozen=True, slots=True)
class CatalogIdentity:
    kind: Literal["dbf", "json", "null"]
    path: str = ""
    size: int = 0
    mtime_ns: int = 0
    complete: bool = False  # 由 catalog.complete 复制；禁止独立赋值

@dataclass(frozen=True, slots=True)
class CatalogBinding:
    catalog: CardCatalog
    game: GameContext | None
    identity: CatalogIdentity
    warnings: tuple[str, ...] = ()

class CatalogProvider(Protocol):
    def bind(self, request: GameRequest) -> CatalogBinding: ...
```

说明：

- **`Problem.kind` 是退出码的唯一来源**；`CODES`（`shell/errors.py`）只存 `code → 默认 hint`，不存 kind。生产约定：shell（`load_input` / `compile_spec`）发 `INPUT`；core（bind / facts）发 `ENVIRONMENT`；组合层（entry / adapters，含 `port.preflight`）可发 `INPUT` / `ENVIRONMENT` / `RENDER` / `INTERNAL`；`dependency_missing` 由 entry 的 lazy import 失败点或 preflight 发 `ENVIRONMENT`。`Problem` 永远带 kind；未注册 code 在测试里失败；hint 为空时用 `CODES` 默认。
- `known_premiums` / `known_banners` **不进 catalog**：它们是产品政策（`NORMAL`/`GOLDEN`、10 个 banner），留在 shell 常量里；catalog 只提供游戏事实（classes / cardtypes / rarities / spell_schools）。`premium` / `cost_banner` 因此永不 deferred。
- `CardFacts` v1 只留 `cardtype`；`classes` 没有 shell 消费点，不放进契约。职业合法性走 `known_classes`。
- `CardRef` 不带 `manifest()`；manifest 字段映射归 `shell/manifest.py`。
- `GameContext` 是纯值。派生路径（纯属性，无 I/O、无 `assert_exists`）：`data_win` / `dbf_path` / `strings_dir` / `managed` / `assembly_csharp` / `resources` / `globalgamemanagers`；`route_cache` 是 `cache_root` 的兼容别名。游戏布局字面量只在这里出现，不散落进 core。
- `CatalogIdentity` 的 `complete` 只从 `binding.catalog.complete` 复制；manifest 只读它。`kind="null"` 表示 dev/null catalog，此时 `path=""`、不加 `catalog_incomplete`。
- `CatalogBinding.warnings` 承载 bind 期已知警告（如 `duplicate_card_id`）；`compile_spec` 把它并入 `RenderSpec.warnings`。
- `CatalogProvider` 的**真实实现**是 `DbfCatalogProvider(*, cache_root, locale)`；`NullCatalogProvider` / fake provider 只用于 dev/test。`locale` / `cache_root` 是 CLI 级参数，**不进 GameRequest**。`bind` 只收 `GameRequest`。
- 渲染链路里的 `RenderCard` / `RenderRequest` / `RenderReport` 也归 contracts；`RenderRequest` 是 adapter→core 的形状，不是端口协议（端口只认 `spec`）。形状见第 7 节。

## 4. 卡牌事实与存在性

- `DbfCatalog.complete = True`；`lookup` 同时接受 dbf id 与 card id（`m_noteMiniGuid`）。
- `NullCatalog.complete = False`；`JsonCatalog` 的 `complete` 从 JSON 顶层 `"complete": true|false` 读取，缺省 `False`。
- 判定规则：

| 条件 | 结果 |
| --- | --- |
| `facts is not None` | 正常校验 |
| `facts is None` 且 `catalog.complete` | `unknown_card`，输入错误（2） |
| `facts is None` 且 `not catalog.complete` | 逐卡 `deferred`，不阻塞 |

- **存在性口径**：dbf `CARD` 行可解析即存在；不按 collectible 过滤。可渲染性（资产是否存在、尺寸是否合规格）是 core dry-run 的事，不在 shell 膨胀。
- **facts 投影**：`DbfCatalog` 只读 `CARD` + `CARDTYPE` tag，构造 `CardFacts`，不为 `spec` 构造完整 `Card`。`known_*` 来自 `core/infra` 的**静态枚举镜像**（`CardType` / `CardClass` / `Rarity` / `SpellSchool`），不是 dbf 观测集，也不在 spec 期调 IL / pythonnet；镜像缺值视为版本未支持，改代码或更新镜像，不降级为观测值。`unknown_class` 等 hint 要提示“若客户端较新，可能是枚举镜像未更新”。
- **装载与查询失败**：`CatalogProvider.bind` **必须**在返回前打开 dbf、建立 facts 索引；`compile_spec` 不再碰 dbf 解析。`DbfCatalog` / facts 路径必须接收显式 `GameContext`（或 root / dbf 路径），**禁止调用 `current()`**；`install()` 只服务吸收期 render 代码。`lookup` 只在装载成功后返回 `None`；dbf 缺失、解析失败、版本不支持一律抛 `EnvironmentUnavailable`，不能吞成 `unknown_card`。`complete` 只表示“索引覆盖完整”，不表示查询一定成功。
- **重复 card id**：索引先到先得；`DbfCatalog.duplicates` 记录重复项，`CatalogProvider.bind` 把它放进 `CatalogBinding.warnings` 的 `duplicate_card_id`；`compile_spec` 并入 manifest `warnings`（不阻塞）。
- **`catalog_incomplete`**：仅当 `catalog.complete=False`、`identity.kind != "null"`、且 `compile_spec` 实际产生了 `deferred` 时，才加一条全局 warning；null catalog 不加，逐卡 `deferred` 已说明弱化范围。
- **`--catalog`**：只用于 `spec`（第 5.3 节）；JSON 缺省 `complete=False`，因此 dev 路径默认走 deferred。

## 5. 输入、入口与命令矩阵

### 5.1 两阶段输入

依赖 catalog 的检查与不依赖 catalog 的检查必须分开，否则“游戏没装”会盖掉 TOML 写错。

```python
@dataclass(frozen=True)
class InputDraft:
    command: Literal["spec", "render"]
    source: Literal["inline", "toml"]
    base: Path
    game: GameRequest          # --game > TOML game_dir；已校验显式安装根
    catalog_path: Path | None  # --catalog
    options: InputOptions      # out_dir / jobs / antialias / 全局 style
    cards: tuple[CardDraft, ...]
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class InputOptions:
    out_dir: Path
    jobs: int
    antialias: bool
    hero_style: bool
    bg_style: bool

@dataclass(frozen=True)
class CardDraft:
    input_id: str
    ref: CardRef
    outname: str
    out_path: Path
    overrides: Mapping[str, object]  # name/desc/classes/...，字段与 CardSpec 一致
    assets: Mapping[str, Path]
    hero_style: bool
    bg_style: bool

@dataclass(frozen=True)
class RenderOptions:
    out_dir: Path
    jobs: int
    antialias: bool

@dataclass(frozen=True)
class RenderSpec:
    source: Literal["inline", "toml"]
    options: RenderOptions
    cards: tuple[CardSpec, ...]       # CardDraft 编译后：有效 style + deferred + 覆盖
    game: GameContext | None = None
    catalog: CatalogIdentity = CatalogIdentity(kind="null")
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class CardSpec:
    input_id: str
    ref: CardRef
    outname: str
    out_path: Path
    overrides: Mapping[str, object]
    assets: Mapping[str, Path]
    hero_style: bool
    bg_style: bool
    deferred: tuple[str, ...] = ()

def load_input(..., cwd) -> InputDraft:
    """语法/结构/类型/id/outname/asset/runes/classes/races 结构规则/
    premium/cost_banner 产品常量/显式 game_dir 安装根校验/--catalog 与
    --game、render 的互斥。不依赖 catalog。"""

def compile_spec(draft: InputDraft, binding: CatalogBinding) -> RenderSpec:
    """只做：unknown_card、classes/cardtype/rarity/spell_school 的 known_*
    成员检查、hero/bg style 适用性。不得包含产品常量检查。"""
```

- **判据**：不需要 `catalog.lookup` / `known_*` 的检查一律在 `load_input`。因此 `premium`、`cost_banner`、`classes` / `races` 的空/重复/元素规则、runes、tech_level、asset 存在性都在 bind 前报。
- `load_input` 失败 → `SpecErrors`（2），不碰游戏数据、不加载 dbf、不跑 product.db 探测。
- 显式 `game_dir` 的安装根校验在 `load_input`：存在、是目录、含 `Hearthstone.exe`；否则 `game_dir_invalid`（2）。`--game` > TOML `game_dir`（相对 TOML 文件目录）；`GameRequest.source` 记录来路。
- `--catalog` 的 JSON 读取放在 `load_input` 成功之后、`compile_spec` 之前；坏 catalog 不会盖掉 TOML 语法错误。
- `build_spec(...)` 保留为兼容包装：`compile_spec(load_input(...), CatalogBinding(catalog or NullCatalog(), None, CatalogIdentity(kind="null" if catalog is None else "json", path="<memory>", complete=(catalog.complete if catalog is not None else False))))`。新代码走两阶段。
- `InputDraft` / `CardDraft` 是 shell 类型；core 不认它们。

### 5.2 入口与 run 的分工

**entry.main**（组合层）：

```text
parse argv（自定义 parser；usage 错误格式化后 SystemExit(2)）
  → 配置 logging（eidolon logger，stderr；try/finally 移除 handler）
  → provider_factory = provider_factory or (lambda: _build_provider(args.cache_root, args.locale))
    port_factory = port_factory or (lambda: _build_port(args))
  → shell.cli.run(args, provider_factory, port_factory, cwd)
  → 异常映射：EnvironmentUnavailable→3；未预期异常→internal(1)
  → finally 清理 handler
```

`main(argv, *, cwd=None, provider_factory=None, port_factory=None)`：factory 参数是 tests/entry 的注入点；默认 factory 内部 lazy import core。

**shell.cli.run**（壳）：

```text
draft = load_input(args, cwd)              # 失败 → SpecErrors → 打印/2；尚未 import core
  → binding = (shell 直读 JsonCatalog) if draft.catalog_path else provider_factory().bind(draft.game)
  → spec = compile_spec(draft, binding)    # SpecErrors → 打印/2
  → spec: 打印 manifest → 0
  → render: port = port_factory()          # 只在 load_input/compile_spec 成功后
           → port.preflight(spec)          # INPUT→SpecErrors→2；ENV→EnvironmentUnavailable
           → 打印 manifest → stdout
           → port.render(spec) → 结果 manifest / 0/1/2/3
```

- `run` 捕获 `SpecErrors`（含 preflight 的 INPUT 类）→ `format_problem` 到 stderr、返回 2；`CatalogError` → `Problem(INPUT, catalog_invalid)` 走同一路径。entry 只映射 `EnvironmentUnavailable`→3 与未预期→internal(1)。
- `--catalog` 与 `--game`/TOML `game_dir`、render 的互斥在 `load_input` 内判；`run` 不再重复。
- **factory 只在 `load_input` 成功后调用**：`--help`、`spec --catalog`、坏 TOML 都不会 import core / UnityPy；`render` 的 port 也在输入合法后才构造。
- `entry.py` 顶层只 import 标准库、`eidolon.shell`、`eidolon.contracts`、`eidolon.version`；所有 `eidolon.core` import 放在 factory 函数体内。
- `spec` 不创建 `RenderPort`、不 install `GameContext`；`render` 由组合层适配器在首次调用 core 前 `install(ctx)` 一次。`--jobs` 时 worker payload 携带 `GameContext`，worker 启动时各自 `install()`；worker 不读 env。
- `install/current` 是吸收 Angelía 的过渡设施：新 core 代码优先显式传 `ctx`；`dbf` / `facts` 路径禁止 `current()`。
- `--cache-root` / `--locale` 是 CLI 级参数，entry 读 `args` 后传给 `_build_provider`；`--cache-root` 默认由 `shell/paths.py::default_cache_root()` 算。`--game` / TOML `game_dir` 走 `GameRequest`。
- 入口不做字段校验、不解析 TOML、不拼 manifest 格式。超过约 150 行，说明有逻辑该下沉。

### 5.3 命令矩阵

| `--catalog` | `--game` / TOML `game_dir` | `spec` | `render` |
| --- | --- | --- | --- |
| 有 | 无 | 0 / 2（`catalog_invalid`、complete=true 下的 `unknown_card`、枚举错误；`environment.game=null`） | 2 `usage` |
| 有 | 有 | 2 `usage`（不要混用两个事实源） | 2 `usage` |
| 无 | 有或无 | 真实 dbf；0 / 2 / 3 | 真实 dbf；0 / 1 / 2 / 3 |

- **`--catalog` 仅用于 `spec`**：它是校验用的开发逃逸口，不是渲染事实源。render 必须使用与 core 同源的 dbf；混用 JSON 校验 + dbf 渲染会制造不可复现结果。usage 消息要点明“TOML `game_dir` 也算 `--game`”。
- `--game` 允许与 `--toml` 同用（机器相关的安装覆盖），且优先于 TOML `game_dir`；`--outdir` / `--jobs` / `--antialias` / 全局 style 仍按 TOML 规则不允许。
- `--locale` / `--cache-root` / `-v` / `--debug` 允许与 `--toml` 同用；`-v` / `--debug` 不列入 `option_not_allowed`。

### 5.4 spec 与 render 的环境依赖

| 检查 | `spec` | `render` |
| --- | --- | --- |
| 游戏根 / `Hearthstone.exe` | ✓（`--catalog` 除外） | ✓ |
| `dbf.unity3d` 存在 / 可解析 / facts | ✓（`--catalog` 除外） | ✓ |
| `Strings/<locale>` | ✗ | ✓ |
| cache_root 可写 | ✗ | ✓ |
| out_dir 可创建 / 可写 | ✗ | ✓（preflight 一次） |
| UnityPy | ✓（dbf） | ✓ |
| pythonnet / .NET | ✗ | ✓ |

`spec` 必须能在只读 home、无本地化、无写权限的机器上跑；`render` 的 locale / cache / out_dir / pythonnet 预检在打印计划清单前完成，失败按第 9 节归类。

## 6. 路径、locale、缓存

- **安装根**：含 `Hearthstone.exe` 的目录。显式 `--game` / TOML `game_dir` 的安装根校验在 `load_input`；失败 `game_dir_invalid`（2）。
- **优先级**：`--game` > TOML `game_dir`（相对 TOML 文件目录）> 探测。`GameRequest.source` 记来路。
- **探测**：无显式 root 时读战网 product.db。`game_not_found`（3）：product.db 缺失 / 无 `hs_beta` 条目 / 条目无 `install_path` / `install_path` 目录不存在；`path` 用 product.db 绝对路径，message 带失败原因。`game_dir_incomplete`（3）：product.db 给了 `install_path`、目录存在但没有 `Hearthstone.exe`；`path` = 该目录。
- **dbf**：root 是安装根但 `Data/Win/dbf.unity3d` 不存在 → `dbf_missing`（3），无论 root 来自 `--game` / TOML / 探测。存在但解析失败 / 版本不支持 → `dbf_unreadable`（3）。
- **locale**：`--locale` > `"zhcn"`（产品/语料默认，不是游戏探测）；v1 不支持 TOML `locale`。`Strings/<locale>` 缺失只在 render 报 `locale_missing`（3），message 列出 `Strings/` 下实际存在的目录，hint 指向 `--locale`。dbf 文本 `m_locValues[12]` 固定 zhCN，是 v1 已知限制。
- **cache_root**：`--cache-root` > `%LOCALAPPDATA%\Eidolon\cache`（Windows）/ `$XDG_CACHE_HOME/eidolon` 或 `~/.cache/eidolon`；相对 cwd。它是 route 缓存根，不是输出/供给缓存；`cache_unwritable`（3）的 hint 指向该路径与 `--cache-root`。cache_root 不参与内容身份，默认不进 manifest 复现字段；`--debug` 日志记录。未来 supply index 需要独立根时另加 `supply_cache`，不复用。
- **route 缓存健康（失效判据）**：`route.db` 是派生缓存，消费 route 行时以**行内 md5 对盘上内容做 used-hash**（stat 的 size/mtime_ns 相同也必须哈希；进程内按 `(bundle, size, mtime_ns, md5)` 缓存结果，同包只付一次）。内容失配 → 计数/日志标记当前代 stale → 在 `route.db.lock` 内**自动重建一次** → 重试该包；重建后仍失配或重建失败 → `BundleContentMismatch`（资产轴归 ENV 3，path=bundle，hint 指向战网扫描/修复或显式 refresh），不循环。打开库先 `PRAGMA quick_check`：坏库/打不开 → 删库重建一次，重建失败 → `route_cache_unreadable`（ENV 3）。`route.dirty`（未清洁退出标记）+ `route.health`（上次抽样时刻）用于蓝屏/崩溃后的加速检测：脏标记或超过阈值 → 抽样 used-hash（默认 32 包）；脏标记**接管**（删旧建新）要求标记超时（>5min）**且**持有者 pid 不再存活（持有者只是慢时只抽样不动标记；旧格式标记回退纯超时语义），显式全量走内部 `verify_all`，不接 render/CLI。计数经 `route.stats()` 暴露；不读 env、不新增 console script。
- **route 缓存健康已知限制**（残险如实记账，非静默；每条 = 风险场景 × 现状缓解 × 触发条件）：
  1. **used-hash 进程内 memo 信任**：同一进程内某包校验通过后，若游戏文件在 `(size, mtime_ns)` 不变下**再次**漂移（同会话中途 bit rot / 半路写坏），本进程不会二次发现。缓解：同包只付一次哈希是显式成本取舍；失配自动重建会换行 md5（memo 键失配不误命中旧结论）；新进程（冷 memo）或 dirty/6h 阈值触发的健康抽样仍会检查。触发条件：同一进程生命周期内同一包二次漂移。
  2. **manifest/locale 的 used-hash 只在库已存在时生效**：缓存根无有效 `route.db` 时（首跑 / 库曾被删），读 `asset_manifest` / locale catalog 走 `peek_existing` → 不建库也不做 used-hash，这两包的内容漂移在该轮不被航线健康面发现。缓解：这是显式设计（避免一次 manifest 读取触发数百秒级全量建库）；库一旦存在，manifest/locale 消费同路 used-hash + 单次自动重建；manifest 主包另有坏盘读防护（`load_defended`）。触发条件：无现存有效库且 manifest/locale 包本身已损坏。
  3. **`verify_all` 无后台任务 / 产品命令**：全量校验只是内部库函数，默认健康门只抽样 32 包 + 被消费包 used-hash。缓解：抽样确定性等距（可复现）；任何真被消费的包必过 used-hash，错误最迟在消费时响亮（绝不静默错显）；显式 refresh（重建）等效全量重扫。触发条件：包既不被消费也不在抽样集合 → 其漂移被发现要等到首次被消费。
  4. **dirty 接管的 pid 判定残差**：pid 复用（持有者死后 pid 被无关进程复用）或退出码恰为 `STILL_ACTIVE`(259) 会误判"持有者活着" → 不接管，陈旧标记滞留、后续每个新进程多付一次强制抽样（抽样照跑，正确性不受影响），直到该 pid 真正退出。保守方向：宁可晚接管，不误删活人标记。
- **out_dir**：CLI 相对 cwd；TOML 相对 TOML 文件目录。`out_dir_invalid`（2）= 纯形状：路径是文件、盘符/UNC 不存在、父路径是文件、非法字符/保留名。`out_dir_unwritable`（3）= 无权限、只读、配额、空间不足、`mkdir` 的 `PermissionError` / `ENOSPC`。实现：`NotADirectoryError` / `FileExistsError` → 2；`PermissionError` / `EACCES` / `ENOSPC` / `EROFS` → 3。
- **manifest environment**：

```json
"environment": {
  "game": {"root": "...", "locale": "zhcn", "version": "...", "version_source": "product.db", "root_source": "product.db"},
  "dbf": {"path": "...\\dbf.unity3d", "size": 123, "mtime_ns": 456},
  "catalog": {"kind": "dbf", "path": "...\\dbf.unity3d", "size": 123, "mtime_ns": 456, "complete": true},
  "eidolon": "0.1.0"
}
```

`--catalog` 时 `game` / `dbf` 为 `null`，`catalog.kind="json"`；`kind="null"` 时 `catalog` 全空、不加 warning。

## 7. 渲染端口

```python
class RenderPort(Protocol):
    def preflight(self, spec: RenderSpec) -> None: ...
    def render(self, spec: RenderSpec) -> RenderReport: ...

@dataclass(frozen=True, slots=True)
class RenderCard:
    ref: CardRef
    out_path: Path
    overrides: Mapping[str, object]
    assets: Mapping[str, Path]
    hero_style: bool   # 请求 ∩ 生效适用（adapter 交集下发）；raw 请求只进结果 manifest
    bg_style: bool
    session_t: float | None = None   # None → core 用 PRODUCT_SESSION_T (0.0)

@dataclass(frozen=True, slots=True)
class RenderRequest:
    cards: tuple[RenderCard, ...]
    out_dir: Path
    jobs: int
    antialias: bool
    game: GameContext                # kw_only；adapter 断言 spec.game 非空后构造
    font_dirs: tuple[Path, ...] = () # OS 字体目录（adapter 从 shell/paths 注入，不进 GameContext）

@dataclass(frozen=True, slots=True)
class RenderedCard:
    ref: CardRef
    path: Path
    sha256: str
    elapsed_ms: int
    warnings: tuple[str, ...] = ()   # 渲染期卡级警告（进结果 manifest）

@dataclass(frozen=True, slots=True)
class RenderFailure:
    ref: CardRef
    path: Path
    problem: Problem   # kind ∈ {ENVIRONMENT, RENDER}

@dataclass(frozen=True, slots=True)
class RenderReport:
    rendered: tuple[RenderedCard, ...] = ()
    failures: tuple[RenderFailure, ...] = ()
    warnings: tuple[str, ...] = ()   # 渲染期全局警告（进结果 manifest）
```

- `shell/ports.py` **只放 `RenderPort` 协议**；`RenderSpec → RenderRequest` 的形状化在组合层 `adapters.py`。适配器只做形状转换、`preflight` 检查与 `install(ctx)`；**Card 构造留在 core**（core 从 dbf + 覆盖构造 `Card`）。
- `preflight(spec)` 在打印计划清单前跑：locale / cache / out_dir / pythonnet；INPUT 类（`out_dir_invalid` 等）抛 `SpecErrors`（组合层可 import shell），ENVIRONMENT 类（`out_dir_unwritable`、`locale_missing`、`dependency_missing`）抛 `EnvironmentUnavailable`。`spec` 命令不调用。
- `render` v1 仍先打印计划 manifest 到 stdout，再渲染；结果 manifest 由 `shell/manifest.py` 格式化、`shell` 写盘，core 不认 manifest 格式。
- 端口 `render(spec)` 收已校验 spec；适配器断言 `spec.game` 非空，只有这时才向 core 构造 `game` 非空的 `RenderRequest`。`render` + `--catalog` 已在命令矩阵里拒绝。
- 退出码：`any(f.problem.kind is ENVIRONMENT)` → 3；否则 `any(... RENDER)` → 1；否则 0。混合批次 3 优先于 1。

## 8. 覆盖与保真

- 无覆盖：基准路径。
- 有覆盖：自定义渲染；manifest 记 `overrides`，不声称与游戏一致。
- 纹理 / 材质类覆盖只落 plan / supply；需要几何变化的覆盖走“换 prefab / kit”，不在 v1。
- 覆盖注入不改进程级 scene 缓存；输出缓存 key 必须包含覆盖项与资产 sha。
- 渲染期才知道的 warnings（覆盖、字体回退等）进结果 manifest；`RenderSpec.warnings` 只放输入期已知警告。

## 9. 错误与提示

退出码只是粗分类，不是主契约；主契约是 **kind + code + path + hint + cause**。

### 9.1 判定原则

按“修什么能解决”分类：

| 修什么能解决 | kind | 退出码 |
| --- | --- | --- |
| 改 CLI / TOML 输入 | `input` | 2 |
| 改机器 / 游戏安装 / 依赖 / 权限 | `environment` | 3 |
| 改渲染实现 / 资产内容，或单卡运行期失败 | `render` | 1 |
| 程序 bug / 未预期异常 | `internal` | 1 |

生产约定：**shell（`load_input` / `compile_spec`）发 `INPUT`；core（bind / facts）发 `ENVIRONMENT`；组合层（entry / adapters，含 `port.preflight`）可发 `INPUT` / `ENVIRONMENT` / `RENDER` / `INTERNAL`**。`dependency_missing` 由 entry 的 lazy import 失败点或 preflight 发 `ENVIRONMENT`。显式 `--game` 不存在或不是安装根 → `input`（`load_input` 抛）；是安装根但装不完整（缺 dbf / locale / 资产）或探测失败 → `environment`（bind / preflight 抛）。

### 9.2 错误对象与格式

`Problem`（第 3 节）统一承载；`CODES` 只存默认 hint，`kind` 由产生点给；`format_problem` 只在 shell 一侧：

```text
error[unknown_card] ids[2]: dbf 999999 不在当前游戏数据中
  hint: 确认 id；dbf id 用整数，card id 用 m_noteMiniGuid（如 CS2_182）
```

```text
error[dbf_missing] <game-install-root>\Data\Win\dbf.unity3d: 游戏安装不完整：缺少 dbf.unity3d（--game 指向 <game-install-root>）
  hint: 在战网里扫描/修复游戏文件；或把 --game 指向包含 Hearthstone.exe 的目录
  cause: FileNotFoundError: ...
```

- 单行头固定为 `error[<code>] <path>: <message>`；`hint` / `cause` 各占一行。
- `path` 是**可操作定位符**：输入字段（`ids[2]`、`cards[1].asset.portrait`、`--game`）、实际文件/目录、`argv`、`eidolon`，或明确的 `env:unitypy` / `env:dotnet` / `env:python` 哨兵。环境错误优先用实际文件/目录；`game_not_found` 用 product.db 绝对路径。
- `hint` 默认来自 `CODES[code]`；逐条 `Problem` 可覆盖。每个注册 code 必须有非空 hint。
- `cause` 保留底层异常摘要；`--debug` 打完整 traceback（靠 `raise ... from` 保链）。
- 输入错误收集后一次打印（上限 50）；环境错误 fail-fast（诊断顺序保证它不掩盖输入错误）；渲染失败逐卡收集，最后汇总。
- 未预期异常 → `internal`，`path="eidolon"`，hint 固定“这是 bug；用 --debug 附 traceback 反馈”；默认只打 cause，`--debug` 打 traceback。
- 自定义 parser 的 `error()` 先格式化 `Problem(usage)` 再 `raise SystemExit(2)`；`--help` 走 `SystemExit(0)`。这样保留现有测试的 `SystemExit` 形状，同时输出统一格式。

### 9.3 code 注册表

`shell/errors.py::CODES: dict[str, str]` 是唯一注册表：`code → 默认 hint`（**不存 kind**）。新增 code 必须同时改 `CODES`、本表、`docs/schema.md`；AST 测试扫描 `errors.add(...)` / `Problem(code=...)` 字面量，断言全部已注册；另按 code 分组断言 `Problem(kind=...)` 字面量的 kind 唯一（`write_failed` 被写成 `RENDER` 就红）。未注册 code 在测试里失败；`Problem` 永远带 kind，不做运行期 kind 兜底，只有 hint 为空时用 `CODES` 默认。

输入（2）：`usage`、`invalid_id`、`duplicate_id`、`unknown_card`、`unknown_class`、`unknown_key`、`enum`、`range`、`missing`、`type`、`io`、`toml_syntax`、`format_version`、`empty_cards`、`mode`、`option_not_allowed`、`style`、`banner`、`runes_total`、`unknown_rune`、`duplicate_outname`、`empty_classes`、`empty_class`、`duplicate_class`、`empty_race`、`duplicate_race`、`empty_rune`、`asset`、`asset_ext`、`asset_missing`、`asset_dimensions`、`outname`、`catalog_invalid`、`game_dir_invalid`、`out_dir_invalid`。

环境（3）：`game_not_found`、`game_dir_incomplete`、`dbf_missing`、`dbf_unreadable`、`dependency_missing`、`constants_unavailable`、`locale_missing`、`cache_unwritable`、`route_cache_unreadable`、`out_dir_unwritable`、`asset_missing_in_game`、`asset_format_unsupported`、`write_failed`。

渲染（1）：`render_failed`。内部（1）：`internal`。

- `asset_missing_in_game` / `write_failed` 是环境结论（安装不完整 / 权限或空间），不是单卡渲染 bug；可逐卡收集，最终退出 3。
- `asset_format_unsupported`（B2）是环境结论的另一形态：资产**在场**但形态在离线解码域外（首个实证=BC7 肖像 `DMF_254t5` 的 mip 链，fmt=25）——游戏内可渲染、离线链解码不可解，扫描/修复无效；hint 指升级 Eidolon。与 `asset_missing_in_game` 分立避免误导性 hint；退出码同为 3。
- `out_dir_invalid`（形状）是输入 2；`out_dir_unwritable`（权限/配额/空间/父目录 mkdir 失败）是环境 3。两者都在 render preflight 报，不是 per-card。
- `unknown_rune`（runes 键名白名单，load_input）与 `asset_dimensions`（覆盖资产尺寸不符，render preflight 静态表拦截；v1 无 render 期同尺寸分支）是输入 2；`constants_unavailable`（live 枚举/IL 表与镜像漂移，或 pythonnet 装载失败）是环境 3。
- `catalog` 旧 code 改名为 `catalog_invalid`；迁移期在 `CODES` 保留 `catalog` 键一版，值同 `catalog_invalid` 的 hint（`CODES` 是 `str→str`，没有 kind 映射位），测试同步。

### 9.4 诊断顺序

1. `load_input`：CLI/TOML 语法、结构、类型、id、outname、asset、runes、classes/races 结构、premium/banner、显式 game_dir 安装根、`--catalog` 互斥。**不碰游戏数据。**
2. `--catalog` JSON 读取（仅 spec）：输入错误 2。
3. `provider.bind`：game 探测 / dbf 存在性与解析 / facts；环境错误 3。
4. `compile_spec`：facts / 枚举 / style 适用性；输入错误 2。
5. render preflight：locale / cache / out_dir / pythonnet；输入或环境错误；**在打印 manifest 前**。
6. 打印计划 manifest；`port.render`；逐卡失败汇总（env 3 优先，render 1）。

保证“TOML 写错了”不会被“游戏没装”盖掉；`out_dir_invalid` 时 stdout 为空。

- `run` 捕获 `SpecErrors`（含 preflight 的 INPUT 类）→ 打印/2；`CatalogError` → `Problem(INPUT, catalog_invalid)` 走同一路径。entry 只映射 `EnvironmentUnavailable`→3 与未预期→internal(1)。

### 9.5 输出与编码

- 错误写 stderr，manifest 写 stdout；输入非法时 stdout 为空。
- entry 启动时**仅当** stdout / stderr 有 `reconfigure` 时才重配 UTF-8（`errors="backslashreplace"`）；进程内测试用 `StringIO` 时跳过。UTF-8 行为用子进程断言。
- 捕获 `BrokenPipeError`（`spec | head`）静默退出；`KeyboardInterrupt` 退出 130；`--debug` 才打 traceback。

## 10. 跨切面能力

| 角色 | 例子 | 放哪 | 规则 |
| --- | --- | --- | --- |
| 契约 / 词汇 | `CardRef` / `CardFacts` / `Problem` | `contracts.py` | 纯数据 / 协议 / 异常 |
| 跨切面设施 | 日志、时钟、文件系统、环境 | 标准库 + entry 配置 | 不做 eidolon 包装层；值通过参数流入 |
| 外部适配器 | 游戏安装、dbf、资产、渲染器 | `core/infra` / `core/render` | 只被 core / 组合层 import |

### 10.1 日志

- 用标准库 `logging`，不造 `eidolon.infra.logging`。模块级 `logger = logging.getLogger(__name__)`；库代码不配置 handler、不读 env。
- `entry.py` 配 `logging.getLogger("eidolon")`（不碰 root）：stderr handler，格式 `%(levelname)s %(name)s: %(message)s`；handler 的安装/移除在 `main()` 的 `try/finally` 里成对完成，同一进程多次调用不累积 handler。
- 级别：默认 `WARNING`；`-v/--verbose` → `INFO`；`--debug` → `DEBUG` + 未预期异常 traceback。`-v` / `--debug` 允许与 `--toml` 同用。
- **用户可见的失败走 `Problem`，不走 logger**；同一件事不要既 log error 又 print。日志是诊断，不是契约。
- 影响保真 / 覆盖的结果性警告进 manifest 的 `warnings` / `deferred`，不进日志。`RenderSpec.warnings` 只放输入期已知警告；渲染期 warnings 进结果 manifest。
- `--jobs` v1：worker 只回传结果，父进程单点打日志；worker 不配 logging、不写 stdout/stderr。
- v1 不做逐卡进度：端口只在结束时返回 `RenderReport`。以后要 `[3/10]`，再加 `on_result` / `iter_results`，不要用日志冒充协议。
- `eidolon/__init__.py` 给 `logging.getLogger("eidolon")` 挂 `NullHandler`。

### 10.2 其他跨切面

- 时钟：core 直接用 `time.perf_counter`；只有需要确定性测试的模块才注入 `Clock`，不做全局。
- 路径 / 环境：entry 解析 `GameRequest` / `out_dir`；`GameContext` 由 `provider.bind` 构造；`GameContext` 的派生路径属性是唯一布局来源。`install/current` 只是吸收期过渡设施。
- 随机 / UUID：不需要；缓存 key 用内容 hash。
- 文件 IO：shell 读输入文件、检查 asset、写 manifest；core 读游戏资产、写 PNG。没有共享 IO 层。

一句话：**契约共享，设施用标准库并在入口配置，适配器留在 core。** 三者都不需要“公共 infra”。

## 11. 测试与守卫

- `tests/shell/`：fake catalog / provider / port，无游戏依赖；rev4 搬迁时迁入的原 149 个 shell 测试已全绿（当前默认 discover 计数见 AGENTS.md「当前状态」，以实跑为准）。
- `tests/core/`：facts 投影、索引；默认用 fake reader 纯单测（不 import UnityPy）。
- `tests/integration/`：真实 dbf / 游戏安装的集成测试放这里，文件用 `integration_*.py`，默认 `test*.py` 不匹配，**不进入默认 `discover`**（不是 `skipUnless`）；显式运行 `python -m unittest discover -s tests/integration -p 'integration_*.py' -t . -v`。默认测试的 skip 数必须为 0。
- `tests/entry/`：装配顺序、provider 选择、factory 注入、退出码映射、日志 handler 生命周期、UTF-8 / BrokenPipe、`--help` / `spec --catalog` / 坏 TOML 不加载 `UnityPy` / `eidolon.core`。
- `tests/architecture/`：
  - `eidolon/shell/` 中不得出现 `eidolon.core`；
  - `eidolon/core/` 中不得出现 `eidolon.shell`；
  - `eidolon/contracts.py` 只 import 标准库；
  - `eidolon/__init__.py` 不得 import `eidolon.core`；
  - stdlib-only 守卫覆盖 `shell/**/*.py` + `contracts.py`（递归、文件数下限、相对 import 还原成绝对名）；
  - `python -m eidolon --help` / `spec --catalog` / 坏 TOML 子进程断言 `sys.modules` 里没有 `UnityPy` / `eidolon.core`；
  - `core/infra/dbf.py` / `facts.py` 不得出现 `current(`；
  - 仅 `shell/paths.py` 可读 `LOCALAPPDATA` / `XDG_CACHE_HOME` / `HOME`；禁止任何 `HEARTHSTONE_*`；AST 按“文件 + 键名”白名单，其余 `os.environ` / `os.getenv` 一律失败；`Path.home` / `expanduser` 也只允许出现在 `shell/paths.py`；
  - `Problem(code=...)` 字面量按 code 分组，kind 唯一；
  - 单测目录必须有 `__init__.py`，`discover` 数量有下限，防止“0 tests OK”；
  - stdlib / import-graph 守卫本身住 `tests/architecture/`，不随 step 2 搬进 `tests/shell/`。

## 12. 迁移步骤

**状态：步骤 1-8 已全部落地（rev4 搬迁 + core 接入 Phase 0-4，2026-11-08）；本节保留为迁移记录，以下按当时计划书写。**

**不变量（迁移期）**：每步结束 `python -m unittest discover -s tests -t .` 必须全绿（当时基线 149 + 新增 N）且默认 skip 为 0；不得删除断言来变绿；新增测试单独计数。每步同步 `docs/schema.md` / README 对应小节。

1. **抽 contracts（纯搬，不改语义）**：`CardRef` / `CardFacts` / `CardCatalog` / `GameContext` / `Problem` 等移到 `eidolon/contracts.py`；`CardRef.manifest()` 移到 `shell/manifest.py`；加 `eidolon/version.py`（manifest 的 `eidolon` 字段用它，避免 `__init__` 循环）；保留 `SpecError` 类（字段 `code/path/message`，`.format()` 委托 `format_problem`），不把它别名到 `Problem`；给 `NullCatalog` / `JsonCatalog` 补 `complete` 属性（Protocol 已带它，否则 `isinstance` 测试立刻红）；`known_premiums` / `known_banners` / `CardFacts.classes` **暂留**。加 contracts 纯净守卫、`tests/*/__init__.py`、stdlib rglob + 文件数下限；stdlib / import-graph 守卫住 `tests/architecture/`，不随 step 2 搬。149 绿。
2. **搬壳**：`eidolon/*.py` → `eidolon/shell/`；`tests/test_*.py` → `tests/shell/`；console script 暂指 `eidolon.shell.cli:main`；import-graph（shell 无 core）落地。149 绿。
3. **接入口（行为不变）**（已完成，rev4）：`entry.py` + `__main__.py`；`cli.main` 拆 `parse_args` + `run`；`main(argv, *, cwd=None, provider_factory=None, port_factory=None)`；`run` 在 `load_input` 成功后才调用 factory（`spec --catalog` / 坏 TOML 不 import core）；`run` 捕获 `SpecErrors` / `CatalogError` → 打印/2；`load_input` / `compile_spec` 两阶段 + `build_spec` 兼容包装；当时默认 provider 为 `NullCatalogProvider`（NullCatalog + game=None），`--catalog` 由 shell 直读 `JsonCatalog.from_path`（不建 StaticCatalogProvider）；当时保留 `shell/render.py` 旧 stub，`RenderRequest` / `NullRenderPort` 推到第 5 步——两者均已被后续步骤取代：默认 provider 切 `DbfCatalogProvider`（entry lazy import，第 4 步），stub 随真实端口接入删除（第 5 步）。自定义 parser 格式化后 `SystemExit(2)`；logging / UTF-8（带 `hasattr` 守卫）。
4. **真实 catalog 与产品语义**：`core/infra` 落 `GameContext` / `game_install` / `dbf` / `facts` / `DbfCatalog` / `DbfCatalogProvider`；默认切真实 dbf；`--catalog` 改 spec-only；`unknown_card` / `complete` / `catalog_incomplete`；删 `known_premiums` / `known_banners` / `CardFacts.classes`，premium/banner 不再 deferred；`Problem.kind` / `CODES` / 退出码 3 / game_dir 分类 / manifest environment / catalog identity 落地。测试改造逐条：
   - `test_catalog.py:31`（`complete` 属性）、`:38-44`（known_premiums/banners）、`:51,71,104`（`CardFacts.classes`）；
   - `test_validation.py:294-299`（premium deferred）；
   - `test_manifest.py:35`（`warnings==[]`，加 `catalog_incomplete` 条件后按新语义）；
   - `test_cli.py:148-156`（render + `--catalog` 期望 1 → 2）；`test_python_m_eidolon_render_stub`（subprocess 无游戏 → 3；或改 in-process fake provider + 旧 stub 期望 1）；`test_python_m_eidolon_spec`（subprocess 无 catalog → 3；保留 `--catalog` 变体 0）；
   - `test_cli.py:134-144`（parser 仍 `SystemExit(2)`，若改成返回 2 需列明改法；推荐保留 `SystemExit`）。
   把不带 `--catalog` 的 shell 测试改为注入 fake provider；README/examples/schema 同步。
5. **渲染端口与核吸收**：`RenderPort`（`preflight` + `render(spec)`）+ `adapters.py` 形状化 + `RenderRequest` / `RenderReport` / `RenderFailure`；core 吸收 Angelía render / supply / recipes；吸收前置 C/D/E 与白名单见 §12.2；`install(ctx)` 只在 render 路径，worker 各自 install；`ctx.route_cache` 映射到 `ctx.cache_root`。
6. **asset 覆盖**：`frame` / `portrait` / `watermark`；尺寸规约；水印强制/无层报错。
7. **结果 manifest**：`render` 写 `out_dir/manifest.json`（输入摘要 + 输出 sha + 耗时 + render 期 warnings）。
8. **收口**：import-graph / stdlib / no-UnityPy / no-current / no-env 守卫；坏 TOML 不加载 core 的子进程断言；schema / README / AGENTS 示例 / PROVENANCE 同步。

### 12.1 公开面与文档清单

- 公开 API 定义为 `eidolon` 包属性 + console script；模块路径搬迁不承诺稳定。
- `SpecError` 保留类与 `.format()`；新代码用 `Problem`；`format_problem` 唯一格式化点。
- `build_spec` 兼容包装保留；新代码只用 `load_input` + `compile_spec`。
- `__init__.py` / `tests/support.py` / `pyproject.toml` 的 console script、optional extras（UnityPy / pythonnet）同步。
- TOML `TOP_LEVEL_KEYS` 加 `game_dir`；CLI 加 `--game` / `--locale` / `--cache-root` / `-v` / `--debug`；`--catalog` 与 `--game`/TOML `game_dir` 互斥、与 render 互斥。
- README：`HEARTHSTONE_DIR` → `--game`；`schema = 1` → `format_version = 1`；退出码加 3；版本钉死表述与“v1 只记录”对齐。
- `docs/schema.md`：退出码、`environment`、`--catalog` spec-only、`known_*` 变更、`premium` 不再 deferred。

### 12.2 迁移白名单（core）

只搬 `resolve_game_root`（去掉 env 分支）、`resolve_version`（保留 `install_path == root` 同装判据）、`_same_install`、product.db walk；**不搬** `PROVENANCE_VERSION` / `PROVENANCE_COMPATIBLE` / `classify_client_version` / `is_strict` / `resolve_version_strict` / `resolve_route_mode` / env 分支。v1 只记录 version，不做版本闸；`FALLBACK_UNITY_VERSION` 只做 UnityPy 解析兜底，不当游戏版本闸。`ctx.route_cache` 映射到 `ctx.cache_root`；未来 supply index 需要独立根时另加 `supply_cache`，不复用。

## 13. 非目标与待定

- 不引入插件、entry points、依赖注入框架；Protocol + 手写装配足够。
- 不做 asset 尺寸 / 格式校验（core 的职责）；不在 shell 里探测可渲染性。
- 不做日志文件 / 轮转 / 结构化 JSON 日志 / 遥测；stdout 只放 manifest，stderr 只放错误与诊断。
- 不读游戏输入环境变量；OS 级目录变量只用于默认缓存根。
- 待定：`--catalog` 是否在 1.0 移除；结果 manifest 的 schema；`RenderReport` 字段；逐卡进度是否需要端口回调；TOML `locale` 是否开放；版本闸（v1 只记录）。
- v1 限制：locale 默认 `zhcn`；dbf 文本固定 `m_locValues[12]`（zhCN）；`--catalog` 仅 spec；枚举镜像过期视为“未支持版本”，不降级为观测集。

## 14. 决策记录

| 决策 | 选择 | 拒绝 |
| --- | --- | --- |
| 共享层 | 纯 `contracts` | 公共 `infra` |
| 入口 | 组合层 `entry` / `adapters`；`shell.cli.run` 编排输入 | `shell/cli.py` 直接 import core |
| 输入阶段 | `load_input`（不碰游戏数据）+ `compile_spec`（只做 catalog 检查） | 单趟 `build_spec` 先 bind 后校验 |
| catalog 绑定 | `CatalogBinding(catalog, game|None, identity, warnings)`；`GameRequest` | game 必填 / 无 catalog 身份 |
| 显式 game_dir | `load_input` 校验安装根 → input 2；core 只发 environment | bind 判显式路径再发 2（无异常类型） |
| 存在性 | `catalog.complete` + `unknown_card`；lookup 失败必须 raise | 查不到一律 deferred / 吞成 unknown |
| `--catalog` | 仅 `spec`；与 `--game`/TOML `game_dir` 互斥 | 混用 JSON 校验 + dbf 渲染 |
| 错误契约 | `Problem.kind` 单一来源；`CODES` 只存 hint；kind 决定退出码 | 只靠退出码 / 双份 kind / `EXIT_BY_CODE` |
| RenderFailure | 允许 `{ENVIRONMENT, RENDER}`；混合批次 3 > 1 | 固定 `RENDER` / 拆两套容器 |
| 日志 | 标准库 `logging`，`eidolon` logger，entry 唯一配置点；v1 无逐卡进度 | `eidolon/infra/logging` 包装层 |
| 端口 | `shell/ports.py` 只放协议；形状化在 `adapters.py`；preflight 在打印前 | 形状化放 ports.py / manifest 先打印 |
| 契约位置 | 顶层 `contracts.py` | `core/contracts.py` |
| 适配器 | 组合层 | core 实现 shell 的 Protocol（会让 core import shell） |
