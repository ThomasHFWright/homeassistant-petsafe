"""Calendar platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.const import CONF_ENABLE_SMARTDOOR_SCHEDULES, DEFAULT_ENABLE_SMARTDOOR_SCHEDULES
from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.calendar import CalendarEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartdoor_schedule import PetSafeExtendedSmartDoorScheduleCalendar


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
    del hass
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
        async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_smartdoor_schedule_calendars))
