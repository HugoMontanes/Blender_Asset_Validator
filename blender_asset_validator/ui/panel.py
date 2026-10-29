import bpy

from ..core.engine import get_validation_objects, load_config
from ..core.result import Severity
from ..core.state import get_results
from ..core.steps import STEPS, step_approved


_SEVERITY_ICON = {
    Severity.ERROR: "ERROR",
    Severity.WARNING: "QUESTION",
    Severity.INFO: "INFO",
}

# Tools that belong to a guided step (index into STEPS), drawn under its buttons, one list per row
_STEP_TOOLS = {
    2: [[("asset_validator.clean_topology", "MOD_REMESH"), ("asset_validator.retopologize", "MESH_GRID")]],
    3: [[("asset_validator.hard_surface_prep", "MOD_BEVEL")],
        [("asset_validator.auto_unwrap", "UV"), ("asset_validator.set_texel_density", "TEXTURE")],
        [("asset_validator.bake_normals", "IMAGE_DATA"), ("asset_validator.export_bake_pairs", "EXPORT")]],
    4: [[("asset_validator.generate_lods", "DUPLICATE")]],
    5: [[("asset_validator.export", "EXPORT")]],
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
        layout.prop(scene, "asset_validator_engine")
        layout.prop(scene, "asset_validator_preset")
        layout.prop(scene, "asset_validator_guided")
        try:
            config = load_config()
        except (OSError, ValueError) as e:  # usually a hand-edited asset_validator.json
            layout.label(text=f"Config error: {e}", icon="ERROR")
            return
        if scene.asset_validator_guided:
            _draw_guided(layout, scene, config)
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
    layout.operator("asset_validator.hard_surface_prep", icon="MOD_BEVEL")
    uv_row = layout.row(align=True)
    uv_row.operator("asset_validator.auto_unwrap", icon="UV")
    uv_row.operator("asset_validator.set_texel_density", icon="TEXTURE")
    bake_row = layout.row(align=True)
    bake_row.operator("asset_validator.bake_normals", icon="IMAGE_DATA")
    bake_row.operator("asset_validator.export_bake_pairs", icon="EXPORT")
    _draw_heatmap_row(layout)

    if results is None:
        layout.separator()
        layout.label(text="Run Validate Asset to check this scene", icon="INFO")
        return

    errors = _draw_results(layout, results)

    layout.separator()
    export_row = layout.row()
    export_row.enabled = not errors
    export_row.scale_y = 1.3
    export_row.operator("asset_validator.export", icon="EXPORT")

    if errors:
        layout.label(text="Fix errors to unlock export", icon="LOCKED")


def _draw_heatmap_row(layout):
    row = layout.row(align=True)
    row.operator_menu_enum("asset_validator.show_heatmap", "metric", text="Heatmap", icon="COLOR")
    row.operator("asset_validator.clear_heatmap", text="", icon="X")


def _draw_guided(layout, scene, config):
    """Every step as a button (click one to start from it), then the current step's
    findings, fixes and tools, and Approve & Next."""
    current = scene.asset_validator_step
    objects = get_validation_objects(config)
    col = layout.column(align=True)
    for index, (label, _, _) in enumerate(STEPS):
        icon = "CHECKMARK" if step_approved(objects, index) else (
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
    for tools in _STEP_TOOLS.get(current, []):
        tool_row = box.row(align=True)
        for idname, icon in tools:
            tool_row.operator(idname, icon=icon)
    if current in (2, 3):  # topology and UV heatmaps
        _draw_heatmap_row(box)

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
    warnings = [r for r in results if r.severity == Severity.WARNING and r.waived is None]
    accepted = sum(1 for r in results if r.waived is not None)
    accepted_note = f", {accepted} accepted" if accepted else ""

    layout.separator()
    row = layout.row(align=True)
    row.alert = bool(errors)
    if errors:
        row.label(text=f"{len(errors)} error(s)  {len(warnings)} warning(s){accepted_note}", icon="ERROR")
    elif warnings:
        row.label(text=f"Passed  —  {len(warnings)} warning(s){accepted_note}", icon="QUESTION")
    else:
        row.label(text=f"All checks passed{accepted_note}", icon="CHECKMARK")

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
            row.active = r.waived is None
            icon = _SEVERITY_ICON.get(r.severity, "DOT")
            row.label(text=r.message, icon=icon)
            if r.select is not None:
                row.operator("asset_validator.select_result", text="Show", icon="RESTRICT_SELECT_OFF").result_index = idx
            if r.fix is not None:
                fix_op = row.operator("asset_validator.fix_result", text="Fix", icon="TOOL_SETTINGS")
                fix_op.result_index = idx
            if r.severity == Severity.WARNING and r.object_name:
                waive = row.operator("asset_validator.waive_result", text="",
                                     icon="CHECKBOX_HLT" if r.waived is not None else "CHECKBOX_DEHLT")
                waive.result_index = idx

            hint = f"Accepted: {r.waived}" if r.waived is not None else r.fix_hint and f"→ {r.fix_hint}"
            if hint:
                hint_row = col.row()
                hint_row.scale_y = 0.7
                hint_row.active = r.waived is None
                hint_row.label(text=f"   {hint}")

            col.separator(factor=0.5)

    return bool(errors)
