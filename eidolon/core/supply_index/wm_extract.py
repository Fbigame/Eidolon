"""wm_extract — cold 侧 watermark 域提取（四级裁决+dbf 三表；UnityPy 面）。

职责切分（参照 eidolon/core/supply/watermarks.py 头注同判）：**哪张水印**（四级裁决）
=本模块（eidolon/core/infra/card.py:Card.watermark_ref 语义转写——数据源 dbf 直读）；**纹理字节**
=decode worker（portrait 同款 Texture2D→PNG，ref→resolve→decode）。

转写锚（渲染铁律：file:Class 函数位；参照只读，禁 import）：
- 四级裁决=eidolon/core/infra/card.py:Card.watermark_ref（:448 起）：卡级 override
  （EntityDef.cs:EntityDef.GetWatermarkTextureOverride）→ 活跃 set 纹理
  （set_id=card_set_offline 离线 GetCardSet 正典；CARD_SET 行 m_cardWatermarkTexture）
  → core set 无条件年标（EntityBase.cs:EntityBase.IsCoreCard；ref=DLL 反射
  SetRotationIcon.CORE_SET_WATERMARK_EVEN，冻结参照裁决=偶数轮）→ None。
  HIDE_WATERMARK 闸在消费侧 alpha 层（Actor.cs:Actor.UpdateWatermark）不在此。
- dbf 三表读取=dbf_metadata.DbfModule 字段语义（watermark_override/card_set_dict/
  card_set_offline）+ cold 域 raw pairs 读取口径（必须保留 #2：禁 env.container）。
"""
from __future__ import annotations

from pathlib import Path

from eidolon.core.supply_index._unity import (
    container_pairs,
    iter_serialized,
    load_bundle,
)


def read_dbf_watermark_inputs(win: Path) -> dict:
    """dbf.unity3d 水印三表（raw pairs；禁 env.container）——四级裁决数据面。"""
    env = load_bundle(win / "dbf.unity3d")
    sf = next(iter_serialized(env))
    pairs = {k: pid for k, pid in container_pairs(sf)}

    def read(name: str) -> list[dict]:
        key = next((k for k in pairs if k.upper().endswith(f"/{name}.ASSET")
                    or k.upper().endswith(f"{name}.ASSET")), None)
        if key is None:
            raise KeyError(f"dbf.unity3d 内无 {name}.asset")
        return sf.objects[pairs[key]].read_typetree()["Records"]

    return {
        "watermark_override": {u["m_ID"]: u["m_watermarkTextureOverride"]
                               for u in read("CARD")
                               if u["m_watermarkTextureOverride"]},
        "card_set_dict": {u["m_ID"]: u for u in read("CARD_SET")},
        # 离线 GetCardSet 正典（watermark-chain 定案）：CARD_SET_TIMING 203 首条（表序=优先序）
        "card_set_offline": _card_set_offline(read("CARD_SET_TIMING")),
    }


def _card_set_offline(rows: list[dict]) -> dict[int, int]:
    out: dict[int, int] = {}
    for u in rows:
        if u["m_eventTimingEvent"] == 203 and u["m_cardId"] not in out:
            out[u["m_cardId"]] = u["m_cardSetId"]
    return out


def resolve_watermark_ref(dbf_id: int | None, inputs: dict, year_icon: str) -> str | None:
    """四级水印裁决 → 纹理 ref（"名.ext:GUID"）或 None=无水印。

    [card.py:Card.watermark_ref :443-469 语义逐字转写；year_icon=tables.year_icon_even
    （DLL 反射直取，偶数轮冻结参照）]"""
    if dbf_id is None:
        return None
    text = inputs["watermark_override"].get(dbf_id) or ""
    sid = inputs["card_set_offline"].get(dbf_id)
    row = inputs["card_set_dict"].get(sid) if sid is not None else None
    if not text:
        text = (row or {}).get("m_cardWatermarkTexture") or ""
    if row and row.get("m_isCoreCardSet"):
        text = year_icon
    return text or None
