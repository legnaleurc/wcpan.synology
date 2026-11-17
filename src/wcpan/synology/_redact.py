"""Sanitize known credential fields in parsed JSON and header dictionaries."""

from typing import Any, cast

from ._secret import Secret


_SECRET_FIELDS = frozenset(
    {
        "sid",
        "_sid",
        "session_id",
        "password",
        "passwd",
        "otp_code",
        "account",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "synotoken",
        "api_key",
        "client_secret",
        "secret",
        "x_syno_token",
        "x_api_key",
    }
)


def redact(value: Any) -> Any:
    if isinstance(value, Secret):
        return str(value)
    if isinstance(value, dict):
        result = {
            key: "[REDACTED]"
            if str(key).lower().replace("-", "_") in _SECRET_FIELDS
            else redact(item)
            for key, item in cast(dict[str, Any], value).items()
        }
        return result
    if isinstance(value, list):
        return [redact(item) for item in cast(list[Any], value)]
    return value
