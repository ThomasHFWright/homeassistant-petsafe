"""SmartDoor state normalization helpers."""

from __future__ import annotations

from custom_components.petsafe_extended.const import (
    SMARTDOOR_FINAL_ACT_LOCKED,
    SMARTDOOR_FINAL_ACT_UNLOCKED,
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


def smartdoor_final_acts_match(actual: str | None, expected: str | None) -> bool:
    """Return whether two SmartDoor final-act values represent the same state."""
    return normalize_smartdoor_value(actual) == normalize_smartdoor_value(expected)


def get_smartdoor_locked_state(mode: str | None, latch_state: str | None) -> bool | None:
    """Return the Home Assistant lock state for a SmartDoor."""
    normalized_mode = normalize_smartdoor_value(mode)
    if normalized_mode in {
        normalize_smartdoor_value(SMARTDOOR_MODE_MANUAL_LOCKED),
        normalize_smartdoor_value(SMARTDOOR_MODE_SMART),
    }:
        return True
    if normalized_mode == normalize_smartdoor_value(SMARTDOOR_MODE_MANUAL_UNLOCKED):
        return False

    normalized_latch_state = normalize_smartdoor_value(latch_state)
    if normalized_latch_state in _LOCKED_LATCH_STATES:
        return True
    if normalized_latch_state in _UNLOCKED_LATCH_STATES:
        return False

    return None


def get_smartdoor_locked_mode_option(mode: str | None) -> str | None:
    """Return the Home Assistant locked-mode option for a SmartDoor mode."""
    normalized_mode = normalize_smartdoor_value(mode)
    if normalized_mode == normalize_smartdoor_value(SMARTDOOR_MODE_MANUAL_LOCKED):
        return "locked"
    if normalized_mode == normalize_smartdoor_value(SMARTDOOR_MODE_SMART):
        return "smart"
    return None


def get_smartdoor_final_act_value(door: object) -> str | None:
    """Return the raw SmartDoor final-act token from the cached device payload."""
    data = getattr(door, "data", None)
    if not isinstance(data, dict):
        return None

    reported_state = data.get("shadow", {}).get("state", {}).get("reported", {})
    if not isinstance(reported_state, dict):
        return None

    power_state = reported_state.get("power", {})
    if not isinstance(power_state, dict):
        return None

    final_act = power_state.get("finalAct")
    return final_act if isinstance(final_act, str) else None


def get_smartdoor_final_act_option(door: object) -> str | None:
    """Return the Home Assistant final-act option for a SmartDoor device."""
    normalized_final_act = normalize_smartdoor_value(get_smartdoor_final_act_value(door))
    if normalized_final_act == normalize_smartdoor_value(SMARTDOOR_FINAL_ACT_LOCKED):
        return "locked"
    if normalized_final_act == normalize_smartdoor_value(SMARTDOOR_FINAL_ACT_UNLOCKED):
        return "unlocked"
    return None
