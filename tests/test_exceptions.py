from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from wcpan.synology._client import (
    _DefaultSynologyClient,
)
from wcpan.synology.exceptions import (
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
    SynologyPermanentUploadError,
    SynologyPermissionError,
    SynologyProtocolError,
    SynologyQuotaExceededError,
    SynologyStorageFullError,
    SynologyUnsupportedError,
    SynologyUploadConflictError,
    SynologyUploadError,
)
from wcpan.synology.types import (
    SynologyFileId,
    SynologyPath,
)


class TestFileErrors(IsolatedAsyncioTestCase):
    def setUp(self):
        self.transport = MagicMock()
        self.client = _DefaultSynologyClient(transport=self.transport)

    def fail_request(self, code):
        payload = {"success": False, "error": {"code": code}}
        error = SynologyApiError(
            "API rejected request", error_code=code, error=payload["error"]
        )
        self.transport.request = AsyncMock(side_effect=error)
        return error

    async def test_missing_lookup_raises_not_found(self):
        raw = self.fail_request(1003)
        with self.assertRaises(SynologyNotFoundError) as caught:
            await self.client.get_file(SynologyFileId("absent"))
        self.assertEqual(caught.exception.error_code, 1003)
        self.assertEqual(caught.exception.error, raw.error)
        self.assertIs(caught.exception.__cause__, raw)

    async def test_files_errors_preserve_diagnostics(self):
        for code, cls in [
            (1002, SynologyPermissionError),
            (1003, SynologyNotFoundError),
            (1005, SynologyDirectoryNotFoundError),
            (1008, SynologyDirectoryNotFoundError),
            (1009, SynologyInvalidOperationError),
            (1010, SynologyInvalidOperationError),
            (1011, SynologyUnsupportedError),
            (1014, SynologyStorageFullError),
            (1015, SynologyStorageFullError),
            (1016, SynologyQuotaExceededError),
            (1017, SynologyQuotaExceededError),
            (1018, SynologyBusyError),
            (1019, SynologyBusyError),
            (1020, SynologyBusyError),
            (1021, SynologyBusyError),
            (1024, SynologyInvalidOperationError),
            (1025, SynologyInvalidOperationError),
            (1032, SynologyInvalidNameError),
            (1033, SynologyFileTooLargeError),
            (1034, SynologyPathTooLongError),
            (1047, SynologyBusyError),
            (1068, SynologyPermissionError),
            (1069, SynologyLockedError),
            (1070, SynologyPermissionError),
            (1078, SynologyBusyError),
            (1022, SynologyConflictError),
            (1035, SynologyNameTooLongError),
        ]:
            with self.subTest(code=code):
                raw = self.fail_request(code)
                with self.assertRaises(cls) as caught:
                    await self.client.list_folder(SynologyPath("/folder"))
                self.assertIsInstance(caught.exception, SynologyApiError)
                self.assertEqual(caught.exception.error_code, code)
                self.assertEqual(caught.exception.error, raw.error)
                self.assertIs(caught.exception.__cause__, raw)

    async def test_missing_parent_is_not_a_missing_child(self):
        self.fail_request(1005)
        with self.assertRaises(SynologyDirectoryNotFoundError):
            await self.client.get_file(SynologyPath("/missing-parent/child"))

    async def test_sharing_error_is_not_mistaken_for_absence(self):
        # The UI sometimes displays protection errors as NON_EXIST, but its
        # message table distinguishes them from node_not_exist.
        raw = self.fail_request(1036)
        with self.assertRaises(SynologyApiError) as caught:
            await self.client.get_file(SynologyPath("/protected"))
        self.assertIs(caught.exception, raw)

    async def test_unknown_error_is_unchanged(self):
        raw = self.fail_request(99999)
        with self.assertRaises(SynologyApiError) as caught:
            await self.client.get_file(SynologyPath("/file"))
        self.assertIs(caught.exception, raw)

    async def test_permission_denied_is_not_absence(self):
        self.fail_request(1002)
        with self.assertRaises(SynologyPermissionError):
            await self.client.get_file(SynologyPath("/private"))

    async def test_webhook_codes_are_not_interpreted_as_files_codes(self):
        raw = self.fail_request(1003)
        with self.assertRaises(SynologyApiError) as caught:
            await self.client.list_webhooks(app_id="test")
        self.assertIs(caught.exception, raw)

    async def test_generic_call_stays_raw_even_for_files(self):
        raw = self.fail_request(1003)
        with self.assertRaises(SynologyApiError) as caught:
            await self.client.call(
                api="SYNO.SynologyDrive.Files", version=11, method="get"
            )
        self.assertIs(caught.exception, raw)

    async def test_move_task_failure_is_semantic(self):
        payload = {
            "status": "finished",
            "result": {"errors": [{"code": 1002, "message": "permission denied"}]},
        }
        self.transport.request = AsyncMock(
            side_effect=[{"async_task_id": "task"}, payload]
        )
        with patch("wcpan.synology._client.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(SynologyPermissionError) as caught:
                await self.client.move(SynologyFileId("file"), SynologyPath("/target"))
        self.assertEqual(caught.exception.error, payload["result"]["errors"][0])

    async def test_rename_name_too_long_has_context(self):
        raw = self.fail_request(1035)
        with self.assertRaises(SynologyNameTooLongError) as caught:
            await self.client.rename(SynologyFileId("file"), "long-name")
        self.assertEqual(caught.exception.file_name, "long-name")
        self.assertEqual(caught.exception.error, raw.error)

    async def test_upload_legacy_conflict_is_also_semantic(self):
        raw = self.fail_request(1022)
        self.transport.upload = AsyncMock(side_effect=raw)

        async def chunks():
            yield b"data"

        with self.assertRaises(SynologyUploadConflictError) as caught:
            await self.client.upload(SynologyPath("/parent"), "file", chunks())
        self.assertIsInstance(caught.exception, SynologyConflictError)
        self.assertIsInstance(caught.exception, SynologyUploadError)
        self.assertEqual(caught.exception.file_name, "file")
        self.assertEqual(caught.exception.error_code, 1022)
        self.assertEqual(caught.exception.error, raw.error)

    async def test_upload_permission_is_semantic(self):
        raw = self.fail_request(1002)
        self.transport.upload = AsyncMock(side_effect=raw)

        async def chunks():
            yield b"data"

        with self.assertRaises(SynologyPermissionError) as caught:
            await self.client.upload(SynologyPath("/parent"), "file", chunks())
        self.assertIsInstance(caught.exception, SynologyUploadError)
        self.assertEqual(caught.exception.file_name, "file")

    async def test_upload_errors_keep_semantics_and_context(self):
        for code, cls in [
            (1003, SynologyNotFoundError),
            (1005, SynologyDirectoryNotFoundError),
            (1009, SynologyInvalidOperationError),
            (1011, SynologyUnsupportedError),
            (1014, SynologyStorageFullError),
            (1016, SynologyQuotaExceededError),
            (1018, SynologyBusyError),
            (1032, SynologyInvalidNameError),
            (1033, SynologyFileTooLargeError),
            (1034, SynologyPathTooLongError),
            (1035, SynologyNameTooLongError),
            (1069, SynologyLockedError),
        ]:
            with self.subTest(code=code):
                raw = self.fail_request(code)
                self.transport.upload = AsyncMock(side_effect=raw)

                async def chunks():
                    yield b"data"

                with self.assertRaises(SynologyUploadError) as caught:
                    await self.client.upload(SynologyPath("/parent"), "file", chunks())
                self.assertIsInstance(caught.exception, cls)
                self.assertEqual(caught.exception.file_name, "file")
                self.assertEqual(caught.exception.error_code, code)
                self.assertEqual(caught.exception.error, raw.error)
                self.assertIs(caught.exception.__cause__, raw)
                if code in (1032, 1033, 1034, 1035):
                    self.assertIsInstance(
                        caught.exception, SynologyPermanentUploadError
                    )
                    self.assertFalse(caught.exception.retryable)

    async def test_generic_name_too_long_is_not_upload_error(self):
        self.fail_request(1035)
        with self.assertRaises(SynologyNameTooLongError) as caught:
            await self.client.get_file(SynologyFileId("file"))
        self.assertNotIsInstance(caught.exception, SynologyUploadError)

    async def test_get_file_rejects_missing_data(self):
        for data in (None, [], "file"):
            with self.subTest(data=data):
                self.transport.request = AsyncMock(return_value=data)
                with self.assertRaises(SynologyProtocolError):
                    await self.client.get_file(SynologyFileId("file"))

    async def test_typed_methods_reject_malformed_data(self):
        operations = [
            lambda: self.client.list_folder(SynologyPath("/")),
            lambda: self.client.move(SynologyFileId("file"), SynologyPath("/")),
            lambda: self.client.delete(SynologyFileId("file")),
            lambda: self.client.list_webhooks(app_id="1"),
            lambda: self.client.create_webhook(app_id="1", url="https://example.test"),
        ]
        for operation in operations:
            for data in (None, {}, {"items": None, "total": "1"}):
                with self.subTest(operation=operation, data=data):
                    self.transport.request = AsyncMock(return_value=data)
                    with self.assertRaises(SynologyProtocolError):
                        await operation()

    async def test_upload_protocol_failure_keeps_upload_context(self):
        self.transport.upload = AsyncMock(return_value=None)

        async def chunks():
            yield b"data"

        with self.assertRaises(SynologyUploadError) as caught:
            await self.client.upload(SynologyPath("/parent"), "file", chunks())
        self.assertIsInstance(caught.exception, SynologyProtocolError)
        self.assertEqual(caught.exception.file_name, "file")

    async def test_delete_task_failure_is_semantic(self):
        payload = {"status": "finished", "result": {"errors": [{"code": 1003}]}}
        self.transport.request = AsyncMock(
            side_effect=[{"async_task_id": "task"}, payload]
        )
        with patch("wcpan.synology._client.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(SynologyNotFoundError) as caught:
                await self.client.delete(SynologyFileId("file"))
        self.assertEqual(caught.exception.error, payload["result"]["errors"][0])
        self.assertEqual(caught.exception.__cause__.error_code, 1003)

    async def test_malformed_task_results_raise_protocol_error(self):
        for data in (
            None,
            {},
            {"status": "finished", "result": {}},
            {"status": "finished", "result": []},
            {"status": "finished", "result": {"errors": {}}},
            {"status": "finished", "result": {"errors": "none"}},
            {"status": "finished", "result": {"errors": [{}]}},
            {"status": "finished", "result": {"errors": [None]}},
            {"status": "finished", "result": {"errors": [{"code": "1003"}]}},
        ):
            with self.subTest(data=data):
                self.transport.request = AsyncMock(return_value=data)
                with patch(
                    "wcpan.synology._client.asyncio.sleep", new_callable=AsyncMock
                ):
                    with self.assertRaises(SynologyProtocolError) as caught:
                        await self.client.wait_task("task")
                    self.assertIsNone(caught.exception.error)
                    self.assertFalse(hasattr(caught.exception, "payload"))
