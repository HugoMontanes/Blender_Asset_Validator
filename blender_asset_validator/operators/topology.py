import bpy

from . import ObjectModeOnly
from ..core.engine import load_config
from ..core.state import clear_results
from ..operations.topology import clean_topology, retopologize
from ..ui.redraw import redraw_view3d


def _selected_meshes(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


class ASSET_VALIDATOR_OT_clean_topology(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.clean_topology"
    bl_label = "Clean Topology"
    bl_description = (
        "Tris to quads, dissolve flat edge loops and relax the edge flow along the surface. "
        "Keeps shape, UVs, seams, sharp edges and materials. Works on LODs too"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        config = load_config()
        objects = _selected_meshes(context)
        if not objects:
            self.report({"ERROR"}, "Select at least one mesh object first")
            return {"CANCELLED"}

        cleaned, lines = set(), []
        for obj in objects:
            if obj.data in cleaned:
                continue  # linked duplicates share the mesh — clean it once
            cleaned.add(obj.data)
            lines.append(f"'{obj.name}': {clean_topology(obj, config)}")
        print("\n".join(lines))

        clear_results()  # the meshes changed under the old results
        redraw_view3d(context)
        self.report({"INFO"}, lines[0] if len(lines) == 1 else f"Cleaned {len(lines)} meshes — {'; '.join(lines)}")
        return {"FINISHED"}


class ASSET_VALIDATOR_OT_retopologize(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.retopologize"
    bl_label = "Retopologize"
    bl_description = (
        "Build a new all-quads '<name>_Retopo' object whose edge flow follows the curvature (QuadriFlow), "
        "with materials, UVs and normals resampled from the original. The original is hidden"
    )
    bl_options = {"REGISTER", "UNDO"}

    ratio: bpy.props.FloatProperty(
        name="Triangle Ratio", description="Target triangle count as a fraction of the original",
        default=0.5, min=0.01, max=2.0,
    )
    use_symmetry: bpy.props.BoolProperty(name="Symmetry", description="Mirror the result on X", default=False)

    def execute(self, context):
        merge_distance = load_config().get("optimization", {}).get("merge_distance", 0.0001)
        objects = _selected_meshes(context)
        if not objects:
            self.report({"ERROR"}, "Select at least one mesh object first")
            return {"CANCELLED"}

        created, failed = [], []
        for obj in objects:
            try:
                created.append(retopologize(context, obj, self.ratio, self.use_symmetry, merge_distance))
            except RuntimeError as e:
                failed.append(f"'{obj.name}': {str(e).strip().splitlines()[-1]}")
                continue
            obj.hide_set(True)

        for obj in objects:
            obj.select_set(False)
        for new in created:
            new.select_set(True)
        if created:
            context.view_layer.objects.active = created[0]

        clear_results()
        redraw_view3d(context)
        if failed:
            self.report({"WARNING"}, f"Retopologized {len(created)}, failed {len(failed)} — " + "; ".join(failed))
        else:
            self.report({"INFO"}, f"Created {len(created)} retopologized object(s)")
        return {"FINISHED"} if created else {"CANCELLED"}
