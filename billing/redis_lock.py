"""
Redis-backed distributed lock.

Why this exists
----------------
amnezia-api's client-creation flow on the VPN server is read-modify-write
without any locking on its side: it reads the interface config file, computes
a free IP, appends a new [Peer] block in the app's memory, then writes the
whole file back and applies it. If two POST /clients requests for the same
VPN server overlap (two purchases at nearly the same time, a retry racing the
original request, etc.), the second write can be based on a config snapshot
read *before* the first write landed — the first peer is silently lost from
the file even though amnezia-api returned 200 with a well-formed config to
that first caller. The client then holds a config that was never applied to
the server's WireGuard interface, and the connection never comes up.

We don't control amnezia-api's code, so we fix this on our side: never let
billing send two concurrent client-mutating requests (create/delete/patch)
to the *same* VPN server. A per-server Redis lock serializes those calls
without limiting throughput across different servers.
"""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# A single connection pool for the process; redis-py handles pooling
# internally, so creating this once at import time is safe and cheap.
# Short timeouts matter here: if Redis is unreachable (down, or simply
# absent — e.g. in the unit test environment, which mocks AmneziaClient but
# doesn't run a Redis container), we want to fail fast into the except
# RedisError branch below rather than hang the request for the default
# multi-second socket timeout.
_redis: Redis = Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
)

_UNLOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# How long a lock is held before it auto-expires if the process holding it
# crashes without releasing it. Must comfortably exceed the slowest realistic
# amnezia-api call (docker exec + wg syncconf), with headroom.
#
# AmneziaClient's HTTP methods retry up to 3 times on 5xx/connection errors
# (see integrations/amnezia/client.py's _retryable), with exponential backoff
# between attempts. Worst case inside one lock-held call: 3 attempts at
# AmneziaClient.DEFAULT_TIMEOUT (15s) each, plus waits of ~2s and ~4s between
# them ≈ 51s. TTL must exceed that, or the lock can expire mid-retry and
# reopen the exact concurrent-write race it exists to prevent.
DEFAULT_LOCK_TTL_SECONDS = 75

# How long a caller waits to acquire the lock before giving up.
DEFAULT_WAIT_TIMEOUT_SECONDS = 20
_POLL_INTERVAL_SECONDS = 0.2


class LockTimeoutError(RuntimeError):
    """Raised when a lock could not be acquired within the wait timeout."""


@asynccontextmanager
async def redis_lock(
    key: str,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
    wait_timeout_seconds: int = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> AsyncIterator[None]:
    """
    Hold an exclusive Redis lock for the duration of the `async with` block.

    Blocks (polling) until the lock is acquired or `wait_timeout_seconds`
    elapses, in which case `LockTimeoutError` is raised. The lock has a TTL
    so a crashed holder can't wedge the key forever.

    If Redis itself is unavailable, we log and let the caller proceed
    unlocked rather than hard-failing client provisioning — a missed lock
    under a Redis outage is strictly better than blocking all purchases.
    """
    token = uuid.uuid4().hex
    lock_key = f"lock:{key}"
    acquired = False

    try:
        elapsed = 0.0
        while elapsed < wait_timeout_seconds:
            acquired = await _redis.set(lock_key, token, nx=True, ex=ttl_seconds)
            if acquired:
                break
            import asyncio

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

        if not acquired:
            raise LockTimeoutError(
                f"Could not acquire lock '{lock_key}' within {wait_timeout_seconds}s"
            )
    except RedisError as exc:
        logger.warning(
            "Redis unavailable while acquiring lock '%s' (%s) — proceeding "
            "without the lock. Concurrent requests to the same VPN server "
            "may race.",
            lock_key,
            exc,
        )
        acquired = False

    try:
        yield
    finally:
        if acquired:
            try:
                await _redis.eval(_UNLOCK_SCRIPT, 1, lock_key, token)
            except RedisError as exc:
                logger.warning(
                    "Failed to release lock '%s': %s (will expire via TTL)",
                    lock_key,
                    exc,
                )
