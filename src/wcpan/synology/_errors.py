"""Interpret only Drive Files codes supported by observed UI behavior."""

from collections.abc import Mapping
from typing import Any, cast

from .exceptions import (
    SynologyApiError,
    SynologyBusyError,
    SynologyConflictError,
    SynologyDirectoryNotFoundError,
    SynologyFileTooLargeError,
    SynologyInvalidNameError,
    SynologyInvalidOperationError,
    SynologyLockedError,
    SynologyNameTooLongError,
    SynologyNotFoundError,
    SynologyPathTooLongError,
    SynologyPermissionError,
    SynologyProtocolError,
    SynologyQuotaExceededError,
    SynologyStorageFullError,
    SynologyUnsupportedError,
    SynologyUploadBusyError,
    SynologyUploadConflictError,
    SynologyUploadDirectoryNotFoundError,
    SynologyUploadError,
    SynologyUploadFileTooLargeError,
    SynologyUploadInvalidNameError,
    SynologyUploadInvalidOperationError,
    SynologyUploadLockedError,
    SynologyUploadNameTooLongError,
    SynologyUploadNotFoundError,
    SynologyUploadPathTooLongError,
    SynologyUploadPermissionError,
    SynologyUploadProtocolError,
    SynologyUploadQuotaExceededError,
    SynologyUploadStorageFullError,
    SynologyUploadUnsupportedError,
)


def response_object(
    value: object, message: str, *, operation: str | None = None
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SynologyProtocolError(message, operation=operation)
    return cast(dict[str, Any], value)


def response_field(data: Mapping[str, Any], key: str, expected: type) -> Any:
    value = data.get(key)
    if not isinstance(value, expected):
        raise SynologyProtocolError(f"Invalid response field {key!r}")
    return value


def file_error(error: SynologyApiError) -> SynologyApiError:
    # Evidence and scope: docs/error-model.md (Drive UI TI97 bundles).
    # Do not apply these codes to other API families.
    classes: dict[int, type[SynologyApiError]] = {
        1002: SynologyPermissionError,
        1003: SynologyNotFoundError,
        1005: SynologyDirectoryNotFoundError,
        1008: SynologyDirectoryNotFoundError,
        1009: SynologyInvalidOperationError,
        1010: SynologyInvalidOperationError,
        1011: SynologyUnsupportedError,
        1014: SynologyStorageFullError,
        1015: SynologyStorageFullError,
        1016: SynologyQuotaExceededError,
        1017: SynologyQuotaExceededError,
        1018: SynologyBusyError,
        1019: SynologyBusyError,
        1020: SynologyBusyError,
        1021: SynologyBusyError,
        1022: SynologyConflictError,
        1024: SynologyInvalidOperationError,
        1025: SynologyInvalidOperationError,
        1032: SynologyInvalidNameError,
        1033: SynologyFileTooLargeError,
        1034: SynologyPathTooLongError,
        1035: SynologyNameTooLongError,
        1047: SynologyBusyError,
        1068: SynologyPermissionError,
        1069: SynologyLockedError,
        1070: SynologyPermissionError,
        1078: SynologyBusyError,
    }
    cls = classes.get(error.error_code) if error.error_code is not None else None
    if cls is None or isinstance(error, cls):
        return error
    return cls(
        str(error),
        error_code=error.error_code,
        error=error.error,
        operation=error.operation,
        http_status=error.http_status,
    )


def upload_error(error: SynologyApiError, file_name: str) -> SynologyUploadError:
    mapped = file_error(error)
    classes: dict[type[SynologyApiError], type[SynologyUploadError]] = {
        SynologyProtocolError: SynologyUploadProtocolError,
        SynologyConflictError: SynologyUploadConflictError,
        SynologyPermissionError: SynologyUploadPermissionError,
        SynologyNotFoundError: SynologyUploadNotFoundError,
        SynologyDirectoryNotFoundError: SynologyUploadDirectoryNotFoundError,
        SynologyInvalidOperationError: SynologyUploadInvalidOperationError,
        SynologyUnsupportedError: SynologyUploadUnsupportedError,
        SynologyStorageFullError: SynologyUploadStorageFullError,
        SynologyQuotaExceededError: SynologyUploadQuotaExceededError,
        SynologyBusyError: SynologyUploadBusyError,
        SynologyInvalidNameError: SynologyUploadInvalidNameError,
        SynologyFileTooLargeError: SynologyUploadFileTooLargeError,
        SynologyPathTooLongError: SynologyUploadPathTooLongError,
        SynologyNameTooLongError: SynologyUploadNameTooLongError,
        SynologyLockedError: SynologyUploadLockedError,
    }
    cls = classes.get(type(mapped), SynologyUploadError)
    return cls(
        str(error),
        file_name=file_name,
        error_code=error.error_code,
        error=error.error,
        operation=error.operation,
        http_status=error.http_status,
    )
