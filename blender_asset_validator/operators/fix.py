import bpy

from . import ObjectModeOnly
from ..core.engine import load_config, validate_and_store
from ..core.result import Severity
from ..core.state import get_results
from ..core.steps import step_checks
from ..core.waivers import apply_waivers, set_waiver
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


class ASSET_VALIDATOR_OT_waive_result(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.waive_result"
    bl_label = "Accept Warning"
    bl_description = "Accept this warning for this asset, with a reason stored on the object; click again to withdraw it"
    bl_options = {"REGISTER", "UNDO"}

    result_index: bpy.props.IntProperty(options={"HIDDEN"})
    reason: bpy.props.StringProperty(name="Reason", description="Why this warning is fine for this asset", options={"SKIP_SAVE"})

    def invoke(self, context, event):
        results = get_results()
        if results and self.result_index < len(results):
            apply_waivers(results)  # an undo since validation may have changed what the object stores
            if results[self.result_index].waived is None:
                return context.window_manager.invoke_props_dialog(self)
        return self.execute(context)

    def execute(self, context):
        results = get_results()
        if not results or self.result_index >= len(results):
            self.report({"ERROR"}, "Result no longer available — re-run Validate")
            return {"CANCELLED"}
        apply_waivers(results)  # the redo panel runs this after an undo the cached results didn't see
        result = results[self.result_index]
        if result.severity != Severity.WARNING or not result.object_name:
            self.report({"ERROR"}, "Only warnings about an object can be accepted; errors must be fixed")
            return {"CANCELLED"}
        if result.waived is None and not self.reason.strip():
            self.report({"ERROR"}, "Give a reason for accepting it")
            return {"CANCELLED"}
        try:
            set_waiver(result, None if result.waived is not None else self.reason.strip())
        except KeyError:  # the object was renamed or deleted since validation
            self.report({"ERROR"}, _STALE)
            return {"CANCELLED"}

        apply_waivers(results)  # only the acceptance changed: no checks to re-run
        redraw_view3d(context)
        return {"FINISHED"}
