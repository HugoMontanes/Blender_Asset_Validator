"""QuadriFlow in a background Blender started by topology._Remesher, which can kill it at a time
limit: on some inputs QuadriFlow never returns. One job per stdin line, {"in", "out", "faces",
"symmetry"}; the answer is the "out" .npz (co, quads; empty if it failed), renamed into place whole."""
import json
import os
import sys
import time

import bpy
import numpy as np

_MAX_REMESH_TRIS = 300_000  # denser inputs are decimated first: memory and time grow with them


def remesh(co, sizes, corners, target_faces, symmetry):
    """(vertex positions, quads) QuadriFlow made of the faces, or None."""
    starts = np.cumsum(sizes) - sizes
    mesh = bpy.data.meshes.new("part")
    mesh.from_pydata(co.tolist(), [], [corners[s:s + n].tolist() for s, n in zip(starts, sizes)])
    obj = bpy.data.objects.new("part", mesh)
    bpy.context.scene.collection.objects.link(obj)
    try:
        with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj], selected_editable_objects=[obj]):
            tris = int((sizes - 2).sum())
            if tris > _MAX_REMESH_TRIS:
                # shortcut: only the input is thinned — detail finer than the cap's edge length is lost
                obj.modifiers.new("cap", "DECIMATE").ratio = _MAX_REMESH_TRIS / tris
                bpy.ops.object.modifier_apply(modifier="cap")
            before = (len(obj.data.vertices), len(obj.data.polygons))
            try:
                bpy.ops.object.quadriflow_remesh(
                    mode="FACES", target_faces=target_faces, use_mesh_symmetry=symmetry,
                    use_preserve_sharp=True, use_preserve_boundary=True, smooth_normals=False, seed=0,
                )
            except RuntimeError:  # refused, e.g. not manifold
                return None
        result = obj.data
        # QuadriFlow reports most failures only to the UI and leaves the mesh untouched
        if not result.polygons or (len(result.vertices), len(result.polygons)) == before \
                or any(p.loop_total != 4 for p in result.polygons):
            return None
        out_co = np.empty(len(result.vertices) * 3, np.float32)
        result.vertices.foreach_get("co", out_co)
        quads = np.empty(len(result.loops), np.int32)
        result.loops.foreach_get("vertex_index", quads)
        return out_co.reshape(-1, 3), quads.reshape(-1, 4)
    finally:
        mesh = obj.data
        bpy.data.objects.remove(obj)
        bpy.data.meshes.remove(mesh)


def _patient(action, *args):
    """action(*args), retried for a few seconds while Windows reports the file busy (an antivirus scanning it)."""
    for _ in range(100):
        try:
            return action(*args)
        except PermissionError:
            time.sleep(0.05)
    return action(*args)


def _read(path):
    with np.load(path) as data:
        return data["co"], data["sizes"], data["corners"]


def main():
    for line in sys.stdin:
        job = json.loads(line)
        made = remesh(*_patient(_read, job["in"]), job["faces"], job["symmetry"])
        co, quads = made or (np.empty((0, 3), np.float32), np.empty((0, 4), np.int32))
        partial = job["out"] + ".part.npz"
        np.savez(partial, co=co, quads=quads)
        _patient(os.replace, partial, job["out"])


if __name__ == "__main__":  # blender --python runs it as __main__; importing it does nothing
    main()
