"""守卫：core 包骨架约束与 Phase 1/3 落地预埋（扫描范围 = eidolon/core/**/*.py）。

- core 任何文件不得出现 env 访问（``os.environ`` / ``os.getenv`` /
  ``Path.home`` / ``expanduser``；白名单只有 ``eidolon/shell/paths.py``，
  不在 core 范围内，扫描器复用 env 守卫保证口径一致）；
- core 任何文件（含注释 / docstring）不得出现 ``HEARTHSTONE`` 字样；
- core 不得有 ``print(`` 调用（core 无 ``__main__``，故无豁免）；
- ``core/infra/dbf.py`` / ``core/infra/facts.py`` 不得出现 ``current(``——
  文件未落地（Phase 1 前）跳过，落地后自动生效；
- ``eidolon/core/__init__.py`` 必须为空（仅允许模块 docstring / 注释 / 空行，
  不得 import 子模块）；
- ``eidolon/adapters.py``（Phase 3）顶层 import 白名单：标准库 /
  ``eidolon.contracts`` / ``eidolon.shell.*``，禁止任何 ``eidolon.core``；
- ``eidolon/core/render/api.py``（Phase 3）顶层 import 白名单：标准库 /
  ``eidolon.contracts`` / ``eidolon.core.render.params``，禁止
  ``card`` / ``game_tag`` / ``dll_reflect`` / ``components`` / ``batch`` /
  ``render_with``（CLR 链只能进函数体，见设计 §7.1.1）；
- ``eidolon/core/render/{constants,card_overrides,assets,preflight}.py``
  （Phase 3b）顶层 import 白名单（设计 §7.4 注入面 / §6.5 CLR 时序）：
  ``constants`` 只许标准库 + contracts；``card_overrides`` 加
  ``render.constants`` 且禁止 ``card`` / ``game_tag`` / ``dll_reflect``；
  ``assets`` 加 PIL；``preflight`` 只许标准库 + contracts；
- ``eidolon/core/infra/catalog.py`` + ``facts.py`` 的顶层 import **传递闭包**
  只许标准库 + ``eidolon.contracts`` + 两者自身——不得含 ``UnityPy`` /
  ``dbf`` / ``card`` / ``game_tag`` / ``dll_reflect``（保证 spec 无
  UnityPy/CLR 可跑，设计 §6.4）。
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

from tests.architecture.test_env_guards import _scan as _env_scan
from tests.support import ROOT

PACKAGE_DIR = ROOT / "eidolon"
CORE_DIR = PACKAGE_DIR / "core"
# 取值日期 2026-11-09：core 实测 84 个 .py（Phase 1-4 渲染/supply/infra 全量
# 落地后）；下限防止守卫被搬空后静默通过（骨架期旧值 6 远低于实际覆盖面）。
MIN_CORE_FILES = 84

_NO_CURRENT_FILES = ("infra/dbf.py", "infra/facts.py")

# 设计 §7.1.1：api.py 顶层禁止的 CLR 渲染链模块（按叶子模块名匹配）
_API_BANNED_LEAVES = frozenset(
    {"card", "game_tag", "dll_reflect", "components", "batch", "render_with"}
)

# 设计 §7.4：card_overrides 顶层禁止的 live 枚举/反射链模块（按叶子模块名匹配）
_OVERRIDES_BANNED_LEAVES = frozenset({"card", "game_tag", "dll_reflect"})

# Phase 3b 四件的顶层 import 白名单（relpath → (allowed prefixes, banned leaves)）；
# allowed 判定 = 标准库 ∪ 前缀命中。api.py 的白名单沿用既有专测。
_PHASE3B_TOP_LEVEL_RULES: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
    "render/constants.py": (("eidolon.contracts",), frozenset()),
    "render/card_overrides.py": (
        ("eidolon.contracts", "eidolon.core.render.constants"),
        _OVERRIDES_BANNED_LEAVES,
    ),
    "render/assets.py": (("eidolon.contracts", "PIL"), frozenset()),
    "render/preflight.py": (("eidolon.contracts",), frozenset()),
}

# 设计 §6.4：catalog/facts 顶层 import 传递闭包只许这些 eidolon 模块。
_CLOSURE_ROOTS = ("infra/catalog.py", "infra/facts.py")
_CLOSURE_ALLOWED = frozenset(
    {"eidolon.contracts", "eidolon.core.infra.facts", "eidolon.core.infra.catalog"}
)


def _eidolon_module_file(name: str) -> Path | None:
    """eidolon 内部 import 名 → 本地文件（模块 .py 优先，其次包 __init__.py）。

    从全名逐级缩短取最长命中；非 eidolon 名返回 None。"""
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        if not (prefix == "eidolon" or prefix.startswith("eidolon.")):
            return None
        candidate = ROOT.joinpath(*parts[:i])
        module = candidate.with_name(candidate.name + ".py")
        if module.is_file():
            return module
        init = candidate / "__init__.py"
        if init.is_file():
            return init
    return None


def _closure_name_ok(name: str) -> bool:
    """import 名可接受 = 任一祖先前缀是标准库或闭包白名单成员。"""
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        if _is_stdlib(prefix) or prefix in _CLOSURE_ALLOWED:
            return True
    return False


def _core_files() -> list[Path]:
    files = sorted(CORE_DIR.rglob("*.py"))
    assert files, "core 包不存在"
    return files


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_of(path: Path) -> str:
    parts = path.relative_to(ROOT).with_suffix("").parts[:-1]
    return ".".join(parts)


def _resolve(module: str | None, level: int, package: str) -> str:
    """相对 import 还原成绝对名（level=1 即当前包）。"""
    if level == 0:
        return module or ""
    parts = package.split(".") if package else []
    base = parts[: len(parts) - (level - 1)]
    if module:
        return ".".join(base + [module])
    return ".".join(base)


def _top_level_imports(path: Path) -> list[str]:
    """模块顶层（函数 / 类体之外）import 的绝对名。

    ``from X import y`` 同时记录 ``X`` 与 ``X.y``（import X 的副作用
    与 ``from pkg import submodule`` 两种情况都要覆盖）。
    """
    tree = ast.parse(_text(path), filename=str(path))
    package = _package_of(path)
    names: list[str] = []
    for node in tree.body:  # 只看顶层语句
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve(node.module, node.level, package)
            for alias in node.names:
                if alias.name != "*":
                    names.append(f"{base}.{alias.name}" if base else alias.name)
            if base:
                names.append(base)
    return names


def _is_stdlib(name: str) -> bool:
    return name.split(".")[0] in sys.stdlib_module_names


def _allowed_prefixes(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        name == prefix or name.startswith(prefix + ".") for prefix in prefixes
    )


class CoreGuardTests(unittest.TestCase):
    def test_core_never_touches_env(self) -> None:
        files = _core_files()
        self.assertGreaterEqual(
            len(files), MIN_CORE_FILES, "core 守卫覆盖的文件数低于下限"
        )
        offenders: list[str] = []
        for path in files:
            for finding in _env_scan(path):
                offenders.append(f"{path.relative_to(ROOT)}: {finding}")
        self.assertEqual(offenders, [])

    def test_core_never_mentions_hearthstone(self) -> None:
        offenders: list[str] = []
        for path in _core_files():
            if "HEARTHSTONE" in _text(path):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_core_never_prints(self) -> None:
        offenders: list[str] = []
        for path in _core_files():
            tree = ast.parse(_text(path), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(
                    node.func, ast.Name
                ) and node.func.id == "print":
                    offenders.append(
                        f"{path.relative_to(ROOT)}: line {node.lineno}"
                    )
        self.assertEqual(offenders, [])

    def test_dbf_facts_never_call_current(self) -> None:
        # 文件未落地时跳过（Phase 1 落地后守卫自动生效）。
        offenders: list[str] = []
        for rel in _NO_CURRENT_FILES:
            path = CORE_DIR / rel
            if not path.exists():
                continue
            if "current(" in _text(path):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_catalog_facts_import_closure(self) -> None:
        # 设计 §6.4：catalog/facts 的顶层 import 传递闭包只许标准库 + contracts +
        # facts + catalog 自身；UnityPy / dbf / card / game_tag / dll_reflect
        # 一律不得出现（保证 spec 路径不加载 UnityPy/CLR）。
        offenders: list[str] = []
        visited: set[Path] = set()
        queue: list[Path] = [CORE_DIR / rel for rel in _CLOSURE_ROOTS]
        while queue:
            path = queue.pop()
            if path in visited:
                continue
            visited.add(path)
            self.assertTrue(path.is_file(), f"闭包根缺失：{path}")
            for name in _top_level_imports(path):
                if not _closure_name_ok(name):
                    offenders.append(f"{path.relative_to(ROOT)}: {name}")
                    continue
                module_file = _eidolon_module_file(name)
                if module_file is not None and module_file not in visited:
                    queue.append(module_file)
        self.assertEqual(offenders, [])

    def test_core_init_is_empty(self) -> None:
        path = CORE_DIR / "__init__.py"
        tree = ast.parse(_text(path), filename=str(path))
        offenders: list[str] = []
        for index, node in enumerate(tree.body):
            if (
                index == 0
                and isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                continue  # 模块 docstring 允许
            offenders.append(f"line {node.lineno}: {type(node).__name__}")
        self.assertEqual(offenders, [])

    def test_adapters_top_level_import_whitelist(self) -> None:
        # Phase 3 落地前文件不存在，跳过；落地后自动生效。
        path = PACKAGE_DIR / "adapters.py"
        if not path.exists():
            return
        allowed = ("eidolon.contracts", "eidolon.shell")
        offenders: list[str] = []
        for name in _top_level_imports(path):
            if _is_stdlib(name) or _allowed_prefixes(name, allowed):
                continue
            offenders.append(name)
        self.assertEqual(offenders, [])
        banned = [
            name
            for name in _top_level_imports(path)
            if name == "eidolon.core" or name.startswith("eidolon.core.")
        ]
        self.assertEqual(banned, [])

    def test_render_api_top_level_import_whitelist(self) -> None:
        # Phase 3 落地前文件不存在，跳过；落地后自动生效。
        path = CORE_DIR / "render" / "api.py"
        if not path.exists():
            return
        allowed = ("eidolon.contracts", "eidolon.core.render.params")
        offenders: list[str] = []
        for name in _top_level_imports(path):
            if _is_stdlib(name) or _allowed_prefixes(name, allowed):
                continue
            offenders.append(name)
        self.assertEqual(offenders, [])
        banned = [
            name
            for name in _top_level_imports(path)
            if name.split(".")[-1] in _API_BANNED_LEAVES
            and name.startswith("eidolon.core.")
        ]
        self.assertEqual(banned, [])

    def test_render_phase3b_top_level_import_whitelists(self) -> None:
        # 设计 §7.4 注入面 / §6.5 CLR 时序：constants/card_overrides/assets/
        # preflight 顶层只碰各自白名单；card_overrides 另禁 live 枚举链叶子。
        for rel, (allowed, banned_leaves) in _PHASE3B_TOP_LEVEL_RULES.items():
            path = CORE_DIR / "render" / Path(rel).name
            self.assertTrue(path.exists(), f"守卫对象缺失：render/{rel}")
            names = _top_level_imports(path)
            offenders = [
                name for name in names
                if not (_is_stdlib(name) or _allowed_prefixes(name, allowed))
            ]
            self.assertEqual(
                offenders, [],
                f"render/{rel} 顶层 import 超出白名单 {allowed}")
            banned = [
                name for name in names
                if name.split(".")[-1] in banned_leaves
                and name.startswith("eidolon.core.")
            ]
            self.assertEqual(
                banned, [],
                f"render/{rel} 顶层不得 import live 枚举/反射链 {sorted(banned_leaves)}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
