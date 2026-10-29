"""Hard Surface Prep: smooth by angle, Auto Unwrap and texel density, then the mid-poly modifiers."""
import math

import bpy
import numpy as np

from ..core.mesh_utils import read_array
from .uvs import auto_unwrap, set_texel_density

_BEVEL_WIDTH = 0.005  # of the object's largest local dimension; the modifier stays live to tune it


def prep_mesh(obj: bpy.types.Object, config: dict, angle: float, bevel: bool) -> str:
    """Once per mesh; with `bevel`, the sharp edges become bevel weight instead."""
    with bpy.context.temp_override(selected_editable_objects=[obj], selected_objects=[obj], active_object=obj, object=obj):
        bpy.ops.object.shade_smooth_by_angle(angle=angle, keep_sharp_edges=True)
    sharp = _sharp_edges(obj.data)
    # On a mesh with no sharp edge Auto Unwrap seams by topology.feature_angle: make it this angle
    unwrap_config = {**config, "topology": {**config.get("topology", {}), "feature_angle": math.degrees(angle)}}
    notes = [f"{sharp.sum()} sharp edge(s)", auto_unwrap(obj, unwrap_config)]  # seams on the sharp edges
    target = config.get("uv", {}).get("texel_density", 0)
    if target:
        notes.append(set_texel_density(obj, target, config))
    if bevel and sharp.any():
        _sharp_to_bevel_weight(obj.data, sharp)
    return ", ".join(notes)


def _sharp_edges(mesh: bpy.types.Mesh) -> np.ndarray:
    attribute = mesh.attributes.get("sharp_edge")
    return read_array(attribute.data, "value", dtype=bool) if attribute else np.zeros(len(mesh.edges), bool)


def _sharp_to_bevel_weight(mesh: bpy.types.Mesh, sharp: np.ndarray) -> None:
    """The Bevel modifier copies the sharp flag onto the borders of the chamfer (hard
    edges, a faceted bevel), so the edges it rounds stop being sharp."""
    weight = mesh.attributes.get("bevel_weight_edge") or mesh.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
    weight.data.foreach_set("value", np.maximum(read_array(weight.data, "value"), sharp).astype(np.float32))
    mesh.attributes.remove(mesh.attributes["sharp_edge"])  # looked up again: adding an attribute can move the others


def add_modifiers(obj: bpy.types.Object, bevel_segments: int) -> list:
    """Bevel by weight (when bevel_segments > 0) and Weighted Normal, last, unless the object has them."""
    added = []
    # Shade Auto Smooth's modifier, pinned last: the marked sharp edges replace it, and after a Bevel it re-sharpens the chamfer
    auto_smooth = [m for m in obj.modifiers if m.type == "NODES" and m.node_group and m.node_group.name.startswith("Smooth by Angle")]
    for modifier in auto_smooth:
        obj.modifiers.remove(modifier)
    if auto_smooth:
        added.append("Smooth by Angle modifier removed (the edges are marked sharp)")
    if bevel_segments and not any(m.type == "BEVEL" and m.limit_method == "WEIGHT" and m.show_viewport for m in obj.modifiers):
        modifier = obj.modifiers.new("Bevel", "BEVEL")
        modifier.limit_method = "WEIGHT"
        modifier.segments = bevel_segments
        modifier.width = _BEVEL_WIDTH * float(np.ptp(np.array(obj.bound_box), axis=0).max())
        added.append(f"Bevel ({bevel_segments} segments) added")
    for modifier in obj.modifiers:
        if modifier.type == "WEIGHTED_NORMAL":
            modifier.use_pin_to_last = True  # one added by hand may sit before the Bevel
    note = add_weighted_normal(obj)
    if note:
        added.append(note)
    return added


def has_weighted_normal(obj: bpy.types.Object) -> bool:
    return any(m.type == "WEIGHTED_NORMAL" and m.show_viewport for m in obj.modifiers)  # exporters evaluate the viewport


def add_weighted_normal(obj: bpy.types.Object):
    """Fixer for check_weighted_normal: Face Area, Keep Sharp, pinned last so a later Bevel goes above it."""
    if has_weighted_normal(obj):
        return None
    modifier = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    modifier.keep_sharp = True
    modifier.use_pin_to_last = True
    return "Weighted Normal added"
