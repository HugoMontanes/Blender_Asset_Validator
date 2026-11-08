import json
import re
import time
import zlib
from pathlib import Path
from typing import Any

import bpy

from .registry import get_checks
from .result import CheckResult, Severity
from .roles import role
from .state import set_results
from .waivers import apply_waivers
from ..report.generator import generate_report


_CONFIG_DIR = Path(__file__).parent.parent / "config"

def _profiles(folder: str, none: tuple) -> list:
    """Static list: Blender drops strings returned by a dynamic items callback. The .blend
    stores the item's number, so it comes from the name: adding a profile can't shift the others."""
    return [(*none, 0)] + [
        (path.stem, path.stem.capitalize(), f"config/{folder}/{path.name}", zlib.crc32(path.stem.encode()) & 0x7FFFFFFF)
        for path in sorted((_CONFIG_DIR / folder).glob("*.json"))
    ]


ENGINE_ITEMS = _profiles("engines", ("NONE", "Custom", "config/default.json rules, no engine conventions"))
PRESET_ITEMS = _profiles("presets", ("NONE", "Default", "No preset on top of the engine's rules"))
PROJECT_CONFIG = "asset_validator.json"  # next to the .blend: the project's own rules, merged last


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_config() -> dict[str, Any]:
    """default.json <- the scene's engine <- its preset (panel dropdowns) <- the
    asset_validator.json next to the .blend, each merged on top of the last."""
    config = _read_json(_CONFIG_DIR / "default.json")
    scene = bpy.context.scene
    for folder, prop in (("engines", "asset_validator_engine"), ("presets", "asset_validator_preset")):
        name = getattr(scene, prop, "NONE")
        if name not in ("NONE", ""):  # "": saved with a profile this install doesn't have
            config = _merge_dicts(config, _read_json(_CONFIG_DIR / folder / f"{name}.json"))
    project = Path(bpy.path.abspath(f"//{PROJECT_CONFIG}"))
    if bpy.data.filepath and project.exists():
        config = _merge_dicts(config, _read_json(project))
    _check_roles(config.get("roles", {}))
    return config


def _check_roles(roles: dict) -> None:
    """Raises ValueError on a role pattern that would fail at match time (hand-edited asset_validator.json)."""
    for key in ("collision", "socket"):
        try:
            pattern = re.compile(roles.get(key) or "")
        except re.error as e:
            raise ValueError(f"roles.{key} is not a valid regex: {e}") from e
        if key == "collision" and roles.get(key) and "owner" not in pattern.groupindex:
            raise ValueError("roles.collision needs a (?P<owner>...) group: the name of the mesh it belongs to")


def get_validation_objects(config: dict[str, Any]) -> list[bpy.types.Object]:
    """The export set. Validate, Fix and Export all use it, so the export gate
    and the result indices always refer to the same objects."""
    context = bpy.context
    export_cfg = config.get("export", {})
    if export_cfg.get("use_selection", True):
        objects = context.selected_objects
    elif export_cfg.get("use_active_collection", False):
        objects = context.view_layer.active_layer_collection.collection.all_objects
    else:
        objects = context.scene.objects

    return [obj for obj in objects if obj.type == "MESH"]


def _invalid_mesh(mesh: bpy.types.Mesh) -> bool:
    """Blender's own Mesh.validate finds something to repair, measured on a copy. A stale edit-mode
    selection index made bmesh.from_mesh crash Blender in every check that reads the mesh."""
    copy = mesh.copy()
    try:
        return copy.validate(clean_customdata=False)
    finally:
        bpy.data.meshes.remove(copy)


def _invalid_mesh_result(obj: bpy.types.Object) -> CheckResult:
    def repair():
        obj.data.validate(clean_customdata=False)
        return "Repaired the mesh data"
    return CheckResult(
        severity=Severity.ERROR,
        message=f"'{obj.name}' has invalid mesh data (a stale selection, duplicate faces...): reading it can crash "
                "Blender, so its other checks wait until it's repaired",
        object_name=obj.name,
        fix_hint="Fix runs Blender's own mesh validation, which repairs it",
        check_name="mesh_data",
        fix=repair,
    )


def run_validation(
    config: dict[str, Any],
    objects: list[bpy.types.Object] | None = None,
    checks: set[str] | None = None,
) -> list[CheckResult]:
    """`checks`: names of the check functions to run (a guided step's), None for all."""
    steps = validation_steps(config, objects, checks)
    try:
        while True:
            next(steps)
    except StopIteration as end:
        return end.value


_STATUS_EVERY = 0.1  # seconds between the status lines validation_steps yields


def validation_steps(
    config: dict[str, Any],
    objects: list[bpy.types.Object] | None = None,
    checks: set[str] | None = None,
):
    """run_validation as a generator, for a modal Validate: yields a status line every _STATUS_EVERY
    seconds, between one object's check and the next, and returns the results."""
    if objects is None:
        objects = get_validation_objects(config)

    invalid_meshes = {m for m in {o.data for o in objects if o.type == "MESH"} if _invalid_mesh(m)}  # once per mesh
    results = [_invalid_mesh_result(obj) for obj in objects if obj.type == "MESH" and obj.data in invalid_meshes]
    invalid = {r.object_name for r in results}
    objects = [obj for obj in objects if obj.name not in invalid]
    roles = {obj: role(obj, config) for obj in objects}

    selected = [c for c in get_checks() if checks is None or c.__name__ in checks]
    last = time.perf_counter()
    for number, check in enumerate(selected, 1):
        targets = [obj for obj in objects if roles[obj] in check.roles]
        for batch in [targets] if check.whole_set else ([obj] for obj in targets):
            if not batch:
                continue
            if time.perf_counter() - last > _STATUS_EVERY:
                yield f"check {number}/{len(selected)}, {check.__name__.removeprefix('check_')}: '{batch[0].name}'"
                last = time.perf_counter()
            try:
                results.extend(check(batch, config))
            except Exception as e:
                results.append(CheckResult(
                    severity=Severity.ERROR,
                    message=f"Check '{check.__name__}' raised an exception"
                            + (f" on '{batch[0].name}'" if len(batch) == 1 else "") + f": {e}",
                    check_name=check.__name__,
                ))

    apply_waivers(results)
    return results


def store_results(results: list[CheckResult]) -> list[CheckResult]:
    """Persist the results for the panel, and print the report."""
    set_results(results)
    generate_report(results)
    return results


def validate_and_store(
    config: dict[str, Any],
    objects: list[bpy.types.Object] | None = None,
    checks: set[str] | None = None,
) -> list[CheckResult]:
    """Run the checks, persist the results for the panel, and print the report."""
    return store_results(run_validation(config, objects, checks))


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value

    return merged
