from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from ._client import DefaultSynologyClient
from ._transport import create_transport
from .types import SynologyClient


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
        yield DefaultSynologyClient(transport=transport)
