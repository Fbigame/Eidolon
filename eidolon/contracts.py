"""共享契约：纯数据 / 协议 / 携带 Problem 的异常。

contracts 只依赖标准库；不放 I/O、不放业务函数。``shell/`` 与 ``core/``
互不 import，只共同依赖本模块（见 docs/architecture.md §2.1）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal, Mapping, Protocol, runtime_checkable


class ProblemKind(StrEnum):
    """错误大类；``Problem.kind`` 是退出码的唯一来源。"""

    INPUT = "input"
    ENVIRONMENT = "environment"
    RENDER = "render"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class Problem:
    """统一错误对象：kind / code / path / message / hint / cause。

    ``hint`` 覆盖 ``shell.errors.CODES`` 的默认；空则回落注册表。
    """

    kind: ProblemKind
    code: str
    path: str  # 输入定位 / 文件路径 / argv / env:* 哨兵 / eidolon
    message: str
    hint: str = ""
    cause: str = ""


class EnvironmentUnavailable(Exception):
    """环境不可用（游戏没装、dbf 读不到、依赖缺失等）。

    携带一个 ``kind`` 必须为 :attr:`ProblemKind.ENVIRONMENT` 的
    :class:`Problem`；entry 把它映射为退出码 3。
    """

    def __init__(self, problem: Problem) -> None:
        if problem.kind is not ProblemKind.ENVIRONMENT:
            raise ValueError(
                "EnvironmentUnavailable.problem.kind 必须是 ENVIRONMENT，"
                f"实际为 {problem.kind!r}"
            )
        self.problem = problem
        super().__init__(problem.message)


class InputRejected(Exception):
    """core 的输入类错误（覆盖映射 / 预检用）。

    携带一个 ``kind`` 必须为 :attr:`ProblemKind.INPUT` 的 :class:`Problem`；
    构造形状对齐 :class:`EnvironmentUnavailable`。``shell.cli.run`` 捕获后
    转输入错误（退出码 2）；render 期（preflight 之外）被逐卡分类归
    ``render_failed``（RENDER 1，plan manifest 已打印后不得再声称 INPUT）。
    """

    def __init__(self, problem: Problem) -> None:
        if problem.kind is not ProblemKind.INPUT:
            raise ValueError(
                "InputRejected.problem.kind 必须是 INPUT，"
                f"实际为 {problem.kind!r}"
            )
        self.problem = problem
        super().__init__(problem.message)


@dataclass(frozen=True, slots=True)
class CardRef:
    """归一化后的卡标识。``kind`` 为 ``"dbf"``（value=int）或 ``"card"``（value=str）。"""

    kind: Literal["dbf", "card"]
    value: int | str

    def __post_init__(self) -> None:
        if self.kind not in ("dbf", "card"):
            raise ValueError(f"unknown CardRef kind: {self.kind!r}")
        if self.kind == "dbf" and not isinstance(self.value, int):
            raise ValueError(f"dbf CardRef.value 必须是 int: {self.value!r}")
        if self.kind == "card" and not isinstance(self.value, str):
            raise ValueError(f"card CardRef.value 必须是 str: {self.value!r}")

    @property
    def is_dbf(self) -> bool:
        return self.kind == "dbf"


@dataclass(frozen=True, slots=True)
class CardFacts:
    """catalog 对一张已知卡的最小事实集（v1 只投影 ``cardtype``）。"""

    cardtype: str


@runtime_checkable
class CardCatalog(Protocol):
    """shell 与 core 共同依赖的只读 catalog 协议。

    ``complete`` 表示「索引覆盖是否完整」：complete 的 catalog 查不到卡
    即 ``unknown_card``；不 complete 的 catalog 查不到只 ``deferred``。
    """

    complete: bool
    known_classes: tuple[str, ...]
    known_cardtypes: tuple[str, ...]
    known_rarities: tuple[str, ...]
    known_spell_schools: tuple[str, ...]

    def lookup(self, ref: CardRef) -> CardFacts | None:
        """按归一化 ref 查卡；未知卡返回 ``None``。"""
        ...


@dataclass(frozen=True, slots=True)
class GameRequest:
    """provider.bind 的输入：显式 game_dir（load_input 已校验安装根）或空（待探测）。"""

    game_dir: Path | None
    source: Literal["--game", "toml game_dir", ""] = ""


@dataclass(frozen=True, slots=True)
class GameContext:
    """游戏安装的纯值描述；由 provider 构造，core 消费。

    派生路径是纯属性：无 I/O、不 ``assert`` 存在。游戏安装布局字面量
    只出现在本类，不散落进 shell / core。
    """

    root: Path
    cache_root: Path
    locale: str = "zhcn"
    version: str | None = None
    version_source: str = ""
    root_source: str = ""
    route_mode: str = "auto"  # 渲染开关；v1 固定 auto
    version_strict: bool = False  # 渲染开关；v1 固定 False

    def identity(self) -> tuple:
        """渲染身份六元组（core/infra/context.install 同异判定用）。

        root / cache_root / locale / version / route_mode / version_strict 六项
        是影响渲染语义与进程级缓存键的事实；来路账 ``root_source`` /
        ``version_source`` **不参与**——同根不同来路 = 同一渲染身份，判定走
        本元组而非 ``__eq__``。
        """
        return (
            self.root,
            self.cache_root,
            self.locale,
            self.version,
            self.route_mode,
            self.version_strict,
        )

    @property
    def game_exe(self) -> Path:
        """安装根完整性字面量（``load_input`` 校验与 core preflight 共用）。"""
        return self.root / "Hearthstone.exe"

    @property
    def data_win(self) -> Path:
        return self.root / "Data" / "Win"

    @property
    def dbf_path(self) -> Path:
        return self.data_win / "dbf.unity3d"

    @property
    def strings_dir(self) -> Path:
        return self.root / "Strings" / self.locale

    @property
    def managed(self) -> Path:
        return self.root / "Hearthstone_Data" / "Managed"

    @property
    def assembly_csharp(self) -> Path:
        return self.managed / "Assembly-CSharp.dll"

    @property
    def resources(self) -> Path:
        return self.root / "Hearthstone_Data" / "resources.assets"

    @property
    def globalgamemanagers(self) -> Path:
        return self.root / "Hearthstone_Data" / "globalgamemanagers"

    @property
    def route_cache(self) -> Path:
        """``cache_root`` 的只读兼容别名（吸收期）。"""
        return self.cache_root


@dataclass(frozen=True, slots=True)
class CatalogIdentity:
    """catalog 的身份（manifest 复现字段）。

    ``complete`` 只从 ``binding.catalog.complete`` 复制；禁止独立赋值。
    ``kind="null"`` 表示 dev/null catalog：``path=""``，manifest 不加
    ``catalog_incomplete``。
    """

    kind: Literal["dbf", "json", "null"]
    path: str = ""
    size: int = 0
    mtime_ns: int = 0
    complete: bool = False


@dataclass(frozen=True, slots=True)
class CatalogBinding:
    """bind 的结果：catalog + 游戏（可为空）+ 身份 + bind 期已知警告。"""

    catalog: CardCatalog
    game: GameContext | None
    identity: CatalogIdentity
    warnings: tuple[str, ...] = ()


class CatalogProvider(Protocol):
    """catalog 绑定协议；真实实现是 core 的 ``DbfCatalogProvider``。"""

    def bind(self, request: GameRequest) -> CatalogBinding:
        ...


# ---------------------------------------------------------------------------
# 渲染报告（architecture §7 的最小契约；不放渲染逻辑）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RenderCard:
    """core 渲染端口的单卡输入（§5.2；adapter 从 ``CardSpec`` 构造）。

    ``overrides`` 键 = ``CardSpec`` 字段名：
    ``name`` / ``desc`` / ``classes`` / ``races`` / ``cost`` / ``attack`` /
    ``health`` / ``armor`` / ``cardtype`` / ``rarity`` / ``premium`` /
    ``spell_school`` / ``cost_banner`` / ``elite`` / ``runes`` / ``tech_level``。
    ``assets`` 键只允许 ``portrait`` / ``frame`` / ``watermark``（§10.0 三座位）。
    两者由 adapter 构造为**普通 dict**（进程池 payload 只允许基础类型）。
    """

    ref: CardRef
    out_path: Path
    overrides: Mapping[str, object] = field(default_factory=dict)
    assets: Mapping[str, Path] = field(default_factory=dict)
    hero_style: bool = False   # 请求 ∩ 生效适用（adapter 交集下发；审计裁决 A）；raw 请求值只进结果 manifest
    bg_style: bool = False     # 同上；raw 请求值按 style_requested[1] 记结果 manifest
    session_t: float | None = None   # None → core 用 PRODUCT_SESSION_T (0.0)


@dataclass(frozen=True, slots=True)
class RenderRequest:
    """core 渲染端口请求（§5.2）。

    ``game`` 设计稿声明位在 ``antialias`` 之后，但「无默认字段排在有默认字段
    之后」不是合法 dataclass 形状；以 ``kw_only`` 保持声明次序并强制关键字传参。
    ``font_dirs`` 是 OS 字体目录（由 adapter 从 shell/paths 注入），不进
    ``GameContext``（避免污染游戏身份）。
    """

    cards: tuple[RenderCard, ...]
    out_dir: Path
    jobs: int = 1
    antialias: bool = False
    game: GameContext = field(kw_only=True)
    font_dirs: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderedCard:
    """一张成功渲染的输出。"""

    ref: CardRef
    path: Path
    sha256: str
    elapsed_ms: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderFailure:
    """一张失败的渲染；``problem.kind`` ∈ {ENVIRONMENT, RENDER}，混合批次 3 优先于 1。"""

    ref: CardRef
    path: Path
    problem: Problem


@dataclass(frozen=True, slots=True)
class RenderReport:
    """端口 ``render(spec)`` 的结果容器。"""

    rendered: tuple[RenderedCard, ...] = ()
    failures: tuple[RenderFailure, ...] = ()
    warnings: tuple[str, ...] = ()
