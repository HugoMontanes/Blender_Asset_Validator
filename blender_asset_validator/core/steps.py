"""The guided pipeline: the checks split into steps the artist reviews and
approves one at a time, in an order where each step's fixes don't undo an
earlier one (decimating comes after the topology work, export last)."""
from typing import Optional

# (label, what the artist should look at, check function names; None = every check)
STEPS = [
    ("Object setup", "Applied transforms, names, materials and textures",
     {"check_transforms", "check_naming", "check_materials"}),
    ("Mesh integrity", "Flipped normals, loose and non-manifold geometry, zero-area faces",
     {"check_normals", "check_manifold", "check_degenerate_faces"}),
    ("Topology", "Ngons, warped quads, poles and slivers. Clean Topology / Retopologize live here",
     {"check_ngons", "check_quad_planarity", "check_topology"}),
    ("Shading & UVs", "Hard edges off UV seams, GPU vertex cost, missing or overlapping UVs",
     {"check_shading", "check_uvs"}),
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
