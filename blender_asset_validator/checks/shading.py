from functools import partial
from typing import List

import bpy
import numpy as np

from ..core.mesh_utils import bake_mesh, read_array, select_in_edit_mode
from ..core.registry import register_check
from ..core.result import CheckResult, Severity
from ..operations.hard_surface import add_weighted_normal, has_weighted_normal

_SAME = 1e-4  # normals/UVs closer than this share a GPU vertex


@register_check
def check_shading(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    """The GPU duplicates a vertex wherever its normal, UV or material changes, so
    the real cost is that count, not the triangles. A hard edge on a UV seam is
    free (the seam split it already); off a seam it costs vertices and the normal
    map has to fight the shading split (Polycount: hard edges go on UV seams)."""
    results = []
    if not config.get("geometry", {}).get("check_shading", True):
        return results

    for obj in objects:
        mesh = bake_mesh(obj)  # modifiers applied: Smooth by Angle decides the hard edges
        try:
            stats = shading_stats(mesh)
            same_topology = len(mesh.edges) == len(obj.data.edges)
        finally:
            bpy.data.meshes.remove(mesh)

        hard = stats["hard_off_seam"]
        if hard:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' has {len(hard)} hard edge(s) not on a UV seam",
                object_name=obj.name,
                fix_hint="Mark them as seams and re-unwrap, or soften them (Edge > Mark Smooth)",
                check_name="shading",
                select=partial(select_in_edit_mode, obj, "EDGE", hard) if same_topology else None,
            ))
        results.append(CheckResult(
            severity=Severity.INFO,
            message=(
                f"'{obj.name}' exports {stats['gpu_verts']:,} GPU vertices for {stats['tris']:,} triangles "
                f"({stats['gpu_verts'] / max(stats['verts'], 1):.1f}x its {stats['verts']:,} mesh vertices)"
            ),
            object_name=obj.name,
            check_name="shading",
        ))

    return results


@register_check(roles=("asset",))  # LODs carry the normals baked in, with no modifiers
def check_weighted_normal(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    """Mid-poly profiles shade the bevels with a Weighted Normal modifier: without it the big faces curve."""
    if not config.get("hard_surface", {}).get("require_weighted_normal", False):
        return []
    return [CheckResult(
        severity=Severity.ERROR,
        message=f"'{obj.name}' has no Weighted Normal modifier (the profile is mid-poly)",
        object_name=obj.name,
        fix_hint="Fix adds one (Keep Sharp, last in the stack); Hard Surface Prep adds it too",
        check_name="weighted_normal",
        fix=partial(add_weighted_normal, obj),
    ) for obj in objects if not has_weighted_normal(obj)]


def shading_stats(mesh: bpy.types.Mesh) -> dict:
    normals = read_array(mesh.corner_normals, "vector", 3)
    uvs = [read_array(layer.data, "uv", 2) for layer in mesh.uv_layers]
    corner_vert = read_array(mesh.loops, "vertex_index", dtype=np.int64)
    corner_edge = read_array(mesh.loops, "edge_index", dtype=np.int64)
    loop_start = read_array(mesh.polygons, "loop_start", dtype=np.int64)
    loop_total = read_array(mesh.polygons, "loop_total", dtype=np.int64)
    corner_mat = np.repeat(read_array(mesh.polygons, "material_index", dtype=np.int64), loop_total)

    def snap(values):
        return np.round(values.astype(np.float64) / _SAME).astype(np.int64)

    keys = np.column_stack([corner_vert, corner_mat, snap(normals), *(snap(uv) for uv in uvs)])
    gpu_verts = len(np.unique(keys, axis=0)) if len(keys) else 0

    # Corner i runs along edge corner_edge[i] to corner nxt[i]; pair the two faces of each 2-face edge
    nxt = np.arange(len(corner_vert)) + 1
    nxt[loop_start + loop_total - 1] = loop_start
    two_faced = np.flatnonzero(np.bincount(corner_edge, minlength=len(mesh.edges))[corner_edge] == 2)
    two_faced = two_faced[np.argsort(corner_edge[two_faced], kind="stable")]
    a0, b0 = two_faced[0::2], two_faced[1::2]
    a1, b1 = nxt[a0], nxt[b0]
    # Match corners by vertex: flipped neighbours wind the same way, not opposite
    opposite = corner_vert[a0] == corner_vert[b1]
    pairs = ((a0, np.where(opposite, b1, b0)), (a1, np.where(opposite, b0, b1)))

    def split(values):
        return np.logical_or(*(np.linalg.norm(values[a] - values[b], axis=1) > _SAME for a, b in pairs))

    hard = split(normals)
    seam = split(uvs[0]) if uvs else np.zeros(len(a0), bool)

    return {
        "hard_off_seam": corner_edge[a0][hard & ~seam].tolist(),
        "gpu_verts": gpu_verts,
        "verts": len(mesh.vertices),
        "tris": int((loop_total - 2).sum()),
    }
