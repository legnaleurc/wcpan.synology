from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientConnectionError

from wcpan.synology import (
    SynologyApiError,
    SynologyAuthenticationError,
    SynologyNetworkError,
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

        async def chunks():
            yield b"first chunk"
            raise error

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
