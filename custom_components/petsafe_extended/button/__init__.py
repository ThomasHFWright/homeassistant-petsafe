"""Button platform for petsafe_extended."""

from __future__ import annotations

from custom_components.petsafe_extended.const import CONF_ENABLE_SMARTDOOR_SCHEDULES, DEFAULT_ENABLE_SMARTDOOR_SCHEDULES
from custom_components.petsafe_extended.data import PetSafeExtendedConfigEntry
from custom_components.petsafe_extended.utils import filter_selected_devices
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .feeder_feed import FEEDER_BUTTON_DESCRIPTIONS, PetSafeExtendedFeederButton
from .feeder_refresh import FEEDER_REFRESH_BUTTON_DESCRIPTIONS, PetSafeExtendedFeederRefreshButton
from .litterbox_action import LITTERBOX_BUTTON_DESCRIPTIONS, PetSafeExtendedLitterboxButton
from .smartdoor_refresh import SMARTDOOR_REFRESH_BUTTON_DESCRIPTIONS, PetSafeExtendedSmartDoorRefreshButton


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    del hass
    coordinator = entry.runtime_data.coordinator
    schedules_enabled = entry.options.get(CONF_ENABLE_SMARTDOOR_SCHEDULES, DEFAULT_ENABLE_SMARTDOOR_SCHEDULES)

    try:
        feeders = filter_selected_devices(await coordinator.get_feeders(), entry.data.get("feeders"))
        litterboxes = filter_selected_devices(await coordinator.get_litterboxes(), entry.data.get("litterboxes"))
        smartdoors = (
            filter_selected_devices(await coordinator.get_smartdoors(), entry.data.get("smartdoors"))
            if schedules_enabled
            else []
        )
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady("Failed to retrieve PetSafe devices") from err

    entities: list[ButtonEntity] = [
        PetSafeExtendedFeederButton(coordinator, feeder, description)
        for feeder in feeders
        for description in FEEDER_BUTTON_DESCRIPTIONS
    ]
    entities.extend(
        PetSafeExtendedFeederRefreshButton(coordinator, feeder, description)
        for feeder in feeders
        for description in FEEDER_REFRESH_BUTTON_DESCRIPTIONS
    )
    entities.extend(
        PetSafeExtendedLitterboxButton(coordinator, litterbox, description)
        for litterbox in litterboxes
        for description in LITTERBOX_BUTTON_DESCRIPTIONS
    )
    if schedules_enabled:
        entities.extend(
            PetSafeExtendedSmartDoorRefreshButton(coordinator, smartdoor, description)
            for smartdoor in smartdoors
            for description in SMARTDOOR_REFRESH_BUTTON_DESCRIPTIONS
        )

    if entities:
        async_add_entities(entities)
