"""错误契约：退出码、CODES 注册表、format_problem、SpecError(s)。

主契约是 :class:`~eidolon.contracts.Problem`（kind 是退出码的唯一来源，
``CODES`` 只存 code → 默认 hint）；退出码只做粗分类：

* ``0``   成功；
* ``1``   渲染失败或内部错误；
* ``2``   输入非法（CLI 用法、TOML、字段校验、catalog 读取失败）；
* ``3``   环境不可用（游戏没装、dbf 缺失、权限、依赖缺失等）；
* ``130`` KeyboardInterrupt。

生产约定：shell（load_input / compile_spec）发 ``INPUT``；core（bind /
facts）发 ``ENVIRONMENT``；组合层可发全部四类。新增 code 必须同时改
``CODES``、docs/architecture.md §9.3、docs/schema.md。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from eidolon.contracts import Problem, ProblemKind

EXIT_OK = 0
EXIT_RENDER_FAILED = 1
EXIT_INVALID_INPUT = 2
EXIT_ENVIRONMENT = 3
EXIT_INTERRUPTED = 130

MAX_ERRORS = 50
"""一次校验最多报告的 error 条数，超出部分丢弃并标记 truncated。"""

# code → 默认 hint（不存 kind）。每个注册 code 必须有非空 hint。
CODES: dict[str, str] = {
    # ---- 输入（2）----
    "usage": "检查命令行参数；--help 查看完整用法",
    "invalid_id": "确认 id；dbf id 用整数，card id 用 m_noteMiniGuid（如 CS2_182）",
    "duplicate_id": "同一批输入里去掉重复的 id",
    "unknown_card": "确认 id 是否存在于当前游戏数据；若客户端较新，也可能是枚举镜像未更新",
    "unknown_class": "使用已知职业名；若客户端较新，可能是枚举镜像未更新",
    "unknown_key": "删除未知键或改为受支持的键（见 docs/schema.md）",
    "enum": "使用受支持的枚举值（见 docs/schema.md）",
    "range": "把值调整到允许范围内",
    "missing": "补上必填字段",
    "type": "修正字段类型",
    "io": "确认文件路径与读取权限",
    "toml_syntax": "修正 TOML 语法",
    "format_version": "把 format_version 改为 1",
    "empty_cards": "至少声明一张 [[cards]]",
    "mode": "位置 id 与 --toml 只能二选一",
    "option_not_allowed": "该选项只在命令行模式可用；TOML 模式请把值写进文件",
    "style": "hero_style 只适用于 HERO 卡；bg_style 只适用于非 HERO 卡",
    "banner": "cost_banner 使用受支持的 10 个值之一（NONE、GRIMY_GOONS、KABAL 等）",
    "runes_total": "符文计数总和必须 <= 3",
    "unknown_rune": "rune 名只允许 BLOOD/FROST/UNHOLY",
    "duplicate_outname": "为重名的卡改 outname",
    "empty_classes": "classes 不能为空；要清空覆盖请删除该键",
    "empty_class": "职业名不能为空",
    "duplicate_class": "去掉重复的职业",
    "empty_race": "race 必须是非空字符串",
    "duplicate_race": "去掉重复的种族",
    "empty_rune": "rune 名不能为空",
    "asset": "asset 路径不能为空",
    "asset_ext": "asset 必须是 .png 文件",
    "asset_missing": "确认 asset 文件存在；相对路径按 TOML 所在目录解析",
    "asset_dimensions": "覆盖资产尺寸必须匹配座位规约（portrait 512×512 / frame 1024×1024 / watermark 128 或 256 见方）",
    "outname": "outname 不能包含路径分隔符或 '..'",
    "catalog_invalid": "确认 --catalog 指向合法的 JSON catalog（结构见 docs/schema.md）",
    "game_dir_invalid": "把 --game（或 TOML game_dir）指向包含 Hearthstone.exe 的游戏安装目录",
    "out_dir_invalid": "确认输出目录路径形状合法（不是文件、盘符/父路径存在）",
    # ---- 环境（3）----
    "game_not_found": "确认游戏已安装，或用 --game 指向安装根",
    "game_dir_incomplete": "在战网里对游戏执行扫描/修复",
    "dbf_missing": "在战网里扫描/修复游戏文件；或把 --game 指向包含 Hearthstone.exe 的目录",
    "dbf_unreadable": "更新游戏或 Eidolon；dbf 版本可能不受支持",
    "dependency_missing": "安装缺失的依赖（UnityPy / pythonnet / .NET 运行时）",
    "constants_unavailable": "客户端版本可能超出已支持集合；升级 Eidolon 或 facts 枚举镜像",
    "locale_missing": "用 --locale 选择游戏数据里实际存在的语言目录",
    "cache_unwritable": "确认缓存目录可写，或用 --cache-root 换一个位置",
    "route_cache_unreadable": "删除缓存根下的 route.db（派生缓存）后重试；或在战网里扫描/修复游戏文件",
    "out_dir_unwritable": "确认输出目录可写（权限 / 只读 / 磁盘空间）",
    "asset_missing_in_game": "确认游戏安装完整（在战网里扫描/修复）",
    "asset_format_unsupported": "该资产游戏内可正常渲染；其纹理格式（如 BC7）在 Eidolon 离线解码域外，扫描/修复无效——升级 Eidolon 换取更大格式覆盖",
    "write_failed": "确认磁盘可写且空间充足",
    # ---- 渲染（1）----
    "render_failed": "查看 message 定位失败原因；疑似实现问题请附 --debug 输出反馈",
    # ---- 内部（1）----
    "internal": "这是 bug；用 --debug 附 traceback 反馈",
    # ---- 迁移期保留 ----
    # 旧 code `catalog` 与 catalog_invalid 同义；保留一版后移除。
    "catalog": "确认 --catalog 指向合法的 JSON catalog（结构见 docs/schema.md）",
}


def format_problem(problem: Problem) -> str:
    """Problem 的唯一格式化点：``error[<code>] <path>: <message>`` + hint + cause。"""
    location = problem.path or "<root>"
    lines = [f"error[{problem.code}] {location}: {problem.message}"]
    hint = problem.hint or CODES.get(problem.code, "")
    if hint:
        lines.append(f"  hint: {hint}")
    if problem.cause:
        lines.append(f"  cause: {problem.cause}")
    return "\n".join(lines)


@dataclass(frozen=True)
class SpecError:
    """一条输入错误（shell 只发 INPUT）。

    ``path`` 使用输入结构里的定位符，例如 ``cards[1].cost``、
    ``cards[0].asset.portrait``、``--jobs``。
    """

    code: str
    path: str
    message: str

    def as_problem(self) -> Problem:
        return Problem(
            kind=ProblemKind.INPUT, code=self.code, path=self.path, message=self.message
        )

    def format(self) -> str:
        return format_problem(self.as_problem())

    def __str__(self) -> str:  # pragma: no cover - 便利方法
        return self.format()


class SpecErrors(Exception):
    """收集一组 :class:`SpecError`，全部校验结束后一次抛出。"""

    def __init__(self, errors: Iterable[SpecError] | None = None) -> None:
        initial = list(errors or ())
        self.truncated = len(initial) > MAX_ERRORS
        self.errors: list[SpecError] = initial[:MAX_ERRORS]
        super().__init__(str(self) if self.errors else "spec errors")

    def add(self, code: str, path: str, message: str) -> None:
        """追加一条错误；超过上限时只置 truncated，不再保存。"""
        if len(self.errors) >= MAX_ERRORS:
            self.truncated = True
            return
        self.errors.append(SpecError(code=code, path=path, message=message))

    def extend(self, errors: Iterable[SpecError]) -> None:
        for error in errors:
            self.add(error.code, error.path, error.message)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(error.code for error in self.errors)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(error.path for error in self.errors)

    def raise_if_any(self) -> None:
        if self.errors:
            raise self

    def __str__(self) -> str:
        lines = [error.format() for error in self.errors]
        if self.truncated:
            lines.append(f"... 错误过多，仅显示前 {MAX_ERRORS} 条")
        return "\n".join(lines)
