# Drive error interpretation

The transport raises `SynologyApiError` for unsuccessful RPC responses. Typed
Files RPC methods translate the codes below into subclasses, retaining `error_code`,
`payload`, and the original exception as their cause. Generic `call()` remains
raw, and the Files mapping does not apply to Webhooks or outer Tasks API errors.
File-operation task result errors use the Files mapping. `download()` is excluded:
it streams response bytes without interpreting them as RPC error envelopes.

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
Its `original_error` retains the underlying transport exception, including after
the client adds upload context. Errors from the upload source iterator retain
their identity and explicit `__cause__`, even if the HTTP library wraps them
while sending. Re-raising can change their traceback and implicit `__context__`,
as with normal Python exception propagation.
Upload closes the iterator obtained from the source when it supports `aclose()`,
including on errors, cancellation, and early server replies. Reads and closing
are serialized so cleanup does not close an iterator while a read is running.
If closing also fails during an existing failure or cancellation, the original
exception remains primary and receives a note describing the cleanup failure.
If there is no existing failure, a close error is raised; the server may already
have accepted the upload, so that exception alone does not mean a retry is safe.

Rejected logins raise `SynologyAuthenticationError` (a `SynologyApiError`) with
`error_code` and the RPC envelope in `payload`. Connectivity failures during login
raise `SynologyNetworkError` instead.

Invalid JSON, malformed RPC envelopes, missing session tokens, non-object
`get_file()` data, and malformed task results raise `SynologyProtocolError`.
Upload protocol failures are also `SynologyUploadError`. Generic `call()` allows
successful responses without data, since some RPC methods return no value.

For server-reported RPC errors, `payload` is the full response envelope. For
file-operation task errors it is the task data object, including all reported
errors; the first error selects the raised exception. For protocol errors it
contains the invalid decoded data, or the response text when JSON decoding fails.
Undecodable bytes in that diagnostic text are replaced with the Unicode
replacement character. Malformed task results retain the complete task data.

## Deliberately uninterpreted cases

Other codes remain raw, retaining their response payload. Examples include
1000/1048 (system errors), 1001 (`perm_op_fail`, insufficiently specific),
1031 (`access_token_invalid`, not necessarily the DSM login session), and the
sharing, Office, Chat, label, watermark, and cold-storage codes. Add categories
when a supported operation needs them and their meaning is established.

In particular, the permission panel displays both 1003 and 1036 as `NON_EXIST`,
but the message table calls 1036 `protection_shared_error`. UI presentation alone
must not turn this protection error into `SynologyNotFoundError`.

Downloads retain streaming transport behavior. JSON file contents must not be
mistaken for API errors; error-body handling needs separate protocol evidence.
Raw `stream_call()` and CLI downloads use this same path. The CLI consumes the
stream and reports HTTP status, headers, and received byte count as metadata.
