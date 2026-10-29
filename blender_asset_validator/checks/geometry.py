from functools import partial
from typing import List

import bpy

from ..core.mesh_utils import evaluated_triangle_count
from ..core.registry import register_check
from ..core.result import CheckResult, Severity
from ..operations.cleanup import fix_degenerate_faces as _fix_degenerate_faces
from ..operations.decimate import fix_polycount as _fix_polycount


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
