"""What each object is to the target engine, from the name patterns of the
engine profile (config "roles"): an asset, a generated LOD, a collision mesh
or a socket. Checks run per role, and an asset is exported with its parts."""
import re
from typing import List, Optional

import bpy


def role(obj: bpy.types.Object, config: dict) -> str:
    if obj.get("asset_validator_lod", False):
        return "lod"
    if obj.type == "MESH" and collision_owner(obj, config) is not None:
        return "collision"
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


def renamed_collision(obj: bpy.types.Object, owner: str, config: dict) -> str:
    """obj's name with its owner part replaced: UCX_Chair_01 -> UCX_Chair_LOD0_01."""
    start = _collision_match(obj.name, config).start("owner")
    return obj.name[:start] + owner + obj.name[start + len(collision_owner(obj, config)):]


def _collision_match(name: str, config: dict):
    pattern = config.get("roles", {}).get("collision")
    return re.match(pattern, name) if pattern else None
