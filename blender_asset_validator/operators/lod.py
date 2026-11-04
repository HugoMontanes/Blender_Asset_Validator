import bpy

from . import ObjectModeOnly
from ..core.engine import load_config
from ..core.mesh_utils import repair_invalid
from ..operations.lod import STRAY, generate_lods, lods_of
from ..ui.redraw import redraw_view3d
from .uvs import asset_meshes


class ASSET_VALIDATOR_OT_generate_lods(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.generate_lods"
    bl_label = "Generate LODs"
    bl_description = "Bake (or regenerate) shape-preserving LOD meshes of the selected objects (config 'lod')"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        config = load_config()
        objects = asset_meshes(context.selected_objects, config)  # not LODs, collision or high-poly meshes

        if not objects:
            self.report({"ERROR"}, "Select at least one asset mesh first")
            return {"CANCELLED"}
        repair_invalid(objects, self)

        created = generate_lods(objects, config)
        print("\n".join(created))

        strayed = [lod.name for obj in objects for lod in lods_of(obj) if STRAY in lod]
        if strayed:
            self.report({"WARNING"}, f"Generated {len(created)} LOD object(s); these stray from their source past "
                        f"lod.max_deviation, give them a higher ratio: {', '.join(strayed)}")
        elif created:
            self.report({"INFO"}, f"Generated {len(created)} LOD object(s)")
        else:
            self.report({"WARNING"}, "No LOD levels configured (config/default.json 'lod.levels')")

        redraw_view3d(context)
        return {"FINISHED"}
