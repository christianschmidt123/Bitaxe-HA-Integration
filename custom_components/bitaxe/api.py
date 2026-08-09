from __future__ import annotations

from typing import Any
import logging

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


async def fetch_bitaxe_data(hass, url: str) -> dict[str, Any]:
    """Fetch JSON data using the Home Assistant session."""
    session = async_get_clientsession(hass)

    try:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientError as e:
        _LOGGER.error("Client error occurred while fetching %s: %s", url, e)
    except Exception as e:
        _LOGGER.error("Unexpected error occurred while fetching %s: %s", url, e)

    return {}


async def download_binary(hass, url: str) -> bytes:
    """Download a binary asset using the Home Assistant session."""
    session = async_get_clientsession(hass)

    try:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()
    except aiohttp.ClientError as e:
        _LOGGER.error("Client error occurred while downloading %s: %s", url, e)
        raise


async def upload_binary(hass, url: str, payload: bytes) -> str:
    """Upload a binary payload using the Home Assistant session."""
    session = async_get_clientsession(hass)

    try:
        async with session.post(
            url,
            data=payload,
            headers={"Content-Type": "application/octet-stream"},
        ) as response:
            response.raise_for_status()
            return await response.text()
    except aiohttp.ClientError as e:
        _LOGGER.error("Client error occurred while uploading to %s: %s", url, e)
        raise
