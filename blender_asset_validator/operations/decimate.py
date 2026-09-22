from typing import Optional

import bpy

from ..core.mesh_utils import evaluated_triangle_count

_MODIFIER_NAME = "AssetValidator_Decimate"


def _decimate_ratio(current_tris: int, budget: int) -> float:
    """Ratio for a Decimate modifier that brings current_tris under budget."""
    if current_tris <= budget or current_tris <= 0:
        return 1.0
    return max(0.01, min(1.0, budget / current_tris))


def fix_polycount(obj: bpy.types.Object, config: dict) -> Optional[str]:
    """Fixer for check_polycount. Sizes a Decimate modifier against the
    evaluated (modifiers-applied) triangle count, so re-validation — which
    also reads the evaluated mesh — actually sees the reduction."""
    if obj.get("asset_validator_lod", False):
        return None  # LOD copies carry their own hand-picked ratio — don't compound it

    budget = config.get("geometry", {}).get("max_triangles", 50000)
    tri_count = evaluated_triangle_count(obj)
    ratio = _decimate_ratio(tri_count, budget)
    if ratio >= 1.0:
        return None

    modifier = obj.modifiers.get(_MODIFIER_NAME)
    if modifier is None:
        modifier = obj.modifiers.new(name=_MODIFIER_NAME, type="DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = ratio

    return f"added/updated Decimate modifier (ratio {ratio:.2f}) — ~{tri_count:,} -> ~{round(tri_count * ratio):,} tris"


if __name__ == "__main__":
    assert _decimate_ratio(100_000, 50_000) == 0.5
    assert _decimate_ratio(30_000, 50_000) == 1.0
    assert _decimate_ratio(0, 50_000) == 1.0
    assert _decimate_ratio(100_000, 0) == 0.01  # floor clamp, never an invalid 0.0 ratio
    print("decimate.py self-check OK")
