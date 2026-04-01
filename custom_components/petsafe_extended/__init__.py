"""The PetSafe Integration integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import importlib
from importlib import metadata
import logging
from pathlib import Path
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import httpx

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_AREA_ID,
    ATTR_DEVICE_ID,
    ATTR_ENTITY_ID,
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_TOKEN,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.loader import async_get_integration
from homeassistant.requirements import RequirementsNotFound, _async_get_manager, async_process_requirements

from .const import (
    ATTR_AMOUNT,
    ATTR_SLOW_FEED,
    ATTR_TIME,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    SERVICE_ADD_SCHEDULE,
    SERVICE_DELETE_ALL_SCHEDULES,
    SERVICE_DELETE_SCHEDULE,
    SERVICE_FEED,
    SERVICE_MODIFY_SCHEDULE,
    SERVICE_PRIME,
)
from .helpers import get_feeders_for_service

if TYPE_CHECKING:
    import petsafe

_LOGGER = logging.getLogger(__name__)


def _has_distribution(distribution_name: str) -> bool:
    """Return whether a distribution is installed in the current interpreter."""
    try:
        metadata.distribution(distribution_name)
    except metadata.PackageNotFoundError:
        return False
    return True


def _get_distribution_top_levels(distribution_name: str) -> list[str]:
    """Return top-level module names advertised by a distribution."""
    try:
        dist = metadata.distribution(distribution_name)
    except metadata.PackageNotFoundError:
        return []

    top_level = dist.read_text("top_level.txt")
    if not top_level:
        return []

    return [line.strip() for line in top_level.splitlines() if line.strip()]


def _ensure_deps_path(config_dir: str) -> None:
    """Ensure Home Assistant's config deps directory is importable."""
    deps_path = str(Path(config_dir) / "deps")
    if deps_path not in sys.path:
        sys.path.insert(0, deps_path)


def _invalidate_import_state() -> None:
    """Refresh Python's import caches after runtime requirement installation."""
    importlib.invalidate_caches()
    sys.path_importer_cache.clear()


def _get_distribution_root(distribution_name: str, module_name: str) -> str | None:
    """Return the import root for an installed distribution."""
    try:
        dist = metadata.distribution(distribution_name)
    except metadata.PackageNotFoundError:
        return None

    module_init = dist.locate_file(f"{module_name}/__init__.py")
    if module_init.exists():
        return str(module_init.parent.parent)

    return None


def _run_uv_command(*args: str) -> str | None:
    """Return stdout from a uv command for the current interpreter."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "uv", *args],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    return output or None


def _get_uv_install_location(distribution_name: str) -> str | None:
    """Return uv's reported installation location for a distribution."""
    if not (output := _run_uv_command("pip", "show", distribution_name)):
        return None

    for line in output.splitlines():
        if line.startswith("Location:"):
            location = line.partition(":")[2].strip()
            if location:
                return location

    return None


def _get_uv_cache_dir() -> Path | None:
    """Return the active uv cache directory for the current interpreter."""
    if not (output := _run_uv_command("cache", "dir")):
        return None

    cache_dir = Path(output)
    return cache_dir if cache_dir.exists() else None


def _get_uv_archive_parent(cache_dir: Path, module_name: str) -> str | None:
    """Return the extracted uv archive path containing a module, if present."""
    for archive_root in sorted(cache_dir.glob("archive-v*")):
        for module_init in archive_root.glob(f"*/{module_name}/__init__.py"):
            return str(module_init.parent.parent)
    return None


async def _async_import_petsafe(hass: HomeAssistant) -> Any:
    """Ensure the petsafe dependency is installed before importing it."""
    integration = await async_get_integration(hass, DOMAIN)
    manager = _async_get_manager(hass)
    _ensure_deps_path(hass.config.config_dir)

    if not await hass.async_add_executor_job(_has_distribution, "petsafe-api"):
        for requirement in integration.requirements:
            manager.is_installed_cache.discard(requirement)
            manager.install_failure_history.discard(requirement)

    await async_process_requirements(
        hass,
        integration.domain,
        integration.requirements,
        integration.is_built_in,
    )
    await hass.async_add_executor_job(_invalidate_import_state)

    try:
        return await hass.async_add_executor_job(importlib.import_module, "petsafe")
    except ModuleNotFoundError:
        candidate_roots = [
            await hass.async_add_executor_job(_get_distribution_root, "petsafe-api", "petsafe"),
            await hass.async_add_executor_job(_get_uv_install_location, "petsafe-api"),
        ]

        for import_root in candidate_roots:
            if not import_root:
                continue

            if import_root not in sys.path:
                sys.path.insert(0, import_root)

            await hass.async_add_executor_job(_invalidate_import_state)
            try:
                return await hass.async_add_executor_job(importlib.import_module, "petsafe")
            except ModuleNotFoundError:
                continue

        cache_dir: Path | None = await hass.async_add_executor_job(_get_uv_cache_dir)
        if cache_dir:
            if archive_parent := await hass.async_add_executor_job(_get_uv_archive_parent, cache_dir, "petsafe"):
                if archive_parent not in sys.path:
                    sys.path.insert(0, archive_parent)
                await hass.async_add_executor_job(_invalidate_import_state)
                return await hass.async_add_executor_job(importlib.import_module, "petsafe")

        top_levels = await hass.async_add_executor_job(_get_distribution_top_levels, "petsafe-api")
        for module_name in top_levels:
            if module_name == "petsafe":
                continue
            try:
                module = await hass.async_add_executor_job(importlib.import_module, module_name)
            except ModuleNotFoundError:
                continue

            _LOGGER.warning("Imported petsafe-api using top-level module '%s'", module_name)
            return module

        _LOGGER.warning(
            (
                "petsafe-api installation did not yield an importable 'petsafe' module; "
                "distribution_root=%s, uv_install_location=%s, uv_cache_dir=%s, home=%s"
            ),
            candidate_roots[0],
            candidate_roots[1],
            cache_dir,
            Path.home(),
        )
        raise


PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.LOCK,
]


def _entry_has_selected_devices(entry: ConfigEntry, key: str) -> bool:
    """Return whether a config entry should load a device-specific platform."""
    selected = entry.data.get(key)
    return selected is None or len(selected) > 0


def _get_entry_platforms(entry: ConfigEntry) -> list[Platform]:
    """Return only the platforms needed for the selected devices."""
    platforms: list[Platform] = []

    if _entry_has_selected_devices(entry, "feeders") or _entry_has_selected_devices(entry, "litterboxes"):
        platforms.append(Platform.SENSOR)
    if _entry_has_selected_devices(entry, "feeders"):
        platforms.append(Platform.SWITCH)
    if _entry_has_selected_devices(entry, "feeders") or _entry_has_selected_devices(entry, "litterboxes"):
        platforms.append(Platform.BUTTON)
    if _entry_has_selected_devices(entry, "litterboxes"):
        platforms.append(Platform.SELECT)
    if _entry_has_selected_devices(entry, "smartdoors"):
        platforms.append(Platform.LOCK)

    return platforms


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PetSafe Integration from a config entry."""
    try:
        petsafe = await _async_import_petsafe(hass)
    except (ModuleNotFoundError, RequirementsNotFound) as err:
        raise ConfigEntryNotReady("Unable to import the petsafe dependency") from err

    client = petsafe.PetSafeClient(
        entry.data.get(CONF_EMAIL),
        entry.data.get(CONF_TOKEN),
        entry.data.get(CONF_REFRESH_TOKEN),
        entry.data.get(CONF_ACCESS_TOKEN),
        client=get_async_client(hass),
    )

    hass.data.setdefault(DOMAIN, {})

    coordinator = PetSafeCoordinator(hass, client, entry)

    hass.data[DOMAIN][entry.entry_id] = coordinator

    async def handle_add_schedule(call: ServiceCall) -> None:
        device_ids = call.data.get(ATTR_DEVICE_ID)
        area_ids = call.data.get(ATTR_AREA_ID)
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        time = call.data.get(ATTR_TIME)
        amount = call.data.get(ATTR_AMOUNT)
        matched_devices = get_feeders_for_service(hass, area_ids, device_ids, entity_ids)
        for device_id in matched_devices:
            device = next(d for d in await coordinator.get_feeders() if d.api_name == device_id)
            if device is not None:
                await device.schedule_feed(time, amount, False)

    hass.services.async_register(DOMAIN, SERVICE_ADD_SCHEDULE, handle_add_schedule)

    async def handle_delete_schedule(call: ServiceCall) -> None:
        device_ids = call.data.get(ATTR_DEVICE_ID)
        area_ids = call.data.get(ATTR_AREA_ID)
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        time = call.data.get(ATTR_TIME)
        matched_devices = get_feeders_for_service(hass, area_ids, device_ids, entity_ids)

        for device_id in matched_devices:
            device = next(d for d in await coordinator.get_feeders() if d.api_name == device_id)
            if device is not None:
                schedules = await device.get_schedules()
                for schedule in schedules:
                    if schedule["time"] + ":00" == time:
                        await device.delete_schedule(str(schedule["id"]), False)
                        break

    hass.services.async_register(DOMAIN, SERVICE_DELETE_SCHEDULE, handle_delete_schedule)

    async def handle_delete_all_schedules(call: ServiceCall) -> None:
        device_ids = call.data.get(ATTR_DEVICE_ID)
        area_ids = call.data.get(ATTR_AREA_ID)
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        matched_devices = get_feeders_for_service(hass, area_ids, device_ids, entity_ids)

        for device_id in matched_devices:
            device = next(d for d in await coordinator.get_feeders() if d.api_name == device_id)
            if device is not None:
                await device.delete_all_schedules(False)

    hass.services.async_register(DOMAIN, SERVICE_DELETE_ALL_SCHEDULES, handle_delete_all_schedules)

    async def handle_modify_schedule(call: ServiceCall) -> None:
        device_ids = call.data.get(ATTR_DEVICE_ID)
        area_ids = call.data.get(ATTR_AREA_ID)
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        time = call.data.get(ATTR_TIME)
        amount = call.data.get(ATTR_AMOUNT)
        matched_devices = get_feeders_for_service(hass, area_ids, device_ids, entity_ids)

        for device_id in matched_devices:
            device = next(d for d in await coordinator.get_feeders() if d.api_name == device_id)
            if device is not None:
                schedules = await device.get_schedules()
                for schedule in schedules:
                    if schedule["time"] + ":00" == time:
                        await device.modify_schedule(schedule["time"], amount, str(schedule["id"]), False)
                        break

    hass.services.async_register(DOMAIN, SERVICE_MODIFY_SCHEDULE, handle_modify_schedule)

    async def handle_feed(call: ServiceCall) -> None:
        device_ids = call.data.get(ATTR_DEVICE_ID)
        area_ids = call.data.get(ATTR_AREA_ID)
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        amount = call.data.get(ATTR_AMOUNT)
        slow_feed = call.data.get(ATTR_SLOW_FEED)
        matched_devices = get_feeders_for_service(hass, area_ids, device_ids, entity_ids)

        for device_id in matched_devices:
            device = next(d for d in await coordinator.get_feeders() if d.api_name == device_id)
            if device is not None:
                await device.feed(amount, slow_feed, False)
                await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_FEED, handle_feed)

    async def handle_prime(call: ServiceCall) -> None:
        device_ids = call.data.get(ATTR_DEVICE_ID)
        area_ids = call.data.get(ATTR_AREA_ID)
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        matched_devices = get_feeders_for_service(hass, area_ids, device_ids, entity_ids)

        for device_id in matched_devices:
            device = next(d for d in await coordinator.get_feeders() if d.api_name == device_id)
            if device is not None:
                # NB: DeviceSmartFeed.prime() synchronously updates state after priming.
                # Directly send a 5/8 cup meal here so that we can defer the update.
                await device.feed(5, False, False)
                await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_PRIME, handle_prime)

    await coordinator.async_config_entry_first_refresh()

    platforms = _get_entry_platforms(entry)
    if platforms:
        await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = _get_entry_platforms(entry)
    if not platforms:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, platforms):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class PetSafeData:
    """Container for the devices returned by the PetSafe API."""

    def __init__(
        self,
        feeders: list[petsafe.devices.DeviceSmartFeed],
        litterboxes: list[petsafe.devices.DeviceScoopfree],
        smartdoors: list[petsafe.devices.DeviceSmartDoor],
    ):
        """Initialize the cached PetSafe device data."""
        self.feeders = feeders
        self.litterboxes = litterboxes
        self.smartdoors = smartdoors


class PetSafeCoordinator(DataUpdateCoordinator):
    """Data Update Coordinator for petsafe devices."""

    def __init__(self, hass: HomeAssistant, api: petsafe.PetSafeClient, entry: ConfigEntry):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="PetSafe",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=30),
        )
        self.api: petsafe.PetSafeClient = api
        self.hass: HomeAssistant = hass
        self._feeders: list[petsafe.devices.DeviceSmartFeed] = None
        self._litterboxes: list[petsafe.devices.DeviceScoopfree] = None
        self._smartdoors: list[petsafe.devices.DeviceSmartDoor] = None
        self._device_lock = asyncio.Lock()
        self.entry = entry
        self._authErrorCount = 0

    async def get_feeders(self) -> list[petsafe.devices.DeviceSmartFeed]:
        """Return the list of feeders."""
        async with self._device_lock:
            try:
                if self._feeders is None:
                    self._feeders = await self.api.get_feeders()
            except httpx.HTTPStatusError as ex:
                if ex.response.status_code in (401, 403):
                    await self.entry.async_start_reauth(self.hass)
                else:
                    raise
            return self._feeders

    async def get_litterboxes(self) -> list[petsafe.devices.DeviceScoopfree]:
        """Return the list of litterboxes."""
        async with self._device_lock:
            try:
                if self._litterboxes is None:
                    self._litterboxes = await self.api.get_litterboxes()
            except httpx.HTTPStatusError as ex:
                if ex.response.status_code in (401, 403):
                    await self.entry.async_start_reauth(self.hass)
                else:
                    raise
            return self._litterboxes

    async def get_smartdoors(self) -> list[petsafe.devices.DeviceSmartDoor]:
        """Return the list of smart doors."""
        async with self._device_lock:
            try:
                if self._smartdoors is None:
                    self._smartdoors = await self.api.get_smartdoors()
            except httpx.HTTPStatusError as ex:
                if ex.response.status_code in (401, 403):
                    await self.entry.async_start_reauth(self.hass)
                else:
                    raise
            return self._smartdoors

    async def _async_update_data(self) -> PetSafeData:
        """Fetch data from API endpoint."""
        try:
            async with self._device_lock:
                self._feeders = await self.api.get_feeders()
                self._litterboxes = await self.api.get_litterboxes()
                self._smartdoors = await self.api.get_smartdoors()
                self._authErrorCount = 0
                return PetSafeData(
                    self._feeders,
                    self._litterboxes,
                    self._smartdoors,
                )
        except httpx.HTTPStatusError as ex:
            if ex.response.status_code in (401, 403):
                self._authErrorCount += 1
                if self._authErrorCount >= 5:
                    self._authErrorCount = 0
                    raise ConfigEntryAuthFailed from ex

            else:
                raise UpdateFailed from ex
        except Exception as ex:
            raise UpdateFailed from ex
