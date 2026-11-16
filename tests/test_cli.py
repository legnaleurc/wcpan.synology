from argparse import Namespace
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from wcpan.synology.cli import (
    apply_env_fallbacks,
    build_parser,
    parse_params,
    print_help_topic,
)


class TestEnvFallbacks(TestCase):
    def test_missing_options_use_environment(self) -> None:
        args = build_parser().parse_args(["tasks", "list"])
        apply_env_fallbacks(
            args,
            environ={
                "WCPAN_SYNOLOGY_BASE_URL": "https://nas.example:5001",
                "WCPAN_SYNOLOGY_USERNAME": "user",
                "WCPAN_SYNOLOGY_PASSWORD": "secret",
                "WCPAN_SYNOLOGY_OTP_CODE": "123456",
            },
        )
        self.assertEqual("https://nas.example:5001", args.base_url)
        self.assertEqual("user", args.username)
        self.assertEqual("secret", args.password)
        self.assertEqual("123456", args.otp_code)

    def test_explicit_options_win_at_each_level(self) -> None:
        for command in (
            ["--username=explicit", "tasks", "list"],
            ["tasks", "--username=explicit", "list"],
            ["tasks", "list", "--username=explicit"],
            ["tasks", "list", "--username="],
        ):
            with self.subTest(command=command):
                args = build_parser().parse_args(command)
                expected = args.username
                apply_env_fallbacks(
                    args, environ={"WCPAN_SYNOLOGY_USERNAME": "fallback"}
                )
                self.assertEqual(expected, args.username)

    def test_unset_environment_leaves_options_missing(self) -> None:
        args = build_parser().parse_args(["tasks", "list"])
        apply_env_fallbacks(args, environ={})
        self.assertIsNone(args.base_url)
        self.assertIsNone(args.username)
        self.assertIsNone(args.password)
        self.assertIsNone(args.otp_code)

    def test_defaults_to_process_environment(self) -> None:
        args = Namespace()
        with patch.dict("os.environ", {"WCPAN_SYNOLOGY_USERNAME": "user"}, clear=True):
            apply_env_fallbacks(args)
        self.assertEqual("user", args.username)


class TestParseParams(TestCase):
    def test_parse_json_values(self) -> None:
        rv = parse_params(
            [
                'path="id:123"',
                'files=["id:1","id:2"]',
                "limit=100",
            ]
        )

        self.assertEqual("id:123", rv["path"])
        self.assertEqual(["id:1", "id:2"], rv["files"])
        self.assertEqual(100, rv["limit"])

    def test_reject_invalid_json(self) -> None:
        with self.assertRaises(SystemExit):
            parse_params(["path=id:123"])

    def test_normalize_dashed_keys(self) -> None:
        rv = parse_params(['conflict-action="stop"'])
        self.assertEqual("stop", rv["conflict_action"])


class TestHelpSurface(TestCase):
    def test_auth_options_preserved_at_each_command_level(self) -> None:
        auth = [
            "--base-url=https://nas.example:5001",
            "--username=user",
            "--password=secret",
            "--otp-code=123456",
        ]
        commands = [
            ["webhooks", "list", "--app-id=123"],
            ["call", "--api=example", "--version=1", "--method=list"],
        ]
        for command in commands:
            for position in range(len(command)):
                with self.subTest(command=command, position=position):
                    args = build_parser().parse_args(
                        command[:position] + auth + command[position:]
                    )
                    self.assertEqual("https://nas.example:5001", args.base_url)
                    self.assertEqual("user", args.username)
                    self.assertEqual("secret", args.password)
                    self.assertEqual("123456", args.otp_code)

    def test_parse_namespaced_command(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["files", "get", "--path", "id:123"])

        self.assertEqual("files", args.command)
        self.assertEqual("get", args.api_method)
        self.assertEqual("id:123", args.path)

    def test_parse_global_options_after_subcommands(self) -> None:
        parser = build_parser()

        args = parser.parse_args(
            [
                "files",
                "get",
                "--base-url",
                "https://nas.example:5001",
                "--username",
                "user",
                "--password",
                "secret",
                "--path",
                "id:123",
            ]
        )

        self.assertEqual("https://nas.example:5001", args.base_url)
        self.assertEqual("user", args.username)
        self.assertEqual("secret", args.password)
        self.assertEqual("id:123", args.path)

    def test_method_help_includes_global_options(self) -> None:
        parser = build_parser()
        output = StringIO()

        with patch("sys.stdout", output):
            with self.assertRaises(SystemExit):
                parser.parse_args(["files", "get", "--help"])

        self.assertIn("--base-url", output.getvalue())
        self.assertIn("--username", output.getvalue())
        self.assertIn("--password", output.getvalue())

    def test_print_namespace_help(self) -> None:
        output = StringIO()

        with patch("sys.stdout", output):
            print_help_topic(Namespace(topic=["files"]))

        self.assertIn("SYNO.SynologyDrive.Files", output.getvalue())
        self.assertIn("Methods:", output.getvalue())

    def test_print_method_help(self) -> None:
        output = StringIO()

        with patch("sys.stdout", output):
            print_help_topic(Namespace(topic=["webhooks", "create"]))

        self.assertIn("Create a webhook", output.getvalue())
        self.assertIn("Example:", output.getvalue())


class TestWebhookAppId(TestCase):
    def test_integer_string_app_id_for_each_method(self) -> None:
        for method in ("create", "get", "update", "delete", "list"):
            with self.subTest(method=method):
                command = ["webhooks", method, "--app-id", "123"]
                if method in ("get", "update", "delete"):
                    command += ["--webhook-id", "456"]
                if method == "create":
                    command += ["--url", "https://example.test/hook"]
                args = build_parser().parse_args(command)
                self.assertIs(type(args.app_id), str)
                self.assertEqual("123", args.app_id)
                with patch("sys.stderr", StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        build_parser().parse_args(command + ["--app-id", "my-app"])
                self.assertEqual(2, caught.exception.code)

    def test_integer_string_webhook_id_for_each_method(self) -> None:
        for method in ("get", "update", "delete"):
            with self.subTest(method=method):
                command = ["webhooks", method, "--app-id", "0", "--webhook-id"]
                args = build_parser().parse_args(command + ["123"])
                self.assertIs(type(args.webhook_id), str)
                self.assertEqual("123", args.webhook_id)
                with patch("sys.stderr", StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        build_parser().parse_args(command + ["hook-id"])
                self.assertEqual(2, caught.exception.code)
