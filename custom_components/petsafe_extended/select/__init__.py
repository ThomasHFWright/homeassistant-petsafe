"""Select platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.const import DOMAIN
from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .litterbox_rake_timer import LITTERBOX_SELECT_DESCRIPTIONS, PetSafeExtendedLitterboxSelect
from .smartdoor_final_act import PetSafeExtendedSmartDoorFinalActSelect
from .smartdoor_operating_mode import PetSafeExtendedSmartDoorOperatingModeSelect
from .smartdoor_override import PetSafeExtendedSmartDoorOverrideSelect


def _async_update_select_entity_categories(hass: HomeAssistant, entities: list[SelectEntity]) -> None:
    """Apply updated select entity categories to existing registry entries."""
    entity_registry = er.async_get(hass)

    for entity in entities:
        if entity.unique_id is None:
            continue

        entity_id = entity_registry.async_get_entity_id("select", DOMAIN, entity.unique_id)
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
    """Set up the select platform."""
    coordinator = entry.runtime_data.coordinator

    try:
        litterboxes = filter_selected_devices(await coordinator.get_litterboxes(), entry.data.get("litterboxes"))
        smartdoors = filter_selected_devices(await coordinator.get_smartdoors(), entry.data.get("smartdoors"))
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe devices") from err

    entities: list[SelectEntity] = [
        PetSafeExtendedLitterboxSelect(coordinator, litterbox, description)
        for litterbox in litterboxes
        for description in LITTERBOX_SELECT_DESCRIPTIONS
    ]
    entities.extend(PetSafeExtendedSmartDoorOperatingModeSelect(coordinator, smartdoor) for smartdoor in smartdoors)
    entities.extend(PetSafeExtendedSmartDoorOverrideSelect(coordinator, smartdoor) for smartdoor in smartdoors)
    entities.extend(PetSafeExtendedSmartDoorFinalActSelect(coordinator, smartdoor) for smartdoor in smartdoors)
    if entities:
        _async_update_select_entity_categories(hass, entities)
        async_add_entities(entities)
