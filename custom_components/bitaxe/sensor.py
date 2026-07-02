import logging
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfInformation,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bitaxe"

SENSOR_NAME_MAP = {
    "power": "Power Consumption",
    "voltage": "Input Voltage",
    "current": "Input Current",
    "temp": "Temperature ASIC",
    "temp2": "Temperature 2",
    "vrTemp": "Temperature VR",
    "coreVoltageActual": "Core Voltage Actual",
    "actualFrequency": "Actual Frequency",
    "expectedHashrate": "Expected Hash Rate",
    "fanspeed": "Fan Speed",
    "fanrpm": "Fan RPM",
    "fan2rpm": "Fan 2 RPM",
    "hashRate": "Hash Rate",
    "hashRate_1m": "Hash Rate (1m)",
    "hashRate_10m": "Hash Rate (10m)",
    "hashRate_1h": "Hash Rate (1h)",
    "errorPercentage": "ASIC Error Rate",
    "sharesAccepted": "Shares Accepted",
    "sharesRejected": "Shares Rejected",
    "bestDiff": "All-Time Best Difficulty",
    "bestSessionDiff": "Best Difficulty Since System Boot",
    "poolDifficulty": "Pool Difficulty",
    "responseTime": "Pool Response Time",
    "processTime": "Pool Process Time",
    "uptimeSeconds": "Uptime",
    "wifiRSSI": "Wi-Fi RSSI",
    "freeHeap": "Free Heap Memory",
    "cpuUsage": "CPU Usage",
    "blockHeight": "Current Block Height",
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up all BitAxe sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.unique_id]["coordinator"]
    device_name = entry.data.get("device_name", "BitAxe Miner")

    _LOGGER.debug(f"Setting up all sensors for device: {device_name}")

    sensors = [
        BitAxeSensor(coordinator, sensor_type, device_name, entry)
        for sensor_type in SENSOR_NAME_MAP.keys()
    ]

    async_add_entities(sensors, update_before_add=True)


class BitAxeSensor(SensorEntity):
    """Representation of a BitAxe sensor using modern SensorEntity."""

    def __init__(self, coordinator: DataUpdateCoordinator, sensor_type: str, device_name: str, entry):
        super().__init__()
        self.coordinator = coordinator
        self.sensor_type = sensor_type
        self.entry = entry
        self._device_name = device_name

        self._attr_name = f"{SENSOR_NAME_MAP.get(sensor_type, sensor_type)} ({device_name})"
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        self._attr_icon = self._get_icon(sensor_type)
        
        self._set_device_and_state_classes()

        _LOGGER.debug(f"Initialized BitAxeSensor: {self._attr_name} (ID: {self._attr_unique_id})")

    @property
    def device_info(self):
        """Group all sensors under one device."""
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": self._device_name,
            "manufacturer": "Open Source Hardware",
            "model": "BitAxe Miner",
            "via_device": None,
        }

    @property
    def native_value(self):
        """Return the state of the sensor with noise reduction."""
        value = self.coordinator.data.get(self.sensor_type, None)

        if value is None:
            return None

        # 1. Rauschunterdrückung für den RAM (Konvertierung in MB, gerundet)
        if self.sensor_type == "freeHeap":
            return round(float(value) / (1024 * 1024), 2)

        # 2. Schwierigkeitsgrade als reine Zahlen ausgeben (HA formatiert das k, M, G im Dashboard selbst!)
        if self.sensor_type in ["bestDiff", "bestSessionDiff", "poolDifficulty"]:
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return value

        # 3. Uptime lesbar halten
        if self.sensor_type == "uptimeSeconds":
            return self._format_uptime(value)

        # 4. Beruhigung von Leistung und Lüftern (1 Dezimalstelle reicht)
        if self.sensor_type in ["power", "fanspeed", "cpuUsage"]:
            return round(float(value), 1)

        # 5. Spannungen von mV in V umrechnen
        if self.sensor_type in ["voltage", "coreVoltageActual"]:
            return round(float(value) / 1000.0, 2) if float(value) > 100 else round(float(value), 2)

        # 6. Stromstärke von mA in A umrechnen
        if self.sensor_type == "current":
            return round(float(value) / 1000.0, 2)

        # 7. Hashrates glätten
        if self.sensor_type in ["hashRate", "hashRate_1m", "hashRate_10m", "hashRate_1h", "expectedHashrate"]:
            return round(float(value), 1)

        if self.sensor_type in ["responseTime", "processTime"]:
            return round(float(value), 0)

        return value

    @staticmethod
    def _format_uptime(seconds):
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m {seconds}s"

    def _set_device_and_state_classes(self):
        """Assign native Home Assistant Device and State Classes."""
        # Standard Zuweisungen für Diagramme und Statistik-Minderung
        if self.sensor_type == "power":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
        elif self.sensor_type in ["voltage", "coreVoltageActual"]:
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        elif self.sensor_type == "current":
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        elif self.sensor_type in ["temp", "temp2", "vrTemp"]:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif self.sensor_type in ["fanspeed", "cpuUsage", "errorPercentage"]:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = PERCENTAGE
        elif self.sensor_type == "wifiRSSI":
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
        elif self.sensor_type == "uptimeSeconds":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        elif self.sensor_type in ["responseTime", "processTime"]:
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
        
        # Speicher korrigiert auf Megabytes (reduziert Log-Spam enorm)
        elif self.sensor_type == "freeHeap":
            self._attr_device_class = SensorDeviceClass.DATA_SIZE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES

        # Hashrates & Frequenzen
        elif self.sensor_type in ["hashRate", "hashRate_1m", "hashRate_10m", "hashRate_1h", "expectedHashrate"]:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = "GH/s"
        elif self.sensor_type == "actualFrequency":
            self._attr_device_class = SensorDeviceClass.FREQUENCY
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfFrequency.MEGAHERTZ
        elif self.sensor_type in ["fanrpm", "fan2rpm"]:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = "RPM"
        
        # Shares steigen immer weiter an
        elif self.sensor_type in ["sharesAccepted", "sharesRejected"]:
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    def _get_icon(self, sensor_type):
        """Select crisp Material Design Icons for the entities."""
        if sensor_type == "bestSessionDiff":
            return "mdi:star"
        elif sensor_type in ["bestDiff", "poolDifficulty"]:
            return "mdi:trophy"
        elif sensor_type in ["fanspeed", "fanrpm", "fan2rpm"]:
            return "mdi:fan"
        elif sensor_type in ["hashRate", "hashRate_1m", "hashRate_10m", "hashRate_1h", "expectedHashrate"]:
            return "mdi:speedometer"
        elif sensor_type == "power":
            return "mdi:flash"
        elif sensor_type in ["voltage", "coreVoltageActual"]:
            return "mdi:sine-wave"
        elif sensor_type == "current":
            return "mdi:amperage"
        elif sensor_type == "sharesAccepted":
            return "mdi:share"
        elif sensor_type == "sharesRejected":
            return "mdi:share-off"
        elif sensor_type in ["temp", "temp2", "vrTemp"]:
            return "mdi:thermometer"
        elif sensor_type == "uptimeSeconds":
            return "mdi:clock"
        elif sensor_type == "errorPercentage":
            return "mdi:alert-circle-outline"
        elif sensor_type == "wifiRSSI":
            return "mdi:wifi"
        elif sensor_type == "freeHeap":
            return "mdi:memory"
        elif sensor_type == "cpuUsage":
            return "mdi:cpu-64-bit"
        elif sensor_type == "actualFrequency":
            return "mdi:sine-wave"
        elif sensor_type == "blockHeight":
            return "mdi:cube-outline"
        return "mdi:help-circle"
