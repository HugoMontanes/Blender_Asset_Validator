from typing import List, Set, Tuple

import bpy
import bmesh

from ..core.registry import register_check
from ..core.result import CheckResult, Severity


@register_check
def check_polycount(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    budget = config.get("geometry", {}).get("max_triangles", 50000)

    for obj in objects:
        mesh = obj.data
        tri_count = 0
        for poly in mesh.polygons:
            n = len(poly.vertices)
            tri_count += n - 2  # fan triangulation: n-2 tris per n-gon

        if tri_count > budget:
            results.append(CheckResult(
                severity=Severity.ERROR,
                message=f"'{obj.name}' has {tri_count:,} triangles (budget: {budget:,})",
                object_name=obj.name,
                fix_hint=f"Reduce geometry. Target: ≤{budget:,} triangles",
                check_name="polycount",
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


def _detect_uv_overlap(bm: bmesh.types.BMesh, uv_layer) -> bool:
    """
    Grid-based UV overlap detection.
    Discretises each triangle into cells and flags any cell hit by two
    non-adjacent triangles. Resolution = 512×512, acceptable for game assets.
    """
    GRID = 512
    cell_owner: dict[Tuple[int, int], int] = {}

    for face_idx, face in enumerate(bm.faces):
        loops = list(face.loops)
        if len(loops) < 3:
            continue

        uvs = [loop[uv_layer].uv for loop in loops]
        xs = [u.x for u in uvs]
        ys = [u.y for u in uvs]

        x0 = max(0, int(min(xs) * GRID))
        x1 = min(GRID - 1, int(max(xs) * GRID))
        y0 = max(0, int(min(ys) * GRID))
        y1 = min(GRID - 1, int(max(ys) * GRID))

        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                cell = (gx, gy)
                prev = cell_owner.get(cell)
                if prev is None:
                    cell_owner[cell] = face_idx
                elif prev != face_idx:
                    return True

    return False
