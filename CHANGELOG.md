# Changelog

## 0.1.1

- route 缓存 v6：新增全局 cab 索引，跨包资源定位更快
- 首次渲染按请求卡集预热 route 缓存：只建工作集，不再触发全量建库
- 资产格式错误改为 typed 错误（环境类退出码）；route 脏标记改按进程 pid 判定；字体/locale 失败面收口
- scoped route 缓存的内容失配自愈：lazy 补行原位刷新，健康门多失配逐个修复
- CI 与 nightly 工作流

## 0.1.0

- 离线卡牌渲染：读取本地游戏安装，输出 PNG 与结果 manifest
- CLI / TOML 批量；hero/bg 形态；frame / portrait / watermark 覆盖
- 统一错误对象与退出码；结果 manifest 逐卡 ok/error
- 环境：Windows、Python 3.13、本地游戏安装、.NET 运行时

已知限制

- 默认是预览质量；需要更高质量时用 `--antialias`
- 首次运行需要建立缓存，耗时取决于安装大小与磁盘
- 无输出缓存、无逐卡进度
