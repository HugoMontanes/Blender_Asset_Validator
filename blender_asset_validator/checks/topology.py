import math
from typing import List

import bmesh
import bpy

from ..core.registry import register_check
from ..core.result import CheckResult, Severity

_QUAD_DOMINANT = 0.5  # below this share of quads, poles are meaningless (every triangulated vert is one)


@register_check
def check_topology(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    """Edge-flow rules for curved surfaces: no 6+ edge poles, 3/5 poles kept out
    of smoothly curved areas (they pinch shading there), no sliver triangles."""
    results = []
    cfg = config.get("topology", {})
    if not cfg.get("check_topology", True):
        return results

    max_valence = cfg.get("max_pole_valence", 5)
    curve_angle = math.radians(cfg.get("pole_curvature_angle", 10.0))
    min_quality = cfg.get("min_triangle_quality", 0.1)
    hard_angle = math.radians(cfg.get("feature_angle", 30.0))

    for obj in objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        stats = topology_stats(bm, max_valence, curve_angle, min_quality, hard_angle)
        bm.free()

        problems = []
        if stats["high_poles"]:
            problems.append(f"{stats['high_poles']} pole(s) with >{max_valence} edges")
        if stats["curved_poles"]:
            problems.append(f"{stats['curved_poles']} pole(s) on curved areas")
        if stats["slivers"]:
            problems.append(f"{stats['slivers']} sliver triangle(s)")
        if problems:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' edge flow: " + ", ".join(problems),
                object_name=obj.name,
                fix_hint="Clean Topology (keeps UVs) or Retopologize (new quad object)",
                check_name="topology",
            ))

    return results


def topology_stats(bm, max_valence: int, curve_angle: float, min_quality: float, hard_angle: float) -> dict:
    quads = sum(1 for f in bm.faces if len(f.verts) == 4)
    high_poles = curved_poles = 0
    if bm.faces and quads / len(bm.faces) >= _QUAD_DOMINANT:
        for v in bm.verts:
            if v.is_boundary or not v.link_faces:
                continue
            valence = len(v.link_edges)
            if valence > max_valence:
                high_poles += 1
            elif valence != 4:
                bend = max(e.calc_face_angle(0.0) for e in v.link_edges)
                if curve_angle < bend <= hard_angle:  # past hard_angle it's a hard corner, poles belong there
                    curved_poles += 1

    slivers = 0
    for f in bm.faces:
        if len(f.verts) != 3:
            continue
        edge_sq = sum(e.calc_length() ** 2 for e in f.edges)
        if edge_sq and 4 * math.sqrt(3) * f.calc_area() / edge_sq < min_quality:  # 1 = equilateral
            slivers += 1
    return {"high_poles": high_poles, "curved_poles": curved_poles, "slivers": slivers}
