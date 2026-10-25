#!/usr/bin/env python3
"""Report which supabase/migrations have actually reached the database.

Schema state cannot be inferred from the migrations directory: this project has
no migration runner (the exec_sql RPC main.py expects does not exist), so files
are applied by hand in the SQL editor and the two drift silently. This probes
the database for the objects each migration creates.

Usage: python3 scripts/verify_migrations.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, "backend", "admin-api", ".env")

# (migration file, probe path, human description)
CHECKS = [
    ("202608240001_pms_chat_toggles.sql",
     "semester_config?select=pms_chat_student,pms_chat_mentor,pms_chat_panel,pms_chat_admin&limit=1",
     "semester_config.pms_chat_* columns"),
    ("202608240002_email_deliveries.sql",
     "email_deliveries?select=id&limit=1",
     "email_deliveries table"),
]


def load_env(path):
    if not os.path.exists(path):
        sys.exit(f"No env file at {path}")
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main():
    env = load_env(ENV)
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing from the env file")

    pending = []
    for fname, path, desc in CHECKS:
        req = urllib.request.Request(
            f"{url}/rest/v1/{path}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        try:
            urllib.request.urlopen(req, timeout=20).read()
            print(f"  applied  {desc}")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read()).get("code", "")
            except Exception:  # noqa: BLE001 - the status alone is enough
                pass
            print(f"  PENDING  {desc}  (HTTP {exc.code} {detail})")
            pending.append(fname)
        except Exception as exc:  # noqa: BLE001 - network, DNS, timeout
            print(f"  UNKNOWN  {desc}  ({type(exc).__name__}: {exc})")
            pending.append(fname)

    if pending:
        print("\nRun these in the Supabase SQL editor:")
        for f in pending:
            print(f"  supabase/migrations/{f}")
        return 1
    print("\nAll tracked migrations are applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
