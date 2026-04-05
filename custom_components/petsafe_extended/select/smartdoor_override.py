"""SmartDoor schedule override select entity."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.entity.smartdoor_control import PetSafeExtendedSmartDoorControlEntity
from custom_components.petsafe_extended.entity_utils.smartdoor_access import (
    SMARTDOOR_ACCESS_SMART_SCHEDULE,
    SMARTDOOR_OVERRIDE_OPTIONS,
)
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.exceptions import HomeAssistantError

SMARTDOOR_OVERRIDE_DESCRIPTION = SelectEntityDescription(
    key="smart_override",
    name="Smart Override",
    translation_key="smart_override",
    options=SMARTDOOR_OVERRIDE_OPTIONS,
)


class PetSafeExtendedSmartDoorOverrideSelect(SelectEntity, PetSafeExtendedSmartDoorControlEntity):
    """Representation of the SmartDoor temporary schedule override select."""

    def __init__(self, coordinator: Any, door: Any) -> None:
        """Initialize the SmartDoor override select."""
        super().__init__(coordinator, door, SMARTDOOR_OVERRIDE_DESCRIPTION)

    @property
    def current_option(self) -> str:
        """Return the current SmartDoor override option."""
        return self.coordinator.get_smartdoor_override_option(self._api_name)

    async def async_select_option(self, option: str) -> None:
        """Change the SmartDoor override option."""
        if option == SMARTDOOR_ACCESS_SMART_SCHEDULE:
            if self.current_option == SMARTDOOR_ACCESS_SMART_SCHEDULE:
                return
            raise HomeAssistantError(
                "PetSafe does not expose a direct way to clear Smart Override. "
                "It clears at the next schedule event or in the PetSafe app."
            )

        self._door = await self.coordinator.async_set_smartdoor_override(self._api_name, option)
