import bpy

from ..core.result import Severity
from ..core.state import get_results


_SEVERITY_ICON = {
    Severity.ERROR: "ERROR",
    Severity.WARNING: "QUESTION",
    Severity.INFO: "INFO",
}


class ASSET_VALIDATOR_PT_main(bpy.types.Panel):
    bl_label = "Asset Validator"
    bl_idname = "ASSET_VALIDATOR_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Validator"

    def draw(self, context):
        layout = self.layout
        results = get_results()

        layout.prop(context.scene, "asset_validator_preset")

        col = layout.column(align=True)
        col.scale_y = 1.4
        col.operator("asset_validator.validate", icon="CHECKMARK")
        col.operator("asset_validator.fix_all", text="Fix All", icon="MOD_DECIM")

        layout.separator()
        lod_row = layout.row()
        lod_row.scale_y = 1.2
        lod_row.operator("asset_validator.generate_lods", icon="DUPLICATE")

        if results is None:
            layout.separator()
            layout.label(text="Run Validate Asset to check this scene", icon="INFO")
            return

        errors = [r for r in results if r.severity == Severity.ERROR]
        warnings = [r for r in results if r.severity == Severity.WARNING]

        layout.separator()
        row = layout.row(align=True)
        row.alert = bool(errors)
        if errors:
            row.label(text=f"{len(errors)} error(s)  {len(warnings)} warning(s)", icon="ERROR")
        elif warnings:
            row.label(text=f"Passed  —  {len(warnings)} warning(s)", icon="QUESTION")
        else:
            row.label(text="All checks passed", icon="CHECKMARK")

        if results:
            layout.separator()
            box = layout.box()
            col = box.column(align=True)

            current_check = None
            for idx, r in enumerate(results):
                if r.check_name != current_check:
                    current_check = r.check_name
                    sub = col.row()
                    sub.label(text=r.check_name.upper(), icon="PREFERENCES")
                    col.separator(factor=0.3)

                row = col.row(align=True)
                row.alert = r.severity == Severity.ERROR
                icon = _SEVERITY_ICON.get(r.severity, "DOT")
                row.label(text=r.message, icon=icon)
                if r.fix is not None:
                    fix_op = row.operator("asset_validator.fix_result", text="Fix", icon="TOOL_SETTINGS")
                    fix_op.result_index = idx

                if r.fix_hint:
                    hint_row = col.row()
                    hint_row.scale_y = 0.7
                    hint_row.label(text=f"   → {r.fix_hint}")

                col.separator(factor=0.5)

        layout.separator()
        export_row = layout.row()
        export_row.enabled = not bool(errors)
        export_row.scale_y = 1.3
        export_row.operator("asset_validator.export_fbx", icon="EXPORT")

        if errors:
            layout.label(text="Fix errors to unlock export", icon="LOCKED")
