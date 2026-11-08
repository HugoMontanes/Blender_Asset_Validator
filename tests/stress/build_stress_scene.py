"""Builds tests/stress/StressTest.blend: meshes made to push the add-on to its limits, from 80 triangles to
5M, the modifier stacks and naming an artist really ships, and real models (test_assets/: Poly Haven CC0,
Stanford, the earlier FBX/OBJ). Each case says what an artist expects from the add-on; run_stress.py runs
every tool on each case and compares. The case list also goes to StressTest_manifest.json.
    blender -b --factory-startup --python-exit-code 1 --python tests/stress/build_stress_scene.py

Case fields: expect = checks that should fire, forbid = checks that must not (false positives),
artist_ok = fires but is intended (an artist would accept it), gap = what an artist expects that no check
covers yet, tools = which run_stress.py runs ("auto" picks by size)."""
import json
import math
import os
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ASSETS = os.path.join(REPO, "test_assets")
OUT = os.path.join(HERE, "StressTest.blend")
sys.path.insert(0, REPO)
import blender_asset_validator as bav  # noqa: E402

CASES = []
GAP = 1.5


def material(name, color=(0.6, 0.6, 0.6)):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1)
    mat.diffuse_color = (*color, 1)
    return mat


DEFAULT = None


def from_bm(name, fill, mat="default", smooth=False, uvs=True):
    bm = bmesh.new()
    if uvs:
        bm.loops.layers.uv.new("UVMap")
    fill(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return finish(name, me, mat, smooth)


def from_arrays(name, co, faces, uv=None, mat="default", smooth=False):
    """Fast path for big meshes: co (n,3), faces (m,k) equal-sided, uv per corner (m*k,2)."""
    faces = np.asarray(faces, np.int32)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(co))
    me.vertices.foreach_set("co", np.asarray(co, np.float32).ravel())
    k = faces.shape[1]
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, k, dtype=np.int32))
    me.update(calc_edges=True)
    if uv is not None:
        me.uv_layers.new(name="UVMap").data.foreach_set("uv", np.asarray(uv, np.float32).ravel())
    return finish(name, me, mat, smooth)


def finish(name, me, mat, smooth):
    if mat == "default":
        mat = DEFAULT
    if mat is not None:
        me.materials.append(mat)
    me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
    obj = bpy.data.objects.new(name, me)
    return obj


def grid_arrays(nu, nv, closed_u=False):
    """Quad faces and per-corner UVs of an nu x nv quad grid ((nu+1) x (nv+1) vertices, or nu columns if closed_u)."""
    cols = nu if closed_u else nu + 1
    i, j = np.meshgrid(np.arange(nu), np.arange(nv), indexing="ij")
    i, j = i.ravel(), j.ravel()
    i1 = (i + 1) % cols if closed_u else i + 1
    faces = np.stack([j * cols + i, j * cols + i1, (j + 1) * cols + i1, (j + 1) * cols + i], 1)
    u = np.stack([i, i + 1, i + 1, i], 1) / nu
    v = np.stack([j, j, j + 1, j + 1], 1) / nv
    return cols, faces, np.stack([u.ravel(), v.ravel()], 1)


def plane(name, nu, nv, sx, sy, z=None, mat="default", uv_scale=1.0):
    cols, faces, uv = grid_arrays(nu, nv)
    x, y = np.meshgrid(np.linspace(-sx / 2, sx / 2, nu + 1), np.linspace(-sy / 2, sy / 2, nv + 1))
    co = np.stack([x.ravel(), y.ravel(), np.zeros(x.size) if z is None else z(x, y).ravel()], 1)
    return from_arrays(name, co, faces, uv * uv_scale, mat)


def rock(name, subdivisions, radius=1.0, seed=0, mat="default"):
    def fill(bm):  # past 9 subdivisions: past that, split every edge once more per level
        bmesh.ops.create_icosphere(bm, subdivisions=min(subdivisions, 9), radius=radius, calc_uvs=True)
        for _ in range(subdivisions - 9):
            bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
    obj = from_bm(name, fill, mat, smooth=True)
    co = np.empty(len(obj.data.vertices) * 3, np.float32)
    obj.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    n = co / np.linalg.norm(co, axis=1, keepdims=True)
    rng = np.random.default_rng(seed)
    bump = sum(a * np.sin(f * n @ rng.normal(size=3) + rng.uniform(0, 6)) for a, f in ((0.12, 3), (0.05, 9), (0.015, 31)))
    obj.data.vertices.foreach_set("co", (co * (1 + bump)[:, None]).ravel())
    obj.data.update()
    return obj


def cyl(segments=16, depth=1.0, radius=0.5, caps=True, tris=False):
    return lambda bm: bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=tris, segments=segments, radius1=radius,
                                            radius2=radius, depth=depth, calc_uvs=True)


def cube(size=1.0):
    return lambda bm: bmesh.ops.create_cube(bm, size=size, calc_uvs=True)


def then(fill, edit):
    def run(bm):
        fill(bm)
        for seq in (bm.verts, bm.edges, bm.faces):
            seq.ensure_lookup_table()
        edit(bm)
    return run


class Row:
    def __init__(self, title, y):
        self.collection = bpy.data.collections.new(title)
        bpy.context.scene.collection.children.link(self.collection)
        self.x, self.y, self.depth = 0.0, y, 0.0

    def place(self, obj, width=None, depth=None):
        bpy.context.view_layer.update()
        dims = obj.dimensions
        w = width if width is not None else max(dims.x, 0.2)
        self.x += w / 2
        obj.location.x += self.x
        obj.location.y += self.y
        self.x += w / 2 + GAP
        self.depth = max(self.depth, depth if depth is not None else dims.y)

    def add(self, obj, intent, expect=(), forbid=(), artist_ok=(), gap="", tools="auto", extra=(), select=None, place=True, on=None):
        """One case: `obj` is placed and linked; `extra` are linked only; `select` (names) is the validation set."""
        for o in (obj, *extra):
            if o.name not in self.collection.objects:  # tools need theirs in the view layer first
                self.collection.objects.link(o)
        if place:
            self.place(obj)
            for e in extra:
                if e.parent is None:
                    e.location.x += obj.location.x
                    e.location.y += obj.location.y
        CASES.append({
            "name": obj.name, "row": self.collection.name, "intent": intent,
            "select": select or [obj.name], "objects": [obj.name, *(e.name for e in extra)],
            "on": on, "expect": list(expect), "forbid": list(forbid), "artist_ok": list(artist_ok), "gap": gap, "tools": tools,
        })
        return obj

    def below(self, extra=GAP * 2):
        return self.y - self.depth - extra


# --------------------------------------------------------------------------------------------- 01

def row_budget(row):
    for name, sub in (("RockTiny", 2), ("RockGame", 5), ("RockHero", 7)):
        obj = rock(name, sub)
        tris = 20 * 4 ** (sub - 1)  # bmesh's icosphere: 20 * 4^(n-1) faces
        row.add(obj, f"Displaced icosphere, {tris:,} tris", expect=["polycount"] if tris > 50000 else [],
                forbid=[] if tris > 50000 else ["polycount"])
    row.add(rock("Rock1M", 9, radius=2.0), "Scan-sized rock, 1.31M tris: every check and tool at scan scale",
            expect=["polycount"], tools=["validate", "fix_all", "lods", "export"])
    t = time.perf_counter()
    row.add(rock("Rock5M", 10, radius=3.0), "ZBrush-export-sized rock, 5.24M tris: where does it break",
            expect=["polycount"], tools=["validate", "fix_all", "lods"])
    print(f"Rock5M built in {time.perf_counter() - t:.1f}s")
    # 125 x 200 quads = 50,000 tris: exactly on budget, must pass; one more quad row goes over
    row.add(plane("BudgetExact", 125, 200, 2.5, 4.0), "Exactly 50,000 tris = the budget: must pass", forbid=["polycount"])
    row.add(plane("BudgetOver", 125, 201, 2.5, 4.02), "50,250 tris: just over budget", expect=["polycount"])

    sub = from_bm("SubDUnapplied", cube(1.0), smooth=True)
    sub.modifiers.new("Subdivision", "SUBSURF").levels = 6  # 6 faces * 4^6 = 24,576 quads... x2 tris = 49k
    sub.modifiers["Subdivision"].render_levels = 7
    row.add(sub, "Cube + Subdivision 6 viewport / 7 render, unapplied: 49k tris in the viewport, 196k on render",
            forbid=["polycount"], gap="Polycount reads the viewport level; an exporter or baker reading render levels gets 4x the triangles")

    ground = plane("GrassScatter", 20, 20, 4, 4)
    ground.modifiers.new("Scatter", "NODES").node_group = scatter_group()
    row.add(ground, "800 tris of mesh data + a Geometry Nodes scatter of 6,000 realized pebbles (~480k tris)",
            expect=["polycount"], gap="Checks that read obj.data (ngons, normals, UVs...) never see the scattered pebbles")


def scatter_group():
    group = bpy.data.node_groups.new("StressScatter", "GeometryNodeTree")
    group.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, link = group.nodes, group.links.new
    gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    dist, inst = n.new("GeometryNodeDistributePointsOnFaces"), n.new("GeometryNodeInstanceOnPoints")
    ico, real, join = n.new("GeometryNodeMeshIcoSphere"), n.new("GeometryNodeRealizeInstances"), n.new("GeometryNodeJoinGeometry")
    dist.inputs["Density"].default_value = 375.0  # 16 m2 -> ~6,000 points
    ico.inputs["Radius"].default_value, ico.inputs["Subdivisions"].default_value = 0.02, 2
    link(gin.outputs[0], dist.inputs["Mesh"])
    link(dist.outputs["Points"], inst.inputs["Points"])
    link(ico.outputs["Mesh"], inst.inputs["Instance"])
    link(inst.outputs["Instances"], real.inputs["Geometry"])
    link(gin.outputs[0], join.inputs["Geometry"])
    link(real.outputs["Geometry"], join.inputs["Geometry"])
    link(join.outputs["Geometry"], gout.inputs[0])
    return group


# --------------------------------------------------------------------------------------------- 02

def row_modifiers(row):
    half = from_bm("MirrorOpenSeam", then(cyl(24, 1.2, 0.5), lambda bm: bmesh.ops.delete(
        bm, geom=[v for v in bm.verts if v.co.x < -1e-4], context="VERTS")))
    m = half.modifiers.new("Mirror", "MIRROR")
    m.use_clip, m.use_mirror_merge = False, False
    row.add(half, "Half a cylinder + Mirror without Merge: the exported mesh is open down the middle",
            gap="No check sees the open seam or the doubled centre vertices the Mirror leaves (they read obj.data)")

    cutter = from_bm("BooleanCutter", cyl(32, 2.0, 0.3), mat=None)
    cutter.display_type = "WIRE"
    boxed = from_bm("BooleanUnapplied", cube(1.0))
    b = boxed.modifiers.new("Boolean", "BOOLEAN")
    b.object, b.operation = cutter, "DIFFERENCE"
    cutter.parent = boxed
    row.add(boxed, "Cube with an unapplied Boolean: the export has a 32-gon and slivers, obj.data is a clean cube",
            expect=["ngons"], extra=[cutter], select=["BooleanUnapplied", "BooleanCutter"], on="BooleanUnapplied",
            gap="Cutter objects get validated and exported as assets; ngon/sliver checks read the cube, not the boolean result")

    solid = plane("SolidifyZero", 4, 4, 1, 1)
    solid.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.0
    row.add(solid, "Solidify with thickness 0: two coincident shells in the export (z-fighting, zero-volume)",
            gap="Coincident shells / z-fighting isn't detected (phase 4 lists it)")

    plank = from_bm("ArrayOverlap", cube(1.0))
    plank.data.transform(np.diag([1.0, 0.2, 0.05, 1.0]).tolist())
    a = plank.modifiers.new("Array", "ARRAY")
    a.count, a.relative_offset_displace = 6, (0.5, 0, 0)
    row.add(plank, "Array with relative offset 0.5: planks interpenetrate and coplanar faces overlap",
            gap="Self-intersection and coplanar overlap aren't detected")

    neg = from_bm("NegativeScale", cube(1.0))
    neg.scale = (-1, 1, 1)
    row.add(neg, "Mirrored by scale -1: unapplied, and applying it later flips every face", expect=["transforms"])

    inside = from_bm("InsideOut", then(cube(1.0), lambda bm: bmesh.ops.reverse_faces(bm, faces=bm.faces[:])))
    row.add(inside, "A closed box with every face flipped (what applying a negative scale leaves)", expect=["normals"])

    keys = rock("ShapeKeys", 3)
    keys.shape_key_add(name="Basis")
    sk = keys.shape_key_add(name="Squash")
    for p in sk.data:
        p.co.z *= 0.5
    row.add(keys, "Rock with shape keys: do LODs / Clean Topology / Retopologize / Fix keep them?",
            gap="Tools may drop shape keys without saying so")

    skinned = skinned_arm()
    row.add(skinned[0], "Arm skinned to a bent armature: the export is the posed mesh", extra=skinned[1:],
            select=[skinned[0].name], gap="LODs bake the pose and drop the Armature (known, phase 5); nothing warns at validation")

    disp = plane("DisplaceUnapplied", 40, 40, 2, 2)
    tex = bpy.data.textures.new("StressClouds", "CLOUDS")
    tex.noise_scale = 0.15
    d = disp.modifiers.new("Displace", "DISPLACE")
    d.texture, d.strength = tex, 1.2
    row.add(disp, "Flat grid + strong Displace: the export folds over itself, obj.data is flat",
            gap="Folded/self-intersecting evaluated geometry isn't detected; the topology checks read the flat grid")


def skinned_arm():
    arm_data = bpy.data.armatures.new("ArmRig")
    rig = bpy.data.objects.new("ArmRig", arm_data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    upper = arm_data.edit_bones.new("Upper")
    upper.head, upper.tail = (0, 0, 0), (0, 0, 1)
    lower = arm_data.edit_bones.new("Lower")
    lower.head, lower.tail, lower.parent = (0, 0, 1), (0, 0, 2), upper
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.scene.collection.objects.unlink(rig)
    rig.pose.bones["Lower"].rotation_mode = "XYZ"
    rig.pose.bones["Lower"].rotation_euler = (math.radians(80), 0, 0)
    arm = from_bm("SkinnedArm", lambda bm: (cyl(12, 2.0, 0.2)(bm), bmesh.ops.translate(bm, vec=(0, 0, 1), verts=bm.verts),
                                            bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1], cuts=11)),
                  smooth=True)
    for bone in ("Upper", "Lower"):
        arm.vertex_groups.new(name=bone)
    for v in arm.data.vertices:
        w = min(max(v.co.z - 0.6, 0.0) / 0.8, 1.0)
        arm.vertex_groups["Upper"].add([v.index], 1 - w, "REPLACE")
        arm.vertex_groups["Lower"].add([v.index], w, "REPLACE")
    arm.modifiers.new("Armature", "ARMATURE").object = rig
    arm.parent = rig
    return arm, rig


# --------------------------------------------------------------------------------------------- 03

def row_hard_surface(row, config):
    from blender_asset_validator.operations import hard_surface
    golden = from_bm("CrateGolden", then(cube(1.0), lambda bm: bmesh.ops.inset_individual(bm, faces=bm.faces[:], thickness=0.08, depth=-0.03)), uvs=False)
    row.collection.objects.link(golden)
    hard_surface.prep_mesh(golden, config, math.radians(30), bevel=True)
    hard_surface.add_modifiers(golden, 2)
    row.add(golden, "The add-on's own Prep + Bevel 2 + Weighted Normal output: an artist expects it to pass clean",
            forbid=["*error", "uvs", "uv_layout", "shading", "topology"])

    panel = from_bm("BooleanPanel", cube(1.0))
    cutter = from_bm("PanelCutter", lambda bm: [bmesh.ops.translate(bm, vec=(x, y, 0), verts=bmesh.ops.create_cone(
        bm, cap_ends=True, segments=24, radius1=0.08, radius2=0.08, depth=2)["verts"]) for x in (-0.25, 0.25) for y in (-0.25, 0, 0.25)], mat=None)
    b = panel.modifiers.new("Boolean", "BOOLEAN")
    b.object = cutter
    bpy.context.scene.collection.objects.link(cutter)
    bpy.context.scene.collection.objects.link(panel)
    bpy.context.view_layer.update()
    evaluated = bpy.data.meshes.new_from_object(panel.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    for o in (panel, cutter):
        bpy.context.scene.collection.objects.unlink(o)
    panel.modifiers.clear()
    old, panel.data = panel.data, evaluated
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(cutter)
    panel.name = panel.data.name = "BooleanPanel"
    row.add(panel, "Applied boolean: 6 holes through a cube, ngon faces and long slivers as Blender leaves them",
            expect=["ngons"], artist_ok=["topology"])

    def bolts(bm):
        rng = np.random.default_rng(1)
        for _ in range(3000):
            r = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=8, radius1=0.01, radius2=0.01, depth=0.02)
            bmesh.ops.translate(bm, vec=tuple(rng.uniform(-0.5, 0.5, 3)), verts=r["verts"])
    row.add(from_bm("Bolts3000", bolts), "3,000 loose 8-sided bolts in one mesh (like the Audi's 11k parts): 96k tris",
            expect=["polycount"], tools="all")

    body = from_bm("WeaponBody", cube(1.0))
    body.data.transform(np.diag([1.2, 0.2, 0.3, 1.0]).tolist())
    parts = []
    for i, (name, loc, rot) in enumerate((("WeaponSlide", (0.1, 0, 0.25), 0), ("WeaponTrigger", (-0.1, 0, -0.2), 15),
                                          ("WeaponHammer", (-0.55, 0, 0.25), -30), ("WeaponMag", (-0.35, 0, -0.4), 8))):
        part = from_bm(name, cube(0.2))
        part.parent, part.location, part.rotation_euler = body, loc, (0, math.radians(rot), 0)
        parts.append(part)
    row.add(body, "Gun body + 4 parented moving parts with their pivots rotated, as they come from an FBX",
            expect=["transforms"], extra=parts, select=["WeaponBody", *(p.name for p in parts)],
            gap="Child rotations are pivots of moving parts: applying them breaks the rig; the error can't be accepted")

    row.add(from_bm("ThinPanel", lambda bm: (cube(1.0)(bm), bmesh.ops.scale(bm, vec=(1, 1, 0.0005), verts=bm.verts))),
            "1 m panel 0.5 mm thick: Clean Topology / LODs / bake cage on a wafer", forbid=["*error"], tools="all")

    tri = from_bm("CustomNormalsTris", cyl(32, 1.0, 0.4, tris=True), smooth=True)
    bm = bmesh.new()
    bm.from_mesh(tri.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(tri.data)
    bm.free()
    tri.data.normals_split_custom_set_from_vertices([v.co.normalized()[:] for v in tri.data.vertices])
    row.add(tri, "All triangles + custom normals, as an FBX from Max/Maya arrives", forbid=["*error"])

    cols, faces, uv = grid_arrays(16, 2000, closed_u=True)
    a = np.linspace(0, 2 * math.pi, 16, endpoint=False)
    z = np.linspace(0, 100, 2001)
    co = np.stack([np.tile(0.05 * np.cos(a), 2001), np.tile(0.05 * np.sin(a), 2001), np.repeat(z, 16)], 1)
    pipe = from_arrays("Pipe100m", co, faces, uv * [1, 50], smooth=True)
    pipe.rotation_euler.y = math.radians(90)
    row.add(pipe, "100 m pipe 10 cm wide, 64k tris: LOD deviation measured against a 100 m diagonal",
            expect=["polycount", "transforms"], gap="LOD deviation in % of the diagonal lets a long thin pipe collapse (known limit)")


# --------------------------------------------------------------------------------------------- 04

def row_organic(row):
    scan = rock("ScanDirty", 8, radius=1.5, seed=3)
    bm = bmesh.new()
    bm.from_mesh(scan.data)
    bm.faces.ensure_lookup_table()
    rng = np.random.default_rng(2)
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in rng.choice(len(bm.faces), 150, replace=False)], context="FACES_ONLY")
    bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.calc_center_median().z > 1.3])
    for p in rng.uniform(-1, 1, (40, 3)):
        bm.verts.new(p)
    bm.to_mesh(scan.data)
    bm.free()
    row.add(scan, "Raw photogrammetry: 327k tris, 150 holes, a flipped cap, 40 floating vertices",
            expect=["polycount", "normals", "manifold"], tools="all")

    row.add(from_bm("SculptPoles", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=0.6, calc_uvs=True), smooth=True),
            "UV sphere: two 64-edge poles on a smooth surface", expect=["topology"])

    head = from_bm("CharacterMirroredUV", lambda bm: (bmesh.ops.create_cube(bm, size=1.0),
                                                       bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=6, use_grid_fill=True)), smooth=True)
    for v in head.data.vertices:
        v.co = v.co.normalized() * 0.5
    mirror_uvs(head)
    row.add(head, "Character-style head with the left half's UVs mirrored on the right (stacked on purpose)",
            artist_ok=["uvs"], gap="Mirrored/stacked UVs are standard practice; the overlap warning can't tell them from a mistake (UV offset +1 convention)")


def mirror_uvs(obj):
    me = obj.data
    uv = me.uv_layers.new(name="UVMap") if not me.uv_layers else me.uv_layers[0]
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (0.05 + 0.9 * abs(co.x) * 2 * 0.5, 0.05 + 0.9 * (co.z + 0.5))


# --------------------------------------------------------------------------------------------- 05

def row_environment(row):
    row.add(plane("WallTrim", 8, 6, 4, 3, mat=material("Trim_Metal", (0.5, 0.5, 0.55)), uv_scale=1.0),
            "4x3 m wall mapped to a trim sheet (material named Trim_*): UVs may leave 0-1", forbid=["uv_layout"])
    wt = CASES[-1]
    obj = bpy.data.objects[wt["name"]]
    uv = obj.data.uv_layers[0]
    for d in uv.data:
        d.uv = (d.uv.x, 2.0 + d.uv.y * 0.12)
    row.add(plane("FloorTiling", 20, 20, 10, 10, mat=material("M_Concrete", (0.4, 0.4, 0.4)), uv_scale=20.0),
            "10x10 m floor tiling 20x, material M_Concrete (doesn't match the tiling regex)", expect=["uv_layout"],
            artist_ok=["uv_layout"], gap="Only the material name says 'tiling'; a 'repeats' flag per material would be explicit")

    udim = from_bm("PropUDIM", cube(1.0))
    udim.data.materials.clear()
    udim.data.materials.append(udim_material())
    for i, d in enumerate(udim.data.uv_layers[0].data):
        d.uv = (d.uv.x * 0.3 + (i // 4) % 3, d.uv.y * 0.9)  # each face in tile 1001, 1002 or 1003
    row.add(udim, "UDIM prop: faces spread over tiles 1001-1003", forbid=["uv_layout", "materials"])

    lm = from_bm("LightmapOverlap", cube(1.0))
    layer = lm.data.uv_layers.new(name="Lightmap")
    layer.data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1] * len(lm.data.polygons))  # every face on the same square
    row.add(lm, "UV1 copied from a stacked UV0: the lightmap overlaps", expect=["lightmap_uv"])

    terrain = plane("Terrain1km", 250, 250, 1000, 1000, z=lambda x, y: 25 * np.sin(x / 90) * np.cos(y / 70))
    row.add(terrain, "1 km terrain, 125k tris, UVs 0-1: texel density 2 px/m", expect=["polycount", "uv_layout"], tools="auto",
            place=False)
    terrain.location = (0, row.y - 600, -30)

    row.add(from_bm("Screw1mm", cyl(12, 0.003, 0.001)), "A 1 mm screw: scale off by 100 (cm vs m)?",
            gap="No absurd-size check (bbox < 1 cm or > 1 km: phase 3)")
    far = from_bm("FarFromOrigin", cube(1.0))
    far.data.transform(((1, 0, 0, 10000), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    row.add(far, "Location applied, but the geometry sits 10 km from the pivot", place=False,
            gap="Pivot far from the geometry (and float precision at 10 km) isn't reported once location is applied")
    far.location = (-10000 + row.x, row.y, 0)
    row.x += 2.5

    palette = from_bm("PaletteUV", cube(1.0))
    for i, d in enumerate(palette.data.uv_layers[0].data):
        d.uv = (0.1 + 0.2 * (i // 4 % 4) + d.uv.x * 1e-5, 0.1 + d.uv.y * 1e-5)
    row.add(palette, "Palette texture: each face's UVs collapsed into one swatch", forbid=["uv_layout", "uvs"])

    zero = from_bm("UVAllZero", cube(1.0))
    zero.data.uv_layers[0].data.foreach_set("uv", [0.0] * 2 * len(zero.data.loops))
    row.add(zero, "UV map present but every UV at (0,0): unwrapped never", gap="A UV map with no area at all isn't reported as 'not unwrapped'")

    nan = from_bm("UVNaN", cube(1.0))
    nan.data.uv_layers[0].data[0].uv = (float("nan"), 0.5)
    row.add(nan, "One NaN UV (a broken importer): every UV check must survive it", expect=[])

    huge = from_bm("UVHuge", cube(1.0))
    for d in huge.data.uv_layers[0].data:
        d.uv = (d.uv.x + 1e6, d.uv.y - 1e6)
    row.add(huge, "UVs at 1,000,000: float32 precision", expect=["uv_layout"])

    multi = rock("EightUVMaps", 3)
    for i in range(7):
        multi.data.uv_layers.new(name=f"UV{i + 1}")
    row.add(multi, "8 UV maps (Blender's max): GPU vertex cost and lightmap = UV1", forbid=["*error"])

    missing = from_bm("MissingTexture", cube(1.0), mat=texture_material("M_MissingTex", "//textures/T_DoesNotExist_D.png"))
    row.add(missing, "Material pointing at a texture file that isn't there", expect=["materials"])


def udim_material():
    mat = material("M_PropUDIM")
    folder = os.path.join(HERE, "textures")
    os.makedirs(folder, exist_ok=True)
    for number in (1001, 1002, 1003):  # one PNG per tile on disk; loading the first as TILED finds the rest
        tile = bpy.data.images.new(f"tile{number}", 64, 64)
        tile.pixels.foreach_set(np.tile([number % 10 / 3, 0.4, 0.6, 1.0], 64 * 64).astype(np.float32))
        tile.filepath_raw, tile.file_format = os.path.join(folder, f"T_PropUDIM.{number}.png"), "PNG"
        tile.save()
        bpy.data.images.remove(tile)
    image = bpy.data.images.load(os.path.join(folder, "T_PropUDIM.1001.png"))
    image.source = "TILED"
    image.name = "T_PropUDIM"
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    mat.node_tree.links.new(node.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    return mat


def texture_material(name, path):
    mat = material(name)
    image = bpy.data.images.new(name.replace("M_", "T_"), 4, 4)
    image.source, image.filepath = "FILE", path
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    return mat


# --------------------------------------------------------------------------------------------- 06

def row_foliage(row):
    rng = np.random.default_rng(4)
    n = 5000
    base = rng.uniform(-2, 2, (n, 2))
    ang = rng.uniform(0, math.pi, n)
    h = rng.uniform(0.15, 0.35, n)
    co, faces, uv = [], [], []
    for k, extra in enumerate((0.0, math.pi / 2)):  # two crossed quads per tuft
        dx, dy = 0.08 * np.cos(ang + extra), 0.08 * np.sin(ang + extra)
        quad = np.stack([
            np.stack([base[:, 0] - dx, base[:, 1] - dy, np.zeros(n)], 1), np.stack([base[:, 0] + dx, base[:, 1] + dy, np.zeros(n)], 1),
            np.stack([base[:, 0] + dx, base[:, 1] + dy, h], 1), np.stack([base[:, 0] - dx, base[:, 1] - dy, h], 1)], 1)
        co.append(quad.reshape(-1, 3))
    co = np.concatenate(co)
    faces = np.arange(len(co)).reshape(-1, 4)
    uv = np.tile([[0, 0], [1, 0], [1, 1], [0, 1]], (len(faces), 1))
    row.add(from_arrays("GrassCards", co, faces, uv, mat=material("M_Grass_Alpha", (0.3, 0.6, 0.2))),
            "5,000 crossed-quad grass tufts (20k tris) all sharing one card texture", artist_ok=["uvs"],
            gap="Foliage cards share UV space on purpose: the overlap warning fires on every foliage asset")

    leaf = plane("LeavesTwoSided", 1, 1, 0.4, 0.6, mat=material("M_Leaf_Alpha", (0.25, 0.5, 0.2)))
    verts, faces = [v.co[:] for v in leaf.data.vertices], [list(p.vertices) for p in leaf.data.polygons]
    leaf.data.clear_geometry()
    leaf.data.from_pydata(verts, [], faces + [f[::-1] for f in faces])
    leaf.data.uv_layers.new(name="UVMap")
    row.add(leaf, "Leaf card duplicated and flipped for two-sided shading (a classic foliage trick)",
            expect=["mesh_data"], artist_ok=["mesh_data"],
            gap="Fix (Blender's validate) deletes the back face: the leaf goes one-sided with no warning")

    trunk = from_bm("TreeJoined", cyl(10, 3.0, 0.15), mat=material("M_Bark", (0.35, 0.25, 0.15)))
    trunk.data.materials.append(material("M_Leaf_Alpha"))
    bm = bmesh.new()
    bm.from_mesh(trunk.data)
    uvl = bm.loops.layers.uv.active
    for _ in range(400):
        p = rng.normal(0, 0.6, 3)
        p[2] = abs(p[2]) + 1.2
        s = 0.15
        vs = [bm.verts.new(p + o) for o in ((-s, 0, -s), (s, 0, -s), (s, 0, s), (-s, 0, s))]
        f = bm.faces.new(vs)
        f.material_index = 1
        for loop, c in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            loop[uvl].uv = c
    bm.to_mesh(trunk.data)
    bm.free()
    row.add(trunk, "Trunk + 400 leaf cards in one mesh, two materials (bark, alpha leaves)", artist_ok=["uvs", "uv_layout"])


# --------------------------------------------------------------------------------------------- 07

def row_robustness(row):
    row.add(bpy.data.objects.new("EmptyMesh", bpy.data.meshes.new("EmptyMesh")), "A mesh with nothing in it", tools="all")
    pts = bpy.data.meshes.new("PointsOnly")
    pts.from_pydata([tuple(p) for p in np.random.default_rng(5).uniform(-0.5, 0.5, (100, 3))], [], [])
    row.add(bpy.data.objects.new("PointsOnly", pts), "100 vertices, no edges or faces (a point cloud)", expect=["manifold"], tools="all")
    wire = bpy.data.meshes.new("EdgesOnly")
    wire.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1), (1, 2), (2, 3), (3, 0)], [])
    row.add(bpy.data.objects.new("EdgesOnly", wire), "A wire square: edges, no faces", expect=["manifold"], tools="all")
    row.add(from_arrays("SingleTriangle", [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)], [(0, 0), (1, 0), (0, 1)]),
            "One triangle", tools="all")
    nanv = from_bm("NaNVertex", cube(1.0))
    nanv.data.vertices[0].co = (float("nan"), 0, 0)
    row.add(nanv, "One NaN vertex (a broken import): nothing may crash", gap="NaN/inf coordinates aren't reported", tools="all")

    many = from_bm("Materials64", lambda bm: bmesh.ops.create_grid(bm, x_segments=8, y_segments=8, size=1, calc_uvs=True), mat=None)
    for i in range(64):
        many.data.materials.append(None if i in (5, 17, 40) else material(f"M_Slot{i:02d}", (i / 64, 0.5, 1 - i / 64)))
    for p in many.data.polygons:
        p.material_index = p.index % 10
    row.add(many, "64 material slots: 3 empty, 51 used by no face (64 draw calls if it exported)", expect=["materials"],
            gap="Material count against a draw-call budget, and slots no face uses, aren't checked (phase 3)")

    row.add(from_bm("Cañón_Ñandú_ü", cube(1.0)), "Non-ASCII name: naming error, and export file names", expect=["naming"], tools="all")
    row.add(from_bm("A" * 63, cube(1.0)), "63-byte name, Blender's maximum: suffixes like _LOD1 / _high can't fit", tools="all")

    src = rock("SharedRockSrc", 5)
    shared = src.data
    shared.name = "SharedRock"
    copies = []
    for i in range(200):
        o = bpy.data.objects.new(f"Instance{i:03d}", shared)
        o.location = ((i % 20) * 0.3, (i // 20) * 0.3, 0)
        copies.append(o)
    lead = copies[0]
    row.add(lead, "200 objects sharing one 5k-tri mesh (linked duplicates): validate once per mesh?",
            extra=copies[1:], select=[o.name for o in copies], place=False)
    for o in copies:
        o.location.x += row.x
        o.location.y += row.y
    row.x += 7.0
    bpy.data.objects.remove(src)

    dup = plane("DuplicateFaces", 3, 3, 1, 1)
    verts, faces = [v.co[:] for v in dup.data.vertices], [list(p.vertices) for p in dup.data.polygons]
    dup.data.clear_geometry()
    dup.data.from_pydata(verts, [], faces + faces[:3])
    row.add(dup, "3 faces stored twice (invalid mesh data): repaired before reading", expect=["mesh_data"], tools="all")

    row.add(from_arrays("CollinearQuad", [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)]),
            "A quad whose 4 vertices sit on one line: zero area, distinct vertices", expect=["geometry_cleanup"], tools="all")

    a = np.linspace(0, 2 * math.pi, 1000, endpoint=False)
    r = 0.5 + 0.2 * np.sin(7 * a)
    row.add(from_arrays("Ngon1000Concave", np.stack([r * np.cos(a), r * np.sin(a), np.zeros(1000)], 1), [np.arange(1000)],
                        np.stack([0.5 + 0.5 * r * np.cos(a), 0.5 + 0.5 * r * np.sin(a)], 1)),
            "One 1,000-sided concave ngon (a CAD/vector import)", expect=["ngons"], tools="all")


# --------------------------------------------------------------------------------------------- 08

def row_pipeline(row):
    chair_low = from_bm("Chair_low", cube(1.0))
    chair_high = from_bm("Chair_high", then(cube(1.0), lambda bm: bmesh.ops.bevel(bm, geom=bm.edges[:], offset=0.05, segments=4, affect="EDGES")), smooth=True)
    bolts = from_bm("Chair_high_bolts", cyl(16, 0.05, 0.03), smooth=True)
    bolts.location = (0.3, 0, 0.5)
    row.add(chair_low, "Painter-style multi-part high: Chair_low <- Chair_high + Chair_high_bolts", forbid=["bake_pairs"],
            extra=[chair_high, bolts], select=["Chair_low", "Chair_high", "Chair_high_bolts"], tools=["validate", "bake", "export"])
    row.add(from_bm("Gun_high", cyl(32, 0.4, 0.1), smooth=True), "A high-poly with no low: a typo", expect=["bake_pairs"])
    table, table_low = from_bm("Table", cube(1.0)), from_bm("Table_low", cube(1.0))
    table_high = from_bm("Table_high", cube(1.0))
    table_low.location.x = 1.3
    row.add(table, "Table, Table_low and Table_high: which low gets the bake?", expect=["bake_pairs"],
            extra=[table_low, table_high], select=["Table", "Table_low", "Table_high"])

    crate = from_bm("Crate", cube(1.0))
    concave = from_bm("UCX_Crate_01", lambda bm: (bmesh.ops.create_cube(bm, size=1.1), bmesh.ops.translate(
        bm, vec=(0, 0, -0.4), verts=[v for v in bm.verts if v.co.x > 0 and v.co.z > 0])), mat=None)
    rotated = from_bm("UCX_Crate_02", cube(0.5), mat=None)
    rotated.rotation_euler.z = math.radians(20)
    for c in (concave, rotated):
        c.display_type = "WIRE"
    row.add(crate, "Crate + a concave UCX (Unreal rebuilds it convex) + a UCX with unapplied rotation",
            expect=["transforms"], extra=[concave, rotated], select=["Crate", "UCX_Crate_01", "UCX_Crate_02"],
            gap="A concave UCX collides wrong in Unreal; no convexity check yet (phase 3)", tools=["validate", "export"])
    row.add(from_bm("UCX_Ghost_01", cube(1.0), mat=None), "A UCX named after a mesh that doesn't exist", expect=["collisions"])

    lamp = from_bm("Lamp", cyl(16, 1.5, 0.1))
    socket = bpy.data.objects.new("SOCKET_Lamp_Top", None)
    socket.parent, socket.location = lamp, (0, 0, 0.8)
    orphan = bpy.data.objects.new("SOCKET_Orphan", None)
    orphan.location = (0.6, 0, 0)
    row.add(lamp, "Lamp with a parented socket + a socket parented to nothing", extra=[socket, orphan],
            select=["Lamp"], gap="A SOCKET_ with no parent is silently left out of every export", tools=["validate", "export"])

    manual = rock("RockManual", 4)
    manual_lod = rock("RockManual_LOD1", 3)
    manual_lod.location.x = 2.4
    row.add(manual, "Artist-made LOD named RockManual_LOD1 (no add-on marker): exported as a separate asset?",
            extra=[manual_lod], select=["RockManual", "RockManual_LOD1"], tools=["validate", "export"],
            gap="Hand-made _LODn meshes aren't recognised as LODs: Unreal/Unity export them as separate assets")


# --------------------------------------------------------------------------------------------- 10

REAL = [  # (collection, path, intent)
    ("PH_Barrel", "polyhaven_Barrel_01/Barrel_01_1k.gltf", "Poly Haven game prop, 2.7k tris"),
    ("PH_Table", "polyhaven_wooden_table_02/wooden_table_02_1k.gltf", "Poly Haven table, 196 tris"),
    ("PH_Camera", "polyhaven_Camera_01/Camera_01_1k.gltf", "Poly Haven hard surface, many parts, 27k tris"),
    ("PH_ChessSet", "polyhaven_chess_set/chess_set_1k.gltf", "Poly Haven chess set: 32 pieces, instanced meshes"),
    ("PH_Bust", "polyhaven_marble_bust_01/marble_bust_01_1k.gltf", "Poly Haven organic sculpt, 17k tris"),
    ("PH_Ship", "polyhaven_ship_pinnace/ship_pinnace_1k.gltf", "Poly Haven rigged ship, 184k tris"),
    ("PH_CoastRocks", "polyhaven_coast_rocks_02/coast_rocks_02_1k.gltf", "Poly Haven photogrammetry, 2.4M tris"),
    ("PH_Tree", "polyhaven_tree_small_02/tree_small_02_1k.gltf", "Poly Haven tree with leaf cards, 4.7M tris"),
    ("PH_Grass", "polyhaven_grass_medium_01/grass_medium_01_1k.gltf", "Poly Haven grass clumps, 1.6M tris"),
    ("ST_Dragon", "stanford_dragon/dragon_recon/dragon_vrip.ply", "Stanford dragon raw scan, 871k tris, no UVs, no material"),
    ("TA_AudiR8", "2009-audi-r8-lms/source/2009 Audi R8 LMS.fbx", "Audi R8 FBX (from run 1-3)"),
    ("TA_Gipsy", "076-gipsy-danger/source/076-Gipsy-Danger/076 Gipsy Danger.fbx", "Gipsy Danger FBX, 924 parts"),
    ("TA_Rock", "gray-big-rock/source/sutr_tmave_sedy/sutr_tmave_sedy.FBX", "Scanned rock FBX"),
    ("TA_Police", "rank-3-police-unit/source/r3pu/r3pu.obj", "Police unit OBJ"),
    ("TA_TRex", "tyrannosaurus-rex-skeleton/source/dyno_tex/dyno_tex.obj", "T-Rex skeleton OBJ"),
]


def import_real(row):
    for name, rel, intent in REAL:
        path = os.path.join(ASSETS, rel)
        if not os.path.exists(path):
            print("MISSING", path)
            continue
        before = set(bpy.data.objects)
        collection = bpy.data.collections.new(name)
        row.collection.children.link(collection)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[row.collection.name].children[name]
        ext = os.path.splitext(path)[1].lower()
        t = time.perf_counter()
        {".gltf": lambda: bpy.ops.import_scene.gltf(filepath=path), ".fbx": lambda: bpy.ops.import_scene.fbx(filepath=path),
         ".obj": lambda: bpy.ops.wm.obj_import(filepath=path), ".ply": lambda: bpy.ops.wm.ply_import(filepath=path)}[ext]()
        new = [o for o in bpy.data.objects if o not in before]
        for o in new:  # importers link into the active collection; make sure
            if collection not in o.users_collection:
                collection.objects.link(o)
        bpy.context.view_layer.update()
        meshes = [o for o in new if o.type == "MESH"]
        corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        lo = [min(c[i] for c in corners) for i in range(3)] if corners else [0, 0, 0]
        hi = [max(c[i] for c in corners) for i in range(3)] if corners else [0, 0, 0]
        width = max(hi[0] - lo[0], 0.5)
        shift = (row.x + width / 2 - (lo[0] + hi[0]) / 2, row.y - (lo[1] + hi[1]) / 2, -lo[2])
        for o in new:
            if o.parent is None:
                o.location = (o.location.x + shift[0], o.location.y + shift[1], o.location.z + shift[2])
        row.x += width + GAP * 2
        row.depth = max(row.depth, hi[1] - lo[1])
        tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
        print(f"imported {name}: {len(new)} objects, {len(meshes)} meshes, {tris:,} tris in {time.perf_counter() - t:.1f}s")
        CASES.append({"name": name, "row": row.collection.name, "intent": f"{intent} ({len(meshes)} meshes, {tris:,} tris as imported)",
                      "select": [o.name for o in meshes], "objects": [o.name for o in new], "expect": [], "forbid": [],
                      "artist_ok": [], "gap": "", "tools": "auto", "real": True, "tris": tris})
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection


def main():
    global DEFAULT
    t0 = time.perf_counter()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    bav.register()
    from blender_asset_validator.core import engine
    scene = bpy.context.scene
    scene.asset_validator_engine = "unreal"
    with open(os.path.join(HERE, engine.PROJECT_CONFIG), "w", encoding="utf-8") as f:
        json.dump({"transforms": {"check_location": False}, "export": {"path": "//_out/exports/"}}, f, indent=2)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)  # relative paths (textures, config) need the .blend's folder
    config = engine.load_config()
    DEFAULT = material("M_Stress", (0.62, 0.6, 0.58))
    scene.world = bpy.data.worlds.new("Stress")
    scene.world.color = (0.18, 0.19, 0.21)

    y = 0.0
    for title, build in (("01 Budget ladder", row_budget), ("02 Modifiers (export != mesh data)", row_modifiers),
                         ("03 Hard surface", lambda r: row_hard_surface(r, config)), ("04 Organic and scans", row_organic),
                         ("05 Environment and UVs", row_environment), ("06 Foliage", row_foliage),
                         ("07 Robustness", row_robustness), ("08 Pipeline naming", row_pipeline),
                         ("10 Real models", import_real)):
        t = time.perf_counter()
        row = Row(title, y)
        build(row)
        y = row.below()
        print(f"{title}: {sum(c['row'] == title for c in CASES)} cases in {time.perf_counter() - t:.1f}s", flush=True)

    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    for obj in scene.objects:
        obj.select_set(False)

    problems = [f"{c['name']}: object {n} missing" for c in CASES for n in c["objects"] if n not in bpy.data.objects]
    tris = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in scene.objects if o.type == "MESH"}
    for name, want in (("BudgetExact", 50000), ("BudgetOver", 50250), ("Rock5M", 5242880)):
        if tris.get(name) != want:
            problems.append(f"{name}: {tris.get(name)} tris, wanted {want}")
    text = bpy.data.texts.new("StressManifest")
    text.write(json.dumps(CASES, indent=1, ensure_ascii=False))
    with open(os.path.join(HERE, "StressTest_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(CASES, f, indent=1, ensure_ascii=False)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    lines = [f"STRESS FAIL {p}" for p in problems] or [
        f"STRESS OK: {len(CASES)} cases, {sum(tris.values()):,} tris in {len(tris)} meshes, built in {time.perf_counter() - t0:.0f}s"]
    print("\n".join(lines))
    if problems:
        raise SystemExit(1)


main()
