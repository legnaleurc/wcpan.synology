# Drive error interpretation

The transport raises `SynologyApiError` for unsuccessful RPC responses. Typed
Files RPC methods translate the codes below into subclasses, retaining `error_code`,
the parsed `error` object, operation metadata, and the original exception as
their cause. Generic `call()` remains
raw, and the Files mapping does not apply to Webhooks or outer Tasks API errors.
File-operation task result errors use the Files mapping. `download()` is excluded:
successful file contents stream without interpretation as RPC error envelopes.

## Evidence

These mappings come from the supplied Drive web UI TI97 bundles:

- `synodrive_common_TI97.js`, `SYNO.SDS.Drive.Utils.initErrorStr()`, constructs
  an array of message keys, then assigns each entry to `1000 + index`.
- `synodrive_TI97.js`, `onGotoPathError()`, distinguishes `1002` (`NO_PERM`)
  from `1003` (`NON_EXIST`).
- The UI declares Files.get v3; the library uses v11. The code-1003 missing-child
  response was also observed live against v11. The other mappings are based on
  UI evidence, not a claim of a complete specification across DSM versions.

## Mappings

All class names below have the `Synology` prefix and `Error` suffix.

| Codes | UI message keys | Exception |
| --- | --- | --- |
| 1002, 1068, 1070 | permission_not_enough, error_privilege_not_enough | Permission |
| 1003 | node_not_exist | NotFound |
| 1005, 1008 | dir_not_exist | DirectoryNotFound |
| 1009, 1010 | move_to_child, copy_to_child | InvalidOperation |
| 1011 | not_support | Unsupported |
| 1014, 1015 | no_enough_space, space_not_enough | StorageFull |
| 1016, 1017 | volume_quota_full, share_quota_full | QuotaExceeded |
| 1018–1021 | volume_moving, backuping, moving_data (maintenance for non-admins) | Busy |
| 1022 | filename_exist | Conflict |
| 1024, 1025 | parent_path_conflict, file_type_conflict | InvalidOperation |
| 1032 | reserved_name | InvalidName |
| 1033 | file_too_big | FileTooLarge |
| 1034 | error_long_path | PathTooLong |
| 1035 | name_too_long | NameTooLong |
| 1047 | index_home_migrating | Busy |
| 1069 | error_node_locking_locked | Locked |
| 1078 | err_transforming_homes | Busy |

`DirectoryNotFound` inherits `NotFound`; `QuotaExceeded` inherits `StorageFull`.
`get_file()` raises `SynologyNotFoundError` for 1003, consistent with other
file operations. Codes 1005/1008 map to `SynologyDirectoryNotFoundError`; this
does not guarantee which code the server sends for every missing directory.
Catch `SynologyNotFoundError` to cover both missing nodes and directories.

Existing contextual upload/create/rename conflict exceptions remain
`SynologyUploadConflictError` (also a `SynologyConflictError`). The existing
create/rename/upload name-too-long behavior uses `SynologyUploadNameTooLongError`,
which inherits the neutral `SynologyNameTooLongError` and
`SynologyPermanentUploadError`. Other operations use the neutral exception.
Recognized upload failures inherit `SynologyUploadError` and their semantic
exception, retaining the destination `file_name`. Upload codes 1032–1035 also
inherit `SynologyPermanentUploadError` with `retryable = False`. Other semantic
categories do not promise that a retry will succeed: even Busy needs a caller's
retry policy.

## Transport and response failures

Connection, timeout, TLS, and HTTP status failures during RPC requests and
download setup raise `SynologyNetworkError`. After a download yields its raw
response, body-read failures retain their aiohttp or Python exception types;
exceptions from the consumer's code are not reclassified.
Network exceptions expose `operation`, optional `http_status`, and a parsed
`error` object when an HTTP failure body contains one. Their messages contain
the operation and failure category, without copying the HTTP library message.
`original_error` and the explicit cause contain a safe `SynologyTransportError`
snapshot with `error_type` and optional `errno`. The raw HTTP exception, its
request URL, and its response headers are not retained. Code that previously
used `isinstance(original_error, ...)` should use these fields or `http_status`.
The snapshot is preserved when the client adds upload context.
Errors from the upload source iterator retain
their identity and explicit `__cause__`, even if the HTTP library wraps them
while sending. Re-raising can change their traceback and implicit `__context__`,
as with normal Python exception propagation.
Upload closes the iterator obtained from the source when it supports `aclose()`,
including on errors, cancellation, and early server replies. Reads and closing
are serialized so cleanup does not close an iterator while a read is running.
If closing also fails during an existing failure or cancellation, the original
exception remains primary and receives a note naming the cleanup exception type.
If there is no existing failure, a close error is raised; the server may already
have accepted the upload, so that exception alone does not mean a retry is safe.

Rejected logins raise `SynologyAuthenticationError` (a `SynologyApiError`) with
`error_code` and the parsed, censored `error` object. Connectivity failures during login
raise `SynologyNetworkError` instead.

Invalid JSON, malformed RPC envelopes, missing session tokens, non-object
`get_file()` data, and malformed task results raise `SynologyProtocolError`.
Upload protocol failures are also `SynologyUploadError`. Generic `call()` allows
successful responses without data, since some RPC methods return no value.

API exceptions expose `error_code`, `error`, `operation`, and `http_status`.
The last two are `None` when unavailable. Only the parsed `error` object is
retained, rather than its containing response envelope. For completed task
failures, the first item of `result.errors` is retained and selects the exception.
Protocol exceptions do not retain malformed data, response text, or a JSON parser
exception that holds the input body. Error messages remain short; applications
can inspect structured fields for handling and choose where to log failures.

This replaces the former `payload` attribute and constructor parameter. Callers
should use `.error` for structured API details. Full JSON envelopes are
available only through optional response diagnostics; malformed text is omitted.

## Optional response diagnostics

The `wcpan.synology` logger emits response details at `DEBUG`. The library does
not configure logging, add output handlers, or log raised failures at ERROR.
Applications decide how to handle and log a failed operation. For example:

```python
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("wcpan.synology").setLevel(logging.DEBUG)
```

RPC response previews are redacted before being limited to 4096 characters,
with a truncation marker when necessary. This includes successful RPC responses
and error envelopes. A diagnostic object supplies safe `__str__` and `__repr__`
formatting. Invalid JSON produces a metadata-only log message; its text is never
logged. HTTP failure bodies are parsed for an `error` object on a
best-effort basis; a body-read failure does not replace the HTTP status failure.
Successful file-download streams are never read or logged for diagnostics.

## Credential redaction

SID, password, and OTP values use an internal `Secret` wrapper. Its `__str__`,
`__repr__`, and `__format__` show `[REDACTED]`; `.reveal()` is required when
assembling HTTP parameters. Public client credential arguments remain strings.

A small recursive sanitizer masks known credential keys in parsed JSON and
header dictionaries, including session IDs, passwords, OTPs, tokens,
authorization headers, cookies, and API keys. Exceptions and response previews
use sanitized copies. Successful library return values and streamed file bytes
remain unchanged; CLI JSON output masks these credential fields.

Transport errors are represented by safe metadata rather than raw exceptions.
The library does not traverse or modify arbitrary exception graphs, scan strings
with regular expressions, or keep a registry of secret values. Upload-source
and consumer exceptions remain owned by the application and retain their type
and identity. Cleanup notes include only an exception type, not its message.

This protects known credential fields and formatting of wrapped credentials.
Credentials echoed under unrelated JSON keys or embedded in arbitrary strings
are not detected. Third-party HTTP tracing, server access logs, debugger locals,
and application logging of successful raw responses need their own handling.

## Deliberately uninterpreted cases

Other codes remain `SynologyApiError`, retaining their parsed error object. Examples include
1000/1048 (system errors), 1001 (`perm_op_fail`, insufficiently specific),
1031 (`access_token_invalid`, not necessarily the DSM login session), and the
sharing, Office, Chat, label, watermark, and cold-storage codes. Add categories
when a supported operation needs them and their meaning is established.

In particular, the permission panel displays both 1003 and 1036 as `NON_EXIST`,
but the message table calls 1036 `protection_shared_error`. UI presentation alone
must not turn this protection error into `SynologyNotFoundError`.

Downloads retain streaming transport behavior. Successful JSON file contents
are never interpreted as API errors. An unsuccessful HTTP status can expose
a parsed `error` object, just like other HTTP failures.
Raw `stream_call()` and CLI downloads use this same path. The CLI consumes the
stream and reports HTTP status, headers, and received byte count as metadata.
