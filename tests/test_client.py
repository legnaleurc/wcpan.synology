from contextlib import asynccontextmanager
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, call, patch

from wcpan.synology._client import DefaultSynologyClient
from wcpan.synology.exceptions import (
    SynologyApiError,
    SynologyNameTooLongError,
    SynologyNetworkError,
    SynologyPermanentUploadError,
    SynologyUploadConflictError,
    SynologyUploadError,
)
from wcpan.synology.lib import create_client
from wcpan.synology.types import (
    SynologyChildRef,
    SynologyClient,
    SynologyFileId,
    SynologyPath,
    SynologyPermanentLink,
)


def make_file_info(file_id: str, name: str) -> dict:
    return {
        "file_id": file_id,
        "parent_id": "parent",
        "name": name,
        "type": "file",
        "content_type": "file",
        "size": 0,
        "created_time": 0,
        "modified_time": 0,
        "sync_id": 1,
    }


class TestClientUpload(IsolatedAsyncioTestCase):
    async def test_upload_success(self) -> None:
        transport = MagicMock()
        transport.upload = AsyncMock(return_value=make_file_info("id", "file.bin"))
        client = DefaultSynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        rv = await client.upload(SynologyPath("id:parent"), "file.bin", chunks())

        self.assertEqual("id", rv["file_id"])

    async def test_upload_conflict(self) -> None:
        transport = MagicMock()
        transport.upload = AsyncMock(
            side_effect=SynologyApiError("conflict", error_code=1022)
        )
        client = DefaultSynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        with self.assertRaises(SynologyUploadConflictError):
            await client.upload(SynologyPath("id:parent"), "file.bin", chunks())

    async def test_upload_error_from_api(self) -> None:
        transport = MagicMock()
        transport.upload = AsyncMock(
            side_effect=SynologyApiError("bad", error_code=108)
        )
        client = DefaultSynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        with self.assertRaises(SynologyUploadError):
            await client.upload(SynologyPath("id:parent"), "file.bin", chunks())

    async def test_upload_error_from_network(self) -> None:
        transport = MagicMock()
        error = SynologyNetworkError("reset", ConnectionResetError("reset"))
        transport.upload = AsyncMock(side_effect=error)
        client = DefaultSynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        with self.assertRaises(SynologyNetworkError) as caught:
            await client.upload(SynologyPath("id:parent"), "file.bin", chunks())
        self.assertIs(caught.exception.original_error, error.original_error)
        self.assertIs(caught.exception.__cause__, error)
        self.assertIn("file.bin", str(caught.exception))

    async def test_upload_parent_file_id_is_normalized_for_child_path(self) -> None:
        transport = MagicMock()
        transport.upload = AsyncMock(return_value=make_file_info("id", "file.bin"))
        client = DefaultSynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        await client.upload(SynologyFileId("parent-id"), "file.bin", chunks())

        _, kwargs = transport.upload.await_args
        self.assertEqual("id:parent-id/file.bin", kwargs["form_fields"]["path"])


class TestTaskPolling(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        patcher = patch("wcpan.synology._client.asyncio.sleep", new_callable=AsyncMock)
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    async def test_task_can_finish_after_sixth_poll(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(
            side_effect=[{"status": "running"}] * 6 + [{"status": "finished"}]
        )
        await DefaultSynologyClient(transport=transport).wait_task("task-id")
        self.assertEqual(transport.request.await_count, 7)

    async def test_task_exhausts_ten_polls(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value={"status": "running"})
        with self.assertRaisesRegex(SynologyApiError, "did not finish in time"):
            await DefaultSynologyClient(transport=transport).wait_task("task-id")
        self.assertEqual(transport.request.await_count, 10)
        self.assertEqual(
            self.sleep.await_args_list,
            [call(0.5), call(1.0), call(2.0)] + [call(4.0)] * 7,
        )

    async def test_wait_task_accepts_null_errors(self) -> None:
        # A successful delete task, as observed live.
        transport = MagicMock()
        transport.request = AsyncMock(
            return_value={
                "status": "finished",
                "progress": 100,
                "result": {"action": "delete", "errors": None, "names": ["x"]},
            }
        )
        await DefaultSynologyClient(transport=transport).wait_task("task-id")

    async def test_wait_task_raises_on_reported_error(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(
            return_value={
                "status": "finished",
                "result": {"errors": [{"code": 1022, "message": "conflict"}]},
            }
        )
        client = DefaultSynologyClient(transport=transport)

        with self.assertRaises(SynologyApiError):
            await client.wait_task("task-id")


class TestPathParameters(IsolatedAsyncioTestCase):
    async def test_get_file_returns_file_info(self) -> None:
        transport = MagicMock()
        info = make_file_info("id", "file.bin")
        transport.request = AsyncMock(return_value=info)

        result = await DefaultSynologyClient(transport=transport).get_file(
            SynologyFileId("id")
        )

        self.assertIs(result, info)

    async def test_get_file_propagates_api_error(self) -> None:
        error = SynologyApiError("permission denied", error_code=105)
        transport = MagicMock()
        transport.request = AsyncMock(side_effect=error)

        with self.assertRaises(SynologyApiError) as caught:
            await DefaultSynologyClient(transport=transport).get_file(
                SynologyFileId("inaccessible")
            )

        self.assertIs(caught.exception, error)

    async def test_get_file_accepts_child_ref(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value=make_file_info("id", "file.bin"))
        client = DefaultSynologyClient(transport=transport)

        await client.get_file(SynologyChildRef(SynologyFileId("parent-id"), "file.bin"))

        _, kwargs = transport.request.await_args
        self.assertEqual("id:parent-id/file.bin", kwargs["path"])

    async def test_list_folder_accepts_sort_options(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value={"items": [], "total": 0})

        await DefaultSynologyClient(transport=transport).list_folder(
            SynologyFileId("folder"),
            sort_by="modified_time",
            sort_direction="desc",
        )

        _, kwargs = transport.request.await_args
        self.assertEqual("modified_time", kwargs["sort_by"])
        self.assertEqual("desc", kwargs["sort_direction"])

    async def test_get_file_accepts_file_id(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value=make_file_info("id", "file.bin"))
        client = DefaultSynologyClient(transport=transport)

        await client.get_file(SynologyFileId("node-id"))

        _, kwargs = transport.request.await_args
        self.assertEqual("id:node-id", kwargs["path"])

    async def test_get_file_accepts_permanent_link(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value=make_file_info("id", "file.bin"))
        client = DefaultSynologyClient(transport=transport)

        await client.get_file(SynologyPermanentLink("perm://node"))

        _, kwargs = transport.request.await_args
        self.assertEqual("link:perm://node", kwargs["path"])

    async def test_rename_accepts_synology_path(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value=make_file_info("id", "renamed.bin"))
        client = DefaultSynologyClient(transport=transport)

        await client.rename(SynologyPath("/mydrive/file.bin"), "renamed.bin")

        _, kwargs = transport.request.await_args
        self.assertEqual("/mydrive/file.bin", kwargs["path"])

    async def test_move_uses_distinct_node_and_parent_serialization(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value={"async_task_id": "task-id"})
        client = DefaultSynologyClient(transport=transport)
        client.wait_task = AsyncMock(return_value=None)

        await client.move(
            SynologyPermanentLink("perm://node"),
            SynologyFileId("parent-id"),
        )

        _, kwargs = transport.request.await_args
        self.assertEqual(["link:perm://node"], kwargs["files"])
        self.assertEqual("id:parent-id", kwargs["to_parent_folder"])

    async def test_delete_uses_canonical_file_id_format(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value={"async_task_id": "task-id"})
        client = DefaultSynologyClient(transport=transport)
        client.wait_task = AsyncMock(return_value=None)

        await client.delete(SynologyFileId("node-id"))

        _, kwargs = transport.request.await_args
        self.assertEqual(["id:node-id"], kwargs["files"])


class TestCompatibility(IsolatedAsyncioTestCase):
    async def test_destination_names_are_normalized(self) -> None:
        raw_name = "かなは\u3099.txt"
        expected_name = "かなば.txt"
        for operation in ("create_folder", "rename", "upload"):
            with self.subTest(operation=operation):
                transport = MagicMock()
                transport.request = AsyncMock(return_value={})
                transport.upload = AsyncMock(return_value={})
                client = DefaultSynologyClient(transport=transport)
                if operation == "upload":

                    async def chunks():
                        yield b"data"

                    await client.upload(SynologyFileId("parent"), raw_name, chunks())
                    kwargs = transport.upload.await_args.kwargs
                    self.assertEqual(kwargs["file_name"], expected_name)
                    self.assertEqual(
                        kwargs["form_fields"]["path"], f"id:parent/{expected_name}"
                    )
                elif operation == "create_folder":
                    await client.create_folder(SynologyFileId("parent"), raw_name)
                    self.assertEqual(
                        transport.request.await_args.kwargs["path"],
                        f"id:parent/{expected_name}",
                    )
                else:
                    await client.rename(SynologyFileId("node"), raw_name)
                    self.assertEqual(
                        transport.request.await_args.kwargs["name"], expected_name
                    )

    async def test_name_too_long_is_permanent(self) -> None:
        for operation in ("create_folder", "upload"):
            with self.subTest(operation=operation):
                error = SynologyApiError("name too long", error_code=1035)
                transport = MagicMock()
                transport.request = AsyncMock(side_effect=error)
                transport.upload = AsyncMock(side_effect=error)
                client = DefaultSynologyClient(transport=transport)
                with self.assertRaises(SynologyNameTooLongError) as caught:
                    if operation == "upload":

                        async def chunks():
                            yield b"data"

                        await client.upload(SynologyFileId("parent"), "long", chunks())
                    else:
                        await client.create_folder(SynologyFileId("parent"), "long")
                self.assertIsInstance(caught.exception, SynologyPermanentUploadError)
                self.assertIsInstance(caught.exception, SynologyUploadError)
                self.assertFalse(caught.exception.retryable)
                self.assertEqual(caught.exception.reason, "name_too_long")
                self.assertEqual(caught.exception.file_name, "long")
                self.assertIs(caught.exception.__cause__, error)

    async def test_create_and_rename_keep_conflict_behavior(self) -> None:
        for operation in ("create_folder", "rename"):
            with self.subTest(operation=operation):
                transport = MagicMock()
                transport.request = AsyncMock(
                    side_effect=SynologyApiError("conflict", error_code=1022)
                )
                client = DefaultSynologyClient(transport=transport)
                with self.assertRaises(SynologyUploadConflictError):
                    await getattr(client, operation)(SynologyFileId("node"), "name")

    async def test_rename_reports_name_too_long_error(self) -> None:
        error = SynologyApiError("name too long", error_code=1035)
        transport = MagicMock()
        transport.request = AsyncMock(side_effect=error)
        with self.assertRaises(SynologyApiError) as caught:
            await DefaultSynologyClient(transport=transport).rename(
                SynologyFileId("node"), "long"
            )
        self.assertIsInstance(caught.exception, SynologyNameTooLongError)
        self.assertIs(caught.exception.__cause__, error)


class TestClientFactory(IsolatedAsyncioTestCase):
    async def test_client_interface_is_abstract(self):
        with self.assertRaises(TypeError):
            SynologyClient()

    async def test_factory_yields_default_client_and_closes_transport(self):
        transport = MagicMock()
        transport.request = AsyncMock(return_value={"ok": True})
        closed = MagicMock()

        @asynccontextmanager
        async def transport_context(**kwargs):
            try:
                yield transport
            finally:
                closed()

        with patch(
            "wcpan.synology.lib.create_transport", side_effect=transport_context
        ) as factory:
            async with create_client(
                base_url="https://nas.example",
                username="user",
                password="secret",
                otp_code="123456",
            ) as client:
                self.assertIsInstance(client, SynologyClient)
                self.assertIsInstance(client, DefaultSynologyClient)
                self.assertEqual(
                    await client.call(api="test", version=1, method="get"), {"ok": True}
                )
                closed.assert_not_called()
            factory.assert_called_once_with(
                base_url="https://nas.example",
                username="user",
                password="secret",
                otp_code="123456",
            )
        closed.assert_called_once_with()
