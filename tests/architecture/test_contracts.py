"""contracts 契约：纯净性（只 stdlib、无 I/O）与类型不变量。"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

from eidolon.contracts import (
    CardFacts,
    CardRef,
    CatalogBinding,
    CatalogIdentity,
    EnvironmentUnavailable,
    GameContext,
    GameRequest,
    InputRejected,
    Problem,
    ProblemKind,
    RenderCard,
    RenderRequest,
    RenderedCard,
    RenderFailure,
    RenderReport,
)
from tests.support import ROOT

CONTRACTS = ROOT / "eidolon" / "contracts.py"

_FORBIDDEN_CALLS = frozenset(
    {"open", "write_text", "read_text", "mkdir", "unlink", "stat", "glob", "rglob"}
)


class ContractsPurityTests(unittest.TestCase):
    def test_imports_are_stdlib_only(self) -> None:
        allowed = set(sys.stdlib_module_names) | {"eidolon"}
        tree = ast.parse(CONTRACTS.read_text(encoding="utf-8"), filename=str(CONTRACTS))
        roots: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    roots.append("eidolon")
                elif node.module:
                    roots.append(node.module.split(".")[0])
        offenders = [root for root in roots if root not in allowed]
        self.assertEqual(offenders, [])

    def test_no_io_in_contracts(self) -> None:
        tree = ast.parse(CONTRACTS.read_text(encoding="utf-8"), filename=str(CONTRACTS))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in _FORBIDDEN_CALLS:
                offenders.append(f"contracts.py:{node.lineno}:{name}")
        self.assertEqual(offenders, [])


class ProblemTests(unittest.TestCase):
    def test_frozen_value_semantics(self) -> None:
        first = Problem(ProblemKind.INPUT, "invalid_id", "ids[0]", "msg")
        second = Problem(ProblemKind.INPUT, "invalid_id", "ids[0]", "msg")
        self.assertEqual(first, second)
        with self.assertRaises(Exception):
            first.code = "x"  # type: ignore[misc]

    def test_defaults(self) -> None:
        problem = Problem(ProblemKind.INPUT, "mode", "<input>", "msg")
        self.assertEqual(problem.hint, "")
        self.assertEqual(problem.cause, "")


class EnvironmentUnavailableTests(unittest.TestCase):
    def test_carries_environment_problem(self) -> None:
        problem = Problem(ProblemKind.ENVIRONMENT, "game_not_found", "p", "msg")
        exc = EnvironmentUnavailable(problem)
        self.assertIs(exc.problem, problem)

    def test_rejects_non_environment_kind(self) -> None:
        problem = Problem(ProblemKind.INPUT, "mode", "p", "msg")
        with self.assertRaises(ValueError):
            EnvironmentUnavailable(problem)


class InputRejectedTests(unittest.TestCase):
    """core 的输入类错误（§5.3；构造形状对齐 EnvironmentUnavailable）。"""

    def test_carries_input_problem(self) -> None:
        problem = Problem(ProblemKind.INPUT, "enum", "cards[0].classes", "msg")
        exc = InputRejected(problem)
        self.assertIs(exc.problem, problem)

    def test_message_carried(self) -> None:
        exc = InputRejected(Problem(ProblemKind.INPUT, "style", "p", "互斥"))
        self.assertEqual(str(exc), "互斥")

    def test_rejects_non_input_kind(self) -> None:
        for kind in (ProblemKind.ENVIRONMENT, ProblemKind.RENDER,
                     ProblemKind.INTERNAL):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    InputRejected(Problem(kind, "x", "p", "msg"))


class CardRefTests(unittest.TestCase):
    def test_dbf_and_card(self) -> None:
        self.assertEqual(CardRef("dbf", 8).value, 8)
        self.assertTrue(CardRef("dbf", 8).is_dbf)
        self.assertFalse(CardRef("card", "CS2_182").is_dbf)

    def test_validation(self) -> None:
        for kind, value in (("hero", 8), ("dbf", "8"), ("card", 8)):
            with self.subTest(kind=kind, value=value):
                with self.assertRaises(ValueError):
                    CardRef(kind, value)  # type: ignore[arg-type]


class CardFactsTests(unittest.TestCase):
    def test_only_cardtype(self) -> None:
        facts = CardFacts(cardtype="MINION")
        self.assertEqual(facts.cardtype, "MINION")
        # rev4：classes 没有 shell 消费点，不进契约。
        self.assertFalse(hasattr(facts, "classes"))


class GameContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = GameContext(
            root=Path("D:/Games/Hearthstone"),
            cache_root=Path("C:/cache/eidolon"),
        )

    def test_derived_paths(self) -> None:
        # player 数据根是 <root>/Hearthstone_Data，不是 Data/Win。
        self.assertEqual(self.ctx.data_win, Path("D:/Games/Hearthstone/Data/Win"))
        self.assertEqual(
            self.ctx.dbf_path, Path("D:/Games/Hearthstone/Data/Win/dbf.unity3d")
        )
        self.assertEqual(
            self.ctx.strings_dir, Path("D:/Games/Hearthstone/Strings/zhcn")
        )
        self.assertEqual(
            self.ctx.managed, Path("D:/Games/Hearthstone/Hearthstone_Data/Managed")
        )
        self.assertEqual(
            self.ctx.assembly_csharp,
            Path("D:/Games/Hearthstone/Hearthstone_Data/Managed/Assembly-CSharp.dll"),
        )
        self.assertEqual(
            self.ctx.resources,
            Path("D:/Games/Hearthstone/Hearthstone_Data/resources.assets"),
        )
        self.assertEqual(
            self.ctx.globalgamemanagers,
            Path("D:/Games/Hearthstone/Hearthstone_Data/globalgamemanagers"),
        )

    def test_route_cache_is_cache_root_alias(self) -> None:
        self.assertIs(self.ctx.route_cache, self.ctx.cache_root)

    def test_game_exe_property(self) -> None:
        # 安装根完整性字面量（load_input 校验与 core preflight 共用）。
        self.assertEqual(
            self.ctx.game_exe, Path("D:/Games/Hearthstone/Hearthstone.exe")
        )

    def test_identity_six_tuple(self) -> None:
        ctx = GameContext(
            root=Path("D:/Games/Hearthstone"),
            cache_root=Path("C:/cache/eidolon"),
            locale="zhcn",
            version="37.0.2",
            route_mode="auto",
            version_strict=False,
        )
        self.assertEqual(
            ctx.identity(),
            (ctx.root, ctx.cache_root, ctx.locale, ctx.version,
             ctx.route_mode, ctx.version_strict),
        )

    def test_identity_ignores_provenance(self) -> None:
        # 来路账（root_source / version_source）不参与身份：同根不同来路 = 同身份。
        first = GameContext(
            root=Path("D:/Games/Hearthstone"),
            cache_root=Path("C:/cache"),
            version="37.0.2",
            root_source="--game",
            version_source="product.db",
        )
        second = GameContext(
            root=Path("D:/Games/Hearthstone"),
            cache_root=Path("C:/cache"),
            version="37.0.2",
            root_source="product.db",
            version_source="power.log:x",
        )
        self.assertEqual(first.identity(), second.identity())
        self.assertNotEqual(first, second)  # __eq__ 仍全字段比较（含账面）

    def test_defaults(self) -> None:
        self.assertEqual(self.ctx.locale, "zhcn")
        self.assertIsNone(self.ctx.version)
        self.assertEqual(self.ctx.route_mode, "auto")
        self.assertIs(self.ctx.version_strict, False)


class BindingTypesTests(unittest.TestCase):
    def test_game_request_defaults(self) -> None:
        self.assertEqual(GameRequest(None).source, "")
        request = GameRequest(Path("D:/Games/Hearthstone"), source="--game")
        self.assertEqual(request.game_dir, Path("D:/Games/Hearthstone"))

    def test_catalog_identity_defaults(self) -> None:
        identity = CatalogIdentity(kind="null")
        self.assertEqual(identity.path, "")
        self.assertEqual(identity.size, 0)
        self.assertEqual(identity.mtime_ns, 0)
        self.assertIs(identity.complete, False)

    def test_catalog_binding_defaults(self) -> None:
        binding = CatalogBinding(
            catalog=_FakeCatalog(), game=None, identity=CatalogIdentity(kind="null")
        )
        self.assertEqual(binding.warnings, ())


class RenderShapeTests(unittest.TestCase):
    """core 渲染端口形状（§5.2：RenderCard / RenderRequest + warnings 面）。"""

    def setUp(self) -> None:
        self.ctx = GameContext(root=Path("D:/Games/Hearthstone"),
                               cache_root=Path("C:/cache/eidolon"))

    def test_render_card_defaults(self) -> None:
        card = RenderCard(ref=CardRef("dbf", 8), out_path=Path("o/a.png"))
        self.assertEqual(card.overrides, {})
        self.assertEqual(card.assets, {})
        self.assertIs(card.hero_style, False)
        self.assertIs(card.bg_style, False)
        self.assertIsNone(card.session_t)

    def test_render_card_is_frozen(self) -> None:
        card = RenderCard(ref=CardRef("dbf", 8), out_path=Path("o/a.png"))
        with self.assertRaises(Exception):
            card.hero_style = True  # type: ignore[misc]

    def test_render_request_defaults_and_kw_only_game(self) -> None:
        request = RenderRequest(cards=(), out_dir=Path("o"), game=self.ctx)
        self.assertEqual(request.jobs, 1)
        self.assertIs(request.antialias, False)
        self.assertEqual(request.font_dirs, ())
        self.assertIs(request.game, self.ctx)

    def test_render_request_requires_game(self) -> None:
        with self.assertRaises(TypeError):
            RenderRequest(cards=(), out_dir=Path("o"))  # type: ignore[call-arg]

    def test_rendered_card_warnings_default(self) -> None:
        card = RenderedCard(ref=CardRef("dbf", 8), path=Path("x"),
                            sha256="ab", elapsed_ms=1)
        self.assertEqual(card.warnings, ())

    def test_report_defaults_empty(self) -> None:
        report = RenderReport()
        self.assertEqual(report.rendered, ())
        self.assertEqual(report.failures, ())
        self.assertEqual(report.warnings, ())

    def test_report_is_frozen(self) -> None:
        report = RenderReport()
        with self.assertRaises(Exception):
            report.rendered = ()  # type: ignore[misc]

    def test_failure_carries_problem(self) -> None:
        problem = Problem(ProblemKind.RENDER, "render_failed", "x.png", "boom")
        failure = RenderFailure(
            ref=CardRef("dbf", 8), path=Path("x.png"), problem=problem
        )
        self.assertIs(failure.problem, problem)
        rendered = RenderedCard(
            ref=CardRef("dbf", 8), path=Path("x.png"), sha256="ab12", elapsed_ms=7
        )
        report = RenderReport(rendered=(rendered,), failures=(failure,))
        self.assertEqual(report.rendered[0].sha256, "ab12")
        self.assertEqual(report.failures[0].problem.code, "render_failed")

    def test_render_port_annotations_resolve(self) -> None:
        # ports.py 曾用未定义的字符串注解占位；现在必须可解析。
        from typing import get_type_hints

        from eidolon.contracts import RenderReport as RenderReportContract
        from eidolon.shell.ports import RenderPort
        from eidolon.shell.spec import RenderSpec

        hints = get_type_hints(RenderPort.render)
        self.assertIs(hints["spec"], RenderSpec)
        self.assertIs(hints["return"], RenderReportContract)
        preflight_hints = get_type_hints(RenderPort.preflight)
        # get_type_hints 把 `-> None` 解析成 NoneType。
        self.assertIs(preflight_hints["return"], type(None))


class _FakeCatalog:
    complete = False
    known_classes: tuple[str, ...] = ()
    known_cardtypes: tuple[str, ...] = ()
    known_rarities: tuple[str, ...] = ()
    known_spell_schools: tuple[str, ...] = ()

    def lookup(self, ref: CardRef) -> CardFacts | None:
        return None


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
