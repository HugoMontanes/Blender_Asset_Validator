import os

import bpy

from . import ObjectModeOnly
from ..core.engine import get_validation_objects, load_config, validate_and_store
from ..core.result import Severity
from ..operations.lod import lods_of


class ASSET_VALIDATOR_OT_export_fbx(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.export_fbx"
    bl_label = "Export FBX"
    bl_description = "Validate then export mesh objects as FBX files (blocked if errors exist)"

    def execute(self, context):
        config = load_config()
        export_cfg = config.get("export", {})
        # Selected LODs ride along with their source (with_lods), never as assets of their own
        validation_objects = [o for o in get_validation_objects(config) if not o.get("asset_validator_lod", False)]

        if not validation_objects:
            self.report({"ERROR"}, "Export blocked: no mesh objects are available for export")
            return {"CANCELLED"}

        export_path = export_cfg.get("path", "//exports/")
        if export_path.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, f"Save the .blend first — export path '{export_path}' is relative to it")
            return {"CANCELLED"}

        # Gate everything that will be written, LOD meshes included
        results = validate_and_store(config, objects=[o for obj in validation_objects for o in _with_lods(obj, config)])

        errors = [r for r in results if r.severity == Severity.ERROR]
        if errors:
            self.report({"ERROR"}, f"Export blocked - {len(errors)} error(s) must be fixed first")
            return {"CANCELLED"}

        export_dir = bpy.path.abspath(export_path)
        os.makedirs(export_dir, exist_ok=True)

        previous_selection = list(context.selected_objects)
        previous_active = context.view_layer.objects.active
        try:
            exported_paths = _export_fbx_files(context, config, validation_objects, export_dir)
        finally:
            _restore_selection(context, previous_selection, previous_active)

        if len(exported_paths) == 1:
            self.report({"INFO"}, f"Exported -> {exported_paths[0]}")
        else:
            self.report({"INFO"}, f"Exported {len(exported_paths)} FBX files to {export_dir}")

        return {"FINISHED"}


def _with_lods(obj, config):
    return [obj] if config.get("lod", {}).get("export_target", "none") == "none" else [obj, *lods_of(obj)]


def _export_fbx_files(context, config, validation_objects, export_dir):
    export_cfg = config.get("export", {})
    export_target = config.get("lod", {}).get("export_target", "none")

    if not export_cfg.get("individual_files", True):
        objects = [o for obj in validation_objects for o in _with_lods(obj, config)]
        name = _get_combined_export_name(context, export_cfg, validation_objects)
        return [_export_objects(context, export_cfg, objects, name, export_dir)]

    if export_target == "unity_godot":
        # One fbx per LOD level — the engine's LOD group is assembled after import.
        return [
            _export_objects(context, export_cfg, [lod_obj], lod_obj.name, export_dir)
            for obj in validation_objects
            for lod_obj in _with_lods(obj, config)
        ]

    # "unreal": base + its _LODn siblings in ONE fbx — Unreal auto-detects LODs
    # from that naming convention. "none": _with_lods() is just the object.
    return [
        _export_objects(context, export_cfg, _with_lods(obj, config), obj.name, export_dir)
        for obj in validation_objects
    ]


def _export_objects(context, export_cfg, objects, name, export_dir):
    _select_only_objects(context, objects)
    fbx_path = os.path.join(export_dir, f"{_sanitize_export_name(name)}.fbx")
    bpy.ops.export_scene.fbx(filepath=fbx_path, **_build_export_kwargs(export_cfg))
    return fbx_path


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
        "use_armature_deform_only": export_cfg.get("use_armature_deform_only", False),
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
            return collection.name

    active_object = context.active_object
    if active_object in validation_objects:
        return active_object.name

    return validation_objects[0].name


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
