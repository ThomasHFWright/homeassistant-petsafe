"""The PetSafe Extended integration."""

from __future__ import annotations

from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
from homeassistant.loader import async_get_integration
from homeassistant.requirements import RequirementsNotFound

from .api import async_import_petsafe, create_petsafe_client
from .const import CONF_ENABLE_SMARTDOOR_SCHEDULES, DEFAULT_ENABLE_SMARTDOOR_SCHEDULES, DOMAIN, LOGGER
from .coordinator import PetSafeExtendedDataUpdateCoordinator
from .data import PetSafeExtendedConfigEntry, PetSafeExtendedRuntimeData
from .service_actions import async_setup_services
from .utils.auth import get_entry_unique_id

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.EVENT,
    Platform.LOCK,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_SCHEDULE_ENTITY_UNIQUE_ID_SUFFIXES = {
    "_schedule",
    "_schedule_rule_count",
    "_active_schedule_rule_count",
    "_scheduled_pet_count",
    "_smart_access",
    "_next_smart_access",
    "_next_smart_access_change",
    "_refresh_schedule_data",
}
_DIAGNOSTIC_ENTITY_CATEGORY_BY_UNIQUE_ID_SUFFIX = {
    "_battery_level": EntityCategory.DIAGNOSTIC,
    "_battery_voltage": EntityCategory.DIAGNOSTIC,
    "_signal_strength": EntityCategory.DIAGNOSTIC,
    "_ac_power": EntityCategory.DIAGNOSTIC,
    "_connectivity": EntityCategory.DIAGNOSTIC,
    "_problem": EntityCategory.DIAGNOSTIC,
    "_schedule": EntityCategory.DIAGNOSTIC,
    "_schedule_rule_count": EntityCategory.DIAGNOSTIC,
    "_active_schedule_rule_count": EntityCategory.DIAGNOSTIC,
    "_scheduled_pet_count": EntityCategory.DIAGNOSTIC,
}
_SMARTDOOR_PET_ENTITY_UNIQUE_ID_SUFFIX_TO_DOMAIN = {
    "_last_seen": "sensor",
    "_last_activity": "sensor",
    "_smart_access": "sensor",
    "_next_smart_access": "sensor",
    "_next_smart_access_change": "sensor",
    "_schedule": "calendar",
    "_activity": "event",
}
_SMARTDOOR_SCHEDULE_PET_ENTITY_UNIQUE_ID_SUFFIXES = {
    "_smart_access",
    "_next_smart_access",
    "_next_smart_access_change",
    "_schedule",
}


def _entry_has_selected_devices(entry: ConfigEntry, key: str) -> bool:
    """Return whether a config entry should load a device-specific platform."""
    selected = entry.data.get(key)
    return selected is None or len(selected) > 0


def _get_entry_platforms(entry: ConfigEntry) -> list[Platform]:
    """Return only the platforms needed for the selected devices."""
    platforms: list[Platform] = []
    schedules_enabled = _entry_smartdoor_schedules_enabled(entry)

    if (
        _entry_has_selected_devices(entry, "feeders")
        or _entry_has_selected_devices(entry, "litterboxes")
        or _entry_has_selected_devices(entry, "smartdoors")
    ):
        platforms.append(Platform.SENSOR)
    if _entry_has_selected_devices(entry, "smartdoors"):
        platforms.append(Platform.BINARY_SENSOR)
    if _entry_has_selected_devices(entry, "smartdoors") and schedules_enabled:
        platforms.append(Platform.CALENDAR)
    if _entry_has_selected_devices(entry, "feeders"):
        platforms.append(Platform.SWITCH)
    if (
        _entry_has_selected_devices(entry, "feeders")
        or _entry_has_selected_devices(entry, "litterboxes")
        or _entry_has_selected_devices(entry, "smartdoors")
    ):
        platforms.append(Platform.BUTTON)
    if _entry_has_selected_devices(entry, "litterboxes") or _entry_has_selected_devices(entry, "smartdoors"):
        platforms.append(Platform.SELECT)
    if _entry_has_selected_devices(entry, "smartdoors"):
        platforms.append(Platform.EVENT)
    if _entry_has_selected_devices(entry, "smartdoors"):
        platforms.append(Platform.LOCK)

    return platforms


def _entry_smartdoor_schedules_enabled(entry: ConfigEntry) -> bool:
    """Return whether SmartDoor schedule entities should be created for an entry."""
    return bool(entry.options.get(CONF_ENABLE_SMARTDOOR_SCHEDULES, DEFAULT_ENABLE_SMARTDOOR_SCHEDULES))


def _is_schedule_entity_unique_id(unique_id: str | None) -> bool:
    """Return whether a unique ID belongs to a SmartDoor schedule entity."""
    return unique_id is not None and any(unique_id.endswith(suffix) for suffix in _SCHEDULE_ENTITY_UNIQUE_ID_SUFFIXES)


def _async_remove_schedule_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove SmartDoor schedule entities from the entity registry for a config entry."""
    entity_reg = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(entity_reg, entry.entry_id):
        if _is_schedule_entity_unique_id(entity_entry.unique_id):
            entity_reg.async_remove(entity_entry.entity_id)


def _async_remove_smartdoor_pet_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    pet_ids_by_door: dict[str, set[str] | tuple[str, ...]],
    *,
    schedule_only: bool = False,
) -> None:
    """Remove SmartDoor pet-derived entities for the provided doors and pets."""
    entity_reg = er.async_get(hass)
    suffix_to_domain = {
        suffix: domain
        for suffix, domain in _SMARTDOOR_PET_ENTITY_UNIQUE_ID_SUFFIX_TO_DOMAIN.items()
        if not schedule_only or suffix in _SMARTDOOR_SCHEDULE_PET_ENTITY_UNIQUE_ID_SUFFIXES
    }

    for door_api_name, pet_ids in pet_ids_by_door.items():
        for pet_id in pet_ids:
            for suffix, domain in suffix_to_domain.items():
                unique_id = f"{door_api_name}_{pet_id}{suffix}"
                entity_id = entity_reg.async_get_entity_id(domain, DOMAIN, unique_id)
                if entity_id is None:
                    continue

                entity_entry = entity_reg.async_get(entity_id)
                if entity_entry is None or entity_entry.config_entry_id != entry.entry_id:
                    continue

                entity_reg.async_remove(entity_id)


def _async_update_diagnostic_entity_categories(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply diagnostic entity categories to existing SmartDoor registry entries."""
    entity_reg = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(entity_reg, entry.entry_id):
        unique_id = entity_entry.unique_id
        if unique_id is None:
            continue

        entity_category = next(
            (
                category
                for suffix, category in _DIAGNOSTIC_ENTITY_CATEGORY_BY_UNIQUE_ID_SUFFIX.items()
                if unique_id.endswith(suffix)
            ),
            None,
        )
        if entity_category is None or entity_entry.entity_category == entity_category:
            continue

        entity_reg.async_update_entity(entity_entry.entity_id, entity_category=entity_category)


async def _async_handle_entry_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload an entry after options change and purge removed schedule entities when needed."""
    typed_entry = cast(PetSafeExtendedConfigEntry, entry)
    runtime_data = typed_entry.runtime_data
    schedules_enabled = _entry_smartdoor_schedules_enabled(typed_entry)
    if runtime_data.smartdoor_schedules_enabled and not schedules_enabled:
        _async_remove_schedule_entities(hass, typed_entry)
    await hass.config_entries.async_reload(entry.entry_id)


def _ensure_entry_unique_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Backfill a stable unique ID for legacy entries that do not have one yet."""
    if entry.unique_id is not None:
        return

    unique_id = get_entry_unique_id(entry)
    if unique_id is None:
        return

    if any(
        existing_entry.entry_id != entry.entry_id and existing_entry.unique_id == unique_id
        for existing_entry in hass.config_entries.async_entries(DOMAIN)
    ):
        LOGGER.warning(
            "Skipping unique_id backfill for entry %s because %s is already in use",
            entry.entry_id,
            unique_id,
        )
        return

    hass.config_entries.async_update_entry(entry, unique_id=unique_id)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the PetSafe integration at component scope."""
    del config
    await async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PetSafe Extended from a config entry."""
    typed_entry = cast(PetSafeExtendedConfigEntry, entry)
    _ensure_entry_unique_id(hass, typed_entry)
    schedules_enabled = _entry_smartdoor_schedules_enabled(typed_entry)

    try:
        petsafe = await async_import_petsafe(hass)
    except (ModuleNotFoundError, RequirementsNotFound) as err:
        raise ConfigEntryNotReady("Unable to import the petsafe dependency") from err

    integration = await async_get_integration(hass, DOMAIN)
    client = create_petsafe_client(hass, petsafe, typed_entry)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, client, typed_entry)
    typed_entry.runtime_data = PetSafeExtendedRuntimeData(
        client=client,
        coordinator=coordinator,
        integration=integration,
        smartdoor_schedules_enabled=schedules_enabled,
    )
    typed_entry.async_on_unload(typed_entry.add_update_listener(_async_handle_entry_update))

    await coordinator.async_config_entry_first_refresh()
    _async_update_diagnostic_entity_categories(hass, typed_entry)
    if not schedules_enabled:
        _async_remove_schedule_entities(hass, typed_entry)

    platforms = _get_entry_platforms(typed_entry)
    typed_entry.runtime_data.loaded_platforms = tuple(platforms)
    if platforms:
        await hass.config_entries.async_forward_entry_setups(typed_entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    typed_entry = cast(PetSafeExtendedConfigEntry, entry)
    platforms = list(typed_entry.runtime_data.loaded_platforms) if typed_entry.runtime_data.loaded_platforms else []
    if not platforms:
        platforms = _get_entry_platforms(entry)
    if not platforms:
        return True

    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        typed_entry.runtime_data.loaded_platforms = ()
    return unload_ok
