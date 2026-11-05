"""Bake helper: a tangent-space normal map from the _high meshes onto their low, with the
cage and ray distance measured from the meshes instead of guessed."""
import math
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..core.mesh_utils import bake_mesh, read_array, to_world
from ..core.roles import bake_base
from .hard_surface import _bent_edges, _set_sharp_edges, _sharp_edges, auto_smooth_modifiers
from .lod import _shape, _stray

_SAMPLES = 16  # anti-aliasing of the bake; the render's samples (4096 by default) would take minutes
# ponytail: a random sample past this many high vertices; a spike of a few vertices can miss it and the
# cage comes out short (the 10 % pad covers a dense bump). Measure them all if a real high shows it.
_MAX_PROBES = 100_000
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
        verts = to_world(read_array(mesh.vertices, "co", 3), evaluated.matrix_world)
        tris = read_array(mesh.loop_triangles, "vertices", 3, np.int32)
        return BVHTree.FromPolygons(verts.tolist(), tris.tolist()), float(np.linalg.norm(np.ptp(verts, axis=0)))
    finally:
        evaluated.to_mesh_clear()


def _world_vertices(evaluated: bpy.types.Object) -> np.ndarray:
    mesh = evaluated.to_mesh()
    try:
        return to_world(read_array(mesh.vertices, "co", 3), evaluated.matrix_world)
    finally:
        evaluated.to_mesh_clear()


def add_triangulate(obj: bpy.types.Object):
    """The bake, Substance Painter and the engine each triangulate non-planar quads their own way, and
    the tangent basis changes with the diagonal: a Triangulate modifier gives all three the same triangles."""
    if any(m.type == "TRIANGULATE" and m.show_viewport for m in obj.modifiers):
        return None
    modifier = obj.modifiers.new("Triangulate", "TRIANGULATE")  # lands before a pinned Weighted Normal
    modifier.keep_custom_normals = True
    return modifier


def bake_normals(low: bpy.types.Object, highs: list, config: dict) -> str:
    """Bakes into the image <base>_N and saves it as a PNG in bake.path. ValueError if the low can't be baked."""
    if not low.data.uv_layers:
        raise ValueError("no UV map to bake into")
    if not low.material_slots or any(slot.material is None for slot in low.material_slots):
        raise ValueError("every material slot needs a material (the bake writes through an image node in each)")
    cfg, uv = config.get("bake", {}), config.get("uv", {})
    size = uv.get("texture_size", 2048)
    extrusion, ray = ray_distances(low, highs)  # first: it may raise, and nothing is changed yet
    triangulate = add_triangulate(low)

    name = f"{bake_base(low, config)}_N"
    image = bpy.data.images.get(name) or bpy.data.images.new(name, size, size, is_data=True)
    if tuple(image.size) != (size, size):
        image.scale(size, size)
    image.colorspace_settings.is_data = True  # an sRGB image would get the bake gamma-encoded
    scene = bpy.context.scene
    render = scene.render.engine, scene.cycles.samples
    layer = bpy.context.view_layer
    # Cycles bakes the high's shader normal: a Normal Map in its material (a copy of a textured low) was baked
    # in. Painter and Marmoset bake the geometry, so every object renders with a plain material for the bake
    override, layer.material_override = layer.material_override, bpy.data.materials.new("AV_bake_plain")
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
        try:
            with bpy.context.temp_override(selected_objects=selected, selected_editable_objects=selected, active_object=low, object=low):
                # An option left out comes from the scene's Bake panel (measured: its cage object and
                # normal_r leaked in), so every one that changes the result is given
                bpy.ops.object.bake(
                    type="NORMAL", normal_space="TANGENT", normal_r="POS_X", normal_g=cfg.get("normal_g", "POS_Y"),
                    normal_b="POS_Z", use_selected_to_active=True, use_cage=False, cage_extrusion=extrusion,
                    max_ray_distance=ray, margin_type="ADJACENT_FACES",
                    margin=max(1, uv.get("min_island_gap_px", 8) // 2),  # the paddings of two islands meet mid-gap
                    uv_layer=low.data.uv_layers[0].name, use_clear=True, target="IMAGE_TEXTURES",
                )
        except RuntimeError as e:  # Blender's own refusals, such as a low that's disabled for rendering
            if triangulate is not None:  # nothing was baked through it, and a cancelled operator leaves no undo step
                low.modifiers.remove(triangulate)
            raise ValueError(str(e).removeprefix("Error: ").strip()) from e
    finally:
        for tree, node, active in added:
            tree.nodes.remove(node)
            tree.nodes.active = active
        scene.render.engine, scene.cycles.samples = render
        bpy.data.materials.remove(layer.material_override)
        layer.material_override = override

    folder = bpy.path.abspath(cfg.get("path", "//bakes/"))
    os.makedirs(folder, exist_ok=True)
    image.filepath_raw = os.path.join(folder, f"{name}.png")
    image.file_format = "PNG"
    image.save()
    note = f"{name}.png ({size} px, {len(highs)} high mesh(es), cage {extrusion:.3g} m, ray {ray:.3g} m, green {cfg.get('normal_g', 'POS_Y')})"
    return f"Triangulate added, {note}" if triangulate is not None else note


def make_high(low: bpy.types.Object, config: dict, crease: float, levels: int) -> str:
    """A hidden <base>_high to bake from: low's copy where it is, with a Subdivision modifier last."""
    name = bake_base(low, config) + config.get("bake", {}).get("high_suffix", "_high")
    if name in bpy.context.scene.objects:  # one in another scene isn't this low's: the new one gets .001, still a high
        return f"'{name}' already exists, left as it is (delete it to make a new one)"
    if len(name.encode()) > 63:  # Blender would cut the suffix off, and the copy would be an asset
        return f"not made, '{name}' is past Blender's 63-byte names: shorten '{low.name}'"
    high = low.copy()
    high.data = low.data.copy()
    high.name = high.data.name = name
    for collection in low.users_collection:
        collection.objects.link(high)
    weights = high.data.attributes.get("bevel_weight_edge")  # Prep with Bevel turns the sharp edges into these
    edges = _sharp_edges(high.data) | (read_array(weights.data, "value") > 0 if weights else False)
    if not edges.any():  # as Auto Unwrap seams an unmarked mesh
        edges = _bent_edges(high.data, math.radians(config.get("topology", {}).get("feature_angle", 30.0)))
    creases = high.data.attributes.get("crease_edge") or high.data.attributes.new("crease_edge", "FLOAT", "EDGE")
    creases.data.foreach_set("value", np.where(edges, crease, read_array(creases.data, "value")).astype(np.float32))
    high.data.shade_smooth()
    if crease >= 1.0:  # or the shading bends across a hard crease
        _set_sharp_edges(high.data, edges)
    elif "sharp_edge" in high.data.attributes:  # they'd facet a rounded one
        high.data.attributes.remove(high.data.attributes["sharp_edge"])
    for modifier in [m for m in high.modifiers if m.type in ("TRIANGULATE", "WEIGHTED_NORMAL")] + auto_smooth_modifiers(high):
        high.modifiers.remove(modifier)  # the low's shading: the Subdivision smooths the high
    subdivision = high.modifiers.new("Subdivision", "SUBSURF")
    subdivision.levels = subdivision.render_levels = levels  # the bake reads render, ray_distances the viewport
    low_mesh, high_mesh = bake_mesh(low), bake_mesh(high)
    try:
        low_shape, high_shape = _shape(low_mesh, low.matrix_world), _shape(high_mesh, high.matrix_world)
        note = (f"'{high.name}' made: {int(edges.sum())} edge(s) creased {crease:g}, level {levels}, "
                f"{len(high_mesh.loop_triangles):,} triangles, strays {_stray(low_shape, high_shape):.1f} % of its size from the low")
    finally:
        bpy.data.meshes.remove(low_mesh)
        bpy.data.meshes.remove(high_mesh)
    others = int((read_array(low.data.polygons, "loop_total", dtype=np.int64) != 4).sum())
    if others:
        note += f". {others:,} face(s) aren't quads: SubD pinches around them (Clean Topology turns triangles into quads)"
    high.hide_set(True)
    return note
