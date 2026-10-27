import re
from typing import List

import bpy

from ..core.registry import register_check
from ..core.result import CheckResult, Severity
from ..core.roles import collision_owner


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
