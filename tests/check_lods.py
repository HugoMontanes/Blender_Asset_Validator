import sys, os, traceback, random
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT_DIR = os.path.join(HERE, "_out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(__file__))[0] + ".txt")
sys.path.insert(0, REPO)

log = open(OUT, "w", encoding="utf-8")
def say(m): log.write(m + "\n"); log.flush()
def check(name, cond, extra=""): say(f"{'PASS' if cond else 'FAIL'}  {name}  {extra}")

import bpy, bmesh
try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import blender_asset_validator as bav
    from blender_asset_validator.operations import lod as lod_ops, topology as topo
    from blender_asset_validator.core.mesh_utils import bake_mesh
    from blender_asset_validator.core import engine
    bav.register()
    say("Blender " + bpy.app.version_string)

    CFG = {"lod": {"collection": "LODs", "levels": [
        {"suffix": "_LOD1", "ratio": 0.5}, {"suffix": "_LOD2", "ratio": 0.25}, {"suffix": "_LOD3", "ratio": 0.1}]}}

    def obj_from_bm(name, bm, mats=1, smooth=False):
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        for i in range(mats):
            me.materials.append(bpy.data.materials.new(f"{name}_M{i}"))
        for p in me.polygons: p.use_smooth = smooth
        o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
        return o

    def tris(o): return sum(len(p.vertices) - 2 for p in o.data.polygons)

    def border(o):
        bm = bmesh.new(); bm.from_mesh(o.data)
        edges = [e for e in bm.edges if len(e.link_faces) == 1]
        length = sum(e.calc_length() for e in edges)
        off = max((min(1 - abs(v.co.x), 1 - abs(v.co.y)) for e in edges for v in e.verts), default=0)
        bm.free(); return length, off

    def uv_borders(o):
        bm = bmesh.new(); bm.from_mesh(o.data)
        n = sum(topo._is_uv_border(e, list(bm.loops.layers.uv.values())) for e in bm.edges if len(e.link_faces) == 2)
        bm.free(); return n

    # A: flat grid, 2 materials -> planar dissolve should crush it, keeping borders/materials
    bm = bmesh.new(); bm.loops.layers.uv.new(); bmesh.ops.create_grid(bm, x_segments=100, y_segments=100, size=1.0, calc_uvs=True)
    for f in bm.faces: f.material_index = 0 if f.calc_center_median().x < 0 else 1
    flat = obj_from_bm("Flat", bm, mats=2)
    # B: smooth UV sphere with seam
    bm = bmesh.new(); bm.loops.layers.uv.new(); bmesh.ops.create_uvsphere(bm, u_segments=128, v_segments=64, radius=1.0, calc_uvs=True)
    sphere = obj_from_bm("Sphere", bm, smooth=True)
    # C: noisy open grid -> border must survive collapse
    random.seed(1)
    bm = bmesh.new(); bm.loops.layers.uv.new(); bmesh.ops.create_grid(bm, x_segments=80, y_segments=80, size=1.0, calc_uvs=True)
    for v in bm.verts: v.co.z = random.uniform(-0.05, 0.05)
    noisy = obj_from_bm("Noisy", bm)
    noisy_border = border(noisy)

    meshes_before = len(bpy.data.meshes)
    log_lines = lod_ops.generate_lods([flat, sphere, noisy], CFG)
    for l in log_lines: say("   " + l)

    fl = lod_ops.lods_of(flat)
    check("flat: LOD names", [o.name for o in fl] == ["Flat_LOD1", "Flat_LOD2", "Flat_LOD3"])
    check("flat: planar dissolve crushes coplanar grid", tris(fl[0]) < 200, f"{tris(flat)} -> {tris(fl[0])}")
    check("flat: both materials kept", {p.material_index for p in fl[2].data.polygons} == {0, 1})
    check("flat: dims unchanged", (fl[2].dimensions - flat.dimensions).length < 1e-4)

    sl = lod_ops.lods_of(sphere)
    src = tris(sphere)
    for o, r in zip(sl, (0.5, 0.25, 0.1)):
        t = tris(o)
        check(f"sphere {o.name}: tris near target", abs(t - src * r) <= src * r * 0.1, f"{t} vs {round(src*r)}")
        dev = max(abs(v.co.length - 1.0) for v in o.data.vertices)
        check(f"sphere {o.name}: shape kept", dev < 0.02, f"max radial dev {dev:.4f}")
        check(f"sphere {o.name}: UV seam kept", uv_borders(o) > 0, f"{uv_borders(o)} uv-border edges")
        check(f"sphere {o.name}: all triangles", all(len(p.vertices) == 3 for p in o.data.polygons))
        check(f"sphere {o.name}: custom normals", o.data.has_custom_normals)
        check(f"sphere {o.name}: no protect group", lod_ops._PROTECT_GROUP not in o.vertex_groups)
        check(f"sphere {o.name}: in LODs collection", [c.name for c in o.users_collection] == ["LODs"])
        check(f"sphere {o.name}: own mesh", o.data.users == 1 and o.data != sphere.data)

    nl = lod_ops.lods_of(noisy)
    for o in nl:
        length, off = border(o)
        check(f"noisy {o.name}: border kept", off < 1e-4 and abs(length - noisy_border[0]) < 0.05,
              f"border len {length:.3f} vs {noisy_border[0]:.3f}, max off-border {off:.5f}")

    # baseline: plain collapse at LOD3 ratio, to see what the protection buys
    plain = noisy.copy(); plain.data = noisy.data.copy(); bpy.context.scene.collection.objects.link(plain)
    m = plain.modifiers.new("d", "DECIMATE"); m.ratio = 0.1
    plain.data = bake_mesh(plain); plain.modifiers.clear()
    say(f"   baseline plain collapse 0.1: border len {border(plain)[0]:.3f}, max off-border {border(plain)[1]:.5f}")
    bpy.data.objects.remove(plain)

    check("no temp objects left", not [o for o in bpy.data.objects if o.name.startswith("_AssetValidator")])
    check("source meshes untouched", lod_ops._PROTECT_GROUP not in sphere.vertex_groups and tris(sphere) == src)
    after_first = len(bpy.data.meshes)
    lod_ops.generate_lods([flat, sphere, noisy], CFG)
    check("regenerate: no duplicate objects", len(lod_ops.lods_of(sphere)) == 3)
    check("regenerate: no orphan meshes", len(bpy.data.meshes) == after_first,
          f"{meshes_before} -> {after_first} -> {len(bpy.data.meshes)}")

    # source with its own modifier (Mirror): LOD counts from the evaluated mesh
    bm = bmesh.new(); bm.loops.layers.uv.new(); bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=1.0, calc_uvs=True)
    half = obj_from_bm("Half", bm, smooth=True)
    half.modifiers.new("mirror", "MIRROR").use_axis[0] = True
    from blender_asset_validator.core.mesh_utils import evaluated_triangle_count
    ev = evaluated_triangle_count(half)
    lod_ops.generate_lods([half], CFG)
    hl = lod_ops.lods_of(half)
    check("modifier source: LOD1 relative to evaluated tris", abs(tris(hl[0]) - ev * 0.5) <= ev * 0.05, f"{tris(hl[0])} vs {ev*0.5:.0f}")
    check("modifier source: LOD has no modifiers", not hl[0].modifiers)
    from blender_asset_validator.core.steps import APPROVED
    half[APPROVED] = [0, 1, 2]
    lod_ops.generate_lods([half], CFG)
    check("LODs don't inherit the source's step approvals", APPROVED not in lod_ops.lods_of(half)[0] and list(half[APPROVED]) == [0, 1, 2])

    # operator path
    bpy.ops.object.select_all(action="DESELECT"); sphere.select_set(True); bpy.context.view_layer.objects.active = sphere
    check("operator FINISHED", bpy.ops.asset_validator.generate_lods() == {"FINISHED"})

    # Faces stacked on the same vertices survived the collapse (1,182 in a papercraft robot's LODs)
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    verts, faces = [v.co[:] for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces]; bm.free()
    dup_mesh = bpy.data.meshes.new("Dups"); dup_mesh.from_pydata(verts, [], faces + [f[::-1] for f in faces[::50]])
    dup_mesh.materials.append(bpy.data.materials.new("DupsM"))
    dups = bpy.data.objects.new("Dups", dup_mesh); bpy.context.scene.collection.objects.link(dups)
    lod_ops.generate_lods([dups], CFG)
    invalid = [l.name for l in lod_ops.lods_of(dups) if engine._invalid_mesh(l.data)]
    check("LODs come out as valid meshes (no duplicate faces), even from a source with some", len(lod_ops.lods_of(dups)) == 3 and not invalid, str(invalid))
    # LOD3 crumpled a 48-sided barrel (1.3 % of its size) with no word: a LOD that strays past lod.max_deviation says so
    shape = lod_ops._shape(dups.data, dups.matrix_world)
    check("LOD deviation: a mesh against itself strays 0", lod_ops._stray(shape, shape) < 1e-6)
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.5, radius2=0.5, depth=1.4)
    cyl = obj_from_bm("Cyl16", bm)
    lod_ops.generate_lods([cyl, dups], CFG)
    strayed = sorted(l.name for o in (cyl, dups) for l in lod_ops.lods_of(o) if lod_ops.STRAY in l)
    check("LOD deviation: a 16-sided cylinder's LODs stray (1.4 % at half its 60 tris), a dense sphere's don't",
          strayed == ["Cyl16_LOD1", "Cyl16_LOD2", "Cyl16_LOD3"], str(strayed))

    # A copy of a LOD keeps its properties: regenerating deleted it with the LODs, and the tools skipped it
    from blender_asset_validator.core.roles import role, lod_source
    renamed = lod_ops.lods_of(dups)[0]; renamed.name = "SM_Dups_LOD1"  # renamed, then copied: the copy isn't the LOD
    kept = renamed.copy(); bpy.context.scene.collection.objects.link(kept)
    lod_ops.generate_lods([dups], CFG)
    check("a copy of a LOD survives regenerating them, as an asset of its own",
          kept.name in bpy.data.objects and role(kept, CFG) == "asset" and lod_source(kept) is None
          and kept not in lod_ops.lods_of(dups) and [role(l, CFG) for l in lod_ops.lods_of(dups)] == ["lod"] * 3, kept.name)

    # Every evaluation in the artist's scene re-read all its objects: LODs of a 940-part robot took past 25 min.
    # 4x the parts: about 5x the time now (removing an ID scans the file), it was 16-24x
    import time
    def parts(n, tag):
        made = []
        for i in range(n):
            bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.3)
            made.append(obj_from_bm(f"Part{tag}{i}", bm))
        return made
    timings = []
    for n in (50, 200):
        group = parts(n, n)
        t = time.perf_counter(); lod_ops.generate_lods(group, CFG); timings.append(time.perf_counter() - t)
    check("LODs of many parts scale with the parts, not their square", timings[1] < 8 * timings[0],
          f"50 parts {timings[0]:.1f}s, 200 parts {timings[1]:.1f}s ({timings[1] / timings[0]:.1f}x)")
    check("LODs leave no scratch scene behind", len(bpy.data.scenes) == 1, [s.name for s in bpy.data.scenes])
    bav.unregister()
    say("DONE")
except Exception:
    say("EXCEPTION\n" + traceback.format_exc())
