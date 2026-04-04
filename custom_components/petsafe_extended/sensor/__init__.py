"""Sensor platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.const import (
    CONF_ENABLE_SMARTDOOR_SCHEDULES,
    DEFAULT_ENABLE_SMARTDOOR_SCHEDULES,
    DOMAIN,
)
from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .feeder import FEEDER_SENSOR_DESCRIPTIONS, PetSafeExtendedFeederSensor
from .litterbox import LITTERBOX_SENSOR_DESCRIPTIONS, PetSafeExtendedLitterboxSensor
from .smartdoor_diagnostic import SMARTDOOR_DIAGNOSTIC_SENSOR_DESCRIPTIONS, PetSafeExtendedSmartDoorDiagnosticSensor
from .smartdoor_pet import (
    SMARTDOOR_PET_LAST_ACTIVITY_DESCRIPTION,
    SMARTDOOR_PET_LAST_SEEN_DESCRIPTION,
    SMARTDOOR_PET_NEXT_SMART_ACCESS_CHANGE_DESCRIPTION,
    SMARTDOOR_PET_NEXT_SMART_ACCESS_DESCRIPTION,
    SMARTDOOR_PET_SMART_ACCESS_DESCRIPTION,
    PetSafeExtendedSmartDoorPetSensor,
)
from .smartdoor_schedule import (
    SMARTDOOR_SCHEDULE_RULE_COUNT_DESCRIPTION,
    SMARTDOOR_SCHEDULE_SCHEDULED_PET_COUNT_DESCRIPTION,
    PetSafeExtendedSmartDoorScheduleSensor,
)


def _async_update_sensor_entity_categories(hass: HomeAssistant, entities: list[SensorEntity]) -> None:
    """Apply updated sensor entity categories to existing registry entries."""
    entity_registry = er.async_get(hass)

    for entity in entities:
        if entity.entity_category is None or entity.unique_id is None:
            continue

        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, entity.unique_id)
        if entity_id is None:
            continue

        existing_entry = entity_registry.async_get(entity_id)
        if existing_entry is None or existing_entry.entity_category == entity.entity_category:
            continue

        entity_registry.async_update_entity(entity_id, entity_category=entity.entity_category)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data.coordinator
    schedules_enabled = entry.options.get(CONF_ENABLE_SMARTDOOR_SCHEDULES, DEFAULT_ENABLE_SMARTDOOR_SCHEDULES)

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
        PetSafeExtendedSmartDoorDiagnosticSensor(coordinator, smartdoor, description)
        for smartdoor in smartdoors
        for description in SMARTDOOR_DIAGNOSTIC_SENSOR_DESCRIPTIONS
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
    if schedules_enabled:
        entities.extend(
            PetSafeExtendedSmartDoorPetSensor(coordinator, smartdoor, pet_id, description)
            for smartdoor in smartdoors
            for pet_id in coordinator.get_smartdoor_pet_ids(smartdoor.api_name)
            for description in (
                SMARTDOOR_PET_SMART_ACCESS_DESCRIPTION,
                SMARTDOOR_PET_NEXT_SMART_ACCESS_DESCRIPTION,
                SMARTDOOR_PET_NEXT_SMART_ACCESS_CHANGE_DESCRIPTION,
            )
        )
        entities.extend(
            PetSafeExtendedSmartDoorScheduleSensor(coordinator, smartdoor, description)
            for smartdoor in smartdoors
            for description in (
                SMARTDOOR_SCHEDULE_RULE_COUNT_DESCRIPTION,
                SMARTDOOR_SCHEDULE_SCHEDULED_PET_COUNT_DESCRIPTION,
            )
        )

    if entities:
        _async_update_sensor_entity_categories(hass, entities)
        async_add_entities(entities)
