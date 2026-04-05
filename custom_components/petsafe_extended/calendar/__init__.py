"""Calendar platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.const import (
    CONF_ENABLE_SMARTDOOR_SCHEDULES,
    DEFAULT_ENABLE_SMARTDOOR_SCHEDULES,
    DOMAIN,
)
from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.calendar import CalendarEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartdoor_schedule import PetSafeExtendedSmartDoorScheduleCalendar


def _async_update_calendar_entity_categories(hass: HomeAssistant, entities: list[CalendarEntity]) -> None:
    """Apply updated calendar entity categories to existing registry entries."""
    entity_registry = er.async_get(hass)

    for entity in entities:
        if entity.unique_id is None:
            continue

        entity_id = entity_registry.async_get_entity_id("calendar", DOMAIN, entity.unique_id)
        if entity_id is None:
            continue

        existing_entry = entity_registry.async_get(entity_id)
        if existing_entry is None or existing_entry.entity_category == entity.entity_category:
            continue

        entity_registry.async_update_entity(entity_id, entity_category=entity.entity_category)


def _build_smartdoor_schedule_calendars(
    coordinator,
    smartdoors: list,
    *,
    known_unique_ids: set[str] | None = None,
) -> list[CalendarEntity]:
    """Build SmartDoor per-pet schedule calendars, optionally excluding known entities."""
    known = known_unique_ids or set()
    entities: list[CalendarEntity] = []
    for smartdoor in smartdoors:
        for pet_id in coordinator.get_smartdoor_scheduled_pet_ids(smartdoor.api_name):
            entity = PetSafeExtendedSmartDoorScheduleCalendar(coordinator, smartdoor, pet_id)
            if entity.unique_id not in known:
                entities.append(entity)
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar platform."""
    if not entry.options.get(CONF_ENABLE_SMARTDOOR_SCHEDULES, DEFAULT_ENABLE_SMARTDOOR_SCHEDULES):
        return

    coordinator = entry.runtime_data.coordinator

    try:
        smartdoors = filter_selected_devices(await coordinator.get_smartdoors(), entry.data.get("smartdoors"))
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe devices") from err

    entities = _build_smartdoor_schedule_calendars(coordinator, smartdoors)
    if entities:
        _async_update_calendar_entity_categories(hass, entities)
        async_add_entities(entities)

    selected_smartdoor_api_names = {smartdoor.api_name for smartdoor in smartdoors}
    known_unique_ids = {entity.unique_id for entity in entities if entity.unique_id is not None}

    @callback
    def _async_add_new_smartdoor_schedule_calendars() -> None:
        if coordinator.data is None:
            return

        current_smartdoors = [
            smartdoor for smartdoor in coordinator.data.smartdoors if smartdoor.api_name in selected_smartdoor_api_names
        ]
        new_entities = _build_smartdoor_schedule_calendars(
            coordinator,
            current_smartdoors,
            known_unique_ids=known_unique_ids,
        )
        if not new_entities:
            return

        known_unique_ids.update(entity.unique_id for entity in new_entities if entity.unique_id is not None)
        _async_update_calendar_entity_categories(hass, new_entities)
        async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_smartdoor_schedule_calendars))
