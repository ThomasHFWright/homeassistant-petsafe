"""Lock platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartdoor import PetSafeExtendedSmartDoorLock


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SmartDoor lock platform."""
    del hass
    coordinator = entry.runtime_data.coordinator

    try:
        smartdoors = filter_selected_devices(await coordinator.get_smartdoors(), entry.data.get("smartdoors"))
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe SmartDoor devices") from err

    entities = [PetSafeExtendedSmartDoorLock(coordinator, smartdoor) for smartdoor in smartdoors]
    if entities:
        async_add_entities(entities)
