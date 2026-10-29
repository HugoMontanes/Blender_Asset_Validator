import re
from functools import partial
from typing import List

import bpy
import numpy as np

from ..core.mesh_utils import read_array, select_in_edit_mode
from ..core.registry import register_check
from ..core.result import CheckResult, Severity
from ..operations.uvs import (
    crowded_islands, generate_lightmap_uv, island_bounds, median_density, texel_density, uv_overlap, uv_stats,
)

_EPSILON = 1e-4  # UVs this far past a 0–1 or UDIM tile edge still count as on it


@register_check
def check_uvs(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    results = []
    if not config.get("geometry", {}).get("check_uvs", True):
        return results

    for obj in objects:
        mesh = obj.data

        if not mesh.uv_layers:
            results.append(CheckResult(
                severity=Severity.ERROR,
                message=f"'{obj.name}' has no UV map",
                object_name=obj.name,
                fix_hint="Edit Mode > UV > Unwrap  (U), or Asset Validator > Auto Unwrap",
                check_name="uvs",
            ))
            continue

        if uv_overlap(mesh, mesh.uv_layers[0]):  # UV0: what the engine's materials sample
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' has overlapping UVs",
                object_name=obj.name,
                fix_hint="UV Editor > UV > Pack Islands or manually fix overlaps",
                check_name="uvs",
            ))

    return results


@register_check
def check_uv_layout(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    """UV0's islands against the texture they get painted on: texel density, stretch,
    gaps between islands and the 0–1 square. No Fix: repacking the UVs of an asset
    that is already textured breaks its textures, so Set Texel Density and Auto
    Unwrap are tools the artist runs, never part of Fix All."""
    results = []
    cfg = config.get("uv", {})
    size = cfg.get("texture_size", 2048)
    target = cfg.get("texel_density", 0)
    tolerance = cfg.get("texel_tolerance", 0.2)
    max_area, max_angle = cfg.get("max_area_stretch", 0.3), cfg.get("max_angle_stretch", 10.0)
    gap = cfg.get("min_island_gap_px", 8)

    for obj in objects:
        mesh = obj.data
        if not mesh.uv_layers or not mesh.polygons:
            continue  # check_uvs reports a missing UV map
        layer = mesh.uv_layers[0]
        stats = uv_stats(obj, layer)
        island = stats["island"]
        islands = len(stats["island_area"])

        def warn(bad, message, hint):
            if len(bad):
                faces = np.flatnonzero(np.isin(island, bad)).tolist()
                results.append(CheckResult(
                    severity=Severity.WARNING, message=f"'{obj.name}': {message}", object_name=obj.name,
                    fix_hint=hint, check_name="uv_layout", select=partial(select_in_edit_mode, obj, "FACE", faces),
                ))

        lo, hi = island_bounds(mesh, layer, island)
        # Inside one texel: a palette / solid-colour mapping, no texture detail for density, stretch or gaps to measure
        solid = ((hi - lo) * size < 1).all(axis=1)
        density = texel_density(stats, size)
        results.append(CheckResult(
            severity=Severity.INFO,
            message=(f"'{obj.name}' UV0: {islands} island(s), texel density {median_density(stats, size):.0f} px/m "
                     f"at {size} px" + (f" (target {target:g})" if target else "")
                     + (f", {solid.sum()} solid-colour (under a pixel)" if solid.any() else "")),
            object_name=obj.name,
            check_name="uv_layout",
        ))
        with np.errstate(invalid="ignore"):
            off = np.flatnonzero(~solid & np.isfinite(density) & (np.abs(density / target - 1) > tolerance)) if target else []
        if len(off):
            warn(off, f"{len(off)} of {islands} UV island(s) are more than {tolerance:.0%} off the {target:g} px/m "
                      f"texel density ({density[off].min():.0f}–{density[off].max():.0f} px/m)",
                 "Set Texel Density, or scale those islands in the UV Editor")

        with np.errstate(invalid="ignore"):
            stretched = np.flatnonzero(~solid & ((stats["island_area_stretch"] > max_area) | (stats["island_angle_stretch"] > max_angle)))
        warn(stretched, f"{len(stretched)} UV island(s) stretch past the limit (area {max_area:.0%}, angles {max_angle:g}°)",
             "Seam them where they bend most and unwrap again (Auto Unwrap); Heatmap > UV Stretch shows where")

        tiling, udim = _island_kinds(obj, island, cfg.get("tiling_materials", ""))
        in_square = (lo >= -_EPSILON).all(axis=1) & (hi <= 1 + _EPSILON).all(axis=1)
        in_tile = (lo >= -_EPSILON).all(axis=1) & (np.floor(lo + _EPSILON) == np.floor(hi - _EPSILON)).all(axis=1)
        outside = ~tiling & ~np.where(udim, in_tile, in_square)
        # An island off the texture shares no pixels with the others: it gets the 0–1 warning, not a gap one
        crowded = crowded_islands(mesh, layer, island, size, gap, skip=tiling | outside | solid)
        warn(crowded, f"{len(crowded)} UV island(s) closer than {gap:g} px to another at {size} px: "
                      "their colours bleed into each other in the mipmaps",
             "Pack Islands with a bigger margin")
        warn(np.flatnonzero(outside), f"{outside.sum()} UV island(s) outside 0–1 (or across a UDIM tile)",
             "Pack Islands; if the material repeats on purpose, match its name with uv.tiling_materials")

    return results


def _island_kinds(obj: bpy.types.Object, island: np.ndarray, tiling: str) -> tuple:
    """Per island: on a tiling material (name matches `tiling`: its UVs repeat on
    purpose, so neither 0–1 nor gaps apply), and on a UDIM material (it only has to
    stay inside one tile)."""
    kinds = [_material_kind(slot.material, tiling) for slot in obj.material_slots] or [""]
    material = np.minimum(read_array(obj.data.polygons, "material_index", dtype=np.int64), len(kinds) - 1)
    face_kind = np.array(kinds)[material]
    count = int(island.max()) + 1
    repeats, udim = np.zeros(count, bool), np.zeros(count, bool)
    repeats[island[face_kind == "tiling"]] = True
    udim[island[face_kind == "udim"]] = True
    return repeats, udim


def _material_kind(material, tiling: str) -> str:
    if material is None:
        return ""
    if tiling and re.search(tiling, material.name):
        return "tiling"
    nodes = material.node_tree.nodes if material.node_tree else []
    if any(n.type == "TEX_IMAGE" and n.image and n.image.source == "TILED" for n in nodes):
        return "udim"
    return ""


@register_check
def check_lightmap_uv(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    """UV1 is the lightmap channel in Unreal and Unity: every face needs its own spot
    in 0–1. Both engines can build one on import, so a missing UV1 only counts when
    the project asks for it (uv.require_lightmap). The fix rebuilds UV1 only."""
    results = []
    required = config.get("uv", {}).get("require_lightmap", False)
    for obj in objects:
        layers = obj.data.uv_layers
        if not layers:
            continue  # check_uvs reports it
        fix = partial(generate_lightmap_uv, obj, config)
        if len(layers) < 2:
            if required:
                results.append(CheckResult(
                    severity=Severity.ERROR, message=f"'{obj.name}' has no lightmap UV (UV1)", object_name=obj.name,
                    fix_hint="Fix generates it with Lightmap Pack", check_name="lightmap_uv", fix=fix,
                ))
            continue
        layer = layers[1]
        problems = []
        if uv_overlap(obj.data, layer):
            problems.append("overlapping faces")
        uv = read_array(layer.data, "uv", 2, np.float64)
        if ((uv < -_EPSILON) | (uv > 1 + _EPSILON)).any():
            problems.append("UVs outside 0–1")
        if problems:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' lightmap UV '{layer.name}' has {' and '.join(problems)}",
                object_name=obj.name,
                fix_hint="Fix rebuilds it with Lightmap Pack (UV0 is not touched)",
                check_name="lightmap_uv",
                fix=fix,
            ))
    return results
