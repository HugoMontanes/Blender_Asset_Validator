import sys, os, traceback, json, math, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT_DIR = os.path.join(HERE, "_out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(__file__))[0] + ".txt")
sys.path.insert(0, REPO)

WORK = os.path.join(OUT_DIR, "work")
os.makedirs(WORK, exist_ok=True)

log = open(OUT, "w", encoding="utf-8")


def say(msg):
    log.write(msg + "\n"); log.flush()


def check(name, cond, extra=""):
    say(f"{'PASS' if cond else 'FAIL'}  {name}  {extra}")


import bpy, bmesh

try:
    import blender_asset_validator as bav
    from blender_asset_validator.core import engine, state
    from blender_asset_validator.operators import export as export_mod, lod as lod_mod
    from blender_asset_validator.operations import decimate, lod as lod_ops
    from blender_asset_validator.checks import geometry
    bav.register()
    say("register OK, Blender " + bpy.app.version_string)
except Exception:
    say("IMPORT/REGISTER FAILED\n" + traceback.format_exc()); raise SystemExit

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.app.handlers.load_post.clear() if False else None
bav.unregister(); bav.register()  # re-register after factory reset


class _Safe:
    def __init__(self, op): self.op = op
    def __call__(self, *a, **k):
        try: return self.op(*a, **k)
        except RuntimeError as e:
            say("   (op error: %s)" % str(e).strip().splitlines()[-1][:160]); return {"CANCELLED"}
    def poll(self, *a): return self.op.poll(*a)
class _AV:
    def __getattr__(self, n): return _Safe(getattr(bpy.ops.asset_validator, n))
AV = _AV()

def results():
    return state.get_results()


def msgs(check_name=None):
    return [(r.check_name, r.severity.value, r.message) for r in (results() or []) if check_name in (None, r.check_name)]


def make_mesh(name, bm_fill, mat=True, uv=True, apply_scale=True):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new(); bm_fill(bm)
    if uv:
        bm.loops.layers.uv.new("UVMap")
    bm.to_mesh(mesh); bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if mat:
        m = bpy.data.materials.new(name + "Mat"); m.use_nodes = True
        obj.data.materials.append(m)
    return obj


def cube(bm): bmesh.ops.create_cube(bm, size=1.0)


def unwrap_cube_uv(obj):
    bm = bmesh.new(); bm.from_mesh(obj.data)
    uvl = bm.loops.layers.uv.active
    # give every face its own non-overlapping cell; 0.22 of 2048 px on a 1 m face is 450 px/m, inside the 512 ±20% default
    for i, f in enumerate(bm.faces):
        ox, oy = (i % 4) * 0.25, (i // 4) * 0.25
        for j, l in enumerate(f.loops):
            l[uvl].uv = (ox + [0, .22, .22, 0][j % 4], oy + [0, 0, .22, .22][j % 4])
    bm.to_mesh(obj.data); bm.free()


def select(*objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


# ---------- 1. clean asset passes ----------
good = make_mesh("GoodCube", cube); unwrap_cube_uv(good)
select(good)
r = AV.validate()
check("validate operator runs", r == {"FINISHED"}, str(r))
errs = [m for m in msgs() if m[1] == "ERROR"]
check("clean cube has no errors", not errs, str(msgs()))

# ---------- 2. bad assets ----------
bad_name = make_mesh("bad_name", cube); unwrap_cube_uv(bad_name)
no_uv = make_mesh("NoUv", cube, uv=False)
no_mat = make_mesh("NoMat", cube, mat=False); unwrap_cube_uv(no_mat)
scaled = make_mesh("Scaled", cube); unwrap_cube_uv(scaled); scaled.scale = (2, 2, 2); scaled.location = (3, 0, 0)

def ngon(bm):
    vs = [bm.verts.new((math.cos(a * 2 * math.pi / 6), math.sin(a * 2 * math.pi / 6), 0)) for a in range(6)]
    bm.faces.new(vs)
ng = make_mesh("Ngon", ngon)

def overlap_uv_fill(bm):
    bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=1)
overlap = make_mesh("Overlap", overlap_uv_fill)
bm = bmesh.new(); bm.from_mesh(overlap.data); uvl = bm.loops.layers.uv.active
for f in bm.faces:
    for l in f.loops: l[uvl].uv = (0.0 + 0.01 * (l.vert.co.x > 0), 0.0 + 0.01 * (l.vert.co.y > 0))  # all faces stacked
bm.to_mesh(overlap.data); bm.free()

# adjacent-quads grid with a proper layout: must NOT flag overlap
adj = make_mesh("Adjacent", overlap_uv_fill)
bm = bmesh.new(); bm.from_mesh(adj.data); uvl = bm.loops.layers.uv.active
for f in bm.faces:
    for l in f.loops: l[uvl].uv = ((l.vert.co.x + 1) / 2, (l.vert.co.y + 1) / 2)
bm.to_mesh(adj.data); bm.free()

def degen(bm):
    bmesh.ops.create_cube(bm, size=1.0)
    v = [bm.verts.new((5, 0, 0)), bm.verts.new((6, 0, 0)), bm.verts.new((7, 0, 0))]
    bm.faces.new(v)  # collinear => zero area
degen_obj = make_mesh("Degen", degen); unwrap_cube_uv(degen_obj)

def ico(bm): bmesh.ops.create_icosphere(bm, subdivisions=7, radius=1.0)  # ~164k tris
heavy = make_mesh("Heavy", ico)
bm = bmesh.new(); bm.from_mesh(heavy.data)
# trivial per-face unique UV to avoid UV noise; skip, just copy UV from planar projection
uvl = bm.loops.layers.uv.active
for f in bm.faces:
    for l in f.loops: l[uvl].uv = ((l.vert.co.x + 1) / 2, (l.vert.co.y + 1) / 2)
bm.to_mesh(heavy.data); bm.free()

# textures
img_missing = bpy.data.images.new("tmp", 4, 4); img_missing.source = "FILE"; img_missing.filepath = os.path.join(WORK, "does_not_exist.png")
tex_obj = make_mesh("TexMissing", cube); unwrap_cube_uv(tex_obj)
mt = tex_obj.data.materials[0]; n = mt.node_tree.nodes.new("ShaderNodeTexImage"); n.image = img_missing
_t = bpy.data.images.new("t1001", 4, 4); _t.filepath_raw = os.path.join(WORK, "tex.1001.png"); _t.file_format = "PNG"; _t.save()
udim = bpy.data.images.load(os.path.join(WORK, "tex.1001.png")); udim.name = "udim"; udim.source = "TILED"; udim.filepath = os.path.join(WORK, "tex.<UDIM>.png")
udim_obj = make_mesh("TexUdim", cube); unwrap_cube_uv(udim_obj)
n2 = udim_obj.data.materials[0].node_tree.nodes.new("ShaderNodeTexImage"); n2.image = udim
generated = bpy.data.images.new("gen", 4, 4)  # source GENERATED, no file
gen_obj = make_mesh("TexGen", cube); unwrap_cube_uv(gen_obj)
n3 = gen_obj.data.materials[0].node_tree.nodes.new("ShaderNodeTexImage"); n3.image = generated

all_objs = [good, bad_name, no_uv, no_mat, scaled, ng, overlap, adj, degen_obj, heavy, tex_obj, udim_obj, gen_obj]
select(*all_objs)
AV.validate()
M = msgs()
for m in M: say("   " + " | ".join(m))

def has(check_name, obj, sev=None):
    return any(c == check_name and f"'{obj}'" in t and (sev is None or s == sev) for c, s, t in M)

check("naming flags bad_name", has("naming", "bad_name", "ERROR"))
check("no UV flagged", has("uvs", "NoUv", "ERROR"))
check("no material flagged", has("materials", "NoMat", "ERROR"))
check("ngon flagged", has("ngons", "Ngon"))
check("UV overlap flagged on stacked UVs", has("uvs", "Overlap", "WARNING"))
check("UV overlap NOT flagged on adjacent quads", not has("uvs", "Adjacent"))
check("degenerate face flagged", has("geometry_cleanup", "Degen", "ERROR"))
check("polycount flagged on heavy", has("polycount", "Heavy", "ERROR"))
check("missing texture file flagged", any("does_not_exist" in t for _, _, t in M))
check("UDIM image not reported missing", not any("udim" in t.lower() and "missing" in t for _, _, t in M))
check("generated image reported as no file on disk (expected)", any("gen" in t and "no file on disk" in t for _, _, t in M))
check("good cube still clean in mixed run", not any("'GoodCube'" in t for _, s, t in M if s != "INFO"))

# ---------- 3. Fix All ----------
AV.validate()
r = AV.fix_all()
check("fix_all runs", r == {"FINISHED"}, str(r))
M = msgs()
check("degenerate fixed after Fix All", not has("geometry_cleanup", "Degen"))
mod = heavy.modifiers.get("AssetValidator_Decimate")
check("heavy got decimate modifier", mod is not None, f"ratio={mod.ratio if mod else None}")
check("heavy polycount cleared after Fix All (single pass)", not has("polycount", "Heavy"),
      f"tris={geometry.evaluated_triangle_count(heavy)}")
# second Fix must not reset ratio upward
ratio_before = mod.ratio
AV.validate(); AV.fix_all()
check("decimate ratio never increases on repeated Fix", heavy.modifiers["AssetValidator_Decimate"].ratio <= ratio_before + 1e-9)

# ---------- 4. fix_result with bad index / stale ----------
r = AV.fix_result(result_index=9999)
check("fix_result out-of-range cancelled", r == {"CANCELLED"}, str(r))

# ---------- 5. presets ----------
bpy.context.scene.asset_validator_preset = "mobile"
check("changing preset clears results", results() is None)
select(good); AV.validate()
bpy.context.scene.asset_validator_preset = "cinematic"
check("preset cleared again", results() is None)
bpy.context.scene.asset_validator_preset = "NONE"

# ---------- 6. LODs ----------
select(good, bad_name)
r = AV.generate_lods()
check("generate_lods runs", r == {"FINISHED"}, str(r))
lods = [o for o in bpy.data.objects if o.get("asset_validator_lod")]
check("6 LOD objects (2 src x 3)", len(lods) == 6, str([o.name for o in lods]))
check("LOD names exact", {"GoodCube_LOD1", "GoodCube_LOD2", "GoodCube_LOD3"} <= {o.name for o in lods})
select(good, bad_name)
AV.generate_lods()
lods = [o for o in bpy.data.objects if o.get("asset_validator_lod")]
check("regenerating LODs does not duplicate", len(lods) == 6, str(sorted(o.name for o in lods)))
select(good)
check("unselected LODs not in validation set", all(o not in engine.get_validation_objects(engine.load_config()) for o in lods))
select(*[o for o in lods if o.name.startswith("GoodCube")])
check("selected LODs validate on their own", AV.validate() == {"FINISHED"} and len(engine.get_validation_objects(engine.load_config())) == 3)

# ---------- 7. Export ----------
select(good)
r = AV.export()
check("export blocked for unsaved blend w/ relative path", r == {"CANCELLED"}, str(r))

blend = os.path.join(WORK, "t.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend)
check("save_as_mainfile works", os.path.exists(blend))
exports = os.path.join(WORK, "exports")

def run_export(target, individual=True, objs=None):
    import shutil; shutil.rmtree(exports, ignore_errors=True)
    orig = engine.load_config
    def patched():
        c = orig(); c["lod"]["export_target"] = target; c["export"]["individual_files"] = individual; return c
    export_mod.load_config = patched
    try:
        select(*(objs or [good]))
        r = AV.export()
    finally:
        export_mod.load_config = orig
    files = sorted(os.listdir(exports)) if os.path.isdir(exports) else []
    return r, files

select(good); AV.generate_lods()
r, files = run_export("none")
check("export none -> 1 fbx", r == {"FINISHED"} and files == ["GoodCube.fbx"], f"{r} {files}")
r, files = run_export("unreal")
check("export unreal -> 1 fbx per asset", r == {"FINISHED"} and files == ["GoodCube.fbx"], f"{r} {files}")
sz_none = os.path.getsize(os.path.join(exports, "GoodCube.fbx"))
r, files = run_export("unity")
check("export unity -> 1 fbx per asset, LODs inside", r == {"FINISHED"} and files == ["GoodCube.fbx"], f"{r} {files}")
check("export unity: names restored", good.name == "GoodCube" and lod_ops.lods_of(good)[0].name == "GoodCube_LOD1")
r, files = run_export("unreal", objs=[good, *lod_ops.lods_of(good)])
check("selected LODs not exported twice", r == {"FINISHED"} and files == ["GoodCube.fbx"], f"{r} {files}")
lod1 = lod_ops.lods_of(good)[0]; lod1.name = "bad lod"
r, files = run_export("unreal")
check("export gate validates the LODs it writes", r == {"CANCELLED"} and not files, f"{r} {files}")
lod1.name = "GoodCube_LOD1"
r, files = run_export("unreal", individual=False)
check("export combined unreal -> 1 fbx", r == {"FINISHED"} and len(files) == 1, f"{r} {files}")

# export gate uses validated objects, not live selection: select only a bad object -> blocked
r, files = run_export("none", objs=[bad_name])
check("export blocked when validation errors exist", r == {"CANCELLED"} and not files, f"{r} {files}")

# selection restored after export
select(good)
run_export("none")
check("selection restored after export", bpy.context.view_layer.objects.active == good and good.select_get())

# ---------- 8. Edit mode gating ----------
select(good)
bpy.ops.object.mode_set(mode="EDIT")
check("validate polls False in Edit Mode", not AV.validate.poll())
check("export polls False in Edit Mode", not AV.export.poll())
bpy.ops.object.mode_set(mode="OBJECT")
check("validate polls True in Object Mode", AV.validate.poll())

# ---------- 9. file load clears results ----------
select(good); AV.validate()
check("results exist before load", results() is not None)
bpy.ops.wm.open_mainfile(filepath=blend)
check("load_post handler clears results", results() is None)

# ---------- 10. no objects ----------
for o in list(bpy.context.scene.objects): o.select_set(False)
r = AV.validate()
check("validate with nothing selected cancelled", r == {"CANCELLED"}, str(r))

# A real asset's stale edit-mode selection made bmesh.from_mesh crash Blender (ROADMAP); the API can't
# write one, so duplicate faces, which Blender's validate repairs too, stand in for it here
dup_mesh = bpy.data.meshes.new("DupFaces")
dup_mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3), (3, 2, 1, 0)])
dup = bpy.data.objects.new("DupFaces", dup_mesh); bpy.context.scene.collection.objects.link(dup)
dup_mesh.materials.append(bpy.data.materials.new("DupMat"))
plain = make_mesh("PlainNeighbour", cube)
found = engine.run_validation(engine.load_config(), [dup, plain])
mine = [r for r in found if r.object_name == "DupFaces"]
check("invalid mesh data: one error with a Fix, none of the other checks read it",
      len(mine) == 1 and mine[0].check_name == "mesh_data" and mine[0].severity.value == "ERROR" and mine[0].fix is not None,
      str([(r.check_name, r.message[:60]) for r in mine]))
check("invalid mesh data: the other objects are still checked", any(r.object_name == "PlainNeighbour" for r in found))
check("invalid mesh data: the check doesn't change the mesh", len(dup_mesh.polygons) == 2)
mine[0].fix()
check("invalid mesh data: Fix repairs it and its checks run again",
      not any(r.check_name == "mesh_data" for r in engine.run_validation(engine.load_config(), [dup])) and len(dup_mesh.polygons) == 1)
# Fix All: the repaired mesh's own checks (a face flipped inward here) only run after the repair
bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
verts, faces = [v.co[:] for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces]; bm.free()
broken_mesh = bpy.data.meshes.new("DupFlipped")
broken_mesh.from_pydata(verts, [], [faces[0][::-1]] + faces[1:] + [faces[2][::-1]])
broken_mesh.materials.append(bpy.data.materials.new("DupFlippedMat"))
broken = bpy.data.objects.new("DupFlipped", broken_mesh); bpy.context.scene.collection.objects.link(broken)
select(broken); AV.validate(); AV.fix_all()
left = [(r.check_name, r.message[:50]) for r in results() if r.object_name == "DupFlipped" and r.fix is not None]
check("Fix All also applies the fixes a mesh_data repair uncovers", not left, str(left))
# Every tool repairs first: bmesh drops duplicate faces on its own, so a spy, not the mesh, tells here
from blender_asset_validator.core import mesh_utils
from blender_asset_validator.operators import uvs as op_uvs, topology as op_topo, lod as op_lod, hard_surface as op_hs
real_repair, repaired_by = mesh_utils.repair_invalid, set()
spied = (op_uvs, op_topo, op_lod, op_hs, mesh_utils)
for module in spied:
    module.repair_invalid = lambda objects, operator=None: (
        repaired_by.add(type(operator).bl_idname if operator else "select") if dup in objects else None,
        real_repair(objects, operator))[1]
select(plain)
mesh_utils.select_in_edit_mode(dup, "FACE", [0])  # Show on a result whose object isn't selected
bpy.ops.object.mode_set(mode="OBJECT")
check("Show repairs invalid mesh data first, even on an object that isn't selected", "select" in repaired_by)
repaired_by.clear()
select(dup)
tools = (("auto_unwrap", {}), ("set_texel_density", {"density": 512}), ("hard_surface_prep", {}),
         ("clean_topology", {}), ("generate_lods", {}), ("retopologize", {}))  # last: it hides the original
for name, kwargs in tools:
    getattr(AV, name)(**kwargs)
check("every mesh tool repairs invalid mesh data before reading the selection",
      repaired_by == {f"asset_validator.{name}" for name, _ in tools}, str(sorted(repaired_by)))
for module in spied:
    module.repair_invalid = real_repair

# ---------- 10b. Validate in steps (modal: status bar, Esc) ----------
# The whole stress scene sat 25 min in Validate with no sign of life and no way out
saved, engine._STATUS_EVERY = engine._STATUS_EVERY, 0.0  # a status line between every two objects
objs = [make_mesh(f"Stepped{i}", fill) for i, fill in enumerate((cube, ngon, overlap_uv_fill, cube))]
steps = engine.validation_steps(engine.load_config(), objs)
lines = []
try:
    while True:
        lines.append(next(steps))
except StopIteration as end:
    stepped = end.value
engine._STATUS_EVERY = saved
plain = engine.run_validation(engine.load_config(), objs)
check("validation in steps: a status line between objects, the same results as in one go",
      len(lines) > len(objs) and [r.message for r in stepped] == [r.message for r in plain], f"{len(lines)} lines: {lines[:2]}")
parent, child = make_mesh("LinkParent", cube), make_mesh("LinkChild", cube)
child.parent = parent
cfg = engine.load_config(); cfg["export"]["individual_files"] = False
drops = lambda objs: [r.object_name for r in engine.run_validation(cfg, objs) if "drops that link" in r.message]
check("checks that compare objects still see the whole set: a child exported with its parent keeps the link",
      drops([child]) == ["LinkChild"] and drops([parent, child]) == [], f"{drops([child])} {drops([parent, child])}")

# ---------- 11. unregister clean ----------
try:
    bav.unregister(); say("PASS  unregister clean")
except Exception:
    say("FAIL  unregister\n" + traceback.format_exc())

# decimate self-check
decimate_ok = True
say("DONE")
