"""SmartDoor binary sensor entities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from custom_components.petsafe_extended.entity.smartdoor import PetSafeExtendedSmartDoorEntity
from custom_components.petsafe_extended.entity_utils.smartdoor_diagnostics import (
    normalize_smartdoor_error_state,
    normalize_smartdoor_has_adapter,
    smartdoor_has_problem,
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
    SMARTDOOR_PROBLEM_DESCRIPTION,
)


class PetSafeExtendedSmartDoorBinarySensor(BinarySensorEntity, PetSafeExtendedSmartDoorEntity):
    """Representation of a SmartDoor binary sensor."""

    def __init__(self, coordinator: Any, door: Any, description: BinarySensorEntityDescription) -> None:
        """Initialize the SmartDoor binary sensor."""
        super().__init__(coordinator, door, description)

    @property
    def is_on(self) -> bool | None:
        """Return the current binary sensor state."""
        door = self._get_door()
        if door is None:
            return None

        if self.entity_description.key == SMARTDOOR_AC_POWER_DESCRIPTION.key:
            return normalize_smartdoor_has_adapter(getattr(door, "has_adapter", None))
        if self.entity_description.key == SMARTDOOR_PROBLEM_DESCRIPTION.key:
            return smartdoor_has_problem(getattr(door, "error_state", None))
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return additional attributes for SmartDoor binary sensors."""
        if self.entity_description.key != SMARTDOOR_PROBLEM_DESCRIPTION.key:
            return {}

        door = self._get_door()
        if door is None:
            return {}

        error_state = normalize_smartdoor_error_state(getattr(door, "error_state", None))
        if error_state is None:
            return {}
        return {"error_state": error_state}
