import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.ips = {}

    async def dispatch(self, request: Request, call_next):
        from backend.recovery_ext.flags import get_flags
        flags = get_flags()
        
        if not flags.enable_rate_limiting:
            return await call_next(request)
            
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Clean up old records
        self.ips = {k: v for k, v in self.ips.items() if now - v["start"] < self.window_seconds}
        
        if ip not in self.ips:
            self.ips[ip] = {"count": 1, "start": now}
        else:
            self.ips[ip]["count"] += 1
            if self.ips[ip]["count"] > self.max_requests:
                return JSONResponse(status_code=429, content={"detail": "Too many requests"})
                
        return await call_next(request)
