"""SmartDoor diagnostic refresh buttons for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory

SMARTDOOR_REFRESH_BUTTON_DESCRIPTIONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="refresh_schedule_data",
        name="Refresh Schedule Data",
        translation_key="refresh_schedule_data",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:refresh",
    ),
)


class PetSafeExtendedSmartDoorRefreshButton(ButtonEntity, PetSafeExtendedEntity):
    """Representation of a SmartDoor schedule refresh button."""

    def __init__(self, coordinator: Any, door: Any, description: ButtonEntityDescription) -> None:
        """Initialize the SmartDoor schedule refresh button."""
        super().__init__(
            coordinator,
            door.api_name,
            description,
            door,
            default_model="SmartDoor",
        )

    async def async_press(self) -> None:
        """Force a SmartDoor schedule refresh."""
        await self.coordinator.async_refresh_smartdoor_schedule_data(self._api_name)
