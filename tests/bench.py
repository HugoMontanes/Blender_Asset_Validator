# Times every check on UV spheres of ~16k, 260k and 1M triangles (smooth, with UVs).
# Not run by run.ps1: Start-Process <blender> -ArgumentList '-b','--factory-startup','--python','tests\bench.py' -Wait
# Results in tests/_out/bench.txt; compare with the baseline in docs/ROADMAP.md.
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "_out")
os.makedirs(OUT_DIR, exist_ok=True)
sys.path.insert(0, os.path.dirname(HERE))
log = open(os.path.join(OUT_DIR, "bench.txt"), "w", encoding="utf-8")


def say(msg):
    log.write(msg + "\n"); log.flush()


import bpy, bmesh

bpy.ops.wm.read_factory_settings(use_empty=True)
import blender_asset_validator as bav
from blender_asset_validator.core import engine
from blender_asset_validator.core.registry import get_checks

bav.register()
config = engine.load_config()
say(f"Blender {bpy.app.version_string}")
for segments in (64, 256, 512):
    bm = bmesh.new()
    bm.loops.layers.uv.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments * 2, v_segments=segments, radius=1.0, calc_uvs=True)
    mesh = bpy.data.meshes.new(f"Sphere{segments}")
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(f"Sphere{segments}", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(bpy.data.materials.new("M"))
    say(f"== {sum(len(p.vertices) - 2 for p in mesh.polygons):,} tris")
    total = 0.0
    for check in get_checks():
        start = time.perf_counter()
        check([obj], config)
        elapsed = time.perf_counter() - start
        total += elapsed
        say(f"   {check.__name__}: {elapsed:.2f}s")
    say(f"   TOTAL {total:.2f}s")
bav.unregister()
say("DONE")
