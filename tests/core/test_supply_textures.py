"""supply.textures — mip 链直提格式域守卫（B2 typed 收口；零游戏 fake）。

覆盖（判据：资产缺失/游戏数据不在预期形态类不再裸 ``ValueError``）：

* ``_extract_chain`` 格式域外（fmt=25=BC7，DMF_254t5 实证）→
  ``GameAssetFormatUnsupported``（kind=ENVIRONMENT，code=``asset_format_unsupported``，
  path=bundle::纹理名，message 带 fmt/mip_count/尺寸，cause 带根因）——
  且守卫在 ``get_image_data()`` 之前（域外不付整图数据读取消耗）；
* 支持域内（fmt=12）照旧提取（守卫不误伤；字节账断言照跑）；
* ``_decode_level`` 臂集 == ``_SUPPORTED_MIP_FORMATS``（域内不炸、域外
  ValueError 背板——加臂须同步加集的漂移钉）；
* ``art._portrait_chain`` 卡上下文包装：typed 失败回填 card_id 进 message，
  类型/code/path/cause 原样保留；非 typed 异常原样穿出。

fake resolver 形状：``_find_texture`` 只消费 ``env.objects[*].type.name`` /
``.path_id`` / ``read_typetree()``；``obj.read()`` 用断言桩——被调即红。

import 纪律（test_supply_seed 同款）：textures/art 经 resolve_asset_ref 顶层
链拖 UnityPy，本模块 collection 期不得装载——``test_render_import_seams`` 的
轻 import 断言依赖 discover 全量收集后 ``sys.modules`` 干净；两个模块只在
用例执行期（setUp）装载。
"""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from eidolon.core.infra.errors import (
    EnvironmentUnavailable,
    GameAssetFormatUnsupported,
    GameAssetMissing,
)

_BUNDLE = "cardtexture_base_global-384202c8-texture-0.unity3d"
_NAME = "HS21-109"
_PATH_ID = 1234


def _tree(fmt: int, w: int = 512, h: int = 512, n: int = 10) -> dict:
    return {"m_Name": _NAME, "m_TextureFormat": fmt,
            "m_Width": w, "m_Height": h, "m_MipCount": n,
            "m_TextureSettings": {"m_FilterMode": 1, "m_MipBias": 0.0}}


class _NeverReadObj:
    """断言桩 obj：``read()`` 被调即红（守卫必须在取整图数据之前）。"""

    def __init__(self, tree: dict) -> None:
        self._tree = tree
        self.path_id = _PATH_ID
        self.read_called = False

    @property
    def type(self):
        class _T:
            name = "Texture2D"
        return _T()

    def read_typetree(self) -> dict:
        return self._tree

    def read(self):
        self.read_called = True
        raise AssertionError("域外 fmt 不得走到 get_image_data()")


def _install_resolver(textures, testcase: unittest.TestCase,
                      obj: _NeverReadObj) -> None:
    """monkeypatch textures.get_resolver → 返回含单 obj 的 fake env。"""
    class _Env:
        objects = [obj]

    class _Resolver:
        def open_bundle(self, bundle: str):
            return _Env()

    patcher = mock.patch.object(textures, "get_resolver", lambda: _Resolver())
    patcher.start()
    testcase.addCleanup(patcher.stop)


class ExtractChainFormatGuardTests(unittest.TestCase):
    """_extract_chain 格式域守卫（B2：裸 ValueError → typed）。"""

    def setUp(self) -> None:
        import eidolon.core.supply.textures as m

        self.textures = m

    def test_unsupported_fmt_raises_typed(self) -> None:
        obj = _NeverReadObj(_tree(fmt=25))
        _install_resolver(self.textures, self, obj)
        with self.assertRaises(GameAssetFormatUnsupported) as caught:
            self.textures._extract_chain(_NAME, _BUNDLE, _PATH_ID)
        problem = caught.exception.problem
        self.assertEqual(problem.kind.value, "environment")
        self.assertEqual(problem.code, "asset_format_unsupported")
        self.assertEqual(problem.path, f"{_BUNDLE}::{_NAME}")
        self.assertIn("fmt=25", problem.message)
        self.assertIn("mip_count=10", problem.message)
        self.assertIn("512x512", problem.message)
        self.assertIn("TextureFormat 25", problem.cause)
        self.assertFalse(obj.read_called, "守卫必须在 get_image_data() 之前")
        # 退出码面：EnvironmentUnavailable 家族 → ENV 3（hint 走 CODES 默认）。
        self.assertIsInstance(caught.exception, EnvironmentUnavailable)

    def test_unsupported_fmt_without_bundle_keeps_bare_name_path(self) -> None:
        obj = _NeverReadObj(_tree(fmt=50))
        _install_resolver(self.textures, self, obj)
        with self.assertRaises(GameAssetFormatUnsupported) as caught:
            self.textures._extract_chain(_NAME, "", _PATH_ID)
        self.assertEqual(caught.exception.problem.path, _NAME)

    def test_supported_fmt_passes_guard_and_extracts(self) -> None:
        obj = _NeverReadObj(_tree(fmt=12, w=2, h=2, n=1))
        _install_resolver(self.textures, self, obj)

        class _Reader:
            def get_image_data(self) -> bytes:
                return bytes(16)   # level_bytes(12, 2, 2) = 1*1*16

        obj.read = lambda: _Reader()   # 支持域内：放行取数据
        lods = []

        def _fake_decode(data, w, h, fmt):
            arr = np.zeros((h, w, 4), np.uint8)
            lods.append((w, h, fmt))
            return arr

        with mock.patch.object(self.textures, "_decode_level", _fake_decode):
            ent = self.textures._extract_chain(_NAME, _BUNDLE, _PATH_ID)
        self.assertEqual(ent["filter"], 1)
        self.assertEqual(ent["bias"], 0.0)
        self.assertEqual(len(ent["lods"]), 1)
        self.assertEqual(lods, [(2, 2, 12)])


class DecodeLevelDomainTests(unittest.TestCase):
    """``_decode_level`` 臂集 == ``_SUPPORTED_MIP_FORMATS``（漂移钉）。"""

    def setUp(self) -> None:
        import eidolon.core.supply.textures as m

        self.textures = m

    def test_every_supported_fmt_decodes(self) -> None:
        for fmt in sorted(self.textures._SUPPORTED_MIP_FORMATS):
            w = h = 4
            lb = self.textures._level_bytes(fmt, w, h)
            data = bytes(lb)
            arr = self.textures._decode_level(data, w, h, fmt)
            self.assertEqual(arr.shape, (4, 4, 4), f"fmt={fmt} 须产 RGBA uint8")

    def test_out_of_domain_fmt_raises_valueerror_backstop(self) -> None:
        for fmt in (0, 25, 50, 71):
            with self.assertRaises(ValueError, msg=f"fmt={fmt}"):
                self.textures._decode_level(bytes(64), 4, 4, fmt)


class PortraitChainCardContextTests(unittest.TestCase):
    """art._portrait_chain：typed 失败回填 card_id（B2 语义保留）。"""

    def setUp(self) -> None:
        import eidolon.core.supply.art as m

        self.art = m

    def test_format_unsupported_message_gains_card_id(self) -> None:
        boom = GameAssetFormatUnsupported(
            path=f"{_BUNDLE}::{_NAME}",
            message=f"asset_format_unsupported: 纹理 {_NAME!r} 的 mip 链格式域外"
                    "（fmt=25）",
            cause="TextureFormat 25 不在离线链解码域",
        )
        with mock.patch.object(self.art, "chain_for_name",
                               mock.Mock(side_effect=boom)):
            with self.assertRaises(GameAssetFormatUnsupported) as caught:
                self.art._portrait_chain("DMF_254t5", _NAME, (_BUNDLE, _PATH_ID))
        problem = caught.exception.problem
        self.assertEqual(problem.code, "asset_format_unsupported")
        self.assertEqual(problem.path, f"{_BUNDLE}::{_NAME}")
        self.assertIn("card_id=DMF_254t5", problem.message)
        self.assertEqual(problem.cause, "TextureFormat 25 不在离线链解码域")

    def test_asset_missing_enriched_same_shape(self) -> None:
        boom = GameAssetMissing(path=f"{_BUNDLE}::{_NAME}",
                                message="asset_missing_in_game: bundle 内无纹理")
        with mock.patch.object(self.art, "chain_for_name",
                               mock.Mock(side_effect=boom)):
            with self.assertRaises(GameAssetMissing) as caught:
                self.art._portrait_chain("CARD_X", _NAME, (_BUNDLE, _PATH_ID))
        problem = caught.exception.problem
        self.assertEqual(problem.code, "asset_missing_in_game")
        self.assertIn("card_id=CARD_X", problem.message)

    def test_non_typed_exception_passes_through_untouched(self) -> None:
        with mock.patch.object(self.art, "chain_for_name",
                               mock.Mock(side_effect=KeyError("boom"))):
            with self.assertRaises(KeyError):
                self.art._portrait_chain("CARD_X", _NAME, (_BUNDLE, _PATH_ID))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
