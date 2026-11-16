import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientConnectionError, ClientSession, ClientTimeout, web
from aiohttp.test_utils import TestServer

from wcpan.synology import (
    SynologyApiError,
    SynologyAuthenticationError,
    SynologyClient,
    SynologyConflictError,
    SynologyNetworkError,
    SynologyPath,
    SynologyProtocolError,
)
from wcpan.synology._transport import (
    SynologyTransport,
    build_multipart_body,
    encode_rpc_value,
    login,
)


class TestRpcErrors(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.response = MagicMock()
        self.response.json = AsyncMock()
        self.response.text = AsyncMock(return_value="<html>invalid</html>")
        self.session = MagicMock()
        for method in (self.session.get, self.session.post):
            method.return_value.__aenter__ = AsyncMock(return_value=self.response)
        self.transport = SynologyTransport(
            session=self.session, base_url="https://nas.example", sid="sid"
        )

    async def request(self, operation):
        if operation == "login":
            return await login(
                self.session,
                base_url="https://nas.example",
                username="user",
                password="pw",
            )
        if operation == "upload":

            async def chunks():
                yield b"hello"

            return await self.transport.upload(
                "api",
                1,
                "upload",
                form_fields={},
                file_name="file",
                file_data=chunks(),
                mime_type="application/octet-stream",
            )
        return await self.transport.request("api", 1, "get")

    async def test_invalid_envelopes_raise_protocol_error(self):
        for operation in ("login", "request", "upload"):
            for payload in (
                None,
                [],
                {},
                {"success": "false"},
                {"success": False, "error": None},
                {"success": False, "error": {}},
                {"success": False, "error": {"code": "1003"}},
            ):
                with self.subTest(operation=operation, payload=payload):
                    self.response.json.return_value = payload
                    with self.assertRaises(SynologyProtocolError):
                        await self.request(operation)

    async def test_invalid_json_is_protocol_error(self):
        self.response.json.side_effect = ValueError("bad JSON")
        for operation in ("login", "request", "upload"):
            with self.subTest(operation=operation):
                with self.assertRaises(SynologyProtocolError) as caught:
                    await self.request(operation)
                self.assertEqual(caught.exception.payload, "<html>invalid</html>")

    async def test_invalid_utf8_is_protocol_error(self):
        body = b"proxy error: \xff"
        self.response.json.side_effect = UnicodeDecodeError(
            "utf-8", body, 13, 14, "invalid start byte"
        )
        self.response.text.side_effect = lambda **kwargs: body.decode(
            "utf-8", errors=kwargs.get("errors", "strict")
        )
        for operation in ("login", "request", "upload"):
            with self.subTest(operation=operation):
                with self.assertRaises(SynologyProtocolError) as caught:
                    await self.request(operation)
                self.assertEqual(caught.exception.payload, "proxy error: \ufffd")

    async def test_login_rejection_keeps_code_and_payload(self):
        payload = {"success": False, "error": {"code": 403}}
        self.response.json.return_value = payload
        with self.assertRaises(SynologyAuthenticationError) as caught:
            await self.request("login")
        self.assertEqual(caught.exception.error_code, 403)
        self.assertIs(caught.exception.payload, payload)

    async def test_login_connection_failure_is_network_error(self):
        error = ClientConnectionError("unreachable")
        self.session.get.return_value.__aenter__.side_effect = error
        with self.assertRaises(SynologyNetworkError) as caught:
            await self.request("login")
        self.assertIs(caught.exception.original_error, error)

    async def test_login_missing_session_is_protocol_error(self):
        self.response.json.return_value = {"success": True, "data": {}}
        with self.assertRaises(SynologyProtocolError):
            await self.request("login")

    async def test_api_rejection_keeps_envelope(self):
        payload = {"success": False, "error": {"code": 1003}}
        self.response.json.return_value = payload
        for operation in ("request", "upload"):
            with self.assertRaises(SynologyApiError) as caught:
                await self.request(operation)
            self.assertEqual(caught.exception.error_code, 1003)
            self.assertIs(caught.exception.payload, payload)

    async def test_upload_source_failure_survives_connection_wrapper(self):
        error = FileNotFoundError("missing source")
        cause = OSError("source storage failed")

        async def chunks():
            yield b"first chunk"
            raise error from cause

        def post(*args, **kwargs):
            async def send():
                try:
                    async for _ in kwargs["data"]:
                        pass
                except Exception as exc:
                    raise ClientConnectionError("sending failed") from exc
                return self.response

            context = MagicMock()
            context.__aenter__ = AsyncMock(side_effect=send)
            return context

        self.session.post.side_effect = post
        with self.assertRaises(FileNotFoundError) as caught:
            await self.transport.upload(
                "api",
                1,
                "upload",
                form_fields={},
                file_name="missing",
                file_data=chunks(),
                mime_type="application/octet-stream",
            )
        self.assertIs(caught.exception, error)
        self.assertIs(caught.exception.__cause__, cause)

    async def test_client_preserves_synology_source_errors(self):
        client = SynologyClient(transport=self.transport)
        for error in (
            SynologyApiError("source missing", error_code=1003),
            SynologyNetworkError("source unavailable", OSError("connection reset")),
        ):
            with self.subTest(error=type(error).__name__):
                cause = RuntimeError("source failure")

                async def chunks():
                    yield b"first chunk"
                    raise error from cause

                def post(*args, **kwargs):
                    async def send():
                        try:
                            async for _ in kwargs["data"]:
                                pass
                        except Exception as exc:
                            raise ClientConnectionError("sending failed") from exc

                    context = MagicMock()
                    context.__aenter__ = AsyncMock(side_effect=send)
                    return context

                self.session.post.side_effect = post
                with self.assertRaises(type(error)) as caught:
                    await client.upload(SynologyPath("/target"), "file", chunks())
                self.assertIs(caught.exception, error)
                self.assertIs(caught.exception.__cause__, cause)
                self.assertIsNone(caught.exception.__context__)

    async def test_successful_reply_does_not_hide_source_failure(self):
        error = FileNotFoundError("missing source")

        async def chunks():
            yield b"first chunk"
            raise error

        def post(*args, **kwargs):
            async def send():
                try:
                    async for _ in kwargs["data"]:
                        pass
                except FileNotFoundError:
                    pass
                return self.response

            context = MagicMock()
            context.__aenter__ = AsyncMock(side_effect=send)
            return context

        self.response.json.return_value = {"success": True, "data": {}}
        self.session.post.side_effect = post
        with self.assertRaises(FileNotFoundError) as caught:
            await self.request_upload(chunks())
        self.assertIs(caught.exception, error)

    async def request_upload(self, chunks):
        return await self.transport.upload(
            "api",
            1,
            "upload",
            form_fields={},
            file_name="file",
            file_data=chunks,
            mime_type="application/octet-stream",
        )


class TestUploadIntegration(IsolatedAsyncioTestCase):
    async def make_client(self, handler):
        app = web.Application()
        app.router.add_post("/webapi/entry.cgi", handler)
        server = TestServer(app, host="127.0.0.1")
        await server.start_server()
        self.addAsyncCleanup(server.close)
        session = ClientSession(timeout=ClientTimeout(total=5))
        self.addAsyncCleanup(session.close)
        return SynologyClient(
            transport=SynologyTransport(
                session=session,
                base_url=str(server.make_url("")),
                sid="test",
            )
        )

    async def test_source_failure_preserves_identity_and_cause(self):
        received = asyncio.Event()

        async def handler(request):
            await request.content.readany()
            received.set()
            try:
                await request.read()
            except ConnectionResetError:
                pass
            return web.json_response({"success": True, "data": {}})

        client = await self.make_client(handler)
        error = SynologyApiError("source missing", error_code=1003)
        cause = OSError("source storage failed")

        async def chunks():
            yield b"data" * 16384
            await received.wait()
            raise error from cause

        with self.assertRaises(SynologyApiError) as caught:
            await asyncio.wait_for(
                client.upload(SynologyPath("/target"), "file", chunks()), 5
            )
        self.assertIs(caught.exception, error)
        self.assertIs(caught.exception.__cause__, cause)

    async def test_cancellation_closes_source(self):
        received = asyncio.Event()
        finish = asyncio.Event()
        closed = asyncio.Event()

        async def handler(request):
            received.set()
            await finish.wait()
            return web.json_response({"success": True, "data": {}})

        client = await self.make_client(handler)

        async def chunks():
            try:
                while True:
                    yield b"data" * 16384
            finally:
                closed.set()

        source = chunks()
        task = asyncio.create_task(
            client.upload(SynologyPath("/target"), "file", source)
        )
        try:
            await asyncio.wait_for(received.wait(), 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(closed.is_set())
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await source.aclose()
            finish.set()

    async def test_early_rejection_closes_source(self):
        started = asyncio.Event()
        closed = asyncio.Event()

        async def handler(request):
            await started.wait()
            return web.json_response({"success": False, "error": {"code": 1022}})

        client = await self.make_client(handler)

        async def chunks():
            try:
                started.set()
                yield b"data" * 16384
                # Keep a source read in flight when the server rejects it.
                await asyncio.Event().wait()
            finally:
                closed.set()

        source = chunks()
        try:
            with self.assertRaises(SynologyConflictError):
                await asyncio.wait_for(
                    client.upload(SynologyPath("/target"), "file", source), 5
                )
            self.assertTrue(closed.is_set())
        finally:
            await source.aclose()

    async def test_cancellation_during_blocked_source_read(self):
        reading = asyncio.Event()
        closed = asyncio.Event()
        finish = asyncio.Event()

        async def handler(request):
            await finish.wait()
            return web.json_response({"success": True, "data": {}})

        client = await self.make_client(handler)

        async def chunks():
            try:
                yield b"data" * 16384
                reading.set()
                await asyncio.Event().wait()
            finally:
                closed.set()

        source = chunks()
        task = asyncio.create_task(
            client.upload(SynologyPath("/target"), "file", source)
        )
        try:
            await asyncio.wait_for(reading.wait(), 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
            self.assertTrue(task.cancelled())
            self.assertTrue(closed.is_set())
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await source.aclose()
            finish.set()

    async def test_source_close_failure_preserves_cancellation(self):
        received = asyncio.Event()
        finish = asyncio.Event()
        closed = asyncio.Event()

        async def handler(request):
            received.set()
            await finish.wait()
            return web.json_response({"success": True, "data": {}})

        client = await self.make_client(handler)

        class Source:
            def __aiter__(self):
                return self

            async def __anext__(self):
                return b"data" * 16384

            async def aclose(self):
                closed.set()
                raise RuntimeError("source close failed")

        task = asyncio.create_task(
            client.upload(SynologyPath("/target"), "file", Source())
        )
        try:
            await asyncio.wait_for(received.wait(), 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError) as caught:
                await asyncio.wait_for(task, 5)
            self.assertTrue(task.cancelled())
            self.assertTrue(closed.is_set())
            self.assertTrue(
                any(
                    "source close failed" in note for note in caught.exception.__notes__
                )
            )
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            finish.set()


class TestEncodeRpcValue(IsolatedAsyncioTestCase):
    async def test_encode_string_as_json_string(self) -> None:
        self.assertEqual(encode_rpc_value("id:123"), '"id:123"')


class TestMultipartBody(IsolatedAsyncioTestCase):
    async def test_scalar_fields_have_no_content_type(self) -> None:
        async def chunks():
            yield b"hello"

        content_type, body = build_multipart_body(
            form_fields={
                "path": "id:parent/file.txt",
                "type": "file",
                "mute": True,
            },
            file_name="file.txt",
            file_data=chunks(),
            file_content_type="text/plain",
        )

        parts = [chunk async for chunk in body]
        data = b"".join(parts)

        self.assertIn(b"multipart/form-data; boundary=", content_type.encode())
        self.assertIn(b'name="path"', data)
        self.assertIn(b'name="file"; filename="file.txt"', data)
        self.assertIn(b"Content-Type: text/plain", data)
        self.assertNotIn(b'name="path"\r\nContent-Type:', data)
        self.assertNotIn(b'name="type"\r\nContent-Type:', data)


class TestDownload(IsolatedAsyncioTestCase):
    async def test_consumer_error_is_not_wrapped_as_network_error(self) -> None:
        response = MagicMock()
        response.wait_for_close = AsyncMock()
        session = MagicMock()
        session.get = AsyncMock(return_value=response)
        transport = SynologyTransport(
            session=session,
            base_url="https://nas.example",
            sid="sid",
        )
        error = RuntimeError("consumer failed")

        with self.assertRaises(RuntimeError) as caught:
            async with transport.download("api", 1, "download"):
                raise error

        self.assertIs(caught.exception, error)
        response.release.assert_called_once_with()
        response.wait_for_close.assert_awaited_once_with()
