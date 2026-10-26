from typing import Optional

import bpy
import bmesh


def fix_degenerate_faces(obj: bpy.types.Object, config: dict) -> Optional[str]:
    """Fixer for check_degenerate_faces: merges duplicate vertices, dissolves
    zero-length edges, then deletes any face still under the check's area epsilon."""
    cfg = config.get("optimization", {})
    area_epsilon = config.get("geometry", {}).get("degenerate_face_area_epsilon", 1e-10)
    mesh = obj.data
    before = len(mesh.polygons)

    bm = bmesh.new()
    bm.from_mesh(mesh)

    if cfg.get("merge_by_distance", True):
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=cfg.get("merge_distance", 0.0001))

    if cfg.get("fix_degenerate_faces", True):
        bmesh.ops.dissolve_degenerate(bm, dist=cfg.get("degenerate_merge_distance", 0.0001), edges=bm.edges)
        # Collinear faces with long edges survive dissolve_degenerate but still fail the check
        leftovers = [face for face in bm.faces if face.calc_area() <= area_epsilon]
        if leftovers:
            bmesh.ops.delete(bm, geom=leftovers, context="FACES")

    bm.to_mesh(mesh)
    mesh.update()
    bm.free()

    removed = before - len(mesh.polygons)
    if not removed:
        return None
    return f"removed {removed} degenerate face(s)"
