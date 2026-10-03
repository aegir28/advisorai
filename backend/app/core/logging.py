"""Logging setup: one line per record, always carrying the request ID, with secrets redacted.

Blueprint: signed URLs, JWTs and keys are never logged. The code avoids putting them in log calls in
the first place; this formatter is the safety net for the day something slips through.
"""

import logging
import re

from .request_id import RequestIdFilter

_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    # JWTs (header.payload.signature, base64url)
    (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"), "[redacted-jwt]"),
    # Authorization / apikey values
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"), r"\1 [redacted]"),
    # Signed URL tokens and similar secrets, in a query string or a plain key=value pair
    (re.compile(r"(?i)\b((?:token|apikey|access_token|signature|sig)=)[^&\s\"']+"), r"\1[redacted]"),
    # Provider API keys (sk-..., sk-proj-...): the key itself, wherever it appears
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "[redacted-key]"),
    # Passwords inside connection strings: scheme://user:password@host
    (re.compile(r"(?i)(://[^:/\s@]+:)[^@\s]+@"), r"\1[redacted]@"),
]


def redact(message: str) -> str:
    for pattern, replacement in _REDACTIONS:
        message = pattern.sub(replacement, message)
    return message


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(_FORMAT))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger("advisorai")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False

    # httpx logs every request URL at INFO. Keep it quiet: signed-URL calls carry sensitive paths.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
