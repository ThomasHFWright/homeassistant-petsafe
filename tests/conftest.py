"""Fixtures for PetSafe integration tests."""

from __future__ import annotations

# pylint: disable=wrong-import-position,import-error,too-few-public-methods

import sys
import types
from pathlib import Path

import pytest
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_EMAIL, CONF_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if "petsafe" not in sys.modules:
    petsafe_module = types.ModuleType("petsafe")
    petsafe_const = types.ModuleType("petsafe.const")
    petsafe_const.SMARTDOOR_MODE_MANUAL_LOCKED = "manual_locked"
    petsafe_const.SMARTDOOR_MODE_MANUAL_UNLOCKED = "manual_unlocked"
    petsafe_const.SMARTDOOR_MODE_SMART = "smart"
    petsafe_module.const = petsafe_const
    petsafe_module.devices = types.SimpleNamespace(
        DeviceSmartDoor=object,
        DeviceSmartFeed=object,
        DeviceScoopfree=object,
    )

    class _StubPetSafeClient:  # pragma: no cover - import stub
        """Stub PetSafe client used for import resolution in tests."""

        def __init__(self, *args, **kwargs) -> None:
            pass

    petsafe_module.PetSafeClient = _StubPetSafeClient
    sys.modules["petsafe"] = petsafe_module
    sys.modules["petsafe.const"] = petsafe_const

from custom_components.petsafe.const import CONF_REFRESH_TOKEN, DOMAIN  # noqa: E402


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry for the PetSafe integration."""

    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_TOKEN: "token",
            CONF_REFRESH_TOKEN: "refresh",
            CONF_ACCESS_TOKEN: "access",
        },
        unique_id="test_entry",
    )
