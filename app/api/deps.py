import secrets
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

from app.config import get_settings

_checks: dict[str, deque] = defaultdict(deque)
_admin: dict[str, deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    """Take the entry our own trusted proxy appended (counted from the right), never the client-supplied first one."""
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    hops = max(1, get_settings().trusted_proxy_hops)
    if len(parts) >= hops:
        return parts[-hops]
    return request.client.host if request.client else "unknown"


def origin(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _hit(store: dict[str, deque], key: str, limit: int, msg: str) -> None:
    now, window = time.time(), store[key]
    if len(store) > 5000:  # keep memory bounded
        for k in [k for k, v in store.items() if not v or now - v[-1] > 60]:
            del store[k]
        window = store[key]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(429, msg)
    window.append(now)


def rate_limit(request: Request) -> None:
    """Per-IP sliding window (in-memory, per instance). Protects your Claude/search bill."""
    _hit(_checks, client_ip(request), get_settings().rate_limit_per_minute,
         "Too many requests. Please wait a minute and try again.")


def rate_limit_admin(request: Request) -> None:
    _hit(_admin, client_ip(request), 60, "Too many admin requests.")


def require_admin(x_admin_key: str = Header(default="")) -> None:
    key = get_settings().admin_key
    if not key:
        raise HTTPException(503, "Admin is disabled (ADMIN_KEY is not set).")
    if not secrets.compare_digest(x_admin_key.encode(), key.encode()):
        raise HTTPException(401, "Invalid admin key.")
