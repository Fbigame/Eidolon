# Eidolon

炉石卡牌离线渲染器。从本地游戏安装读取数据，把卡牌渲染成 PNG，不需要游戏客户端在运行。

> 状态：**渲染已接入**。输入归一化 / 校验 / manifest、真实 catalog
> （dbf）与渲染端口（PNG 输出 + 结果 manifest）已实现；本机需要游戏安装
> 与 core 渲染运行时依赖（见 `pyproject.toml`）。

## 环境要求

- Windows
- Python 3.13+
- 本地炉石安装（`render` 与真实 `spec` 需要；`spec --catalog` 不需要）
- .NET 运行时（CoreCLR，建议 .NET 8+；`render` 需要，`spec` 不需要）。用
  `dotnet --list-runtimes` 确认能看到 `Microsoft.NETCore.App`；Windows 自带的
  .NET Framework 4.8 不算，需另装 .NET Runtime（不需要 SDK）。缺失时 `render`
  在 preflight 报 `dependency_missing` 并退出 3。

## 安装

```powershell
uv sync
```

## 用法

两种互斥的输入模式，默认命令行模式。

```text
eidolon spec|render <id>... [--outdir DIR] [--jobs N] [--hero-style] [--bg-style] [--antialias] [--game DIR] [--locale LOC] [--cache-root DIR] [--catalog PATH] [-v] [--debug]
eidolon spec|render --toml FILE [--game DIR] [--locale LOC] [--cache-root DIR] [--catalog PATH] [-v] [--debug]
```

### 命令行模式

```text
eidolon spec 8 CS2_182 --outdir out --jobs 4
```

- `<id>`：纯数字按 dbf id 处理（如 `8`），其余按 card id 处理（如 `CS1_113`）。
- `--outdir`：输出目录，默认 `.`；每张卡写到 `<outdir>/<id>.png`。
- `--jobs`：工作进程数，默认 `1`。
- `--antialias`：4x 覆盖超采样，输出质量更高、速度更慢；默认 1x 预览。
- `--hero-style`：HERO 卡使用 PLAY（棋盘）形态；`--bg-style`：非 HERO 卡使用酒馆战棋装饰。两个开关正交，各自只作用于适用的卡；整批没有适用卡时报错。
- `--game`：游戏安装根（含 `Hearthstone.exe` 的目录）。**不读任何游戏路径
  环境变量，没有硬编码默认**；缺省时由战网 product.db 探测。spec 会真实
  读取本机游戏 dbf 做存在性校验，manifest 的 `environment.game` / `dbf` /
  `catalog` 记录来路与身份；`--catalog` 仍是 spec 专属的开发逃逸口。
- 覆盖资产尺寸（preflight 静态校验，`asset_dimensions` 输入 2）：`portrait` 512×512、`frame` 1024×1024（类色图集，不是 512×707 整帧）、`watermark` 128×128 或 256×256；`watermark` 覆盖在场即强制显示；`runes` 键只允许 `BLOOD/FROST/UNHOLY`。
- `--locale`：游戏数据语言，默认 `zhcn`。
- `--cache-root`：route/supply 缓存根（相对 cwd）；缺省 `%LOCALAPPDATA%\Eidolon\cache`（Windows）或 `~/.cache/eidolon`。
- `-v` / `--debug`：INFO / DEBUG 日志（stderr）；`--debug` 让未预期异常打印 traceback。

### 批量模式（TOML）

```text
eidolon spec --toml job.toml
```

```toml
format_version = 1

out_dir = "out"
jobs = 1

[[cards]]
id = "CS1_113"

[[cards]]
id = 101954
hero_style = true
```

`--outdir` / `--jobs` / `--antialias` / `--hero-style` / `--bg-style` 只在命令行模式可用；批量模式的输出目录与进程数从文件顶层读取。`--game` 允许与 `--toml` 同用，优先于 TOML 顶层 `game_dir`（相对 TOML 文件目录，须为含 `Hearthstone.exe` 的安装根）。`--toml` 不能与位置 id 混用。

### 校验目录（--catalog）

```text
eidolon spec --toml job.toml --catalog catalog.json
```

- `--catalog` 是**开发用校验逃逸口**，只提供已知枚举与逐卡 `cardtype`
  （结构见 `tests/fixtures/catalog.json`），把无 catalog 时 deferred 的
  检查升级为真实校验；它**不是渲染事实源**。
- **仅 `spec` 可用**；与 `--game` / TOML `game_dir` / `render` 任一混用
  退出码 2（TOML `game_dir` 也算 `--game`）。
- catalog 未标 `"complete": true` 时，查不到的卡不阻塞，该卡涉及的
  catalog 检查记入 `deferred`；**仅当**确实有卡产生了 `deferred` 时，
  manifest 的 `warnings` 才加一条 `catalog_incomplete`（无 deferred 不加；
  complete catalog 查不到则直接 `unknown_card` 退出 2）。
- 不带 `--catalog` 且未接真实 dbf 时走 dev null catalog（deferred 路径）。

### spec 与 render

- `spec`：解析 + 校验 + 向 stdout 打印计划 manifest，不渲染。
- `render`：同上，然后经渲染端口 preflight（依赖 / locale / 安装完整性 /
  缓存与输出目录 / 覆盖资产与语义校验）→ 打印计划 manifest → 渲染 PNG →
  写结果 manifest（`out_dir/manifest.json`：逐卡 ok / sha256 / elapsed_ms /
  生效与请求的 style / overrides / 覆盖资产 sha / warnings）。

## 输出

`spec` / `render` 的计划 manifest 写 stdout（JSON，稳定键序，含
`environment` 段：游戏/dbf/catalog 身份 + `eidolon` 版本）。`render` 另写
结果 manifest 到 `out_dir/manifest.json`（逐卡结果 + warnings，见上文）。
错误写 stderr（`error[<code>] <path>: <message>` + hint）；输入非法或
preflight 未通过时 stdout 为空。输入 schema 与 manifest 结构见
`docs/schema.md`。

退出码：

| 码 | 含义 |
| --- | --- |
| `0` | 校验成功（`spec`）或渲染成功（`render`） |
| `1` | 逐卡渲染失败或内部错误 |
| `2` | 输入非法：用法/互斥、id/字段/TOML 语义、`unknown_card`、catalog 读取失败、preflight 的覆盖资产/语义校验 |
| `3` | 环境不可用（游戏/dbf/依赖/locale/权限/缓存或输出目录不可写） |
| `130` | 中断（Ctrl+C） |

## 测试

```bash
python -m unittest discover -s tests -t . -v
python -m eidolon spec --toml tests/fixtures/batch.toml --catalog tests/fixtures/catalog.json
```

## 游戏资源

炉石传说的名称、美术、声音、文本、脚本和其他素材属于对应权利人。本项目不提供游戏资源下载、不随源码分发游戏资源；本项目 MIT 许可证仅覆盖自有源码。
