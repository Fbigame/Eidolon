"""overrides — 公开资产覆盖域（contract E，2026-11-06）：Card 覆盖座位的装载/校验/
身份单点。

外审 E 行（docs/audit/2026-11-06-eidolon-absorption-audit.md）：渲染链只有内部 plan
材质槽、没有公开覆盖接缝。contract C（14603b84）在 Card 落了 frame_asset/portrait_asset
座位；本域把座位消费化——装载+校验+内容寻址身份单一来源，消费经 render_with/assemble
链流入 plan 材质槽（frame/portrait）与水印 V-pass（watermark），**覆盖落 plan/supply
不改 scene 缓存**（_SCENES/_KIT_CACHE 零触碰——plan 每卡新构、scene 只读，判据面）。

语义定位（D 不变量继承）：覆盖=**卡级渲染输入**，禁进 GameContext/install。@item
会话 memo=天然单卡不跨卡（machine.Session 作用域），同卡同会话重复访问零重装载。

fail loud 纪律（contract E 判据 5）：覆盖座位非 None 即用户显式意图——路径不存在/
不可读/格式错一律 raise（带 kind+路径上下文），**禁静默回落数据轴**（回落=意图被吞，
外审「覆盖会静默无效」病灶的装载侧闭合）。

身份=内容寻址：sha256(文件字节) → 合成 ref `override:<kind>:<sha16>`。合成 ref 与
游戏资产 ref（"名.ext:GUID" 形）空间不相交（游戏 ref 无 `override:` 前缀），故
supply.textures._REF_ENTRY（ref 串→mip 链 memo）对覆盖恒 miss→None→mip0 直采：
「同 ref 身份换内容返回旧链」的串图位在构造上不存在（缓存键面账对 _REF_ENTRY 的
「若覆盖走 ref 身份」条件不成立——覆盖不走数据 ref 身份，豁免有据）。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PIL import Image

from eidolon.core.supply.machine import item

_KINDS = ("frame", "portrait", "watermark")
"""覆盖座种类域（合成 ref 种子+报错上下文；未知 kind=本域断言响亮，禁静默扩张）。"""


@item("overrides", "asset")
def asset(spec: str, kind: str) -> dict:
    """覆盖资产装载+校验（contract E 单点）：路径 → {"img","sha256","ref","path"}。

    spec=路径串（调用方经 _normalize 归一 os.fspath，str/Path 同址同 memo token）；
    kind ∈ frame/portrait/watermark（座位来源，进合成 ref 与报错上下文）。

    校验链（fail loud，逐级带上下文）：
      * kind 白名单断言；
      * spec 非空串；
      * 路径存在且是文件（目录/缺路径点名）；
      * PIL 可开且可转 RGBA（格式错=链式 raise，含 PIL 原因）——尺寸/内容语义不校验
        （产品 schema 分工：外壳只校验扩展名与存在性，尺寸/格式留给渲染层=本域）。

    返回 img=PIL RGBA（内存面，会话内单实例）；sha256=文件字节十六进制摘要（资产
    身份）；ref=`override:<kind>:<sha16>`（合成身份，进 plan atlas_ref/wm_ref——
    mip 链 entry_for_ref 对其恒 None=mip0 直采，见模块头注）；path=绝对路径串（账面）。
    """
    assert kind in _KINDS, f"覆盖 kind 非法：{kind!r}（域={_KINDS}）"
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError(f"{kind} 覆盖路径非法：{spec!r}（须非空路径串）")
    p = Path(spec)
    if not p.exists():
        raise FileNotFoundError(
            f"{kind} 覆盖路径不存在：{p}（覆盖座非 None=显式意图，禁静默回落数据轴——"
            "contract E fail loud）")
    if not p.is_file():
        raise ValueError(f"{kind} 覆盖路径不是文件：{p}（目录/特殊文件不收）")
    data = p.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    try:
        with Image.open(p) as im:
            img = im.convert("RGBA")   # 模式归一（内存面；惰性 load 在此触发）
    except Exception as e:  # noqa: BLE001 —— 格式错=响亮重raise（带 kind/路径/原因）
        raise ValueError(
            f"{kind} 覆盖资产格式错：{p}（sha256={sha[:16]}…）——PIL 无法解码为图："
            f"{type(e).__name__}: {e}") from e
    return {"img": img, "sha256": sha,
            "ref": f"override:{kind}:{sha[:16]}",
            "path": str(p.resolve())}


def _normalize(spec) -> str:
    """座位值归一：str/Path → fspath 串（同址同 token）；他型=TypeError 响亮。"""
    if isinstance(spec, (str, os.PathLike)):
        return os.fspath(spec)
    raise TypeError(
        f"覆盖座位须为 str|Path（得到 {type(spec).__name__}: {spec!r}）——"
        "覆盖轴类型面显式（contract E）")


def _of(card, attr: str, kind: str) -> dict | None:
    """座位读点：None=数据轴照旧（零装载零行为）；非 None=装载校验（fail loud）。"""
    spec = getattr(card, attr, None)
    return None if spec is None else asset(_normalize(spec), kind)


def frame_of(card) -> dict | None:
    """Card.frame_asset 座位读点（帧覆盖=类色图集写点平面整体换覆盖图）。"""
    return _of(card, "frame_asset", "frame")


def portrait_of(card) -> dict | None:
    """Card.portrait_asset 座位读点（原画覆盖=portrait 运行时槽复写）。"""
    return _of(card, "portrait_asset", "portrait")


def watermark_of(card) -> dict | None:
    """Card.watermark_asset 座位读点（水印覆盖=V-pass _SecondTex 源换覆盖图）。"""
    return _of(card, "watermark_asset", "watermark")
