import json
import secrets
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from aiohttp import ClientResponse, ClientSession

from .errors import (
    SynologyApiError,
    SynologyAuthenticationError,
    SynologyNetworkError,
)


def encode_rpc_value(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


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
            payload = await response.json(content_type=None)
    except Exception as exc:
        raise SynologyAuthenticationError(str(exc)) from exc
    if not payload.get("success", False):
        error = payload.get("error", {})
        raise SynologyAuthenticationError(
            f"Login failed with error code {error.get('code', 'unknown')}"
        )
    sid = payload.get("data", {}).get("sid")
    if not sid:
        raise SynologyAuthenticationError("No session token in response")
    return str(sid)


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
                payload = await response.json(content_type=None)
        except SynologyApiError:
            raise
        except Exception as exc:
            raise SynologyNetworkError(str(exc), exc) from exc
        if not payload.get("success", False):
            error = payload.get("error", {})
            code = error.get("code")
            raise SynologyApiError(
                f"{api}.{method} failed with code {code}",
                error_code=code,
                payload=payload,
            )
        return payload.get("data")

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
        except Exception as exc:
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
        content_type, body = build_multipart_body(
            form_fields=form_fields,
            file_name=file_name,
            file_data=file_data,
            file_content_type=mime_type,
        )
        try:
            async with self._session.post(
                f"{self._base_url}/webapi/entry.cgi",
                params=query,
                headers={"Content-Type": content_type},
                data=body,
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except SynologyApiError:
            raise
        except Exception as exc:
            raise SynologyNetworkError(str(exc), exc) from exc
        if not payload.get("success", False):
            error = payload.get("error", {})
            code = error.get("code")
            raise SynologyApiError(
                f"{api}.{method} failed with code {code}",
                error_code=code,
                payload=payload,
            )
        return payload.get("data")


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
