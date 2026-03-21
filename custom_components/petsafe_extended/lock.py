"""Support for PetSafe SmartDoor locks."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PetSafeCoordinator
from .const import DOMAIN
from .helpers import filter_selected_devices
from .SmartDoorEntities import PetSafeSmartDoorLockEntity


async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up PetSafe SmartDoor lock entities."""

    coordinator: PetSafeCoordinator = hass.data[DOMAIN][config.entry_id]

    try:
        smartdoors = filter_selected_devices(await coordinator.get_smartdoors(), config.data.get("smartdoors"))
    except Exception as exc:  # pylint: disable=broad-except
        raise ConfigEntryNotReady("Failed to retrieve PetSafe SmartDoor devices") from exc

    entities = [PetSafeSmartDoorLockEntity(hass, smartdoor, coordinator, name="Door") for smartdoor in smartdoors]

    if entities:
        async_add_entities(entities)
