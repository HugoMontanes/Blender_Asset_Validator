import math

import bpy

from . import ObjectModeOnly
from ..core.engine import load_config
from ..core.roles import role
from ..core.state import clear_results
from ..operations.uvs import auto_unwrap, median_density, set_texel_density, uv_stats
from ..ui.redraw import redraw_view3d

SKIPPED_NOTE = "LODs and collision meshes keep their UVs"


def asset_meshes(objects, config):
    """The asset meshes: a LOD shares its asset's texture and a collision mesh has none to rewrite."""
    return [obj for obj in objects if obj.type == "MESH" and role(obj, config) == "asset"]


def _meshes(objects, config):
    """One asset object per mesh: linked duplicates share their UVs."""
    return list({obj.data: obj for obj in asset_meshes(objects, config)}.values())


class ASSET_VALIDATOR_OT_set_texel_density(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.set_texel_density"
    bl_label = "Set Texel Density"
    bl_description = (
        "Scale every UV island of the selected meshes to one texel density (px/m at uv.texture_size), "
        "then pack them without rescaling. Rearranges UV0: run it before baking or texturing"
    )
    bl_options = {"REGISTER", "UNDO"}

    density: bpy.props.FloatProperty(name="Density (px/m)", description="Texel density to set, 0 = the profile's", min=0.0)
    from_active: bpy.props.BoolProperty(
        name="Copy from Active", description="Give the other selected meshes the active object's texel density",
    )

    def execute(self, context):
        config = load_config()
        cfg = config.get("uv", {})
        density = self.density or cfg.get("texel_density", 0)
        targets = _meshes(context.selected_objects, config)
        active = context.active_object
        if self.from_active:
            if active is None or active.type != "MESH" or not active.data.uv_layers:
                self.report({"ERROR"}, "Copy from Active needs an active mesh with UVs")
                return {"CANCELLED"}
            density = median_density(uv_stats(active, active.data.uv_layers[0]), cfg.get("texture_size", 2048))
            targets = [obj for obj in targets if obj.data is not active.data]
        if not targets:
            self.report({"ERROR"}, f"Select at least one asset mesh first ({SKIPPED_NOTE})")
            return {"CANCELLED"}
        if not density or math.isnan(density):
            self.report({"ERROR"}, "No texel density to set: give one, or set uv.texel_density in the profile")
            return {"CANCELLED"}

        lines = [f"'{obj.name}': {set_texel_density(obj, density, config)}" for obj in targets]
        print("\n".join(lines))
        clear_results()  # the UVs changed under the old results
        redraw_view3d(context)
        self.report({"INFO"}, lines[0] if len(lines) == 1 else "; ".join(lines))
        return {"FINISHED"}


class ASSET_VALIDATOR_OT_auto_unwrap(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.auto_unwrap"
    bl_label = "Auto Unwrap"
    bl_description = (
        "Hard surface unwrap of UV0: seams on sharp edges (or by angle if none are marked), material borders "
        "and open borders, then islands that stretch too much are cut and unwrapped again, and packed. "
        "Uses Minimum Stretch and the 'uv_importance' vertex group where Blender has them (4.3+). Replaces UV0"
    )
    bl_options = {"REGISTER", "UNDO"}

    straighten: bpy.props.BoolProperty(
        name="Straighten Quad Islands", description="Follow Active Quads on islands made only of quads",
    )

    def execute(self, context):
        config = load_config()
        objects = _meshes(context.selected_objects, config)
        if not objects:
            self.report({"ERROR"}, f"Select at least one asset mesh first ({SKIPPED_NOTE})")
            return {"CANCELLED"}
        lines = [f"'{obj.name}': {auto_unwrap(obj, config, self.straighten)}" for obj in objects]
        print("\n".join(lines))
        clear_results()
        redraw_view3d(context)
        self.report({"INFO"}, lines[0] if len(lines) == 1 else "; ".join(lines))
        return {"FINISHED"}
