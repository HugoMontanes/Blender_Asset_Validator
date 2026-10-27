"""Warnings an artist accepted, with the reason, stored on the object so they
travel with the .blend. Errors can't be accepted: they block the export."""
import hashlib
import re
from typing import List, Optional

import bpy

from .result import CheckResult, Severity

_PROP = "asset_validator_waivers"


def waiver_key(result: CheckResult) -> str:
    # ponytail: keyed on the message with the object name and the numbers blanked, so a waiver
    # survives the counts changing; give CheckResult a stable code if two findings ever read alike
    text = result.message.replace(f"'{result.object_name}'", "'*'")
    text = re.sub(r"\d[\d,.]*", "#", f"{result.check_name}:{text}")
    return hashlib.md5(text.encode()).hexdigest()[:16]  # IDProperty keys are capped at 63 bytes


def set_waiver(result: CheckResult, reason: Optional[str]) -> None:
    """Accept `result` for `reason`, or withdraw the acceptance with None."""
    obj = bpy.data.objects[result.object_name]
    waivers = dict(obj.get(_PROP, {}))
    if reason:
        waivers[waiver_key(result)] = reason
    else:
        waivers.pop(waiver_key(result), None)
    obj[_PROP] = waivers


def apply_waivers(results: List[CheckResult]) -> None:
    for result in results:
        obj = bpy.data.objects.get(result.object_name) if result.object_name else None
        if obj is not None and result.severity == Severity.WARNING:
            result.waived = obj.get(_PROP, {}).get(waiver_key(result))
