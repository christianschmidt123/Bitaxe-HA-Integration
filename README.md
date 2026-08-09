# Bitaxe Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-blue.svg)](https://hacs.xyz/)
[![Latest Release](https://img.shields.io/github/v/release/christianschmidt123/Bitaxe-HA-Integration)](https://github.com/christianschmidt123/Bitaxe-HA-Integration/releases)
[![Stars](https://img.shields.io/github/stars/christianschmidt123/Bitaxe-HA-Integration)](https://github.com/christianschmidt123/Bitaxe-HA-Integration/stargazers)
[![Open your Home Assistant instance and open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=christianschmidt123&repository=Bitaxe-HA-Integration&category=integration)


This is a custom integration for Bitaxe miners in Home Assistant.

## Features

- **Real-time Monitoring**: Keep track of power, temperature, hashrate, difficulty, and other mining metrics in real-time.
- **Easy Configuration**: Configure your Bitaxe device effortlessly through Home Assistant's user interface.
- **Energy Dashboard ready**: Includes a cumulative energy sensor with Home Assistant energy metadata.
- **Readable units**:
  - Hashrate entities use a fixed `TH/s` unit for stable long-term statistics.
  - Difficulty entities are scaled automatically (mD, D, kD, MD, GD, TD, PD).
- **Benchmark workflow**:
  - Start automatic benchmark runs directly from Home Assistant (30W / 40W PSU profiles).
  - Stop a running benchmark at any time.
  - Live benchmark status sensors for progress, best frequency, and best voltage.
- **Extended telemetry**: Additional fan speed and fan RPM entities are included where provided by firmware.

## Manual Installation

1. Navigate to your Home Assistant configuration directory. This is usually the `/config` directory in your Home Assistant setup.

2. Clone the repository directly into the `custom_components` folder (create the folder if it doesn't exist):
   ```bash
   mkdir -p custom_components
   git clone https://github.com/christianschmidt123/Bitaxe-HA-Integration.git /config/custom_components/bitaxe
   ```

3.  Restart Home Assistant.

## HACS Installation

1. Open the HACS section in your Home Assistant.

2. Go to **Integrations** and select **Add Repository**.

3. Enter the URL for this repository: `https://github.com/christianschmidt123/Bitaxe-HA-Integration`.

4. Install the integration and follow the configuration steps.

## Configuration

To set up the integration, follow these steps:

1. Go to Settings > Devices & Services > Add Integration.
2. Home Assistant should discover compatible Bitaxe/AxeOS devices automatically on the local network.
3. If your Bitaxe is not discovered automatically, search for "Bitaxe" and select it manually.
4. Enter the IP address of your Bitaxe miner.
5. The integration will read the Bitaxe hostname automatically and use it as the device name when possible. You can still provide an optional custom name during manual setup.
6. Complete the setup.

## Available Sensors

The integration creates one device with the following sensors:

> Note: Some benchmark entity labels currently remain in German because they mirror the exact entity names exposed by the integration.

| Sensor | Description | Unit / Behavior |
| --- | --- | --- |
| Power Consumption | Current miner power draw | W |
| Total Energy Consumed | Cumulative energy from power over time | Wh (total_increasing, Energy Dashboard compatible) |
| Input Voltage | Input voltage | V |
| Input Current | Input current | A |
| Temperature ASIC | ASIC temperature | °C |
| Temperature 2 | Additional temperature | °C |
| Temperature VR | VR temperature | °C |
| Core Voltage Actual | Core voltage | V |
| Actual Frequency | ASIC frequency | MHz |
| Fan Speed | Fan speed percentage | % |
| Fan RPM | Fan speed | RPM |
| Fan 2 RPM | Second fan speed | RPM |
| Expected Hash Rate | Expected hashrate | TH/s (fixed unit) |
| Hash Rate | Current hashrate | TH/s (fixed unit) |
| Hash Rate (1m) | 1-minute hashrate average | TH/s (fixed unit) |
| Hash Rate (10m) | 10-minute hashrate average | TH/s (fixed unit) |
| Hash Rate (1h) | 1-hour hashrate average | TH/s (fixed unit) |
| ASIC Error Rate | ASIC error percentage | % |
| Shares Accepted | Accepted shares | counter |
| Shares Rejected | Rejected shares | counter |
| All-Time Best Difficulty | Best all-time difficulty | Dynamic SI `D` scaling |
| Best Difficulty Since System Boot | Best difficulty since boot | Dynamic SI `D` scaling |
| Pool Difficulty | Current pool difficulty | Dynamic SI `D` scaling |
| Pool Response Time | Pool response time | ms |
| Pool Process Time | Pool processing time | ms |
| Uptime | Device uptime | s (`device_class: duration`) |
| Wi-Fi RSSI | Wi-Fi signal strength | dBm |
| Free Heap Memory | Free heap memory | MB |
| CPU Usage | CPU usage | % |
| Current Block Height | Current Bitcoin block height | number |
| Benchmark Status | Live benchmark state text | text |
| Benchmark Fortschritt | Live benchmark progress *(entity label currently in German)* | % |
| Benchmark Beste Frequenz | Best benchmark frequency so far *(entity label currently in German)* | MHz |
| Benchmark Beste Spannung | Best benchmark voltage so far *(entity label currently in German)* | mV |

## Available Buttons

The integration also creates device buttons:

- `Benchmark (30W Netzteil)` - Starts the benchmark with a 30W power limit *(button label currently in German)*.
- `Benchmark (40W Netzteil)` - Starts the benchmark with a 40W power limit *(button label currently in German)*.
- `Benchmark Abbrechen` - Cancels a running benchmark immediately *(button label currently in German)*.

## Notes on Unit Behavior

- Hashrate values from the Bitaxe API are published in a fixed `TH/s` unit to keep Home Assistant long-term statistics consistent.
- Difficulty values are also normalized with SI prefixes for large ranges.
- Entity names stay unchanged, so existing dashboards/automations continue to reference the same entities.
- If you had older hashrate statistics stored with another unit, update the old unit in Home Assistant statistics or clear that entity's historical statistics once.

Example template snippet (convert TH/s to H/s if needed):
```jinja2
{{ states('sensor.hash_rate') | float(0) * 1e12 }}
```

## Energy Dashboard

- `Total Energy Consumed` is provided as an energy sensor (`device_class: energy`, `state_class: total_increasing`, unit: Wh).
- This allows direct usage in Home Assistant's Energy Dashboard (or via a utility meter, depending on your dashboard setup).

## Screenshots

### Setup Screen
<img src="custom_components/bitaxe/images/Setup.png" alt="Setup Screen" style="max-width: 100%; height: auto;">

### Sensor Data Screen
<img src="custom_components/bitaxe/images/Sensor.png" alt="Sensor Data Screen" style="max-width: 100%; height: auto;">
