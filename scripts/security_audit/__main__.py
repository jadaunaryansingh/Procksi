"""CLI entry point.

    python -m scripts.security_audit [options]

Runs three passes and merges their findings:
  * static  — reads the Postgres catalogs as the service role (needs --dsn / DATABASE_URL)
  * probe   — hits /rest/v1 and /storage/v1 as the anon key to confirm findings
  * auth    — inspects API keys / sample JWTs, optional Management API + signup probe

Exit code is 2 when any finding is at or above --fail-level (default HIGH), else 0.
"""

from __future__ import annotations

import argparse
import sys
import traceback

from . import __version__
from .config import build_config
from .model import AuditReport, Finding, Severity
from .report import render_console, write_outputs


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scripts.security_audit", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env-file", action="append", metavar="PATH",
                   help="extra .env file to read (repeatable). Defaults to the backend/*/.env set.")
    p.add_argument("--dsn", help="Postgres connection string (overrides DATABASE_URL).")
    p.add_argument("--supabase-url", help="https://<ref>.supabase.co")
    p.add_argument("--anon-key", help="publishable / anon key for the live probe.")
    p.add_argument("--service-key", help="service-role key (only used to clean up the signup probe).")
    p.add_argument("--sb-access-token", help="Supabase personal access token for the Management API check.")
    p.add_argument("--no-static", action="store_true",
                   help="skip the Postgres catalog pass even if a DSN is available (black-box mode).")
    p.add_argument("--tables-file", metavar="PATH",
                   help="newline-separated table names to probe when the OpenAPI root is not reachable.")
    p.add_argument("--schemas", default="public", help="comma-separated schemas to audit (default: public).")
    p.add_argument("--admin-emails", default="",
                   help="comma-separated allowlist; auth users with role metadata NOT in this list are flagged.")
    p.add_argument("--no-probe", action="store_true", help="skip the live anon REST/storage probe.")
    p.add_argument("--write-probe", action="store_true",
                   help="also test write permission per table with an invalid body (no real rows created).")
    p.add_argument("--destructive", action="store_true",
                   help="with --write-probe, allow a real insert+delete round-trip where a table permits it.")
    p.add_argument("--signup-probe", action="store_true",
                   help="register a throwaway auth user (role=admin metadata) then delete it (needs --service-key).")
    p.add_argument("--sample-jwt", action="append", metavar="TOKEN",
                   help="a real user access token to inspect (repeatable).")
    p.add_argument("--json", metavar="PATH", help="write the full report as JSON.")
    p.add_argument("--md", metavar="PATH", help="write the full report as Markdown.")
    p.add_argument("--fail-level", default="HIGH",
                   choices=[s.name for s in Severity], help="exit 2 if any finding is >= this (default HIGH).")
    p.add_argument("--timeout", type=float, default=20.0, help="per-request / connect timeout seconds.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cfg = build_config(args)

    report = AuditReport()
    report.meta["auditor_version"] = __version__
    report.meta["config_sources"] = cfg.sources
    report.meta["env_files_used"] = cfg.env_files_used

    if not cfg.dsn and not (cfg.anon_key and cfg.supabase_url):
        print("nothing to do: need either --dsn (static) or --supabase-url + --anon-key (probe).",
              file=sys.stderr)
        return 1

    # 1. static -----------------------------------------------------------
    if cfg.dsn:
        try:
            from . import static_checks
            report.extend(static_checks.run(cfg, report.meta))
        except Exception as exc:  # noqa: BLE001
            report.add(Finding(
                code="static.crash", severity=Severity.MEDIUM, category="exposure",
                title=f"Static pass crashed: {exc}", obj="database",
                detail="".join(traceback.format_exc()), remediation="Check the DSN / DB reachability.",
            ))

    # feed the anon-executable SECURITY DEFINER RPCs the static pass flagged into the probe
    report.meta["rpc_candidates"] = sorted({
        f.evidence["name"]
        for f in report.findings
        if f.code == "functions.security_definer_public"
        and isinstance(f.evidence, dict)
        and f.evidence.get("anon_exec")
        and f.evidence.get("name")
    })

    known_tables = [
        f.obj.split(".", 1)[1] for f in report.findings
        if f.category == "rls" and f.obj.startswith(tuple(s + "." for s in cfg.schemas))
    ]

    # 2. probe ----------------------------------------------------------
    if cfg.do_probe:
        try:
            from . import probe_checks
            report.extend(probe_checks.run(cfg, report.meta, known_tables=known_tables))
        except Exception as exc:  # noqa: BLE001
            report.add(Finding(
                code="probe.crash", severity=Severity.LOW, category="probe",
                title=f"Live probe crashed: {exc}", obj="rest",
                detail="".join(traceback.format_exc()), remediation="",
            ))

    # 3. auth / jwt ---------------------------------------------------------
    try:
        from . import auth_checks
        report.extend(auth_checks.run(cfg, report.meta))
    except Exception as exc:  # noqa: BLE001
        report.add(Finding(
            code="auth.crash", severity=Severity.LOW, category="auth",
            title=f"Auth pass crashed: {exc}", obj="auth",
            detail="".join(traceback.format_exc()), remediation="",
        ))

    # Write files first so a console-rendering hiccup never loses the report.
    write_outputs(report, cfg)
    try:
        render_console(report, cfg)
    except Exception as exc:  # noqa: BLE001 - never fail the run over terminal encoding
        print(f"(console render skipped: {exc}); see --md / --json output", file=sys.stderr)

    for f in report.sorted():
        if f.code.endswith(".crash"):
            print(f"\n[{f.severity.label}] {f.title}\n{f.detail}", file=sys.stderr)

    return 2 if report.worst() >= cfg.fail_level else 0


if __name__ == "__main__":
    raise SystemExit(main())
