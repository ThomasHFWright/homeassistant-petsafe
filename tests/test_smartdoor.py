"""Tests for PetSafe SmartDoor entities and platform setup."""

from __future__ import annotations

# pylint: disable=import-error,protected-access,redefined-outer-name

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from homeassistant.exceptions import ConfigEntryNotReady

try:
    from petsafe.const import (
        SMARTDOOR_MODE_MANUAL_LOCKED,
        SMARTDOOR_MODE_MANUAL_UNLOCKED,
        SMARTDOOR_MODE_SMART,
    )
except ModuleNotFoundError:  # pragma: no cover - fallback for lint environments
    SMARTDOOR_MODE_MANUAL_LOCKED = "manual_locked"
    SMARTDOOR_MODE_MANUAL_UNLOCKED = "manual_unlocked"
    SMARTDOOR_MODE_SMART = "smart"

from custom_components.petsafe import PetSafeCoordinator, PetSafeData
from custom_components.petsafe.const import DOMAIN
from custom_components.petsafe.lock import async_setup_entry
from custom_components.petsafe.SmartDoorEntities import PetSafeSmartDoorLockEntity


def _create_smartdoor(
    *,
    api_name: str = "smartdoor-1",
    mode: str | None = SMARTDOOR_MODE_SMART,
    latch_state: str | None = "Closed",
    connection_status: str | None = "online",
    battery_level: int | None = 75,
) -> SimpleNamespace:
    """Construct a SmartDoor device stub with async methods."""

    door = SimpleNamespace()
    door.api_name = api_name
    door.data = {
        "productName": "SmartDoor",
        "friendlyName": "Back Door",
        "timezone": "America/Chicago",
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
    return door


@pytest.fixture
def coordinator(hass, mock_config_entry):
    """Create a coordinator instance with a mocked API client."""

    api = MagicMock()
    mock_config_entry.add_to_hass(hass)
    return PetSafeCoordinator(hass, api, mock_config_entry)


@pytest.mark.asyncio
async def test_lock_entity_state_and_controls(hass, coordinator) -> None:
    """Validate SmartDoor lock entity properties and control actions."""

    coordinator.async_request_refresh = AsyncMock()
    door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_LOCKED, latch_state="Open")
    coordinator.data = PetSafeData([], [], [door])

    entity = PetSafeSmartDoorLockEntity(hass, door, coordinator)

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
        "friendlyName": "Back Door",
        "timezone": "America/Chicago",
    }
    for key, value in expected_attrs.items():
        assert entity.extra_state_attributes[key] == value

    await entity.async_unlock()
    door.unlock.assert_awaited_once_with(update_data=False)
    coordinator.async_request_refresh.assert_awaited()

    coordinator.async_request_refresh.reset_mock()
    await entity.async_lock()
    door.lock.assert_awaited_once_with(update_data=False)
    coordinator.async_request_refresh.assert_awaited()

    door.connection_status = "offline"
    assert entity.available is False


@pytest.mark.asyncio
async def test_lock_entity_updates_from_coordinator(hass, coordinator) -> None:
    """Ensure the entity replaces its door reference when coordinator data changes."""

    original_door = _create_smartdoor(mode=SMARTDOOR_MODE_MANUAL_UNLOCKED)
    updated_door = _create_smartdoor(
        mode=SMARTDOOR_MODE_MANUAL_LOCKED,
        latch_state="Open",
        connection_status="offline",
    )
    coordinator.data = PetSafeData([], [], [original_door])
    entity = PetSafeSmartDoorLockEntity(hass, original_door, coordinator)
    entity.hass = hass
    entity.entity_id = "lock.test_door"

    assert entity.is_locked is False

    coordinator.data = PetSafeData([], [], [updated_door])
    entity._handle_coordinator_update()

    assert entity.is_locked is True
    assert entity.available is False
    assert entity.is_open is True


@pytest.mark.asyncio
async def test_lock_platform_setup_adds_entities(hass, mock_config_entry) -> None:
    """The lock platform should add one entity per smartdoor from the coordinator."""

    door = _create_smartdoor()
    coordinator = PetSafeCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = coordinator

    async_add_entities = MagicMock()
    with patch.object(
        PetSafeCoordinator, "get_smartdoors", AsyncMock(return_value=[door])
    ):
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

    async_add_entities.assert_called_once()
    added_entities = async_add_entities.call_args[0][0]
    assert len(added_entities) == 1
    assert isinstance(added_entities[0], PetSafeSmartDoorLockEntity)


@pytest.mark.asyncio
async def test_lock_platform_setup_handles_failure(hass, mock_config_entry) -> None:
    """A failure retrieving smartdoors should raise ConfigEntryNotReady."""

    coordinator = PetSafeCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = coordinator

    with (
        patch.object(
            PetSafeCoordinator, "get_smartdoors", AsyncMock(side_effect=RuntimeError)
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, mock_config_entry, MagicMock())


@pytest.mark.asyncio
async def test_coordinator_get_smartdoors_caches_results(
    hass, mock_config_entry
) -> None:
    """Coordinator caching should avoid redundant API calls."""

    api = MagicMock()
    door = _create_smartdoor()
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeCoordinator(hass, api, mock_config_entry)

    first = await coordinator.get_smartdoors()
    second = await coordinator.get_smartdoors()

    assert first is second
    api.get_smartdoors.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_get_smartdoors_triggers_reauth(
    hass, mock_config_entry
) -> None:
    """HTTP auth errors should trigger reauthentication flow."""

    api = MagicMock()
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(401, request=request)
    api.get_smartdoors = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=request, response=response
        )
    )
    coordinator = PetSafeCoordinator(hass, api, mock_config_entry)

    mock_config_entry.async_start_reauth = AsyncMock()
    result = await coordinator.get_smartdoors()

    mock_config_entry.async_start_reauth.assert_awaited_once_with(hass)
    assert result is None


@pytest.mark.asyncio
async def test_coordinator_update_data_includes_smartdoors(
    hass, mock_config_entry
) -> None:
    """The coordinator should populate smartdoor data during updates."""

    door = _create_smartdoor()
    api = MagicMock()
    api.get_feeders = AsyncMock(return_value=["feeder"])
    api.get_litterboxes = AsyncMock(return_value=["litterbox"])
    api.get_smartdoors = AsyncMock(return_value=[door])
    coordinator = PetSafeCoordinator(hass, api, mock_config_entry)

    data = await coordinator._async_update_data()

    assert isinstance(data, PetSafeData)
    assert data.smartdoors == [door]
    api.get_feeders.assert_awaited_once()
    api.get_litterboxes.assert_awaited_once()
    api.get_smartdoors.assert_awaited_once()
