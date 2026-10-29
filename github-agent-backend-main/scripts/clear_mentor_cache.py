"""
Clear the mentor lookup cache to force refresh of mentor names
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.backend.utils.cache import cache

def clear_mentor_cache():
    """Clear mentor lookup cache"""
    cache_key = "hackeval:mentors:lookup"
    
    try:
        result = cache.delete(cache_key)
        print(f"✅ Cleared mentor cache: {cache_key}")
        print(f"   Result: {result}")
    except Exception as e:
        print(f"❌ Failed to clear cache: {e}")

if __name__ == "__main__":
    clear_mentor_cache()
