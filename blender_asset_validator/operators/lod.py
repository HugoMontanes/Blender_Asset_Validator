import bpy

from . import ObjectModeOnly
from ..core.engine import load_config
from ..operations.lod import generate_lods
from ..ui.redraw import redraw_view3d


class ASSET_VALIDATOR_OT_generate_lods(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.generate_lods"
    bl_label = "Generate LODs"
    bl_description = "Bake (or regenerate) shape-preserving LOD meshes of the selected objects (config 'lod')"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        config = load_config()
        objects = [
            obj for obj in context.selected_objects
            if obj.type == "MESH" and not obj.get("asset_validator_lod", False)
        ]

        if not objects:
            self.report({"ERROR"}, "Select at least one source mesh object first")
            return {"CANCELLED"}

        created = generate_lods(objects, config)
        print("\n".join(created))

        if created:
            self.report({"INFO"}, f"Generated {len(created)} LOD object(s)")
        else:
            self.report({"WARNING"}, "No LOD levels configured (config/default.json 'lod.levels')")

        redraw_view3d(context)
        return {"FINISHED"}
