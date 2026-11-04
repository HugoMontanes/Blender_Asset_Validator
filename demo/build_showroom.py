"""Builds demo/Showroom.blend from code alone (no third-party assets), one row per collection: every check on
an object made to trip it, then each tool next to its result. Fails if a station doesn't show its label:
    blender -b --factory-startup --python-exit-code 1 --python demo/build_showroom.py [-- out.blend]"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Euler, Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import blender_asset_validator as bav  # noqa: E402

OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(REPO, "demo", "Showroom.blend")
SPACING, PER_LINE, LINE_GAP, ROW_GAP = 3.0, 9, 4.5, 6.0


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1)
    mat.diffuse_color = (*color, 1)
    return mat


def mesh(name, fill, mat=None, uvs=True, smooth=False):
    bm = bmesh.new()
    if uvs:
        bm.loops.layers.uv.new("UVMap")
    fill(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if mat is not None:
        me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = smooth
    return bpy.data.objects.new(name, me)


def label(text, location, size, collection):
    curve = bpy.data.curves.new(f"Label_{len(bpy.data.curves)}", "FONT")
    curve.body, curve.size, curve.align_x = text, size, "CENTER" if size < 0.4 else "LEFT"
    curve.materials.append(bpy.data.materials.get("Label") or material("Label", (0.92, 0.92, 0.92)))
    obj = bpy.data.objects.new(curve.name, curve)
    obj.location, obj.rotation_euler = location, (math.radians(70), 0, 0)  # stood up towards the camera
    collection.objects.link(obj)


class Row:
    def __init__(self, title, color, top):
        self.collection = bpy.data.collections.new(title)
        bpy.context.scene.collection.children.link(self.collection)
        self.top, self.count, self.mat = top, 0, material(title + "_Mat", color)
        label(title, (-5.0, top, 0), 0.6, self.collection)

    def slot(self, caption):
        """The next free spot, PER_LINE to a line, with its caption under it."""
        x, y = self.count % PER_LINE * SPACING, self.top - self.count // PER_LINE * LINE_GAP
        self.count += 1
        label(caption, (x, y - 1.3, 0), 0.18, self.collection)
        return x, y, 0.0

    def add(self, obj, caption):
        self.collection.objects.link(obj)
        obj.location = self.slot(caption)
        return obj

    def below(self):
        return self.top - (max(self.count, 1) - 1) // PER_LINE * LINE_GAP - ROW_GAP


def cube(size=1.0):
    return lambda bm: bmesh.ops.create_cube(bm, size=size, calc_uvs=True)


def cylinder(segments=16, depth=1.4, radius=0.5, caps=True, tris=True):
    return lambda bm: bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=tris, segments=segments, radius1=radius,
                                            radius2=radius, depth=depth, calc_uvs=True)


def grid(n=8, size=0.8):
    return lambda bm: bmesh.ops.create_grid(bm, x_segments=n, y_segments=n, size=size, calc_uvs=True)


def then(fill, edit):
    def run(bm):
        fill(bm)
        bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        edit(bm)
    return run


def same_uvs(bm):
    layer = bm.loops.layers.uv.active
    for f in bm.faces:
        for loop, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            loop[layer].uv = uv


def collapse_some(bm):
    for f in list(bm.faces)[::9]:
        center = f.calc_center_median()
        for v in f.verts:
            v.co = center


def blob(name, mat):
    def fill(bm):
        bmesh.ops.create_icosphere(bm, subdivisions=4, radius=0.7, calc_uvs=True)
        for v in bm.verts:
            v.co *= 1 + 0.15 * math.sin(5 * v.co.x) * math.cos(4 * v.co.z)
    return mesh(name, fill, mat, smooth=True)


def build_checks(row):
    m = row.mat
    stations = [
        (mesh("CrateNgons", cylinder(8, tris=False), m), "ngons", "N-gon caps"),
        (mesh("BarrelFlipped", then(cylinder(16), lambda bm: bmesh.ops.reverse_faces(bm, faces=bm.faces[3:6])), m),
         "normals", "3 faces facing inward"),
        (mesh("PipeNonManifold", then(cylinder(12, caps=False), lambda bm: bm.faces.new(
            (*next(e for e in bm.edges if len(e.link_faces) == 2).verts, bm.verts.new((1.0, 0, 0))))), m),
         "manifold", "Edge with 3 faces"),
        (mesh("PanelDegenerate", then(grid(), collapse_some), m), "geometry_cleanup", "Degenerate faces"),
        (mesh("PropTransforms", cube(), m), "transforms", "Unapplied scale, rotation"),
        (mesh("RockOverBudget", lambda bm: bmesh.ops.create_icosphere(bm, subdivisions=7, radius=0.6, calc_uvs=True), m, smooth=True),
         "polycount", "82k tris, budget 50k"),
        (mesh("SignNoMaterial", grid(2)), "materials", "No material"),
        (mesh("BoxOverlappingUVs", then(cube(), same_uvs), m), "uvs", "Overlapping UVs"),
        (mesh("TileWarpedQuads", then(grid(6), lambda bm: [setattr(v.co, "z", 0.12 * (i % 2 * 2 - 1)) for i, v in enumerate(bm.verts)]), m),
         "topology", "Warped quads"),
        (mesh("LampHardEdges", then(cylinder(24), lambda bm: [setattr(e, "smooth", False) for e in list(bm.edges)[::5]]), m, smooth=True),
         "shading", "Hard edges off seams"),
        (mesh("ColumnPoles", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=0.6, calc_uvs=True), m, smooth=True),
         "topology", "24-edge poles"),
        (mesh("WallDuplicateFaces", grid(3), m), "mesh_data", "Duplicate faces"),
        (mesh("crate legacy.001", cube(), m), "naming", "Not PascalCase"),
        (mesh("CrateTinyTexels", cube(0.2), m), "uv_layout", "Off the texel density"),
        (mesh("UCX_Missing_01", cube(1.1)), "collisions", "UCX of a missing mesh"),
        (mesh("Antenna_high", cylinder(32, depth=1.2, radius=0.08), m, smooth=True), "bake_pairs", "High-poly with no low"),
        (mesh("CrateClean", cube(), m), None, "Reference: no errors"),
    ]
    wall = stations[11][0].data  # the same faces again, flipped: what Blender's validate calls duplicates
    verts, faces = [v.co[:] for v in wall.vertices], [list(p.vertices) for p in wall.polygons]
    wall.clear_geometry()
    wall.from_pydata(verts, [], faces + [f[::-1] for f in faces[::2]])
    for obj, _, caption in stations:
        row.add(obj, caption)
    stations[4][0].scale, stations[4][0].rotation_euler = (1.6, 1.0, 0.6), (0, 0, math.radians(30))
    return [(obj, check) for obj, check, _ in stations]


def build_hard_surface(row, config):
    from blender_asset_validator.operations import hard_surface, uvs

    def crate(name):
        def fill(bm):
            bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.inset_individual(bm, faces=bm.faces[:], thickness=0.08, depth=-0.04)  # recessed panels
        return mesh(name, fill, row.mat, uvs=False)

    row.add(crate("SciFiCrate"), "Before: no UVs")
    prepped = row.add(crate("SciFiCrate_Prepped"), "Prep + Bevel")
    hard_surface.prep_mesh(prepped, config, math.radians(30), bevel=True)
    hard_surface.add_modifiers(prepped, 2)
    row.add(mesh("Canister", cylinder(32, tris=False), row.mat, uvs=False, smooth=True), "Before: no UVs")
    unwrapped = row.add(mesh("Canister_Unwrapped", cylinder(32, tris=False), row.mat, uvs=False, smooth=True), "Auto Unwrap")
    uvs.auto_unwrap(unwrapped, config)
    return prepped, unwrapped


def build_topology(row, config):
    from blender_asset_validator.operations import topology
    row.add(blob("Blob", row.mat), "Before: all triangles")
    cleaned = row.add(blob("Blob_Cleaned", row.mat), "Clean Topology")
    topology.clean_topology(cleaned, config)
    source = row.add(blob("Blob_ForRetopo", row.mat), "Retopologize: quads")
    retopo, _ = topology.retopologize(source, 0.5, False, 1e-4)
    for c in retopo.users_collection:
        c.objects.unlink(retopo)
    row.collection.objects.link(retopo)
    retopo.location = source.location  # in its source's place: the source is hidden
    source.hide_set(True)
    return cleaned, retopo


def build_lods(row, config):
    from blender_asset_validator.operations import lod
    bpy.ops.mesh.primitive_monkey_add(size=1.2)
    statue = bpy.context.active_object
    bpy.context.scene.collection.objects.unlink(statue)
    statue.name = statue.data.name = "Statue"
    statue.modifiers.new("Subdivision", "SUBSURF").levels = 2
    statue.data.materials.append(row.mat)
    row.add(statue, "LOD0 (Subdivision)")
    lod.generate_lods([statue], config)
    created = lod.lods_of(statue)
    for obj in created:
        row.collection.objects.link(obj)  # also in the add-on's LODs collection
        obj.hide_set(False)
        obj.location = row.slot(f"{obj.name.replace('Statue_', '')}: {len(obj.data.polygons):,} faces")
    return created


def build_bake(row, config):
    from blender_asset_validator.operations import bake, hard_surface

    def turret(bm):
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=0.6, radius2=0.5, depth=0.8)
        bmesh.ops.translate(bm, vec=(0, 0, 0.6), verts=bmesh.ops.create_cube(bm, size=0.5)["verts"])

    def highpoly(obj):
        bevel = obj.modifiers.new("Bevel", "BEVEL")
        bevel.width, bevel.segments, bevel.limit_method = 0.05, 4, "ANGLE"
        obj.modifiers.new("Subdivision", "SUBSURF").levels = 2
        for p in obj.data.polygons:
            p.use_smooth = True
        return obj

    low = row.add(mesh("Turret", turret, row.mat, uvs=False), "Low-poly + baked normals")
    row.add(highpoly(mesh("TurretPreview", turret, row.mat, uvs=False)), "High-poly (hidden on low)")
    high = highpoly(mesh("Turret_high", turret, uvs=False))
    row.collection.objects.link(high)
    high.location = low.location
    hard_surface.prep_mesh(low, config, math.radians(30), bevel=False)
    hard_surface.add_modifiers(low, 0)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)  # bake.path is relative to the .blend
    note = bake.bake_normals(low, [high], config)
    high.hide_set(True)
    image = bpy.data.images[f"{low.name}_N"]
    image.colorspace_settings.name = "Non-Color"
    tree = low.data.materials[0].node_tree
    tex, nmap = tree.nodes.new("ShaderNodeTexImage"), tree.nodes.new("ShaderNodeNormalMap")
    tex.image, nmap.uv_map = image, low.data.uv_layers[0].name
    tree.links.new(tex.outputs["Color"], nmap.inputs["Color"])
    tree.links.new(nmap.outputs["Normal"], tree.nodes["Principled BSDF"].inputs["Normal"])
    return note


def build_export(row, config):
    from blender_asset_validator.operations import lod
    def barrel_shape(bm):  # enough geometry that LOD3, at 10 %, is still a barrel
        cylinder(48, depth=1.2, tris=False)(bm)
        bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1], cuts=7)
        for v in bm.verts:
            v.co.xy *= 1 + 0.12 * math.cos(v.co.z * 2.4)
    barrel = row.add(mesh("Barrel", barrel_shape, row.mat), "LODs, UCX, socket")
    for p in barrel.data.polygons:
        p.use_smooth = abs(p.normal.z) < 0.5
    collision = mesh("UCX_Barrel_01", cylinder(8, depth=1.25, radius=0.55))
    row.collection.objects.link(collision)
    collision.location, collision.display_type = barrel.location, "WIRE"
    socket = bpy.data.objects.new("SOCKET_Barrel_Top", None)
    row.collection.objects.link(socket)
    socket.parent, socket.location, socket.empty_display_type = barrel, (0, 0, 0.7), "ARROWS"
    lod.generate_lods([barrel], config)
    for obj in lod.lods_of(barrel):
        row.collection.objects.link(obj)
        obj.hide_set(False)
        obj.location = row.slot(obj.name.replace("Barrel_", ""))


def build_heatmaps(row, config):
    from blender_asset_validator.operations import heatmap
    wavy = then(grid(10, 0.9), lambda bm: [setattr(v.co, "z", 0.15 * math.sin(7 * v.co.x) * math.sin(5 * v.co.y + 3 * v.co.x)) for v in bm.verts])
    heatmap.show_heatmap(row.add(mesh("HeatWarp", wavy, row.mat), "Heatmap: Quad Warp"), "WARP", config)
    slivers = row.add(mesh("HeatSlivers", cylinder(160, depth=0.6, radius=0.6), row.mat), "Heatmap: Triangle Quality")  # fan caps: slivers
    heatmap.show_heatmap(slivers, "TRI_QUALITY", config)
    sphere = mesh("HeatStretch", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.6, calc_uvs=True), row.mat, smooth=True)
    heatmap.show_heatmap(row.add(sphere, "Heatmap: UV Stretch"), "UV_STRETCH", config)


def aim(cam, objects, tilt=50.0, fill=0.95):
    """Camera looking down the rows at `tilt`, as close as it gets with every object in frame."""
    corners = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    center = Vector([(min(c[i] for c in corners) + max(c[i] for c in corners)) / 2 for i in range(3)])
    rot = Euler((math.radians(tilt), 0, 0)).to_quaternion()
    scene = bpy.context.scene
    tx = cam.data.sensor_width / 2 / cam.data.lens
    ty = tx * scene.render.resolution_y / scene.render.resolution_x
    inv = rot.inverted()
    d = max(max(p.z + abs(p.x) / (tx * fill), p.z + abs(p.y) / (ty * fill)) for p in (inv @ (c - center) for c in corners))
    cam.rotation_euler = rot.to_euler()
    cam.location = center + rot @ Vector((0, 0, d))


def self_check(expected, results, tools):
    found = {}
    for r in results:
        found.setdefault(r.object_name, set()).add((r.check_name, r.severity.value))
    failures = [f for f in tools if f]
    for obj, check in expected:
        got = found.get(obj.name, set())
        if check is None and any(s == "ERROR" for _, s in got) or check is not None and check not in {c for c, _ in got}:
            failures.append(f"{obj.name}: expected {check or 'no error'}, got {sorted(got)}")
    lines = [f"SHOWROOM FAIL {f}" for f in failures] or [f"SHOWROOM OK: {len(expected)} check stations, {len(tools)} tool stations"]
    with open(os.path.splitext(OUT)[0] + "_check.txt", "w", encoding="utf-8") as log:  # the Store's Blender drops stdout
        log.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if failures:
        raise SystemExit(1)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0  # it saves twice (the bake needs a path): no .blend1
    bav.register()
    from blender_asset_validator.core import engine
    scene = bpy.context.scene
    scene.asset_validator_engine = "unreal"
    # The project's own rules, read from next to the .blend: a showroom lays its assets out across the scene
    with open(os.path.join(os.path.dirname(OUT), engine.PROJECT_CONFIG), "w", encoding="utf-8") as f:
        json.dump({"transforms": {"check_location": False}}, f, indent=2)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    config = engine.load_config()
    scene.world = bpy.data.worlds.new("Showroom")
    scene.world.color = (0.18, 0.19, 0.21)

    row = Row("01 Checks", (0.8, 0.45, 0.35), 0.0)
    expected = build_checks(row)
    row = Row("02 Hard Surface", (0.55, 0.6, 0.7), row.below())
    prepped, unwrapped = build_hard_surface(row, config)
    row = Row("03 Topology", (0.5, 0.7, 0.5), row.below())
    cleaned, retopo = build_topology(row, config)
    row = Row("04 LODs", (0.75, 0.7, 0.45), row.below())
    lods = build_lods(row, config)
    row = Row("05 Bake", (0.6, 0.6, 0.62), row.below())
    bake_note = build_bake(row, config)
    row = Row("06 Export", (0.7, 0.5, 0.35), row.below())
    build_export(row, config)
    row = Row("07 Heatmaps", (0.7, 0.7, 0.7), row.below())
    build_heatmaps(row, config)

    cam = bpy.data.objects.new("ShowroomCam", bpy.data.cameras.new("ShowroomCam"))
    scene.collection.objects.link(cam)
    bpy.context.view_layer.update()  # matrix_world follows the new locations only after an update
    aim(cam, [o for o in scene.objects if o.type in ("MESH", "FONT") and o.visible_get()])
    scene.camera = cam
    for obj in scene.objects:
        obj.select_set(False)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))

    tools = [
        None if {m.type for m in prepped.modifiers} >= {"BEVEL", "WEIGHTED_NORMAL"} and prepped.data.uv_layers else "Prep: no Bevel, WN or UVs",
        None if unwrapped.data.uv_layers else "Auto Unwrap: no UVs",
        None if len(cleaned.data.polygons) < 1280 else "Clean Topology: nothing merged",
        None if sum(len(p.vertices) == 4 for p in retopo.data.polygons) > len(retopo.data.polygons) / 2 else "Retopologize: not quads",
        None if len(lods) == 3 else f"LODs: {len(lods)}",
        None if "_N.png" in bake_note else f"Bake: {bake_note}",
    ]
    self_check(expected, engine.run_validation(config, [obj for obj, _ in expected]), tools)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print(f"Saved {OUT}")


main()
