"""Supabase / Postgres security auditor for the Procksi project.

Checks every table, policy, grant, function, view, storage bucket and the auth /
JWT surface, and (optionally) probes the deployed REST API as an anonymous user
to confirm findings empirically rather than only reading configuration.

Entry point: ``python -m scripts.security_audit`` (see ``README.md``).
"""

__version__ = "1.0.0"
