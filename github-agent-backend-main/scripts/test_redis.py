
import os
import sys
import redis
from dotenv import load_dotenv

sys.path.append(os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

def test_redis():
    redis_url = os.getenv("REDIS_URL")
    
    print(f"Testing Redis connection...")
    if not redis_url:
        print("❌ REDIS_URL is not set in .env")
        return

    # Obfuscate credentials for display
    safe_url = redis_url
    if "@" in redis_url:
        prefix, suffix = redis_url.split("@")
        safe_url = f"{prefix.split(':')[0]}:***@{suffix}"
    
    print(f"URL: {safe_url}")

    try:
        r = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        print("Pinging Redis...")
        response = r.ping()
        print(f"Response: {response}")
        
        # Test write/read
        print("Testing SET/GET...")
        r.set("test_key", "hello_redis")
        val = r.get("test_key")
        print(f"Values: {val}")
        
        if val == "hello_redis":
            print("✅ Redis connection successful!")
        else:
            print("❌ Value mismatch!")

    except Exception as e:
        print(f"❌ Redis connection failed: {e}")

if __name__ == "__main__":
    test_redis()
