"""Black-box confirmation: hit the deployed Supabase REST + Storage API with the
*anonymous* publishable key and see what actually answers.

Read probes are always safe. Write probes (opt-in) send a deliberately invalid
body so the row is rejected by schema validation *after* the permission check —
the HTTP status then tells us whether RLS would have allowed the write, without
ever creating a real row. The destructive probe (separately opt-in) does a real
insert followed by an immediate delete and shouts if cleanup fails.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import AuditConfig
from .model import Finding, Severity
from .static_checks import SENSITIVE_COL

# PostgREST error codes
_PERM_DENIED = {"42501"}          # insufficient_privilege -> RLS / grant blocked (good)
_SCHEMA_REJECT_STATUS = {400, 409, 422}  # body reached the table but was rejected on content


def _client(cfg: AuditConfig) -> httpx.Client:
    return httpx.Client(
        base_url=cfg.supabase_url,
        headers={"apikey": cfg.anon_key, "Authorization": f"Bearer {cfg.anon_key}"},
        timeout=cfg.timeout,
        follow_redirects=False,
    )


def _openapi_tables(cfg: AuditConfig, key: str) -> list[str]:
    """PostgREST root returns an OpenAPI doc listing every exposed table.

    Newer Supabase restricts this endpoint to *secret* keys, so we try the
    service key when we have one; the anon key still works on older projects.
    """
    if not key:
        return []
    try:
        with httpx.Client(base_url=cfg.supabase_url, timeout=cfg.timeout) as c:
            r = c.get("/rest/v1/", headers={"apikey": key, "Authorization": f"Bearer {key}"})
        if r.status_code != 200:
            return []
        data = r.json()
        defs = data.get("definitions") or {}
        paths = data.get("paths") or {}
        names = set(defs.keys())
        names |= {p.strip("/").split("/")[0] for p in paths if p.startswith("/") and p != "/"}
        return sorted(n for n in names if n and not n.startswith("(") and not n.startswith("rpc/"))
    except Exception:
        return []


def _tables_from_file(path) -> list[str]:
    try:
        return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    except Exception:
        return []


def run(cfg: AuditConfig, meta: dict[str, Any], known_tables: list[str] | None = None) -> list[Finding]:
    if not (cfg.do_probe and cfg.anon_key and cfg.supabase_url):
        return []

    findings: list[Finding] = []
    with _client(cfg) as cli:
        exposed = _openapi_tables(cfg, cfg.service_key or "") or _openapi_tables(cfg, cfg.anon_key or "")
        from_file = _tables_from_file(cfg.tables_file) if cfg.tables_file else []
        meta["postgrest_openapi_tables"] = exposed
        tables = sorted(set(exposed) | set(known_tables or []) | set(from_file))
        meta["probe_table_source"] = (
            "openapi" if exposed else "static" if known_tables else "tables-file" if from_file else "none"
        )
        if not tables:
            findings.append(Finding(
                code="probe.no_tables", severity=Severity.MEDIUM, category="probe",
                title="Live probe could not enumerate any tables",
                obj="rest",
                detail="The OpenAPI root needs a secret key (pass --service-key), the static pass did not "
                       "run (no --dsn), and no --tables-file was given. Nothing to probe.",
                remediation="Re-run with --service-key, or --dsn, or --tables-file listing table names.",
            ))

        anon_readable: list[str] = []
        anon_writable: list[str] = []
        anon_select_zero: list[str] = []

        for tbl in tables:
            rd = _probe_read(cli, tbl)
            if rd["verdict"] == "data":
                anon_readable.append(tbl)
                sev = Severity.CRITICAL if rd["sensitive"] else Severity.HIGH
                findings.append(Finding(
                    code="probe.anon_read", severity=sev, category="probe",
                    title=f"Anon can READ real rows from {tbl} over /rest/v1",
                    obj=f"public.{tbl}", confirmed=True,
                    detail=f"GET /rest/v1/{tbl}?limit=1 returned HTTP 200 with {rd['rows']} row(s) "
                           f"(visible count {rd.get('visible_count', '?')}) using only the publishable key."
                           + (f" Sensitive columns in the response: {', '.join(rd['sensitive'])}."
                              if rd["sensitive"] else ""),
                    remediation=f"Enable RLS on {tbl} and drop any permissive anon SELECT policy.",
                    evidence=rd,
                ))
            elif rd["verdict"] == "select_zero_rows":
                anon_select_zero.append(tbl)
                findings.append(Finding(
                    code="probe.anon_select_permitted", severity=Severity.LOW, category="probe",
                    title=f"Anon SELECT is permitted on {tbl} at the grant level (0 rows returned)",
                    obj=f"public.{tbl}", confirmed=True,
                    detail=f"GET /rest/v1/{tbl} returned HTTP 200 but an empty set. Either RLS is filtering "
                           "every row (safe) or the table is simply empty. The privilege-level GRANT to "
                           "anon still exists — add the static pass (--dsn) to see the RLS state.",
                    remediation=f"REVOKE SELECT ON {tbl} FROM anon;  (defence in depth) and confirm RLS is ON.",
                    evidence=rd,
                ))

            if cfg.do_write_probe:
                wr = _probe_write(cli, tbl, destructive=cfg.do_destructive)
                if wr["verdict"] == "allowed":
                    anon_writable.append(tbl)
                    findings.append(Finding(
                        code="probe.anon_write", severity=Severity.CRITICAL, category="probe",
                        title=f"Anon can WRITE to {tbl} over /rest/v1",
                        obj=f"public.{tbl}", confirmed=True,
                        detail=wr["detail"],
                        remediation=f"Enable RLS on {tbl}; drop permissive anon INSERT/UPDATE/DELETE policies.",
                        evidence=wr,
                    ))
                elif wr["verdict"] == "inserted":
                    findings.append(Finding(
                        code="probe.anon_write_row_created", severity=Severity.CRITICAL, category="probe",
                        title=f"Anon INSERT into {tbl} actually created a row",
                        obj=f"public.{tbl}", confirmed=True,
                        detail=wr["detail"],
                        remediation=f"Enable RLS on {tbl} immediately. " + wr.get("cleanup_note", ""),
                        evidence=wr,
                    ))

        meta["probe_anon_readable"] = anon_readable
        meta["probe_anon_writable"] = anon_writable
        meta["probe_anon_select_zero_rows"] = anon_select_zero

        findings += _probe_storage(cli, cfg, meta)
        findings += _probe_rpc(cli, meta)

    return findings


# ---------------------------------------------------------------------------

_SENS = SENSITIVE_COL


def _probe_read(cli: httpx.Client, tbl: str) -> dict:
    """Distinguish the three outcomes that matter:

      * ``data``            - HTTP 200 with at least one row  -> anon truly reads this table
      * ``select_zero_rows``- HTTP 200 but empty              -> grant exists, RLS may be filtering
      * ``blocked``         - 401/403/PGRST                   -> anon has no privilege (good)

    An RLS-denied SELECT returns *200 with an empty body*, not an error, so status
    alone is not enough.
    """
    out: dict[str, Any] = {"table": tbl, "verdict": "blocked", "status": None,
                           "rows": 0, "sensitive": [], "visible_count": None}
    try:
        r = cli.get(
            f"/rest/v1/{tbl}",
            params={"limit": 1},
            headers={"Accept": "application/json", "Prefer": "count=estimated"},
        )
    except Exception as exc:
        out["verdict"] = "error"
        out["error"] = repr(exc)
        return out
    out["status"] = r.status_code

    cr = r.headers.get("content-range") or ""
    if "/" in cr:
        tail = cr.rsplit("/", 1)[-1]
        out["visible_count"] = None if tail in ("*", "") else int(tail)

    if r.status_code != 200:
        code = None
        try:
            code = (r.json() or {}).get("code")
        except Exception:
            pass
        out["pg_code"] = code
        out["verdict"] = "not_exposed" if r.status_code == 404 else "blocked"
        return out

    try:
        body = r.json()
    except Exception:
        body = None
    if isinstance(body, list) and body:
        out["verdict"] = "data"
        out["rows"] = len(body)
        keys: set[str] = set()
        for row in body:
            if isinstance(row, dict):
                keys |= set(row.keys())
        out["sensitive"] = sorted(k for k in keys if _SENS.search(k))
    else:
        out["verdict"] = "select_zero_rows"
    return out


def _probe_write(cli: httpx.Client, tbl: str, destructive: bool) -> dict:
    """Send an empty object. 401/403 => blocked. 4xx schema error => RLS allowed it.
    201 => a row was created (only expected when the table has no NOT NULL columns)."""
    out: dict[str, Any] = {"table": tbl, "verdict": "blocked", "status": None}
    try:
        r = cli.post(
            f"/rest/v1/{tbl}",
            json={},
            headers={"Prefer": "return=representation", "Content-Type": "application/json"},
        )
    except Exception as exc:
        out["verdict"] = "error"
        out["detail"] = repr(exc)
        return out

    out["status"] = r.status_code
    code = None
    try:
        code = (r.json() or {}).get("code")
    except Exception:
        pass
    out["pg_code"] = code

    if r.status_code in (401, 403) or code in _PERM_DENIED:
        out["verdict"] = "blocked"
        out["detail"] = f"POST /rest/v1/{tbl} rejected with HTTP {r.status_code} (permission denied)."
    elif r.status_code == 201:
        out["verdict"] = "inserted"
        out["detail"] = (f"POST /rest/v1/{tbl} with an empty body returned 201 — the anon role may "
                         f"insert rows here.")
        _cleanup_inserted(cli, tbl, r, out)
    elif r.status_code in _SCHEMA_REJECT_STATUS:
        out["verdict"] = "allowed"
        out["detail"] = (f"POST /rest/v1/{tbl} passed the permission check and was rejected only on "
                         f"content (HTTP {r.status_code}, pg code {code}). RLS/grants would let the "
                         f"anon role write to this table.")
    else:
        out["verdict"] = "unclear"
        out["detail"] = f"POST /rest/v1/{tbl} returned HTTP {r.status_code} (pg code {code})."
    return out


def _cleanup_inserted(cli: httpx.Client, tbl: str, resp: httpx.Response, out: dict) -> None:
    try:
        body = resp.json()
        row = body[0] if isinstance(body, list) and body else None
        if not row:
            out["cleanup_note"] = "Could not read the created row back; delete it manually."
            return
        pk = next((k for k in ("id", "uuid", "uid") if k in row), None)
        if not pk:
            out["cleanup_note"] = f"Created row {row!r} — no obvious primary key; delete it manually."
            return
        d = cli.delete(f"/rest/v1/{tbl}", params={pk: f"eq.{row[pk]}"})
        out["cleanup_note"] = (f"Auto-deleted the test row ({pk}={row[pk]}, HTTP {d.status_code})."
                               if d.status_code in (200, 204)
                               else f"FAILED to delete test row {pk}={row[pk]} (HTTP {d.status_code}) — remove it manually.")
    except Exception as exc:  # noqa: BLE001
        out["cleanup_note"] = f"Cleanup errored: {exc!r} — check {tbl} for a stray empty row."


def _probe_storage(cli: httpx.Client, cfg: AuditConfig, meta: dict) -> list[Finding]:
    out: list[Finding] = []
    base = cfg.supabase_url.rstrip("/")
    try:
        r = cli.get(f"{base}/storage/v1/bucket")
    except Exception:
        return out
    if r.status_code == 200:
        try:
            buckets = [b.get("name") for b in r.json()]
        except Exception:
            buckets = []
        meta["probe_storage_buckets"] = buckets
        # Supabase always 200s this endpoint; an empty list means nothing is
        # actually disclosed. Only flag when bucket names come back.
        if buckets:
            out.append(Finding(
                code="probe.storage_bucket_list", severity=Severity.HIGH, category="probe",
                title="Anon can enumerate Storage buckets",
                obj="storage", confirmed=True,
                detail=f"GET /storage/v1/bucket returned {buckets} with only the publishable key.",
                remediation="Add an RLS policy on storage.buckets so the anon role sees nothing.",
                evidence={"buckets": buckets},
            ))
        for name in buckets:
            try:
                lr = cli.post(f"{base}/storage/v1/object/list/{name}", json={"prefix": "", "limit": 1})
            except Exception:
                continue
            if lr.status_code == 200:
                out.append(Finding(
                    code="probe.storage_object_list", severity=Severity.HIGH, category="probe",
                    title=f"Anon can list objects in bucket '{name}'",
                    obj=f"storage:{name}", confirmed=True,
                    detail=f"POST /storage/v1/object/list/{name} returned HTTP 200 for an anonymous caller.",
                    remediation=f"Make '{name}' private and restrict the storage.objects SELECT policy.",
                ))
    return out


def _probe_rpc(cli: httpx.Client, meta: dict) -> list[Finding]:
    """Try the SECURITY DEFINER RPCs the static pass flagged (passed via meta)."""
    out: list[Finding] = []
    for fn in meta.get("rpc_candidates", []):
        try:
            r = cli.post(f"/rest/v1/rpc/{fn}", json={})
        except Exception:
            continue
        if r.status_code in (200, 204):
            out.append(Finding(
                code="probe.rpc_executed", severity=Severity.HIGH, category="probe",
                title=f"Anon successfully executed SECURITY DEFINER RPC {fn}()",
                obj=f"rpc:{fn}", confirmed=True,
                detail=f"POST /rest/v1/rpc/{fn} returned HTTP {r.status_code} for an anonymous caller.",
                remediation=f"REVOKE EXECUTE ON FUNCTION public.{fn} FROM anon;",
            ))
        elif r.status_code in (400, 404) and "PGRST202" not in r.text:
            out.append(Finding(
                code="probe.rpc_reachable", severity=Severity.MEDIUM, category="probe",
                title=f"SECURITY DEFINER RPC {fn}() is reachable by anon (rejected on args)",
                obj=f"rpc:{fn}", confirmed=True,
                detail=f"POST /rest/v1/rpc/{fn} returned HTTP {r.status_code}; the function is exposed "
                       "and only argument validation stopped the call.",
                remediation=f"REVOKE EXECUTE ON FUNCTION public.{fn} FROM anon, authenticated;",
            ))
    return out
