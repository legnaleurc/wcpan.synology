from abc import ABC, abstractmethod
from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import NotRequired, TypedDict

from aiohttp import ClientResponse


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


type SynologyNodeRef = SynologyFileId | SynologyPermanentLink
type SynologyParentRef = SynologyPath | SynologyFileId


@dataclass(frozen=True)
class SynologyChildRef:
    parent_ref: SynologyParentRef
    name: str


type SynologyLookupRef = (
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
    """Webhook data with app_id and webhook_id as strings containing integers."""

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


class SynologyClient(ABC):
    """Async interface to Synology Drive operations."""

    @abstractmethod
    async def call(
        self,
        *,
        api: str,
        version: int,
        method: str,
        **params: JsonValue,
    ) -> JsonValue: ...

    @abstractmethod
    def stream_call(
        self,
        *,
        api: str,
        version: int,
        method: str,
        extra_headers: dict[str, str] | None = None,
        **params: JsonValue,
    ) -> AbstractAsyncContextManager[ClientResponse]: ...

    @abstractmethod
    async def get_file(self, path: SynologyLookupRef) -> SynologyFileInfo: ...

    @abstractmethod
    async def list_folder(
        self,
        path: SynologyLookupRef,
        *,
        offset: int = 0,
        limit: int = 1000,
        sort_by: str = "name",
        sort_direction: str = "asc",
    ) -> tuple[list[SynologyFileInfo], int]: ...

    @abstractmethod
    async def create_folder(
        self,
        parent_path: SynologyParentRef,
        name: str,
    ) -> SynologyFileInfo: ...

    @abstractmethod
    async def rename(
        self,
        path: SynologyLookupRef,
        new_name: str,
    ) -> SynologyFileInfo: ...

    @abstractmethod
    async def move(
        self,
        node_id: SynologyNodeRef,
        new_parent_path: SynologyParentRef,
    ) -> None: ...

    @abstractmethod
    async def delete(self, node_id: SynologyNodeRef) -> None: ...

    @abstractmethod
    async def wait_task(self, task_id: str) -> None: ...

    @abstractmethod
    async def upload(
        self,
        parent_path: SynologyParentRef,
        name: str,
        data: AsyncIterable[bytes],
        *,
        mime_type: str | None = None,
    ) -> SynologyFileInfo: ...

    @abstractmethod
    def download(
        self,
        node_id: SynologyNodeRef,
        *,
        range_: slice | None = None,
    ) -> AbstractAsyncContextManager[ClientResponse]: ...

    @abstractmethod
    async def list_webhooks(self, *, app_id: str) -> list[SynologyWebhookInfo]: ...

    @abstractmethod
    async def create_webhook(self, *, url: str, app_id: str) -> str: ...

    @abstractmethod
    async def delete_webhook(self, *, webhook_id: str, app_id: str) -> None: ...
