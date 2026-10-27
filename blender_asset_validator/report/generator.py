import html
import json
from datetime import datetime
from pathlib import Path
from typing import List

from ..core.result import CheckResult, Severity


def generate_report(results: List[CheckResult]) -> str:
    errors = [r for r in results if r.severity == Severity.ERROR]
    warnings = [r for r in results if r.severity == Severity.WARNING and r.waived is None]
    accepted = [r for r in results if r.waived is not None]
    infos = [r for r in results if r.severity == Severity.INFO]

    lines = [
        "=" * 60,
        f"  ASSET VALIDATOR REPORT  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        f"  Errors:   {len(errors)}",
        f"  Warnings: {len(warnings)}",
        f"  Accepted: {len(accepted)}",
        f"  Info:     {len(infos)}",
        "-" * 60,
    ]

    for result in results:
        prefix = "[ACC]" if result.waived is not None else {"ERROR": "[ERR]", "WARNING": "[WRN]", "INFO": "[INF]"}.get(result.severity.value, "[???]")
        obj_tag = f"  obj='{result.object_name}'" if result.object_name else ""
        lines.append(f"{prefix} [{result.check_name}]{obj_tag}")
        lines.append(f"      {result.message}")
        if result.waived is not None:
            lines.append(f"      accepted: {result.waived}")
        elif result.fix_hint:
            lines.append(f"      → {result.fix_hint}")

    lines.append("=" * 60)
    status = "PASSED" if not errors else "FAILED"
    lines.append(f"  STATUS: {status}")
    lines.append("=" * 60)

    report_text = "\n".join(lines)
    print(report_text)
    return report_text


def file_report(path: str, engine: str, preset: str, results: List[CheckResult]) -> dict:
    """One .blend's results as plain data, for write_report."""
    errors = sum(r.severity == Severity.ERROR for r in results)
    return {
        "file": path,
        "engine": engine,
        "preset": preset,
        "passed": not errors,
        "errors": errors,
        "warnings": sum(r.severity == Severity.WARNING and r.waived is None for r in results),
        "accepted": sum(r.waived is not None for r in results),
        "results": [
            {
                "severity": r.severity.value,
                "check": r.check_name,
                "object": r.object_name,
                "message": r.message,
                "fix_hint": r.fix_hint,
                "accepted": r.waived,
            }
            for r in results
        ],
    }


def write_report(path: str, reports: List[dict]) -> None:
    """JSON, or an HTML table when `path` ends in .html."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in (".html", ".htm"):
        out.write_text(_html(reports), encoding="utf-8")
    else:
        out.write_text(json.dumps({"generated": datetime.now().isoformat(timespec="seconds"), "files": reports}, indent=2), encoding="utf-8")


def _html(reports: List[dict]) -> str:
    e = html.escape
    sections = []
    for rep in reports:
        rows = "".join(
            f"<tr class='{'accepted' if r['accepted'] is not None else r['severity'].lower()}'><td>{e(r['severity'])}</td>"
            f"<td>{e(r['check'])}</td><td>{e(r['object'] or '')}</td><td>{e(r['message'])}</td>"
            f"<td>{e(r['accepted'] if r['accepted'] is not None else r['fix_hint'] or '')}</td></tr>"
            for r in rep["results"]
        )
        sections.append(
            f"<h2>{e(rep['file'])} — {'PASSED' if rep['passed'] else 'FAILED'}</h2>"
            f"<p>Engine {e(rep['engine'])}, preset {e(rep['preset'])}: {rep['errors']} error(s), "
            f"{rep['warnings']} warning(s), {rep['accepted']} accepted</p>"
            f"<table><tr><th>Severity</th><th>Check</th><th>Object</th><th>Message</th><th>Fix / accepted because</th></tr>{rows}</table>"
        )
    return (
        "<!doctype html><meta charset='utf-8'><title>Asset Validator report</title><style>"
        "body{font-family:sans-serif;margin:16px}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;vertical-align:top}"
        ".error{background:#fdd}.warning{background:#ffd}.accepted{color:#888}</style>"
        f"<h1>Asset Validator report</h1><p>{datetime.now().isoformat(timespec='seconds')}</p>" + "".join(sections)
    )
