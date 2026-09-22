import os

import bpy

from ..core.engine import load_config, validate_and_store
from ..core.result import Severity


class ASSET_VALIDATOR_OT_export_fbx(bpy.types.Operator):
    bl_idname = "asset_validator.export_fbx"
    bl_label = "Export FBX"
    bl_description = "Validate then export mesh objects as FBX files (blocked if errors exist)"

    def execute(self, context):
        config = load_config()
        export_cfg = config.get("export", {})
        lod_cfg = config.get("lod", {})
        validation_objects = _get_validation_objects(context, export_cfg)

        if not validation_objects:
            self.report({"ERROR"}, "Export blocked: no mesh objects are available for export")
            return {"CANCELLED"}

        results = validate_and_store(config, objects=validation_objects)

        errors = [r for r in results if r.severity == Severity.ERROR]
        if errors:
            self.report({"ERROR"}, f"Export blocked - {len(errors)} error(s) must be fixed first")
            return {"CANCELLED"}

        export_dir = bpy.path.abspath(export_cfg.get("path", "//exports/"))
        os.makedirs(export_dir, exist_ok=True)

        exported_paths = _export_fbx_files(context, export_cfg, lod_cfg, validation_objects, export_dir)

        if len(exported_paths) == 1:
            self.report({"INFO"}, f"Exported -> {exported_paths[0]}")
        else:
            self.report({"INFO"}, f"Exported {len(exported_paths)} FBX files to {export_dir}")

        return {"FINISHED"}


def _get_validation_objects(context, export_cfg):
    if export_cfg.get("use_selection", True):
        objects = [obj for obj in context.selected_objects if obj.type == "MESH"]
    elif export_cfg.get("use_active_collection", False):
        collection = context.view_layer.active_layer_collection.collection
        objects = [obj for obj in collection.all_objects if obj.type == "MESH"]
    else:
        objects = [obj for obj in context.scene.objects if obj.type == "MESH"]

    # LOD copies are validated/exported through their source, not standalone
    return [obj for obj in objects if not obj.get("asset_validator_lod", False)]


def _export_fbx_files(context, export_cfg, lod_cfg, validation_objects, export_dir):
    if not export_cfg.get("individual_files", True):
        export_name = _get_combined_export_name(context, export_cfg, validation_objects)
        fbx_path = os.path.join(export_dir, f"{export_name}.fbx")
        bpy.ops.export_scene.fbx(filepath=fbx_path, **_build_export_kwargs(export_cfg))
        return [fbx_path]

    export_target = lod_cfg.get("export_target", "none")
    previous_selection = list(context.selected_objects)
    previous_active = context.view_layer.objects.active
    exported_paths = []

    try:
        for obj in validation_objects:
            if export_target == "unreal":
                exported_paths.append(_export_unreal_lod_group(context, export_cfg, obj, export_dir))
            elif export_target == "unity_godot":
                exported_paths.extend(_export_unity_godot_lod_levels(context, export_cfg, obj, export_dir))
            else:
                exported_paths.append(_export_single_object(context, export_cfg, obj, export_dir))
    finally:
        _restore_selection(context, previous_selection, previous_active)

    return exported_paths


def _get_lod_siblings(obj):
    """LOD copies generated from `obj` by operations/lod.py, ordered LOD1, LOD2, ..."""
    return sorted(
        (o for o in bpy.data.objects if o.get("asset_validator_lod_source") == obj.name),
        key=lambda o: o.name,
    )


def _export_single_object(context, export_cfg, obj, export_dir):
    _select_only_objects(context, [obj])
    export_name = _sanitize_export_name(obj.name)
    fbx_path = os.path.join(export_dir, f"{export_name}.fbx")
    bpy.ops.export_scene.fbx(filepath=fbx_path, **_build_export_kwargs(export_cfg))
    return fbx_path


def _export_unreal_lod_group(context, export_cfg, obj, export_dir):
    # Base object + its _LODn siblings in ONE fbx — Unreal auto-detects LODs
    # from that naming convention when they're sibling objects in the same file.
    _select_only_objects(context, [obj, *_get_lod_siblings(obj)])
    export_name = _sanitize_export_name(obj.name)
    fbx_path = os.path.join(export_dir, f"{export_name}.fbx")
    bpy.ops.export_scene.fbx(filepath=fbx_path, **_build_export_kwargs(export_cfg))
    return fbx_path


def _export_unity_godot_lod_levels(context, export_cfg, obj, export_dir):
    # One fbx per LOD level — the engine's LOD group is assembled after import.
    return [
        _export_single_object(context, export_cfg, lod_obj, export_dir)
        for lod_obj in [obj, *_get_lod_siblings(obj)]
    ]


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


def _select_only_objects(context, objects):
    for selected_obj in context.selected_objects:
        selected_obj.select_set(False)

    for obj in objects:
        obj.select_set(True)

    if objects:
        context.view_layer.objects.active = objects[0]


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
