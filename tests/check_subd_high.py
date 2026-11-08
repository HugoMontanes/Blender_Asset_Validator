"""Phase 2, third part: Make SubD High (the _high from the low with crease and Subdivision).
Criteria in docs/ROADMAP.md."""
import sys, os, traceback, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "_out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(__file__))[0] + ".txt")
WORK = os.path.join(OUT_DIR, "work_subd_high")
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)
sys.path.insert(0, os.path.dirname(HERE))
log = open(OUT, "w", encoding="utf-8")


def say(msg):
    log.write(msg + "\n"); log.flush()


def check(name, cond, extra=""):
    say(f"{'PASS' if cond else 'FAIL'}  {name}  {extra}")


import bpy, bmesh
import numpy as np

try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import blender_asset_validator as bav
    from blender_asset_validator.core import engine, roles
    bav.register()
    say("register OK, Blender " + bpy.app.version_string)
except Exception:
    say("IMPORT/REGISTER FAILED\n" + traceback.format_exc()); raise SystemExit

scene = bpy.context.scene


def cube(name, sharp=True, cuts=0):
    """A 2 m cube, every face its own UV cell, its 12 outer edges sharp."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_cube(bm, size=2.0)
    for i, f in enumerate(bm.faces):
        for j, l in enumerate(f.loops):
            l[uv].uv = ((i % 3) * 0.33 + 0.02 + (0, .29, .29, 0)[j], (i // 3) * 0.5 + 0.02 + (0, 0, .29, .29)[j])
    if cuts:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    mesh = bpy.data.meshes.new(name); bm.to_mesh(mesh); bm.free()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    mesh.materials.append(bpy.data.materials.new(name + "Mat"))
    if sharp:
        mesh.attributes.new("sharp_edge", "BOOLEAN", "EDGE").data.foreach_set("value", outer_edges(mesh))
    return obj


def outer_edges(mesh):
    """The edges on the cube's 12 corners lines (both ends on two faces of the box)."""
    co = np.array([v.co for v in mesh.vertices])
    mid = np.array([(co[e.vertices[0]] + co[e.vertices[1]]) / 2 for e in mesh.edges])
    return np.isclose(np.abs(mid), 1.0).sum(axis=1) >= 2


def values(mesh, name, dtype=float):
    attribute = mesh.attributes.get(name)
    out = np.zeros(len(attribute.data) if attribute else len(mesh.edges), dtype)
    if attribute:
        attribute.data.foreach_get("value", out)
    return out


def select(*objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def run(op, expect="", **kw):
    """bpy.ops raises for a reported ERROR, and for a crash: tell them apart."""
    try:
        return op(**kw)
    except RuntimeError as e:
        return {"CANCELLED"} if expect and expect in str(e) else {"CRASHED: " + str(e)}


try:
    cfg = engine.load_config()

    # AC-1, AC-8: the high is a hidden copy where the low is, and the low stays selected
    box = cube("Box")
    box.location = (1.0, 2.0, 3.0)
    shelf = bpy.data.collections.new("Shelf"); scene.collection.children.link(shelf); shelf.objects.link(box)
    crate = cube("Crate_low")
    select(box, crate)
    r = run(bpy.ops.asset_validator.make_high)
    high = bpy.data.objects.get("Box_high")
    check("AC-8: Make SubD High runs from bpy.ops", r == {"FINISHED"}, str(r))
    check("AC-1: Box_high is Box's high", high is not None and roles.role(high, cfg) == "high" and roles.highs_of(box, cfg) == [high])
    check("AC-1: Crate_low gives Crate_high", "Crate_high" in bpy.data.objects and roles.highs_of(crate, cfg) == [bpy.data.objects["Crate_high"]])
    check("AC-1: same matrix and collections, its own mesh", high is not None and high.matrix_world == box.matrix_world
          and set(high.users_collection) == set(box.users_collection) and high.data is not box.data)
    check("AC-1: the high is hidden, the low still selected and active", high is not None and not high.visible_get()
          and box.select_get() and bpy.context.view_layer.objects.active == box)

    # AC-2: the sharp edges creased; below 1 they stop being sharp, at 1 they stay
    hm = high.data
    creased = values(hm, "crease_edge")
    check("AC-2: the 12 sharp edges creased 0.9, no other", np.allclose(creased[outer_edges(hm)], 0.9) and not creased[~outer_edges(hm)].any(),
          str(np.unique(creased.round(3))))
    check("AC-2: no sharp edge left and every face smooth", not values(hm, "sharp_edge", bool).any() and all(p.use_smooth for p in hm.polygons))
    check("AC-2: the low keeps its sharp edges", values(box.data, "sharp_edge", bool).sum() == 12)
    hard = cube("Hard")
    select(hard)
    run(bpy.ops.asset_validator.make_high, crease=1.0)
    hm = bpy.data.objects["Hard_high"].data
    check("AC-2: with crease 1 the 12 edges stay sharp", np.allclose(values(hm, "crease_edge")[outer_edges(hm)], 1.0)
          and values(hm, "sharp_edge", bool).sum() == 12)

    # AC-3: the low's shape modifiers come along, its shading ones don't
    stacked = cube("Stacked")
    stacked.modifiers.new("Bevel", "BEVEL")
    stacked.modifiers.new("Triangulate", "TRIANGULATE")
    stacked.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL").use_pin_to_last = True
    select(stacked)
    run(bpy.ops.asset_validator.make_high, levels=3)  # not 2: a new Subdivision renders at 2 already
    mods = bpy.data.objects["Stacked_high"].modifiers
    check("AC-3: the high's stack is Bevel -> Subdivision", [m.type for m in mods] == ["BEVEL", "SUBSURF"], str([m.type for m in mods]))
    check("AC-3: Subdivision at the level asked in viewport and render", mods[-1].type == "SUBSURF" and mods[-1].levels == 3 and mods[-1].render_levels == 3)
    check("AC-3: the low keeps its three", [m.type for m in stacked.modifiers] == ["BEVEL", "TRIANGULATE", "WEIGHTED_NORMAL"])

    # AC-4: after Prep with Bevel the sharp edges are bevel weights; with no marks at all, the bent edges
    prepped = cube("Prepped", sharp=False)
    select(prepped)
    run(bpy.ops.asset_validator.hard_surface_prep, bevel=True)
    weights = values(prepped.data, "bevel_weight_edge")
    check("AC-4: (setup) Prep left bevel weights and no sharp edge", (weights > 0).sum() == 12 and not values(prepped.data, "sharp_edge", bool).any())
    weighted = cube("Weighted", sharp=False)  # 3 weights: on a cube the bent edges would be Prep's same 12
    weighted.data.attributes.new("bevel_weight_edge", "FLOAT", "EDGE").data.foreach_set("value", [1.0, 0.5, 0.2] + [0.0] * 9)
    select(prepped, weighted)
    run(bpy.ops.asset_validator.make_high)
    hm = bpy.data.objects["Prepped_high"].data
    check("AC-4: the high creases Prep's bevel-weighted edges", np.allclose(values(hm, "crease_edge")[values(hm, "bevel_weight_edge") > 0], 0.9)
          and (values(hm, "crease_edge") > 0).sum() == 12)
    creased = values(bpy.data.objects["Weighted_high"].data, "crease_edge")
    check("AC-4: only the bevel-weighted edges, not the bent ones", np.allclose(creased, [0.9] * 3 + [0.0] * 9), str(creased.round(2)))
    plain = cube("Plain", sharp=False)
    select(plain)
    run(bpy.ops.asset_validator.make_high)
    hm = bpy.data.objects["Plain_high"].data
    check("AC-4: an unmarked cube creases its 12 edges by angle", np.allclose(values(hm, "crease_edge")[outer_edges(hm)], 0.9)
          and (values(hm, "crease_edge") > 0).sum() == 12)
    bare = cube("Bare", sharp=False)
    select(bare)
    run(bpy.ops.asset_validator.make_high, crease=1.0)
    hm = bpy.data.objects["Bare_high"].data
    check("crease 1 on edges found by angle (or by weight) makes them sharp too, or the shading bends across them",
          np.array_equal(values(hm, "sharp_edge", bool), outer_edges(hm)))

    # Review: Shade Auto Smooth's modifier, pinned last, would re-sharpen the rounded edges after the Subdivision
    smoothed = cube("Smoothed")
    select(smoothed)
    bpy.ops.object.shade_auto_smooth()
    run(bpy.ops.asset_validator.make_high)
    mods = bpy.data.objects["Smoothed_high"].modifiers
    check("the low's Smooth by Angle modifier isn't copied", [m.type for m in mods] == ["SUBSURF"], str([m.type for m in mods]))

    # Review: a Box_high in another scene isn't this scene's high; a name past Blender's 63 bytes would lose its suffix
    other = bpy.data.scenes.new("Other")
    other.collection.objects.link(cube("Far"))
    away = bpy.data.objects.new("Far_high", bpy.data.meshes.new("Far_high")); other.collection.objects.link(away)
    bpy.data.objects.remove(bpy.data.objects["Far"])
    far = cube("Far")
    select(far)
    run(bpy.ops.asset_validator.make_high)
    check("a Far_high in another scene doesn't stop Far getting its own", len(roles.highs_of(far, cfg)) == 1, str(roles.highs_of(far, cfg)))
    long_low = cube("L" * 60)
    count = len(bpy.data.objects)
    select(long_low)
    r = run(bpy.ops.asset_validator.make_high, "63")
    check("a name too long for its _high is cancelled and says so", r == {"CANCELLED"} and len(bpy.data.objects) == count, str(r))

    # AC-5: a high that's there already is left alone; LODs, highs and empty meshes are skipped
    before = (high.data, len(high.modifiers), len(bpy.data.objects))
    select(box)
    r = run(bpy.ops.asset_validator.make_high, "already exists")
    check("AC-5: an existing Box_high isn't touched, and with nothing made the operator cancels",
          r == {"CANCELLED"} and (high.data, len(high.modifiers), len(bpy.data.objects)) == before, str(r))
    empty = bpy.data.objects.new("Empty", bpy.data.meshes.new("Empty")); scene.collection.objects.link(empty)
    select(plain)
    run(bpy.ops.asset_validator.generate_lods)
    lod = next(o for o in bpy.data.objects if roles.role(o, cfg) == "lod")
    count = len(bpy.data.objects)
    select(empty, high, lod)
    r = run(bpy.ops.asset_validator.make_high, "Select the low-poly asset meshes")
    check("AC-5: a LOD, a high and a mesh with no faces: cancelled, nothing made", r == {"CANCELLED"} and len(bpy.data.objects) == count, str(r))

    # AC-6: baking from the high: crease 1 bakes flat, 0.9 tilts the pixels along the edges
    from blender_asset_validator.operations import bake
    bake_cfg = {**cfg, "bake": {**cfg["bake"], "path": WORK}, "uv": {**cfg["uv"], "texture_size": 128}}
    island = np.zeros((128, 128), bool)  # inside each face's UV cell, clear of the bake margin
    for i in range(6):
        x0, y0, w = int(((i % 3) * 0.33 + 0.02) * 128), int(((i // 3) * 0.5 + 0.02) * 128), int(0.29 * 128)
        island[y0 + 2:y0 + w - 2, x0 + 2:x0 + w - 2] = True
    dense = cube("Dense", cuts=3)
    tilted = {}
    for value in (1.0, 0.9):
        select(dense)
        run(bpy.ops.asset_validator.make_high, crease=value)
        bake.bake_normals(dense, roles.highs_of(dense, cfg), bake_cfg)
        px = np.array(bpy.data.images["Dense_N"].pixels[:]).reshape(128, 128, 4)[..., :3] * 2 - 1
        tilted[value] = float((np.degrees(np.arccos(np.clip(px[..., 2], -1, 1)))[island] > 5).mean())
        bpy.data.objects.remove(bpy.data.objects["Dense_high"])
    check("AC-6: crease 1 bakes flat", tilted[1.0] == 0.0, f"{tilted[1.0]:.1%} of the island pixels tilted past 5 deg")
    check("AC-6: crease 0.9 rounds the edges, and only near them", 0.02 < tilted[0.9] < 0.4, f"{tilted[0.9]:.1%}")

    # AC-7: the line says what was made, and what SubD will pinch
    msg = bake.make_high(cube("Lined"), cfg, 0.9, 2)
    check("AC-7: the line: creased edges, level, triangles (6 faces x 16 quads x 2) and how far it strays",
          "12 edge(s) creased 0.9" in msg and "level 2" in msg and "192 triangles" in msg and "% of its size from the low" in msg
          and "aren't quads" not in msg, msg)
    tri = cube("Tri")
    bm = bmesh.new(); bm.from_mesh(tri.data); bmesh.ops.triangulate(bm, faces=bm.faces[:]); bm.to_mesh(tri.data); bm.free()
    msg = bake.make_high(tri, cfg, 0.9, 2)
    check("AC-7: a triangulated low: the line counts the faces that aren't quads", "12 face(s) aren't quads" in msg, msg)

    # Blender's Subdivision freezes on a big ngon (measured: 200 sides 1.9 s, 400 sides 24 s; a CAD import's
    # 1,000-sided face never finished): the low is skipped with a line saying why
    import math, time
    ring = [(math.cos(a), math.sin(a), 0) for a in np.linspace(0, 2 * math.pi, 300, endpoint=False)]
    me = bpy.data.meshes.new("Ngon"); me.from_pydata(ring, [], [list(range(300))])
    ngon = bpy.data.objects.new("Ngon", me); scene.collection.objects.link(ngon)
    t = time.perf_counter(); msg = bake.make_high(ngon, cfg, 0.9, 2); elapsed = time.perf_counter() - t
    check("a low with a 300-sided face: no high, the line says why, at once",
          "Ngon_high" not in bpy.data.objects and "more than 64 sides" in msg and elapsed < 1.0, f"{elapsed:.1f}s {msg}")

    from blender_asset_validator.ui import panel
    check("AC-8: the button is among the tools of Shading & UVs",
          "asset_validator.make_high" in [op for row in panel._STEP_TOOLS[3] for op, _ in row])
except Exception:
    say("EXCEPTION\n" + traceback.format_exc())

try:
    bav.unregister(); say("PASS  unregister clean")
except Exception:
    say("FAIL  unregister\n" + traceback.format_exc())
say("DONE")
