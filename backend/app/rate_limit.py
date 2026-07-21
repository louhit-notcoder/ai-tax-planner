from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Any

from .config import get_settings


class RateLimiter:
    """Multi-instance rate limiter in production, in-memory only for local development."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._memory: dict[str, deque[float]] = defaultdict(deque)
        self._memory_lock = asyncio.Lock()
        self._redis: Any | None = None
        if self.settings.rate_limit_backend == "redis":
            try:
                from redis.asyncio import Redis
            except ImportError as exc:
                raise RuntimeError("redis package is required when RATE_LIMIT_BACKEND=redis") from exc
            self._redis = Redis.from_url(self.settings.redis_url, decode_responses=True)

    async def allowed(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
        if self._redis is None:
            return await self._allowed_memory(key, limit=limit, window_seconds=window_seconds)
        bucket = f"gp:rl:{window_seconds}:{key}:{int(time.time() // window_seconds)}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(bucket)
                pipe.expire(bucket, window_seconds + 5)
                count, _ = await pipe.execute()
            return int(count) <= limit
        except Exception:
            # Production fails closed for abuse protection.
            return False

    async def _allowed_memory(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        async with self._memory_lock:
            window = self._memory[key]
            while window and window[0] < now - window_seconds:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
