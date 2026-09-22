from typing import Optional

import bpy
import bmesh


def fix_degenerate_faces(obj: bpy.types.Object, config: dict) -> Optional[str]:
    """Fixer for check_degenerate_faces: merges duplicate vertices, then
    dissolves the zero-area faces that leaves behind."""
    cfg = config.get("optimization", {})
    mesh = obj.data
    before = len(mesh.polygons)

    bm = bmesh.new()
    bm.from_mesh(mesh)

    if cfg.get("merge_by_distance", True):
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=cfg.get("merge_distance", 0.0001))

    if cfg.get("fix_degenerate_faces", True):
        bmesh.ops.dissolve_degenerate(bm, dist=cfg.get("degenerate_merge_distance", 0.0001), edges=bm.edges)

    bm.to_mesh(mesh)
    mesh.update()
    bm.free()

    removed = before - len(mesh.polygons)
    if not removed:
        return None
    return f"dissolved {removed} degenerate face(s)"
