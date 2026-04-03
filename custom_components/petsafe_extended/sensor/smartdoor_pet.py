"""SmartDoor pet sensor entities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from custom_components.petsafe_extended.coordinator.smartdoor_activity import (
    SMARTDOOR_PET_ACTIVITY_OPTIONS,
    SMARTDOOR_PET_ACTIVITY_UNKNOWN,
)
from custom_components.petsafe_extended.coordinator.smartdoor_schedules import (
    SMARTDOOR_SCHEDULE_ACCESS_OPTIONS,
    SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN,
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

SMARTDOOR_PET_SMART_ACCESS_DESCRIPTION = SensorEntityDescription(
    key="smart_access",
    name="Smart Access",
    translation_key="smart_access",
    device_class=SensorDeviceClass.ENUM,
    options=SMARTDOOR_SCHEDULE_ACCESS_OPTIONS,
)

SMARTDOOR_PET_NEXT_SMART_ACCESS_DESCRIPTION = SensorEntityDescription(
    key="next_smart_access",
    name="Next Smart Access",
    translation_key="next_smart_access",
    device_class=SensorDeviceClass.ENUM,
    options=SMARTDOOR_SCHEDULE_ACCESS_OPTIONS,
)

SMARTDOOR_PET_NEXT_SMART_ACCESS_CHANGE_DESCRIPTION = SensorEntityDescription(
    key="next_smart_access_change",
    name="Next Smart Access Change",
    translation_key="next_smart_access_change",
    device_class=SensorDeviceClass.TIMESTAMP,
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
        if self.entity_description.key == SMARTDOOR_PET_SMART_ACCESS_DESCRIPTION.key:
            schedule_state = self.coordinator.get_smartdoor_pet_schedule_state(self._api_name, self._pet_id)
            if schedule_state is None:
                return SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN
            return schedule_state.smart_access
        if self.entity_description.key == SMARTDOOR_PET_NEXT_SMART_ACCESS_DESCRIPTION.key:
            schedule_state = self.coordinator.get_smartdoor_pet_schedule_state(self._api_name, self._pet_id)
            if schedule_state is None or schedule_state.next_smart_access is None:
                return SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN
            return schedule_state.next_smart_access
        if self.entity_description.key == SMARTDOOR_PET_NEXT_SMART_ACCESS_CHANGE_DESCRIPTION.key:
            schedule_state = self.coordinator.get_smartdoor_pet_schedule_state(self._api_name, self._pet_id)
            if schedule_state is None:
                return None
            return schedule_state.next_change_at

        if pet_state is None:
            return None
        return pet_state.last_seen

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return user-facing pet profile attributes."""
        if self.entity_description.key == SMARTDOOR_PET_LAST_ACTIVITY_DESCRIPTION.key:
            return self._get_pet_profile_attributes()

        if self.entity_description.key in {
            SMARTDOOR_PET_SMART_ACCESS_DESCRIPTION.key,
            SMARTDOOR_PET_NEXT_SMART_ACCESS_DESCRIPTION.key,
            SMARTDOOR_PET_NEXT_SMART_ACCESS_CHANGE_DESCRIPTION.key,
        }:
            return self._get_schedule_attributes()
        return {}

    def _get_schedule_attributes(self) -> Mapping[str, Any]:
        """Return user-facing schedule-derived pet access attributes."""
        schedule_state = self.coordinator.get_smartdoor_pet_schedule_state(self._api_name, self._pet_id)
        if schedule_state is None:
            return {}

        attributes = {
            "effective_access": schedule_state.effective_access,
            "control_source": schedule_state.control_source,
            "active_schedule_title": schedule_state.active_schedule_title,
            "next_smart_access": schedule_state.next_smart_access,
            "next_schedule_title": schedule_state.next_schedule_title,
            "next_change_at": schedule_state.next_change_at,
        }
        return {key: value for key, value in attributes.items() if value not in (None, [], ())}
