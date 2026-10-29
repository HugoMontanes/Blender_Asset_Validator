"""Phase 2, second part: the bake helper (low/high pairing, the high role, measured
cage and ray distances, Bake Normals, Export Bake Pairs). Criteria in docs/ROADMAP.md."""
import sys, os, traceback, json, shutil, time
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "_out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(__file__))[0] + ".txt")
WORK = os.path.join(OUT_DIR, "work_bake")
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
    from blender_asset_validator.operations import bake, hard_surface
    from io_scene_fbx import parse_fbx
    bav.register()
    say("register OK, Blender " + bpy.app.version_string)
except Exception:
    say("IMPORT/REGISTER FAILED\n" + traceback.format_exc()); raise SystemExit

scene = bpy.context.scene
SIZE = 128


def config(normal_g="POS_Y"):
    cfg = engine.load_config()
    cfg["bake"]["normal_g"] = normal_g
    cfg["bake"]["path"] = WORK
    cfg["uv"]["texture_size"] = SIZE
    return cfg


def from_bm(name, fill, material=True, uv=True):
    bm = bmesh.new()
    if uv:
        bm.loops.layers.uv.new("UVMap")
    fill(bm)
    mesh = bpy.data.meshes.new(name); bm.to_mesh(mesh); bm.free()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    if material:
        mesh.materials.append(bpy.data.materials.new(name + "Mat"))
    return obj


def cube(name, size=2.0, **kw):
    obj = from_bm(name, lambda bm: bmesh.ops.create_cube(bm, size=size), **kw)
    if obj.data.uv_layers:  # every face its own UV cell: no overlaps, gaps all round
        bm = bmesh.new(); bm.from_mesh(obj.data); uv = bm.loops.layers.uv.active
        for i, f in enumerate(bm.faces):
            for j, l in enumerate(f.loops):
                l[uv].uv = ((i % 3) * 0.33 + 0.02 + (0, .29, .29, 0)[j], (i // 3) * 0.5 + 0.02 + (0, 0, .29, .29)[j])
        bm.to_mesh(obj.data); bm.free()
    return obj


def bevelled_high(name, offset=0.0):
    high = cube(name, material=False, uv=False)
    bevel = high.modifiers.new("Bevel", "BEVEL"); bevel.width = 0.2; bevel.segments = 4
    for p in high.data.polygons:
        p.use_smooth = True
    high.location.z = offset
    return high


def select(*objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def run(op, expect=""):
    """bpy.ops raises for a reported ERROR, and for a crash: tell them apart."""
    try:
        return op()
    except RuntimeError as e:
        return {"CANCELLED"} if expect and expect in str(e) else {"CRASHED: " + str(e)}


def pixels(image):
    return np.array(image.pixels[:]).reshape(image.size[1], image.size[0], 4)[..., :3]


def fbx_models(path):
    root, _ = parse_fbx.parse(path)
    objs = next(e for e in root.elems if e.id == b"Objects")
    return sorted(e.props[1].split(b"\x00\x01")[0].decode() for e in objs.elems if e.id == b"Model")


try:
    # AC-1: pairing by name, Substance Painter's rule
    box = cube("Box")
    for name in ("Box_high", "Box_high_bolts", "Box_high.001", "Box_highlight", "Box_HIGH"):
        cube(name, material=False, uv=False)
    paired = sorted(o.name for o in roles.highs_of(box, config()))
    check("AC-1: Box pairs with Box_high, Box_high_bolts and Box_high.001, not Box_highlight or Box_HIGH",
          paired == ["Box_high", "Box_high.001", "Box_high_bolts"], str(paired))
    crate_low, crate_high = cube("Crate_low"), cube("Crate_high", material=False, uv=False)
    check("AC-1: Crate_low pairs with Crate_high", roles.highs_of(crate_low, config()) == [crate_high])
    check("AC-1: the roles", [roles.role(bpy.data.objects[n], config()) for n in ("Box", "Box_high.001", "Box_highlight", "Crate_low")]
          == ["asset", "high", "asset", "asset"])

    # AC-2: a high skips the checks and the tools
    messy = from_bm("Box_high_messy", lambda bm: bmesh.ops.create_circle(bm, cap_ends=True, segments=8, radius=1.0), material=False, uv=False)
    results = engine.run_validation(config(), [box, messy])
    check("AC-2: a high with an ngon and no material gives no result", not [r for r in results if r.object_name == messy.name],
          str([r.message for r in results if r.object_name == messy.name]))
    tower = cube("Tower_high")
    results = engine.run_validation(config(), [tower, crate_high])
    check("a high with no low to bake onto warns that it won't be exported (an asset named ..._high by chance)",
          [(r.object_name, r.severity.value) for r in results] == [("Tower_high", "WARNING")] and "won't be checked or exported" in results[0].message,
          str([r.message for r in results]))
    select(messy)
    r = run(bpy.ops.asset_validator.hard_surface_prep, "Select at least one asset mesh")
    check("AC-2: Prep skips a high", r == {"CANCELLED"} and not messy.modifiers and not messy.data.uv_layers, str(r))
    r = run(bpy.ops.asset_validator.generate_lods, "Select at least one asset mesh")
    check("AC-2: Generate LODs skips a high", r == {"CANCELLED"}, str(r))

    # AC-3: measured distances; the high floats 3 cm up, so its bottom sits 3 cm inside
    meas = cube("Meas")
    meas_high = bevelled_high("Meas_high", offset=0.03)
    meas_high.modifiers.new("Subsurf", "SUBSURF").levels = 2
    extrusion, ray = bake.ray_distances(meas, [meas_high])
    check("AC-3: the cage covers the 3 cm outside without passing 5", 0.03 <= extrusion < 0.05, f"{extrusion:.4f}")
    check("AC-3: the ray reaches the bottom, 3 cm inside (more at the rounded corners)", ray >= extrusion + 0.03 and ray < 0.15, f"{ray:.4f}")
    meas_high.location.x = 2.5  # laid beside the low, like LODs in a row
    try:
        bake.ray_distances(meas, [meas_high]); error = ""
    except ValueError as e:
        error = str(e)
    check("a high beside its low, not on it, is refused and says so", "don't sit on it" in error, error)
    meas_high.location.x = 0.0

    # Edge cases before the .blend is saved
    select(box)
    r = run(bpy.ops.asset_validator.bake_normals, "Save the .blend first")
    check("edge case: unsaved .blend with a relative bake.path is cancelled", r == {"CANCELLED"}, str(r))

    # AC-4: a flat high just outside a flat low bakes flat, with no seam at the hard edges
    flat = cube("Flat")
    cube("Flat_high", size=2.04, material=False, uv=False)
    scene.cycles.samples = 77
    engine_before = scene.render.engine
    msg = bake.bake_normals(flat, roles.highs_of(flat, config()), config())
    deviation = np.abs(pixels(bpy.data.images["Flat_N"]) - [0.5, 0.5, 1.0]).max(axis=2)
    check("AC-4: flat on flat bakes (0.5, 0.5, 1) everywhere, hard edges too", deviation.max() < 0.02, f"{deviation.max():.3f} {msg}")
    check("AC-4: the render engine and samples are put back", scene.render.engine == engine_before and scene.cycles.samples == 77,
          f"{scene.render.engine} {scene.cycles.samples}")

    # AC-4, AC-5: a bevelled high tilts the edge pixels; DirectX green is 1 - OpenGL green
    bev = cube("Bev")
    bevelled_high("Bev_high")
    hard_surface.add_weighted_normal(bev)
    nodes = bev.data.materials[0].node_tree.nodes
    before = (len(nodes), nodes.active)
    bake.bake_normals(bev, roles.highs_of(bev, config()), config("POS_Y"))
    opengl = pixels(bpy.data.images["Bev_N"]).copy()
    msg = bake.bake_normals(bev, roles.highs_of(bev, config()), config("NEG_Y"))
    directx = pixels(bpy.data.images["Bev_N"])
    tilted = np.abs(opengl - [0.5, 0.5, 1.0]).max(axis=2) > 0.05
    check("AC-4: the bevel tilts the pixels along the edges", tilted.mean() > 0.02, f"{tilted.mean():.1%} of the texture")
    check("AC-4: DirectX green = 1 - OpenGL green, red and blue the same",
          np.abs(directx[tilted, 1] - (1 - opengl[tilted, 1])).max() < 0.01 and np.abs(directx[tilted][:, [0, 2]] - opengl[tilted][:, [0, 2]]).max() < 0.01)
    png = os.path.join(WORK, "Bev_N.png")
    saved = bpy.data.images.load(png, check_existing=False) if os.path.exists(png) else None
    check("AC-4: Bev_N.png on disk at the profile's size", saved is not None and tuple(saved.size) == (SIZE, SIZE), msg)
    check("AC-4: one image, reused by the second bake", len([i for i in bpy.data.images if i.name.startswith("Bev_N")]) == 2)  # + the loaded copy
    check("AC-4: the material has no node left over and the same active node", (len(nodes), nodes.active) == before)
    lightmap = bev.data.uv_layers.new(name="Lightmap")
    shifted = np.array([(u * 0.5 + 0.5, v * 0.5) for u, v in (d.uv for d in bev.data.uv_layers[0].data)], np.float32)
    lightmap.data.foreach_set("uv", shifted.ravel())
    bev.data.uv_layers.active = lightmap; lightmap.active_render = True
    bake.bake_normals(bev, roles.highs_of(bev, config()), config("POS_Y"))
    check("AC-4: bakes into UV0 with the lightmap UV active", np.abs(pixels(bpy.data.images["Bev_N"]) - opengl).max() < 0.01)
    stack = [m.type for m in bev.modifiers]
    check("AC-5: the stack ends Triangulate -> Weighted Normal, one Triangulate after two bakes",
          stack == ["TRIANGULATE", "WEIGHTED_NORMAL"] and bev.modifiers[0].keep_custom_normals, str(stack))

    # Edge cases of the low
    for name, fill_uv, slot in (("NoUV", False, True), ("Slot", True, False)):
        low = cube(name, uv=fill_uv, material=slot)
        if not slot:
            low.data.materials.append(None)
        cube(f"{name}_high", size=2.04, material=False, uv=False)
        try:
            bake.bake_normals(low, roles.highs_of(low, config()), config()); error = ""
        except ValueError as e:
            error = str(e)
        check(f"edge case: {name} isn't baked and says why", error and not low.modifiers and f"{name}_N" not in bpy.data.images, error)

    # The operators, with the .blend saved and the project's rules next to it
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(WORK, "bake_test.blend"))
    with open(os.path.join(WORK, "asset_validator.json"), "w") as f:
        json.dump({"uv": {"texture_size": SIZE}}, f)
    bpy.ops.object.select_all(action="DESELECT")
    r = run(bpy.ops.asset_validator.bake_normals, "Select the low-poly asset meshes")
    check("edge case: nothing selected is cancelled", r == {"CANCELLED"}, str(r))
    lonely = cube("Lonely")
    select(lonely)
    r = run(bpy.ops.asset_validator.bake_normals, "no _high mesh to bake from")
    check("edge case: an asset without a high is cancelled and says so", r == {"CANCELLED"} and not lonely.modifiers, str(r))
    select(flat, lonely)
    r = run(bpy.ops.asset_validator.bake_normals)
    check("AC-7: Bake Normals runs from bpy.ops into //bakes/", r == {"FINISHED"} and os.path.exists(os.path.join(WORK, "bakes", "Flat_N.png")), str(r))

    # AC-2: Export writes the asset without its highs
    select(box, *roles.highs_of(box, config()))
    r = run(bpy.ops.asset_validator.export)
    exported = sorted(os.listdir(os.path.join(WORK, "exports"))) if os.path.isdir(os.path.join(WORK, "exports")) else []
    check("AC-2: Export writes Box alone, no high in it", r == {"FINISHED"} and exported == ["Box.fbx"]
          and fbx_models(os.path.join(WORK, "exports", "Box.fbx")) == ["Box"], f"{r} {exported}")

    # AC-6: the pair files
    select(box)
    r = run(bpy.ops.asset_validator.export_bake_pairs)
    low_fbx, high_fbx = (os.path.join(WORK, "bakes", f"Box{s}.fbx") for s in ("_low", "_high"))
    check("AC-6: Box_low.fbx holds Box_low", r == {"FINISHED"} and os.path.exists(low_fbx) and fbx_models(low_fbx) == ["Box_low"], str(r))
    check("AC-6: Box_high.fbx holds the highs, the dot turned into _",
          os.path.exists(high_fbx) and fbx_models(high_fbx) == ["Box_high", "Box_high_001", "Box_high_bolts", "Box_high_messy"],
          str(fbx_models(high_fbx)) if os.path.exists(high_fbx) else "")
    check("AC-6: the scene names are put back, the low got its Triangulate",
          box.name == "Box" and "Box_high.001" in bpy.data.objects and [m.type for m in box.modifiers] == ["TRIANGULATE"])
    select(lonely)
    r = run(bpy.ops.asset_validator.export_bake_pairs, "No _high mesh pairs")
    check("edge case: Export Bake Pairs without a high is cancelled", r == {"CANCELLED"} and not lonely.modifiers, str(r))

    # NFR-1: measuring against a 1M-vertex high
    big = bpy.data.meshes.new("Big_high")
    big.vertices.add(1_000_000)
    big.vertices.foreach_set("co", np.random.default_rng(1).uniform(-1.02, 1.02, 3_000_000).astype(np.float32))
    big_high = bpy.data.objects.new("Big_high", big); scene.collection.objects.link(big_high)
    start = time.perf_counter()
    bake.ray_distances(cube("Big"), [big_high])
    elapsed = time.perf_counter() - start
    check("NFR-1: ray_distances with a 1M-vertex high takes under 1 s", elapsed < 1.0, f"{elapsed:.2f} s")
except Exception:
    say("EXCEPTION\n" + traceback.format_exc())

try:
    bav.unregister(); say("PASS  unregister clean")
except Exception:
    say("FAIL  unregister\n" + traceback.format_exc())
say("DONE")
