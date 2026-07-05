# Bitaxe Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-blue.svg)](https://hacs.xyz/)
[![Latest Release](https://img.shields.io/github/v/release/DerMiika/Bitaxe-HA-Integration)](https://github.com/DerMiika/Bitaxe-HA-Integration/releases)
[![Stars](https://img.shields.io/github/stars/DerMiika/Bitaxe-HA-Integration)](https://github.com/DerMiika/Bitaxe-HA-Integration/stargazers)


This is a custom integration for Bitaxe miners in Home Assistant.

## Features

- **Real-time Monitoring**: Keep track of power, temperature, hashrate, difficulty, and other mining metrics in real-time.
- **Easy Configuration**: Configure your Bitaxe device effortlessly through Home Assistant's user interface.
- **Energy Dashboard ready**: Includes a cumulative energy sensor with Home Assistant energy metadata.
- **Dynamic SI scaling**:
  - Hashrate entities are scaled automatically (mH/s, kH/s, MH/s, GH/s, TH/s, PH/s).
  - Difficulty entities are scaled automatically (mD, D, kD, MD, GD, TD, PD).

## Manual Installation

1. Navigate to your Home Assistant configuration directory. This is usually the `/config` directory in your Home Assistant setup.

2. Clone the repository directly into the `custom_components` folder (create the folder if it doesn't exist):
   ```bash
   mkdir -p custom_components
   git clone https://github.com/DerMiika/Bitaxe-HA-Integration.git /config/custom_components/bitaxe
   ```

3.  Restart Home Assistant.

## HACS Installation

1. Open the HACS section in your Home Assistant.

2. Go to **Integrations** and select **Add Repository**.

3. Enter the URL for this repository: `https://github.com/DerMiika/Bitaxe-HA-Integration`.

4. Install the integration and follow the configuration steps.

## Configuration

To set up the integration, follow these steps:

1. Go to Settings > Devices & Services > Add Integration.
2. Search for "Bitaxe" and select it.
3. Enter the IP address of your Bitaxe miner.
4.  Choose a name for your Bitaxe miner (this can be any name you prefer).
5.  Complete the setup.

## Available Sensors

The integration creates one device with the following sensors:

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
| Expected Hash Rate | Expected hashrate | Dynamic SI `H/s` scaling |
| Hash Rate | Current hashrate | Dynamic SI `H/s` scaling |
| Hash Rate (1m) | 1-minute hashrate average | Dynamic SI `H/s` scaling |
| Hash Rate (10m) | 10-minute hashrate average | Dynamic SI `H/s` scaling |
| Hash Rate (1h) | 1-hour hashrate average | Dynamic SI `H/s` scaling |
| ASIC Error Rate | ASIC error percentage | % |
| Shares Accepted | Accepted shares | counter |
| Shares Rejected | Rejected shares | counter |
| All-Time Best Difficulty | Best all-time difficulty | Dynamic SI `D` scaling |
| Best Difficulty Since System Boot | Best difficulty since boot | Dynamic SI `D` scaling |
| Pool Difficulty | Current pool difficulty | Dynamic SI `D` scaling |
| Pool Response Time | Pool response time | ms |
| Pool Process Time | Pool processing time | ms |
| Uptime | Device uptime | formatted text (`Xd Xh Xm Xs`) |
| Wi-Fi RSSI | Wi-Fi signal strength | dBm |
| Free Heap Memory | Free heap memory | MB |
| CPU Usage | CPU usage | % |
| Current Block Height | Current Bitcoin block height | number |

## Notes on Unit Scaling

- Hashrate values from the Bitaxe API are normalized and shown with readable SI prefixes.
- Difficulty values are also normalized with SI prefixes for large ranges.
- Entity names stay unchanged, so existing dashboards/automations continue to reference the same entities.
- Unit prefixes update automatically when values cross SI thresholds (for example MH/s -> GH/s).
- If you rely on fixed units in templates/automations, normalize values first or compare raw thresholds carefully (for example, convert to H/s before comparing).

## Energy Dashboard

- `Total Energy Consumed` is provided as an energy sensor (`device_class: energy`, `state_class: total_increasing`, unit: Wh).
- This allows direct usage in Home Assistant's Energy Dashboard (or via a utility meter, depending on your dashboard setup).

## Screenshots

### Setup Screen
<img src="custom_components/bitaxe/images/Setup.png" alt="Setup Screen" style="max-width: 100%; height: auto;">

### Sensor Data Screen
<img src="custom_components/bitaxe/images/Sensor.png" alt="Sensor Data Screen" style="max-width: 100%; height: auto;">
