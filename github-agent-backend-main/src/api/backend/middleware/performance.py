"""
Performance Monitoring Middleware
Tracks slow queries, request duration, and database IO patterns
"""
import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import json

logger = logging.getLogger("performance")

class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track request performance and log slow endpoints
    """
    
    def __init__(self, app, slow_threshold: float = 1.0):
        """
        Args:
            app: FastAPI application
            slow_threshold: Time in seconds to consider request "slow" (default: 1.0s)
        """
        super().__init__(app)
        self.slow_threshold = slow_threshold
        self.request_count = 0
        self.slow_request_count = 0
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Start timer
        start_time = time.time()
        
        # Get request details
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params)
        
        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # Log exception
            duration = time.time() - start_time
            logger.error(
                f"❌ REQUEST FAILED | {method} {path} | "
                f"Duration: {duration:.3f}s | Error: {str(e)}"
            )
            raise
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Increment counters
        self.request_count += 1
        
        # Log slow requests
        if duration > self.slow_threshold:
            self.slow_request_count += 1
            
            # Format query params for logging
            params_str = json.dumps(query_params) if query_params else "none"
            
            logger.warning(
                f"🐌 SLOW REQUEST | {method} {path} | "
                f"Duration: {duration:.3f}s | "
                f"Status: {status_code} | "
                f"Params: {params_str}"
            )
            
            # Add header to response for debugging
            response.headers["X-Response-Time"] = f"{duration:.3f}s"
            response.headers["X-Slow-Request"] = "true"
        else:
            # Add timing header to all responses
            response.headers["X-Response-Time"] = f"{duration:.3f}s"
        
        # Log critical endpoints (always log certain paths regardless of speed)
        if path.startswith("/api/reports") or path.startswith("/api/teams"):
            logger.info(
                f"📊 REPORT REQUEST | {method} {path} | "
                f"Duration: {duration:.3f}s | Status: {status_code}"
            )
        
        return response
    
    def get_stats(self) -> dict:
        """Get middleware statistics"""
        return {
            "total_requests": self.request_count,
            "slow_requests": self.slow_request_count,
            "slow_request_percentage": round(
                (self.slow_request_count / self.request_count * 100) if self.request_count > 0 else 0,
                2
            ),
            "slow_threshold_seconds": self.slow_threshold
        }


# Query tracking decorator
def track_query(query_name: str):
    """
    Decorator to track specific database query performance
    
    Usage:
        @track_query("get_batch_leaderboard")
        async def get_leaderboard(batch_id: str):
            # query logic
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start
                
                if duration > 0.5:  # Log queries >500ms
                    logger.warning(
                        f"🔍 SLOW QUERY: {query_name} | Duration: {duration:.3f}s"
                    )
                
                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(
                    f"❌ QUERY FAILED: {query_name} | Duration: {duration:.3f}s | Error: {str(e)}"
                )
                raise
        
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start
                
                if duration > 0.5:
                    logger.warning(
                        f"🔍 SLOW QUERY: {query_name} | Duration: {duration:.3f}s"
                    )
                
                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(
                    f"❌ QUERY FAILED: {query_name} | Duration: {duration:.3f}s | Error: {str(e)}"
                )
                raise
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Database query logger
class DatabaseQueryLogger:
    """Log database queries for analysis"""
    
    def __init__(self):
        self.queries = []
        self.enabled = False
    
    def log_query(self, table: str, operation: str, filters: dict, duration: float):
        """Log a database query"""
        if not self.enabled:
            return
        
        self.queries.append({
            "table": table,
            "operation": operation,
            "filters": filters,
            "duration": duration,
            "timestamp": time.time()
        })
    
    def get_slow_queries(self, threshold: float = 0.5):
        """Get queries slower than threshold"""
        return [q for q in self.queries if q["duration"] > threshold]
    
    def get_stats(self):
        """Get query statistics"""
        if not self.queries:
            return {"total_queries": 0}
        
        durations = [q["duration"] for q in self.queries]
        return {
            "total_queries": len(self.queries),
            "avg_duration": sum(durations) / len(durations),
            "max_duration": max(durations),
            "min_duration": min(durations),
            "slow_queries": len(self.get_slow_queries())
        }
    
    def clear(self):
        """Clear logged queries"""
        self.queries = []


# Global query logger instance
query_logger = DatabaseQueryLogger()
