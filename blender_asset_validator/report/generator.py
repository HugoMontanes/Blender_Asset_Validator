from datetime import datetime
from typing import List

from ..core.result import CheckResult, Severity


def generate_report(results: List[CheckResult]) -> str:
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
    return report_text

