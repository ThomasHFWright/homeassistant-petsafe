"""Litterbox button entities for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription

LITTERBOX_BUTTON_DESCRIPTIONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="clean",
        name="Clean",
    ),
    ButtonEntityDescription(
        key="reset",
        name="Reset",
    ),
)


class PetSafeExtendedLitterboxButton(ButtonEntity, PetSafeExtendedEntity):
    """Representation of a litterbox button."""

    def __init__(self, coordinator: Any, litterbox: Any, description: ButtonEntityDescription) -> None:
        """Initialize the litterbox button."""
        super().__init__(coordinator, litterbox.api_name, description, litterbox)

    async def async_press(self) -> None:
        """Handle the button press."""
        if self.entity_description.key == "clean":
            await self.coordinator.async_rake_litterbox(self._api_name)
            return
        await self.coordinator.async_reset_litterbox(self._api_name)
