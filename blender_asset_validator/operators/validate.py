import bpy

from ..core.engine import load_config, validate_and_store
from ..ui.redraw import redraw_view3d


class ASSET_VALIDATOR_OT_validate(bpy.types.Operator):
    bl_idname = "asset_validator.validate"
    bl_label = "Validate Asset"
    bl_description = "Run all pipeline checks on mesh objects in the scene"

    def execute(self, context):
        config = load_config()
        results = validate_and_store(config)

        errors = sum(1 for r in results if r.severity.value == "ERROR")
        warnings = sum(1 for r in results if r.severity.value == "WARNING")

        if errors:
            self.report({"WARNING"}, f"Validation failed — {errors} error(s), {warnings} warning(s)")
        else:
            self.report({"INFO"}, f"Validation passed — {warnings} warning(s)")

        redraw_view3d(context)
        return {"FINISHED"}
