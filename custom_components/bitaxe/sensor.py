import logging
import re
import time
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
    UnitOfEnergy,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bitaxe"

HASHRATE_SENSOR_TYPES = ["hashRate", "hashRate_1m", "hashRate_10m", "hashRate_1h", "expectedHashrate"]
DIFFICULTY_SENSOR_TYPES = ["bestDiff", "bestSessionDiff", "poolDifficulty"]
SI_PREFIXES = {
    -1: "m",
    0: "",
    1: "k",
    2: "M",
    3: "G",
    4: "T",
    5: "P",
}
GH_TO_H_MULTIPLIER = 1_000_000_000
UPTIME_PATTERN = re.compile(
    r"(?=.*\d)\s*(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?\s*"
)

SENSOR_NAME_MAP = {
    "power": "Power Consumption",
    "energy": "Total Energy Consumed",  # NEU: Der berechnete Energiezähler für das Dashboard
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

    # Speicher für die Energieberechnung an die Coordinator-Instanz hängen, falls noch nicht vorhanden
    if not hasattr(coordinator, "_last_energy_calc_time"):
        coordinator._last_energy_calc_time = time.time()
        coordinator._total_energy_wh = 0.0

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
        
        # Sonderlogik für unseren selbstberechneten Energiewert
        if self.sensor_type == "energy":
            current_power = self.coordinator.data.get("power", None)
            if current_power is not None:
                now = time.time()
                time_delta = now - self.coordinator._last_energy_calc_time
                
                # Berechnung: Watt * Stunden = Wattstunden (Wh)
                if time_delta > 0:
                    hours = time_delta / 3600.0
                    added_energy = float(current_power) * hours
                    self.coordinator._total_energy_wh += added_energy
                
                self.coordinator._last_energy_calc_time = now
            
            # Rückgabe in Wattstunden (Wh), auf 2 Nachkommastellen gerundet
            return round(self.coordinator._total_energy_wh, 2)

        value = self.coordinator.data.get(self.sensor_type, None)
        if value is None:
            return None

        if self.sensor_type == "freeHeap":
            return round(float(value) / (1024 * 1024), 2)

        if self.sensor_type in DIFFICULTY_SENSOR_TYPES:
            try:
                scaled_value, unit = BitAxeSensor._format_with_si_prefix(float(value), base_unit="D")
                self._attr_native_unit_of_measurement = unit
                return scaled_value
            except (ValueError, TypeError):
                return value

        if self.sensor_type == "uptimeSeconds":
            return self._parse_uptime_to_seconds(value)

        if self.sensor_type in ["power", "fanspeed", "cpuUsage"]:
            return round(float(value), 1)

        if self.sensor_type in ["voltage", "coreVoltageActual"]:
            return round(float(value) / 1000.0, 2) if float(value) > 100 else round(float(value), 2)

        if self.sensor_type == "current":
            return round(float(value) / 1000.0, 2)

        if self.sensor_type in HASHRATE_SENSOR_TYPES:
            try:
                # Bitaxe API values are in GH/s. Convert to H/s before SI scaling.
                scaled_value, unit = BitAxeSensor._format_with_si_prefix(
                    float(value) * GH_TO_H_MULTIPLIER, base_unit="H/s"
                )
                self._attr_native_unit_of_measurement = unit
                return scaled_value
            except (ValueError, TypeError):
                return value

        if self.sensor_type in ["responseTime", "processTime"]:
            return round(float(value), 0)

        return value

    @staticmethod
    def _parse_uptime_to_seconds(value):
        if isinstance(value, (int, float)):
            return int(value)

        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None

            try:
                return int(float(stripped))
            except ValueError:
                pass

            match = UPTIME_PATTERN.fullmatch(stripped)
            if match:
                days, hours, minutes, seconds = (int(group or 0) for group in match.groups())
                return days * 86400 + hours * 3600 + minutes * 60 + seconds

        return None

    @staticmethod
    def _format_with_si_prefix(value: float, base_unit: str = ""):
        """Format a numeric value using dynamic SI prefixes."""
        if value == 0:
            return 0.0, f"{SI_PREFIXES[0]}{base_unit}"

        sign = -1 if value < 0 else 1
        abs_value = abs(value)

        exponent = 0
        max_exponent = max(SI_PREFIXES)
        min_exponent = min(SI_PREFIXES)
        while abs_value >= 1000 and exponent < max_exponent:
            abs_value /= 1000.0
            exponent += 1
        while abs_value < 1 and exponent > min_exponent:
            abs_value *= 1000.0
            exponent -= 1

        prefix = SI_PREFIXES.get(exponent, "")
        scaled_value = abs_value * sign

        if abs(scaled_value) >= 100:
            rounded = round(scaled_value, 1)
        elif abs(scaled_value) >= 10:
            rounded = round(scaled_value, 2)
        else:
            rounded = round(scaled_value, 3)

        return rounded, f"{prefix}{base_unit}"

    def _set_device_and_state_classes(self):
        """Assign native Home Assistant Device and State Classes."""
        if self.sensor_type == "power":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            
        elif self.sensor_type == "energy":
            # NEU: Exakte Konfiguration für das Energie-Dashboard
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR

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
        elif self.sensor_type == "freeHeap":
            self._attr_device_class = SensorDeviceClass.DATA_SIZE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
        elif self.sensor_type in HASHRATE_SENSOR_TYPES:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = "H/s"
        elif self.sensor_type == "actualFrequency":
            self._attr_device_class = SensorDeviceClass.FREQUENCY
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfFrequency.MEGAHERTZ
        elif self.sensor_type in ["fanrpm", "fan2rpm"]:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = "RPM"
        elif self.sensor_type in ["sharesAccepted", "sharesRejected"]:
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif self.sensor_type in DIFFICULTY_SENSOR_TYPES:
            self._attr_native_unit_of_measurement = "D"

    def _get_icon(self, sensor_type):
        """Select crisp Material Design Icons for the entities."""
        if sensor_type == "energy":
            return "mdi:lightning-bolt"
        elif sensor_type == "bestSessionDiff":
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
