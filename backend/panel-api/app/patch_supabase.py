import sys
import gc
import httpx
import threading
from postgrest._sync.request_builder import (
    SyncQueryRequestBuilder,
    SyncMaybeSingleRequestBuilder,
    SyncSingleRequestBuilder,
)

# ── Intercept and customize HTTPX Client creation for Supabase/Postgrest ──
_orig_httpx_init = httpx.Client.__init__

def patched_httpx_init(self, *args, **kwargs):
    # Walk the frame stack to see if called from postgrest or supabase modules
    f = sys._getframe(1)
    is_postgrest = False
    while f:
        module_name = f.f_globals.get("__name__", "")
        if "postgrest" in module_name or "supabase" in module_name:
            is_postgrest = True
            break
        f = f.f_back
        
    if is_postgrest:
        # Disable HTTP/2 to prevent HTTP/2 framing/stream bugs under concurrency
        kwargs["http2"] = False
        # Enable HTTP keep-alive for quick consecutive requests with reasonable idle expiry
        kwargs["limits"] = httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=30.0)
        # Set a solid request timeout
        kwargs["timeout"] = httpx.Timeout(15.0)
    
    _orig_httpx_init(self, *args, **kwargs)

httpx.Client.__init__ = patched_httpx_init

# Preserve original execute methods
_orig_query_execute = SyncQueryRequestBuilder.execute
_orig_maybe_single_execute = SyncMaybeSingleRequestBuilder.execute
_orig_single_execute = SyncSingleRequestBuilder.execute

# Thread lock for synchronizing session replacement
_session_replace_lock = threading.Lock()

def replace_session_in_all_objects(old_session, new_session):
    """Scan memory and replace any reference to old_session with new_session to prevent 'client has been closed' error."""
    count = 0
    try:
        for obj in gc.get_objects():
            try:
                if hasattr(obj, "__dict__") and obj.__dict__.get("session") is old_session:
                    obj.session = new_session
                    count += 1
            except Exception:
                pass
    except Exception as e:
        print(f"Error scanning GC objects: {e}")
    print(f"Replaced session in {count} postgrest/client objects.")

def patched_execute_wrapper(orig_execute):
    def wrapped(self, *args, **kwargs):
        try:
            return orig_execute(self, *args, **kwargs)
        except httpx.RequestError as exc:
            old_session = self.session
            print(f"Postgrest query failed with transport error: {exc}. Rebuilding session and retrying...")
            
            with _session_replace_lock:
                # Double-check: has another thread already replaced this session?
                if self.session is not old_session:
                    print("Session already replaced by another thread. Retrying directly...")
                    return orig_execute(self, *args, **kwargs)
                
                # Re-check and recreate global clients to get a fresh connection pool
                new_service_client = None
                new_anon_client = None
                
                # 1. Reset Panel Portal global clients
                try:
                    if "app.supabase_client" in sys.modules:
                        from app.supabase_client import reset_clients, get_supabase_service, get_supabase_anon
                        reset_clients()
                        new_service_client = get_supabase_service()
                        new_anon_client = get_supabase_anon()
                except Exception as e:
                    print(f"Error resetting Panel Portal clients: {e}")

                # 2. Reset Admin Portal global clients
                try:
                    if "app.main" in sys.modules:
                        import app.main
                        from supabase import create_client
                        if hasattr(app.main, "SUPABASE_URL"):
                            url = app.main.SUPABASE_URL
                            service_key = getattr(app.main, "SUPABASE_SERVICE_ROLE_KEY", None)
                            pub_key = getattr(app.main, "SUPABASE_PUBLISHABLE_KEY", None)
                            if url and service_key:
                                app.main.service_client = create_client(url, service_key)
                                new_service_client = app.main.service_client
                            if url and pub_key:
                                app.main.auth_client = create_client(url, pub_key)
                                new_anon_client = app.main.auth_client
                except Exception as e:
                    print(f"Error resetting Admin Portal clients: {e}")

                # Determine the appropriate new session
                new_session = None
                if new_service_client and hasattr(new_service_client, "postgrest") and new_service_client.postgrest.session is not old_session:
                    new_session = new_service_client.postgrest.session
                elif new_anon_client and hasattr(new_anon_client, "postgrest") and new_anon_client.postgrest.session is not old_session:
                    new_session = new_anon_client.postgrest.session
                
                # Fallback: create a new httpx.Client manually if we couldn't match a global client
                if not new_session:
                    new_session = httpx.Client(
                        base_url=old_session.base_url,
                        headers=old_session.headers,
                        cookies=old_session.cookies,
                        timeout=old_session.timeout,
                    )
                
                # Replace the session in all active objects in memory
                replace_session_in_all_objects(old_session, new_session)
                
                # Close the old session to release the socket resources
                try:
                    old_session.close()
                except Exception:
                    pass
            
            # Retry the query execution once
            return orig_execute(self, *args, **kwargs)
    return wrapped

# Apply monkey patches
SyncQueryRequestBuilder.execute = patched_execute_wrapper(_orig_query_execute)
SyncMaybeSingleRequestBuilder.execute = patched_execute_wrapper(_orig_maybe_single_execute)
SyncSingleRequestBuilder.execute = patched_execute_wrapper(_orig_single_execute)
print("Supabase/Postgrest HTTPX disconnect auto-retry monkey patches successfully applied.")
