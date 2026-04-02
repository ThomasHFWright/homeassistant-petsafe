"""Sensor platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended import PetSafeCoordinator, SensorEntities
from custom_components.petsafe_extended.const import DOMAIN
from custom_components.petsafe_extended.helpers import filter_selected_devices
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: PetSafeCoordinator = hass.data[DOMAIN][entry.entry_id]

    try:
        feeders = filter_selected_devices(await coordinator.get_feeders(), entry.data.get("feeders"))
        litterboxes = filter_selected_devices(await coordinator.get_litterboxes(), entry.data.get("litterboxes"))
    except Exception as exc:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe devices") from exc

    entities = []
    for feeder in feeders:
        entities.append(
            SensorEntities.PetSafeFeederSensorEntity(
                hass=hass,
                name="Battery Level",
                device_class="battery",
                device_type="battery",
                device=feeder,
                coordinator=coordinator,
            )
        )
        entities.append(
            SensorEntities.PetSafeFeederSensorEntity(
                hass=hass,
                name="Last Feeding",
                device_type="last_feeding",
                device_class="timestamp",
                device=feeder,
                coordinator=coordinator,
            )
        )
        entities.append(
            SensorEntities.PetSafeFeederSensorEntity(
                hass=hass,
                name="Next Feeding",
                device_type="next_feeding",
                device_class="timestamp",
                device=feeder,
                coordinator=coordinator,
            )
        )
        entities.append(
            SensorEntities.PetSafeFeederSensorEntity(
                hass=hass,
                name="Food Level",
                device_type="food_level",
                device=feeder,
                coordinator=coordinator,
                icon="mdi:bowl",
            )
        )
        entities.append(
            SensorEntities.PetSafeFeederSensorEntity(
                hass=hass,
                name="Signal Strength",
                device_type="signal_strength",
                device=feeder,
                coordinator=coordinator,
                device_class="signal_strength",
                entity_category=EntityCategory.DIAGNOSTIC,
            )
        )

    for litterbox in litterboxes:
        entities.append(
            SensorEntities.PetSafeLitterboxSensorEntity(
                hass=hass,
                name="Rake Counter",
                device_type="rake_counter",
                device=litterbox,
                coordinator=coordinator,
                icon="mdi:rake",
            )
        )
        entities.append(
            SensorEntities.PetSafeLitterboxSensorEntity(
                hass=hass,
                name="Rake Status",
                device_type="rake_status",
                device=litterbox,
                coordinator=coordinator,
                icon="mdi:rake",
            )
        )
        entities.append(
            SensorEntities.PetSafeLitterboxSensorEntity(
                hass=hass,
                name="Signal Strength",
                device_type="signal_strength",
                device=litterbox,
                coordinator=coordinator,
                device_class="signal_strength",
                entity_category=EntityCategory.DIAGNOSTIC,
            )
        )
        entities.append(
            SensorEntities.PetSafeLitterboxSensorEntity(
                hass=hass,
                name="Last Cleaning",
                device_type="last_cleaning",
                device=litterbox,
                coordinator=coordinator,
                device_class="timestamp",
            )
        )

    if entities:
        async_add_entities(entities)
