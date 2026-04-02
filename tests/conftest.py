"""Fixtures for PetSafe integration tests."""

from __future__ import annotations

from pathlib import Path

# pylint: disable=wrong-import-position,import-error,too-few-public-methods
import sys
import types
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_ACCESS_TOKEN, CONF_EMAIL, CONF_TOKEN

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if "petsafe" not in sys.modules:
    petsafe_module: Any = types.ModuleType("petsafe")
    petsafe_const: Any = types.ModuleType("petsafe.const")
    petsafe_client: Any = types.ModuleType("petsafe.client")

    class _InvalidUserException(Exception):
        """Stub invalid-user exception."""

    class _InvalidCodeException(Exception):
        """Stub invalid-code exception."""

    setattr(petsafe_const, "SMARTDOOR_MODE_MANUAL_LOCKED", "manual_locked")
    setattr(petsafe_const, "SMARTDOOR_MODE_MANUAL_UNLOCKED", "manual_unlocked")
    setattr(petsafe_const, "SMARTDOOR_MODE_SMART", "smart")
    setattr(petsafe_module, "const", petsafe_const)
    setattr(petsafe_client, "InvalidUserException", _InvalidUserException)
    setattr(petsafe_client, "InvalidCodeException", _InvalidCodeException)
    setattr(petsafe_module, "client", petsafe_client)
    setattr(
        petsafe_module,
        "devices",
        types.SimpleNamespace(
            DeviceSmartDoor=object,
            DeviceSmartFeed=object,
            DeviceScoopfree=object,
        ),
    )

    class _StubPetSafeClient:  # pragma: no cover - import stub
        """Stub PetSafe client used for import resolution in tests."""

        def __init__(self, *args, **kwargs) -> None:
            pass

    setattr(petsafe_module, "PetSafeClient", _StubPetSafeClient)
    sys.modules["petsafe"] = petsafe_module
    sys.modules["petsafe.client"] = petsafe_client
    sys.modules["petsafe.const"] = petsafe_const

from custom_components.petsafe_extended.const import CONF_REFRESH_TOKEN, DOMAIN
from custom_components.petsafe_extended.data import PetSafeExtendedRuntimeData


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


@pytest.fixture
def attach_runtime_data():
    """Attach runtime data to a config entry for platform tests."""

    def _attach(entry: MockConfigEntry, coordinator: Any, client: Any | None = None) -> MockConfigEntry:
        entry.runtime_data = PetSafeExtendedRuntimeData(
            client=client or SimpleNamespace(),
            coordinator=coordinator,
            integration=cast(
                Any,
                SimpleNamespace(
                    name="PetSafe Extended",
                    version="0.1.0",
                    domain=DOMAIN,
                    documentation="https://example.com/docs",
                    issue_tracker="https://example.com/issues",
                ),
            ),
        )
        return entry

    return _attach
