"""Feeder diagnostic refresh buttons for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.const import FEEDER_MODEL_GEN1
from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory

FEEDER_REFRESH_BUTTON_DESCRIPTIONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="refresh_feeding_schedule_data",
        name="Refresh Schedule Data",
        translation_key="refresh_feeding_schedule_data",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:refresh",
    ),
)


class PetSafeExtendedFeederRefreshButton(ButtonEntity, PetSafeExtendedEntity):
    """Representation of a feeder schedule refresh button."""

    def __init__(self, coordinator: Any, feeder: Any, description: ButtonEntityDescription) -> None:
        """Initialize the feeder schedule refresh button."""
        super().__init__(
            coordinator,
            feeder.api_name,
            description,
            feeder,
            default_model=FEEDER_MODEL_GEN1,
        )

    async def async_press(self) -> None:
        """Force a feeder schedule refresh."""
        await self.coordinator.async_refresh_feeder_schedule_data(self._api_name)
