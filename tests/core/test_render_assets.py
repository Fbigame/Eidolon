"""core/render/assets 单测（§10.0/§10.1 尺寸/格式规约；纯 PIL，无 supply session）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eidolon.contracts import InputRejected
from eidolon.core.render.assets import (
    ASSET_DIMENSIONS,
    read_rgba,
    validate_dimensions,
)


def _png_bytes(size: tuple[int, int]) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


class AssetDimensionsTableTests(unittest.TestCase):
    def test_table_matches_design_10_1(self) -> None:
        self.assertEqual(ASSET_DIMENSIONS, {
            "portrait": ((512, 512),),
            "frame": ((1024, 1024),),
            "watermark": ((128, 128), (256, 256)),
        })


class ValidateDimensionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def write_png(self, name: str, size: tuple[int, int]) -> Path:
        path = self.dir / name
        path.write_bytes(_png_bytes(size))
        return path

    def test_legal_sizes_pass(self) -> None:
        for kind, size in (("portrait", (512, 512)), ("frame", (1024, 1024)),
                           ("watermark", (128, 128)), ("watermark", (256, 256))):
            with self.subTest(kind=kind, size=size):
                path = self.write_png(f"{kind}_{size[0]}.png", size)
                self.assertEqual(validate_dimensions(path, kind), size)

    def test_off_table_sizes_rejected(self) -> None:
        for kind, size in (("portrait", (511, 511)), ("portrait", (512, 707)),
                           ("frame", (512, 707)),     # 整帧 PNG ≠ 类色图集
                           ("watermark", (300, 300)),
                           ("watermark", (512, 512))):
            with self.subTest(kind=kind, size=size):
                path = self.write_png(f"bad_{kind}_{size[0]}x{size[1]}.png", size)
                with self.assertRaises(InputRejected) as ctx:
                    validate_dimensions(path, kind)
                self.assertEqual(ctx.exception.problem.code, "asset_dimensions")
                self.assertEqual(ctx.exception.problem.kind.value, "input")
                self.assertEqual(ctx.exception.problem.path, str(path))

    def test_corrupt_bytes_rejected_as_asset(self) -> None:
        path = self.dir / "corrupt.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\nnot-really-a-png")
        with self.assertRaises(InputRejected) as ctx:
            validate_dimensions(path, "portrait")
        self.assertEqual(ctx.exception.problem.code, "asset")

    def test_jpeg_bytes_in_png_name_rejected_as_asset(self) -> None:
        # 与 read_rgba 同门：尺寸合法但内容不是 PNG → asset（不得只看尺寸）。
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (512, 512), (10, 20, 30)).save(buf, format="JPEG")
        path = self.dir / "jpeg_as_png.png"
        path.write_bytes(buf.getvalue())
        with self.assertRaises(InputRejected) as ctx:
            validate_dimensions(path, "portrait")
        self.assertEqual(ctx.exception.problem.code, "asset")
        self.assertIn("非 PNG", ctx.exception.problem.message)

    def test_unknown_kind_rejected(self) -> None:
        path = self.write_png("ok.png", (512, 512))
        with self.assertRaises(InputRejected) as ctx:
            validate_dimensions(path, "banner")
        self.assertEqual(ctx.exception.problem.code, "asset")


class ReadRgbaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_returns_rgba(self) -> None:
        path = self.dir / "p.png"
        path.write_bytes(_png_bytes((512, 512)))
        image = read_rgba(path)
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (512, 512))

    def test_jpeg_bytes_in_png_name_rejected(self) -> None:
        # P1-6：格式门按内容嗅探（im.format），与扩展名无关——JPEG 字节存
        # .png 名 → InputRejected(INPUT, "asset")。
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (512, 512), (10, 20, 30)).save(buf, format="JPEG")
        path = self.dir / "jpeg_as_png.png"
        path.write_bytes(buf.getvalue())
        with self.assertRaises(InputRejected) as ctx:
            read_rgba(path)
        self.assertEqual(ctx.exception.problem.code, "asset")
        self.assertEqual(ctx.exception.problem.kind.value, "input")
        self.assertIn("非 PNG", ctx.exception.problem.message)
        self.assertIn("JPEG", ctx.exception.problem.message)

    def test_corrupt_bytes_rejected_as_asset(self) -> None:
        path = self.dir / "corrupt.png"
        path.write_bytes(b"")
        with self.assertRaises(InputRejected) as ctx:
            read_rgba(path)
        self.assertEqual(ctx.exception.problem.code, "asset")

    def test_missing_file_rejected_as_asset(self) -> None:
        with self.assertRaises(InputRejected) as ctx:
            read_rgba(self.dir / "nope.png")
        self.assertEqual(ctx.exception.problem.code, "asset")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
