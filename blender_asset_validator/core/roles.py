"""What each object is to the target engine, from the name patterns of the
engine profile (config "roles"): an asset, a generated LOD, a collision mesh,
a socket or a high-poly bake source (config "bake"). Checks run per role, and
an asset is exported with its parts."""
import re
from typing import List, Optional

import bpy


LOD_MARKER = "asset_validator_lod"
LOD_SOURCE = "asset_validator_lod_source"  # on a LOD: its source object
LOD_LEVEL = "asset_validator_lod_level"
LOD_SLOT = "asset_validator_lod_object_{}"  # on the source, per level: the LOD object generate_lods made


def is_lod(obj: bpy.types.Object) -> bool:
    """A LOD generate_lods made, renamed or not, but not a copy of one: a copy keeps its properties, and
    regenerating the LODs deleted the user's copies with them. The source points back at the one it made
    (Blender doesn't repoint that at a copy); LODs from before the back pointer count as made."""
    if not obj.get(LOD_MARKER, False):
        return False
    source, slot = obj.get(LOD_SOURCE), LOD_SLOT.format(obj.get(LOD_LEVEL, 0))
    return source is None or slot not in source or source[slot] == obj


def lod_source(obj: bpy.types.Object):
    """The source object of a LOD generate_lods made, else None."""
    return obj.get(LOD_SOURCE) if is_lod(obj) else None


def role(obj: bpy.types.Object, config: dict) -> str:
    if is_lod(obj):
        return "lod"
    if obj.type == "MESH" and collision_owner(obj, config) is not None:
        return "collision"
    if obj.type == "MESH" and high_owner(obj.name, config) is not None:
        return "high"
    pattern = config.get("roles", {}).get("socket")
    if obj.type == "EMPTY" and pattern and re.match(pattern, obj.name):
        return "socket"
    return "asset"


def collision_owner(obj: bpy.types.Object, config: dict) -> Optional[str]:
    """Name of the mesh a collision object belongs to, None if it isn't one."""
    match = _collision_match(obj.name, config)
    if match is None:
        return None
    # The _NN index is optional, so UCX_Pipe_90 may be Pipe's or Pipe_90's: a mesh with the whole name wins
    whole = obj.name[match.start("owner"):]
    target = bpy.context.scene.objects.get(whole)
    return whole if target is not None and target is not obj and target.type == "MESH" else match.group("owner")


def collisions_of(obj: bpy.types.Object, config: dict) -> List[bpy.types.Object]:
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and collision_owner(o, config) == obj.name]


def sockets_of(obj: bpy.types.Object, config: dict) -> List[bpy.types.Object]:
    return [c for c in obj.children if role(c, config) == "socket"]


def high_owner(name: str, config: dict) -> Optional[str]:
    """Base name of the low a high-poly mesh bakes onto, None if it isn't one. Substance Painter's
    match by mesh name: Chair_high, Chair_high_bolts -> Chair, case-sensitive. Chair_high.001
    too: Blender's duplicates (Export Bake Pairs writes it Chair_high_001)."""
    suffix = config.get("bake", {}).get("high_suffix", "_high")
    match = re.match(f"(.+){re.escape(suffix)}([._].*)?$", name) if suffix else None
    return match.group(1) if match else None


def bake_base(obj: bpy.types.Object, config: dict) -> str:
    """A low's name without its low suffix (Chair_low -> Chair): what its highs are named after."""
    suffix = config.get("bake", {}).get("low_suffix", "_low")
    return obj.name[:-len(suffix)] if suffix and obj.name.endswith(suffix) else obj.name


def highs_of(obj: bpy.types.Object, config: dict) -> List[bpy.types.Object]:
    base = bake_base(obj, config)
    return [o for o in bpy.context.scene.objects
            if o.type == "MESH" and high_owner(o.name, config) == base and role(o, config) == "high"]


def renamed_collision(obj: bpy.types.Object, owner: str, config: dict) -> str:
    """obj's name with its owner part replaced: UCX_Chair_01 -> UCX_Chair_LOD0_01."""
    start = _collision_match(obj.name, config).start("owner")
    return obj.name[:start] + owner + obj.name[start + len(collision_owner(obj, config)):]


def _collision_match(name: str, config: dict):
    pattern = config.get("roles", {}).get("collision")
    return re.match(pattern, name) if pattern else None
