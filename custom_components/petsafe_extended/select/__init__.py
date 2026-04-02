"""Select platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .litterbox_rake_timer import LITTERBOX_SELECT_DESCRIPTIONS, PetSafeExtendedLitterboxSelect
from .smartdoor_final_act import PetSafeExtendedSmartDoorFinalActSelect
from .smartdoor_operating_mode import PetSafeExtendedSmartDoorOperatingModeSelect


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    del hass
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
    entities.extend(PetSafeExtendedSmartDoorFinalActSelect(coordinator, smartdoor) for smartdoor in smartdoors)
    if entities:
        async_add_entities(entities)
