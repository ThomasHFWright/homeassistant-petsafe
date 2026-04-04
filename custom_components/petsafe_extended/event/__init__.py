"""Event platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartdoor_activity import PetSafeExtendedSmartDoorActivityEvent


def _build_smartdoor_pet_activity_entities(
    coordinator,
    smartdoors: list,
    *,
    known_unique_ids: set[str] | None = None,
) -> list[EventEntity]:
    """Build per-pet SmartDoor activity events, optionally excluding known entities."""
    known = known_unique_ids or set()
    entities: list[EventEntity] = []
    for smartdoor in smartdoors:
        for pet_id in coordinator.get_smartdoor_pet_ids(smartdoor.api_name):
            entity = PetSafeExtendedSmartDoorActivityEvent(coordinator, smartdoor, pet_id)
            if entity.unique_id not in known:
                entities.append(entity)
    return entities


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
    entities.extend(_build_smartdoor_pet_activity_entities(coordinator, smartdoors))

    if entities:
        async_add_entities(entities)

    selected_smartdoor_api_names = {smartdoor.api_name for smartdoor in smartdoors}
    known_unique_ids = {entity.unique_id for entity in entities if entity.unique_id is not None}

    @callback
    def _async_add_new_smartdoor_pet_events() -> None:
        if coordinator.data is None:
            return

        current_smartdoors = [
            smartdoor for smartdoor in coordinator.data.smartdoors if smartdoor.api_name in selected_smartdoor_api_names
        ]
        new_entities = _build_smartdoor_pet_activity_entities(
            coordinator,
            current_smartdoors,
            known_unique_ids=known_unique_ids,
        )
        if not new_entities:
            return

        known_unique_ids.update(entity.unique_id for entity in new_entities if entity.unique_id is not None)
        async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_smartdoor_pet_events))
