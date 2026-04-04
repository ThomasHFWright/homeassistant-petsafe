"""Calendar platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.const import CONF_ENABLE_SMARTDOOR_SCHEDULES, DEFAULT_ENABLE_SMARTDOOR_SCHEDULES
from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.calendar import CalendarEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartdoor_schedule import PetSafeExtendedSmartDoorScheduleCalendar


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

    entities: list[CalendarEntity] = [
        PetSafeExtendedSmartDoorScheduleCalendar(coordinator, smartdoor, pet_id)
        for smartdoor in smartdoors
        for pet_id in coordinator.get_smartdoor_scheduled_pet_ids(smartdoor.api_name)
    ]
    if entities:
        async_add_entities(entities)
