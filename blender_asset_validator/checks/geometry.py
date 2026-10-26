from collections import defaultdict
from functools import partial
from typing import List

import bpy
import bmesh
from mathutils.geometry import intersect_tri_tri_2d

from ..core.mesh_utils import evaluated_triangle_count
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

        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        uv_layer = bm.loops.layers.uv.active

        if uv_layer is None:
            bm.free()
            continue

        overlap = _detect_uv_overlap(bm, uv_layer)
        bm.free()

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


def _detect_uv_overlap(bm: bmesh.types.BMesh, uv_layer) -> bool:
    """Not BVHTree.overlap: its tri-tri test treats coplanar triangles (every UV
    triangle at z=0) as never intersecting. `bm.faces` are pre-triangulated."""
    triangles = []
    for face in bm.faces:
        uvs = [loop[uv_layer].uv for loop in face.loops]
        center = (uvs[0] + uvs[1] + uvs[2]) / 3
        # Shrink toward the centroid so neighbours touching along an edge/vertex don't count
        triangles.append([center.lerp(uv, 1.0 - _UV_SHRINK) for uv in uvs])
    return _any_triangles_overlap(triangles)


def _any_triangles_overlap(triangles) -> bool:
    if len(triangles) < 2:
        return False

    us = [p.x for tri in triangles for p in tri]
    vs = [p.y for tri in triangles for p in tri]
    min_u, min_v = min(us), min(vs)
    cells = max(1, int(len(triangles) ** 0.5))
    cell_w = (max(us) - min_u) / cells or 1.0
    cell_h = (max(vs) - min_v) / cells or 1.0

    def cell_range(lo, hi, origin, size):
        return range(min(int((lo - origin) / size), cells - 1), min(int((hi - origin) / size), cells - 1) + 1)

    grid = defaultdict(list)
    for idx, tri in enumerate(triangles):
        for cu in cell_range(min(p.x for p in tri), max(p.x for p in tri), min_u, cell_w):
            for cv in cell_range(min(p.y for p in tri), max(p.y for p in tri), min_v, cell_h):
                grid[cu, cv].append(idx)

    tested = set()
    for members in grid.values():
        for pos, a in enumerate(members):
            for b in members[pos + 1:]:
                if (a, b) in tested:
                    continue
                tested.add((a, b))
                if intersect_tri_tri_2d(*triangles[a], *triangles[b]):
                    return True
    return False
