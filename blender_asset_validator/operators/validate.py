import bpy

from ..core.engine import load_config, run_validation
from ..core.state import set_results
from ..report.generator import generate_report


class ASSET_VALIDATOR_OT_validate(bpy.types.Operator):
    bl_idname = "asset_validator.validate"
    bl_label = "Validate Asset"
    bl_description = "Run all pipeline checks on mesh objects in the scene"

    def execute(self, context):
        config = load_config()
        results = run_validation(config)
        set_results(results)
        generate_report(results)

        errors = sum(1 for r in results if r.severity.value == "ERROR")
        warnings = sum(1 for r in results if r.severity.value == "WARNING")

        if errors:
            self.report({"WARNING"}, f"Validation failed — {errors} error(s), {warnings} warning(s)")
        else:
            self.report({"INFO"}, f"Validation passed — {warnings} warning(s)")

        # Force N-panel redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()

        return {"FINISHED"}
