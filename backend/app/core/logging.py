"""Logging setup: one line per record, always carrying the request ID."""

import logging

from .request_id import RequestIdFilter

_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger("advisorai")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False
