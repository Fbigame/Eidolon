"""shell/paths：default_font_dirs（OS 字体目录计算；env 只在本模块读）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eidolon.shell.paths import default_font_dirs


class DefaultFontDirsTests(unittest.TestCase):
    def test_windir_fonts_included_when_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fonts = Path(tmp) / "Fonts"
            fonts.mkdir()
            with mock.patch.dict(os.environ, {"WINDIR": tmp, "LOCALAPPDATA": ""}):
                dirs = default_font_dirs()
            self.assertEqual(dirs, (fonts,))

    def test_localappdata_user_fonts_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            user_fonts = Path(tmp) / "Microsoft" / "Windows" / "Fonts"
            user_fonts.mkdir(parents=True)
            with mock.patch.dict(os.environ, {"WINDIR": "", "LOCALAPPDATA": tmp}):
                dirs = default_font_dirs()
            self.assertEqual(dirs, (user_fonts,))

    def test_both_dirs_ordered_windir_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            windir_fonts = Path(tmp) / "w" / "Fonts"
            user_fonts = Path(tmp) / "u" / "Microsoft" / "Windows" / "Fonts"
            windir_fonts.mkdir(parents=True)
            user_fonts.mkdir(parents=True)
            with mock.patch.dict(
                os.environ, {"WINDIR": str(Path(tmp) / "w"), "LOCALAPPDATA": str(Path(tmp) / "u")}
            ):
                dirs = default_font_dirs()
            self.assertEqual(dirs, (windir_fonts, user_fonts))

    def test_nonexistent_dirs_skipped(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "WINDIR": "Q:/definitely-not-a-real-windows-dir",
                "LOCALAPPDATA": "Q:/definitely-not-a-real-user-dir",
            },
        ):
            dirs = default_font_dirs()
        # 都不存在 → 兜底（与 glyph_supply 的政策兜底同值）。
        self.assertEqual(dirs, (Path("C:/Windows/Fonts"),))

    def test_missing_env_falls_back_to_policy_constant(self) -> None:
        env = {k: v for k, v in os.environ.items()
               if k not in ("WINDIR", "LOCALAPPDATA")}
        with mock.patch.dict(os.environ, env, clear=True):
            dirs = default_font_dirs()
        self.assertEqual(dirs, (Path("C:/Windows/Fonts"),))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
