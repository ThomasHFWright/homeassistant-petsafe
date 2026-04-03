"""SmartDoor schedule normalization and per-pet timeline helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo
from hashlib import sha1
from typing import Any

from custom_components.petsafe_extended.const import SMARTDOOR_MODE_MANUAL_LOCKED, SMARTDOOR_MODE_MANUAL_UNLOCKED
from custom_components.petsafe_extended.data import (
    PetSafeExtendedSmartDoorPetScheduleState,
    PetSafeExtendedSmartDoorScheduleRule,
    PetSafeExtendedSmartDoorScheduleSummary,
)
from custom_components.petsafe_extended.utils.smartdoor import smartdoor_modes_match
from homeassistant.util import dt as dt_util

SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN = "unknown"
SMARTDOOR_SCHEDULE_ACCESS_NO_ACCESS = "no_access"
SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY = "out_only"
SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY = "in_only"
SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS = "full_access"
SMARTDOOR_SCHEDULE_ACCESS_OPTIONS = [
    SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN,
    SMARTDOOR_SCHEDULE_ACCESS_NO_ACCESS,
    SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
    SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
    SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
]

SMARTDOOR_SCHEDULE_CONTROL_SOURCE_SMART = "smart"
SMARTDOOR_SCHEDULE_CONTROL_SOURCE_MANUAL_LOCKED = "manual_locked"
SMARTDOOR_SCHEDULE_CONTROL_SOURCE_MANUAL_UNLOCKED = "manual_unlocked"

_DAY_MASK_LENGTH = 7
_LOOKBACK_DAYS = 8
_LOOKAHEAD_DAYS = 8
_PETSAFE_DAY_INDEX_TO_WEEKDAY = (6, 0, 1, 2, 3, 4, 5)
_ACCESS_VALUE_TO_OPTION = {
    0: SMARTDOOR_SCHEDULE_ACCESS_NO_ACCESS,
    1: SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
    2: SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
    3: SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
}
_ACCESS_LABELS = {
    SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN: "Unknown",
    SMARTDOOR_SCHEDULE_ACCESS_NO_ACCESS: "No access",
    SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY: "Out only",
    SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY: "In only",
    SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS: "Full access",
}


@dataclass(slots=True, frozen=True)
class PetSafeExtendedSmartDoorPetScheduleTransition:
    """A concrete SmartDoor schedule transition affecting a single pet."""

    start: datetime
    access: str
    title: str
    schedule_id: str
    pet_id: str
    pet_name: str
    pet_count: int


@dataclass(slots=True, frozen=True)
class PetSafeExtendedSmartDoorPetScheduleInterval:
    """A concrete SmartDoor schedule interval affecting a single pet."""

    start: datetime
    end: datetime | None
    access: str
    title: str
    schedule_id: str
    pet_id: str
    pet_name: str


def copy_smartdoor_schedule_rules(
    rules_by_door: dict[str, tuple[PetSafeExtendedSmartDoorScheduleRule, ...]] | None,
) -> dict[str, tuple[PetSafeExtendedSmartDoorScheduleRule, ...]]:
    """Return a detached copy of the SmartDoor schedule-rule cache."""
    if not rules_by_door:
        return {}
    return {api_name: tuple(rules) for api_name, rules in rules_by_door.items()}


def copy_smartdoor_schedule_summaries(
    summaries_by_door: dict[str, PetSafeExtendedSmartDoorScheduleSummary] | None,
) -> dict[str, PetSafeExtendedSmartDoorScheduleSummary]:
    """Return a detached copy of the SmartDoor schedule-summary cache."""
    if not summaries_by_door:
        return {}
    return {
        api_name: PetSafeExtendedSmartDoorScheduleSummary(
            schedule_rule_count=summary.schedule_rule_count,
            enabled_schedule_count=summary.enabled_schedule_count,
            disabled_schedule_count=summary.disabled_schedule_count,
            scheduled_pet_count=summary.scheduled_pet_count,
            next_schedule_change_at=summary.next_schedule_change_at,
            next_schedule_title=summary.next_schedule_title,
            next_schedule_access=summary.next_schedule_access,
            next_schedule_pet_name=summary.next_schedule_pet_name,
        )
        for api_name, summary in summaries_by_door.items()
    }


def copy_smartdoor_pet_schedule_states(
    states_by_door: dict[str, dict[str, PetSafeExtendedSmartDoorPetScheduleState]] | None,
) -> dict[str, dict[str, PetSafeExtendedSmartDoorPetScheduleState]]:
    """Return a detached copy of the SmartDoor pet schedule-state cache."""
    if not states_by_door:
        return {}
    return {
        api_name: {
            pet_id: PetSafeExtendedSmartDoorPetScheduleState(
                smart_access=state.smart_access,
                effective_access=state.effective_access,
                control_source=state.control_source,
                active_schedule_title=state.active_schedule_title,
                next_change_at=state.next_change_at,
                next_smart_access=state.next_smart_access,
                next_schedule_title=state.next_schedule_title,
            )
            for pet_id, state in pet_states.items()
        }
        for api_name, pet_states in states_by_door.items()
    }


def parse_smartdoor_schedule_rules(
    schedules: list[dict[str, Any]],
    *,
    timezone: str | None,
    pet_names_by_id: dict[str, str],
) -> tuple[PetSafeExtendedSmartDoorScheduleRule, ...]:
    """Normalize raw SmartDoor schedule payloads into cached rules."""
    rules: list[PetSafeExtendedSmartDoorScheduleRule] = []

    for schedule in schedules:
        pet_ids = schedule.get("petIds")
        raw_pet_ids = (
            tuple(sorted({pet_id for pet_id in pet_ids if isinstance(pet_id, str)}))
            if isinstance(pet_ids, list)
            else ()
        )
        pet_names = tuple(pet_names_by_id.get(pet_id, f"Pet {index + 1}") for index, pet_id in enumerate(raw_pet_ids))
        title = _normalize_optional_string(schedule.get("title"))
        start_time = _normalize_optional_string(schedule.get("startTime"))
        day_of_week = _normalize_day_mask(schedule.get("dayOfWeek"))
        access = normalize_smartdoor_schedule_access(schedule.get("access"))
        schedule_id = _normalize_optional_string(schedule.get("scheduleId")) or _build_schedule_id(
            title, start_time, day_of_week, access, raw_pet_ids
        )
        rules.append(
            PetSafeExtendedSmartDoorScheduleRule(
                schedule_id=schedule_id,
                title=title,
                start_time=start_time,
                day_of_week=day_of_week,
                access=access,
                is_enabled=_normalize_enabled(schedule.get("isEnabled")),
                pet_ids=raw_pet_ids,
                pet_names=pet_names,
                pet_count=len(raw_pet_ids),
                timezone=_normalize_optional_string(timezone),
                next_action_at=_parse_millis_timestamp(schedule.get("nextActionAt")),
                prev_action_at=_parse_millis_timestamp(schedule.get("prevActionAt")),
            )
        )

    return tuple(
        sorted(
            rules,
            key=lambda rule: (
                rule.next_action_at or datetime.max.replace(tzinfo=UTC),
                rule.start_time or "",
                rule.title or "",
                rule.schedule_id,
            ),
        )
    )


def get_smartdoor_scheduled_pet_ids(
    rules: tuple[PetSafeExtendedSmartDoorScheduleRule, ...],
) -> tuple[str, ...]:
    """Return pets referenced by at least one enabled SmartDoor schedule."""
    ordered_pet_ids: list[str] = []
    seen_pet_ids: set[str] = set()
    for rule in rules:
        if not rule.is_enabled:
            continue
        for pet_id in rule.pet_ids:
            if pet_id in seen_pet_ids:
                continue
            seen_pet_ids.add(pet_id)
            ordered_pet_ids.append(pet_id)
    return tuple(ordered_pet_ids)


def build_smartdoor_schedule_summary(
    rules: tuple[PetSafeExtendedSmartDoorScheduleRule, ...],
    linked_pet_ids: tuple[str, ...],
    *,
    now: datetime,
    default_timezone: tzinfo,
) -> PetSafeExtendedSmartDoorScheduleSummary:
    """Build a summarized schedule view for SmartDoor schedule entities."""
    enabled_count = sum(1 for rule in rules if rule.is_enabled)
    summary = PetSafeExtendedSmartDoorScheduleSummary(
        schedule_rule_count=len(rules),
        enabled_schedule_count=enabled_count,
        disabled_schedule_count=len(rules) - enabled_count,
    )

    scheduled_pet_ids = _order_pet_ids(
        linked_pet_ids,
        get_smartdoor_scheduled_pet_ids(rules),
    )
    summary.scheduled_pet_count = len(scheduled_pet_ids)
    if not scheduled_pet_ids:
        return summary

    next_interval: PetSafeExtendedSmartDoorPetScheduleInterval | None = None
    for pet_id in scheduled_pet_ids:
        candidate = get_next_smartdoor_pet_schedule_interval(
            rules,
            now=now,
            default_timezone=default_timezone,
            pet_id=pet_id,
            include_current=False,
        )
        if candidate is None:
            continue
        if next_interval is None or candidate.start < next_interval.start:
            next_interval = candidate

    if next_interval is None:
        return summary

    summary.next_schedule_change_at = next_interval.start
    summary.next_schedule_title = next_interval.title
    summary.next_schedule_access = next_interval.access
    summary.next_schedule_pet_name = next_interval.pet_name
    return summary


def build_smartdoor_pet_schedule_states(
    rules: tuple[PetSafeExtendedSmartDoorScheduleRule, ...],
    linked_pet_ids: tuple[str, ...],
    *,
    door_mode: str | None,
    now: datetime,
    default_timezone: tzinfo,
) -> dict[str, PetSafeExtendedSmartDoorPetScheduleState]:
    """Build the current schedule-derived access state for each linked pet."""
    states: dict[str, PetSafeExtendedSmartDoorPetScheduleState] = {}

    for pet_id in linked_pet_ids:
        current_interval = get_current_smartdoor_pet_schedule_interval(
            rules,
            now=now,
            default_timezone=default_timezone,
            pet_id=pet_id,
        )
        smart_access = current_interval.access if current_interval is not None else SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN
        effective_access, control_source = _resolve_effective_pet_access(door_mode, smart_access)
        next_interval = get_next_smartdoor_pet_schedule_interval(
            rules,
            now=now,
            default_timezone=default_timezone,
            pet_id=pet_id,
            include_current=False,
        )
        states[pet_id] = PetSafeExtendedSmartDoorPetScheduleState(
            smart_access=smart_access,
            effective_access=effective_access,
            control_source=control_source,
            active_schedule_title=current_interval.title if current_interval is not None else None,
            next_change_at=next_interval.start if next_interval is not None else None,
            next_smart_access=next_interval.access if next_interval is not None else None,
            next_schedule_title=next_interval.title if next_interval is not None else None,
        )

    return states


def get_current_smartdoor_pet_schedule_interval(
    rules: tuple[PetSafeExtendedSmartDoorScheduleRule, ...],
    *,
    now: datetime,
    default_timezone: tzinfo,
    pet_id: str,
) -> PetSafeExtendedSmartDoorPetScheduleInterval | None:
    """Return the current effective schedule interval for a pet."""
    intervals = _build_pet_schedule_intervals(
        rules,
        pet_id=pet_id,
        start=now,
        end=now,
        default_timezone=default_timezone,
    )
    return next(
        (interval for interval in intervals if interval.start <= now and (interval.end is None or now < interval.end)),
        None,
    )


def get_next_smartdoor_pet_schedule_interval(
    rules: tuple[PetSafeExtendedSmartDoorScheduleRule, ...],
    *,
    now: datetime,
    default_timezone: tzinfo,
    pet_id: str,
    include_current: bool,
) -> PetSafeExtendedSmartDoorPetScheduleInterval | None:
    """Return the current or next future schedule interval for a pet."""
    intervals = _build_pet_schedule_intervals(
        rules,
        pet_id=pet_id,
        start=now,
        end=now,
        default_timezone=default_timezone,
    )
    for interval in intervals:
        if interval.start <= now and (interval.end is None or now < interval.end):
            if include_current:
                return interval
            continue
        if interval.start > now:
            return interval
    return None


def expand_smartdoor_pet_schedule_intervals(
    rules: tuple[PetSafeExtendedSmartDoorScheduleRule, ...],
    *,
    start: datetime,
    end: datetime,
    default_timezone: tzinfo,
    pet_id: str,
) -> tuple[PetSafeExtendedSmartDoorPetScheduleInterval, ...]:
    """Expand a pet's schedule into calendar-ready intervals in the requested range."""
    range_start = _coerce_datetime(start, default_timezone)
    range_end = _coerce_datetime(end, default_timezone)
    intervals = _build_pet_schedule_intervals(
        rules,
        pet_id=pet_id,
        start=range_start,
        end=range_end,
        default_timezone=default_timezone,
    )

    projected: list[PetSafeExtendedSmartDoorPetScheduleInterval] = []
    for interval in intervals:
        interval_end = interval.end or range_end
        if interval.start >= range_end or interval_end <= range_start:
            continue

        projected_start = max(interval.start, range_start)
        projected_end = min(interval_end, range_end)
        if projected_end <= projected_start:
            continue

        projected.append(
            PetSafeExtendedSmartDoorPetScheduleInterval(
                start=projected_start,
                end=projected_end,
                access=interval.access,
                title=interval.title,
                schedule_id=interval.schedule_id,
                pet_id=interval.pet_id,
                pet_name=interval.pet_name,
            )
        )

    return tuple(projected)


def format_smartdoor_schedule_interval_summary(interval: PetSafeExtendedSmartDoorPetScheduleInterval) -> str:
    """Return a user-facing calendar event summary for a schedule interval."""
    access_label = get_smartdoor_schedule_access_label(interval.access)
    title = interval.title or "Scheduled access"
    return f"{access_label} · {title}"


def describe_smartdoor_schedule_interval(interval: PetSafeExtendedSmartDoorPetScheduleInterval) -> str | None:
    """Return a user-facing description for a schedule interval."""
    lines = [f"Access: {get_smartdoor_schedule_access_label(interval.access)}"]
    if interval.title:
        lines.append(f"Source: {interval.title}")
    return "\n".join(lines) if lines else None


def normalize_smartdoor_schedule_access(value: Any) -> str:
    """Return a normalized SmartDoor access option from a raw API value."""
    try:
        raw_value = int(value)
    except TypeError, ValueError:
        return SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN
    return _ACCESS_VALUE_TO_OPTION.get(raw_value, SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN)


def get_smartdoor_schedule_access_label(access: str) -> str:
    """Return a user-facing label for a SmartDoor access option."""
    return _ACCESS_LABELS.get(access, _ACCESS_LABELS[SMARTDOOR_SCHEDULE_ACCESS_UNKNOWN])


def _build_pet_schedule_intervals(
    rules: tuple[PetSafeExtendedSmartDoorScheduleRule, ...],
    *,
    pet_id: str,
    start: datetime,
    end: datetime,
    default_timezone: tzinfo,
) -> tuple[PetSafeExtendedSmartDoorPetScheduleInterval, ...]:
    """Build effective schedule intervals for a pet around a requested range."""
    pet_rules = tuple(rule for rule in rules if rule.is_enabled and pet_id in rule.pet_ids)
    if not pet_rules:
        return ()

    applicable_timezone = _resolve_timezone(
        next((rule.timezone for rule in pet_rules if rule.timezone), None),
        default_timezone,
    )
    window_start = _coerce_datetime(start, applicable_timezone) - timedelta(days=_LOOKBACK_DAYS)
    window_end = _coerce_datetime(end, applicable_timezone) + timedelta(days=_LOOKAHEAD_DAYS)
    transitions = _build_pet_schedule_transitions(
        pet_rules,
        pet_id=pet_id,
        start=window_start,
        end=window_end,
        timezone=applicable_timezone,
    )
    if not transitions:
        return ()

    intervals: list[PetSafeExtendedSmartDoorPetScheduleInterval] = []
    for index, transition in enumerate(transitions):
        next_start = transitions[index + 1].start if index + 1 < len(transitions) else None
        candidate = PetSafeExtendedSmartDoorPetScheduleInterval(
            start=transition.start,
            end=next_start,
            access=transition.access,
            title=transition.title,
            schedule_id=transition.schedule_id,
            pet_id=transition.pet_id,
            pet_name=transition.pet_name,
        )
        if intervals and intervals[-1].access == candidate.access and intervals[-1].title == candidate.title:
            previous = intervals[-1]
            intervals[-1] = PetSafeExtendedSmartDoorPetScheduleInterval(
                start=previous.start,
                end=candidate.end,
                access=previous.access,
                title=previous.title,
                schedule_id=previous.schedule_id,
                pet_id=previous.pet_id,
                pet_name=previous.pet_name,
            )
            continue
        intervals.append(candidate)

    return tuple(intervals)


def _build_pet_schedule_transitions(
    rules: tuple[PetSafeExtendedSmartDoorScheduleRule, ...],
    *,
    pet_id: str,
    start: datetime,
    end: datetime,
    timezone: tzinfo,
) -> tuple[PetSafeExtendedSmartDoorPetScheduleTransition, ...]:
    """Build concrete effective transitions for a pet across a time window."""
    candidates_by_start: dict[datetime, list[PetSafeExtendedSmartDoorPetScheduleTransition]] = {}

    for rule in rules:
        parsed_time = _parse_schedule_time(rule.start_time)
        weekdays = _parse_day_mask(rule.day_of_week)
        if parsed_time is None or not weekdays:
            continue

        pet_name = _get_pet_name_from_rule(rule, pet_id)
        for occurrence in _generate_occurrence_starts(
            start=start,
            end=end,
            weekdays=weekdays,
            schedule_time=parsed_time,
            timezone=timezone,
        ):
            candidates_by_start.setdefault(occurrence, []).append(
                PetSafeExtendedSmartDoorPetScheduleTransition(
                    start=occurrence,
                    access=rule.access,
                    title=rule.title or "Scheduled access",
                    schedule_id=rule.schedule_id,
                    pet_id=pet_id,
                    pet_name=pet_name,
                    pet_count=rule.pet_count,
                )
            )

    transitions: list[PetSafeExtendedSmartDoorPetScheduleTransition] = []
    for occurrence in sorted(candidates_by_start):
        winner = min(candidates_by_start[occurrence], key=_transition_precedence_key)
        transitions.append(winner)

    return tuple(transitions)


def _generate_occurrence_starts(
    *,
    start: datetime,
    end: datetime,
    weekdays: tuple[int, ...],
    schedule_time: time,
    timezone: tzinfo,
) -> tuple[datetime, ...]:
    """Generate concrete recurring start times for a schedule rule."""
    occurrences: list[datetime] = []
    current_date = start.date()
    end_date = end.date()

    while current_date <= end_date:
        if current_date.weekday() in weekdays:
            occurrence = datetime.combine(current_date, schedule_time, timezone)
            if start <= occurrence <= end:
                occurrences.append(occurrence)
        current_date += timedelta(days=1)

    return tuple(occurrences)


def _transition_precedence_key(
    transition: PetSafeExtendedSmartDoorPetScheduleTransition,
) -> tuple[int, str, str]:
    """Return a stable precedence key for simultaneous pet schedule transitions."""
    return (transition.pet_count, transition.schedule_id, transition.title)


def _get_pet_name_from_rule(rule: PetSafeExtendedSmartDoorScheduleRule, pet_id: str) -> str:
    """Return the safe pet display name associated with a rule."""
    try:
        pet_index = rule.pet_ids.index(pet_id)
    except ValueError:
        return "Pet"
    if pet_index < len(rule.pet_names):
        return rule.pet_names[pet_index]
    return f"Pet {pet_index + 1}"


def _order_pet_ids(linked_pet_ids: tuple[str, ...], scheduled_pet_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Return scheduled pet identifiers ordered to match the linked-pet display order."""
    scheduled_set = set(scheduled_pet_ids)
    ordered = tuple(pet_id for pet_id in linked_pet_ids if pet_id in scheduled_set)
    extras = tuple(pet_id for pet_id in scheduled_pet_ids if pet_id not in set(ordered))
    return ordered + extras


def _build_schedule_id(
    title: str | None,
    start_time: str | None,
    day_of_week: str | None,
    access: str,
    pet_ids: tuple[str, ...],
) -> str:
    """Return a deterministic schedule identifier when the API omits one."""
    seed = "|".join(
        [
            title or "",
            start_time or "",
            day_of_week or "",
            access,
            ",".join(pet_ids),
        ]
    )
    return sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _resolve_effective_pet_access(door_mode: str | None, smart_access: str) -> tuple[str, str]:
    """Return the current effective access after applying the live door mode."""
    if smartdoor_modes_match(door_mode, SMARTDOOR_MODE_MANUAL_UNLOCKED):
        return SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS, SMARTDOOR_SCHEDULE_CONTROL_SOURCE_MANUAL_UNLOCKED
    if smartdoor_modes_match(door_mode, SMARTDOOR_MODE_MANUAL_LOCKED):
        return SMARTDOOR_SCHEDULE_ACCESS_NO_ACCESS, SMARTDOOR_SCHEDULE_CONTROL_SOURCE_MANUAL_LOCKED
    return smart_access, SMARTDOOR_SCHEDULE_CONTROL_SOURCE_SMART


def _normalize_optional_string(value: Any) -> str | None:
    """Normalize an optional string field from a schedule payload."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_day_mask(value: Any) -> str | None:
    """Normalize the PetSafe weekly day mask string."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if len(normalized) != _DAY_MASK_LENGTH or any(character not in {"0", "1"} for character in normalized):
        return None
    return normalized


def _normalize_enabled(value: Any) -> bool:
    """Normalize the PetSafe enabled flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _parse_millis_timestamp(value: Any) -> datetime | None:
    """Convert a millisecond epoch timestamp into a timezone-aware datetime."""
    if value in (None, ""):
        return None
    try:
        timestamp = int(value) / 1000
    except TypeError, ValueError:
        return None
    return datetime.fromtimestamp(timestamp, UTC)


def _parse_schedule_time(value: str | None) -> time | None:
    """Parse a SmartDoor schedule HH:MM time string."""
    if value is None:
        return None
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except TypeError, ValueError:
        return None


def _parse_day_mask(value: str | None) -> tuple[int, ...]:
    """Convert a PetSafe weekly day mask into Python weekday indexes."""
    if value is None:
        return ()
    return tuple(_PETSAFE_DAY_INDEX_TO_WEEKDAY[index] for index, character in enumerate(value) if character == "1")


def _resolve_timezone(value: str | None, default_timezone: tzinfo) -> tzinfo:
    """Return a timezone for schedule projection."""
    if value is not None and (timezone := dt_util.get_time_zone(value)) is not None:
        return timezone
    return default_timezone


def _coerce_datetime(value: datetime, timezone: tzinfo) -> datetime:
    """Return a timezone-aware datetime from a calendar boundary."""
    if value.tzinfo is not None:
        return value.astimezone(timezone)
    return value.replace(tzinfo=timezone)
