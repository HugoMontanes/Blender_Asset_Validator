import json
from pathlib import Path
from typing import Any

import bpy

from .registry import get_checks
from .result import CheckResult, Severity
from .state import set_results
from ..report.generator import generate_report


_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.json"


def load_config(path: Path = _CONFIG_PATH) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_preset(preset_name: str) -> dict[str, Any]:
    preset_path = Path(__file__).parent.parent / "config" / "presets" / f"{preset_name}.json"
    base = load_config()
    if preset_path.exists():
        with open(preset_path, "r", encoding="utf-8") as file:
            preset = json.load(file)
        base = _merge_dicts(base, preset)
    return base


def _default_mesh_objects() -> list[bpy.types.Object]:
    # LOD copies (operations/lod.py) share their source's mesh data — they're
    # validated/optimized through the source, not counted separately here.
    return [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.get("asset_validator_lod", False)
    ]


def run_validation(
    config: dict[str, Any],
    objects: list[bpy.types.Object] | None = None,
) -> list[CheckResult]:
    if objects is None:
        objects = _default_mesh_objects()

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
