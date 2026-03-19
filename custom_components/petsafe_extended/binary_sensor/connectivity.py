"""Connectivity binary sensor for petsafe_extended."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

if TYPE_CHECKING:
    from custom_components.petsafe_extended.coordinator import PetSafeExtendedDataUpdateCoordinator

ENTITY_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="api_connectivity",
        translation_key="api_connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:api",
        has_entity_name=True,
    ),
)


class PetSafeExtendedConnectivitySensor(BinarySensorEntity, PetSafeExtendedEntity):
    """Connectivity sensor for petsafe_extended."""

    def __init__(
        self,
        coordinator: PetSafeExtendedDataUpdateCoordinator,
        entity_description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entity_description)

    @property
    def is_on(self) -> bool:
        """Return true if the API connection is established."""
        # Connection is considered established if coordinator has valid data
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return additional state attributes."""
        return {
            "update_interval": str(self.coordinator.update_interval),
            "api_endpoint": "JSONPlaceholder (Demo)",
        }
