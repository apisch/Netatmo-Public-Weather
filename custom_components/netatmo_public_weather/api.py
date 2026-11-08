"""Minimal async client for the Netatmo public weather API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Any

import aiohttp

from .const import API_PUBLIC_DATA
from .geo import BBox

_LOGGER = logging.getLogger(__name__)

# Netatmo API error codes, see https://dev.netatmo.com/apidocumentation
_AUTH_CODES = frozenset({2, 3, 13})  # invalid token, expired token, bad scope
_RATE_CODES = frozenset({26})  # user usage reached
REQUEST_TIMEOUT = 30


class NetatmoApiError(Exception):
    """Generic API failure (retry later)."""


class NetatmoAuthError(NetatmoApiError):
    """The token is invalid or lacks the scope; user must re-authenticate."""


class NetatmoRateLimitError(NetatmoApiError):
    """Netatmo rejected the call because of its rate limit."""


TokenGetter = Callable[[], Awaitable[str]]


class NetatmoPublicClient:
    """Fetch public station data inside a bounding box."""

    def __init__(self, websession: aiohttp.ClientSession, get_token: TokenGetter) -> None:
        """Initialize with a session and a coroutine returning a valid token."""
        self._websession = websession
        self._get_token = get_token
        self.last_body: list[dict[str, Any]] | None = None

    async def async_get_public_data(self, bbox: BBox) -> list[dict[str, Any]]:
        """Return the raw station list for the given box."""
        token = await self._get_token()
        params = {
            "lat_ne": f"{bbox.lat_ne:.6f}",
            "lon_ne": f"{bbox.lon_ne:.6f}",
            "lat_sw": f"{bbox.lat_sw:.6f}",
            "lon_sw": f"{bbox.lon_sw:.6f}",
            "filter": "false",
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._websession.post(
                    API_PUBLIC_DATA,
                    data=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
                status = resp.status
                try:
                    payload: Any = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    payload = None
        except (TimeoutError, aiohttp.ClientError) as err:
            raise NetatmoApiError(f"Cannot reach Netatmo: {err}") from err

        _raise_for_error(status, payload)
        body = payload.get("body") if isinstance(payload, dict) else None
        if not isinstance(body, list):
            raise NetatmoApiError("Unexpected response from Netatmo")
        self.last_body = body
        return body


def _raise_for_error(status: int, payload: Any) -> None:
    error = payload.get("error") if isinstance(payload, dict) else None
    code: int | None = None
    message = ""
    if isinstance(error, dict):
        code = error.get("code") if isinstance(error.get("code"), int) else None
        message = str(error.get("message", ""))
    elif isinstance(error, str):
        message = error

    if status == 429 or code in _RATE_CODES:
        raise NetatmoRateLimitError(message or "rate limit reached")
    if status in (401, 403) or code in _AUTH_CODES or message == "invalid_token":
        raise NetatmoAuthError(message or f"HTTP {status}")
    if status >= 400 or error is not None:
        raise NetatmoApiError(message or f"HTTP {status}")
