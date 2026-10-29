import sys, os, traceback, math
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT_DIR = os.path.join(HERE, "_out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(__file__))[0] + ".txt")
sys.path.insert(0, REPO)
out = open(OUT, "w", encoding="utf-8")
def say(m): out.write(m + "\n"); out.flush()
def check(name, cond, extra=""): say(f"{'PASS' if cond else 'FAIL'}  {name}  {extra}")
import bpy, bmesh
from mathutils import Vector
try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import blender_asset_validator as bav
    from blender_asset_validator.operations import topology as topo, lod as lod_ops, cleanup
    from blender_asset_validator.core import engine
    bav.register(); CFG = engine.load_config()
    def mk(name, bm, smooth=False):
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        for p in me.polygons: p.use_smooth = smooth
        o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o); return o
    def tris(m): return sum(len(p.vertices) - 2 for p in m.polygons)
    def _bm(o): b = bmesh.new(); b.from_mesh(o.data); return b

    # 3+ faces on an edge (a fin) and two shells touching at one vertex: cut open, then remeshed
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    e = next(e for e in bm.edges if e.verts[0].co.z > 0.5 and e.verts[1].co.z > 0.5)
    tip = bm.verts.new(e.verts[0].co * 1.5); bm.faces.new([e.verts[0], e.verts[1], tip])
    top = max(bm.verts, key=lambda v: v.co.z).co.copy()
    ret = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.5)
    low = min(ret["verts"], key=lambda v: v.co.z)
    bmesh.ops.translate(bm, verts=ret["verts"], vec=top - low.co)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)  # spheres now share the pole vertex
    nm = mk("NonManifold", bm)
    check("fixture is non-manifold", any(topo._manifold_problems(_bm(nm)).values()))
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.calc_center_median().x > 0])
    fl = mk("Flipped", bm)
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    bmesh.ops.split_edges(bm, edges=bm.edges)
    sp = mk("SplitFbx", bm, smooth=True)
    for o, should_work in ((nm, True), (fl, True), (sp, True)):
        try:
            n, note = topo.retopologize(o, 0.5, False, 1e-4); ok = True
            msg = f"{len(n.data.polygons)} quads"
        except RuntimeError as e:
            ok, msg = False, str(e)
        leftover = f"{o.name}_Retopo" in bpy.data.objects
        check(f"retopo {o.name}: {'works after repair' if should_work else 'fails with diagnosis'}",
              ok == should_work and leftover == should_work and (should_work or "3+ faces" in msg), msg[:140])
    def glass(name, thickness, scale):
        # thin closed glass panel: curved box, local units; object scaled like a cm FBX import
        bm = bmesh.new(); bm.loops.layers.uv.new(); bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=12, use_grid_fill=True)
        for v in bm.verts:
            v.co.x *= 2; v.co.z = v.co.z * thickness + 0.3 * v.co.x ** 2
        o = mk(name, bm, smooth=True); o.scale = (scale,) * 3; return o
    for name, thickness, scale in (("GlassThin", 1e-4, 1.0), ("GlassCmScaled", 1e-3, 0.01)):
        g = glass(name, thickness, scale)
        try:
            n, note = topo.retopologize(g, 0.5, False, 1e-4)
            check(f"retopo {name}: thin shell not fused by welding", len(n.data.polygons) > 0, f"{len(n.data.polygons)} quads; {note}")
        except RuntimeError as e:
            check(f"retopo {name}: thin shell not fused by welding", False, str(e)[:200])
    bm = bmesh.new(); bm.loops.layers.uv.new()
    bmesh.ops.create_grid(bm, x_segments=30, y_segments=15, size=1.0, calc_uvs=True)
    for v in bm.verts: v.co.z = 0.3 * v.co.x ** 2
    dup = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])
    bmesh.ops.reverse_faces(bm, faces=[g for g in dup["geom"] if isinstance(g, bmesh.types.BMFace)])
    ds = mk("DoubleSided", bm, smooth=True)
    try:
        n, note = topo.retopologize(ds, 0.5, False, 1e-4)
        check("retopo exact double-sided glass", len(n.data.polygons) > 0, f"{len(n.data.polygons)} quads")
    except RuntimeError as e:
        check("retopo exact double-sided glass", False, str(e)[:200])

    check("retopo: original untouched by the repair", len(sp.data.vertices) == len(sp.data.loops))

    # small loose parts (teeth, rivets) survive instead of being erased by QuadriFlow's quad size
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=1.0)
    for i in range(5):
        r = bmesh.ops.create_cube(bm, size=0.05)
        bmesh.ops.translate(bm, verts=r["verts"], vec=Vector((1.5 + i * 0.2, 0, 0)))
    pp = mk("Parts", bm)
    n, note = topo.retopologize(pp, 0.5, False, 1e-4)
    far = sum(1 for v in n.data.vertices if v.co.x > 1.4)
    check("retopo per part: small parts kept", far == 5 * 8 and "5 small part(s) kept" in note, f"{far} verts, {note}")
    check("retopo per part: no temp objects/meshes left",
          not [d for d in (*bpy.data.objects, *bpy.data.meshes) if d.name.startswith("_AssetValidator")])

    # protected weight no longer hard-blocks collapse
    bm = bmesh.new(); uv = bm.loops.layers.uv.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=1.0, calc_uvs=True)
    for i, f in enumerate(bm.faces):
        for l in f.loops: l[uv].uv += Vector(((i % 50) * 2.0, (i // 50) * 2.0))
    isl = mk("Islands", bm, smooth=True); src = tris(isl.data)
    lod_ops.generate_lods([isl], {"lod": {"levels": [{"ratio": 0.25}]}})
    got = tris(lod_ops.lods_of(isl)[0].data)
    check("all-protected mesh reaches LOD target", abs(got - src / 4) <= src / 4 * 0.05, f"{src} -> {got}")

    # split-vertex hard edges are not welded by Clean Topology
    bm = bmesh.new(); bm.loops.layers.uv.new(); bmesh.ops.create_cube(bm, size=2.0, calc_uvs=True)
    bmesh.ops.split_edges(bm, edges=bm.edges)
    split = mk("SplitCube", bm, smooth=True); v0 = len(split.data.vertices)
    topo.clean_topology(split, CFG)
    check("split cube: vertices not welded", len(split.data.vertices) == v0, f"{v0} -> {len(split.data.vertices)}")

    # custom normals on a regular (non-LOD) mesh are re-transferred, not left stale
    bm = bmesh.new(); bm.loops.layers.uv.new(); bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0, calc_uvs=True)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    cn = mk("CustomN", bm, smooth=True)
    cn.data.normals_split_custom_set_from_vertices([v.co.normalized() for v in cn.data.vertices])
    topo.clean_topology(cn, CFG)
    normals = [n.vector for n in cn.data.corner_normals]
    err = max((normals[l.index] - cn.data.vertices[l.vertex_index].co.normalized()).length for l in cn.data.loops)
    check("custom normals re-transferred after clean", cn.data.has_custom_normals and err < 0.05, f"max err {err:.4f}")
    check("no temp objects left", not [o for o in bpy.data.objects if o.name.startswith("_AssetValidator")])

    # linked duplicates of a cleaned LOD keep sharing; LOD clean keeps normals
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    s = mk("Src", bm, smooth=True); lod_ops.generate_lods([s], CFG)
    lod1 = lod_ops.lods_of(s)[0]; twin = lod1.copy(); bpy.context.scene.collection.objects.link(twin)
    topo.clean_topology(lod1, CFG)
    check("LOD clean: mesh still shared with linked duplicate", twin.data == lod1.data and lod1.data.has_custom_normals)

    # zero-area triangle in the sampled surface -> finite UV
    me = bpy.data.meshes.new("deg"); me.from_pydata([(0,0,0),(1,0,0),(2,0,0)], [], [(0,1,2)]); me.uv_layers.new()
    uv = topo.Surface(me).uv_at(Vector((0.5, 0.1, 0)), 0, 0)
    check("uv_at on zero-area tri is finite", all(math.isfinite(c) for c in uv), str(tuple(uv)))

    # degenerate fix only touches the bad faces: two closed shells 0.05 mm apart (glass with
    # thickness) stay separate instead of being welded into a non-manifold, misoriented mess
    bm = bmesh.new(); bm.loops.layers.uv.new()
    bmesh.ops.create_cube(bm, size=1.0)
    inner = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    bmesh.ops.scale(bm, vec=(0.9999, 0.9999, 0.9999), verts=inner)  # 0.05 mm inside, under the 0.1 mm merge distance
    bmesh.ops.reverse_faces(bm, faces=list({f for v in inner for f in v.link_faces}))
    far = [bm.verts.new(p) for p in ((5, 0, 0), (6, 0, 0), (7, 0, 0))]
    bm.faces.new(far)  # collinear: zero area
    shells = mk("TwoShells", bm)
    faces0 = len(shells.data.polygons)
    msg = cleanup.fix_degenerate_faces(shells, CFG)
    bm = bmesh.new(); bm.from_mesh(shells.data)
    fins = sum(1 for e in bm.edges if len(e.link_faces) > 2); wrong = len(cleanup.wrong_way_faces(bm)[0])
    used = sum(1 for v in bm.verts if v.link_faces); bm.free()
    check("degenerate fix: only the bad face goes, shells not welded",
          len(shells.data.polygons) == faces0 - 1 and used == 16 and not fins and not wrong,
          f"{msg}; {faces0} -> {len(shells.data.polygons)} faces, {used} verts in faces, {fins} fins, {wrong} wrong")

    # one NaN UV (broken import) must not put every triangle in one overlap-grid cell and hang Validate
    from blender_asset_validator.checks import uvs
    import time
    bm = bmesh.new(); bm.loops.layers.uv.new()
    bmesh.ops.create_grid(bm, x_segments=150, y_segments=150, size=1.0, calc_uvs=True)  # 45k tris: ~4 s without the guard
    nan_uv = mk("NanUV", bm)
    nan_uv.data.uv_layers.active.data[0].uv = (float("nan"), 0.0)
    t = time.perf_counter(); uvs.check_uvs([nan_uv], CFG); elapsed = time.perf_counter() - t
    check("UV overlap with a NaN UV stays fast", elapsed < 1.0, f"{elapsed:.2f}s")

    # flat_angle from config drives LOD planar dissolve too
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
    lo = mk("LowSphere", bm)
    cfg = dict(CFG); cfg["topology"] = dict(CFG["topology"], flat_angle=60.0); cfg["lod"] = {"levels": [{"ratio": 1.0}]}
    lod_ops.generate_lods([lo], cfg)
    check("LOD planar dissolve honours topology.flat_angle", tris(lod_ops.lods_of(lo)[0].data) < tris(lo.data),
          f"{tris(lo.data)} -> {tris(lod_ops.lods_of(lo)[0].data)}")

    # hard-edged custom normals (a baked hard-surface mesh) survive a transfer and Fix
    def flat_normals(o):  # every edge hard: each corner gets its face's normal
        o.data.normals_split_custom_set([tuple(p.normal) for p in o.data.polygons for _ in p.loop_indices])
    def off_face(me):  # worst corner normal against its own face, degrees
        return max(math.degrees(Vector(me.corner_normals[i].vector).angle(p.normal, 0)) for p in me.polygons for i in p.loop_indices)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bmesh.ops.triangulate(bm, faces=bm.faces)
    hard = mk("HardCube", bm, smooth=True); flat_normals(hard)
    copy = hard.data.copy(); topo.transfer_normals(copy, hard)
    check("normals transferred onto an identical mesh keep hard edges", off_face(copy) < 1, f"{off_face(copy):.0f} deg off")
    bpy.data.meshes.remove(copy)
    bm = bmesh.new(); bm.from_mesh(hard.data); bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:2]); bm.to_mesh(hard.data); bm.free()
    msg = cleanup.fix_normals(hard, CFG)
    check("fix normals on hard edges: every corner faces its face", msg and off_face(hard.data) < 1, f"{msg}; {off_face(hard.data):.0f} deg off")
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
    bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.calc_center_median().x > 0.3])
    outward = mk("FlippedFacesOutwardNormals", bm, smooth=True)
    outward.data.normals_split_custom_set_from_vertices([v.co.normalized() for v in outward.data.vertices])
    cleanup.fix_normals(outward, CFG)
    me = outward.data
    inward = sum(Vector(me.corner_normals[i].vector).dot(p.center) <= 0 for p in me.polygons for i in p.loop_indices)
    check("fix normals: custom normals that already faced out stay out", not inward, f"{inward} corners inward")

    # a small consistent closed shell recalc_face_normals turns inside out: its volume says it's fine
    cone = bpy.data.meshes.new("Cone10")
    cone.from_pydata([(-0.319, 1.04, -3.851), (0.602, 0.886, -3.727), (1.227, -0.95, -3.402), (0.414, -0.753, -3.508),
                      (-1.349, -0.678, -3.213), (-1.228, 0.988, -2.891), (-0.38, -0.376, 3.396)], [],
                     [(0, 6, 1), (1, 6, 2), (3, 4, 5), (2, 6, 3), (1, 2, 3), (3, 6, 4), (5, 0, 1), (1, 3, 5), (4, 6, 5), (5, 6, 0)])
    bm = bmesh.new(); bm.from_mesh(cone)
    check("10-face cone facing out: nothing wrong or inward", cleanup.wrong_way_faces(bm)[:2] == ([], []), str(cleanup.wrong_way_faces(bm)))
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    check("the same cone inside out: inward", cleanup.wrong_way_faces(bm)[:2] == ([], list(range(10))), str(cleanup.wrong_way_faces(bm)))
    bm.free(); bpy.data.meshes.remove(cone)
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1.0); bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:3])
    check("open grid: the 3 odd faces are wrong, not the other 13", cleanup.wrong_way_faces(bm)[0] == [0, 1, 2], str(cleanup.wrong_way_faces(bm)[0]))
    bm.free()
    # a room (closed, inward on purpose) with one stray face, as a collapse leaves on its LOD: it stays a room
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=3, use_grid_fill=True)
    bmesh.ops.reverse_faces(bm, faces=bm.faces); bm.faces.ensure_lookup_table(); bmesh.ops.reverse_faces(bm, faces=[bm.faces[5]])
    room = mk("Room", bm)
    w, i, _ = cleanup.wrong_way_faces(_bm(room))
    check("inward room with a stray face: only that face is wrong", w == [5] and len(i) == len(room.data.polygons) - 1, f"wrong {len(w)}, inward {len(i)}")
    cleanup.fix_normals(room, CFG)
    w, i, _ = cleanup.wrong_way_faces(_bm(room))
    check("fixed, the room still faces inward", not w and len(i) == len(room.data.polygons), f"wrong {len(w)}, inward {len(i)}")

    # LODs come out export-clean: no loose geometry or odd flipped faces, carried over or made by the collapse
    bm = bmesh.new(); bm.loops.layers.uv.new(); bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0, calc_uvs=True)
    bm.faces.ensure_lookup_table(); bmesh.ops.reverse_faces(bm, faces=[bm.faces[40], bm.faces[41]])
    bm.edges.new((bm.verts.new((2, 0, 0)), bm.verts.new((3, 0, 0))))
    flawed = mk("Flawed", bm, smooth=True)
    lod_ops.generate_lods([flawed], CFG)
    left = [r.message for o in lod_ops.lods_of(flawed) for r in engine.run_validation(CFG, [o]) if r.check_name in ("normals", "manifold")]
    check("LODs: no loose geometry or flipped faces", len(lod_ops.lods_of(flawed)) == 3 and not left, str(left))
    lod_ops.generate_lods([outward], CFG)  # custom normals cleared for the decimation, then transferred back
    check("LODs of a mesh with custom normals get them back", all(o.data.has_custom_normals for o in lod_ops.lods_of(outward)))

    # a parented part: warned when the export drops the link to its parent
    from blender_asset_validator.checks.transforms import check_transforms
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); body = mk("Body", bm)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=0.2); part = mk("Part", bm); part.parent = body
    def warned(objs, cfg): return [r.object_name for r in check_transforms(objs, cfg) if "drops that link" in r.message]
    one_file = dict(CFG, export=dict(CFG["export"], individual_files=False))
    unreal_one_file = dict(one_file, lod=dict(CFG["lod"], export_target="unreal"))
    lod_ops.generate_lods([part], CFG)
    check("parented part warned that the hierarchy is lost", warned([body, part], CFG) == ["Part"], str(warned([body, part], CFG)))
    check("no hierarchy warning when everything exports to one file", not warned([body, part], one_file))
    check("one file without the parent: warned", warned([part], one_file) == ["Part"])
    check("one file, an Unreal LOD group in the parent's place: warned", warned([body, part], unreal_one_file) == ["Part"])
    check("no hierarchy warning on the part's LODs", not warned(lod_ops.lods_of(part), CFG))

    bav.unregister()
    say("DONE")
except Exception:
    say("EXCEPTION\n" + traceback.format_exc())
