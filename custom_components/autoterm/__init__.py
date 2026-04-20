"""Autoterm Air 2D Standheizung – Home Assistant Integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_PORT, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import AutotermConfigEntry, AutotermCoordinator, AutotermData
from .protocol import AutotermProtocol

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: AutotermConfigEntry) -> bool:
    """Integration einrichten aus einem Config-Entry."""
    port = entry.data[CONF_PORT]
    # Options > Data > Default — Options-Flow schreibt in entry.options.
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    protocol = AutotermProtocol(port)

    # Serielle Verbindung im Executor öffnen (pyserial ist synchron-blockierend).
    try:
        await hass.async_add_executor_job(protocol.connect)
    except Exception as err:
        raise ConfigEntryNotReady(
            f"Konnte nicht mit Autoterm auf Port {port} verbinden: {err}"
        ) from err

    coordinator = AutotermCoordinator(hass, entry, protocol, scan_interval)

    # Ersten Datenabruf durchführen — wirft ConfigEntryNotReady bei Fehlern.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = AutotermData(coordinator=coordinator, protocol=protocol)

    # Options-Änderungen triggern einen Reload.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AutotermConfigEntry) -> bool:
    """Integration entfernen — serielle Verbindung sauber schließen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        protocol = entry.runtime_data.protocol
        await hass.async_add_executor_job(protocol.disconnect)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: AutotermConfigEntry) -> None:
    """Integration nach Options-Änderung neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)
