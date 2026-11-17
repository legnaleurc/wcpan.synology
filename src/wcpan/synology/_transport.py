import asyncio
import json
import secrets
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any, cast

from aiohttp import ClientError, ClientResponse, ClientResponseError, ClientSession

from ._diagnostics import log_invalid_response, log_response
from ._errors import response_object
from ._redact import redact
from ._secret import Secret
from ._upload import UploadSource
from .exceptions import (
    SynologyApiError,
    SynologyAuthenticationError,
    SynologyNetworkError,
    SynologyProtocolError,
    SynologyTransportError,
)


def encode_rpc_value(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def network_error(exc: Exception, operation: str) -> SynologyNetworkError:
    status = (exc.status or None) if isinstance(exc, ClientResponseError) else None
    reason = f"HTTP {status}" if status is not None else type(exc).__name__
    return SynologyNetworkError(
        f"{operation} failed: {reason}",
        SynologyTransportError(exc),
        operation=operation,
        http_status=status,
    )


async def check_http_status(response: ClientResponse, operation: str) -> None:
    # Read an error body before raise_for_status() can release the connection.
    parsed: Any = None
    if response.status >= 400:
        try:
            parsed = await response.json(content_type=None)
        except (ValueError, ClientError, OSError, asyncio.TimeoutError):
            log_invalid_response(operation)
        else:
            log_response(operation, parsed)
    failure = None
    try:
        response.raise_for_status()
    except ClientResponseError as exc:
        failure = network_error(exc, operation)
        if isinstance(parsed, dict):
            details = cast(dict[str, Any], parsed).get("error")
            if isinstance(details, dict):
                failure.error = redact(details)
    if failure is not None:
        raise failure from failure.original_error


async def read_rpc_response(
    response: ClientResponse,
    operation: str,
    error_class: type[SynologyApiError] = SynologyApiError,
) -> Any:
    await check_http_status(response, operation)
    payload: Any = None
    invalid_json = False
    try:
        payload = await response.json(content_type=None)
    except ValueError:
        invalid_json = True
    # Raise outside the parser's handler: its exception may retain the full body.
    if invalid_json:
        log_invalid_response(operation)
        raise SynologyProtocolError(
            f"{operation} returned invalid JSON",
            operation=operation,
            http_status=response.status,
        )
    log_response(operation, payload)
    if not isinstance(payload, dict):
        raise SynologyProtocolError(
            f"{operation} returned an invalid envelope",
            operation=operation,
            http_status=response.status,
        )
    payload = cast(dict[str, Any], payload)
    if type(payload.get("success")) is not bool:
        raise SynologyProtocolError(
            f"{operation} returned an invalid envelope",
            operation=operation,
            http_status=response.status,
        )
    if not payload["success"]:
        error = payload.get("error")
        if not isinstance(error, dict):
            raise SynologyProtocolError(
                f"{operation} returned an invalid error",
                operation=operation,
                http_status=response.status,
            )
        error = cast(dict[str, Any], error)
        if type(error.get("code")) is not int:
            raise SynologyProtocolError(
                f"{operation} returned an invalid error",
                operation=operation,
                http_status=response.status,
            )
        code = error["code"]
        raise error_class(
            f"{operation} failed with code {code}",
            error_code=code,
            error=error,
            operation=operation,
            http_status=response.status,
        )
    return payload.get("data")


async def login(
    session: ClientSession,
    *,
    base_url: str,
    username: str,
    password: str | Secret,
    otp_code: str | Secret | None = None,
) -> Secret:
    password_secret = password if isinstance(password, Secret) else Secret(password)
    otp_secret = (
        (otp_code if isinstance(otp_code, Secret) else Secret(otp_code))
        if otp_code
        else None
    )
    params = {
        "api": "SYNO.API.Auth",
        "version": "3",
        "method": "login",
        "account": username,
        "passwd": password_secret.reveal(),
        "session": "Drive",
        "format": "sid",
    }
    if otp_code:
        params["otp_code"] = otp_secret.reveal() if otp_secret else ""
    data: Any = None
    try:
        async with session.get(
            f"{base_url}/webapi/auth.cgi",
            params=params,
        ) as response:
            data = await read_rpc_response(
                response, "SYNO.API.Auth.login", SynologyAuthenticationError
            )
    except (ClientError, asyncio.TimeoutError, OSError) as exc:
        failure = network_error(exc, "SYNO.API.Auth.login")
    else:
        failure = None
    if failure is not None:
        raise failure from failure.original_error
    data = response_object(data, "Invalid login response")
    sid = data.get("sid")
    if not isinstance(sid, str) or not sid:
        raise SynologyProtocolError(
            "No session token in response", operation="SYNO.API.Auth.login"
        )
    return Secret(sid)


async def logout(session: ClientSession, *, base_url: str, sid: Secret) -> None:
    params = {
        "api": "SYNO.API.Auth",
        "version": "3",
        "method": "logout",
        "session": "Drive",
        "_sid": sid.reveal(),
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
        sid: str | Secret,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._sid = sid if isinstance(sid, Secret) else Secret(sid)

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
            "_sid": self._sid.reveal(),
        }
        for key, value in params.items():
            query[key] = encode_rpc_value(value)
        failure = None
        try:
            async with self._session.get(
                f"{self._base_url}/webapi/entry.cgi",
                params=query,
            ) as response:
                return await read_rpc_response(response, f"{api}.{method}")
        except (ClientError, asyncio.TimeoutError, OSError) as exc:
            failure = network_error(exc, f"{api}.{method}")
        raise failure from failure.original_error

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
            "_sid": self._sid.reveal(),
        }
        for key, value in params.items():
            query[key] = encode_rpc_value(value)
        response: ClientResponse | None = None
        try:
            failure = None
            try:
                response = await self._session.get(
                    f"{self._base_url}/webapi/entry.cgi",
                    params=query,
                    headers=extra_headers or {},
                )
                await check_http_status(response, f"{api}.{method}")
            except (ClientError, asyncio.TimeoutError, OSError) as exc:
                failure = network_error(exc, f"{api}.{method}")
            if failure is not None:
                raise failure from failure.original_error
            assert response is not None
            yield response
        finally:
            if response is not None:
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
            "_sid": self._sid.reveal(),
        }
        async with UploadSource(file_data) as source:
            content_type, body = build_multipart_body(
                form_fields=form_fields,
                file_name=file_name,
                file_data=source,
                file_content_type=mime_type,
            )
            result: Any = None
            failure = None
            try:
                async with self._session.post(
                    f"{self._base_url}/webapi/entry.cgi",
                    params=query,
                    headers={"Content-Type": content_type},
                    data=body,
                ) as response:
                    result = await read_rpc_response(response, f"{api}.{method}")
            except Exception as exc:
                if source.error is None:
                    if isinstance(exc, (ClientError, asyncio.TimeoutError, OSError)):
                        failure = network_error(exc, f"{api}.{method}")
                    else:
                        raise
            # Re-raise outside the handler to retain an explicit source cause.
            if source.error is not None:
                raise source.error
            if failure is not None:
                raise failure from failure.original_error
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
    password_secret = Secret(password)
    otp_secret = Secret(otp_code) if otp_code else None
    async with ClientSession() as session:
        sid = await login(
            session,
            base_url=base_url.rstrip("/"),
            username=username,
            password=password_secret,
            otp_code=otp_secret,
        )
        try:
            yield SynologyTransport(
                session=session,
                base_url=base_url,
                sid=sid,
            )
        finally:
            await logout(session, base_url=base_url.rstrip("/"), sid=sid)
