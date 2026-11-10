"""batch — 批量渲染门面（consumer-v2 段1：本体=old batch 逐字副本，消费面换新 components 委托壳——dispatch 由新 card.assemble 承担）。

契约：
  * 调用方只构造 RenderJob；不传 t / session_time / phase。
  * form=三态形态词表（plain/bg/hero，与 zone_when.stem_form 同一词表；调用方
    `form=zt.stem_form(stem, None)` 直通）。解码单点+HERO×bg 守卫=components.
    resolve_form；bg/hero 显式（True/False），plain=None 数据推导——裸名是旧账
    兼容歧义形态（旧 bacon 行裸名别名存在，显式 constructed 被 full 门证伪：
    120259/98918，2026-10-31）；对拍原始轴=render_with 显式 cfg.use_bg_style。
    （style 混轴枚举退役，2026-10-30 render-form-axis）
  * 本门面串行渲染；--jobs 进程池由 gate 在 chunk 层拥有，不在本模块内再开 pool。
  * 图片只落盘，RenderResult 不携带 PIL.Image；图片消费口=RenderResult.out_png。
  * gate 的 data 读审计在 chunk 外层包 render_data_window；本模块不感知 gate/data。

初相正典（2026-10-27 用户裁定）：内部固定 t_phase=0.0、session_time=None——渲染只对齐
初相，这就是正典而非过渡；旧 v2 相位轴（t / session_time）已退役，不再是渲染输入，
任何调用方都无从（也无需）传相位。
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Literal

from eidolon.core.infra.card import Card
from eidolon.core.render.game.actor.components import (  # consumer-v2 新链（段1 委托壳）
    RenderConfig,
    RenderForm,
    canonical_cfg,
    render_with,
    resolve_form,
)

RenderVariant = Literal["origin", "notext", "textonly"]
RenderPayload = dict[str, Any]
RenderCardsResult = list["RenderResult"]

_VARIANTS = {"origin", "notext", "textonly"}
_VARIANT_FLAGS = {
    "origin": (False, False),
    "notext": (True, False),
    "textonly": (False, True),
}


@dataclass(frozen=True)
class RenderJob:
    """一张卡 + 一个态的最小渲染任务。

    form 无缺省必填——忘传=TypeError（fail loud）：形态是调用方必须显式想清楚
    的语义，不设静默缺省。
    card（contract C 判据 1/2，2026-11-06）：Card 门面实例（eidolon.core.infra.card.Card）
    ——render_cards 四入口收 Card 的批量面：传 Card 时整链（resolve_form 守卫→
    render_with→assemble→resolve_prefab→compile_plan）复用本对象，零 from_dbf，
    desc/assets/tag 覆盖就地生效；None=dbf 旧路径零变化。dbf 仍是任务身份轴
    （校验/log 面），传 Card 时建议给 canonical 数字串。
    """

    stem: str
    dbf: str
    form: RenderForm
    variant: RenderVariant = "origin"
    out_png: Path | None = None
    card: Card | None = None


@dataclass
class RenderResult:
    """单卡单态结果；失败也返回，不靠异常打断整批。"""

    job: RenderJob
    ok: bool
    elapsed_s: float
    out_png: Path | None = None
    result: RenderPayload | None = None
    error: str | None = None
    traceback: str | None = None

    @property
    def stem(self) -> str:
        return self.job.stem

    @property
    def variant(self) -> RenderVariant:
        return self.job.variant


def _validate(job: RenderJob) -> None:
    if not job.stem:
        raise ValueError("RenderJob.stem 不能为空")
    if not job.dbf:
        raise ValueError(f"RenderJob[{job.stem}].dbf 不能为空")
    if job.variant not in _VARIANTS:
        raise ValueError(f"RenderJob[{job.stem}].variant 非法：{job.variant!r}")
    if job.form not in ("plain", "bg", "hero"):
        raise ValueError(f"RenderJob[{job.stem}].form 非法：{job.form!r}（词表三态 plain/bg/hero）")
    if job.card is not None and not isinstance(job.card, Card):
        raise ValueError(
            f"RenderJob[{job.stem}].card 须为 Card 门面实例（eidolon.core.infra.card.Card），"
            f"得到 {type(job.card).__name__}")


def _render_job(job: RenderJob, cfg: RenderConfig, out_png: Path) -> RenderPayload:
    """把 job 映射到 render_with；固定相位 0，形态按 job.form 解码（单点+
    HERO×bg 守卫=resolve_form，components 层与薄壳共用）。
    job.card 在场=Card 轴（contract C 判据 1/2）：Card 对象直通 resolve_form/
    render_with，整链零 from_dbf；None=dbf 旧路径。"""
    notext, textonly = _VARIANT_FLAGS[job.variant]
    target = job.card if job.card is not None else job.dbf
    use_bg_style, zone = resolve_form(target, job.form)
    job_cfg = replace(cfg, use_bg_style=use_bg_style)
    res = render_with(
        target,
        job_cfg,
        t_phase=0.0,
        zone=zone,
        notext=notext,
        textonly=textonly,
        out_png=out_png,
        session_time=None,
    )
    # 图片只走文件；批量结果不带 PIL.Image。t 也不再进入对外 payload。
    res.pop("image", None)
    res.pop("t", None)
    return res


def render_cards(
    cards: Iterable[RenderJob],
    *,
    out_dir: Path | None = None,
    cfg: RenderConfig | None = None,
    fail_fast: bool = False,
) -> RenderCardsResult:
    """批量渲染门面。串行；调用方负责进程池/分块。

    Card 轴（contract C 判据 1/2，2026-11-06）：RenderJob.card 传 Card 门面实例
    时整链零 from_dbf（desc/assets/tag 覆盖就地生效）；None=dbf 旧路径零变化。

    output:
      * job.out_png 优先；
      * 否则 out_dir / <variant> / render_<stem>.png；
      * 两者都没有 = 开渲前报错（不存在只返回 log、不产出图的合法路径）。
    """
    jobs = tuple(cards)
    if not jobs:
        return []

    plans: list[tuple[RenderJob, Path]] = []
    seen: set[tuple[str, str]] = set()
    for job in jobs:
        _validate(job)
        key = (job.stem, job.variant)
        if key in seen:
            raise ValueError(f"重复的 (stem, variant)：{key}")
        seen.add(key)

        out_png = job.out_png
        if out_png is None:
            if out_dir is None:
                raise ValueError(f"RenderJob[{job.stem}] 缺 out_png，且未给 out_dir")
            out_png = out_dir / job.variant / f"render_{job.stem}.png"
        out_png = Path(out_png)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        plans.append((job, out_png))

    base_cfg = cfg or canonical_cfg()
    base_cfg.apply()   # 进程级 mip 钩子；render_with 每卡也会 apply，重复无害

    results: RenderCardsResult = []
    for job, out_png in plans:
        t0 = time.perf_counter()
        try:
            payload = _render_job(job, base_cfg, out_png)
            results.append(RenderResult(
                job=job, ok=True, elapsed_s=round(time.perf_counter() - t0, 3),
                out_png=out_png, result=payload,
            ))
        except Exception as exc:  # noqa: BLE001 —— 批量失败隔离，不中断同批其它卡
            results.append(RenderResult(
                job=job, ok=False, elapsed_s=round(time.perf_counter() - t0, 3),
                out_png=out_png, error=f"{type(exc).__name__}: {exc}",
                traceback=traceback.format_exc(),
            ))
            if fail_fast:
                break
    return results


__all__ = [
    "RenderCardsResult",
    "RenderForm",
    "RenderJob",
    "RenderPayload",
    "RenderResult",
    "RenderVariant",
    "render_cards",
]
