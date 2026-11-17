"""Track and close upload sources independently of the HTTP writer."""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from types import TracebackType
from typing import Self


class UploadSource(AsyncIterator[bytes]):
    def __init__(self, data: AsyncIterable[bytes]) -> None:
        self._iterator = aiter(data)
        self._lock = asyncio.Lock()
        self._closed = False
        self.error: Exception | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            await self.aclose()
        except Exception as cleanup_error:
            if exc is None:
                raise
            exc.add_note(
                f"Upload source cleanup also failed: {type(cleanup_error).__name__}"
            )

    async def __anext__(self) -> bytes:
        async with self._lock:
            if self._closed:
                raise StopAsyncIteration
            try:
                return await anext(self._iterator)
            except StopAsyncIteration:
                raise
            except Exception as exc:
                self.error = exc
                raise

    async def aclose(self) -> None:
        # Wait for an in-flight read to finish before closing its iterator.
        # Once closed, any late HTTP-writer reads stop without touching it.
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            close = getattr(self._iterator, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception as exc:
                    if self.error is None:
                        self.error = exc
                    raise
