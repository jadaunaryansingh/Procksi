"""Runtime configuration: resolve DB DSN, Supabase URL and keys from CLI flags,
the process environment, and (as a fallback) the project's backend ``.env`` files.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .model import Severity

REPO_ROOT = Path(__file__).resolve().parents[2]

# Order matters: the first file that defines a key wins. mentor-api carries a
# real DATABASE_URL; admin-api carries the service-role key.
DEFAULT_ENV_FILES = [
    REPO_ROOT / "backend" / "mentor-api" / ".env",
    REPO_ROOT / "backend" / "admin-api" / ".env",
    REPO_ROOT / "backend" / "student-api" / ".env",
    REPO_ROOT / "backend" / "panel-api" / ".env",
    REPO_ROOT / ".env",
]

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw or raw.lstrip().startswith("#"):
            continue
        m = _ENV_LINE.match(raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out.setdefault(key, val)
    return out


def _layered_env(env_files: list[Path]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in env_files:
        for k, v in _parse_env_file(path).items():
            merged.setdefault(k, v)
    return merged


def normalize_dsn(dsn: str) -> str:
    """Turn a SQLAlchemy-style URL into one libpq/psycopg accepts and force TLS."""
    dsn = dsn.strip()
    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", dsn)
    dsn = re.sub(r"^postgres\+\w+://", "postgresql://", dsn)
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


@dataclass
class AuditConfig:
    dsn: str | None = None
    supabase_url: str | None = None
    anon_key: str | None = None
    service_key: str | None = None
    sb_access_token: str | None = None

    schemas: list[str] = field(default_factory=lambda: ["public"])
    admin_emails: set[str] = field(default_factory=set)

    do_probe: bool = True             # anon read probes of every exposed table
    do_write_probe: bool = False      # permission-only writes (invalid payload, never a valid row)
    do_destructive: bool = False      # real insert + immediate delete round-trip
    do_signup_probe: bool = False     # register a throwaway auth user, then delete it

    sample_jwts: list[str] = field(default_factory=list)
    tables_file: Path | None = None
    fail_level: Severity = Severity.HIGH
    json_out: Path | None = None
    md_out: Path | None = None
    timeout: float = 20.0

    # ---- derived / diagnostic ----
    env_files_used: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def project_ref(self) -> str | None:
        if self.supabase_url:
            m = re.search(r"https?://([a-z0-9]+)\.supabase\.", self.supabase_url)
            if m:
                return m.group(1)
        if self.dsn:
            m = re.search(r"postgres\.([a-z0-9]{16,})[:@]", self.dsn)
            if m:
                return m.group(1)
        return None

    @property
    def rest_url(self) -> str | None:
        return f"{self.supabase_url.rstrip('/')}/rest/v1" if self.supabase_url else None


def _looks_like_anon(key: str) -> bool:
    if key.startswith(("sb_publishable_", "sbp_pk_")):
        return True
    # legacy anon JWT: role claim == anon
    return bool(re.search(r'"role":\s*"anon"', _b64_mid(key) or ""))


def _b64_mid(jwt: str) -> str | None:
    import base64

    parts = jwt.split(".")
    if len(parts) != 3:
        return None
    try:
        pad = "=" * (-len(parts[1]) % 4)
        return base64.urlsafe_b64decode(parts[1] + pad).decode("utf-8", "replace")
    except Exception:
        return None


def build_config(args) -> AuditConfig:
    env_files = [Path(p) for p in (args.env_file or [])] or DEFAULT_ENV_FILES
    file_env = _layered_env(env_files)

    def pick(*names: str, cli: str | None = None) -> tuple[str | None, str]:
        if cli:
            return cli, "cli"
        for n in names:
            if os.environ.get(n):
                return os.environ[n], f"env:{n}"
        for n in names:
            if file_env.get(n):
                return file_env[n], f"file:{n}"
        return None, "unset"

    cfg = AuditConfig()
    cfg.env_files_used = [str(p) for p in env_files if p.is_file()]

    if getattr(args, "no_static", False):
        cfg.dsn = None
        cfg.sources["dsn"] = "disabled(--no-static)"
    else:
        dsn, src = pick("SECURITY_AUDIT_DSN", "DATABASE_URL", cli=args.dsn)
        cfg.dsn = normalize_dsn(dsn) if dsn else None
        cfg.sources["dsn"] = src

    url, src = pick("SUPABASE_URL", "VITE_SUPABASE_URL", cli=args.supabase_url)
    cfg.supabase_url = url.rstrip("/") if url else None
    cfg.sources["supabase_url"] = src

    anon, src = pick(
        "SUPABASE_PUBLISHABLE_KEY", "VITE_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY",
        "SUPABASE_KEY", cli=args.anon_key,
    )
    if anon and not args.anon_key and anon.startswith("sb_secret_"):
        anon = None  # never probe with a secret key
        src = "unset(rejected secret key)"
    cfg.anon_key = anon
    cfg.sources["anon_key"] = src

    svc, src = pick("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", cli=args.service_key)
    cfg.service_key = svc
    cfg.sources["service_key"] = src

    tok, src = pick("SUPABASE_ACCESS_TOKEN", cli=args.sb_access_token)
    cfg.sb_access_token = tok
    cfg.sources["sb_access_token"] = src

    if args.schemas:
        cfg.schemas = [s.strip() for s in args.schemas.split(",") if s.strip()]
    if args.admin_emails:
        cfg.admin_emails = {e.strip().lower() for e in args.admin_emails.split(",") if e.strip()}

    cfg.do_probe = not args.no_probe and bool(cfg.anon_key and cfg.supabase_url)
    cfg.do_write_probe = bool(args.write_probe)
    cfg.do_destructive = bool(args.destructive)
    cfg.do_signup_probe = bool(args.signup_probe)
    cfg.sample_jwts = list(args.sample_jwt or [])
    cfg.tables_file = Path(args.tables_file) if getattr(args, "tables_file", None) else None
    cfg.fail_level = Severity.parse(args.fail_level)
    cfg.json_out = Path(args.json) if args.json else None
    cfg.md_out = Path(args.md) if args.md else None
    if args.timeout:
        cfg.timeout = float(args.timeout)
    return cfg
