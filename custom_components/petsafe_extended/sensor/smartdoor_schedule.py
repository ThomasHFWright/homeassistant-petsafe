"""SmartDoor schedule summary sensor entities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from custom_components.petsafe_extended.entity.smartdoor_schedule import PetSafeExtendedSmartDoorScheduleEntity
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory

SMARTDOOR_SCHEDULE_RULE_COUNT_DESCRIPTION = SensorEntityDescription(
    key="schedule_rule_count",
    name="Schedule Rule Count",
    translation_key="schedule_rule_count",
    icon="mdi:calendar-text",
    entity_category=EntityCategory.DIAGNOSTIC,
)

SMARTDOOR_ACTIVE_SCHEDULE_RULE_COUNT_DESCRIPTION = SensorEntityDescription(
    key="active_schedule_rule_count",
    name="Active Schedule Rule Count",
    translation_key="active_schedule_rule_count",
    icon="mdi:calendar-check",
    entity_category=EntityCategory.DIAGNOSTIC,
)

SMARTDOOR_SCHEDULE_SCHEDULED_PET_COUNT_DESCRIPTION = SensorEntityDescription(
    key="scheduled_pet_count",
    name="Scheduled Pet Count",
    translation_key="scheduled_pet_count",
    icon="mdi:paw",
    entity_category=EntityCategory.DIAGNOSTIC,
)


class PetSafeExtendedSmartDoorScheduleSensor(SensorEntity, PetSafeExtendedSmartDoorScheduleEntity):
    """Representation of a SmartDoor schedule summary sensor."""

    def __init__(
        self,
        coordinator: Any,
        door: Any,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the SmartDoor schedule sensor."""
        super().__init__(coordinator, door, description)

    @property
    def native_value(self) -> Any:
        """Return the current SmartDoor schedule summary state."""
        summary = self.coordinator.get_smartdoor_schedule_summary(self._api_name)
        if summary is None:
            return None

        if self.entity_description.key == SMARTDOOR_ACTIVE_SCHEDULE_RULE_COUNT_DESCRIPTION.key:
            return summary.enabled_schedule_count
        if self.entity_description.key == SMARTDOOR_SCHEDULE_SCHEDULED_PET_COUNT_DESCRIPTION.key:
            return summary.scheduled_pet_count
        return summary.schedule_rule_count

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the current SmartDoor schedule summary attributes."""
        summary = self.coordinator.get_smartdoor_schedule_summary(self._api_name)
        if summary is None:
            return {}

        attributes = {
            "enabled_schedule_count": summary.enabled_schedule_count,
            "disabled_schedule_count": summary.disabled_schedule_count,
            "scheduled_pet_count": summary.scheduled_pet_count,
            "next_schedule_change_at": summary.next_schedule_change_at,
            "next_schedule_title": summary.next_schedule_title,
            "next_schedule_access": summary.next_schedule_access,
            "next_schedule_pet": summary.next_schedule_pet_name,
        }
        return {key: value for key, value in attributes.items() if value not in (None, [], ())}
