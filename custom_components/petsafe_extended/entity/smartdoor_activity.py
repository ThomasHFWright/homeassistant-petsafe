"""Shared SmartDoor activity event entity helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from custom_components.petsafe_extended.data import PetSafeExtendedSmartDoorActivityRecord
from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from custom_components.petsafe_extended.lock.smartdoor import SMARTDOOR_MODEL
from homeassistant.helpers.entity import EntityDescription


class PetSafeExtendedSmartDoorActivityEntity(PetSafeExtendedEntity):
    """Base class for SmartDoor activity event entities attached to the door device."""

    _door: Any

    def __init__(
        self,
        coordinator: Any,
        door: Any,
        entity_description: EntityDescription,
        pet_id: str | None = None,
    ) -> None:
        """Initialize a SmartDoor activity entity."""
        super().__init__(
            coordinator,
            door.api_name,
            entity_description,
            door,
            default_model=SMARTDOOR_MODEL,
        )
        self._door = door
        self._pet_id = pet_id
        if pet_id is None:
            self._attr_unique_id = f"{door.api_name}_{entity_description.key}"
        else:
            self._attr_unique_id = f"{door.api_name}_{pet_id}_{entity_description.key}"

    @property
    def name(self) -> str | None:
        """Return the user-facing entity name."""
        base_name = self.entity_description.name
        if not isinstance(base_name, str):
            return None
        if self._pet_id is None:
            return base_name
        pet_name = self.coordinator.get_pet_display_name(self._api_name, self._pet_id)
        return f"{pet_name} {base_name}"

    @property
    def available(self) -> bool:
        """Return whether the linked SmartDoor and optional pet are available."""
        if not super().available or self._get_door() is None:
            return False
        if self._pet_id is None:
            return True
        return self._pet_id in self.coordinator.get_smartdoor_pet_ids(self._api_name)

    def _get_door(self) -> Any | None:
        """Return the current SmartDoor device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return next((door for door in self.coordinator.data.smartdoors if door.api_name == self._api_name), None)

    def _build_event_attributes(self, record: PetSafeExtendedSmartDoorActivityRecord) -> Mapping[str, Any]:
        """Return privacy-safe event attributes for a SmartDoor activity record."""
        attributes: dict[str, Any] = {
            "occurred_at": record.timestamp.isoformat(),
            "raw_code": record.code,
        }
        if record.pet_id is not None:
            attributes["pet_name"] = self.coordinator.get_pet_display_name(self._api_name, record.pet_id)
        return attributes

    def _handle_coordinator_update(self) -> None:
        """Refresh the cached SmartDoor reference after coordinator updates."""
        if door := self._get_door():
            self._door = door
        super()._handle_coordinator_update()
