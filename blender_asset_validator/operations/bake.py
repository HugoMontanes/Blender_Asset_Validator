"""Bake helper: a tangent-space normal map from the _high meshes onto their low, with the
cage and ray distance measured from the meshes instead of guessed."""
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..core.mesh_utils import read_array
from ..core.roles import bake_base

_SAMPLES = 16  # anti-aliasing of the bake; the render's samples (4096 by default) would take minutes
_MAX_PROBES = 100_000  # high-poly vertices measured; a random sample past that
_MAX_OFFSET = 0.1  # median high-to-low distance, of the low's diagonal, past which the pair isn't on top of each other


def ray_distances(low: bpy.types.Object, highs: list) -> tuple:
    """(cage extrusion, max ray distance) in metres: rays start on the low inflated past the
    high's farthest point outside it, and reach its deepest point inside. ValueError if the
    high isn't on top of the low."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    tree, diagonal = _world_bvh(low.evaluated_get(depsgraph))
    points = np.concatenate([_world_vertices(h.evaluated_get(depsgraph)) for h in highs])
    if not len(points):
        raise ValueError("its high meshes have no vertices")
    if len(points) > _MAX_PROBES:
        points = points[np.random.default_rng(0).choice(len(points), _MAX_PROBES, replace=False)]
    signed = np.empty(len(points))
    for i, point in enumerate(points.tolist()):
        location, normal, _, _ = tree.find_nearest(point)
        signed[i] = (Vector(point) - location).dot(normal)
    typical = float(np.median(np.abs(signed)))
    if typical > _MAX_OFFSET * diagonal:  # measured: LODs laid side by side gave a cage bigger than the car
        raise ValueError(f"its high meshes don't sit on it: half their vertices are over {typical:.3g} m away "
                         f"({typical / diagonal:.0%} of its size). Move them together")
    pad = 0.001 * diagonal  # a high lying on the low still needs the rays to start above it
    extrusion = 1.1 * max(signed.max(), 0.0) + pad
    return extrusion, extrusion + 1.1 * max(-signed.min(), 0.0) + pad


def _world_bvh(evaluated: bpy.types.Object):
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        verts = _to_world(read_array(mesh.vertices, "co", 3), evaluated.matrix_world)
        tris = read_array(mesh.loop_triangles, "vertices", 3, np.int32)
        return BVHTree.FromPolygons(verts.tolist(), tris.tolist()), float(np.linalg.norm(np.ptp(verts, axis=0)))
    finally:
        evaluated.to_mesh_clear()


def _world_vertices(evaluated: bpy.types.Object) -> np.ndarray:
    mesh = evaluated.to_mesh()
    try:
        return _to_world(read_array(mesh.vertices, "co", 3), evaluated.matrix_world)
    finally:
        evaluated.to_mesh_clear()


def _to_world(co: np.ndarray, matrix) -> np.ndarray:
    m = np.array(matrix)
    return co @ m[:3, :3].T + m[:3, 3]


def add_triangulate(obj: bpy.types.Object):
    """The bake, Substance Painter and the engine each triangulate non-planar quads their own way, and
    the tangent basis changes with the diagonal: a Triangulate modifier gives all three the same triangles."""
    if any(m.type == "TRIANGULATE" and m.show_viewport for m in obj.modifiers):
        return None
    obj.modifiers.new("Triangulate", "TRIANGULATE").keep_custom_normals = True  # lands before a pinned Weighted Normal
    return "Triangulate added"


def bake_normals(low: bpy.types.Object, highs: list, config: dict) -> str:
    """Bakes into the image <base>_N and saves it as a PNG in bake.path. ValueError if the low can't be baked."""
    if not low.data.uv_layers:
        raise ValueError("no UV map to bake into")
    if not low.material_slots or any(slot.material is None for slot in low.material_slots):
        raise ValueError("every material slot needs a material (the bake writes through an image node in each)")
    cfg, uv = config.get("bake", {}), config.get("uv", {})
    size = uv.get("texture_size", 2048)
    extrusion, ray = ray_distances(low, highs)  # first: it may raise, and nothing is changed yet
    notes = [note for note in (add_triangulate(low),) if note]

    name = f"{bake_base(low, config)}_N"
    image = bpy.data.images.get(name) or bpy.data.images.new(name, size, size, is_data=True)
    if tuple(image.size) != (size, size):
        image.scale(size, size)
    image.colorspace_settings.is_data = True  # an sRGB image would get the bake gamma-encoded
    scene = bpy.context.scene
    render = scene.render.engine, scene.cycles.samples
    added = []  # (node tree, temporary image node, the node that was active)
    try:
        for material in {slot.material for slot in low.material_slots}:
            if material.node_tree is None:
                material.use_nodes = True  # 4.2: a material made from Python has no node tree yet
            nodes = material.node_tree.nodes
            node = nodes.new("ShaderNodeTexImage")
            node.image = image
            added.append((material.node_tree, node, nodes.active))
            nodes.active = node  # the bake writes into the active image node
        scene.render.engine, scene.cycles.samples = "CYCLES", _SAMPLES
        selected = [low, *highs]
        with bpy.context.temp_override(selected_objects=selected, selected_editable_objects=selected, active_object=low, object=low):
            bpy.ops.object.bake(
                type="NORMAL", normal_space="TANGENT", normal_g=cfg.get("normal_g", "POS_Y"),
                use_selected_to_active=True, cage_extrusion=extrusion, max_ray_distance=ray,
                margin=max(1, uv.get("min_island_gap_px", 8) // 2),  # the paddings of two islands meet mid-gap
                uv_layer=low.data.uv_layers[0].name, use_clear=True, target="IMAGE_TEXTURES",
            )
    finally:
        for tree, node, active in added:
            tree.nodes.remove(node)
            tree.nodes.active = active
        scene.render.engine, scene.cycles.samples = render

    folder = bpy.path.abspath(cfg.get("path", "//bakes/"))
    os.makedirs(folder, exist_ok=True)
    image.filepath_raw = os.path.join(folder, f"{name}.png")
    image.file_format = "PNG"
    image.save()
    notes.append(f"{name}.png ({size} px, {len(highs)} high mesh(es), cage {extrusion:.3g} m, ray {ray:.3g} m, green {cfg.get('normal_g', 'POS_Y')})")
    return ", ".join(notes)
