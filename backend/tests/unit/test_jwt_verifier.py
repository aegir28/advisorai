import time
import uuid
from typing import Any

import jwt
import pytest

from app.auth.verifier import AuthError, AuthUnavailableError, JwtVerifier
from tests.support import (
    ISSUER,
    KeyPair,
    StaticKeyProvider,
    claims,
    forge_hs256_with_public_key,
    forge_unsigned,
    make_keypair,
    mint,
)

pytestmark = pytest.mark.anyio

USER = uuid.UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture(scope="module")
def keys() -> KeyPair:
    return make_keypair("key-1")


@pytest.fixture
def verifier(keys: KeyPair) -> JwtVerifier:
    return JwtVerifier(StaticKeyProvider(keys), ISSUER)


async def rejected(verifier: JwtVerifier, token: str) -> str:
    with pytest.raises(AuthError) as caught:
        await verifier.verify(token)
    return caught.value.reason


async def test_accepts_a_valid_token_and_returns_the_subject(verifier: JwtVerifier, keys: KeyPair) -> None:
    verified = await verifier.verify(mint(keys, claims(USER, extra={"session_id": "s-1"})))
    assert verified.sub == USER
    assert verified.session_id == "s-1"


async def test_rejects_an_expired_token(verifier: JwtVerifier, keys: KeyPair) -> None:
    assert await rejected(verifier, mint(keys, claims(USER, expires_in=-60))) == "expired"


async def test_a_few_seconds_of_clock_skew_is_tolerated(verifier: JwtVerifier, keys: KeyPair) -> None:
    await verifier.verify(mint(keys, claims(USER, expires_in=-2)))


async def test_rejects_the_wrong_issuer(verifier: JwtVerifier, keys: KeyPair) -> None:
    assert (
        await rejected(verifier, mint(keys, claims(USER, iss="https://evil.example/auth/v1")))
        == "wrong_issuer"
    )


async def test_rejects_the_wrong_audience(verifier: JwtVerifier, keys: KeyPair) -> None:
    assert await rejected(verifier, mint(keys, claims(USER, aud="anon"))) == "wrong_audience"
    assert await rejected(verifier, mint(keys, claims(USER, aud="service_role"))) == "wrong_audience"


async def test_rejects_a_token_signed_by_a_different_key_with_the_same_kid(verifier: JwtVerifier) -> None:
    attacker = make_keypair("key-1")  # same kid, different key
    assert await rejected(verifier, mint(attacker, claims(USER))) == "invalid"


async def test_rejects_an_unknown_kid(verifier: JwtVerifier, keys: KeyPair) -> None:
    assert await rejected(verifier, mint(keys, claims(USER), kid="rotated-away")) == "unknown_key"


async def test_rejects_a_token_without_a_kid(verifier: JwtVerifier, keys: KeyPair) -> None:
    token = jwt.encode(claims(USER), keys.private_key, algorithm="ES256")  # no kid header
    assert await rejected(verifier, token) == "missing_kid"


async def test_rejects_alg_none(verifier: JwtVerifier) -> None:
    assert await rejected(verifier, forge_unsigned(claims(USER), "key-1")) == "algorithm_not_allowed"


async def test_rejects_hs256_signed_with_the_public_key(verifier: JwtVerifier, keys: KeyPair) -> None:
    token = forge_hs256_with_public_key(claims(USER), "key-1", keys.public_pem())
    assert await rejected(verifier, token) == "algorithm_not_allowed"


@pytest.mark.parametrize("missing", ["exp", "iat", "sub", "aud", "iss"])
async def test_rejects_a_token_missing_a_required_claim(
    verifier: JwtVerifier, keys: KeyPair, missing: str
) -> None:
    payload = claims(USER)
    del payload[missing]
    assert await rejected(verifier, mint(keys, payload)) == "invalid"


@pytest.mark.parametrize("sub", ["not-a-uuid", "", "12345", "../../etc/passwd"])
async def test_rejects_a_subject_that_is_not_a_uuid(verifier: JwtVerifier, keys: KeyPair, sub: str) -> None:
    assert await rejected(verifier, mint(keys, claims(sub))) in {"bad_subject", "invalid"}


@pytest.mark.parametrize("role", ["anon", "service_role", None])
async def test_rejects_a_token_that_is_not_an_authenticated_user_role(
    verifier: JwtVerifier, keys: KeyPair, role: str | None
) -> None:
    assert await rejected(verifier, mint(keys, claims(USER, role=role))) == "wrong_role"


async def test_rejects_anonymous_sign_in_sessions(verifier: JwtVerifier, keys: KeyPair) -> None:
    assert (
        await rejected(verifier, mint(keys, claims(USER, extra={"is_anonymous": True})))
        == "anonymous_session"
    )


@pytest.mark.parametrize("garbage", ["", "abc", "a.b", "a.b.c", "Bearer x", "eyJhbGciOiJFUzI1NiJ9.e30.x"])
async def test_rejects_malformed_tokens(verifier: JwtVerifier, garbage: str) -> None:
    assert await rejected(verifier, garbage) in {"malformed", "algorithm_not_allowed", "missing_kid"}


async def test_rejects_a_token_whose_kid_points_at_a_key_of_the_wrong_type() -> None:
    """An RSA-only key set must not verify an ES256 token."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class RsaProvider:
        async def get_key(self, kid: str) -> Any | None:
            return rsa_key.public_key()

    ec_keys = make_keypair("key-1")
    verifier = JwtVerifier(RsaProvider(), ISSUER)
    assert await rejected(verifier, mint(ec_keys, claims(USER))) == "invalid"


async def test_key_provider_outage_is_not_reported_as_a_bad_token(keys: KeyPair) -> None:
    from app.auth.jwks import KeyUnavailableError

    class DownProvider:
        async def get_key(self, kid: str) -> Any | None:
            raise KeyUnavailableError

    with pytest.raises(AuthUnavailableError):
        await JwtVerifier(DownProvider(), ISSUER).verify(mint(keys, claims(USER)))


async def test_a_token_is_not_valid_beyond_its_expiry_plus_leeway(keys: KeyPair) -> None:
    strict = JwtVerifier(StaticKeyProvider(keys), ISSUER, leeway_seconds=0)
    token = mint(keys, claims(USER, expires_in=1))
    await strict.verify(token)
    time.sleep(1.2)
    with pytest.raises(AuthError):
        await strict.verify(token)
