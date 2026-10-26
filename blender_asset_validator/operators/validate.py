import bpy

from . import ObjectModeOnly
from ..core.engine import get_validation_objects, load_config, validate_and_store
from ..core.result import Severity
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

        results = validate_and_store(config, objects)

        errors = sum(1 for r in results if r.severity == Severity.ERROR)
        warnings = sum(1 for r in results if r.severity == Severity.WARNING)

        if errors:
            self.report({"WARNING"}, f"Validation failed — {errors} error(s), {warnings} warning(s)")
        else:
            self.report({"INFO"}, f"Validation passed — {warnings} warning(s)")

        redraw_view3d(context)
        return {"FINISHED"}
