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
| **Transforms** | Unapplied location, rotation, or scale; a warning on parented parts whose link the export drops (each asset in its own file, the parent not exported, or an Unreal LOD group in its place) |
| **Polycount** | Triangle count over the configured budget (default: 50 000) |
| **Ngons** | Faces with more than 4 vertices |
| **UVs** | Missing UV maps, overlapping UV0 islands |
| **UV layout** | UV0 islands off the profile's texel density (px/m at `uv.texture_size`, ±`texel_tolerance`), islands that stretch (area or angles), islands closer than `min_island_gap_px` to another (colours bleed in the mipmaps; measured on the texture's pixel grid), islands outside 0–1 (tiling materials and UDIM tiles allowed). Also reports each object's median texel density |
| **Lightmap UV** | UV1 (the lightmap channel in Unreal and Unity) with overlapping faces or outside 0–1; a missing UV1 only when `uv.require_lightmap` is set. **Fix** rebuilds UV1 with Lightmap Pack and leaves UV0 alone |
| **Geometry cleanup** | Degenerate / zero-area faces that should be fixed before export |
| **Topology** | Edge-flow rules: poles with 6+ edges, 3/5-edge poles on smoothly curved areas (hard corners are fine), sliver triangles, warped quads |
| **Normals / manifold** | Faces facing against most of their part, closed parts facing inward (by signed volume), loose geometry, edges shared by 3+ faces |
| **Shading** | Hard edges off UV seams, GPU vertex cost |
| **Mid-poly** | Assets without a Weighted Normal modifier, only when `hard_surface.require_weighted_normal` is set. **Fix** adds one |
| **Collisions** | Collision meshes named after a mesh that doesn't exist (they'd be left out) |
| **Bake pairs** | High-poly meshes (`_high`) with no low-poly to bake onto: a typo, or an asset whose name happens to end in the suffix (it would be left out of the checks and the export) |
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

**Heatmap** colors the selected meshes by a metric (blue fine, red bad, gray not applicable): *Quad Warp*, *Triangle Quality*, *Texel Density* (too dense or too sparse against the target) and *UV Stretch*. It's a temporary color attribute (`AV_heat`) shown with Solid shading > Attribute; the ✕ button removes it, and Export strips it so it never reaches the engine.

### Hard surface and UV tools

All three rewrite UV0 of the selected meshes, so they belong before baking or texturing. That is also why the UV layout warnings have no **Fix**: Fix All would repack the UVs of an asset that is already textured and break its textures. Selected LODs and collision meshes are skipped: a LOD shares its asset's texture.

- **Hard Surface Prep** runs the whole low-poly setup in one click: smooth shading with every edge bent more than *Sharp Angle* (`topology.feature_angle`) marked sharp, keeping the ones already marked; Auto Unwrap, which puts the seams on those sharp edges; the profile's texel density, when it has one; and a Weighted Normal modifier (Keep Sharp, pinned last in the stack) so big flat faces shade flat. *Bevel Sharp Edges* (redo panel) is the mid-poly option: the sharp edges become bevel weight 1 and a Bevel modifier with *Segments* rounds them. They stop being sharp, because the Bevel would copy the sharp flag onto the borders of the chamfer and shade it faceted. For the same reason Prep removes a *Smooth by Angle* modifier (Shade Auto Smooth): the marked sharp edges do its job. Both modifiers stay live to tweak; an object that already has a Weighted Normal, or a Bevel limited by weight, doesn't get a second one, and a Weighted Normal added by hand is pinned last too. The chamfer faces take their UVs from the faces beside them, squeezed (30–37% less area on a cube): fine for tiling and trim textures, the usual mid-poly case.
- **Auto Unwrap** (hard surface): seams on edges marked sharp (or, if none are marked, edges bent more than `topology.feature_angle`), on material borders and open borders; unwrap with Minimum Stretch where Blender has it (4.3+, otherwise Conformal; islands Minimum Stretch collapses to zero area get Conformal) and the `uv_importance` vertex group as weights if the object has one; every island that still stretches past the limits is cut along its most bent path of edges (concave ones first, where the seam hides) and only those islands are unwrapped again; then packed to fill 0–1 with the profile's margin (dense layouts end up with less margin; the gap check says so). Made for hard surface: on organic or scanned meshes the angle seams give thousands of small islands. *Straighten Quad Islands* (redo panel) runs Follow Active Quads on islands made only of quads.
- **Set Texel Density** scales every island to one density (the profile's, or the one typed in the redo panel) and packs them without rescaling; it says so when they don't fit in one texture. *Copy from Active* gives the other selected meshes the active object's density.

### Baking

High-poly meshes pair with their low-poly asset by name, the way Substance Painter's *match by mesh name* does it (case-sensitive): `Chair` or `Chair_low` bakes from `Chair_high`, `Chair_high_bolts`, `Chair_high.001`... (`bake.low_suffix` / `bake.high_suffix`). High meshes skip every check (one with no low gets a *Bake pairs* warning), are never exported to the engine, and Prep, the UV tools and Generate LODs leave them alone. Retopologize still works on them: that's how a low is made from a sculpt.

- **Bake Normals** bakes a tangent-space normal map from each selected asset's high meshes into its UV0 with Cycles, and saves it as `<name>_N.png` (Non-Color, `uv.texture_size`) in `bake.path` (`//bakes/`). The cage and the ray distance are measured, not guessed: the high's vertices are measured against the low's surface, the cage extrusion covers the farthest point outside it and the rays reach the deepest point inside (plus a 10% margin). The green channel follows the Engine (`bake.normal_g`: DirectX `NEG_Y` for Unreal, OpenGL `POS_Y` otherwise), and the padding is half of `uv.min_island_gap_px`, so the paddings of two islands meet in the middle of the gap. One image per low, shared by all its materials; baking again overwrites it. A high that isn't on top of its low (half its vertices farther than 10% of the low's size, e.g. a low laid beside it) is refused instead of baked through a cage metres thick. Bake onto a clean UV0: islands that overlap (the *UVs* check) share their texels.
- **Export Bake Pairs** writes the selected assets to `<name>_low.fbx`, renamed `X_low`, and their high meshes to `<name>_high.fbx`, for baking in Substance Painter or Marmoset Toolbag with matching by name. A dot after the suffix becomes `_` (Painter pairs `Chair_high_001` but not `Chair_high.001`), and the scene names are put back afterwards.

Both add a Triangulate modifier to the low first (keeping custom normals, before a pinned Weighted Normal), so the baker and the engine see the same triangles: each one triangulates a non-planar quad its own way, and the tangent basis changes with the diagonal.

### Batch validation (CI)

```powershell
blender -b --factory-startup --python blender_asset_validator/cli.py -- --engine unreal --report report.html [--jobs 4] a.blend b.blend
```

Validates every mesh in each file with the engine and preset saved in it (or the ones given), prints the report, writes a `.json` or `.html` report, and exits with 1 if any file has errors. `--factory-startup` keeps an installed copy of the addon from loading next to this one.

Several files are validated at once, each in its own background Blender: `--jobs N` (default: half the logical cores, about one per physical core; each Blender holds its whole scene in memory, so lower it for heavy scenes). The checks are single-threaded Python and Blender's data isn't thread-safe, which is why it's processes, not threads. The reports and the console output keep the order of the files, and a file whose Blender dies (a corrupt .blend) fails on its own without stopping the others. `--jobs 1` validates them one after another in the same Blender.

### Mesh optimization

All three work on the selected meshes and can be undone.

- **Generate LODs** bakes `_LOD1..n` meshes of the selected assets (not of LODs, collision or high-poly meshes) into the `LODs` collection, each one from the previous level: planar dissolve of flat areas, then a collapse to `ratio x` the source triangles that removes open borders, seams and UV/material borders last, then loose geometry and stray flipped faces are cleaned (they would block the export) and the source's normals are transferred, hard edges included. Hard edges aren't protected on their own: on a game mesh they sit on UV seams, and protecting them as well folded the mesh into edges with 3+ faces. Set `lod.clean_topology` to run Clean Topology on every level (quads instead of triangles).
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
  "uv": {
    "texture_size": 2048,
    "texel_density": 512,
    "texel_tolerance": 0.2,
    "max_area_stretch": 0.3,
    "max_angle_stretch": 10.0,
    "min_island_gap_px": 8,
    "tiling_materials": "(?i)(tiling|tileable|trim)",
    "require_lightmap": false
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

UV checks measure UV0 (the first UV map, the one the engine's materials sample) against a `texture_size` px texture: `texel_density` is the target in px per metre (0 = no target; 512 is common for indie/PC, 1024 for AAA), `max_area_stretch` the fraction a face's UV scale may differ from its island's, `max_angle_stretch` the mean corner angle error in degrees. Islands of a material whose name matches `tiling_materials` repeat on purpose: they may leave 0–1 and are left out of the gap check. On a material with a UDIM image, an island only has to stay inside one tile.

`hard_surface.require_weighted_normal` makes a missing Weighted Normal modifier an error, for mid-poly projects (bevelled edges shaded by face-weighted normals instead of a baked normal map). Generated LODs are exempt: their normals are baked in.

`roles.collision` and `roles.socket` are regexes on object names; the collision one names the mesh it belongs to with a `(?P<owner>...)` group.

`bake.normal_g` is the normal map's green channel (`POS_Y` OpenGL, `NEG_Y` DirectX; the Unreal profile sets it), `bake.path` the folder for the baked maps and the bake pair files.

Two presets are included:

| Preset | Budget | Ngons | Texel density |
|---|---|---|---|
| `mobile.json` | 5 000 triangles | not allowed | 256 px/m at 1024 px, 4 px gaps |
| `cinematic.json` | 500 000 triangles | allowed | 1024 px/m at 4096 px, 16 px gaps |

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
|   |-- roles.py             # asset / LOD / collision / socket / high, from the name patterns
|   |-- steps.py             # Guided steps and per-object approvals
|   |-- waivers.py           # Accepted warnings
|   |-- result.py            # CheckResult dataclass + Severity enum
|   `-- state.py             # Shared validation results for UI/operators
|-- checks/
|   |-- naming.py            # Naming, collision owners
|   |-- transforms.py
|   |-- geometry.py          # Polycount, ngons, degenerate faces
|   |-- integrity.py         # Normals, manifold
|   |-- topology.py          # Edge-flow rules (poles, slivers, warped quads)
|   |-- shading.py           # Hard edges off seams, GPU vertex cost, mid-poly Weighted Normal
|   |-- uvs.py               # UV overlap, texel density, stretch, gaps, 0-1, lightmap UV
|   `-- materials.py
|-- operations/
|   |-- bake.py              # Measured cage and ray distances, normal map bake, Triangulate
|   |-- cleanup.py           # Fixers
|   |-- hard_surface.py      # Hard Surface Prep, Bevel and Weighted Normal modifiers
|   |-- heatmap.py           # Per-face heatmaps
|   |-- lod.py               # LOD baking
|   |-- topology.py          # Clean Topology, Retopologize, shared feature detection
|   `-- uvs.py               # UV islands and their metrics, Set Texel Density, lightmap UV, Auto Unwrap
|-- operators/
|   |-- validate.py, fix.py  # Validate, guided steps, Fix, Show, Accept
|   |-- heatmap.py
|   |-- lod.py, topology.py  # Generate LODs, Clean Topology, Retopologize
|   |-- uvs.py               # Auto Unwrap, Set Texel Density
|   |-- hard_surface.py      # Hard Surface Prep
|   |-- bake.py              # Bake Normals
|   `-- export.py            # Per-engine export, Export Bake Pairs
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

`tests/check_*.py` build their own scenes and run headless in Blender (validation and export, LODs, topology, UVs, hard surface, baking, review regressions). `check_scene.py` also opens a real scene that is not committed: `Addon_Test.blend` at the repo root, or the one in `$env:AV_SCENE` (skipped if it's missing, never saved). From the repo root:

```powershell
.\tests\run.ps1                      # all checks
.\tests\run.ps1 check_topology       # just one
.\tests\run.ps1 -Blender "C:\path\to\blender.exe"
```

Blender is found via `-Blender`, `$env:BLENDER`, `blender` on PATH, the Microsoft Store install, or `Program Files\Blender Foundation`. Results go to `tests/_out/`; the script exits 1 if any check fails or doesn't finish.

`tests/bench.py` times every check on 16k, 260k and 1M-triangle meshes (not run by `run.ps1`; see its header). The plan and its status are in [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## License

MIT
