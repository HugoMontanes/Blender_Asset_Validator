from typing import List, Optional

import bpy
import bmesh
import numpy as np

from ..core.mesh_utils import read_array
from .topology import loose_parts


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
    """Fixer for check_normals: flips exactly the faces it reported. Custom normals are read before and
    written back: the flip regroups the smooth fans and scrambles the neighbours' ones, and a transfer
    blurs hard edges (a cube's went 90° off). A flipped face keeps its own, turned to face out with it."""
    mesh = obj.data
    custom = mesh.has_custom_normals
    if custom:
        normals = read_array(mesh.corner_normals, "vector", 3)
        old_vert = read_array(mesh.loops, "vertex_index", dtype=np.int64)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    wrong, _, _ = wrong_way_faces(bm)
    bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=[bm.faces[i] for i in wrong])
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    if wrong and custom:
        new_vert = read_array(mesh.loops, "vertex_index", dtype=np.int64)
        old = normals.copy()
        for i in wrong:  # same faces, same corner slots; only their order inside each flipped face changed
            poly = mesh.polygons[i]
            corners = range(poly.loop_start, poly.loop_start + poly.loop_total)
            by_vert = {old_vert[c]: old[c] for c in corners}
            for c in corners:
                n = by_vert[new_vert[c]]
                normals[c] = n if n.dot(poly.normal) >= 0 else -n
        mesh.normals_split_custom_set(normals.tolist())  # a list: a numpy array is parsed row by row, 6x slower
    return f"flipped {len(wrong)} face(s)" if wrong else None


def wrong_way_faces(bm: bmesh.types.BMesh) -> tuple:
    """(indices of faces pointing against most of their part, of faces on closed parts pointing inward,
    of edges where the surface can't be oriented). Inward goes by signed volume: recalc_face_normals only
    guesses the outside and turned a 10-face cone inside out. It's apart: usually on purpose (room, skydome)."""
    bm.normal_update()
    before = [f.normal.copy() for f in bm.faces]
    work = bm.copy()  # same element order as bm
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.normal_update()
    work.faces.ensure_lookup_table()
    flips = {i for i, (f, n) in enumerate(zip(work.faces, before)) if f.normal.dot(n) < 0}
    twisted = [e.index for e in work.edges if len(e.link_loops) == 2 and e.link_loops[0].vert is e.link_loops[1].vert]

    bm.faces.index_update()
    wrong, inward = [], []
    for part in loose_parts(bm):
        flipped = [f.index for f in part if f.index in flips]
        kept = [f.index for f in part if f.index not in flips]
        # The fewer are odd, even on a closed part: a room with one stray face stays a room. Fixed, the part
        # points the way recalc put it (sign 1) or the opposite
        odd, rest, sign = (flipped, kept, 1) if len(flipped) <= len(kept) else (kept, flipped, -1)
        wrong.extend(odd)
        # ponytail: a flat closed shell (welded double-sided card) has ~0 volume, so its inward warning is a
        # coin toss; compare the volume against the part's area if one turns up
        closed = all(len(e.link_faces) == 2 for f in part for e in f.edges)
        if closed and sign * _signed_volume([work.faces[f.index] for f in part]) < 0:
            inward.extend(rest)
    work.free()
    return sorted(wrong), sorted(inward), twisted


def _signed_volume(faces) -> float:
    """Volume a closed surface encloses: positive when its faces point outward."""
    origin = faces[0].verts[0].co.copy()  # a point on it: no float cancellation far from the world origin
    return sum((f.verts[0].co - origin).dot(f.normal) * f.calc_area() for f in faces) / 3


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
