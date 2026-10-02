"""Supabase JWT verification (ADR 0005, step 1).

Everything about a token is checked before any database context is built from it: signature (JWKS,
asymmetric keys only), expiry, issuer, audience = authenticated, subject. The rejection REASON is a
short code for server-side logs; it is never sent to the caller.
"""

import uuid
from dataclasses import dataclass

import jwt

from .jwks import KeyProvider, KeyUnavailableError

AUDIENCE = "authenticated"
# Asymmetric algorithms only. `none` and every HS* algorithm are rejected, which closes the classic
# algorithm-confusion attack (a public key used as an HMAC secret).
ALLOWED_ALGORITHMS = frozenset({"ES256", "RS256", "EdDSA"})


class AuthError(Exception):
    """The token is not acceptable. `reason` is for logs only."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AuthUnavailableError(Exception):
    """Verification could not run (for example the key set is unreachable). Not the caller's fault."""


@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    sub: uuid.UUID
    session_id: str | None


class JwtVerifier:
    def __init__(self, keys: KeyProvider, issuer: str, *, leeway_seconds: int = 5) -> None:
        self._keys = keys
        self._issuer = issuer
        self._leeway = leeway_seconds

    async def verify(self, token: str) -> VerifiedClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("malformed") from exc

        algorithm = header.get("alg")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise AuthError("algorithm_not_allowed")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise AuthError("missing_kid")

        try:
            key = await self._keys.get_key(kid)
        except KeyUnavailableError as exc:
            raise AuthUnavailableError from exc
        if key is None:
            raise AuthError("unknown_key")

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=AUDIENCE,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthError("wrong_audience") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthError("wrong_issuer") from exc
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            # Bad signature, missing claim, or a key of the wrong type for the algorithm (PyJWT raises
            # TypeError/ValueError for some of those). Any of them is "invalid", never a 500.
            raise AuthError("invalid") from exc

        if claims.get("role") != "authenticated":
            raise AuthError("wrong_role")
        if claims.get("is_anonymous") is True:
            raise AuthError("anonymous_session")
        try:
            subject = uuid.UUID(str(claims["sub"]))
        except ValueError as exc:
            raise AuthError("bad_subject") from exc

        session_id = claims.get("session_id")
        return VerifiedClaims(sub=subject, session_id=session_id if isinstance(session_id, str) else None)
