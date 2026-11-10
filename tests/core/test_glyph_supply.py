"""glyph_supply — install_font_dirs 注入/重置语义（默认 discover 收集；无 UnityPy/CLR）。

设计 §8：``WINDIR`` / ``LOCALAPPDATA`` env 消费删除；新增 ``install_font_dirs``——
模块级 ``_FONT_DIRS`` / ``_FACE_DIR``，并**重置** ``_FAMILY_INDEX`` / ``_NAME_CACHE`` /
``_FACE_DIR``（同进程换目录/测试注入后索引不陈旧）；``font_dirs()`` 只读注入值，
空则 ``(Path("C:/Windows/Fonts"),)`` 兜底（产品政策写死，非 env）；``family_index()``
首次调用才枚举（进程级 memo）。

本测试用 tmp 空目录，不枚举真实字体（family_index 对空目录=空表）。glyph_supply
import 链含 ft_unhinted（freetype）与 _provenance——非 UnityPy 非 CLR，允许。

B4 增补（字体失败面判据「响亮或明确回退」）：空目录下缺字回退=响亮事件
（level=none）；坏字体文件/不可枚举目录=跳过 + WARNING（回退降级有账）。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import eidolon.core.render.text.glyph_supply as gs

MODULE_FILE = Path(gs.__file__)
_DEFAULT_FONT_DIRS = (Path("C:/Windows/Fonts"),)


class InstallFontDirsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.dir_a = self.tmp / "fonts-a"
        self.dir_b = self.tmp / "fonts-b"
        self.dir_a.mkdir()
        self.dir_b.mkdir()
        self.addCleanup(gs.install_font_dirs, (), cache_dir=self.tmp / "reset")

    def test_install_then_font_dirs_is_injected_value(self) -> None:
        gs.install_font_dirs((self.dir_a,))
        self.assertEqual(gs.font_dirs(), (self.dir_a,))

    def test_reinstall_replaces_dirs_and_rebuilds_family_index(self) -> None:
        gs.install_font_dirs((self.dir_a,))
        first_index = gs.family_index()
        self.assertEqual(first_index, {})   # 空目录=空索引（不枚举真实字体、不炸）
        gs.install_font_dirs((self.dir_b,))
        self.assertEqual(gs.font_dirs(), (self.dir_b,))
        second_index = gs.family_index()
        self.assertIsNot(
            second_index, first_index,
            "install_font_dirs 后族索引必须重建（_FAMILY_INDEX 重置），不得复用陈旧 memo")
        self.assertEqual(second_index, {})

    def test_reinstall_resets_face_dir(self) -> None:
        explicit = self.tmp / "face-cache"
        gs.install_font_dirs((self.dir_a,), cache_dir=explicit)
        self.assertEqual(gs._FACE_DIR, explicit)
        gs.install_font_dirs((self.dir_b,))
        self.assertIsNone(
            gs._FACE_DIR,
            "cache_dir 缺省重装时 _FACE_DIR 须复位（下次落盘经 ctx.cache_root 解析）")

    def test_default_fallback_when_never_installed(self) -> None:
        gs.install_font_dirs(())
        self.assertEqual(gs.font_dirs(), _DEFAULT_FONT_DIRS)

    def test_family_index_uses_injected_dir_only(self) -> None:
        # 目录 B 放一个非字体文件：索引仍为空（不炸、不收非字体文件）。
        (self.dir_b / "not_a_font.txt").write_text("junk", encoding="utf-8")
        gs.install_font_dirs((self.dir_b,))
        self.assertEqual(gs.family_index(), {})


class NoEnvPolicyTests(unittest.TestCase):
    """产品政策：字体目录不来自 OS 目录变量（文本断言 + 行为断言）。"""

    def test_source_has_no_env_or_temp_references(self) -> None:
        text = MODULE_FILE.read_text(encoding="utf-8")
        for banned in ("WINDIR", "LOCALAPPDATA", "os.environ", "os.getenv",
                       "tempfile", "angelia-fontcache"):
            self.assertNotIn(banned, text, f"glyph_supply 残留 env/temp 面：{banned}")

    def test_font_dirs_ignores_process_environment(self) -> None:
        gs.install_font_dirs(())
        # 即便进程 env 里有对应变量（CI/开发机常见），font_dirs 也只认注入值。
        import os

        env = os.environ.copy()
        env.setdefault("WINDIR", "Z:/somewhere")
        env.setdefault("LOCALAPPDATA", "Z:/elsewhere")
        self.assertEqual(gs.font_dirs(), _DEFAULT_FONT_DIRS)


class FontFailureSurfaceTests(unittest.TestCase):
    """B4 字体失败面：空目录/坏字体文件/不可枚举目录 = 响亮或明确回退。

    判据基线（任务单 §10 B4）：
    - 空字体目录 + 缺字 → ``resolve_fallback`` 返回 ``(None, level=none)``
      事件（advance 0、resolved_ch None）——调用方据此出零宽位并记响亮
      缺字事件（uber_text._fallback_char_info → record_missing），不静默 tofu；
    - 后缀在字体域但解析失败（坏字体/权限）→ 跳过 + WARNING 一声（进程
      一次，_NAME_CACHE memo）；
    - 目录不可枚举（权限拒绝）→ 跳过整目录 + WARNING（不炸整卡，缺字
      仍有响亮事件）。
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.empty = self.tmp / "fonts-empty"
        self.empty.mkdir()
        # 注入/重置互为清理：restore 模块级字体面（目录清空 + 索引重置）。
        self.addCleanup(gs.install_font_dirs, (), cache_dir=self.tmp / "reset")

    def test_resolve_fallback_none_event_with_empty_dirs(self) -> None:
        gs.install_font_dirs((self.empty,))
        # font_object=None：跳过资产级（①），直接落 OS 族名表（②）——零
        # UnityPy 面；ppem 取冷僻值避开进程级 memo 撞键。
        face, ev = gs.resolve_fallback("㐀", 77, font_object=None)
        self.assertIsNone(face, "空字体目录下两级回退无候选，face 必为 None")
        self.assertEqual(ev["level"], "none")
        self.assertEqual(ev["advance_px"], 0)
        self.assertIsNone(ev["resolved_ch"])
        self.assertIn("none@", ev["source"])

    def test_corrupt_font_file_skipped_with_warning(self) -> None:
        (self.empty / "broken.ttf").write_bytes(b"not a font at all")
        gs.install_font_dirs((self.empty,))
        with self.assertLogs(gs.logger, level="WARNING") as captured:
            self.assertEqual(gs.family_index(), {}, "坏字体不入族索引")
        self.assertTrue(
            any("broken.ttf" in line for line in captured.output),
            f"坏字体跳过须有 WARNING：{captured.output}")
        # memo 生效：只重置族索引（不碰 _NAME_CACHE）再枚举，同文件不重复告警。
        gs._FAMILY_INDEX = None
        with self.assertNoLogs(gs.logger, level="WARNING"):
            self.assertEqual(gs.family_index(), {})

    def test_non_font_suffix_junk_no_warning(self) -> None:
        (self.empty / "notes.txt").write_text("junk", encoding="utf-8")
        gs.install_font_dirs((self.empty,))
        with self.assertNoLogs(gs.logger, level="WARNING"):
            self.assertEqual(gs.family_index(), {})

    def test_unreadable_font_dir_skipped_with_warning(self) -> None:
        other = self.tmp / "fonts-other"
        other.mkdir()
        gs.install_font_dirs((self.empty, other))
        original = Path.iterdir

        def guarded(self_path):
            if self_path == self.empty:
                raise PermissionError(13, "测试桩：拒绝枚举", str(self_path))
            return original(self_path)

        with mock.patch.object(Path, "iterdir", autospec=True, side_effect=guarded):
            with self.assertLogs(gs.logger, level="WARNING") as captured:
                idx = gs.family_index()
        self.assertEqual(idx, {}, "不可枚举目录的候选缺席；其余目录空=空索引")
        self.assertTrue(
            any(str(self.empty) in line for line in captured.output),
            f"不可枚举目录须有 WARNING：{captured.output}")


if __name__ == "__main__":
    unittest.main()
