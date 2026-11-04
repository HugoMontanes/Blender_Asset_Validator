from typing import List

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..core.mesh_utils import bake_mesh, read_array, to_world
from ..core.roles import LOD_LEVEL as _LEVEL, LOD_MARKER as _MARKER, LOD_SLOT, LOD_SOURCE as _SOURCE, is_lod
from ..core.steps import APPROVED
from .cleanup import delete_loose, fix_normals
from .topology import Surface, topology_settings, transfer_normals, clean_bmesh, feature_verts

_PROTECT_GROUP = "AssetValidator_LOD_Protect"
_PROTECT_FACTOR = 10.0  # collapse cost added to protected edges
# Not 0: the collapse decimator never collapses an edge whose two weights are both ~0,
# which would turn the soft protection into a hard block and miss the triangle target
_PROTECTED_WEIGHT = 0.001


def lods_of(obj: bpy.types.Object) -> List[bpy.types.Object]:
    """LOD copies generated from `obj`, ordered LOD1, LOD2, ..."""
    return sorted(
        (o for o in bpy.data.objects if o.get(_SOURCE) == obj and is_lod(o)),
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
    max_deviation = cfg.get("max_deviation", 1.0)

    for obj in objects:
        if is_lod(obj):
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
        base_shape = _shape(base, obj.matrix_world)

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
            for key in [k for k in lod_obj.keys() if k == APPROVED or k.startswith(LOD_SLOT.format(""))]:
                del lod_obj[key]  # copied from the source: its step approvals and its pointers to its LODs
            obj[LOD_SLOT.format(level_idx)] = lod_obj
            group = lod_obj.vertex_groups.get(_PROTECT_GROUP)
            if group is not None:
                lod_obj.vertex_groups.remove(group)
            collection.objects.link(lod_obj)  # obj.copy() isn't in any collection yet

            line = f"Generated '{lod_obj.name}' from '{obj.name}' ({source_tris:,} -> {_tri_count(mesh):,} tris, target {target:,})"
            stray = _stray(base_shape, _shape(mesh, obj.matrix_world)) if base_shape else 0.0
            if stray > max_deviation:
                lod_obj[STRAY] = round(stray, 2)
                line += f": strays {stray:.1f} % of its size from the source (limit {max_deviation:g} %), give it a higher ratio"
            created.append(line)
        bpy.data.meshes.remove(base)

    return created


def _reduce(mesh: bpy.types.Mesh, target_tris: int, normals_source, surface, clean, flat_angle: float) -> bpy.types.Mesh:
    """New mesh: `mesh` reduced to ~target_tris without breaking its borders, seams or UV/material borders."""
    tmp = bpy.data.objects.new("_AssetValidator_LOD_tmp", mesh.copy())
    bpy.context.scene.collection.objects.link(tmp)
    try:
        # Hard edges (sharp, or split custom normals) stay out of the decimation: kept as borders and
        # protected, they folded a LOD's mesh into edges with 3+ faces (20 on a pistol magazine). On a
        # game mesh they mostly sit on UV seams, still protected; the normals come back from the source
        sharp = tmp.data.attributes.get("sharp_edge")
        if sharp is not None:
            tmp.data.attributes.remove(sharp)
        with bpy.context.temp_override(object=tmp):  # an operator: only recent Blender keeps them as an attribute
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        _write_protect_group(tmp)
        planar = tmp.modifiers.new("planar", "DECIMATE")
        planar.decimate_type = "DISSOLVE"
        planar.angle_limit = flat_angle  # only truly flat regions — never changes the silhouette
        planar.delimit = {"NORMAL", "MATERIAL", "SEAM", "UV"}
        _bake_into(tmp)

        tris = _tri_count(tmp.data)
        if tris > target_tris:
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

        # Collapse leaves loose edges and odd flipped faces behind, and those would block the export
        delete_loose(tmp, {})
        tmp.data.validate(clean_customdata=False)  # and faces stacked on the same vertices (1,182 on a papercraft robot)
        fix_normals(tmp, {})
        if normals_source is not None:
            transfer_normals(tmp.data, normals_source)
        return tmp.data
    finally:
        bpy.data.objects.remove(tmp)


_MAX_SAMPLES = 20_000  # vertices compared per mesh: ~0.1 s, and a 191k-tri car body read the same as all of them
STRAY = "asset_validator_lod_stray"  # on a LOD past lod.max_deviation: how far it strays, in % of the source's size


def _shape(mesh: bpy.types.Mesh, matrix):
    """(sampled world vertices, BVH of the world triangles, bbox diagonal) of `mesh` placed by `matrix`, so an
    object's scale counts as it's seen. None without faces: no surface to compare."""
    if not mesh.polygons:
        return None
    mesh.calc_loop_triangles()
    co = to_world(read_array(mesh.vertices, "co", 3, np.float64), matrix)
    tris = read_array(mesh.loop_triangles, "vertices", 3, np.int32)
    tree = BVHTree.FromPolygons(co.tolist(), tris.tolist())
    return co[::-(-len(co) // _MAX_SAMPLES)], tree, float(np.linalg.norm(np.ptp(co, axis=0))) or 1.0


def _stray(base, lod) -> float:
    """How far a LOD strays from its source, in % of the source's size: the 99th percentile of the distances
    both ways (source vertices to the LOD catch dents and lost features, LOD vertices to the source spikes),
    so one stray vertex doesn't count. `base`, `lod`: _shape()s; a LOD with no faces left strays 100 %."""
    if lod is None:
        return 100.0

    def far(points, tree):
        return float(np.percentile([(Vector(p) - tree.find_nearest(p)[0]).length for p in points.tolist()], 99))

    return max(far(base[0], lod[1]), far(lod[0], base[1])) / base[2] * 100


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
