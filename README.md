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
- **Two operating modes** (preset modes, matching the official Autoterm panels):
  - **Temperature mode** – heater regulates to the target temperature, fan is adjusted automatically
  - **Power mode** – heater runs at a fixed power / fan level 1–9, target temperature is ignored
- **Fan-only mode** – ventilation without combustion
- **Fan speed / power level** 1–9 (takes effect immediately in both heat and fan-only mode)
- **Configurable heater temperature source** – which sensor the heater firmware itself uses:
  - *Control panel* (default) – sensor in the panel
  - *Heater unit (built-in)* – sensor inside the heater
  - *External sensor wired to the heater* – hardware sensor attached to the heater
- **Optional Home Assistant indoor sensor** – any HA temperature sensor can act as a software thermostat. A two-point controller drives the heater setpoint based on this sensor, with configurable hysteresis (default 1.0 °C).
- **Live status**: Igniting, Heating, Cooling, Standby …
- **Burn-out protection** – heater cannot be turned off during the first ~4 minutes after ignition
- **Sensors**: Indoor/outdoor temperature, heater temperature, supply voltage, fan RPM, fuel pump
- Full **Config Flow UI** – no YAML needed
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

## Options

After setup, open the integration and click **Configure** to adjust:

| Option | Default | Description |
|---|---|---|
| **Poll interval** | 10 s | How often the heater status is polled (5–60 s) |
| **Heater temperature source** | Control panel | Which sensor the heater firmware uses when running in Temperature mode: *Control panel*, *Heater unit (built-in)* or *External sensor wired to the heater*. Independent of the optional HA sensor below. |
| **Indoor temperature sensor (Home Assistant)** | – | Optional HA temperature sensor (e.g. a Zigbee / BLE thermometer in the living space) used as a software thermostat. When set, Home Assistant drives the heater setpoint based on this sensor. |
| **Hysteresis** | 1.0 °C | Allowed deviation from the target before the HA thermostat switches state (0.1–5.0 °C). Only used when the HA indoor sensor is configured. |

### How the modes interact with the sensor options

- **Temperature mode + no HA sensor** – heater regulates autonomously using the configured *heater temperature source*.
- **Temperature mode + HA sensor** – HA reads the sensor and switches the heater's internal setpoint between minimum and maximum around the target, giving you a real indoor thermostat regardless of where the heater is mounted.
- **Power mode** – heater runs at the selected fan/power level 1–9. Both the target temperature and the temperature source are ignored by the firmware. The HA thermostat is not used in this mode.

## Usage examples

Switch to power mode at level 7:

```yaml
service: climate.set_preset_mode
target:
  entity_id: climate.parking_heater
data:
  preset_mode: power

service: climate.set_fan_mode
target:
  entity_id: climate.parking_heater
data:
  fan_mode: "7"
```

Switch back to temperature mode at 21 °C:

```yaml
service: climate.set_preset_mode
target:
  entity_id: climate.parking_heater
data:
  preset_mode: temperature

service: climate.set_temperature
target:
  entity_id: climate.parking_heater
data:
  temperature: 21
```

## Removal

1. **Settings → Devices & Services** → click the Autoterm integration
2. Click **Delete**
3. Optionally uninstall via HACS

## Known Limitations

- Only the **Autoterm Air 2D** (Planar 2D) is supported.
- A **minimum run time of ~4 minutes** applies after ignition (burn-out protection) — the heater cannot be turned off during this time.
- The **USB serial adapter must remain connected** for communication.
- The "Heat + Ventilation" and "Thermostat" firmware modes of the original Autoterm panels are not yet supported; use the HA indoor sensor option for equivalent behaviour.
- Selecting **External sensor wired to the heater** only works if a hardware sensor is actually connected to the heater unit.

## License

MIT — see [LICENSE](./LICENSE).
