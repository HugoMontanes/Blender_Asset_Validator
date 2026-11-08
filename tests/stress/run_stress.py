"""Runs every case of StressTest.blend through the add-on the way an artist would: Validate, Export, Generate
LODs, Retopologize, Make SubD High + Bake, Clean Topology / Auto Unwrap / Prep (each on a copy), then Fix All
and Export again. One Blender per case, so a crash or a hang is a finding, not the end of the run.
    python tests/stress/run_stress.py [--jobs 3] [--timeout 1500] [case ...]
Writes tests/stress/_out/results/<case>.json (after every step, so a killed run keeps what it did),
_out/logs/<case>.log, _out/work/<case>.blend (the case after its tools: open it to look) and _out/summary.json."""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "_out")
BLEND = os.path.join(HERE, "StressTest.blend")
MANIFEST = os.path.join(HERE, "StressTest_manifest.json")
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
SCENE_CASE = "__whole_scene__"


# ------------------------------------------------------------------------------------------ orchestrator

def orchestrate(argv):
    from concurrent.futures import ThreadPoolExecutor
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 3
    timeout = int(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 1500
    wanted = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--jobs", "--timeout"))]
    with open(MANIFEST, encoding="utf-8") as f:
        cases = json.load(f)
    names = [c["name"] for c in cases] + [SCENE_CASE]
    names = [n for n in names if not wanted or n in wanted]
    weight = {c["name"]: c.get("tris", 0) for c in cases}
    names.sort(key=lambda n: -weight.get(n, 10 ** 9 if n == SCENE_CASE else 0))  # heaviest first: they set the wall time
    for d in ("results", "logs", "work"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)

    def run(name):
        safe = _safe(name)
        log = os.path.join(OUT, "logs", safe + ".log")
        t = time.perf_counter()
        with open(log, "w", encoding="utf-8", errors="replace") as out:
            try:
                code = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "--python", __file__, "--", "case", name],
                                      stdout=out, stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        seconds = time.perf_counter() - t
        result_path = os.path.join(OUT, "results", safe + ".json")
        result = json.load(open(result_path, encoding="utf-8")) if os.path.exists(result_path) else {"case": name, "steps": []}
        result["process"] = {"exit": code, "seconds": round(seconds, 1)}
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, ensure_ascii=False)
        print(f"{name:32s} exit={code!s:8s} {seconds:7.1f}s  {verdict(result)}", flush=True)
        return result

    t0 = time.perf_counter()
    with ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(run, names))
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"seconds": round(time.perf_counter() - t0), "results": results}, f, indent=1, ensure_ascii=False)
    print(f"done in {time.perf_counter() - t0:.0f}s -> {os.path.join(OUT, 'summary.json')}")


def verdict(result):
    v = next((s for s in result.get("steps", []) if s["step"] == "validate"), None)
    if v is None or "expectation" not in v:
        return "no validation"
    e = v["expectation"]
    bad = [f"missed {e['missed']}" if e["missed"] else "", f"false+ {e['false_positive']}" if e["false_positive"] else ""]
    crashed = [s["step"] for s in result["steps"] if not s.get("ok", True)]
    return " ".join(b for b in bad if b) + (f" FAILED {crashed}" if crashed else "") or "as expected"


def _safe(name):
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:80]


# ------------------------------------------------------------------------------------------ inside Blender

def in_blender(name):
    import contextlib
    import faulthandler
    import io
    import traceback
    # A hang shows up in the log as the stack it's stuck in (STRESS_DUMP seconds apart, default 300)
    faulthandler.dump_traceback_later(int(os.environ.get("STRESS_DUMP", 300)), repeat=True)

    import bpy
    sys.path.insert(0, REPO)
    import blender_asset_validator as bav
    from blender_asset_validator.core import engine
    from blender_asset_validator.core.registry import get_checks
    from blender_asset_validator.core.roles import role

    with open(MANIFEST, encoding="utf-8") as f:
        cases = {c["name"]: c for c in json.load(f)}
    if name == SCENE_CASE:
        case = {"name": name, "intent": "Select everything and Validate once, like an artist checking a whole scene",
                "objects": sorted({o for c in cases.values() for o in c["objects"]}), "select": None,
                "expect": [], "forbid": [], "artist_ok": [], "gap": "", "tools": ["validate"]}
    else:
        case = cases[name]
    safe = _safe(name)
    work = os.path.join(OUT, "work", safe)
    os.makedirs(work, exist_ok=True)
    result = {"case": name, "intent": case["intent"], "steps": []}
    result_path = os.path.join(OUT, "results", safe + ".json")

    def flush():
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, ensure_ascii=False, default=str)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    bav.register()
    with open(os.path.join(work, engine.PROJECT_CONFIG), "w", encoding="utf-8") as f:
        json.dump({"transforms": {"check_location": False}, "export": {"path": "//exports/"}, "bake": {"path": "//bakes/"}}, f)
    t = time.perf_counter()
    with bpy.data.libraries.load(BLEND, link=False) as (src, dst):
        dst.objects = [n for n in case["objects"] if n in src.objects]
    scene = bpy.context.scene
    for obj in dst.objects:
        if obj is not None:
            scene.collection.objects.link(obj)
    scene.asset_validator_engine = "unreal"
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, safe + ".blend"))
    result["load_seconds"] = round(time.perf_counter() - t, 2)
    config = engine.load_config()

    def objs(names):
        return [bpy.data.objects[n] for n in names if n in bpy.data.objects]

    selected = objs(case["select"]) if case["select"] else [o for o in scene.objects if o.type == "MESH"]
    meshes = [o for o in selected if o.type == "MESH"]
    tris = sum(_tris(o) for o in meshes)
    result["tris"] = tris
    tools = case["tools"]
    if tools == "auto":
        tools = (["validate", "export", "lods", "retopo", "subd_high", "bake", "clean", "unwrap", "prep", "fix_all"] if tris <= 100_000 else
                 ["validate", "export", "lods", "retopo", "clean", "fix_all"] if tris <= 600_000 else
                 ["validate", "export", "lods", "fix_all"])
    elif tools == "all":
        tools = ["validate", "export", "lods", "retopo", "subd_high", "bake", "clean", "unwrap", "prep", "fix_all"]
    if os.environ.get("STRESS_TOOLS"):  # e.g. STRESS_TOOLS=validate,lods to look at one step
        tools = os.environ["STRESS_TOOLS"].split(",")
    result["tools"] = tools

    def select(objects):
        for o in scene.objects:
            o.select_set(False)
        for o in objects:
            o.hide_set(False)
            o.select_set(True)
        if objects:
            bpy.context.view_layer.objects.active = objects[0]

    def issues(objects):
        """{object: {check: worst severity}} of warnings and errors, plus the full list."""
        res = engine.run_validation(config, objects)
        found = {}
        for r in res:
            if r.severity.value in ("WARNING", "ERROR") and r.waived is None:
                worst = found.setdefault(r.object_name, {})
                worst[r.check_name] = "ERROR" if r.severity.value == "ERROR" or worst.get(r.check_name) == "ERROR" else "WARNING"
        return res, found

    def step(label, fn):
        entry = {"step": label, "started": True}
        result["steps"].append(entry)
        flush()
        out = io.StringIO()
        t = time.perf_counter()
        try:
            with contextlib.redirect_stdout(out):
                entry.update(fn() or {})
            entry["ok"] = True
        except Exception:
            entry["ok"] = False
            entry["error"] = traceback.format_exc()[-3000:]
        entry["seconds"] = round(time.perf_counter() - t, 2)
        entry["printed"] = out.getvalue()[-4000:]
        entry.pop("started")
        flush()
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        return entry

    def op(call, **kw):
        try:
            return sorted(call(**kw))
        except RuntimeError as e:  # operator reported an ERROR
            return [f"RuntimeError: {str(e).strip()[:500]}"]

    # 1. Validate, with each check timed
    def validate():
        res, found = issues(selected)
        timings = {}
        roles = {o: role(o, config) for o in meshes}
        for check in get_checks():
            targets = [o for o in meshes if roles[o] in check.roles]
            if targets:
                t = time.perf_counter()
                try:
                    check(targets, config)
                except Exception as e:
                    timings[check.__name__ + " RAISED"] = str(e)[:300]
                timings[check.__name__] = round(time.perf_counter() - t, 3)
        scope = {case["on"]: found.get(case["on"], {})} if case.get("on") else found  # expectations about one object
        fired = {c for d in scope.values() for c in d}
        errors = {c for d in scope.values() for c, s in d.items() if s == "ERROR"}
        forbid = set(case["forbid"])
        false_positive = sorted((fired & forbid) | ({"*error"} if "*error" in forbid and errors else set()))
        return {
            "results": [{"object": r.object_name, "check": r.check_name, "severity": r.severity.value,
                         "message": r.message[:300], "fix": r.fix is not None} for r in res],
            "check_seconds": timings,
            "expectation": {"missed": sorted(set(case["expect"]) - fired), "false_positive": false_positive,
                            "artist_ok_fired": sorted(set(case["artist_ok"]) & fired), "fired": sorted(fired),
                            "errors": sorted(errors), "gap": case["gap"]},
        }

    base_found = {}

    def run_validate():
        entry = validate()
        base_found.update({o: d for o, d in issues(selected)[1].items()})
        return entry

    def export(tag):
        def run():
            select(selected)
            ret = op(bpy.ops.asset_validator.export)
            folder = os.path.join(work, "exports")
            files = {f: os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder)} if os.path.isdir(folder) else {}
            return {"return": ret, "files": files}
        return run

    def delta(objects, reference):
        """Checks firing on the tool's output that didn't on its source: what the tool broke."""
        _, found = issues(objects)
        out = {}
        for o in objects:
            new = {c: s for c, s in found.get(o.name, {}).items() if c not in reference}
            out[o.name] = {"tris": _tris(o), "issues": found.get(o.name, {}), "introduced": new,
                           "shape_keys": len(o.data.shape_keys.key_blocks) if o.type == "MESH" and o.data.shape_keys else 0}
        return out

    def source_issues(objects):
        return {c for o in objects for c in base_found.get(o.name, {})}

    def lods():
        from blender_asset_validator.operations.lod import lods_of
        assets = [o for o in meshes if role(o, config) == "asset"]
        select(assets)
        ret = op(bpy.ops.asset_validator.generate_lods)
        made = [l for o in assets for l in lods_of(o)]
        return {"return": ret, "lods": delta(made, source_issues(assets)),
                "stray": [l.name for l in made if "asset_validator_lod_stray" in l]}

    def retopo():
        before = set(bpy.data.objects)
        select(meshes)
        ret = op(bpy.ops.asset_validator.retopologize, ratio=0.5)
        made = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        return {"return": ret, "made": delta(made, source_issues(meshes))}

    def subd_high():
        before = set(bpy.data.objects)
        select(meshes)
        ret = op(bpy.ops.asset_validator.make_high)
        made = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        return {"return": ret, "highs": {o.name: _tris(o, evaluated=True) for o in made}}

    def bake():
        select(meshes)
        return {"return": op(bpy.ops.asset_validator.bake_normals),
                "images": [i.name for i in bpy.data.images if i.name.endswith("_N")]}

    def on_copies(operator, **kw):
        def run():
            copies = []
            for o in meshes:
                if role(o, config) != "asset":
                    continue
                c = o.copy()
                c.data = o.data.copy()
                c.name = o.name[:52] + "_Copy"
                scene.collection.objects.link(c)
                copies.append((o, c))
            if not copies:
                return {"skipped": "no asset meshes"}
            select([c for _, c in copies])
            ret = op(operator, **kw)
            out = delta([c for _, c in copies], source_issues([o for o, _ in copies]))
            for o, c in copies:  # keep the result in the work file, out of the way
                c.name = o.name[:48] + "_" + label_of(operator)
                c.hide_set(True)
            return {"return": ret, "copies": out}
        return run

    def label_of(operator):
        return {"clean_topology": "Clean", "auto_unwrap": "Unwrap", "hard_surface_prep": "Prep"}[operator.idname_py().split(".")[1]]

    def fix_all():
        select(selected)
        bpy.ops.asset_validator.validate()
        ret = op(bpy.ops.asset_validator.fix_all)
        after = delta(meshes, source_issues(meshes))
        _, found = issues(selected)
        remaining_fixable = [(r.object_name, r.check_name) for r in engine.run_validation(config, selected) if r.fix is not None]
        return {"return": ret, "after": after, "still_fixable": remaining_fixable[:50]}

    plan = {
        "validate": run_validate, "export": export("as-is"), "lods": lods, "retopo": retopo, "subd_high": subd_high,
        "bake": bake, "clean": on_copies(bpy.ops.asset_validator.clean_topology),
        "unwrap": on_copies(bpy.ops.asset_validator.auto_unwrap),
        "prep": on_copies(bpy.ops.asset_validator.hard_surface_prep, bevel=True),
        "fix_all": fix_all,
    }
    for tool in tools:
        if tool == "bake" and tris > 30_000:
            continue  # Cycles in -b: a big bake is minutes of CPU for little news
        step(tool, plan[tool])
    if "fix_all" in tools:
        step("export_after_fix", export("after Fix All"))
    t = time.perf_counter()
    bpy.ops.wm.save_mainfile()
    result["save_seconds"] = round(time.perf_counter() - t, 2)
    result["done"] = True
    flush()


def _tris(obj, evaluated=False):
    import bpy
    if obj.type != "MESH":
        return 0
    if evaluated:
        from blender_asset_validator.core.mesh_utils import evaluated_triangle_count
        return evaluated_triangle_count(obj)
    import numpy as np
    total = np.empty(len(obj.data.polygons), np.int32)
    obj.data.polygons.foreach_get("loop_total", total)
    return int((total - 2).sum())


if __name__ == "__main__":
    if "--" in sys.argv and sys.argv[sys.argv.index("--") + 1:][:1] == ["case"]:
        in_blender(sys.argv[sys.argv.index("--") + 2])
    else:
        orchestrate(sys.argv[1:])
