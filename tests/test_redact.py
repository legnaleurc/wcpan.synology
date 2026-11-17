import traceback
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import quote_plus

from aiohttp import ClientResponseError, RequestInfo
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from wcpan.synology._redact import redact
from wcpan.synology._secret import Secret
from wcpan.synology._transport import SynologyTransport, login
from wcpan.synology.exceptions import SynologyApiError, SynologyNetworkError


class TestSecret(TestCase):
    def test_all_formatting_paths_hide_value(self):
        secret = Secret("credential/value +?")
        for rendered in (
            str(secret),
            repr(secret),
            f"{secret}",
            f"{secret!s}",
            f"{secret!r}",
            f"{secret!a}",
            f"{secret:>20}",
            str({"token": secret}),
        ):
            with self.subTest(rendered=rendered):
                self.assertNotIn(secret.reveal(), rendered)
                self.assertIn("[REDACTED]", rendered)
        self.assertEqual(secret.reveal(), "credential/value +?")
        self.assertNotIsInstance(secret, str)

    def test_logging_and_json_do_not_implicitly_reveal(self):
        import json
        import logging

        secret = Secret("credential-value")
        with self.assertLogs("wcpan.synology", level="DEBUG") as logs:
            logging.getLogger("wcpan.synology").debug(
                "token=%s token=%r", secret, secret
            )
        self.assertNotIn("credential-value", logs.output[0])
        with self.assertRaises(TypeError):
            json.dumps({"sid": secret})

    def test_structured_credentials_are_copied(self):
        payload = {"error": {"_sid": "secret", "PASSWORD": "secret", "code": 403}}
        error = SynologyApiError("API failed", error=payload["error"])
        self.assertNotIn("secret", repr(error.error))
        self.assertEqual(payload["error"]["_sid"], "secret")
        self.assertEqual(error.error["code"], 403)
        self.assertEqual(
            redact({"nested": [{"Set-Cookie": "secret"}]}),
            {"nested": [{"Set-Cookie": "[REDACTED]"}]},
        )


class TestTransportRedaction(IsolatedAsyncioTestCase):
    async def test_http_errors_and_chains_are_censored(self):
        for operation in ("login", "request", "upload", "download"):
            with self.subTest(operation=operation):
                secret = "credential/value +?"
                url = URL("https://nas.example/webapi/entry.cgi").with_query(
                    _sid=secret, passwd=secret, otp_code=secret
                )
                headers = CIMultiDictProxy(
                    CIMultiDict(Authorization=f"Bearer {secret}")
                )
                info = RequestInfo(url, "GET", headers, url)
                raw = ClientResponseError(
                    info, (), status=403, message=f"Forbidden {secret}", headers=headers
                )
                response = MagicMock()
                response.status = 403
                response.wait_for_close = AsyncMock()
                response.json = AsyncMock(return_value={})
                response.raise_for_status.side_effect = raw
                session = MagicMock()
                session.get.return_value.__aenter__ = AsyncMock(return_value=response)
                session.post.return_value.__aenter__ = AsyncMock(return_value=response)
                transport = SynologyTransport(
                    session=session, base_url="https://nas.example", sid=secret
                )
                with self.assertRaises(SynologyNetworkError) as caught:
                    if operation == "login":
                        await login(
                            session,
                            base_url="https://nas.example",
                            username="user",
                            password=secret,
                        )
                    elif operation == "request":
                        await transport.request("api", 1, "get")
                    elif operation == "upload":

                        async def chunks():
                            yield b"data"

                        await transport.upload(
                            "api",
                            1,
                            "upload",
                            form_fields={},
                            file_name="file",
                            file_data=chunks(),
                            mime_type="text/plain",
                        )
                    else:
                        session.get = AsyncMock(return_value=response)
                        async with transport.download("api", 1, "download"):
                            pass
                error = caught.exception
                self.assertIsNot(error.original_error, raw)
                self.assertIs(error.__cause__, error.original_error)
                self.assertIsNone(error.__context__)
                self.assertIsNone(error.original_error.__context__)
                diagnostics = str(error) + repr(error.original_error)
                diagnostics += "".join(traceback.format_exception(error))
                self.assertNotIn(secret, diagnostics)
                self.assertNotIn(quote_plus(secret), diagnostics)
                # The original library exception is untouched, not retained.
                self.assertIn(secret, str(raw))
                self.assertIn("403", str(error))
                self.assertIsInstance(error.operation, str)
                self.assertEqual(error.http_status, 403)

    async def test_credentials_are_revealed_only_for_request_parameters(self):
        response = MagicMock()
        response.status = 200
        response.json = AsyncMock(
            return_value={"success": True, "data": {"sid": "session-secret"}}
        )
        session = MagicMock()
        session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        sid = await login(
            session,
            base_url="https://nas.example",
            username="user",
            password=Secret("password-secret"),
            otp_code=Secret("otp-secret"),
        )
        self.assertIsInstance(sid, Secret)
        self.assertEqual(sid.reveal(), "session-secret")
        query = session.get.call_args.kwargs["params"]
        self.assertEqual(query["passwd"], "password-secret")
        self.assertEqual(query["otp_code"], "otp-secret")
        transport = SynologyTransport(
            session=session, base_url="https://nas.example", sid=sid
        )
        await transport.request("api", 1, "get")
        self.assertEqual(
            session.get.call_args.kwargs["params"]["_sid"], "session-secret"
        )
        self.assertNotIn("session-secret", repr(vars(transport)))

    async def test_protocol_payload_echo_is_censored(self):
        response = MagicMock()
        response.status = 200
        response.json = AsyncMock(
            return_value={
                "success": False,
                "error": {"code": 403},
                "echo": "session-secret",
            }
        )
        session = MagicMock()
        session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        transport = SynologyTransport(
            session=session, base_url="https://nas.example", sid="session-secret"
        )
        with self.assertRaises(SynologyApiError) as caught:
            await transport.request("api", 1, "get")
        self.assertNotIn("session-secret", repr(caught.exception.error))


class TestCliRedaction(IsolatedAsyncioTestCase):
    async def test_cli_censors_response_credentials_and_cookies(self):
        from contextlib import asynccontextmanager
        from io import StringIO
        from unittest.mock import patch

        from wcpan.synology._cli import build_parser, run_client_command

        @asynccontextmanager
        async def client(**kwargs):
            instance = MagicMock()
            instance.call = AsyncMock(
                return_value={
                    "sid": "session-secret",
                    "password": "password-secret",
                    "headers": {"Set-Cookie": "session=cookie-secret"},
                    "count": 3,
                }
            )
            yield instance

        args = build_parser().parse_args(
            [
                "--base-url",
                "https://nas.example",
                "--username",
                "user",
                "--password",
                "password-secret",
                "call",
                "--api",
                "test",
                "--version",
                "1",
                "--method",
                "get",
            ]
        )
        with (
            patch("wcpan.synology._cli.create_client", client),
            patch("sys.stdout", new_callable=StringIO) as output,
        ):
            await run_client_command(args)
        self.assertNotIn("secret", output.getvalue())
        self.assertIn('"count": 3', output.getvalue())

    def test_parser_error_censors_secret_options(self):
        from io import StringIO
        from unittest.mock import patch

        from wcpan.synology._cli import build_parser, parse_json_value, parse_params

        with patch("sys.stderr", new_callable=StringIO) as output:
            with self.assertRaises(SystemExit):
                build_parser().error("invalid --password secret --otp-code=123456")
        self.assertNotIn("secret", output.getvalue())
        self.assertNotIn("123456", output.getvalue())
        for parse, value in ((parse_params, ["secret"]), (parse_json_value, "secret")):
            with self.assertRaises(SystemExit) as caught:
                parse(value)
            self.assertNotIn("secret", str(caught.exception))
