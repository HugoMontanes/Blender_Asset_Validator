"""The guided pipeline: the checks split into steps the artist reviews and
approves one at a time, in an order where each step's fixes don't undo an
earlier one (decimating comes after the topology work, export last)."""
from typing import Optional

APPROVED = "asset_validator_approved"  # object property: indices of the steps approved on it

# (label, what the artist should look at, check function names; None = every check)
STEPS = [
    ("Object setup", "Applied transforms, names, collisions, materials and textures",
     {"check_transforms", "check_naming", "check_collisions", "check_materials"}),
    ("Mesh integrity", "Flipped normals, loose and non-manifold geometry, zero-area faces",
     {"check_normals", "check_manifold", "check_degenerate_faces"}),
    ("Topology", "Ngons, warped quads, poles and slivers. Clean Topology / Retopologize live here",
     {"check_ngons", "check_quad_planarity", "check_topology"}),
    ("Shading & UVs", "Hard edges off UV seams, GPU vertex cost, mid-poly Weighted Normal, UV overlaps, texel density, stretch, gaps, lightmap UV",
     {"check_shading", "check_weighted_normal", "check_uvs", "check_uv_layout", "check_lightmap_uv"}),
    ("Budget & LODs", "Triangle budget, then generate the LODs",
     {"check_polycount"}),
    ("Final check & export", "Every check once more, then export",
     None),
]


def step_checks(scene) -> Optional[set]:
    """Check names of the scene's current step, or None (all checks) outside guided mode."""
    if not getattr(scene, "asset_validator_guided", False):
        return None
    return STEPS[min(scene.asset_validator_step, len(STEPS) - 1)][2]


def step_approved(objects, index: int) -> bool:
    """Approvals live on the objects: a new object (Retopologize) or another
    selection starts unapproved."""
    return bool(objects) and all(index in obj.get(APPROVED, []) for obj in objects)


def approve_step(objects, index: int) -> None:
    for obj in objects:
        obj[APPROVED] = sorted({*obj.get(APPROVED, []), index})
