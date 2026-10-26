import bpy

from ..core.result import Severity
from ..core.state import get_results
from ..core.steps import STEPS


_SEVERITY_ICON = {
    Severity.ERROR: "ERROR",
    Severity.WARNING: "QUESTION",
    Severity.INFO: "INFO",
}

# Tools that belong to a guided step (index into STEPS), drawn under its buttons
_STEP_TOOLS = {
    2: [("asset_validator.clean_topology", "MOD_REMESH"), ("asset_validator.retopologize", "MESH_GRID")],
    4: [("asset_validator.generate_lods", "DUPLICATE")],
    5: [("asset_validator.export_fbx", "EXPORT")],
}


class ASSET_VALIDATOR_PT_main(bpy.types.Panel):
    bl_label = "Asset Validator"
    bl_idname = "ASSET_VALIDATOR_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Validator"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "asset_validator_preset")
        layout.prop(scene, "asset_validator_guided")
        if scene.asset_validator_guided:
            _draw_guided(layout, scene)
        else:
            _draw_all_at_once(layout)


def _draw_all_at_once(layout):
    results = get_results()

    col = layout.column(align=True)
    col.scale_y = 1.4
    col.operator("asset_validator.validate", icon="CHECKMARK")
    col.operator("asset_validator.fix_all", text="Fix All", icon="MOD_DECIM")

    layout.separator()
    lod_row = layout.row()
    lod_row.scale_y = 1.2
    lod_row.operator("asset_validator.generate_lods", icon="DUPLICATE")
    topo_row = layout.row(align=True)
    topo_row.operator("asset_validator.clean_topology", icon="MOD_REMESH")
    topo_row.operator("asset_validator.retopologize", icon="MESH_GRID")

    if results is None:
        layout.separator()
        layout.label(text="Run Validate Asset to check this scene", icon="INFO")
        return

    errors = _draw_results(layout, results)

    layout.separator()
    export_row = layout.row()
    export_row.enabled = not errors
    export_row.scale_y = 1.3
    export_row.operator("asset_validator.export_fbx", icon="EXPORT")

    if errors:
        layout.label(text="Fix errors to unlock export", icon="LOCKED")


def _draw_guided(layout, scene):
    """Every step as a button (click one to start from it), then the current step's
    findings, fixes and tools, and Approve & Next."""
    current = scene.asset_validator_step
    col = layout.column(align=True)
    for index, (label, _, _) in enumerate(STEPS):
        icon = "CHECKMARK" if scene.asset_validator_approved[index] else (
            "RADIOBUT_ON" if index == current else "RADIOBUT_OFF")
        op = col.operator("asset_validator.go_to_step", text=f"{index + 1}. {label}", icon=icon,
                          depress=index == current)
        op.index = index

    label, description, _ = STEPS[current]
    box = layout.box()
    box.label(text=f"Step {current + 1}: {label}", icon="PLAY")
    box.label(text=description)

    row = box.row(align=True)
    row.scale_y = 1.3
    row.operator("asset_validator.validate", text="Check Step", icon="CHECKMARK")
    row.operator("asset_validator.fix_all", text="Fix Step", icon="MOD_DECIM")
    tools = _STEP_TOOLS.get(current)
    if tools:
        tool_row = box.row(align=True)
        for idname, icon in tools:
            tool_row.operator(idname, icon=icon)

    results = get_results()
    if results is None:
        box.label(text="Click Check Step to see this step's findings", icon="INFO")
        return
    errors = _draw_results(box, results)

    approve = box.row()
    approve.scale_y = 1.4
    approve.enabled = not errors
    last = current == len(STEPS) - 1
    approve.operator("asset_validator.approve_step", text="Approve" if last else "Approve & Next", icon="CHECKMARK")
    if errors:
        box.label(text="Fix this step's errors to approve it", icon="LOCKED")


def _draw_results(layout, results) -> bool:
    """Summary line and the findings grouped by check; True if any is an error."""
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
            if r.select is not None:
                row.operator("asset_validator.select_result", text="Show", icon="RESTRICT_SELECT_OFF").result_index = idx
            if r.fix is not None:
                fix_op = row.operator("asset_validator.fix_result", text="Fix", icon="TOOL_SETTINGS")
                fix_op.result_index = idx

            if r.fix_hint:
                hint_row = col.row()
                hint_row.scale_y = 0.7
                hint_row.label(text=f"   → {r.fix_hint}")

            col.separator(factor=0.5)

    return bool(errors)
