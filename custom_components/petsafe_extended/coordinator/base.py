"""Coordinator implementation for petsafe_extended."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import time
from typing import TYPE_CHECKING, Any, cast

import httpx

from custom_components.petsafe_extended.const import (
    CAT_IN_BOX,
    DOMAIN,
    ERROR_SENSOR_BLOCKED,
    LOGGER,
    RAKE_BUTTON_DETECTED,
    RAKE_FINISHED,
    RAKE_NOW,
    SMARTDOOR_MODE_MANUAL_LOCKED,
    SMARTDOOR_MODE_MANUAL_UNLOCKED,
)
from custom_components.petsafe_extended.data import (
    PetSafeExtendedConfigEntry,
    PetSafeExtendedCoordinatorData,
    PetSafeExtendedFeederDetails,
    PetSafeExtendedLitterboxDetails,
)
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
            update_interval=timedelta(seconds=30),
        )
        self.api = api
        self.config_entry = entry
        self._feeders: list[Any] | None = None
        self._litterboxes: list[Any] | None = None
        self._smartdoors: list[Any] | None = None
        self._feeder_details: dict[str, PetSafeExtendedFeederDetails] = {}
        self._litterbox_details: dict[str, PetSafeExtendedLitterboxDetails] = {}
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
        return PetSafeExtendedCoordinatorData(
            feeders=list(self._feeders if self._feeders is not None else current.feeders),
            litterboxes=list(self._litterboxes if self._litterboxes is not None else current.litterboxes),
            smartdoors=list(self._smartdoors if self._smartdoors is not None else current.smartdoors),
            feeder_details=dict(self._feeder_details or current.feeder_details),
            litterbox_details=dict(self._litterbox_details or current.litterbox_details),
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
        if refresh:
            await self.async_request_refresh()

    async def async_set_smartdoor_lock(self, api_name: str, locked: bool) -> Any:
        """Lock or unlock a smart door and return the refreshed device."""
        await self.get_smartdoors()
        async with self._device_lock:
            door = self._find_cached_smartdoor(api_name)
            if door is None:
                raise ValueError(f"Unknown SmartDoor API name: {api_name}")
            try:
                if locked:
                    await door.lock(update_data=False)
                    expected_mode = SMARTDOOR_MODE_MANUAL_LOCKED
                else:
                    await door.unlock(update_data=False)
                    expected_mode = SMARTDOOR_MODE_MANUAL_UNLOCKED
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                raise
        return await self.async_refresh_smartdoor(api_name, expected_mode=expected_mode)

    async def async_refresh_smartdoor(
        self,
        api_name: str,
        *,
        expected_mode: str | None = None,
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
                self.async_set_updated_data(self._cached_snapshot())

                if expected_mode is None or door.mode == expected_mode:
                    return door

            if attempt < attempts - 1:
                await asyncio.sleep(refresh_interval)

        if refreshed_door is None:
            raise ValueError(f"Unknown SmartDoor API name: {api_name}")
        LOGGER.debug(
            "SmartDoor %s did not report expected mode %s after %s refresh attempts",
            api_name,
            expected_mode,
            attempts,
        )
        return refreshed_door

    async def _async_update_data(self) -> PetSafeExtendedCoordinatorData:
        """Fetch data from the PetSafe API."""
        try:
            async with self._device_lock:
                feeders = await self.api.get_feeders()
                litterboxes = await self.api.get_litterboxes()
                smartdoors = await self.api.get_smartdoors()
                feeder_details = await self._async_build_feeder_details(feeders)
                litterbox_details = await self._async_build_litterbox_details(litterboxes)
                self._feeders = feeders
                self._litterboxes = litterboxes
                self._smartdoors = smartdoors
                self._feeder_details = feeder_details
                self._litterbox_details = litterbox_details
                return PetSafeExtendedCoordinatorData(
                    feeders=list(feeders),
                    litterboxes=list(litterboxes),
                    smartdoors=list(smartdoors),
                    feeder_details=dict(feeder_details),
                    litterbox_details=dict(litterbox_details),
                )
        except httpx.HTTPStatusError as err:
            if self._is_auth_error(err):
                self._raise_auth_failed(err)
            raise UpdateFailed("Failed to refresh PetSafe devices") from err
        except Exception as err:
            raise UpdateFailed("Failed to refresh PetSafe devices") from err

    async def _async_build_feeder_details(self, feeders: list[Any]) -> dict[str, PetSafeExtendedFeederDetails]:
        """Build supplemental feeder state."""
        previous = self.data.feeder_details if self.data else {}
        details: dict[str, PetSafeExtendedFeederDetails] = {}

        for feeder in feeders:
            try:
                feeding = await feeder.get_last_feeding()
                schedules = await feeder.get_schedules()
                details[feeder.api_name] = PetSafeExtendedFeederDetails(
                    last_feeding=self._parse_feeding_timestamp(feeding),
                    next_feeding=self._get_next_feeding_time(schedules),
                )
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                LOGGER.debug("Failed to refresh feeder details for %s: %s", feeder.api_name, err)
                details[feeder.api_name] = previous.get(feeder.api_name, PetSafeExtendedFeederDetails())
            except Exception as err:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
                LOGGER.debug("Failed to refresh feeder details for %s: %s", feeder.api_name, err)
                details[feeder.api_name] = previous.get(feeder.api_name, PetSafeExtendedFeederDetails())

        return details

    async def _async_build_litterbox_details(
        self,
        litterboxes: list[Any],
    ) -> dict[str, PetSafeExtendedLitterboxDetails]:
        """Build supplemental litterbox state."""
        previous = self.data.litterbox_details if self.data else {}
        details: dict[str, PetSafeExtendedLitterboxDetails] = {}

        for litterbox in litterboxes:
            try:
                events = await litterbox.get_activity()
                details[litterbox.api_name] = self._parse_litterbox_activity(litterbox, events)
            except httpx.HTTPStatusError as err:
                if self._is_auth_error(err):
                    self._raise_auth_failed(err)
                LOGGER.debug("Failed to refresh litterbox details for %s: %s", litterbox.api_name, err)
                details[litterbox.api_name] = previous.get(litterbox.api_name, PetSafeExtendedLitterboxDetails())
            except Exception as err:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
                LOGGER.debug("Failed to refresh litterbox details for %s: %s", litterbox.api_name, err)
                details[litterbox.api_name] = previous.get(litterbox.api_name, PetSafeExtendedLitterboxDetails())

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
