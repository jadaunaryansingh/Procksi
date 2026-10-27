"""Render an :class:`AuditReport` to the console, Markdown and JSON."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .model import SEV_COLOUR, AuditReport, Severity

# Windows terminals default to cp1252; box-drawing / status glyphs then crash the
# writer. Force a UTF-8-safe console and fall back to ASCII box characters.
_console = Console(safe_box=True, legacy_windows=False)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def render_console(report: AuditReport, cfg) -> None:
    counts = report.counts()
    _console.rule("[bold]Procksi database security audit")
    _console.print(
        f"[dim]{_now()}  project={cfg.project_ref or '?'}  "
        f"schemas={','.join(cfg.schemas)}  "
        f"modes=static:{'on' if cfg.dsn else 'off'} "
        f"probe:{'on' if cfg.do_probe else 'off'} "
        f"write-probe:{'on' if cfg.do_write_probe else 'off'} "
        f"signup-probe:{'on' if cfg.do_signup_probe else 'off'}[/dim]"
    )

    summary = Table(show_header=True, header_style="bold")
    summary.add_column("severity")
    summary.add_column("count", justify="right")
    for sev in sorted(Severity, reverse=True):
        summary.add_row(f"[{SEV_COLOUR[sev]}]{sev.label}[/]", str(counts[sev]))
    _console.print(summary)

    t = Table(show_header=True, header_style="bold", show_lines=False, expand=True)
    t.add_column("sev", no_wrap=True)
    t.add_column("cat", no_wrap=True)
    t.add_column("object", no_wrap=True, max_width=32, overflow="fold")
    t.add_column("finding", overflow="fold")
    t.add_column("live", no_wrap=True)
    for f in report.sorted():
        t.add_row(
            f"[{SEV_COLOUR[f.severity]}]{f.severity.label}[/]",
            f.category,
            f.obj,
            f.title,
            "yes" if f.confirmed else "",
        )
    _console.print(t)

    worst = report.worst()
    verdict_colour = SEV_COLOUR.get(worst, "dim")
    _console.print(
        f"\nWorst severity: [{verdict_colour}]{worst.label}[/]  "
        f"(fails at {cfg.fail_level.label})"
    )


def to_markdown(report: AuditReport, cfg) -> str:
    counts = report.counts()
    lines: list[str] = []
    lines.append("# Procksi database security audit\n")
    lines.append(f"- **Run (UTC):** {_now()}")
    lines.append(f"- **Project:** `{cfg.project_ref or '?'}`  ")
    lines.append(f"- **Schemas:** `{', '.join(cfg.schemas)}`")
    lines.append(
        f"- **Modes:** static `{'on' if cfg.dsn else 'off'}`, "
        f"anon-probe `{'on' if cfg.do_probe else 'off'}`, "
        f"write-probe `{'on' if cfg.do_write_probe else 'off'}`, "
        f"signup-probe `{'on' if cfg.do_signup_probe else 'off'}`"
    )
    if report.meta.get("tables_scanned") is not None:
        lines.append(f"- **Tables scanned:** {report.meta['tables_scanned']}")
    if report.meta.get("auth_users"):
        au = report.meta["auth_users"]
        lines.append(
            f"- **auth.users:** {au.get('total')} total, {au.get('unconfirmed')} unconfirmed, "
            f"{au.get('last7')} new in 7d, {au.get('last24')} in 24h"
        )
    lines.append("")
    lines.append("## Summary\n")
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    for sev in sorted(Severity, reverse=True):
        lines.append(f"| {sev.label} | {counts[sev]} |")
    lines.append(f"\n**Worst severity: {report.worst().label}**  (CI fails at {cfg.fail_level.label})\n")

    cur = None
    for f in report.sorted():
        if f.severity != cur:
            cur = f.severity
            lines.append(f"\n## {cur.label}\n")
        live = " _(confirmed live)_" if f.confirmed else ""
        lines.append(f"### [{f.category}] {f.title}{live}\n")
        lines.append(f"- **Object:** `{f.obj}`")
        lines.append(f"- **Code:** `{f.code}`")
        lines.append(f"- **Detail:** {f.detail}")
        if f.remediation:
            lines.append(f"- **Fix:** {f.remediation}")
        if f.evidence not in (None, {}, [], ""):
            ev = json.dumps(f.evidence, indent=2, default=str)
            if len(ev) > 4000:
                ev = ev[:4000] + "\n… (truncated)"
            lines.append(f"\n```json\n{ev}\n```")
        lines.append("")
    return "\n".join(lines)


def to_json(report: AuditReport, cfg) -> str:
    payload = {
        "run_utc": _now(),
        "project_ref": cfg.project_ref,
        "schemas": cfg.schemas,
        "modes": {
            "static": bool(cfg.dsn),
            "probe": cfg.do_probe,
            "write_probe": cfg.do_write_probe,
            "destructive": cfg.do_destructive,
            "signup_probe": cfg.do_signup_probe,
        },
        "meta": report.meta,
        "summary": {s.label: report.counts()[s] for s in sorted(Severity, reverse=True)},
        "worst_severity": report.worst().label,
        "findings": [
            {
                "code": f.code,
                "severity": f.severity.label,
                "category": f.category,
                "title": f.title,
                "object": f.obj,
                "detail": f.detail,
                "remediation": f.remediation,
                "confirmed_live": f.confirmed,
                "evidence": f.evidence,
            }
            for f in report.sorted()
        ],
    }
    return json.dumps(payload, indent=2, default=str)


def write_outputs(report: AuditReport, cfg) -> None:
    if cfg.md_out:
        Path(cfg.md_out).write_text(to_markdown(report, cfg), encoding="utf-8")
        _console.print(f"[green]wrote[/] {cfg.md_out}")
    if cfg.json_out:
        Path(cfg.json_out).write_text(to_json(report, cfg), encoding="utf-8")
        _console.print(f"[green]wrote[/] {cfg.json_out}")
