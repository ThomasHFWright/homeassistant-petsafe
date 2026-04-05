"""Binary sensor platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.const import DOMAIN
from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartdoor import SMARTDOOR_BINARY_SENSOR_DESCRIPTIONS, PetSafeExtendedSmartDoorBinarySensor


def _async_update_binary_sensor_entity_categories(
    hass: HomeAssistant,
    entities: list[BinarySensorEntity],
) -> None:
    """Apply updated binary sensor categories to existing registry entries."""
    entity_registry = er.async_get(hass)

    for entity in entities:
        if entity.entity_category is None or entity.unique_id is None:
            continue

        entity_id = entity_registry.async_get_entity_id("binary_sensor", DOMAIN, entity.unique_id)
        if entity_id is None:
            continue

        existing_entry = entity_registry.async_get(entity_id)
        if existing_entry is None or existing_entry.entity_category == entity.entity_category:
            continue

        entity_registry.async_update_entity(entity_id, entity_category=entity.entity_category)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator = entry.runtime_data.coordinator

    try:
        smartdoors = filter_selected_devices(await coordinator.get_smartdoors(), entry.data.get("smartdoors"))
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe SmartDoor devices") from err

    entities: list[BinarySensorEntity] = [
        PetSafeExtendedSmartDoorBinarySensor(coordinator, smartdoor, description)
        for smartdoor in smartdoors
        for description in SMARTDOOR_BINARY_SENSOR_DESCRIPTIONS
    ]
    if entities:
        _async_update_binary_sensor_entity_categories(hass, entities)
        async_add_entities(entities)
        _async_update_binary_sensor_entity_categories(hass, entities)
