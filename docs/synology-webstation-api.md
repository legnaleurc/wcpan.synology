# Synology WebStation SynologyDrive API Reference

This document is a self-contained reference for the Synology Drive APIs exposed through DSM WebStation `webapi/entry.cgi`.

It describes the `SYNO.SynologyDrive.*` API family, including:

- common transport rules shared by the Drive API surface
- the namespace catalog commonly exposed by DSM Drive
- detailed request and response guidance for the documented namespaces in this file

All examples are sanitized. Server names, IDs, paths, and tokens are placeholders.

## Drive API Family Overview

The WebStation-facing Drive API is a namespace-based RPC surface. The most
commonly exposed namespaces fall into a few functional groups.

### Content And Navigation

- `SYNO.SynologyDrive.Files`
  - primary file and folder operations such as metadata lookup, listing, search,
    create, rename, move, delete, download, and upload
- `SYNO.SynologyDrive.Tasks`
  - async task tracking for operations that do not finish in the initial request
- `SYNO.SynologyDrive.Labels`
  - personal labels and shared-label operations used by file classification flows
- `SYNO.SynologyDrive.TeamFolders`
  - team folder listing and management flows
- `SYNO.SynologyDrive.Trash`
  - recycle-bin style listing, restore, and empty operations
- `SYNO.SynologyDrive.Revisions`
  - file version history and restore flows

### Sharing And Permissions

- `SYNO.SynologyDrive.Share`
  - share-link oriented operations
- `SYNO.SynologyDrive.Sharing`
  - sharing membership and sharing-state operations
- `SYNO.SynologyDrive.Share.Priv`
  - share privilege lookup and update flows
- `SYNO.SynologyDrive.AdvanceSharing`
  - protected-share features such as passwords, expiration, and advanced access rules
- `SYNO.SynologyDrive.AdvanceSharing.Public`
  - public-link specific advanced sharing flows
- `SYNO.SynologyDrive.FileRequest`
  - file-request creation and management
- `SYNO.SynologyDrive.Users`
  - user lookup and access-related operations used by sharing workflows

### Bootstrap, Settings, And App State

- `SYNO.SynologyDrive.Info`
  - Drive capability and environment bootstrap information
- `SYNO.SynologyDrive.Config`
  - Drive feature configuration
- `SYNO.SynologyDrive.Settings`
  - user or package settings
- `SYNO.SynologyDrive.DSM`
  - DSM integration helpers used by the Drive web app
- `SYNO.SynologyDrive.String`
  - localized string or string-bundle related lookup
- `SYNO.SynologyDrive.Notifications`
  - Drive notification flows

### Cross-App And Service Integrations

- `SYNO.SynologyDrive.Office`
  - Drive and Synology Office integration
- `SYNO.SynologyDrive.Photos`
  - Drive and Synology Photos integration
- `SYNO.SynologyDrive.Services.DocumentViewer`
  - document preview and viewer service integration
- `SYNO.SynologyDrive.Services.SynologyChat`
  - Synology Chat integration hooks
- `SYNO.SynologyDrive.Services.VideoStation`
  - Video Station integration hooks
- `SYNO.SynologyDrive.Webhooks`
  - outbound webhook registration and lifecycle management

### Common Method Families

Across the Drive API family, method names typically follow a small set of
patterns:

- read-style methods: `get`, `list`, `search`, `status`, `quota`, `get_metadata`, `get_thumbnail`
- write-style methods: `create`, `update`, `delete`, `set`, `move`, `copy`, `restore`
- sharing-style methods: `create_link`, `request_access`, `shared_with_me`, `shared_with_others`
- list variants: `list_ancestor`, `list_labelled`, `list_shared_with_me`, `list_starred`
- upload/download methods: `download`, `upload`, `upload_from_dsm`
- device or integration methods: `sync_to_device`, `bind`, `access`

When approaching a new namespace, start by identifying its method family and
then apply the transport rules from the next sections.

## Observed Namespace Catalog

This section enumerates the `SYNO.SynologyDrive.*` namespaces observed in the
Drive web bundles and summarizes their apparent role in the web application.
Where method names were visible in request descriptors, they are listed as
observed method hints rather than exhaustive schemas.

### `SYNO.SynologyDrive.AdvanceSharing`

- purpose: advanced share-link management, including protected links, access
  rules, expiration, and password-oriented flows
- observed method hints: `create_link`, `get`, `update`, `delete`

### `SYNO.SynologyDrive.AdvanceSharing.Public`

- purpose: public-facing advanced-sharing flows for links intended for broader
  external access
- observed method hints: `get`, `update`, `delete`

### `SYNO.SynologyDrive.Config`

- purpose: Drive package configuration and capability toggles used by the web
  app at bootstrap time
- observed method hints: `get`

### `SYNO.SynologyDrive.DSM`

- purpose: DSM integration helpers used by the Drive UI when it needs DSM-side
  environment or package state
- observed method hints: `get`, `status`

### `SYNO.SynologyDrive.FileRequest`

- purpose: file-request creation, retrieval, and lifecycle management
- observed method hints: `create`, `get`, `list`, `update`, `delete`

### `SYNO.SynologyDrive.Files`

- purpose: primary file and folder namespace for metadata, listing, search,
  create, move, delete, upload, download, and related content operations
- observed method hints: `get`, `list`, `search`, `create`, `update`, `move`,
  `copy`, `delete`, `download`, `upload`, `upload_from_dsm`, `get_metadata`,
  `get_thumbnail`, `list_ancestor`, `list_labelled`, `list_starred`,
  `list_shared_with_me`, `shared_with_me`, `shared_with_others`,
  `sync_to_device`

### `SYNO.SynologyDrive.Info`

- purpose: Drive environment bootstrap and capability discovery
- observed method hints: `get`

### `SYNO.SynologyDrive.Labels`

- purpose: personal labels and shared labels attached to files
- observed method hints: `list`, `create`, `update`, `delete`, `set`
- observed response shape hints:
  - personal labels commonly expose `label_id`, `name`, `color`, `position`
  - shared labels additionally expose fields such as `permission`, `display`,
    and `apply_permission`

### `SYNO.SynologyDrive.Notifications`

- purpose: Drive notification retrieval and state updates inside the web UI
- observed method hints: `list`, `get`, `update`

### `SYNO.SynologyDrive.Office`

- purpose: integration points between Drive and Synology Office documents
- observed method hints: `get`, `access`, `lock`, `request_unlock`

### `SYNO.SynologyDrive.Photos`

- purpose: integration points between Drive and Synology Photos resources
- observed method hints: `get`, `list`

### `SYNO.SynologyDrive.Revisions`

- purpose: file revision history and revision restore workflows
- observed method hints: `list`, `get`, `restore`

### `SYNO.SynologyDrive.SCIM.Photo`

- purpose: SCIM-backed photo lookup or photo identity helpers referenced by the
  Drive web app
- observed method hints: `get`

### `SYNO.SynologyDrive.SCIM.User`

- purpose: SCIM-backed user lookup or identity helpers referenced by the Drive
  web app
- observed method hints: `get`, `list`

### `SYNO.SynologyDrive.Services.DocumentViewer`

- purpose: document preview and viewer service integration
- observed method hints: `get`, `access`

### `SYNO.SynologyDrive.Services.SynologyChat`

- purpose: Synology Chat integration used for sharing and collaboration entry
  points
- observed method hints: `get`, `send`, `bind`

### `SYNO.SynologyDrive.Services.VideoStation`

- purpose: Video Station integration used when Drive content is handed off to
  media playback flows
- observed method hints: `get`, `access`

### `SYNO.SynologyDrive.Settings`

- purpose: user or package settings stored for the Drive experience
- observed method hints: `get`, `set`, `update`

### `SYNO.SynologyDrive.Share`

- purpose: share-link oriented operations for Drive nodes
- observed method hints: `create`, `get`, `update`, `delete`, `create_link`

### `SYNO.SynologyDrive.Share.Priv`

- purpose: privilege lookup and modification for share recipients and link roles
- observed method hints: `get`, `list`, `update`, `delete`

### `SYNO.SynologyDrive.Sharing`

- purpose: sharing state, recipient management, and shared-content listing
- observed method hints: `list`, `get`, `update`, `delete`, `shared_with_me`,
  `shared_with_others`, `request_access`

### `SYNO.SynologyDrive.String`

- purpose: localized strings or string-resource access used by the Drive app
- observed method hints: `get`

### `SYNO.SynologyDrive.Tasks`

- purpose: async task inspection for operations that continue after the initial
  request
- observed method hints: `list`, `get`, `status`

### `SYNO.SynologyDrive.TeamFolders`

- purpose: team-folder discovery and management
- observed method hints: `list`, `get`, `update`

### `SYNO.SynologyDrive.Trash`

- purpose: recycle-bin style operations for deleted Drive content
- observed method hints: `list`, `restore`, `empty`

### `SYNO.SynologyDrive.Users`

- purpose: user lookup and recipient resolution used by permissions, sharing,
  and access-related flows
- observed method hints: `get`, `list`, `search`

### `SYNO.SynologyDrive.Webhooks`

- purpose: webhook registration, inspection, update, and deletion
- observed method hints: `create`, `get`, `update`, `delete`, `list`

## Using Undocumented Namespaces Safely

For Drive namespaces that are not expanded into full method-by-method sections
later in this file, use the following checklist:

- call `/webapi/entry.cgi`
- send `api`, `version`, `method`, and `_sid`
- JSON-encode scalar ids and array/object parameters when using query-string RPC
- expect namespace availability and accepted method sets to vary by DSM version and Drive package version
- verify on the target server that the namespace exists, the requested version is accepted, and the request format matches that deployment

## Scope And Verification

The reference combines two sources:

- exported Synology Drive OpenAPI schemas for method fields and response shapes
- live WebStation probing for transport rules and async task behavior

Verification status:

- `SYNO.SynologyDrive.Files`
  - `get`, `list`, `search`, `create`, `update`, `move`, `delete`, `download`, `upload`: WebStation transport live-verified
- `SYNO.SynologyDrive.Tasks`
  - `list`, `get`: live-verified
  - conflict payload for `move` with `conflict_action=stop`: live-verified
- `SYNO.SynologyDrive.Webhooks`
  - namespace exists and methods are recognized: live-verified
  - `create`, `get`, `delete`: live-verified with JSON-encoded query parameters
  - field-level schemas: taken from the exported Synology schema

## Common Rules

### Entrypoint

All documented methods use:

```http
/webapi/entry.cgi
```

Authentication is via an existing DSM WebAPI session id:

- `_sid=<sid>`

This document assumes the caller already has a valid `_sid`.

### Response Envelope

The common JSON envelope is:

```json
{
  "success": true,
  "data": {}
}
```

or:

```json
{
  "success": false,
  "error": {
    "code": 401,
    "errors": {
      "message": "..."
    }
  }
}
```

### Normal Transport

For `Files`, `Tasks`, and `Webhooks`, the working WebStation transport is:

```http
GET /webapi/entry.cgi
```

Query parameters always include:

- `api=<namespace>`
- `version=<version>`
- `method=<method>`
- `_sid=<sid>`

Observed compatibility notes:

- The WebStation API index advertises `requestFormat: JSON` for these namespaces.
- In practice, the working transport is query-string RPC with JSON-encoded parameter values.
- Scalar fields such as `webhook_id` and `app_id` must be JSON-encoded as strings.
- Array-valued fields such as `files` must be JSON-stringified inside a single query parameter.

Working example:

```text
api=SYNO.SynologyDrive.Files
version=11
method=move
_sid=<sid>
to_parent_folder="id:<folder-id>"
conflict_action="stop"
files=["id:<file-id>"]
```

### Upload Transport

`SYNO.SynologyDrive.Files.upload` uses multipart upload instead of the normal query-string RPC.

Working pattern:

```http
POST /webapi/entry.cgi?api=SYNO.SynologyDrive.Files&version=11&method=upload&_sid=<sid>
Content-Type: multipart/form-data
```

Multipart fields:

- `file`
- `path`
- optional upload fields such as `type`, `conflict_action`, `mute`

Observed working `path` form for upload:

- `id:<parent-id>/<basename>`

### Path And ID Forms

Observed working path forms on WebStation:

- ID-system forms:
  - `link:<permanent_link>`
  - `id:<file-id>`
  - `id:<file-id>/<basename>`
- path forms:
  - `/mydrive/<relative-path>`
  - `/team-folders/<team-folder-name>/<relative-path>`
  - `/views/<view_id>/<relative-path>`
  - `/volumes/<absolute-path>`

Notes:

- `link:<permanent_link>` is the explicit permanent-link reference form.
- `id:<file-id>` addresses an existing node directly.
- `id:<file-id>/<basename>` is used when addressing a child beneath a parent id,
  such as upload and create-style operations.
- `/volumes/<absolute-path>` is an absolute-path form rather than a Drive-relative
  path.

Observed response path behavior:

- `display_path` is the full accessible path
- `path` is a Drive-relative path in the current navigation context

This difference matters when comparing request payloads with returned metadata.

### Async Behavior

`SYNO.SynologyDrive.Files.move` returns an async task id immediately.

The initial response does not prove the move succeeded. The authoritative result is in:

- `SYNO.SynologyDrive.Tasks.get`

Observed example for a conflict with `conflict_action=stop`:

- initial move call: `success: true` with `async_task_id`
- later task result: `status: finished` and `result.errors[0].code == 1022`

## `SYNO.SynologyDrive.Files`

Namespace metadata:

- namespace: `SYNO.SynologyDrive.Files`
- advertised WebStation version: `11`
- entrypoint: `/webapi/entry.cgi`

### Method Summary

| Method | Purpose | Status |
| --- | --- | --- |
| `get` | Fetch one file or folder by path or id | live-verified |
| `list` | List children in a folder | live-verified |
| `search` | Search files | live-verified |
| `create` | Create a folder or small file | live-verified |
| `update` | Rename or update metadata | live-verified |
| `move` | Move files or folders | live-verified |
| `delete` | Delete files or folders | live-verified |
| `download` | Download files | live-verified |
| `upload` | Multipart upload | live-verified |

### Common File Metadata Shape

Most successful `Files` methods return a `FileInfo` object or an array of them.

Observed field semantics from a live `list` response:

- `file_id`: file or folder id
- `parent_id`: parent folder id
- `name`
- `type`: `file` or `dir`
- `content_type`: media or preview classification; for example a regular file can be `type: "file"` with `content_type: "image"`, while folders use `content_type: "dir"`
- `path`: path relative to the requested parent or navigation root; for `list(path="id:<folder-id>")` the child entries are returned as `/<child-name>`, not as full Drive paths
- `display_path`: full accessible Drive path such as `/team-folders/<share>/<path>`
- `size`: bytes; folders are `0`
- `hash`: content hash for files, empty string for folders
- `created_time`
- `modified_time`
- `access_time`
- `change_time`
- `capabilities`
- `version_id`: observed as a string in live payloads
- `sync_id`
- `change_id`
- `max_id`
- `removed`
- `shared`
- `starred`
- `encrypted`

Timestamp caveat from the observed payload:

- `modified_time` looks like the file content timestamp
- `created_time`, `access_time`, and `change_time` look more like Drive record or sync-event timestamps than filesystem birth / access / ctime values
- `image_metadata.time` exists in the observed payload, but its meaning is still unknown

The exported schema and live payloads also include:

- `permanent_link`
- `owner`
- `shared_with`
- `labels`
- `properties`
- `app_properties`
- `image_metadata`
- `watermark_version`
- `disable_download`
- `enable_watermark`
- `force_watermark_download`
- `support_remote`
- `transient`
- `uploaded_size`
- `last_modified_by`
- `dsm_path`
- `sync_to_device`
- `revisions`
- `content_snippet`
- `adv_shared`
- `in_disconnected_cold_tier`
- `node_locking`

### `get`

Transport:

```text
api=SYNO.SynologyDrive.Files
version=11
method=get
_sid=<sid>
path=<full-path-or-id-ref>
```

Required fields:

- `path`

Accepted forms observed on WebStation:

- `link:<permanent_link>`
- `id:<file-id>`
- `/mydrive/<path>`
- `/team-folders/<share>/<path>`
- `/views/<view_id>/<path>`
- `/volumes/<absolute-path>`

Response:

- `success: true`
- `data: <FileInfo>`

### `list`

Transport:

```text
api=SYNO.SynologyDrive.Files
version=11
method=list
_sid=<sid>
path=<folder-path-or-id-ref>
sort_by=name
sort_direction=asc
offset=0
limit=0
filter={"type":["file","dir"]}
extra=["sync_to_device"]
```

Required fields:

- `path`

Optional query-style fields:

- `sort_by`
- `sort_direction`
- `offset`
- `limit`

Optional body-style fields carried in the form payload:

- `filter`
  - `extensions`
  - `type`
  - `label_id`
  - `starred`
- `extra`
  - currently documented value: `sync_to_device`

Response:

```json
{
  "success": true,
  "data": {
    "total": 2,
    "items": [
      {
        "file_id": "<file-id>",
        "name": "a.txt",
        "type": "file",
        "content_type": "image",
        "path": "/a.txt",
        "display_path": "/team-folders/share/folder/a.txt"
      }
    ]
  }
}
```

### `search`

`search` is available on WebStation and was live-verified as a recognized working method.

This document records method availability and transport compatibility. It does not restate the full search schema because the current integration does not depend on it.

Transport:

```text
api=SYNO.SynologyDrive.Files
version=11
method=search
_sid=<sid>
...
```

### `create`

`create` supports:

- folder creation
- small file creation via base64 body content

Transport:

```text
api=SYNO.SynologyDrive.Files
version=11
method=create
_sid=<sid>
type=folder
path=id:<parent-id>/new-folder
conflict_action=stop
mute=false
```

Required fields:

- `type`
  - valid values: `file`, `folder`
- `path`

Optional fields:

- `conflict_action`
  - `overwrite`, `autorename`, `stop`
- `mute`
- `permanent_link`
- `encrypted`
- `removed`
- `file_content`
  - base64 encoded
  - limited to about 1 MB
- `labels`
- `modified_time`
- `access_time`
- `created_time`

Response:

- `success: true`
- `data: <FileInfo>`

### `update`

`update` is the rename and metadata-update method on WebStation.

Transport:

```text
api=SYNO.SynologyDrive.Files
version=11
method=update
_sid=<sid>
path=id:<file-id>
name=new-name.txt
```

Required fields:

- `path`

Optional fields:

- `name`
- `mute`
- `encrypted`
- `removed`
- `starred`
- `labels`
- `modified_time`
- `created_time`
- `access_time`

Observed behavior:

- rename conflicts are surfaced as normal API errors
- move conflicts are not surfaced here because `move` is async

Response:

- `success: true`
- `data: <FileInfo>`

### `move`

Transport:

```text
api=SYNO.SynologyDrive.Files
version=11
method=move
_sid=<sid>
to_parent_folder=id:<folder-id>
conflict_action=stop
files=["id:<file-id>"]
```

Required fields:

- `to_parent_folder`
- `files`

Optional fields:

- `dry_run`
- `conflict_action`
  - `overwrite`, `autorename`, `skip`, `stop`, `version`

Important transport rule:

- `files` must be one JSON-stringified array field, not repeated `files=` entries

Immediate response:

```json
{
  "success": true,
  "data": {
    "async_task_id": "task-<n>"
  }
}
```

Authoritative result:

- poll `SYNO.SynologyDrive.Tasks.get(task_id)`

Observed conflict behavior for `conflict_action=stop`:

- initial move response still returns `success: true`
- the task later finishes with:
  - `result.errors[0].code == 1022`
  - `result.errors[0].message == "file operation is stopped"`
- source and destination remain unchanged after the blocked move

### `delete`

Transport:

```text
api=SYNO.SynologyDrive.Files
version=11
method=delete
_sid=<sid>
files=["id:<file-id>"]
permanent=false
```

Required fields:

- `files`

Optional fields:

- `permanent`

Transport note:

- `files` follows the same JSON-stringified array rule as `move`

Response:

- `success: true`
- async tracking may be needed depending on the operation result path

### `download`

Transport:

```text
api=SYNO.SynologyDrive.Files
version=11
method=download
_sid=<sid>
files=["id:<file-id>"]
dry_run=false
force_download=true
archive_name=download
```

Required fields:

- `files`

Optional fields:

- `dry_run`
- `decrypt`
- `force_download`
- `archive_name`

Behavior:

- one file may be returned directly
- multiple files are archived into a zip stream
- `dry_run=true` is used to validate whether the download can proceed

### `upload`

Transport:

```http
POST /webapi/entry.cgi?api=SYNO.SynologyDrive.Files&version=11&method=upload&_sid=<sid>
Content-Type: multipart/form-data
```

Multipart fields:

- required:
  - `file`
  - `path`
- optional:
  - `conflict_action`
  - `type`
  - `mute`
  - `encrypted`
  - `starred`
  - `labels`
  - `modified_time`
  - `created_time`
  - `access_time`

Observed working path form:

- `id:<parent-id>/<basename>`

Example:

```text
path=id:<parent-id>/report.pdf
type=file
conflict_action=stop
```

Response:

- `success: true`
- `data: <FileInfo>`

## `SYNO.SynologyDrive.Tasks`

Namespace metadata:

- namespace: `SYNO.SynologyDrive.Tasks`
- version: `1`
- entrypoint: `/webapi/entry.cgi`

This namespace is the authoritative source for async Drive operation results.

### `list`

Transport:

```text
api=SYNO.SynologyDrive.Tasks
version=1
method=list
_sid=<sid>
```

Response:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "task_id": "task-<n>",
        "status": "in_progress",
        "progress": 0,
        "result": {
          "action": "move",
          "errors": null,
          "names": ["sample.txt"],
          "params": {
            "files": [
              {
                "path": "id:<file-id>"
              }
            ]
          }
        }
      }
    ],
    "total": 1
  }
}
```

### `get`

Transport:

```text
api=SYNO.SynologyDrive.Tasks
version=1
method=get
_sid=<sid>
task_id=task-<n>
```

Success response:

```json
{
  "success": true,
  "data": {
    "task_id": "task-<n>",
    "status": "finished",
    "progress": 100,
    "result": {
      "action": "move",
      "errors": [],
      "processed_size": 123,
      "total_size": 123,
      "names": ["sample.txt"],
      "params": {
        "files": [
          {
            "path": "id:<file-id>"
          }
        ]
      },
      "targets": [
        {
          "file_id": "<file-id>",
          "parent_id": "<parent-id>",
          "file_type": "file",
          "name": "sample.txt",
          "path": "/folder/sample.txt"
        }
      ]
    }
  }
}
```

Observed invalid task response:

```json
{
  "success": false,
  "error": {
    "code": 401,
    "errors": {
      "message": "invalid task id"
    }
  }
}
```

Observed move-conflict response:

```json
{
  "success": true,
  "data": {
    "task_id": "task-<n>",
    "status": "finished",
    "progress": 100,
    "result": {
      "action": "move",
      "errors": [
        {
          "code": 1022,
          "message": "file operation is stopped",
          "context": {
            "file_type": "file",
            "name": "sample.txt",
            "path": "/folder/sample.txt"
          }
        }
      ],
      "processed_size": 0,
      "total_size": 123
    }
  }
}
```

Practical rule:

- for async file operations, task status is authoritative
- do not treat the initial `async_task_id` response as final success

## `SYNO.SynologyDrive.Webhooks`

Namespace metadata:

- namespace: `SYNO.SynologyDrive.Webhooks`
- version: `2`
- entrypoint: `/webapi/entry.cgi`

Methods recognized on WebStation:

- `create`
- `get`
- `update`
- `delete`
- `list`

Transport:

```text
api=SYNO.SynologyDrive.Webhooks
version=2
method=<create|get|update|delete|list>
_sid=<sid>
...
```

### Webhook Object

Fields:

- `webhook_id`
- `app_id`
- `type`
  - `url` or `shared_library`
- `url`
- `so_name`
- `token`
- `options`

`options` fields:

- `filter_file_ext`
- `filter_events`

### `create`

Required fields:

- `type`
- `app_id`

Additional required field for URL webhook:

- `url`

Optional fields:

- `token`
- `options`
- `so_name`

Response:

```json
{
  "success": true,
  "data": {
    "type": "url",
    "url": "https://example.invalid/webhook",
    "token": "",
    "app_id": "<app-id>",
    "webhook_id": "<webhook-id>"
  }
}
```

### `get`

Required fields:

- `webhook_id`
- `app_id`

Observed live-verified transport:

- query parameters are JSON-encoded strings
- example shape:
  - `api=SYNO.SynologyDrive.Webhooks`
  - `version=2`
  - `method=get`
  - `_sid=<sid>`
  - `webhook_id="<webhook-id>"`
  - `app_id="<app-id>"`

Response:

- `success: true`
- `data: <WebhookObject>`

### `update`

Required fields:

- `webhook_id`
- `app_id`
- `type`

Optional fields:

- `url`
- `token`
- `options`
- `so_name`

Response:

- `success: true`
- `data: <WebhookObject>`

### `delete`

Required fields:

- `webhook_id`
- `app_id`

Observed live-verified transport:

- query parameters are JSON-encoded strings
- example shape:
  - `api=SYNO.SynologyDrive.Webhooks`
  - `version=2`
  - `method=delete`
  - `_sid=<sid>`
  - `webhook_id="<webhook-id>"`
  - `app_id="<app-id>"`

Response:

```json
{
  "success": true
}
```

### `list`

Required fields:

- `app_id`

Response:

```json
{
  "success": true,
  "data": {
    "total": 1,
    "items": [
      {
        "type": "url",
        "url": "https://example.invalid/webhook",
        "token": "",
        "app_id": "<app-id>",
        "webhook_id": "<webhook-id>"
      }
    ]
  }
}
```

## Compatibility Notes For Migration

The WebStation SynologyDrive APIs cover the current integration surface:

- file metadata lookup
- folder listing
- create folder
- rename
- move
- delete
- upload
- download
- webhook management
- async task tracking

Important incompatibilities from the REST-style API shape:

1. Calls go to `/webapi/entry.cgi` with `api`, `version`, and `method`, not resource paths.
2. Authentication uses `_sid`.
3. Normal requests are query-string RPC calls.
4. Parameter values are JSON-encoded, including scalar ids like `app_id` and `webhook_id`.
5. Array params such as `files` must be JSON-stringified.
6. Upload uses multipart and places `api`, `version`, `method`, and `_sid` in the query string.
7. `move` success must be confirmed with `SYNO.SynologyDrive.Tasks.get`.
