"""Climate Entity für die Autoterm Air 2D Standheizung."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_FAN_LEVEL,
    DEFAULT_TARGET_TEMP,
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    DOMAIN,
    FAN_MODES,
    MIN_RUN_TIME_SECONDS,
    TEMP_MAX,
    TEMP_MIN,
)
from .coordinator import AutotermConfigEntry, AutotermCoordinator
from .protocol import AutotermProtocol

_LOGGER = logging.getLogger(__name__)

# Die Climate-Entity ist die einzige, die Writes an die Heizung schickt.
# Serialisieren: niemals zwei Kommandos gleichzeitig.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AutotermConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Climate Entity einrichten."""
    data = entry.runtime_data
    async_add_entities([AutotermClimate(data.coordinator, data.protocol, entry)])


class AutotermClimate(CoordinatorEntity[AutotermCoordinator], ClimateEntity):
    """Home Assistant Climate Entity für die Autoterm Air 2D Standheizung."""

    _attr_has_entity_name = True
    _attr_translation_key = "heater"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = TEMP_MIN
    _attr_max_temp = TEMP_MAX
    _attr_target_temperature_step = 1.0
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.FAN_ONLY, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_fan_modes = FAN_MODES

    def __init__(
        self,
        coordinator: AutotermCoordinator,
        protocol: AutotermProtocol,
        entry: AutotermConfigEntry,
    ) -> None:
        """Initialisieren."""
        super().__init__(coordinator)
        self._protocol = protocol
        self._target_temp = DEFAULT_TARGET_TEMP
        self._fan_mode = str(DEFAULT_FAN_LEVEL)
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Autoterm Air 2D",
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )
        # Zeitpunkt des letzten Einschaltens – None solange unbekannt.
        self._turn_on_time: datetime | None = None

    # ---- Freibrenn-Schutz ------------------------------------------------

    def _freibrenn_schutz_aktiv(self) -> bool:
        """True, solange die Freibrenn-Phase läuft."""
        if self._turn_on_time is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self._turn_on_time).total_seconds()
        return elapsed < MIN_RUN_TIME_SECONDS

    def _verbleibende_schutzzeit(self) -> int:
        """Verbleibende Sekunden der Freibrenn-Phase."""
        if self._turn_on_time is None:
            return 0
        elapsed = (datetime.now(timezone.utc) - self._turn_on_time).total_seconds()
        return max(0, int(MIN_RUN_TIME_SECONDS - elapsed))

    # ---- State -----------------------------------------------------------

    @property
    def available(self) -> bool:
        """Climate ist verfügbar, solange der Coordinator zuletzt erfolgreich war."""
        return super().available and bool(self.coordinator.data)

    @property
    def hvac_mode(self) -> HVACMode:
        """Aktueller Betriebsmodus."""
        data = self.coordinator.data
        if not data:
            return HVACMode.OFF
        if data.get("is_heating"):
            return HVACMode.HEAT
        if data.get("is_fan_only"):
            return HVACMode.FAN_ONLY
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Detaillierte HVAC-Aktion."""
        data = self.coordinator.data
        if not data:
            return HVACAction.OFF
        status_key = data.get("status_key", (0, 1))
        if status_key in {(2, 1), (2, 2), (2, 3), (2, 4)}:
            return HVACAction.PREHEATING
        if status_key == (3, 0):
            return HVACAction.HEATING
        if status_key == (3, 35):
            return HVACAction.FAN
        if status_key in {(1, 0), (1, 1), (3, 4)}:
            return HVACAction.COOLING
        return HVACAction.OFF

    @property
    def current_temperature(self) -> float | None:
        """Aktuelle Innentemperatur."""
        data = self.coordinator.data
        return data.get("temp_internal") if data else None

    @property
    def target_temperature(self) -> float:
        """Zieltemperatur."""
        return float(self._target_temp)

    @property
    def fan_mode(self) -> str:
        """Aktuelle Lüfterstufe."""
        return self._fan_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Zusätzliche Attribute."""
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {
            "status": data.get("status_text"),
            "freibrennschutz_aktiv": self._freibrenn_schutz_aktiv(),
        }
        if self._freibrenn_schutz_aktiv():
            attrs["ausschalten_gesperrt_noch_sekunden"] = self._verbleibende_schutzzeit()
        return attrs

    # ---- Actions ---------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Betriebsmodus setzen (Fehler werfen HomeAssistantError)."""
        fan_level = int(self._fan_mode)

        if hvac_mode == HVACMode.OFF:
            if self._freibrenn_schutz_aktiv():
                remaining = self._verbleibende_schutzzeit()
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="freibrennschutz_aktiv",
                    translation_placeholders={
                        "minutes": str(MIN_RUN_TIME_SECONDS // 60),
                        "remaining": str(remaining),
                    },
                )
            success = await self.hass.async_add_executor_job(self._protocol.turn_off)
            if not success:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="turn_off_failed",
                )
            self._turn_on_time = None

        elif hvac_mode == HVACMode.HEAT:
            success = await self.hass.async_add_executor_job(
                self._protocol.turn_on, self._target_temp, fan_level
            )
            if not success:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="turn_on_failed",
                )
            self._turn_on_time = datetime.now(timezone.utc)

        elif hvac_mode == HVACMode.FAN_ONLY:
            success = await self.hass.async_add_executor_job(
                self._protocol.fan_only, fan_level
            )
            if not success:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="fan_only_failed",
                )
            self._turn_on_time = datetime.now(timezone.utc)

        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Zieltemperatur setzen."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        self._target_temp = int(temp)

        if self.hvac_mode == HVACMode.HEAT:
            success = await self.hass.async_add_executor_job(
                self._protocol.set_temperature, self._target_temp
            )
            if not success:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="set_temperature_failed",
                )

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Lüfterstufe setzen."""
        self._fan_mode = fan_mode
        fan_level = int(fan_mode)

        if self.hvac_mode == HVACMode.FAN_ONLY:
            success = await self.hass.async_add_executor_job(
                self._protocol.fan_only, fan_level
            )
            if not success:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="fan_only_failed",
                )

        self.async_write_ha_state()
