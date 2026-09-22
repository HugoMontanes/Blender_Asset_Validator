import bpy

from ..core.engine import load_config, validate_and_store
from ..core.state import get_results
from ..ui.redraw import redraw_view3d


class ASSET_VALIDATOR_OT_fix_result(bpy.types.Operator):
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

        message = result.fix()
        validate_and_store(load_config())
        redraw_view3d(context)

        self.report({"INFO"}, message or "Fix applied")
        return {"FINISHED"}


class ASSET_VALIDATOR_OT_fix_all(bpy.types.Operator):
    bl_idname = "asset_validator.fix_all"
    bl_label = "Fix All"
    bl_description = "Apply every automatic fix available for the current results"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        results = get_results()
        if not results:
            self.report({"WARNING"}, "Nothing to fix — run Validate first")
            return {"CANCELLED"}

        fixed = 0
        for result in results:
            if result.fix is not None and result.fix() is not None:
                fixed += 1

        validate_and_store(load_config())
        redraw_view3d(context)

        if fixed:
            self.report({"INFO"}, f"Applied {fixed} fix(es)")
        else:
            self.report({"INFO"}, "No automatic fixes available")
        return {"FINISHED"}
