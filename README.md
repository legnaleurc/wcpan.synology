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

Upload connection failures raise `SynologyNetworkError`, preserving the original
error for callers that implement retries. API code `1022` raises
`SynologyUploadConflictError`. Code `1035` raises `SynologyNameTooLongError` for
uploads and folder creation; it inherits `SynologyPermanentUploadError`, with
`retryable = False` and `reason = "name_too_long"`. Other upload API failures raise
`SynologyUploadError`. These exceptions are available from `wcpan.synology`.

## Development

```bash
make test
make lint
make coverage
make build
```
