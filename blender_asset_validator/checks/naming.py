import re
from typing import List

import bpy

from ..core.registry import register_check
from ..core.result import CheckResult, Severity
from ..core.roles import collision_owner, high_owner, role


@register_check
def check_naming(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    pattern = config.get("naming", {}).get("pattern", r"^[A-Z][a-zA-Z0-9_]+$")
    description = config.get("naming", {}).get("description", pattern)
    compiled = re.compile(pattern)

    for obj in objects:
        if not compiled.match(obj.name):
            results.append(CheckResult(
                severity=Severity.ERROR,
                message=f"'{obj.name}' violates naming convention",
                object_name=obj.name,
                fix_hint=f"Rename to match: {description}",
                check_name="naming",
            ))

        if obj.data and not compiled.match(obj.data.name):
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"Mesh data '{obj.data.name}' on '{obj.name}' violates naming convention",
                object_name=obj.name,
                fix_hint=f"Rename mesh data to match: {description}",
                check_name="naming",
            ))

    return results


@register_check(roles=("collision",))
def check_collisions(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    """A collision is exported with the mesh its name points at; with no such
    mesh it's left out, and engines skip a misnamed one without a word."""
    results = []
    for obj in objects:
        owner = collision_owner(obj, config)
        target = bpy.context.scene.objects.get(owner)
        if target is None or target.type != "MESH":
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"Collision '{obj.name}' is named after '{owner}', but the scene has no mesh called that: it won't be exported",
                object_name=obj.name,
                fix_hint=f"Rename it after its mesh (pattern: {config.get('roles', {}).get('collision')})",
                check_name="collisions",
            ))
    return results


@register_check(roles=("high",))
def check_bake_pairs(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    """A high-poly mesh skips the checks and the export; with no low to bake onto it's
    a typo, or an asset whose name happens to end in the suffix."""
    results = []
    cfg = config.get("bake", {})
    low_suffix, high_suffix = cfg.get("low_suffix", "_low"), cfg.get("high_suffix", "_high")
    for obj in objects:
        base = high_owner(obj.name, config)
        # The lows highs_of pairs it with: Chair_low_high goes with Chair_low_low, not with Chair_low
        names = (base + low_suffix,) if not low_suffix or base.endswith(low_suffix) else (base, base + low_suffix)
        lows = [o for o in map(bpy.context.scene.objects.get, names)
                if o is not None and o.type == "MESH" and role(o, config) == "asset"]
        if len(lows) > 1:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' bakes onto both '{base}' and '{base}{low_suffix}': they'd share the "
                        f"normal map {base}_N, and Export Bake Pairs can't name both {base}{low_suffix}",
                object_name=obj.name,
                fix_hint="Rename one of the two low-poly meshes",
                check_name="bake_pairs",
            ))
        elif not lows:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' is a high-poly mesh (its name has {high_suffix}), but there's no "
                        f"{' or '.join(repr(n) for n in names)} to bake onto: it won't be checked or exported",
                object_name=obj.name,
                fix_hint=f"Rename it after its low-poly, or drop {high_suffix} from the name if it's an asset",
                check_name="bake_pairs",
            ))
    return results
