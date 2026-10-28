from functools import partial
from typing import List

import bmesh
import bpy

from ..core.mesh_utils import select_in_edit_mode
from ..core.registry import register_check
from ..core.result import CheckResult, Severity
from ..operations.cleanup import delete_loose, fix_normals, wrong_way_faces


@register_check
def check_normals(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    """Faces facing the wrong way: engines cull back faces, so they render invisible.
    Fix flips exactly the faces reported, so it always clears the error; what can't
    be made consistent is reported apart. Rules: cleanup.wrong_way_faces."""
    results = []
    if not config.get("geometry", {}).get("check_normals", True):
        return results

    for obj in objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        wrong, inward, twisted = wrong_way_faces(bm)
        bm.free()

        if wrong:
            results.append(CheckResult(
                severity=Severity.ERROR,
                message=f"'{obj.name}' has {len(wrong)} face(s) facing the wrong way",
                object_name=obj.name,
                fix_hint="Fix flips just these; by hand: Show, then Edit Mode > Mesh > Normals > Flip",
                check_name="normals",
                fix=partial(fix_normals, obj, config),
                select=partial(select_in_edit_mode, obj, "FACE", wrong),
            ))
        if inward:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' has closed part(s) facing inward ({len(inward)} face(s)): fine for a room or skydome",
                object_name=obj.name,
                fix_hint="If it should be seen from outside: Show, then Edit Mode > Mesh > Normals > Flip",
                check_name="normals",
                # no fix: Fix All would turn intended interiors outward
                select=partial(select_in_edit_mode, obj, "FACE", inward),
            ))
        if twisted:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' has {len(twisted)} edge(s) where the surface can't be oriented (twisted, Möbius-like)",
                object_name=obj.name,
                fix_hint="Recalculate can't fix these: delete and rebuild the faces around them",
                check_name="normals",
                select=partial(select_in_edit_mode, obj, "EDGE", twisted),
            ))

    return results


@register_check
def check_manifold(objects: List[bpy.types.Object], config: dict) -> List[CheckResult]:
    """Loose vertices/edges, edges shared by 3+ faces and surfaces touching at a
    single vertex: bakers, remeshers and decimators misbehave on all of them."""
    results = []
    if not config.get("geometry", {}).get("check_manifold", True):
        return results

    for obj in objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        loose_verts = [v.index for v in bm.verts if not v.link_faces]
        loose_edges = [e.index for e in bm.edges if not e.link_faces]
        fins = [e.index for e in bm.edges if len(e.link_faces) > 2]
        bowties = [
            v.index for v in bm.verts
            if v.link_faces and not v.is_manifold and all(len(e.link_faces) <= 2 for e in v.link_edges)
        ]
        bm.free()

        if loose_verts or loose_edges:
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' has {len(loose_verts)} loose vertex(es), {len(loose_edges)} loose edge(s)",
                object_name=obj.name,
                fix_hint="Edit Mode > Mesh > Clean Up > Delete Loose",
                check_name="manifold",
                fix=partial(delete_loose, obj, config),
                select=partial(select_in_edit_mode, obj, "VERT", loose_verts) if loose_verts
                else partial(select_in_edit_mode, obj, "EDGE", loose_edges),
            ))
        if fins or bowties:
            problems = [f"{n} {label}" for n, label in (
                (len(fins), "edge(s) shared by 3+ faces"), (len(bowties), "vertex(es) joining surfaces at one point"),
            ) if n]
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' non-manifold: " + ", ".join(problems),
                object_name=obj.name,
                fix_hint="Separate or merge the overlapping parts (Select > All by Trait > Non Manifold)",
                check_name="manifold",
                select=partial(select_in_edit_mode, obj, "EDGE", fins) if fins
                else partial(select_in_edit_mode, obj, "VERT", bowties),
            ))

    return results
