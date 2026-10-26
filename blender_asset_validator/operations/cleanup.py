from typing import List, Optional

import bpy
import bmesh

from .topology import loose_parts, transfer_normals


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
        wrong, _ = wrong_way_faces(bm)
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
    """(indices of faces Recalculate Outside would flip, indices of edges it still
    can't make consistent, i.e. non-orientable surface). Open parts have no outside,
    so one that faces the other way as a whole is fine; only its odd faces count."""
    bm.normal_update()
    before = [f.normal.copy() for f in bm.faces]
    work = bm.copy()  # same element order as bm
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.normal_update()
    flips = {i for i, (f, n) in enumerate(zip(work.faces, before)) if f.normal.dot(n) < 0}
    twisted = [e.index for e in work.edges if len(e.link_loops) == 2 and e.link_loops[0].vert is e.link_loops[1].vert]
    work.free()

    bm.faces.index_update()
    wrong = []
    for part in loose_parts(bm):
        flipped = [f.index for f in part if f.index in flips]
        closed = all(len(e.link_faces) == 2 for f in part for e in f.edges)
        if closed or len(flipped) < len(part):
            wrong.extend(flipped)
    return sorted(wrong), twisted


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


def triangulate_faces(obj: bpy.types.Object, indices: List[int]) -> Optional[str]:
    """Fixer for check_quad_planarity: split warped quads now, so the engine
    and the baker can't each pick a different diagonal."""
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    faces = [bm.faces[i] for i in indices if i < len(bm.faces) and len(bm.faces[i].verts) == 4]
    bmesh.ops.triangulate(bm, faces=faces, quad_method="BEAUTY")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return f"triangulated {len(faces)} warped quad(s)" if faces else None
