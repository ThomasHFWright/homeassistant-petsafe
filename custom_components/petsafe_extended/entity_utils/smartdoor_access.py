"""Shared SmartDoor access and override helpers."""

from __future__ import annotations

from typing import Any

SMARTDOOR_ACCESS_UNKNOWN = "unknown"
SMARTDOOR_ACCESS_SMART_SCHEDULE = "smart_schedule"
SMARTDOOR_ACCESS_NO_ACCESS = "no_access"
SMARTDOOR_ACCESS_OUT_ONLY = "out_only"
SMARTDOOR_ACCESS_IN_ONLY = "in_only"
SMARTDOOR_ACCESS_FULL_ACCESS = "full_access"

SMARTDOOR_SCHEDULE_ACCESS_OPTIONS = [
    SMARTDOOR_ACCESS_UNKNOWN,
    SMARTDOOR_ACCESS_NO_ACCESS,
    SMARTDOOR_ACCESS_OUT_ONLY,
    SMARTDOOR_ACCESS_IN_ONLY,
    SMARTDOOR_ACCESS_FULL_ACCESS,
]
SMARTDOOR_OVERRIDE_OPTIONS = [
    SMARTDOOR_ACCESS_SMART_SCHEDULE,
    SMARTDOOR_ACCESS_NO_ACCESS,
    SMARTDOOR_ACCESS_OUT_ONLY,
    SMARTDOOR_ACCESS_IN_ONLY,
    SMARTDOOR_ACCESS_FULL_ACCESS,
]

SMARTDOOR_CONTROL_SOURCE_SMART = "smart"
SMARTDOOR_CONTROL_SOURCE_SMART_OVERRIDE = "smart_override"
SMARTDOOR_CONTROL_SOURCE_MANUAL_LOCKED = "manual_locked"
SMARTDOOR_CONTROL_SOURCE_MANUAL_UNLOCKED = "manual_unlocked"

_ACCESS_VALUE_TO_OPTION = {
    0: SMARTDOOR_ACCESS_NO_ACCESS,
    1: SMARTDOOR_ACCESS_OUT_ONLY,
    2: SMARTDOOR_ACCESS_IN_ONLY,
    3: SMARTDOOR_ACCESS_FULL_ACCESS,
}
_OVERRIDE_OPTION_TO_ACCESS_VALUE = {option: value for value, option in _ACCESS_VALUE_TO_OPTION.items()}
_ACCESS_LABELS = {
    SMARTDOOR_ACCESS_UNKNOWN: "Unknown",
    SMARTDOOR_ACCESS_NO_ACCESS: "No access",
    SMARTDOOR_ACCESS_OUT_ONLY: "Out only",
    SMARTDOOR_ACCESS_IN_ONLY: "In only",
    SMARTDOOR_ACCESS_FULL_ACCESS: "Full access",
    SMARTDOOR_ACCESS_SMART_SCHEDULE: "Smart Schedule",
}


def normalize_smartdoor_access_option(value: Any) -> str:
    """Return a normalized SmartDoor schedule access option from a raw API value."""
    try:
        raw_value = int(value)
    except TypeError, ValueError:
        return SMARTDOOR_ACCESS_UNKNOWN
    return _ACCESS_VALUE_TO_OPTION.get(raw_value, SMARTDOOR_ACCESS_UNKNOWN)


def get_smartdoor_access_label(access: str) -> str:
    """Return a user-facing label for a SmartDoor access option."""
    return _ACCESS_LABELS.get(access, _ACCESS_LABELS[SMARTDOOR_ACCESS_UNKNOWN])


def normalize_smartdoor_override_option(value: Any) -> str:
    """Return the current SmartDoor override option from the raw override payload."""
    if value in (None, [], (), {}):
        return SMARTDOOR_ACCESS_SMART_SCHEDULE

    if isinstance(value, list):
        active_item = next((item for item in value if isinstance(item, dict) and item), None)
        return normalize_smartdoor_override_option(active_item)

    if not isinstance(value, dict) or not value:
        return SMARTDOOR_ACCESS_SMART_SCHEDULE

    option = normalize_smartdoor_access_option(value.get("access"))
    if option == SMARTDOOR_ACCESS_UNKNOWN:
        return SMARTDOOR_ACCESS_SMART_SCHEDULE
    return option


def smartdoor_override_is_active(option: str | None) -> bool:
    """Return whether a SmartDoor override option represents an active override."""
    return option in _OVERRIDE_OPTION_TO_ACCESS_VALUE


def smartdoor_override_option_to_access_value(option: str) -> int | None:
    """Return the PetSafe API access value for a SmartDoor override option."""
    return _OVERRIDE_OPTION_TO_ACCESS_VALUE.get(option)
