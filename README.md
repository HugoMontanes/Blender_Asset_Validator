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

---

## Configuration

Rules are driven by `config/default.json`. Edit it directly or drop a preset into `config/presets/` and load it via `engine.load_preset("preset_name")`.

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
|   `-- materials.py
|-- operators/
|   |-- validate.py          # Validate operator
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
