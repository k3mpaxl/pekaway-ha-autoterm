"""Diagnose-Daten für die Autoterm Integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import AutotermConfigEntry

# Der Port enthält ggf. vom User verwendete Pfade – redactbar.
TO_REDACT = {"port"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AutotermConfigEntry
) -> dict[str, Any]:
    """Diagnose für einen Config-Entry liefern."""
    coordinator = entry.runtime_data.coordinator

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "data": coordinator.data or {},
    }
