"""SmartDoor binary sensor entities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from custom_components.petsafe_extended.entity.smartdoor import PetSafeExtendedSmartDoorEntity
from custom_components.petsafe_extended.entity_utils.smartdoor_diagnostics import (
    normalize_smartdoor_connection_status,
    normalize_smartdoor_error_state,
    normalize_smartdoor_has_adapter,
    smartdoor_has_problem,
    smartdoor_is_connected,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

SMARTDOOR_AC_POWER_DESCRIPTION = BinarySensorEntityDescription(
    key="ac_power",
    name="AC Power",
    translation_key="ac_power",
    device_class=BinarySensorDeviceClass.PLUG,
    entity_category=EntityCategory.DIAGNOSTIC,
)

SMARTDOOR_CONNECTIVITY_DESCRIPTION = BinarySensorEntityDescription(
    key="connectivity",
    name="Connectivity",
    translation_key="connectivity",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)

SMARTDOOR_PROBLEM_DESCRIPTION = BinarySensorEntityDescription(
    key="problem",
    name="Problem",
    translation_key="problem",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
)

SMARTDOOR_BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    SMARTDOOR_AC_POWER_DESCRIPTION,
    SMARTDOOR_CONNECTIVITY_DESCRIPTION,
    SMARTDOOR_PROBLEM_DESCRIPTION,
)


class PetSafeExtendedSmartDoorBinarySensor(BinarySensorEntity, PetSafeExtendedSmartDoorEntity):
    """Representation of a SmartDoor binary sensor."""

    def __init__(self, coordinator: Any, door: Any, description: BinarySensorEntityDescription) -> None:
        """Initialize the SmartDoor binary sensor."""
        super().__init__(coordinator, door, description)

    @property
    def available(self) -> bool:
        """Return whether the binary sensor is available."""
        if self.entity_description.key != SMARTDOOR_CONNECTIVITY_DESCRIPTION.key:
            return super().available

        return self.coordinator.last_update_success and self._get_door() is not None

    @property
    def is_on(self) -> bool | None:
        """Return the current binary sensor state."""
        door = self._get_door()
        if door is None:
            return None

        if self.entity_description.key == SMARTDOOR_AC_POWER_DESCRIPTION.key:
            return normalize_smartdoor_has_adapter(getattr(door, "has_adapter", None))
        if self.entity_description.key == SMARTDOOR_CONNECTIVITY_DESCRIPTION.key:
            return smartdoor_is_connected(getattr(door, "connection_status", None))
        if self.entity_description.key == SMARTDOOR_PROBLEM_DESCRIPTION.key:
            return smartdoor_has_problem(getattr(door, "error_state", None))
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return additional attributes for SmartDoor binary sensors."""
        door = self._get_door()
        if door is None:
            return {}

        if self.entity_description.key == SMARTDOOR_CONNECTIVITY_DESCRIPTION.key:
            connection_status = normalize_smartdoor_connection_status(getattr(door, "connection_status", None))
            if connection_status is None:
                return {}
            return {"connection_status": connection_status}

        if self.entity_description.key != SMARTDOOR_PROBLEM_DESCRIPTION.key:
            return {}

        error_state = normalize_smartdoor_error_state(getattr(door, "error_state", None))
        if error_state is None:
            return {}
        return {"error_state": error_state}
