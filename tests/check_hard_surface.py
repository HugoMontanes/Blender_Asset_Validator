import sys, os, traceback, math
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "_out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(__file__))[0] + ".txt")
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
    from blender_asset_validator.core import engine
    from blender_asset_validator.checks import shading, uvs as uv_checks
    from blender_asset_validator.operations import hard_surface, uvs
    from blender_asset_validator.core.mesh_utils import bake_mesh, read_array
    bav.register()
    say("register OK, Blender " + bpy.app.version_string)
except Exception:
    say("IMPORT/REGISTER FAILED\n" + traceback.format_exc()); raise SystemExit


def config(texel_density=0, require_weighted_normal=False):
    cfg = engine.load_config()
    cfg["uv"]["texel_density"] = texel_density
    cfg["hard_surface"]["require_weighted_normal"] = require_weighted_normal
    return cfg


def from_bm(name, fill):
    bm = bmesh.new(); fill(bm)
    mesh = bpy.data.meshes.new(name); bm.to_mesh(mesh); bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(bpy.data.materials.new(name + "Mat"))
    return obj


def cylinder(name):
    return from_bm(name, lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=1.0, radius2=1.0, depth=2.0))


def cube(name, size=1.0):
    return from_bm(name, lambda bm: bmesh.ops.create_cube(bm, size=size))


def select(*objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def sharp_of(mesh):
    attribute = mesh.attributes.get("sharp_edge")
    return read_array(attribute.data, "value", dtype=bool) if attribute else np.zeros(len(mesh.edges), bool)


def warnings(obj, cfg):
    return [r.message for r in uv_checks.check_uv_layout([obj], cfg) + uv_checks.check_uvs([obj], cfg) + shading.check_shading([obj], cfg)
            if r.severity.value != "INFO"]


def islands(obj):
    return int(uvs.face_islands(obj.data, obj.data.uv_layers[0]).max()) + 1


ANGLE = math.radians(30)

# AC-1, AC-5: sharp by angle, Auto Unwrap, clean layout and shading
cyl = cylinder("Cyl")
msg = hard_surface.prep_mesh(cyl, config(), ANGLE, bevel=False)
hard_surface.add_modifiers(cyl, 0)
check("AC-1: a 32-sided cylinder gets its 64 cap rims sharp and 3 islands", sharp_of(cyl.data).sum() == 64 and islands(cyl) == 3, msg)
check("AC-1/5: no UV layout, UV or hard-edge warning after Prep", not warnings(cyl, config()), str(warnings(cyl, config())))
check("AC-1: every face shaded smooth", all(p.use_smooth for p in cyl.data.polygons))

# AC-2: a hand-marked sharp edge survives and becomes a seam
marked = cylinder("Marked")
bm = bmesh.new(); bm.from_mesh(marked.data)
tube = next(e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1)
tube_index = tube.index
tube.smooth = False
bm.to_mesh(marked.data); bm.free()
hard_surface.prep_mesh(marked, config(), ANGLE, bevel=False)
check("AC-2: the hand-marked tube edge stays sharp and is a seam",
      sharp_of(marked.data)[tube_index] and marked.data.edges[tube_index].use_seam and sharp_of(marked.data).sum() == 65)

# AC-3: the profile's texel density
box = cube("Box")
msg = hard_surface.prep_mesh(box, config(texel_density=512), ANGLE, bevel=False)
density = uvs.texel_density(uvs.uv_stats(box, box.data.uv_layers[0]), 2048)
lo, hi = uvs.island_bounds(box.data, box.data.uv_layers[0], uvs.face_islands(box.data, box.data.uv_layers[0]))
check("AC-3: every island at 512 px/m and inside 0-1", np.allclose(density, 512, rtol=0.01) and (lo >= 0).all() and (hi <= 1).all(),
      f"{msg} {density}")
big = cube("BigBox", size=8.0)
msg = hard_surface.prep_mesh(big, config(texel_density=512), ANGLE, bevel=False)
check("edge case: a density that doesn't fit says so", "doesn't fit" in msg, msg)

# AC-4: one Weighted Normal, Keep Sharp, not duplicated
added = hard_surface.add_modifiers(box, 0)
again = hard_surface.add_modifiers(box, 0)
wn = [m for m in box.modifiers if m.type == "WEIGHTED_NORMAL"]
check("AC-4: Weighted Normal with Keep Sharp added once", len(wn) == 1 and wn[0].keep_sharp and added and not again, f"{added} {again}")
hard_surface.add_modifiers(box, 2)
check("AC-6: a Bevel added after the Weighted Normal still goes above it", [m.type for m in box.modifiers] == ["BEVEL", "WEIGHTED_NORMAL"],
      str([m.type for m in box.modifiers]))

# AC-6: Bevel on the sharp edges, through the operator
bev = cube("Bevelled")
select(bev)
r = bpy.ops.asset_validator.hard_surface_prep(bevel=True, segments=2)
evaluated = bake_mesh(bev)
poly_n = read_array(evaluated.polygons, "normal", 3)
corner_n = read_array(evaluated.corner_normals, "vector", 3)
face = np.repeat(np.arange(len(evaluated.polygons)), read_array(evaluated.polygons, "loop_total", dtype=np.int64))
large = read_array(evaluated.polygons, "area")[face] > 0.5
deviation = np.degrees(np.arccos(np.clip((corner_n * poly_n[face]).sum(axis=1), -1, 1)))
check("AC-6: the stack is Bevel then Weighted Normal", r == {"FINISHED"} and [m.type for m in bev.modifiers] == ["BEVEL", "WEIGHTED_NORMAL"],
      str([m.type for m in bev.modifiers]))
check("AC-6: the evaluated mesh has no sharp edges and its big faces stay flat (< 2°)",
      not sharp_of(evaluated).any() and large.any() and deviation[large].max() < 2.0, f"{deviation[large].max():.2f}°, {len(evaluated.polygons)} faces")
check("AC-6: the 12 cube edges carry bevel weight 1, none sharp on the mesh",
      not sharp_of(bev.data).any() and (read_array(bev.data.attributes["bevel_weight_edge"].data, "value") == 1).sum() == 12)
bpy.data.meshes.remove(evaluated)

# Review fixes: a Weighted Normal added by hand, a Bevel with another limit, Shade Auto Smooth's modifier
manual = cube("Manual")
manual.modifiers.new("MyWN", "WEIGHTED_NORMAL")
manual.modifiers.new("MyBevel", "BEVEL").limit_method = "ANGLE"
hard_surface.add_modifiers(manual, 2)
stack = [(m.type, m.limit_method if m.type == "BEVEL" else "") for m in manual.modifiers]
check("a hand-added Weighted Normal ends after the new Bevel; a Bevel by angle doesn't stand in for the one by weight",
      stack == [("BEVEL", "ANGLE"), ("BEVEL", "WEIGHT"), ("WEIGHTED_NORMAL", "")], str(stack))
auto = cube("AutoSmooth")
select(auto)
bpy.ops.object.shade_auto_smooth()
r = bpy.ops.asset_validator.hard_surface_prep(bevel=True, segments=1)
evaluated = bake_mesh(auto)
check("Shade Auto Smooth's modifier is removed, so it can't re-sharpen the bevel",
      [m.type for m in auto.modifiers] == ["BEVEL", "WEIGHTED_NORMAL"] and not sharp_of(evaluated).any(), str([m.name for m in auto.modifiers]))
bpy.data.meshes.remove(evaluated)

octo = from_bm("Octo", lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=1.0, radius2=1.0, depth=2.0))  # tube bends 45°
select(octo)  # headless, INVOKE_DEFAULT runs execute: invoke is checked with the UI open (ROADMAP, phase 2 notes)
bpy.ops.asset_validator.hard_surface_prep(angle=math.radians(60))
at_60 = sharp_of(octo.data).sum()
bpy.ops.asset_validator.hard_surface_prep()
check("Sharp Angle: 60° marks the 16 rims, the 30° default the 8 tube edges too",
      at_60 == 16 and sharp_of(octo.data).sum() == 24, f"{at_60}, {sharp_of(octo.data).sum()}")
tube = from_bm("Tube", lambda bm: bmesh.ops.create_cone(bm, cap_ends=False, segments=8, radius1=1.0, radius2=1.0, depth=2.0))
hard_surface.prep_mesh(tube, config(), math.radians(60), bevel=False)
check("with nothing sharp at the Prep angle, Auto Unwrap seams by that angle too (the 45° tube stays one island)",
      islands(tube) == 1, f"{islands(tube)} islands")

asset = cube("Asset"); asset_lod = cube("Asset_LOD1"); asset_lod["asset_validator_lod"] = True
lod_uv = read_array(asset_lod.data.uv_layers[0].data, "uv", 2).copy() if asset_lod.data.uv_layers else None
select(asset, asset_lod)
bpy.ops.asset_validator.hard_surface_prep()
check("Prep leaves generated LODs alone", hard_surface.has_weighted_normal(asset) and not asset_lod.modifiers
      and lod_uv is None and not asset_lod.data.uv_layers)
select(asset_lod)
try:
    r = bpy.ops.asset_validator.auto_unwrap()
except RuntimeError as e:
    r = {"CANCELLED"} if "LODs and collision meshes keep their UVs" in str(e) else {"CRASHED: " + str(e)}
check("Auto Unwrap on a LOD alone is cancelled", r == {"CANCELLED"} and not asset_lod.data.uv_layers, str(r))

# AC-7: the mid-poly check
plain = cube("Plain")
lod = cube("Plain_LOD1"); lod["asset_validator_lod"] = True
results = [r for r in engine.run_validation(config(require_weighted_normal=True), [plain, lod]) if r.check_name == "weighted_normal"]
check("AC-7: mid-poly profile: an error on the asset with a fix, none on the LOD",
      len(results) == 1 and results[0].object_name == "Plain" and results[0].severity.value == "ERROR" and results[0].fix is not None,
      str([(r.object_name, r.message) for r in results]))
results[0].fix()
check("AC-7: the fix adds it and the error goes", not shading.check_weighted_normal([plain], config(require_weighted_normal=True)))
plain.modifiers[0].show_viewport = False
check("edge case: a disabled Weighted Normal doesn't count", len(shading.check_weighted_normal([plain], config(require_weighted_normal=True))) == 1)
check("AC-7: without the profile, no result", not shading.check_weighted_normal([cube("Other")], config()))

# Edge cases: linked duplicates, meshes without faces, nothing selected
twin_a = cube("TwinA"); twin_b = bpy.data.objects.new("TwinB", twin_a.data); bpy.context.scene.collection.objects.link(twin_b)
empty_mesh = bpy.data.objects.new("NoFaces", bpy.data.meshes.new("NoFaces")); bpy.context.scene.collection.objects.link(empty_mesh)
select(twin_a, twin_b, empty_mesh)
r = bpy.ops.asset_validator.hard_surface_prep()
check("edge case: linked duplicates both get the modifiers, a mesh without faces is skipped",
      r == {"FINISHED"} and all(hard_surface.has_weighted_normal(o) for o in (twin_a, twin_b)) and not empty_mesh.modifiers)
check("Prep restores Object Mode and the selection", bpy.context.mode == "OBJECT" and twin_a.select_get() and twin_b.select_get())
bpy.ops.object.select_all(action="DESELECT")
try:
    r = bpy.ops.asset_validator.hard_surface_prep()
except RuntimeError as e:  # bpy.ops raises for a reported ERROR, and for a crash: tell them apart
    r = {"CANCELLED"} if "Select at least one asset mesh" in str(e) else {"CRASHED: " + str(e)}
check("Prep with nothing selected is cancelled", r == {"CANCELLED"}, str(r))

try:
    bav.unregister(); say("PASS  unregister clean")
except Exception:
    say("FAIL  unregister\n" + traceback.format_exc())
say("DONE")
