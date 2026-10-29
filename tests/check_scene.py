# The user's own scene (Addon_Test.blend at the repo root, not committed): opened, never saved.
# Synthetic meshes miss what real assets do (palette UVs, UVs hundreds of tiles wide, islands
# Minimum Stretch collapses); this runs the checks and the UV tools on it with time limits.
import sys, os, traceback, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT_DIR = os.path.join(HERE, "_out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(__file__))[0] + ".txt")
SCENE = os.path.join(REPO, "Addon_Test.blend")
sys.path.insert(0, REPO)
log = open(OUT, "w", encoding="utf-8")


def say(msg):
    log.write(msg + "\n"); log.flush()


def check(name, cond, extra=""):
    say(f"{'PASS' if cond else 'FAIL'}  {name}  {extra}")


import bpy
import numpy as np

if not os.path.exists(SCENE):
    say(f"SKIP  {SCENE} not found")
    say("DONE"); raise SystemExit

try:
    bpy.ops.wm.open_mainfile(filepath=SCENE)
    import blender_asset_validator as bav
    from blender_asset_validator.core import engine
    from blender_asset_validator.checks import uvs as uv_checks
    from blender_asset_validator.core.mesh_utils import read_array
    from blender_asset_validator.operations import uvs, heatmap
    bav.register()
    say("register OK, Blender " + bpy.app.version_string)
except Exception:
    say("IMPORT/REGISTER FAILED\n" + traceback.format_exc()); raise SystemExit

cfg = engine.load_config()
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.data.polygons]
say(f"   {len(meshes)} meshes, {sum(len(o.data.polygons) for o in meshes):,} faces")
check("the scene has meshes", bool(meshes))

t = time.perf_counter(); results = engine.run_validation(cfg, meshes); elapsed = time.perf_counter() - t
crashed = [r.message for r in results if "raised an exception" in r.message]
check("every check runs on the scene", not crashed, str(crashed))
check("full validation under 30 s", elapsed < 30, f"{elapsed:.1f}s")
for r in results:
    if r.check_name in ("uvs", "uv_layout", "lightmap_uv"):
        say(f"   {r.severity.value}: {r.message}")

big = max(meshes, key=lambda o: len(o.data.polygons))
for metric in heatmap.METRICS:
    t = time.perf_counter()
    try:
        heatmap.show_heatmap(big, metric, cfg); crashed = ""
    except Exception as e:
        crashed = repr(e)
    check(f"heatmap {metric} runs", not crashed and time.perf_counter() - t < 10, f"{time.perf_counter() - t:.2f}s {crashed}")
heatmap.clear_heatmap(big)


def copy_of(obj):
    dup = obj.copy(); dup.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(dup)
    bpy.ops.object.select_all(action="DESELECT"); dup.select_set(True); bpy.context.view_layer.objects.active = dup
    return dup


def collapsed_share(obj):
    """Fraction of the 3D area whose UVs have no area: what an unwrap that failed leaves."""
    stats = uvs.uv_stats(obj, obj.data.uv_layers[0])
    flat = (stats["face_uv_area"] < 1e-14) & (stats["face_area"] > 0)
    return stats["face_area"][flat].sum() / stats["face_area"].sum()


dup = copy_of(big)
t = time.perf_counter(); msg = uvs.auto_unwrap(dup, cfg); elapsed = time.perf_counter() - t
share = collapsed_share(dup)
check("Auto Unwrap on the scene's biggest mesh: under 60 s", elapsed < 60, f"{elapsed:.1f}s {msg}")
check("Auto Unwrap leaves no collapsed islands (under 1% of the area)", share < 0.01, f"{share:.1%}")
after = [r.message for r in uv_checks.check_uv_layout([dup], cfg) + uv_checks.check_uvs([dup], cfg) if r.severity.value != "INFO"]
for m in after:
    say(f"   after Auto Unwrap: {m}")

dup = copy_of(big)
t = time.perf_counter(); msg = uvs.set_texel_density(dup, 64, cfg); elapsed = time.perf_counter() - t
stats = uvs.uv_stats(dup, dup.data.uv_layers[0])
density = uvs.texel_density(stats, cfg["uv"]["texture_size"])
textured = np.isfinite(density) & (stats["island_uv_area"] * cfg["uv"]["texture_size"] ** 2 >= 16)  # slivers under 4x4 px: float32 UVs blur their area by a few %
off = density[textured][~np.isclose(density[textured], 64, rtol=0.02)]
check("Set Texel Density on the scene's biggest mesh: under 30 s, every textured island at the density",
      elapsed < 30 and textured.any() and not len(off), f"{elapsed:.1f}s {msg}; {textured.sum()} textured, off: {np.round(off[:10], 1)}")

say("DONE")
