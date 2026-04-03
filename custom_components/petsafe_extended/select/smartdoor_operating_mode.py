"""SmartDoor locked-mode preference select entity."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.const import SMARTDOOR_MODE_MANUAL_LOCKED, SMARTDOOR_MODE_SMART
from custom_components.petsafe_extended.entity.smartdoor_control import PetSafeExtendedSmartDoorControlEntity
from custom_components.petsafe_extended.utils.smartdoor import get_smartdoor_locked_mode_option
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

SMARTDOOR_OPERATING_MODE_OPTIONS = ["locked", "smart"]

SMARTDOOR_OPERATING_MODE_DESCRIPTION = SelectEntityDescription(
    key="operating_mode",
    name="Locked Mode",
    translation_key="operating_mode",
    options=SMARTDOOR_OPERATING_MODE_OPTIONS,
    entity_category=EntityCategory.CONFIG,
)

_OPTION_TO_MODE = {
    "locked": SMARTDOOR_MODE_MANUAL_LOCKED,
    "smart": SMARTDOOR_MODE_SMART,
}


class PetSafeExtendedSmartDoorOperatingModeSelect(SelectEntity, RestoreEntity, PetSafeExtendedSmartDoorControlEntity):
    """Representation of the SmartDoor locked-mode preference select."""

    def __init__(self, coordinator: Any, door: Any) -> None:
        """Initialize the SmartDoor locked-mode preference select."""
        super().__init__(coordinator, door, SMARTDOOR_OPERATING_MODE_DESCRIPTION)

    async def async_added_to_hass(self) -> None:
        """Restore the locked-mode preference when the door is currently unlocked."""
        await super().async_added_to_hass()

        if self._door is None:
            return

        if get_smartdoor_locked_mode_option(getattr(self._door, "mode", None)) is not None:
            return

        if (last_state := await self.async_get_last_state()) is None:
            return

        if last_state.state not in SMARTDOOR_OPERATING_MODE_OPTIONS:
            return

        self.coordinator.async_set_smartdoor_locked_mode_preference(
            self._api_name,
            _OPTION_TO_MODE[last_state.state],
        )

    @property
    def current_option(self) -> str | None:
        """Return the current SmartDoor locked-mode option."""
        if (
            self._door is not None
            and (live_option := get_smartdoor_locked_mode_option(getattr(self._door, "mode", None))) is not None
        ):
            return live_option

        return self.coordinator.get_smartdoor_locked_mode_option(self._api_name)

    async def async_select_option(self, option: str) -> None:
        """Change the SmartDoor locked-mode preference."""
        self._door = await self.coordinator.async_set_smartdoor_locked_mode(self._api_name, _OPTION_TO_MODE[option])
