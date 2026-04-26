from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from wcpan.synology._transport import (
    SynologyTransport,
    build_multipart_body,
    encode_rpc_value,
)


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
