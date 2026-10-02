from typing import Any

import httpx
import pytest

from app.auth.jwks import JwksKeyProvider, KeyUnavailableError
from tests.support import KeyPair, make_keypair

pytestmark = pytest.mark.anyio

URL = "http://127.0.0.1:54321/auth/v1/.well-known/jwks.json"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeJwks:
    """A JWKS endpoint that counts requests and can be changed or broken."""

    def __init__(self, *pairs: KeyPair) -> None:
        self.keys: list[dict[str, Any]] = [p.jwk() for p in pairs]
        self.calls = 0
        self.fail = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.fail:
            return httpx.Response(503, text="nope")
        return httpx.Response(200, json={"keys": self.keys})


def provider(endpoint: FakeJwks, clock: Clock, **kw: float) -> JwksKeyProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(endpoint.handler))
    return JwksKeyProvider(URL, client, clock=clock, **kw)


async def test_fetches_once_and_caches() -> None:
    k1 = make_keypair("k1")
    endpoint, clock = FakeJwks(k1), Clock()
    keys = provider(endpoint, clock)
    assert await keys.get_key("k1") is not None
    assert await keys.get_key("k1") is not None
    assert endpoint.calls == 1


async def test_refetches_after_the_ttl() -> None:
    endpoint, clock = FakeJwks(make_keypair("k1")), Clock()
    keys = provider(endpoint, clock, ttl_seconds=600)
    await keys.get_key("k1")
    clock.now += 601
    await keys.get_key("k1")
    assert endpoint.calls == 2


async def test_an_unknown_kid_triggers_one_refetch_for_key_rotation() -> None:
    old, new = make_keypair("old"), make_keypair("new")
    endpoint, clock = FakeJwks(old), Clock()
    keys = provider(endpoint, clock, min_refetch_seconds=30)
    assert await keys.get_key("old") is not None
    endpoint.keys = [old.jwk(), new.jwk()]  # the project rotated its keys
    clock.now += 31
    assert await keys.get_key("new") is not None
    assert endpoint.calls == 2


async def test_forged_kids_cannot_cause_a_stream_of_outbound_requests() -> None:
    endpoint, clock = FakeJwks(make_keypair("k1")), Clock()
    keys = provider(endpoint, clock, min_refetch_seconds=30)
    await keys.get_key("k1")
    for i in range(20):
        assert await keys.get_key(f"forged-{i}") is None
    assert endpoint.calls == 1  # inside the cooldown: no refetch at all


async def test_symmetric_and_malformed_entries_are_ignored() -> None:
    k1 = make_keypair("k1")
    endpoint, clock = FakeJwks(k1), Clock()
    endpoint.keys += [{"kty": "oct", "kid": "shared", "k": "c2VjcmV0"}, {"kty": "EC", "crv": "P-256"}]
    keys = provider(endpoint, clock)
    assert await keys.get_key("k1") is not None
    assert await keys.get_key("shared") is None


async def test_an_outage_with_no_cached_keys_is_reported_as_unavailable() -> None:
    endpoint, clock = FakeJwks(make_keypair("k1")), Clock()
    endpoint.fail = True
    with pytest.raises(KeyUnavailableError):
        await provider(endpoint, clock).get_key("k1")


async def test_an_outage_keeps_serving_the_last_good_keys_and_backs_off() -> None:
    endpoint, clock = FakeJwks(make_keypair("k1")), Clock()
    keys = provider(endpoint, clock, ttl_seconds=600, min_refetch_seconds=30)
    assert await keys.get_key("k1") is not None
    endpoint.fail = True
    clock.now += 700
    assert await keys.get_key("k1") is not None  # stale but still valid keys
    calls_after_failure = endpoint.calls
    assert await keys.get_key("k1") is not None
    assert endpoint.calls == calls_after_failure  # backing off, not hammering


async def test_a_garbage_response_is_treated_as_an_outage() -> None:
    clock = Clock()
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>")))
    with pytest.raises(KeyUnavailableError):
        await JwksKeyProvider(URL, client, clock=clock).get_key("k1")
