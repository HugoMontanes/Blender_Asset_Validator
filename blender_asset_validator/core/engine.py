import json
import os
from pathlib import Path
from typing import Dict, Any, List

import bpy

from .registry import get_checks
from .result import CheckResult, Severity


_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.json"


def load_config(path: Path = _CONFIG_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_preset(preset_name: str) -> Dict[str, Any]:
    preset_path = Path(__file__).parent.parent / "config" / "presets" / f"{preset_name}.json"
    base = load_config()
    if preset_path.exists():
        with open(preset_path, "r", encoding="utf-8") as f:
            preset = json.load(f)
        base.update(preset)
    return base


def run_validation(config: Dict[str, Any]) -> List[CheckResult]:
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    results: List[CheckResult] = []

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
