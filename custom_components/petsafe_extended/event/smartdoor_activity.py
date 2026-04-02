"""SmartDoor activity event entities."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.coordinator.smartdoor_activity import SMARTDOOR_ACTIVITY_EVENT_TYPES
from custom_components.petsafe_extended.data import PetSafeExtendedSmartDoorActivityRecord
from custom_components.petsafe_extended.entity.smartdoor_activity import PetSafeExtendedSmartDoorActivityEntity
from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import callback

SMARTDOOR_ACTIVITY_EVENT_DESCRIPTION = EventEntityDescription(
    key="activity",
    name="Activity",
    event_types=SMARTDOOR_ACTIVITY_EVENT_TYPES,
)


class PetSafeExtendedSmartDoorActivityEvent(EventEntity, PetSafeExtendedSmartDoorActivityEntity):
    """Representation of SmartDoor activity as a Home Assistant event entity."""

    def __init__(
        self,
        coordinator: Any,
        door: Any,
        pet_id: str | None = None,
    ) -> None:
        """Initialize the SmartDoor activity event entity."""
        super().__init__(coordinator, door, SMARTDOOR_ACTIVITY_EVENT_DESCRIPTION, pet_id)

    async def async_added_to_hass(self) -> None:
        """Register activity callbacks when added to Home Assistant."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_subscribe_smartdoor_activity(self._api_name, self._async_handle_activity)
        )

    @callback
    def _async_handle_activity(self, record: PetSafeExtendedSmartDoorActivityRecord) -> None:
        """Handle a new SmartDoor activity record."""
        if self._pet_id is not None and record.pet_id != self._pet_id:
            return
        self._trigger_event(record.event_type, dict(self._build_event_attributes(record)))
        self.async_write_ha_state()
