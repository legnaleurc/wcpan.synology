import asyncio
import unicodedata
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, cast

from aiohttp import ClientResponse

from ._errors import file_error, response_field, response_object, upload_error
from ._transport import SynologyTransport
from ._types import (
    to_file_identifier_value,
    to_parent_parameter_value,
    to_path_parameter_value,
)
from ._upload import UploadSource
from .exceptions import (
    SynologyApiError,
    SynologyNetworkError,
    SynologyProtocolError,
    SynologyUploadConflictError,
    SynologyUploadNameTooLongError,
)
from .types import (
    JsonValue,
    SynologyAsyncTaskResponse,
    SynologyClient,
    SynologyFileInfo,
    SynologyFileListResponse,
    SynologyLookupRef,
    SynologyNodeRef,
    SynologyParentRef,
    SynologyWebhookCreateResponse,
    SynologyWebhookInfo,
    SynologyWebhookListResponse,
)


FILES_API = "SYNO.SynologyDrive.Files"
FILES_VERSION = 11
TASKS_API = "SYNO.SynologyDrive.Tasks"
TASKS_VERSION = 1
WEBHOOKS_API = "SYNO.SynologyDrive.Webhooks"
WEBHOOKS_VERSION = 2
TASK_POLL_DELAYS = [0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


class DefaultSynologyClient(SynologyClient):  # pyright: ignore[reportUnusedClass]
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

    def stream_call(
        self,
        *,
        api: str,
        version: int,
        method: str,
        extra_headers: dict[str, str] | None = None,
        **params: JsonValue,
    ) -> AbstractAsyncContextManager[ClientResponse]:
        """Stream a raw RPC response without interpreting its contents."""
        return self._transport.download(
            api, version, method, extra_headers=extra_headers, **params
        )

    async def _request(self, api: str, version: int, method: str, **params: Any) -> Any:
        try:
            data = await self._transport.request(api, version, method, **params)
        except SynologyApiError as exc:
            if api != FILES_API:
                raise
            mapped = file_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc
        if api == WEBHOOKS_API and method == "delete":
            return data
        return response_object(
            data, f"{api}.{method} returned no object", operation=f"{api}.{method}"
        )

    async def get_file(self, path: SynologyLookupRef) -> SynologyFileInfo:
        data = await self._request(
            FILES_API,
            FILES_VERSION,
            "get",
            path=to_path_parameter_value(path),
        )
        return cast(
            SynologyFileInfo, response_object(data, "Files.get returned no file object")
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
        data: SynologyFileListResponse = await self._request(
            FILES_API,
            FILES_VERSION,
            "list",
            path=to_path_parameter_value(path),
            sort_by=sort_by,
            sort_direction=sort_direction,
            offset=offset,
            limit=limit,
        )
        return response_field(data, "items", list), response_field(data, "total", int)

    async def create_folder(
        self,
        parent_path: SynologyParentRef,
        name: str,
    ) -> SynologyFileInfo:
        name = unicodedata.normalize("NFC", name)
        try:
            data: SynologyFileInfo = await self._request(
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
                    error_code=exc.error_code,
                    error=exc.error,
                    operation=exc.operation,
                    http_status=exc.http_status,
                ) from (exc.__cause__ or exc)
            if exc.error_code == 1035:
                raise SynologyUploadNameTooLongError(
                    f"File name is too long for Synology Drive: {name!r}",
                    file_name=name,
                    error_code=exc.error_code,
                    error=exc.error,
                    operation=exc.operation,
                    http_status=exc.http_status,
                ) from (exc.__cause__ or exc)
            raise
        return data

    async def rename(
        self,
        path: SynologyLookupRef,
        new_name: str,
    ) -> SynologyFileInfo:
        new_name = unicodedata.normalize("NFC", new_name)
        try:
            data: SynologyFileInfo = await self._request(
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
                    error_code=exc.error_code,
                    error=exc.error,
                    operation=exc.operation,
                    http_status=exc.http_status,
                ) from (exc.__cause__ or exc)
            if exc.error_code == 1035:
                raise SynologyUploadNameTooLongError(
                    f"File name is too long for Synology Drive: {new_name!r}",
                    file_name=new_name,
                    error_code=exc.error_code,
                    error=exc.error,
                    operation=exc.operation,
                    http_status=exc.http_status,
                ) from (exc.__cause__ or exc)
            raise
        return data

    async def move(
        self,
        node_id: SynologyNodeRef,
        new_parent_path: SynologyParentRef,
    ) -> None:
        data: SynologyAsyncTaskResponse = await self._request(
            FILES_API,
            FILES_VERSION,
            "move",
            files=[to_file_identifier_value(node_id)],
            to_parent_folder=to_parent_parameter_value(new_parent_path),
            conflict_action="stop",
        )
        await self.wait_task(response_field(data, "async_task_id", str))

    async def delete(self, node_id: SynologyNodeRef) -> None:
        data: SynologyAsyncTaskResponse = await self._request(
            FILES_API,
            FILES_VERSION,
            "delete",
            files=[to_file_identifier_value(node_id)],
        )
        await self.wait_task(response_field(data, "async_task_id", str))

    async def wait_task(self, task_id: str) -> None:
        """Wait for a Files operation; failures retain the first parsed task error."""
        for delay in TASK_POLL_DELAYS:
            await asyncio.sleep(delay)
            data = response_object(
                await self._request(
                    TASKS_API,
                    TASKS_VERSION,
                    "get",
                    task_id=task_id,
                ),
                "Invalid task response",
                operation=f"{TASKS_API}.get",
            )
            if not isinstance(data.get("status"), str):
                raise SynologyProtocolError(
                    "Invalid task response", operation=f"{TASKS_API}.get"
                )
            if data["status"] != "finished":
                continue
            result = data.get("result")
            if result is None:
                errors = []
            else:
                result = response_object(
                    result, "Invalid task result", operation=f"{TASKS_API}.get"
                )
                if "errors" not in result:
                    raise SynologyProtocolError(
                        "Invalid task result", operation=f"{TASKS_API}.get"
                    )
                # A finished delete reports success as `null`, others as `[]`.
                reported: object = result["errors"]
                if reported is None:
                    reported = []
                if not isinstance(reported, list):
                    raise SynologyProtocolError(
                        "Invalid task result", operation=f"{TASKS_API}.get"
                    )
                errors = cast(list[Any], reported)
            for entry in errors:
                error = response_object(
                    entry, "Invalid task error", operation=f"{TASKS_API}.get"
                )
                if type(error.get("code")) is not int or (
                    "message" in error and not isinstance(error["message"], str)
                ):
                    raise SynologyProtocolError(
                        "Invalid task errors", operation=f"{TASKS_API}.get"
                    )
            if errors:
                code = errors[0]["code"]
                raw = SynologyApiError(
                    "Files task failed with code " + str(code),
                    error_code=code,
                    error=errors[0],
                    operation=f"{TASKS_API}.get",
                )
                mapped = file_error(raw)
                if mapped is raw:
                    raise raw
                raise mapped from raw
            return
        raise SynologyApiError(
            "Task did not finish in time", operation=f"{TASKS_API}.get"
        )

    async def upload(
        self,
        parent_path: SynologyParentRef,
        name: str,
        data: AsyncIterable[bytes],
        *,
        mime_type: str | None = None,
    ) -> SynologyFileInfo:
        name = unicodedata.normalize("NFC", name)
        async with UploadSource(data) as source:
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
                    file_data=source,
                    mime_type=mime_type or "application/octet-stream",
                )
                response_object(result, "Files.upload returned no file object")
            except SynologyApiError as exc:
                if exc is source.error:
                    raise
                raise upload_error(exc, name) from exc
            except SynologyNetworkError as exc:
                if exc is source.error:
                    raise
                raise SynologyNetworkError(
                    f"Upload failed for {name!r}: {exc}",
                    original_error=exc.original_error or exc,
                    operation=exc.operation,
                    http_status=exc.http_status,
                    error=exc.error,
                ) from exc
            if source.error is not None:
                raise source.error
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
        data: SynologyWebhookListResponse = await self._request(
            WEBHOOKS_API,
            WEBHOOKS_VERSION,
            "list",
            app_id=app_id,
        )
        return response_field(data, "items", list)

    async def create_webhook(self, *, url: str, app_id: str) -> str:
        data: SynologyWebhookCreateResponse = await self._request(
            WEBHOOKS_API,
            WEBHOOKS_VERSION,
            "create",
            type="url",
            url=url,
            app_id=app_id,
        )
        return response_field(data, "webhook_id", str)

    async def delete_webhook(self, *, webhook_id: str, app_id: str) -> None:
        await self._request(
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
