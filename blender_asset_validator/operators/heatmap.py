import bpy

from . import ObjectModeOnly
from ..core.engine import load_config
from ..operations.heatmap import METRICS, clear_heatmap, show_heatmap


def _view3d_spaces(context):
    return [area.spaces.active for area in context.screen.areas if area.type == "VIEW_3D"]


class ASSET_VALIDATOR_OT_show_heatmap(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.show_heatmap"
    bl_label = "Heatmap"
    bl_description = "Color the faces of the selected meshes by a quality metric (blue fine, red bad, gray not applicable)"
    bl_options = {"REGISTER", "UNDO"}

    metric: bpy.props.EnumProperty(items=[(key, label, desc) for key, (label, desc, _) in METRICS.items()])

    def execute(self, context):
        objects = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not objects:
            self.report({"ERROR"}, "Select at least one mesh object first")
            return {"CANCELLED"}
        config = load_config()
        for mesh_owner in {obj.data: obj for obj in objects}.values():  # linked duplicates: once per mesh
            show_heatmap(mesh_owner, self.metric, config)
        for space in _view3d_spaces(context):
            space.shading.type = "SOLID"
            space.shading.color_type = "VERTEX"  # shown as "Attribute" in the UI
        self.report({"INFO"}, f"{METRICS[self.metric][0]}: blue fine, red bad, gray not applicable")
        return {"FINISHED"}


class ASSET_VALIDATOR_OT_clear_heatmap(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.clear_heatmap"
    bl_label = "Clear Heatmap"
    bl_description = "Remove the heatmap colors from every mesh and go back to material colors"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cleared = sum(clear_heatmap(obj) for obj in {o.data: o for o in context.scene.objects if o.type == "MESH"}.values())
        for space in _view3d_spaces(context):
            if space.shading.color_type == "VERTEX":
                space.shading.color_type = "MATERIAL"
        self.report({"INFO"}, f"Cleared {cleared} heatmap(s)")
        return {"FINISHED"}
