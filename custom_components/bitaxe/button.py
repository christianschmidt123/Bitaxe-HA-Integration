import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .benchmark import run_bitaxe_benchmark, load_benchmark_status

_LOGGER = logging.getLogger(__name__)
DOMAIN = "bitaxe"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Setzt den Bitaxe Benchmark Button auf."""
    device_name = entry.data.get("device_name", "BitAxe Miner")
    async_add_entities([BitaxeBenchmarkButton(hass, entry, device_name)], True)

class BitaxeBenchmarkButton(ButtonEntity):
    """Button Entität für das Dashboard."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_name: str) -> None:
        self.hass = hass
        self.entry = entry
        self._device_name = device_name
        self._attr_name = f"Benchmark & Overclock ({device_name})"
        self._attr_unique_id = f"{entry.entry_id}_benchmark_button"
        self._attr_icon = "mdi:speedometer"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": self._device_name,
        }

    async def async_press(self) -> None:
        """Wird getriggert, wenn der Button gedrückt wird."""
        status = load_benchmark_status(self.hass, self.entry.entry_id)
        if status and status.get("is_running"):
            _LOGGER.warning("Benchmark läuft bereits für diesen Bitaxe.")
            return

        _LOGGER.info("Starte Bitaxe 24h Benchmark im Hintergrund...")
        
        # Startet den Executor-Thread nativ im Hintergrund (ohne HA zu blockieren)
        self.hass.async_add_executor_job(
            run_bitaxe_benchmark,
            self.hass,
            self.entry.entry_id,
            self.entry.data["ip_address"]
        )
