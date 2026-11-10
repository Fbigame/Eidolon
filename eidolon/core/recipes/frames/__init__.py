"""frames — 帧域（批9a① 立壳：转发态，步2 还原后为配方实现住址；supply 源=eidolon/core/supply/frames/ 整域转发）。

包面=supply.frames __all__（kit 族六件+类）+ D 节签名表深位域项（kits.actor_ref/
spell_school_names）+ 三子模块（dk.rune_atlas／injectors.badge_kit_mem/faction_kit_mem/
btf_tree_mem／supplements.ta_supplement/portrait_uv1/material_state）。
FRAME_SPECS 自批14 增补导出（specs.py 六帧族参数化差异表=纯数据，帧域规格面；
消费方=render/game/frames.py 帧键分派——textures 先例同款转发形态）。
"""
from eidolon.core.supply.frames import (AbilityKit, BadgesKit, BtfKit, Kit, OrnamentsKit,
                                   ability_kit, badges_kit, bacon_kit, btf_kit, kit,
                                   ornaments_kit)
from eidolon.core.supply.frames import dk, injectors, supplements
from eidolon.core.supply.frames.kits import actor_ref, spell_school_names
from eidolon.core.supply.frames.specs import FRAME_SPECS

__all__ = ["Kit", "kit", "AbilityKit", "ability_kit", "bacon_kit",
           "BadgesKit", "badges_kit", "OrnamentsKit", "ornaments_kit",
           "BtfKit", "btf_kit",
           "actor_ref", "spell_school_names", "dk", "injectors", "supplements",
           "FRAME_SPECS"]
