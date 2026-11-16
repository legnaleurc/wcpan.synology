# wcpan.synology

Async client library and CLI for the Synology Drive APIs exposed through DSM
WebStation.

The documentation in [`docs/synology-webstation-api.md`](docs/synology-webstation-api.md)
covers the broader Synology Drive API family. The current library and CLI
surface in this repository focus on:

- `SYNO.SynologyDrive.Files`
- `SYNO.SynologyDrive.Tasks`
- `SYNO.SynologyDrive.Webhooks`

## Installation

```bash
uv add wcpan-synology
```

The package requires Python 3.12 or newer.

## Usage

Namespaced API help:

```bash
uv run wcpan-synology help
uv run wcpan-synology help files
uv run wcpan-synology help files list
uv run wcpan-synology files list --help
```

Login options (`--base-url`, `--username`, `--password`, and `--otp-code`) can
appear before the command or after subcommands.

Omitted login options fall back to `WCPAN_SYNOLOGY_BASE_URL`,
`WCPAN_SYNOLOGY_USERNAME`, `WCPAN_SYNOLOGY_PASSWORD`, and
`WCPAN_SYNOLOGY_OTP_CODE`, respectively. Explicit command-line values take
precedence over environment variables. Network commands still require a base
URL, username, and password; the OTP code is optional.

Namespaced API call:

```bash
uv run wcpan-synology \
  --base-url https://nas.example:5001 \
  --username user \
  --password secret \
  files list \
  --path "id:123" \
  --limit 100
```

Python reference types:

```python
from wcpan.synology import (
    SynologyFileId,
    SynologyPath,
    SynologyPermanentLink,
    create_client,
)

async with create_client(
    base_url="https://nas.example:5001",
    username="user",
    password="secret",
) as client:
    by_file_id = await client.get_file(SynologyFileId("123456"))
    by_permalink = await client.get_file(
        SynologyPermanentLink("https://nas.example/d/some-token")
    )
    listing = await client.list_folder(SynologyPath("/mydrive/Documents"))
```

Use these types when the API parameter is named `path` but the actual value is
not a DSM path string. This avoids mixing raw file ids, permanent links, and
plain paths in one untyped `str`. File identifiers are normalized to their
canonical Synology forms:

- `SynologyFileId("123")` -> `id:123`
- `SynologyPermanentLink("...")` -> `link:...`

Generic API call:

```bash
uv run wcpan-synology \
  --base-url https://nas.example:5001 \
  --username user \
  --password secret \
  call \
  --api SYNO.SynologyDrive.Files \
  --version 11 \
  --method list \
  --param path='\"id:123\"' \
  --param sort_by='\"name\"' \
  --param sort_direction='\"asc\"'
```

## Compatibility behavior

Folder creation, rename, and upload normalize destination names to Unicode NFC.
Uploads use the normalized name for both the destination path and multipart
filename. Scalar multipart fields intentionally omit `Content-Type`; only the
file part includes it, matching behavior verified against Synology servers.

Errors from typed Files RPC methods use Synology-specific exceptions, not Python's
local filesystem exceptions. They inherit `SynologyApiError` and retain
`error_code`, the original response in `payload`, and the underlying error as
`__cause__` when translated:

| Drive Files codes | Exception / behavior |
| --- | --- |
| 1002, 1068, 1070 | `SynologyPermissionError` |
| 1003 | `SynologyNotFoundError` |
| 1005, 1008 | `SynologyDirectoryNotFoundError` (also `SynologyNotFoundError`) |
| 1009, 1010, 1024, 1025 | `SynologyInvalidOperationError` |
| 1011 | `SynologyUnsupportedError` |
| 1014, 1015 | `SynologyStorageFullError` |
| 1016, 1017 | `SynologyQuotaExceededError` (also `SynologyStorageFullError`) |
| 1018–1021, 1047, 1078 | `SynologyBusyError` |
| 1022 | `SynologyConflictError` |
| 1032 | `SynologyInvalidNameError` |
| 1033 | `SynologyFileTooLargeError` |
| 1034 | `SynologyPathTooLongError` |
| 1035 | `SynologyNameTooLongError` |
| 1069 | `SynologyLockedError` |

See [the error model](docs/error-model.md) for the evidence, scope, inheritance,
and deliberately uninterpreted cases. `get_file()` raises for missing files.
Codes 1005/1008 distinguish missing directories; the server may also report a
missing directory as 1003. Catch `SynologyNotFoundError` for any absence.

These meanings are derived from the Drive web UI's `Utils.initErrorStr()` and
navigation error handlers (TI97 bundles), and the missing-file behavior was
observed against Files v11. They are scoped to the Files API, not assumed for
Webhooks or other API families. Completed file-operation task failures use the
same mapping. Unknown errors remain `SynologyApiError`; generic `call()` always
preserves raw API errors. `download()` is excluded from the semantic mapping:
it retains streaming transport behavior and does not interpret file contents
as API errors. HTTP download errors raise `SynologyNetworkError`.

Upload connection failures raise `SynologyNetworkError`, preserving the original
error for retry decisions. Folder creation, rename, and upload retain the
existing `SynologyUploadConflictError` for code 1022; it is also a
`SynologyConflictError`. Recognized upload failures inherit both
`SynologyUploadError` and their semantic exception, and retain `file_name`,
`error_code`, and `payload`. Invalid names, oversized files, and excessive path
or name lengths also inherit `SynologyPermanentUploadError` (`retryable = False`).
The contextual name-too-long class is `SynologyUploadNameTooLongError`, also a
`SynologyNameTooLongError`, with `reason = "name_too_long"`; create/rename retain
this contextual behavior. Other Files operations use the neutral
`SynologyNameTooLongError`. Unknown upload codes raise `SynologyUploadError`.
Exceptions from the upload data iterator propagate unchanged.

Login transport failures raise `SynologyNetworkError`; rejected logins raise
`SynologyAuthenticationError`, retaining the server code and payload.
Malformed RPC envelopes, invalid JSON, missing login tokens, and invalid lookup
or task data raise `SynologyProtocolError` (a `SynologyApiError`). Upload protocol
errors also inherit `SynologyUploadError`. Generic `call()` permits empty
successful data; `get_file()` requires a file object. All exceptions are available
from `wcpan.synology`.

## Development

```bash
make test
make lint
make coverage
make build
```
