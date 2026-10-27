[README.md](https://github.com/user-attachments/files/27019346/README.md)
# Blender Asset Validator

A Blender addon that validates 3D assets against configurable pipeline standards and exports them the way the target engine (Unreal, Unity, Godot) expects. Built as a Tech Artist pipeline tool for enforcing quality gates inside Blender.

![Blender](https://img.shields.io/badge/Blender-4.2%2B-orange?logo=blender) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) ![License](https://img.shields.io/badge/license-MIT-green)

---

## What it does

Runs a set of checks on mesh objects and reports errors and warnings in an N-panel. Export is blocked until all errors are resolved.

By default, each selected asset is exported to its own file, together with its LODs, collision meshes and sockets when the Engine uses them.

| Check | What it catches |
|---|---|
| **Naming** | Objects or mesh data that do not match the configured regex (default: PascalCase) |
| **Transforms** | Unapplied location, rotation, or scale |
| **Polycount** | Triangle count over the configured budget (default: 50 000) |
| **Ngons** | Faces with more than 4 vertices |
| **UVs** | Missing UV maps, overlapping UV islands |
| **Geometry cleanup** | Degenerate / zero-area faces that should be fixed before export |
| **Topology** | Edge-flow rules: poles with 6+ edges, 3/5-edge poles on smoothly curved areas (hard corners are fine), sliver triangles, warped quads |
| **Normals / manifold** | Faces facing the wrong way, closed parts facing inward, loose geometry, edges shared by 3+ faces |
| **Shading** | Hard edges off UV seams, GPU vertex cost |
| **Collisions** | Collision meshes named after a mesh that doesn't exist (they'd be left out) |
| **Materials** | Empty material slots, Image Texture nodes with no image or missing file |

Each failed check shows the offending object, a description of the problem, and a fix hint; many have **Fix** and **Show** (opens Edit Mode with the culprits selected). A warning that is fine for this asset can be **accepted** with the checkbox next to it: the reason is stored on the object and the report lists it as accepted. Errors can't be accepted.

---

## Installation

The addon is a Blender 4.2+ extension (`blender_manifest.toml`).

1. Download or clone this repository
2. Zip the `blender_asset_validator/` folder (or build it: `blender --command extension build --source-dir blender_asset_validator`)
3. In Blender: **Edit > Preferences > Get Extensions > ⌄ (top right) > Install from Disk** > select the zip

The panel appears in the **N-panel > Asset Validator** tab of any 3D Viewport.

---

## Usage

1. Open a `.blend` file with mesh objects
2. Press **N** in the 3D Viewport and click the **Asset Validator** tab
3. Pick the **Engine** (and a **Preset** if the platform needs one)
4. Click **Validate Asset** to run the checks, or tick **Step by Step** to review them in order
5. Fix any errors shown in the panel
6. Select the mesh assets you want to export
7. Click **Export**

The addon re-validates the export set before writing files.

With the default export settings, selecting `Chair`, `Table`, and `Lamp` will create:

- `//exports/Chair.fbx`
- `//exports/Table.fbx`
- `//exports/Lamp.fbx`

If `export.individual_files` is set to `false`, the addon exports one combined file instead.

### Engines

The **Engine** dropdown loads `config/engines/<engine>.json` on top of the default rules. It decides the file format, how LODs are laid out and which names are collision meshes or sockets. Collision meshes skip the render checks (materials, UVs, topology...) and are written in their asset's file; selected LODs and collisions are never exported on their own.

| Engine | File | LODs | Collision / sockets |
|---|---|---|---|
| Custom | FBX | not exported | none |
| Unreal | FBX, one per asset | Empty with `fbx_type = LodGroup` (an FBX LOD Group) over `Name_LOD0..n` | `UCX_`/`UBX_`/`USP_`/`UCP_Name[_NN]` (renamed after `Name_LOD0` on export), `SOCKET_` empties parented to the asset |
| Unity | FBX, one per asset | `Name_LOD0..n` side by side (Unity builds the LOD Group) | `UCX_Name[_NN]`, for an import script: Unity has no convention of its own |
| Godot | glTF binary (.glb) | not exported: Godot builds its own on import | `Name-colonly` / `Name-convcolonly` (`-col` meshes are regular assets) |

### Heatmaps

**Heatmap** colors the selected meshes by a metric (blue fine, red bad, gray not applicable): *Quad Warp* and *Triangle Quality*. It's a temporary color attribute (`AV_heat`) shown with Solid shading > Attribute; the ✕ button removes it, and Export strips it so it never reaches the engine.

### Batch validation (CI)

```powershell
blender -b --factory-startup --python blender_asset_validator/cli.py -- --engine unreal --report report.html a.blend b.blend
```

Validates every mesh in each file with the engine and preset saved in it (or the ones given), prints the report, writes a `.json` or `.html` report, and exits with 1 if any file has errors. `--factory-startup` keeps an installed copy of the addon from loading next to this one.

### Mesh optimization

All three work on the selected meshes and can be undone.

- **Generate LODs** bakes `_LOD1..n` meshes into the `LODs` collection, each one from the previous level: planar dissolve of flat areas, then a collapse to `ratio x` the source triangles that removes open borders, seams, UV/material borders and sharp edges last, then the source's normals are transferred. Set `lod.clean_topology` to run Clean Topology on every level (quads instead of triangles).
- **Clean Topology** edits the mesh in place without changing its shape or UVs: triangles to quads, flat edge loops dissolved (only whole loops on straight, flat strips, so quads stay quads), and the free vertices relaxed along the original surface for even edge flow. Borders, seams, sharp/hard edges and material borders are pinned. Relax is skipped on objects with a Subdivision/Multires modifier or shape keys. On a LOD it relaxes onto the full-resolution source.
- **Retopologize** creates `<name>_Retopo`, an all-quad mesh whose edge flow follows the curvature (Blender's QuadriFlow), and hides the original; the mesh must be manifold with consistent normals, otherwise it reports the failure and creates nothing. Materials, UVs and normals are resampled from the original and seams are marked at UV island borders; re-unwrap if the islands need to be cleaner. Triangle ratio and symmetry are in the redo panel (F9).

---

## Configuration

Rules are driven by `config/default.json`, with the Engine's `config/engines/<engine>.json`, the Preset's `config/presets/<preset>.json` and an optional `asset_validator.json` next to the .blend (the project's own rules) merged on top, in that order. Validate, Fix and Export all check the same objects, the ones Export would export (`export.use_selection` / `use_active_collection`). The buttons are disabled in Edit Mode.

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

- `format`: `fbx` or `gltf` (.glb)
- `path`: output folder
- `use_selection`: validate and export only selected mesh objects
- `use_active_collection`: use the active collection instead of selection
- `individual_files`: export one FBX per asset instead of one combined FBX

Topology angles are in degrees: `flat_angle` is the bend still treated as flat (dissolve), `feature_angle` the bend from which an edge counts as a hard edge (pinned, poles allowed), `quad_angle` the tolerance when joining triangles into quads. `min_triangle_quality` is 1 for an equilateral triangle.

`roles.collision` and `roles.socket` are regexes on object names; the collision one names the mesh it belongs to with a `(?P<owner>...)` group.

Two presets are included:

| Preset | Budget | Ngons |
|---|---|---|
| `mobile.json` | 5 000 triangles | not allowed |
| `cinematic.json` | 500 000 triangles | allowed |

---

## Adding a new check

Create a file in `checks/`, decorate the function with `@register_check`, and import it in `checks/__init__.py`. The engine will pick it up automatically. Checks run on assets and LODs; use `@register_check(roles=("asset", "lod", "collision"))` for one that also applies to collision meshes. Add it to a step in `core/steps.py` for the guided mode.

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
|-- __init__.py              # register/unregister
|-- blender_manifest.toml    # extension metadata (Blender 4.2+)
|-- cli.py                   # batch validation without the UI
|-- config/
|   |-- default.json         # Default rules and export settings
|   |-- engines/             # Unreal, Unity, Godot conventions
|   `-- presets/             # Platform / budget overrides
|-- core/
|   |-- registry.py          # @register_check decorator
|   |-- engine.py            # Loads config and runs checks
|   |-- roles.py             # asset / LOD / collision / socket, from the engine's name patterns
|   |-- steps.py             # Guided steps and per-object approvals
|   |-- waivers.py           # Accepted warnings
|   |-- result.py            # CheckResult dataclass + Severity enum
|   `-- state.py             # Shared validation results for UI/operators
|-- checks/
|   |-- naming.py            # Naming, collision owners
|   |-- transforms.py
|   |-- geometry.py          # Polycount, ngons, UV overlap, degenerate faces
|   |-- integrity.py         # Normals, manifold
|   |-- topology.py          # Edge-flow rules (poles, slivers, warped quads)
|   |-- shading.py           # Hard edges off seams, GPU vertex cost
|   `-- materials.py
|-- operations/
|   |-- cleanup.py           # Fixers
|   |-- heatmap.py           # Per-face heatmaps
|   |-- lod.py               # LOD baking
|   `-- topology.py          # Clean Topology, Retopologize, shared feature detection
|-- operators/
|   |-- validate.py, fix.py  # Validate, guided steps, Fix, Show, Accept
|   |-- heatmap.py
|   |-- lod.py, topology.py  # Generate LODs, Clean Topology, Retopologize
|   `-- export.py            # Per-engine export
|-- ui/
|   `-- panel.py             # N-panel UI
`-- report/
    `-- generator.py         # Console, JSON and HTML reports
```

---

## Development setup

The repo includes a `.vscode/settings.json` configured for the [Blender Development](https://marketplace.visualstudio.com/items?itemName=JacquesLucke.blender-development) extension. Install it, then use **Blender: Start** from the command palette to launch Blender with the addon loaded and auto-reloaded on save.

For IntelliSense on `bpy` and `bmesh`:

```bash
pip install fake-bpy-module-4.3
```

### Tests

`tests/check_*.py` build their own scenes and run headless in Blender (validation and export, LODs, topology, review regressions). From the repo root:

```powershell
.\tests\run.ps1                      # all checks
.\tests\run.ps1 check_topology       # just one
.\tests\run.ps1 -Blender "C:\path\to\blender.exe"
```

Blender is found via `-Blender`, `$env:BLENDER`, `blender` on PATH, or the Microsoft Store install. Results go to `tests/_out/`; the script exits 1 if any check fails or doesn't finish.

`tests/bench.py` times every check on 16k, 260k and 1M-triangle meshes (not run by `run.ps1`; see its header). The plan and its status are in [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## License

MIT
