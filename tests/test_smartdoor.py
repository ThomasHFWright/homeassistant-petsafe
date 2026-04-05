"""Tests for PetSafe SmartDoor entities and platform setup."""

from __future__ import annotations

from datetime import timedelta
import json
import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import petsafe_extended as integration_module
from custom_components.petsafe_extended.binary_sensor import async_setup_entry as async_setup_binary_sensor_entry
from custom_components.petsafe_extended.binary_sensor.smartdoor import (
    SMARTDOOR_AC_POWER_DESCRIPTION,
    SMARTDOOR_CONNECTIVITY_DESCRIPTION,
    SMARTDOOR_PROBLEM_DESCRIPTION,
    PetSafeExtendedSmartDoorBinarySensor,
)
from custom_components.petsafe_extended.button import async_setup_entry as async_setup_button_entry
from custom_components.petsafe_extended.button.feeder_refresh import PetSafeExtendedFeederRefreshButton
from custom_components.petsafe_extended.button.smartdoor_refresh import (
    SMARTDOOR_REFRESH_BUTTON_DESCRIPTIONS,
    PetSafeExtendedSmartDoorRefreshButton,
)
from custom_components.petsafe_extended.calendar import async_setup_entry as async_setup_calendar_entry
from custom_components.petsafe_extended.calendar.smartdoor_schedule import PetSafeExtendedSmartDoorScheduleCalendar
from custom_components.petsafe_extended.const import (
    CONF_ENABLE_SMARTDOOR_SCHEDULES,
    DOMAIN,
    FEEDER_LAST_FEEDING_REFRESH_INTERVAL,
    LITTERBOX_ACTIVITY_REFRESH_INTERVAL,
    SMARTDOOR_ACTIVITY_REFRESH_INTERVAL,
    SMARTDOOR_FINAL_ACT_LOCKED,
    SMARTDOOR_FINAL_ACT_UNLOCKED,
    SMARTDOOR_MODE_MANUAL_LOCKED,
    SMARTDOOR_MODE_MANUAL_UNLOCKED,
    SMARTDOOR_MODE_SMART,
)
from custom_components.petsafe_extended.coordinator import PetSafeExtendedDataUpdateCoordinator
from custom_components.petsafe_extended.coordinator.smartdoor_activity import (
    SMARTDOOR_ACTIVITY_EVENT_TYPES,
    SMARTDOOR_EVENT_TYPE_MODE_CHANGED,
    SMARTDOOR_EVENT_TYPE_PET_ENTERED,
    SMARTDOOR_EVENT_TYPE_PET_EXITED,
    SMARTDOOR_PET_ACTIVITY_ENTERED,
    SMARTDOOR_PET_ACTIVITY_EXITED,
    SMARTDOOR_PET_ACTIVITY_UNKNOWN,
)
from custom_components.petsafe_extended.coordinator.smartdoor_schedules import (
    SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
    SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
    SMARTDOOR_SCHEDULE_ACCESS_NO_ACCESS,
    SMARTDOOR_SCHEDULE_ACCESS_OPTIONS,
    SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
    build_smartdoor_pet_schedule_states,
    build_smartdoor_schedule_summary,
    describe_smartdoor_schedule_interval,
    expand_smartdoor_pet_schedule_intervals,
)
from custom_components.petsafe_extended.data import (
    PetSafeExtendedCoordinatorData,
    PetSafeExtendedPetLinkData,
    PetSafeExtendedPetProductLink,
    PetSafeExtendedPetProfile,
    PetSafeExtendedSmartDoorActivityRecord,
    PetSafeExtendedSmartDoorPetScheduleState,
    PetSafeExtendedSmartDoorPetState,
    PetSafeExtendedSmartDoorScheduleRule,
    PetSafeExtendedSmartDoorScheduleSummary,
)
from custom_components.petsafe_extended.diagnostics import async_get_config_entry_diagnostics
from custom_components.petsafe_extended.entity_utils.smartdoor_access import (
    SMARTDOOR_ACCESS_SMART_SCHEDULE,
    SMARTDOOR_CONTROL_SOURCE_SMART_OVERRIDE,
)
from custom_components.petsafe_extended.event import async_setup_entry as async_setup_event_entry
from custom_components.petsafe_extended.event.smartdoor_activity import PetSafeExtendedSmartDoorActivityEvent
from custom_components.petsafe_extended.lock import async_setup_entry
from custom_components.petsafe_extended.lock.smartdoor import PetSafeExtendedSmartDoorLock
from custom_components.petsafe_extended.select import async_setup_entry as async_setup_select_entry
from custom_components.petsafe_extended.select.smartdoor_final_act import PetSafeExtendedSmartDoorFinalActSelect
from custom_components.petsafe_extended.select.smartdoor_operating_mode import (
    PetSafeExtendedSmartDoorOperatingModeSelect,
)
from custom_components.petsafe_extended.select.smartdoor_override import PetSafeExtendedSmartDoorOverrideSelect
from custom_components.petsafe_extended.sensor import async_setup_entry as async_setup_sensor_entry
from custom_components.petsafe_extended.sensor.smartdoor_diagnostic import (
    SMARTDOOR_BATTERY_LEVEL_DESCRIPTION,
    SMARTDOOR_BATTERY_VOLTAGE_DESCRIPTION,
    SMARTDOOR_SIGNAL_STRENGTH_DESCRIPTION,
    PetSafeExtendedSmartDoorDiagnosticSensor,
)
from custom_components.petsafe_extended.sensor.smartdoor_pet import (
    SMARTDOOR_PET_LAST_ACTIVITY_DESCRIPTION,
    SMARTDOOR_PET_SMART_ACCESS_DESCRIPTION,
    PetSafeExtendedSmartDoorPetSensor,
)
from custom_components.petsafe_extended.sensor.smartdoor_schedule import PetSafeExtendedSmartDoorScheduleSensor
from homeassistant.const import EntityCategory, Platform
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util


def _create_smartdoor(
    *,
    api_name: str = "smartdoor-1",
    mode: str | None = SMARTDOOR_MODE_SMART,
    latch_state: str | None = "Closed",
    final_act: str | None = SMARTDOOR_FINAL_ACT_UNLOCKED,
    connection_status: str | None = "online",
    battery_level: int | None = 75,
    battery_voltage: float | None = 12.3,
    rssi: int | None = -40,
    has_adapter: bool | None = False,
    error_state: str | None = None,
    override_payload: list[dict[str, Any]] | None = None,
) -> Any:
    """Construct a SmartDoor device stub with async methods."""
    door = SimpleNamespace()
    door.api_name = api_name
    door.data = {
        "productName": "SmartDoor",
        "friendlyName": "Back Door",
        "shadow": {
            "state": {
                "reported": {
                    "power": {
                        "finalAct": final_act,
                    }
                }
            }
        },
    }
    door.firmware = "1.0.0"
    door.mode = mode
    door.latch_state = latch_state
    door.error_state = error_state
    door.has_adapter = has_adapter
    door.connection_status = connection_status
    door.battery_voltage = battery_voltage
    door.rssi = rssi
    door.battery_level = battery_level
    door.lock = AsyncMock()
    door.unlock = AsyncMock()
    door.set_mode = AsyncMock()
    door.set_final_act = AsyncMock()
    door.override_schedule = AsyncMock()
    door.get_schedules = AsyncMock(return_value=[])
    door.get_override_schedules = AsyncMock(return_value=override_payload or [{}])
    door.get_preferences = AsyncMock(return_value={})
    return door


def _create_product_stub(api_name: str, product_name: str, product_type: str) -> Any:
    """Construct a generic PetSafe product stub for coordinator tests."""
    product = SimpleNamespace()
    product.api_name = api_name
    product.data = {
        "productId": api_name,
        "thingName": api_name,
        "friendlyName": product_name,
        "productName": product_type,
    }
    return product


def _create_feeder(
    *,
    api_name: str = "feeder-1",
    schedules: list[dict[str, Any]] | None = None,
    feeding: dict[str, Any] | None = None,
) -> Any:
    """Construct a feeder device stub with async methods."""
    feeder = SimpleNamespace()
    feeder.api_name = api_name
    feeder.data = {
        "productName": "Smart Feed",
        "friendlyName": "Kitchen Feeder",
        "network_rssi": -52,
    }
    feeder.battery_level = 80
    feeder.food_low_status = 0
    feeder.is_locked = False
    feeder.is_paused = False
    feeder.is_slow_feed = False
    feeder.feed = AsyncMock()
    feeder.lock = AsyncMock()
    feeder.pause = AsyncMock()
    feeder.slow_feed = AsyncMock()
    feeder.schedule_feed = AsyncMock()
    feeder.delete_schedule = AsyncMock()
    feeder.delete_all_schedules = AsyncMock()
    feeder.modify_schedule = AsyncMock()
    feeder.get_last_feeding = AsyncMock(return_value=feeding or {"payload": {"time": 1_775_191_200}})
    feeder.get_schedules = AsyncMock(return_value=schedules or [{"time": "08:00", "id": "morning"}])
    return feeder


def _create_litterbox(
    *,
    api_name: str = "litter-1",
    activity: list[dict[str, Any]] | None = None,
) -> Any:
    """Construct a litter box device stub with async methods."""
    litterbox = SimpleNamespace()
    litterbox.api_name = api_name
    litterbox.data = {
        "productName": "ScoopFree",
        "friendlyName": "Main Litter Box",
        "shadow": {
            "state": {
                "reported": {
                    "rakeCount": 3,
                    "rssi": -61,
                    "rakeDelayTime": 10,
                }
            }
        },
    }
    litterbox.rake = AsyncMock()
    litterbox.reset_counters = AsyncMock()
    litterbox.modify_timer = AsyncMock()
    litterbox.get_activity = AsyncMock(return_value=activity or [])
    return litterbox


def _create_activity_item(code: str, timestamp: str, *, pet_id: str | None = None) -> dict[str, Any]:
    """Build a SmartDoor activity payload for tests."""
    payload: dict[str, Any] = {}
    if pet_id is not None:
        payload["petId"] = pet_id
    return {
        "code": code,
        "thingName": "door-1",
        "timestamp": timestamp,
        "payload": payload,
    }


def _create_activity_record(
    *,
    timestamp: str = "2026-04-02T08:00:00.000Z",
    code: str = "PET_ENTERED",
    event_type: str = SMARTDOOR_EVENT_TYPE_PET_ENTERED,
    activity: str = SMARTDOOR_PET_ACTIVITY_ENTERED,
    pet_id: str | None = "pet-1",
) -> PetSafeExtendedSmartDoorActivityRecord:
    """Build a normalized SmartDoor activity record for event entity tests."""
    parsed_timestamp = dt_util.parse_datetime(timestamp)
    assert parsed_timestamp is not None
    return PetSafeExtendedSmartDoorActivityRecord(
        timestamp=parsed_timestamp,
        code=code,
        event_type=event_type,
        activity=activity,
        pet_id=pet_id,
    )


def _create_schedule(
    *,
    title: str,
    start_time: str,
    day_of_week: str = "1111111",
    access: int = 3,
    pet_ids: list[str] | None = None,
    is_enabled: bool = True,
    next_action_at: int | None = None,
    prev_action_at: int | None = None,
) -> dict[str, Any]:
    """Build a SmartDoor schedule payload for tests."""
    schedule: dict[str, Any] = {
        "scheduleId": f"{title.lower().replace(' ', '-')}-id",
        "title": title,
        "startTime": start_time,
        "dayOfWeek": day_of_week,
        "access": access,
        "isEnabled": is_enabled,
        "petIds": pet_ids or [],
    }
    if next_action_at is not None:
        schedule["nextActionAt"] = next_action_at
    if prev_action_at is not None:
        schedule["prevActionAt"] = prev_action_at
    return schedule


@pytest.fixture
def coordinator(hass, mock_config_entry, attach_runtime_data):
    """Create a coordinator instance with a mocked API client."""
    api = MagicMock()
    mock_config_entry.add_to_hass(hass)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    attach_runtime_data(mock_config_entry, coordinator)
    return coordinator


def test_smartdoor_mode_constants_match_api_contract() -> None:
    """SmartDoor mode constants should match the PetSafe API payload values."""
    assert SMARTDOOR_MODE_MANUAL_LOCKED == "MANUAL_LOCKED"
    assert SMARTDOOR_MODE_MANUAL_UNLOCKED == "MANUAL_UNLOCKED"
    assert SMARTDOOR_MODE_SMART == "SMART"


@pytest.mark.asyncio
async def test_lock_entity_state_and_controls(coordinator) -> None:
    """Validate SmartDoor lock entity properties and control actions."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_LOCKED, latch_state="Open")
    unlocked_door = _create_smartdoor(
        mode=SMARTDOOR_MODE_MANUAL_UNLOCKED,
        latch_state="Open",
    )
    relocked_door = _create_smartdoor(
        mode=SMARTDOOR_MODE_MANUAL_LOCKED,
        latch_state="Open",
    )
    coordinator.async_set_smartdoor_lock = AsyncMock(side_effect=[unlocked_door, relocked_door])
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    entity = PetSafeExtendedSmartDoorLock(coordinator, door)

    assert entity.unique_id == "smartdoor-1_smartdoor_lock"
    assert entity.available is True
    assert entity.is_locked is True
    assert entity.is_open is True

    expected_attrs = {
        "mode": SMARTDOOR_MODE_MANUAL_LOCKED,
        "latch_state": "Open",
        "error_state": None,
        "has_adapter": False,
        "connection_status": "online",
        "battery_voltage": 12.3,
        "rssi": -40,
        "battery_level": 75,
    }
    for key, value in expected_attrs.items():
        assert entity.extra_state_attributes[key] == value

    await entity.async_unlock()
    assert entity.is_locked is False

    await entity.async_lock()
    assert entity.is_locked is True

    assert coordinator.async_set_smartdoor_lock.await_args_list == [
        call(door.api_name, False),
        call(door.api_name, True),
    ]

    relocked_door.connection_status = "offline"
    assert entity.available is False


@pytest.mark.asyncio
async def test_lock_entity_uses_smartdoor_model_fallback(coordinator) -> None:
    """SmartDoor devices without product metadata should still register the correct model."""
    door = _create_smartdoor()
    door.data = {"friendlyName": "Back Door"}
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    entity = PetSafeExtendedSmartDoorLock(coordinator, door)

    assert entity.device_info is not None
    assert entity.device_info.get("model") == "SmartDoor"


@pytest.mark.asyncio
async def test_lock_entity_updates_from_coordinator(coordinator, hass) -> None:
    """Ensure the entity replaces its door reference when coordinator data changes."""
    original_door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_UNLOCKED)
    updated_door = _create_smartdoor(
        mode=SMARTDOOR_MODE_MANUAL_LOCKED,
        latch_state="Open",
        connection_status="offline",
    )
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[original_door])
    entity = PetSafeExtendedSmartDoorLock(coordinator, original_door)
    entity.hass = hass
    entity.entity_id = "lock.test_door"

    assert entity.is_locked is False

    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[updated_door])
    entity._handle_coordinator_update()  # noqa: SLF001

    assert entity.is_locked is True
    assert entity.available is False
    assert entity.is_open is True


@pytest.mark.asyncio
async def test_lock_entity_treats_smart_mode_as_locked(coordinator) -> None:
    """Smart mode should remain on the locked side of the Home Assistant lock abstraction."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_SMART, latch_state="Closed")
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    entity = PetSafeExtendedSmartDoorLock(coordinator, door)

    assert entity.is_locked is True


@pytest.mark.asyncio
async def test_lock_entity_normalizes_mode_and_latch_state(coordinator) -> None:
    """Lock state should tolerate raw API casing and fall back to latch state."""
    unlocked_door = _create_smartdoor(mode="MANUAL_UNLOCKED", latch_state="UNLOCKED")
    smart_door = _create_smartdoor(mode="SMART", latch_state="Closed")
    locked_door = _create_smartdoor(mode="unexpected_mode", latch_state="LOCKED")
    unknown_door = _create_smartdoor(mode="unexpected_mode", latch_state="unexpected_state")

    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[unlocked_door])
    unlocked_entity = PetSafeExtendedSmartDoorLock(coordinator, unlocked_door)
    assert unlocked_entity.is_locked is False

    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[smart_door])
    smart_entity = PetSafeExtendedSmartDoorLock(coordinator, smart_door)
    assert smart_entity.is_locked is True

    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[locked_door])
    locked_entity = PetSafeExtendedSmartDoorLock(coordinator, locked_door)
    assert locked_entity.is_locked is True

    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[unknown_door])
    unknown_entity = PetSafeExtendedSmartDoorLock(coordinator, unknown_door)
    assert unknown_entity.is_locked is None


@pytest.mark.asyncio
async def test_lock_platform_setup_adds_entities(hass, mock_config_entry, attach_runtime_data) -> None:
    """The lock platform should add one entity per smartdoor from the coordinator."""
    door = _create_smartdoor()
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)

    async_add_entities = MagicMock()
    with patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])):
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]
    assert len(added_entities) == 1
    assert isinstance(added_entities[0], PetSafeExtendedSmartDoorLock)


@pytest.mark.asyncio
async def test_lock_platform_setup_handles_failure(hass, mock_config_entry, attach_runtime_data) -> None:
    """A failure retrieving smartdoors should raise ConfigEntryNotReady."""
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)

    with (
        patch.object(coordinator, "get_smartdoors", AsyncMock(side_effect=RuntimeError)),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, mock_config_entry, MagicMock())


@pytest.mark.asyncio
async def test_smartdoor_diagnostic_sensor_values(coordinator) -> None:
    """SmartDoor diagnostic sensors should normalize current door telemetry."""
    door = _create_smartdoor(
        battery_level=100,
        battery_voltage=5862,
        rssi=-40,
    )
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    battery_entity = PetSafeExtendedSmartDoorDiagnosticSensor(
        coordinator,
        door,
        SMARTDOOR_BATTERY_LEVEL_DESCRIPTION,
    )
    voltage_entity = PetSafeExtendedSmartDoorDiagnosticSensor(
        coordinator,
        door,
        SMARTDOOR_BATTERY_VOLTAGE_DESCRIPTION,
    )
    signal_entity = PetSafeExtendedSmartDoorDiagnosticSensor(
        coordinator,
        door,
        SMARTDOOR_SIGNAL_STRENGTH_DESCRIPTION,
    )

    assert battery_entity.native_value == 100
    assert battery_entity.entity_category is EntityCategory.DIAGNOSTIC
    assert voltage_entity.native_value == 5.862
    assert voltage_entity.entity_category is EntityCategory.DIAGNOSTIC
    assert voltage_entity.entity_registry_enabled_default is False
    assert signal_entity.native_value == -40
    assert signal_entity.entity_category is EntityCategory.DIAGNOSTIC
    assert signal_entity.entity_registry_enabled_default is False


@pytest.mark.asyncio
async def test_smartdoor_binary_sensor_values(coordinator) -> None:
    """SmartDoor binary sensors should expose AC power, connectivity, and problem state."""
    door = _create_smartdoor(
        has_adapter=False,
        connection_status="online",
        error_state="NONE",
    )
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    ac_power_entity = PetSafeExtendedSmartDoorBinarySensor(
        coordinator,
        door,
        SMARTDOOR_AC_POWER_DESCRIPTION,
    )
    connectivity_entity = PetSafeExtendedSmartDoorBinarySensor(
        coordinator,
        door,
        SMARTDOOR_CONNECTIVITY_DESCRIPTION,
    )
    problem_entity = PetSafeExtendedSmartDoorBinarySensor(
        coordinator,
        door,
        SMARTDOOR_PROBLEM_DESCRIPTION,
    )

    assert ac_power_entity.is_on is False
    assert ac_power_entity.entity_category is EntityCategory.DIAGNOSTIC
    assert connectivity_entity.is_on is True
    assert connectivity_entity.available is True
    assert connectivity_entity.entity_category is EntityCategory.DIAGNOSTIC
    assert connectivity_entity.extra_state_attributes == {"connection_status": "online"}
    assert problem_entity.is_on is False
    assert problem_entity.extra_state_attributes == {"error_state": "NONE"}

    door.has_adapter = True
    door.connection_status = "offline"
    door.error_state = "SENSOR_BLOCKED"

    assert ac_power_entity.is_on is True
    assert connectivity_entity.is_on is False
    assert connectivity_entity.available is True
    assert connectivity_entity.extra_state_attributes == {"connection_status": "offline"}
    assert problem_entity.is_on is True
    assert problem_entity.extra_state_attributes == {"error_state": "SENSOR_BLOCKED"}


@pytest.mark.asyncio
async def test_binary_sensor_platform_setup_adds_smartdoor_entities(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """The binary sensor platform should add SmartDoor diagnostic entities."""
    door = _create_smartdoor()
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)

    async_add_entities = MagicMock()
    with patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])):
        await async_setup_binary_sensor_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]
    assert len(added_entities) == 3
    assert all(isinstance(entity, PetSafeExtendedSmartDoorBinarySensor) for entity in added_entities)
    assert {entity.entity_description.key for entity in added_entities} == {"ac_power", "connectivity", "problem"}


@pytest.mark.asyncio
async def test_binary_sensor_platform_updates_existing_diagnostic_entity_categories(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Existing SmartDoor binary sensors should migrate into the diagnostic section."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    entity_reg = er.async_get(hass)
    existing_entry = entity_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "door-1_ac_power",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_ac_power",
    )
    connectivity_entry = entity_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "door-1_connectivity",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_connectivity",
    )
    assert existing_entry.entity_category is None
    assert connectivity_entry.entity_category is None

    async_add_entities = MagicMock()
    with patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])):
        await async_setup_binary_sensor_entry(hass, mock_config_entry, async_add_entities)

    updated_entry = entity_reg.async_get(existing_entry.entity_id)
    updated_connectivity_entry = entity_reg.async_get(connectivity_entry.entity_id)
    assert updated_entry is not None
    assert updated_connectivity_entry is not None
    assert updated_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert updated_connectivity_entry.entity_category is EntityCategory.DIAGNOSTIC


@pytest.mark.asyncio
async def test_operating_mode_select_state_and_controls(coordinator) -> None:
    """SmartDoor locked-mode select should expose and change the preferred locked mode."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_SMART)
    locked_door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_LOCKED)
    coordinator.async_set_smartdoor_locked_mode = AsyncMock(return_value=locked_door)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    entity = PetSafeExtendedSmartDoorOperatingModeSelect(coordinator, door)

    assert entity.current_option == "smart"
    assert entity.translation_key == "operating_mode"
    assert entity.entity_category is None

    await entity.async_select_option("locked")

    assert entity.current_option == "locked"
    coordinator.async_set_smartdoor_locked_mode.assert_awaited_once_with(
        door.api_name,
        SMARTDOOR_MODE_MANUAL_LOCKED,
    )


@pytest.mark.asyncio
async def test_smartdoor_override_select_state_and_controls(coordinator) -> None:
    """SmartDoor override select should expose and change the current schedule override."""
    door = _create_smartdoor()
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        smartdoor_override_options={door.api_name: SMARTDOOR_ACCESS_SMART_SCHEDULE},
    )
    updated_door = _create_smartdoor(override_payload=[{"thingName": door.api_name, "access": 3}])
    coordinator.async_set_smartdoor_override = AsyncMock(return_value=updated_door)
    coordinator.get_smartdoor_override_option = MagicMock(  # type: ignore[method-assign]
        side_effect=[SMARTDOOR_ACCESS_SMART_SCHEDULE, "full_access"]
    )

    entity = PetSafeExtendedSmartDoorOverrideSelect(coordinator, door)

    assert entity.current_option == SMARTDOOR_ACCESS_SMART_SCHEDULE
    assert entity.translation_key == "smart_override"
    assert entity.entity_category is None

    await entity.async_select_option("full_access")

    assert entity.current_option == "full_access"
    coordinator.async_set_smartdoor_override.assert_awaited_once_with(door.api_name, "full_access")


@pytest.mark.asyncio
async def test_smartdoor_override_select_cannot_clear_active_override(coordinator) -> None:
    """Selecting Smart Schedule should raise until PetSafe exposes a direct clear path."""
    door = _create_smartdoor(override_payload=[{"thingName": "smartdoor-1", "access": 3}])
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        smartdoor_override_options={door.api_name: "full_access"},
    )
    entity = PetSafeExtendedSmartDoorOverrideSelect(coordinator, door)

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option(SMARTDOOR_ACCESS_SMART_SCHEDULE)


@pytest.mark.asyncio
async def test_operating_mode_select_uses_locked_preference_when_unlocked(coordinator) -> None:
    """When the SmartDoor is unlocked, the select should expose the stored locked-mode preference."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_UNLOCKED)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])
    coordinator.async_set_smartdoor_locked_mode_preference(door.api_name, SMARTDOOR_MODE_SMART)

    entity = PetSafeExtendedSmartDoorOperatingModeSelect(coordinator, door)

    assert entity.current_option == "smart"


@pytest.mark.asyncio
async def test_operating_mode_select_restores_preference_when_unlocked(coordinator, hass) -> None:
    """The locked-mode preference should restore across HA restarts while the door is unlocked."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_UNLOCKED)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    entity = PetSafeExtendedSmartDoorOperatingModeSelect(coordinator, door)
    entity.hass = hass
    entity.entity_id = "select.test_locked_mode"
    entity.async_get_last_state = AsyncMock(return_value=SimpleNamespace(state="smart"))  # type: ignore[method-assign]
    coordinator.async_set_updated_data = MagicMock()

    await entity.async_added_to_hass()

    assert entity.current_option == "smart"


@pytest.mark.asyncio
async def test_final_act_select_state_and_controls(coordinator) -> None:
    """SmartDoor final-act select should expose and change the current power-loss action."""
    door = _create_smartdoor(final_act=SMARTDOOR_FINAL_ACT_UNLOCKED)
    locked_door = _create_smartdoor(final_act=SMARTDOOR_FINAL_ACT_LOCKED)
    coordinator.async_set_smartdoor_final_act = AsyncMock(return_value=locked_door)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    entity = PetSafeExtendedSmartDoorFinalActSelect(coordinator, door)

    assert entity.current_option == "unlocked"
    assert entity.translation_key == "final_act"

    await entity.async_select_option("locked")

    assert entity.current_option == "locked"
    coordinator.async_set_smartdoor_final_act.assert_awaited_once_with(
        door.api_name,
        SMARTDOOR_FINAL_ACT_LOCKED,
    )


@pytest.mark.asyncio
async def test_select_platform_adds_smartdoor_selects(hass, mock_config_entry, attach_runtime_data) -> None:
    """The select platform should add the SmartDoor locked-mode, override, and final-act selects."""
    door = _create_smartdoor(api_name="door-1")
    door.get_activity = AsyncMock(return_value=[])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)

    async_add_entities = MagicMock()
    with (
        patch.object(coordinator, "get_litterboxes", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])),
    ):
        await async_setup_select_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]

    assert len(added_entities) == 3
    assert any(isinstance(entity, PetSafeExtendedSmartDoorOperatingModeSelect) for entity in added_entities)
    assert any(isinstance(entity, PetSafeExtendedSmartDoorOverrideSelect) for entity in added_entities)
    assert any(isinstance(entity, PetSafeExtendedSmartDoorFinalActSelect) for entity in added_entities)
    assert {entity.translation_key for entity in added_entities} == {
        "operating_mode",
        "smart_override",
        "final_act",
    }
    operating_mode_entity = next(
        entity for entity in added_entities if isinstance(entity, PetSafeExtendedSmartDoorOperatingModeSelect)
    )
    assert operating_mode_entity.options == ["locked", "smart"]
    override_entity = next(
        entity for entity in added_entities if isinstance(entity, PetSafeExtendedSmartDoorOverrideSelect)
    )
    assert override_entity.options == ["smart_schedule", "no_access", "out_only", "in_only", "full_access"]
    assert all(entity.device_info is not None for entity in added_entities)
    assert all(entity.device_info["identifiers"] == {("petsafe_extended", "door-1")} for entity in added_entities)


@pytest.mark.asyncio
async def test_select_platform_updates_existing_registry_entity_categories(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Existing SmartDoor selects should migrate to their current entity categories."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)

    entity_reg = er.async_get(hass)
    operating_mode_entity = PetSafeExtendedSmartDoorOperatingModeSelect(coordinator, door)
    final_act_entity = PetSafeExtendedSmartDoorFinalActSelect(coordinator, door)
    assert operating_mode_entity.unique_id is not None
    assert final_act_entity.unique_id is not None

    locked_mode_entry = entity_reg.async_get_or_create(
        "select",
        DOMAIN,
        operating_mode_entity.unique_id,
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_locked_mode",
        entity_category=EntityCategory.CONFIG,
    )
    power_loss_entry = entity_reg.async_get_or_create(
        "select",
        DOMAIN,
        final_act_entity.unique_id,
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_power_loss_action",
        entity_category=EntityCategory.CONFIG,
    )

    async_add_entities = MagicMock()
    with (
        patch.object(coordinator, "get_litterboxes", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])),
    ):
        await async_setup_select_entry(hass, mock_config_entry, async_add_entities)

    updated_locked_mode_entry = entity_reg.async_get(locked_mode_entry.entity_id)
    updated_power_loss_entry = entity_reg.async_get(power_loss_entry.entity_id)

    assert updated_locked_mode_entry is not None
    assert updated_power_loss_entry is not None
    assert updated_locked_mode_entry.entity_category is None
    assert updated_power_loss_entry.entity_category is EntityCategory.CONFIG


@pytest.mark.asyncio
async def test_coordinator_get_smartdoors_caches_results(hass, mock_config_entry) -> None:
    """Coordinator caching should avoid redundant API calls."""
    api = MagicMock()
    door = _create_smartdoor()
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)

    first = await coordinator.get_smartdoors()
    second = await coordinator.get_smartdoors()

    assert first is second
    api.get_smartdoors.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_get_smartdoors_raises_auth_failed(hass, mock_config_entry) -> None:
    """HTTP auth errors should raise Home Assistant reauth requests immediately."""
    api = MagicMock()
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(401, request=request)
    api.get_smartdoors = AsyncMock(
        side_effect=httpx.HTTPStatusError("Unauthorized", request=request, response=response)
    )
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator.get_smartdoors()


@pytest.mark.asyncio
async def test_coordinator_applies_smartdoor_override_during_refresh(hass, mock_config_entry) -> None:
    """A fetched SmartDoor override should update effective per-pet access in the same refresh cycle."""
    door = _create_smartdoor(
        api_name="door-1",
        override_payload=[{"thingName": "door-1", "access": 3}],
    )
    door.get_schedules = AsyncMock(
        return_value=[
            _create_schedule(
                title="Cats outside",
                start_time="08:00",
                access=1,
                pet_ids=["pet-1"],
            )
        ]
    )
    door.get_preferences = AsyncMock(return_value={"tz": "Europe/London"})

    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_feeder_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_litterbox_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_pet_links = AsyncMock(  # noqa: SLF001
        return_value=PetSafeExtendedPetLinkData(
            links=(PetSafeExtendedPetProductLink("pet-1", "door-1", "smartdoor"),),
            pets_by_id={
                "pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo"),
            },
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_type_by_product_id={"door-1": "smartdoor"},
        )
    )
    coordinator._async_build_smartdoor_pet_states = AsyncMock(return_value=({}, {}, {}))  # noqa: SLF001

    fixed_now = dt_util.parse_datetime("2026-04-03T09:00:00+01:00")
    assert fixed_now is not None

    with patch("custom_components.petsafe_extended.coordinator.base.dt_util.now", return_value=fixed_now):
        await coordinator.async_refresh()

    pet_schedule_state = coordinator.get_smartdoor_pet_schedule_state("door-1", "pet-1")

    assert coordinator.get_smartdoor_override_option("door-1") == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert pet_schedule_state is not None
    assert pet_schedule_state.smart_access == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY
    assert pet_schedule_state.effective_access == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert pet_schedule_state.override_access == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert pet_schedule_state.control_source == SMARTDOOR_CONTROL_SOURCE_SMART_OVERRIDE


@pytest.mark.asyncio
async def test_coordinator_async_set_smartdoor_override_updates_cached_state(hass, mock_config_entry) -> None:
    """Setting a SmartDoor override should update the cached override and effective per-pet state."""
    door = _create_smartdoor(api_name="door-1")
    door.get_override_schedules = AsyncMock(return_value=[{"thingName": "door-1", "access": 3}])
    api = MagicMock()
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            links=(PetSafeExtendedPetProductLink("pet-1", "door-1", "smartdoor"),),
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_schedule_rules={
            "door-1": (
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="cats-out",
                    title="Cats outside",
                    start_time="08:00",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
                    is_enabled=True,
                    pet_ids=("pet-1",),
                    pet_names=("Milo",),
                    pet_count=1,
                    timezone="Europe/London",
                ),
            )
        },
        smartdoor_override_options={"door-1": SMARTDOOR_ACCESS_SMART_SCHEDULE},
    )

    fixed_now = dt_util.parse_datetime("2026-04-03T09:00:00+01:00")
    assert fixed_now is not None

    with patch("custom_components.petsafe_extended.coordinator.base.dt_util.now", return_value=fixed_now):
        refreshed_door = await coordinator.async_set_smartdoor_override("door-1", "full_access")

    pet_schedule_state = coordinator.get_smartdoor_pet_schedule_state("door-1", "pet-1")

    assert refreshed_door is door
    door.override_schedule.assert_awaited_once_with(3, update_data=False)
    assert coordinator.get_smartdoor_override_option("door-1") == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert pet_schedule_state is not None
    assert pet_schedule_state.smart_access == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY
    assert pet_schedule_state.effective_access == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert pet_schedule_state.override_access == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert pet_schedule_state.control_source == SMARTDOOR_CONTROL_SOURCE_SMART_OVERRIDE


@pytest.mark.asyncio
async def test_coordinator_update_data_includes_smartdoors(hass, mock_config_entry) -> None:
    """The coordinator should populate smartdoor data during updates."""
    door = _create_smartdoor()
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=["feeder"])
    api.get_litterboxes = AsyncMock(return_value=["litterbox"])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_feeder_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_litterbox_details = AsyncMock(return_value={})  # noqa: SLF001

    await coordinator.async_refresh()
    data = coordinator.data

    assert isinstance(data, PetSafeExtendedCoordinatorData)
    assert data.smartdoors == [door]
    api.get_feeders.assert_awaited_once()
    api.get_litterboxes.assert_awaited_once()
    api.get_smartdoors.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_builds_generic_pet_product_links(hass, mock_config_entry) -> None:
    """Pet linkage should support one pet mapped to multiple product types."""
    door = _create_smartdoor(api_name="door-1")
    door.data["productId"] = "door-1"
    door.data["thingName"] = "door-1"
    feeder = _create_product_stub("feeder-1", "Kitchen Feeder", "SmartFeed")
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[feeder])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_feeder_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_litterbox_details = AsyncMock(return_value={})  # noqa: SLF001

    pet_products = {
        "pet-1": [
            {"productId": "door-1", "productType": "SmartDoor"},
            {"productId": "tracker-9", "productType": "Pet Tracker"},
            {"productId": "feeder-1", "productType": "SmartFeed"},
        ],
        "pet-2": [
            {"productId": "door-1", "productType": "SmartDoor"},
        ],
    }

    with (
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pets",
            AsyncMock(
                return_value=[
                    {"petId": "pet-1", "name": "Milo", "petType": "cat", "technology": "microchip"},
                    {"petId": "pet-2", "name": "Otis", "petType": "cat"},
                ]
            ),
        ),
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pet_products",
            AsyncMock(side_effect=lambda hass, client, pet_id: pet_products[pet_id]),
        ),
    ):
        await coordinator.async_refresh()

    data = coordinator.data

    assert data is not None
    assert data.pet_links.pets_by_id["pet-1"].name == "Milo"
    assert data.pet_links.product_ids_by_pet_id["pet-1"] == ("door-1", "feeder-1", "tracker-9")
    assert data.pet_links.pet_ids_by_product_id["door-1"] == ("pet-1", "pet-2")
    assert data.pet_links.product_type_by_product_id["door-1"] == "smartdoor"
    assert data.pet_links.product_type_by_product_id["feeder-1"] == "feeder"
    assert data.pet_links.product_type_by_product_id["tracker-9"] == "tracker"
    assert coordinator.get_product_ids_for_pet("pet-1") == ("door-1", "feeder-1", "tracker-9")
    assert coordinator.get_smartdoor_pet_ids("door-1") == ("pet-1", "pet-2")


@pytest.mark.asyncio
async def test_coordinator_builds_smartdoor_pet_states_from_activity(hass, mock_config_entry) -> None:
    """SmartDoor activity should derive latest per-pet state from linked pet events."""
    door = _create_smartdoor(api_name="door-1")
    door.data["productId"] = "door-1"
    door.data["thingName"] = "door-1"
    door.get_activity = AsyncMock(
        return_value=[
            _create_activity_item("CLOUD_MODE_CHANGE_UNLOCKED", "2026-04-02T08:00:00.000Z"),
            _create_activity_item("PET_ENTERED", "2026-04-02T08:02:00.000Z", pet_id="pet-1"),
            _create_activity_item("PET_EXITED", "2026-04-02T08:04:00.000Z", pet_id="pet-2"),
        ]
    )
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_feeder_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_litterbox_details = AsyncMock(return_value={})  # noqa: SLF001

    with (
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pets",
            AsyncMock(
                return_value=[
                    {
                        "petId": "pet-1",
                        "profile": {
                            "name": "Milo",
                            "petType": "cat",
                            "gender": "male",
                            "weight": 4.2,
                            "unit": "kg",
                        },
                        "technologies": [{"technology": "MICROCHIP"}],
                    },
                    {
                        "petId": "pet-2",
                        "profile": {
                            "name": "Otis",
                            "petType": "cat",
                            "gender": "male",
                            "weight": 5.0,
                            "unit": "kg",
                        },
                        "technologies": [{"technology": "MICROCHIP"}],
                    },
                ]
            ),
        ),
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pet_products",
            AsyncMock(return_value=[{"productId": "door-1", "productType": "SmartDoor"}]),
        ),
    ):
        await coordinator.async_refresh()

    pet_one_state = coordinator.get_smartdoor_pet_state("door-1", "pet-1")
    pet_two_state = coordinator.get_smartdoor_pet_state("door-1", "pet-2")

    assert pet_one_state is not None
    assert pet_two_state is not None
    assert pet_one_state.last_activity == SMARTDOOR_PET_ACTIVITY_ENTERED
    assert pet_two_state.last_activity == SMARTDOOR_PET_ACTIVITY_EXITED
    assert coordinator.get_pet_profile("pet-1").name == "Milo"  # type: ignore[union-attr]
    assert coordinator.data.smartdoor_activity_records["door-1"][-1].pet_id == "pet-2"
    door.get_activity.assert_awaited_once_with(limit=200)


@pytest.mark.asyncio
async def test_coordinator_smartdoor_activity_uses_since_cursor(hass, mock_config_entry) -> None:
    """Subsequent SmartDoor activity refreshes should use a watermark cursor."""
    door = _create_smartdoor(api_name="door-1")
    door.data["productId"] = "door-1"
    initial_activity = [
        _create_activity_item("PET_ENTERED", "2026-04-02T08:02:00.000Z", pet_id="pet-1"),
    ]
    updated_activity = [
        _create_activity_item("PET_EXITED", "2026-04-02T08:05:00.000Z", pet_id="pet-1"),
    ]
    door.get_activity = AsyncMock(side_effect=[initial_activity, updated_activity])
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_feeder_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_litterbox_details = AsyncMock(return_value={})  # noqa: SLF001

    with (
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pets",
            AsyncMock(
                return_value=[
                    {
                        "petId": "pet-1",
                        "profile": {"name": "Milo", "petType": "cat"},
                        "technologies": [{"technology": "MICROCHIP"}],
                    }
                ]
            ),
        ),
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pet_products",
            AsyncMock(return_value=[{"productId": "door-1", "productType": "SmartDoor"}]),
        ),
    ):
        await coordinator.async_refresh()
        coordinator._smartdoor_activity_last_refresh_by_door["door-1"] = (  # noqa: SLF001
            time.monotonic() - SMARTDOOR_ACTIVITY_REFRESH_INTERVAL.total_seconds()
        )
        await coordinator.async_refresh()

    pet_state = coordinator.get_smartdoor_pet_state("door-1", "pet-1")

    assert pet_state is not None
    assert pet_state.last_activity == SMARTDOOR_PET_ACTIVITY_EXITED
    assert door.get_activity.await_args_list == [
        call(limit=200),
        call(since="2026-04-02T08:02:00.000Z"),
    ]


@pytest.mark.asyncio
async def test_coordinator_smartdoor_activity_does_not_replay_startup_history(hass, mock_config_entry) -> None:
    """Initial SmartDoor history seeding should not dispatch old events to listeners."""
    door = _create_smartdoor(api_name="door-1")
    door.data["productId"] = "door-1"
    door.get_activity = AsyncMock(
        side_effect=[
            [_create_activity_item("PET_ENTERED", "2026-04-02T08:02:00.000Z", pet_id="pet-1")],
            [
                _create_activity_item("PET_ENTERED", "2026-04-02T08:02:00.000Z", pet_id="pet-1"),
                _create_activity_item("PET_EXITED", "2026-04-02T08:05:00.000Z", pet_id="pet-1"),
            ],
        ]
    )
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_feeder_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_litterbox_details = AsyncMock(return_value={})  # noqa: SLF001
    observed_records: list[PetSafeExtendedSmartDoorActivityRecord] = []
    unsubscribe = coordinator.async_subscribe_smartdoor_activity("door-1", observed_records.append)

    with (
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pets",
            AsyncMock(return_value=[{"petId": "pet-1", "profile": {"name": "Milo"}}]),
        ),
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pet_products",
            AsyncMock(return_value=[{"productId": "door-1", "productType": "SmartDoor"}]),
        ),
    ):
        await coordinator.async_refresh()
        assert observed_records == []

        coordinator._smartdoor_activity_last_refresh_by_door["door-1"] = (  # noqa: SLF001
            time.monotonic() - SMARTDOOR_ACTIVITY_REFRESH_INTERVAL.total_seconds()
        )
        await coordinator.async_refresh()

    assert [record.event_type for record in observed_records] == [SMARTDOOR_EVENT_TYPE_PET_EXITED]
    unsubscribe()


@pytest.mark.asyncio
async def test_coordinator_dispatches_multiple_smartdoor_events_in_order(hass, mock_config_entry) -> None:
    """New SmartDoor records from a single poll should all be dispatched in timestamp order."""
    door = _create_smartdoor(api_name="door-1")
    door.data["productId"] = "door-1"
    door.get_activity = AsyncMock(
        side_effect=[
            [],
            [
                _create_activity_item("USER_MODE_CHANGE_SMART", "2026-04-02T08:10:00.000Z"),
                _create_activity_item("PET_EXITED", "2026-04-02T08:11:00.000Z", pet_id="pet-1"),
            ],
        ]
    )
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_feeder_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_litterbox_details = AsyncMock(return_value={})  # noqa: SLF001
    observed_records: list[PetSafeExtendedSmartDoorActivityRecord] = []
    coordinator.async_subscribe_smartdoor_activity("door-1", observed_records.append)

    with (
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pets",
            AsyncMock(return_value=[{"petId": "pet-1", "profile": {"name": "Milo"}}]),
        ),
        patch(
            "custom_components.petsafe_extended.coordinator.pet_links.async_list_pet_products",
            AsyncMock(return_value=[{"productId": "door-1", "productType": "SmartDoor"}]),
        ),
    ):
        await coordinator.async_refresh()
        coordinator._smartdoor_activity_last_refresh_by_door["door-1"] = (  # noqa: SLF001
            time.monotonic() - SMARTDOOR_ACTIVITY_REFRESH_INTERVAL.total_seconds()
        )
        await coordinator.async_refresh()

    assert [record.event_type for record in observed_records] == [
        SMARTDOOR_EVENT_TYPE_MODE_CHANGED,
        SMARTDOOR_EVENT_TYPE_PET_EXITED,
    ]


@pytest.mark.asyncio
async def test_coordinator_pet_links_use_slow_refresh_cache(hass, mock_config_entry) -> None:
    """Pet directory endpoints should not run on every fast coordinator refresh."""
    door = _create_smartdoor(api_name="door-1")
    door.data["productId"] = "door-1"
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_feeder_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_litterbox_details = AsyncMock(return_value={})  # noqa: SLF001

    list_pets = AsyncMock(return_value=[{"petId": "pet-1", "name": "Milo"}])
    list_pet_products = AsyncMock(return_value=[{"productId": "door-1", "productType": "SmartDoor"}])

    with (
        patch("custom_components.petsafe_extended.coordinator.pet_links.async_list_pets", list_pets),
        patch("custom_components.petsafe_extended.coordinator.pet_links.async_list_pet_products", list_pet_products),
    ):
        await coordinator.async_refresh()
        await coordinator.async_refresh()

    assert list_pets.await_count == 1
    assert list_pet_products.await_count == 1


@pytest.mark.asyncio
async def test_sensor_platform_adds_smartdoor_pet_sensors(hass, mock_config_entry, attach_runtime_data) -> None:
    """The sensor platform should create SmartDoor pet sensors plus schedule summary sensors."""
    door = _create_smartdoor(api_name="door-1")
    next_change = dt_util.parse_datetime("2026-04-03T19:30:00+01:00")
    assert next_change is not None
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            links=(
                PetSafeExtendedPetProductLink("pet-1", "door-1", "smartdoor"),
                PetSafeExtendedPetProductLink("pet-2", "door-1", "smartdoor"),
            ),
            pets_by_id={
                "pet-1": PetSafeExtendedPetProfile(
                    pet_id="pet-1",
                    name="Milo",
                    pet_type="cat",
                    gender="male",
                    weight=4.2,
                    weight_unit="kg",
                    technology="MICROCHIP",
                ),
                "pet-2": PetSafeExtendedPetProfile(
                    pet_id="pet-2",
                    pet_type="cat",
                ),
            },
            product_ids_by_pet_id={
                "pet-1": ("door-1",),
                "pet-2": ("door-1",),
            },
            pet_ids_by_product_id={"door-1": ("pet-1", "pet-2")},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_pet_states={
            "door-1": {
                "pet-1": PetSafeExtendedSmartDoorPetState(
                    last_seen=None,
                    last_activity=SMARTDOOR_PET_ACTIVITY_ENTERED,
                    last_activity_at=None,
                    last_activity_code="PET_ENTERED",
                ),
                "pet-2": PetSafeExtendedSmartDoorPetState(
                    last_seen=None,
                    last_activity=SMARTDOOR_PET_ACTIVITY_UNKNOWN,
                    last_activity_at=None,
                    last_activity_code=None,
                ),
            }
        },
        smartdoor_schedule_summaries={
            "door-1": PetSafeExtendedSmartDoorScheduleSummary(
                schedule_rule_count=2,
                enabled_schedule_count=2,
                disabled_schedule_count=0,
                scheduled_pet_count=2,
            )
        },
        smartdoor_schedule_rules={
            "door-1": (
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="pet-1-rule",
                    title="Cats outside",
                    start_time="08:00",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    is_enabled=True,
                    pet_ids=("pet-1",),
                    pet_names=("Milo",),
                    pet_count=1,
                ),
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="pet-2-rule",
                    title="Cats in at night",
                    start_time="19:30",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_NO_ACCESS,
                    is_enabled=True,
                    pet_ids=("pet-2",),
                    pet_names=("Pet 2",),
                    pet_count=1,
                ),
            )
        },
        smartdoor_pet_schedule_states={
            "door-1": {
                "pet-1": PetSafeExtendedSmartDoorPetScheduleState(
                    smart_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    effective_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    active_schedule_title="Cats outside",
                    next_change_at=next_change,
                    next_smart_access=SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
                    next_schedule_title="Cats in at night",
                ),
                "pet-2": PetSafeExtendedSmartDoorPetScheduleState(
                    smart_access=SMARTDOOR_SCHEDULE_ACCESS_NO_ACCESS,
                    effective_access=SMARTDOOR_SCHEDULE_ACCESS_NO_ACCESS,
                    active_schedule_title="Cats in at night",
                    next_change_at=next_change,
                    next_smart_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    next_schedule_title="Cats outside",
                ),
            }
        },
    )

    async_add_entities = MagicMock()
    with (
        patch.object(coordinator, "get_feeders", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_litterboxes", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])),
    ):
        await async_setup_sensor_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]

    assert len(added_entities) == 16
    diagnostic_entities = [
        entity for entity in added_entities if isinstance(entity, PetSafeExtendedSmartDoorDiagnosticSensor)
    ]
    pet_entities = [entity for entity in added_entities if isinstance(entity, PetSafeExtendedSmartDoorPetSensor)]
    schedule_entities = [
        entity for entity in added_entities if isinstance(entity, PetSafeExtendedSmartDoorScheduleSensor)
    ]
    assert len(diagnostic_entities) == 3
    assert len(pet_entities) == 10
    assert len(schedule_entities) == 3
    assert {entity.entity_description.key for entity in diagnostic_entities} == {
        "battery_level",
        "battery_voltage",
        "signal_strength",
    }
    assert {entity.entity_description.key for entity in schedule_entities} == {
        "schedule_rule_count",
        "active_schedule_rule_count",
        "scheduled_pet_count",
    }
    assert all(entity.entity_category is EntityCategory.DIAGNOSTIC for entity in schedule_entities)
    activity_entities = [entity for entity in pet_entities if entity.entity_description.key == "last_activity"]
    access_entities = [entity for entity in pet_entities if entity.entity_description.key == "smart_access"]
    next_access_entities = [entity for entity in pet_entities if entity.entity_description.key == "next_smart_access"]
    activity_names = sorted(entity_name for entity in activity_entities if (entity_name := entity.name) is not None)
    assert activity_names == ["Milo Last Activity", "Pet 2 Last Activity"]
    assert access_entities[0].native_value in SMARTDOOR_SCHEDULE_ACCESS_OPTIONS
    assert next_access_entities[0].native_value in SMARTDOOR_SCHEDULE_ACCESS_OPTIONS
    assert "pet_id" not in access_entities[0].extra_state_attributes
    assert all(entity.device_info is not None for entity in added_entities)
    assert all(entity.device_info["identifiers"] == {("petsafe_extended", "door-1")} for entity in added_entities)
    assert all(entity.translation_key == "last_activity" for entity in activity_entities)
    assert activity_entities[0].extra_state_attributes["technology"] == "MICROCHIP"
    schedule_values = {entity.entity_description.key: entity.native_value for entity in schedule_entities}
    assert schedule_values == {
        "schedule_rule_count": 2,
        "active_schedule_rule_count": 2,
        "scheduled_pet_count": 2,
    }


@pytest.mark.asyncio
async def test_sensor_platform_skips_smartdoor_schedule_entities_when_disabled(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Disabling SmartDoor schedules should leave only the always-on pet sensors."""
    door = _create_smartdoor(api_name="door-1")
    disabled_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**mock_config_entry.data},
        options={CONF_ENABLE_SMARTDOOR_SCHEDULES: False},
        unique_id=mock_config_entry.unique_id,
    )
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), disabled_entry)
    disabled_entry.add_to_hass(hass)
    attach_runtime_data(disabled_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            links=(
                PetSafeExtendedPetProductLink("pet-1", "door-1", "smartdoor"),
                PetSafeExtendedPetProductLink("pet-2", "door-1", "smartdoor"),
            ),
            pets_by_id={
                "pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo"),
                "pet-2": PetSafeExtendedPetProfile(pet_id="pet-2", name="Ruby"),
            },
            product_ids_by_pet_id={"pet-1": ("door-1",), "pet-2": ("door-1",)},
            pet_ids_by_product_id={"door-1": ("pet-1", "pet-2")},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_pet_states={
            "door-1": {
                "pet-1": PetSafeExtendedSmartDoorPetState(
                    last_seen=None,
                    last_activity=SMARTDOOR_PET_ACTIVITY_ENTERED,
                    last_activity_at=None,
                    last_activity_code="PET_ENTERED",
                ),
                "pet-2": PetSafeExtendedSmartDoorPetState(
                    last_seen=None,
                    last_activity=SMARTDOOR_PET_ACTIVITY_UNKNOWN,
                    last_activity_at=None,
                    last_activity_code=None,
                ),
            }
        },
        smartdoor_schedule_summaries={
            "door-1": PetSafeExtendedSmartDoorScheduleSummary(
                schedule_rule_count=2,
                enabled_schedule_count=2,
                disabled_schedule_count=0,
                scheduled_pet_count=2,
            )
        },
        smartdoor_pet_schedule_states={
            "door-1": {
                "pet-1": PetSafeExtendedSmartDoorPetScheduleState(
                    smart_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    effective_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                )
            }
        },
    )

    async_add_entities = MagicMock()
    with (
        patch.object(coordinator, "get_feeders", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_litterboxes", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])),
    ):
        await async_setup_sensor_entry(hass, disabled_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]

    assert len(added_entities) == 7
    diagnostic_entities = [
        entity for entity in added_entities if isinstance(entity, PetSafeExtendedSmartDoorDiagnosticSensor)
    ]
    pet_entities = [entity for entity in added_entities if isinstance(entity, PetSafeExtendedSmartDoorPetSensor)]
    assert len(diagnostic_entities) == 3
    assert len(pet_entities) == 4
    assert {entity.entity_description.key for entity in diagnostic_entities} == {
        "battery_level",
        "battery_voltage",
        "signal_strength",
    }
    assert {entity.entity_description.key for entity in pet_entities} == {"last_seen", "last_activity"}


@pytest.mark.asyncio
async def test_schedule_pet_sensor_availability_uses_scheduled_pet_membership(coordinator) -> None:
    """Schedule-derived pet sensors should go unavailable when the pet is no longer scheduled."""
    door = _create_smartdoor(api_name="door-1")
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_schedule_rules={},
        smartdoor_pet_schedule_states={
            "door-1": {
                "pet-1": PetSafeExtendedSmartDoorPetScheduleState(
                    smart_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    effective_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                )
            }
        },
    )

    schedule_entity = PetSafeExtendedSmartDoorPetSensor(
        coordinator,
        door,
        "pet-1",
        SMARTDOOR_PET_SMART_ACCESS_DESCRIPTION,
    )
    activity_entity = PetSafeExtendedSmartDoorPetSensor(
        coordinator,
        door,
        "pet-1",
        SMARTDOOR_PET_LAST_ACTIVITY_DESCRIPTION,
    )

    assert schedule_entity.available is False
    assert activity_entity.available is True


@pytest.mark.asyncio
async def test_smartdoor_pet_sensor_reports_override_in_attributes(coordinator) -> None:
    """Schedule-derived pet sensors should expose override details without changing schedule state."""
    door = _create_smartdoor(api_name="door-1")
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_schedule_rules={
            "door-1": (
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="cats-out",
                    title="Cats outside",
                    start_time="08:00",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
                    is_enabled=True,
                    pet_ids=("pet-1",),
                    pet_names=("Milo",),
                    pet_count=1,
                    timezone="Europe/London",
                ),
            )
        },
        smartdoor_pet_schedule_states={
            "door-1": {
                "pet-1": PetSafeExtendedSmartDoorPetScheduleState(
                    smart_access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
                    effective_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    override_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    control_source=SMARTDOOR_CONTROL_SOURCE_SMART_OVERRIDE,
                    active_schedule_title="Cats outside",
                )
            }
        },
    )

    entity = PetSafeExtendedSmartDoorPetSensor(
        coordinator,
        door,
        "pet-1",
        SMARTDOOR_PET_SMART_ACCESS_DESCRIPTION,
    )

    assert entity.native_value == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY
    assert entity.extra_state_attributes["effective_access"] == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert entity.extra_state_attributes["override_access"] == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert entity.extra_state_attributes["control_source"] == SMARTDOOR_CONTROL_SOURCE_SMART_OVERRIDE


@pytest.mark.asyncio
async def test_sensor_platform_updates_existing_diagnostic_entity_categories(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Existing SmartDoor diagnostic sensors should migrate into the diagnostic section."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    entity_reg = er.async_get(hass)
    existing_entry = entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_battery_level",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_battery_level",
    )
    assert existing_entry.entity_category is None

    async_add_entities = MagicMock()
    with (
        patch.object(coordinator, "get_feeders", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_litterboxes", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])),
    ):
        await async_setup_sensor_entry(hass, mock_config_entry, async_add_entities)

    updated_entry = entity_reg.async_get(existing_entry.entity_id)
    assert updated_entry is not None
    assert updated_entry.entity_category is EntityCategory.DIAGNOSTIC


@pytest.mark.asyncio
async def test_calendar_platform_adds_smartdoor_schedule_calendar(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """The calendar platform should add one per-pet schedule calendar for each scheduled pet."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            links=(PetSafeExtendedPetProductLink("pet-1", "door-1", "smartdoor"),),
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_schedule_rules={
            "door-1": (
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="milo-out",
                    title="Milo out",
                    start_time="08:00",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
                    is_enabled=True,
                    pet_ids=("pet-1",),
                    pet_names=("Milo",),
                    pet_count=1,
                    timezone="Europe/London",
                ),
            )
        },
    )

    async_add_entities = MagicMock()
    with patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])):
        await async_setup_calendar_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]

    assert len(added_entities) == 1
    assert isinstance(added_entities[0], PetSafeExtendedSmartDoorScheduleCalendar)
    assert added_entities[0].entity_category is EntityCategory.DIAGNOSTIC
    assert added_entities[0].device_info is not None
    assert added_entities[0].device_info["identifiers"] == {("petsafe_extended", "door-1")}
    assert added_entities[0].name == "Milo Schedule"


@pytest.mark.asyncio
async def test_calendar_platform_skips_smartdoor_schedule_calendar_when_disabled(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Disabling SmartDoor schedules should suppress the calendar platform entirely."""
    door = _create_smartdoor(api_name="door-1")
    disabled_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**mock_config_entry.data},
        options={CONF_ENABLE_SMARTDOOR_SCHEDULES: False},
        unique_id=mock_config_entry.unique_id,
    )
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), disabled_entry)
    disabled_entry.add_to_hass(hass)
    attach_runtime_data(disabled_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    async_add_entities = MagicMock()
    with patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])):
        await async_setup_calendar_entry(hass, disabled_entry, async_add_entities)

    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_button_platform_adds_schedule_refresh_buttons(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """The button platform should expose feeder and SmartDoor schedule refresh actions."""
    feeder = _create_feeder(api_name="feeder-1")
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(feeders=[feeder], smartdoors=[door])

    async_add_entities = MagicMock()
    with (
        patch.object(coordinator, "get_feeders", AsyncMock(return_value=[feeder])),
        patch.object(coordinator, "get_litterboxes", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])),
    ):
        await async_setup_button_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]
    assert any(isinstance(entity, PetSafeExtendedFeederRefreshButton) for entity in added_entities)
    smartdoor_refresh_entities = [
        entity for entity in added_entities if isinstance(entity, PetSafeExtendedSmartDoorRefreshButton)
    ]
    assert len(smartdoor_refresh_entities) == 2
    assert {entity.entity_description.key for entity in smartdoor_refresh_entities} == {
        "refresh_pet_data",
        "refresh_schedule_data",
    }


@pytest.mark.asyncio
async def test_button_platform_skips_smartdoor_schedule_refresh_button_when_disabled(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Disabling SmartDoor schedules should suppress the SmartDoor refresh button only."""
    feeder = _create_feeder(api_name="feeder-1")
    door = _create_smartdoor(api_name="door-1")
    disabled_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**mock_config_entry.data},
        options={CONF_ENABLE_SMARTDOOR_SCHEDULES: False},
        unique_id=mock_config_entry.unique_id,
    )
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), disabled_entry)
    disabled_entry.add_to_hass(hass)
    attach_runtime_data(disabled_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(feeders=[feeder], smartdoors=[door])

    async_add_entities = MagicMock()
    with (
        patch.object(coordinator, "get_feeders", AsyncMock(return_value=[feeder])),
        patch.object(coordinator, "get_litterboxes", AsyncMock(return_value=[])),
    ):
        await async_setup_button_entry(hass, disabled_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]
    assert any(isinstance(entity, PetSafeExtendedFeederRefreshButton) for entity in added_entities)
    smartdoor_refresh_entities = [
        entity for entity in added_entities if isinstance(entity, PetSafeExtendedSmartDoorRefreshButton)
    ]
    assert len(smartdoor_refresh_entities) == 1
    assert smartdoor_refresh_entities[0].entity_description.key == "refresh_pet_data"


@pytest.mark.asyncio
async def test_smartdoor_pet_refresh_button_reloads_pet_entities(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Refreshing pet data should prune stale pet entities before reloading the entry."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
    )

    async def _refresh_pet_links() -> None:
        coordinator.data = PetSafeExtendedCoordinatorData(
            smartdoors=[door],
            pet_links=PetSafeExtendedPetLinkData(
                pet_ids_by_product_id={"door-1": ("pet-2",)},
                product_ids_by_pet_id={"pet-2": ("door-1",)},
                pets_by_id={"pet-2": PetSafeExtendedPetProfile(pet_id="pet-2", name="Ruby")},
                product_type_by_product_id={"door-1": "smartdoor"},
            ),
        )

    coordinator.async_refresh_pet_links = AsyncMock(side_effect=_refresh_pet_links)
    pet_button_description = next(
        description for description in SMARTDOOR_REFRESH_BUTTON_DESCRIPTIONS if description.key == "refresh_pet_data"
    )
    entity = PetSafeExtendedSmartDoorRefreshButton(coordinator, door, pet_button_description)
    entity.hass = hass

    entity_reg = er.async_get(hass)
    last_activity_entry = entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_pet-1_last_activity",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_milo_last_activity",
    )
    schedule_entry = entity_reg.async_get_or_create(
        "calendar",
        DOMAIN,
        "door-1_pet-1_schedule",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_milo_schedule",
    )

    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)) as mock_reload:
        await entity.async_press()

    coordinator.async_refresh_pet_links.assert_awaited_once()
    mock_reload.assert_awaited_once_with(mock_config_entry.entry_id)
    assert entity_reg.async_get(last_activity_entry.entity_id) is None
    assert entity_reg.async_get(schedule_entry.entity_id) is None


@pytest.mark.asyncio
async def test_smartdoor_schedule_refresh_button_reloads_schedule_entities(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Refreshing schedule data should prune stale schedule entities before reloading the entry."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            pet_ids_by_product_id={"door-1": ("pet-1", "pet-2")},
            product_ids_by_pet_id={"pet-1": ("door-1",), "pet-2": ("door-1",)},
            pets_by_id={
                "pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo"),
                "pet-2": PetSafeExtendedPetProfile(pet_id="pet-2", name="Ruby"),
            },
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_schedule_rules={
            "door-1": (
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="milo-only",
                    title="Milo only",
                    start_time="08:00",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    is_enabled=True,
                    pet_ids=("pet-1",),
                    pet_names=("Milo",),
                    pet_count=1,
                ),
            )
        },
    )

    async def _refresh_schedule_data(_: str) -> None:
        coordinator.data = PetSafeExtendedCoordinatorData(
            smartdoors=[door],
            pet_links=coordinator.data.pet_links,
            smartdoor_schedule_rules={
                "door-1": (
                    PetSafeExtendedSmartDoorScheduleRule(
                        schedule_id="ruby-only",
                        title="Ruby only",
                        start_time="09:00",
                        day_of_week="1111111",
                        access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                        is_enabled=True,
                        pet_ids=("pet-2",),
                        pet_names=("Ruby",),
                        pet_count=1,
                    ),
                )
            },
        )

    coordinator.async_refresh_smartdoor_schedule_data = AsyncMock(side_effect=_refresh_schedule_data)
    schedule_button_description = next(
        description
        for description in SMARTDOOR_REFRESH_BUTTON_DESCRIPTIONS
        if description.key == "refresh_schedule_data"
    )
    entity = PetSafeExtendedSmartDoorRefreshButton(coordinator, door, schedule_button_description)
    entity.hass = hass

    entity_reg = er.async_get(hass)
    old_schedule_entry = entity_reg.async_get_or_create(
        "calendar",
        DOMAIN,
        "door-1_pet-1_schedule",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_milo_schedule",
    )
    old_access_entry = entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_pet-1_smart_access",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_milo_smart_access",
    )
    old_activity_entry = entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_pet-1_last_activity",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_milo_last_activity",
    )

    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)) as mock_reload:
        await entity.async_press()

    coordinator.async_refresh_smartdoor_schedule_data.assert_awaited_once_with("door-1")
    mock_reload.assert_awaited_once_with(mock_config_entry.entry_id)
    assert entity_reg.async_get(old_schedule_entry.entity_id) is None
    assert entity_reg.async_get(old_access_entry.entity_id) is None
    assert entity_reg.async_get(old_activity_entry.entity_id) is not None


@pytest.mark.asyncio
async def test_smartdoor_schedule_calendar_exposes_upcoming_events(coordinator, hass) -> None:
    """The per-pet SmartDoor schedule calendar should expose effective schedule intervals."""
    await hass.config.async_set_time_zone("Europe/London")
    door = _create_smartdoor(api_name="door-1")
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            links=(PetSafeExtendedPetProductLink("pet-1", "door-1", "smartdoor"),),
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_schedule_rules={
            "door-1": (
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="cats-out",
                    title="Cats outside",
                    start_time="08:00",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    is_enabled=True,
                    pet_ids=("pet-1",),
                    pet_names=("Milo",),
                    pet_count=1,
                    timezone="Europe/London",
                ),
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="cats-in",
                    title="Cats in at night",
                    start_time="19:30",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
                    is_enabled=True,
                    pet_ids=("pet-1",),
                    pet_names=("Milo",),
                    pet_count=1,
                    timezone="Europe/London",
                ),
            )
        },
    )
    entity = PetSafeExtendedSmartDoorScheduleCalendar(coordinator, door, "pet-1")
    entity.hass = hass

    fixed_now = dt_util.parse_datetime("2026-04-03T07:00:00+01:00")
    assert fixed_now is not None

    with patch(
        "custom_components.petsafe_extended.calendar.smartdoor_schedule.dt_util.now",
        return_value=fixed_now,
    ):
        next_event = entity.event
        assert next_event is not None
        assert next_event.summary == "In only · Cats in at night"
        assert next_event.description == "Access: In only\nSource: Cats in at night"
        assert next_event.start.isoformat() == "2026-04-02T19:30:00+01:00"
        assert next_event.end.isoformat() == "2026-04-03T08:00:00+01:00"

        start = dt_util.parse_datetime("2026-04-03T00:00:00+01:00")
        end = dt_util.parse_datetime("2026-04-04T00:00:00+01:00")
        assert start is not None
        assert end is not None
        events = await entity.async_get_events(
            hass,
            start,
            end,
        )

    assert len(events) == 3
    assert [event.summary for event in events] == [
        "In only · Cats in at night",
        "Full access · Cats outside",
        "In only · Cats in at night",
    ]
    assert events[0].start.isoformat() == "2026-04-03T00:00:00+01:00"
    assert events[0].end.isoformat() == "2026-04-03T08:00:00+01:00"
    assert events[1].start.isoformat() == "2026-04-03T08:00:00+01:00"
    assert events[1].end.isoformat() == "2026-04-03T19:30:00+01:00"
    assert events[2].start.isoformat() == "2026-04-03T19:30:00+01:00"
    assert events[2].end.isoformat() == "2026-04-04T00:00:00+01:00"


@pytest.mark.asyncio
async def test_sensor_platform_dynamically_adds_new_pet_entities(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Background pet-link refreshes should add new pet sensors without reloading the entry."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    async_add_entities = MagicMock()
    with (
        patch.object(coordinator, "get_feeders", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_litterboxes", AsyncMock(return_value=[])),
        patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])),
    ):
        await async_setup_sensor_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 1
    async_add_entities.reset_mock()

    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_pet_states={
            "door-1": {
                "pet-1": PetSafeExtendedSmartDoorPetState(
                    last_activity=SMARTDOOR_PET_ACTIVITY_UNKNOWN,
                )
            }
        },
    )

    coordinator.async_update_listeners()

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]
    assert {entity.unique_id for entity in added_entities} == {
        "door-1_pet-1_last_seen",
        "door-1_pet-1_last_activity",
    }


@pytest.mark.asyncio
async def test_calendar_platform_dynamically_adds_new_scheduled_pet_entities(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Background schedule refreshes should add new pet calendars without reloading the entry."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    async_add_entities = MagicMock()
    with patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])):
        await async_setup_calendar_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_not_called()

    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
        smartdoor_schedule_rules={
            "door-1": (
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="pet-1-rule",
                    title="Cats outside",
                    start_time="08:00",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
                    is_enabled=True,
                    pet_ids=("pet-1",),
                    pet_names=("Milo",),
                    pet_count=1,
                ),
            )
        },
    )

    coordinator.async_update_listeners()

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]
    assert len(added_entities) == 1
    assert isinstance(added_entities[0], PetSafeExtendedSmartDoorScheduleCalendar)
    assert added_entities[0].unique_id == "door-1_pet-1_schedule"


@pytest.mark.asyncio
async def test_event_platform_dynamically_adds_new_pet_entities(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Background pet-link refreshes should add per-pet activity events without reloading the entry."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    async_add_entities = MagicMock()
    with patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])):
        await async_setup_event_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 1
    door_entities = async_add_entities.call_args[0][0]
    assert len(door_entities) == 1
    assert isinstance(door_entities[0], PetSafeExtendedSmartDoorActivityEvent)
    async_add_entities.reset_mock()

    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
    )

    coordinator.async_update_listeners()

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]
    assert len(added_entities) == 1
    assert isinstance(added_entities[0], PetSafeExtendedSmartDoorActivityEvent)
    assert added_entities[0].unique_id == "door-1_pet-1_activity"


def test_smartdoor_schedule_intervals_and_description() -> None:
    """SmartDoor schedules should expand into per-pet intervals with access labels."""
    rules = (
        PetSafeExtendedSmartDoorScheduleRule(
            schedule_id="cats-out",
            title="Cats outside",
            start_time="08:00",
            day_of_week="1111111",
            access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
            is_enabled=True,
            pet_ids=("pet-1", "pet-2"),
            pet_names=("Frank", "Milo"),
            pet_count=2,
            timezone="Europe/London",
        ),
        PetSafeExtendedSmartDoorScheduleRule(
            schedule_id="cats-in",
            title="Cats in at night",
            start_time="19:30",
            day_of_week="1111111",
            access=SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
            is_enabled=True,
            pet_ids=("pet-1", "pet-2"),
            pet_names=("Frank", "Milo"),
            pet_count=2,
            timezone="Europe/London",
        ),
    )

    start = dt_util.parse_datetime("2026-04-03T00:00:00+01:00")
    end = dt_util.parse_datetime("2026-04-04T00:00:00+01:00")
    assert start is not None
    assert end is not None
    assert start.tzinfo is not None

    intervals = expand_smartdoor_pet_schedule_intervals(
        rules,
        start=start,
        end=end,
        default_timezone=start.tzinfo,
        pet_id="pet-1",
    )

    assert len(intervals) == 3
    assert intervals[0].title == "Cats in at night"
    assert intervals[0].start.isoformat() == "2026-04-03T00:00:00+01:00"
    assert intervals[0].end is not None
    assert intervals[0].end.isoformat() == "2026-04-03T08:00:00+01:00"
    assert intervals[1].title == "Cats outside"
    assert describe_smartdoor_schedule_interval(intervals[1]) == "Access: Out only\nSource: Cats outside"


def test_smartdoor_schedule_projection_keeps_pet_timelines_independent() -> None:
    """A pet's schedule should not be truncated by unrelated pets' schedules."""
    now = dt_util.parse_datetime("2026-04-03T10:00:00+01:00")
    assert now is not None
    assert now.tzinfo is not None

    rules = (
        PetSafeExtendedSmartDoorScheduleRule(
            schedule_id="dogs-open",
            title="Dogs in and out",
            start_time="00:00",
            day_of_week="1111111",
            access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
            is_enabled=True,
            pet_ids=("dog-1", "dog-2"),
            pet_names=("Frank", "Ruby"),
            pet_count=2,
            timezone="Europe/London",
        ),
        PetSafeExtendedSmartDoorScheduleRule(
            schedule_id="cats-out",
            title="Cats outside",
            start_time="08:00",
            day_of_week="1111111",
            access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
            is_enabled=True,
            pet_ids=("cat-1", "cat-2", "cat-3"),
            pet_names=("Clover", "Livvy", "Tilly"),
            pet_count=3,
            timezone="Europe/London",
        ),
        PetSafeExtendedSmartDoorScheduleRule(
            schedule_id="livvy-in",
            title="Livvy in at 10pm",
            start_time="22:00",
            day_of_week="1111111",
            access=SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
            is_enabled=True,
            pet_ids=("cat-2",),
            pet_names=("Livvy",),
            pet_count=1,
            timezone="Europe/London",
        ),
    )

    dog_intervals = expand_smartdoor_pet_schedule_intervals(
        rules,
        start=now.replace(hour=0, minute=0),
        end=now.replace(hour=0, minute=0) + timedelta(days=1),
        default_timezone=now.tzinfo,
        pet_id="dog-1",
    )
    assert [interval.title for interval in dog_intervals] == ["Dogs in and out"]
    assert dog_intervals[0].start.isoformat() == "2026-04-03T00:00:00+01:00"
    assert dog_intervals[0].end is not None
    assert dog_intervals[0].end.isoformat() == "2026-04-04T00:00:00+01:00"

    pet_states = build_smartdoor_pet_schedule_states(
        rules,
        ("dog-1", "cat-2"),
        door_mode=SMARTDOOR_MODE_SMART,
        override_access=None,
        now=now,
        default_timezone=now.tzinfo,
    )
    assert pet_states["dog-1"].smart_access == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert pet_states["cat-2"].smart_access == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY
    assert pet_states["cat-2"].next_smart_access == SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY


def test_build_smartdoor_pet_schedule_states_applies_override() -> None:
    """Active SmartDoor overrides should replace effective access while preserving schedule state."""
    now = dt_util.parse_datetime("2026-04-06T09:00:00+01:00")
    assert now is not None
    assert now.tzinfo is not None
    rule = PetSafeExtendedSmartDoorScheduleRule(
        schedule_id="cats-out",
        title="Cats outside",
        start_time="08:00",
        day_of_week="1111111",
        access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
        is_enabled=True,
        pet_ids=("cat-1",),
        pet_names=("Milo",),
        pet_count=1,
        timezone="Europe/London",
    )

    pet_states = build_smartdoor_pet_schedule_states(
        (rule,),
        ("cat-1",),
        door_mode=SMARTDOOR_MODE_SMART,
        override_access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
        now=now,
        default_timezone=now.tzinfo,
    )

    assert pet_states["cat-1"].smart_access == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY
    assert pet_states["cat-1"].effective_access == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert pet_states["cat-1"].override_access == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert pet_states["cat-1"].control_source == SMARTDOOR_CONTROL_SOURCE_SMART_OVERRIDE
    assert pet_states["cat-1"].next_smart_access == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY
    assert pet_states["cat-1"].next_schedule_title == "Cats outside"
    assert pet_states["cat-1"].next_change_at == dt_util.parse_datetime("2026-04-07T08:00:00+01:00")


def test_build_smartdoor_schedule_summary_tracks_next_single_rule_trigger() -> None:
    """Single repeating schedules should still expose the next trigger in the summary view."""
    now = dt_util.parse_datetime("2026-04-06T09:00:00+01:00")
    assert now is not None
    assert now.tzinfo is not None
    rule = PetSafeExtendedSmartDoorScheduleRule(
        schedule_id="dogs-all-day",
        title="Dogs in and out",
        start_time="08:00",
        day_of_week="1111111",
        access=SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS,
        is_enabled=True,
        pet_ids=("dog-1",),
        pet_names=("Frank",),
        pet_count=1,
        timezone="Europe/London",
    )

    summary = build_smartdoor_schedule_summary(
        (rule,),
        ("dog-1",),
        now=now,
        default_timezone=now.tzinfo,
    )

    assert summary.schedule_rule_count == 1
    assert summary.enabled_schedule_count == 1
    assert summary.scheduled_pet_count == 1
    assert summary.next_schedule_change_at == dt_util.parse_datetime("2026-04-07T08:00:00+01:00")
    assert summary.next_schedule_title == "Dogs in and out"
    assert summary.next_schedule_access == SMARTDOOR_SCHEDULE_ACCESS_FULL_ACCESS
    assert summary.next_schedule_pet_name == "Frank"


@pytest.mark.asyncio
async def test_coordinator_builds_smartdoor_schedule_summary(hass, mock_config_entry) -> None:
    """Coordinator refresh should cache per-pet SmartDoor schedules and access state."""
    door = _create_smartdoor(api_name="door-1")
    door.get_schedules = AsyncMock(
        return_value=[
            _create_schedule(
                title="Cats outside",
                start_time="08:00",
                access=1,
                pet_ids=["pet-1", "pet-2"],
            ),
            _create_schedule(
                title="Cats in at night",
                start_time="19:30",
                access=2,
                pet_ids=["pet-1", "pet-2"],
            ),
            _create_schedule(
                title="Disabled schedule",
                start_time="12:00",
                access=0,
                pet_ids=["pet-1"],
                is_enabled=False,
            ),
        ]
    )
    door.get_preferences = AsyncMock(return_value={"tz": "Europe/London"})

    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_feeder_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_litterbox_details = AsyncMock(return_value={})  # noqa: SLF001
    coordinator._async_build_pet_links = AsyncMock(  # noqa: SLF001
        return_value=PetSafeExtendedPetLinkData(
            links=(
                PetSafeExtendedPetProductLink("pet-1", "door-1", "smartdoor"),
                PetSafeExtendedPetProductLink("pet-2", "door-1", "smartdoor"),
            ),
            pets_by_id={
                "pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo"),
                "pet-2": PetSafeExtendedPetProfile(pet_id="pet-2", name="Frank"),
            },
            product_ids_by_pet_id={"pet-1": ("door-1",), "pet-2": ("door-1",)},
            pet_ids_by_product_id={"door-1": ("pet-1", "pet-2")},
            product_type_by_product_id={"door-1": "smartdoor"},
        )
    )
    coordinator._async_build_smartdoor_pet_states = AsyncMock(return_value=({}, {}, {}))  # noqa: SLF001

    fixed_now = dt_util.parse_datetime("2026-04-03T07:00:00+01:00")
    assert fixed_now is not None

    with patch("custom_components.petsafe_extended.coordinator.base.dt_util.now", return_value=fixed_now):
        await coordinator.async_refresh()

    rules = coordinator.get_smartdoor_schedule_rules("door-1")
    summary = coordinator.get_smartdoor_schedule_summary("door-1")
    pet_schedule_state = coordinator.get_smartdoor_pet_schedule_state("door-1", "pet-1")

    assert rules is not None
    assert summary is not None
    assert pet_schedule_state is not None
    assert len(rules) == 3
    assert rules[0].pet_names == ("Milo", "Frank")
    assert rules[0].access == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY
    assert rules[0].schedule_id == "cats-outside-id"
    assert coordinator.get_smartdoor_scheduled_pet_ids("door-1") == ("pet-1", "pet-2")
    assert summary.schedule_rule_count == 3
    assert summary.enabled_schedule_count == 2
    assert summary.disabled_schedule_count == 1
    assert summary.scheduled_pet_count == 2
    assert summary.next_schedule_title == "Cats outside"
    assert summary.next_schedule_access == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY
    assert summary.next_schedule_pet_name == "Milo"
    assert pet_schedule_state.smart_access == SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY
    assert pet_schedule_state.next_smart_access == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY


@pytest.mark.asyncio
async def test_coordinator_preserves_smartdoor_schedule_summary_on_refresh_failure(hass, mock_config_entry) -> None:
    """Schedule refresh failures should preserve the previous SmartDoor schedule cache."""
    door = _create_smartdoor(api_name="door-1")
    door.get_schedules = AsyncMock(side_effect=RuntimeError("boom"))
    door.get_preferences = AsyncMock(return_value={"tz": "Europe/London"})
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    previous_rule = PetSafeExtendedSmartDoorScheduleRule(
        schedule_id="cats-out",
        title="Cats outside",
        start_time="08:00",
        day_of_week="1111111",
        access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
        is_enabled=True,
        pet_ids=("pet-1",),
        pet_names=("Milo",),
        pet_count=1,
        timezone="Europe/London",
    )
    previous_summary = PetSafeExtendedSmartDoorScheduleSummary(
        schedule_rule_count=1,
        enabled_schedule_count=1,
        disabled_schedule_count=0,
        scheduled_pet_count=1,
        next_schedule_title="Cats outside",
        next_schedule_pet_name="Milo",
    )
    previous_pet_schedule_state = PetSafeExtendedSmartDoorPetScheduleState(
        smart_access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
        effective_access=SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY,
    )
    coordinator._smartdoor_schedule_rules = {"door-1": (previous_rule,)}  # noqa: SLF001
    coordinator._smartdoor_schedule_summaries = {"door-1": previous_summary}  # noqa: SLF001
    coordinator._smartdoor_pet_schedule_states = {"door-1": {"pet-1": previous_pet_schedule_state}}  # noqa: SLF001

    pet_links = PetSafeExtendedPetLinkData(
        pet_ids_by_product_id={"door-1": ("pet-1",)},
    )
    fixed_now = dt_util.parse_datetime("2026-04-03T07:00:00+01:00")
    assert fixed_now is not None

    with patch("custom_components.petsafe_extended.coordinator.base.dt_util.now", return_value=fixed_now):
        rules = await coordinator._async_build_smartdoor_schedule_data(  # noqa: SLF001
            [door],
            pet_links,
            0.0,
        )
        coordinator._smartdoor_schedule_rules = rules  # noqa: SLF001
        summaries, pet_states = coordinator._rebuild_smartdoor_schedule_views(  # noqa: SLF001
            [door],
            pet_links,
            rules,
        )

    assert rules["door-1"] == (previous_rule,)
    assert summaries["door-1"].schedule_rule_count == 1
    assert summaries["door-1"].scheduled_pet_count == 1
    assert pet_states["door-1"]["pet-1"].smart_access == SMARTDOOR_SCHEDULE_ACCESS_OUT_ONLY


@pytest.mark.asyncio
async def test_event_platform_adds_smartdoor_activity_entities(hass, mock_config_entry, attach_runtime_data) -> None:
    """The event platform should create one door event and one per-pet event for each linked pet."""
    door = _create_smartdoor(api_name="door-1")
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            links=(
                PetSafeExtendedPetProductLink("pet-1", "door-1", "smartdoor"),
                PetSafeExtendedPetProductLink("pet-2", "door-1", "smartdoor"),
            ),
            pets_by_id={
                "pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo"),
                "pet-2": PetSafeExtendedPetProfile(pet_id="pet-2"),
            },
            product_ids_by_pet_id={"pet-1": ("door-1",), "pet-2": ("door-1",)},
            pet_ids_by_product_id={"door-1": ("pet-1", "pet-2")},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
    )

    async_add_entities = MagicMock()
    with patch.object(coordinator, "get_smartdoors", AsyncMock(return_value=[door])):
        await async_setup_event_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]

    assert len(added_entities) == 3
    assert all(isinstance(entity, PetSafeExtendedSmartDoorActivityEvent) for entity in added_entities)
    assert sorted(entity.name for entity in added_entities) == ["Activity", "Milo Activity", "Pet 2 Activity"]
    assert all(entity.device_info is not None for entity in added_entities)
    assert all(entity.device_info["identifiers"] == {("petsafe_extended", "door-1")} for entity in added_entities)
    assert all(entity.event_types == SMARTDOOR_ACTIVITY_EVENT_TYPES for entity in added_entities)
    assert all(entity.translation_key == "activity" for entity in added_entities)


@pytest.mark.asyncio
async def test_smartdoor_event_entities_filter_records_by_pet(coordinator) -> None:
    """Door-wide events should receive all records while pet events only receive matching pet records."""
    door = _create_smartdoor(api_name="door-1")
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[door],
        pet_links=PetSafeExtendedPetLinkData(
            links=(PetSafeExtendedPetProductLink("pet-1", "door-1", "smartdoor"),),
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
            product_ids_by_pet_id={"pet-1": ("door-1",)},
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            product_type_by_product_id={"door-1": "smartdoor"},
        ),
    )

    door_entity = PetSafeExtendedSmartDoorActivityEvent(coordinator, door)
    pet_entity = PetSafeExtendedSmartDoorActivityEvent(coordinator, door, "pet-1")
    other_pet_entity = PetSafeExtendedSmartDoorActivityEvent(coordinator, door, "pet-2")
    for entity_id, entity in (
        ("event.pet_door_activity", door_entity),
        ("event.pet_door_milo_activity", pet_entity),
        ("event.pet_door_pet_2_activity", other_pet_entity),
    ):
        entity.entity_id = entity_id
        entity.async_write_ha_state = MagicMock()

    pet_exit_record = _create_activity_record(
        timestamp="2026-04-02T17:46:27.624Z",
        code="PET_EXITED",
        event_type=SMARTDOOR_EVENT_TYPE_PET_EXITED,
        activity=SMARTDOOR_PET_ACTIVITY_EXITED,
        pet_id="pet-1",
    )
    mode_change_record = _create_activity_record(
        timestamp="2026-04-02T17:46:09.269Z",
        code="USER_MODE_CHANGE_SMART",
        event_type=SMARTDOOR_EVENT_TYPE_MODE_CHANGED,
        activity=SMARTDOOR_PET_ACTIVITY_UNKNOWN,
        pet_id=None,
    )

    door_entity._async_handle_activity(mode_change_record)  # noqa: SLF001
    assert door_entity.state is not None
    assert door_entity.state_attributes["event_type"] == SMARTDOOR_EVENT_TYPE_MODE_CHANGED
    assert door_entity.state_attributes["raw_code"] == "USER_MODE_CHANGE_SMART"
    assert door_entity.state_attributes["event_subtype"] == "user_mode_change_smart"
    door_entity._async_handle_activity(pet_exit_record)  # noqa: SLF001
    pet_entity._async_handle_activity(mode_change_record)  # noqa: SLF001
    pet_entity._async_handle_activity(pet_exit_record)  # noqa: SLF001
    other_pet_entity._async_handle_activity(pet_exit_record)  # noqa: SLF001

    assert door_entity.state is not None
    assert door_entity.state_attributes["event_type"] == SMARTDOOR_EVENT_TYPE_PET_EXITED
    assert door_entity.state_attributes["raw_code"] == "PET_EXITED"
    assert door_entity.state_attributes["pet_name"] == "Milo"
    assert "event_subtype" not in door_entity.state_attributes
    assert pet_entity.state is not None
    assert pet_entity.state_attributes["event_type"] == SMARTDOOR_EVENT_TYPE_PET_EXITED
    assert pet_entity.state_attributes["raw_code"] == "PET_EXITED"
    assert pet_entity.state_attributes["pet_name"] == "Milo"
    assert other_pet_entity.state is None
    cast(MagicMock, other_pet_entity.async_write_ha_state).assert_not_called()


@pytest.mark.asyncio
async def test_diagnostics_do_not_expose_pet_link_identifiers(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """Diagnostics should summarize pet links without leaking raw identifiers."""
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)
    coordinator.data = PetSafeExtendedCoordinatorData(
        smartdoors=[_create_smartdoor(api_name="door-private")],
        pet_links=PetSafeExtendedPetLinkData(
            links=(
                PetSafeExtendedPetProductLink(
                    pet_id="pet-private",
                    product_id="door-private",
                    product_type="smartdoor",
                ),
            ),
            pets_by_id={
                "pet-private": PetSafeExtendedPetProfile(
                    pet_id="pet-private",
                    name="Milo",
                    pet_type="cat",
                    technology="microchip",
                )
            },
            product_ids_by_pet_id={"pet-private": ("door-private",)},
            pet_ids_by_product_id={"door-private": ("pet-private",)},
            product_type_by_product_id={"door-private": "smartdoor"},
        ),
        smartdoor_schedule_rules={
            "door-private": (
                PetSafeExtendedSmartDoorScheduleRule(
                    schedule_id="cats-night",
                    title="Cats in at night",
                    start_time="19:30",
                    day_of_week="1111111",
                    access=SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
                    is_enabled=True,
                    pet_ids=("pet-private",),
                    pet_names=("Milo",),
                    pet_count=1,
                    timezone="Europe/London",
                ),
            )
        },
        smartdoor_schedule_summaries={
            "door-private": PetSafeExtendedSmartDoorScheduleSummary(
                schedule_rule_count=1,
                enabled_schedule_count=1,
                disabled_schedule_count=0,
                scheduled_pet_count=1,
                next_schedule_title="Cats in at night",
                next_schedule_pet_name="Milo",
            )
        },
        smartdoor_pet_schedule_states={
            "door-private": {
                "pet-private": PetSafeExtendedSmartDoorPetScheduleState(
                    smart_access=SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
                    effective_access=SMARTDOOR_SCHEDULE_ACCESS_IN_ONLY,
                )
            }
        },
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    serialized = json.dumps(diagnostics)

    assert diagnostics["data_summary"]["pet_profiles"] == 1
    assert diagnostics["data_summary"]["pet_product_links"] == 1
    assert diagnostics["data_summary"]["linked_products"] == 1
    assert diagnostics["data_summary"]["smartdoor_schedule_doors"] == 1
    assert diagnostics["data_summary"]["smartdoor_schedule_rules"] == 1
    assert diagnostics["data_summary"]["smartdoor_scheduled_pets"] == 1
    assert diagnostics["data_summary"]["smartdoor_schedule_summaries"] == 1
    assert diagnostics["data_summary"]["smartdoor_pet_schedule_states"] == 1
    assert "pet-private" not in serialized
    assert "door-private" not in serialized


@pytest.mark.asyncio
async def test_entry_platforms_include_sensor_for_smartdoor_only(mock_config_entry) -> None:
    """SmartDoor-only entries should now load sensor, binary sensor, calendar, button, select, event, and lock."""
    smartdoor_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **mock_config_entry.data,
            "feeders": [],
            "litterboxes": [],
            "smartdoors": ["door-1"],
        },
        unique_id=mock_config_entry.unique_id,
    )

    platforms = integration_module._get_entry_platforms(smartdoor_entry)  # noqa: SLF001

    assert platforms == [
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.CALENDAR,
        Platform.BUTTON,
        Platform.SELECT,
        Platform.EVENT,
        Platform.LOCK,
    ]


def test_entry_platforms_skip_calendar_when_schedules_disabled(mock_config_entry) -> None:
    """Disabling SmartDoor schedules should remove the calendar platform only."""
    smartdoor_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **mock_config_entry.data,
            "feeders": [],
            "litterboxes": [],
            "smartdoors": ["door-1"],
        },
        options={CONF_ENABLE_SMARTDOOR_SCHEDULES: False},
        unique_id=mock_config_entry.unique_id,
    )

    platforms = integration_module._get_entry_platforms(smartdoor_entry)  # noqa: SLF001

    assert platforms == [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.EVENT, Platform.LOCK]


def test_remove_schedule_entities_removes_only_schedule_registry_entries(hass, mock_config_entry) -> None:
    """Turning schedules off should remove only the schedule-derived entities from the registry."""
    mock_config_entry.add_to_hass(hass)
    entity_reg = er.async_get(hass)

    schedule_entry = entity_reg.async_get_or_create(
        "calendar",
        DOMAIN,
        "door-1_pet-1_schedule",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_milo_schedule",
    )
    schedule_sensor_entry = entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_schedule_rule_count",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_schedule_rule_count",
    )
    refresh_button_entry = entity_reg.async_get_or_create(
        "button",
        DOMAIN,
        "door-1_refresh_schedule_data",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_refresh_schedule_data",
    )
    activity_entry = entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_pet-1_last_activity",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_milo_last_activity",
    )

    integration_module._async_remove_schedule_entities(hass, mock_config_entry)  # noqa: SLF001

    assert entity_reg.async_get(schedule_entry.entity_id) is None
    assert entity_reg.async_get(schedule_sensor_entry.entity_id) is None
    assert entity_reg.async_get(refresh_button_entry.entity_id) is None
    assert entity_reg.async_get(activity_entry.entity_id) is not None


def test_update_diagnostic_entity_categories_updates_existing_registry_entries(hass, mock_config_entry) -> None:
    """Diagnostic SmartDoor entities should move into the diagnostic section on existing installs."""
    mock_config_entry.add_to_hass(hass)
    entity_reg = er.async_get(hass)

    ac_power_entry = entity_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "door-1_ac_power",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_ac_power",
    )
    connectivity_entry = entity_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "door-1_connectivity",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_connectivity",
    )
    battery_entry = entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_battery_level",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_battery_level",
    )
    schedule_rule_entry = entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_schedule_rule_count",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_schedule_rule_count",
    )
    active_schedule_rule_entry = entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_active_schedule_rule_count",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_active_schedule_rule_count",
    )
    calendar_entry = entity_reg.async_get_or_create(
        "calendar",
        DOMAIN,
        "door-1_pet-1_schedule",
        config_entry=mock_config_entry,
        suggested_object_id="pet_door_milo_schedule",
    )

    assert ac_power_entry.entity_category is None
    assert connectivity_entry.entity_category is None
    assert battery_entry.entity_category is None
    assert schedule_rule_entry.entity_category is None
    assert active_schedule_rule_entry.entity_category is None
    assert calendar_entry.entity_category is None

    integration_module._async_update_diagnostic_entity_categories(hass, mock_config_entry)  # noqa: SLF001

    updated_ac_power_entry = entity_reg.async_get(ac_power_entry.entity_id)
    updated_connectivity_entry = entity_reg.async_get(connectivity_entry.entity_id)
    updated_battery_entry = entity_reg.async_get(battery_entry.entity_id)
    updated_schedule_rule_entry = entity_reg.async_get(schedule_rule_entry.entity_id)
    updated_active_schedule_rule_entry = entity_reg.async_get(active_schedule_rule_entry.entity_id)
    updated_calendar_entry = entity_reg.async_get(calendar_entry.entity_id)
    assert updated_ac_power_entry is not None
    assert updated_connectivity_entry is not None
    assert updated_battery_entry is not None
    assert updated_schedule_rule_entry is not None
    assert updated_active_schedule_rule_entry is not None
    assert updated_calendar_entry is not None
    assert updated_ac_power_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert updated_connectivity_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert updated_battery_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert updated_schedule_rule_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert updated_active_schedule_rule_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert updated_calendar_entry.entity_category is EntityCategory.DIAGNOSTIC


@pytest.mark.asyncio
async def test_coordinator_refresh_skips_schedule_polling_when_schedules_disabled(hass, mock_config_entry) -> None:
    """Disabling SmartDoor schedules should skip schedule refresh work entirely."""
    disabled_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**mock_config_entry.data},
        options={CONF_ENABLE_SMARTDOOR_SCHEDULES: False},
        unique_id=mock_config_entry.unique_id,
    )
    door = _create_smartdoor(api_name="door-1")
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, disabled_entry)
    coordinator._async_build_pet_links = AsyncMock(return_value=PetSafeExtendedPetLinkData())  # noqa: SLF001
    coordinator._async_build_smartdoor_pet_states = AsyncMock(return_value=({}, {}, {}))  # noqa: SLF001
    coordinator._async_build_smartdoor_schedule_data = AsyncMock(return_value={})  # noqa: SLF001

    await coordinator.async_refresh()

    coordinator._async_build_smartdoor_schedule_data.assert_not_awaited()  # noqa: SLF001
    door.get_schedules.assert_not_awaited()
    door.get_preferences.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinator_uses_split_refresh_intervals(hass, mock_config_entry) -> None:
    """Fast activity should refresh every heartbeat while slow schedule/config calls stay cached."""
    feeder = _create_feeder(api_name="feeder-1")
    litterbox = _create_litterbox(api_name="litter-1")
    door = _create_smartdoor(api_name="door-1")
    door.get_activity = AsyncMock(return_value=[])

    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[feeder])
    api.get_litterboxes = AsyncMock(return_value=[litterbox])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._async_build_pet_links = AsyncMock(  # noqa: SLF001
        return_value=PetSafeExtendedPetLinkData(
            pet_ids_by_product_id={"door-1": ("pet-1",)},
            pets_by_id={"pet-1": PetSafeExtendedPetProfile(pet_id="pet-1", name="Milo")},
        )
    )

    await coordinator.async_refresh()
    coordinator._smartdoor_activity_last_refresh_by_door["door-1"] = (  # noqa: SLF001
        time.monotonic() - SMARTDOOR_ACTIVITY_REFRESH_INTERVAL.total_seconds()
    )
    coordinator._feeder_last_feeding_last_refresh_by_feeder["feeder-1"] = (  # noqa: SLF001
        time.monotonic() - FEEDER_LAST_FEEDING_REFRESH_INTERVAL.total_seconds() + 30
    )
    coordinator._feeder_schedule_last_refresh_by_feeder["feeder-1"] = time.monotonic()  # noqa: SLF001
    coordinator._litterbox_activity_last_refresh_by_litterbox["litter-1"] = (  # noqa: SLF001
        time.monotonic() - LITTERBOX_ACTIVITY_REFRESH_INTERVAL.total_seconds() + 30
    )
    coordinator._smartdoor_schedule_last_refresh_by_door["door-1"] = time.monotonic()  # noqa: SLF001
    coordinator._feeders_last_refresh_monotonic = time.monotonic()  # noqa: SLF001
    coordinator._litterboxes_last_refresh_monotonic = time.monotonic()  # noqa: SLF001
    coordinator._smartdoors_last_refresh_monotonic = time.monotonic()  # noqa: SLF001

    await coordinator.async_refresh()

    assert api.get_feeders.await_count == 1
    assert api.get_litterboxes.await_count == 1
    assert api.get_smartdoors.await_count == 1
    assert feeder.get_last_feeding.await_count == 1
    assert feeder.get_schedules.await_count == 1
    assert litterbox.get_activity.await_count == 1
    assert door.get_schedules.await_count == 1
    assert door.get_preferences.await_count == 1
    assert door.get_activity.await_count == 2


@pytest.mark.asyncio
async def test_manual_refresh_helpers_force_slow_data_refresh(hass, mock_config_entry) -> None:
    """Manual maintenance refreshes should bypass the slow schedule and pet-link timers."""
    feeder = _create_feeder(api_name="feeder-1")
    door = _create_smartdoor(api_name="door-1")
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=[feeder])
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)

    await coordinator.async_refresh()

    coordinator.async_request_refresh = AsyncMock()  # type: ignore[method-assign]
    await coordinator.async_refresh_feeder_schedule_data("feeder-1")
    await coordinator.async_refresh_smartdoor_schedule_data("door-1")
    await coordinator.async_refresh_pet_links()

    assert coordinator.async_request_refresh.await_count == 3

    with patch(
        "custom_components.petsafe_extended.coordinator.base.async_build_pet_link_data",
        AsyncMock(return_value=PetSafeExtendedPetLinkData()),
    ) as mock_build_pet_links:
        await coordinator.async_refresh()

    assert feeder.get_schedules.await_count == 2
    assert door.get_schedules.await_count == 2
    assert door.get_preferences.await_count == 2
    mock_build_pet_links.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_refresh_smartdoor_updates_live_state(hass, mock_config_entry) -> None:
    """Refreshing a SmartDoor after a command should publish the new state immediately."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_SMART)
    mode_updates = iter(
        [
            SMARTDOOR_MODE_SMART,
            SMARTDOOR_MODE_MANUAL_LOCKED,
        ]
    )

    async def _update_data() -> None:
        door.mode = next(mode_updates)

    door.update_data = AsyncMock(side_effect=_update_data)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(
        feeders=cast(Any, ["feeder"]),
        litterboxes=cast(Any, ["litterbox"]),
        smartdoors=[door],
    )

    refreshed = await coordinator.async_refresh_smartdoor(
        door.api_name,
        expected_mode=SMARTDOOR_MODE_MANUAL_LOCKED,
        refresh_attempts=2,
        refresh_interval=0,
    )

    assert refreshed is door
    assert door.update_data.await_count == 2
    assert coordinator.data.feeders == ["feeder"]
    assert coordinator.data.litterboxes == ["litterbox"]
    assert coordinator.data.smartdoors == [door]
    assert coordinator.data.smartdoors[0].mode == SMARTDOOR_MODE_MANUAL_LOCKED


@pytest.mark.asyncio
async def test_coordinator_refresh_smartdoor_matches_modes_case_insensitively(hass, mock_config_entry) -> None:
    """Refresh logic should not spin when live mode casing differs from local constants."""
    door = _create_smartdoor(mode="MANUAL_LOCKED")
    door.update_data = AsyncMock()
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    refreshed = await coordinator.async_refresh_smartdoor(
        door.api_name,
        expected_mode="manual_locked",
        refresh_attempts=3,
        refresh_interval=0,
    )

    assert refreshed is door
    door.update_data.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_sets_smartdoor_locked_mode_when_already_locked(hass, mock_config_entry) -> None:
    """Changing the locked-mode preference while locked should update the live device mode."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_SMART)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])
    coordinator.async_refresh_smartdoor = AsyncMock(return_value=door)

    refreshed = await coordinator.async_set_smartdoor_locked_mode(
        door.api_name,
        SMARTDOOR_MODE_MANUAL_LOCKED,
    )

    assert refreshed is door
    door.set_mode.assert_awaited_once_with(SMARTDOOR_MODE_MANUAL_LOCKED, update_data=False)
    coordinator.async_refresh_smartdoor.assert_awaited_once_with(
        door.api_name,
        expected_mode=SMARTDOOR_MODE_MANUAL_LOCKED,
    )
    assert coordinator.get_smartdoor_locked_mode_option(door.api_name) == "locked"


@pytest.mark.asyncio
async def test_coordinator_updates_locked_mode_preference_without_api_when_unlocked(hass, mock_config_entry) -> None:
    """Changing the locked-mode preference while unlocked should avoid SmartDoor mode writes."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_UNLOCKED)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    refreshed = await coordinator.async_set_smartdoor_locked_mode(
        door.api_name,
        SMARTDOOR_MODE_SMART,
    )

    assert refreshed is door
    door.set_mode.assert_not_awaited()
    assert coordinator.get_smartdoor_locked_mode_option(door.api_name) == "smart"


@pytest.mark.asyncio
async def test_coordinator_lock_uses_locked_mode_preference(hass, mock_config_entry) -> None:
    """Lock requests should apply the stored locked-mode preference instead of always using manual lock."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_UNLOCKED)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])
    coordinator.async_set_smartdoor_locked_mode_preference(door.api_name, SMARTDOOR_MODE_SMART)
    coordinator.async_set_smartdoor_operating_mode = AsyncMock(return_value=door)

    await coordinator.async_set_smartdoor_lock(door.api_name, True)

    coordinator.async_set_smartdoor_operating_mode.assert_awaited_once_with(
        door.api_name,
        SMARTDOOR_MODE_SMART,
    )


@pytest.mark.asyncio
async def test_coordinator_sets_smartdoor_final_act(hass, mock_config_entry) -> None:
    """Coordinator final-act writes should call the library setter and refresh the door."""
    door = _create_smartdoor(final_act=SMARTDOOR_FINAL_ACT_UNLOCKED)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])
    coordinator.async_refresh_smartdoor = AsyncMock(return_value=door)

    refreshed = await coordinator.async_set_smartdoor_final_act(
        door.api_name,
        SMARTDOOR_FINAL_ACT_LOCKED,
    )

    assert refreshed is door
    door.set_final_act.assert_awaited_once_with(SMARTDOOR_FINAL_ACT_LOCKED, update_data=False)
    coordinator.async_refresh_smartdoor.assert_awaited_once_with(
        door.api_name,
        expected_final_act=SMARTDOOR_FINAL_ACT_LOCKED,
    )


@pytest.mark.asyncio
async def test_coordinator_refresh_smartdoor_matches_final_act(hass, mock_config_entry) -> None:
    """Refresh logic should wait until the SmartDoor reports the expected final-act state."""
    door = _create_smartdoor(final_act=SMARTDOOR_FINAL_ACT_UNLOCKED)
    final_act_updates = iter([SMARTDOOR_FINAL_ACT_UNLOCKED, SMARTDOOR_FINAL_ACT_LOCKED])

    async def _update_data() -> None:
        door.data["shadow"]["state"]["reported"]["power"]["finalAct"] = next(final_act_updates)

    door.update_data = AsyncMock(side_effect=_update_data)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    refreshed = await coordinator.async_refresh_smartdoor(
        door.api_name,
        expected_final_act=SMARTDOOR_FINAL_ACT_LOCKED,
        refresh_attempts=2,
        refresh_interval=0,
    )

    assert refreshed is door
    assert door.update_data.await_count == 2
