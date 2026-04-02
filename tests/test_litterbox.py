"""Tests for litterbox entities."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.petsafe_extended.button.litterbox_action import (
    LITTERBOX_BUTTON_DESCRIPTIONS,
    PetSafeExtendedLitterboxButton,
)
from custom_components.petsafe_extended.coordinator import PetSafeExtendedDataUpdateCoordinator
from custom_components.petsafe_extended.data import PetSafeExtendedCoordinatorData, PetSafeExtendedLitterboxDetails
from custom_components.petsafe_extended.select.litterbox_rake_timer import (
    LITTERBOX_SELECT_DESCRIPTIONS,
    PetSafeExtendedLitterboxSelect,
)
from custom_components.petsafe_extended.sensor.litterbox import (
    LITTERBOX_SENSOR_DESCRIPTIONS,
    PetSafeExtendedLitterboxSensor,
)


def _create_litterbox(api_name: str = "litter-1") -> Any:
    """Create a litterbox stub for entity tests."""
    litterbox = SimpleNamespace()
    litterbox.api_name = api_name
    litterbox.friendly_name = "Main Litterbox"
    litterbox.product_name = "ScoopFree"
    litterbox.firmware = "1.0.0"
    litterbox.data = {
        "shadow": {
            "state": {
                "reported": {
                    "rakeCount": 7,
                    "rakeDelayTime": 15,
                    "rssi": -61,
                }
            }
        }
    }
    return litterbox


@pytest.mark.asyncio
async def test_litterbox_entities_use_coordinator_state(hass, mock_config_entry) -> None:
    """Litterbox entities should expose coordinator-backed values and commands."""
    litterbox = _create_litterbox()
    coordinator = PetSafeExtendedDataUpdateCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeExtendedCoordinatorData(
        litterboxes=[litterbox],
        litterbox_details={
            litterbox.api_name: PetSafeExtendedLitterboxDetails(
                last_cleaning=datetime(2026, 4, 1, 9, 30, tzinfo=UTC),
                rake_status="idle",
            )
        },
    )
    coordinator.async_rake_litterbox = AsyncMock()
    coordinator.async_reset_litterbox = AsyncMock()
    coordinator.async_set_litterbox_rake_timer = AsyncMock()

    rake_counter = PetSafeExtendedLitterboxSensor(coordinator, litterbox, LITTERBOX_SENSOR_DESCRIPTIONS[0])
    rake_status = PetSafeExtendedLitterboxSensor(coordinator, litterbox, LITTERBOX_SENSOR_DESCRIPTIONS[1])
    signal_strength = PetSafeExtendedLitterboxSensor(coordinator, litterbox, LITTERBOX_SENSOR_DESCRIPTIONS[2])
    last_cleaning = PetSafeExtendedLitterboxSensor(coordinator, litterbox, LITTERBOX_SENSOR_DESCRIPTIONS[3])

    assert rake_counter.native_value == 7
    assert rake_status.native_value == "idle"
    assert signal_strength.native_value == -61
    assert last_cleaning.native_value == datetime(2026, 4, 1, 9, 30, tzinfo=UTC)

    clean_button = PetSafeExtendedLitterboxButton(coordinator, litterbox, LITTERBOX_BUTTON_DESCRIPTIONS[0])
    reset_button = PetSafeExtendedLitterboxButton(coordinator, litterbox, LITTERBOX_BUTTON_DESCRIPTIONS[1])
    timer_select = PetSafeExtendedLitterboxSelect(coordinator, litterbox, LITTERBOX_SELECT_DESCRIPTIONS[0])

    await clean_button.async_press()
    await reset_button.async_press()
    await timer_select.async_select_option("20")

    assert timer_select.current_option == "15"
    coordinator.async_rake_litterbox.assert_awaited_once_with(litterbox.api_name)
    coordinator.async_reset_litterbox.assert_awaited_once_with(litterbox.api_name)
    coordinator.async_set_litterbox_rake_timer.assert_awaited_once_with(litterbox.api_name, 20)
