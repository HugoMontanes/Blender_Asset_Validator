from typing import List

import bpy

from ..core.mesh_utils import evaluated_triangle_count
from ..core.result import OperationResult

_MARKER = "asset_validator_lod"
_MODIFIER_NAME = "AssetValidator_LOD_Decimate"


def generate_lods(objects: List[bpy.types.Object], config: dict) -> List[OperationResult]:
    """
    Create decimated LOD copies of each source object.

    Each copy is a linked duplicate (shares the source's mesh data, no extra
    memory) with its own Decimate modifier per `config["lod"]["levels"]`. Not
    applied and not exported anywhere yet — that's a separate, later step.
    """
    results = []
    cfg = config.get("lod", {})
    levels = cfg.get("levels", [])
    if not levels:
        return results

    collection = _get_or_create_collection(cfg.get("collection", "LODs"))

    for obj in objects:
        if obj.get(_MARKER, False):
            continue  # don't generate LODs of LODs

        source_tris = evaluated_triangle_count(obj)  # modifiers applied — matches check_polycount

        for level in levels:
            suffix = level.get("suffix", "_LOD1")
            ratio = level.get("ratio", 0.5)

            lod_obj = obj.copy()  # linked duplicate: shares mesh data, own modifier stack
            lod_obj.name = f"{obj.name}{suffix}"
            lod_obj[_MARKER] = True
            lod_obj["asset_validator_lod_source"] = obj.name

            modifier = lod_obj.modifiers.new(name=_MODIFIER_NAME, type="DECIMATE")
            modifier.decimate_type = "COLLAPSE"
            modifier.ratio = ratio

            collection.objects.link(lod_obj)

            results.append(OperationResult(
                operation_name="generate_lods",
                object_name=lod_obj.name,
                message=f"Generated '{lod_obj.name}' from '{obj.name}' (ratio {ratio:.2f})",
                before_value=source_tris,
                after_value=round(source_tris * ratio),
            ))

    return results


def _get_or_create_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection
