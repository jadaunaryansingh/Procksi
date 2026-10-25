"""Configuration-level checks: read the Postgres catalogs as the service role and
reason about RLS, policies, grants, functions, views, storage and auth.users.

Every finding here is inference from configuration. The live probe module
(:mod:`probe_checks`) confirms the exploitable ones against the real API.
"""

from __future__ import annotations

import re
from typing import Any

from .config import AuditConfig
from .db import connect, parse_pg_roles, q, q1
from .model import Finding, Severity

EXPOSED_ROLES = {"anon", "authenticated", "public"}
WRITE_CMDS = {"INSERT", "UPDATE", "DELETE", "ALL"}
OPEN_EXPR = {"", "true", "(true)"}

SENSITIVE_COL = re.compile(
    r"(pass(word|wd)?|pwd|passphrase|secret|(^|_)token($|_)|refresh_token|access_token|"
    r"api[_-]?key|client_secret|private[_-]?key|\bsalt\b|_hash$|^hash$|password_hash|"
    r"\botp\b|\bcvv\b|\bssn\b|aadha?ar|bank_acc|card_number)",
    re.I,
)

# ---------------------------------------------------------------------------
# Catalog queries
# ---------------------------------------------------------------------------

SQL_TABLES = """
select n.nspname as schema, c.relname as name,
       c.relrowsecurity as rls_enabled,
       c.relforcerowsecurity as rls_forced,
       c.relkind as kind
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = any(%s) and c.relkind in ('r','p','v','m')
order by 1, 2;
"""

SQL_POLICIES = """
select schemaname as schema, tablename as name, policyname,
       permissive, roles::text as roles, cmd,
       coalesce(qual, '') as using_expr,
       coalesce(with_check, '') as check_expr
from pg_policies
where schemaname = any(%s)
order by 1, 2, 3;
"""

SQL_TABLE_GRANTS = """
select table_schema as schema, table_name as name, grantee, privilege_type
from information_schema.role_table_grants
where table_schema = any(%s) and grantee in ('anon','authenticated','PUBLIC')
order by 1, 2;
"""

SQL_SENSITIVE_COLS = """
select table_schema as schema, table_name as name, column_name, data_type
from information_schema.columns
where table_schema = any(%s)
order by 1, 2, ordinal_position;
"""

SQL_FUNCTIONS = """
select n.nspname as schema, p.proname as name,
       p.prosecdef as security_definer,
       pg_get_userbyid(p.proowner) as owner,
       l.lanname as language,
       has_function_privilege('anon', p.oid, 'EXECUTE') as anon_exec,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') as auth_exec,
       pg_get_function_identity_arguments(p.oid) as args
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
join pg_language l on l.oid = p.prolang
where n.nspname = any(%s)
order by 1, 2;
"""

SQL_VIEWS = """
select n.nspname as schema, c.relname as name,
       pg_get_userbyid(c.relowner) as owner,
       (select option_value
          from pg_options_to_table(c.reloptions)
         where option_name = 'security_invoker') as security_invoker
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind in ('v','m') and n.nspname = any(%s);
"""

SQL_ROLE_ATTRS = """
select rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolreplication
from pg_roles
where rolname in ('anon','authenticated','service_role','authenticator','postgres');
"""

SQL_ROLE_MEMBERSHIP = """
select r.rolname as role, m.rolname as member_of
from pg_auth_members am
join pg_roles r on r.oid = am.member
join pg_roles m on m.oid = am.roleid
where r.rolname in ('anon','authenticated','authenticator');
"""

SQL_SCHEMA_USAGE = """
select nspname,
       has_schema_privilege('anon', oid, 'USAGE') as anon_usage,
       has_schema_privilege('authenticated', oid, 'USAGE') as auth_usage
from pg_namespace
where nspname not like 'pg\\_%' and nspname not in ('information_schema')
order by nspname;
"""

SQL_STORAGE_BUCKETS = "select id, name, public, created_at from storage.buckets order by name;"

SQL_STORAGE_POLICIES = """
select policyname, cmd, roles::text as roles,
       coalesce(qual,'') as using_expr, coalesce(with_check,'') as check_expr
from pg_policies
where schemaname = 'storage' and tablename = 'objects';
"""

SQL_STORAGE_OBJECTS_RLS = """
select coalesce(bool_and(c.relrowsecurity), false) as rls_enabled
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'storage' and c.relname = 'objects';
"""

SQL_AUTH_META = """
select id::text, email, created_at, last_sign_in_at,
       (email_confirmed_at is not null) as confirmed,
       raw_user_meta_data->>'role'      as um_role,
       raw_app_meta_data->>'role'       as am_role,
       (raw_user_meta_data ? 'is_admin')  as um_is_admin,
       (raw_user_meta_data ? 'isAdmin')   as um_isAdmin,
       (raw_user_meta_data ? 'claims')    as um_claims,
       (raw_user_meta_data ? 'user_role') as um_user_role
from auth.users
where raw_user_meta_data ?| array['role','is_admin','isAdmin','claims','user_role','app_metadata','permissions']
   or raw_app_meta_data->>'role' is not null
order by created_at desc
limit 200;
"""

SQL_AUTH_TOTALS = """
select count(*) as total,
       count(*) filter (where email_confirmed_at is null) as unconfirmed,
       count(*) filter (where created_at > now() - interval '7 days') as last7,
       count(*) filter (where created_at > now() - interval '24 hours') as last24
from auth.users;
"""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _exposed_roles(roles: list[str]) -> list[str]:
    return [r for r in roles if r in EXPOSED_ROLES]


def _grant_map(rows: list[dict]) -> dict[tuple[str, str], dict[str, set[str]]]:
    out: dict[tuple[str, str], dict[str, set[str]]] = {}
    for r in rows:
        key = (r["schema"], r["name"])
        g = r["grantee"].lower() if r["grantee"] != "PUBLIC" else "public"
        out.setdefault(key, {}).setdefault(g, set()).add(r["privilege_type"].upper())
    return out


def _is_open(expr: str) -> bool:
    return expr.strip().lower() in OPEN_EXPR


def _refs_auth_uid(*exprs: str) -> bool:
    blob = " ".join(exprs).lower()
    return "auth.uid()" in blob or "auth.jwt()" in blob or "current_setting('request.jwt" in blob


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------

def run(cfg: AuditConfig, meta: dict[str, Any]) -> list[Finding]:
    if not cfg.dsn:
        return [Finding(
            code="static.skipped", severity=Severity.INFO, category="exposure",
            title="Static catalog checks skipped — no database DSN available",
            obj="database",
            detail="Pass --dsn or set DATABASE_URL / SECURITY_AUDIT_DSN so the auditor "
                   "can read pg_policies, grants, functions and storage config.",
            remediation="Provide a direct Postgres connection string for the project.",
        )]

    findings: list[Finding] = []
    with connect(cfg.dsn, cfg.timeout) as conn:
        ver = q1(conn, "select version() as v")
        meta["postgres_version"] = (ver or {}).get("v", "?")

        tables = q(conn, SQL_TABLES, (cfg.schemas,))
        policies = q(conn, SQL_POLICIES, (cfg.schemas,))
        grants = _grant_map(q(conn, SQL_TABLE_GRANTS, (cfg.schemas,)))
        cols = q(conn, SQL_SENSITIVE_COLS, (cfg.schemas,))
        funcs = q(conn, SQL_FUNCTIONS, (cfg.schemas,))
        views = q(conn, SQL_VIEWS, (cfg.schemas,))
        role_attrs = q(conn, SQL_ROLE_ATTRS)
        role_members = q(conn, SQL_ROLE_MEMBERSHIP)
        schema_usage = q(conn, SQL_SCHEMA_USAGE)

        base_tables = [t for t in tables if t["kind"] in ("r", "p")]
        meta["tables_scanned"] = len(base_tables)
        meta["schemas"] = cfg.schemas

        pol_by_table: dict[tuple[str, str], list[dict]] = {}
        for p in policies:
            pol_by_table.setdefault((p["schema"], p["name"]), []).append(p)

        # expose table+read-reachability for the probe module and sensitive-col check
        reachable_read: dict[tuple[str, str], set[str]] = {}

        findings += _check_role_attrs(role_attrs, role_members)
        findings += _check_schema_exposure(schema_usage, cfg)

        for t in base_tables:
            key = (t["schema"], t["name"])
            tname = f"{t['schema']}.{t['name']}"
            tgrants = grants.get(key, {})
            anon_g = tgrants.get("anon", set()) | tgrants.get("public", set())
            auth_g = tgrants.get("authenticated", set()) | tgrants.get("public", set())
            tpol = pol_by_table.get(key, [])

            f, read_roles = _check_table(tname, t, anon_g, auth_g, tpol)
            findings += f
            if read_roles:
                reachable_read[key] = read_roles

        findings += _check_sensitive_columns(cols, reachable_read, grants)
        findings += _check_functions(funcs, cfg)
        findings += _check_views(views, grants, cfg)
        findings += _check_storage(conn)
        findings += _check_auth_users(conn, cfg, meta)

        meta["reachable_read_tables"] = sorted(f"{s}.{n}" for (s, n) in reachable_read)

    return findings


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------

def _check_role_attrs(attrs: list[dict], members: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    for r in attrs:
        rn = r["rolname"]
        if rn in ("anon", "authenticated"):
            if r["rolbypassrls"]:
                out.append(Finding(
                    code="role.bypassrls", severity=Severity.CRITICAL, category="grants",
                    title=f"Role '{rn}' has BYPASSRLS — every RLS policy is ignored for it",
                    obj=f"role:{rn}",
                    detail=f"'{rn}' is the role PostgREST uses for {'anonymous' if rn=='anon' else 'logged-in'} "
                           "requests. With BYPASSRLS it reads and writes every table regardless of policy.",
                    remediation=f"ALTER ROLE {rn} NOBYPASSRLS;",
                    evidence=r,
                ))
            if r["rolsuper"]:
                out.append(Finding(
                    code="role.superuser", severity=Severity.CRITICAL, category="grants",
                    title=f"Role '{rn}' is SUPERUSER", obj=f"role:{rn}",
                    detail="A PostgREST request role must never be superuser.",
                    remediation=f"ALTER ROLE {rn} NOSUPERUSER;", evidence=r,
                ))
    for m in members:
        if m["role"] in ("anon", "authenticated") and m["member_of"] in ("service_role", "postgres", "supabase_admin"):
            out.append(Finding(
                code="role.escalation_membership", severity=Severity.CRITICAL, category="grants",
                title=f"Role '{m['role']}' is a member of '{m['member_of']}'",
                obj=f"role:{m['role']}",
                detail="Anyone hitting the API as this role inherits the elevated role's privileges.",
                remediation=f"REVOKE {m['member_of']} FROM {m['role']};", evidence=m,
            ))
    return out


def _check_schema_exposure(usage: list[dict], cfg: AuditConfig) -> list[Finding]:
    out: list[Finding] = []
    for s in usage:
        n = s["nspname"]
        if n in ("public", "storage", "graphql_public", "auth", "extensions", "vault", "realtime",
                 "supabase_functions", "supabase_migrations", "net", "pgsodium", "pgsodium_masks",
                 "cron", "graphql", "_analytics", "_realtime", "pgbouncer"):
            continue
        if s["anon_usage"] or s["auth_usage"]:
            who = "anon" if s["anon_usage"] else "authenticated"
            out.append(Finding(
                code="exposure.extra_schema_usage", severity=Severity.LOW, category="exposure",
                title=f"Schema '{n}' grants USAGE to '{who}'",
                obj=f"schema:{n}",
                detail="If this schema is in PostgREST's exposed list its tables are reachable over the API. "
                       "Confirm it is intentional and that its tables carry RLS.",
                remediation=f"REVOKE USAGE ON SCHEMA {n} FROM anon, authenticated;  -- if not meant to be public",
                evidence=s,
            ))
    return out


def _check_table(
    tname: str, t: dict, anon_g: set[str], auth_g: set[str], tpol: list[dict]
) -> tuple[list[Finding], set[str]]:
    """Return (findings, roles that can READ this table)."""
    out: list[Finding] = []
    read_roles: set[str] = set()

    anon_write = anon_g & WRITE_CMDS
    auth_write = auth_g & WRITE_CMDS
    anon_read = "SELECT" in anon_g
    auth_read = "SELECT" in auth_g

    if not t["rls_enabled"]:
        if anon_g or auth_g:
            roles = sorted({r for r, g in (("anon", anon_g), ("authenticated", auth_g)) if g})
            privs = sorted(anon_g | auth_g)
            out.append(Finding(
                code="rls.disabled_with_grants", severity=Severity.CRITICAL, category="rls",
                title=f"RLS is OFF on {tname} and {'/'.join(roles)} hold {', '.join(privs)}",
                obj=tname,
                detail="PostgREST talks to Postgres as anon/authenticated. With RLS disabled and these "
                       "grants in place, anyone with the publishable key (anon) or any signed-up user "
                       "(authenticated) can operate directly on this table via /rest/v1/.",
                remediation=f"ALTER TABLE {tname} ENABLE ROW LEVEL SECURITY; "
                            "then add scoped policies (or none, to deny all non-service access).",
                evidence={"anon_grants": sorted(anon_g), "authenticated_grants": sorted(auth_g)},
            ))
            if anon_read:
                read_roles.add("anon")
            if auth_read:
                read_roles.add("authenticated")
        else:
            out.append(Finding(
                code="rls.disabled_no_grants", severity=Severity.MEDIUM, category="rls",
                title=f"RLS is OFF on {tname}",
                obj=tname,
                detail="No anon/authenticated grants exist today, so the table is not currently reachable, "
                       "but any future GRANT (or a broad `GRANT ... ON ALL TABLES`) exposes it instantly.",
                remediation=f"ALTER TABLE {tname} ENABLE ROW LEVEL SECURITY;",
            ))
        return out, read_roles

    # RLS enabled -------------------------------------------------------------
    exposed_policies = [p for p in tpol if _exposed_roles(parse_pg_roles(p["roles"]))]
    if not exposed_policies:
        if anon_g or auth_g:
            out.append(Finding(
                code="rls.enabled_no_policy", severity=Severity.INFO, category="rls",
                title=f"RLS on {tname} with no anon/authenticated policy — deny-all (latent grants present)",
                obj=tname,
                detail="Safe today: RLS with no matching policy denies the request role. The standing "
                       "grants become live the moment a permissive policy is added, so keep an eye on it.",
                remediation="No action required; consider REVOKEing the unused grants for defence in depth.",
                evidence={"anon_grants": sorted(anon_g), "authenticated_grants": sorted(auth_g)},
            ))
        return out, read_roles

    for p in exposed_policies:
        roles = _exposed_roles(parse_pg_roles(p["roles"]))
        is_restrictive = (p["permissive"] or "").upper() == "RESTRICTIVE"
        cmd = (p["cmd"] or "ALL").upper()
        using_expr, check_expr = p["using_expr"], p["check_expr"]
        scoped = _refs_auth_uid(using_expr, check_expr)

        if is_restrictive:
            continue  # restrictive policies only ever narrow access

        worst_role = "anon" if "anon" in roles or "public" in roles else "authenticated"
        role_txt = ", ".join(roles)

        if cmd in ("SELECT", "ALL") and (_is_open(using_expr) or (cmd == "ALL" and not using_expr)):
            if not scoped:
                sev = Severity.HIGH if worst_role == "authenticated" else Severity.CRITICAL
                out.append(Finding(
                    code="rls.permissive_read", severity=sev, category="rls",
                    title=f"Policy '{p['policyname']}' lets {role_txt} READ all of {tname}",
                    obj=tname,
                    detail=f"USING ({using_expr or 'true'}) with no row scoping. "
                           f"{'Any signed-up user' if worst_role=='authenticated' else 'Anyone with the anon key'} "
                           "can select every row.",
                    remediation=f"Rewrite the policy to scope rows (e.g. USING (user_id = auth.uid())), "
                                f"or DROP POLICY \"{p['policyname']}\" ON {tname} if the API should not read it.",
                    evidence=p,
                ))
            read_roles.update(roles)

        if cmd in WRITE_CMDS and (_is_open(check_expr) or _is_open(using_expr) or not check_expr):
            if not scoped:
                out.append(Finding(
                    code="rls.permissive_write", severity=Severity.CRITICAL, category="rls",
                    title=f"Policy '{p['policyname']}' lets {role_txt} {cmd} on {tname}",
                    obj=tname,
                    detail=f"WITH CHECK ({check_expr or 'true'}) / USING ({using_expr or 'true'}) — unscoped write. "
                           f"{'Any signed-up user' if worst_role=='authenticated' else 'Anyone with the anon key'} "
                           f"can {cmd.lower()} rows here.",
                    remediation=f"Scope the policy to the caller (auth.uid()) or DROP POLICY "
                                f"\"{p['policyname']}\" ON {tname}; the backend uses the service role and does "
                                "not need this policy.",
                    evidence=p,
                ))
    return out, read_roles


def _check_sensitive_columns(
    cols: list[dict],
    reachable_read: dict[tuple[str, str], set[str]],
    grants: dict,
) -> list[Finding]:
    out: list[Finding] = []
    by_table: dict[tuple[str, str], list[str]] = {}
    for c in cols:
        if SENSITIVE_COL.search(c["column_name"]):
            by_table.setdefault((c["schema"], c["name"]), []).append(c["column_name"])
    for key, sens in by_table.items():
        roles = reachable_read.get(key)
        if not roles:
            continue
        tname = f"{key[0]}.{key[1]}"
        sev = Severity.CRITICAL if "anon" in roles else Severity.HIGH
        out.append(Finding(
            code="data.sensitive_columns_reachable", severity=sev, category="rls",
            title=f"{tname} is readable by {', '.join(sorted(roles))} and holds sensitive columns",
            obj=tname,
            detail=f"Exposed columns: {', '.join(sorted(sens))}. Combined with the read access on this "
                   "table, these values (password hashes / tokens / secrets) can be pulled over the API "
                   "and cracked or replayed offline.",
            remediation="Remove the read access (see the RLS finding for this table), move the secret "
                        "columns to a table the API cannot read, or null them out of API responses with a view.",
            evidence={"columns": sorted(sens)},
        ))
    return out


def _check_functions(funcs: list[dict], cfg: AuditConfig) -> list[Finding]:
    out: list[Finding] = []
    for fn in funcs:
        if not fn["security_definer"]:
            continue
        if not (fn["anon_exec"] or fn["auth_exec"]):
            continue
        who = []
        if fn["anon_exec"]:
            who.append("anon")
        if fn["auth_exec"]:
            who.append("authenticated")
        sev = Severity.HIGH if "anon" in who else Severity.MEDIUM
        fq = f"{fn['schema']}.{fn['name']}({fn['args']})"
        out.append(Finding(
            code="functions.security_definer_public", severity=sev, category="functions",
            title=f"SECURITY DEFINER function {fn['schema']}.{fn['name']} is executable by {', '.join(who)}",
            obj=fq,
            detail=f"Owned by '{fn['owner']}'. Callable without the right privileges via "
                   f"POST /rest/v1/rpc/{fn['name']} — it runs with the owner's rights and can touch data "
                   "the caller cannot.",
            remediation=f"REVOKE EXECUTE ON FUNCTION {fq} FROM {', '.join(who)};  "
                        "or recreate it with SECURITY INVOKER if it does not need elevation.",
            evidence=fn,
        ))
    return out


def _check_views(views: list[dict], grants: dict, cfg: AuditConfig) -> list[Finding]:
    out: list[Finding] = []
    gmap = grants
    for v in views:
        si = (v["security_invoker"] or "false").lower()
        if si in ("on", "true"):
            continue
        key = (v["schema"], v["name"])
        tg = gmap.get(key, {})
        readers = sorted({r for r in ("anon", "authenticated")
                          if "SELECT" in (tg.get(r, set()) | tg.get("public", set()))})
        if not readers:
            continue
        out.append(Finding(
            code="views.rls_bypass", severity=Severity.HIGH, category="exposure",
            title=f"View {v['schema']}.{v['name']} runs as owner (security_invoker off) and is readable by {', '.join(readers)}",
            obj=f"{v['schema']}.{v['name']}",
            detail=f"Owned by '{v['owner']}'. A non-security_invoker view evaluates its query with the "
                   "owner's rights, bypassing RLS on the underlying tables. Selecting the view over the "
                   "API leaks whatever the owner can see.",
            remediation=f"ALTER VIEW {v['schema']}.{v['name']} SET (security_invoker = on);  "
                        "and add RLS on the base tables.",
            evidence=v,
        ))
    return out


def _check_storage(conn) -> list[Finding]:
    out: list[Finding] = []
    buckets = q(conn, SQL_STORAGE_BUCKETS)
    pols = q(conn, SQL_STORAGE_POLICIES)
    rls_row = q1(conn, SQL_STORAGE_OBJECTS_RLS)
    obj_rls = bool((rls_row or {}).get("rls_enabled"))

    for b in buckets:
        if b["public"]:
            out.append(Finding(
                code="storage.public_bucket", severity=Severity.HIGH, category="storage",
                title=f"Storage bucket '{b['name']}' is public",
                obj=f"storage:{b['name']}",
                detail="Every object in a public bucket is downloadable by anyone who knows or guesses "
                       "the path (/storage/v1/object/public/<bucket>/<key>) — no key, no session.",
                remediation=f"Set bucket '{b['name']}' to private and serve files through signed URLs.",
                evidence=b,
            ))
    if not obj_rls and buckets:
        out.append(Finding(
            code="storage.objects_rls_off", severity=Severity.CRITICAL, category="storage",
            title="RLS is disabled on storage.objects",
            obj="storage:objects",
            detail="With RLS off, the storage grants decide access and anon/authenticated can list, "
                   "upload, overwrite and delete objects in every bucket.",
            remediation="ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY; add scoped policies.",
        ))
    for p in pols:
        roles = _exposed_roles(parse_pg_roles(p["roles"]))
        if not roles:
            continue
        cmd = (p["cmd"] or "ALL").upper()
        open_read = cmd in ("SELECT", "ALL") and _is_open(p["using_expr"])
        open_write = cmd in WRITE_CMDS and (_is_open(p["check_expr"]) or _is_open(p["using_expr"]) or not p["check_expr"])
        if open_write:
            out.append(Finding(
                code="storage.public_write_policy", severity=Severity.CRITICAL, category="storage",
                title=f"storage.objects policy '{p['policyname']}' grants {cmd} to {', '.join(roles)}",
                obj="storage:objects",
                detail="Anyone (or any signed-up user) can upload, overwrite or delete stored files "
                       "across buckets.",
                remediation=f"DROP POLICY \"{p['policyname']}\" ON storage.objects; replace with a policy "
                            "scoped to bucket_id and owner = auth.uid().",
                evidence=p,
            ))
        elif open_read:
            out.append(Finding(
                code="storage.public_read_policy", severity=Severity.HIGH, category="storage",
                title=f"storage.objects policy '{p['policyname']}' grants SELECT to {', '.join(roles)} unconditionally",
                obj="storage:objects",
                detail="Objects in every bucket can be listed and downloaded over the API without scoping.",
                remediation=f"Scope or DROP POLICY \"{p['policyname']}\" ON storage.objects.",
                evidence=p,
            ))
    return out


def _check_auth_users(conn, cfg: AuditConfig, meta: dict) -> list[Finding]:
    out: list[Finding] = []
    totals = q1(conn, SQL_AUTH_TOTALS) or {}
    meta["auth_users"] = totals
    rows = q(conn, SQL_AUTH_META)

    flagged = []
    for r in rows:
        email = (r["email"] or "").lower()
        if email in cfg.admin_emails:
            continue
        markers = {k: r[k] for k in
                   ("um_role", "am_role", "um_is_admin", "um_isadmin", "um_claims", "um_user_role")
                   if r.get(k)}
        if markers:
            flagged.append({"email": r["email"], "created_at": str(r["created_at"]),
                            "last_sign_in_at": str(r["last_sign_in_at"]), "markers": markers})

    if flagged:
        out.append(Finding(
            code="auth.self_assigned_privilege_metadata", severity=Severity.HIGH, category="auth",
            title=f"{len(flagged)} auth user(s) carry role/admin markers in user_metadata",
            obj="auth.users",
            detail="`raw_user_meta_data` is written by the client at sign-up (POST /auth/v1/signup "
                   "`data:{...}`) and is fully attacker-controlled. Any backend that reads "
                   "user_metadata.role (or is_admin / claims) to authorize a request can be bypassed by "
                   "signing up with that field set. Confirm no service trusts these fields, and clear "
                   "them from non-admin accounts.",
            remediation="In the API, derive role only from a server-owned table (e.g. public.admins) or "
                        "app_metadata (which the client cannot set). Then: "
                        "UPDATE auth.users SET raw_user_meta_data = raw_user_meta_data - 'role' - 'is_admin' "
                        "- 'isAdmin' - 'claims' WHERE email <> ALL(<admin allowlist>);",
            evidence=flagged[:25],
        ))

    if totals.get("last24"):
        out.append(Finding(
            code="auth.recent_signups", severity=Severity.INFO, category="auth",
            title=f"{totals['last24']} new auth users in the last 24h "
                  f"({totals.get('last7')} in 7d, {totals.get('total')} total, "
                  f"{totals.get('unconfirmed')} unconfirmed)",
            obj="auth.users",
            detail="Baseline figure for triage. A spike, or many unconfirmed / disposable-domain "
                   "addresses, suggests automated abuse.",
            remediation="Review recent rows; disable open signup if it is not required.",
            evidence=totals,
        ))
    return out
