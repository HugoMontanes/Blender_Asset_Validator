"""Per-face heatmaps: a temporary color attribute shown with Solid shading >
Attribute. Blue is fine, red is bad, gray means the metric doesn't apply to
that face. Export strips the attribute so it never reaches the engine."""
import math

import bpy
import numpy as np

from ..core.mesh_utils import read_array
from .cleanup import quad_warps
from .uvs import median_density, uv_stats

HEAT = "AV_heat"
_RAMP = np.array([[0.0, 0.2, 1.0], [0.0, 0.9, 0.3], [1.0, 0.9, 0.0], [1.0, 0.1, 0.0]])  # blue, green, yellow, red
_GRAY = (0.5, 0.5, 0.5)


def _warp(obj: bpy.types.Object, config: dict) -> np.ndarray:
    """Quads by how bent they are: past the middle of the ramp means over the check's limit, red is twice it."""
    mesh = obj.data
    limit = math.radians(config.get("topology", {}).get("max_quad_warp", 10.0))
    values = np.full(len(mesh.polygons), np.nan)
    quads, warp = quad_warps(mesh)
    values[quads] = warp / (2 * limit)
    return values


def _triangle_quality(obj: bpy.types.Object, config: dict) -> np.ndarray:
    """Triangles by how thin they are, with check_topology's quality (1 = equilateral): past the
    middle of the ramp means under its min_triangle_quality, red is half of it."""
    mesh = obj.data
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


def _texel_density(obj: bpy.types.Object, config: dict) -> np.ndarray:
    """Faces by how far their texel density is from the target (or, with none, from the object's
    median), too dense or too sparse alike: past the middle of the ramp means over texel_tolerance."""
    if not obj.data.uv_layers:
        return np.full(len(obj.data.polygons), np.nan)
    cfg = config.get("uv", {})
    size = cfg.get("texture_size", 2048)
    stats = uv_stats(obj, obj.data.uv_layers[0])
    target = cfg.get("texel_density", 0) or median_density(stats, size)
    if math.isnan(target):  # no target and every island under a pixel: nothing to compare against
        return np.full(len(obj.data.polygons), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        density = np.sqrt(stats["face_uv_area"] / stats["face_area"]) * size
        values = np.abs(np.log2(density / target)) / (2 * math.log2(1 + cfg.get("texel_tolerance", 0.2)))
    values[~np.isfinite(values) & (stats["face_area"] > 0)] = 1.0  # collapsed UVs
    values[~(stats["face_area"] > 0)] = np.nan
    return values


def _uv_stretch(obj: bpy.types.Object, config: dict) -> np.ndarray:
    """Faces by UV stretch, area or angle, whichever is worse: past the middle of the ramp means over the check's limit."""
    if not obj.data.uv_layers:
        return np.full(len(obj.data.polygons), np.nan)
    cfg = config.get("uv", {})
    stats = uv_stats(obj, obj.data.uv_layers[0])
    return np.maximum(stats["face_area_stretch"] / cfg.get("max_area_stretch", 0.3),
                      stats["face_angle_stretch"] / cfg.get("max_angle_stretch", 10.0)) / 2


# id: (label, description, per-face values in 0..1 or NaN)
METRICS = {
    "WARP": ("Quad Warp", "Quads bent across their diagonal: the engine and the baker may split them differently", _warp),
    "TRI_QUALITY": ("Triangle Quality", "Thin, sliver triangles: shading artifacts and wasted GPU work", _triangle_quality),
    "TEXEL_DENSITY": ("Texel Density", "Faces whose texture resolution is off the target, too dense or too blurry", _texel_density),
    "UV_STRETCH": ("UV Stretch", "Faces whose UVs distort the texture (area or angles)", _uv_stretch),
}


def show_heatmap(obj: bpy.types.Object, metric: str, config: dict) -> None:
    mesh = obj.data
    values = METRICS[metric][2](obj, config)
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
