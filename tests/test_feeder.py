"""Tests for feeder entities and services."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.petsafe_extended.button.feeder_feed import (
    FEEDER_BUTTON_DESCRIPTIONS,
    PetSafeExtendedFeederButton,
)
from custom_components.petsafe_extended.const import DOMAIN, FEEDER_MODEL_GEN2, SERVICE_FEED
from custom_components.petsafe_extended.coordinator import PetSafeExtendedDataUpdateCoordinator
from custom_components.petsafe_extended.data import PetSafeExtendedCoordinatorData, PetSafeExtendedFeederDetails
from custom_components.petsafe_extended.sensor.feeder import FEEDER_SENSOR_DESCRIPTIONS, PetSafeExtendedFeederSensor
from custom_components.petsafe_extended.service_actions import async_setup_services
from custom_components.petsafe_extended.switch.feeder_control import (
    FEEDER_SWITCH_DESCRIPTIONS,
    PetSafeExtendedFeederSwitch,
)
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.helpers import device_registry as dr


def _create_feeder(api_name: str = "feeder-1") -> Any:
    """Create a feeder stub for entity tests."""
    feeder = SimpleNamespace()
    feeder.api_name = api_name
    feeder.friendly_name = "Kitchen Feeder"
    feeder.product_name = FEEDER_MODEL_GEN2
    feeder.firmware = "1.0.0"
    feeder.battery_level = 83
    feeder.food_low_status = 1
    feeder.data = {"network_rssi": -54}
    feeder.is_locked = False
    feeder.is_paused = True
    feeder.is_slow_feed = False
    return feeder


@pytest.mark.asyncio
async def test_feeder_entities_use_coordinator_state(hass, mock_config_entry) -> None:
    """Feeder entities should expose coordinator-backed values and commands."""
    feeder = _create_feeder()
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(
        feeders=[feeder],
        feeder_details={
            feeder.api_name: PetSafeExtendedFeederDetails(
                last_feeding=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
                next_feeding=datetime(2026, 4, 1, 18, 0, tzinfo=UTC),
            )
        },
    )
    coordinator.async_feed_feeder = AsyncMock()
    coordinator.async_set_feeder_child_lock = AsyncMock()
    coordinator.async_set_feeder_paused = AsyncMock()
    coordinator.async_set_feeder_slow_feed = AsyncMock()

    battery = PetSafeExtendedFeederSensor(coordinator, feeder, FEEDER_SENSOR_DESCRIPTIONS[0])
    last_feeding = PetSafeExtendedFeederSensor(coordinator, feeder, FEEDER_SENSOR_DESCRIPTIONS[1])
    next_feeding = PetSafeExtendedFeederSensor(coordinator, feeder, FEEDER_SENSOR_DESCRIPTIONS[2])
    food_level = PetSafeExtendedFeederSensor(coordinator, feeder, FEEDER_SENSOR_DESCRIPTIONS[3])
    signal_strength = PetSafeExtendedFeederSensor(coordinator, feeder, FEEDER_SENSOR_DESCRIPTIONS[4])

    assert battery.native_value == 83
    assert last_feeding.native_value == datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
    assert next_feeding.native_value == datetime(2026, 4, 1, 18, 0, tzinfo=UTC)
    assert food_level.native_value == "low"
    assert signal_strength.native_value == -54

    feed_button = PetSafeExtendedFeederButton(coordinator, feeder, FEEDER_BUTTON_DESCRIPTIONS[0])
    await feed_button.async_press()
    coordinator.async_feed_feeder.assert_awaited_once_with(feeder.api_name, 1, None)

    paused_switch = PetSafeExtendedFeederSwitch(coordinator, feeder, FEEDER_SWITCH_DESCRIPTIONS[0])
    child_lock_switch = PetSafeExtendedFeederSwitch(coordinator, feeder, FEEDER_SWITCH_DESCRIPTIONS[1])
    slow_feed_switch = PetSafeExtendedFeederSwitch(coordinator, feeder, FEEDER_SWITCH_DESCRIPTIONS[2])

    assert paused_switch.is_on is True
    assert child_lock_switch.is_on is False
    assert slow_feed_switch.is_on is False

    await child_lock_switch.async_turn_on()
    await paused_switch.async_turn_off()
    await slow_feed_switch.async_turn_on()

    coordinator.async_set_feeder_child_lock.assert_awaited_once_with(feeder.api_name, True)
    coordinator.async_set_feeder_paused.assert_awaited_once_with(feeder.api_name, False)
    coordinator.async_set_feeder_slow_feed.assert_awaited_once_with(feeder.api_name, True)


@pytest.mark.asyncio
async def test_feed_service_routes_targets_to_coordinator(
    hass,
    mock_config_entry,
    attach_runtime_data,
) -> None:
    """The feed service should target the matching feeder device."""
    feeder = _create_feeder()
    api = MagicMock()
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, api, mock_config_entry)
    coordinator._feeders = [feeder]  # noqa: SLF001
    coordinator.async_feed_feeder = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    mock_config_entry.add_to_hass(hass)
    attach_runtime_data(mock_config_entry, coordinator)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, feeder.api_name)},
        manufacturer="PetSafe",
        model=FEEDER_MODEL_GEN2,
        name=feeder.friendly_name,
    )

    await async_setup_services(hass)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_FEED,
        {
            ATTR_DEVICE_ID: [device.id],
            "amount": 2,
        },
        blocking=True,
    )

    coordinator.async_feed_feeder.assert_awaited_once_with(feeder.api_name, 2, None, refresh=False)
    coordinator.async_request_refresh.assert_awaited_once()
