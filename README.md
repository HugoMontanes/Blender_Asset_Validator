[README.md](https://github.com/user-attachments/files/27019346/README.md)
# Blender Asset Validator

A Blender addon that validates 3D assets against configurable pipeline standards before exporting to FBX. Built as a Tech Artist pipeline tool for enforcing quality gates inside Blender.

![Blender](https://img.shields.io/badge/Blender-4.0%2B-orange?logo=blender) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) ![License](https://img.shields.io/badge/license-MIT-green)

---

## What it does

Runs a set of checks on mesh objects and reports errors and warnings in an N-panel. Export to FBX is blocked until all errors are resolved.

By default, selected mesh objects are exported as separate FBX files named after each object.

| Check | What it catches |
|---|---|
| **Naming** | Objects or mesh data that do not match the configured regex (default: PascalCase) |
| **Transforms** | Unapplied location, rotation, or scale |
| **Polycount** | Triangle count over the configured budget (default: 50 000) |
| **Ngons** | Faces with more than 4 vertices |
| **UVs** | Missing UV maps, overlapping UV islands |
| **Geometry cleanup** | Degenerate / zero-area faces that should be fixed before export |
| **Topology** | Edge-flow rules: poles with 6+ edges, 3/5-edge poles on smoothly curved areas (hard corners are fine), sliver triangles |
| **Materials** | Empty material slots, Image Texture nodes with no image or missing file |

Each failed check shows the offending object, a description of the problem, and a fix hint.

---

## Installation

1. Download or clone this repository
2. Zip the `blender_asset_validator/` folder
3. In Blender: **Edit > Preferences > Add-ons > Install** > select the zip
4. Enable **Object: Asset Validator**

The panel appears in the **N-panel > Asset Validator** tab of any 3D Viewport.

---

## Usage

1. Open a `.blend` file with mesh objects
2. Press **N** in the 3D Viewport and click the **Asset Validator** tab
3. Click **Validate Asset** to run the checks
4. Fix any errors shown in the panel
5. Select the mesh assets you want to export
6. Click **Export FBX**

The addon re-validates the export set before writing files.

With the default export settings, selecting `Chair`, `Table`, and `Lamp` will create:

- `//exports/Chair.fbx`
- `//exports/Table.fbx`
- `//exports/Lamp.fbx`

If `export.individual_files` is set to `false`, the addon exports one combined FBX instead.

### Mesh optimization

All three work on the selected meshes and can be undone.

- **Generate LODs** bakes `_LOD1..n` meshes into the `LODs` collection, each one from the previous level: planar dissolve of flat areas, then a collapse to `ratio x` the source triangles that removes open borders, seams, UV/material borders and sharp edges last, then the source's normals are transferred. Set `lod.clean_topology` to run Clean Topology on every level (quads instead of triangles).
- **Clean Topology** edits the mesh in place without changing its shape or UVs: triangles to quads, flat edge loops dissolved (only whole loops on straight, flat strips, so quads stay quads), and the free vertices relaxed along the original surface for even edge flow. Borders, seams, sharp/hard edges and material borders are pinned. Relax is skipped on objects with a Subdivision/Multires modifier or shape keys. On a LOD it relaxes onto the full-resolution source.
- **Retopologize** creates `<name>_Retopo`, an all-quad mesh whose edge flow follows the curvature (Blender's QuadriFlow), and hides the original; the mesh must be manifold with consistent normals, otherwise it reports the failure and creates nothing. Materials, UVs and normals are resampled from the original and seams are marked at UV island borders; re-unwrap if the islands need to be cleaner. Triangle ratio and symmetry are in the redo panel (F9).

---

## Configuration

Rules are driven by `config/default.json`. Edit it directly, or drop a preset into `config/presets/` and pick it in the panel's **Preset** dropdown: its values are merged on top of `default.json`. Validate, Fix and Export all check the same objects, the ones Export would export (`export.use_selection` / `use_active_collection`). The buttons are disabled in Edit Mode.

```json
{
  "naming": {
    "pattern": "^[A-Z][a-zA-Z0-9_]+$",
    "description": "PascalCase - starts with uppercase, letters/numbers/underscores only"
  },
  "geometry": {
    "max_triangles": 50000,
    "allow_ngons": false,
    "check_uvs": true,
    "check_degenerate_faces": true,
    "degenerate_face_area_epsilon": 1e-10
  },
  "transforms": {
    "check_location": true,
    "check_rotation": true,
    "check_scale": true
  },
  "materials": {
    "require_material": true,
    "check_textures": true
  },
  "topology": {
    "check_topology": true,
    "max_pole_valence": 5,
    "pole_curvature_angle": 10.0,
    "min_triangle_quality": 0.1,
    "flat_angle": 1.0,
    "feature_angle": 30.0,
    "quad_angle": 40.0,
    "relax_iterations": 5,
    "relax_factor": 0.5
  },
  "lod": {
    "clean_topology": false,
    "levels": [{"suffix": "_LOD1", "ratio": 0.5}, {"suffix": "_LOD2", "ratio": 0.25}, {"suffix": "_LOD3", "ratio": 0.1}]
  },
  "export": {
    "path": "//exports/",
    "axis_forward": "X",
    "axis_up": "Y",
    "use_selection": true,
    "use_active_collection": false,
    "individual_files": true
  }
}
```

Key export options:

- `path`: output folder for FBX files
- `use_selection`: validate and export only selected mesh objects
- `use_active_collection`: use the active collection instead of selection
- `individual_files`: export one FBX per asset instead of one combined FBX

Topology angles are in degrees: `flat_angle` is the bend still treated as flat (dissolve), `feature_angle` the bend from which an edge counts as a hard edge (pinned, poles allowed), `quad_angle` the tolerance when joining triangles into quads. `min_triangle_quality` is 1 for an equilateral triangle.

Two presets are included:

| Preset | Budget | Ngons |
|---|---|---|
| `mobile.json` | 5 000 triangles | not allowed |
| `cinematic.json` | 500 000 triangles | allowed |

---

## Adding a new check

Create a file in `checks/`, decorate the function with `@register_check`, and import it in `checks/__init__.py`. The engine will pick it up automatically.

```python
# checks/my_check.py
from ..core.registry import register_check
from ..core.result import CheckResult, Severity

@register_check
def check_something(objects, config):
    results = []
    for obj in objects:
        if some_condition(obj):
            results.append(CheckResult(
                severity=Severity.WARNING,
                message=f"'{obj.name}' has a problem",
                object_name=obj.name,
                fix_hint="Here is how to fix it",
                check_name="my_check",
            ))
    return results
```

```python
# checks/__init__.py
from . import naming, transforms, geometry, materials, my_check
```

---

## Project structure

```text
blender_asset_validator/
|-- __init__.py              # bl_info, register/unregister
|-- config/
|   |-- default.json         # Default rules and export settings
|   `-- presets/             # Per-project overrides
|-- core/
|   |-- registry.py          # @register_check decorator
|   |-- engine.py            # Loads config and runs checks
|   |-- result.py            # CheckResult dataclass + Severity enum
|   `-- state.py             # Shared validation results for UI/operators
|-- checks/
|   |-- naming.py
|   |-- transforms.py
|   |-- geometry.py          # Polycount, ngons, UV overlap, degenerate faces
|   |-- topology.py          # Edge-flow rules (poles, slivers)
|   `-- materials.py
|-- operations/
|   |-- lod.py               # LOD baking
|   `-- topology.py          # Clean Topology, Retopologize, shared feature detection
|-- operators/
|   |-- validate.py          # Validate operator
|   |-- lod.py, topology.py  # Generate LODs, Clean Topology, Retopologize
|   `-- export.py            # FBX export operator with per-asset export support
|-- ui/
|   `-- panel.py             # N-panel UI
`-- report/
    `-- generator.py         # Console report + optional JSON output
```

---

## Development setup

The repo includes a `.vscode/settings.json` configured for the [Blender Development](https://marketplace.visualstudio.com/items?itemName=JacquesLucke.blender-development) extension. Install it, then use **Blender: Start** from the command palette to launch Blender with the addon loaded and auto-reloaded on save.

For IntelliSense on `bpy` and `bmesh`:

```bash
pip install fake-bpy-module-4.3
```

---

## License

MIT
