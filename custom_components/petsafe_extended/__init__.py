"""The PetSafe Extended integration."""

from __future__ import annotations

from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.loader import async_get_integration
from homeassistant.requirements import RequirementsNotFound

from .api import async_import_petsafe, create_petsafe_client
from .const import DOMAIN, LOGGER
from .coordinator import PetSafeExtendedDataUpdateCoordinator
from .data import PetSafeExtendedConfigEntry, PetSafeExtendedRuntimeData
from .service_actions import async_setup_services
from .utils.auth import get_entry_unique_id

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.CALENDAR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.EVENT,
    Platform.LOCK,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _entry_has_selected_devices(entry: ConfigEntry, key: str) -> bool:
    """Return whether a config entry should load a device-specific platform."""
    selected = entry.data.get(key)
    return selected is None or len(selected) > 0


def _get_entry_platforms(entry: ConfigEntry) -> list[Platform]:
    """Return only the platforms needed for the selected devices."""
    platforms: list[Platform] = []

    if (
        _entry_has_selected_devices(entry, "feeders")
        or _entry_has_selected_devices(entry, "litterboxes")
        or _entry_has_selected_devices(entry, "smartdoors")
    ):
        platforms.append(Platform.SENSOR)
    if _entry_has_selected_devices(entry, "smartdoors"):
        platforms.append(Platform.CALENDAR)
    if _entry_has_selected_devices(entry, "feeders"):
        platforms.append(Platform.SWITCH)
    if _entry_has_selected_devices(entry, "feeders") or _entry_has_selected_devices(entry, "litterboxes"):
        platforms.append(Platform.BUTTON)
    if _entry_has_selected_devices(entry, "litterboxes") or _entry_has_selected_devices(entry, "smartdoors"):
        platforms.append(Platform.SELECT)
    if _entry_has_selected_devices(entry, "smartdoors"):
        platforms.append(Platform.EVENT)
    if _entry_has_selected_devices(entry, "smartdoors"):
        platforms.append(Platform.LOCK)

    return platforms


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
    )

    await coordinator.async_config_entry_first_refresh()

    platforms = _get_entry_platforms(typed_entry)
    if platforms:
        await hass.config_entries.async_forward_entry_setups(typed_entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = _get_entry_platforms(entry)
    if not platforms:
        return True

    return await hass.config_entries.async_unload_platforms(entry, platforms)
