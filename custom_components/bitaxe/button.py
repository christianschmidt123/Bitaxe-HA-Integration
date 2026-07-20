import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .benchmark import run_bitaxe_benchmark, load_benchmark_status, cancel_benchmark

_LOGGER = logging.getLogger(__name__)
DOMAIN = "bitaxe"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    device_name = entry.data.get("device_name", "BitAxe Miner")
    
    async_add_entities([
        BitaxeBenchmarkButton(hass, entry, device_name, max_power=30, label="Benchmark (30W Netzteil)"),
        BitaxeBenchmarkButton(hass, entry, device_name, max_power=40, label="Benchmark (40W Netzteil)"),
        BitaxeCancelButton(hass, entry, device_name),
    ], True)


class BitaxeBenchmarkButton(ButtonEntity):
    """Button zum Starten des Benchmarks mit definiertem Watt-Limit."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_name: str, max_power: int, label: str) -> None:
        self.hass = hass
        self.entry = entry
        self._device_name = device_name
        self._max_power = max_power
        
        self._attr_name = f"{label} ({device_name})"
        self._attr_unique_id = f"{entry.entry_id}_benchmark_button_{max_power}w"
        self._attr_icon = "mdi:play-circle-outline"

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self.entry.entry_id)}, "name": self._device_name}

    async def async_press(self) -> None:
        status = load_benchmark_status(self.hass, self.entry.entry_id)
        if status and status.get("is_running"):
            _LOGGER.warning("Benchmark läuft bereits für diesen Bitaxe.")
            return

        _LOGGER.info(f"Starte Bitaxe Benchmark mit {self._max_power}W Limit im Hintergrund...")
        
        self.hass.async_add_executor_job(
            run_bitaxe_benchmark,
            self.hass,
            self.entry.entry_id,
            self.entry.data["ip_address"],
            self._max_power
        )


class BitaxeCancelButton(ButtonEntity):
    """Button zum sofortigen Abbrechen eines laufenden Benchmarks."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_name: str) -> None:
        self.hass = hass
        self.entry = entry
        self._device_name = device_name
        
        self._attr_name = f"Benchmark Abbrechen ({device_name})"
        self._attr_unique_id = f"{entry.entry_id}_benchmark_cancel_button"
        self._attr_icon = "mdi:stop-circle-outline"

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self.entry.entry_id)}, "name": self._device_name}

    async def async_press(self) -> None:
        status = load_benchmark_status(self.hass, self.entry.entry_id)
        if not status or not status.get("is_running"):
            _LOGGER.info("Es läuft aktuell kein Benchmark, der abgebrochen werden könnte.")
            return

        _LOGGER.info("Abbruch-Signal für Bitaxe Benchmark wird gesendet...")
        cancel_benchmark(self.hass, self.entry.entry_id)
