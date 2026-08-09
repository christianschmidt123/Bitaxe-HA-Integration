import asyncio
import logging

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

_LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


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
