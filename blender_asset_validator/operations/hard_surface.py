"""Hard Surface Prep: smooth by angle, Auto Unwrap and texel density, then the mid-poly modifiers."""
import math

import bpy
import numpy as np

from ..core.mesh_utils import read_array
from .uvs import auto_unwrap_steps, finish, set_texel_density

_BEVEL_WIDTH = 0.005  # of the mesh's largest local dimension; the modifier stays live to tune it
# Each edge's chamfer at most this much of the shortest edge at its ends (its bevel weight scales the
# width): on the Makarov, as few crossing faces as Blender's clamp, with chamfers 2-40x as wide
_EDGE_CLAMP = 0.25


def prep_mesh(obj: bpy.types.Object, config: dict, angle: float, bevel: bool) -> str:
    """Once per mesh; with `bevel`, the sharp edges become bevel weight instead."""
    return finish(prep_mesh_steps(obj, config, angle, bevel))


def prep_mesh_steps(obj: bpy.types.Object, config: dict, angle: float, bevel: bool):
    """prep_mesh() a step at a time, like auto_unwrap_steps."""
    yield "marking sharp edges"
    sharp = _sharp_edges(obj.data) | _bent_edges(obj.data, angle)
    obj.data.shade_smooth()
    _set_sharp_edges(obj.data, sharp)
    # On a mesh with no sharp edge Auto Unwrap seams by topology.feature_angle: make it this angle
    unwrap_config = {**config, "topology": {**config.get("topology", {}), "feature_angle": math.degrees(angle)}}
    notes = [f"{sharp.sum()} sharp edge(s)", (yield from auto_unwrap_steps(obj, unwrap_config))]  # seams on the sharp edges
    target = config.get("uv", {}).get("texel_density", 0)
    if target:
        yield "setting the texel density"
        notes.append(set_texel_density(obj, target, config))
    if bevel and sharp.any():
        _sharp_to_bevel_weight(obj.data, sharp)
    return ", ".join(notes)


def _sharp_edges(mesh: bpy.types.Mesh) -> np.ndarray:
    attribute = mesh.attributes.get("sharp_edge")
    return read_array(attribute.data, "value", dtype=bool) if attribute else np.zeros(len(mesh.edges), bool)


def _set_sharp_edges(mesh: bpy.types.Mesh, sharp: np.ndarray) -> None:
    attribute = mesh.attributes.get("sharp_edge") or mesh.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    attribute.data.foreach_set("value", sharp)


def _bent_edges(mesh: bpy.types.Mesh, angle: float) -> np.ndarray:
    """Edges whose two faces meet at more than `angle`. Not shade_smooth_by_angle: on a mesh with
    custom normals it measures those (on the Makarov it marked 279 flat edges and skipped bent ones)."""
    corner_edge = read_array(mesh.loops, "edge_index", dtype=np.int64)
    corner_face = np.repeat(np.arange(len(mesh.polygons)), read_array(mesh.polygons, "loop_total", dtype=np.int64))
    faces = np.bincount(corner_edge, minlength=len(mesh.edges))
    two_faced = np.flatnonzero(faces[corner_edge] == 2)
    two_faced = two_faced[np.argsort(corner_edge[two_faced], kind="stable")]
    normals = read_array(mesh.polygons, "normal", 3)
    a, b = corner_face[two_faced[0::2]], corner_face[two_faced[1::2]]
    bent = faces > 2  # like Blender's: an edge with 3+ faces is sharp
    bent[corner_edge[two_faced[0::2]]] = (normals[a] * normals[b]).sum(axis=1) < math.cos(angle)
    return bent


def _bevel_width(mesh: bpy.types.Mesh) -> float:
    co = read_array(mesh.vertices, "co", 3)
    return _BEVEL_WIDTH * float(np.ptp(co, axis=0).max()) if len(co) else 0.0


def _sharp_to_bevel_weight(mesh: bpy.types.Mesh, sharp: np.ndarray) -> None:
    """The Bevel modifier copies the sharp flag onto the borders of the chamfer (hard
    edges, a faceted bevel), so the edges it rounds stop being sharp."""
    co, ends = read_array(mesh.vertices, "co", 3), read_array(mesh.edges, "vertices", 2, np.int64)
    length = np.linalg.norm(co[ends[:, 0]] - co[ends[:, 1]], axis=1)
    shortest = np.full(len(co), np.inf)
    np.minimum.at(shortest, ends.ravel(), np.repeat(length, 2))
    room = np.clip(_EDGE_CLAMP * shortest[ends].min(axis=1) / max(_bevel_width(mesh), 1e-12), 0.0, 1.0)
    weight = mesh.attributes.get("bevel_weight_edge") or mesh.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
    weight.data.foreach_set("value", np.maximum(read_array(weight.data, "value"), sharp * room).astype(np.float32))
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
        modifier.width = _bevel_width(obj.data)  # the width the bevel weights were clamped for
        modifier.use_clamp_overlap = False  # global: one short edge shrank every Makarov chamfer to 0-55 %
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
