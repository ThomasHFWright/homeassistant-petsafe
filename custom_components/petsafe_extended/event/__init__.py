"""Event platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartdoor_activity import PetSafeExtendedSmartDoorActivityEvent


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the event platform."""
    del hass
    coordinator = entry.runtime_data.coordinator

    try:
        smartdoors = filter_selected_devices(await coordinator.get_smartdoors(), entry.data.get("smartdoors"))
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe SmartDoor devices") from err

    entities: list[EventEntity] = [
        PetSafeExtendedSmartDoorActivityEvent(coordinator, smartdoor) for smartdoor in smartdoors
    ]
    entities.extend(
        PetSafeExtendedSmartDoorActivityEvent(coordinator, smartdoor, pet_id)
        for smartdoor in smartdoors
        for pet_id in coordinator.get_smartdoor_pet_ids(smartdoor.api_name)
    )

    if entities:
        async_add_entities(entities)
