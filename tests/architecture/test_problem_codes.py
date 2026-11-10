"""守卫：Problem code 注册表、kind 唯一性、测试目录结构、discover 下限。"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from eidolon.contracts import ProblemKind
from eidolon.shell.errors import CODES
from tests.support import ROOT

PACKAGE_DIR = ROOT / "eidolon"
TESTS_DIR = ROOT / "tests"

# 不随 discover 默认进入的目录（fixtures 无测试；__pycache__ 非源码）。
_SKIP_DIRS = frozenset({"fixtures", "__pycache__"})
# 取值日期 2026-11-09：discover 实测 559 例（写入时口径；同日终回归 560——
# 并行返工批次在途加例推高，下限不追上限）。下限只防「守卫被搬空 /
# 0 tests OK」。
MIN_DISCOVER_TESTS = 559
# 取值日期 2026-11-09：全包 ``Problem(`` 调用点实测 35 处（位置参数 31 +
# 关键字 4）；其中 31 处可静态解析出 code 字面量。审计 P2 起补 helper 间接层
# 的**调用点**解析（_HELPER_CODE_ARG：helper 把 code 透传给内部 Problem），
# 三个 helper 的调用点逐个人工可解析；仅剩 ``SpecError.as_problem`` 的
# ``self.code``（实例状态，静态不可解析——由 errors.add 扫描 + 单测覆盖）。
MIN_PROBLEM_SITES = 35
MIN_RESOLVED_CODES = 31

# helper 名 → code 参数下标（helper 内部 Problem 的 code 来自该形参；调用点
# 字面量由此可解析，闭合「helper 间接层」盲区）。
_HELPER_CODE_ARG = {
    "_env_unavailable": 0,
    "_asset_rejected": 0,
    "_input_rejected": 1,
}


def _python_files() -> list[Path]:
    return sorted(PACKAGE_DIR.rglob("*.py"))


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_calls() -> list[tuple[Path, ast.Call, dict[str, str]]]:
    """全包函数调用扫描；附带每文件的模块级字符串常量表（code 常量名解析用）。"""
    calls: list[tuple[Path, ast.Call, dict[str, str]]] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        constants = _file_constants(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                calls.append((path, node, constants))
    return calls


def _func_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _file_constants(tree: ast.Module) -> dict[str, str]:
    """模块级简单赋值 ``NAME = "字面量"``（game_install 的 _GAME_NOT_FOUND 等常量）。"""
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if (
                isinstance(target, ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                constants[target.id] = node.value.value
    return constants


def _kind_expr(node: ast.AST) -> str | None:
    """``ProblemKind.X`` 枚举引用 → kind 值；其他形状 None。"""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "ProblemKind"
    ):
        return ProblemKind[node.attr].value
    return None


def _code_arg(call: ast.Call, constants: dict[str, str]) -> str | None:
    """``Problem(...)`` 的 code 实参字面量；静态不可确定 → None。

    覆盖形状（2026-11-09 全包实测 37 处调用点）：
    - 关键字 ``code="x"``（shell cli / entry，4 处）；
    - 位置参数 ``Problem(ProblemKind.X, "x", ...)``——core 全部走这个形状
      （审计 P1-7 指认：旧扫描只看关键字，core 一处都扫不到）；
    - 位置参数为模块级字符串常量名（game_install 的 ``_GAME_NOT_FOUND`` 等）。
    已知盲区（仅 1 处）：``SpecError.as_problem`` 的 ``self.code``——实例状态，
    静态不可解析；helper 间接层（``_env_unavailable`` / ``_asset_rejected`` /
    ``_input_rejected``）的**调用点**由 ``_HELPER_CODE_ARG`` 单独扫描（见
    ``test_literal_codes_registered``），不留盲区。
    """
    code = _literal(_keyword(call, "code") or ast.Constant(value=None))
    if code is not None:
        return code
    if len(call.args) < 2 or _kind_expr(call.args[0]) is None:
        return None  # 第一位置参数不是 ProblemKind.X——非既定构造形状
    second = call.args[1]
    code = _literal(second)
    if code is not None:
        return code
    if isinstance(second, ast.Name):
        return constants.get(second.id)
    return None


def _kind_arg(call: ast.Call) -> str | None:
    """kind 实参：关键字 ``kind=`` 优先，否则第一位置参数。"""
    kind_node = _keyword(call, "kind")
    if kind_node is not None:
        if isinstance(kind_node, ast.Constant) and isinstance(kind_node.value, str):
            return kind_node.value
        return _kind_expr(kind_node)
    if call.args:
        return _kind_expr(call.args[0])
    return None


class ProblemRegistryTests(unittest.TestCase):
    """所有 errors.add(...) / Problem(code=...) 字面量都必须已注册。"""

    def test_literal_codes_registered(self) -> None:
        unregistered: list[str] = []
        total = 0
        resolved = 0
        helper_calls = 0
        helper_unresolved: list[str] = []
        for path, call, constants in _scan_calls():
            name = _func_name(call)
            if name in _HELPER_CODE_ARG:
                # helper 间接层：code 是 helper 形参；解析调用点对应实参。
                idx = _HELPER_CODE_ARG[name]
                helper_calls += 1
                arg = call.args[idx] if len(call.args) > idx else None
                code = _literal(arg) if arg is not None else None
                if code is None and isinstance(arg, ast.Name):
                    code = constants.get(arg.id)
                if code is None:
                    helper_unresolved.append(f"{path.name}: {name}(...)")
                elif code not in CODES:
                    unregistered.append(f"{path.name}: {name}(code={code!r})")
            if name == "add":
                # errors.add(code, path, message)：三个位置参数，首个是字符串字面量。
                # （deferred.add / seen.add 等 set 操作只有一个参数，不匹配。）
                if len(call.args) >= 3:
                    code = _literal(call.args[0])
                    if code is not None and code not in CODES:
                        unregistered.append(f"{path.name}: add({code!r})")
            elif name == "Problem":
                total += 1
                code = _code_arg(call, constants)
                if code is not None:
                    resolved += 1
                    if code not in CODES:
                        unregistered.append(f"{path.name}: Problem(code={code!r})")
        self.assertGreaterEqual(
            total, MIN_PROBLEM_SITES, "Problem( 调用点少于下限——扫描器或源面漂移"
        )
        self.assertGreaterEqual(
            resolved, MIN_RESOLVED_CODES, "可解析 code 的调用点少于下限"
        )
        self.assertGreater(helper_calls, 0, "helper 调用点扫描为 0——形状漂移")
        self.assertEqual(helper_unresolved, [],
                         f"helper 调用点 code 不可解析：{helper_unresolved}")
        self.assertEqual(unregistered, [])

    def test_problem_kind_unique_per_code(self) -> None:
        kinds_by_code: dict[str, set[str]] = {}
        for _path, call, constants in _scan_calls():
            if _func_name(call) != "Problem":
                continue
            code = _code_arg(call, constants)
            if code is None:
                continue
            kind = _kind_arg(call)
            if kind is None:
                continue
            kinds_by_code.setdefault(code, set()).add(kind)
        mixed = {code: kinds for code, kinds in kinds_by_code.items() if len(kinds) > 1}
        self.assertEqual(mixed, {})

    def test_every_registered_code_has_hint(self) -> None:
        empty = [code for code, hint in CODES.items() if not hint.strip()]
        self.assertEqual(empty, [])

    def test_kind_members_cover_registry_groups(self) -> None:
        # kind 值与退出码约定：input/environment/render/internal。
        self.assertEqual(
            {member.value for member in ProblemKind},
            {"input", "environment", "render", "internal"},
        )


class TestLayoutTests(unittest.TestCase):
    def test_test_directories_have_init(self) -> None:
        missing: list[str] = []
        for child in sorted(TESTS_DIR.iterdir()):
            if not child.is_dir() or child.name in _SKIP_DIRS:
                continue
            if not (child / "__init__.py").is_file():
                missing.append(child.name)
        self.assertEqual(missing, [])

    def test_discovery_count_floor(self) -> None:
        loader = unittest.TestLoader()
        suite = loader.discover(str(TESTS_DIR), top_level_dir=str(ROOT))
        self.assertGreaterEqual(
            suite.countTestCases(),
            MIN_DISCOVER_TESTS,
            "discover 数量低于下限，防止「0 tests OK」",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
