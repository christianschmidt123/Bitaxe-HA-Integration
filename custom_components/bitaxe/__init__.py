from datetime import timedelta
import logging
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval

from .api import async_fetch_system_info
from .benchmark import load_benchmark_status, run_bitaxe_benchmark

DOMAIN = "bitaxe"
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: config_entries.ConfigEntry):
    ip_address = entry.data["ip_address"]
    device_id = entry.unique_id or ip_address

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"BitAxe Sensor Data ({device_id})",
        update_method=lambda: fetch_bitaxe_data(hass, ip_address),
        update_interval=timedelta(seconds=30),
    )

    await coordinator.async_refresh()

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    # "button" zur Plattform-Liste hinzugefügt
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])

    async_track_time_interval(
        hass,
        _update_coordinator(coordinator),
        timedelta(seconds=30)
    )

    # AUTOMATISCHER RESUME: Prüfen, ob vor dem HA-Neustart ein Benchmark lief
    status = await hass.async_add_executor_job(load_benchmark_status, hass, entry.entry_id)
    if status and status.get("is_running"):
        _LOGGER.info(f"Unvollständigen Bitaxe Benchmark für {ip_address} erkannt. Setze im Hintergrund fort...")
        hass.async_add_executor_job(
            run_bitaxe_benchmark,
            hass,
            entry.entry_id,
            ip_address
        )

    return True

def _update_coordinator(coordinator: DataUpdateCoordinator):
    async def refresh(now):
        await coordinator.async_request_refresh()
    return refresh

async def fetch_bitaxe_data(hass: HomeAssistant, ip_address):
    try:
        data = await async_fetch_system_info(hass, ip_address)
        _LOGGER.debug("Fetched data: %s", data)
        return data
    except Exception as e:
        _LOGGER.error("Error fetching data from BitAxe API: %s", e)
        return None
