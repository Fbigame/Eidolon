"""子进程守卫：坏 TOML / --help / spec --catalog / render fake port 不 import core。

Phase 1b 语义性变化：``spec`` 默认路径（无 ``--catalog``）经真实 provider
**会**载入 core + UnityPy——这是设计要求（设计文档 §9.2 的 lazy import
只保证「不触发 factory 的路径不加载」），不再有
「默认 spec 不加载 core」的守卫；改为反向断言：默认 factory 构造即载入
core（只构造不 bind，不依赖游戏安装）。

Phase 3c：render 的默认 port factory 是组合层 CoreRenderPort（顶层只碰
标准库 + contracts + shell）——注入 fake port 后整条 render 编排
（bind → compile → preflight(no-op) → render → 结果 manifest）也不载入
core / UnityPy。

审计 P1-7：探针模块过滤器加 CLR 面（``clr`` / ``pythonnet``）——spec /
坏输入路径连渲染运行时都不许加载。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from tests.support import BATCH_TOML, CATALOG_JSON, ROOT

# main 的 stdout/stderr 全部重定向进缓冲，探针只回传退出码与模块快照。
# NullCatalogProvider 是 shell 类（shell 永不 import core，见架构守卫），
# 无条件导入不影响「无 core」断言。
_PROBE = """\
import io, json, sys
from contextlib import redirect_stderr, redirect_stdout
from eidolon.entry import main
from eidolon.shell.catalog import NullCatalogProvider

buf_out, buf_err = io.StringIO(), io.StringIO()
try:
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        code = main({args!r}, provider_factory={factory!r})
except SystemExit as exc:
    code = exc.code if exc.code is not None else 0
mods = sorted(
    m for m in sys.modules
    if m == 'eidolon.core'
    or m.startswith('eidolon.core.')
    or m.split('.')[0] == 'UnityPy'
    or m == 'clr'
    or m.startswith('clr.')
    or m.split('.')[0] == 'pythonnet'
)
print(int(code))
print(json.dumps(mods))
"""

# render + fake port 探针：port 是测试内联类（返回与卡数对齐的空 sha 报告），
# out_dir 指向探针自建的临时目录；整条 render 编排全程无 core import。
_RENDER_PROBE = """\
import io, json, os, sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from eidolon.contracts import RenderReport, RenderedCard
from eidolon.entry import main
from eidolon.shell.catalog import NullCatalogProvider

class FakePort:
    def preflight(self, spec):
        spec.options.out_dir.mkdir(parents=True, exist_ok=True)
    def render(self, spec):
        return RenderReport(rendered=tuple(
            RenderedCard(ref=c.ref, path=c.out_path, sha256='0'*64,
                         elapsed_ms=1) for c in spec.cards))

with tempfile.TemporaryDirectory() as tmp:
    outdir = os.path.join(tmp, 'out')
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = main(['render', '8', '--outdir', outdir],
                        provider_factory=NullCatalogProvider,
                        port_factory=FakePort)
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
    wrote = os.path.isfile(os.path.join(outdir, 'manifest.json'))
mods = sorted(
    m for m in sys.modules
    if m == 'eidolon.core'
    or m.startswith('eidolon.core.')
    or m.split('.')[0] == 'UnityPy'
    or m == 'clr'
    or m.startswith('clr.')
    or m.split('.')[0] == 'pythonnet'
)
print(int(code))
print(str(wrote))
print(json.dumps(mods))
"""

# 反向断言：默认 provider factory 构造即载入 core（lazy import 在函数体内，
# 但构造是 spec 默认路径的一部分）。只构造不 bind——不依赖游戏安装。
_FACTORY_PROBE = """\
import json, sys
from pathlib import Path
from eidolon.entry import _default_provider_factory
from eidolon.shell import cli

args = cli.parse_args(["spec", "8"])
factory = _default_provider_factory(args, Path.cwd())
provider = factory()
mods = sorted(
    m for m in sys.modules
    if m == 'eidolon.core'
    or m.startswith('eidolon.core.')
    or m.split('.')[0] == 'UnityPy'
    or m == 'clr'
    or m.startswith('clr.')
    or m.split('.')[0] == 'pythonnet'
)
print(provider.__class__.__module__ + '.' + provider.__class__.__name__)
print(json.dumps(mods))
"""


def _run_probe(source: str) -> tuple[list[str], str]:
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    lines = result.stdout.strip().splitlines()
    assert len(lines) >= 2, f"探针输出异常: {result.stdout!r} {result.stderr!r}"
    return lines, result.stderr


def _probe_main(args: list[str], factory: str = "None") -> tuple[int, list[str]]:
    lines, stderr = _run_probe(_PROBE.format(args=args, factory=factory))
    return int(lines[0]), json.loads(lines[-1])


def _probe_render() -> tuple[int, bool, list[str]]:
    lines, stderr = _run_probe(_RENDER_PROBE)
    return int(lines[0]), lines[1] == "True", json.loads(lines[-1])


class NoCoreImportTests(unittest.TestCase):
    def test_bad_toml_does_not_load_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.toml"
            bad.write_text("format_version = \n", encoding="utf-8")
            code, mods = _probe_main(["spec", "--toml", str(bad)])
        self.assertEqual(code, 2)
        self.assertEqual(mods, [])

    def test_help_does_not_load_core(self) -> None:
        code, mods = _probe_main(["--help"])
        self.assertEqual(code, 0)
        self.assertEqual(mods, [])

    def test_spec_with_catalog_does_not_load_core(self) -> None:
        code, mods = _probe_main(
            ["spec", "8", "--catalog", str(CATALOG_JSON)]
        )
        self.assertEqual(code, 0)
        self.assertEqual(mods, [])

    def test_render_fake_port_does_not_load_core(self) -> None:
        # Phase 3c：render 注入 fake port（组合层适配器顶层只 import
        # 标准库 + contracts + shell）→ 整条 render 编排（bind → compile →
        # preflight → render → 结果 manifest）无 eidolon.core / UnityPy。
        code, wrote, mods = _probe_render()
        self.assertEqual(code, 0)
        self.assertTrue(wrote)
        self.assertEqual(mods, [])


class DefaultFactoryLoadsCoreTests(unittest.TestCase):
    """Phase 1b 反向守卫：默认 provider factory 构造即载入 core + UnityPy。

    审计 P1-7 补面：spec 路径载 UnityPy 但**不得**载 CLR（bind 只建 facts
    索引，CLR 只在 render 期；探针过滤器已含 clr / pythonnet）。"""

    def test_default_factory_construction_imports_core(self) -> None:
        lines, stderr = _run_probe(_FACTORY_PROBE)
        self.assertEqual(
            lines[0], "eidolon.core.infra.provider.DbfCatalogProvider", stderr
        )
        mods = json.loads(lines[-1])
        self.assertIn("eidolon.core.infra.provider", mods)
        self.assertTrue(
            any(m == "UnityPy" or m.startswith("UnityPy.") for m in mods),
            f"UnityPy 未加载: {mods}",
        )
        self.assertFalse(
            any(
                m == "clr"
                or m.startswith("clr.")
                or m.split(".")[0] == "pythonnet"
                for m in mods
            ),
            f"spec 路径不得载入 CLR: {mods}",
        )


class Utf8OutputTests(unittest.TestCase):
    def test_manifest_streams_utf8(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "eidolon",
                "spec",
                "--toml",
                str(BATCH_TOML),
                "--catalog",
                str(CATALOG_JSON),
            ],
            cwd=ROOT,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        stdout = result.stdout.decode("utf-8")
        self.assertIn("测试名字", stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
