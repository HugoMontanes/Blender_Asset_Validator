import json
import re
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


def run_validation(
    config: dict[str, Any],
    objects: list[bpy.types.Object] | None = None,
    checks: set[str] | None = None,
) -> list[CheckResult]:
    """`checks`: names of the check functions to run (a guided step's), None for all."""
    if objects is None:
        objects = get_validation_objects(config)

    results: list[CheckResult] = []
    roles = {obj: role(obj, config) for obj in objects}

    for check in get_checks():
        if checks is not None and check.__name__ not in checks:
            continue
        targets = [obj for obj in objects if roles[obj] in check.roles]
        if not targets:
            continue
        try:
            results.extend(check(targets, config))
        except Exception as e:
            results.append(CheckResult(
                severity=Severity.ERROR,
                message=f"Check '{check.__name__}' raised an exception: {e}",
                check_name=check.__name__,
            ))

    apply_waivers(results)
    return results


def validate_and_store(
    config: dict[str, Any],
    objects: list[bpy.types.Object] | None = None,
    checks: set[str] | None = None,
) -> list[CheckResult]:
    """Run the checks, persist the results for the panel, and print the report."""
    results = run_validation(config, objects, checks)
    set_results(results)
    generate_report(results)
    return results


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value

    return merged
