# Blender Asset Validator Project Guide

This document explains the project in plain language for someone who understands Blender but does not yet know how Blender addons are structured or how this addon works internally.

## 1. What this addon is for

The addon checks 3D assets before export.

In a production pipeline, artists often need to follow rules such as:

- Object names must follow a naming convention.
- Meshes must stay under a triangle budget.
- UVs must exist and should not overlap.
- Materials and textures must be assigned correctly.
- Transforms should be applied before export.

This addon automates those checks inside Blender so the user can catch problems early. It also blocks FBX export if there are validation errors.

## 2. What a Blender addon is

A Blender addon is a Python package that Blender can load.

At a high level, an addon usually contains:

- `bl_info`: metadata Blender shows in the Add-ons window.
- `register()` / `unregister()`: functions Blender calls when the addon is enabled or disabled.
- Operators: actions the user can run, like pressing a button.
- Panels: UI elements shown in Blender.
- Supporting code: business logic, data models, utilities, configuration files.

In this project, the addon lives in the `blender_asset_validator/` folder.

## 3. How the project is organized

The project is split into a few clear layers:

- `__init__.py`
  This is the addon entry point. It defines `bl_info`, imports the check modules, and registers the Blender classes.

- `checks/`
  This folder contains the validation rules. Each file defines one or more checks.

- `core/`
  This is the internal engine. It loads config, stores results, and runs the registered checks.

- `operators/`
  These are Blender actions. One operator validates the scene. Another validates and exports to FBX.

- `ui/`
  This contains the panel shown in Blender's N-panel.

- `report/`
  This generates a text report and can also write JSON output.

- `config/`
  This contains the default validation rules and optional presets.

## 4. What happens when Blender loads the addon

When Blender enables the addon:

1. Blender imports `blender_asset_validator/__init__.py`.
2. That file imports `checks/`.
3. Importing `checks/` imports each check module such as `naming.py`, `transforms.py`, `geometry.py`, and `materials.py`.
4. Each check function is decorated with `@register_check`.
5. The decorator adds the function to the internal check registry.
6. `register()` registers the Blender UI panel and operators.

That means the checks are "discovered" at import time rather than by scanning files dynamically.

## 5. The most important project idea: checks are plugins

Each validation rule is just a Python function with a consistent shape:

```python
@register_check
def check_something(objects, config):
    results = []
    ...
    return results
```

The function receives:

- `objects`: the mesh objects that should be validated.
- `config`: the JSON configuration already loaded into Python.

The function returns a list of `CheckResult` objects.

This is a good design because new checks are easy to add without changing the validation engine.

## 6. How validation works

The validation flow is handled mainly by `core/engine.py`.

### Config loading

`load_config()` reads `config/default.json`.

`load_preset()` starts from the default config and applies preset overrides on top of it. The project now merges nested dictionaries correctly, which means a preset can override only one part of a section without deleting the rest of that section's defaults.

### Running checks

`run_validation()` gathers the mesh objects to validate and then runs every registered check one by one.

If one check crashes, the engine catches the exception and converts it into a validation error instead of breaking the whole addon. That is important in tools meant for artists because one broken rule should not destroy the whole workflow.

## 7. What a validation result looks like

`core/result.py` defines:

- `Severity`
  The result level: `INFO`, `WARNING`, or `ERROR`.

- `CheckResult`
  A small data object containing:
  - severity
  - message
  - object name
  - fix hint
  - check name

This keeps the check code simple. Every check just creates consistent result objects and the UI/report systems can render them however they want.

## 8. What each current check does

### `checks/naming.py`

Validates object names and mesh-data names against a regex pattern from config.

Why this matters:

- consistent naming helps exports, automation, and downstream tools
- regex makes the rule customizable per team

### `checks/transforms.py`

Checks whether location, rotation, and scale are applied.

Why this matters:

- unapplied transforms often cause export problems
- collision, animation, and placement tools usually assume normalized transforms

### `checks/geometry.py`

This file contains several geometry-related checks:

- `check_polycount`
  Counts triangles and compares them to a budget.

- `check_ngons`
  Warns when faces have more than four vertices if ngons are not allowed.

- `check_uvs`
  Verifies that a UV map exists and tries to detect overlapping UVs.

- `check_degenerate_faces`
  Flags zero-area faces that should be cleaned before export.

Why these matter:

- geometry cost affects runtime performance
- ngons can triangulate unpredictably
- broken UVs affect texturing and baking
- degenerate faces can create export or shading issues

### `checks/materials.py`

Checks:

- objects without material slots
- empty material slots
- image texture nodes without assigned images
- texture references that point to missing files

Why this matters:

- materials and textures are a common source of broken assets
- a path existing in Blender is not enough; the file also needs to exist on disk or be packed into the blend file

## 9. How the UI works

The main UI lives in `ui/panel.py`.

It creates a panel in:

- `View3D`
- sidebar / N-panel
- tab name: `Asset Validator`

The panel does three main things:

1. Shows a `Validate Asset` button.
2. Shows a summary of errors and warnings after validation.
3. Lists the results grouped by check name.

If there are errors, the export button is disabled in the UI.

## 10. How the operators work

Operators are Blender commands that can be triggered by buttons or menus.

### `operators/validate.py`

This operator:

1. loads config
2. runs validation
3. stores results in shared state
4. generates a text report
5. refreshes the 3D view panel

### `operators/export.py`

This operator:

1. loads config
2. determines which objects are actually going to be exported
3. validates that same object set
4. blocks export if errors exist
5. exports to FBX if validation passes

A useful improvement in the current project is that export validation now follows export scope more closely. For example, if export is configured to use selected objects, the validator now checks the selected mesh objects instead of unrelated meshes elsewhere in the scene.

Another important behavior is naming and file splitting:

- when `individual_files` is enabled, each mesh asset is exported as its own FBX file
- each exported file uses the Blender object name
- invalid filename characters are sanitized so exports still succeed on Windows
- the addon temporarily changes selection during export, then restores the user's original selection

## 11. Why `core/state.py` exists

Blender UI panels do not automatically "remember" the output of a previous operator run.

This project uses a simple shared module-level state to store the latest validation results. The validate operator writes into it, and the UI panel reads from it.

This is a lightweight pattern and works well for a small addon.

## 12. How reporting works

`report/generator.py` builds a plain text report from all `CheckResult` objects.

It:

- counts errors, warnings, and infos
- prints a readable report to Blender's console
- can optionally write a JSON report file

This is useful because the same validation data can feed:

- the Blender UI
- the console
- future automation or CI-style exports via JSON

## 13. How configuration works

The addon is rule-driven rather than hardcoded.

That means most thresholds and behaviors live in JSON:

- naming regex
- triangle budget
- whether ngons are allowed
- whether UVs are required
- transform thresholds
- material requirements
- FBX export settings

Some especially useful export settings are:

- `path`
  The output folder for exported FBX files.

- `use_selection`
  Export only the currently selected mesh objects.

- `use_active_collection`
  Export mesh objects from the active collection.

- `individual_files`
  Export one FBX per mesh asset instead of one combined FBX.

This is a strong design choice because different projects can have different needs without rewriting Python code.

## 14. Why presets matter

Presets in `config/presets/` let you adjust the base rules for different project types.

Examples:

- a mobile project may need a very low triangle budget
- a cinematic project may allow much higher detail and ngons

This turns one addon into a reusable pipeline tool instead of a one-project script.

## 15. Design strengths of the project

The project already has several good architectural decisions:

- checks are modular and easy to extend
- results are represented with a clear shared data model
- the UI is separated from the validation engine
- config is externalized into JSON
- export is guarded by validation
- failures inside a check do not crash the whole tool

These are exactly the kinds of patterns that make pipeline tools maintainable.

## 16. Improvements that were important during review

The review highlighted a few practical issues worth understanding:

- Check registry duplication on reload
  Blender addon development often reloads Python modules. If the registry stores duplicate functions every time a module reloads, results can appear multiple times. The registry now keys checks by module and function name to avoid that.

- Shallow preset merging
  A top-level `dict.update()` is not enough for nested config. Deep merging is safer because it preserves unspecified defaults.

- Export validation scope
  Validation should match what will be exported. Otherwise unrelated scene assets can incorrectly block export.

- Export naming
  Using the `.blend` file name alone is not ideal for asset exports. The exporter now names files from the Blender object name so the output matches the artist's selected asset.

- Texture path verification
  A texture node may still contain a filepath string even when the file is gone on disk. The material check now verifies the resolved file path more carefully.

- Degenerate geometry
  Zero-area faces are now explicitly checked because they can cause real production issues.

## 17. Good next checks to add later

If you want to extend the addon further, these would be valuable next checks:

- Non-manifold geometry
  Useful for 3D printing, boolean workflows, and some game pipelines.

- Doubled or loose geometry
  Can catch loose vertices, loose edges, or duplicate vertices after bad merges.

- Missing or invalid custom normals
  Helpful when a project depends on weighted normals or imported shading data.

- Material-count budget
  Useful in real-time pipelines where too many materials on one asset is expensive.

- UV set count
  Some pipelines require exactly one UV set, or exactly two for lightmaps.

- Object origin rules
  Helpful when assets must pivot from the ground center or world origin.

- Modifier policy
  Some teams require modifiers to be applied before export, while others require specific ones to stay live.

- Collection or export naming rules
  Useful when export tools or build scripts depend on scene organization.

## 18. How to add a new check

To add a new check:

1. Create a new file in `checks/` or add a function to an existing check file.
2. Decorate the function with `@register_check`.
3. Return a list of `CheckResult` objects.
4. Import that file in `checks/__init__.py`.
5. Add any new config options to `config/default.json`.

That is all the engine needs.

## 19. How to think about this project as a beginner

If you are new to Blender addons, the easiest mental model is:

- Blender UI button calls an operator.
- The operator calls the validation engine.
- The engine runs small independent rule functions.
- Each rule returns structured results.
- The UI and reports display those results.

So the project is not "one big Blender script." It is a small application with:

- an entry point
- a plugin system for checks
- a validation engine
- a UI
- reporting
- configuration

That is why it scales better than a quick one-file script.

## 20. Suggested learning order

If you want to understand the codebase step by step, read files in this order:

1. `blender_asset_validator/__init__.py`
2. `blender_asset_validator/ui/panel.py`
3. `blender_asset_validator/operators/validate.py`
4. `blender_asset_validator/core/engine.py`
5. `blender_asset_validator/core/result.py`
6. `blender_asset_validator/checks/naming.py`
7. `blender_asset_validator/checks/transforms.py`
8. `blender_asset_validator/checks/geometry.py`
9. `blender_asset_validator/checks/materials.py`
10. `blender_asset_validator/report/generator.py`

That reading order follows the user journey from clicking a button to seeing results.

## 21. Final summary

This addon is already a solid small pipeline tool.

Its main purpose is to stop bad assets before export, and its architecture is built around modular checks plus a small validation engine. That makes it a very good learning project for Blender addon structure, technical art tooling, and Python-based pipeline automation.
