"""SmartDoor state normalization helpers."""

from __future__ import annotations

from custom_components.petsafe_extended.const import (
    SMARTDOOR_MODE_MANUAL_LOCKED,
    SMARTDOOR_MODE_MANUAL_UNLOCKED,
    SMARTDOOR_MODE_SMART,
)

_LOCKED_LATCH_STATES = {"LOCKED"}
_UNLOCKED_LATCH_STATES = {"UNLOCKED"}


def normalize_smartdoor_value(value: str | None) -> str | None:
    """Return a normalized SmartDoor state token."""
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    return normalized.replace(" ", "_").upper()


def smartdoor_modes_match(actual: str | None, expected: str | None) -> bool:
    """Return whether two SmartDoor mode values represent the same mode."""
    return normalize_smartdoor_value(actual) == normalize_smartdoor_value(expected)


def get_smartdoor_locked_state(mode: str | None, latch_state: str | None) -> bool | None:
    """Return the Home Assistant lock state for a SmartDoor."""
    normalized_mode = normalize_smartdoor_value(mode)
    if normalized_mode == normalize_smartdoor_value(SMARTDOOR_MODE_MANUAL_LOCKED):
        return True
    if normalized_mode in {
        normalize_smartdoor_value(SMARTDOOR_MODE_MANUAL_UNLOCKED),
        normalize_smartdoor_value(SMARTDOOR_MODE_SMART),
    }:
        return False

    normalized_latch_state = normalize_smartdoor_value(latch_state)
    if normalized_latch_state in _LOCKED_LATCH_STATES:
        return True
    if normalized_latch_state in _UNLOCKED_LATCH_STATES:
        return False

    return None
