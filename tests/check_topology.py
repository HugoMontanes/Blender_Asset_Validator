import sys, os, traceback, random, math
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
from mathutils import Vector
try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import blender_asset_validator as bav
    from blender_asset_validator.operations import topology as topo, lod as lod_ops
    from blender_asset_validator.checks import topology as topo_check
    from blender_asset_validator.core import engine
    bav.register()
    say("Blender " + bpy.app.version_string)
    CFG = engine.load_config()

    def new_bm(): bm = bmesh.new(); bm.loops.layers.uv.new(); return bm
    def obj_from_bm(name, bm, mats=1, smooth=False):
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        for i in range(mats): me.materials.append(bpy.data.materials.new(f"{name}_M{i}"))
        for p in me.polygons: p.use_smooth = smooth
        o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
        return o
    def quad_pct(o): return 100 * sum(len(p.vertices) == 4 for p in o.data.polygons) // max(1, len(o.data.polygons))
    def tris(o): return sum(len(p.vertices) - 2 for p in o.data.polygons)

    def uv_error(o, surface):
        """Max UV difference vs the original surface, sampled per face like resample_faces."""
        bm = bmesh.new(); bm.from_mesh(o.data); layer = bm.loops.layers.uv.active; err = 0.0
        for f in bm.faces:
            hit = surface.nearest(f.calc_center_median())
            for l in f.loops:
                err = max(err, (l[layer].uv - surface.uv_at(l.vert.co, hit[2], 0)).length)
        bm.free(); return err

    def vert_uv_error(o, surface):
        """Max UV difference vs the original surface at each vertex (seam verts are pinned, skipped)."""
        bm = bmesh.new(); bm.from_mesh(o.data); layer = bm.loops.layers.uv.active; err = 0.0
        for v in bm.verts:
            uvs = {tuple(round(c, 6) for c in l[layer].uv) for l in v.link_loops}
            if len(uvs) != 1: continue
            hit = surface.nearest(v.co)
            err = max(err, (v.link_loops[0][layer].uv - surface.uv_at(v.co, hit[2], 0)).length)
        bm.free(); return err

    def surf_dev(o, surface):
        return max((v.co - surface.nearest(v.co)[0]).length for v in o.data.vertices)

    # 1. triangulated flat grid -> quads -> flat loops dissolved
    bm = new_bm(); bmesh.ops.create_grid(bm, x_segments=40, y_segments=40, size=1.0, calc_uvs=True)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    flat = obj_from_bm("FlatTris", bm)
    s_flat = topo.Surface(flat.data); dims = flat.dimensions.copy(); n0 = len(flat.data.polygons)
    say("   " + topo.clean_topology(flat, CFG))
    check("flat tris: collapses to a handful of quads", len(flat.data.polygons) <= 4 and quad_pct(flat) == 100, f"{n0} -> {len(flat.data.polygons)}")
    check("flat tris: dims kept", (flat.dimensions - dims).length < 1e-5)
    check("flat tris: UVs kept", uv_error(flat, s_flat) < 1e-4, f"{uv_error(flat, s_flat):.6f}")

    # 2. triangulated smooth UV sphere with seam + 2 materials
    bm = new_bm(); bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0, calc_uvs=True)
    for f in bm.faces: f.material_index = 0 if f.calc_center_median().z >= 0 else 1
    bmesh.ops.triangulate(bm, faces=bm.faces)
    sph = obj_from_bm("SphereTris", bm, mats=2, smooth=True)
    s_sph = topo.Surface(sph.data); n0 = len(sph.data.polygons); q0 = quad_pct(sph)
    say("   " + topo.clean_topology(sph, CFG))
    check("sphere tris: mostly quads again", quad_pct(sph) >= 90, f"{q0}% -> {quad_pct(sph)}%")
    check("sphere tris: same tri count (no shape loss)", tris(sph) == n0, f"{n0} -> {tris(sph)}")
    check("sphere tris: on original surface", surf_dev(sph, s_sph) < 1e-4, f"{surf_dev(sph, s_sph):.6f}")
    check("sphere tris: UVs kept", vert_uv_error(sph, s_sph) < 1e-4, f"{vert_uv_error(sph, s_sph):.6f}")
    check("sphere tris: materials kept", {p.material_index for p in sph.data.polygons} == {0, 1})

    # 3. jittered, slightly curved grid -> relax evens edge lengths, stays on the surface
    random.seed(3)
    bm = new_bm(); bmesh.ops.create_grid(bm, x_segments=30, y_segments=30, size=1.0, calc_uvs=True)
    for v in bm.verts:
        if not v.is_boundary:
            v.co.x += random.uniform(-0.02, 0.02); v.co.y += random.uniform(-0.02, 0.02)
        v.co.z = 0.3 * math.sin(v.co.x * 2) * math.cos(v.co.y * 2)
    jit = obj_from_bm("Jitter", bm, smooth=True)
    def edge_cv(o):
        ls = [(o.data.vertices[e.vertices[0]].co - o.data.vertices[e.vertices[1]].co).length for e in o.data.edges]
        m = sum(ls) / len(ls); return (sum((l - m) ** 2 for l in ls) / len(ls)) ** 0.5 / m
    s_jit = topo.Surface(jit.data); cv0 = edge_cv(jit)
    border0 = sorted(tuple(round(c, 6) for c in v.co) for v in jit.data.vertices if abs(v.co.x) > 0.9999 or abs(v.co.y) > 0.9999)
    say("   " + topo.clean_topology(jit, CFG))
    check("jitter: edge flow more even", edge_cv(jit) < cv0 * 0.8, f"edge-length CV {cv0:.3f} -> {edge_cv(jit):.3f}")
    check("jitter: on original surface", surf_dev(jit, s_jit) < 1e-3, f"{surf_dev(jit, s_jit):.6f}")
    border1 = sorted(tuple(round(c, 6) for c in v.co) for v in jit.data.vertices if abs(v.co.x) > 0.9999 or abs(v.co.y) > 0.9999)
    check("jitter: border untouched", border0 == border1)
    check("jitter: UVs follow the surface", vert_uv_error(jit, s_jit) < 1e-4, f"{vert_uv_error(jit, s_jit):.6f}")

    # 4. subdivided cube: hard corners must survive
    bm = new_bm(); bmesh.ops.create_cube(bm, size=2.0, calc_uvs=True)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=5, use_grid_fill=True)
    cube = obj_from_bm("Cube", bm); dims = cube.dimensions.copy(); n0 = len(cube.data.polygons)
    s_cube = topo.Surface(cube.data)
    say("   " + topo.clean_topology(cube, CFG))
    check("cube: UVs kept", uv_error(cube, s_cube) < 1e-4, f"{uv_error(cube, s_cube):.6f}")
    check("cube: flat faces collapsed", len(cube.data.polygons) < n0, f"{n0} -> {len(cube.data.polygons)}")
    check("cube: corners kept", (cube.dimensions - dims).length < 1e-5 and all(
        any((v.co - Vector(c)).length < 1e-5 for v in cube.data.vertices) for c in [(1,1,1),(-1,-1,-1),(1,-1,1),(-1,1,-1)]))

    # 5. topology check
    def stats(o):
        bm = bmesh.new(); bm.from_mesh(o.data)
        s = topo_check.topology_stats(bm, 5, math.radians(10), 0.1, math.radians(30)); bm.free(); return s
    bm = new_bm(); bmesh.ops.create_cube(bm, size=2.0); bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=3, use_grid_fill=True)
    for v in bm.verts: v.co.normalize()
    qs = obj_from_bm("QuadSphere", bm)
    check("check: quad-sphere corner poles flagged as curved", stats(qs)["curved_poles"] == 8, str(stats(qs)))
    bm = new_bm(); bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
    uvs = obj_from_bm("UvSphere", bm)
    check("check: UV-sphere 16-edge poles flagged", stats(uvs)["high_poles"] == 2, str(stats(uvs)))
    bm = new_bm(); bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1.0)
    grid = obj_from_bm("Grid", bm)
    check("check: clean grid passes", stats(grid) == {"high_poles": 0, "curved_poles": 0, "slivers": 0}, str(stats(grid)))
    bm = new_bm(); bmesh.ops.create_cube(bm, size=2.0); hard = obj_from_bm("HardCube", bm)
    check("check: hard-corner poles of a cube not flagged", stats(hard)["curved_poles"] == 0, str(stats(hard)))
    bm = new_bm(); a, b, c = (bm.verts.new(p) for p in [(0,0,0),(1,0,0),(0.5,0.01,0)]); bm.faces.new((a, b, c))
    sliver = obj_from_bm("Sliver", bm)
    check("check: sliver flagged", stats(sliver)["slivers"] == 1)
    res = topo_check.check_topology([qs, uvs, grid], CFG)
    check("check: registered warnings", len(res) == 2 and all(r.check_name == "topology" for r in res), "; ".join(r.message for r in res))

    # 6. retopologize (QuadriFlow) on the cleaned 2-material sphere copy
    bm = new_bm(); bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=1.0, calc_uvs=True)
    for f in bm.faces: f.material_index = 0 if f.calc_center_median().z >= 0 else 1
    rs = obj_from_bm("Rsphere", bm, mats=2, smooth=True)
    s_rs = topo.Surface(rs.data); n0 = tris(rs)
    new = topo.retopologize(bpy.context, rs, 0.5, False, 1e-4)
    say(f"   retopo: {n0} tris -> {len(new.data.polygons)} faces, {quad_pct(new)}% quads")
    check("retopo: all quads", quad_pct(new) == 100)
    check("retopo: face count near target", abs(tris(new) - n0 * 0.5) < n0 * 0.5 * 0.3, f"{tris(new)} tris vs {n0*0.5:.0f}")
    check("retopo: on original surface", surf_dev(new, s_rs) < 1e-4, f"{surf_dev(new, s_rs):.6f}")
    mat_ok = sum((p.material_index == 0) == (p.center.z >= 0) for p in new.data.polygons) / len(new.data.polygons)
    check("retopo: materials resampled", mat_ok > 0.97, f"{mat_ok:.1%}")
    check("retopo: UV map + seams", bool(new.data.uv_layers) and any(e.use_seam for e in new.data.edges))
    check("retopo: UVs match original", uv_error(new, s_rs) < 1e-3, f"{uv_error(new, s_rs):.6f}")
    check("retopo: custom normals", new.data.has_custom_normals)
    check("retopo: name + collection", new.name == "Rsphere_Retopo" and new.users_collection == rs.users_collection)

    # 7. operators (non-manifold mesh: QuadriFlow must fail cleanly)
    bm = new_bm(); vs = [bm.verts.new(p) for p in [(0,0,0),(1,0,0),(0,1,0)]]; bm.faces.new(vs)  # QuadriFlow can't remesh one triangle
    nm = obj_from_bm("NonManifold", bm)
    bpy.ops.object.select_all(action="DESELECT")
    nm.select_set(True); bpy.context.view_layer.objects.active = nm
    try:
        r = bpy.ops.asset_validator.retopologize()
        say(f"   retopo non-manifold returned {r}, objects {[o.name for o in bpy.data.objects if 'NonManifold' in o.name]}, visible {nm.visible_get()}")
    except RuntimeError as e:
        r = {"CANCELLED"}; say("   (op error: %s)" % str(e).strip().splitlines()[-1][:200])
    check("operator retopo: QuadriFlow failure handled cleanly", r == {"CANCELLED"} and "NonManifold_Retopo" not in bpy.data.objects and nm.visible_get())
    bpy.ops.object.select_all(action="DESELECT"); qs.select_set(True); grid.select_set(True)
    bpy.context.view_layer.objects.active = qs
    check("operator clean FINISHED", bpy.ops.asset_validator.clean_topology() == {"FINISHED"})
    bpy.ops.object.select_all(action="DESELECT"); uvs.select_set(True); bpy.context.view_layer.objects.active = uvs
    check("operator retopo FINISHED + source hidden", bpy.ops.asset_validator.retopologize(ratio=1.0) == {"FINISHED"}
          and not uvs.visible_get() and bpy.context.active_object.name == "UvSphere_Retopo")

    # 8. LODs with clean_topology
    cfg = dict(CFG); cfg["lod"] = dict(CFG["lod"], clean_topology=True)
    bm = new_bm(); bmesh.ops.create_uvsphere(bm, u_segments=128, v_segments=64, radius=1.0, calc_uvs=True)
    big = obj_from_bm("Big", bm, smooth=True); src = tris(big); s_big = topo.Surface(big.data)
    for l in lod_ops.generate_lods([big], cfg): say("   " + l)
    for o, r in zip(lod_ops.lods_of(big), (0.5, 0.25, 0.1)):
        check(f"clean LOD {o.name}: quad dominant", quad_pct(o) >= 35, f"{quad_pct(o)}% quads")
        check(f"clean LOD {o.name}: tris within target", tris(o) <= src * r * 1.02, f"{tris(o)} vs {src*r:.0f}")
        check(f"clean LOD {o.name}: shape kept", max(abs(v.co.length - 1) for v in o.data.vertices) < 0.01)
        check(f"clean LOD {o.name}: custom normals", o.data.has_custom_normals)
    lod1 = lod_ops.lods_of(big)[0]
    msg = topo.clean_topology(lod1, CFG)
    check("clean on an existing LOD (relaxes onto source)", surf_dev(lod1, s_big) < 1e-3 and lod1.data.has_custom_normals, msg)

    bav.unregister()
    say("DONE")
except Exception:
    say("EXCEPTION\n" + traceback.format_exc())
