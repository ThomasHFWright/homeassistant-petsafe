"""Tests for PetSafe SmartDoor entities and platform setup."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import petsafe_extended as integration_module
from custom_components.petsafe_extended.const import (
    DOMAIN,
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
from custom_components.petsafe_extended.data import (
    PetSafeExtendedCoordinatorData,
    PetSafeExtendedPetLinkData,
    PetSafeExtendedPetProductLink,
    PetSafeExtendedPetProfile,
    PetSafeExtendedSmartDoorActivityRecord,
    PetSafeExtendedSmartDoorPetState,
)
from custom_components.petsafe_extended.diagnostics import async_get_config_entry_diagnostics
from custom_components.petsafe_extended.event import async_setup_entry as async_setup_event_entry
from custom_components.petsafe_extended.event.smartdoor_activity import PetSafeExtendedSmartDoorActivityEvent
from custom_components.petsafe_extended.lock import async_setup_entry
from custom_components.petsafe_extended.lock.smartdoor import PetSafeExtendedSmartDoorLock
from custom_components.petsafe_extended.select import async_setup_entry as async_setup_select_entry
from custom_components.petsafe_extended.select.smartdoor_final_act import PetSafeExtendedSmartDoorFinalActSelect
from custom_components.petsafe_extended.select.smartdoor_operating_mode import (
    PetSafeExtendedSmartDoorOperatingModeSelect,
)
from custom_components.petsafe_extended.sensor import async_setup_entry as async_setup_sensor_entry
from custom_components.petsafe_extended.sensor.smartdoor_pet import PetSafeExtendedSmartDoorPetSensor
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.util import dt as dt_util


def _create_smartdoor(
    *,
    api_name: str = "smartdoor-1",
    mode: str | None = SMARTDOOR_MODE_SMART,
    latch_state: str | None = "Closed",
    final_act: str | None = SMARTDOOR_FINAL_ACT_UNLOCKED,
    connection_status: str | None = "online",
    battery_level: int | None = 75,
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
    door.error_state = None
    door.has_adapter = False
    door.connection_status = connection_status
    door.battery_voltage = 12.3
    door.rssi = -40
    door.battery_level = battery_level
    door.lock = AsyncMock()
    door.unlock = AsyncMock()
    door.set_mode = AsyncMock()
    door.set_final_act = AsyncMock()
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
async def test_lock_entity_normalizes_mode_and_latch_state(coordinator) -> None:
    """Lock state should tolerate raw API casing and fall back to latch state."""
    unlocked_door = _create_smartdoor(mode="MANUAL_UNLOCKED", latch_state="UNLOCKED")
    locked_door = _create_smartdoor(mode="unexpected_mode", latch_state="LOCKED")
    unknown_door = _create_smartdoor(mode="unexpected_mode", latch_state="unexpected_state")

    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[unlocked_door])
    unlocked_entity = PetSafeExtendedSmartDoorLock(coordinator, unlocked_door)
    assert unlocked_entity.is_locked is False

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
async def test_operating_mode_select_state_and_controls(coordinator) -> None:
    """SmartDoor operating mode select should expose and change the current mode."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_SMART)
    locked_door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_LOCKED)
    coordinator.async_set_smartdoor_operating_mode = AsyncMock(return_value=locked_door)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])

    entity = PetSafeExtendedSmartDoorOperatingModeSelect(coordinator, door)

    assert entity.current_option == "smart"
    assert entity.translation_key == "operating_mode"

    await entity.async_select_option("locked")

    assert entity.current_option == "locked"
    coordinator.async_set_smartdoor_operating_mode.assert_awaited_once_with(
        door.api_name,
        SMARTDOOR_MODE_MANUAL_LOCKED,
    )


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
    """The select platform should add the SmartDoor mode and final-act selects."""
    door = _create_smartdoor(api_name="door-1")
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

    assert len(added_entities) == 2
    assert any(isinstance(entity, PetSafeExtendedSmartDoorOperatingModeSelect) for entity in added_entities)
    assert any(isinstance(entity, PetSafeExtendedSmartDoorFinalActSelect) for entity in added_entities)
    assert {entity.translation_key for entity in added_entities} == {"operating_mode", "final_act"}
    assert all(entity.device_info is not None for entity in added_entities)
    assert all(entity.device_info["identifiers"] == {("petsafe_extended", "door-1")} for entity in added_entities)


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
    """The sensor platform should create one sensor pair per linked SmartDoor pet."""
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

    assert len(added_entities) == 4
    assert all(isinstance(entity, PetSafeExtendedSmartDoorPetSensor) for entity in added_entities)
    activity_entities = [entity for entity in added_entities if entity.entity_description.key == "last_activity"]
    assert sorted(entity.name for entity in activity_entities) == ["Milo Last Activity", "Pet 2 Last Activity"]
    assert all(entity.device_info is not None for entity in added_entities)
    assert all(entity.device_info["identifiers"] == {("petsafe_extended", "door-1")} for entity in added_entities)
    assert all(entity.translation_key == "last_activity" for entity in activity_entities)
    assert activity_entities[0].extra_state_attributes["technology"] == "MICROCHIP"
    assert "pet_id" not in activity_entities[0].extra_state_attributes


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
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    serialized = json.dumps(diagnostics)

    assert diagnostics["data_summary"]["pet_profiles"] == 1
    assert diagnostics["data_summary"]["pet_product_links"] == 1
    assert diagnostics["data_summary"]["linked_products"] == 1
    assert "pet-private" not in serialized
    assert "door-private" not in serialized


@pytest.mark.asyncio
async def test_entry_platforms_include_sensor_for_smartdoor_only(mock_config_entry) -> None:
    """SmartDoor-only entries should now load sensor, select, event, and lock platforms."""
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

    assert platforms == [Platform.SENSOR, Platform.SELECT, Platform.EVENT, Platform.LOCK]


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
async def test_coordinator_sets_smartdoor_operating_mode(hass, mock_config_entry) -> None:
    """Coordinator operating-mode writes should call the library setter and refresh the door."""
    door = _create_smartdoor(mode=SMARTDOOR_MODE_SMART)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(smartdoors=[door])
    coordinator.async_refresh_smartdoor = AsyncMock(return_value=door)

    refreshed = await coordinator.async_set_smartdoor_operating_mode(
        door.api_name,
        SMARTDOOR_MODE_MANUAL_LOCKED,
    )

    assert refreshed is door
    door.set_mode.assert_awaited_once_with(SMARTDOOR_MODE_MANUAL_LOCKED, update_data=False)
    coordinator.async_refresh_smartdoor.assert_awaited_once_with(
        door.api_name,
        expected_mode=SMARTDOOR_MODE_MANUAL_LOCKED,
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
