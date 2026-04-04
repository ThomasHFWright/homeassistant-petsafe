"""Shared SmartDoor entity helpers."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.helpers.entity import EntityDescription

SMARTDOOR_MODEL = "SmartDoor"


class PetSafeExtendedSmartDoorEntity(PetSafeExtendedEntity):
    """Base class for entities attached to a SmartDoor device."""

    _door: Any

    def __init__(
        self,
        coordinator: Any,
        door: Any,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize a SmartDoor entity."""
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
        """Return whether the SmartDoor is currently available."""
        door = self._get_door()
        if not super().available or door is None:
            return False
        connection = getattr(door, "connection_status", None)
        return connection is None or str(connection).lower() != "offline"

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
