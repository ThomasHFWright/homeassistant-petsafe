"""Coordinator implementation for petsafe_extended."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import time
from typing import TYPE_CHECKING, Any, cast

import httpx

from custom_components.petsafe_extended.const import (
    CAT_IN_BOX,
    CONF_ENABLE_SMARTDOOR_SCHEDULES,
    COORDINATOR_HEARTBEAT_INTERVAL,
    DEFAULT_ENABLE_SMARTDOOR_SCHEDULES,
    DEVICE_LIST_REFRESH_INTERVAL,
    DOMAIN,
    ERROR_SENSOR_BLOCKED,
    FEEDER_LAST_FEEDING_REFRESH_INTERVAL,
    FEEDER_SCHEDULE_REFRESH_INTERVAL,
    LITTERBOX_ACTIVITY_REFRESH_INTERVAL,
    LOGGER,
    RAKE_BUTTON_DETECTED,
    RAKE_FINISHED,
    RAKE_NOW,
    SMARTDOOR_ACTIVITY_REFRESH_INTERVAL,
    SMARTDOOR_MODE_MANUAL_LOCKED,
    SMARTDOOR_MODE_MANUAL_UNLOCKED,
    SMARTDOOR_MODE_SMART,
    SMARTDOOR_SCHEDULE_REFRESH_INTERVAL,
)
from custom_components.petsafe_extended.coordinator.pet_links import (
    PET_LINK_REFRESH_INTERVAL,
    async_build_pet_link_data,
    copy_pet_link_data,
)
from custom_components.petsafe_extended.coordinator.smartdoor_activity import (
    SMARTDOOR_ACTIVITY_INITIAL_LIMIT,
    apply_activity_records,
    copy_smartdoor_activity_records,
    copy_smartdoor_pet_states,
    extract_cursor,
    get_new_activity_records,
    merge_activity_records,
    parse_smartdoor_activity_records,
    seed_pet_states,
)
from custom_components.petsafe_extended.coordinator.smartdoor_schedules import (
    build_smartdoor_pet_schedule_states,
    build_smartdoor_schedule_summary,
    copy_smartdoor_pet_schedule_states,
    copy_smartdoor_schedule_rules,
    copy_smartdoor_schedule_summaries,
    get_smartdoor_scheduled_pet_ids,
    parse_smartdoor_schedule_rules,
)
from custom_components.petsafe_extended.data import (
    PetSafeExtendedConfigEntry,
    PetSafeExtendedCoordinatorData,
    PetSafeExtendedFeederDetails,
    PetSafeExtendedLitterboxDetails,
    PetSafeExtendedPetLinkData,
    PetSafeExtendedPetProfile,
    PetSafeExtendedSmartDoorActivityRecord,
    PetSafeExtendedSmartDoorPetScheduleState,
    PetSafeExtendedSmartDoorPetState,
    PetSafeExtendedSmartDoorScheduleRule,
    PetSafeExtendedSmartDoorScheduleSummary,
)
from custom_components.petsafe_extended.utils.smartdoor import (
    get_smartdoor_final_act_value,
    get_smartdoor_locked_mode_option,
    smartdoor_final_acts_match,
    smartdoor_modes_match,
)
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_AUTH_STATUS_CODES = {401, 403}


class PetSafeExtendedDataUpdateCoordinator(DataUpdateCoordinator[PetSafeExtendedCoordinatorData]):
    """Coordinate PetSafe device updates and command execution."""

    config_entry: PetSafeExtendedConfigEntry

    def __init__(self, hass: HomeAssistant, api: Any, entry: PetSafeExtendedConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=COORDINATOR_HEARTBEAT_INTERVAL,
        )
        self.api = api
        self.config_entry = entry
        self._feeders: list[Any] | None = None
        self._litterboxes: list[Any] | None = None
        self._smartdoors: list[Any] | None = None
        self._feeders_last_refresh_monotonic: float | None = None
        self._litterboxes_last_refresh_monotonic: float | None = None
        self._smartdoors_last_refresh_monotonic: float | None = None
        self._feeder_details: dict[str, PetSafeExtendedFeederDetails] = {}
        self._litterbox_details: dict[str, PetSafeExtendedLitterboxDetails] = {}
        self._pet_links: PetSafeExtendedPetLinkData | None = None
        self._pet_links_last_refresh_monotonic: float | None = None
        self._feeder_schedule_payloads: dict[str, tuple[dict[str, Any], ...]] = {}
        self._feeder_last_feeding_last_refresh_by_feeder: dict[str, float] = {}
        self._feeder_schedule_last_refresh_by_feeder: dict[str, float] = {}
        self._litterbox_activity_last_refresh_by_litterbox: dict[str, float] = {}
        self._smartdoor_activity_records: dict[str, tuple[PetSafeExtendedSmartDoorActivityRecord, ...]] = {}
        self._smartdoor_activity_cursor_by_door: dict[str, str] = {}
        self._smartdoor_activity_last_refresh_by_door: dict[str, float] = {}
        self._smartdoor_pet_states: dict[str, dict[str, PetSafeExtendedSmartDoorPetState]] = {}
        self._smartdoor_schedule_rules: dict[str, tuple[PetSafeExtendedSmartDoorScheduleRule, ...]] = {}
        self._smartdoor_schedule_summaries: dict[str, PetSafeExtendedSmartDoorScheduleSummary] = {}
        self._smartdoor_pet_schedule_states: dict[str, dict[str, PetSafeExtendedSmartDoorPetScheduleState]] = {}
        self._smartdoor_schedule_last_refresh_by_door: dict[str, float] = {}
        self._smartdoor_locked_mode_preferences: dict[str, str] = {}
        self._smartdoor_activity_listeners: dict[
            str, list[Callable[[PetSafeExtendedSmartDoorActivityRecord], None]]
        ] = {}
        self._force_refresh_feeders = False
        self._force_refresh_litterboxes = False
        self._force_refresh_smartdoors = False
        self._force_refresh_pet_links = False
        self._force_refresh_feeder_last_feeding_api_names: set[str] = set()
        self._force_refresh_feeder_schedule_api_names: set[str] = set()
        self._force_refresh_litterbox_activity_api_names: set[str] = set()
        self._force_refresh_smartdoor_schedule_api_names: set[str] = set()
        self._device_lock = asyncio.Lock()

    @staticmethod
    def _is_auth_error(error: httpx.HTTPStatusError) -> bool:
        """Return whether an HTTP error should trigger reauthentication."""
        return error.response.status_code in _AUTH_STATUS_CODES

    @staticmethod
    def _raise_auth_failed(error: httpx.HTTPStatusError) -> None:
        """Raise a Home Assistant auth failure from an HTTP status error."""
        raise ConfigEntryAuthFailed("PetSafe authentication failed") from error

    def _cached_snapshot(self) -> PetSafeExtendedCoordinatorData:
        """Build a data snapshot from the coordinator caches."""
        current = self.data or PetSafeExtendedCoordinatorData()
        pet_links = self._pet_links if self._pet_links is not None else current.pet_links
        return PetSafeExtendedCoordinatorData(
            feeders=list(self._feeders if self._feeders is not None else current.feeders),
            litterboxes=list(self._litterboxes if self._litterboxes is not None else current.litterboxes),
            smartdoors=list(self._smartdoors if self._smartdoors is not None else current.smartdoors),
            feeder_details=dict(self._feeder_details or current.feeder_details),
            litterbox_details=dict(self._litterbox_details or current.litterbox_details),
            pet_links=copy_pet_link_data(pet_links),
            smartdoor_activity_records=copy_smartdoor_activity_records(
                self._smartdoor_activity_records or current.smartdoor_activity_records
            ),
            smartdoor_pet_states=copy_smartdoor_pet_states(self._smartdoor_pet_states or current.smartdoor_pet_states),
            smartdoor_schedule_rules=copy_smartdoor_schedule_rules(
                self._smartdoor_schedule_rules or current.smartdoor_schedule_rules
            ),
            smartdoor_schedule_summaries=copy_smartdoor_schedule_summaries(
                self._smartdoor_schedule_summaries or current.smartdoor_schedule_summaries
            ),
            smartdoor_pet_schedule_states=copy_smartdoor_pet_schedule_states(
                self._smartdoor_pet_schedule_states or current.smartdoor_pet_schedule_states
            ),
        )

    def _find_cached_feeder(self, api_name: str) -> Any | None:
        """Return a cached feeder by API name."""
        if self._feeders is None and self.data:
            self._feeders = list(self.data.feeders)
        return next((feeder for feeder in self._feeders or [] if feeder.api_name == api_name), None)

    def _find_cached_litterbox(self, api_name: str) -> Any | None:
        """Return a cached litterbox by API name."""
        if self._litterboxes is None and self.data:
            self._litterboxes = list(self.data.litterboxes)
        return next((litterbox for litterbox in self._litterboxes or [] if litterbox.api_name == api_name), None)

    def _find_cached_smartdoor(self, api_name: str) -> Any | None:
        """Return a cached smart door by API name."""
        if self._smartdoors is None and self.data:
            self._smartdoors = list(self.data.smartdoors)
        return next((smartdoor for smartdoor in self._smartdoors or [] if smartdoor.api_name == api_name), None)

    def _current_pet_links(self) -> PetSafeExtendedPetLinkData | None:
        """Return the most recent pet link snapshot from cache or coordinator data."""
        if self._pet_links is not None:
            return self._pet_links
        if self.data is not None:
            return self.data.pet_links
        return None

    def _current_smartdoor_activity_records(self) -> dict[str, tuple[PetSafeExtendedSmartDoorActivityRecord, ...]]:
        """Return cached SmartDoor activity records."""
        if self._smartdoor_activity_records:
            return self._smartdoor_activity_records
        if self.data is not None:
            return self.data.smartdoor_activity_records
        return {}

    def _current_smartdoor_pet_states(self) -> dict[str, dict[str, PetSafeExtendedSmartDoorPetState]]:
        """Return cached SmartDoor pet states."""
        if self._smartdoor_pet_states:
            return self._smartdoor_pet_states
        if self.data is not None:
            return self.data.smartdoor_pet_states
        return {}

    def _current_smartdoor_schedule_rules(self) -> dict[str, tuple[PetSafeExtendedSmartDoorScheduleRule, ...]]:
        """Return cached SmartDoor schedule rules."""
        if self._smartdoor_schedule_rules:
            return self._smartdoor_schedule_rules
        if self.data is not None:
            return self.data.smartdoor_schedule_rules
        return {}

    def _current_smartdoor_schedule_summaries(self) -> dict[str, PetSafeExtendedSmartDoorScheduleSummary]:
        """Return cached SmartDoor schedule summaries."""
        if self._smartdoor_schedule_summaries:
            return self._smartdoor_schedule_summaries
        if self.data is not None:
            return self.data.smartdoor_schedule_summaries
        return {}

    def _current_smartdoor_pet_schedule_states(self) -> dict[str, dict[str, PetSafeExtendedSmartDoorPetScheduleState]]:
        """Return cached SmartDoor pet schedule states."""
        if self._smartdoor_pet_schedule_states:
            return self._smartdoor_pet_schedule_states
        if self.data is not None:
            return self.data.smartdoor_pet_schedule_states
        return {}

    @staticmethod
    def _refresh_due(
        last_refresh_monotonic: float | None,
        interval: timedelta,
        now_monotonic: float,
        *,
        force: bool = False,
    ) -> bool:
        """Return whether a cached value should be refreshed."""
        return (
            force
            or last_refresh_monotonic is None
            or (now_monotonic - last_refresh_monotonic) >= interval.total_seconds()
        )

    @staticmethod
    def _cleanup_timestamp_map(last_refresh_by_key: dict[str, float], active_keys: set[str]) -> None:
        """Drop per-device refresh timestamps for devices that no longer exist."""
        for key in tuple(last_refresh_by_key):
            if key not in active_keys:
                last_refresh_by_key.pop(key, None)

    @staticmethod
    def _cleanup_force_refresh_keys(force_refresh_keys: set[str], active_keys: set[str]) -> None:
        """Drop forced-refresh markers for devices that no longer exist."""
        force_refresh_keys.intersection_update(active_keys)

    def _cached_feeders_for_update(self) -> list[Any]:
        """Return the current feeder cache for a coordinator refresh cycle."""
        if self._feeders is not None:
            return list(self._feeders)
        if self.data is not None:
            return list(self.data.feeders)
        return []

    def _cached_litterboxes_for_update(self) -> list[Any]:
        """Return the current litterbox cache for a coordinator refresh cycle."""
        if self._litterboxes is not None:
            return list(self._litterboxes)
        if self.data is not None:
            return list(self.data.litterboxes)
        return []

    def _cached_smartdoors_for_update(self) -> list[Any]:
        """Return the current SmartDoor cache for a coordinator refresh cycle."""
        if self._smartdoors is not None:
            return list(self._smartdoors)
        if self.data is not None:
            return list(self.data.smartdoors)
        return []

    def _normalize_smartdoor_locked_mode(self, mode: str | None) -> str:
        """Return a supported SmartDoor locked-mode preference."""
        if smartdoor_modes_match(mode, SMARTDOOR_MODE_SMART):
            return SMARTDOOR_MODE_SMART
        return SMARTDOOR_MODE_MANUAL_LOCKED

    def _smartdoor_schedules_enabled(self) -> bool:
        """Return whether SmartDoor schedule entities and polling are enabled."""
        return bool(
            self.config_entry.options.get(
                CONF_ENABLE_SMARTDOOR_SCHEDULES,
                DEFAULT_ENABLE_SMARTDOOR_SCHEDULES,
            )
        )

    def _seed_smartdoor_locked_mode_preferences(self, smartdoors: list[Any]) -> None:
        """Seed SmartDoor locked-mode preferences from live device state."""
        previous_preferences = dict(self._smartdoor_locked_mode_preferences)
        updated_preferences: dict[str, str] = {}

        for door in smartdoors:
            api_name = cast(str, door.api_name)
            live_option = get_smartdoor_locked_mode_option(getattr(door, "mode", None))
            if live_option == "smart":
                updated_preferences[api_name] = SMARTDOOR_MODE_SMART
            elif live_option == "locked":
                updated_preferences[api_name] = SMARTDOOR_MODE_MANUAL_LOCKED
            else:
                updated_preferences[api_name] = previous_preferences.get(api_name, SMARTDOOR_MODE_MANUAL_LOCKED)

        self._smartdoor_locked_mode_preferences = updated_preferences

    async def get_feeders(self) -> list[Any]:
        """Return the list of feeders."""
        async with self._device_lock:
            try:
                if self._feeders is None:
                    if self.data is not None:
                        self._feeders = list(self.data.feeders)
                    else:
                        self._feeders = await self.api.get_feeders()
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
            return self._feeders or []

    async def get_litterboxes(self) -> list[Any]:
        """Return the list of litterboxes."""
        async with self._device_lock:
            try:
                if self._litterboxes is None:
                    if self.data is not None:
                        self._litterboxes = list(self.data.litterboxes)
                    else:
                        self._litterboxes = await self.api.get_litterboxes()
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
            return self._litterboxes or []

    async def get_smartdoors(self) -> list[Any]:
        """Return the list of smart doors."""
        async with self._device_lock:
            try:
                if self._smartdoors is None:
                    if self.data is not None:
                        self._smartdoors = list(self.data.smartdoors)
                    else:
                        self._smartdoors = await self.api.get_smartdoors()
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
            return self._smartdoors or []

    def get_pet_profile(self, pet_id: str) -> PetSafeExtendedPetProfile | None:
        """Return a pet profile from the most recent coordinator snapshot."""
        pet_links = self._current_pet_links()
        if pet_links is None:
            return None
        return pet_links.pets_by_id.get(pet_id)

    def get_product_ids_for_pet(self, pet_id: str) -> tuple[str, ...]:
        """Return linked product identifiers for a pet."""
        pet_links = self._current_pet_links()
        if pet_links is None:
            return ()
        return pet_links.product_ids_by_pet_id.get(pet_id, ())

    def get_pet_ids_for_product(self, product_id: str) -> tuple[str, ...]:
        """Return linked pet identifiers for a product."""
        pet_links = self._current_pet_links()
        if pet_links is None:
            return ()
        return pet_links.pet_ids_by_product_id.get(product_id, ())

    def get_smartdoor_pet_ids(self, api_name: str) -> tuple[str, ...]:
        """Return pet identifiers linked to a SmartDoor."""
        return self.get_pet_ids_for_product(api_name)

    def get_smartdoor_pet_state(self, api_name: str, pet_id: str) -> PetSafeExtendedSmartDoorPetState | None:
        """Return the latest SmartDoor pet state for a linked pet."""
        return self._current_smartdoor_pet_states().get(api_name, {}).get(pet_id)

    def get_smartdoor_schedule_rules(self, api_name: str) -> tuple[PetSafeExtendedSmartDoorScheduleRule, ...] | None:
        """Return the cached SmartDoor schedule rules for a door."""
        return self._current_smartdoor_schedule_rules().get(api_name)

    def get_smartdoor_schedule_summary(self, api_name: str) -> PetSafeExtendedSmartDoorScheduleSummary | None:
        """Return the cached SmartDoor schedule summary for a door."""
        return self._current_smartdoor_schedule_summaries().get(api_name)

    def get_smartdoor_scheduled_pet_ids(self, api_name: str) -> tuple[str, ...]:
        """Return linked pets with at least one enabled SmartDoor schedule."""
        if not self._smartdoor_schedules_enabled():
            return ()

        rules = self.get_smartdoor_schedule_rules(api_name) or ()
        scheduled_pet_ids = get_smartdoor_scheduled_pet_ids(rules)
        if not scheduled_pet_ids:
            return ()

        linked_pet_ids = self.get_smartdoor_pet_ids(api_name)
        scheduled_pet_id_set = set(scheduled_pet_ids)
        ordered = tuple(pet_id for pet_id in linked_pet_ids if pet_id in scheduled_pet_id_set)
        extras = tuple(pet_id for pet_id in scheduled_pet_ids if pet_id not in set(ordered))
        return ordered + extras

    def get_smartdoor_pet_schedule_state(
        self,
        api_name: str,
        pet_id: str,
    ) -> PetSafeExtendedSmartDoorPetScheduleState | None:
        """Return the current SmartDoor schedule-derived state for a pet."""
        return self._current_smartdoor_pet_schedule_states().get(api_name, {}).get(pet_id)

    def get_smartdoor_locked_mode_preference(self, api_name: str) -> str:
        """Return the preferred SmartDoor mode to apply when locking."""
        return self._smartdoor_locked_mode_preferences.get(api_name, SMARTDOOR_MODE_MANUAL_LOCKED)

    def get_smartdoor_locked_mode_option(self, api_name: str) -> str:
        """Return the Home Assistant option for the preferred locked mode."""
        option = get_smartdoor_locked_mode_option(self.get_smartdoor_locked_mode_preference(api_name))
        return option or "locked"

    async def async_refresh_feeder_schedule_data(self, api_name: str) -> None:
        """Force a feeder schedule refresh on the next coordinator cycle."""
        await self.get_feeders()
        if self._find_cached_feeder(api_name) is None:
            raise ValueError(f"Unknown feeder API name: {api_name}")
        self._force_refresh_feeder_schedule_api_names.add(api_name)
        await self.async_request_refresh()

    async def async_refresh_smartdoor_schedule_data(self, api_name: str) -> None:
        """Force a SmartDoor schedule and preference refresh on the next coordinator cycle."""
        await self.get_smartdoors()
        if self._find_cached_smartdoor(api_name) is None:
            raise ValueError(f"Unknown SmartDoor API name: {api_name}")
        self._force_refresh_smartdoor_schedule_api_names.add(api_name)
        await self.async_request_refresh()

    async def async_refresh_pet_links(self) -> None:
        """Force a pet-link refresh on the next coordinator cycle."""
        self._force_refresh_pet_links = True
        await self.async_request_refresh()

    @callback
    def async_set_smartdoor_locked_mode_preference(self, api_name: str, mode: str) -> None:
        """Persist the preferred SmartDoor mode to use when the door is locked."""
        normalized_mode = self._normalize_smartdoor_locked_mode(mode)
        if self._smartdoor_locked_mode_preferences.get(api_name) == normalized_mode:
            return

        self._smartdoor_locked_mode_preferences[api_name] = normalized_mode
        self.async_set_updated_data(self._cached_snapshot())

    @callback
    def async_subscribe_smartdoor_activity(
        self,
        api_name: str,
        update_listener: Callable[[PetSafeExtendedSmartDoorActivityRecord], None],
    ) -> Callable[[], None]:
        """Subscribe to new SmartDoor activity records for a specific door."""
        listeners = self._smartdoor_activity_listeners.setdefault(api_name, [])
        listeners.append(update_listener)

        @callback
        def unsubscribe() -> None:
            current_listeners = self._smartdoor_activity_listeners.get(api_name)
            if not current_listeners:
                return
            if update_listener in current_listeners:
                current_listeners.remove(update_listener)
            if not current_listeners:
                self._smartdoor_activity_listeners.pop(api_name, None)

        return unsubscribe

    def get_pet_display_name(self, api_name: str, pet_id: str) -> str:
        """Return a user-facing pet name without exposing raw identifiers."""
        profile = self.get_pet_profile(pet_id)
        if profile is not None and profile.name:
            return profile.name

        linked_pet_ids = self.get_smartdoor_pet_ids(api_name)
        try:
            pet_index = linked_pet_ids.index(pet_id) + 1
        except ValueError:
            pet_index = 1
        return f"Pet {pet_index}"

    async def async_feed_feeder(
        self,
        api_name: str,
        amount: int,
        slow_feed: bool | None,
        *,
        refresh: bool = True,
    ) -> None:
        """Feed a meal from a feeder."""
        await self.get_feeders()
        async with self._device_lock:
            feeder = self._find_cached_feeder(api_name)
            if feeder is None:
                raise ValueError(f"Unknown feeder API name: {api_name}")
            try:
                await feeder.feed(amount, slow_feed, False)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_feeders = True
        self._force_refresh_feeder_last_feeding_api_names.add(api_name)
        if refresh:
            await self.async_request_refresh()

    async def async_prime_feeder(self, api_name: str, *, refresh: bool = True) -> None:
        """Prime a feeder by dispensing 5/8 cup."""
        await self.async_feed_feeder(api_name, 5, False, refresh=refresh)

    async def async_set_feeder_child_lock(self, api_name: str, enabled: bool, *, refresh: bool = True) -> None:
        """Enable or disable the feeder child lock."""
        await self.get_feeders()
        async with self._device_lock:
            feeder = self._find_cached_feeder(api_name)
            if feeder is None:
                raise ValueError(f"Unknown feeder API name: {api_name}")
            try:
                await feeder.lock(enabled)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_feeders = True
        if refresh:
            await self.async_request_refresh()

    async def async_set_feeder_paused(self, api_name: str, enabled: bool, *, refresh: bool = True) -> None:
        """Pause or resume a feeder."""
        await self.get_feeders()
        async with self._device_lock:
            feeder = self._find_cached_feeder(api_name)
            if feeder is None:
                raise ValueError(f"Unknown feeder API name: {api_name}")
            try:
                await feeder.pause(enabled)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_feeders = True
        if refresh:
            await self.async_request_refresh()

    async def async_set_feeder_slow_feed(self, api_name: str, enabled: bool, *, refresh: bool = True) -> None:
        """Enable or disable feeder slow-feed mode."""
        await self.get_feeders()
        async with self._device_lock:
            feeder = self._find_cached_feeder(api_name)
            if feeder is None:
                raise ValueError(f"Unknown feeder API name: {api_name}")
            try:
                await feeder.slow_feed(enabled)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_feeders = True
        if refresh:
            await self.async_request_refresh()

    async def async_add_feeding_schedule(
        self,
        api_name: str,
        feed_time: str,
        amount: int,
        *,
        refresh: bool = True,
    ) -> None:
        """Add a feeding schedule to a feeder."""
        await self.get_feeders()
        async with self._device_lock:
            feeder = self._find_cached_feeder(api_name)
            if feeder is None:
                raise ValueError(f"Unknown feeder API name: {api_name}")
            try:
                await feeder.schedule_feed(feed_time, amount, False)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_feeder_schedule_api_names.add(api_name)
        if refresh:
            await self.async_request_refresh()

    async def async_delete_feeding_schedule(
        self,
        api_name: str,
        feed_time: str,
        *,
        refresh: bool = True,
    ) -> None:
        """Delete a feeding schedule from a feeder."""
        await self.get_feeders()
        async with self._device_lock:
            feeder = self._find_cached_feeder(api_name)
            if feeder is None:
                raise ValueError(f"Unknown feeder API name: {api_name}")
            try:
                schedules = await feeder.get_schedules()
                for schedule in schedules:
                    schedule_time = cast(str, schedule["time"])
                    if feed_time in {schedule_time, f"{schedule_time}:00"}:
                        await feeder.delete_schedule(str(schedule["id"]), False)
                        break
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_feeder_schedule_api_names.add(api_name)
        if refresh:
            await self.async_request_refresh()

    async def async_delete_all_feeding_schedules(self, api_name: str, *, refresh: bool = True) -> None:
        """Delete all feeding schedules from a feeder."""
        await self.get_feeders()
        async with self._device_lock:
            feeder = self._find_cached_feeder(api_name)
            if feeder is None:
                raise ValueError(f"Unknown feeder API name: {api_name}")
            try:
                await feeder.delete_all_schedules(False)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_feeder_schedule_api_names.add(api_name)
        if refresh:
            await self.async_request_refresh()

    async def async_modify_feeding_schedule(
        self,
        api_name: str,
        feed_time: str,
        amount: int,
        *,
        refresh: bool = True,
    ) -> None:
        """Modify an existing feeding schedule."""
        await self.get_feeders()
        async with self._device_lock:
            feeder = self._find_cached_feeder(api_name)
            if feeder is None:
                raise ValueError(f"Unknown feeder API name: {api_name}")
            try:
                schedules = await feeder.get_schedules()
                for schedule in schedules:
                    schedule_time = cast(str, schedule["time"])
                    if feed_time in {schedule_time, f"{schedule_time}:00"}:
                        await feeder.modify_schedule(schedule_time, amount, str(schedule["id"]), False)
                        break
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_feeder_schedule_api_names.add(api_name)
        if refresh:
            await self.async_request_refresh()

    async def async_rake_litterbox(self, api_name: str, *, refresh: bool = True) -> None:
        """Run the litterbox rake."""
        await self.get_litterboxes()
        async with self._device_lock:
            litterbox = self._find_cached_litterbox(api_name)
            if litterbox is None:
                raise ValueError(f"Unknown litterbox API name: {api_name}")
            try:
                await litterbox.rake(False)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_litterboxes = True
        self._force_refresh_litterbox_activity_api_names.add(api_name)
        if refresh:
            await self.async_request_refresh()

    async def async_reset_litterbox(self, api_name: str, *, refresh: bool = True) -> None:
        """Reset a litterbox counter."""
        await self.get_litterboxes()
        async with self._device_lock:
            litterbox = self._find_cached_litterbox(api_name)
            if litterbox is None:
                raise ValueError(f"Unknown litterbox API name: {api_name}")
            try:
                await litterbox.reset(0, False)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_litterboxes = True
        self._force_refresh_litterbox_activity_api_names.add(api_name)
        if refresh:
            await self.async_request_refresh()

    async def async_set_litterbox_rake_timer(
        self,
        api_name: str,
        minutes: int,
        *,
        refresh: bool = True,
    ) -> None:
        """Set the litterbox rake delay timer."""
        await self.get_litterboxes()
        async with self._device_lock:
            litterbox = self._find_cached_litterbox(api_name)
            if litterbox is None:
                raise ValueError(f"Unknown litterbox API name: {api_name}")
            try:
                await litterbox.modify_timer(minutes, False)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        self._force_refresh_litterboxes = True
        self._force_refresh_litterbox_activity_api_names.add(api_name)
        if refresh:
            await self.async_request_refresh()

    async def async_set_smartdoor_lock(self, api_name: str, locked: bool) -> Any:
        """Lock or unlock a smart door and return the refreshed device."""
        if not locked:
            return await self.async_set_smartdoor_operating_mode(api_name, SMARTDOOR_MODE_MANUAL_UNLOCKED)

        expected_mode = self.get_smartdoor_locked_mode_preference(api_name)
        return await self.async_set_smartdoor_operating_mode(api_name, expected_mode)

    async def async_set_smartdoor_operating_mode(self, api_name: str, mode: str) -> Any:
        """Set a SmartDoor operating mode and return the refreshed device."""
        normalized_mode = (
            self._normalize_smartdoor_locked_mode(mode)
            if not smartdoor_modes_match(
                mode,
                SMARTDOOR_MODE_MANUAL_UNLOCKED,
            )
            else SMARTDOOR_MODE_MANUAL_UNLOCKED
        )
        await self.get_smartdoors()
        async with self._device_lock:
            door = self._find_cached_smartdoor(api_name)
            if door is None:
                raise ValueError(f"Unknown SmartDoor API name: {api_name}")
            try:
                await door.set_mode(normalized_mode, update_data=False)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        refreshed = await self.async_refresh_smartdoor(api_name, expected_mode=normalized_mode)
        if not smartdoor_modes_match(normalized_mode, SMARTDOOR_MODE_MANUAL_UNLOCKED):
            self.async_set_smartdoor_locked_mode_preference(api_name, normalized_mode)
        return refreshed

    async def async_set_smartdoor_locked_mode(self, api_name: str, mode: str) -> Any:
        """Set the preferred SmartDoor locked mode and apply it immediately when already locked."""
        normalized_mode = self._normalize_smartdoor_locked_mode(mode)
        await self.get_smartdoors()
        async with self._device_lock:
            door = self._find_cached_smartdoor(api_name)
            if door is None:
                raise ValueError(f"Unknown SmartDoor API name: {api_name}")
            current_mode = getattr(door, "mode", None)

        if smartdoor_modes_match(current_mode, SMARTDOOR_MODE_MANUAL_UNLOCKED):
            self.async_set_smartdoor_locked_mode_preference(api_name, normalized_mode)
            return door

        if smartdoor_modes_match(current_mode, normalized_mode):
            self.async_set_smartdoor_locked_mode_preference(api_name, normalized_mode)
            return door

        return await self.async_set_smartdoor_operating_mode(api_name, normalized_mode)

    async def async_set_smartdoor_final_act(self, api_name: str, final_act: str) -> Any:
        """Set a SmartDoor final-act state and return the refreshed device."""
        await self.get_smartdoors()
        async with self._device_lock:
            door = self._find_cached_smartdoor(api_name)
            if door is None:
                raise ValueError(f"Unknown SmartDoor API name: {api_name}")
            try:
                await door.set_final_act(final_act, update_data=False)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        return await self.async_refresh_smartdoor(api_name, expected_final_act=final_act)

    async def async_refresh_smartdoor(
        self,
        api_name: str,
        *,
        expected_mode: str | None = None,
        expected_final_act: str | None = None,
        refresh_attempts: int = 4,
        refresh_interval: float = 1.0,
    ) -> Any:
        """Refresh a SmartDoor after sending a command to it."""
        await self.get_smartdoors()
        attempts = max(refresh_attempts, 1)
        refreshed_door: Any | None = None

        for attempt in range(attempts):
            async with self._device_lock:
                door = self._find_cached_smartdoor(api_name)
                if door is None:
                    raise ValueError(f"Unknown SmartDoor API name: {api_name}")

                try:
                    await door.update_data()
                except httpx.HTTPStatusError as err:
                    if self._is_auth_error(err):
                        self._raise_auth_failed(err)
                    raise

                if self._smartdoors is None:
                    self._smartdoors = []
                for index, cached_door in enumerate(self._smartdoors):
                    if cached_door.api_name == door.api_name:
                        self._smartdoors[index] = door
                        break
                else:
                    self._smartdoors.append(door)

                refreshed_door = door
                self._update_live_smartdoor_schedule_state(door)
                self.async_set_updated_data(self._cached_snapshot())

                if (expected_mode is None or smartdoor_modes_match(door.mode, expected_mode)) and (
                    expected_final_act is None
                    or smartdoor_final_acts_match(get_smartdoor_final_act_value(door), expected_final_act)
                ):
                    return door

            if attempt < attempts - 1:
                await asyncio.sleep(refresh_interval)

        if refreshed_door is None:
            raise ValueError(f"Unknown SmartDoor API name: {api_name}")
        LOGGER.debug(
            "SmartDoor %s did not report expected mode %s / final act %s after %s refresh attempts",
            api_name,
            expected_mode,
            expected_final_act,
            attempts,
        )
        return refreshed_door

    async def _async_get_feeders_for_update(self, now_monotonic: float) -> list[Any]:
        """Return the current feeder list, refreshing it when due."""
        refresh_due = self._refresh_due(
            self._feeders_last_refresh_monotonic,
            DEVICE_LIST_REFRESH_INTERVAL,
            now_monotonic,
            force=self._force_refresh_feeders,
        )
        if not refresh_due:
            return self._cached_feeders_for_update()

        feeders = await self.api.get_feeders()
        self._feeders_last_refresh_monotonic = now_monotonic
        self._force_refresh_feeders = False
        return feeders

    async def _async_get_litterboxes_for_update(self, now_monotonic: float) -> list[Any]:
        """Return the current litterbox list, refreshing it when due."""
        refresh_due = self._refresh_due(
            self._litterboxes_last_refresh_monotonic,
            DEVICE_LIST_REFRESH_INTERVAL,
            now_monotonic,
            force=self._force_refresh_litterboxes,
        )
        if not refresh_due:
            return self._cached_litterboxes_for_update()

        litterboxes = await self.api.get_litterboxes()
        self._litterboxes_last_refresh_monotonic = now_monotonic
        self._force_refresh_litterboxes = False
        return litterboxes

    async def _async_get_smartdoors_for_update(self, now_monotonic: float) -> list[Any]:
        """Return the current SmartDoor list, refreshing it when due."""
        refresh_due = self._refresh_due(
            self._smartdoors_last_refresh_monotonic,
            DEVICE_LIST_REFRESH_INTERVAL,
            now_monotonic,
            force=self._force_refresh_smartdoors,
        )
        if not refresh_due:
            return self._cached_smartdoors_for_update()

        smartdoors = await self.api.get_smartdoors()
        self._smartdoors_last_refresh_monotonic = now_monotonic
        self._force_refresh_smartdoors = False
        return smartdoors

    def _rebuild_smartdoor_schedule_views(
        self,
        smartdoors: list[Any],
        pet_links: PetSafeExtendedPetLinkData,
        rules_by_door: dict[str, tuple[PetSafeExtendedSmartDoorScheduleRule, ...]],
    ) -> tuple[
        dict[str, PetSafeExtendedSmartDoorScheduleSummary],
        dict[str, dict[str, PetSafeExtendedSmartDoorPetScheduleState]],
    ]:
        """Recompute schedule summaries and per-pet state from cached rules."""
        previous_summaries = copy_smartdoor_schedule_summaries(self._current_smartdoor_schedule_summaries())
        previous_pet_schedule_states = copy_smartdoor_pet_schedule_states(self._current_smartdoor_pet_schedule_states())
        schedule_summaries: dict[str, PetSafeExtendedSmartDoorScheduleSummary] = {}
        pet_schedule_states: dict[str, dict[str, PetSafeExtendedSmartDoorPetScheduleState]] = {}
        default_timezone = dt_util.DEFAULT_TIME_ZONE or UTC
        now = dt_util.now().astimezone(default_timezone)
        current_data = self.data or PetSafeExtendedCoordinatorData()

        for door in smartdoors:
            door_api_name = cast(str, door.api_name)
            rules = rules_by_door.get(door_api_name) or current_data.smartdoor_schedule_rules.get(door_api_name)
            if rules is None:
                if door_api_name in previous_summaries:
                    schedule_summaries[door_api_name] = previous_summaries[door_api_name]
                if door_api_name in previous_pet_schedule_states:
                    pet_schedule_states[door_api_name] = previous_pet_schedule_states[door_api_name]
                continue

            linked_pet_ids = tuple(sorted(pet_links.pet_ids_by_product_id.get(door_api_name, ())))
            schedule_summaries[door_api_name] = build_smartdoor_schedule_summary(
                rules,
                linked_pet_ids,
                now=now,
                default_timezone=default_timezone,
            )
            pet_schedule_states[door_api_name] = build_smartdoor_pet_schedule_states(
                rules,
                linked_pet_ids,
                door_mode=getattr(door, "mode", None),
                now=now,
                default_timezone=default_timezone,
            )

        return schedule_summaries, pet_schedule_states

    async def _async_update_data(self) -> PetSafeExtendedCoordinatorData:
        """Fetch data from the PetSafe API."""
        try:
            async with self._device_lock:
                now_monotonic = time.monotonic()
                feeders = await self._async_get_feeders_for_update(now_monotonic)
                litterboxes = await self._async_get_litterboxes_for_update(now_monotonic)
                smartdoors = await self._async_get_smartdoors_for_update(now_monotonic)
                feeder_details = await self._async_build_feeder_details(feeders, now_monotonic)
                litterbox_details = await self._async_build_litterbox_details(litterboxes, now_monotonic)
                pet_links = await self._async_build_pet_links(feeders, litterboxes, smartdoors)
                (
                    smartdoor_activity_records,
                    smartdoor_pet_states,
                    dispatch_records_by_door,
                ) = await self._async_build_smartdoor_pet_states(smartdoors, pet_links, now_monotonic)
                smartdoor_schedule_rules = copy_smartdoor_schedule_rules(self._current_smartdoor_schedule_rules())
                if self._smartdoor_schedules_enabled():
                    smartdoor_schedule_rules = await self._async_build_smartdoor_schedule_data(
                        smartdoors,
                        pet_links,
                        now_monotonic,
                    )
                    smartdoor_schedule_summaries, smartdoor_pet_schedule_states = (
                        self._rebuild_smartdoor_schedule_views(
                            smartdoors,
                            pet_links,
                            smartdoor_schedule_rules,
                        )
                    )
                else:
                    smartdoor_schedule_summaries = {}
                    smartdoor_pet_schedule_states = {}
                self._feeders = feeders
                self._litterboxes = litterboxes
                self._smartdoors = smartdoors
                self._seed_smartdoor_locked_mode_preferences(smartdoors)
                self._feeder_details = feeder_details
                self._litterbox_details = litterbox_details
                self._pet_links = pet_links
                self._smartdoor_activity_records = smartdoor_activity_records
                self._smartdoor_pet_states = smartdoor_pet_states
                self._smartdoor_schedule_rules = smartdoor_schedule_rules
                self._smartdoor_schedule_summaries = smartdoor_schedule_summaries
                self._smartdoor_pet_schedule_states = smartdoor_pet_schedule_states
                data = PetSafeExtendedCoordinatorData(
                    feeders=list(feeders),
                    litterboxes=list(litterboxes),
                    smartdoors=list(smartdoors),
                    feeder_details=dict(feeder_details),
                    litterbox_details=dict(litterbox_details),
                    pet_links=copy_pet_link_data(pet_links),
                    smartdoor_activity_records=copy_smartdoor_activity_records(smartdoor_activity_records),
                    smartdoor_pet_states=copy_smartdoor_pet_states(smartdoor_pet_states),
                    smartdoor_schedule_rules=copy_smartdoor_schedule_rules(smartdoor_schedule_rules),
                    smartdoor_schedule_summaries=copy_smartdoor_schedule_summaries(smartdoor_schedule_summaries),
                    smartdoor_pet_schedule_states=copy_smartdoor_pet_schedule_states(smartdoor_pet_schedule_states),
                )
        except httpx.HTTPStatusError as err:
            if self._is_auth_error(err):
                self._raise_auth_failed(err)
            raise UpdateFailed("Failed to refresh PetSafe devices") from err
        except Exception as err:
            raise UpdateFailed("Failed to refresh PetSafe devices") from err
        else:
            self._async_dispatch_smartdoor_activity(dispatch_records_by_door)
            return data

    async def _async_build_pet_links(
        self,
        feeders: list[Any],
        litterboxes: list[Any],
        smartdoors: list[Any],
    ) -> PetSafeExtendedPetLinkData:
        """Build or reuse the slow-changing pet/product linkage graph."""
        previous_data = copy_pet_link_data(self._current_pet_links())
        now_monotonic = time.monotonic()

        if (
            not self._force_refresh_pet_links
            and self._pet_links_last_refresh_monotonic is not None
            and (now_monotonic - self._pet_links_last_refresh_monotonic) < PET_LINK_REFRESH_INTERVAL.total_seconds()
        ):
            return previous_data

        try:
            pet_links = await async_build_pet_link_data(
                self.hass,
                self.api,
                feeders,
                litterboxes,
                smartdoors,
                previous_data,
            )
        except httpx.HTTPStatusError as err:
            if self._is_auth_error(err):
                self._raise_auth_failed(err)
            LOGGER.debug("Failed to refresh PetSafe pet links: %s", err)
            return previous_data
        except Exception as err:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
            LOGGER.debug("Failed to refresh PetSafe pet links: %s", err)
            return previous_data

        self._pet_links_last_refresh_monotonic = now_monotonic
        self._force_refresh_pet_links = False
        return pet_links

    async def _async_build_smartdoor_pet_states(
        self,
        smartdoors: list[Any],
        pet_links: PetSafeExtendedPetLinkData,
        now_monotonic: float,
    ) -> tuple[
        dict[str, tuple[PetSafeExtendedSmartDoorActivityRecord, ...]],
        dict[str, dict[str, PetSafeExtendedSmartDoorPetState]],
        dict[str, tuple[PetSafeExtendedSmartDoorActivityRecord, ...]],
    ]:
        """Build SmartDoor activity caches used by pet sensor entities."""
        previous_records = copy_smartdoor_activity_records(self._current_smartdoor_activity_records())
        previous_states = copy_smartdoor_pet_states(self._current_smartdoor_pet_states())
        activity_records: dict[str, tuple[PetSafeExtendedSmartDoorActivityRecord, ...]] = {}
        pet_states: dict[str, dict[str, PetSafeExtendedSmartDoorPetState]] = {}
        dispatch_records_by_door: dict[str, tuple[PetSafeExtendedSmartDoorActivityRecord, ...]] = {}

        for door in smartdoors:
            door_api_name = cast(str, door.api_name)
            linked_pet_ids = tuple(sorted(pet_links.pet_ids_by_product_id.get(door_api_name, ())))

            door_previous_states = previous_states.get(door_api_name, {})
            current_states = seed_pet_states(linked_pet_ids)
            for pet_id, previous_state in door_previous_states.items():
                if pet_id in current_states:
                    current_states[pet_id] = previous_state

            activity_items: list[dict[str, Any]] = []
            try:
                refresh_due = self._refresh_due(
                    self._smartdoor_activity_last_refresh_by_door.get(door_api_name),
                    SMARTDOOR_ACTIVITY_REFRESH_INTERVAL,
                    now_monotonic,
                )
                if refresh_due:
                    since = self._smartdoor_activity_cursor_by_door.get(door_api_name)
                    if since is None:
                        activity_items = await door.get_activity(limit=SMARTDOOR_ACTIVITY_INITIAL_LIMIT)
                    else:
                        activity_items = await door.get_activity(since=since)
                    self._smartdoor_activity_last_refresh_by_door[door_api_name] = now_monotonic
                else:
                    since = self._smartdoor_activity_cursor_by_door.get(door_api_name)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                LOGGER.debug("Failed to refresh SmartDoor activity for %s: %s", door_api_name, err)
                activity_records[door_api_name] = previous_records.get(door_api_name, ())
                pet_states[door_api_name] = current_states
                dispatch_records_by_door[door_api_name] = ()
                continue
            except Exception as err:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
                LOGGER.debug("Failed to refresh SmartDoor activity for %s: %s", door_api_name, err)
                activity_records[door_api_name] = previous_records.get(door_api_name, ())
                pet_states[door_api_name] = current_states
                dispatch_records_by_door[door_api_name] = ()
                continue

            parsed_records = parse_smartdoor_activity_records(activity_items, linked_pet_ids)
            previous_door_records = previous_records.get(door_api_name, ())
            activity_records[door_api_name] = merge_activity_records(previous_door_records, parsed_records)
            pet_states[door_api_name] = apply_activity_records(
                linked_pet_ids,
                current_states,
                activity_records[door_api_name],
            )
            if since is None:
                dispatch_records_by_door[door_api_name] = ()
            else:
                dispatch_records_by_door[door_api_name] = tuple(
                    get_new_activity_records(previous_door_records, parsed_records)
                )

            cursor = extract_cursor(activity_items, self._smartdoor_activity_cursor_by_door.get(door_api_name))
            if cursor is not None:
                self._smartdoor_activity_cursor_by_door[door_api_name] = cursor

        current_door_ids = {cast(str, door.api_name) for door in smartdoors}
        for api_name in tuple(self._smartdoor_activity_cursor_by_door):
            if api_name not in current_door_ids:
                self._smartdoor_activity_cursor_by_door.pop(api_name, None)
        self._cleanup_timestamp_map(self._smartdoor_activity_last_refresh_by_door, current_door_ids)

        return activity_records, pet_states, dispatch_records_by_door

    async def _async_build_smartdoor_schedule_data(
        self,
        smartdoors: list[Any],
        pet_links: PetSafeExtendedPetLinkData,
        now_monotonic: float,
    ) -> dict[str, tuple[PetSafeExtendedSmartDoorScheduleRule, ...]]:
        """Refresh SmartDoor schedule rules only when the slow schedule bucket is due."""
        previous_rules = copy_smartdoor_schedule_rules(self._current_smartdoor_schedule_rules())
        schedule_rules: dict[str, tuple[PetSafeExtendedSmartDoorScheduleRule, ...]] = {}

        for door in smartdoors:
            door_api_name = cast(str, door.api_name)
            linked_pet_ids = tuple(sorted(pet_links.pet_ids_by_product_id.get(door_api_name, ())))
            pet_names_by_id: dict[str, str] = {}
            for index, pet_id in enumerate(linked_pet_ids, start=1):
                profile = pet_links.pets_by_id.get(pet_id)
                pet_names_by_id[pet_id] = profile.name if profile is not None and profile.name else f"Pet {index}"

            try:
                refresh_due = self._refresh_due(
                    self._smartdoor_schedule_last_refresh_by_door.get(door_api_name),
                    SMARTDOOR_SCHEDULE_REFRESH_INTERVAL,
                    now_monotonic,
                    force=door_api_name in self._force_refresh_smartdoor_schedule_api_names,
                )
                if not refresh_due:
                    if door_api_name in previous_rules:
                        schedule_rules[door_api_name] = previous_rules[door_api_name]
                    continue

                schedules = await door.get_schedules()
                preferences = await door.get_preferences()
                self._smartdoor_schedule_last_refresh_by_door[door_api_name] = now_monotonic
                self._force_refresh_smartdoor_schedule_api_names.discard(door_api_name)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                LOGGER.debug("Failed to refresh SmartDoor schedules for %s: %s", door_api_name, err)
                if door_api_name in previous_rules:
                    schedule_rules[door_api_name] = previous_rules[door_api_name]
                continue
            except Exception as err:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
                LOGGER.debug("Failed to refresh SmartDoor schedules for %s: %s", door_api_name, err)
                if door_api_name in previous_rules:
                    schedule_rules[door_api_name] = previous_rules[door_api_name]
                continue

            timezone = cast(str | None, preferences.get("tz")) if isinstance(preferences, dict) else None
            schedule_rules[door_api_name] = parse_smartdoor_schedule_rules(
                schedules if isinstance(schedules, list) else [],
                timezone=timezone or getattr(door, "timezone", None),
                pet_names_by_id=pet_names_by_id,
            )
        current_door_ids = {cast(str, door.api_name) for door in smartdoors}
        self._cleanup_timestamp_map(self._smartdoor_schedule_last_refresh_by_door, current_door_ids)
        self._cleanup_force_refresh_keys(self._force_refresh_smartdoor_schedule_api_names, current_door_ids)
        return schedule_rules

    def _update_live_smartdoor_schedule_state(self, door: Any) -> None:
        """Recompute per-pet schedule state after a live SmartDoor mode refresh."""
        if not self._smartdoor_schedules_enabled():
            return

        door_api_name = cast(str, door.api_name)
        rules = self._current_smartdoor_schedule_rules().get(door_api_name)
        if rules is None:
            return

        pet_links = self._current_pet_links()
        linked_pet_ids = tuple(sorted(pet_links.pet_ids_by_product_id.get(door_api_name, ()))) if pet_links else ()
        default_timezone = dt_util.DEFAULT_TIME_ZONE or UTC
        now = dt_util.now().astimezone(default_timezone)
        self._smartdoor_pet_schedule_states[door_api_name] = build_smartdoor_pet_schedule_states(
            rules,
            linked_pet_ids,
            door_mode=getattr(door, "mode", None),
            now=now,
            default_timezone=default_timezone,
        )
        self._smartdoor_schedule_summaries[door_api_name] = build_smartdoor_schedule_summary(
            rules,
            linked_pet_ids,
            now=now,
            default_timezone=default_timezone,
        )

    @callback
    def _async_dispatch_smartdoor_activity(
        self,
        records_by_door: dict[str, tuple[PetSafeExtendedSmartDoorActivityRecord, ...]],
    ) -> None:
        """Dispatch new SmartDoor activity records to subscribed listeners."""
        for api_name, records in records_by_door.items():
            if not records:
                continue
            listeners = tuple(self._smartdoor_activity_listeners.get(api_name, ()))
            if not listeners:
                continue
            for record in records:
                for listener in listeners:
                    listener(record)

    async def _async_build_feeder_details(
        self,
        feeders: list[Any],
        now_monotonic: float,
    ) -> dict[str, PetSafeExtendedFeederDetails]:
        """Build supplemental feeder state."""
        previous = self.data.feeder_details if self.data else {}
        details: dict[str, PetSafeExtendedFeederDetails] = {}
        active_feeder_ids = {cast(str, feeder.api_name) for feeder in feeders}

        for feeder in feeders:
            feeder_api_name = cast(str, feeder.api_name)
            last_feeding = previous.get(feeder_api_name, PetSafeExtendedFeederDetails()).last_feeding
            schedules = list(self._feeder_schedule_payloads.get(feeder_api_name, ()))

            last_feeding_due = self._refresh_due(
                self._feeder_last_feeding_last_refresh_by_feeder.get(feeder_api_name),
                FEEDER_LAST_FEEDING_REFRESH_INTERVAL,
                now_monotonic,
                force=feeder_api_name in self._force_refresh_feeder_last_feeding_api_names,
            )
            schedules_due = self._refresh_due(
                self._feeder_schedule_last_refresh_by_feeder.get(feeder_api_name),
                FEEDER_SCHEDULE_REFRESH_INTERVAL,
                now_monotonic,
                force=feeder_api_name in self._force_refresh_feeder_schedule_api_names,
            )

            try:
                if last_feeding_due:
                    feeding = await feeder.get_last_feeding()
                    last_feeding = self._parse_feeding_timestamp(feeding)
                    self._feeder_last_feeding_last_refresh_by_feeder[feeder_api_name] = now_monotonic
                    self._force_refresh_feeder_last_feeding_api_names.discard(feeder_api_name)

                if schedules_due:
                    schedules = await feeder.get_schedules()
                    cached_schedules = tuple(schedule for schedule in schedules if isinstance(schedule, dict))
                    self._feeder_schedule_payloads[feeder_api_name] = cached_schedules
                    schedules = list(cached_schedules)
                    self._feeder_schedule_last_refresh_by_feeder[feeder_api_name] = now_monotonic
                    self._force_refresh_feeder_schedule_api_names.discard(feeder_api_name)

                details[feeder_api_name] = PetSafeExtendedFeederDetails(
                    last_feeding=last_feeding,
                    next_feeding=self._get_next_feeding_time(schedules),
                )
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                LOGGER.debug("Failed to refresh feeder details for %s: %s", feeder_api_name, err)
                details[feeder_api_name] = previous.get(feeder_api_name, PetSafeExtendedFeederDetails())
            except Exception as err:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
                LOGGER.debug("Failed to refresh feeder details for %s: %s", feeder_api_name, err)
                details[feeder_api_name] = previous.get(feeder_api_name, PetSafeExtendedFeederDetails())

        self._cleanup_timestamp_map(self._feeder_last_feeding_last_refresh_by_feeder, active_feeder_ids)
        self._cleanup_timestamp_map(self._feeder_schedule_last_refresh_by_feeder, active_feeder_ids)
        self._cleanup_force_refresh_keys(self._force_refresh_feeder_last_feeding_api_names, active_feeder_ids)
        self._cleanup_force_refresh_keys(self._force_refresh_feeder_schedule_api_names, active_feeder_ids)
        for feeder_api_name in tuple(self._feeder_schedule_payloads):
            if feeder_api_name not in active_feeder_ids:
                self._feeder_schedule_payloads.pop(feeder_api_name, None)

        return details

    async def _async_build_litterbox_details(
        self,
        litterboxes: list[Any],
        now_monotonic: float,
    ) -> dict[str, PetSafeExtendedLitterboxDetails]:
        """Build supplemental litterbox state."""
        previous = self.data.litterbox_details if self.data else {}
        details: dict[str, PetSafeExtendedLitterboxDetails] = {}
        active_litterbox_ids = {cast(str, litterbox.api_name) for litterbox in litterboxes}

        for litterbox in litterboxes:
            litterbox_api_name = cast(str, litterbox.api_name)
            try:
                refresh_due = self._refresh_due(
                    self._litterbox_activity_last_refresh_by_litterbox.get(litterbox_api_name),
                    LITTERBOX_ACTIVITY_REFRESH_INTERVAL,
                    now_monotonic,
                    force=litterbox_api_name in self._force_refresh_litterbox_activity_api_names,
                )
                if refresh_due:
                    events = await litterbox.get_activity()
                    details[litterbox_api_name] = self._parse_litterbox_activity(litterbox, events)
                    self._litterbox_activity_last_refresh_by_litterbox[litterbox_api_name] = now_monotonic
                    self._force_refresh_litterbox_activity_api_names.discard(litterbox_api_name)
                else:
                    details[litterbox_api_name] = previous.get(litterbox_api_name, PetSafeExtendedLitterboxDetails())
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                LOGGER.debug("Failed to refresh litterbox details for %s: %s", litterbox_api_name, err)
                details[litterbox_api_name] = previous.get(litterbox_api_name, PetSafeExtendedLitterboxDetails())
            except Exception as err:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
                LOGGER.debug("Failed to refresh litterbox details for %s: %s", litterbox_api_name, err)
                details[litterbox_api_name] = previous.get(litterbox_api_name, PetSafeExtendedLitterboxDetails())

        self._cleanup_timestamp_map(self._litterbox_activity_last_refresh_by_litterbox, active_litterbox_ids)
        self._cleanup_force_refresh_keys(self._force_refresh_litterbox_activity_api_names, active_litterbox_ids)
        return details

    @staticmethod
    def _parse_feeding_timestamp(feeding: dict[str, Any] | None) -> datetime | None:
        """Parse a feeder timestamp payload into UTC."""
        timestamp = cast(int | None, feeding.get("payload", {}).get("time")) if feeding else None
        if not timestamp:
            return None
        return datetime.fromtimestamp(timestamp, UTC)

    @staticmethod
    def _get_next_feeding_time(schedules: list[dict[str, Any]]) -> datetime | None:
        """Return the next scheduled feeder time in local time."""
        if not schedules:
            return None

        now = dt_util.now()
        today = now.date()
        feeding_times: list[datetime] = []

        for schedule in schedules:
            schedule_time = schedule.get("time")
            if not isinstance(schedule_time, str):
                continue
            try:
                parsed_time = datetime.strptime(schedule_time, "%H:%M").time()
            except ValueError:
                continue
            feeding_times.append(dt_util.as_local(datetime.combine(today, parsed_time)))

        if not feeding_times:
            return None

        sorted_times = sorted(feeding_times)
        for feeding_time in sorted_times:
            if feeding_time > now:
                return feeding_time

        return dt_util.as_local(sorted_times[0] + timedelta(days=1))

    @staticmethod
    def _parse_litterbox_activity(litterbox: Any, events: dict[str, Any]) -> PetSafeExtendedLitterboxDetails:
        """Derive litterbox detail sensors from activity history."""
        last_cleaning: datetime | None = None
        rake_status: str | None = None
        reported_state = litterbox.data.get("shadow", {}).get("state", {}).get("reported", {})
        rake_delay_seconds = cast(int, reported_state.get("rakeDelayTime", 0)) * 60

        for item in reversed(events.get("data", [])):
            payload = item.get("payload", {})
            code = payload.get("code")
            timestamp_ms = cast(int | None, payload.get("timestamp"))

            if last_cleaning is None and code == RAKE_FINISHED and timestamp_ms is not None:
                last_cleaning = datetime.fromtimestamp(timestamp_ms / 1000, UTC)

            if rake_status is None:
                if code == RAKE_FINISHED:
                    rake_status = "idle"
                elif code == CAT_IN_BOX and timestamp_ms is not None:
                    rake_status = "timing"
                    if (timestamp_ms / 1000) + rake_delay_seconds <= time.time():
                        rake_status = "raking"
                elif code in {RAKE_BUTTON_DETECTED, RAKE_NOW}:
                    rake_status = "raking"
                elif code == ERROR_SENSOR_BLOCKED:
                    rake_status = "jammed"

            if last_cleaning is not None and rake_status is not None:
                break

        return PetSafeExtendedLitterboxDetails(
            last_cleaning=last_cleaning,
            rake_status=rake_status,
        )
