class SynologyError(Exception):
    pass


class SynologyAuthenticationError(SynologyError):
    pass


class SynologyApiError(SynologyError):
    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        payload: object | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.payload = payload


class SynologyNetworkError(SynologyError):
    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class SynologyUploadError(SynologyError):
    def __init__(self, message: str, *, file_name: str | None = None) -> None:
        super().__init__(message)
        self.file_name = file_name


class SynologyPermanentUploadError(SynologyUploadError):
    """An upload failure that cannot succeed by retrying unchanged."""

    retryable = False


class SynologyNameTooLongError(SynologyPermanentUploadError):
    """Synology rejected the destination name as too long."""

    reason = "name_too_long"


class SynologyUploadConflictError(SynologyUploadError):
    pass
