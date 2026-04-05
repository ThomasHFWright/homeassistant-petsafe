"""Per-pet SmartDoor schedule calendar entities."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any

from custom_components.petsafe_extended.coordinator.smartdoor_schedules import (
    PetSafeExtendedSmartDoorPetScheduleInterval,
    describe_smartdoor_schedule_interval,
    expand_smartdoor_pet_schedule_intervals,
    format_smartdoor_schedule_interval_summary,
    get_current_smartdoor_pet_schedule_interval,
    get_next_smartdoor_pet_schedule_interval,
)
from custom_components.petsafe_extended.entity.smartdoor_pet import PetSafeExtendedSmartDoorPetEntity
from homeassistant.components.calendar import CalendarEntity, CalendarEntityDescription, CalendarEvent
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

SMARTDOOR_SCHEDULE_CALENDAR_DESCRIPTION = CalendarEntityDescription(
    key="schedule",
    name="Schedule",
    translation_key="schedule",
    entity_category=EntityCategory.DIAGNOSTIC,
)


class PetSafeExtendedSmartDoorScheduleCalendar(CalendarEntity, PetSafeExtendedSmartDoorPetEntity):
    """Representation of a SmartDoor pet schedule as a Home Assistant calendar."""

    def __init__(
        self,
        coordinator: Any,
        door: Any,
        pet_id: str,
    ) -> None:
        """Initialize the SmartDoor pet schedule calendar."""
        super().__init__(
            coordinator,
            door,
            pet_id,
            SMARTDOOR_SCHEDULE_CALENDAR_DESCRIPTION,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming schedule interval for the pet."""
        rules = self.coordinator.get_smartdoor_schedule_rules(self._api_name)
        if rules is None:
            return None

        timezone = self._default_timezone()
        now = dt_util.now().astimezone(timezone)
        interval = get_current_smartdoor_pet_schedule_interval(
            rules,
            now=now,
            default_timezone=timezone,
            pet_id=self._pet_id,
        )
        if interval is None:
            interval = get_next_smartdoor_pet_schedule_interval(
                rules,
                now=now,
                default_timezone=timezone,
                pet_id=self._pet_id,
                include_current=False,
            )
        if interval is None:
            return None

        return _as_calendar_event(
            interval,
            fallback_end=max(now + timedelta(days=7), interval.start + timedelta(days=1)),
        )

    async def async_get_events(
        self,
        hass: Any,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return the pet schedule intervals within a datetime range."""
        del hass
        rules = self.coordinator.get_smartdoor_schedule_rules(self._api_name)
        if rules is None:
            return []

        timezone = self._default_timezone()
        start = _coerce_datetime(start_date, timezone)
        end = _coerce_datetime(end_date, timezone, end_of_day=True)
        intervals = expand_smartdoor_pet_schedule_intervals(
            rules,
            start=start,
            end=end,
            default_timezone=timezone,
            pet_id=self._pet_id,
        )
        return [_as_calendar_event(interval, fallback_end=end) for interval in intervals]

    def _default_timezone(self) -> tzinfo:
        """Return the Home Assistant timezone used for calendar projection."""
        if self.hass is not None and (timezone := dt_util.get_time_zone(self.hass.config.time_zone)) is not None:
            return timezone
        return dt_util.DEFAULT_TIME_ZONE or UTC

    def _pet_ids_for_availability(self) -> tuple[str, ...]:
        """Return the scheduled pet identifiers that should keep this calendar available."""
        return self.coordinator.get_smartdoor_scheduled_pet_ids(self._api_name)


def _as_calendar_event(
    interval: PetSafeExtendedSmartDoorPetScheduleInterval,
    *,
    fallback_end: datetime,
) -> CalendarEvent:
    """Convert a per-pet schedule interval into a Home Assistant calendar event."""
    end = interval.end if interval.end is not None else fallback_end
    return CalendarEvent(
        summary=format_smartdoor_schedule_interval_summary(interval),
        start=interval.start,
        end=end,
        description=describe_smartdoor_schedule_interval(interval),
    )


def _coerce_datetime(value: datetime | date, timezone: tzinfo, *, end_of_day: bool = False) -> datetime:
    """Return a timezone-aware datetime from a calendar query boundary."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone)
        return value.replace(tzinfo=timezone)

    boundary_time = time.max if end_of_day else time.min
    return datetime.combine(value, boundary_time, timezone)
