"""Sensor platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .feeder import FEEDER_SENSOR_DESCRIPTIONS, PetSafeExtendedFeederSensor
from .litterbox import LITTERBOX_SENSOR_DESCRIPTIONS, PetSafeExtendedLitterboxSensor
from .smartdoor_pet import (
    SMARTDOOR_PET_LAST_ACTIVITY_DESCRIPTION,
    SMARTDOOR_PET_LAST_SEEN_DESCRIPTION,
    PetSafeExtendedSmartDoorPetSensor,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    del hass
    coordinator = entry.runtime_data.coordinator

    try:
        feeders = filter_selected_devices(await coordinator.get_feeders(), entry.data.get("feeders"))
        litterboxes = filter_selected_devices(await coordinator.get_litterboxes(), entry.data.get("litterboxes"))
        smartdoors = filter_selected_devices(await coordinator.get_smartdoors(), entry.data.get("smartdoors"))
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe devices") from err

    entities: list[SensorEntity] = [
        PetSafeExtendedFeederSensor(coordinator, feeder, description)
        for feeder in feeders
        for description in FEEDER_SENSOR_DESCRIPTIONS
    ]
    entities.extend(
        PetSafeExtendedLitterboxSensor(coordinator, litterbox, description)
        for litterbox in litterboxes
        for description in LITTERBOX_SENSOR_DESCRIPTIONS
    )
    entities.extend(
        PetSafeExtendedSmartDoorPetSensor(coordinator, smartdoor, pet_id, description)
        for smartdoor in smartdoors
        for pet_id in coordinator.get_smartdoor_pet_ids(smartdoor.api_name)
        for description in (
            SMARTDOOR_PET_LAST_SEEN_DESCRIPTION,
            SMARTDOOR_PET_LAST_ACTIVITY_DESCRIPTION,
        )
    )

    if entities:
        async_add_entities(entities)
