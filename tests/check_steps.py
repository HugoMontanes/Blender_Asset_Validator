import sys, os, traceback
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
    from blender_asset_validator.core import engine, state, registry
    from blender_asset_validator.core.steps import STEPS
    from blender_asset_validator.operations import topology as topo
    bav.register()
    CFG = engine.load_config()
    AV = bpy.ops.asset_validator

    def mk(name, fill, smooth=False):
        bm = bmesh.new(); bm.loops.layers.uv.new("UVMap"); fill(bm)
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        for p in me.polygons: p.use_smooth = smooth
        o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
        m = bpy.data.materials.new(name + "Mat"); o.data.materials.append(m)
        return o
    def run(checks, *objs):
        return [r for r in engine.run_validation(CFG, list(objs)) if r.check_name in checks]
    def select(*objs):
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs: o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]

    # every check sits in exactly one step (the last step runs them all)
    names = [c.__name__ for c in registry.get_checks()]
    placed = [n for _, _, checks in STEPS if checks for n in checks]
    check("every check in exactly one step", sorted(placed) == sorted(names), f"{sorted(set(names) ^ set(placed))}")

    # ---------- normals ----------
    def sphere(bm): bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
    half = mk("HalfFlipped", lambda bm: (sphere(bm), bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.calc_center_median().x > 0])))
    inside = mk("InsideOut", lambda bm: (bmesh.ops.create_cube(bm, size=1.0), bmesh.ops.reverse_faces(bm, faces=bm.faces)))
    ok_sphere = mk("GoodSphere", sphere, smooth=True)
    grid = mk("OpenGrid", lambda bm: bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1.0))
    r = run({"normals"}, half, inside, ok_sphere, grid)
    msgs = {x.object_name: x for x in r}
    check("normals: half-flipped sphere is an error", "HalfFlipped" in msgs and msgs["HalfFlipped"].severity.value == "ERROR", str([x.message for x in r]))
    check("normals: inside-out cube is a warning without fix (could be a room)",
          "InsideOut" in msgs and msgs["InsideOut"].severity.value == "WARNING" and msgs["InsideOut"].fix is None)
    check("normals: good sphere and open grid clean", "GoodSphere" not in msgs and "OpenGrid" not in msgs)
    down = mk("GridFacingDown", lambda bm: (bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1.0), bmesh.ops.reverse_faces(bm, faces=bm.faces)))
    def mobius(bm):
        import math
        n = 24; ring = []
        for i in range(n):
            a = 2 * math.pi * i / n; t = a / 2
            c = Vector((math.cos(a), math.sin(a), 0)); w = Vector((math.cos(a) * math.cos(t), math.sin(a) * math.cos(t), math.sin(t))) * 0.3
            ring.append((bm.verts.new(c - w), bm.verts.new(c + w)))
        for i in range(n):
            (a0, a1), (b0, b1) = ring[i], ring[(i + 1) % n]
            bm.faces.new((a0, a1, b1, b0) if i < n - 1 else (a0, a1, b0, b1))  # half twist closes the strip
    mb = mk("Mobius", mobius)
    r2 = run({"normals"}, down, mb)
    check("normals: open grid facing the other way is fine", not any(x.object_name == "GridFacingDown" for x in r2), str([x.message for x in r2]))
    check("normals: Möbius strip reported as can't-orient warning, no fix",
          any(x.object_name == "Mobius" and x.severity.value == "WARNING" and x.fix is None for x in r2))
    msgs["HalfFlipped"].fix()
    check("normals: fix clears the error", not run({"normals"}, half))
    check("normals: fix makes the sphere face outward", all(p.normal.dot(p.center) > 0 for p in half.data.polygons))

    # ---------- manifold ----------
    def loose(bm):
        bmesh.ops.create_cube(bm, size=1.0)
        a, b = bm.verts.new((3, 0, 0)), bm.verts.new((4, 0, 0)); bm.edges.new((a, b)); bm.verts.new((5, 0, 0))
    lo = mk("Loose", loose)
    def fin(bm):
        bmesh.ops.create_cube(bm, size=1.0)
        bm.edges.ensure_lookup_table(); e = bm.edges[0]; bm.faces.new([e.verts[0], e.verts[1], bm.verts.new((3, 3, 3))])
    fn = mk("Fin", fin)
    r = run({"manifold"}, lo, fn, grid, ok_sphere)
    check("manifold: loose geometry warned", any(x.object_name == "Loose" and "loose" in x.message for x in r), str([x.message for x in r]))
    check("manifold: fin edge warned", any(x.object_name == "Fin" and "3+ faces" in x.message for x in r))
    check("manifold: open grid and sphere clean", not any(x.object_name in ("OpenGrid", "GoodSphere") for x in r))
    next(x for x in r if x.object_name == "Loose").fix()
    check("manifold: delete loose leaves the cube", len(lo.data.vertices) == 8 and not run({"manifold"}, lo))

    # ---------- warped quads ----------
    def warped(bm):
        bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=1.0)
        max(bm.verts, key=lambda v: v.co.x + v.co.y).co.z = 0.8
    wq = mk("Warped", warped)
    r = run({"topology"}, wq, ok_sphere, grid)
    w = [x for x in r if "warped" in x.message]
    check("planarity: warped quad flagged", len(w) == 1 and w[0].object_name == "Warped", str([x.message for x in r]))
    w[0].fix()
    check("planarity: fix triangulates only it", len(wq.data.polygons) == 5 and not [x for x in run({"topology"}, wq) if "warped" in x.message])
    wq2 = mk("WarpedRenumbered", warped)
    def w_index(o): return next(p.index for p in o.data.polygons if any(o.data.vertices[i].co.z for i in p.vertices))
    w = next(x for x in run({"topology"}, wq2) if "warped" in x.message)
    bm = bmesh.new(); bm.from_mesh(wq2.data); bm.faces.ensure_lookup_table()
    flat = next(f for f in bm.faces if all(v.co.z == 0 for v in f.verts) and f.index < w_index(wq2))
    bmesh.ops.delete(bm, geom=[flat], context="FACES_ONLY")  # an earlier fix renumbers the faces
    bm.to_mesh(wq2.data); bm.free()
    w.fix()
    check("planarity: fix finds the warped quad again after renumbering",
          len(wq2.data.polygons) == 4 and not [x for x in run({"topology"}, wq2) if "warped" in x.message],
          f"{len(wq2.data.polygons)} faces")

    # ---------- shading ----------
    def sharp_cube(bm):
        bmesh.ops.create_cube(bm, size=1.0)
        uv = bm.loops.layers.uv.active
        for f in bm.faces:
            for l in f.loops: l[uv].uv = (l.vert.co.x + l.vert.co.z, l.vert.co.y + l.vert.co.z)  # one connected UV blob
    sc = mk("SharpNoSeams", sharp_cube)  # flat shading: every edge hard, none on a seam
    sm = mk("SmoothSphere", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0, calc_uvs=True), smooth=True)
    r = run({"shading"}, sc, sm)
    hard = [x for x in r if "hard edge" in x.message]
    info = {x.object_name: x.message for x in r if x.severity.value == "INFO"}
    check("shading: hard edges off seams warned", len(hard) == 1 and hard[0].object_name == "SharpNoSeams", str([x.message for x in r]))
    check("shading: flat cube counts 24 GPU vertices", "24 GPU vertices" in info.get("SharpNoSeams", ""), info.get("SharpNoSeams"))
    check("shading: GPU vertex info for every object", set(info) == {"SharpNoSeams", "SmoothSphere"})

    # ---------- Show ----------
    select(sc, sm)
    state.set_results(r)
    AV.select_result(result_index=r.index(hard[0]))
    sel = sum(1 for e in bmesh.from_edit_mesh(sc.data).edges if e.select)
    check("show: Edit Mode with the hard edges selected", bpy.context.mode == "EDIT_MESH" and sel == 12, f"{bpy.context.mode} {sel}")
    check("show: object selection kept", sm.select_get())
    bpy.ops.object.mode_set(mode="OBJECT")

    # ---------- guided steps ----------
    scene = bpy.context.scene
    scene.asset_validator_guided = True
    half2 = mk("HalfFlippedTwo", lambda bm: (sphere(bm), bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.calc_center_median().x > 0])))
    select(half2)
    AV.go_to_step(index=1)
    names = {x.check_name for x in state.get_results()}
    check("guided: entering a step runs only its checks", names and names <= {"normals", "manifold", "geometry_cleanup"}, str(names))
    try:
        blocked = AV.approve_step() == {"CANCELLED"}
    except RuntimeError as e:  # bpy.ops raises on a reported ERROR
        blocked = "errors" in str(e)
    check("guided: approve blocked by errors", blocked and scene.asset_validator_step == 1 and not scene.asset_validator_approved[1])
    AV.fix_all()
    check("guided: Fix Step re-checks only the step", {x.check_name for x in state.get_results()} <= {"normals", "manifold", "geometry_cleanup"})
    r = AV.approve_step()
    check("guided: approve marks the step and moves on", r == {"FINISHED"} and scene.asset_validator_approved[1] and scene.asset_validator_step == 2)
    check("guided: next step's findings already shown", all(x.check_name in ("ngons", "topology") for x in state.get_results()))
    AV.go_to_step(index=5)
    check("guided: last step runs every check", "shading" in {x.check_name for x in state.get_results()})
    scene.asset_validator_guided = False
    AV.validate()
    check("all-at-once mode runs beyond the last step's checks", "shading" in {x.check_name for x in state.get_results()})

    # ---------- retopo: collapsed parts are kept ----------
    orig = topo._quadriflow
    def collapsing(ctx, mesh, target, sym):
        res = orig(ctx, mesh, target, sym)
        if res is not None:
            bm = bmesh.new(); bm.from_mesh(res)
            bmesh.ops.delete(bm, geom=bm.faces[: len(bm.faces) * 3 // 4], context="FACES")
            bm.to_mesh(res); bm.free()
        return res
    topo._quadriflow = collapsing
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=1.0)
    r2 = bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.5)
    bmesh.ops.translate(bm, verts=r2["verts"], vec=Vector((3, 0, 0)))
    me = bpy.data.meshes.new("TwoParts"); bm.to_mesh(me); bm.free()
    tp = bpy.data.objects.new("TwoParts", me); scene.collection.objects.link(tp)
    try:
        topo.retopologize(bpy.context, tp, 0.5, False, 1e-4)
        check("retopo: all-collapsed mesh raises", False)
    except RuntimeError as e:
        check("retopo: all-collapsed mesh raises with advice", "collapsed" in str(e), str(e))
    def losing(ctx, mesh, target, sym):  # drops a cap, like QuadriFlow erasing a thin bone
        res = orig(ctx, mesh, target, sym)
        bm = bmesh.new(); bm.from_mesh(res)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().x > 0.7], context="FACES")
        bm.to_mesh(res); bm.free()
        return res
    topo._quadriflow = losing
    lost, note = topo.retopologize(bpy.context, tp, 0.5, False, 1e-4)
    check("retopo: surface QuadriFlow lost is kept from the original",
          "original face(s) kept" in note and max(v.co.x for v in lost.data.vertices) > 0.99, note)
    topo._quadriflow = orig
    new, note = topo.retopologize(bpy.context, tp, 0.5, False, 1e-4)
    check("retopo: healthy run keeps nothing extra", "collapsed" not in note and "original face" not in note, note)

    bav.unregister()
    say("DONE")
except Exception:
    say("EXCEPTION\n" + traceback.format_exc())
