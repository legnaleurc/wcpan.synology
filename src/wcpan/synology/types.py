from dataclasses import dataclass
from typing import NotRequired, TypedDict


type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


@dataclass(frozen=True)
class SynologyPath:
    path: str


@dataclass(frozen=True)
class SynologyFileId:
    file_id: str


@dataclass(frozen=True)
class SynologyPermanentLink:
    permanent_link: str


type FileIdentifier = SynologyFileId | SynologyPermanentLink
type ParentParameter = SynologyPath | SynologyFileId


@dataclass(frozen=True)
class SynologyChildRef:
    parent_ref: ParentParameter
    name: str


type PathParameter = (
    SynologyPath | SynologyFileId | SynologyPermanentLink | SynologyChildRef
)


class SynologyFileInfo(TypedDict):
    file_id: str
    parent_id: str
    permanent_link: NotRequired[str]
    display_path: NotRequired[str]
    name: str
    type: str
    content_type: str
    hash: NotRequired[str]
    size: int
    created_time: int
    modified_time: int
    change_time: NotRequired[int]
    sync_id: int
    max_id: NotRequired[int]
    removed: NotRequired[bool]


class SynologyFileListResponse(TypedDict):
    items: list[SynologyFileInfo]
    total: int


class SynologyWebhookInfo(TypedDict):
    webhook_id: str
    app_id: str
    type: str
    url: str
    so_name: str
    token: str


class SynologyWebhookEvent(TypedDict):
    event_type: str
    file_id: str
    permanent_link: str
    file_type: str
    parent_id: str


class SynologyWebhookListResponse(TypedDict):
    items: list[SynologyWebhookInfo]
    total: int


class SynologyWebhookCreateResponse(TypedDict):
    webhook_id: str


class SynologyTaskError(TypedDict):
    code: int
    message: NotRequired[str]


class SynologyTaskResult(TypedDict):
    errors: list[SynologyTaskError]


class SynologyTaskInfo(TypedDict):
    status: str
    result: NotRequired[SynologyTaskResult]


class SynologyAsyncTaskResponse(TypedDict):
    async_task_id: str


def to_path_parameter_value(value: PathParameter) -> str:
    if isinstance(value, SynologyPath):
        return value.path
    if isinstance(value, SynologyFileId):
        return f"id:{value.file_id}"
    if isinstance(value, SynologyChildRef):
        return f"{to_parent_parameter_value(value.parent_ref)}/{value.name}"
    return f"link:{value.permanent_link}"


def to_file_identifier_value(value: FileIdentifier) -> str:
    if isinstance(value, SynologyFileId):
        return f"id:{value.file_id}"
    return f"link:{value.permanent_link}"


def to_parent_parameter_value(value: ParentParameter) -> str:
    if isinstance(value, SynologyPath):
        return value.path
    # Child-addressing with `id:<id>/<name>` is already documented and
    # validated, so normalize file-id parents to that form when composing.
    return f"id:{value.file_id}"
