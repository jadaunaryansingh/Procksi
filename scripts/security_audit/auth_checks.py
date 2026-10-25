"""Auth / JWT surface.

Three independent angles:
  1. Static inspection of the API keys and any sample user JWTs handed in.
  2. Supabase Management API auth config  (only if SUPABASE_ACCESS_TOKEN is set).
  3. A live signup probe  (opt-in) that registers a throwaway user with an
     attacker-style ``data:{role:"admin"}`` payload, inspects the issued token,
     then deletes the user with the service-role key.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from .config import AuditConfig
from .model import Finding, Severity

MGMT = "https://api.supabase.com"


def _b64json(segment: str) -> dict | None:
    try:
        pad = "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(segment + pad))
    except Exception:
        return None


def decode_jwt(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header = _b64json(parts[0]) or {}
    payload = _b64json(parts[1]) or {}
    return {"header": header, "payload": payload}


def run(cfg: AuditConfig, meta: dict[str, Any]) -> list[Finding]:
    out: list[Finding] = []
    out += _inspect_key("publishable/anon key", cfg.anon_key)
    out += _inspect_key("service-role key", cfg.service_key, expect_role="service_role")
    for i, tok in enumerate(cfg.sample_jwts):
        out += _inspect_sample_jwt(f"sample JWT #{i + 1}", tok)

    if cfg.sb_access_token and cfg.project_ref:
        out += _mgmt_auth_config(cfg, meta)
    else:
        out.append(Finding(
            code="auth.mgmt_not_checked", severity=Severity.INFO, category="auth",
            title="Supabase Auth config not read from the Management API",
            obj="auth",
            detail="No SUPABASE_ACCESS_TOKEN provided, so signup / confirmation / JWT-expiry settings "
                   "were not read directly. Use --signup-probe for an empirical check instead.",
            remediation="Set SUPABASE_ACCESS_TOKEN (a personal access token) to include this check.",
        ))

    if cfg.do_signup_probe:
        out += _signup_probe(cfg, meta)

    return out


# ---------------------------------------------------------------------------

def _inspect_key(label: str, key: str | None, expect_role: str | None = None) -> list[Finding]:
    if not key:
        return []
    if key.startswith(("sb_publishable_", "sb_secret_", "sbp_")):
        return [Finding(
            code="jwt.new_style_key", severity=Severity.INFO, category="jwt",
            title=f"{label}: new-style Supabase API key (opaque, revocable)",
            obj="auth", detail="Good — these can be rotated individually without changing the JWT secret.",
            remediation="", evidence={"prefix": key.split("_")[0] + "_..."},
        )]
    dec = decode_jwt(key)
    if not dec:
        return []
    payload, header = dec["payload"], dec["header"]
    findings: list[Finding] = []
    if str(header.get("alg", "")).lower() == "none":
        findings.append(Finding(
            code="jwt.alg_none", severity=Severity.CRITICAL, category="jwt",
            title=f"{label} uses alg=none", obj="auth",
            detail="Signature verification is disabled — tokens can be forged at will.",
            remediation="Reissue keys with HS256/RS256.", evidence=header,
        ))
    if "exp" not in payload:
        findings.append(Finding(
            code="jwt.legacy_no_exp", severity=Severity.LOW, category="jwt",
            title=f"{label} is a legacy JWT with no expiry",
            obj="auth",
            detail="Legacy anon/service JWTs never expire; once leaked they are valid until the project "
                   "JWT secret is rotated (which invalidates every session).",
            remediation="Migrate to publishable/secret API keys so this key can be revoked in isolation.",
            evidence={"role": payload.get("role"), "ref": payload.get("ref")},
        ))
    if expect_role and payload.get("role") != expect_role:
        findings.append(Finding(
            code="jwt.unexpected_role", severity=Severity.MEDIUM, category="jwt",
            title=f"{label} carries role={payload.get('role')!r} (expected {expect_role!r})",
            obj="auth", detail="Check that the right key is wired where.", remediation="",
            evidence={"role": payload.get("role")},
        ))
    return findings


def _inspect_sample_jwt(label: str, token: str) -> list[Finding]:
    dec = decode_jwt(token)
    if not dec:
        return [Finding(
            code="jwt.sample_unparseable", severity=Severity.INFO, category="jwt",
            title=f"{label} could not be parsed", obj="auth", detail="", remediation="",
        )]
    p, h = dec["payload"], dec["header"]
    out: list[Finding] = []
    if str(h.get("alg", "")).lower() == "none":
        out.append(Finding(
            code="jwt.sample_alg_none", severity=Severity.CRITICAL, category="jwt",
            title=f"{label}: alg=none", obj="auth", detail="Forgeable token.", remediation="Reject alg=none server-side.",
        ))
    life = None
    if "exp" in p and "iat" in p:
        life = int(p["exp"]) - int(p["iat"])
        if life > 86400:
            sev = Severity.MEDIUM
        elif life > 3600:
            sev = Severity.LOW
        else:
            sev = Severity.INFO
        if sev > Severity.INFO:
            out.append(Finding(
                code="jwt.sample_long_lived", severity=sev, category="jwt",
                title=f"{label}: access token lifetime is {life // 60} min",
                obj="auth",
                detail="Long-lived access tokens widen the window for a stolen token. Supabase default "
                       "is 3600s with refresh-token rotation.",
                remediation="Lower JWT expiry (Auth settings) and rely on refresh rotation.",
                evidence={"exp_seconds": life},
            ))
    role_in_user_meta = isinstance(p.get("user_metadata"), dict) and (
        "role" in p["user_metadata"] or "is_admin" in p["user_metadata"] or "claims" in p["user_metadata"]
    )
    if role_in_user_meta:
        out.append(Finding(
            code="jwt.authz_claim_in_user_metadata", severity=Severity.HIGH, category="jwt",
            title=f"{label}: authorization-relevant field sits in user_metadata",
            obj="auth",
            detail="`user_metadata` is user-writable at signup. If the API authorizes on "
                   f"user_metadata ({sorted(p['user_metadata'])}), any user can elevate themselves.",
            remediation="Authorize on app_metadata or a server-side table only.",
            evidence={"user_metadata_keys": sorted(p["user_metadata"])},
        ))
    out.append(Finding(
        code="jwt.sample_summary", severity=Severity.INFO, category="jwt",
        title=f"{label}: role={p.get('role')} aud={p.get('aud')} "
              f"life={f'{life}s' if life else '?'} alg={h.get('alg')}",
        obj="auth", detail="Decoded without signature verification for inspection.", remediation="",
        evidence={"payload_keys": sorted(p.keys())},
    ))
    return out


def _mgmt_auth_config(cfg: AuditConfig, meta: dict) -> list[Finding]:
    out: list[Finding] = []
    ref = cfg.project_ref
    hdr = {"Authorization": f"Bearer {cfg.sb_access_token}"}
    try:
        with httpx.Client(timeout=cfg.timeout, headers=hdr) as cli:
            r = cli.get(f"{MGMT}/v1/projects/{ref}/config/auth")
            pg = cli.get(f"{MGMT}/v1/projects/{ref}/postgrest")
    except Exception as exc:
        return [Finding(
            code="auth.mgmt_error", severity=Severity.INFO, category="auth",
            title="Management API request failed", obj="auth", detail=repr(exc), remediation="",
        )]
    if r.status_code != 200:
        return [Finding(
            code="auth.mgmt_error", severity=Severity.INFO, category="auth",
            title=f"Management API returned HTTP {r.status_code} for auth config",
            obj="auth", detail=r.text[:300], remediation="Check the access token's scope.",
        )]
    conf = r.json()
    meta["auth_config"] = {k: conf.get(k) for k in (
        "disable_signup", "mailer_autoconfirm", "external_email_enabled", "external_anonymous_users_enabled",
        "jwt_exp", "refresh_token_rotation_enabled", "security_captcha_enabled",
        "password_min_length", "security_update_password_require_reauthentication",
    )}

    if conf.get("disable_signup") is False:
        out.append(Finding(
            code="auth.open_signup", severity=Severity.HIGH, category="auth",
            title="Public sign-up is enabled",
            obj="auth",
            detail="Anyone can create an `authenticated` session with the publishable key. Combined with "
                   "any permissive `authenticated` RLS policy, that is world read/write. Only leave signup "
                   "open if every table's policies are scoped to auth.uid().",
            remediation="Auth → Providers: disable email signups, or gate them (allowed domains / invite only).",
            evidence={"disable_signup": False},
        ))
    if conf.get("external_anonymous_users_enabled"):
        out.append(Finding(
            code="auth.anonymous_users", severity=Severity.MEDIUM, category="auth",
            title="Anonymous sign-ins are enabled",
            obj="auth", detail="Clients can obtain an `authenticated` JWT with no credentials at all.",
            remediation="Disable anonymous sign-ins unless a feature needs them.",
        ))
    if conf.get("mailer_autoconfirm"):
        out.append(Finding(
            code="auth.autoconfirm", severity=Severity.MEDIUM, category="auth",
            title="New emails are auto-confirmed",
            obj="auth", detail="Sign-ups are usable immediately without proving control of the address.",
            remediation="Enable email confirmation.",
        ))
    je = conf.get("jwt_exp")
    if isinstance(je, int) and je > 3600:
        out.append(Finding(
            code="auth.jwt_exp_long", severity=Severity.LOW, category="auth",
            title=f"Access-token lifetime is {je}s (> 1h)",
            obj="auth", detail="Longer than the Supabase default; widens the replay window for a stolen token.",
            remediation="Set JWT expiry to 3600s.", evidence={"jwt_exp": je},
        ))
    if conf.get("refresh_token_rotation_enabled") is False:
        out.append(Finding(
            code="auth.no_refresh_rotation", severity=Severity.MEDIUM, category="auth",
            title="Refresh-token rotation is disabled",
            obj="auth", detail="A stolen refresh token stays valid indefinitely with no reuse detection.",
            remediation="Enable refresh-token rotation + reuse detection.",
        ))
    if conf.get("security_captcha_enabled") is False and conf.get("disable_signup") is False:
        out.append(Finding(
            code="auth.no_captcha", severity=Severity.LOW, category="auth",
            title="No CAPTCHA on auth endpoints while signup is open",
            obj="auth", detail="Signup/login can be scripted for mass account creation or credential stuffing.",
            remediation="Enable CAPTCHA (hCaptcha/Turnstile) for auth.",
        ))
    pml = conf.get("password_min_length")
    if isinstance(pml, int) and pml < 8:
        out.append(Finding(
            code="auth.weak_password_policy", severity=Severity.MEDIUM, category="auth",
            title=f"Minimum password length is {pml}",
            obj="auth", detail="Below the widely recommended floor of 8+.",
            remediation="Raise the minimum and enable leaked-password protection.",
        ))
    if pg is not None and pg.status_code == 200:
        pgc = pg.json()
        meta["postgrest_config"] = {k: pgc.get(k) for k in ("db_schema", "db_extra_search_path", "max_rows")}
        schemas = str(pgc.get("db_schema", ""))
        extra = [s.strip() for s in schemas.split(",") if s.strip() and s.strip() not in ("public", "graphql_public", "storage")]
        if extra:
            out.append(Finding(
                code="auth.extra_exposed_schema", severity=Severity.MEDIUM, category="exposure",
                title=f"PostgREST also exposes schema(s): {', '.join(extra)}",
                obj="rest",
                detail="Tables in these schemas are reachable over /rest/v1. Re-run this audit with "
                       f"--schemas public,{','.join(extra)} to cover them.",
                remediation="Trim db-schema to the minimum, and RLS every table in the exposed schemas.",
                evidence={"db_schema": schemas},
            ))
    return out


def _signup_probe(cfg: AuditConfig, meta: dict) -> list[Finding]:
    if not (cfg.supabase_url and cfg.anon_key):
        return [Finding(
            code="auth.signup_probe_skipped", severity=Severity.INFO, category="auth",
            title="Signup probe skipped — need Supabase URL + anon key", obj="auth", detail="", remediation="",
        )]
    if not cfg.service_key:
        return [Finding(
            code="auth.signup_probe_skipped", severity=Severity.INFO, category="auth",
            title="Signup probe skipped — no service-role key to delete the test user afterwards",
            obj="auth",
            detail="Provide --service-key so the throwaway account can be cleaned up. Refusing to create "
                   "an account it cannot remove.",
            remediation="",
        )]

    ts = int(time.time())
    email = f"secaudit_probe_{ts}@example.com"
    password = base64.urlsafe_b64encode(f"Sa!{ts}{time.time_ns()}".encode()).decode()[:24] + "aA1!"
    out: list[Finding] = []
    base = cfg.supabase_url.rstrip("/")
    hdr = {"apikey": cfg.anon_key, "Content-Type": "application/json"}
    payload = {"email": email, "password": password, "data": {"role": "admin", "is_admin": True}}

    try:
        with httpx.Client(timeout=cfg.timeout) as cli:
            r = cli.post(f"{base}/auth/v1/signup", headers=hdr, json=payload)
    except Exception as exc:
        return [Finding(
            code="auth.signup_probe_error", severity=Severity.INFO, category="auth",
            title="Signup probe request failed", obj="auth", detail=repr(exc), remediation="",
        )]

    meta["signup_probe_status"] = r.status_code
    if r.status_code in (400, 422) and "signup" in r.text.lower() and "disabled" in r.text.lower():
        return [Finding(
            code="auth.signup_disabled_confirmed", severity=Severity.INFO, category="auth",
            title="Signup probe: public sign-up is disabled (good)",
            obj="auth", detail=f"POST /auth/v1/signup -> HTTP {r.status_code}: {r.text[:200]}", remediation="",
            confirmed=True,
        )]
    if r.status_code not in (200, 201):
        return [Finding(
            code="auth.signup_probe_inconclusive", severity=Severity.INFO, category="auth",
            title=f"Signup probe inconclusive (HTTP {r.status_code})",
            obj="auth", detail=r.text[:300], remediation="", confirmed=True,
        )]

    body = r.json()
    user = body.get("user") or {}
    uid = user.get("id")
    access = body.get("access_token") or (body.get("session") or {}).get("access_token")
    um = (user.get("user_metadata") or {})

    out.append(Finding(
        code="auth.signup_open_confirmed", severity=Severity.HIGH, category="auth", confirmed=True,
        title="Signup probe: created an account with only the publishable key",
        obj="auth",
        detail=f"POST /auth/v1/signup returned HTTP {r.status_code} and a user record. Anyone can do this.",
        remediation="Disable / gate public signup, and scope every `authenticated` RLS policy.",
        evidence={"email": email, "confirmed_immediately": bool(access)},
    ))
    if um.get("role") == "admin" or um.get("is_admin") is True:
        out.append(Finding(
            code="auth.signup_self_role_confirmed", severity=Severity.CRITICAL, category="auth", confirmed=True,
            title="Signup probe: the client set its own user_metadata.role = admin",
            obj="auth",
            detail="The `data:{role:'admin'}` sent at signup was stored verbatim on the user. Any backend "
                   "that reads user_metadata.role / is_admin for authorization is fully bypassable by "
                   "self-registration.",
            remediation="Never authorize on user_metadata. Use app_metadata or a server-owned table.",
            evidence={"user_metadata": um},
        ))
    if access:
        dec = decode_jwt(access) or {}
        p = dec.get("payload", {})
        life = (int(p["exp"]) - int(p["iat"])) if ("exp" in p and "iat" in p) else None
        out.append(Finding(
            code="auth.signup_token_confirmed", severity=Severity.MEDIUM if not p.get("user_metadata", {}).get("role") else Severity.HIGH,
            category="auth", confirmed=True,
            title=f"Signup probe: session issued immediately (role={p.get('role')}, life={f'{life}s' if life else '?'})",
            obj="auth",
            detail="An `authenticated` access token was returned without email confirmation, usable "
                   "against /rest/v1 right away."
                   + (f" It also carries user_metadata.role={p['user_metadata']['role']!r}."
                      if p.get("user_metadata", {}).get("role") else ""),
            remediation="Require email confirmation; keep JWT lifetime at 3600s.",
            evidence={"jwt_payload_keys": sorted(p.keys()), "life_seconds": life},
        ))

    # cleanup ---------------------------------------------------------------
    deleted = False
    if uid:
        try:
            with httpx.Client(timeout=cfg.timeout) as cli:
                d = cli.request(
                    "DELETE",
                    f"{base}/auth/v1/admin/users/{uid}",
                    headers={"apikey": cfg.service_key, "Authorization": f"Bearer {cfg.service_key}"},
                )
            deleted = d.status_code in (200, 204)
        except Exception:
            deleted = False
    if not deleted:
        out.append(Finding(
            code="auth.signup_probe_cleanup_failed", severity=Severity.HIGH, category="auth",
            title="Signup probe could NOT delete its test user",
            obj="auth",
            detail=f"Remove auth user {email} (id={uid}) manually.",
            remediation=f"In the Supabase dashboard, delete user {email}.",
            evidence={"user_id": uid},
        ))
    else:
        meta["signup_probe_cleanup"] = "ok"
    return out
