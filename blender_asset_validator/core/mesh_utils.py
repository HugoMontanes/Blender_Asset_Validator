import bpy


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
