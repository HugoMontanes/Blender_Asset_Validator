from typing import List

import bmesh
import bpy

from ..core.mesh_utils import bake_mesh
from ..core.steps import APPROVED
from .topology import Surface, topology_settings, transfer_normals, clean_bmesh, feature_verts

_MARKER = "asset_validator_lod"
_SOURCE = "asset_validator_lod_source"
_LEVEL = "asset_validator_lod_level"
_PROTECT_GROUP = "AssetValidator_LOD_Protect"
_PROTECT_FACTOR = 10.0  # collapse cost added to protected edges
# Not 0: the collapse decimator never collapses an edge whose two weights are both ~0,
# which would turn the soft protection into a hard block and miss the triangle target
_PROTECTED_WEIGHT = 0.001


def lods_of(obj: bpy.types.Object) -> List[bpy.types.Object]:
    """LOD copies generated from `obj`, ordered LOD1, LOD2, ..."""
    return sorted(
        (o for o in bpy.data.objects if o.get(_SOURCE) == obj),
        key=lambda o: o.get(_LEVEL, 0),
    )


def generate_lods(objects: List[bpy.types.Object], config: dict) -> List[str]:
    """
    Bake LOD meshes of each source object, replacing any it already has.

    Each level is built from the previous one (progressive, less popping):
    planar dissolve -> feature-weighted collapse to the target triangle count
    (ratio of the source's evaluated tris) -> triangulate, or Clean Topology if
    `lod.clean_topology` -> normals transferred from the source.
    Returns one log line per created copy.
    """
    created = []
    cfg = config.get("lod", {})
    levels = cfg.get("levels", [])
    if not levels:
        return created

    collection = _get_or_create_collection(cfg.get("collection", "LODs"))
    settings = topology_settings(config)
    clean = settings if cfg.get("clean_topology", False) else None

    for obj in objects:
        if obj.get(_MARKER, False):
            continue  # don't generate LODs of LODs

        for old_lod in lods_of(obj):
            old_mesh = old_lod.data
            bpy.data.objects.remove(old_lod)  # frees the names so the new copies get them exactly
            if old_mesh is not None and old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)

        base = mesh = bake_mesh(obj)  # modifiers applied — matches check_polycount and the export
        source_tris = _tri_count(base)
        smooth = any(p.use_smooth for p in base.polygons)
        surface = Surface(base) if clean else None

        for level_idx, level in enumerate(levels, start=1):
            suffix = level.get("suffix", f"_LOD{level_idx}")
            target = max(4, round(source_tris * level.get("ratio", 0.5)))
            mesh = _reduce(mesh, target, obj if smooth else None, surface, clean, settings["flat"])

            # ponytail: modifiers are baked in, so rigged meshes get a static LOD;
            # rebuild from obj.data and re-add the Armature modifier if skinned assets need LODs
            lod_obj = obj.copy()  # keeps transform, parent and custom props
            lod_obj.modifiers.clear()
            lod_obj.data = mesh
            lod_obj.name = mesh.name = f"{obj.name}{suffix}"
            lod_obj[_MARKER] = True
            lod_obj[_SOURCE] = obj  # ID pointer, survives renaming the source
            lod_obj[_LEVEL] = level_idx
            lod_obj.pop(APPROVED, None)  # copied from the source: the decimated mesh passed no step yet
            group = lod_obj.vertex_groups.get(_PROTECT_GROUP)
            if group is not None:
                lod_obj.vertex_groups.remove(group)
            collection.objects.link(lod_obj)  # obj.copy() isn't in any collection yet

            created.append(
                f"Generated '{lod_obj.name}' from '{obj.name}' "
                f"({source_tris:,} -> {_tri_count(mesh):,} tris, target {target:,})"
            )
        bpy.data.meshes.remove(base)

    return created


def _reduce(mesh: bpy.types.Mesh, target_tris: int, normals_source, surface, clean, flat_angle: float) -> bpy.types.Mesh:
    """New mesh: `mesh` reduced to ~target_tris without breaking its borders, seams or hard edges."""
    tmp = bpy.data.objects.new("_AssetValidator_LOD_tmp", mesh.copy())
    bpy.context.scene.collection.objects.link(tmp)
    try:
        planar = tmp.modifiers.new("planar", "DECIMATE")
        planar.decimate_type = "DISSOLVE"
        planar.angle_limit = flat_angle  # only truly flat regions — never changes the silhouette
        planar.delimit = {"NORMAL", "MATERIAL", "SEAM", "SHARP", "UV"}
        _bake_into(tmp)

        tris = _tri_count(tmp.data)
        if tris > target_tris:
            _write_protect_group(tmp)
            collapse = tmp.modifiers.new("collapse", "DECIMATE")
            collapse.decimate_type = "COLLAPSE"
            collapse.ratio = target_tris / tris
            collapse.vertex_group = _PROTECT_GROUP
            collapse.vertex_group_factor = _PROTECT_FACTOR

        if clean is None:
            tri = tmp.modifiers.new("triangulate", "TRIANGULATE")
            tri.quad_method = "BEAUTY"
            tri.ngon_method = "BEAUTY"
        _bake_into(tmp)

        if clean is not None:
            bm = bmesh.new()
            bm.from_mesh(tmp.data)
            clean_bmesh(bm, surface, clean)  # relaxes onto the full-res source, not the previous LOD
            bm.to_mesh(tmp.data)
            bm.free()

        if normals_source is not None:
            transfer_normals(tmp.data, normals_source)
        return tmp.data
    finally:
        bpy.data.objects.remove(tmp)


def _write_protect_group(obj: bpy.types.Object) -> None:
    """Low weight on the shape-defining vertices (topology.feature_verts), 1 elsewhere.
    Collapse makes low-weight edges costlier to remove."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    protected = {v.index for v in feature_verts(bm)}
    vert_count = len(bm.verts)
    bm.free()

    group = obj.vertex_groups.get(_PROTECT_GROUP) or obj.vertex_groups.new(name=_PROTECT_GROUP)
    group.add([i for i in range(vert_count) if i not in protected], 1.0, "REPLACE")
    group.add(list(protected), _PROTECTED_WEIGHT, "REPLACE")


def _bake_into(obj: bpy.types.Object) -> None:
    old = obj.data
    obj.data = bake_mesh(obj)
    obj.modifiers.clear()
    bpy.data.meshes.remove(old)


def _tri_count(mesh: bpy.types.Mesh) -> int:
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


def _get_or_create_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection
