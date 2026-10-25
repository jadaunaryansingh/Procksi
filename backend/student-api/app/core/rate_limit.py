"""Shared slowapi Limiter instance.

Lives in its own module so route files can `@limiter.limit(...)` a specific
endpoint without importing app.main (which imports the route modules, so a
route module importing the limiter straight from main.py would be circular).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
