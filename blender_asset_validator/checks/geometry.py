from functools import partial
from typing import List

import bpy
import numpy as np

from ..core.mesh_utils import evaluated_triangle_count, read_array
from ..core.registry import register_check
from ..core.result import CheckResult, Severity
from ..operations.cleanup import fix_degenerate_faces as _fix_degenerate_faces
from ..operations.decimate import fix_polycount as _fix_polycount

_UV_SHRINK = 1e-4


@register_check
def check_polycount(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    budget = config.get("geometry", {}).get("max_triangles", 50000)

    for obj in objects:
        tri_count = evaluated_triangle_count(obj)  # modifiers applied — what actually exports

        if tri_count > budget:
            results.append(CheckResult(
                severity=Severity.ERROR,
                message=f"'{obj.name}' has {tri_count:,} triangles with modifiers applied (budget: {budget:,})",
                object_name=obj.name,
                fix_hint=f"Reduce geometry. Target: ≤{budget:,} triangles",
                check_name="polycount",
                fix=partial(_fix_polycount, obj, config),
            ))

    return results


@register_check
def check_ngons(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    if config.get("geometry", {}).get("allow_ngons", False):
        return results

    for obj in objects:
        ngon_count = sum(1 for p in obj.data.polygons if len(p.vertices) > 4)
        if ngon_count:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' has {ngon_count} ngon(s) (faces with 5+ verts)",
                object_name=obj.name,
                fix_hint="Edit Mode > Face Select > Select All By Trait > Faces by Sides (>4)",
                check_name="ngons",
            ))

    return results


@register_check
def check_uvs(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    if not config.get("geometry", {}).get("check_uvs", True):
        return results

    for obj in objects:
        mesh = obj.data

        if not mesh.uv_layers:
            results.append(CheckResult(
                severity=Severity.ERROR,
                message=f"'{obj.name}' has no UV map",
                object_name=obj.name,
                fix_hint="Edit Mode > UV > Unwrap  (U)",
                check_name="uvs",
            ))
            continue

        layer = mesh.uv_layers.active
        if layer is None:
            continue
        overlap = _uv_overlap(mesh, layer)

        if overlap:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' has overlapping UVs",
                object_name=obj.name,
                fix_hint="UV Editor > UV > Pack Islands or manually fix overlaps",
                check_name="uvs",
            ))

    return results


@register_check
def check_degenerate_faces(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    cfg = config.get("geometry", {})
    if not cfg.get("check_degenerate_faces", True):
        return results

    area_epsilon = cfg.get("degenerate_face_area_epsilon", 1e-10)

    for obj in objects:
        degenerate_faces = sum(1 for poly in obj.data.polygons if poly.area <= area_epsilon)
        if degenerate_faces:
            results.append(CheckResult(
                severity=Severity.ERROR,
                message=f"'{obj.name}' has {degenerate_faces} degenerate face(s)",
                object_name=obj.name,
                fix_hint="Delete zero-area faces or merge overlapping vertices before export",
                check_name="geometry_cleanup",
                fix=partial(_fix_degenerate_faces, obj, config),
            ))

    return results


def _uv_overlap(mesh: bpy.types.Mesh, layer) -> bool:
    """Not BVHTree.overlap: its tri-tri test treats coplanar triangles (every UV
    triangle at z=0) as never intersecting."""
    mesh.calc_loop_triangles()
    tris = read_array(layer.data, "uv", 2, np.float64)[read_array(mesh.loop_triangles, "loops", 3, np.int64)]
    tris = tris[np.isfinite(tris).all(axis=(1, 2))]  # one NaN UV would put every triangle in one grid cell: O(T²)
    center = tris.mean(axis=1, keepdims=True)
    # Shrink toward the centroid so neighbours touching along an edge/vertex don't count
    return _any_triangles_overlap(center + (tris - center) * (1.0 - _UV_SHRINK))


def _any_triangles_overlap(tris: np.ndarray) -> bool:
    """tris: (T, 3, 2). Broad phase: a grid of ~sqrt(T) cells a side over their
    bounds; only triangles sharing a cell are tested against each other."""
    if len(tris) < 2:
        return False
    cells = max(1, int(len(tris) ** 0.5))
    lo, hi = tris.min(axis=1), tris.max(axis=1)
    origin = lo.min(axis=0)
    size = (hi.max(axis=0) - origin) / cells
    size[size == 0] = 1.0

    def cell_of(points):
        return np.minimum(((points - origin) / size).astype(np.int64), cells - 1)

    first = cell_of(lo)
    span = cell_of(hi) - first + 1
    count = span[:, 0] * span[:, 1]  # cells each triangle covers
    nth = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    width = np.repeat(span[:, 0], count)
    cell = (np.repeat(first[:, 0], count) + nth % width) * cells + np.repeat(first[:, 1], count) + nth // width
    order = np.argsort(cell, kind="stable")
    cell, tri = cell[order], np.repeat(np.arange(len(tris)), count)[order]
    axes, own_min, own_max = _sat_axes(tris)
    for gap in range(1, len(cell)):
        same = np.flatnonzero(cell[:-gap] == cell[gap:])
        if not len(same):
            return False  # sorted by cell: no run of one cell is `gap` long
        a, b = tri[same], tri[same + gap]
        # Test each pair once, in the cell where their bounding boxes start overlapping
        start, end = np.maximum(lo[a], lo[b]), np.minimum(hi[a], hi[b])
        home = cell_of(start)
        keep = (start <= end).all(axis=1) & (home[:, 0] * cells + home[:, 1] == cell[same])
        a, b = a[keep], b[keep]
        apart = _separated(axes[a], own_min[a], own_max[a], tris[b])
        apart |= _separated(axes[b], own_min[b], own_max[b], tris[a])
        if not apart.all():
            return True
    return False


def _sat_axes(tris: np.ndarray) -> tuple:
    """Each triangle's edge normals (T, 3, 2) and its own extent along them (T, 3) min and max."""
    edges = np.roll(tris, -1, axis=1) - tris
    axes = np.stack([-edges[..., 1], edges[..., 0]], axis=2)
    own = np.einsum("tak,tvk->tav", axes, tris)
    return axes, own.min(axis=2), own.max(axis=2)


def _separated(axes, own_min, own_max, other) -> np.ndarray:
    """Per pair: True where one of the first triangle's edge normals separates it from `other` (N, 3, 2)."""
    proj = np.einsum("nak,nvk->nav", axes, other)
    return ((proj.max(axis=2) < own_min) | (proj.min(axis=2) > own_max)).any(axis=1)
