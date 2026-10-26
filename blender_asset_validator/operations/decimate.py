from typing import Optional

import bpy

from ..core.mesh_utils import evaluated_triangle_count

_MODIFIER_NAME = "AssetValidator_Decimate"


def _decimate_ratio(current_tris: int, budget: int, current_ratio: float = 1.0) -> float:
    """Absolute Decimate ratio that brings current_tris under budget. current_tris
    is measured WITH the existing modifier, so the new ratio compounds on it."""
    if current_tris <= budget or current_tris <= 0:
        return current_ratio
    return max(0.01, min(1.0, current_ratio * budget / current_tris))


def fix_polycount(obj: bpy.types.Object, config: dict) -> Optional[str]:
    """Fixer for check_polycount. Sizes a Decimate modifier against the
    evaluated (modifiers-applied) triangle count, so re-validation — which
    also reads the evaluated mesh — actually sees the reduction."""
    if obj.get("asset_validator_lod", False):
        return None  # LOD copies carry their own hand-picked ratio — don't compound it

    budget = config.get("geometry", {}).get("max_triangles", 50000)
    tri_count = evaluated_triangle_count(obj)
    modifier = obj.modifiers.get(_MODIFIER_NAME)
    current_ratio = modifier.ratio if modifier else 1.0
    ratio = _decimate_ratio(tri_count, budget, current_ratio)
    if ratio >= current_ratio:
        return None

    if modifier is None:
        modifier = obj.modifiers.new(name=_MODIFIER_NAME, type="DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = ratio

    expected = round(tri_count * ratio / current_ratio)
    return f"added/updated Decimate modifier (ratio {ratio:.2f}) — ~{tri_count:,} -> ~{expected:,} tris"


if __name__ == "__main__":
    assert _decimate_ratio(100_000, 50_000) == 0.5
    assert _decimate_ratio(30_000, 50_000) == 1.0
    assert _decimate_ratio(0, 50_000) == 1.0
    assert _decimate_ratio(100_000, 0) == 0.01  # floor clamp, never an invalid 0.0 ratio
    # Second Fix: Collapse left 50.4k at ratio 0.5 — must go lower, not back to ~0.99
    assert abs(_decimate_ratio(50_400, 50_000, 0.5) - 0.5 * 50_000 / 50_400) < 1e-12
    assert _decimate_ratio(40_000, 50_000, 0.5) == 0.5  # already under budget: unchanged
    print("decimate.py self-check OK")
