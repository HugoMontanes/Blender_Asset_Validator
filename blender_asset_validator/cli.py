"""Batch validation without the UI, for CI or a whole folder of assets:

    blender -b --factory-startup --python <addon folder>/cli.py -- [--engine unreal] [--preset mobile]
        [--report out.json | out.html] [a.blend b.blend ...]

Validates every mesh of each .blend's scene (or of the .blend Blender was
opened with), with the engine and preset saved in it unless given. Exits
with 1 if any file has errors. --factory-startup keeps an
installed copy of the addon from loading next to this one."""
import argparse
import importlib
import sys
from pathlib import Path

if __name__ == "__main__" and not globals().get("__package__"):  # run as a script: import the addon as a package (PEP 366)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = Path(__file__).resolve().parent.name
    importlib.import_module(__package__)

import bpy

from .core.engine import ENGINE_ITEMS, PRESET_ITEMS, load_config, run_validation
from .report.generator import file_report, generate_report, write_report


def main(argv) -> int:
    parser = argparse.ArgumentParser(prog="cli.py", description="Validate .blend files with the Asset Validator rules")
    parser.add_argument("--engine", choices=[item[0] for item in ENGINE_ITEMS], help="default: the one saved in each .blend")
    parser.add_argument("--preset", choices=[item[0] for item in PRESET_ITEMS], help="default: the one saved in each .blend")
    parser.add_argument("--report", help="write the results to this .json or .html file")
    parser.add_argument("files", nargs="*", help=".blend files (default: the one Blender opened)")
    args = parser.parse_args(argv)

    files = args.files or ([bpy.data.filepath] if bpy.data.filepath else [])
    if not files:
        parser.error("no .blend given and Blender was started without one")

    reports = []
    for path in files:
        if Path(path).resolve() != Path(bpy.data.filepath or ".").resolve():
            bpy.ops.wm.open_mainfile(filepath=str(path))
        scene = bpy.context.scene
        if args.engine:
            scene.asset_validator_engine = args.engine
        if args.preset:
            scene.asset_validator_preset = args.preset
        print(f"\n### {path}")
        results = run_validation(load_config(), [o for o in scene.objects if o.type == "MESH"])
        generate_report(results)
        reports.append(file_report(str(path), scene.asset_validator_engine, scene.asset_validator_preset, results))

    if args.report:
        write_report(args.report, reports)
        print(f"Report written to {args.report}")
    failed = [r["file"] for r in reports if not r["passed"]]
    print(f"{len(reports) - len(failed)} of {len(reports)} file(s) passed" + (": failed " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    importlib.import_module(__package__).register()
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
