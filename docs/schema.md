# Eidolon 外壳输入 / manifest schema

> 本文描述**当前已实现**的契约（2026-11-08，rev4 + core 接入 Phase 0-4 落地）。
> 目标设计唯一源是 `docs/architecture.md`；core（dbf / 真实 provider /
> 渲染端口）已接入，`render` 已真实化（PNG + 结果 manifest），退出码 3 为环境错误。

本文件描述 `eidolon` 外壳当前实现的契约：两种输入面（命令行、TOML）如何
经两阶段（`load_input` → provider/bind → `compile_spec`）归一成
`RenderSpec`，以及 `spec` / `render` 输出什么。

## 1. CLI

```text
eidolon spec|render <id>... [--outdir DIR] [--jobs N] [--hero-style] [--bg-style] [--antialias] [--game DIR] [--locale LOC] [--cache-root DIR] [--catalog PATH] [-v] [--debug]
eidolon spec|render --toml FILE [--game DIR] [--locale LOC] [--cache-root DIR] [--catalog PATH] [-v] [--debug]
```

- `spec`：两阶段输入后向 stdout 打印 manifest，退出码 `0`，不渲染。
- `render`：同样解析 + 校验，然后经渲染端口 preflight（通过后打印计划
  manifest）再渲染；组合层适配器 `adapters.CoreRenderPort`（core 渲染流水线）
  输出 PNG 并写结果 manifest（第 8 节），退出码 `0` / `1` / `2` / `3`。
- 位置 id 与 `--toml` 互斥；两者都不给退出码 `2`。
- `--outdir` / `--jobs` / `--hero-style` / `--bg-style` / `--antialias`
  是命令行模式的全局选项；与 `--toml` 同时出现一律退出码 `2`
  （`option_not_allowed`，TOML 模式只认文件）。
- `--game` / `--locale` / `--cache-root` / `-v` / `--debug` 允许与
  `--toml` 同用（`--game` 优先于 TOML `game_dir`）。
- `--catalog PATH` **仅用于 `spec`**；与 `--game`、TOML `game_dir`、
  `render` 任一同时出现退出码 `2`（`usage`；TOML `game_dir` 也算
  `--game`）。
- `--cache-root` 相对 cwd；缺省由 `shell/paths.py::default_cache_root()`
  计算（`%LOCALAPPDATA%\Eidolon\cache` / `$XDG_CACHE_HOME/eidolon` /
  `~/.cache/eidolon`）。`--locale` 缺省 `zhcn`。
- 未知参数 / 类型不合法（如 `--jobs many`）由自定义 parser 报
  `error[usage]` 后 `SystemExit(2)`；`--help` 退出码 `0`。
- 错误写 stderr，manifest 写 stdout；输入非法时 stdout 为空。

退出码（`Problem.kind` 单源映射）：

| 码 | 含义 |
| --- | --- |
| `0` | 校验成功（`spec`），或渲染成功（`render`） |
| `1` | 逐卡渲染失败或内部错误（`render` / `internal`） |
| `2` | 输入非法：CLI 用法、互斥冲突、TOML 结构/类型/语义、`unknown_card`、catalog 读取失败、preflight 的覆盖资产/语义校验 |
| `3` | 环境不可用（游戏没装、dbf 缺失、locale/权限/缓存不可写、依赖缺失） |
| `130` | `KeyboardInterrupt` |

## 2. 命令行模式

```text
eidolon spec 8 CS2_182 --outdir out --jobs 4 --antialias
```

- 命令行参数只有字符串：`8` / `008` 一律按 dbf（前导零归一化），`CS2_182` → card id。
- 其余必须匹配 `^[A-Za-z0-9_]+$`。
- 归一化后重复（`8` 与 `"008"`）→ 错误。
- 命令行模式没有卡级覆盖，也没有 asset。
- 默认输出目录 `.`、`jobs = 1`、`antialias = false`。

## 3. TOML schema（`format_version = 1`）

顶层键：

| 键 | 类型 | 缺省 | 说明 |
| --- | --- | --- | --- |
| `format_version` | int | 必填 | 仅支持 `1` |
| `out_dir` | str | `"."` | 相对 TOML 文件所在目录解析 |
| `jobs` | int | `1` | 必须 `>= 1` |
| `antialias` | bool | `false` | `false` = 1x 快速路径；`true` = 4x 覆盖超采样 |
| `game_dir` | str | 无 | 游戏安装根（含 `Hearthstone.exe`），相对 TOML 文件目录；`--game` 优先 |
| `cards` | table array | 必填 | 不能为空 |

`game_dir` 在 `load_input` 里校验安装根：存在、是目录、含
`Hearthstone.exe`；否则 `game_dir_invalid`（2）。真实 dbf 读取（探测
product.db、`dbf.unity3d` 解析）属 core，已由 `DbfCatalogProvider` 落地。

卡级键（全部可选，缺省表示「不覆盖，交给渲染层走数据」）：

| 键 | 类型 | 约束 |
| --- | --- | --- |
| `id` | int / str | 必填；int = dbf；str = card id；**纯数字字符串非法**（dbf 必须写整数） |
| `name` / `desc` | str | `desc` 去首尾换行（多行字符串的收尾换行不保留） |
| `classes` | list[str] | 非空、无重复；catalog 有 `known_classes` 时须为已知职业 |
| `races` | list[str] | 元素非空、无重复；允许空 list；保留输入顺序 |
| `cost` / `attack` / `health` / `armor` | int | bool 不算 int |
| `cardtype` / `rarity` / `spell_school` | str | 非空；catalog 有对应 `known_*` 时校验成员，否则 deferred |
| `premium` | str | 恒只允许 `NORMAL` / `GOLDEN`（shell 产品常量，**永不 deferred**） |
| `cost_banner` | str | 恒为 10 值之一：`NONE`、`GRIMY_GOONS`、`KABAL`、`JADE_LOTUS`、`ZERG`、`TERRAN`、`PROTOSS`、`TRADEABLE`、`FORGE`、`PREPARE`（同上，永不 deferred） |
| `elite` | bool | — |
| `runes` | inline table | 键仅 `BLOOD` / `FROST` / `UNHOLY`（未知键名 `unknown_rune` 退出 2）；值 `0..3`，总和 `<= 3`；`{}` 表示清空 |
| `tech_level` | int | `0..7` |
| `hero_style` / `bg_style` | bool | 逐卡；语义见第 4 节 |
| `outname` | str | 不含 `/`、`\`、`..`；缺 `.png` 自动补；缺省 `<id>.png` |
| `asset` | table | 键仅 `portrait` / `frame` / `watermark` |

`[cards.asset]` 的值必须是 `.png` 文件；相对 TOML 文件所在目录解析，写出
绝对路径。外壳只校验扩展名与存在性；尺寸在 render preflight 静态拦截
（`asset_dimensions` 退出 2：portrait 512×512 / frame 1024×1024 /
watermark 128×128 或 256×256，表即全部合法尺寸，不做缩放/letterbox）。

未知键（顶层、卡级、asset 级）一律报错并带路径，例如
`cards[2].foo`、`cards[0].asset.foo`。

## 4. `hero_style` / `bg_style`

TOML 逐卡：

- 已知卡（catalog `lookup` 有 `cardtype`）：
  - `hero_style = true` 且非 `HERO` → 错误；
  - `bg_style = true` 且 `HERO` → 错误。
- 未知卡或无 catalog：保留原始布尔，检查记入该卡 `deferred`，不阻塞。

CLI 全局：

- `--hero-style` 只作用于 HERO 卡；`--bg-style` 只作用于非 HERO 卡。
- 两个开关正交：同时给时各自只作用于适用卡。
- 如果某个开启的开关在本批里没有任何适用卡（且不存在无法判定的未知卡）→ 错误。
- 无 catalog：保留开关请求值，逐卡 `deferred`，不报「无适用卡」。
- catalog 里查不到的卡：complete catalog 下直接 `unknown_card`；
  不 complete catalog 下 deferred（外壳不掌握卡数据）。

`bg_style` 不会根据战棋数据自动推导；必须显式开启。

## 5. Catalog

```python
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
```

- `premium` / `cost_banner` 是 shell 产品常量（`PREMIUMS` / `BANNERS`），
  **不进 catalog**，恒直接校验，永不 deferred。
- 存在性判定：

| 条件 | 结果 |
| --- | --- |
| `facts is not None` | 正常校验 |
| `facts is None` 且 `catalog.complete` | `unknown_card`，输入错误（2） |
| `facts is None` 且 `not catalog.complete` | 逐卡 `deferred`，不阻塞 |

- `catalog_incomplete` 全局 warning：仅当 `catalog.complete=False`、
  catalog 身份 `kind != "null"`、且 `compile_spec` 实际产生了
  `deferred` 时加一条；null catalog 不加。
- `NullCatalog`：`complete=False`，所有 `known_*` 为空，`lookup` 恒
  `None`。此时 `classes`、`cardtype`、`rarity`、`spell_school` 以及逐卡
  style 检查进入 `deferred`（不阻塞）。
- 默认 provider：entry 组合根 lazy import 的 `core/infra::DbfCatalogProvider`
  （dbf 索引 + `GameContext` 构造；`catalog kind="dbf"`、`complete=true`）。
  `shell/catalog.py::NullCatalogProvider` 只作 dev/test 用
  （`catalog kind="null"`、`game=None`）。
- `JsonCatalog` 结构（`--catalog` 由 shell 直读；**仅 `spec` 可用**）：

```json
{
  "complete": false,
  "known_classes": ["MAGE"],
  "known_cardtypes": ["HERO", "MINION"],
  "known_rarities": ["COMMON", "LEGENDARY"],
  "known_spell_schools": ["FIRE"],
  "cards": {
    "8": {"cardtype": "MINION"},
    "CS2_182": {"cardtype": "MINION"}
  }
}
```

  顶层 `complete` 缺省 `False`；未知顶层键 / 卡条目里 `cardtype` 以外的
  键一律 `catalog_invalid`（2）。`cards` 的 key 是字符串：dbf 用十进制
  字符串（如 `"8"`），card id 原样；外壳用 `str(ref.value)` 查。

## 6. Manifest

```json
{
  "format_version": 1,
  "source": "toml",
  "options": {"out_dir": "<abs-out-dir>", "jobs": 4, "antialias": false},
  "environment": {
    "game": null,
    "dbf": null,
    "catalog": {"kind": "json", "path": "<abs-catalog-path>", "size": 900, "mtime_ns": 1339, "complete": false},
    "eidolon": "0.1.0"
  },
  "cards": [
    {
      "input_id": "CS2_182",
      "id": {"kind": "card", "value": "CS2_182"},
      "out": "<out-dir>\\yeti.png",
      "hero_style": false,
      "bg_style": false,
      "overrides": {
        "name": "…",
        "desc": "…",
        "classes": ["MAGE"],
        "races": ["鱼人", "野兽"],
        "fields": {"cost": 3, "cardtype": "MINION", "runes": {"BLOOD": 1}},
        "assets": {"portrait": "<abs-art-path>\\x.png"}
      },
      "deferred": ["rarity"]
    }
  ],
  "warnings": ["catalog_incomplete"]
}
```

- 卡按输入顺序输出；`classes` / `races` 保留输入顺序。
- dbf 的 `id` 为 `{"kind": "dbf", "value": 8}`（value 是整数）；card 的 value 是字符串。
- 只输出显式给出的 overrides；`overrides` 为空时整个键省略。
- `fields` 按固定字段顺序输出；`runes` 键排序；`assets` 键排序。
- 路径（`options.out_dir`、`out`、`assets.*`）一律绝对路径。
- `environment`：`game` 由真实 provider（`DbfCatalogProvider`）构造——root /
  locale / version / version_source / root_source；`--catalog` 时 `null`；
  `dbf` 仅在 `catalog.kind == "dbf"` 时给出 `{path, size, mtime_ns}`，否则
  `null`；`catalog` 是 catalog 身份（`kind` ∈ `dbf` / `json` / `null`；json 时
  `path` / `size` / `mtime_ns` 来自 `--catalog` 文件，null 时全空且不加
  warning；dbf 时三字段来自 dbf 文件、`complete=true`）；
  `eidolon` 是版本（`eidolon.version`）。
- `deferred` 去重并按固定顺序输出：`classes`、`cardtype`、`rarity`、
  `spell_school`、`hero_style`、`bg_style`（`premium` / `cost_banner`
  恒直接校验，不在其中）。
- `warnings` 稳定输出，取值（固定顺序）：
  - `duplicate_card_id`：dbf 索引发现重复 card id（先到先得，不阻塞）；
  - `catalog_incomplete`：触发条件见第 5 节（complete=False、非 null
    catalog、且实际产生了 `deferred`）。
- 同一输入产生逐字节相同的 manifest（稳定排序 / 稳定键序）。

## 7. 错误对象与提示

- 主契约是 `Problem(kind / code / path / message / hint / cause)`
  （`eidolon/contracts.py`）；`kind`（`input` / `environment` /
  `render` / `internal`）是退出码的唯一来源。
- `CODES`（`shell/errors.py`）只存 `code → 默认 hint`；`format_problem`
  是唯一格式化点，输出 `error[<code>] <path>: <message>` +
  `  hint: …` + `  cause: …`。
- 生产约定：shell（`load_input` / `compile_spec`）发 `input`；core 发
  `environment`；组合层（entry / adapters，含 preflight）可发 `input` /
  `environment` / `render` / `internal`。
- 输入错误收集后一次打印（上限 50 条，超出截断标注）。
- 完整 code 注册表见 `docs/architecture.md` §9.3。

## 8. 结果 manifest（render 命令，`out_dir/manifest.json`）

- 顶层结构与计划 manifest 同序（`format_version` / `source` / `options` /
  `environment` / `cards` / `warnings`）；`environment` 与计划 manifest
  同源生成。
- `cards` 按输入顺序一张不落：ok 卡带 `sha256` / `elapsed_ms` /
  `hero_style` / `bg_style`（生效值）/ `style_requested`（请求值，两个
  布尔）/ `overrides` / `assets_sha256`（覆盖资产文件字节 sha256）/ 
  `warnings`；失败卡带 `error`（`Problem` 全字段）。
- 全局 `warnings` = spec 警告 + 渲染报告警告 + shell 侧
  （`asset_hash_unavailable` / `report_missing`）按出现顺序去重。

## 9. 未实现（by design）

- 输出 PNG 缓存。
- supply-index 是内部派生缓存（`eidolon/core/supply_index`，Phase 5 已落地），
  **不是输入/输出契约**：不进本 schema、无产品 CLI（内部入口
  `python -m eidolon.core.supply_index`）、不接 render；`--cache-root` 显式给。
- asset 像素内容校验：preflight 只做可解码 + 静态尺寸表（§3
  `asset` 行），不做语义/像素级校验。
