"""Redis-backed fixed-window rate limiting, per docs/05-security-anti-fraud.md's
per-endpoint limits table. The full sweep across every endpoint is Phase 7 —
this is wired into auth (docs/02's OTP endpoints) now since it's part of
those endpoints' documented contract.
"""

from fastapi import HTTPException

from app.redis_client import redis_client


async def rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    full_key = f"ratelimit:{key}"
    count = await redis_client.incr(full_key)
    if count == 1:
        await redis_client.expire(full_key, window_seconds)
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "RATE_LIMITED", "message": "too many requests, try again later"}},
        )
