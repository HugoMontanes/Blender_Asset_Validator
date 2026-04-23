import os

import bpy

from ..core.engine import load_config, run_validation
from ..core.result import Severity
from ..core.state import set_results
from ..report.generator import generate_report


class ASSET_VALIDATOR_OT_export_fbx(bpy.types.Operator):
    bl_idname = "asset_validator.export_fbx"
    bl_label = "Export FBX"
    bl_description = "Validate then export mesh objects as FBX files (blocked if errors exist)"

    def execute(self, context):
        config = load_config()
        export_cfg = config.get("export", {})
        validation_objects = _get_validation_objects(context, export_cfg)

        if not validation_objects:
            self.report({"ERROR"}, "Export blocked: no mesh objects are available for export")
            return {"CANCELLED"}

        results = run_validation(config, objects=validation_objects)
        set_results(results)
        generate_report(results)

        errors = [r for r in results if r.severity == Severity.ERROR]
        if errors:
            self.report({"ERROR"}, f"Export blocked - {len(errors)} error(s) must be fixed first")
            return {"CANCELLED"}

        export_dir = bpy.path.abspath(export_cfg.get("path", "//exports/"))
        os.makedirs(export_dir, exist_ok=True)

        exported_paths = _export_fbx_files(context, export_cfg, validation_objects, export_dir)

        if len(exported_paths) == 1:
            self.report({"INFO"}, f"Exported -> {exported_paths[0]}")
        else:
            self.report({"INFO"}, f"Exported {len(exported_paths)} FBX files to {export_dir}")

        return {"FINISHED"}


def _get_validation_objects(context, export_cfg):
    if export_cfg.get("use_selection", True):
        return [obj for obj in context.selected_objects if obj.type == "MESH"]

    if export_cfg.get("use_active_collection", False):
        collection = context.view_layer.active_layer_collection.collection
        return [obj for obj in collection.all_objects if obj.type == "MESH"]

    return [obj for obj in context.scene.objects if obj.type == "MESH"]


def _export_fbx_files(context, export_cfg, validation_objects, export_dir):
    if not export_cfg.get("individual_files", True):
        export_name = _get_combined_export_name(context, export_cfg, validation_objects)
        fbx_path = os.path.join(export_dir, f"{export_name}.fbx")
        bpy.ops.export_scene.fbx(filepath=fbx_path, **_build_export_kwargs(export_cfg))
        return [fbx_path]

    previous_selection = list(context.selected_objects)
    previous_active = context.view_layer.objects.active
    exported_paths = []

    try:
        for obj in validation_objects:
            _select_only_object(context, obj)

            export_name = _sanitize_export_name(obj.name)
            fbx_path = os.path.join(export_dir, f"{export_name}.fbx")
            bpy.ops.export_scene.fbx(filepath=fbx_path, **_build_export_kwargs(export_cfg))
            exported_paths.append(fbx_path)
    finally:
        _restore_selection(context, previous_selection, previous_active)

    return exported_paths


def _build_export_kwargs(export_cfg):
    return {
        "use_selection": True,
        "use_active_collection": False,
        "global_scale": export_cfg.get("global_scale", 1.0),
        "apply_unit_scale": export_cfg.get("apply_unit_scale", True),
        "apply_scale_options": export_cfg.get("apply_scale_options", "FBX_SCALE_NONE"),
        "bake_space_transform": export_cfg.get("bake_space_transform", False),
        "axis_forward": export_cfg.get("axis_forward", "-Z"),
        "axis_up": export_cfg.get("axis_up", "Y"),
        "use_mesh_modifiers": export_cfg.get("use_mesh_modifiers", True),
        "mesh_smooth_type": export_cfg.get("mesh_smooth_type", "OFF"),
        "use_tspace": export_cfg.get("use_tspace", False),
        "add_leaf_bones": export_cfg.get("add_leaf_bones", False),
        "primary_bone_axis": export_cfg.get("primary_bone_axis", "Y"),
        "secondary_bone_axis": export_cfg.get("secondary_bone_axis", "X"),
        "armature_nodetype": export_cfg.get("armature_nodetype", "NULL"),
        "path_mode": export_cfg.get("path_mode", "AUTO"),
    }


def _get_combined_export_name(context, export_cfg, validation_objects):
    if export_cfg.get("use_active_collection", False):
        collection = context.view_layer.active_layer_collection.collection
        if collection:
            return _sanitize_export_name(collection.name)

    active_object = context.active_object
    if active_object and active_object.type == "MESH" and active_object in validation_objects:
        return _sanitize_export_name(active_object.name)

    if validation_objects:
        return _sanitize_export_name(validation_objects[0].name)

    return "untitled"


def _select_only_object(context, obj):
    for selected_obj in context.selected_objects:
        selected_obj.select_set(False)

    obj.select_set(True)
    context.view_layer.objects.active = obj


def _restore_selection(context, previous_selection, previous_active):
    for selected_obj in context.selected_objects:
        selected_obj.select_set(False)

    for selected_obj in previous_selection:
        if selected_obj.name in bpy.data.objects:
            selected_obj.select_set(True)

    if previous_active and previous_active.name in bpy.data.objects:
        context.view_layer.objects.active = previous_active


def _sanitize_export_name(name):
    invalid_chars = '<>:"/\\|?*'
    sanitized = "".join("_" if char in invalid_chars else char for char in name).strip()
    return sanitized or "untitled"
