import bpy


def redraw_view3d(context: bpy.types.Context) -> None:
    for area in context.screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()
