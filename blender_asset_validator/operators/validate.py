import bpy

from . import ObjectModeOnly
from ..core.engine import get_validation_objects, load_config, validate_and_store
from ..core.result import Severity
from ..core.state import clear_results
from ..core.steps import STEPS, step_checks
from ..ui.redraw import redraw_view3d


class ASSET_VALIDATOR_OT_validate(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.validate"
    bl_label = "Validate Asset"
    bl_description = "Run all pipeline checks on the mesh objects that Export would export"

    def execute(self, context):
        config = load_config()
        objects = get_validation_objects(config)
        if not objects:
            self.report({"ERROR"}, "No mesh objects to validate (check the selection / config 'export')")
            return {"CANCELLED"}

        results = validate_and_store(config, objects, step_checks(context.scene))

        errors = sum(1 for r in results if r.severity == Severity.ERROR)
        warnings = sum(1 for r in results if r.severity == Severity.WARNING)

        if errors:
            self.report({"WARNING"}, f"Validation failed — {errors} error(s), {warnings} warning(s)")
        else:
            self.report({"INFO"}, f"Validation passed — {warnings} warning(s)")

        redraw_view3d(context)
        return {"FINISHED"}


class ASSET_VALIDATOR_OT_go_to_step(bpy.types.Operator):
    bl_idname = "asset_validator.go_to_step"
    bl_label = "Go to Step"
    bl_description = "Work on this step: runs its checks on the current selection"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty()

    def execute(self, context):
        _enter_step(context, self.index)
        return {"FINISHED"}


class ASSET_VALIDATOR_OT_approve_step(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.approve_step"
    bl_label = "Approve & Next"
    bl_description = "Mark this step as reviewed and move on to the next one (blocked while it has errors)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        config = load_config()
        objects = get_validation_objects(config)
        if not objects:
            self.report({"ERROR"}, "No mesh objects to validate (check the selection / config 'export')")
            return {"CANCELLED"}
        # Re-check: the artist may have edited by hand since the results were made
        results = validate_and_store(config, objects, step_checks(scene))
        redraw_view3d(context)
        if any(r.severity == Severity.ERROR for r in results):
            self.report({"ERROR"}, "Fix this step's errors before approving it")
            return {"CANCELLED"}
        scene.asset_validator_approved[scene.asset_validator_step] = True
        if scene.asset_validator_step + 1 < len(STEPS):
            _enter_step(context, scene.asset_validator_step + 1)
        else:
            self.report({"INFO"}, "All steps approved")
        return {"FINISHED"}


def _enter_step(context, index):
    """Switch the scene to step `index` and show its findings right away."""
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    context.scene.asset_validator_step = index
    config = load_config()
    objects = get_validation_objects(config)
    if objects:
        validate_and_store(config, objects, step_checks(context.scene))
    else:
        clear_results()
    redraw_view3d(context)
