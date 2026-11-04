import math

import bpy

from . import ObjectModeOnly, Steps, restorable
from ..core.engine import load_config
from ..operations.hard_surface import add_modifiers, prep_mesh_steps
from .uvs import SKIPPED_NOTE, asset_meshes


class ASSET_VALIDATOR_OT_hard_surface_prep(ObjectModeOnly, Steps, bpy.types.Operator):
    bl_idname = "asset_validator.hard_surface_prep"
    bl_label = "Hard Surface Prep"
    bl_description = (
        "Smooth by angle with the bent edges marked sharp, Auto Unwrap, the profile's texel density and a "
        "Weighted Normal modifier; optionally a Bevel on the sharp edges (mid-poly). Replaces UV0: run it before baking. "
        "Esc stops it between steps and puts back the mesh it was on"
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
        return super().invoke(context, event)

    def _begin(self, context) -> bool:
        self._config = load_config()
        self._objects = [obj for obj in asset_meshes(context.selected_objects, self._config) if obj.data.polygons]
        if not self._objects:
            self.report({"ERROR"}, f"Select at least one asset mesh with faces first ({SKIPPED_NOTE})")
            return False
        self._prepared = set()
        return True

    def _work(self):
        return self._each(self._objects, self._prep)

    def _prep(self, obj):
        notes = []
        if obj.data not in self._prepared:  # linked duplicates share the mesh, not the modifiers
            self._prepared.add(obj.data)
            notes.append((yield from restorable(obj, prep_mesh_steps(obj, self._config, self.angle, self.bevel))))
        notes += add_modifiers(obj, self.segments if self.bevel else 0)
        return ", ".join(notes) or "shared mesh already prepared"
