import json
from datetime import datetime
from pathlib import Path
from typing import List

import bpy

from ..core.result import CheckResult, Severity


def generate_report(results: List[CheckResult], output_path: str = None) -> str:
    errors = [r for r in results if r.severity == Severity.ERROR]
    warnings = [r for r in results if r.severity == Severity.WARNING]
    infos = [r for r in results if r.severity == Severity.INFO]

    lines = [
        "=" * 60,
        f"  ASSET VALIDATOR REPORT  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        f"  Errors:   {len(errors)}",
        f"  Warnings: {len(warnings)}",
        f"  Info:     {len(infos)}",
        "-" * 60,
    ]

    for result in results:
        prefix = {"ERROR": "[ERR]", "WARNING": "[WRN]", "INFO": "[INF]"}.get(result.severity.value, "[???]")
        obj_tag = f"  obj='{result.object_name}'" if result.object_name else ""
        lines.append(f"{prefix} [{result.check_name}]{obj_tag}")
        lines.append(f"      {result.message}")
        if result.fix_hint:
            lines.append(f"      → {result.fix_hint}")

    lines.append("=" * 60)
    status = "PASSED" if not errors else "FAILED"
    lines.append(f"  STATUS: {status}")
    lines.append("=" * 60)

    report_text = "\n".join(lines)
    print(report_text)

    if output_path:
        _write_json(results, output_path)

    return report_text


def _write_json(results: List[CheckResult], output_path: str) -> None:
    data = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "errors": sum(1 for r in results if r.severity == Severity.ERROR),
            "warnings": sum(1 for r in results if r.severity == Severity.WARNING),
            "infos": sum(1 for r in results if r.severity == Severity.INFO),
        },
        "results": [
            {
                "severity": r.severity.value,
                "check": r.check_name,
                "object": r.object_name,
                "message": r.message,
                "fix_hint": r.fix_hint,
            }
            for r in results
        ],
    }
    path = Path(bpy.path.abspath(output_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
