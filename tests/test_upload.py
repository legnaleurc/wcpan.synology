from unittest import IsolatedAsyncioTestCase

from wcpan.synology._upload import UploadSource
from wcpan.synology.exceptions import (
    SynologyApiError,
)


class TestUploadCleanup(IsolatedAsyncioTestCase):
    async def test_cleanup_failure_does_not_replace_read_failure(self):
        error = SynologyApiError("source missing", error_code=1003)
        cause = OSError("source storage failed")
        cleanup_error = RuntimeError("close failed")

        class Source:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise error from cause

            async def aclose(self):
                raise cleanup_error

        source = UploadSource(Source())
        with self.assertRaises(SynologyApiError) as caught:
            async with source:
                await anext(source)
        self.assertIs(caught.exception, error)
        self.assertIs(caught.exception.__cause__, cause)
        self.assertIs(source.error, error)
        self.assertTrue(any("RuntimeError" in note for note in error.__notes__))

    async def test_cleanup_failure_after_success_is_reported(self):
        cleanup_error = RuntimeError("close failed")

        class Source:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

            async def aclose(self):
                raise cleanup_error

        with self.assertRaises(RuntimeError) as caught:
            async with UploadSource(Source()) as source:
                self.assertEqual([chunk async for chunk in source], [])
        self.assertIs(caught.exception, cleanup_error)
