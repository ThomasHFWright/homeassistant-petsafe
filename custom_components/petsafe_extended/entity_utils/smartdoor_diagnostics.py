"""SmartDoor diagnostic value normalization helpers."""

from __future__ import annotations

from typing import Any

_SMARTDOOR_CLEAR_ERROR_STATES = {
    "",
    "clear",
    "no error",
    "no_error",
    "none",
    "normal",
    "ok",
}
_SMARTDOOR_FALSE_STRINGS = {"0", "false", "no", "off"}
_SMARTDOOR_TRUE_STRINGS = {"1", "true", "yes", "on"}
_SMARTDOOR_OFFLINE_STATES = {
    "disconnected",
    "offline",
    "unavailable",
}


def normalize_smartdoor_battery_voltage(value: Any) -> float | None:
    """Return a SmartDoor battery voltage in volts."""
    if value is None or isinstance(value, bool):
        return None

    try:
        voltage = float(value)
    except TypeError, ValueError:
        return None

    # The live API reports SmartDoor battery voltage in millivolts.
    if abs(voltage) > 100:
        voltage /= 1000

    return round(voltage, 3)


def normalize_smartdoor_signal_strength(value: Any) -> int | None:
    """Return a SmartDoor RSSI value as an integer."""
    if value is None or isinstance(value, bool):
        return None

    try:
        return int(value)
    except TypeError, ValueError:
        return None


def normalize_smartdoor_has_adapter(value: Any) -> bool | None:
    """Return whether a SmartDoor is currently on AC power."""
    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in (0, 1):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _SMARTDOOR_TRUE_STRINGS:
            return True
        if normalized in _SMARTDOOR_FALSE_STRINGS:
            return False

    return None


def normalize_smartdoor_error_state(value: Any) -> str | None:
    """Return a normalized SmartDoor error-state string."""
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return str(value)


def normalize_smartdoor_connection_status(value: Any) -> str | None:
    """Return a normalized SmartDoor connection-status string."""
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return str(value)


def smartdoor_is_connected(value: Any) -> bool | None:
    """Return whether a SmartDoor connection-status value indicates connectivity."""
    normalized = normalize_smartdoor_connection_status(value)
    if normalized is None:
        return None
    return normalized.strip().lower() not in _SMARTDOOR_OFFLINE_STATES


def smartdoor_has_problem(value: Any) -> bool:
    """Return whether a SmartDoor error-state value represents a problem."""
    normalized = normalize_smartdoor_error_state(value)
    if normalized is None:
        return False
    return normalized.strip().lower() not in _SMARTDOOR_CLEAR_ERROR_STATES
