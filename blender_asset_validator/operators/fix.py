import bpy

from . import ObjectModeOnly
from ..core.engine import load_config, validate_and_store
from ..core.state import get_results
from ..core.steps import step_checks
from ..ui.redraw import redraw_view3d

_STALE = "Scene changed since validation (undo or deleted object) — re-run Validate"


class ASSET_VALIDATOR_OT_fix_result(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.fix_result"
    bl_label = "Fix"
    bl_description = "Apply the automatic fix for this issue"
    bl_options = {"REGISTER", "UNDO"}

    result_index: bpy.props.IntProperty()

    def execute(self, context):
        results = get_results()
        if not results or self.result_index >= len(results):
            self.report({"ERROR"}, "Result no longer available — re-run Validate")
            return {"CANCELLED"}

        result = results[self.result_index]
        if result.fix is None:
            self.report({"WARNING"}, "No automatic fix for this issue")
            return {"CANCELLED"}

        try:
            message = result.fix()
        except ReferenceError:  # the fix's bpy Object was freed by undo or deletion
            self.report({"ERROR"}, _STALE)
            return {"CANCELLED"}

        validate_and_store(load_config(), checks=step_checks(context.scene))
        redraw_view3d(context)

        self.report({"INFO"}, message or "Fix applied")
        return {"FINISHED"}


class ASSET_VALIDATOR_OT_select_result(bpy.types.Operator):
    bl_idname = "asset_validator.select_result"
    bl_label = "Show"
    bl_description = "Open the object in Edit Mode with the offending elements selected"
    bl_options = {"REGISTER", "UNDO"}

    result_index: bpy.props.IntProperty()

    def execute(self, context):
        results = get_results()
        if not results or self.result_index >= len(results) or results[self.result_index].select is None:
            self.report({"ERROR"}, "Result no longer available — re-run Validate")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")  # flushes Edit Mode changes before reading the mesh
        try:
            results[self.result_index].select()
        except ReferenceError:
            self.report({"ERROR"}, _STALE)
            return {"CANCELLED"}
        return {"FINISHED"}


class ASSET_VALIDATOR_OT_fix_all(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.fix_all"
    bl_label = "Fix All"
    bl_description = "Apply every automatic fix available for the current results"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        results = get_results()
        if not results:
            self.report({"WARNING"}, "Nothing to fix — run Validate first")
            return {"CANCELLED"}

        fixed = stale = 0
        for result in results:
            if result.fix is None:
                continue
            # Keep going on a stale result: returning CANCELLED after earlier fixes
            # already changed data would leave those changes without an undo step.
            try:
                if result.fix() is not None:
                    fixed += 1
            except ReferenceError:
                stale += 1

        validate_and_store(load_config(), checks=step_checks(context.scene))
        redraw_view3d(context)

        if stale:
            self.report({"WARNING"}, f"Applied {fixed} fix(es), skipped {stale}: {_STALE}")
        elif fixed:
            self.report({"INFO"}, f"Applied {fixed} fix(es)")
        else:
            self.report({"INFO"}, "No automatic fixes available")
        return {"FINISHED"}
