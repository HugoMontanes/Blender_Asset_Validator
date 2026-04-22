from typing import List

import bpy

from ..core.registry import register_check
from ..core.result import CheckResult, Severity


@register_check
def check_transforms(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    cfg = config.get("transforms", {})
    loc_thr = cfg.get("location_threshold", 0.001)
    rot_thr = cfg.get("rotation_threshold", 0.001)
    sca_thr = cfg.get("scale_threshold", 0.001)

    for obj in objects:
        if cfg.get("check_location", True):
            loc = obj.location
            if any(abs(v) > loc_thr for v in loc):
                rounded = tuple(round(v, 4) for v in loc)
                results.append(CheckResult(
                    severity=Severity.ERROR,
                    message=f"'{obj.name}' has unapplied location {rounded}",
                    object_name=obj.name,
                    fix_hint="Object > Apply > Location  (Ctrl+A → Location)",
                    check_name="transforms",
                ))

        if cfg.get("check_rotation", True):
            if obj.rotation_mode == "QUATERNION":
                q = obj.rotation_quaternion
                not_identity = abs(q.w - 1.0) > rot_thr or any(abs(v) > rot_thr for v in (q.x, q.y, q.z))
            elif obj.rotation_mode == "AXIS_ANGLE":
                aa = obj.rotation_axis_angle
                not_identity = abs(aa[0]) > rot_thr
            else:
                rot = obj.rotation_euler
                not_identity = any(abs(v) > rot_thr for v in rot)

            if not_identity:
                results.append(CheckResult(
                    severity=Severity.ERROR,
                    message=f"'{obj.name}' has unapplied rotation",
                    object_name=obj.name,
                    fix_hint="Object > Apply > Rotation  (Ctrl+A → Rotation)",
                    check_name="transforms",
                ))

        if cfg.get("check_scale", True):
            scale = obj.scale
            if any(abs(v - 1.0) > sca_thr for v in scale):
                rounded = tuple(round(v, 4) for v in scale)
                results.append(CheckResult(
                    severity=Severity.ERROR,
                    message=f"'{obj.name}' has unapplied scale {rounded}",
                    object_name=obj.name,
                    fix_hint="Object > Apply > Scale  (Ctrl+A → Scale)",
                    check_name="transforms",
                ))

    return results
