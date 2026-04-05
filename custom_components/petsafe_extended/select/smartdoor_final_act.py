"""SmartDoor power-loss action select entity."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.const import SMARTDOOR_FINAL_ACT_LOCKED, SMARTDOOR_FINAL_ACT_UNLOCKED
from custom_components.petsafe_extended.entity.smartdoor_control import PetSafeExtendedSmartDoorControlEntity
from custom_components.petsafe_extended.utils.smartdoor import get_smartdoor_final_act_option
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory

SMARTDOOR_FINAL_ACT_OPTIONS = ["locked", "unlocked"]

SMARTDOOR_FINAL_ACT_DESCRIPTION = SelectEntityDescription(
    key="final_act",
    name="Power Loss Action",
    translation_key="final_act",
    options=SMARTDOOR_FINAL_ACT_OPTIONS,
    entity_category=EntityCategory.CONFIG,
)

_OPTION_TO_FINAL_ACT = {
    "locked": SMARTDOOR_FINAL_ACT_LOCKED,
    "unlocked": SMARTDOOR_FINAL_ACT_UNLOCKED,
}


class PetSafeExtendedSmartDoorFinalActSelect(SelectEntity, PetSafeExtendedSmartDoorControlEntity):
    """Representation of the SmartDoor power-loss action select."""

    def __init__(self, coordinator: Any, door: Any) -> None:
        """Initialize the SmartDoor final-act select."""
        super().__init__(coordinator, door, SMARTDOOR_FINAL_ACT_DESCRIPTION)

    @property
    def current_option(self) -> str | None:
        """Return the current SmartDoor final-act option."""
        return get_smartdoor_final_act_option(self._door)

    async def async_select_option(self, option: str) -> None:
        """Change the SmartDoor power-loss action."""
        self._door = await self.coordinator.async_set_smartdoor_final_act(self._api_name, _OPTION_TO_FINAL_ACT[option])
