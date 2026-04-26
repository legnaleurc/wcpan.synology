from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, call, patch

from wcpan.synology import SynologyNameTooLongError, SynologyPermanentUploadError
from wcpan.synology.client import SynologyClient
from wcpan.synology.errors import (
    SynologyApiError,
    SynologyNetworkError,
    SynologyUploadConflictError,
    SynologyUploadError,
)
from wcpan.synology.types import (
    SynologyChildRef,
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
        client = SynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        rv = await client.upload(SynologyPath("id:parent"), "file.bin", chunks())

        self.assertEqual("id", rv["file_id"])

    async def test_upload_conflict(self) -> None:
        transport = MagicMock()
        transport.upload = AsyncMock(
            side_effect=SynologyApiError("conflict", error_code=1022)
        )
        client = SynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        with self.assertRaises(SynologyUploadConflictError):
            await client.upload(SynologyPath("id:parent"), "file.bin", chunks())

    async def test_upload_error_from_api(self) -> None:
        transport = MagicMock()
        transport.upload = AsyncMock(
            side_effect=SynologyApiError("bad", error_code=108)
        )
        client = SynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        with self.assertRaises(SynologyUploadError):
            await client.upload(SynologyPath("id:parent"), "file.bin", chunks())

    async def test_upload_error_from_network(self) -> None:
        transport = MagicMock()
        error = SynologyNetworkError("reset", ConnectionResetError("reset"))
        transport.upload = AsyncMock(side_effect=error)
        client = SynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        with self.assertRaises(SynologyNetworkError) as caught:
            await client.upload(SynologyPath("id:parent"), "file.bin", chunks())
        self.assertIs(caught.exception.original_error, error)
        self.assertIs(caught.exception.__cause__, error)
        self.assertIn("file.bin", str(caught.exception))

    async def test_upload_parent_file_id_is_normalized_for_child_path(self) -> None:
        transport = MagicMock()
        transport.upload = AsyncMock(return_value=make_file_info("id", "file.bin"))
        client = SynologyClient(transport=transport)

        async def chunks():
            yield b"data"

        await client.upload(SynologyFileId("parent-id"), "file.bin", chunks())

        _, kwargs = transport.upload.await_args
        self.assertEqual("id:parent-id/file.bin", kwargs["form_fields"]["path"])


class TestTaskPolling(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        patcher = patch("wcpan.synology.client.asyncio.sleep", new_callable=AsyncMock)
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    async def test_task_can_finish_after_sixth_poll(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(
            side_effect=[{"status": "running"}] * 6 + [{"status": "finished"}]
        )
        await SynologyClient(transport=transport).wait_task("task-id")
        self.assertEqual(transport.request.await_count, 7)

    async def test_task_exhausts_ten_polls(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value={"status": "running"})
        with self.assertRaisesRegex(SynologyApiError, "did not finish in time"):
            await SynologyClient(transport=transport).wait_task("task-id")
        self.assertEqual(transport.request.await_count, 10)
        self.assertEqual(
            self.sleep.await_args_list,
            [call(0.5), call(1.0), call(2.0)] + [call(4.0)] * 7,
        )

    async def test_wait_task_raises_on_reported_error(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(
            return_value={
                "status": "finished",
                "result": {"errors": [{"code": 1022, "message": "conflict"}]},
            }
        )
        client = SynologyClient(transport=transport)

        with self.assertRaises(SynologyApiError):
            await client.wait_task("task-id")


class TestPathParameters(IsolatedAsyncioTestCase):
    async def test_get_file_returns_none_for_empty_success_payload(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value=None)

        result = await SynologyClient(transport=transport).get_file(
            SynologyFileId("missing")
        )

        self.assertIsNone(result)

    async def test_get_file_propagates_api_error(self) -> None:
        error = SynologyApiError("permission denied", error_code=105)
        transport = MagicMock()
        transport.request = AsyncMock(side_effect=error)

        with self.assertRaises(SynologyApiError) as caught:
            await SynologyClient(transport=transport).get_file(
                SynologyFileId("inaccessible")
            )

        self.assertIs(caught.exception, error)

    async def test_get_file_accepts_child_ref(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value=make_file_info("id", "file.bin"))
        client = SynologyClient(transport=transport)

        await client.get_file(SynologyChildRef(SynologyFileId("parent-id"), "file.bin"))

        _, kwargs = transport.request.await_args
        self.assertEqual("id:parent-id/file.bin", kwargs["path"])

    async def test_list_folder_accepts_sort_options(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value={"items": [], "total": 0})

        await SynologyClient(transport=transport).list_folder(
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
        client = SynologyClient(transport=transport)

        await client.get_file(SynologyFileId("node-id"))

        _, kwargs = transport.request.await_args
        self.assertEqual("id:node-id", kwargs["path"])

    async def test_get_file_accepts_permanent_link(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value=make_file_info("id", "file.bin"))
        client = SynologyClient(transport=transport)

        await client.get_file(SynologyPermanentLink("perm://node"))

        _, kwargs = transport.request.await_args
        self.assertEqual("link:perm://node", kwargs["path"])

    async def test_rename_accepts_synology_path(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value=make_file_info("id", "renamed.bin"))
        client = SynologyClient(transport=transport)

        await client.rename(SynologyPath("/mydrive/file.bin"), "renamed.bin")

        _, kwargs = transport.request.await_args
        self.assertEqual("/mydrive/file.bin", kwargs["path"])

    async def test_move_uses_distinct_node_and_parent_serialization(self) -> None:
        transport = MagicMock()
        transport.request = AsyncMock(return_value={"async_task_id": "task-id"})
        client = SynologyClient(transport=transport)
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
        client = SynologyClient(transport=transport)
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
                client = SynologyClient(transport=transport)
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
                client = SynologyClient(transport=transport)
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
                client = SynologyClient(transport=transport)
                with self.assertRaises(SynologyUploadConflictError):
                    await getattr(client, operation)(SynologyFileId("node"), "name")

    async def test_rename_keeps_generic_name_too_long_error(self) -> None:
        error = SynologyApiError("name too long", error_code=1035)
        transport = MagicMock()
        transport.request = AsyncMock(side_effect=error)
        with self.assertRaises(SynologyApiError) as caught:
            await SynologyClient(transport=transport).rename(
                SynologyFileId("node"), "long"
            )
        self.assertIs(caught.exception, error)
