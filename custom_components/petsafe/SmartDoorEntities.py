"""Entity helpers for PetSafe SmartDoor devices."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.const import ATTR_BATTERY_LEVEL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

import petsafe

from petsafe.const import (
    SMARTDOOR_MODE_MANUAL_LOCKED,
    SMARTDOOR_MODE_MANUAL_UNLOCKED,
    SMARTDOOR_MODE_SMART,
)

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
        super().__init__(coordinator)
        self._door = device
        self._attr_has_entity_name = True
        self._attr_name = name or "Door"
        self._attr_unique_id = f"{device.api_name}_smartdoor_lock"

        model = device.data.get("productName")
        sw_version = device.firmware
        friendly_name = (
            getattr(device, "friendly_name", None)
            or device.data.get("friendlyName")
            or device.data.get("friendly_name")
            or device.api_name
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.api_name)},
            manufacturer=MANUFACTURER,
            model=model,
            name=friendly_name,
            sw_version=sw_version,
        )

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        door = self._door
        if door is None:
            return {}

        data = door.data if isinstance(door.data, Mapping) else {}
        friendly_name = (
            getattr(door, "friendly_name", None)
            or data.get("friendlyName")
            or data.get("friendly_name")
        )
        timezone = getattr(door, "timezone", None) or data.get("timezone")

        attributes = {
            "mode": door.mode,
            "latch_state": door.latch_state,
            "error_state": door.error_state,
            "has_adapter": door.has_adapter,
            "connection_status": door.connection_status,
            "battery_voltage": door.battery_voltage,
            "rssi": door.rssi,
            ATTR_BATTERY_LEVEL: door.battery_level,
        }

        if friendly_name is not None:
            attributes["friendly_name"] = friendly_name
        if timezone is not None:
            attributes["timezone"] = timezone

        return attributes

    @property
    def available(self) -> bool:
        door = self._door
        if door is None:
            return False
        connection = door.connection_status
        return connection is None or connection.lower() != "offline"

    @property
    def is_locked(self) -> bool | None:
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
        door = self._door
        if door is None:
            return None

        latch_state = door.latch_state
        if latch_state is None:
            return None
        return latch_state.lower() == "open"

    async def async_lock(self, **kwargs: Any) -> None:
        if self._door is None:
            return
        await self._door.lock(update_data=False)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: Any) -> None:
        if self._door is None:
            return
        await self._door.unlock(update_data=False)
        await self.coordinator.async_request_refresh()

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not data:
            return

        door = next(
            (
                smartdoor
                for smartdoor in data.smartdoors
                if smartdoor.api_name == self._door.api_name
            ),
            None,
        )
        if door is not None:
            self._door = door

        self.async_write_ha_state()
        super()._handle_coordinator_update()
