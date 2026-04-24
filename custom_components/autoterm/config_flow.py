"""Config Flow für die Autoterm Air 2D Integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_EXTERNAL_TEMP_SENSOR,
    CONF_HEATER_TEMP_SOURCE,
    CONF_HYSTERESIS,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_HEATER_TEMP_SOURCE,
    DEFAULT_HYSTERESIS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HEATER_TEMP_SOURCES,
)
from .protocol import AutotermProtocol

_LOGGER = logging.getLogger(__name__)


class AutotermConnectionError(Exception):
    """Kann sich nicht zur Heizung verbinden."""


async def _validate_serial_port(hass: HomeAssistant, port: str) -> dict[str, Any]:
    """Seriellen Port testen und Verbindung prüfen."""
    protocol = AutotermProtocol(port)

    try:
        await hass.async_add_executor_job(protocol.connect)
    except Exception as err:
        raise AutotermConnectionError(str(err)) from err

    try:
        status = await hass.async_add_executor_job(protocol.get_status)
        if not status:
            raise AutotermConnectionError("Heizung antwortet nicht")
        version = await hass.async_add_executor_job(protocol.get_version)
    finally:
        await hass.async_add_executor_job(protocol.disconnect)

    return {"status": status, "version": version}


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            cv.positive_int, vol.Range(min=5, max=60)
        ),
    }
)


class AutotermConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config Flow für Autoterm."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ersten Einrichtungsschritt verarbeiten."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_PORT]
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_configured()

            try:
                await _validate_serial_port(self.hass, port)
            except AutotermConnectionError as err:
                _LOGGER.warning("Port-Validierung fehlgeschlagen: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unerwarteter Fehler bei Port-Validierung")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Autoterm Air 2D ({port})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"port_example": "/dev/ttyUSB0"},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure-Flow: Port oder Scan-Intervall nachträglich ändern."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_PORT]
            # unique_id kann sich ändern, wenn der Port anders ist
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_mismatch(reason="port_mismatch")

            try:
                await _validate_serial_port(self.hass, port)
            except AutotermConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unerwarteter Fehler bei Reconfigure")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
                    ): cv.string,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(cv.positive_int, vol.Range(min=5, max=60)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Options-Flow für Scan-Intervall."""
        return AutotermOptionsFlow()


class AutotermOptionsFlow(OptionsFlow):
    """Options Flow: erlaubt Änderung des Scan-Intervalls ohne Reload-Tanz."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Options bearbeiten."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_sensor = self.config_entry.options.get(CONF_EXTERNAL_TEMP_SENSOR)
        current_hysteresis = self.config_entry.options.get(
            CONF_HYSTERESIS, DEFAULT_HYSTERESIS
        )
        current_heater_source = self.config_entry.options.get(
            CONF_HEATER_TEMP_SOURCE, DEFAULT_HEATER_TEMP_SOURCE
        )

        schema_dict: dict = {
            vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                cv.positive_int, vol.Range(min=5, max=60)
            ),
            vol.Optional(
                CONF_HEATER_TEMP_SOURCE, default=current_heater_source
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=HEATER_TEMP_SOURCES,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_HEATER_TEMP_SOURCE,
                )
            ),
            vol.Optional(
                CONF_EXTERNAL_TEMP_SENSOR,
                description={"suggested_value": current_sensor},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    device_class="temperature",
                )
            ),
            vol.Optional(
                CONF_HYSTERESIS, default=current_hysteresis
            ): vol.All(
                vol.Coerce(float), vol.Range(min=0.1, max=5.0)
            ),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )
