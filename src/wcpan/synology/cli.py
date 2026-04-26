from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from .client import create_client


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "help":
        print_help_topic(args)
        return
    asyncio.run(run_client_command(args))


def build_parser() -> argparse.ArgumentParser:
    auth_parent = build_auth_parent_parser()
    parser = argparse.ArgumentParser(
        prog="wcpan-synology",
        description="Synology WebStation API client and inspector.",
        parents=[auth_parent],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_generic_call_parser(subparsers, auth_parent=auth_parent)
    add_namespaced_parsers(subparsers, auth_parent=auth_parent)

    help_parser = subparsers.add_parser(
        "help",
        help="Show local API help topics",
        description="Show local help text for namespaces and methods.",
    )
    help_parser.add_argument("topic", nargs="*", help='Examples: "files", "files get"')

    return parser


def build_auth_parent_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--base-url",
        help="DSM base URL such as https://nas.example:5001",
    )
    parser.add_argument("--username", help="DSM username")
    parser.add_argument("--password", help="DSM password")
    parser.add_argument("--otp-code", help="Optional 2FA code")
    return parser


def add_generic_call_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    auth_parent: argparse.ArgumentParser,
) -> None:
    call_parser = subparsers.add_parser(
        "call",
        help="Make a generic RPC call",
        description="Make a raw query-string RPC call with JSON-decoded parameters.",
        parents=[auth_parent],
    )
    call_parser.add_argument("--api", required=True)
    call_parser.add_argument("--version", required=True, type=int)
    call_parser.add_argument("--method", required=True)
    call_parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help='Parameter value must be valid JSON, e.g. path="\\"id:123\\""',
    )


def add_namespaced_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    auth_parent: argparse.ArgumentParser,
) -> None:
    for namespace, namespace_spec in API_CATALOG.items():
        namespace_parser = subparsers.add_parser(
            namespace,
            help=namespace_spec["help"],
            description=namespace_spec["help"],
            parents=[auth_parent],
        )
        method_subparsers = namespace_parser.add_subparsers(
            dest="api_method",
            required=True,
        )
        for method, method_spec in namespace_spec["methods"].items():
            method_parser = method_subparsers.add_parser(
                method,
                help=method_spec["summary"],
                description=build_method_description(namespace, method, method_spec),
                formatter_class=argparse.RawDescriptionHelpFormatter,
                parents=[auth_parent],
            )
            for arg_spec in method_spec["args"]:
                method_parser.add_argument(*arg_spec["flags"], **arg_spec["kwargs"])


def build_method_description(
    namespace: str,
    method: str,
    method_spec: dict[str, Any],
) -> str:
    api = API_CATALOG[namespace]["api"]
    version = API_CATALOG[namespace]["version"]
    example = method_spec["example"]
    return (
        f"{method_spec['summary']}\n\n"
        f"API: {api}\n"
        f"Version: {version}\n"
        f"Method: {method}\n\n"
        f"Example:\n  {example}"
    )


def print_help_topic(args: argparse.Namespace) -> None:
    tokens = args.topic
    if not tokens:
        print("Namespaces:")
        for namespace, spec in API_CATALOG.items():
            print(f"  {namespace}: {spec['help']}")
        print('\nUse "wcpan-synology help <namespace> [method]" for more detail.')
        return

    namespace = tokens[0]
    if namespace not in API_CATALOG:
        raise SystemExit(f"unknown help topic: {namespace}")
    spec = API_CATALOG[namespace]
    if len(tokens) == 1:
        print(f"{namespace}: {spec['help']}")
        print(f"API: {spec['api']}")
        print(f"Version: {spec['version']}")
        print("Methods:")
        for method, method_spec in spec["methods"].items():
            print(f"  {method}: {method_spec['summary']}")
        return

    method = tokens[1]
    method_spec = spec["methods"].get(method)
    if not method_spec:
        raise SystemExit(f"unknown method for {namespace}: {method}")
    print(build_method_description(namespace, method, method_spec))


async def run_client_command(args: argparse.Namespace) -> None:
    if args.command == "help":
        raise SystemExit(f"unsupported async command: {args.command}")

    required = ("base_url", "username", "password")
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        raise SystemExit(f"missing required auth options: {', '.join(missing)}")

    async with create_client(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        otp_code=args.otp_code,
    ) as client:
        payload = await dispatch_command(client, args)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


async def dispatch_command(client: Any, args: argparse.Namespace) -> Any:
    if args.command == "call":
        return await client.call(
            api=args.api,
            version=args.version,
            method=args.method,
            **parse_params(args.param),
        )
    if args.command in API_CATALOG:
        return await run_api_command(client, args)
    raise SystemExit(f"unsupported command: {args.command}")


async def run_api_command(client: Any, args: argparse.Namespace) -> Any:
    namespace_spec = API_CATALOG[args.command]
    method_spec = namespace_spec["methods"][args.api_method]
    if method_spec.get("upload"):
        return await upload_file_command(client, args)
    params = method_spec["params"](args)
    return await client.call(
        api=namespace_spec["api"],
        version=namespace_spec["version"],
        method=args.api_method,
        **params,
    )


async def upload_file_command(client: Any, args: argparse.Namespace) -> Any:
    file_path = Path(args.file)
    name = args.name or file_path.name

    async def chunks() -> Any:
        with file_path.open("rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                yield chunk

    return await client.upload(
        args.parent_path,
        name,
        chunks(),
        mime_type=args.mime_type,
    )


def parse_params(raw_params: list[str]) -> dict[str, Any]:
    parsed = {}
    for raw_param in raw_params:
        if "=" not in raw_param:
            raise SystemExit(f"invalid --param value: {raw_param!r}")
        key, raw_value = raw_param.split("=", 1)
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid JSON for --param {key!r}: {exc}") from exc
        parsed[key.replace("-", "_")] = value
    return parsed


def parse_json_value(raw_value: str) -> Any:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON value: {raw_value!r}: {exc}") from exc


def generic_param_argument() -> dict[str, Any]:
    return {
        "flags": ["--param"],
        "kwargs": {
            "action": "append",
            "default": [],
            "metavar": "KEY=JSON",
            "help": "Extra JSON-decoded RPC parameter.",
        },
    }


def merge_params_with_required(*field_names: str):
    def fn(args: argparse.Namespace) -> dict[str, Any]:
        params = parse_params(args.param)
        for field_name in field_names:
            value = getattr(args, field_name, None)
            if value is not None:
                params[field_name] = value
        return params

    return fn


def create_files_create_params(args: argparse.Namespace) -> dict[str, Any]:
    params = parse_params(args.param)
    params["type"] = args.type
    params["path"] = args.path
    params["conflict_action"] = args.conflict_action
    if args.file_content is not None:
        params["file_content"] = args.file_content
    return params


def create_files_move_params(args: argparse.Namespace) -> dict[str, Any]:
    params = parse_params(args.param)
    params["files"] = parse_json_value(args.files)
    params["to_parent_folder"] = args.to_parent_folder
    params["conflict_action"] = args.conflict_action
    return params


def create_files_delete_params(args: argparse.Namespace) -> dict[str, Any]:
    params = parse_params(args.param)
    params["files"] = parse_json_value(args.files)
    return params


def create_files_download_params(args: argparse.Namespace) -> dict[str, Any]:
    params = parse_params(args.param)
    params["files"] = parse_json_value(args.files)
    params["force_download"] = args.force_download
    return params


API_CATALOG = {
    "files": {
        "api": "SYNO.SynologyDrive.Files",
        "version": 11,
        "help": "File and folder APIs under SYNO.SynologyDrive.Files",
        "methods": {
            "get": {
                "summary": "Get one file or folder by id or path",
                "args": [
                    {
                        "flags": ["--path"],
                        "kwargs": {
                            "required": True,
                            "help": (
                                'Accepted forms include "id:<file-id>" '
                                "and full Drive paths."
                            ),
                        },
                    },
                ],
                "params": lambda args: {"path": args.path},
                "example": 'wcpan-synology files get --path "id:123"',
            },
            "list": {
                "summary": "List children in a folder",
                "args": [
                    {
                        "flags": ["--path"],
                        "kwargs": {
                            "required": True,
                            "help": 'Folder id or path, e.g. "id:123".',
                        },
                    },
                    {
                        "flags": ["--offset"],
                        "kwargs": {
                            "type": int,
                            "default": 0,
                            "help": "Pagination offset.",
                        },
                    },
                    {
                        "flags": ["--limit"],
                        "kwargs": {"type": int, "default": 1000, "help": "Page size."},
                    },
                    {
                        "flags": ["--sort-by"],
                        "kwargs": {
                            "default": "name",
                            "help": "Sort field. Default: name.",
                        },
                    },
                    {
                        "flags": ["--sort-direction"],
                        "kwargs": {
                            "default": "asc",
                            "choices": ("asc", "desc"),
                            "help": "Sort direction.",
                        },
                    },
                ],
                "params": lambda args: {
                    "path": args.path,
                    "offset": args.offset,
                    "limit": args.limit,
                    "sort_by": args.sort_by,
                    "sort_direction": args.sort_direction,
                },
                "example": 'wcpan-synology files list --path "id:123" --limit 100',
            },
            "search": {
                "summary": "Search files",
                "args": [generic_param_argument()],
                "params": lambda args: parse_params(args.param),
                "example": (
                    "wcpan-synology files search "
                    "--param keyword='\"report\"' --param path='\"id:123\"'"
                ),
            },
            "create": {
                "summary": "Create a folder or small file",
                "args": [
                    {
                        "flags": ["--type"],
                        "kwargs": {
                            "required": True,
                            "choices": ("folder", "file"),
                            "help": "Create a folder or a small inline file.",
                        },
                    },
                    {
                        "flags": ["--path"],
                        "kwargs": {
                            "required": True,
                            "help": 'Destination like "id:<parent-id>/new-folder".',
                        },
                    },
                    {
                        "flags": ["--conflict-action"],
                        "kwargs": {"default": "stop", "help": "Conflict behavior."},
                    },
                    {
                        "flags": ["--file-content"],
                        "kwargs": {
                            "help": "Optional inline file payload. Keep this small.",
                        },
                    },
                    generic_param_argument(),
                ],
                "params": create_files_create_params,
                "example": (
                    "wcpan-synology files create --type folder "
                    '--path "id:123/new-folder"'
                ),
            },
            "update": {
                "summary": "Rename or update file metadata",
                "args": [
                    {
                        "flags": ["--path"],
                        "kwargs": {
                            "required": True,
                            "help": "File id or path to update.",
                        },
                    },
                    {
                        "flags": ["--name"],
                        "kwargs": {"help": "New name."},
                    },
                    generic_param_argument(),
                ],
                "params": merge_params_with_required("path", "name"),
                "example": (
                    'wcpan-synology files update --path "id:123" --name "renamed.txt"'
                ),
            },
            "move": {
                "summary": (
                    "Move files or folders and wait on the async "
                    "task yourself if needed"
                ),
                "args": [
                    {
                        "flags": ["--files"],
                        "kwargs": {
                            "required": True,
                            "help": 'JSON array string like ["id:1","id:2"].',
                        },
                    },
                    {
                        "flags": ["--to-parent-folder"],
                        "kwargs": {
                            "required": True,
                            "help": 'Destination folder ref like "id:parent".',
                        },
                    },
                    {
                        "flags": ["--conflict-action"],
                        "kwargs": {"default": "stop", "help": "Conflict behavior."},
                    },
                    generic_param_argument(),
                ],
                "params": create_files_move_params,
                "example": (
                    "wcpan-synology files move --files '[\"id:1\"]' "
                    '--to-parent-folder "id:parent"'
                ),
            },
            "delete": {
                "summary": "Delete files or folders",
                "args": [
                    {
                        "flags": ["--files"],
                        "kwargs": {
                            "required": True,
                            "help": 'JSON array string like ["id:1"].',
                        },
                    },
                    generic_param_argument(),
                ],
                "params": create_files_delete_params,
                "example": "wcpan-synology files delete --files '[\"id:1\"]'",
            },
            "download": {
                "summary": "Download files via generic RPC and print response metadata",
                "args": [
                    {
                        "flags": ["--files"],
                        "kwargs": {
                            "required": True,
                            "help": 'JSON array string like ["id:1"].',
                        },
                    },
                    {
                        "flags": ["--force-download"],
                        "kwargs": {
                            "action": "store_true",
                            "help": "Set force_download=true.",
                        },
                    },
                    generic_param_argument(),
                ],
                "params": create_files_download_params,
                "example": "wcpan-synology files download --files '[\"id:1\"]'",
            },
            "upload": {
                "summary": "Upload one file with multipart transport",
                "upload": True,
                "args": [
                    {
                        "flags": ["--parent-path"],
                        "kwargs": {
                            "required": True,
                            "help": 'Destination folder ref like "id:parent".',
                        },
                    },
                    {
                        "flags": ["--name"],
                        "kwargs": {"help": "Optional destination file name."},
                    },
                    {
                        "flags": ["--mime-type"],
                        "kwargs": {"help": "Optional file MIME type."},
                    },
                    {
                        "flags": ["file"],
                        "kwargs": {"help": "Local file to upload."},
                    },
                ],
                "params": None,
                "example": (
                    'wcpan-synology files upload --parent-path "id:123" ./local.bin'
                ),
            },
        },
    },
    "tasks": {
        "api": "SYNO.SynologyDrive.Tasks",
        "version": 1,
        "help": "Async task APIs under SYNO.SynologyDrive.Tasks",
        "methods": {
            "list": {
                "summary": "List Synology Drive tasks",
                "args": [generic_param_argument()],
                "params": lambda args: parse_params(args.param),
                "example": "wcpan-synology tasks list",
            },
            "get": {
                "summary": "Get one Synology Drive task",
                "args": [
                    {
                        "flags": ["--task-id"],
                        "kwargs": {
                            "required": True,
                            "help": "Task id from an async response.",
                        },
                    },
                    generic_param_argument(),
                ],
                "params": merge_params_with_required("task_id"),
                "example": 'wcpan-synology tasks get --task-id "123"',
            },
        },
    },
    "webhooks": {
        "api": "SYNO.SynologyDrive.Webhooks",
        "version": 2,
        "help": "Webhook APIs under SYNO.SynologyDrive.Webhooks",
        "methods": {
            "create": {
                "summary": "Create a webhook",
                "args": [
                    {
                        "flags": ["--app-id"],
                        "kwargs": {"required": True, "help": "Webhook application id."},
                    },
                    {
                        "flags": ["--url"],
                        "kwargs": {"required": True, "help": "Callback URL."},
                    },
                    {
                        "flags": ["--type"],
                        "kwargs": {"default": "url", "help": "Webhook type."},
                    },
                    generic_param_argument(),
                ],
                "params": merge_params_with_required("app_id", "url", "type"),
                "example": (
                    'wcpan-synology webhooks create --app-id "my-app" '
                    '--url "https://example.test/hook"'
                ),
            },
            "get": {
                "summary": "Get one webhook",
                "args": [
                    {
                        "flags": ["--app-id"],
                        "kwargs": {"required": True, "help": "Webhook application id."},
                    },
                    {
                        "flags": ["--webhook-id"],
                        "kwargs": {"required": True, "help": "Webhook id."},
                    },
                    generic_param_argument(),
                ],
                "params": merge_params_with_required("app_id", "webhook_id"),
                "example": (
                    'wcpan-synology webhooks get --app-id "my-app" --webhook-id "123"'
                ),
            },
            "update": {
                "summary": "Update a webhook",
                "args": [
                    {
                        "flags": ["--app-id"],
                        "kwargs": {"required": True, "help": "Webhook application id."},
                    },
                    {
                        "flags": ["--webhook-id"],
                        "kwargs": {"required": True, "help": "Webhook id."},
                    },
                    {
                        "flags": ["--url"],
                        "kwargs": {"help": "New callback URL."},
                    },
                    {
                        "flags": ["--type"],
                        "kwargs": {"default": "url", "help": "Webhook type."},
                    },
                    generic_param_argument(),
                ],
                "params": merge_params_with_required(
                    "app_id",
                    "webhook_id",
                    "type",
                    "url",
                ),
                "example": (
                    'wcpan-synology webhooks update --app-id "my-app" '
                    '--webhook-id "123" --url "https://example.test/new-hook"'
                ),
            },
            "delete": {
                "summary": "Delete a webhook",
                "args": [
                    {
                        "flags": ["--app-id"],
                        "kwargs": {"required": True, "help": "Webhook application id."},
                    },
                    {
                        "flags": ["--webhook-id"],
                        "kwargs": {"required": True, "help": "Webhook id."},
                    },
                    generic_param_argument(),
                ],
                "params": merge_params_with_required("app_id", "webhook_id"),
                "example": (
                    "wcpan-synology webhooks delete --app-id "
                    '"my-app" --webhook-id "123"'
                ),
            },
            "list": {
                "summary": "List webhooks for an app id",
                "args": [
                    {
                        "flags": ["--app-id"],
                        "kwargs": {"required": True, "help": "Webhook application id."},
                    },
                    generic_param_argument(),
                ],
                "params": merge_params_with_required("app_id"),
                "example": 'wcpan-synology webhooks list --app-id "my-app"',
            },
        },
    },
}
