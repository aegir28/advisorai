"""HMAC signing for the backend <-> n8n channel (both directions).

Signature = HMAC-SHA256(secret, "<timestamp>.<METHOD>.<path>.<sha256(body)>"), hex. The timestamp is checked
against a clock-skew window (replay limit); the body hash binds the signature to exactly one payload. The
secret is a deployment secret on both sides; it is never logged, and a wrong signature reveals nothing.
"""

import hashlib
import hmac
import time

TIMESTAMP_HEADER = "X-Advisorai-Timestamp"
SIGNATURE_HEADER = "X-Advisorai-Signature"


def sign(secret: bytes, method: str, path: str, body: bytes, timestamp: int | None = None) -> tuple[str, str]:
    """(timestamp, signature) for an outgoing request."""
    ts = str(int(time.time()) if timestamp is None else timestamp)
    return ts, _mac(secret, ts, method, path, body)


def _mac(secret: bytes, ts: str, method: str, path: str, body: bytes) -> str:
    material = f"{ts}.{method.upper()}.{path}.{hashlib.sha256(body).hexdigest()}".encode()
    return hmac.new(secret, material, hashlib.sha256).hexdigest()


def verify(
    secret: bytes,
    method: str,
    path: str,
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    *,
    max_skew_seconds: int,
    now: float | None = None,
) -> bool:
    if not timestamp or not signature or not timestamp.isdigit():
        return False
    if abs((time.time() if now is None else now) - int(timestamp)) > max_skew_seconds:
        return False
    return hmac.compare_digest(_mac(secret, timestamp, method, path, body), signature)
