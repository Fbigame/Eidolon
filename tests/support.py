"""共享测试工具。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eidolon.shell.catalog import JsonCatalog
from eidolon.shell.errors import SpecErrors
from eidolon.shell.spec import RenderSpec, build_spec

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BATCH_TOML = FIXTURES / "batch.toml"
CATALOG_JSON = FIXTURES / "catalog.json"


def fixture_catalog() -> JsonCatalog:
    return JsonCatalog.from_path(CATALOG_JSON)


class TomlCase(unittest.TestCase):
    """每个测试一个临时目录，便于写 TOML / asset。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write_toml(self, text: str, name: str = "job.toml") -> Path:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def build(
        self,
        text: str,
        *,
        catalog=None,
        cwd: str | Path | None = None,
    ) -> RenderSpec:
        return build_spec(
            toml_path=self.write_toml(text),
            catalog=catalog,
            cwd=cwd or self.tmp,
        )

    def spec_errors(
        self,
        text: str,
        *,
        catalog=None,
        cwd: str | Path | None = None,
    ) -> SpecErrors:
        try:
            self.build(text, catalog=catalog, cwd=cwd)
        except SpecErrors as exc:
            return exc
        raise AssertionError("预期 build_spec 失败，但成功了")

    def assert_error(
        self,
        errors: SpecErrors,
        *,
        code: str | None = None,
        path: str | None = None,
        message_contains: str | None = None,
    ) -> None:
        for error in errors.errors:
            if code is not None and error.code != code:
                continue
            if path is not None and error.path != path:
                continue
            if message_contains is not None and message_contains not in error.message:
                continue
            return
        summary = "\n".join(error.format() for error in errors.errors)
        raise AssertionError(
            f"未找到匹配错误 code={code!r} path={path!r} "
            f"message_contains={message_contains!r}；实际：\n{summary}"
        )


def toml_with_card(body: str, card_id: str = '"CS2_182"') -> str:
    return f'format_version = 1\n\n[[cards]]\nid = {card_id}\n{body}'
