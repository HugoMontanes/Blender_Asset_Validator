"""Phase 0: engine profiles, object roles, per-engine export layouts, heatmaps,
accepted warnings, JSON/HTML reports and the batch CLI."""
import sys, os, traceback, json, shutil, struct
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT_DIR = os.path.join(HERE, "_out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(__file__))[0] + ".txt")
WORK = os.path.join(OUT_DIR, "work_engines")
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)
sys.path.insert(0, REPO)
out = open(OUT, "w", encoding="utf-8")
def say(m): out.write(m + "\n"); out.flush()
def check(name, cond, extra=""): say(f"{'PASS' if cond else 'FAIL'}  {name}  {extra}")
import bpy, bmesh
try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import blender_asset_validator as bav
    from blender_asset_validator import cli
    from blender_asset_validator.core import engine, state, roles
    from blender_asset_validator.core.result import Severity
    from blender_asset_validator.operations import heatmap
    from blender_asset_validator.operations.lod import lods_of
    from blender_asset_validator.report.generator import file_report, write_report
    from io_scene_fbx import parse_fbx
    bav.register()
    AV = bpy.ops.asset_validator
    scene = bpy.context.scene

    def mk(name, fill=lambda bm: bmesh.ops.create_cube(bm, size=1.0), mat=True):
        bm = bmesh.new(); bm.loops.layers.uv.new("UVMap"); fill(bm)
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
        if mat:
            me.materials.append(bpy.data.materials.new(name + "Mat"))
        return o
    def unwrap(o):  # every face its own UV cell, so the UV check stays quiet
        bm = bmesh.new(); bm.from_mesh(o.data); uv = bm.loops.layers.uv.active
        for i, f in enumerate(bm.faces):
            for j, l in enumerate(f.loops):
                l[uv].uv = ((i % 4) * 0.25 + (0, .2, .2, 0)[j % 4], (i // 4) * 0.25 + (0, 0, .2, .2)[j % 4])
        bm.to_mesh(o.data); bm.free()
    def select(*objs):
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs: o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
    def fbx_nodes(path):
        """{model name: (FBX type of its node attribute or model, parent model name or None)}."""
        root, _ = parse_fbx.parse(path)
        objs = next(e for e in root.elems if e.id == b"Objects")
        models = {e.props[0]: [e.props[1].split(b"\x00\x01")[0].decode(), e.props[2].decode(), None] for e in objs.elems if e.id == b"Model"}
        attrs = {e.props[0]: e.props[2].decode() for e in objs.elems if e.id == b"NodeAttribute"}
        for c in next(e for e in root.elems if e.id == b"Connections").elems:
            child, parent = c.props[1], c.props[2]
            if child in attrs and parent in models:
                models[parent][1] = attrs[child]
            elif child in models and parent in models:
                models[child][2] = models[parent][0]
        return {name: (kind, parent) for name, kind, parent in models.values()}
    def glb_nodes(path):
        data = open(path, "rb").read()
        length = struct.unpack_from("<I", data, 12)[0]
        return [n.get("name") for n in json.loads(data[20:20 + length])["nodes"]]
    exports = os.path.join(WORK, "exports")
    def export(*objs):
        shutil.rmtree(exports, ignore_errors=True)
        select(*objs)
        try:
            r = AV.export()
        except RuntimeError as e:  # bpy.ops raises on a reported ERROR
            r = str(e)
        return r, sorted(os.listdir(exports)) if os.path.isdir(exports) else []

    # engine profiles and config layering
    ids = [item[0] for item in engine.ENGINE_ITEMS]
    check("engines: Custom, Godot, Unity, Unreal", ids == ["NONE", "godot", "unity", "unreal"], str(ids))
    scene.asset_validator_engine = "unity"
    c = engine.load_config()
    check("engine profile merged", c["lod"]["export_target"] == "unity" and c["export"]["axis_forward"] == "-Z")
    scene.asset_validator_preset = "mobile"
    c = engine.load_config()
    check("preset merged on top of the engine", c["geometry"]["max_triangles"] == 5000 and c["lod"]["export_target"] == "unity")
    scene.asset_validator_preset = "NONE"
    blend = os.path.join(WORK, "scene.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    with open(os.path.join(WORK, "asset_validator.json"), "w") as f:
        json.dump({"geometry": {"max_triangles": 1234}}, f)
    check("project asset_validator.json merged last", engine.load_config()["geometry"]["max_triangles"] == 1234)
    for bad in ("^UCX_(.+)$", "^UCX_("):
        with open(os.path.join(WORK, "asset_validator.json"), "w") as f:
            json.dump({"roles": {"collision": bad}}, f)
        try:
            engine.load_config(); refused = False
        except ValueError as e:
            refused = "roles.collision" in str(e)
        check(f"bad roles.collision {bad!r} refused as a config error", refused)
    os.remove(os.path.join(WORK, "asset_validator.json"))
    check("enum items numbered by name, not position", all(len(i) == 4 for i in engine.ENGINE_ITEMS + engine.PRESET_ITEMS)
          and len({i[3] for i in engine.ENGINE_ITEMS}) == len(engine.ENGINE_ITEMS))
    getattr(scene, "bl_system_properties_get", lambda: scene)()["asset_validator_engine"] = 12345  # a profile this install lacks
    check("unknown saved engine falls back to Custom", scene.asset_validator_engine == "" and engine.load_config()["lod"]["export_target"] == "none")
    scene.asset_validator_engine = "unreal"
    check("changing engine clears results", state.get_results() is None)

    # roles
    crate = mk("Crate"); unwrap(crate)
    ucx = mk("UCX_Crate_01", mat=False)
    orphan = mk("UCX_Missing", mat=False)
    sock = bpy.data.objects.new("SOCKET_Top", None); scene.collection.objects.link(sock); sock.parent = crate
    c = engine.load_config()
    check("roles: asset, collision, socket", [roles.role(o, c) for o in (crate, ucx, sock)] == ["asset", "collision", "socket"])
    check("roles: collision owner", roles.collision_owner(ucx, c) == "Crate" and roles.collisions_of(crate, c) == [ucx])
    check("roles: Custom engine has no collisions", roles.role(ucx, {"roles": {}}) == "asset")
    pipe, ucx_pipe = mk("Pipe_90"), mk("UCX_Pipe_90", mat=False)  # no index: the whole name is the owner
    check("roles: owner ending in digits", roles.collision_owner(ucx_pipe, c) == "Pipe_90" and roles.collisions_of(pipe, c) == [ucx_pipe]
          and roles.renamed_collision(ucx_pipe, "Pipe_90_LOD0", c) == "UCX_Pipe_90_LOD0", roles.collision_owner(ucx_pipe, c))
    bpy.data.objects.remove(pipe); bpy.data.objects.remove(ucx_pipe)
    res = engine.run_validation(c, [crate, ucx, orphan])
    by = lambda name: [(r.check_name, r.severity) for r in res if r.object_name == name]
    check("collision skips material/UV checks", not any(n in ("materials", "uvs") for n, _ in by("UCX_Crate_01")), str(by("UCX_Crate_01")))
    check("orphan collision warned", ("collisions", Severity.WARNING) in by("UCX_Missing"), str(by("UCX_Missing")))
    ucx.scale = (2, 2, 2)
    check("collision still gets the transforms check", any(r.check_name == "transforms" and r.object_name == "UCX_Crate_01"
                                                         for r in engine.run_validation(c, [ucx])))
    ucx.scale = (1, 1, 1)
    bpy.data.objects.remove(orphan)

    # export: Unreal
    select(crate); AV.generate_lods()
    r, files = export(crate)
    check("unreal: one fbx", r == {"FINISHED"} and files == ["Crate.fbx"], f"{r} {files}")
    nodes = fbx_nodes(os.path.join(exports, "Crate.fbx")) if files else {}
    say("   " + str(nodes))
    check("unreal: Crate is an FBX LOD Group", nodes.get("Crate", ("",))[0] == "LodGroup")
    check("unreal: LOD0..3 under the group", all(nodes.get(f"Crate_LOD{i}", (None, None))[1] == "Crate" for i in range(4)))
    check("unreal: UCX renamed after LOD0", "UCX_Crate_LOD0_01" in nodes and nodes["UCX_Crate_LOD0_01"][1] is None)
    check("unreal: socket exported", "SOCKET_Top" in nodes)
    check("unreal: names, parents and transforms restored",
          crate.name == "Crate" and ucx.name == "UCX_Crate_01" and crate.parent is None and sock.parent == crate
          and lods_of(crate)[0].parent is None and crate.matrix_world.is_identity and "Crate" not in [o.name for o in bpy.data.objects if o.type == "EMPTY"])
    ucx.hide_set(True)
    bpy.context.view_layer.layer_collection.children["LODs"].hide_viewport = True
    r, files = export(crate)
    nodes = fbx_nodes(os.path.join(exports, "Crate.fbx")) if files else {}
    check("unreal: hidden collisions and LODs still exported", "UCX_Crate_LOD0_01" in nodes and "Crate_LOD3" in nodes and ucx.hide_get(), str(nodes))
    ucx.hide_set(False)
    bpy.context.view_layer.layer_collection.children["LODs"].hide_viewport = False
    r, files = export(crate, ucx, *lods_of(crate))
    check("unreal: selected LODs/collisions not exported on their own", files == ["Crate.fbx"], str(files))

    # export: Unity
    scene.asset_validator_engine = "unity"
    r, files = export(crate)
    nodes = fbx_nodes(os.path.join(exports, "Crate.fbx")) if files else {}
    check("unity: one fbx with Crate_LOD0..3 side by side",
          files == ["Crate.fbx"] and all(nodes.get(f"Crate_LOD{i}", (None, "x"))[1] is None for i in range(4)), str(nodes))
    check("unity: collision kept under its own name", "UCX_Crate_01" in nodes and "Crate" not in nodes)
    crate.name = "Stool"  # LODs keep the Crate_ names they were generated with
    r, files = export(crate)
    nodes = fbx_nodes(os.path.join(exports, "Stool.fbx")) if files else {}
    check("unity: LODs renamed after the asset's current name", all(f"Stool_LOD{i}" in nodes for i in range(4)), str(nodes))
    check("unity: LOD names restored", lods_of(crate)[0].name == "Crate_LOD1")
    crate.name = "Crate"
    with open(os.path.join(WORK, "asset_validator.json"), "w") as f:
        json.dump({"lod": {"export_target": "unity_godot"}}, f)
    r, files = export(crate)
    os.remove(os.path.join(WORK, "asset_validator.json"))
    check("unknown lod.export_target refused", "Unknown lod.export_target" in str(r) and not files, f"{r} {files}")

    # export: Godot
    scene.asset_validator_engine = "godot"
    col = mk("Crate-colonly", mat=False)
    col.hide_set(True)
    r, files = export(crate)
    names = glb_nodes(os.path.join(exports, "Crate.glb")) if files == ["Crate.glb"] else []
    check("godot: one glb with the asset and its (hidden) -colonly", set(names) == {"Crate", "Crate-colonly"}, f"{files} {names}")
    bpy.data.objects.remove(col)

    # heatmaps
    scene.asset_validator_engine = "NONE"
    def warped_grid(bm):
        bmesh.ops.create_grid(bm, x_segments=2, y_segments=1, size=1.0)
        max(bm.verts, key=lambda v: v.co.x + v.co.y).co.z = 0.6
        v = [bm.verts.new(p) for p in ((3, 0, 0), (4, 0, 0), (3, 0.02, 0))]  # quality 0.035: red is under half the 0.1 limit
        bm.faces.new(v)
    hm = mk("Heat", warped_grid)
    select(hm)
    AV.show_heatmap(metric="WARP")
    attr = hm.data.color_attributes.get(heatmap.HEAT)
    colors = [tuple(round(c, 2) for c in attr.data[p.loop_start].color[:3]) for p in hm.data.polygons] if attr else []
    say(f"   warp colors per face: {colors}")
    check("heatmap: attribute shown as active color", attr is not None and hm.data.color_attributes.active_color_name == heatmap.HEAT)
    check("heatmap: warped quad red, flat quad blue, triangle gray",
          len(colors) == 3 and sorted(colors[:2]) == [(0.0, 0.2, 1.0), (1.0, 0.1, 0.0)] and colors[2] == (0.5, 0.5, 0.5), str(colors))
    AV.show_heatmap(metric="TRI_QUALITY")
    attr = hm.data.color_attributes.get(heatmap.HEAT)
    check("heatmap: replaced, not stacked", sum(a.name == heatmap.HEAT for a in hm.data.color_attributes) == 1)
    sliver = attr.data[hm.data.polygons[2].loop_start].color
    check("heatmap: sliver triangle red", sliver[0] > 0.9 and sliver[1] < 0.5 and sliver[2] < 0.1, str(tuple(sliver)))
    AV.clear_heatmap()
    check("heatmap: cleared", heatmap.HEAT not in hm.data.color_attributes)
    select(crate); AV.show_heatmap(metric="WARP")
    export(crate)
    check("heatmap: stripped on export", heatmap.HEAT not in crate.data.color_attributes)

    # accepted warnings
    ng = mk("Warned", lambda bm: bm.faces.new([bm.verts.new((x, y, 0)) for x, y in ((0, 0), (1, 0), (1.5, 1), (0.5, 1.5), (-0.5, 1))]))
    unwrap(ng)
    select(ng); AV.validate()
    find = lambda name: next((i for i, r in enumerate(state.get_results()) if r.check_name == name and r.object_name == "Warned"), None)
    i = find("ngons")
    check("waiver: warning present", i is not None)
    try:
        AV.waive_result(result_index=i, reason="")
        check("waiver: empty reason refused", False)
    except RuntimeError:
        check("waiver: empty reason refused", state.get_results()[i].waived is None)
    AV.waive_result(result_index=i, reason="Flat cap, triangulated in engine")
    i = find("ngons")
    check("waiver: warning accepted with its reason", state.get_results()[i].waived == "Flat cap, triangulated in engine")
    del ng["asset_validator_waivers"]  # what an undo does before the redo panel re-runs the operator
    before = state.get_results()
    AV.waive_result(result_index=i, reason="Edited in the redo panel")
    check("waiver: redo after undo accepts with the new reason, no re-validation",
          state.get_results() is before and before[i].waived == "Edited in the redo panel", str(before[i].waived))
    me = ng.data; bm = bmesh.new(); bm.from_mesh(me)
    bm.faces.new([bm.verts.new((x + 5, y, 0)) for x, y in ((0, 0), (1, 0), (1.5, 1), (0.5, 1.5), (-0.5, 1))])
    bm.to_mesh(me); bm.free()
    AV.validate()
    i = find("ngons")
    check("waiver: survives the count changing", state.get_results()[i].waived is not None, state.get_results()[i].message)
    rep = file_report("x.blend", "NONE", "NONE", state.get_results())
    check("waiver: report counts it as accepted, not as a warning", rep["accepted"] == 1 and not any(
        r["check"] == "ngons" and r["accepted"] is None for r in rep["results"]))
    AV.waive_result(result_index=i)
    check("waiver: clicking again withdraws it", state.get_results()[find("ngons")].waived is None)
    bad = mk("bad_name"); select(bad); AV.validate()
    j = next(k for k, r in enumerate(state.get_results()) if r.severity == Severity.ERROR)
    try:
        AV.waive_result(result_index=j, reason="nope")
        check("waiver: errors can't be accepted", False)
    except RuntimeError:
        check("waiver: errors can't be accepted", state.get_results()[j].waived is None)
    bpy.data.objects.remove(bad)

    # reports and CLI
    json_path, html_path = os.path.join(WORK, "r.json"), os.path.join(WORK, "r.html")
    write_report(json_path, [rep]); write_report(html_path, [rep])
    data = json.load(open(json_path))
    check("report: json", data["files"][0]["accepted"] == 1 and data["files"][0]["passed"])
    check("report: html", "<table>" in open(html_path, encoding="utf-8").read())
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    ok_blend = os.path.join(WORK, "ok.blend")
    for o in list(scene.objects):
        if o not in (crate, ucx):
            bpy.data.objects.remove(o)
    scene.asset_validator_engine = "unreal"  # saved in the .blend: the CLI uses it when not given one
    bpy.ops.wm.save_as_mainfile(filepath=ok_blend)
    mk("bad_name")
    bad_blend = os.path.join(WORK, "bad.blend")
    bpy.ops.wm.save_as_mainfile(filepath=bad_blend)
    code = cli.main(["--report", json_path, ok_blend])
    data = json.load(open(json_path))
    check("cli: the .blend's own engine, clean file passes, exit 0", code == 0 and data["files"][0]["passed"] and data["files"][0]["engine"] == "unreal", str(data["files"][0]["errors"]))
    check("cli: collisions validated as collisions", not any(r["object"] == "UCX_Crate_01" and r["check"] == "materials" for r in data["files"][0]["results"]))
    code = cli.main(["--engine", "NONE", ok_blend])
    check("cli: --engine overrides the saved one", code == 1 and bpy.context.scene.asset_validator_engine == "NONE")
    code = cli.main(["--report", html_path, "--engine", "unreal", ok_blend, bad_blend])
    check("cli: a failing file gives exit 1", code == 1)
    check("cli: html lists both files", all(name in open(html_path, encoding="utf-8").read() for name in ("ok.blend", "bad.blend")))
    def files_of(*argv):
        code = cli.main(["--report", json_path, *argv])
        return code, json.load(open(json_path))["files"]
    parallel = files_of("--jobs", "2", "--engine", "unreal", bad_blend, ok_blend)
    sequential = files_of("--jobs", "1", "--engine", "unreal", bad_blend, ok_blend)
    check("cli --jobs: two background Blenders give the same reports, in the files' order, as one after another",
          parallel == sequential and [f["file"] for f in parallel[1]] == [bad_blend, ok_blend] and parallel[0] == 1,
          f"{[(f['file'], f['errors']) for f in parallel[1]]} vs {[(f['file'], f['errors']) for f in sequential[1]]}")
    corrupt = os.path.join(WORK, "corrupt.blend")
    with open(corrupt, "wb") as f:
        f.write(b"not a blend file")
    code, files = files_of("--jobs", "2", corrupt, ok_blend)
    check("cli --jobs: a corrupt .blend fails on its own, the other file is still validated",
          code == 1 and not files[0]["passed"] and "before writing a report" in files[0]["results"][0]["message"] and files[1]["passed"],
          str([(f["file"], f["passed"], f["results"][:1]) for f in files]))

    bav.unregister()
    say("DONE")
except Exception:
    say("EXCEPTION\n" + traceback.format_exc())
