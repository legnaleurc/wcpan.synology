import logging
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientResponseError, RequestInfo, TooManyRedirects
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from wcpan.synology._diagnostics import RESPONSE_LOG_LIMIT, log_response
from wcpan.synology._transport import (
    SynologyTransport,
    network_error,
    read_rpc_response,
)
from wcpan.synology.exceptions import (
    SynologyApiError,
    SynologyNetworkError,
    SynologyProtocolError,
)


class TestResponseLogs(TestCase):
    def test_redaction_precedes_truncation(self):
        with self.assertLogs("wcpan.synology", level=logging.DEBUG) as logs:
            log_response(
                "api.get",
                {
                    "sid": "session-secret",
                    "access_token": "known-credential",
                    "padding": "x" * RESPONSE_LOG_LIMIT,
                    "password": "late-secret",
                },
            )
        message = logs.records[0].getMessage()
        self.assertNotIn("session-secret", message)
        self.assertNotIn("known-credential", message)
        self.assertNotIn("late-secret", message)
        self.assertIn("[REDACTED]", message)
        self.assertTrue(message.endswith(" [truncated]"))
        self.assertLessEqual(len(message), RESPONSE_LOG_LIMIT + 64)
        self.assertNotIn("known-credential", repr(logs.records[0].args))

    def test_response_formatting_uses_a_sanitized_snapshot(self):
        from wcpan.synology._diagnostics import ResponseDetails

        body = {"count": 1}
        details = ResponseDetails(body)
        body["sid"] = "later-secret"
        self.assertNotIn("later-secret", str(details))
        self.assertNotIn("later-secret", repr(details))
        masked = ResponseDetails({"sid": "session-secret"})
        self.assertNotIn("session-secret", repr(masked))
        self.assertIn("[REDACTED]", str(masked))

    def test_disabled_logging_does_not_render_body(self):
        body = MagicMock()
        body.__str__.side_effect = AssertionError("must not render")
        with self.assertNoLogs("wcpan.synology", level=logging.INFO):
            log_response("api.get", body)


class TestErrorBoundaries(IsolatedAsyncioTestCase):
    def response(self):
        response = MagicMock()
        response.status = 200
        response.json = AsyncMock()
        response.text = AsyncMock()
        return response

    def test_missing_http_status_is_none(self):
        url = URL("https://nas.example")
        info = RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)
        failure = network_error(TooManyRedirects(info, ()), "api.get")
        self.assertIsNone(failure.http_status)
        self.assertEqual(str(failure), "api.get failed: TooManyRedirects")

    async def test_api_error_keeps_only_parsed_error(self):
        response = self.response()
        response.json.return_value = {
            "success": False,
            "error": {"code": 1003, "message": "missing", "sid": "secret"},
            "data": {"unrelated": "private body"},
        }
        with self.assertRaises(SynologyApiError) as caught:
            await read_rpc_response(response, "api.get")
        error = caught.exception
        self.assertEqual(
            error.error, {"code": 1003, "message": "missing", "sid": "[REDACTED]"}
        )
        self.assertEqual(error.error_code, 1003)
        self.assertEqual(error.operation, "api.get")
        self.assertEqual(error.http_status, 200)
        self.assertNotIn("private body", repr(vars(error)))
        self.assertIsNone(error.__context__)
        self.assertFalse(hasattr(error, "payload"))

    async def test_invalid_json_body_is_debug_only(self):
        response = self.response()
        # JSONDecodeError retains the input in .doc; it must not be chained.
        from json import JSONDecodeError

        response.json.side_effect = JSONDecodeError("invalid", "private body", 0)
        response.text.return_value = "private body password=secret"
        with self.assertNoLogs("wcpan.synology", level=logging.INFO):
            with self.assertRaises(SynologyProtocolError) as caught:
                await read_rpc_response(response, "api.get")
        response.text.assert_not_awaited()
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.error)
        self.assertNotIn("private body", repr(vars(caught.exception)))
        with self.assertLogs("wcpan.synology", level=logging.DEBUG) as logs:
            with self.assertRaises(SynologyProtocolError):
                await read_rpc_response(response, "api.get")
        self.assertNotIn("private body", logs.output[0])
        self.assertIn("body omitted", logs.output[0])
        response.text.assert_not_awaited()
        self.assertNotIn("secret", logs.output[0])

    async def test_http_failure_retains_status_and_parsed_error(self):
        response = self.response()
        response.status = 403
        url = URL("https://nas.example/webapi/entry.cgi?_sid=session-secret")
        info = RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)
        response.raise_for_status.side_effect = ClientResponseError(
            info, (), status=403, message="Forbidden"
        )
        response.json.return_value = {
            "error": {"code": 105, "sid": "session-secret"},
            "data": "private body",
        }
        session = MagicMock()
        session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        transport = SynologyTransport(
            session=session, base_url="https://nas.example", sid="session-secret"
        )
        with self.assertRaises(SynologyNetworkError) as caught:
            await transport.request("api", 1, "get")
        error = caught.exception
        self.assertEqual(str(error), "api.get failed: HTTP 403")
        self.assertEqual(error.http_status, 403)
        self.assertEqual(error.operation, "api.get")
        self.assertEqual(error.error, {"code": 105, "sid": "[REDACTED]"})
        self.assertNotIn("private body", repr(vars(error)))
        self.assertNotIn("session-secret", str(error.original_error))

    async def test_http_failure_survives_unreadable_body(self):
        from aiohttp import ClientPayloadError

        response = self.response()
        response.status = 502
        url = URL("https://nas.example/webapi/entry.cgi")
        info = RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)
        raw = ClientResponseError(info, (), status=502, message="Bad Gateway")
        response.raise_for_status.side_effect = raw
        response.json.side_effect = ClientPayloadError("broken body")
        response.text.side_effect = ClientPayloadError("broken body")
        with self.assertLogs("wcpan.synology", level=logging.DEBUG):
            with self.assertRaises(SynologyNetworkError) as caught:
                await read_rpc_response(response, "api.get")
        self.assertEqual(caught.exception.http_status, 502)
        self.assertIsNot(caught.exception.original_error, raw)
        self.assertEqual(
            caught.exception.original_error.error_type, "ClientResponseError"
        )
        self.assertIsNone(caught.exception.error)

    async def test_real_http_error_body_is_read_before_release(self):
        from aiohttp import ClientSession, web
        from aiohttp.test_utils import TestServer

        async def handler(request):
            return web.json_response(
                {
                    "error": {"code": 105, "sid": request.query["_sid"]},
                    "data": "private body",
                },
                status=403,
            )

        app = web.Application()
        app.router.add_get("/webapi/entry.cgi", handler)
        async with TestServer(app, host="127.0.0.1") as server:
            async with ClientSession() as session:
                transport = SynologyTransport(
                    session=session,
                    base_url=str(server.make_url("")),
                    sid="session-secret",
                )
                # Both ordinary RPC and download setup must preserve the error.
                for operation in ("request", "download"):
                    with self.subTest(operation=operation):
                        with self.assertRaises(SynologyNetworkError) as caught:
                            if operation == "request":
                                await transport.request("api", 1, "get")
                            else:
                                async with transport.download("api", 1, "get"):
                                    self.fail("an HTTP failure cannot yield a stream")
                        self.assertEqual(caught.exception.http_status, 403)
                        self.assertEqual(
                            caught.exception.error, {"code": 105, "sid": "[REDACTED]"}
                        )

    async def test_files_mapping_preserves_operation_and_status(self):
        from wcpan.synology._errors import file_error, upload_error

        raw = SynologyApiError(
            "failed",
            error_code=1003,
            error={"code": 1003},
            operation="api.get",
            http_status=200,
        )
        for error in (file_error(raw), upload_error(raw, "file")):
            self.assertEqual(error.operation, "api.get")
            self.assertEqual(error.http_status, 200)
            self.assertEqual(error.error, {"code": 1003})
