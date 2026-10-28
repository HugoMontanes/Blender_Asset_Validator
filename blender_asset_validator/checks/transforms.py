from typing import List

import bpy

from ..core.registry import register_check
from ..core.result import CheckResult, Severity
from ..core.roles import role
from ..operations.lod import lods_of


@register_check(roles=("asset", "lod", "collision"))  # a collision must sit where its mesh does
def check_transforms(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    cfg = config.get("transforms", {})
    loc_thr = cfg.get("location_threshold", 0.001)
    rot_thr = cfg.get("rotation_threshold", 0.001)
    sca_thr = cfg.get("scale_threshold", 0.001)
    one_file_each = config.get("export", {}).get("individual_files", True)
    lod_groups = config.get("lod", {}).get("export_target", "none") == "unreal"

    for obj in objects:
        # LODs and collisions ride in their asset's file. Any other parent link survives only in one
        # shared file that holds the parent too, and not where an Unreal LOD group takes its place
        why = None
        if obj.parent is not None and role(obj, config) == "asset":
            if one_file_each:
                why = "each asset goes to its own file"
            elif obj.parent not in objects:
                why = f"'{obj.parent.name}' isn't exported with it"
            elif lod_groups and lods_of(obj):
                why = "its Unreal LOD group takes the parent's place"
        if why:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' is parented to '{obj.parent.name}', but the export drops that link: {why}",
                object_name=obj.name,
                fix_hint="Join the parts into one mesh (Ctrl+J) or Clear Parent and Keep Transform (Alt+P); "
                         "or accept this and rebuild the hierarchy in the engine",
                check_name="transforms",
            ))

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
