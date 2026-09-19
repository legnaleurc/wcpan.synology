import asyncio
import unicodedata
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from aiohttp import ClientResponse

from ._transport import SynologyTransport, create_transport
from .errors import (
    SynologyApiError,
    SynologyNameTooLongError,
    SynologyNetworkError,
    SynologyUploadConflictError,
    SynologyUploadError,
)
from .types import (
    JsonValue,
    SynologyAsyncTaskResponse,
    SynologyFileInfo,
    SynologyFileListResponse,
    SynologyLookupRef,
    SynologyNodeRef,
    SynologyParentRef,
    SynologyTaskInfo,
    SynologyWebhookCreateResponse,
    SynologyWebhookInfo,
    SynologyWebhookListResponse,
    to_file_identifier_value,
    to_parent_parameter_value,
    to_path_parameter_value,
)


FILES_API = "SYNO.SynologyDrive.Files"
FILES_VERSION = 11
TASKS_API = "SYNO.SynologyDrive.Tasks"
TASKS_VERSION = 1
WEBHOOKS_API = "SYNO.SynologyDrive.Webhooks"
WEBHOOKS_VERSION = 2
TASK_POLL_DELAYS = [0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


class SynologyClient:
    def __init__(self, *, transport: SynologyTransport) -> None:
        self._transport = transport

    async def call(
        self,
        *,
        api: str,
        version: int,
        method: str,
        **params: JsonValue,
    ) -> JsonValue:
        return await self._transport.request(api, version, method, **params)

    async def get_file(self, path: SynologyLookupRef) -> SynologyFileInfo | None:
        return await self._transport.request(
            FILES_API,
            FILES_VERSION,
            "get",
            path=to_path_parameter_value(path),
        )

    async def list_folder(
        self,
        path: SynologyLookupRef,
        *,
        offset: int = 0,
        limit: int = 1000,
        sort_by: str = "name",
        sort_direction: str = "asc",
    ) -> tuple[list[SynologyFileInfo], int]:
        data: SynologyFileListResponse = await self._transport.request(
            FILES_API,
            FILES_VERSION,
            "list",
            path=to_path_parameter_value(path),
            sort_by=sort_by,
            sort_direction=sort_direction,
            offset=offset,
            limit=limit,
        )
        return data["items"], data["total"]

    async def create_folder(
        self,
        parent_path: SynologyParentRef,
        name: str,
    ) -> SynologyFileInfo:
        name = unicodedata.normalize("NFC", name)
        try:
            data: SynologyFileInfo = await self._transport.request(
                FILES_API,
                FILES_VERSION,
                "create",
                type="folder",
                path=f"{to_parent_parameter_value(parent_path)}/{name}",
                conflict_action="stop",
            )
        except SynologyApiError as exc:
            if exc.error_code == 1022:
                raise SynologyUploadConflictError(
                    f"Folder {name!r} already exists",
                    file_name=name,
                ) from exc
            if exc.error_code == 1035:
                raise SynologyNameTooLongError(
                    f"File name is too long for Synology Drive: {name!r}",
                    file_name=name,
                ) from exc
            raise
        return data

    async def rename(
        self,
        path: SynologyLookupRef,
        new_name: str,
    ) -> SynologyFileInfo:
        new_name = unicodedata.normalize("NFC", new_name)
        try:
            data: SynologyFileInfo = await self._transport.request(
                FILES_API,
                FILES_VERSION,
                "update",
                path=to_path_parameter_value(path),
                name=new_name,
            )
        except SynologyApiError as exc:
            if exc.error_code == 1022:
                raise SynologyUploadConflictError(
                    f"Rename conflict for {new_name!r}",
                    file_name=new_name,
                ) from exc
            raise
        return data

    async def move(
        self,
        node_id: SynologyNodeRef,
        new_parent_path: SynologyParentRef,
    ) -> None:
        data: SynologyAsyncTaskResponse = await self._transport.request(
            FILES_API,
            FILES_VERSION,
            "move",
            files=[to_file_identifier_value(node_id)],
            to_parent_folder=to_parent_parameter_value(new_parent_path),
            conflict_action="stop",
        )
        await self.wait_task(data["async_task_id"])

    async def delete(self, node_id: SynologyNodeRef) -> None:
        data: SynologyAsyncTaskResponse = await self._transport.request(
            FILES_API,
            FILES_VERSION,
            "delete",
            files=[to_file_identifier_value(node_id)],
        )
        await self.wait_task(data["async_task_id"])

    async def wait_task(self, task_id: str) -> None:
        for delay in TASK_POLL_DELAYS:
            await asyncio.sleep(delay)
            data: SynologyTaskInfo = await self._transport.request(
                TASKS_API,
                TASKS_VERSION,
                "get",
                task_id=task_id,
            )
            if data["status"] != "finished":
                continue
            result = data.get("result")
            errors = result["errors"] if result else []
            if errors:
                code = errors[0]["code"]
                message = errors[0].get("message", "task failed")
                raise SynologyApiError(message, error_code=code, payload=data)
            return
        raise SynologyApiError(f"Task {task_id!r} did not finish in time")

    async def upload(
        self,
        parent_path: SynologyParentRef,
        name: str,
        data: AsyncIterable[bytes],
        *,
        mime_type: str | None = None,
    ) -> SynologyFileInfo:
        name = unicodedata.normalize("NFC", name)
        try:
            result: SynologyFileInfo = await self._transport.upload(
                FILES_API,
                FILES_VERSION,
                "upload",
                form_fields={
                    "path": f"{to_parent_parameter_value(parent_path)}/{name}",
                    "type": "file",
                    "conflict_action": "stop",
                },
                file_name=name,
                file_data=data,
                mime_type=mime_type or "application/octet-stream",
            )
        except SynologyApiError as exc:
            if exc.error_code == 1022:
                raise SynologyUploadConflictError(
                    f"Upload conflict for {name!r}",
                    file_name=name,
                ) from exc
            if exc.error_code == 1035:
                raise SynologyNameTooLongError(
                    f"File name is too long for Synology Drive: {name!r}",
                    file_name=name,
                ) from exc
            raise SynologyUploadError(
                f"Upload failed for {name!r}: {exc}",
                file_name=name,
            ) from exc
        except SynologyNetworkError as exc:
            raise SynologyNetworkError(
                f"Upload failed for {name!r}: {exc}",
                original_error=exc,
            ) from exc
        return result

    def download(
        self,
        node_id: SynologyNodeRef,
        *,
        range_: slice | None = None,
    ) -> AbstractAsyncContextManager[ClientResponse]:
        return _download(
            transport=self._transport,
            node_id=node_id,
            range_=range_,
        )

    async def list_webhooks(self, *, app_id: str) -> list[SynologyWebhookInfo]:
        data: SynologyWebhookListResponse = await self._transport.request(
            WEBHOOKS_API,
            WEBHOOKS_VERSION,
            "list",
            app_id=app_id,
        )
        return data["items"]

    async def create_webhook(self, *, url: str, app_id: str) -> str:
        data: SynologyWebhookCreateResponse = await self._transport.request(
            WEBHOOKS_API,
            WEBHOOKS_VERSION,
            "create",
            type="url",
            url=url,
            app_id=app_id,
        )
        return data["webhook_id"]

    async def delete_webhook(self, *, webhook_id: str, app_id: str) -> None:
        await self._transport.request(
            WEBHOOKS_API,
            WEBHOOKS_VERSION,
            "delete",
            webhook_id=webhook_id,
            app_id=app_id,
        )


@asynccontextmanager
async def _download(
    *,
    transport: SynologyTransport,
    node_id: SynologyNodeRef,
    range_: slice | None,
) -> AsyncGenerator[ClientResponse]:
    extra_headers: dict[str, str] | None = None
    if range_:
        start = range_.start or 0
        end = "" if range_.stop is None else f"-{range_.stop - 1}"
        extra_headers = {"Range": f"bytes={start}{end}"}
    async with transport.download(
        FILES_API,
        FILES_VERSION,
        "download",
        extra_headers=extra_headers,
        files=[to_file_identifier_value(node_id)],
        force_download=True,
    ) as response:
        yield response


@asynccontextmanager
async def create_client(
    *,
    base_url: str,
    username: str,
    password: str,
    otp_code: str | None = None,
) -> AsyncGenerator[SynologyClient]:
    async with create_transport(
        base_url=base_url,
        username=username,
        password=password,
        otp_code=otp_code,
    ) as transport:
        yield SynologyClient(transport=transport)
