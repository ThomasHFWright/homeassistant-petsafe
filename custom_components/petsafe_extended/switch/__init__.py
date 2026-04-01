"""Switch platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended import PetSafeCoordinator, SwitchEntities
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
    """Set up the switch platform."""
    coordinator: PetSafeCoordinator = hass.data[DOMAIN][entry.entry_id]

    try:
        feeders = filter_selected_devices(await coordinator.get_feeders(), entry.data.get("feeders"))
    except Exception as exc:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe SmartFeed devices") from exc

    entities = []
    for feeder in feeders:
        entities.append(
            SwitchEntities.PetSafeFeederSwitchEntity(
                hass=hass,
                name="Feeding Paused",
                device_type="feeding_paused",
                icon="mdi:pause",
                device=feeder,
                coordinator=coordinator,
                entity_category=EntityCategory.CONFIG,
            )
        )
        entities.append(
            SwitchEntities.PetSafeFeederSwitchEntity(
                hass=hass,
                name="Child Lock",
                device_type="child_lock",
                icon="mdi:lock-open",
                device=feeder,
                coordinator=coordinator,
                entity_category=EntityCategory.CONFIG,
            )
        )
        entities.append(
            SwitchEntities.PetSafeFeederSwitchEntity(
                hass=hass,
                name="Slow Feed",
                device_type="slow_feed",
                icon="mdi:tortoise",
                device=feeder,
                coordinator=coordinator,
                entity_category=EntityCategory.CONFIG,
            )
        )

    if entities:
        async_add_entities(entities)
