"""Shared SmartDoor control entity helpers."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from custom_components.petsafe_extended.lock.smartdoor import SMARTDOOR_MODEL
from homeassistant.helpers.entity import EntityDescription


class PetSafeExtendedSmartDoorControlEntity(PetSafeExtendedEntity):
    """Base class for SmartDoor controls attached to the door device."""

    _door: Any

    def __init__(
        self,
        coordinator: Any,
        door: Any,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize a SmartDoor control entity."""
        super().__init__(
            coordinator,
            door.api_name,
            entity_description,
            door,
            default_model=SMARTDOOR_MODEL,
        )
        self._door = door

    @property
    def available(self) -> bool:
        """Return whether the linked SmartDoor is available."""
        if not super().available or self._get_door() is None:
            return False
        connection = self._door.connection_status
        return connection is None or connection.lower() != "offline"

    def _get_door(self) -> Any | None:
        """Return the current SmartDoor device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return next((door for door in self.coordinator.data.smartdoors if door.api_name == self._api_name), None)

    def _handle_coordinator_update(self) -> None:
        """Refresh the cached SmartDoor reference after coordinator updates."""
        if door := self._get_door():
            self._door = door
        super()._handle_coordinator_update()
