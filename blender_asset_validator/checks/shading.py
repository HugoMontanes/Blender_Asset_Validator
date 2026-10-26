from functools import partial
from typing import List

import bpy

from ..core.mesh_utils import bake_mesh, select_in_edit_mode
from ..core.registry import register_check
from ..core.result import CheckResult, Severity

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


def shading_stats(mesh: bpy.types.Mesh) -> dict:
    mesh.calc_loop_triangles()
    if hasattr(mesh, "corner_normals"):
        normals = [n.vector.copy() for n in mesh.corner_normals]
    else:  # Blender < 4.1
        mesh.calc_normals_split()
        normals = [loop.normal.copy() for loop in mesh.loops]
    uvs = [[d.uv.copy() for d in layer.data] for layer in mesh.uv_layers]
    corner_vert = [loop.vertex_index for loop in mesh.loops]
    corner_mat = [0] * len(mesh.loops)
    edge_corners = {}  # edge -> corners of each face on it, as (corner at its 1st vertex, at its 2nd)
    for poly in mesh.polygons:
        loops = list(poly.loop_indices)
        for i, nxt in zip(loops, loops[1:] + loops[:1]):
            corner_mat[i] = poly.material_index
            edge_corners.setdefault(mesh.loops[i].edge_index, []).append((i, nxt))

    def snap(v):
        return tuple(round(c / _SAME) for c in v)

    gpu_verts = {
        (corner_vert[i], corner_mat[i], snap(normals[i]), *(snap(layer[i]) for layer in uvs))
        for i in range(len(mesh.loops))
    }

    hard_off_seam = []
    for edge, sides in edge_corners.items():
        if len(sides) != 2:
            continue
        (a0, a1), (b0, b1) = sides
        # Match corners by vertex: flipped neighbours wind the same way, not opposite
        pairs = ((a0, b1), (a1, b0)) if corner_vert[a0] == corner_vert[b1] else ((a0, b0), (a1, b1))
        hard = any((normals[a] - normals[b]).length > _SAME for a, b in pairs)
        seam = bool(uvs) and any((uvs[0][a] - uvs[0][b]).length > _SAME for a, b in pairs)
        if hard and not seam:
            hard_off_seam.append(edge)

    return {
        "hard_off_seam": hard_off_seam,
        "gpu_verts": len(gpu_verts),
        "verts": len(mesh.vertices),
        "tris": len(mesh.loop_triangles),
    }
