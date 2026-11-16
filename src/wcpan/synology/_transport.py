import asyncio
import json
import secrets
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

from ._errors import response_object
from ._upload import UploadSource
from .exceptions import (
    SynologyApiError,
    SynologyAuthenticationError,
    SynologyNetworkError,
    SynologyProtocolError,
)


def encode_rpc_value(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


async def read_rpc_response(
    response: ClientResponse,
    operation: str,
    error_class: type[SynologyApiError] = SynologyApiError,
) -> Any:
    try:
        payload = await response.json(content_type=None)
    except ValueError as exc:
        raise SynologyProtocolError(
            f"{operation} returned invalid JSON",
            payload=await response.text(errors="replace"),
        ) from exc
    payload = response_object(payload, f"{operation} returned an invalid envelope")
    if type(payload.get("success")) is not bool:
        raise SynologyProtocolError(
            f"{operation} returned an invalid envelope", payload=payload
        )
    if not payload["success"]:
        error = response_object(
            payload.get("error"), f"{operation} returned an invalid error"
        )
        if type(error.get("code")) is not int:
            raise SynologyProtocolError(
                f"{operation} returned an invalid error", payload=payload
            )
        code = error["code"]
        raise error_class(
            f"{operation} failed with code {code}", error_code=code, payload=payload
        )
    return payload.get("data")


async def login(
    session: ClientSession,
    *,
    base_url: str,
    username: str,
    password: str,
    otp_code: str | None = None,
) -> str:
    params = {
        "api": "SYNO.API.Auth",
        "version": "3",
        "method": "login",
        "account": username,
        "passwd": password,
        "session": "Drive",
        "format": "sid",
    }
    if otp_code:
        params["otp_code"] = otp_code
    try:
        async with session.get(
            f"{base_url}/webapi/auth.cgi",
            params=params,
        ) as response:
            response.raise_for_status()
            data = await read_rpc_response(
                response, "Login", SynologyAuthenticationError
            )
    except (ClientError, asyncio.TimeoutError, OSError) as exc:
        raise SynologyNetworkError(str(exc), exc) from exc
    data = response_object(data, "Invalid login response")
    sid = data.get("sid")
    if not isinstance(sid, str) or not sid:
        raise SynologyProtocolError("No session token in response", payload=data)
    return sid


async def logout(session: ClientSession, *, base_url: str, sid: str) -> None:
    params = {
        "api": "SYNO.API.Auth",
        "version": "3",
        "method": "logout",
        "session": "Drive",
        "_sid": sid,
    }
    with suppress(Exception):
        async with session.get(f"{base_url}/webapi/auth.cgi", params=params):
            pass


class SynologyTransport:
    def __init__(
        self,
        *,
        session: ClientSession,
        base_url: str,
        sid: str,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._sid = sid

    async def request(
        self,
        api: str,
        version: int,
        method: str,
        **params: Any,
    ) -> Any:
        query = {
            "api": api,
            "version": str(version),
            "method": method,
            "_sid": self._sid,
        }
        for key, value in params.items():
            query[key] = encode_rpc_value(value)
        try:
            async with self._session.get(
                f"{self._base_url}/webapi/entry.cgi",
                params=query,
            ) as response:
                response.raise_for_status()
                return await read_rpc_response(response, f"{api}.{method}")
        except (ClientError, asyncio.TimeoutError, OSError) as exc:
            raise SynologyNetworkError(str(exc), exc) from exc

    @asynccontextmanager
    async def download(
        self,
        api: str,
        version: int,
        method: str,
        *,
        extra_headers: dict[str, str] | None = None,
        **params: Any,
    ) -> AsyncGenerator[ClientResponse]:
        query = {
            "api": api,
            "version": str(version),
            "method": method,
            "_sid": self._sid,
        }
        for key, value in params.items():
            query[key] = encode_rpc_value(value)
        try:
            response = await self._session.get(
                f"{self._base_url}/webapi/entry.cgi",
                params=query,
                headers=extra_headers or {},
            )
            response.raise_for_status()
        except (ClientError, asyncio.TimeoutError, OSError) as exc:
            raise SynologyNetworkError(str(exc), exc) from exc
        try:
            yield response
        finally:
            response.release()
            await response.wait_for_close()

    async def upload(
        self,
        api: str,
        version: int,
        method: str,
        *,
        form_fields: dict[str, object],
        file_name: str,
        file_data: AsyncIterable[bytes],
        mime_type: str,
    ) -> Any:
        query = {
            "api": api,
            "version": str(version),
            "method": method,
            "_sid": self._sid,
        }
        async with UploadSource(file_data) as source:
            content_type, body = build_multipart_body(
                form_fields=form_fields,
                file_name=file_name,
                file_data=source,
                file_content_type=mime_type,
            )
            result: Any = None
            try:
                async with self._session.post(
                    f"{self._base_url}/webapi/entry.cgi",
                    params=query,
                    headers={"Content-Type": content_type},
                    data=body,
                ) as response:
                    response.raise_for_status()
                    result = await read_rpc_response(response, f"{api}.{method}")
            except Exception as exc:
                if source.error is None:
                    if isinstance(exc, (ClientError, asyncio.TimeoutError, OSError)):
                        raise SynologyNetworkError(str(exc), exc) from exc
                    raise
            # Re-raise outside the handler to retain an explicit source cause.
            if source.error is not None:
                raise source.error
            return result


def build_multipart_body(
    *,
    form_fields: dict[str, object],
    file_name: str,
    file_data: AsyncIterable[bytes],
    file_content_type: str,
) -> tuple[str, AsyncIterator[bytes]]:
    boundary = secrets.token_hex(16)
    content_type = f"multipart/form-data; boundary={boundary}"
    boundary_bytes = boundary.encode()

    async def generator() -> AsyncIterator[bytes]:
        for key, value in form_fields.items():
            if isinstance(value, bool):
                encoded = "true" if value else "false"
            elif isinstance(value, (dict, list)):
                encoded = encode_rpc_value(value)
            else:
                encoded = str(value)
            yield (
                b"--" + boundary_bytes + b"\r\n"
                b'Content-Disposition: form-data; name="' + key.encode() + b'"\r\n'
                b"\r\n" + encoded.encode() + b"\r\n"
            )
        yield (
            b"--" + boundary_bytes + b"\r\n"
            b'Content-Disposition: form-data; name="file"; filename="'
            + file_name.encode()
            + b'"\r\n'
            b"Content-Type: " + file_content_type.encode() + b"\r\n"
            b"\r\n"
        )
        async for chunk in file_data:
            yield chunk
        yield b"\r\n--" + boundary_bytes + b"--\r\n"

    return content_type, generator()


@asynccontextmanager
async def create_transport(
    *,
    base_url: str,
    username: str,
    password: str,
    otp_code: str | None = None,
) -> AsyncGenerator[SynologyTransport]:
    async with ClientSession() as session:
        sid = await login(
            session,
            base_url=base_url.rstrip("/"),
            username=username,
            password=password,
            otp_code=otp_code,
        )
        try:
            yield SynologyTransport(
                session=session,
                base_url=base_url,
                sid=sid,
            )
        finally:
            await logout(session, base_url=base_url.rstrip("/"), sid=sid)
