from typing import List, Optional

import bpy
import bmesh
import numpy as np

from ..core.mesh_utils import read_array
from .topology import loose_parts, transfer_normals


def fix_degenerate_faces(obj: bpy.types.Object, config: dict) -> Optional[str]:
    """Fixer for check_degenerate_faces, on the faces it reports only: merges each
    one's coincident vertices, dissolves its zero-length edges, then deletes any
    still under the area epsilon. Never the whole mesh: welding everything fused
    separate parts lying closer than the merge distance (a car's glass layers)
    into non-manifold, misoriented shells — 30 bad faces cost 615."""
    cfg = config.get("optimization", {})
    area_epsilon = config.get("geometry", {}).get("degenerate_face_area_epsilon", 1e-10)
    mesh = obj.data
    before = len(mesh.polygons)

    bm = bmesh.new()
    bm.from_mesh(mesh)

    def degenerate():
        return [face for face in bm.faces if face.calc_area() <= area_epsilon]

    if cfg.get("merge_by_distance", True):
        for verts in [list(face.verts) for face in degenerate()]:  # each face with itself, not with its neighbours
            alive = [v for v in verts if v.is_valid]  # an earlier merge may have taken some
            if len(alive) > 1:
                bmesh.ops.remove_doubles(bm, verts=alive, dist=cfg.get("merge_distance", 0.0001))

    if cfg.get("fix_degenerate_faces", True):
        edges = list({edge for face in degenerate() for edge in face.edges})
        bmesh.ops.dissolve_degenerate(bm, dist=cfg.get("degenerate_merge_distance", 0.0001), edges=edges)
        # Collinear faces with long edges survive dissolve_degenerate but still fail the check
        leftovers = degenerate()
        if leftovers:
            bmesh.ops.delete(bm, geom=leftovers, context="FACES")

    bm.to_mesh(mesh)
    mesh.update()
    bm.free()

    removed = before - len(mesh.polygons)
    if not removed:
        return None
    return f"removed {removed} degenerate face(s)"


def fix_normals(obj: bpy.types.Object, config: dict) -> Optional[str]:
    """Fixer for check_normals: flips exactly the faces it reported. Custom normals
    are per corner and flip with their face, so they're re-transferred."""
    mesh = obj.data
    ref = None
    if mesh.has_custom_normals:
        ref = bpy.data.objects.new("_AssetValidator_normals_ref", mesh.copy())
        bpy.context.scene.collection.objects.link(ref)
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        wrong, _, _ = wrong_way_faces(bm)
        bm.faces.ensure_lookup_table()
        bmesh.ops.reverse_faces(bm, faces=[bm.faces[i] for i in wrong])
        flipped = len(wrong)
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        if ref is not None:
            transfer_normals(mesh, ref)
    finally:
        if ref is not None:
            ref_mesh = ref.data
            bpy.data.objects.remove(ref)
            bpy.data.meshes.remove(ref_mesh)
    return f"flipped {flipped} face(s)" if flipped else None


def wrong_way_faces(bm: bmesh.types.BMesh) -> tuple:
    """(indices of faces Recalculate Outside would flip, of faces on closed parts
    facing inward as a whole, of edges it still can't make consistent, i.e.
    non-orientable surface). Open parts have no outside, so one that faces the
    other way as a whole is fine; only its odd faces count. A closed part turned
    inward as a whole is usually on purpose (room, skydome), so it's apart."""
    bm.normal_update()
    before = [f.normal.copy() for f in bm.faces]
    work = bm.copy()  # same element order as bm
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.normal_update()
    flips = {i for i, (f, n) in enumerate(zip(work.faces, before)) if f.normal.dot(n) < 0}
    twisted = [e.index for e in work.edges if len(e.link_loops) == 2 and e.link_loops[0].vert is e.link_loops[1].vert]
    work.free()

    bm.faces.index_update()
    wrong, inward = [], []
    for part in loose_parts(bm):
        flipped = [f.index for f in part if f.index in flips]
        if len(flipped) < len(part):
            wrong.extend(flipped)
        elif all(len(e.link_faces) == 2 for f in part for e in f.edges):
            inward.extend(flipped)
    return sorted(wrong), sorted(inward), twisted


def delete_loose(obj: bpy.types.Object, config: dict) -> Optional[str]:
    """Fixer for check_manifold: vertices and edges without faces."""
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    edges = [e for e in bm.edges if not e.link_faces]
    bmesh.ops.delete(bm, geom=edges, context="EDGES")
    verts = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=verts, context="VERTS")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return f"deleted {len(verts)} loose vertex(es), {len(edges)} loose edge(s)" if verts or edges else None


def warped_quads(mesh: bpy.types.Mesh, max_warp: float) -> List[int]:
    """Indices of quads bent more than max_warp radians."""
    quads, warp = quad_warps(mesh)
    return quads[warp > max_warp].tolist()


def quad_warps(mesh: bpy.types.Mesh) -> tuple:
    """(indices of the quads, angle in radians between the two triangles of each,
    split on its flatter diagonal: 0 = planar)."""
    sizes = read_array(mesh.polygons, "loop_total", dtype=np.int64)
    quads = np.flatnonzero(sizes == 4)
    starts = read_array(mesh.polygons, "loop_start", dtype=np.int64)[quads]
    corner_vert = read_array(mesh.loops, "vertex_index", dtype=np.int64)
    co = read_array(mesh.vertices, "co", 3, np.float64)
    a, b, c, d = (co[corner_vert[starts + k]] for k in range(4))
    return quads, np.minimum(_fold(a, b, c, d), _fold(b, c, d, a))


def _fold(p, q, r, s) -> np.ndarray:
    """Angle between triangles pqr and prs (rows of points), which share diagonal pr; 0 where one has no area."""
    n1, n2 = np.cross(q - p, r - p), np.cross(r - p, s - p)
    lengths = np.linalg.norm(n1, axis=1) * np.linalg.norm(n2, axis=1)
    cos = np.divide((n1 * n2).sum(axis=1), lengths, out=np.ones(len(p)), where=lengths > 0)
    return np.arccos(np.clip(cos, -1.0, 1.0))


def triangulate_warped(obj: bpy.types.Object, max_warp: float) -> Optional[str]:
    """Fixer for check_quad_planarity: split warped quads now, so the engine
    and the baker can't each pick a different diagonal. Finds them again: an
    earlier fix in the same Fix All may have renumbered the faces."""
    mesh = obj.data
    indices = warped_quads(mesh, max_warp)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    faces = [bm.faces[i] for i in indices]
    bmesh.ops.triangulate(bm, faces=faces, quad_method="BEAUTY")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return f"triangulated {len(faces)} warped quad(s)" if faces else None
