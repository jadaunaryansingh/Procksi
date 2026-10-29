
import os
import sys
import redis
from dotenv import load_dotenv

sys.path.append(os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

def test_redis_tls():
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("❌ REDIS_URL not set")
        return
        
    # Force TLS if not present
    if redis_url.startswith("redis://"):
        tls_url = redis_url.replace("redis://", "rediss://")
        print("🔄 Upgrading to TLS (rediss://)...")
    else:
        tls_url = redis_url
        print("ℹ️  Already using TLS/other scheme")

    # Obfuscate
    safe_url = tls_url
    if "@" in tls_url:
        prefix, suffix = tls_url.split("@")
        safe_url = f"{prefix.split(':')[0]}:***@{suffix}"
    
    print(f"Testing URL: {safe_url}")

    try:
        # Note: ssl_cert_reqs=None to bypass self-signed cert issues if any
        r = redis.from_url(
            tls_url,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            ssl_cert_reqs=None 
        )
        print("Pinging Redis...")
        response = r.ping()
        print(f"Response: {response}")
        print("✅ TLS Connection Successful!")

    except Exception as e:
        print(f"❌ TLS Connection failed: {e}")

if __name__ == "__main__":
    test_redis_tls()
