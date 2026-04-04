"""SmartDoor diagnostic sensor entities."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.entity.smartdoor import PetSafeExtendedSmartDoorEntity
from custom_components.petsafe_extended.entity_utils.smartdoor_diagnostics import (
    normalize_smartdoor_battery_voltage,
    normalize_smartdoor_signal_strength,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, UnitOfElectricPotential

SMARTDOOR_BATTERY_LEVEL_DESCRIPTION = SensorEntityDescription(
    key="battery_level",
    name="Battery Level",
    translation_key="battery_level",
    device_class=SensorDeviceClass.BATTERY,
    native_unit_of_measurement=PERCENTAGE,
    entity_category=EntityCategory.DIAGNOSTIC,
)

SMARTDOOR_BATTERY_VOLTAGE_DESCRIPTION = SensorEntityDescription(
    key="battery_voltage",
    name="Battery Voltage",
    translation_key="battery_voltage",
    device_class=SensorDeviceClass.VOLTAGE,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
)

SMARTDOOR_SIGNAL_STRENGTH_DESCRIPTION = SensorEntityDescription(
    key="signal_strength",
    name="Signal Strength",
    translation_key="signal_strength",
    device_class=SensorDeviceClass.SIGNAL_STRENGTH,
    native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
)

SMARTDOOR_DIAGNOSTIC_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SMARTDOOR_BATTERY_LEVEL_DESCRIPTION,
    SMARTDOOR_BATTERY_VOLTAGE_DESCRIPTION,
    SMARTDOOR_SIGNAL_STRENGTH_DESCRIPTION,
)


class PetSafeExtendedSmartDoorDiagnosticSensor(SensorEntity, PetSafeExtendedSmartDoorEntity):
    """Representation of a SmartDoor diagnostic sensor."""

    def __init__(self, coordinator: Any, door: Any, description: SensorEntityDescription) -> None:
        """Initialize the SmartDoor diagnostic sensor."""
        super().__init__(coordinator, door, description)

    @property
    def native_value(self) -> Any:
        """Return the current sensor state."""
        door = self._get_door()
        if door is None:
            return None

        if self.entity_description.key == SMARTDOOR_BATTERY_LEVEL_DESCRIPTION.key:
            return getattr(door, "battery_level", None)
        if self.entity_description.key == SMARTDOOR_BATTERY_VOLTAGE_DESCRIPTION.key:
            return normalize_smartdoor_battery_voltage(getattr(door, "battery_voltage", None))
        if self.entity_description.key == SMARTDOOR_SIGNAL_STRENGTH_DESCRIPTION.key:
            return normalize_smartdoor_signal_strength(getattr(door, "rssi", None))
        return None
