"""Switch platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .feeder_control import FEEDER_SWITCH_DESCRIPTIONS, PetSafeExtendedFeederSwitch


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    del hass
    coordinator = entry.runtime_data.coordinator

    try:
        feeders = filter_selected_devices(await coordinator.get_feeders(), entry.data.get("feeders"))
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe SmartFeed devices") from err

    entities = [
        PetSafeExtendedFeederSwitch(coordinator, feeder, description)
        for feeder in feeders
        for description in FEEDER_SWITCH_DESCRIPTIONS
    ]
    if entities:
        async_add_entities(entities)
