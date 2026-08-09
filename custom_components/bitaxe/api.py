from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

_LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
OTA_DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=300)
OTA_UPLOAD_TIMEOUT = aiohttp.ClientTimeout(total=300)
RESTART_TIMEOUT = aiohttp.ClientTimeout(total=10)


class BitAxeApiError(Exception):
    """Raised when the Bitaxe API cannot be reached."""


async def async_fetch_system_info(hass, host: str) -> dict:
    """Fetch system information from a Bitaxe device."""
    url = f"http://{host}/api/system/info"

    try:
        if hass is not None:
            session = async_get_clientsession(hass)
            async with session.get(url, timeout=REQUEST_TIMEOUT) as response:
                response.raise_for_status()
                return await response.json()

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=REQUEST_TIMEOUT) as response:
                response.raise_for_status()
                return await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        _LOGGER.debug("Failed to fetch Bitaxe system info from %s: %s", host, err)
        raise BitAxeApiError from err


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
        async with session.get(url, timeout=OTA_DOWNLOAD_TIMEOUT) as response:
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
            timeout=OTA_UPLOAD_TIMEOUT,
        ) as response:
            response.raise_for_status()
            return await response.text()
    except aiohttp.ClientError as e:
        _LOGGER.error("Client error occurred while uploading to %s: %s", url, e)
        raise


async def restart_device(hass, host: str) -> str:
    """Trigger a Bitaxe restart via API."""
    session = async_get_clientsession(hass)
    url = f"http://{host}/api/system/restart"

    try:
        async with session.post(url, timeout=RESTART_TIMEOUT) as response:
            response.raise_for_status()
            return await response.text()
    except aiohttp.ClientError as e:
        _LOGGER.error("Client error occurred while restarting %s: %s", host, e)
        raise


def get_bitaxe_device_name(system_info: dict, fallback: str = "Bitaxe Miner") -> str:
    """Return the best available device name from the Bitaxe payload."""
    return (
        str(
            system_info.get("hostname")
            or system_info.get("mdnsHostname")
            or system_info.get("fullHostname")
            or fallback
        )
        .removesuffix(".local")
        .strip()
        or fallback
    )


def get_bitaxe_unique_id(system_info: dict, fallback: str) -> str:
    """Return a stable unique ID for a Bitaxe device."""
    mac_address = system_info.get("macAddr")
    if not mac_address:
        return fallback

    try:
        return format_mac(mac_address)
    except ValueError:
        return fallback
