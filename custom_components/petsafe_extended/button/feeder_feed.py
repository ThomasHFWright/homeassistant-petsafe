"""Feeder button entities for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.const import FEEDER_MODEL_GEN1
from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription

FEEDER_BUTTON_DESCRIPTIONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="feed",
        name="Feed",
    ),
)


class PetSafeExtendedFeederButton(ButtonEntity, PetSafeExtendedEntity):
    """Representation of a feeder button."""

    def __init__(self, coordinator: Any, feeder: Any, description: ButtonEntityDescription) -> None:
        """Initialize the feeder button."""
        super().__init__(
            coordinator,
            feeder.api_name,
            description,
            feeder,
            default_model=FEEDER_MODEL_GEN1,
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_feed_feeder(self._api_name, 1, None)
