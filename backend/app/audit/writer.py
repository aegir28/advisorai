"""Audit writer: records WHAT happened, never what a record says (blueprint, security part).

Rules enforced here AND by a CHECK constraint in the database:

* metadata keys come from a small allow-list and values are short scalars, so content cannot be
  smuggled into an audit row;
* the client IP is stored only as an HMAC-SHA256 under a server-side secret;
* rows are written on the narrow `app_system` path, in their own transaction, so an audit row is not
  lost when the business transaction rolls back.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import uuid
from enum import StrEnum
from typing import Any, Protocol

from pydantic import SecretStr
from sqlalchemy import text

from app.core.request_id import get_request_id
from app.db.database import Database, SystemOperation


class AuditAction(StrEnum):
    """Events from the blueprint's audit table that exist in this phase. Add more with their feature."""

    CASE_CREATE = "case.create"
    CASE_UPDATE = "case.update"
    CASE_DELETE = "case.delete"
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_VIEW = "document.view"
    DOCUMENT_DOWNLOAD = "document.download"
    DOCUMENT_DELETE = "document.delete"
    DOCUMENT_SIGNED_URL_ISSUED = "document.signed_url_issued"
    WORKFLOW_START = "workflow.start"
    WORKFLOW_FINISH = "workflow.finish"
    AI_CALL = "ai.call"
    DATA_DELETION = "data.deletion"
    ADMIN_ACCESS = "admin.access"


ALLOWED_METADATA_KEYS = frozenset(
    {
        "result",
        "scope",
        "verifier",
        "reason",
        "count",
        "ttl_seconds",
        "status",
        "step",
        "completed_at",
        "model",
        "provider",
        "tier",
    }
)
_MAX_VALUE_LENGTH = 120

_INSERT = text(
    "insert into public.audit_logs"
    " (actor_user_id, action, target_type, target_id, request_id, ip_hash, metadata)"
    " values (:actor, :action, :target_type, :target_id, :request_id, :ip_hash, cast(:metadata as jsonb))"
)


logger = logging.getLogger("advisorai.audit")


class AuditError(Exception):
    pass


class AuditRecorder(Protocol):
    """What callers need from an audit writer (so tests and other writers can stand in)."""

    async def record_completed(
        self,
        action: AuditAction,
        *,
        actor: uuid.UUID | None,
        target_type: str | None = None,
        target_id: str | None = None,
        client_ip: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


def validate_metadata(metadata: dict[str, Any]) -> dict[str, str | int | bool]:
    clean: dict[str, str | int | bool] = {}
    for key, value in metadata.items():
        if key not in ALLOWED_METADATA_KEYS:
            raise AuditError(f"audit metadata key {key!r} is not allowed")
        if isinstance(value, bool | int) or (isinstance(value, str) and len(value) <= _MAX_VALUE_LENGTH):
            clean[key] = value
        else:
            raise AuditError(f"audit metadata value for {key!r} must be a short string, int or bool")
    return clean


class AuditWriter:
    def __init__(self, database: Database, ip_hmac_secret: SecretStr | None) -> None:
        self._database = database
        self._secret = ip_hmac_secret

    def hash_ip(self, client_ip: str | None) -> str | None:
        """HMAC-SHA256 of the canonical IP, or None when there is no IP or no secret configured."""
        if client_ip is None or self._secret is None:
            return None
        try:
            canonical = ipaddress.ip_address(client_ip).compressed
        except ValueError:
            return None
        key = self._secret.get_secret_value().encode()
        return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()

    async def record(
        self,
        action: AuditAction,
        *,
        actor: uuid.UUID | None,
        target_type: str | None = None,
        target_id: str | None = None,
        client_ip: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        clean = validate_metadata(metadata or {})
        async with self._database.system_session(SystemOperation.AUDIT_APPEND) as connection:
            await connection.execute(
                _INSERT,
                {
                    "actor": actor,
                    "action": action.value,
                    "target_type": target_type,
                    "target_id": target_id,
                    "request_id": get_request_id(),
                    "ip_hash": self.hash_ip(client_ip),
                    "metadata": json.dumps(clean, separators=(",", ":")),
                },
            )

    async def record_completed(
        self,
        action: AuditAction,
        *,
        actor: uuid.UUID | None,
        target_type: str | None = None,
        target_id: str | None = None,
        client_ip: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Audit an operation that has ALREADY committed (create, delete, upload).

        The business transaction cannot be undone and a 500 would misreport it, so a failure here is
        logged at ERROR (no content: the action and request ID only) and does not fail the request. Use
        `record` where the audit row must exist BEFORE something is released (a signed URL).
        """
        try:
            await self.record(
                action,
                actor=actor,
                target_type=target_type,
                target_id=target_id,
                client_ip=client_ip,
                metadata=metadata,
            )
        except Exception:
            logger.error("audit write failed for %s", action.value, exc_info=True)
