"""Tests for PetSafe auth and polling behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from custom_components.petsafe_extended import (
    PetSafeCoordinator,
    PetSafeData,
    button as button_platform,
    lock as lock_platform,
    select as select_platform,
    sensor as sensor_platform,
    switch as switch_platform,
)
from custom_components.petsafe_extended.const import DOMAIN
from homeassistant.exceptions import ConfigEntryAuthFailed


def _build_auth_error(status_code: int = 401) -> httpx.HTTPStatusError:
    """Create an HTTP auth error for coordinator tests."""
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("Unauthorized", request=request, response=response)


def _create_smartdoor(api_name: str = "door-1") -> Any:
    """Create a SmartDoor stub for coordinator refresh tests."""
    door = SimpleNamespace()
    door.api_name = api_name
    door.data = {"friendlyName": "Pet Door"}
    door.mode = "smart"
    door.lock = AsyncMock()
    door.unlock = AsyncMock()
    door.update_data = AsyncMock(side_effect=_build_auth_error())
    return door


@pytest.mark.asyncio
async def test_polling_auth_failure_raises_reauth_immediately(hass, mock_config_entry) -> None:
    """Polling should trigger reauth on the first auth failure."""
    api = MagicMock()
    api.get_feeders = AsyncMock(side_effect=_build_auth_error())
    api.get_litterboxes = AsyncMock(return_value=[])
    api.get_smartdoors = AsyncMock(return_value=[])
    coordinator = PetSafeCoordinator(hass, api, mock_config_entry)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()  # noqa: SLF001


@pytest.mark.asyncio
async def test_smartdoor_refresh_auth_failure_raises_reauth(hass, mock_config_entry) -> None:
    """SmartDoor command refreshes should raise auth failures immediately."""
    coordinator = PetSafeCoordinator(hass, MagicMock(), mock_config_entry)
    coordinator.data = PetSafeData([], [], [_create_smartdoor()])

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator.async_refresh_smartdoor("door-1", refresh_attempts=1, refresh_interval=0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform_module", "coordinator_method"),
    [
        (button_platform, "get_feeders"),
        (lock_platform, "get_smartdoors"),
        (select_platform, "get_litterboxes"),
        (sensor_platform, "get_feeders"),
        (switch_platform, "get_feeders"),
    ],
)
async def test_platform_setup_propagates_auth_failures(
    hass,
    mock_config_entry,
    platform_module,
    coordinator_method: str,
) -> None:
    """Platform setup should propagate auth failures instead of masking them."""
    coordinator = PetSafeCoordinator(hass, MagicMock(), mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = coordinator

    with (
        patch.object(coordinator, coordinator_method, AsyncMock(side_effect=ConfigEntryAuthFailed)),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await platform_module.async_setup_entry(hass, mock_config_entry, MagicMock())
