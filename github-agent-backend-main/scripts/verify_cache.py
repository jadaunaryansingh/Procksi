
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

def verify_cache_fix():
    from src.api.backend.utils.cache import cache
    
    print("Testing Cache Connection via cache.py...")
    if cache.is_connected:
        print("✅ Cache is connected!")
        # Try a set/get
        cache.set("fix_verify", "working")
        val = cache.get("fix_verify")
        print(f"Value retrieved: {val}")
    else:
        print("❌ Cache is NOT connected.")

if __name__ == "__main__":
    verify_cache_fix()
