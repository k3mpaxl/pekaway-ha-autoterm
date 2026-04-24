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
from homeassistant.const import ATTR_TEMPERATURE, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_EXTERNAL_TEMP_SENSOR,
    CONF_HEATER_TEMP_SOURCE,
    CONF_HYSTERESIS,
    DEFAULT_FAN_LEVEL,
    DEFAULT_HEATER_TEMP_SOURCE,
    DEFAULT_HYSTERESIS,
    DEFAULT_PRESET_MODE,
    DEFAULT_TARGET_TEMP,
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    DOMAIN,
    FAN_MODES,
    HEATER_TEMP_SOURCE_MAP,
    MIN_RUN_TIME_SECONDS,
    PRESET_MODES,
    PRESET_POWER,
    PRESET_TEMPERATURE,
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
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_fan_modes = FAN_MODES
    _attr_preset_modes = PRESET_MODES

    def __init__(
        self,
        coordinator: AutotermCoordinator,
        protocol: AutotermProtocol,
        entry: AutotermConfigEntry,
    ) -> None:
        """Initialisieren."""
        super().__init__(coordinator)
        self._entry = entry
        self._protocol = protocol
        self._target_temp = DEFAULT_TARGET_TEMP
        self._fan_mode = str(DEFAULT_FAN_LEVEL)
        self._preset_mode: str = DEFAULT_PRESET_MODE
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Autoterm Air 2D",
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )
        # Zeitpunkt des letzten Einschaltens – None solange unbekannt.
        self._turn_on_time: datetime | None = None

        # Externer Temperaturfühler (optional, Home-Assistant-Sensor als
        # Software-Thermostat für den Innenraum).
        self._external_sensor: str | None = entry.options.get(
            CONF_EXTERNAL_TEMP_SENSOR
        )
        self._hysteresis: float = float(
            entry.options.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)
        )
        # Temperaturquelle der Heizungs-Firmware (panel/internal/external).
        # Unabhängig vom HA-Sensor – wird auch ohne diesen verwendet.
        self._heater_temp_source_key: str = entry.options.get(
            CONF_HEATER_TEMP_SOURCE, DEFAULT_HEATER_TEMP_SOURCE
        )
        # Zuletzt an die Heizung gesendeter interner Soll-Wert (TEMP_MAX oder TEMP_MIN),
        # wenn der HA-Sensor aktiv ist. None solange noch nichts gesendet wurde.
        self._last_commanded_heater_temp: int | None = None

    async def async_added_to_hass(self) -> None:
        """State-Change-Listener für externen Temperaturfühler registrieren."""
        await super().async_added_to_hass()
        if self._external_sensor:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._external_sensor],
                    self._async_external_sensor_changed,
                )
            )

    # ---- Externer Temperaturfühler --------------------------------------

    def _read_external_temp(self) -> float | None:
        """Aktuellen Wert des externen Temperaturfühlers lesen (oder None)."""
        if not self._external_sensor:
            return None
        state = self.hass.states.get(self._external_sensor)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None, ""):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Externer Temperaturfühler %s liefert ungültigen Wert: %s",
                self._external_sensor,
                state.state,
            )
            return None

    @callback
    def _async_external_sensor_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Callback bei Änderung des externen Temperaturfühlers."""
        self.hass.async_create_task(self._async_control_external())
        self.async_write_ha_state()

    async def _async_control_external(self) -> None:
        """Zweipunktregler: Heizungs-Sollwert abhängig von der externen Temperatur.

        Ist kein externer Fühler konfiguriert oder die Heizung nicht im HEAT-Modus,
        passiert nichts. Andernfalls wird die interne Zieltemperatur der Heizung auf
        ``TEMP_MAX`` (heizt voll) oder ``TEMP_MIN`` (geht in die Regelpause) gesetzt,
        sobald die externe Temperatur die Zieltemperatur unter- bzw. überschreitet
        (Hysterese beidseitig).
        """
        if not self._external_sensor:
            return
        if self.hvac_mode != HVACMode.HEAT:
            return
        if self._preset_mode != PRESET_TEMPERATURE:
            return

        current = self._read_external_temp()
        if current is None:
            return

        target = float(self._target_temp)
        if current <= target - self._hysteresis:
            desired_heater_temp = TEMP_MAX
        elif current >= target + self._hysteresis:
            desired_heater_temp = TEMP_MIN
        else:
            # Innerhalb des Hysteresebandes: nichts ändern.
            return

        if desired_heater_temp == self._last_commanded_heater_temp:
            return

        success = await self.hass.async_add_executor_job(
            self._protocol.set_temperature, desired_heater_temp
        )
        if not success:
            _LOGGER.warning(
                "Setzen des internen Heizungs-Sollwerts (%d°C) fehlgeschlagen",
                desired_heater_temp,
            )
            return

        self._last_commanded_heater_temp = desired_heater_temp
        _LOGGER.debug(
            "Externer Regler: aktuell=%.2f°C, Ziel=%.1f°C, Heizungs-Sollwert=%d°C",
            current,
            target,
            desired_heater_temp,
        )

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
        """Aktuelle Raumtemperatur.

        Priorität:
        1. Optionaler HA-Innenraum-Sensor (CONF_EXTERNAL_TEMP_SENSOR), falls
           konfiguriert und verfügbar.
        2. Hardware-Temperaturquelle der Heizung entsprechend der
           konfigurierten ``heater_temp_source``:
           - ``panel`` / ``internal`` → ``temp_internal`` der Heizung
           - ``external`` → ``temp_external`` der Heizung (Hardware-Fühler)
        3. Fallback: ``temp_internal``.
        """
        if self._external_sensor:
            external = self._read_external_temp()
            if external is not None:
                return external
        data = self.coordinator.data or {}
        if self._heater_temp_source_key == "external":
            value = data.get("temp_external")
            if value is not None:
                return value
        return data.get("temp_internal")

    @property
    def target_temperature(self) -> float:
        """Zieltemperatur."""
        return float(self._target_temp)

    @property
    def fan_mode(self) -> str:
        """Aktuelle Lüfter-/Leistungsstufe."""
        return self._fan_mode

    @property
    def preset_mode(self) -> str:
        """Aktueller Preset-Modus (Temperatur- oder Leistungsmodus)."""
        return self._preset_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Zusätzliche Attribute."""
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {
            "status": data.get("status_text"),
            "freibrennschutz_aktiv": self._freibrenn_schutz_aktiv(),
            "preset_mode": self._preset_mode,
            "heater_temp_source": self._heater_temp_source_key,
        }
        if self._freibrenn_schutz_aktiv():
            attrs["ausschalten_gesperrt_noch_sekunden"] = (
                self._verbleibende_schutzzeit()
            )
        if self._external_sensor and self._preset_mode == PRESET_TEMPERATURE:
            attrs["external_temp_sensor"] = self._external_sensor
            attrs["external_temp"] = self._read_external_temp()
            attrs["hysteresis"] = self._hysteresis
            attrs["heater_internal_setpoint"] = (
                self._last_commanded_heater_temp
            )
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
            self._last_commanded_heater_temp = None

        elif hvac_mode == HVACMode.HEAT:
            await self._async_apply_heating_settings()
            self._turn_on_time = datetime.now(timezone.utc)
            if (
                self._preset_mode == PRESET_TEMPERATURE
                and self._external_sensor
            ):
                # Regler sofort ausführen, um evtl. TEMP_MIN zu setzen,
                # wenn es schon warm ist.
                await self._async_control_external()

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

    async def _async_apply_heating_settings(self) -> None:
        """Aktuelle Heiz-Settings an die Heizung senden.

        Die Autoterm-Firmware übernimmt neue Einstellungen zuverlässig
        nur über das vollständige Start-Kommando (``CMD_TURN_ON``).
        Ein erneutes Senden während die Heizung läuft aktualisiert Modus,
        Temperatur und Lüfter-/Leistungsstufe.
        """
        fan_level = int(self._fan_mode)
        power_mode = self._preset_mode == PRESET_POWER

        if power_mode:
            initial_temp = self._target_temp
        elif self._external_sensor:
            initial_temp = TEMP_MAX
        else:
            initial_temp = self._target_temp

        temp_source = HEATER_TEMP_SOURCE_MAP.get(self._heater_temp_source_key)

        success = await self.hass.async_add_executor_job(
            self._protocol.turn_on,
            initial_temp,
            fan_level,
            power_mode,
            temp_source,
        )
        if not success:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="turn_on_failed",
            )

        if power_mode:
            self._last_commanded_heater_temp = None
        elif self._external_sensor:
            self._last_commanded_heater_temp = initial_temp
        else:
            self._last_commanded_heater_temp = None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Zieltemperatur setzen.

        Im Leistungsmodus hat die Zieltemperatur keine Auswirkung auf die
        Heizung (sie regelt ausschließlich über die Lüfter-/Leistungsstufe).
        Der Wert wird trotzdem gespeichert, damit er beim Wechsel in den
        Temperaturmodus wieder verfügbar ist.
        """
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        self._target_temp = int(temp)

        if self.hvac_mode == HVACMode.HEAT:
            if self._preset_mode == PRESET_POWER:
                # Leistungsmodus: Temperatur-Setpoint wird von der Heizung
                # ignoriert – nichts senden.
                pass
            elif self._external_sensor:
                # Extern geregelt: den neuen Zielwert nicht direkt an die
                # Heizung schicken, sondern den Regler neu bewerten lassen.
                self._last_commanded_heater_temp = None
                await self._async_control_external()
            else:
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
        """Lüfter-/Leistungsstufe setzen.

        Im ``FAN_ONLY``-Modus wird direkt der Lüfter aktualisiert.
        Im ``HEAT``-Modus muss die komplette Settings-Nachricht erneut
        gesendet werden, damit die Heizung die neue Stufe übernimmt –
        ein isoliertes ``set_temperature`` reicht hier nicht aus.
        """
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
        elif self.hvac_mode == HVACMode.HEAT:
            await self._async_apply_heating_settings()

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Preset-Modus (Temperatur- oder Leistungsmodus) setzen."""
        if preset_mode not in PRESET_MODES:
            raise ServiceValidationError(
                f"Unbekannter Preset-Modus: {preset_mode}"
            )
        if preset_mode == self._preset_mode:
            return
        self._preset_mode = preset_mode

        if self.hvac_mode == HVACMode.HEAT:
            await self._async_apply_heating_settings()
            if (
                self._preset_mode == PRESET_TEMPERATURE
                and self._external_sensor
            ):
                await self._async_control_external()

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
