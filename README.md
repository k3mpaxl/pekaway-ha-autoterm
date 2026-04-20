# Autoterm Air 2D — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-%E2%89%A52024.10-blue)](https://www.home-assistant.io/)
[![Validate](https://github.com/k3mpaxl/pekaway-ha-autoterm/actions/workflows/validate.yml/badge.svg)](https://github.com/k3mpaxl/pekaway-ha-autoterm/actions/workflows/validate.yml)

Control your **Autoterm Air 2D** parking heater directly from Home Assistant via a USB serial adapter on a Raspberry Pi.

> Part of the [Pekaway VAN PI CORE](https://github.com/k3mpaxl/pekaway-vanpi-homeassistant) integration family.

The protocol was reverse-engineered and documented here:
[schroeder-robert/autoterm-air-2d-serial-control](https://github.com/schroeder-robert/autoterm-air-2d-serial-control)

## Features

- **Heater on/off** with target temperature (8–35 °C)
- **Fan-only mode** — ventilation without combustion
- **Fan speed** 1–9
- **Live status**: Igniting, Heating, Cooling, Standby …
- **Sensors**: Indoor/outdoor temperature, heater temperature, supply voltage, fan RPM, fuel pump
- Full **Config Flow UI** — no YAML needed
- Automatic **pyserial** installation by HA

## Prerequisites

| | |
|---|---|
| **Heater** | Autoterm Air 2D (Planar 2D) |
| **Adapter** | USB-to-serial adapter (e.g. CH340, CP2102) |
| **Home Assistant** | ≥ 2024.10 |

## Installation via HACS

1. **HACS** → **Integrations** → three dots → **Custom repositories**
2. Enter this repository URL:
   ```
   https://github.com/k3mpaxl/pekaway-ha-autoterm
   ```
   Category: **Integration**
3. Search for **Autoterm Air 2D** and install.
4. Restart Home Assistant.

## Setup

1. **Settings → Devices & Services → + Add Integration**
2. Search for **Autoterm Air 2D**
3. Enter the serial port (e.g. `/dev/ttyUSB0`)
4. The heater is detected and a Climate entity is created.

## Removal

1. **Settings → Devices & Services** → click the Autoterm integration
2. Click **Delete**
3. Optionally uninstall via HACS

## Known Limitations

- Only the **Autoterm Air 2D** (Planar 2D) is supported.
- A minimum run time of ~2 minutes applies after ignition.
- The USB serial adapter must remain connected for communication.

## License

MIT — see [LICENSE](./LICENSE).
