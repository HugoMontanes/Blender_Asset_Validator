import bpy

from . import ObjectModeOnly
from ..core.engine import load_config
from ..core.mesh_utils import repair_invalid
from ..core.roles import bake_base, highs_of
from ..operations.bake import bake_normals, make_high
from ..ui.redraw import redraw_view3d
from .uvs import asset_meshes


class ASSET_VALIDATOR_OT_bake_normals(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.bake_normals"
    bl_label = "Bake Normals"
    bl_description = (
        "Bake a tangent-space normal map from each selected asset's _high meshes (Chair_high, Chair_high_bolts...) "
        "into UV0 with Cycles: cage and ray distance measured from the meshes, the Engine's green channel, saved as "
        "<name>_N.png in bake.path. Adds a Triangulate modifier first, so the bake and the export share their triangles"
    )
    bl_options = {"REGISTER", "UNDO"}  # the Triangulate modifier

    def execute(self, context):
        config = load_config()
        bake_path = config.get("bake", {}).get("path", "//bakes/")
        if bake_path.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, f"Save the .blend first — bake path '{bake_path}' is relative to it")
            return {"CANCELLED"}
        suffix = config.get("bake", {}).get("high_suffix", "_high")
        lows = [obj for obj in asset_meshes(context.selected_objects, config) if obj.data.polygons]
        if not lows:
            self.report({"ERROR"}, f"Select the low-poly asset meshes that the {suffix} meshes bake onto")
            return {"CANCELLED"}

        lines, baked = [], {}  # base name -> the low baked into <base>_N
        for low in lows:
            highs, base = highs_of(low, config), bake_base(low, config)
            if not highs:
                lines.append(f"'{low.name}': no {suffix} mesh to bake from")
                continue
            if base in baked:  # Chair and Chair_low: both would bake into Chair_N
                lines.append(f"'{low.name}': not baked, '{baked[base]}' already baked into {base}_N. Rename one of them")
                continue
            try:
                lines.append(f"'{low.name}': {bake_normals(low, highs, config)}")
                baked[base] = low.name
            except ValueError as e:
                lines.append(f"'{low.name}': not baked, {e}")
        print("\n".join(lines))
        redraw_view3d(context)
        self.report({"INFO"} if baked else {"ERROR"}, lines[0] if len(lines) == 1 else "; ".join(lines))
        return {"FINISHED"} if baked else {"CANCELLED"}


class ASSET_VALIDATOR_OT_make_high(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.make_high"
    bl_label = "Make SubD High"
    bl_description = (
        "Make each selected asset's _high to bake from: a hidden copy with the sharp edges creased and a "
        "Subdivision modifier. The rounding follows the size of the faces next to each edge"
    )
    bl_options = {"REGISTER", "UNDO"}

    crease: bpy.props.FloatProperty(
        name="Crease", description="On the sharp edges: 1 keeps them hard, less rounds them", default=0.9, min=0.0, max=1.0,
    )
    levels: bpy.props.IntProperty(name="Levels", default=2, min=1, max=6)

    def execute(self, context):
        config = load_config()
        lows = [obj for obj in asset_meshes(context.selected_objects, config) if obj.data.polygons]
        if not lows:
            self.report({"ERROR"}, "Select the low-poly asset meshes to make a high of")
            return {"CANCELLED"}
        repair_invalid(lows, self)
        before = len(bpy.data.objects)
        lines = [f"'{low.name}': {make_high(low, config, self.crease, self.levels)}" for low in lows]
        print("\n".join(lines))
        redraw_view3d(context)
        made = len(bpy.data.objects) > before
        self.report({"INFO"} if made else {"ERROR"}, "; ".join(lines))
        return {"FINISHED"} if made else {"CANCELLED"}  # no undo step for nothing
