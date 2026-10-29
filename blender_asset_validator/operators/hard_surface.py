import math

import bpy

from . import ObjectModeOnly
from ..core.engine import load_config
from ..core.state import clear_results
from ..operations.hard_surface import add_modifiers, prep_mesh
from ..ui.redraw import redraw_view3d
from .uvs import SKIPPED_NOTE, asset_meshes


class ASSET_VALIDATOR_OT_hard_surface_prep(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.hard_surface_prep"
    bl_label = "Hard Surface Prep"
    bl_description = (
        "Smooth by angle with the bent edges marked sharp, Auto Unwrap, the profile's texel density and a "
        "Weighted Normal modifier; optionally a Bevel on the sharp edges (mid-poly). Replaces UV0: run it before baking"
    )
    bl_options = {"REGISTER", "UNDO"}

    angle: bpy.props.FloatProperty(
        name="Sharp Angle", description="Edges bent more than this are marked sharp (and become seams)",
        subtype="ANGLE", default=math.radians(30.0), min=0.0, max=math.pi,
    )
    bevel: bpy.props.BoolProperty(
        name="Bevel Sharp Edges", description="Mid-poly support loops: a Bevel modifier rounds the sharp edges, "
        "and the Weighted Normal keeps the big faces flat",
    )
    segments: bpy.props.IntProperty(name="Segments", default=2, min=1, max=8)

    def invoke(self, context, event):
        if not self.properties.is_property_set("angle"):
            self.angle = math.radians(load_config().get("topology", {}).get("feature_angle", 30.0))
        return self.execute(context)

    def execute(self, context):
        config = load_config()
        objects = [obj for obj in asset_meshes(context.selected_objects, config) if obj.data.polygons]
        if not objects:
            self.report({"ERROR"}, f"Select at least one asset mesh with faces first ({SKIPPED_NOTE})")
            return {"CANCELLED"}

        prepared, lines = set(), []
        for obj in objects:
            notes = []
            if obj.data not in prepared:  # linked duplicates share the mesh, not the modifiers
                prepared.add(obj.data)
                notes.append(prep_mesh(obj, config, self.angle, self.bevel))
            notes += add_modifiers(obj, self.segments if self.bevel else 0)
            lines.append(f"'{obj.name}': {', '.join(notes) or 'shared mesh already prepared'}")
        print("\n".join(lines))
        clear_results()
        redraw_view3d(context)
        self.report({"INFO"}, lines[0] if len(lines) == 1 else "; ".join(lines))
        return {"FINISHED"}
