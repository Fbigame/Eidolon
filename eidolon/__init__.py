"""Eidolon 外壳：命令行 / TOML → 统一 RenderSpec → manifest。

输入归一化与校验在 ``shell/``；渲染端口协议在 :mod:`eidolon.shell.ports`，
真实适配器在 :mod:`eidolon.adapters`（组合层，lazy import core）。
本包 ``__init__`` 只 re-export 公开 API，不 import core；版本单源在
:mod:`eidolon.version`。
"""

from __future__ import annotations

import logging

from eidolon.version import __version__

from .contracts import (
    CardCatalog,
    CardFacts,
    CardRef,
    CatalogBinding,
    CatalogIdentity,
    CatalogProvider,
    EnvironmentUnavailable,
    GameContext,
    GameRequest,
    Problem,
    ProblemKind,
)
from .shell.catalog import JsonCatalog, NullCatalog
from .shell.errors import (
    EXIT_ENVIRONMENT,
    EXIT_INVALID_INPUT,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_RENDER_FAILED,
    SpecError,
    SpecErrors,
)
from .shell.manifest import build_manifest, manifest_json
from .shell.spec import (
    CardSpec,
    RenderOptions,
    RenderSpec,
    build_spec,
    parse_id,
)

# 库代码不配置 handler；entry 是唯一配置点。这里只保证「import eidolon
# 不污染 root logger，且未配置时日志静默」。
logging.getLogger("eidolon").addHandler(logging.NullHandler())

__all__ = [
    "CardCatalog",
    "CardFacts",
    "CardRef",
    "CardSpec",
    "CatalogBinding",
    "CatalogIdentity",
    "CatalogProvider",
    "EnvironmentUnavailable",
    "EXIT_ENVIRONMENT",
    "EXIT_INVALID_INPUT",
    "EXIT_INTERRUPTED",
    "EXIT_OK",
    "EXIT_RENDER_FAILED",
    "GameContext",
    "GameRequest",
    "JsonCatalog",
    "NullCatalog",
    "Problem",
    "ProblemKind",
    "RenderOptions",
    "RenderSpec",
    "SpecError",
    "SpecErrors",
    "__version__",
    "build_manifest",
    "build_spec",
    "manifest_json",
    "parse_id",
]
