"""Support for PetSafe SmartDoor locks."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from . import PetSafeCoordinator
from .SmartDoorEntities import PetSafeSmartDoorLockEntity
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, add_entities
) -> None:
    """Set up PetSafe SmartDoor lock entities."""

    coordinator: PetSafeCoordinator = hass.data[DOMAIN][config.entry_id]

    try:
        smartdoors = await coordinator.get_smartdoors()
    except Exception as exc:  # pylint: disable=broad-except
        raise ConfigEntryNotReady(
            "Failed to retrieve PetSafe SmartDoor devices"
        ) from exc

    entities = [
        PetSafeSmartDoorLockEntity(hass, smartdoor, coordinator, name="Door")
        for smartdoor in smartdoors
    ]

    if entities:
        add_entities(entities)
