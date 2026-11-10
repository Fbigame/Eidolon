"""集成测试目录。

真实 dbf / 游戏安装的集成测试文件用 integration_*.py 命名；默认 discover
（test*.py）不加载，显式运行：

    python -m unittest discover -s tests/integration -p "integration_*.py" -t . -v

默认测试的 skip 数必须为 0：不用 skipUnless，直接按文件名隔离。
"""
