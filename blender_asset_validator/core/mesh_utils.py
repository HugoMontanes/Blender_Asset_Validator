import bmesh
import bpy
import numpy as np


def read_array(seq, attr: str, width: int = 1, dtype=np.float32) -> np.ndarray:
    """`attr` of every item of a bpy collection (vertices, loops, polygons, UV data...)
    as a numpy array, `width` columns per item. foreach_get is ~50x faster than a loop."""
    arr = np.empty(len(seq) * width, dtype)
    seq.foreach_get(attr, arr)
    return arr.reshape(-1, width) if width > 1 else arr


def evaluated_triangle_count(obj: bpy.types.Object) -> int:
    """Triangle count of `obj`'s mesh with modifiers applied — what actually gets exported."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return len(mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()


def bake_mesh(obj: bpy.types.Object) -> bpy.types.Mesh:
    """New mesh datablock of `obj` with modifiers applied, without bpy.ops (works headless and in any mode)."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return bpy.data.meshes.new_from_object(
        obj.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph
    )


def select_in_edit_mode(obj: bpy.types.Object, mode: str, indices) -> None:
    """Open obj (made active) in Edit Mode with just these elements selected.
    mode: VERT, EDGE or FACE (what `indices` index). The object selection is
    kept, since it's the validation set; the other selected meshes enter Edit
    Mode too, with nothing selected in them."""
    context = bpy.context
    obj.hide_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj

    for other in {o.data for o in context.selected_objects if o.type == "MESH"}:
        bm = bmesh.new()
        bm.from_mesh(other)
        for seq in (bm.verts, bm.edges, bm.faces):
            for elem in seq:
                elem.select = False
        if other is obj.data:
            seq = {"VERT": bm.verts, "EDGE": bm.edges, "FACE": bm.faces}[mode]
            seq.ensure_lookup_table()
            for i in indices:
                if i < len(seq):
                    seq[i].select_set(True)  # also selects its vertices/edges, as Edit Mode expects
        bm.to_mesh(other)
        bm.free()

    context.tool_settings.mesh_select_mode = (mode == "VERT", mode == "EDGE", mode == "FACE")
    bpy.ops.object.mode_set(mode="EDIT")
