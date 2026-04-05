"""Litterbox sensor entities for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory

LITTERBOX_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="rake_counter",
        name="Rake Counter",
        icon="mdi:rake",
    ),
    SensorEntityDescription(
        key="rake_status",
        name="Rake Status",
        icon="mdi:rake",
    ),
    SensorEntityDescription(
        key="signal_strength",
        name="Signal Strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_cleaning",
        name="Last Cleaning",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)


class PetSafeExtendedLitterboxSensor(SensorEntity, PetSafeExtendedEntity):
    """Representation of a litterbox sensor."""

    def __init__(self, coordinator: Any, litterbox: Any, description: SensorEntityDescription) -> None:
        """Initialize the litterbox sensor."""
        super().__init__(coordinator, litterbox.api_name, description, litterbox)

    @property
    def native_value(self) -> Any:
        """Return the sensor state."""
        litterbox = self._get_litterbox()
        if litterbox is None:
            return None

        reported_state = litterbox.data.get("shadow", {}).get("state", {}).get("reported", {})
        if self.entity_description.key == "rake_counter":
            return reported_state.get("rakeCount")
        if self.entity_description.key == "signal_strength":
            return reported_state.get("rssi")

        details = self.coordinator.data.litterbox_details.get(self._api_name)
        if details is None:
            return None
        if self.entity_description.key == "rake_status":
            return details.rake_status
        if self.entity_description.key == "last_cleaning":
            return details.last_cleaning
        return None

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return super().available and self._get_litterbox() is not None

    def _get_litterbox(self) -> Any | None:
        """Return the current litterbox object from coordinator data."""
        if self.coordinator.data is None:
            return None
        return next(
            (litterbox for litterbox in self.coordinator.data.litterboxes if litterbox.api_name == self._api_name),
            None,
        )
