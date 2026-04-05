"""Shared SmartDoor pet entity helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from custom_components.petsafe_extended.lock.smartdoor import SMARTDOOR_MODEL
from homeassistant.helpers.entity import EntityDescription


class PetSafeExtendedSmartDoorPetEntity(PetSafeExtendedEntity):
    """Base class for SmartDoor pet entities attached to the door device."""

    _door: Any

    def __init__(
        self,
        coordinator: Any,
        door: Any,
        pet_id: str,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize a SmartDoor pet entity."""
        super().__init__(
            coordinator,
            door.api_name,
            entity_description,
            door,
            default_model=SMARTDOOR_MODEL,
        )
        self._door = door
        self._pet_id = pet_id
        self._attr_unique_id = f"{door.api_name}_{pet_id}_{entity_description.key}"

    @property
    def name(self) -> str | None:
        """Return the user-facing entity name."""
        base_name = self.entity_description.name
        if base_name is None:
            return None
        pet_name = self.coordinator.get_pet_display_name(self._api_name, self._pet_id)
        return f"{pet_name} {base_name}"

    @property
    def available(self) -> bool:
        """Return whether the linked SmartDoor and pet state are available."""
        if not super().available or self._get_door() is None:
            return False
        return self._pet_id in self._pet_ids_for_availability()

    def _pet_ids_for_availability(self) -> tuple[str, ...]:
        """Return the pet identifiers that should keep this entity available."""
        return self.coordinator.get_smartdoor_pet_ids(self._api_name)

    def _get_door(self) -> Any | None:
        """Return the current SmartDoor device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return next((door for door in self.coordinator.data.smartdoors if door.api_name == self._api_name), None)

    def _get_pet_profile_attributes(self) -> Mapping[str, Any]:
        """Return user-facing pet profile attributes."""
        profile = self.coordinator.get_pet_profile(self._pet_id)
        if profile is None:
            return {}

        attributes = {
            "pet_name": self.coordinator.get_pet_display_name(self._api_name, self._pet_id),
            "pet_type": profile.pet_type,
            "breed": profile.breed,
            "gender": profile.gender,
            "weight": profile.weight,
            "weight_unit": _normalize_weight_unit(profile.weight_unit),
            "technology": profile.technology,
        }
        return {key: value for key, value in attributes.items() if value not in (None, "")}

    def _handle_coordinator_update(self) -> None:
        """Refresh the cached SmartDoor reference after coordinator updates."""
        if door := self._get_door():
            self._door = door
        super()._handle_coordinator_update()


def _normalize_weight_unit(value: str | None) -> str | None:
    """Return a user-friendly weight unit from the PetSafe profile unit field."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized == "metric":
        return "kg"
    if normalized == "imperial":
        return "lb"
    return value
