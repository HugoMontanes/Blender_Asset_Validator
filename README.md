[README.md](https://github.com/user-attachments/files/26985949/README.md)
# Blender Asset Validator

A Blender addon that validates 3D assets against configurable pipeline standards before exporting to FBX. Built as a Tech Artist pipeline tool — the kind of thing you'd write to enforce quality gates across a production team.

![Blender](https://img.shields.io/badge/Blender-4.0%2B-orange?logo=blender) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) ![License](https://img.shields.io/badge/license-MIT-green)

---

## What it does

Runs a set of checks on every mesh object in the scene and reports errors and warnings in an N-panel. Export to FBX is blocked until all errors are resolved.

| Check | What it catches |
|---|---|
| **Naming** | Objects or mesh data that don't match the configured regex (default: PascalCase) |
| **Transforms** | Unapplied location, rotation, or scale |
| **Polycount** | Triangle count over the configured budget (default: 50 000) |
| **Ngons** | Faces with more than 4 vertices |
| **UVs** | Missing UV maps, overlapping UV islands |
| **Materials** | Empty material slots, Image Texture nodes with no image or missing file |

Each failed check shows the offending object, a description of the problem, and a fix hint.

---

## Installation

1. Download or clone this repository
2. Zip the `blender_asset_validator/` folder
3. In Blender: **Edit → Preferences → Add-ons → Install** → select the zip
4. Enable **Object: Asset Validator**

The panel appears in the **N-panel → Asset Validator** tab of any 3D Viewport.

---

## Usage

1. Open a `.blend` file with mesh objects
2. Press **N** in the 3D Viewport and click the **Asset Validator** tab
3. Click **Validate Asset** — results appear grouped by check type
4. Fix any errors (warnings are non-blocking)
5. Click **Export FBX** — the addon re-validates before exporting and writes the file to the path configured in `default.json` (default: `//exports/<filename>.fbx`)

---

## Configuration

Rules are driven by `config/default.json`. Edit it directly or drop a preset into `config/presets/` and load it via `engine.load_preset("preset_name")`.

```json
{
  "naming": {
    "pattern": "^[A-Z][a-zA-Z0-9_]+$",
    "description": "PascalCase — starts with uppercase, letters/numbers/underscores only"
  },
  "geometry": {
    "max_triangles": 50000,
    "allow_ngons": false,
    "check_uvs": true
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
    "axis_forward": "-Z",
    "axis_up": "Y"
  }
}
```

Two presets are included:

| Preset | Budget | Ngons |
|---|---|---|
| `mobile.json` | 5 000 triangles | not allowed |
| `cinematic.json` | 500 000 triangles | allowed |

---

## Adding a new check

Create a file in `checks/`, decorate the function with `@register_check`, and import it in `checks/__init__.py`. That's it — the engine picks it up automatically.

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

```
blender_asset_validator/
├── __init__.py              # bl_info, register/unregister
├── config/
│   ├── default.json         # Default rules (budgets, naming, export settings)
│   └── presets/             # Per-project overrides (mobile, cinematic, ...)
├── core/
│   ├── registry.py          # @register_check decorator
│   ├── engine.py            # Loads config, discovers and runs checks
│   ├── result.py            # CheckResult dataclass + Severity enum
│   └── state.py             # Module-level results store shared by operator and panel
├── checks/
│   ├── naming.py
│   ├── transforms.py
│   ├── geometry.py          # Polycount, ngons, UV overlap
│   └── materials.py
├── operators/
│   ├── validate.py          # ASSET_VALIDATOR_OT_validate
│   └── export.py            # ASSET_VALIDATOR_OT_export_fbx
├── ui/
│   └── panel.py             # N-panel: results grouped by check, export button
└── report/
    └── generator.py         # Console report + optional JSON output
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
