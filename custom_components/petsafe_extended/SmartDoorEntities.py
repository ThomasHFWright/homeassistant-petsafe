"""Entity helpers for PetSafe SmartDoor devices."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import petsafe
from petsafe.const import SMARTDOOR_MODE_MANUAL_LOCKED, SMARTDOOR_MODE_MANUAL_UNLOCKED, SMARTDOOR_MODE_SMART

from homeassistant.components.lock import LockEntity
from homeassistant.const import ATTR_BATTERY_LEVEL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PetSafeCoordinator, PetSafeData
from .const import DOMAIN, MANUFACTURER


class PetSafeSmartDoorLockEntity(CoordinatorEntity[PetSafeData], LockEntity):
    """Representation of a PetSafe SmartDoor as a Home Assistant lock."""

    _door: petsafe.devices.DeviceSmartDoor | None

    def __init__(
        self,
        hass: HomeAssistant,
        device: petsafe.devices.DeviceSmartDoor,
        coordinator: PetSafeCoordinator,
        *,
        name: str | None = None,
    ) -> None:
        """Initialize the SmartDoor lock entity."""
        super().__init__(coordinator)
        self._door = device
        self._attr_has_entity_name = True
        self._attr_name = name or "Door"
        self._attr_unique_id = f"{device.api_name}_smartdoor_lock"

        model = device.data.get("productName")
        sw_version = device.firmware
        friendly_name = device.data.get("friendlyName") or device.api_name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.api_name)},
            manufacturer=MANUFACTURER,
            model=model,
            name=friendly_name,
            sw_version=sw_version,
        )

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
        if door is None:
            return False
        connection = door.connection_status
        return connection is None or connection.lower() != "offline"

    @property
    def is_locked(self) -> bool | None:
        """Return whether the SmartDoor is currently locked."""
        door = self._door
        if door is None:
            return None

        mode = door.mode
        if mode == SMARTDOOR_MODE_MANUAL_LOCKED:
            return True
        if mode in (SMARTDOOR_MODE_MANUAL_UNLOCKED, SMARTDOOR_MODE_SMART):
            return False
        return None

    @property
    def is_open(self) -> bool | None:
        """Return whether the SmartDoor latch is currently open."""
        door = self._door
        if door is None:
            return None

        latch_state = door.latch_state
        if latch_state is None:
            return None
        return latch_state.lower() == "open"

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the SmartDoor and immediately refresh its state."""
        if self._door is None:
            return
        self._door = await self._async_execute_door_command(
            self._door.lock,
            expected_mode=SMARTDOOR_MODE_MANUAL_LOCKED,
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the SmartDoor and immediately refresh its state."""
        if self._door is None:
            return
        self._door = await self._async_execute_door_command(
            self._door.unlock,
            expected_mode=SMARTDOOR_MODE_MANUAL_UNLOCKED,
        )

    async def async_update(self) -> None:
        """Request a full coordinator refresh."""
        await self.coordinator.async_request_refresh()

    async def _async_execute_door_command(
        self,
        command: Any,
        *,
        expected_mode: str,
    ) -> petsafe.devices.DeviceSmartDoor:
        """Execute a SmartDoor command and refresh its live state immediately."""
        if self._door is None:
            raise RuntimeError("SmartDoor device is not initialized")

        await command(update_data=False)
        return await self.coordinator.async_refresh_smartdoor(
            self._door.api_name,
            expected_mode=expected_mode,
        )

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not data:
            return

        door = next(
            (smartdoor for smartdoor in data.smartdoors if smartdoor.api_name == self._door.api_name),
            None,
        )
        if door is not None:
            self._door = door

        self.async_write_ha_state()
        super()._handle_coordinator_update()
