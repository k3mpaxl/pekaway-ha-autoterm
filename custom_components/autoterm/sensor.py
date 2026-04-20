"""Sensor Entities für die Autoterm Air 2D Standheizung."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MANUFACTURER, DEVICE_MODEL, DOMAIN
from .coordinator import AutotermConfigEntry, AutotermCoordinator

# Sensoren sind reine Reads, parallele Updates sind kein Problem.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AutotermSensorEntityDescription(SensorEntityDescription):
    """Beschreibung für Autoterm Sensoren."""

    data_key: str
    round_digits: int | None = None


SENSOR_DESCRIPTIONS: tuple[AutotermSensorEntityDescription, ...] = (
    AutotermSensorEntityDescription(
        key="temp_internal",
        translation_key="temp_internal",
        data_key="temp_internal",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AutotermSensorEntityDescription(
        key="temp_external",
        translation_key="temp_external",
        data_key="temp_external",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,  # häufig nicht verkabelt
    ),
    AutotermSensorEntityDescription(
        key="temp_heater",
        translation_key="temp_heater",
        data_key="temp_heater",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AutotermSensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        data_key="voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        round_digits=1,
    ),
    AutotermSensorEntityDescription(
        key="fan_rpm_actual",
        translation_key="fan_rpm_actual",
        data_key="fan_rpm_actual",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AutotermSensorEntityDescription(
        key="fan_rpm_set",
        translation_key="fan_rpm_set",
        data_key="fan_rpm_set",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    AutotermSensorEntityDescription(
        key="status_text",
        translation_key="status_text",
        data_key="status_text",
    ),
    AutotermSensorEntityDescription(
        key="fuel_pump_freq",
        translation_key="fuel_pump_freq",
        data_key="fuel_pump_freq",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        round_digits=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AutotermConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sensor Entities einrichten."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        AutotermSensor(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
    )


class AutotermSensor(CoordinatorEntity[AutotermCoordinator], SensorEntity):
    """Sensor Entity für einen Messwert der Autoterm Air 2D."""

    _attr_has_entity_name = True
    entity_description: AutotermSensorEntityDescription

    def __init__(
        self,
        coordinator: AutotermCoordinator,
        description: AutotermSensorEntityDescription,
        entry: AutotermConfigEntry,
    ) -> None:
        """Initialisieren."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Autoterm Air 2D",
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )

    @property
    def available(self) -> bool:
        """Sensor verfügbar wenn Coordinator Daten hat."""
        if not super().available:
            return False
        data = self.coordinator.data
        if not data:
            return False
        # Datenpunkt muss im aktuellen Payload vorhanden sein
        return self.entity_description.data_key in data

    @property
    def native_value(self) -> Any:
        """Aktueller Sensorwert."""
        data = self.coordinator.data
        if not data:
            return None
        value = data.get(self.entity_description.data_key)
        if value is None:
            return None

        digits = self.entity_description.round_digits
        if digits is not None and isinstance(value, (int, float)):
            return round(value, digits)
        return value
