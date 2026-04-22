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

# Importing checks registers them via @register_check — order matters
from . import checks  # noqa: F401 (side-effect import)

from .operators.validate import ASSET_VALIDATOR_OT_validate
from .operators.export import ASSET_VALIDATOR_OT_export_fbx
from .ui.panel import ASSET_VALIDATOR_PT_main

_CLASSES = (
    ASSET_VALIDATOR_OT_validate,
    ASSET_VALIDATOR_OT_export_fbx,
    ASSET_VALIDATOR_PT_main,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
