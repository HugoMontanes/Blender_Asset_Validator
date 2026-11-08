import bpy

from . import ObjectModeOnly, Steps
from ..core.engine import get_validation_objects, load_config, store_results, validate_and_store, validation_steps
from ..core.result import Severity
from ..core.state import clear_results
from ..core.steps import STEPS, approve_step, step_checks
from ..ui.redraw import redraw_view3d


class ASSET_VALIDATOR_OT_validate(ObjectModeOnly, Steps, bpy.types.Operator):
    bl_idname = "asset_validator.validate"
    bl_label = "Validate Asset"
    bl_description = ("Run all pipeline checks on the mesh objects that Export would export. "
                      "Progress in the status bar; Esc stops it and keeps the previous results")

    def _begin(self, context) -> bool:
        self._results = None  # stays None if validation_steps raises: Steps re-raises that error after _finish
        self._config = load_config()
        self._objects = get_validation_objects(self._config)
        if not self._objects:
            self.report({"ERROR"}, "No mesh objects to validate (check the selection / config 'export')")
            return False
        return True

    def _work(self):
        self._results = yield from validation_steps(self._config, self._objects, step_checks(bpy.context.scene))

    def execute(self, context):  # scripts and the redo panel: all in one go, without Steps' wait between steps
        self._timer, self._cancelled = None, False
        if not self._begin(context):
            return {"CANCELLED"}
        for _ in self._work():
            pass
        return self._finish(context)

    def _finish(self, context):
        if self._cancelled or self._results is None:
            self.report({"WARNING"}, "Validation cancelled: the previous results are kept")
            return {"CANCELLED"}
        results = store_results(self._results)
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
        approve_step(objects, scene.asset_validator_step)
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
