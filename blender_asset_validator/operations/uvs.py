"""UV islands and what they cost the texture (texel density, stretch, gaps,
overlaps), in numpy over one UV layer; and the UV tools: Set Texel Density,
lightmap UVs and Auto Unwrap, which are the only functions here that edit."""
import math
from contextlib import contextmanager

import bmesh
import bpy
import numpy as np

from ..core.mesh_utils import read_array

_SNAP = 1e-5  # UVs closer than this are one UV vertex (Blender's own island limit is 1e-4)
_UV_SHRINK = 1e-4
_CUT_ROUNDS = 4
_MAX_GROWN = 5_000_000  # border pixels x gap disk the island gap check sorts at once: ~1 s, ~150 MB


def face_islands(mesh: bpy.types.Mesh, layer) -> np.ndarray:
    """Island index (0..n-1) per polygon: polygons sharing an edge with the same
    UVs on both ends are one island, as Pack Islands sees it."""
    _, keys = _uv_edges(mesh, read_array(layer.data, "uv", 2, np.float64))
    order, repeat = _sorted_runs(keys)
    faces = np.repeat(np.arange(len(mesh.polygons)), read_array(mesh.polygons, "loop_total", dtype=np.int64))[order]
    label = _components(len(mesh.polygons), faces[1:][repeat], faces[:-1][repeat])
    return np.unique(label, return_inverse=True)[1]


def _uv_edges(mesh: bpy.types.Mesh, uv: np.ndarray) -> tuple:
    """Per corner: the next corner around its face, and a key (mesh edge, then the
    UVs at its lower and higher vertex) that two corners share when they are one UV edge."""
    # shortcut: UVs snapped to a 1e-5 grid; two UVs 1e-6 apart across a grid line split an island, use a tolerance merge if one shows up
    loop_start = read_array(mesh.polygons, "loop_start", dtype=np.int64)
    loop_total = read_array(mesh.polygons, "loop_total", dtype=np.int64)
    corner_vert = read_array(mesh.loops, "vertex_index", dtype=np.int64)
    nxt = np.arange(len(corner_vert)) + 1
    nxt[loop_start + loop_total - 1] = loop_start
    flip = (corner_vert > corner_vert[nxt])[:, None]
    low, high = np.where(flip, uv[nxt], uv), np.where(flip, uv, uv[nxt])
    return nxt, np.column_stack([read_array(mesh.loops, "edge_index", dtype=np.int64), _snap(low), _snap(high)])


def _sorted_runs(keys: np.ndarray) -> tuple:
    """Row order that sorts `keys`, and per sorted row after the first whether it repeats the one before."""
    order = np.lexsort(keys.T[::-1])
    return order, (keys[order[1:]] == keys[order[:-1]]).all(axis=1)


def _snap(uv: np.ndarray) -> np.ndarray:
    return np.round(np.nan_to_num(uv, nan=1e9) / _SNAP).astype(np.int64)


def _components(n: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per node, the smallest node of its connected component, for the edges a-b.
    Union-find in numpy: hook each edge's larger root under the smaller, then point
    every node straight at its root; a few rounds even for millions of edges."""
    label = np.arange(n)
    while True:
        la, lb = label[a], label[b]
        apart = la != lb
        if not apart.any():
            return label
        np.minimum.at(label, np.maximum(la, lb)[apart], np.minimum(la, lb)[apart])
        while True:
            root = label[label]
            if (root == label).all():
                break
            label = root


def uv_stats(obj: bpy.types.Object, layer) -> dict:
    """Per polygon and per island of `layer`: 3D area in m² (object scale and scene
    units applied), UV area, and stretch. Area stretch: 0 when a face has its
    island's UV-to-3D scale, 1 when its UV is collapsed. Angle stretch: the mean
    angle error of its triangles' corners, in degrees."""
    mesh = obj.data
    mesh.calc_loop_triangles()
    tri_loops = read_array(mesh.loop_triangles, "loops", 3, np.int64)
    tri_face = read_array(mesh.loop_triangles, "polygon_index", dtype=np.int64)
    corner_vert = read_array(mesh.loops, "vertex_index", dtype=np.int64)
    to_metres = np.array(obj.matrix_world.to_3x3()) * bpy.context.scene.unit_settings.scale_length
    co = read_array(mesh.vertices, "co", 3, np.float64) @ to_metres.T
    p = co[corner_vert[tri_loops]]
    t = read_array(layer.data, "uv", 2, np.float64)[tri_loops]
    area = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1) / 2
    e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
    uv_area = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2

    island = face_islands(mesh, layer)
    count = int(island.max()) + 1 if len(island) else 0
    tri_island = island[tri_face]
    island_area = np.bincount(tri_island, area, count)
    island_uv_area = np.bincount(tri_island, uv_area, count)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = (uv_area / area) / (island_uv_area / island_area)[tri_island]
        area_stretch = np.where(area > 0, 1 - np.minimum(ratio, 1 / ratio), 0.0)
    angle_stretch = np.degrees(np.abs(_corner_angles(t) - _corner_angles(p)).mean(axis=1))
    area_stretch, angle_stretch = np.nan_to_num(area_stretch, nan=1.0), np.nan_to_num(angle_stretch, nan=180.0)

    faces = len(mesh.polygons)
    face_area = np.bincount(tri_face, area, faces)
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "island": island,
            "island_area": island_area,
            "island_uv_area": island_uv_area,
            "island_area_stretch": np.bincount(tri_island, area * area_stretch, count) / island_area,
            "island_angle_stretch": np.bincount(tri_island, area * angle_stretch, count) / island_area,
            "face_area": face_area,
            "face_uv_area": np.bincount(tri_face, uv_area, faces),
            "face_area_stretch": np.bincount(tri_face, area * area_stretch, faces) / face_area,
            "face_angle_stretch": np.bincount(tri_face, area * angle_stretch, faces) / face_area,
        }


def _corner_angles(points: np.ndarray) -> np.ndarray:
    """(T, 3) inner angles of triangles given as (T, 3, 2 or 3) corners; NaN on degenerate ones."""
    angles = []
    for k in range(3):
        a = points[:, (k + 1) % 3] - points[:, k]
        b = points[:, (k + 2) % 3] - points[:, k]
        with np.errstate(divide="ignore", invalid="ignore"):
            cos = (a * b).sum(axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
        angles.append(np.arccos(np.clip(cos, -1.0, 1.0)))
    return np.stack(angles, axis=1)


def texel_density(stats: dict, texture_size: int) -> np.ndarray:
    """Pixels per metre of each island at texture_size; not finite where it has no 3D area."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.sqrt(stats["island_uv_area"] / stats["island_area"]) * texture_size


def median_density(stats: dict, texture_size: int) -> float:
    """The texel density most of the surface has: the islands' median weighted by 3D
    area, leaving out islands under a pixel (solid-colour mappings, collapsed UVs)."""
    density = texel_density(stats, texture_size)
    known = np.isfinite(density) & (stats["island_area"] > 0) & (stats["island_uv_area"] * texture_size ** 2 >= 1)
    if not known.any():
        return math.nan
    order = np.argsort(density[known])
    weight = np.cumsum(stats["island_area"][known][order])
    return float(density[known][order][np.searchsorted(weight, weight[-1] / 2)])


def island_bounds(mesh: bpy.types.Mesh, layer, island: np.ndarray) -> tuple:
    """UV bounding box (lo, hi), each (islands, 2), of every island."""
    corner_island = np.repeat(island, read_array(mesh.polygons, "loop_total", dtype=np.int64))
    uv = read_array(layer.data, "uv", 2, np.float64)
    count = int(island.max()) + 1 if len(island) else 0
    lo, hi = np.full((count, 2), np.inf), np.full((count, 2), -np.inf)
    np.minimum.at(lo, corner_island, uv)
    np.maximum.at(hi, corner_island, uv)
    return lo, hi


def crowded_islands(mesh: bpy.types.Mesh, layer, island: np.ndarray, size: int, gap: float, skip: np.ndarray = None) -> np.ndarray:
    """Islands whose border comes closer than `gap` px to another island's on a
    `size` px texture. Measured on the pixels the texture will have: each border is
    drawn into pixels and grown by half the gap, and islands whose grown borders
    share a pixel bleed into each other. Within a pixel either way, and bounded by
    the pixels drawn: comparing edge pairs went O(n²) on palette UVs (a whole mesh
    in a few pixels). `skip`: islands (bool per island) left out."""
    uv = read_array(layer.data, "uv", 2, np.float64)
    nxt, keys = _uv_edges(mesh, uv)
    order, repeat = _sorted_runs(keys)
    new = np.r_[True, ~repeat]
    border = order[new & np.r_[new[1:], True]]  # UV edges no other corner shares
    border = border[np.isfinite(uv[border]).all(axis=1) & np.isfinite(uv[nxt[border]]).all(axis=1)]
    p, q = uv[border] * size, uv[nxt[border]] * size
    owner = np.repeat(island, read_array(mesh.polygons, "loop_total", dtype=np.int64))[border]
    if skip is not None:
        p, q, owner = p[~skip[owner]], q[~skip[owner]], owner[~skip[owner]]

    reach = math.ceil(gap / 2)
    disk = np.array([(x, y) for x in range(-reach, reach + 1) for y in range(-reach, reach + 1) if x * x + y * y <= (gap / 2) ** 2])
    # Points 1 px apart along each border edge. Past the budget only the longest edges get fewer points:
    # the cap is the highest that fits, so short edges keep 1 px.
    # shortcut: a capped edge is checked coarsely (UVs hundreds of tiles wide, junk UVs); fine for a warning
    steps = np.ceil(np.linalg.norm(q - p, axis=1))
    budget = _MAX_GROWN // len(disk)
    if steps.sum() > budget:
        lengths = np.sort(steps)
        fits = np.cumsum(lengths) + lengths * np.arange(len(lengths) - 1, -1, -1) <= budget
        steps = np.minimum(steps, lengths[fits][-1] if fits.any() else max(1, budget // len(steps)))
    steps = steps.astype(np.int64) + 1
    edge = np.repeat(np.arange(len(p)), steps)
    t = (np.arange(steps.sum()) - np.repeat(np.cumsum(steps) - steps, steps)) / np.repeat(np.maximum(steps - 1, 1), steps)
    drawn = np.unique(np.column_stack([np.floor(p[edge] + (q - p)[edge] * t[:, None]).astype(np.int64), owner[edge]]), axis=0)
    grown = (drawn[:, None, :2] + disk[None]).reshape(-1, 2)
    who = np.repeat(drawn[:, 2], len(disk))
    order = np.lexsort((who, grown[:, 1], grown[:, 0]))
    grown, who = grown[order], who[order]
    shared = (grown[1:] == grown[:-1]).all(axis=1) & (who[1:] != who[:-1])
    return np.unique(np.concatenate([who[1:][shared], who[:-1][shared]]))


def uv_overlap(mesh: bpy.types.Mesh, layer) -> bool:
    """Not BVHTree.overlap: its tri-tri test treats coplanar triangles (every UV
    triangle at z=0) as never intersecting."""
    mesh.calc_loop_triangles()
    tris = read_array(layer.data, "uv", 2, np.float64)[read_array(mesh.loop_triangles, "loops", 3, np.int64)]
    tris = tris[np.isfinite(tris).all(axis=(1, 2))]  # one NaN UV would put every triangle in one grid cell: O(T²)
    center = tris.mean(axis=1, keepdims=True)
    # Shrink toward the centroid so neighbours touching along an edge/vertex don't count
    return _any_triangles_overlap(center + (tris - center) * (1.0 - _UV_SHRINK))


def _any_triangles_overlap(tris: np.ndarray) -> bool:
    """tris: (T, 3, 2). Broad phase: a grid of ~sqrt(T) cells a side over their
    bounds; only triangles sharing a cell are tested against each other."""
    if len(tris) < 2:
        return False
    cells = max(1, int(len(tris) ** 0.5))
    lo, hi = tris.min(axis=1), tris.max(axis=1)
    origin = lo.min(axis=0)
    size = (hi.max(axis=0) - origin) / cells
    size[size == 0] = 1.0

    def cell_of(points):
        return np.minimum(((points - origin) / size).astype(np.int64), cells - 1)

    first = cell_of(lo)
    span = cell_of(hi) - first + 1
    count = span[:, 0] * span[:, 1]  # cells each triangle covers
    nth = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    width = np.repeat(span[:, 0], count)
    cell = (np.repeat(first[:, 0], count) + nth % width) * cells + np.repeat(first[:, 1], count) + nth // width
    order = np.argsort(cell, kind="stable")
    cell, tri = cell[order], np.repeat(np.arange(len(tris)), count)[order]
    axes, own_min, own_max = _sat_axes(tris)
    for gap in range(1, len(cell)):
        same = np.flatnonzero(cell[:-gap] == cell[gap:])
        if not len(same):
            return False  # sorted by cell: no run of one cell is `gap` long
        a, b = tri[same], tri[same + gap]
        # Test each pair once, in the cell where their bounding boxes start overlapping
        start, end = np.maximum(lo[a], lo[b]), np.minimum(hi[a], hi[b])
        home = cell_of(start)
        keep = (start <= end).all(axis=1) & (home[:, 0] * cells + home[:, 1] == cell[same])
        a, b = a[keep], b[keep]
        apart = _separated(axes[a], own_min[a], own_max[a], tris[b])
        apart |= _separated(axes[b], own_min[b], own_max[b], tris[a])
        if not apart.all():
            return True
    return False


def _sat_axes(tris: np.ndarray) -> tuple:
    """Each triangle's edge normals (T, 3, 2) and its own extent along them (T, 3) min and max."""
    edges = np.roll(tris, -1, axis=1) - tris
    axes = np.stack([-edges[..., 1], edges[..., 0]], axis=2)
    own = np.einsum("tak,tvk->tav", axes, tris)
    return axes, own.min(axis=2), own.max(axis=2)


def _separated(axes, own_min, own_max, other) -> np.ndarray:
    """Per pair: True where one of the first triangle's edge normals separates it from `other` (N, 3, 2)."""
    proj = np.einsum("nak,nvk->nav", axes, other)
    return ((proj.max(axis=2) < own_min) | (proj.min(axis=2) > own_max)).any(axis=1)


@contextmanager
def _editing(obj: bpy.types.Object, layer_index: int = 0):
    """obj alone selected and active, in Edit Mode with every face selected and
    UV layer `layer_index` active, for the bpy.ops.uv operators; restores after."""
    view_layer = bpy.context.view_layer
    selected, active = list(bpy.context.selected_objects), view_layer.objects.active
    active_uv = obj.data.uv_layers.active_index
    try:  # from here: a hidden object (export.use_active_collection) can't enter Edit Mode
        for other in selected:
            other.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        obj.data.uv_layers.active_index = layer_index
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        yield
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        obj.data.uv_layers.active_index = active_uv
        obj.select_set(False)
        for other in selected:
            other.select_set(True)
        view_layer.objects.active = active


def _pack(obj: bpy.types.Object, config: dict, scale: bool) -> None:
    cfg = config.get("uv", {})
    margin = cfg.get("min_island_gap_px", 8) / cfg.get("texture_size", 2048)
    # ADD: exact with scale=False. With scale=True the margin shrinks with the layout (dense layouts get
    # less than asked, and check_uv_layout says so); FRACTION would be exact but spun for 20+ s on a cube
    with _editing(obj):
        bpy.ops.uv.pack_islands(scale=scale, rotate=True, shape_method="CONCAVE", margin_method="ADD", margin=margin)


def set_texel_density(obj: bpy.types.Object, density: float, config: dict) -> str:
    """Scales every island of UV0 to `density` px/m (at uv.texture_size) around its
    own centre, then packs them without rescaling."""
    mesh = obj.data
    if not mesh.uv_layers or not mesh.polygons:
        return "no UVs"
    size = config.get("uv", {}).get("texture_size", 2048)
    layer = mesh.uv_layers[0]
    stats = uv_stats(obj, layer)
    island = stats["island"]
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = density / texel_density(stats, size)
    factor[~np.isfinite(factor)] = 1.0  # collapsed islands and ones with no 3D area stay as they are
    lo, hi = island_bounds(mesh, layer, island)
    corner_island = np.repeat(island, read_array(mesh.polygons, "loop_total", dtype=np.int64))
    center = ((lo + hi) / 2)[corner_island]
    # Every island around (0.5, 0.5): float32 UVs near 500 blur a shrunk island's area, and
    # Pack Islands (closest UDIM) packs into the tile they sit on; it moves them all anyway
    uv = read_array(layer.data, "uv", 2, np.float64)
    uv = 0.5 + (uv - center) * factor[corner_island, None]
    layer.data.foreach_set("uv", uv.astype(np.float32).ravel())
    mesh.update()
    _pack(obj, config, scale=False)
    lo, hi = island_bounds(mesh, mesh.uv_layers[0], island)  # Edit Mode rebuilt the layers: `layer` is stale
    if (hi > 1 + 1e-4).any() or (lo < -1e-4).any():
        return f"{density:g} px/m doesn't fit in one {size} px texture: use a bigger texture or a lower density"
    return f"{density:g} px/m, packed in 0–1"


def generate_lightmap_uv(obj: bpy.types.Object, config: dict) -> str:
    """(Re)builds UV1, the lightmap channel, with Lightmap Pack; UV0 is untouched."""
    mesh = obj.data
    if not mesh.uv_layers:
        return None  # no UV0 to sit after: check_uvs reports it
    if len(mesh.uv_layers) < 2:
        mesh.uv_layers.new(name="Lightmap")
    with _editing(obj, 1):
        bpy.ops.uv.lightmap_pack(PREF_CONTEXT="ALL_FACES", PREF_MARGIN_DIV=0.2)
    return f"Generated lightmap UV '{mesh.uv_layers[1].name}'"


def auto_unwrap(obj: bpy.types.Object, config: dict, straighten: bool = False) -> str:
    """Hard surface unwrap: seams on sharp edges (or, with none marked, edges over
    topology.feature_angle), material borders and open borders; unwrap; then any
    island stretching past the uv limits is cut along its most bent path of edges
    (concave ones preferred: the seam hides in the crease) and unwrapped again."""
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
    cfg = config.get("uv", {})
    angle = math.radians(config.get("topology", {}).get("feature_angle", 30.0))
    bm = bmesh.new()
    bm.from_mesh(mesh)
    marked = any(not e.smooth for e in bm.edges)
    for e in bm.edges:
        if (e.is_boundary or (not e.smooth if marked else _bend(e) > angle)
                or len({f.material_index for f in e.link_faces}) > 1):
            e.seam = True
    bm.to_mesh(mesh)
    bm.free()

    cuts, faces = 0, np.arange(len(mesh.polygons))
    conformal = np.zeros(len(mesh.polygons), bool)
    for _ in range(_CUT_ROUNDS):
        conformal = _unwrap(obj, faces, conformal)
        stats = uv_stats(obj, mesh.uv_layers[0])
        bad = np.flatnonzero((stats["island_area_stretch"] > cfg.get("max_area_stretch", 0.3))
                             | (stats["island_angle_stretch"] > cfg.get("max_angle_stretch", 10.0)))
        if not len(bad):
            break
        added = _cut_islands(mesh, stats["island"], bad)
        if not added:
            break
        cuts += added
        faces = np.flatnonzero(np.isin(stats["island"], bad))  # Minimum Stretch is the slow part: redo only what was cut
    if straighten:
        _straighten_quads(obj, uv_stats(obj, mesh.uv_layers[0])["island"])
    _pack(obj, config, scale=True)
    islands = int(face_islands(mesh, mesh.uv_layers[0]).max()) + 1 if mesh.polygons else 0
    return f"{islands} island(s)" + (f", {cuts} seam edge(s) cut to relieve stretch" if cuts else "")


def _bend(edge) -> float:
    """Angle between the normals of a 2-face edge; 0 elsewhere."""
    return edge.calc_face_angle(0.0) if len(edge.link_faces) == 2 else 0.0


def _unwrap(obj: bpy.types.Object, faces: np.ndarray, conformal: np.ndarray) -> np.ndarray:
    """Unwraps `faces` (polygon indices), leaving the other islands' UVs as they are;
    returns `conformal` (bool per face) plus the islands Minimum Stretch collapsed.
    Minimum Stretch where Blender has it, Conformal on the faces in `conformal`: in 5.2
    Minimum Stretch gave 72% of a scanned rock's triangles zero UV area, and on a
    skeleton's big closed islands it did it again every round, minutes each. Angle
    Based fixes the same islands as Conformal, but also took minutes there."""
    unwrap = bpy.ops.uv.unwrap.get_rna_type().properties
    slim = "MINIMUM_STRETCH" in unwrap["method"].enum_items.keys()  # 4.3+
    weights = {}
    if "use_weights" in unwrap.keys() and "uv_importance" in obj.vertex_groups:  # 4.3+
        weights = {"use_weights": True, "weight_group": "uv_importance"}
    with _editing(obj):
        for subset, method in ((faces[~conformal[faces]], "MINIMUM_STRETCH" if slim else "CONFORMAL"),
                               (faces[conformal[faces]], "CONFORMAL")):
            if len(subset):
                _select_faces(obj.data, subset)
                bpy.ops.uv.unwrap(method=method, margin=0.0, **weights)
    if not slim:
        return conformal
    stats = uv_stats(obj, obj.data.uv_layers[0])
    island = stats["island"]
    flat = (stats["face_uv_area"] < 1e-14) & (stats["face_area"] > 0)
    collapsed = (np.bincount(island, stats["face_area"] * flat, len(stats["island_area"])) > 0.05 * stats["island_area"])[island]
    redo = np.intersect1d(np.flatnonzero(collapsed & ~conformal), faces)
    if len(redo):
        with _editing(obj):
            _select_faces(obj.data, redo)
            bpy.ops.uv.unwrap(method="CONFORMAL", margin=0.0, **weights)
    conformal = conformal.copy()
    conformal[redo] = True
    return conformal


def _select_faces(mesh: bpy.types.Mesh, faces) -> bmesh.types.BMesh:
    """In Edit Mode: only `faces` (polygon indices) selected; returns the edit bmesh."""
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.select_set(False)
    for index in faces:
        bm.faces[int(index)].select_set(True)
    bmesh.update_edit_mesh(mesh)
    return bm


def _cut_islands(mesh: bpy.types.Mesh, island: np.ndarray, bad: np.ndarray) -> int:
    """Marks one seam path per island in `bad`: from its most bent inner edge,
    walked both ways along the most bent, straightest edges until it meets a seam
    or an open border, which is what lets the unwrap open the island up."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    face_island = {f: island[f.index] for f in bm.faces}
    targets = set(bad.tolist())
    inner = {}
    for e in bm.edges:
        owners = {face_island[f] for f in e.link_faces}
        if not e.seam and len(e.link_faces) == 2 and len(owners) == 1 and owners <= targets:
            inner.setdefault(owners.pop(), []).append(e)

    def score(e):
        return _bend(e) * (1.5 if not e.is_convex else 1.0)

    added = 0
    for edges in inner.values():
        start = max(edges, key=score)
        if score(start) <= 0:
            continue
        members, path = set(edges), {start}
        for end in start.verts:
            prev, v = start, end
            # shortcut: the walk is capped at the island's edge count; a smooth closed blob may get a long winding seam, which is out of hard surface scope
            while not any(e.seam or e.is_boundary for e in v.link_edges if e not in path) and len(path) < len(members):
                direction = (v.co - prev.other_vert(v).co).normalized()
                options = [e for e in v.link_edges if e in members and e not in path]
                if not options:
                    break
                prev = max(options, key=lambda e: score(e) + 0.1 * direction.dot((e.other_vert(v).co - v.co).normalized()))
                path.add(prev)
                v = prev.other_vert(v)
        for e in path:
            e.seam = True
        added += len(path)
    bm.to_mesh(mesh)
    bm.free()
    return added


def _straighten_quads(obj: bpy.types.Object, island: np.ndarray) -> None:
    """Follow Active Quads on every all-quad island: its edge loops become straight UV lines."""
    mesh = obj.data
    quads = read_array(mesh.polygons, "loop_total", dtype=np.int64) == 4
    with _editing(obj):
        for i in np.unique(island):
            faces = np.flatnonzero(island == i)
            if not quads[faces].all():
                continue
            bm = _select_faces(mesh, faces)
            bm.faces.active = bm.faces[int(faces[0])]
            bmesh.update_edit_mesh(mesh)
            bpy.ops.uv.follow_active_quads(mode="LENGTH_AVERAGE")
        bpy.ops.mesh.select_all(action="SELECT")
