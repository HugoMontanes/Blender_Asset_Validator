import os
from pathlib import Path

import bpy

from ..core.engine import load_config, run_validation
from ..core.result import Severity
from ..core.state import set_results
from ..report.generator import generate_report


class ASSET_VALIDATOR_OT_export_fbx(bpy.types.Operator):
    bl_idname = "asset_validator.export_fbx"
    bl_label = "Export FBX"
    bl_description = "Validate then export selected objects as FBX (blocked if errors exist)"

    def execute(self, context):
        config = load_config()
        export_cfg = config.get("export", {})
        validation_objects = _get_validation_objects(context, export_cfg)

        if export_cfg.get("use_selection", True) and not validation_objects:
            self.report({"ERROR"}, "Export blocked: no mesh objects are selected")
            return {"CANCELLED"}

        # Always re-validate before export so stale results can't be bypassed
        results = run_validation(config, objects=validation_objects)
        set_results(results)
        generate_report(results)

        errors = [r for r in results if r.severity == Severity.ERROR]
        if errors:
            self.report({"ERROR"}, f"Export blocked — {len(errors)} error(s) must be fixed first")
            return {"CANCELLED"}

        export_dir = bpy.path.abspath(export_cfg.get("path", "//exports/"))
        os.makedirs(export_dir, exist_ok=True)

        blend_name = Path(bpy.data.filepath).stem or "untitled"
        fbx_path = os.path.join(export_dir, f"{blend_name}.fbx")

        bpy.ops.export_scene.fbx(
            filepath=fbx_path,
            use_selection=export_cfg.get("use_selection", True),
            use_active_collection=export_cfg.get("use_active_collection", False),
            global_scale=export_cfg.get("global_scale", 1.0),
            apply_unit_scale=export_cfg.get("apply_unit_scale", True),
            apply_scale_options=export_cfg.get("apply_scale_options", "FBX_SCALE_NONE"),
            bake_space_transform=export_cfg.get("bake_space_transform", False),
            axis_forward=export_cfg.get("axis_forward", "-Z"),
            axis_up=export_cfg.get("axis_up", "Y"),
            use_mesh_modifiers=export_cfg.get("use_mesh_modifiers", True),
            mesh_smooth_type=export_cfg.get("mesh_smooth_type", "OFF"),
            use_tspace=export_cfg.get("use_tspace", False),
            add_leaf_bones=export_cfg.get("add_leaf_bones", False),
            primary_bone_axis=export_cfg.get("primary_bone_axis", "Y"),
            secondary_bone_axis=export_cfg.get("secondary_bone_axis", "X"),
            armature_nodetype=export_cfg.get("armature_nodetype", "NULL"),
            path_mode=export_cfg.get("path_mode", "AUTO"),
        )

        self.report({"INFO"}, f"Exported → {fbx_path}")
        return {"FINISHED"}


def _get_validation_objects(context, export_cfg):
    if export_cfg.get("use_selection", True):
        return [obj for obj in context.selected_objects if obj.type == "MESH"]

    if export_cfg.get("use_active_collection", False):
        collection = context.view_layer.active_layer_collection.collection
        return [obj for obj in collection.all_objects if obj.type == "MESH"]

    return [obj for obj in context.scene.objects if obj.type == "MESH"]
