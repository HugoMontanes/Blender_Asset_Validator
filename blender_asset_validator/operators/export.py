import os
from contextlib import ExitStack, contextmanager

import bpy
from mathutils import Matrix

from . import ObjectModeOnly
from ..core.engine import get_validation_objects, load_config, validate_and_store
from ..core.result import Severity
from ..core.roles import bake_base, collisions_of, highs_of, renamed_collision, role, sockets_of
from ..operations.bake import add_triangulate
from ..operations.heatmap import clear_heatmap
from ..operations.lod import lods_of
from .uvs import asset_meshes

_EXTENSIONS = {"fbx": ".fbx", "gltf": ".glb"}
_TARGETS = ("none", "unity", "unreal")  # lod.export_target


class ASSET_VALIDATOR_OT_export(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.export"
    bl_label = "Export"
    bl_description = (
        "Validate, then export each asset with its LODs, collisions and sockets laid out "
        "the way the Engine reads them (blocked if errors exist)"
    )
    bl_options = {"REGISTER", "UNDO"}  # heatmaps are stripped from what gets written

    def execute(self, context):
        config = load_config()
        export_cfg = config.get("export", {})
        if export_cfg.get("format", "fbx") not in _EXTENSIONS:
            self.report({"ERROR"}, f"Unknown export format '{export_cfg.get('format')}' (fbx or gltf)")
            return {"CANCELLED"}
        target = config.get("lod", {}).get("export_target", "none")
        if target not in _TARGETS:
            self.report({"ERROR"}, f"Unknown lod.export_target '{target}' ({', '.join(_TARGETS)})")
            return {"CANCELLED"}
        # Selected LODs and collisions ride along with their asset, never as assets of their own
        assets = [o for o in get_validation_objects(config) if role(o, config) == "asset"]

        if not assets:
            self.report({"ERROR"}, "Export blocked: no mesh objects are available for export")
            return {"CANCELLED"}

        export_path = export_cfg.get("path", "//exports/")
        if export_path.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, f"Save the .blend first — export path '{export_path}' is relative to it")
            return {"CANCELLED"}

        parts = {obj: _parts(obj, config) for obj in assets}
        # Gate everything that will be written, LODs and collisions included
        results = validate_and_store(config, objects=[o for p in parts.values() for o in p if o.type == "MESH"])

        errors = [r for r in results if r.severity == Severity.ERROR]
        if errors:
            self.report({"ERROR"}, f"Export blocked - {len(errors)} error(s) must be fixed first")
            return {"CANCELLED"}

        export_dir = bpy.path.abspath(export_path)
        os.makedirs(export_dir, exist_ok=True)

        try:
            exported_paths = _export_files(context, config, parts, export_dir)
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"FINISHED"}  # earlier assets may be written with their heatmaps stripped: keep the undo step

        if len(exported_paths) == 1:
            self.report({"INFO"}, f"Exported -> {exported_paths[0]}")
        else:
            self.report({"INFO"}, f"Exported {len(exported_paths)} files to {export_dir}")

        return {"FINISHED"}


def _parts(obj, config):
    """obj and everything written in its file."""
    lods = [] if config.get("lod", {}).get("export_target", "none") == "none" else lods_of(obj)
    return [obj, *lods, *collisions_of(obj, config), *sockets_of(obj, config)]


def _export_files(context, config, parts, export_dir):
    if not config.get("export", {}).get("individual_files", True):
        name = _get_combined_export_name(context, config.get("export", {}), list(parts))
        with ExitStack() as stack:
            objects = [o for obj, p in parts.items() for o in stack.enter_context(_engine_layout(context, config, obj, p))]
            return [_export_objects(config, objects, name, export_dir)]

    paths = []
    for obj, p in parts.items():
        name = obj.name  # the layout may rename obj while it's written
        with _engine_layout(context, config, obj, p) as objects:
            paths.append(_export_objects(config, objects, name, export_dir))
    return paths


@contextmanager
def _engine_layout(context, config, obj, parts):
    """The objects to write for obj, renamed and parented the way the target engine
    reads LODs; names and parents are put back afterwards.
    unity: Name_LOD0..n side by side. unreal: an empty with fbx_type "LodGroup"
    (written as an FBX LOD Group node) over Name_LOD0..n, and the UCX_ meshes
    renamed after Name_LOD0, the mesh Unreal matches them to."""
    target = config.get("lod", {}).get("export_target", "none")
    lods = [p for p in parts if p.get("asset_validator_lod", False)]
    if target == "none" or not lods:
        yield parts
        return

    name, lod0 = obj.name, f"{obj.name}_LOD0"
    # LODs keep the name they were generated with: the asset may have been renamed since, or the suffix differ
    renames = [(obj, lod0), *((lod, f"{name}_LOD{level}") for level, lod in enumerate(lods, 1))]
    if target == "unreal":
        renames += [(c, renamed_collision(c, lod0, config)) for c in parts if role(c, config) == "collision"]
    group, reparented = None, []
    with _renamed(renames):
        try:
            if target == "unreal":
                group = bpy.data.objects.new(name, None)  # obj gave the name up above
                group["fbx_type"] = "LodGroup"
                context.scene.collection.objects.link(group)
                for o in (obj, *lods):
                    reparented.append((o, o.parent, o.matrix_parent_inverse.copy(), o.matrix_basis.copy()))
                    world = o.matrix_world.copy()
                    o.parent = group
                    o.matrix_parent_inverse = Matrix.Identity(4)
                    o.matrix_basis = world
                context.view_layer.update()
            yield [*parts, group] if group else parts
        finally:
            for o, parent, inverse, basis in reversed(reparented):
                o.parent, o.matrix_parent_inverse, o.matrix_basis = parent, inverse, basis
            if group is not None:
                bpy.data.objects.remove(group)  # before the names go back: it holds obj's name


@contextmanager
def _renamed(renames):
    """Objects renamed while they're written, (object, new name) pairs; the old names are put back afterwards."""
    old_names = [(o, o.name) for o, _ in renames]
    try:
        for o, new in renames:
            old = o.name
            o.name = new
            if o.name != new:
                raise RuntimeError(f"Export needs to rename '{old}' to '{new}', but that name is taken")
        yield
    finally:
        for o, old in reversed(old_names):
            o.name = old


class ASSET_VALIDATOR_OT_export_bake_pairs(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.export_bake_pairs"
    bl_label = "Export Bake Pairs"
    bl_description = (
        "Write the selected assets to <name>_low.fbx, renamed X_low, and their _high meshes to <name>_high.fbx, "
        "named for Substance Painter's and Marmoset's match by name (bake.path). Adds a Triangulate modifier to "
        "each low first, so the baker and the engine get the same triangles"
    )
    bl_options = {"REGISTER", "UNDO"}  # the Triangulate modifiers

    def execute(self, context):
        config = load_config()
        cfg = config.get("bake", {})
        low_suffix, high_suffix, bake_path = cfg.get("low_suffix", "_low"), cfg.get("high_suffix", "_high"), cfg.get("path", "//bakes/")
        if bake_path.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, f"Save the .blend first — bake path '{bake_path}' is relative to it")
            return {"CANCELLED"}
        lows = asset_meshes(context.selected_objects, config)
        highs = list(dict.fromkeys(h for low in lows for h in highs_of(low, config)))  # Chair and Chair_low share them
        if not highs:
            self.report({"ERROR"}, f"No {high_suffix} mesh pairs with the selected assets (Chair bakes from Chair{high_suffix}...)")
            return {"CANCELLED"}

        for low in lows:
            add_triangulate(low)
        # Painter pairs Chair_low with Chair_high_bolts but not Chair_high.001: a dot can't follow the suffix
        renames = [(o, f"{bake_base(o, config)}{low_suffix}".replace(".", "_")) for o in lows]
        renames += [(o, o.name.replace(".", "_")) for o in highs]
        active = context.active_object
        name = bake_base(active if active in lows else lows[0], config)
        fbx = {**config, "export": {**config.get("export", {}), "format": "fbx"}}  # what both bakers read
        folder = bpy.path.abspath(bake_path)
        os.makedirs(folder, exist_ok=True)
        try:
            with _renamed(renames):
                paths = [_export_objects(fbx, lows, f"{name}{low_suffix}", folder),
                         _export_objects(fbx, highs, f"{name}{high_suffix}", folder)]
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"FINISHED"}  # the Triangulate modifiers stay: keep the undo step
        unpaired = [o.name for o in lows if not highs_of(o, config)]
        note = f" ({len(unpaired)} low(s) without a high: {', '.join(unpaired)})" if unpaired else ""
        self.report({"INFO"}, f"Exported {len(lows)} low and {len(highs)} high mesh(es) -> {paths[0]}, {paths[1]}{note}")
        return {"FINISHED"}


def _export_objects(config, objects, name, export_dir):
    export_cfg = config.get("export", {})
    fmt = export_cfg.get("format", "fbx")
    for obj in objects:
        if obj.type == "MESH":
            clear_heatmap(obj)
    path = os.path.join(export_dir, f"{_sanitize_export_name(name)}{_EXTENSIONS[fmt]}")
    # Written from a temporary collection, not the selection: exporters skip hidden
    # selected objects, and collisions and LODs usually are hidden
    bundle = bpy.data.collections.new("_AssetValidator_export")
    try:
        for obj in objects:
            bundle.objects.link(obj)
        if fmt == "gltf":
            bpy.ops.export_scene.gltf(
                filepath=path, collection=bundle.name, export_format="GLB",
                export_apply=export_cfg.get("use_mesh_modifiers", True),
            )
        else:
            bpy.ops.export_scene.fbx(filepath=path, collection=bundle.name, **_build_export_kwargs(export_cfg))
    finally:
        bpy.data.collections.remove(bundle)
    return path


def _build_export_kwargs(export_cfg):
    return {
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


def _sanitize_export_name(name):
    invalid_chars = '<>:"/\\|?*'
    sanitized = "".join("_" if char in invalid_chars else char for char in name).strip()
    return sanitized or "untitled"
