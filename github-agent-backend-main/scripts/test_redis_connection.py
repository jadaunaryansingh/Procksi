"""
Quick verification script to test Redis connection changes
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("Redis Connection Test")
print("=" * 60)

# Check REDIS_URL
redis_url = os.getenv("REDIS_URL")
if redis_url:
    protocol = redis_url.split("://")[0]
    print(f"✅ REDIS_URL loaded: {protocol}://...")
    if protocol == "rediss":
        print("✅ Using TLS (rediss://)")
    else:
        print("⚠️  Using non-TLS (redis://)")
else:
    print("❌ REDIS_URL not found in environment")

print()

# Test singleton
from src.api.backend.utils.cache import cache
c1 = cache
c2 = cache

print("Singleton Test:")
if c1 is c2:
    print("✅ Same instance (singleton works)")
else:
    print("❌ Different instances (singleton broken)")

if c1._client is c2._client:
    print("✅ Same Redis client (connection pooling works)")
else:
    print("❌ Different Redis clients (pooling broken)")

print()
print("Connection Status:")
print(f"  Connected: {c1._connected}")
print(f"  Client: {type(c1._client).__name__ if c1._client else 'None'}")

print("=" * 60)
