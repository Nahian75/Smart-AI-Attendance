"""Tenant resolution and simple in-process rate limiting."""
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Stricter limit for auth endpoints to prevent brute-force attacks
_AUTH_PATHS = {"/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/change-password"}
_AUTH_RPM = 60   # 60 attempts per minute per IP (brute-force protection)
_CLEANUP_INTERVAL = 300  # purge stale buckets every 5 minutes


class TenantMiddleware(BaseHTTPMiddleware):
    """Attach tenant context from the X-Tenant-ID header or JWT to request.state."""
    async def dispatch(self, request: Request, call_next):
        request.state.tenant_id = request.headers.get("X-Tenant-ID")
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 200):
        super().__init__(app)
        self.rpm = requests_per_minute
        self._buckets: dict[str, list[float]] = {}
        self._last_cleanup: float = time.time()

    def _cleanup(self, now: float) -> None:
        """Remove bucket entries for IPs that have been idle for over a minute."""
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        stale = [ip for ip, ts in self._buckets.items() if not ts or now - ts[-1] > 60]
        for ip in stale:
            del self._buckets[ip]
        self._last_cleanup = now

    async def dispatch(self, request: Request, call_next):
        client = request.client.host if request.client else "unknown"
        now = time.time()

        self._cleanup(now)

        is_auth = request.url.path in _AUTH_PATHS
        limit = _AUTH_RPM if is_auth else self.rpm

        window = self._buckets.setdefault(client, [])
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= limit:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        window.append(now)
        return await call_next(request)
