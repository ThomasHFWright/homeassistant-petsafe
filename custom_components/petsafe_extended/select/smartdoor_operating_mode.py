"""SmartDoor operating mode select entity."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.const import (
    SMARTDOOR_MODE_MANUAL_LOCKED,
    SMARTDOOR_MODE_MANUAL_UNLOCKED,
    SMARTDOOR_MODE_SMART,
)
from custom_components.petsafe_extended.entity.smartdoor_control import PetSafeExtendedSmartDoorControlEntity
from custom_components.petsafe_extended.utils.smartdoor import get_smartdoor_operating_mode_option
from homeassistant.components.select import SelectEntity, SelectEntityDescription

SMARTDOOR_OPERATING_MODE_OPTIONS = ["locked", "unlocked", "smart"]

SMARTDOOR_OPERATING_MODE_DESCRIPTION = SelectEntityDescription(
    key="operating_mode",
    name="Operating Mode",
    translation_key="operating_mode",
    options=SMARTDOOR_OPERATING_MODE_OPTIONS,
)

_OPTION_TO_MODE = {
    "locked": SMARTDOOR_MODE_MANUAL_LOCKED,
    "unlocked": SMARTDOOR_MODE_MANUAL_UNLOCKED,
    "smart": SMARTDOOR_MODE_SMART,
}


class PetSafeExtendedSmartDoorOperatingModeSelect(SelectEntity, PetSafeExtendedSmartDoorControlEntity):
    """Representation of the SmartDoor operating mode select."""

    def __init__(self, coordinator: Any, door: Any) -> None:
        """Initialize the SmartDoor operating mode select."""
        super().__init__(coordinator, door, SMARTDOOR_OPERATING_MODE_DESCRIPTION)

    @property
    def current_option(self) -> str | None:
        """Return the current SmartDoor operating mode option."""
        return get_smartdoor_operating_mode_option(self._door.mode if self._door is not None else None)

    async def async_select_option(self, option: str) -> None:
        """Change the SmartDoor operating mode."""
        self._door = await self.coordinator.async_set_smartdoor_operating_mode(self._api_name, _OPTION_TO_MODE[option])
