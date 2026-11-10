"""组合层适配器：``CoreRenderPort`` —— :class:`~eidolon.shell.ports.RenderPort`
的真实实现（设计 §9.1 / §7.7）。

分层纪律（守卫钉住）：本模块顶层**只** import 标准库 +
``eidolon.contracts`` + ``eidolon.shell.*``；任何 ``eidolon.core.*`` 的
import 都在函数体内——``core.infra.card`` / ``game_tag`` 在 import 期装
CLR（§7.1.1），未 ``context.install`` 就 import 会 ``RuntimeError``，
因此 preflight / render 的第一步都是 ``context.install(spec.game)``，
之后才 lazy import core。

错误分类（§7.7）：INPUT 类收集进 :class:`~eidolon.shell.errors.SpecErrors`
（shell 捕获 → 2）；ENVIRONMENT 类抛
:class:`~eidolon.contracts.EnvironmentUnavailable`（entry → 3）；
``spec.game`` 为 None 是组合层编程错误，直接 ``RuntimeError``（entry
未预期 → internal 1）。
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

from eidolon.contracts import (
    EnvironmentUnavailable,
    InputRejected,
    Problem,
    ProblemKind,
    RenderCard,
    RenderRequest,
    RenderReport,
)
from eidolon.shell.errors import SpecErrors
from eidolon.shell.spec import ASSET_KEYS, CardSpec, RenderSpec

__all__ = ["CoreRenderPort"]

logger = logging.getLogger(__name__)

# 渲染运行时依赖（§7.7 第 2 步；find_spec 只探存在性，不 import）。
_RENDER_DEPENDENCIES = (
    "UnityPy",
    "PIL",
    "numpy",
    "scipy",
    "fontTools",
    "freetype",
    "texture2ddecoder",
    "pythonnet",
)

# .NET 运行时探针结果（进程级缓存）：preflight 只真探一次，成功后渲染链
# 的重复 ``load("coreclr")`` 与本层无关；失败不缓存（raise 即中断本次流程）。
_DOTNET_PROBE_OK = False

# overrides 从 CardSpec 显式字段重建的键序（§9.1；只放非 None 的键）。
_OVERRIDE_KEYS = (
    "name",
    "desc",
    "classes",
    "races",
    "cost",
    "attack",
    "health",
    "armor",
    "cardtype",
    "rarity",
    "premium",
    "spell_school",
    "cost_banner",
    "elite",
    "runes",
    "tech_level",
)


def _env_unavailable(
    code: str, sentinel: str, message: str, *, cause: str = ""
) -> EnvironmentUnavailable:
    return EnvironmentUnavailable(Problem(
        ProblemKind.ENVIRONMENT, code, sentinel, message, cause=cause
    ))


def _probe_writable(directory: Path) -> None:
    """目录可写探针：mkdir + 建删临时文件；失败抛 OSError（调用方分类）。"""
    directory.mkdir(parents=True, exist_ok=True)
    probe = directory / ".eidolon_write_probe"
    probe.write_bytes(b"")
    probe.unlink()


class CoreRenderPort:
    """shell ``render`` 命令的输出端口：preflight + core 渲染流水线。

    ``__init__`` 只收 ``font_dirs``（OS 字体目录，entry 从
    ``shell.paths.default_font_dirs()`` 注入）；``cache_root`` 从
    ``spec.game.cache_root`` 取，不经构造参数传第二份。
    """

    def __init__(self, *, font_dirs: tuple[Path, ...]) -> None:
        self.font_dirs = tuple(Path(d) for d in font_dirs)

    # ------------------------------------------------------------------
    # preflight（§7.7 十步；不打印、不写 stdout，错误全走异常）
    # ------------------------------------------------------------------

    def preflight(self, spec: RenderSpec) -> None:
        # 1. 组合层编程错误：render 路径必须先经 provider.bind 拿到 game。
        #    设计定性为 internal（退出 1）——EnvironmentUnavailable.kind 恒
        #    ENVIRONMENT，装不下 internal，故直接裸 RuntimeError（entry
        #    未预期异常 → internal 1）。
        game = spec.game
        if game is None:
            raise RuntimeError(
                "CoreRenderPort.preflight: spec.game 为 None——render 路径必须"
                "先经 provider.bind（GameContext 缺失是组合层 bug，不是用户输入）"
            )
        # 2. 安装进程渲染身份（幂等；先于任何 core import——§7.7 序）。
        from eidolon.core.infra import context

        context.install(game)
        # 3. 依赖存在性（先于 font/glyph import；§7.7 第 2 步）。
        self._check_dependencies()
        # 4. 字体目录注入 + 字形缓存根探针（glyph_supply import 依赖
        #    fontTools/freetype，必须在第 3 步之后）。
        self._install_fonts(game)
        # 5. locale 语言目录。
        self._check_locale(game)
        # 6. 安装完整性（game_exe / assembly / dbf）。
        self._check_install(game)
        # 7. cache_root 可写。
        self._check_cache_root(game)
        # 8. out_dir 形状（INPUT）与可写（ENV）。
        self._check_out_dir(spec)
        # 9 + 10. 覆盖资产静态规约 + 覆盖语义轻校验；INPUT 收集一次抛，
        #         ENVIRONMENT 不塞进 SpecErrors。
        self._check_overrides(spec)
        # 11. route 预热（组合层附加步，§7.7 十步之外；best-effort——预热是
        #     优化不是正确性前提，任何异常只 WARN 不阻塞渲染）。``spec``
        #     命令不经本类，天然不触达。
        self._prewarm_route(spec)

    def _check_dependencies(self) -> None:
        missing: list[str] = []
        for name in _RENDER_DEPENDENCIES:
            try:
                found = importlib.util.find_spec(name)
            except (ImportError, ValueError):
                found = None
            if found is None:
                missing.append(name)
        if missing:
            raise _env_unavailable(
                "dependency_missing",
                f"env:{missing[0]}",
                f"dependency_missing: 渲染依赖缺失（{', '.join(missing)}）——"
                "按 pyproject.toml 安装渲染运行时依赖",
            )
        # 3b. CLR 真探测：模块存在 ≠ 运行时可用（无 .NET 的机器上
        #     pythonnet 照样装得上）。
        self._probe_dotnet_runtime()

    def _probe_dotnet_runtime(self) -> None:
        """真实探测 .NET 运行时（§7.7 第 3 步后半；进程级缓存）。

        ``find_spec`` 只证明 pythonnet 模块存在，证明不了 CLR 可用：无
        .NET 时 ``load("coreclr")`` 到首卡渲染才抛 RuntimeError，被逐卡期
        映射成 render_failed（用户看到"疑似 bug"）。这里 preflight 就地探
        一次；``load("coreclr")`` 幂等可重复，与渲染链后续 dll_reflect 的
        再调不冲突。测试纪律（默认不触 CLR）由 ``AdaptersCase`` 在本 seam
        打桩。
        """
        global _DOTNET_PROBE_OK
        if _DOTNET_PROBE_OK:
            return
        try:
            from pythonnet import load

            load("coreclr")
        except (ImportError, ModuleNotFoundError, RuntimeError, OSError) as exc:
            cause = f"{type(exc).__name__}: {exc}"
            raise _env_unavailable(
                "dependency_missing",
                "env:dotnet",
                f"dependency_missing: .NET 运行时不可用（{cause}）——"
                "安装 .NET 运行时后重试",
                cause=cause,
            ) from exc
        _DOTNET_PROBE_OK = True

    def _install_fonts(self, game) -> None:
        fonts_cache = game.cache_root / "fonts"
        try:
            from eidolon.core.render.text import glyph_supply
        except ImportError as exc:
            cause = f"{type(exc).__name__}: {exc}"
            raise _env_unavailable(
                "dependency_missing",
                "env:fonttools",
                f"dependency_missing: 字形供给模块装载失败（{cause}）",
                cause=cause,
            ) from exc
        except (RuntimeError, AssertionError, OSError) as exc:
            # §7.7：preflight 内 core import 不得让裸 RuntimeError / 断言 /
            # OSError 落到 entry 的 internal 1。
            cause = f"{type(exc).__name__}: {exc}"
            raise _env_unavailable(
                "constants_unavailable",
                "eidolon",
                f"constants_unavailable: 字形供给模块装载失败（{cause}）",
                cause=cause,
            ) from exc
        try:
            glyph_supply.install_font_dirs(self.font_dirs, cache_dir=fonts_cache)
            _probe_writable(fonts_cache)
        except OSError as exc:
            # 只有 cache_dir 的 mkdir/写探针失败归 cache_unwritable；
            # install_font_dirs 本身无 I/O（目录枚举在 family_index 惰性）。
            cause = f"{type(exc).__name__}: {exc}"
            raise _env_unavailable(
                "cache_unwritable",
                str(fonts_cache),
                f"cache_unwritable: 字形缓存目录不可写（{cause}）",
                cause=cause,
            ) from exc

    def _check_locale(self, game) -> None:
        strings_dir = game.strings_dir
        if strings_dir.is_dir():
            return
        strings_root = game.root / "Strings"
        if strings_root.is_dir():
            available = sorted(p.name for p in strings_root.iterdir() if p.is_dir())
        else:
            available = []
        raise _env_unavailable(
            "locale_missing",
            str(strings_dir),
            f"locale_missing: 游戏数据缺语言目录 {strings_dir}（游戏根 {game.root}）；"
            f"root/Strings 下实际存在：{available if available else '（无 Strings 目录）'}",
        )

    def _check_install(self, game) -> None:
        missing = [p for p in (game.game_exe, game.assembly_csharp) if not p.is_file()]
        dbf_ok = game.dbf_path.is_file()
        if missing:
            detail = [str(p) for p in missing] + (
                [] if dbf_ok else [str(game.dbf_path)]
            )
            raise _env_unavailable(
                "game_dir_incomplete",
                str(missing[0]),
                "game_dir_incomplete: 游戏安装缺少关键文件（"
                + "、".join(detail)
                + "）——在战网里对游戏执行扫描/修复",
            )
        if not dbf_ok:
            raise _env_unavailable(
                "dbf_missing",
                str(game.dbf_path),
                "dbf_missing: 游戏安装缺 Data/Win/dbf.unity3d——"
                "在战网里扫描/修复游戏文件",
            )

    def _check_cache_root(self, game) -> None:
        try:
            _probe_writable(game.cache_root)
        except OSError as exc:
            cause = f"{type(exc).__name__}: {exc}"
            raise _env_unavailable(
                "cache_unwritable",
                str(game.cache_root),
                f"cache_unwritable: 缓存根不可写（{cause}）",
                cause=cause,
            ) from exc

    def _check_out_dir(self, spec: RenderSpec) -> None:
        out_dir = spec.options.out_dir
        shape_bad: str | None = None
        if out_dir.exists() and not out_dir.is_dir():
            shape_bad = f"路径存在但不是目录: {out_dir}"
        else:
            parent = out_dir.parent
            if parent.exists() and not parent.is_dir():
                shape_bad = f"父路径是文件: {parent}"
            else:
                drive = os.path.splitdrive(str(out_dir))[0]
                if drive and not os.path.exists(drive + os.sep):
                    shape_bad = f"盘符/卷不存在: {drive}"
        if shape_bad is not None:
            errors = SpecErrors()
            errors.add("out_dir_invalid", str(out_dir), shape_bad)
            errors.raise_if_any()
        try:
            _probe_writable(out_dir)
        except OSError as exc:
            cause = f"{type(exc).__name__}: {exc}"
            raise _env_unavailable(
                "out_dir_unwritable",
                str(out_dir),
                f"out_dir_unwritable: 输出目录不可写（{cause}）",
                cause=cause,
            ) from exc

    def _check_overrides(self, spec: RenderSpec) -> None:
        """覆盖资产静态规约（§7.7 第 9 步）+ 覆盖语义轻校验（第 10 步）。

        INPUT 类全部收集后抛一次 :class:`SpecErrors`；ENVIRONMENT 类
        （constants_unavailable 等）不塞进 SpecErrors——INPUT 优先抛，
        其次首个 ENV Problem。
        """
        try:
            from eidolon.core.render import assets as core_assets
            from eidolon.core.render.preflight import validate_overrides
        except ImportError as exc:
            cause = f"{type(exc).__name__}: {exc}"
            raise _env_unavailable(
                "dependency_missing",
                "env:pythonnet",
                f"dependency_missing: 渲染链模块装载失败（{cause}）",
                cause=cause,
            ) from exc
        except (RuntimeError, AssertionError, OSError) as exc:
            # §7.7：preflight 内 core import 不落 internal 1。
            cause = f"{type(exc).__name__}: {exc}"
            raise _env_unavailable(
                "constants_unavailable",
                "eidolon",
                f"constants_unavailable: 渲染链模块装载失败（{cause}）",
                cause=cause,
            ) from exc

        errors = SpecErrors()
        env_problems: list[Problem] = []

        render_cards = [self._to_render_card(card) for card in spec.cards]

        for index, card in enumerate(spec.cards):
            for key in sorted(card.assets):
                path = card.assets[key]
                if key not in ASSET_KEYS:
                    continue  # shell 输入面只允许三座位；防御面不校验
                try:
                    core_assets.validate_dimensions(path, key)
                    core_assets.read_rgba(path)
                except InputRejected as exc:
                    errors.add(
                        exc.problem.code,
                        f"cards[{index}].asset.{key}",
                        exc.problem.message,
                    )
                except ImportError as exc:
                    cause = f"{type(exc).__name__}: {exc}"
                    raise _env_unavailable(
                        "dependency_missing",
                        "env:PIL",
                        f"dependency_missing: PIL 装载失败（{cause}）",
                        cause=cause,
                    ) from exc

        for index, render_card in enumerate(render_cards):
            try:
                problems = validate_overrides((render_card,))
            except ImportError as exc:
                cause = f"{type(exc).__name__}: {exc}"
                raise _env_unavailable(
                    "dependency_missing",
                    "env:pythonnet",
                    f"dependency_missing: 渲染链装载失败（{cause}）",
                    cause=cause,
                ) from exc
            except (RuntimeError, AssertionError, OSError) as exc:
                # CLR 装载失败 / _mirror 断言不落 internal 1（§7.7 第 2 步）。
                cause = f"{type(exc).__name__}: {exc}"
                raise _env_unavailable(
                    "constants_unavailable",
                    "eidolon",
                    f"constants_unavailable: 覆盖语义轻校验失败（{cause}）",
                    cause=cause,
                ) from exc
            for problem in problems:
                if problem.kind is ProblemKind.ENVIRONMENT:
                    env_problems.append(problem)
                else:
                    errors.add(
                        problem.code,
                        self._card_problem_path(problem.path, index),
                        problem.message,
                    )

        errors.raise_if_any()
        if env_problems:
            raise EnvironmentUnavailable(env_problems[0])

    @staticmethod
    def _card_problem_path(path: str, index: int) -> str:
        """轻校验 Problem 的 path 补卡级索引（Phase 3b 遗留面）。

        ``card_overrides`` 只给键级定位（``cost`` / ``assets.frame``）；
        preflight style Problem 的 path 在单卡调用下是 ``cards[0]``。两者都
        改写成 ``cards[<index>]`` / ``cards[<index>].<key>``；``eidolon``
        哨兵（live 枚举缺名）原样保留。
        """
        if path.startswith("cards["):
            return f"cards[{index}]"
        if path == "eidolon":
            return path
        return f"cards[{index}].{path}"

    # ------------------------------------------------------------------
    # route 预热（P0-2；best-effort 附加步——失败不阻塞渲染）
    # ------------------------------------------------------------------

    def _prewarm_route(self, spec: RenderSpec) -> None:
        """按请求卡集预热 route 缓存（fresh cache 首跑 scoped 建库）。

        B1 实测（build/phase1/b1/）：无预热时 fresh cache 首个 ``open_bundle``
        触发全量建库（11,159 包 / ~349s）；按卡集 ``route.prewarm`` 只建工作
        集（5 卡 0.7s）。本步在 preflight 尾部（渲染链 ``ensure`` 之前）执行，
        `--jobs` 时 worker 只用父进程已建好的 scoped 库（worker 不跑
        preflight，不会各自触发建库）。任何异常（manifest 缺失 / route 锁忙 /
        OSError）只 WARN——预热是优化，不是正确性前提，失败时渲染链照旧走
        既有建库 / lazy 兜底路径。
        """
        try:
            self._prewarm_route_impl(spec)
        except Exception as exc:  # noqa: BLE001 —— best-effort：绝不阻塞渲染
            logger.warning("route prewarm skipped: %s", exc)

    def _prewarm_route_impl(self, spec: RenderSpec) -> None:
        # core lazy import（组合层纪律：本模块顶层只 import 标准库/contracts/
        # shell；dbf / ManifestIndex / route 都属 core，函数体内引）。
        from eidolon.core.infra import dbf
        from eidolon.core.infra import route
        from eidolon.core.infra.resolve_asset_ref import ManifestIndex

        game = spec.game
        # 1. dbf 会话（provider.bind 已装）；无则跳过（不 WARN——合法缺席）。
        module = dbf.installed_default()
        if module is None:
            return
        # 2. dbf id → 正典 card id。``card_id_to_dbf`` 的键是 casefold 面，
        #    反转直接回查会丢大小写；``cards_map`` 键大小写敏感，必须用
        #    ``m_noteMiniGuid`` 原样值（``Card.card_id`` 同源正典轴）。
        dbf_to_card: dict[int, str] = {}
        for dbf_id, row in module.card.items():
            guid = row.get("m_noteMiniGuid")
            if guid:
                dbf_to_card[dbf_id] = str(guid)
        # 3. 请求卡集 → 正典 card id（有序去重）。``kind=="card"`` 输入大小写
        #    不敏感（core ``resolve_dbf_id`` 同款 casefold 判据），经 dbf 归一；
        #    查不到的跳过（渲染期照旧报错，不静默扩大工作集）。
        ids: dict[str, None] = {}
        for card in spec.cards:
            ref = card.ref
            if ref.kind == "dbf":
                card_id = dbf_to_card.get(ref.value)
            else:
                card_id = dbf_to_card.get(
                    module.card_id_to_dbf.get(str(ref.value).casefold()))
            if card_id is not None:
                ids.setdefault(card_id, None)
        if not ids:
            return
        # 4. 卡集 → bundle 工作集（定位半程，不开包）；空则跳过。
        working = ManifestIndex(game.data_win).card_working_set(
            ids, locale=game.locale)
        bundles = working.get("bundles") or []
        if not bundles:
            return
        # 5. scoped 建库（已命中不重建；mode=off 时库面自己 no-op）。
        route.prewarm(root=game.route_cache, mode=game.route_mode,
                      data_win=game.data_win, version=game.version,
                      bundles=bundles)

    # ------------------------------------------------------------------
    # render + 形状转换（§9.1）
    # ------------------------------------------------------------------

    def render(self, spec: RenderSpec) -> RenderReport:
        game = spec.game
        if game is None:
            raise RuntimeError(
                "CoreRenderPort.render: spec.game 为 None——render 路径必须"
                "先经 provider.bind（GameContext 缺失是组合层 bug，不是用户输入）"
            )
        from eidolon.core.infra import context

        context.install(game)  # 幂等；preflight 已装则 no-op
        request = self.to_request(spec)
        from eidolon.core.render.api import render as core_render

        return core_render(request)

    def to_request(self, spec: RenderSpec) -> RenderRequest:
        """``RenderSpec`` → ``RenderRequest``（不校验字段；只做形状转换）。

        ``overrides`` 从 CardSpec 显式字段重建（只放非 None 键；
        ``runes`` 转普通 dict）；``assets`` 复制；``hero_style`` /
        ``bg_style`` = 请求 ∩ 生效适用（``style_requested[i] and
        CardSpec.hero_style/bg_style``，§5.4——raw 请求不直发 core）；
        ``style_requested`` 原样只进结果 manifest；``session_t=None``
        （core 落 PRODUCT_SESSION_T）。
        """
        return RenderRequest(
            cards=tuple(self._to_render_card(card) for card in spec.cards),
            out_dir=spec.options.out_dir,
            jobs=spec.options.jobs,
            antialias=spec.options.antialias,
            game=spec.game,
            font_dirs=self.font_dirs,
        )

    def _to_render_card(self, card: CardSpec) -> RenderCard:
        overrides: dict[str, object] = {}
        for key in _OVERRIDE_KEYS:
            value = getattr(card, key)
            if value is None:
                continue
            overrides[key] = dict(value) if key == "runes" else value
        hero_requested, bg_requested = card.style_requested
        # 全局 style 开关是批级请求，逐卡必须与生效值取交：`--bg-style` 只作用于
        # 非 HERO 卡，`--hero-style` 只作用于 HERO 卡（README/§5.4 正交语义）。
        return RenderCard(
            ref=card.ref,
            out_path=card.out_path,
            overrides=overrides,
            assets=dict(card.assets),
            hero_style=hero_requested and card.hero_style,
            bg_style=bg_requested and card.bg_style,
            session_t=None,
        )
