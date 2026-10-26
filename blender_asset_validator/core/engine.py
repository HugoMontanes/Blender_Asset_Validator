import json
from pathlib import Path
from typing import Any

import bpy

from .registry import get_checks
from .result import CheckResult, Severity
from .state import set_results
from ..report.generator import generate_report


_CONFIG_DIR = Path(__file__).parent.parent / "config"

# Static list: Blender drops strings returned by a dynamic EnumProperty items callback.
PRESET_ITEMS = [("NONE", "Default", "config/default.json only")] + [
    (path.stem, path.stem.capitalize(), f"config/default.json + presets/{path.name}")
    for path in sorted((_CONFIG_DIR / "presets").glob("*.json"))
]


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_config() -> dict[str, Any]:
    """Default rules with the scene's selected preset (panel dropdown) merged on top."""
    config = _read_json(_CONFIG_DIR / "default.json")
    preset = getattr(bpy.context.scene, "asset_validator_preset", "NONE")
    if preset != "NONE":
        config = _merge_dicts(config, _read_json(_CONFIG_DIR / "presets" / f"{preset}.json"))
    return config


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

    # LOD copies share their source's mesh data — validated/exported through the source
    return [
        obj for obj in objects
        if obj.type == "MESH" and not obj.get("asset_validator_lod", False)
    ]


def run_validation(
    config: dict[str, Any],
    objects: list[bpy.types.Object] | None = None,
) -> list[CheckResult]:
    if objects is None:
        objects = get_validation_objects(config)

    results: list[CheckResult] = []

    for check in get_checks():
        try:
            results.extend(check(objects, config))
        except Exception as e:
            results.append(CheckResult(
                severity=Severity.ERROR,
                message=f"Check '{check.__name__}' raised an exception: {e}",
                check_name=check.__name__,
            ))

    return results


def validate_and_store(
    config: dict[str, Any],
    objects: list[bpy.types.Object] | None = None,
) -> list[CheckResult]:
    """Run all checks, persist the results for the panel, and print the report."""
    results = run_validation(config, objects)
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
