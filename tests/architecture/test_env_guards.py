"""守卫：OS 目录变量只在 shell/paths.py 读取；禁止游戏路径 env。

- ``os.environ`` / ``os.getenv`` / ``Path.home`` / ``expanduser`` 只允许
  出现在 ``eidolon/shell/paths.py``；
- paths.py 里读的键名白名单：LOCALAPPDATA / XDG_CACHE_HOME / HOME / WINDIR；
- 任何位置出现 ``HEARTHSTONE`` 字样即失败；
- 任何位置写 ``os.environ``（Subscript Store / setattr）即失败。
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from tests.support import ROOT

PACKAGE_DIR = ROOT / "eidolon"
PATHS_MODULE = PACKAGE_DIR / "shell" / "paths.py"

# 取值日期 2026-11-09：eidolon/**/*.py 实测 100 个（core 接入全量落地后；
# 旧值 10 是 shell 期骨架面）。下限防止守卫被搬空后静默通过。
MIN_PACKAGE_FILES = 100

_ALLOWED_ENV_KEYS = frozenset({"LOCALAPPDATA", "XDG_CACHE_HOME", "HOME", "WINDIR"})


def _is_os(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "os"


def _is_os_environ(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and _is_os(node.value)
    )


def _is_environ_value(node: ast.AST) -> bool:
    """os.environ，或 ``from os import environ`` 后的裸 ``environ``。"""
    return _is_os_environ(node) or (isinstance(node, ast.Name) and node.id == "environ")


def _is_getenv_func(func: ast.AST) -> bool:
    """os.getenv，或 ``from os import getenv`` 后的裸 ``getenv``。"""
    if isinstance(func, ast.Name):
        return func.id == "getenv"
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "getenv"
        and _is_os(func.value)
    )


def _scan(path: Path) -> list[str]:
    """返回该文件的 env 相关访问记录（供白名单判定）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # from os import environ / getenv：导入即记为 env 访问。
            if node.module == "os":
                for alias in node.names:
                    if alias.name in {"environ", "getenv"}:
                        findings.append(f"from_os:{alias.name}")
        elif isinstance(node, ast.Call):
            func = node.func
            # os.environ.get("KEY") / 裸 environ.get("KEY")
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and _is_environ_value(func.value)
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                findings.append(f"environ.get:{node.args[0].value}")
            elif _is_getenv_func(func) and node.args and isinstance(node.args[0], ast.Constant):
                key = node.args[0].value
                findings.append(f"os.getenv:{key}")
                if "HEARTHSTONE" in key:
                    findings.append(f"hearthstone:{key!r}")
            # Path.home() / <path>.expanduser()
            elif isinstance(func, ast.Attribute) and func.attr in {"home", "expanduser"}:
                findings.append(f"path:{func.attr}")
        elif isinstance(node, ast.Subscript):
            # os.environ["KEY"] / 裸 environ["KEY"] 读取或写入（其他 Subscript 与 env 无关）
            if _is_environ_value(node.value):
                access = "environ.store" if isinstance(node.ctx, ast.Store) else "environ.load"
                key = None
                if isinstance(node.slice, ast.Constant):
                    key = node.slice.value
                    if "HEARTHSTONE" in key:
                        findings.append(f"hearthstone:{key!r}")
                findings.append(f"{access}:{key}")
        elif isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
            # 裸引用（读取 / 传递 / 赋值目标）
            findings.append(f"ref:{node.attr}")
    return findings


class EnvGuardTests(unittest.TestCase):
    def _python_files(self) -> list[Path]:
        files = sorted(PACKAGE_DIR.rglob("*.py"))
        self.assertGreaterEqual(
            len(files), MIN_PACKAGE_FILES, "env 守卫覆盖的文件数低于下限"
        )
        return files

    def test_env_access_only_in_paths_module(self) -> None:
        offenders: list[str] = []
        for path in self._python_files():
            if path == PATHS_MODULE:
                continue
            for finding in _scan(path):
                offenders.append(f"{path.relative_to(ROOT)}: {finding}")
        self.assertEqual(offenders, [])

    def test_paths_module_reads_only_allowed_keys(self) -> None:
        offenders: list[str] = []
        for finding in _scan(PATHS_MODULE):
            kind, _, key = finding.partition(":")
            if kind == "hearthstone":
                offenders.append(finding)
            elif kind in {"environ.get", "os.getenv", "environ.load"}:
                if key not in _ALLOWED_ENV_KEYS:
                    offenders.append(finding)
            elif kind == "environ.store":
                offenders.append(finding)
        self.assertEqual(offenders, [])

    def test_no_hearthstone_anywhere(self) -> None:
        offenders: list[str] = []
        for path in self._python_files():
            for finding in _scan(path):
                if finding.startswith("hearthstone"):
                    offenders.append(f"{path.relative_to(ROOT)}: {finding}")
        self.assertEqual(offenders, [])

    def test_catches_from_os_import_and_bare_environ(self) -> None:
        # 回归：`from os import environ` + 裸 environ["KEY"] 必须被抓到。
        import tempfile

        canary = (
            "from os import environ, getenv\n"
            "v = environ['HEARTHSTONE_DIR']\n"
            "w = getenv('HEARTHSTONE_DATA')\n"
            "environ['X'] = '1'\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canary.py"
            path.write_text(canary, encoding="utf-8")
            findings = _scan(path)
        self.assertTrue(any(f.startswith("from_os:") for f in findings), findings)
        self.assertTrue(any(f.startswith("hearthstone:") for f in findings), findings)
        self.assertTrue(any(f.startswith("environ.load:") for f in findings), findings)
        self.assertTrue(any(f.startswith("os.getenv:") for f in findings), findings)
        self.assertTrue(any(f.startswith("environ.store:") for f in findings), findings)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
