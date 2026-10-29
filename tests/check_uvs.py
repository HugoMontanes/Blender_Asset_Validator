import sys, os, traceback, math, time, random
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
from bpy_extras import mesh_utils

try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import blender_asset_validator as bav
    from blender_asset_validator.core import engine, state
    from blender_asset_validator.checks import uvs as uv_checks
    from blender_asset_validator.operations import uvs, heatmap
    from blender_asset_validator.core.mesh_utils import read_array
    bav.register()
    say("register OK, Blender " + bpy.app.version_string)
except Exception:
    say("IMPORT/REGISTER FAILED\n" + traceback.format_exc()); raise SystemExit


def config(**uv):
    cfg = engine.load_config()
    cfg["uv"].update(uv)
    return cfg


def link(name, mesh, material=None):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    return obj


def quads(name, faces_uv, material=None):
    """One unit quad per entry, side by side in 3D (x = 2i), with the given UV corners."""
    bm = bmesh.new(); uvl = bm.loops.layers.uv.new("UVMap")
    for i, corners in enumerate(faces_uv):
        vs = [bm.verts.new((2 * i + x, y, 0)) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
        face = bm.faces.new(vs)
        for loop, uv in zip(face.loops, corners):
            loop[uvl].uv = uv
    mesh = bpy.data.meshes.new(name); bm.to_mesh(mesh); bm.free()
    return link(name, mesh, material)


def square(x, y, side):
    return [(x, y), (x + side, y), (x + side, y + side), (x, y + side)]


def from_bm(name, fill, uv=True):
    bm = bmesh.new()
    if uv:
        bm.loops.layers.uv.new("UVMap")
    fill(bm)
    mesh = bpy.data.meshes.new(name); bm.to_mesh(mesh); bm.free()
    return link(name, mesh, bpy.data.materials.new(name + "Mat"))


def select(*objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def smart_project(obj, margin=0.02):
    select(obj)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")


def uv_of(obj, layer=0):
    return read_array(obj.data.uv_layers[layer].data, "uv", 2, np.float64)


def op(operator, **props):
    """bpy.ops raises when an operator reports an ERROR: that is a CANCELLED here."""
    try:
        return operator(**props)
    except RuntimeError as e:
        say("   (op error: %s)" % str(e).strip().splitlines()[-1][:160]); return {"CANCELLED"}


def messages(results, check_name):
    return [(r.severity.value, r.message) for r in results if r.check_name == check_name]


CFG = config()

# ---------- islands ----------
def partition(labels):
    groups = {}
    for face, label in enumerate(labels):
        groups.setdefault(label, set()).add(face)
    return sorted(sorted(g) for g in groups.values())

per_face = quads("PerFace", [square(0.3 * i, 0, 0.25) for i in range(3)])
check("islands: separate quads are separate islands", uvs.face_islands(per_face.data, per_face.data.uv_layers[0]).tolist() == [0, 1, 2])
grid = from_bm("Grid", lambda bm: bmesh.ops.create_grid(bm, x_segments=10, y_segments=10, size=1.0, calc_uvs=True))
check("islands: a grid with continuous UVs is one island", set(uvs.face_islands(grid.data, grid.data.uv_layers[0]).tolist()) == {0})
ok = True
for name, fill in (("IcoSP", lambda bm: bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)),
                   ("ConeSP", lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=1.0, radius2=0.3, depth=2.0)),
                   ("SphereUV", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0, calc_uvs=True))):
    obj = from_bm(name, fill)
    if not name.endswith("UV"):
        smart_project(obj)
    mine = partition(uvs.face_islands(obj.data, obj.data.uv_layers[0]))
    theirs = sorted(sorted(island) for island in mesh_utils.mesh_linked_uv_islands(obj.data))
    ok &= mine == theirs
    say(f"   {name}: {len(mine)} islands, bpy_extras {len(theirs)}")
check("islands: same partition as bpy_extras.mesh_linked_uv_islands", ok)

rng = random.Random(4)
ok = True
for _ in range(30):
    n = rng.randint(1, 60)
    edges = [(rng.randrange(n), rng.randrange(n)) for _ in range(rng.randint(0, 2 * n))]
    a = np.array([e[0] for e in edges], np.int64); b = np.array([e[1] for e in edges], np.int64)
    label = uvs._components(n, a, b)
    reach = list(range(n))  # reference: naive relabel to a fixed point
    changed = True
    while changed:
        changed = False
        for x, y in edges:
            m = min(reach[x], reach[y])
            if reach[x] != m or reach[y] != m:
                reach[x] = reach[y] = m; changed = True
    ok &= label.tolist() == reach
check("union-find matches a naive relabel on 30 random graphs", ok)

# ---------- texel density ----------
td = quads("Td", [square(0.1, 0.1, 0.25)])  # 1 m quad on 0.25 of a 2048 texture
stats = uvs.uv_stats(td, td.data.uv_layers[0])
check("texel density: 1 m on a quarter of 2048 px is 512 px/m", abs(uvs.texel_density(stats, 2048)[0] - 512) < 1e-3,
      str(uvs.texel_density(stats, 2048)))
r = uv_checks.check_uv_layout([td], CFG)
check("texel density on target: no warning, INFO shows it", not [m for m in messages(r, "uv_layout") if m[0] == "WARNING"]
      and any("512 px/m" in m[1] for m in messages(r, "uv_layout")), str(messages(r, "uv_layout")))
td.scale = (2, 2, 2); bpy.context.view_layer.update()
stats = uvs.uv_stats(td, td.data.uv_layers[0])
check("texel density follows object scale (2x -> 256)", abs(uvs.texel_density(stats, 2048)[0] - 256) < 1e-3)
r = uv_checks.check_uv_layout([td], CFG)
check("texel density off target: warning with the range", any("off the 512 px/m" in m[1] and "256–256" in m[1] for m in messages(r, "uv_layout")),
      str(messages(r, "uv_layout")))
bpy.context.scene.unit_settings.scale_length = 0.5
check("texel density follows scene units", abs(uvs.texel_density(uvs.uv_stats(td, td.data.uv_layers[0]), 2048)[0] - 512) < 1e-3)
bpy.context.scene.unit_settings.scale_length = 1.0
td.scale = (1, 1, 1); bpy.context.view_layer.update()
r = uv_checks.check_uv_layout([td], config(texel_density=0))
check("texel density 0 = no target: no density warning", not any("texel density (" in m[1] for m in messages(r, "uv_layout")))
mixed = quads("Mixed", [square(0.0, 0.0, 0.25), square(0.5, 0.5, 0.5)])  # 512 and 1024 px/m
check("median density weighs by area (two 1 m² islands -> the lower middle)",
      abs(uvs.median_density(uvs.uv_stats(mixed, mixed.data.uv_layers[0]), 2048) - 512) < 1e-3)

palette = quads("Palette", [square(0.5, 0.5, 0.0001), square(0.5001, 0.5, 0.0001), square(0.1, 0.1, 0.25)])  # two islands in one texel
r = messages(uv_checks.check_uv_layout([palette], CFG), "uv_layout")
check("solid-colour islands (inside one texel): counted, left out of density, stretch and gaps",
      any("2 solid-colour" in m[1] and "density 512 px/m" in m[1] for m in r) and not [m for m in r if m[0] == "WARNING"], str(r))

# ---------- stretch ----------
squashed = quads("Squashed", [[(0, 0), (0.5, 0), (0.5, 0.1), (0, 0.1)]])
r = uv_checks.check_uv_layout([squashed], config(texel_density=0))
check("stretch: a squashed quad is flagged", any("stretch past" in m[1] for m in messages(r, "uv_layout")), str(messages(r, "uv_layout")))
check("stretch: a square quad is not", not any("stretch past" in m[1] for m in messages(uv_checks.check_uv_layout([td], CFG), "uv_layout")))

# ---------- gaps ----------
px = 1 / 2048
near = quads("Near", [square(0.1, 0.1, 0.2), square(0.3 + 4 * px, 0.1, 0.2)])
far = quads("Far", [square(0.1, 0.1, 0.2), square(0.3 + 16 * px, 0.1, 0.2)])
check("gaps: islands 4 px apart flagged", any("closer than 8 px" in m[1] for m in messages(uv_checks.check_uv_layout([near], config(texel_density=0)), "uv_layout")))
check("gaps: islands 16 px apart not flagged", not any("closer than" in m[1] for m in messages(uv_checks.check_uv_layout([far], config(texel_density=0)), "uv_layout")))
diagonal = quads("Diagonal", [square(0.1, 0.1, 0.2), square(0.3 + 3 * px, 0.3 + 3 * px, 0.2)])  # corners 4.2 px apart
check("gaps: corner to corner counts too", any("closer than 8 px" in m[1] for m in messages(uv_checks.check_uv_layout([diagonal], config(texel_density=0)), "uv_layout")))
# brute force on a real layout: each island's distance to its nearest other island, over every edge pair
ico = from_bm("IcoGaps", lambda bm: bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)); smart_project(ico, margin=0.004)
island = uvs.face_islands(ico.data, ico.data.uv_layers[0])
segs = []
for poly in ico.data.polygons:
    loops = list(poly.loop_indices)
    for i, l in enumerate(loops):
        segs.append((island[poly.index], ico.data.uv_layers[0].data[l].uv * 2048, ico.data.uv_layers[0].data[loops[(i + 1) % len(loops)]].uv * 2048))
def seg_dist(p, q, r, s):
    def d(x, a, b):
        ab = b - a; t = max(0.0, min(1.0, (x - a).dot(ab) / max(ab.dot(ab), 1e-30))); return (x - (a + t * ab)).length
    return min(d(p, r, s), d(q, r, s), d(r, p, q), d(s, p, q))
nearest = {}
for i in range(len(segs)):
    for j in range(i + 1, len(segs)):
        a, b = segs[i][0], segs[j][0]
        if a != b:
            dist = seg_dist(segs[i][1], segs[i][2], segs[j][1], segs[j][2])
            nearest[a] = min(nearest.get(a, math.inf), dist); nearest[b] = min(nearest.get(b, math.inf), dist)
for gap in (4, 12):  # smart project leaves ~8 px between islands: one gap under it, one over
    crowded = set(uvs.crowded_islands(ico.data, ico.data.uv_layers[0], island, 2048, gap).tolist())
    must = {i for i, dist in nearest.items() if dist < gap - 2}
    never = {i for i, dist in nearest.items() if dist > gap + 2}
    check(f"gaps: agrees with brute force within the pixel quantization ({gap} px)", must <= crowded and not crowded & never,
          f"{len(crowded)} crowded, {len(must)} must, {len(never)} never, {island.max() + 1} islands; nearest px {sorted(round(d, 1) for d in nearest.values())}")

tiling_near = quads("TilingNear", [square(0.1, 0.1, 0.2), square(0.3 + 4 * px, 0.1, 0.2)], bpy.data.materials.new("Floor_Tileable"))
check("gaps: islands of a tiling material are left out", not any("closer than" in m[1] for m in messages(uv_checks.check_uv_layout([tiling_near], config(texel_density=0)), "uv_layout")))
# UVs hundreds of tiles wide on a material the regex doesn't know (the Audi's carbon fibre): bounded time
huge = quads("HugeUV", [square(0.1 + 0.01 * i, 0.5, 0.005) for i in range(8)] + [square(0.1, 0.1, 0.2), square(0.3 + 4 * px, 0.1, 0.2)])
for poly in huge.data.polygons[:8]:  # 8 islands hundreds of tiles wide, still inside 0-1 so the gap check draws them
    for loop, uv in zip(poly.loop_indices, [(0.0, 0.5), (1.0, 0.5), (1.0, 0.5 + 0.002 * poly.index), (0.0, 0.5 + 0.002 * poly.index)]):
        huge.data.uv_layers[0].data[loop].uv = uv
t = time.perf_counter(); crowded = uvs.crowded_islands(huge.data, huge.data.uv_layers[0], uvs.face_islands(huge.data, huge.data.uv_layers[0]), 2048 * 300, 8); elapsed = time.perf_counter() - t
check("gaps: borders millions of pixels long stay fast (the budget caps only the long edges)", elapsed < 3.0, f"{elapsed:.2f}s, {len(crowded)} crowded")
off = quads("OffSquare", [square(40.0, 0.1, 0.2), square(40.2 + 4 * px, 0.1, 0.2)])
r = messages(uv_checks.check_uv_layout([off], config(texel_density=0)), "uv_layout")
check("gaps: islands off the 0-1 square get the 0-1 warning, not a gap one", any("outside" in m[1] for m in r) and not any("closer than" in m[1] for m in r), str(r))

# ---------- 0-1 bounds ----------
out = quads("Outside", [square(1.1, 0.1, 0.2)])
check("bounds: island past 1 flagged", any("outside 0–1" in m[1] for m in messages(uv_checks.check_uv_layout([out], config(texel_density=0)), "uv_layout")))
tiling = quads("TilingQuad", [square(1.1, 0.1, 0.2)], bpy.data.materials.new("Brick_Tiling"))
check("bounds: tiling material exempt", not any("outside" in m[1] for m in messages(uv_checks.check_uv_layout([tiling], config(texel_density=0)), "uv_layout")))
udim_mat = bpy.data.materials.new("Udim"); udim_mat.use_nodes = True
img = bpy.data.images.new("UdimImg", 4, 4, tiled=True); img.tiles.new(1002)
udim_mat.node_tree.nodes.new("ShaderNodeTexImage").image = img
in_tile = quads("InTile", [square(1.1, 0.1, 0.2)], udim_mat)
across = quads("Across", [square(0.9, 0.1, 0.2)], udim_mat)
check("bounds: UDIM island inside tile 1002 ok", not any("outside" in m[1] for m in messages(uv_checks.check_uv_layout([in_tile], config(texel_density=0)), "uv_layout")))
check("bounds: UDIM island across two tiles flagged", any("outside" in m[1] for m in messages(uv_checks.check_uv_layout([across], config(texel_density=0)), "uv_layout")))
check("bounds: an island touching 1.0 is inside", not any("outside" in m[1] for m in messages(uv_checks.check_uv_layout([quads("Edge", [square(0.8, 0.8, 0.2)])], config(texel_density=0)), "uv_layout")))

# ---------- Show selects the culprits ----------
both = quads("Both", [square(0.1, 0.1, 0.2), square(1.1, 0.1, 0.2)])
res = [x for x in uv_checks.check_uv_layout([both], config(texel_density=0)) if "outside" in x.message]
select(both); res[0].select()
bpy.ops.object.mode_set(mode="OBJECT")
picked = [p.index for p in both.data.polygons if p.select]
check("Show selects the faces of the flagged islands", picked == [1], str(picked))

# ---------- NaN UV stays fast ----------
nan_grid = from_bm("NanGrid", lambda bm: bmesh.ops.create_grid(bm, x_segments=150, y_segments=150, size=1.0, calc_uvs=True))
nan_grid.data.uv_layers[0].data[0].uv = (float("nan"), 0.0)
t = time.perf_counter()
try:
    uv_checks.check_uv_layout([nan_grid], CFG); crashed = ""
except Exception as e:
    crashed = repr(e)
check("layout check with a NaN UV: no crash, stays fast", not crashed and time.perf_counter() - t < 3.0, f"{time.perf_counter() - t:.2f}s {crashed}")

# ---------- lightmap ----------
def cube(bm): bmesh.ops.create_cube(bm, size=1.0)
lm = from_bm("Lm", cube); smart_project(lm)
uv0 = uv_of(lm).copy()
check("lightmap: missing UV1 ignored unless required", not uv_checks.check_lightmap_uv([lm], CFG))
r = uv_checks.check_lightmap_uv([lm], config(require_lightmap=True))
check("lightmap: missing UV1 is an error when required, with a fix", len(r) == 1 and r[0].severity.value == "ERROR" and r[0].fix is not None)
select(lm); msg = r[0].fix()
check("lightmap fix adds UV1 and the error goes", len(lm.data.uv_layers) == 2 and not uv_checks.check_lightmap_uv([lm], config(require_lightmap=True)), str(msg))
check("lightmap fix leaves UV0 and the active layer alone", np.allclose(uv_of(lm), uv0) and lm.data.uv_layers.active_index == 0)
for poly in lm.data.polygons:  # every face on the same square, out of 0-1
    for loop, uv in zip(poly.loop_indices, square(0.0, 1.5, 0.1)):
        lm.data.uv_layers[1].data[loop].uv = uv
r = uv_checks.check_lightmap_uv([lm], CFG)
check("lightmap: overlapping and outside UV1 flagged", len(r) == 1 and "overlapping" in r[0].message and "outside" in r[0].message, str([x.message for x in r]))
r[0].fix()
check("lightmap: fix clears it", not uv_checks.check_lightmap_uv([lm], CFG))

# ---------- heatmaps ----------
values = heatmap.METRICS["TEXEL_DENSITY"][2](td, CFG)
check("heatmap texel density: on target is 0", abs(values[0]) < 1e-6, str(values))
td.scale = (2, 2, 2); bpy.context.view_layer.update()
check("heatmap texel density: half the target is past mid-ramp", heatmap.METRICS["TEXEL_DENSITY"][2](td, CFG)[0] > 0.5)
td.scale = (1, 1, 1); bpy.context.view_layer.update()
check("heatmap stretch: square 0, squashed past mid-ramp",
      heatmap.METRICS["UV_STRETCH"][2](td, CFG)[0] < 1e-6 and heatmap.METRICS["UV_STRETCH"][2](squashed, CFG)[0] > 0.5)
no_uv = from_bm("NoUv", cube, uv=False)
check("heatmap texel density: palette UVs with no target are gray, not red",
      np.isnan(heatmap.METRICS["TEXEL_DENSITY"][2](quads("PaletteHeat", [square(0.5, 0.5, 0.0001)]), config(texel_density=0))).all())
check("heatmaps: no UVs is all gray", np.isnan(heatmap.METRICS["TEXEL_DENSITY"][2](no_uv, CFG)).all()
      and np.isnan(heatmap.METRICS["UV_STRETCH"][2](no_uv, CFG)).all())
select(squashed)
check("heatmap operator runs for the UV metrics", bpy.ops.asset_validator.show_heatmap(metric="UV_STRETCH") == {"FINISHED"}
      and squashed.data.color_attributes.get("AV_heat") is not None)

# ---------- Set Texel Density ----------
boxy = from_bm("Boxy", cube); smart_project(boxy)
msg = uvs.set_texel_density(boxy, 512, CFG)
density = uvs.texel_density(uvs.uv_stats(boxy, boxy.data.uv_layers[0]), 2048)
lo, hi = uvs.island_bounds(boxy.data, boxy.data.uv_layers[0], uvs.face_islands(boxy.data, boxy.data.uv_layers[0]))
check("set texel density: every island at 512 px/m", np.allclose(density, 512, rtol=0.01), str(density))
check("set texel density: packed inside 0-1 with the gap", (lo >= 0).all() and (hi <= 1).all()
      and not uv_checks.check_uv_layout([boxy], CFG)[1:], f"{msg}; {[x.message for x in uv_checks.check_uv_layout([boxy], CFG)]}")
msg = uvs.set_texel_density(boxy, 4096, CFG)
check("set texel density: says when it doesn't fit", "doesn't fit" in msg, msg)
far_uv = quads("FarUV", [square(500.0, 300.0, 40.0), square(-150.0, 0.5, 0.01), square(0.1, 0.1, 0.2)])  # junk / tiling coordinates
msg = uvs.set_texel_density(far_uv, 512, CFG)
density = uvs.texel_density(uvs.uv_stats(far_uv, far_uv.data.uv_layers[0]), 2048)
check("set texel density: islands far out of 0-1 come back exact and packed", np.allclose(density, 512, rtol=0.01) and "packed in 0–1" in msg,
      f"{msg} {density}")
copy_src = quads("CopySrc", [square(0.1, 0.1, 0.125)])  # 256 px/m
copy_dst = from_bm("CopyDst", cube); smart_project(copy_dst)
select(copy_dst, copy_src); bpy.context.view_layer.objects.active = copy_src
r = bpy.ops.asset_validator.set_texel_density(from_active=True)
density = uvs.texel_density(uvs.uv_stats(copy_dst, copy_dst.data.uv_layers[0]), 2048)
check("Copy from Active gives the others the active's density", r == {"FINISHED"} and np.allclose(density, 256, rtol=0.01), str(density))
check("Copy from Active leaves the active alone", np.allclose(uvs.texel_density(uvs.uv_stats(copy_src, copy_src.data.uv_layers[0]), 2048), 256))
bpy.ops.object.select_all(action="DESELECT")
check("Set Texel Density with nothing selected is cancelled", op(bpy.ops.asset_validator.set_texel_density) == {"CANCELLED"})

# ---------- Auto Unwrap ----------
def unwrap_report(obj, cfg=CFG):
    return [x.message for x in uv_checks.check_uv_layout([obj], cfg) + uv_checks.check_uvs([obj], cfg) if x.severity.value == "WARNING"]

box = from_bm("AutoBox", cube)
msg = uvs.auto_unwrap(box, CFG)
check("auto unwrap: a cube (no sharp marked) splits by angle into 6 islands, clean",
      msg.startswith("6 island") and not unwrap_report(box, config(texel_density=0)), f"{msg} {unwrap_report(box, config(texel_density=0))}")
cyl = from_bm("AutoCyl", lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=1.0, radius2=1.0, depth=2.0))
msg = uvs.auto_unwrap(cyl, CFG)
check("auto unwrap: a cylinder gets its tube cut open, clean", "cut" in msg and msg.startswith("3 island")
      and not unwrap_report(cyl, config(texel_density=0)), f"{msg} {unwrap_report(cyl, config(texel_density=0))}")
two = from_bm("AutoTwoMat", lambda bm: bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1.0))
two.data.materials.append(bpy.data.materials.new("Second"))
for p in two.data.polygons:
    p.material_index = int(p.center.x > 0)
check("auto unwrap: material borders become seams", uvs.auto_unwrap(two, CFG).startswith("2 island"))
sharp = from_bm("AutoSharp", lambda bm: bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1.0))
bm = bmesh.new(); bm.from_mesh(sharp.data)
for e in bm.edges:
    if all(abs(v.co.x) < 1e-6 for v in e.verts):
        e.smooth = False
bm.to_mesh(sharp.data); bm.free()
check("auto unwrap: marked sharp edges are the seams (a flat grid cut down the middle)", uvs.auto_unwrap(sharp, CFG).startswith("2 island"))
weighted = from_bm("AutoWeights", cube); weighted.vertex_groups.new(name="uv_importance").add(range(8), 1.0, "REPLACE")
try:
    msg = uvs.auto_unwrap(weighted, CFG); crashed = ""
except Exception as e:
    crashed = repr(e)
check("auto unwrap: with a uv_importance group", not crashed, crashed or msg)
straight = from_bm("AutoStraight", cube)
select(straight)
check("Auto Unwrap operator with Straighten runs and leaves 6 clean islands",
      bpy.ops.asset_validator.auto_unwrap(straighten=True) == {"FINISHED"} and not unwrap_report(straight, config(texel_density=0)),
      str(unwrap_report(straight, config(texel_density=0))))
check("auto unwrap restores Object Mode and the selection", bpy.context.mode == "OBJECT" and straight.select_get()
      and bpy.context.view_layer.objects.active == straight)

# ---------- guided step + full validation ----------
select(box)
check("validate runs the UV checks", bpy.ops.asset_validator.validate() == {"FINISHED"}
      and any(r.check_name == "uv_layout" for r in state.get_results()))

try:
    bav.unregister(); say("PASS  unregister clean")
except Exception:
    say("FAIL  unregister\n" + traceback.format_exc())
say("DONE")
