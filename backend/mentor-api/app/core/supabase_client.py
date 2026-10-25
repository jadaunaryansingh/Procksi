"""Supabase clients: full supabase-py client with JWT key validation monkey-patched."""

from __future__ import annotations

import re
from supabase import Client, create_client
import supabase._sync.client as _sync_mod
import supabase._async.client as _async_mod

# ------------------------------------------------------------------
# Monkey-patch: The supabase-py SDK (v2.x) validates keys against a
# JWT regex. Newer Supabase instances issue keys in the
# "sb_publishable_*" / "sb_secret_*" format which fail that check.
# We widen the regex to also accept those prefixes before importing
# `create_client`.
# ------------------------------------------------------------------
_sync_client_class = getattr(_sync_mod, "SyncClient", getattr(_sync_mod, "Client", None))
_ORIG_INIT_SYNC = _sync_client_class.__init__
_ORIG_INIT_ASYNC = _async_mod.AsyncClient.__init__

_RELAXED_KEY_RE = re.compile(
    r"^(sb_(publishable|secret)_[A-Za-z0-9_-]+|[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_.+/=]*)$"
)

def _patched_sync_init(self, supabase_url, supabase_key, options=None):
    if supabase_key and not _RELAXED_KEY_RE.match(supabase_key):
        raise _sync_mod.SupabaseException("Invalid API key")
    # Temporarily replace the regex check in the original init
    _orig_re_match = re.match
    def _relaxed_match(pattern, string, *a, **kw):
        if "A-Za-z0-9" in str(pattern) and string == supabase_key:
            return True  # skip the JWT check
        return _orig_re_match(pattern, string, *a, **kw)
    re.match = _relaxed_match
    try:
        _ORIG_INIT_SYNC(self, supabase_url, supabase_key, options)
    finally:
        re.match = _orig_re_match

_sync_client_class.__init__ = _patched_sync_init


from app.core.config import settings

_service_client: Client | None = None
_anon_client: Client | None = None


def get_supabase_service() -> Client | None:
    global _service_client
    if not settings.supabase_url or not settings.supabase_service_key:
        return None
    if _service_client is not None:
        return _service_client

    _service_client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _service_client


def get_supabase_anon() -> Client | None:
    global _anon_client
    if not settings.supabase_url or not settings.supabase_key:
        return None
    if _anon_client is not None:
        return _anon_client

    _anon_client = create_client(settings.supabase_url, settings.supabase_key)
    return _anon_client


def reset_clients() -> None:
    global _service_client, _anon_client
    _service_client = None
    _anon_client = None