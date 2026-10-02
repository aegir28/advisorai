"""JWKS key provider: fetches and caches the project's public signing keys.

Only asymmetric keys are accepted (EC, RSA, OKP/EdDSA). Symmetric (`oct`) entries are ignored, so a
shared secret can never be smuggled in through the key set.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx
import jwt

logger = logging.getLogger("advisorai.auth")

_ASYMMETRIC_KEY_TYPES = {"EC", "RSA", "OKP"}


class KeyUnavailableError(Exception):
    """The key set could not be fetched and there is no cached copy to fall back on."""


class KeyProvider(Protocol):
    async def get_key(self, kid: str) -> Any | None:
        """The public key for `kid`, or None if the key set has no such key."""


class JwksKeyProvider:
    """Cache with a TTL. An unknown `kid` triggers one refetch (key rotation), rate-limited so a
    stream of forged `kid`s cannot turn into a stream of outbound requests."""

    def __init__(
        self,
        url: str,
        http: httpx.AsyncClient,
        *,
        ttl_seconds: float = 600.0,
        min_refetch_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = url
        self._http = http
        self._ttl = ttl_seconds
        self._min_refetch = min_refetch_seconds
        self._clock = clock
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str) -> Any | None:
        async with self._lock:
            now = self._clock()
            stale = self._fetched_at is None or now - self._fetched_at >= self._ttl
            unknown = kid not in self._keys
            can_refetch = self._fetched_at is None or now - self._fetched_at >= self._min_refetch
            if stale or (unknown and can_refetch):
                await self._refresh(now)
            return self._keys.get(kid)

    async def _refresh(self, now: float) -> None:
        try:
            response = await self._http.get(self._url, timeout=5.0)
            response.raise_for_status()
            document = response.json()
            keys: dict[str, Any] = {}
            for entry in document.get("keys", []):
                if entry.get("kty") not in _ASYMMETRIC_KEY_TYPES or not entry.get("kid"):
                    continue
                keys[entry["kid"]] = jwt.PyJWK.from_dict(entry).key
        except (httpx.HTTPError, ValueError, KeyError, jwt.PyJWTError) as exc:
            # Log the exception type only: nothing from the response body.
            logger.warning("JWKS refresh failed (%s)", type(exc).__name__)
            if self._fetched_at is None:
                raise KeyUnavailableError from exc
            # Keep serving the last good key set, and back off before trying again.
            self._fetched_at = now - self._ttl + self._min_refetch
            return
        self._keys = keys
        self._fetched_at = now
