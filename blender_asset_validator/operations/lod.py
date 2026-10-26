from typing import List

import bpy

from ..core.mesh_utils import evaluated_triangle_count

_MARKER = "asset_validator_lod"
_SOURCE = "asset_validator_lod_source"
_LEVEL = "asset_validator_lod_level"
_MODIFIER_NAME = "AssetValidator_LOD_Decimate"


def lods_of(obj: bpy.types.Object) -> List[bpy.types.Object]:
    """LOD copies generated from `obj`, ordered LOD1, LOD2, ..."""
    return sorted(
        (o for o in bpy.data.objects if o.get(_SOURCE) == obj),
        key=lambda o: o.get(_LEVEL, 0),
    )


def generate_lods(objects: List[bpy.types.Object], config: dict) -> List[str]:
    """
    Create decimated LOD copies of each source object, replacing any it already has.

    Each copy is a linked duplicate (shares the source's mesh data, no extra
    memory) with its own Decimate modifier per `config["lod"]["levels"]`.
    Returns one log line per created copy.
    """
    created = []
    cfg = config.get("lod", {})
    levels = cfg.get("levels", [])
    if not levels:
        return created

    collection = _get_or_create_collection(cfg.get("collection", "LODs"))

    for obj in objects:
        if obj.get(_MARKER, False):
            continue  # don't generate LODs of LODs

        for old_lod in lods_of(obj):
            bpy.data.objects.remove(old_lod)  # frees the names so the new copies get them exactly

        source_tris = evaluated_triangle_count(obj)  # modifiers applied — matches check_polycount

        for level_idx, level in enumerate(levels, start=1):
            suffix = level.get("suffix", f"_LOD{level_idx}")
            ratio = level.get("ratio", 0.5)

            lod_obj = obj.copy()  # linked duplicate: shares mesh data, own modifier stack
            lod_obj.name = f"{obj.name}{suffix}"
            lod_obj[_MARKER] = True
            lod_obj[_SOURCE] = obj  # ID pointer, survives renaming the source
            lod_obj[_LEVEL] = level_idx

            modifier = lod_obj.modifiers.new(name=_MODIFIER_NAME, type="DECIMATE")
            modifier.decimate_type = "COLLAPSE"
            modifier.ratio = ratio

            collection.objects.link(lod_obj)

            created.append(
                f"Generated '{lod_obj.name}' from '{obj.name}' "
                f"(ratio {ratio:.2f}, ~{source_tris:,} -> ~{round(source_tris * ratio):,} tris)"
            )

    return created


def _get_or_create_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection
