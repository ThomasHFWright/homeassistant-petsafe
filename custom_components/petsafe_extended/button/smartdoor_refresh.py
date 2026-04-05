"""SmartDoor diagnostic refresh buttons for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components import petsafe_extended as integration_module
from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory

SMARTDOOR_REFRESH_BUTTON_DESCRIPTIONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="refresh_pet_data",
        name="Refresh Pet Data",
        translation_key="refresh_pet_data",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:refresh",
    ),
    ButtonEntityDescription(
        key="refresh_schedule_data",
        name="Refresh Schedule Data",
        translation_key="refresh_schedule_data",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:refresh",
    ),
)


class PetSafeExtendedSmartDoorRefreshButton(ButtonEntity, PetSafeExtendedEntity):
    """Representation of a SmartDoor maintenance refresh button."""

    def __init__(self, coordinator: Any, door: Any, description: ButtonEntityDescription) -> None:
        """Initialize the SmartDoor maintenance refresh button."""
        super().__init__(
            coordinator,
            door.api_name,
            description,
            door,
            default_model="SmartDoor",
        )

    async def async_press(self) -> None:
        """Force a SmartDoor pet or schedule refresh."""
        if self.hass is None:
            return

        config_entry = self.coordinator.config_entry
        if self.entity_description.key == "refresh_pet_data":
            old_pet_ids = set(self.coordinator.get_smartdoor_pet_ids(self._api_name))
            await self.coordinator.async_refresh_pet_links()
            new_pet_ids = set(self.coordinator.get_smartdoor_pet_ids(self._api_name))
            integration_module._async_remove_smartdoor_pet_entities(  # noqa: SLF001
                self.hass,
                config_entry,
                {self._api_name: old_pet_ids | new_pet_ids},
            )
            await self.hass.config_entries.async_reload(config_entry.entry_id)
            return

        old_scheduled_pet_ids = set(self.coordinator.get_smartdoor_scheduled_pet_ids(self._api_name))
        await self.coordinator.async_refresh_smartdoor_schedule_data(self._api_name)
        new_scheduled_pet_ids = set(self.coordinator.get_smartdoor_scheduled_pet_ids(self._api_name))
        integration_module._async_remove_smartdoor_pet_entities(  # noqa: SLF001
            self.hass,
            config_entry,
            {self._api_name: old_scheduled_pet_ids | new_scheduled_pet_ids},
            schedule_only=True,
        )
        await self.hass.config_entries.async_reload(config_entry.entry_id)
