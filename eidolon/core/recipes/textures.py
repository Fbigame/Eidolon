"""textures — 纹理域（批9a① 立壳：转发态，步2 还原后为配方实现住址；supply 源=eidolon/core/supply/textures.py）。

supply 包 __init__ 未导出 textures（消费方现用 `from eidolon.core.supply.textures import
mip_registry` 直模块形态），本域照实同形转发。批24⑤ 增 mip_probe（消费时探针，
supply 消费面调用）。（2026-10-23 weapon-dk-frame：增 entry_for_ref——运行期纹理槽
按资产 ref 取真 mip 链条目，消费位=engine/raster 桶构建器。）
（2026-10-30 mip-q1 lazy：增 LazyFloatChain 转发——engine/raster 注册面与帧内采样要
判"链 L0 尺寸/内容"而不物化整链，惰性视图类型是跨域契约的一部分。）"""
from eidolon.core.supply.textures import (
    LazyFloatChain,
    chain_for_name,
    entry_for_ref,
    mip_probe,
    mip_registry,
)

__all__ = ["mip_registry", "mip_probe", "entry_for_ref", "chain_for_name",
           "LazyFloatChain"]
