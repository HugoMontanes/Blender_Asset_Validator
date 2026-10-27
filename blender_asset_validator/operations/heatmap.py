"""Per-face heatmaps: a temporary color attribute shown with Solid shading >
Attribute. Blue is fine, red is bad, gray means the metric doesn't apply to
that face. Export strips the attribute so it never reaches the engine."""
import math

import bpy
import numpy as np

from ..core.mesh_utils import read_array
from .cleanup import quad_warps

HEAT = "AV_heat"
_RAMP = np.array([[0.0, 0.2, 1.0], [0.0, 0.9, 0.3], [1.0, 0.9, 0.0], [1.0, 0.1, 0.0]])  # blue, green, yellow, red
_GRAY = (0.5, 0.5, 0.5)


def _warp(mesh: bpy.types.Mesh, config: dict) -> np.ndarray:
    """Quads by how bent they are: past the middle of the ramp means over the check's limit, red is twice it."""
    limit = math.radians(config.get("topology", {}).get("max_quad_warp", 10.0))
    values = np.full(len(mesh.polygons), np.nan)
    quads, warp = quad_warps(mesh)
    values[quads] = warp / (2 * limit)
    return values


def _triangle_quality(mesh: bpy.types.Mesh, config: dict) -> np.ndarray:
    """Triangles by how thin they are, with check_topology's quality (1 = equilateral): past the
    middle of the ramp means under its min_triangle_quality, red is half of it."""
    limit = config.get("topology", {}).get("min_triangle_quality", 0.1)
    values = np.full(len(mesh.polygons), np.nan)
    tris = np.flatnonzero(read_array(mesh.polygons, "loop_total", dtype=np.int64) == 3)
    starts = read_array(mesh.polygons, "loop_start", dtype=np.int64)[tris]
    corner_vert = read_array(mesh.loops, "vertex_index", dtype=np.int64)
    co = read_array(mesh.vertices, "co", 3, np.float64)
    a, b, c = (co[corner_vert[starts + k]] for k in range(3))
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    edges = ((b - a) ** 2).sum(axis=1) + ((c - b) ** 2).sum(axis=1) + ((a - c) ** 2).sum(axis=1)
    quality = np.divide(4 * math.sqrt(3) * area, edges, out=np.zeros(len(tris)), where=edges > 0)
    values[tris] = np.divide(limit, 2 * quality, out=np.ones(len(tris)), where=quality > 0)
    return values


# id: (label, description, per-face values in 0..1 or NaN)
METRICS = {
    "WARP": ("Quad Warp", "Quads bent across their diagonal: the engine and the baker may split them differently", _warp),
    "TRI_QUALITY": ("Triangle Quality", "Thin, sliver triangles: shading artifacts and wasted GPU work", _triangle_quality),
}


def show_heatmap(obj: bpy.types.Object, metric: str, config: dict) -> None:
    mesh = obj.data
    values = METRICS[metric][2](mesh, config)
    colors = np.ones((len(values), 4))
    colors[:, :3] = _GRAY
    known = ~np.isnan(values)
    colors[known, :3] = _ramp(np.clip(values[known], 0.0, 1.0))
    corner_colors = np.repeat(colors, read_array(mesh.polygons, "loop_total", dtype=np.int64), axis=0)
    clear_heatmap(obj)
    attr = mesh.color_attributes.new(HEAT, "FLOAT_COLOR", "CORNER")
    attr.data.foreach_set("color", corner_colors.astype(np.float32).ravel())
    mesh.color_attributes.active_color = attr


def clear_heatmap(obj: bpy.types.Object) -> bool:
    attr = obj.data.color_attributes.get(HEAT)
    if attr is None:
        return False
    obj.data.color_attributes.remove(attr)
    return True


def _ramp(t: np.ndarray) -> np.ndarray:
    return np.column_stack([np.interp(t, np.linspace(0.0, 1.0, len(_RAMP)), channel) for channel in _RAMP.T])
