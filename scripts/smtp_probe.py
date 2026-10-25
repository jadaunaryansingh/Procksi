#!/usr/bin/env python3
"""
Verify the configured Gmail SMTP credentials actually authenticate.

Usage:
    python3 scripts/smtp_probe.py                  # check all backend .env files
    python3 scripts/smtp_probe.py --send you@x.com # also send a real test email

Checks each backend's .env, reports whether the password differs between
them, and attempts a real STARTTLS login against the configured server.
Prints only lengths and short fingerprints -- never the password itself.
"""
import argparse
import hashlib
import smtplib
import ssl
import sys
from pathlib import Path

ENV_FILES = [
    "backend/admin-api/.env",
    "backend/panel-api/.env",
    "backend/student-api/.env",
    "backend/mentor-api/.env",
]


def read_env(path):
    env = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def fingerprint(secret):
    return hashlib.sha256(secret.encode()).hexdigest()[:12]


def probe(host, port, user, pwd, send_to=None):
    """Return (ok, detail). Uses SMTP_SSL for 465, STARTTLS otherwise."""
    try:
        ctx = ssl.create_default_context()
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
    except Exception as exc:
        return False, f"connect/TLS failed: {type(exc).__name__}: {exc}"

    try:
        server.login(user, pwd)
    except smtplib.SMTPAuthenticationError as exc:
        detail = exc.smtp_error.decode(errors="replace").replace("\n", " ")
        server.close()
        return False, f"{exc.smtp_code} {detail[:160]}"
    except Exception as exc:
        server.close()
        return False, f"login failed: {type(exc).__name__}: {exc}"

    if send_to:
        try:
            msg = (
                f"From: {user}\r\nTo: {send_to}\r\n"
                "Subject: PMS SMTP probe\r\n\r\n"
                "SMTP credentials are working.\r\n"
            )
            server.sendmail(user, [send_to], msg)
        except Exception as exc:
            server.quit()
            return False, f"login OK but send failed: {type(exc).__name__}: {exc}"

    server.quit()
    return True, "login OK" + (f", test mail sent to {send_to}" if send_to else "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", metavar="ADDRESS",
                        help="also send a real test email to this address")
    args = parser.parse_args()

    fingerprints = {}
    failures = 0
    checked = 0

    for path in ENV_FILES:
        if not Path(path).exists():
            print(f"{path:32} (missing)")
            continue

        env = read_env(path)
        pwd = env.get("MAIL_PASSWORD", "").replace(" ", "").strip()
        user = env.get("MAIL_USERNAME", "")
        host = env.get("MAIL_SERVER", "smtp.gmail.com")
        port = int(env.get("MAIL_PORT", 587))

        if not pwd or not user:
            print(f"{path:32} MAIL_USERNAME/MAIL_PASSWORD not set")
            failures += 1
            continue

        fingerprints[path] = fingerprint(pwd)
        ok, detail = probe(host, port, user, pwd, args.send)
        checked += 1
        if not ok:
            failures += 1
        status = "PASS" if ok else "FAIL"
        print(f"{path:32} len={len(pwd):<3} fp={fingerprints[path]}  [{status}] {detail}")

    if len(set(fingerprints.values())) > 1:
        print("\nWARNING: backends do not all share the same MAIL_PASSWORD.")

    if checked and failures == 0:
        print(f"\nAll {checked} backend(s) authenticated successfully.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
