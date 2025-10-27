"""Tests for the PetSafe config flow."""

from __future__ import annotations

import pytest

from custom_components.petsafe.config_flow import ConfigFlow


class _StubDevice:
    """Represent a minimal PetSafe device for config flow tests."""

    def __init__(self, api_name: str, friendly_name: str | None = None, data=None) -> None:
        self.api_name = api_name
        self.friendly_name = friendly_name
        self.data = data or {}


class _StubClient:
    """Stub PetSafe client to validate device collection."""

    def __init__(self) -> None:
        self.id_token = "id"
        self.access_token = "access"
        self.refresh_token = "refresh"

    async def request_tokens_from_code(self, code: str) -> None:  # pragma: no cover - trivial
        return None

    async def get_feeders(self) -> list[_StubDevice]:  # pragma: no cover - config flow only
        return []

    async def get_litterboxes(self) -> list[_StubDevice]:  # pragma: no cover - config flow only
        return []

    async def get_smartdoors(self) -> list[_StubDevice]:
        return [
            _StubDevice(
                api_name="door-id-1",
                friendly_name="API Friendly",
                data={"friendlyName": "Custom Friendly"},
            ),
            _StubDevice(api_name="door-id-2", friendly_name="Fallback Friendly"),
            _StubDevice(api_name="door-id-3"),
        ]


@pytest.mark.asyncio
async def test_get_devices_uses_smartdoor_friendly_name() -> None:
    """The config flow should expose friendly names for smart doors."""

    flow = ConfigFlow()
    flow._client = _StubClient()  # noqa: SLF001 - direct assignment for test

    await flow.get_devices("user@example.com", "123456")

    assert flow._smartdoors == {
        "door-id-1": "Custom Friendly",
        "door-id-2": "Fallback Friendly",
        "door-id-3": "door-id-3",
    }
