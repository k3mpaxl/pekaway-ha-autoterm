"""DataUpdateCoordinator für die Autoterm Air 2D Integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .protocol import AutotermProtocol

_LOGGER = logging.getLogger(__name__)


@dataclass
class AutotermData:
    """Runtime-Daten eines Autoterm Config-Entries."""

    coordinator: AutotermCoordinator
    protocol: AutotermProtocol


type AutotermConfigEntry = ConfigEntry[AutotermData]


class AutotermCoordinator(DataUpdateCoordinator[dict]):
    """Koordinator für regelmäßige Status-Abfragen der Heizung."""

    config_entry: AutotermConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: AutotermConfigEntry,
        protocol: AutotermProtocol,
        scan_interval: int,
    ) -> None:
        """Initialisieren."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}-{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.protocol = protocol

    async def _async_update_data(self) -> dict:
        """Status von der Heizung abrufen (Exceptions → UpdateFailed)."""
        try:
            data = await self.hass.async_add_executor_job(self.protocol.get_status)
        except ConnectionError as err:
            raise UpdateFailed(f"Verbindungsfehler: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Status-Abruf fehlgeschlagen: {err}") from err

        if not data:
            raise UpdateFailed("Leere Antwort von der Heizung erhalten")
        return data
