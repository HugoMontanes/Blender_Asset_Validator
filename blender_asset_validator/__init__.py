bl_info = {
    "name": "Asset Validator",
    "author": "Hugo Montañés García",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > N-Panel > Asset Validator",
    "description": "Validates mesh assets against pipeline standards and exports to FBX",
    "category": "Object",
}

import bpy
from bpy.app.handlers import persistent

# Importing checks registers them via @register_check — order matters
from . import checks  # noqa: F401 (side-effect import)

from .operators.validate import ASSET_VALIDATOR_OT_validate
from .operators.fix import ASSET_VALIDATOR_OT_fix_result, ASSET_VALIDATOR_OT_fix_all
from .operators.lod import ASSET_VALIDATOR_OT_generate_lods
from .operators.topology import ASSET_VALIDATOR_OT_clean_topology, ASSET_VALIDATOR_OT_retopologize
from .operators.export import ASSET_VALIDATOR_OT_export_fbx
from .ui.panel import ASSET_VALIDATOR_PT_main
from .core.engine import PRESET_ITEMS
from .core.state import clear_results

_CLASSES = (
    ASSET_VALIDATOR_OT_validate,
    ASSET_VALIDATOR_OT_fix_result,
    ASSET_VALIDATOR_OT_fix_all,
    ASSET_VALIDATOR_OT_generate_lods,
    ASSET_VALIDATOR_OT_clean_topology,
    ASSET_VALIDATOR_OT_retopologize,
    ASSET_VALIDATOR_OT_export_fbx,
    ASSET_VALIDATOR_PT_main,
)


@persistent
def _clear_results_on_load(*_):  # argument count differs across Blender versions
    clear_results()  # results hold Objects of the previous file


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.asset_validator_preset = bpy.props.EnumProperty(
        name="Preset",
        description="Rule preset merged on top of config/default.json",
        items=PRESET_ITEMS,
        update=lambda self, context: clear_results(),  # old results were judged by other rules
    )
    bpy.app.handlers.load_post.append(_clear_results_on_load)


def unregister():
    bpy.app.handlers.load_post.remove(_clear_results_on_load)
    del bpy.types.Scene.asset_validator_preset
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
