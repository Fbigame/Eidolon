"""art — 原画域（批9a① 立壳：转发态，步2 还原后为配方实现住址；supply 源=eidolon/core/supply/art.py）。

批 portrait-mip-lod（2026-10-20）增 portrait_mip：肖像纹理真 mip 链按需直提
（(bundle, path_id) 消费点登记 → textures.chain_for_name；肖像公式层 LOD 采样消费位）。
批 portrait-locale（2026-10-23）增 portrait_source：肖像资产来源账（locale/变体地址，
plan.portrait["asset"] 消费；寻址与 portrait 同链——客户端 locale 变体解析）。
"""
from eidolon.core.supply.art import portrait, portrait_mip, portrait_source

__all__ = ["portrait", "portrait_mip", "portrait_source"]
