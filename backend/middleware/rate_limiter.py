"""
Rate limiting middleware for JARVIS.
Prevents abuse of API endpoints.
"""
import asyncio
import time
from typing import Callable, Dict, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


class RateLimitConfig:
    """Configuration for rate limiting."""

    # Default limits (requests per minute)
    LIMITS = {
        "/health": "1000/minute",  # Health checks are cheap
        "/chat": "10/minute",  # Chat is expensive
        "/chat/process": "10/minute",
        "/chat/stream": "10/minute",
        "/autodev": "3/minute",  # Code generation is very expensive
        "/autodev/start": "1/minute",
        "/autonomy/start": "1/minute",  # One per 5 min recommended
        "/memory/save": "30/minute",  # Memory operations
        "/browser": "20/minute",  # Browser automation
        "/computer": "20/minute",  # System control
        "/shell": "5/minute",  # Dangerous - very limited
        "default": "100/minute",  # Default for other endpoints
    }

    # Session-based limits
    SESSION_LIMITS = {
        "chat": (10, 60),  # 10 requests per 60 seconds per session
        "autodev": (1, 300),  # 1 job per 5 minutes per session
        "autonomy": (1, 300),  # 1 start per 5 minutes
    }


class SessionRateLimiter:
    """Per-session rate limiter."""

    def __init__(self):
        self.sessions: Dict[str, Dict[str, list]] = {}
        self.cleanup_interval = 3600  # Cleanup old sessions every hour

    async def is_allowed(
        self, session_id: str, endpoint: str, limit: Tuple[int, int]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if request is allowed for session.

        Args:
            session_id: Session identifier
            endpoint: API endpoint
            limit: (max_requests, time_window_seconds)

        Returns:
            (is_allowed, error_message)
        """
        max_requests, window_seconds = limit
        now = time.time()

        if session_id not in self.sessions:
            self.sessions[session_id] = {}

        if endpoint not in self.sessions[session_id]:
            self.sessions[session_id][endpoint] = []

        # Remove old requests outside the window
        requests = self.sessions[session_id][endpoint]
        requests[:] = [ts for ts in requests if now - ts < window_seconds]

        # Check limit
        if len(requests) >= max_requests:
            retry_after = int(window_seconds - (now - requests[0]))
            return False, f"Rate limit exceeded. Retry after {retry_after}s"

        # Add current request
        requests.append(now)
        return True, None

    async def cleanup_old_sessions(self, max_age: int = 3600) -> None:
        """Remove sessions older than max_age seconds."""
        now = time.time()
        old_sessions = [
            sid
            for sid, data in self.sessions.items()
            if all(
                (now - ts) > max_age
                for endpoint_reqs in data.values()
                for ts in endpoint_reqs
            )
        ]
        for sid in old_sessions:
            del self.sessions[sid]


# Global instance
session_limiter = SessionRateLimiter()


async def rate_limit_middleware(request: Request, call_next: Callable):
    """Middleware for rate limiting."""
    path = request.url.path

    # Get session ID
    session_id = request.query_params.get("session_id") or request.headers.get(
        "X-Session-ID"
    )
    if not session_id:
        # Try to get from request body
        try:
            if request.method == "POST":
                body = await request.body()
                if body:
                    import json

                    data = json.loads(body)
                    session_id = data.get("session_id")
        except:
            pass

    session_id = session_id or get_remote_address(request)

    # Check session rate limits for specific endpoints
    for endpoint, (max_req, window) in RateLimitConfig.SESSION_LIMITS.items():
        if endpoint in path:
            allowed, error = await session_limiter.is_allowed(
                session_id, endpoint, (max_req, window)
            )
            if not allowed:
                return JSONResponse(
                    {
                        "error": error,
                        "status": "rate_limited",
                        "retry_after": window,
                    },
                    status_code=429,
                    headers={"Retry-After": str(window)},
                )

    # Continue with request
    response = await call_next(request)
    return response


def setup_rate_limiting(app: FastAPI) -> Limiter:
    """
    Setup rate limiting for FastAPI app.

    Returns:
        Configured Limiter instance
    """
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded, _rate_limit_exceeded_handler
    )
    return limiter


async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        {
            "error": "Rate limit exceeded",
            "detail": str(exc.detail),
            "status": "rate_limited",
        },
        status_code=429,
        headers={"Retry-After": "60"},
    )


# Decorator for manual rate limiting
def rate_limited(limit: str):
    """
    Decorator for rate limiting a specific route.

    Usage:
        @app.post("/expensive")
        @rate_limited("1/minute")
        async def expensive_operation():
            pass
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            # This would integrate with limiter from app state
            return await func(*args, **kwargs)

        return wrapper

    return decorator
