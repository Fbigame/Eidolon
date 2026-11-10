# Eidolon — 产品仓

离线炉石卡牌渲染器。输入一张或一批卡牌的规格，输出 PNG；运行时不依赖游戏客户端。

## 目录与分层

目标结构：

```text
eidolon/
  __init__.py   # 公开 API re-export（不 import core）
  __main__.py   # python -m eidolon → entry.main
  version.py    # __version__（manifest 用）
  entry.py      # 组合根
  adapters.py   # 组合层适配器（CoreRenderPort；顶层只 import 标准库/contracts/shell）
  contracts.py  # CardRef / CardFacts / CardCatalog / GameContext / GameRequest / CatalogIdentity / Problem / RenderShape
  shell/        # cli / input / spec / manifest / catalog / paths / errors / ports / toml_io
  core/         # infra / supply / supply_index / recipes / render
tests/
  shell/  core/  entry/  architecture/  integration/  fixtures/
docs/           # schema、architecture
examples/       # 批量 TOML 示例
```

- 依赖方向：**组合层（`entry.py` / `adapters.py`）→ shell/core；shell 与 core 互不 import，只共同依赖 `contracts`**。
- `shell/` 只用标准库 + `contracts` + `version` + `shell.*`；`core/` 不得 import `shell/`；`contracts.py` 不放 I/O。
- 输入分两阶段：`load_input`（结构/类型/路径，不碰游戏数据）→ `provider.bind` → `compile_spec`（只做 catalog 依赖检查）。
- `shell/ports.py` 只放协议；适配器在组合层，Card 构造留在 core。
- 错误统一 `Problem(kind / code / path / hint / cause)`；`CODES` 只存默认 hint（kind 由产生点给）；退出码只做粗分类。
- 生产约定：shell 发 `input`；core 发 `environment`；组合层（entry / adapters，含 preflight）可发 `input` / `environment` / `render` / `internal`。
- 跨切面设施（日志 / 时钟 / 路径）用标准库 + entry 配置，不建公共 infra；dbf 等游戏适配器留在 `core/infra`。
- 搬迁与 core 接入已完成：`eidolon/` 顶层放 `__init__` / `__main__` / `version` / `entry` / `contracts` / `adapters.py`，实现在 `shell/` + `core/`。

## 输入与输出

- 命令行：`eidolon spec|render <id>... [--outdir] [--jobs] [--hero-style] [--bg-style] [--antialias] [--game] [--locale] [--cache-root] [--catalog] [-v] [--debug]`
- TOML：`format_version = 1`；顶层 `out_dir` / `jobs` / `antialias` / `game_dir`；`[[cards]]` + `[cards.asset]`。
- 统一面：`RenderSpec`（CardSpec 列表 + 全局选项 + game / catalog 身份）。
- `spec` 输出 manifest（JSON，不渲染）；`render` 的 preflight 通过后先打印计划清单，结果 manifest 写 `out_dir/manifest.json`。
- `--catalog` 仅用于 `spec`，与 `--game` / TOML `game_dir` 互斥；真实模式需要游戏安装。
- 字段与校验以 `docs/schema.md` 为准。

## 路径与环境

- `game_dir`：显式 `--game` / TOML `game_dir` > 战网 product.db 探测 > 报错。**不读游戏输入环境变量，不保留硬编码默认。**
- `locale`：`--locale` > `"zhcn"`（产品/语料默认）；v1 不支持 TOML `locale`。
- route / supply 缓存：`--cache-root` > 默认用户缓存目录；OS 级目录变量（`LOCALAPPDATA` / `XDG_CACHE_HOME` / `HOME` / `WINDIR`）只用于算默认根（`WINDIR` / `LOCALAPPDATA` 还用于默认字体目录）。
- 运行期不修改 `os.environ`。

## 边界

- 不随仓分发游戏资产、字体或客户端提取物。
- 无覆盖渲染是基准路径；有覆盖（文本 / 字段 / 资源）是自定义渲染，不声称与游戏一致。
- 覆盖注入落在 plan / supply 层，不改进程级 scene 缓存；输出缓存 key 必须包含覆盖项与资产 sha。
- 不把游戏提取物或私有路径写进公开文件。

## 构建与测试

- Python 3.13+；shell 与 contracts 只用标准库。
- `python -m unittest discover -s tests -t . -v`
- `python -m eidolon spec --toml tests/fixtures/batch.toml --catalog tests/fixtures/catalog.json`
- `python -m eidolon spec --toml examples/batch.toml --game <game-install-root>`（真实 dbf bind；示例 asset 缺失会在输入阶段先报 asset_missing）
- `python -m eidolon render ...`（真实渲染：preflight → 计划 manifest → PNG + 结果 manifest）
