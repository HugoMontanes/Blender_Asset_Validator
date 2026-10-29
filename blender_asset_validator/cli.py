"""Batch validation without the UI, for CI or a whole folder of assets:

    blender -b --factory-startup --python <addon folder>/cli.py -- [--engine unreal] [--preset mobile]
        [--report out.json | out.html] [--jobs N] [a.blend b.blend ...]

Validates every mesh of each .blend's scene (or of the .blend Blender was
opened with), with the engine and preset saved in it unless given. Exits
with 1 if any file has errors. --factory-startup keeps an
installed copy of the addon from loading next to this one. Several files
are validated at once, each in its own background Blender (--jobs)."""
import argparse
import importlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if __name__ == "__main__" and not globals().get("__package__"):  # run as a script: import the addon as a package (PEP 366)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = Path(__file__).resolve().parent.name
    importlib.import_module(__package__)

import bpy

from .core.engine import ENGINE_ITEMS, PRESET_ITEMS, load_config, run_validation
from .core.result import CheckResult, Severity
from .report.generator import file_report, generate_report, write_report


def main(argv) -> int:
    parser = argparse.ArgumentParser(prog="cli.py", description="Validate .blend files with the Asset Validator rules")
    parser.add_argument("--engine", choices=[item[0] for item in ENGINE_ITEMS], help="default: the one saved in each .blend")
    parser.add_argument("--preset", choices=[item[0] for item in PRESET_ITEMS], help="default: the one saved in each .blend")
    parser.add_argument("--report", help="write the results to this .json or .html file")
    # Half the logical cores: about one per physical core, and every Blender holds a whole scene in memory
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2),
                        help="files validated at once, each in its own background Blender (default: half the logical "
                             "cores; 1 = one after another in this Blender)")
    parser.add_argument("files", nargs="*", help=".blend files (default: the one Blender opened)")
    args = parser.parse_args(argv)

    files = args.files or ([bpy.data.filepath] if bpy.data.filepath else [])
    if not files:
        parser.error("no .blend given and Blender was started without one")

    reports = None
    if args.jobs > 1 and len(files) > 1:
        try:
            reports = _validate_in_parallel(files, args)
        except OSError as e:  # this Blender's binary can't be started again from a script
            print(f"Can't start a background Blender ({e}): validating one file at a time")
    if reports is None:
        reports = [_validate_here(path, args) for path in files]

    if args.report:
        write_report(args.report, reports)
        print(f"Report written to {args.report}")
    failed = [r["file"] for r in reports if not r["passed"]]
    print(f"{len(reports) - len(failed)} of {len(reports)} file(s) passed" + (": failed " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0


def _validate_here(path, args) -> dict:
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
    return file_report(str(path), scene.asset_validator_engine, scene.asset_validator_preset, results)


def _validate_in_parallel(files, args) -> list:
    """Each file in its own background Blender, this script with that file alone: the checks are
    single-threaded Python and bpy isn't thread-safe, so processes are what use the other cores.
    The threads only wait for them. Reports and console output come back in the files' order."""
    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(min(args.jobs, len(files))) as pool:
        jobs = [pool.submit(_validate_in_child, path, args, Path(tmp) / str(i)) for i, path in enumerate(files)]
        reports = []
        for job in jobs:
            report, output = job.result()
            print(output)
            reports.append(report)
        return reports


def _validate_in_child(path, args, stem: Path):
    """(file report, its console section). A Blender that dies before writing its report, on a
    corrupt .blend say, fails that file and leaves the others alone."""
    report, log = stem.with_suffix(".json"), stem.with_suffix(".log")
    command = [bpy.app.binary_path, "-b", "--factory-startup", "--python-exit-code", "2", "--python", __file__,
               "--", "--jobs", "1", "--report", str(report)]
    if args.engine:
        command.append(f"--engine={args.engine}")
    if args.preset:
        command.append(f"--preset={args.preset}")
    command.append(str(path))
    with open(log, "w", encoding="utf-8") as out:
        code = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT).returncode
    text = log.read_text(encoding="utf-8", errors="replace")
    if report.exists():
        section = text[text.find("\n### "):].split("\nReport written to")[0]  # without Blender's start-up lines
        return json.loads(report.read_text(encoding="utf-8"))["files"][0], section
    crash = CheckResult(Severity.ERROR, f"Blender exited with code {code} before writing a report (a corrupt .blend?)", check_name="cli")
    return file_report(str(path), args.engine or "", args.preset or "", [crash]), f"\n### {path}\n{text[-2000:]}"


if __name__ == "__main__":
    importlib.import_module(__package__).register()
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
