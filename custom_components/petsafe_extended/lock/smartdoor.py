"""SmartDoor lock entity for petsafe_extended."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from custom_components.petsafe_extended.utils.smartdoor import get_smartdoor_locked_state
from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.const import ATTR_BATTERY_LEVEL

SMARTDOOR_LOCK_DESCRIPTION = LockEntityDescription(
    key="smartdoor_lock",
    name="Door",
)
SMARTDOOR_MODEL = "SmartDoor"


class PetSafeExtendedSmartDoorLock(LockEntity, PetSafeExtendedEntity):
    """Representation of a PetSafe SmartDoor as a Home Assistant lock."""

    _door: Any

    def __init__(self, coordinator: Any, door: Any) -> None:
        """Initialize the SmartDoor lock entity."""
        super().__init__(
            coordinator,
            door.api_name,
            SMARTDOOR_LOCK_DESCRIPTION,
            door,
            default_model=SMARTDOOR_MODEL,
        )
        self._door = door

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return additional SmartDoor state attributes."""
        door = self._door
        if door is None:
            return {}

        return {
            "mode": door.mode,
            "latch_state": door.latch_state,
            "error_state": door.error_state,
            "has_adapter": door.has_adapter,
            "connection_status": door.connection_status,
            "battery_voltage": door.battery_voltage,
            "rssi": door.rssi,
            ATTR_BATTERY_LEVEL: door.battery_level,
        }

    @property
    def available(self) -> bool:
        """Return whether the SmartDoor is currently available."""
        door = self._door
        if not super().available or door is None:
            return False
        connection = door.connection_status
        return connection is None or connection.lower() != "offline"

    @property
    def is_locked(self) -> bool | None:
        """Return whether the SmartDoor is currently locked."""
        door = self._door
        if door is None:
            return None
        return get_smartdoor_locked_state(door.mode, door.latch_state)

    @property
    def is_open(self) -> bool | None:
        """Return whether the SmartDoor latch is currently open."""
        door = self._door
        if door is None or door.latch_state is None:
            return None
        return door.latch_state.lower() == "open"

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the SmartDoor and immediately refresh its state."""
        del kwargs
        self._door = await self.coordinator.async_set_smartdoor_lock(self._api_name, True)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the SmartDoor and immediately refresh its state."""
        del kwargs
        self._door = await self.coordinator.async_set_smartdoor_lock(self._api_name, False)

    async def async_update(self) -> None:
        """Request a full coordinator refresh."""
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        """Update the cached SmartDoor reference from coordinator data."""
        data = self.coordinator.data
        if data is not None:
            door = next((item for item in data.smartdoors if item.api_name == self._api_name), None)
            if door is not None:
                self._door = door

        super()._handle_coordinator_update()
