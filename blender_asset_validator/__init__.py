import bpy
from bpy.app.handlers import persistent

# Importing checks registers them via @register_check — order matters
from . import checks  # noqa: F401 (side-effect import)

from .operators.validate import ASSET_VALIDATOR_OT_validate, ASSET_VALIDATOR_OT_go_to_step, ASSET_VALIDATOR_OT_approve_step
from .operators.fix import (
    ASSET_VALIDATOR_OT_fix_result, ASSET_VALIDATOR_OT_select_result, ASSET_VALIDATOR_OT_fix_all, ASSET_VALIDATOR_OT_waive_result,
)
from .operators.heatmap import ASSET_VALIDATOR_OT_show_heatmap, ASSET_VALIDATOR_OT_clear_heatmap
from .operators.lod import ASSET_VALIDATOR_OT_generate_lods
from .operators.topology import ASSET_VALIDATOR_OT_clean_topology, ASSET_VALIDATOR_OT_retopologize
from .operators.uvs import ASSET_VALIDATOR_OT_set_texel_density, ASSET_VALIDATOR_OT_auto_unwrap
from .operators.hard_surface import ASSET_VALIDATOR_OT_hard_surface_prep
from .operators.export import ASSET_VALIDATOR_OT_export
from .ui.panel import ASSET_VALIDATOR_PT_main
from .core.engine import ENGINE_ITEMS, PRESET_ITEMS
from .core.state import clear_results
from .core.steps import STEPS

_CLASSES = (
    ASSET_VALIDATOR_OT_validate,
    ASSET_VALIDATOR_OT_go_to_step,
    ASSET_VALIDATOR_OT_approve_step,
    ASSET_VALIDATOR_OT_fix_result,
    ASSET_VALIDATOR_OT_select_result,
    ASSET_VALIDATOR_OT_fix_all,
    ASSET_VALIDATOR_OT_waive_result,
    ASSET_VALIDATOR_OT_show_heatmap,
    ASSET_VALIDATOR_OT_clear_heatmap,
    ASSET_VALIDATOR_OT_generate_lods,
    ASSET_VALIDATOR_OT_clean_topology,
    ASSET_VALIDATOR_OT_retopologize,
    ASSET_VALIDATOR_OT_set_texel_density,
    ASSET_VALIDATOR_OT_auto_unwrap,
    ASSET_VALIDATOR_OT_hard_surface_prep,
    ASSET_VALIDATOR_OT_export,
    ASSET_VALIDATOR_PT_main,
)


@persistent
def _clear_results_on_load(*_):  # argument count differs across Blender versions
    clear_results()  # results hold Objects of the previous file


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.asset_validator_engine = bpy.props.EnumProperty(
        name="Engine",
        description="Target engine: its export format, LOD layout and collision/socket naming (config/engines)",
        items=ENGINE_ITEMS,
        update=lambda self, context: clear_results(),
    )
    bpy.types.Scene.asset_validator_preset = bpy.props.EnumProperty(
        name="Preset",
        description="Rule preset (platform, budget) merged on top of the engine's rules (config/presets)",
        items=PRESET_ITEMS,
        update=lambda self, context: clear_results(),  # old results were judged by other rules
    )
    bpy.types.Scene.asset_validator_guided = bpy.props.BoolProperty(
        name="Step by Step",
        description="Review and approve the checks one step at a time instead of all at once",
        update=lambda self, context: clear_results(),  # old results cover other checks
    )
    bpy.types.Scene.asset_validator_step = bpy.props.IntProperty(min=0, max=len(STEPS) - 1)
    bpy.app.handlers.load_post.append(_clear_results_on_load)


def unregister():
    bpy.app.handlers.load_post.remove(_clear_results_on_load)
    del bpy.types.Scene.asset_validator_step
    del bpy.types.Scene.asset_validator_guided
    del bpy.types.Scene.asset_validator_preset
    del bpy.types.Scene.asset_validator_engine
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
