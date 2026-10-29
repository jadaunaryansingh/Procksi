"""
Enhanced Caching Layer for Database IO Optimization
Implements multi-level caching with Redis for expensive queries
"""
from functools import wraps
from typing import Optional, Callable, Any
import json
import hashlib
from redis import Redis
import os
from datetime import datetime

# Initialize Redis connection
redis_client: Optional[Redis] = None

def get_redis_client() -> Optional[Redis]:
    """Get or create Redis client"""
    global redis_client
    
    if redis_client is None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                redis_client = Redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                # Test connection
                redis_client.ping()
                print("✅ Redis cache connected successfully")
            except Exception as e:
                print(f"⚠️  Redis connection failed: {e}")
                redis_client = None
    
    return redis_client


def cache_key(*args, **kwargs) -> str:
    """Generate cache key from function arguments"""
    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
    return hashlib.md5(key_data.encode()).hexdigest()


def cached(
    ttl: int = 3600,
    key_prefix: str = "",
    skip_cache: Callable[[Any], bool] = None
):
    """
    Decorator for caching function results in Redis
    
    Args:
        ttl: Time to live in seconds (default: 1 hour)
        key_prefix: Prefix for cache keys
        skip_cache: Optional function to determine if cache should be skipped
    
    Usage:
        @cached(ttl=3600, key_prefix="leaderboard")
        async def get_batch_leaderboard(batch_id: str):
            # Expensive query
            return data
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            redis = get_redis_client()
            
            # Skip cache if Redis unavailable or skip condition met
            if redis is None or (skip_cache and skip_cache(*args, **kwargs)):
                return await func(*args, **kwargs)
            
            # Generate cache key
            cache_id = cache_key(*args, **kwargs)
            full_key = f"{key_prefix}:{cache_id}" if key_prefix else cache_id
            
            # Try to get from cache
            try:
                cached_data = redis.get(full_key)
                if cached_data:
                    print(f"✅ Cache HIT: {key_prefix}")
                    return json.loads(cached_data)
            except Exception as e:
                print(f"⚠️  Cache read error: {e}")
            
            # Cache miss - execute function
            print(f"❌ Cache MISS: {key_prefix}")
            result = await func(*args, **kwargs)
            
            # Store in cache
            try:
                redis.setex(
                    full_key,
                    ttl,
                    json.dumps(result, default=str)  # default=str for datetime serialization
                )
            except Exception as e:
                print(f"⚠️  Cache write error: {e}")
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            redis = get_redis_client()
            
            # Skip cache if Redis unavailable or skip condition met
            if redis is None or (skip_cache and skip_cache(*args, **kwargs)):
                return func(*args, **kwargs)
            
            # Generate cache key
            cache_id = cache_key(*args, **kwargs)
            full_key = f"{key_prefix}:{cache_id}" if key_prefix else cache_id
            
            # Try to get from cache
            try:
                cached_data = redis.get(full_key)
                if cached_data:
                    print(f"✅ Cache HIT: {key_prefix}")
                    return json.loads(cached_data)
            except Exception as e:
                print(f"⚠️  Cache read error: {e}")
            
            # Cache miss - execute function
            print(f"❌ Cache MISS: {key_prefix}")
            result = func(*args, **kwargs)
            
            # Store in cache
            try:
                redis.setex(
                    full_key,
                    ttl,
                    json.dumps(result, default=str)
                )
            except Exception as e:
                print(f"⚠️  Cache write error: {e}")
            
            return result
        
        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def invalidate_cache(key_pattern: str):
    """
    Invalidate cache entries matching pattern
    
    Args:
        key_pattern: Pattern to match (e.g., "leaderboard:*", "batch:123:*")
    """
    redis = get_redis_client()
    if redis is None:
        return
    
    try:
        # Find matching keys
        keys = redis.keys(key_pattern)
        if keys:
            redis.delete(*keys)
            print(f"🗑️  Invalidated {len(keys)} cache entries: {key_pattern}")
    except Exception as e:
        print(f"⚠️  Cache invalidation error: {e}")


def invalidate_team_caches(team_id: str, batch_id: str = None):
    """Invalidate all caches related to a team"""
    redis = get_redis_client()
    if redis is None:
        return
    
    patterns = [
        f"team:{team_id}:*",
        f"leaderboard:*",  # Leaderboard includes this team
    ]
    
    if batch_id:
        patterns.extend([
            f"batch:{batch_id}:*",
            f"batch_stats:{batch_id}:*",
        ])
    
    for pattern in patterns:
        invalidate_cache(pattern)


# Cache statistics
def get_cache_stats() -> dict:
    """Get Redis cache statistics"""
    redis = get_redis_client()
    if redis is None:
        return {"status": "unavailable"}
    
    try:
        info = redis.info("stats")
        return {
            "status": "connected",
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "hit_rate": round(
                info.get("keyspace_hits", 0) / 
                (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1)) * 100,
                2
            ),
            "total_keys": redis.dbsize()
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# Warmup function
def warmup_cache(batch_id: str):
    """Pre-warm cache with critical data"""
    from src.api.backend.routers.reports import get_batch_leaderboard_report
    
    print(f"🔥 Warming up cache for batch {batch_id}")
    # This will populate cache
    # get_batch_leaderboard_report(batch_id)
    # Add other critical queries here
