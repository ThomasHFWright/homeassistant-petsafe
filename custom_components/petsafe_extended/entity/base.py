"""Base entity helpers for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.const import ATTRIBUTION
from custom_components.petsafe_extended.coordinator import PetSafeExtendedDataUpdateCoordinator
from custom_components.petsafe_extended.entity_utils import create_device_info_from_device
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity


class PetSafeExtendedEntity(CoordinatorEntity[PetSafeExtendedDataUpdateCoordinator]):
    """Base entity for PetSafe devices backed by the coordinator."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PetSafeExtendedDataUpdateCoordinator,
        api_name: str,
        entity_description: EntityDescription,
        device: Any,
        *,
        default_model: str | None = None,
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._api_name = api_name
        self.entity_description = entity_description
        self._attr_entity_category = entity_description.entity_category
        self._attr_entity_registry_enabled_default = getattr(
            entity_description,
            "entity_registry_enabled_default",
            True,
        )
        self._attr_unique_id = f"{api_name}_{entity_description.key}"
        self._attr_device_info = create_device_info_from_device(
            device,
            default_model=default_model,
        )
