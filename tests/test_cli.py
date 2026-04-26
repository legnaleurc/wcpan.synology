from argparse import Namespace
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from wcpan.synology.cli import (
    build_parser,
    parse_params,
    print_help_topic,
)


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
