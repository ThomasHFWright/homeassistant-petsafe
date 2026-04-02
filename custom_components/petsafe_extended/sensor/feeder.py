"""Feeder sensor entities for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.const import FEEDER_MODEL_GEN1
from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory

FEEDER_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="battery",
        name="Battery Level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="last_feeding",
        name="Last Feeding",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="next_feeding",
        name="Next Feeding",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="food_level",
        name="Food Level",
        icon="mdi:bowl",
    ),
    SensorEntityDescription(
        key="signal_strength",
        name="Signal Strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


class PetSafeExtendedFeederSensor(SensorEntity, PetSafeExtendedEntity):
    """Representation of a feeder sensor."""

    def __init__(self, coordinator: Any, feeder: Any, description: SensorEntityDescription) -> None:
        """Initialize the feeder sensor."""
        super().__init__(
            coordinator,
            feeder.api_name,
            description,
            feeder,
            default_model=FEEDER_MODEL_GEN1,
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor state."""
        feeder = self._get_feeder()
        if feeder is None:
            return None

        if self.entity_description.key == "battery":
            return feeder.battery_level
        if self.entity_description.key == "food_level":
            if feeder.food_low_status == 0:
                return "full"
            if feeder.food_low_status == 1:
                return "low"
            return "empty"
        if self.entity_description.key == "signal_strength":
            return feeder.data.get("network_rssi")

        details = self.coordinator.data.feeder_details.get(self._api_name)
        if details is None:
            return None
        if self.entity_description.key == "last_feeding":
            return details.last_feeding
        if self.entity_description.key == "next_feeding":
            return details.next_feeding
        return None

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return super().available and self._get_feeder() is not None

    def _get_feeder(self) -> Any | None:
        """Return the current feeder object from coordinator data."""
        if self.coordinator.data is None:
            return None
        return next((feeder for feeder in self.coordinator.data.feeders if feeder.api_name == self._api_name), None)
