"""Select platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended import PetSafeCoordinator, SelectEntities
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
    """Set up the select platform."""
    coordinator: PetSafeCoordinator = hass.data[DOMAIN][entry.entry_id]

    try:
        litterboxes = filter_selected_devices(await coordinator.get_litterboxes(), entry.data.get("litterboxes"))
    except Exception as exc:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe scoopfree devices") from exc

    entities = [
        SelectEntities.PetSafeLitterboxSelectEntity(
            hass=hass,
            name="Rake Timer",
            device_type="rake_timer",
            device=litterbox,
            coordinator=coordinator,
            options=["5", "10", "15", "20", "25", "30"],
            entity_category=EntityCategory.CONFIG,
        )
        for litterbox in litterboxes
    ]
    if entities:
        async_add_entities(entities)
