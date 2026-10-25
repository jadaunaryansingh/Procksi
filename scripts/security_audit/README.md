# PMS database security auditor

Audits the Supabase/Postgres layer the way an attacker probes it: every table's
RLS state and policies, role grants, `SECURITY DEFINER` functions, RLS-bypassing
views, Storage bucket exposure, the auth / JWT surface, and — optionally — a live
probe of the deployed REST API as an anonymous user to *confirm* each finding.

Built after the 2026-09-03 incident. It re-checks, in one command, every hole
from that incident plus the general classes around them.

## What it checks

| Pass | Needs | Finds |
|---|---|---|
| **static** | a Postgres DSN (service-role creds) | RLS disabled / permissive policies (`USING (true)`), `anon`/`authenticated` write grants, `authenticated` `USING(true)` policies, sensitive columns (`*_hash`, `token`, `secret`…) in reachable tables, `SECURITY DEFINER` functions executable by `anon`/`authenticated`, views with `security_invoker` off, public Storage buckets + `storage.objects` policies, `auth.users` rows carrying self-assigned `role`/`is_admin` metadata, `anon`/`authenticated` role attributes (BYPASSRLS, role membership) |
| **probe** | `SUPABASE_URL` + publishable key | For every exposed table: does `anon` actually get rows back? (real read vs RLS-filtered empty vs blocked). Optional write-permission probe (invalid body, no row created). Storage bucket + object listing as `anon`. Anonymous execution of flagged RPCs. |
| **auth** | keys / `--sample-jwt` / `--sb-access-token` | Key type & JWT `alg`/`exp`, sample-token lifetime, authz claims living in `user_metadata`, Management-API auth config (open signup, autoconfirm, JWT expiry, refresh rotation, CAPTCHA), extra PostgREST-exposed schemas. Optional signup probe: registers a throwaway user with `data:{role:"admin"}`, inspects the issued token, deletes the user with the service key. |

Every probe/auth finding that was proven against the live system is marked
`live` / `confirmed`.

## Install

Deps are already in the backend venvs (`psycopg`, `httpx`, `rich`). Otherwise:

```
pip install "psycopg[binary]" httpx rich
```

## Run

From the repo root. Config resolves from CLI flags → environment →
`backend/*/.env` (first file that defines a key wins).

```bash
# Full audit (static + live probe + auth), read-only:
python -m scripts.security_audit \
  --dsn "postgresql://postgres.<ref>:<PASSWORD>@aws-1-...pooler.supabase.com:6543/postgres" \
  --admin-emails "aiml_project_coordinator@gla.ac.in,admin@gla.ac.in" \
  --md security_audit.md --json security_audit.json

# Black-box only (no DB): enumerate tables via the secret key, probe as anon:
python -m scripts.security_audit --no-static --md security_audit.md

# Add write-permission probing (still creates no real rows):
python -m scripts.security_audit --write-probe

# Add the signup / self-role probe (needs --service-key to clean up):
python -m scripts.security_audit --signup-probe

# Inspect a real user token:
python -m scripts.security_audit --no-static --sample-jwt "eyJhbGci..."
```

### Key flags

| Flag | Meaning |
|---|---|
| `--dsn` | Postgres URL. Falls back to `DATABASE_URL` / `SECURITY_AUDIT_DSN`. |
| `--no-static` | skip the DB pass (black-box mode) |
| `--schemas public,foo` | schemas to audit (default `public`) |
| `--admin-emails a@x,b@y` | allowlist; `auth.users` with role metadata **not** on it are flagged |
| `--write-probe` | per-table write-permission test with an invalid body (no row inserted) |
| `--destructive` | with `--write-probe`, allow a real insert+delete round-trip where a table permits it |
| `--signup-probe` | register + delete a throwaway auth user to test open signup / self-role |
| `--tables-file PATH` | table names to probe when the OpenAPI root is unreachable and no DSN is set |
| `--sb-access-token` | Supabase PAT → pulls auth config from the Management API |
| `--fail-level HIGH` | process exits `2` if any finding is at/above this (CI gate); default `HIGH` |

### Getting a working DSN

The `DATABASE_URL` in `backend/*/.env` currently fails SCRAM auth (password
rotated). Grab a fresh one from **Supabase dashboard → Project Settings →
Database → Connection string → URI** (or reset the DB password there), and pass
it with `--dsn` or export it as `SECURITY_AUDIT_DSN`.

## Output

- Console summary table (severity × finding).
- `--md` : full Markdown report — detail, evidence JSON, and a concrete fix per finding.
- `--json` : same content as structured JSON for diffing between runs / CI.

Exit code `2` when anything is at or above `--fail-level`, else `0`.

## Safety

- The DB session is `SET default_transaction_read_only = on`; the static pass cannot write.
- Read probes are plain `GET`s.
- `--write-probe` sends a deliberately invalid body so the row is rejected on
  content *after* the permission check — it never creates a row. `--destructive`
  is the only mode that inserts, and it deletes what it inserts and shouts if
  cleanup fails.
- `--signup-probe` deletes its test user via the service key and reports loudly
  if that delete fails. It refuses to run without `--service-key`.
