"""
Supabase Database Connection and Utilities
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Singleton client
_supabase_client: Client = None
_supabase_admin_client: Client = None


def get_supabase_client() -> Client:
    """Get Supabase client instance (uses anon key)"""
    global _supabase_client
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment")
    
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    return _supabase_client


def get_supabase_admin_client() -> Client:
    """Get Supabase admin client instance (uses service role key)"""
    global _supabase_admin_client
    
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment")
    
    if _supabase_admin_client is None:
        _supabase_admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    return _supabase_admin_client


# Convenience alias
supabase = get_supabase_client


def get_supabase() -> Client:
    """Alias for get_supabase_client"""
    return get_supabase_client()

