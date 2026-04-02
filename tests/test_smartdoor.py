"""Tests for PetSafe SmartDoor entities and platform setup."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from custom_components.petsafe_extended.const import (
    SMARTDOOR_MODE_MANUAL_LOCKED,
    SMARTDOOR_MODE_MANUAL_UNLOCKED,
    SMARTDOOR_MODE_SMART,
)
from custom_components.petsafe_extended.coordinator import PetSafeExtendedDataUpdateCoordinator
from custom_components.petsafe_extended.data import (
    PetSafeExtendedCoordinatorData,
    PetSafeExtendedPetLinkData,
    PetSafeExtendedPetProductLink,
    PetSafeExtendedPetProfile,
)
from custom_components.petsafe_extended.diagnostics import async_get_config_entry_diagnostics
from custom_components.petsafe_extended.lock import async_setup_entry
from custom_components.petsafe_extended.lock.smartdoor import PetSafeExtendedSmartDoorLock
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady


def _create_smartdoor(
    *,
    api_name: str = "smartdoor-1",
    mode: str | None = SMARTDOOR_MODE_SMART,
    latch_state: str | None = "Closed",
    connection_status: str | None = "online",
    battery_level: int | None = 75,
) -> Any:
    """Construct a SmartDoor device stub with async methods."""
    door = SimpleNamespace()
    door.api_name = api_name
    door.data = {
        "productName": "SmartDoor",
        "friendlyName": "Back Door",
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


@pytest.fixture
def coordinator(hass, mock_config_entry, attach_runtime_data):
    """Create a coordinator instance with a mocked API client."""
    api = MagicMock()
    mock_config_entry.add_to_hass(hass)
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    attach_runtime_data(mock_config_entry, coordinator)
    return coordinator


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
