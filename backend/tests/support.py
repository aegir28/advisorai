"""Shared test helpers: throwaway signing keys, token minting, and fakes for the database."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.auth.dependencies import CurrentUser
from app.db.database import SystemOperation

ISSUER = "http://127.0.0.1:54321/auth/v1"


@dataclass
class KeyPair:
    kid: str
    private_key: ec.EllipticCurvePrivateKey
    public_key: ec.EllipticCurvePublicKey

    def jwk(self) -> dict[str, Any]:
        entry = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.public_key))
        return {**entry, "kid": self.kid, "alg": "ES256", "use": "sig"}

    def public_pem(self) -> bytes:
        return self.public_key.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )


def make_keypair(kid: str = "key-1") -> KeyPair:
    private = ec.generate_private_key(ec.SECP256R1())
    return KeyPair(kid=kid, private_key=private, public_key=private.public_key())


class StaticKeyProvider:
    """A `KeyProvider` holding fixed keys."""

    def __init__(self, *pairs: KeyPair) -> None:
        self._keys = {p.kid: p.public_key for p in pairs}

    async def get_key(self, kid: str) -> Any | None:
        return self._keys.get(kid)


def claims(
    sub: uuid.UUID | str | None = None,
    *,
    aud: str = "authenticated",
    iss: str = ISSUER,
    expires_in: int = 3600,
    role: str | None = "authenticated",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(sub if sub is not None else uuid.uuid4()),
        "aud": aud,
        "iss": iss,
        "iat": now,
        "exp": now + expires_in,
    }
    if role is not None:
        payload["role"] = role
    payload.update(extra or {})
    return payload


def mint(keys: KeyPair, payload: dict[str, Any] | None = None, *, kid: str | None = None) -> str:
    return jwt.encode(
        payload if payload is not None else claims(),
        keys.private_key,
        algorithm="ES256",
        headers={"kid": kid if kid is not None else keys.kid},
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def forge_unsigned(payload: dict[str, Any], kid: str) -> str:
    """An `alg: none` token with an empty signature."""
    header = _b64(json.dumps({"alg": "none", "typ": "JWT", "kid": kid}).encode())
    return f"{header}.{_b64(json.dumps(payload).encode())}."


def forge_hs256_with_public_key(payload: dict[str, Any], kid: str, public_pem: bytes) -> str:
    """The classic algorithm-confusion attack: HS256, signed with the PUBLIC key as the secret."""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid}).encode())
    body = _b64(json.dumps(payload).encode())
    signature = hmac.new(public_pem, f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


# ── Fakes ────────────────────────────────────────────────────────────────────────────────────────
class FakeResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> "FakeResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._row


class FakeConnection:
    def __init__(self, row: dict[str, Any] | None, log: list[tuple[str, dict[str, Any]]]) -> None:
        self._row = row
        self._log = log

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        self._log.append((str(statement), dict(params or {})))
        return FakeResult(self._row)


@dataclass
class FakeDatabase:
    """Stands in for `Database`: records who a session was opened for and what was executed."""

    row: dict[str, Any] | None = None
    ping_error: Exception | None = None
    users: list[CurrentUser] = field(default_factory=list)
    system_operations: list[SystemOperation] = field(default_factory=list)
    executed: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    @asynccontextmanager
    async def user_session(self, user: CurrentUser) -> AsyncIterator[FakeConnection]:
        self.users.append(user)
        yield FakeConnection(self.row, self.executed)

    @asynccontextmanager
    async def system_session(self, operation: SystemOperation) -> AsyncIterator[FakeConnection]:
        self.system_operations.append(operation)
        yield FakeConnection(self.row, self.executed)

    async def ping(self) -> None:
        if self.ping_error is not None:
            raise self.ping_error

    async def dispose(self) -> None:
        return None
