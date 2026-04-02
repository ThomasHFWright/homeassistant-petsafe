"""SmartDoor activity helpers for pet-facing entities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from custom_components.petsafe_extended.data import (
    PetSafeExtendedSmartDoorActivityRecord,
    PetSafeExtendedSmartDoorPetState,
)
from homeassistant.util import dt as dt_util

SMARTDOOR_ACTIVITY_INITIAL_LIMIT = 200
SMARTDOOR_ACTIVITY_HISTORY_LIMIT = 100

SMARTDOOR_PET_ACTIVITY_UNKNOWN = "unknown"
SMARTDOOR_PET_ACTIVITY_ENTERED = "entered"
SMARTDOOR_PET_ACTIVITY_EXITED = "exited"
SMARTDOOR_PET_ACTIVITY_ACTIVITY = "activity"

SMARTDOOR_PET_ACTIVITY_OPTIONS = [
    SMARTDOOR_PET_ACTIVITY_UNKNOWN,
    SMARTDOOR_PET_ACTIVITY_ENTERED,
    SMARTDOOR_PET_ACTIVITY_EXITED,
    SMARTDOOR_PET_ACTIVITY_ACTIVITY,
]

SMARTDOOR_EVENT_TYPE_PET_ENTERED = "pet_entered"
SMARTDOOR_EVENT_TYPE_PET_EXITED = "pet_exited"
SMARTDOOR_EVENT_TYPE_PET_ACTIVITY = "pet_activity"
SMARTDOOR_EVENT_TYPE_SCHEDULE_STARTED = "schedule_started"
SMARTDOOR_EVENT_TYPE_MODE_CHANGED = "mode_changed"
SMARTDOOR_EVENT_TYPE_DOOR_ERROR = "door_error"
SMARTDOOR_EVENT_TYPE_OTHER = "other"

SMARTDOOR_ACTIVITY_EVENT_TYPES = [
    SMARTDOOR_EVENT_TYPE_PET_ENTERED,
    SMARTDOOR_EVENT_TYPE_PET_EXITED,
    SMARTDOOR_EVENT_TYPE_PET_ACTIVITY,
    SMARTDOOR_EVENT_TYPE_SCHEDULE_STARTED,
    SMARTDOOR_EVENT_TYPE_MODE_CHANGED,
    SMARTDOOR_EVENT_TYPE_DOOR_ERROR,
    SMARTDOOR_EVENT_TYPE_OTHER,
]

_PET_ID_KEYS = ("petId", "petID", "pet_id")


def copy_smartdoor_activity_records(
    records_by_door: dict[str, tuple[PetSafeExtendedSmartDoorActivityRecord, ...]] | None,
) -> dict[str, tuple[PetSafeExtendedSmartDoorActivityRecord, ...]]:
    """Return a detached copy of cached SmartDoor activity records."""
    if records_by_door is None:
        return {}
    return {door_api_name: tuple(records) for door_api_name, records in records_by_door.items()}


def copy_smartdoor_pet_states(
    states_by_door: dict[str, dict[str, PetSafeExtendedSmartDoorPetState]] | None,
) -> dict[str, dict[str, PetSafeExtendedSmartDoorPetState]]:
    """Return a detached copy of cached SmartDoor pet states."""
    if states_by_door is None:
        return {}
    return {
        door_api_name: {
            pet_id: PetSafeExtendedSmartDoorPetState(
                last_seen=state.last_seen,
                last_activity=state.last_activity,
                last_activity_at=state.last_activity_at,
                last_activity_code=state.last_activity_code,
            )
            for pet_id, state in pet_states.items()
        }
        for door_api_name, pet_states in states_by_door.items()
    }


def seed_pet_states(linked_pet_ids: tuple[str, ...]) -> dict[str, PetSafeExtendedSmartDoorPetState]:
    """Return default pet states for all pets linked to a SmartDoor."""
    return {
        pet_id: PetSafeExtendedSmartDoorPetState(last_activity=SMARTDOOR_PET_ACTIVITY_UNKNOWN)
        for pet_id in linked_pet_ids
    }


def merge_activity_records(
    previous: tuple[PetSafeExtendedSmartDoorActivityRecord, ...],
    new: list[PetSafeExtendedSmartDoorActivityRecord],
) -> tuple[PetSafeExtendedSmartDoorActivityRecord, ...]:
    """Merge recent activity records while keeping order and removing duplicates."""
    record_map: dict[tuple[str, str, str | None], PetSafeExtendedSmartDoorActivityRecord] = {}
    for record in (*previous, *new):
        record_map[(record.timestamp.isoformat(), record.code, record.pet_id)] = record

    return tuple(
        sorted(
            record_map.values(),
            key=lambda item: item.timestamp,
        )[-SMARTDOOR_ACTIVITY_HISTORY_LIMIT:]
    )


def get_new_activity_records(
    previous: tuple[PetSafeExtendedSmartDoorActivityRecord, ...],
    new: Sequence[PetSafeExtendedSmartDoorActivityRecord],
) -> list[PetSafeExtendedSmartDoorActivityRecord]:
    """Return only activity records that have not already been observed."""
    previous_keys = {_record_key(record) for record in previous}
    emitted_keys: set[tuple[str, str, str | None]] = set()
    fresh_records: list[PetSafeExtendedSmartDoorActivityRecord] = []

    for record in sorted(new, key=lambda item: item.timestamp):
        record_key = _record_key(record)
        if record_key in previous_keys or record_key in emitted_keys:
            continue
        emitted_keys.add(record_key)
        fresh_records.append(record)

    return fresh_records


def apply_activity_records(
    linked_pet_ids: tuple[str, ...],
    previous_states: dict[str, PetSafeExtendedSmartDoorPetState],
    records: Sequence[PetSafeExtendedSmartDoorActivityRecord],
) -> dict[str, PetSafeExtendedSmartDoorPetState]:
    """Apply activity records to derive current per-pet SmartDoor state."""
    states = {
        pet_id: PetSafeExtendedSmartDoorPetState(
            last_seen=previous_states[pet_id].last_seen if pet_id in previous_states else None,
            last_activity=previous_states[pet_id].last_activity
            if pet_id in previous_states
            else SMARTDOOR_PET_ACTIVITY_UNKNOWN,
            last_activity_at=previous_states[pet_id].last_activity_at if pet_id in previous_states else None,
            last_activity_code=previous_states[pet_id].last_activity_code if pet_id in previous_states else None,
        )
        for pet_id in linked_pet_ids
    }

    for record in records:
        if record.pet_id is None or record.pet_id not in states:
            continue
        states[record.pet_id] = PetSafeExtendedSmartDoorPetState(
            last_seen=record.timestamp,
            last_activity=record.activity,
            last_activity_at=record.timestamp,
            last_activity_code=record.code,
        )

    return states


def extract_cursor(activity_items: Sequence[dict[str, Any]], previous_cursor: str | None) -> str | None:
    """Return the latest activity timestamp cursor from raw SmartDoor activity items."""
    timestamps = [timestamp for item in activity_items if (timestamp := _extract_timestamp(item)) is not None]
    if previous_cursor is not None:
        timestamps.append(previous_cursor)
    if not timestamps:
        if previous_cursor is not None:
            return previous_cursor
        return dt_util.utcnow().isoformat()
    return max(timestamps)


def parse_smartdoor_activity_records(
    activity_items: Sequence[dict[str, Any]],
    linked_pet_ids: tuple[str, ...],
) -> list[PetSafeExtendedSmartDoorActivityRecord]:
    """Normalize SmartDoor activity payloads into pet-relevant records."""
    linked_pet_id_set = set(linked_pet_ids)
    records: list[PetSafeExtendedSmartDoorActivityRecord] = []

    for item in activity_items:
        timestamp_str = _extract_timestamp(item)
        code = _extract_code(item)
        if timestamp_str is None or code is None:
            continue

        timestamp = dt_util.parse_datetime(timestamp_str)
        if timestamp is None:
            continue

        pet_id = _extract_pet_id(item)
        if pet_id is not None and linked_pet_id_set and pet_id not in linked_pet_id_set:
            continue

        event_type, activity = _normalize_activity_event(code, pet_id)

        records.append(
            PetSafeExtendedSmartDoorActivityRecord(
                timestamp=timestamp,
                code=code,
                event_type=event_type,
                activity=activity,
                pet_id=pet_id,
            )
        )

    return sorted(records, key=lambda record: record.timestamp)


def _extract_timestamp(item: Mapping[str, Any]) -> str | None:
    """Return the timestamp string for a SmartDoor activity item."""
    for source in (item, _get_nested_mapping(item, "payload")):
        if not isinstance(source, Mapping):
            continue
        for key in ("timestamp", "createdAt", "updatedAt", "time"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_code(item: Mapping[str, Any]) -> str | None:
    """Return the activity code for a SmartDoor item."""
    for source in (item, _get_nested_mapping(item, "payload")):
        if not isinstance(source, Mapping):
            continue
        value = source.get("code")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_pet_id(item: Mapping[str, Any]) -> str | None:
    """Return the pet identifier if the activity item relates to a pet."""
    nested_pet = _get_nested_mapping(_get_nested_mapping(item, "payload"), "pet")
    for source in (item, _get_nested_mapping(item, "payload"), nested_pet):
        if not isinstance(source, Mapping):
            continue
        for key in _PET_ID_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _normalize_activity(code: str, pet_id: str | None) -> str:
    """Normalize a raw PetSafe activity code into a stable pet-facing enum value."""
    return _normalize_activity_event(code, pet_id)[1]


def _normalize_activity_event(code: str, pet_id: str | None) -> tuple[str, str]:
    """Normalize a raw PetSafe activity code into event and pet-state values."""
    normalized = code.strip().upper()
    if pet_id is not None:
        if "ENTER" in normalized or "INBOUND" in normalized:
            return SMARTDOOR_EVENT_TYPE_PET_ENTERED, SMARTDOOR_PET_ACTIVITY_ENTERED
        if "EXIT" in normalized or "OUTBOUND" in normalized or "LEAVE" in normalized:
            return SMARTDOOR_EVENT_TYPE_PET_EXITED, SMARTDOOR_PET_ACTIVITY_EXITED
        return SMARTDOOR_EVENT_TYPE_PET_ACTIVITY, SMARTDOOR_PET_ACTIVITY_ACTIVITY

    if "MODE_CHANGE" in normalized:
        return SMARTDOOR_EVENT_TYPE_MODE_CHANGED, SMARTDOOR_PET_ACTIVITY_UNKNOWN
    if "SCHEDULE" in normalized and any(marker in normalized for marker in ("START", "BEGIN", "RUN")):
        return SMARTDOOR_EVENT_TYPE_SCHEDULE_STARTED, SMARTDOOR_PET_ACTIVITY_UNKNOWN
    if any(marker in normalized for marker in ("ERROR", "FAULT", "JAM", "BLOCK", "STUCK")):
        return SMARTDOOR_EVENT_TYPE_DOOR_ERROR, SMARTDOOR_PET_ACTIVITY_UNKNOWN
    return SMARTDOOR_EVENT_TYPE_OTHER, SMARTDOOR_PET_ACTIVITY_UNKNOWN


def _get_nested_mapping(value: Mapping[str, Any] | None, key: str) -> Mapping[str, Any] | None:
    """Return a nested mapping from a SmartDoor activity payload."""
    if not isinstance(value, Mapping):
        return None
    nested = value.get(key)
    return nested if isinstance(nested, Mapping) else None


def _record_key(record: PetSafeExtendedSmartDoorActivityRecord) -> tuple[str, str, str | None]:
    """Return the dedupe key for a normalized SmartDoor activity record."""
    return record.timestamp.isoformat(), record.code, record.pet_id
