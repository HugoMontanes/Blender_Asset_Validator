import bpy

from . import ObjectModeOnly
from ..core.engine import load_config
from ..core.roles import highs_of
from ..operations.bake import bake_normals
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

        lines, baked = [], 0
        for low in lows:
            highs = highs_of(low, config)
            if not highs:
                lines.append(f"'{low.name}': no {suffix} mesh to bake from")
                continue
            try:
                lines.append(f"'{low.name}': {bake_normals(low, highs, config)}")
                baked += 1
            except ValueError as e:
                lines.append(f"'{low.name}': not baked, {e}")
        print("\n".join(lines))
        redraw_view3d(context)
        self.report({"INFO"} if baked else {"ERROR"}, lines[0] if len(lines) == 1 else "; ".join(lines))
        return {"FINISHED"} if baked else {"CANCELLED"}
