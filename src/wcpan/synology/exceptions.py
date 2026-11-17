from typing import Any

from ._redact import redact


class SynologyError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*(redact(arg) for arg in args))


class SynologyApiError(SynologyError):
    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        error: dict[str, Any] | None = None,
        operation: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.error: dict[str, Any] | None = redact(error)
        self.operation: str | None = redact(operation)
        self.http_status = http_status


class SynologyAuthenticationError(SynologyApiError):
    """The authentication API rejected the login."""


class SynologyProtocolError(SynologyApiError):
    """The server returned an invalid or unexpected response."""


class SynologyNotFoundError(SynologyApiError):
    """The requested Drive node does not exist."""


class SynologyPermissionError(SynologyApiError):
    """Drive denied access to the requested operation."""


class SynologyConflictError(SynologyApiError):
    """The destination name is already taken."""


class SynologyDirectoryNotFoundError(SynologyNotFoundError):
    """A required directory does not exist."""


class SynologyInvalidOperationError(SynologyApiError):
    """The requested source and destination combination is invalid."""


class SynologyUnsupportedError(SynologyApiError):
    """Drive does not support this operation."""


class SynologyStorageFullError(SynologyApiError):
    """Drive has insufficient storage space."""


class SynologyQuotaExceededError(SynologyStorageFullError):
    """The volume or shared-folder quota is exhausted."""


class SynologyBusyError(SynologyApiError):
    """Drive is performing maintenance or moving data."""


class SynologyInvalidNameError(SynologyApiError):
    """The destination uses a reserved name."""


class SynologyFileTooLargeError(SynologyApiError):
    """The file exceeds the permitted size."""


class SynologyPathTooLongError(SynologyApiError):
    """The destination path is too long."""


class SynologyLockedError(SynologyApiError):
    """The node is locked."""


class SynologyTransportError(Exception):
    """Safe transport failure details, without a request URL or response body."""

    def __init__(self, error: Exception) -> None:
        self.error_type = type(error).__name__
        self.errno = error.errno if isinstance(error, OSError) else None
        super().__init__(self.error_type)


class SynologyNetworkError(SynologyError):
    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
        *,
        operation: str | None = None,
        http_status: int | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.original_error = original_error
        self.operation: str | None = redact(operation)
        self.http_status = http_status
        self.error: dict[str, Any] | None = redact(error)


class SynologyUploadError(SynologyApiError):
    def __init__(
        self,
        message: str,
        *,
        file_name: str | None = None,
        error_code: int | None = None,
        error: dict[str, Any] | None = None,
        operation: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(
            message,
            error_code=error_code,
            error=error,
            operation=operation,
            http_status=http_status,
        )
        self.file_name = file_name


class SynologyPermanentUploadError(SynologyUploadError):
    """An upload failure that cannot succeed by retrying unchanged."""

    retryable = False


class SynologyNameTooLongError(SynologyApiError):
    """Synology rejected the destination name as too long."""


class SynologyUploadConflictError(SynologyUploadError, SynologyConflictError):
    pass


class SynologyUploadProtocolError(SynologyUploadError, SynologyProtocolError):
    pass


class SynologyUploadPermissionError(SynologyUploadError, SynologyPermissionError):
    pass


class SynologyUploadNotFoundError(SynologyUploadError, SynologyNotFoundError):
    pass


class SynologyUploadDirectoryNotFoundError(
    SynologyUploadNotFoundError, SynologyDirectoryNotFoundError
):
    pass


class SynologyUploadInvalidOperationError(
    SynologyUploadError, SynologyInvalidOperationError
):
    pass


class SynologyUploadUnsupportedError(SynologyUploadError, SynologyUnsupportedError):
    pass


class SynologyUploadStorageFullError(SynologyUploadError, SynologyStorageFullError):
    pass


class SynologyUploadQuotaExceededError(
    SynologyUploadStorageFullError, SynologyQuotaExceededError
):
    pass


class SynologyUploadBusyError(SynologyUploadError, SynologyBusyError):
    pass


class SynologyUploadInvalidNameError(
    SynologyPermanentUploadError, SynologyInvalidNameError
):
    pass


class SynologyUploadFileTooLargeError(
    SynologyPermanentUploadError, SynologyFileTooLargeError
):
    pass


class SynologyUploadPathTooLongError(
    SynologyPermanentUploadError, SynologyPathTooLongError
):
    pass


class SynologyUploadNameTooLongError(
    SynologyPermanentUploadError, SynologyNameTooLongError
):
    reason = "name_too_long"


class SynologyUploadLockedError(SynologyUploadError, SynologyLockedError):
    pass
