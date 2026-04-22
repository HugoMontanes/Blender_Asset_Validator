from typing import List

import bpy

from ..core.registry import register_check
from ..core.result import CheckResult, Severity


@register_check
def check_materials(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    cfg = config.get("materials", {})
    require_material = cfg.get("require_material", True)
    check_textures = cfg.get("check_textures", True)

    for obj in objects:
        if not obj.material_slots:
            if require_material:
                results.append(CheckResult(
                    severity=Severity.ERROR,
                    message=f"'{obj.name}' has no material slots",
                    object_name=obj.name,
                    fix_hint="Select object → Properties > Material > New",
                    check_name="materials",
                ))
            continue

        for slot_idx, slot in enumerate(obj.material_slots):
            if slot.material is None:
                results.append(CheckResult(
                    severity=Severity.ERROR,
                    message=f"'{obj.name}' slot {slot_idx} is empty",
                    object_name=obj.name,
                    fix_hint="Assign a material or remove the empty slot",
                    check_name="materials",
                ))
                continue

            if not check_textures:
                continue

            mat = slot.material
            if not mat.use_nodes:
                continue

            for node in mat.node_tree.nodes:
                if node.type != "TEX_IMAGE":
                    continue

                if node.image is None:
                    results.append(CheckResult(
                        severity=Severity.WARNING,
                        message=f"'{mat.name}' (on '{obj.name}') has an Image Texture node with no image assigned",
                        object_name=obj.name,
                        fix_hint="Open an image in the Image Texture node",
                        check_name="materials",
                    ))
                elif not node.image.packed_file and not node.image.filepath:
                    results.append(CheckResult(
                        severity=Severity.ERROR,
                        message=f"'{mat.name}' references missing texture '{node.image.name}'",
                        object_name=obj.name,
                        fix_hint="Relink or pack the texture: Image > Pack",
                        check_name="materials",
                    ))

    return results
