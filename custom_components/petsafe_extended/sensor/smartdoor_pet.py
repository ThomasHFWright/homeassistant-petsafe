"""SmartDoor pet sensor entities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from custom_components.petsafe_extended.coordinator.smartdoor_activity import (
    SMARTDOOR_PET_ACTIVITY_OPTIONS,
    SMARTDOOR_PET_ACTIVITY_UNKNOWN,
)
from custom_components.petsafe_extended.entity.smartdoor_pet import PetSafeExtendedSmartDoorPetEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription

SMARTDOOR_PET_LAST_SEEN_DESCRIPTION = SensorEntityDescription(
    key="last_seen",
    name="Last Seen",
    translation_key="last_seen",
    device_class=SensorDeviceClass.TIMESTAMP,
)

SMARTDOOR_PET_LAST_ACTIVITY_DESCRIPTION = SensorEntityDescription(
    key="last_activity",
    name="Last Activity",
    translation_key="last_activity",
    device_class=SensorDeviceClass.ENUM,
    options=SMARTDOOR_PET_ACTIVITY_OPTIONS,
)


class PetSafeExtendedSmartDoorPetSensor(SensorEntity, PetSafeExtendedSmartDoorPetEntity):
    """Representation of a SmartDoor pet status sensor."""

    def __init__(
        self,
        coordinator: Any,
        door: Any,
        pet_id: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the SmartDoor pet sensor."""
        super().__init__(coordinator, door, pet_id, description)

    @property
    def native_value(self) -> Any:
        """Return the current SmartDoor pet sensor state."""
        pet_state = self.coordinator.get_smartdoor_pet_state(self._api_name, self._pet_id)
        if self.entity_description.key == SMARTDOOR_PET_LAST_ACTIVITY_DESCRIPTION.key:
            if pet_state is None:
                return SMARTDOOR_PET_ACTIVITY_UNKNOWN
            return pet_state.last_activity

        if pet_state is None:
            return None
        return pet_state.last_seen

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return user-facing pet profile attributes."""
        if self.entity_description.key != SMARTDOOR_PET_LAST_ACTIVITY_DESCRIPTION.key:
            return {}
        return self._get_pet_profile_attributes()
