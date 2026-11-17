"""Optional structured response diagnostics; applications configure logging."""

import logging
from typing import Any

from ._redact import redact


_L = logging.getLogger("wcpan.synology")
RESPONSE_LOG_LIMIT = 4096


class ResponseDetails:
    def __init__(self, body: Any) -> None:
        self._body = redact(body)

    def __str__(self) -> str:
        detail = str(self._body)
        if len(detail) > RESPONSE_LOG_LIMIT:
            return detail[:RESPONSE_LOG_LIMIT] + " [truncated]"
        return detail

    def __repr__(self) -> str:
        return str(self)


def log_response(operation: str, body: Any) -> None:
    _L.debug("%s response: %s", operation, ResponseDetails(body))


def log_invalid_response(operation: str) -> None:
    _L.debug("%s response body omitted: not valid JSON", operation)
