"""Button platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended import ButtonEntities, PetSafeCoordinator
from custom_components.petsafe_extended.const import DOMAIN
from custom_components.petsafe_extended.helpers import filter_selected_devices
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator: PetSafeCoordinator = hass.data[DOMAIN][entry.entry_id]

    try:
        feeders = filter_selected_devices(await coordinator.get_feeders(), entry.data.get("feeders"))
        litterboxes = filter_selected_devices(await coordinator.get_litterboxes(), entry.data.get("litterboxes"))
    except Exception as exc:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe devices") from exc

    entities = [
        ButtonEntities.PetSafeFeederButtonEntity(
            hass=hass,
            name="Feed",
            device_type="feed",
            device=feeder,
            coordinator=coordinator,
        )
        for feeder in feeders
    ]

    for litterbox in litterboxes:
        entities.append(
            ButtonEntities.PetSafeLitterboxButtonEntity(
                hass=hass,
                name="Clean",
                device_type="clean",
                device=litterbox,
                coordinator=coordinator,
            )
        )
        entities.append(
            ButtonEntities.PetSafeLitterboxButtonEntity(
                hass=hass,
                name="Reset",
                device_type="reset",
                device=litterbox,
                coordinator=coordinator,
            )
        )

    if entities:
        async_add_entities(entities)
