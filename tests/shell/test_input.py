"""load_input / InputDraft：两阶段输入的阶段一（结构 / game_dir / 互斥）。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from eidolon.contracts import GameRequest
from eidolon.shell.errors import SpecErrors
from eidolon.shell.input import InputDraft, load_input
from tests.support import CATALOG_JSON, TomlCase


def make_args(**kw) -> SimpleNamespace:
    base = dict(
        command="spec",
        ids=[],
        toml=None,
        outdir=None,
        jobs=None,
        antialias=None,
        hero_style=None,
        bg_style=None,
        catalog=None,
        game=None,
        locale=None,
        cache_root=None,
        verbose=False,
        debug=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def make_game_root(parent: Path, name: str = "game", *, exe: bool = True) -> Path:
    root = parent / name
    root.mkdir(parents=True, exist_ok=True)
    if exe:
        (root / "Hearthstone.exe").write_bytes(b"")
    return root


def load_errors(args: SimpleNamespace, cwd: Path) -> SpecErrors:
    try:
        load_input(args, cwd)
    except SpecErrors as exc:
        return exc
    raise AssertionError("预期 load_input 失败，但成功了")


def assert_error_code(errors: SpecErrors, code: str, path: str) -> None:
    for error in errors.errors:
        if error.code == code and error.path == path:
            return
    raise AssertionError(
        f"未找到 {code}@{path}；实际：{[(e.code, e.path) for e in errors.errors]}"
    )


class InlineDraftTests(TomlCase):
    def test_inline_draft_shape(self) -> None:
        draft = load_input(make_args(ids=["8", "CS2_182"], command="render"), self.tmp)
        self.assertIsInstance(draft, InputDraft)
        self.assertEqual(draft.command, "render")
        self.assertEqual(draft.source, "inline")
        self.assertEqual(draft.catalog_path, None)
        self.assertEqual(
            draft.game, GameRequest(game_dir=None, source="")
        )
        self.assertEqual([card.ref.value for card in draft.cards], [8, "CS2_182"])
        self.assertEqual(draft.cards[0].outname, "8.png")
        self.assertEqual(dict(draft.cards[0].overrides), {})
        self.assertTrue(draft.cards[0].out_path.is_absolute())

    def test_inline_options(self) -> None:
        draft = load_input(
            make_args(ids=["8"], outdir="out", jobs=4, antialias=True), self.tmp
        )
        self.assertEqual(draft.options.out_dir, (self.tmp / "out").resolve())
        self.assertEqual(draft.options.jobs, 4)
        self.assertTrue(draft.options.antialias)
        self.assertFalse(draft.options.hero_style)

    def test_inline_global_style_requests_live_in_options(self) -> None:
        draft = load_input(
            make_args(ids=["8"], hero_style=True, bg_style=True), self.tmp
        )
        self.assertTrue(draft.options.hero_style)
        self.assertTrue(draft.options.bg_style)
        self.assertFalse(draft.cards[0].hero_style)


class GameRequestTests(TomlCase):
    def test_explicit_game_validated(self) -> None:
        root = make_game_root(self.tmp)
        draft = load_input(make_args(ids=["8"], game=str(root)), self.tmp)
        self.assertEqual(draft.game.game_dir, root.resolve())
        self.assertEqual(draft.game.source, "--game")

    def test_toml_game_dir_relative_to_toml_dir(self) -> None:
        root = make_game_root(self.tmp)
        toml = self.write_toml(
            'format_version = 1\ngame_dir = "game"\n\n[[cards]]\nid = 8\n'
        )
        draft = load_input(make_args(toml=str(toml)), self.tmp)
        self.assertEqual(draft.game.game_dir, root.resolve())
        self.assertEqual(draft.game.source, "toml game_dir")

    def test_cli_game_wins_over_toml_game_dir(self) -> None:
        root_cli = make_game_root(self.tmp, "cli-game")
        make_game_root(self.tmp, "toml-game")
        toml = self.write_toml(
            'format_version = 1\ngame_dir = "toml-game"\n\n[[cards]]\nid = 8\n'
        )
        draft = load_input(
            make_args(toml=str(toml), game=str(root_cli)), self.tmp
        )
        self.assertEqual(draft.game.game_dir, root_cli.resolve())
        self.assertEqual(draft.game.source, "--game")

    def test_missing_game_dir_rejected(self) -> None:
        errors = load_errors(make_args(ids=["8"], game=str(self.tmp / "nope")), self.tmp)
        assert_error_code(errors, "game_dir_invalid", "--game")

    def test_toml_game_dir_without_exe_rejected(self) -> None:
        make_game_root(self.tmp, "incomplete", exe=False)
        toml = self.write_toml(
            'format_version = 1\ngame_dir = "incomplete"\n\n[[cards]]\nid = 8\n'
        )
        errors = load_errors(make_args(toml=str(toml)), self.tmp)
        assert_error_code(errors, "game_dir_invalid", "game_dir")

    def test_game_dir_pointing_at_file_rejected(self) -> None:
        target = self.tmp / "not-a-dir"
        target.write_text("x", encoding="utf-8")
        errors = load_errors(make_args(ids=["8"], game=str(target)), self.tmp)
        assert_error_code(errors, "game_dir_invalid", "--game")


class MultiErrorAggregationTests(TomlCase):
    """inline 模式不做提前 raise：输入错误一次收集（上限 50）。"""

    def test_invalid_id_and_game_dir_collected_together(self) -> None:
        errors = load_errors(
            make_args(ids=["bad-id"], game=str(self.tmp / "missing")), self.tmp
        )
        self.assertIn("invalid_id", errors.codes)
        self.assertIn("game_dir_invalid", errors.codes)

    def test_invalid_id_and_jobs_range_collected_together(self) -> None:
        errors = load_errors(make_args(ids=["bad-id"], jobs=0), self.tmp)
        self.assertIn("invalid_id", errors.codes)
        self.assertIn("range", errors.codes)

    def test_errors_stay_under_cap(self) -> None:
        # 多错误聚合不突破 MAX_ERRORS 上限。
        from eidolon.shell.errors import MAX_ERRORS

        ids = ["bad-id-1", "bad-id-2"]
        errors = load_errors(make_args(ids=ids, jobs=0), self.tmp)
        self.assertLessEqual(len(errors.errors), MAX_ERRORS)


class CatalogExclusiveTests(TomlCase):
    """--catalog 仅 spec；与 --game / TOML game_dir / render 互斥。"""

    def test_catalog_with_render_rejected(self) -> None:
        errors = self._errors(
            make_args(ids=["8"], command="render", catalog=str(CATALOG_JSON))
        )
        self._assert_usage(errors)

    def test_catalog_with_cli_game_rejected(self) -> None:
        root = make_game_root(self.tmp)
        errors = self._errors(
            make_args(ids=["8"], catalog=str(CATALOG_JSON), game=str(root))
        )
        self._assert_usage(errors)

    def test_catalog_with_toml_game_dir_rejected(self) -> None:
        make_game_root(self.tmp)
        toml = self.write_toml(
            'format_version = 1\ngame_dir = "game"\n\n[[cards]]\nid = 8\n'
        )
        errors = self._errors(
            make_args(toml=str(toml), catalog=str(CATALOG_JSON))
        )
        self._assert_usage(errors)
        self.assertIn("game_dir", "\n".join(e.format() for e in errors.errors))

    def test_catalog_alone_with_toml_ok(self) -> None:
        toml = self.write_toml("format_version = 1\n\n[[cards]]\nid = 8\n")
        draft = load_input(
            make_args(toml=str(toml), catalog=str(CATALOG_JSON)), self.tmp
        )
        self.assertEqual(draft.catalog_path, CATALOG_JSON.resolve())

    def _errors(self, args: SimpleNamespace) -> SpecErrors:
        try:
            load_input(args, self.tmp)
        except SpecErrors as exc:
            return exc
        raise AssertionError("预期 load_input 失败，但成功了")

    def _assert_usage(self, errors: SpecErrors) -> None:
        self.assertIn("usage", errors.codes)


class TomlFlagsTests(TomlCase):
    def test_cli_only_flags_still_conflict_with_toml(self) -> None:
        toml = self.write_toml("format_version = 1\n\n[[cards]]\nid = 8\n")
        for extra in (["--outdir", "out"], ["--jobs", "2"]):
            with self.subTest(extra=extra):
                try:
                    load_input(make_args(toml=str(toml), **_kw(extra)), self.tmp)
                except SpecErrors as exc:
                    self.assertIn("option_not_allowed", exc.codes)
                else:
                    raise AssertionError("预期失败")

    def test_new_flags_allowed_with_toml(self) -> None:
        toml = self.write_toml("format_version = 1\n\n[[cards]]\nid = 8\n")
        draft = load_input(
            make_args(
                toml=str(toml),
                locale="zhcn",
                cache_root="cache",
                verbose=True,
                debug=True,
            ),
            self.tmp,
        )
        self.assertEqual(draft.source, "toml")


def _kw(extra: list[str]) -> dict[str, object]:
    mapping = {"--outdir": ("outdir", "out"), "--jobs": ("jobs", 2)}
    key, value = mapping[extra[0]]
    return {key: value}


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
