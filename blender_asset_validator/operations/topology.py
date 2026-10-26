import math
from typing import Optional

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

from ..core.mesh_utils import bake_mesh

_UV_EPSILON = 1e-5
_MAX_DISSOLVE_PASSES = 32


def topology_settings(config: dict) -> dict:
    cfg = config.get("topology", {})
    return {
        "flat": math.radians(cfg.get("flat_angle", 1.0)),
        "feature": math.radians(cfg.get("feature_angle", 30.0)),
        "quad": math.radians(cfg.get("quad_angle", 40.0)),
        "iterations": cfg.get("relax_iterations", 5),
        "factor": cfg.get("relax_factor", 0.5),
    }


def clean_topology(obj: bpy.types.Object, config: dict) -> Optional[str]:
    """In place on obj.data: tris -> quads, dissolve flat edge loops, relax the
    free vertices along the surface. Borders, seams, UV/material borders and
    hard edges stay where they are, so shape and UVs survive."""
    source = obj.get("asset_validator_lod_source")
    target = bake_mesh(source) if source is not None else obj.data  # LODs relax onto the full-res source
    surface = Surface(target)
    if target is not obj.data:
        bpy.data.meshes.remove(target)

    mesh = obj.data
    # Subdivision: relaxing would soften its support loops. Shape keys: only the basis would move
    relax = not mesh.shape_keys and not any(m.type in {"SUBSURF", "MULTIRES"} for m in obj.modifiers)
    before = len(mesh.polygons)
    # Custom normals are per corner and don't survive the new topology: re-transfer them afterwards
    normals_ref = None
    if source is None and mesh.has_custom_normals:
        normals_ref = bpy.data.objects.new("_AssetValidator_normals_ref", mesh.copy())
        bpy.context.scene.collection.objects.link(normals_ref)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    clean_bmesh(bm, surface, topology_settings(config), relax=relax)
    bm.to_mesh(mesh)
    mesh.update()
    quads = sum(1 for f in bm.faces if len(f.verts) == 4)
    after = len(bm.faces)
    bm.free()
    if source is not None and any(p.use_smooth for p in mesh.polygons):
        transfer_normals(mesh, source)
    elif normals_ref is not None:
        ref_mesh = normals_ref.data
        try:
            transfer_normals(mesh, normals_ref)
        finally:
            bpy.data.objects.remove(normals_ref)
            bpy.data.meshes.remove(ref_mesh)

    note = "" if relax else ", relax skipped (Subdivision/Multires modifier or shape keys)"
    return f"{before:,} -> {after:,} faces, {quads * 100 // max(after, 1)}% quads{note}"


def clean_bmesh(bm: bmesh.types.BMesh, surface: "Surface", cfg: dict, relax: bool = True) -> None:
    # No merge-by-distance here: split vertices are often deliberate hard edges (FBX imports)
    bmesh.ops.join_triangles(
        bm, faces=bm.faces, cmp_seam=True, cmp_sharp=True, cmp_uvs=True, cmp_materials=True,
        angle_face_threshold=cfg["quad"], angle_shape_threshold=cfg["quad"],
    )
    _dissolve_flat_loops(bm, cfg)
    if relax:
        _relax(bm, surface, cfg)


def retopologize(context, obj: bpy.types.Object, ratio: float, symmetry: bool, merge_distance: float) -> bpy.types.Object:
    """New quad object built by QuadriFlow from obj's evaluated mesh, with
    materials, UVs and normals resampled from the original. `merge_distance`
    is in world units. Raises RuntimeError."""
    mesh = bake_mesh(obj)
    surface = Surface(mesh)
    smooth = any(p.use_smooth for p in mesh.polygons)
    target_faces = max(8, round(sum(len(p.vertices) - 2 for p in mesh.polygons) * ratio / 2))  # quad = 2 tris

    new = bpy.data.objects.new(f"{obj.name}_Retopo", mesh.copy())
    new.matrix_world = obj.matrix_world.copy()
    for coll in obj.users_collection:
        coll.objects.link(new)
    try:
        local_distance = merge_distance / max(max(abs(c) for c in obj.matrix_world.to_scale()), 1e-12)
        problems = _repair_for_quadriflow(new.data, local_distance)  # only the copy; UVs come from `surface`
        before = (len(new.data.vertices), len(new.data.polygons))
        try:
            with context.temp_override(object=new, active_object=new, selected_objects=[new], selected_editable_objects=[new]):
                bpy.ops.object.quadriflow_remesh(
                    mode="FACES", target_faces=target_faces, use_mesh_symmetry=symmetry,
                    use_preserve_sharp=True, use_preserve_boundary=True, smooth_normals=False, seed=0,
                )
            # QuadriFlow reports most failures only to the UI and leaves the mesh untouched
            polys = new.data.polygons
            failed = not polys or (len(new.data.vertices), len(polys)) == before or any(len(p.vertices) != 4 for p in polys)
        except RuntimeError:
            failed = True
        if failed:
            raise RuntimeError(
                "QuadriFlow failed: " + ", ".join(problems)
                + " (Edit Mode > Select > All by Trait > Non Manifold)"
                if problems else
                "QuadriFlow failed on a clean manifold mesh — try another Triangle Ratio"
            )
    except RuntimeError:
        old = new.data
        bpy.data.objects.remove(new)
        bpy.data.meshes.remove(old)
        raise
    finally:
        bpy.data.meshes.remove(mesh)

    bm = bmesh.new()
    bm.from_mesh(new.data)
    surface.resample_faces(bm)
    uv_layers = list(bm.loops.layers.uv.values())
    for edge in bm.edges:
        edge.seam = _is_uv_border(edge, uv_layers)  # ready for a later re-unwrap
    for face in bm.faces:
        face.smooth = smooth
    bm.to_mesh(new.data)
    bm.free()
    if smooth:
        transfer_normals(new.data, obj)
    return new


def _repair_for_quadriflow(mesh: bpy.types.Mesh, merge_distance: float) -> list:
    """Fix what game/FBX meshes usually trip QuadriFlow on (loose or degenerate
    geometry, flipped faces, vertices split at seams and hard edges) and describe
    what's left. Welding is kept only if it helps: on thin shells (glass with
    thickness) it fuses the inner and outer layers instead."""
    def cleaned(weld):
        bm = bmesh.new()
        bm.from_mesh(mesh)
        if weld:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_distance)  # also drops duplicate faces
        bmesh.ops.dissolve_degenerate(bm, dist=merge_distance, edges=bm.edges)
        bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context="EDGES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return bm, _manifold_problems(bm)

    welded, welded_problems = cleaned(weld=True)
    raw, raw_problems = cleaned(weld=False)
    weld_hurts = sum(welded_problems.values()) > sum(raw_problems.values())
    bm, counts = (raw, raw_problems) if weld_hurts else (welded, welded_problems)
    bm.to_mesh(mesh)
    welded.free()
    raw.free()

    problems = [f"{n} {label}" for label, n in counts.items() if n]
    if problems and weld_hurts:
        problems.append(
            f"welding at {merge_distance:g} (local units) made it worse "
            f"({sum(welded_problems.values())} issues) — likely layers closer than that"
        )
    return problems


def _manifold_problems(bm) -> dict:
    return {
        "edge(s) shared by 3+ faces (overlapping or intersecting parts)":
            sum(1 for e in bm.edges if len(e.link_faces) > 2),
        "vertex(es) where separate surfaces touch at one point": sum(
            1 for v in bm.verts
            if not v.is_manifold and not v.is_boundary and all(len(e.link_faces) <= 2 for e in v.link_edges)
        ),
        "edge(s) between faces that can't be oriented consistently": sum(
            1 for e in bm.edges if len(e.link_loops) == 2 and e.link_loops[0].vert is e.link_loops[1].vert
        ),
    }


def feature_verts(bm: bmesh.types.BMesh, feature_angle: float = math.pi) -> set:
    """Vertices on open borders, seams, sharp edges, material or UV borders, or
    edges bent more than feature_angle — the ones that define the asset's shape."""
    uv_layers = list(bm.loops.layers.uv.values())
    verts = set()
    for edge in bm.edges:
        if _is_feature_edge(edge, uv_layers, feature_angle):
            verts.update(edge.verts)
    return verts


def _is_feature_edge(edge, uv_layers, feature_angle) -> bool:
    faces = edge.link_faces
    return (
        len(faces) != 2
        or edge.seam
        or not edge.smooth
        or faces[0].material_index != faces[1].material_index
        or edge.calc_face_angle(0.0) > feature_angle
        or _is_uv_border(edge, uv_layers)
    )


def _is_uv_border(edge, uv_layers) -> bool:
    """True if the two faces sharing `edge` disagree on the UVs of its vertices."""
    if len(edge.link_loops) != 2:
        return False
    loop_a, loop_b = edge.link_loops
    for layer in uv_layers:
        uvs_a = {loop_a.vert: loop_a[layer].uv, loop_a.link_loop_next.vert: loop_a.link_loop_next[layer].uv}
        uvs_b = {loop_b.vert: loop_b[layer].uv, loop_b.link_loop_next.vert: loop_b.link_loop_next[layer].uv}
        if any((uvs_a[v] - uvs_b[v]).length > _UV_EPSILON for v in edge.verts):
            return True
    return False


def _dissolve_flat_loops(bm, cfg) -> None:
    """Remove whole edge loops that run across flat, straight quad strips: the
    quads on each side merge into one quad, the shape and UVs don't move."""
    uv_layers = list(bm.loops.layers.uv.values())
    for _ in range(_MAX_DISSOLVE_PASSES):
        def candidate(edge):
            return (
                len(edge.link_faces) == 2
                and all(len(f.verts) == 4 for f in edge.link_faces)
                and edge.calc_face_angle(math.pi) < cfg["flat"]
                and not _is_feature_edge(edge, uv_layers, cfg["flat"])
            )

        seen, used_verts, batch = set(), set(), []
        for edge in bm.edges:
            if edge in seen or not candidate(edge):
                continue
            loop = _edge_loop(edge, candidate)
            seen.update(loop or (edge,))
            if not loop:
                continue
            verts = {v for e in loop for v in e.verts}
            if verts & used_verts:
                continue  # crossing a loop already picked this pass would leave a hole
            loop_set = set(loop)
            if all(_straight_through(v, loop_set, uv_layers, cfg["flat"]) for v in verts):
                batch.extend(loop)
                used_verts |= verts
        if not batch:
            return
        bmesh.ops.dissolve_edges(bm, edges=batch, use_verts=True, use_face_split=False)


def _edge_loop(start, candidate):
    """Edges of the loop through `start`, or None unless every edge is a candidate
    and the loop closes or ends on open borders (never on a pole)."""
    edges = [start]
    for v in start.verts:
        edge = start
        while True:
            if v.is_boundary:
                if len(v.link_edges) != 3:
                    return None
                break
            if len(v.link_edges) != 4:
                return None
            faces = set(edge.link_faces)
            opposite = [e for e in v.link_edges if e is not edge and not faces & set(e.link_faces)]
            if len(opposite) != 1:
                return None
            edge = opposite[0]
            if edge is start:
                return edges  # closed loop
            if not candidate(edge):
                return None
            edges.append(edge)
            v = edge.other_vert(v)
    return edges


def _straight_through(v, loop_set, uv_layers, limit) -> bool:
    """After the loop goes, v sits between its two remaining edges: they must be
    collinear in 3D, and in UV on each side of the loop, or dissolving v would
    bend the shape/UVs. The rails may be seams — each side is checked on its own."""
    rails = [e for e in v.link_edges if e not in loop_set]
    if len(rails) != 2:
        return False
    a, b = (e.other_vert(v) for e in rails)
    if _bend(a.co - v.co, b.co - v.co) > limit:
        return False
    for edge in v.link_edges:
        if edge not in loop_set:
            continue
        face_a, face_b = edge.link_faces  # merge into one face; each holds one rail at v
        for layer in uv_layers:
            uv = _loop_uv(face_a, v, layer)
            ends = [_loop_uv(f, _rail_end(f, v, edge), layer) for f in (face_a, face_b)]
            if _bend((ends[0] - uv).to_3d(), (ends[1] - uv).to_3d()) > limit:
                return False
    return True


def _rail_end(face, v, loop_edge):
    rail = next(e for e in face.edges if v in e.verts and e is not loop_edge)
    return rail.other_vert(v)


def _loop_uv(face, vert, layer):
    return next(loop[layer].uv for loop in face.loops if loop.vert is vert)


def _bend(d1: Vector, d2: Vector) -> float:
    if d1.length == 0 or d2.length == 0:
        return math.pi
    return math.pi - d1.angle(d2)


def _relax(bm, surface: "Surface", cfg) -> None:
    """Laplacian smoothing projected back onto the original surface: evens out
    the edge flow tangentially without changing the shape."""
    pinned = feature_verts(bm, cfg["feature"])
    free = [v for v in bm.verts if v not in pinned and v.link_edges]
    for _ in range(cfg["iterations"]):
        targets = [sum((e.other_vert(v).co for e in v.link_edges), Vector()) / len(v.link_edges) for v in free]
        for v, target in zip(free, targets):
            hit = surface.nearest(v.co.lerp(target, cfg["factor"]))
            if hit is not None:
                v.co = hit[0]
    uv_layers = list(bm.loops.layers.uv.values())
    for v in free:
        hit = surface.nearest(v.co)
        if hit is None:
            continue
        for layer_idx, layer in enumerate(uv_layers):
            uv = surface.uv_at(v.co, hit[2], layer_idx)
            for loop in v.link_loops:
                loop[layer].uv = uv


class Surface:
    """Triangulated snapshot of a mesh to project onto and sample UVs/materials from."""

    def __init__(self, mesh: bpy.types.Mesh):
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        layers = list(bm.loops.layers.uv.values())
        self.tris = [
            (
                [loop.vert.co.copy() for loop in face.loops],
                [[loop[layer].uv.to_3d() for loop in face.loops] for layer in layers],
                face.material_index,
            )
            for face in bm.faces
        ]
        self.bvh = BVHTree.FromBMesh(bm)
        bm.free()

    def nearest(self, co):
        hit = self.bvh.find_nearest(co)
        return None if hit[0] is None else hit

    def uv_at(self, co, tri_index, layer_idx):
        corners, uvs, _ = self.tris[tri_index]
        if layer_idx >= len(uvs):
            return Vector((0.0, 0.0))
        uv = barycentric_transform(co, *corners, *uvs[layer_idx])
        if any(math.isnan(c) or math.isinf(c) for c in uv):  # zero-area source triangle
            return min(zip(corners, uvs[layer_idx]), key=lambda cu: (cu[0] - co).length)[1].to_2d()
        return uv.to_2d()

    def resample_faces(self, bm: bmesh.types.BMesh) -> None:
        """Project verts onto the surface, then give every face the material and UVs of
        the triangle under its center — one source island per face, so none straddles a seam."""
        for v in bm.verts:
            hit = self.nearest(v.co)
            if hit is not None:
                v.co = hit[0]
        layer_count = len(self.tris[0][1]) if self.tris else 0
        while len(bm.loops.layers.uv) < layer_count:
            bm.loops.layers.uv.new()
        layers = list(bm.loops.layers.uv.values())
        for face in bm.faces:
            hit = self.nearest(face.calc_center_median())
            if hit is None:
                continue
            face.material_index = self.tris[hit[2]][2]
            for layer_idx, layer in enumerate(layers):
                for loop in face.loops:
                    loop[layer].uv = self.uv_at(loop.vert.co, hit[2], layer_idx)


def transfer_normals(mesh: bpy.types.Mesh, source: bpy.types.Object) -> None:
    """Custom normals of `source` (evaluated, same local space) written into `mesh` in
    place, so linked duplicates keep sharing it and the owner's modifiers aren't applied."""
    holder = bpy.data.objects.new("_AssetValidator_normals", mesh)
    bpy.context.scene.collection.objects.link(holder)
    try:
        transfer = holder.modifiers.new("normals", "DATA_TRANSFER")
        transfer.object = source
        transfer.use_object_transform = False
        transfer.use_loop_data = True
        transfer.data_types_loops = {"CUSTOM_NORMAL"}
        transfer.loop_mapping = "POLYINTERP_NEAREST"
        baked = bake_mesh(holder)
    finally:
        bpy.data.objects.remove(holder)
    try:
        if hasattr(baked, "corner_normals"):
            normals = [tuple(n.vector) for n in baked.corner_normals]
        else:  # Blender < 4.1
            baked.calc_normals_split()
            normals = [tuple(loop.normal) for loop in baked.loops]
    finally:
        bpy.data.meshes.remove(baked)
    if hasattr(mesh, "use_auto_smooth"):  # Blender < 4.1 needs it for custom normals
        mesh.use_auto_smooth = True
    mesh.normals_split_custom_set(normals)
