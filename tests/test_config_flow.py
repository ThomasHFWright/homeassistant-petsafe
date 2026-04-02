"""Tests for the PetSafe Extended config flow."""

from __future__ import annotations

from base64 import urlsafe_b64encode
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.petsafe_extended.const import CONF_REFRESH_TOKEN, DOMAIN
from custom_components.petsafe_extended.utils.auth import build_account_unique_id
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_CODE, CONF_EMAIL, CONF_TOKEN
from homeassistant.data_entry_flow import FlowResultType

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _encode_id_token(subject: str) -> str:
    """Return a JWT-like token with a stable subject claim."""
    payload = urlsafe_b64encode(json.dumps({"sub": subject}).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"header.{payload}.signature"


def _create_device(api_name: str, friendly_name: str) -> SimpleNamespace:
    """Create a device stub for config-flow device selection."""
    return SimpleNamespace(api_name=api_name, friendly_name=friendly_name)


def _build_petsafe_module(
    *,
    id_token: str,
    access_token: str = "new-access-token",
    refresh_token: str = "new-refresh-token",
    request_code_side_effect: Exception | None = None,
    request_tokens_side_effect: Exception | None = None,
    invalid_code: bool = False,
) -> SimpleNamespace:
    """Create a fake petsafe module for config-flow tests."""

    class InvalidUserException(Exception):
        """Stub invalid-user exception."""

    class InvalidCodeException(Exception):
        """Stub invalid-code exception."""

    class FakePetSafeClient:
        """Stub client used by the config flow."""

        instances: list[FakePetSafeClient] = []

        def __init__(self, email: str) -> None:
            self.email = email
            self.id_token = id_token
            self.access_token = access_token
            self.refresh_token = refresh_token
            FakePetSafeClient.instances.append(self)

        async def request_code(self) -> None:
            """Request a one-time code for the supplied account."""
            if request_code_side_effect is not None:
                raise request_code_side_effect

        async def request_tokens_from_code(self, code: str) -> None:
            """Exchange a confirmation code for fresh tokens."""
            if request_tokens_side_effect is not None:
                raise request_tokens_side_effect
            if invalid_code or not code:
                raise InvalidCodeException("invalid code")

        async def get_feeders(self) -> list[SimpleNamespace]:
            """Return feeder device stubs."""
            return [_create_device("feeder-1", "Kitchen Feeder")]

        async def get_litterboxes(self) -> list[SimpleNamespace]:
            """Return litterbox device stubs."""
            return [_create_device("litter-1", "Main Litterbox")]

        async def get_smartdoors(self) -> list[SimpleNamespace]:
            """Return smart door device stubs."""
            return [_create_device("door-1", "Pet Door")]

    return SimpleNamespace(
        PetSafeClient=FakePetSafeClient,
        client=SimpleNamespace(
            InvalidUserException=InvalidUserException,
            InvalidCodeException=InvalidCodeException,
        ),
    )


@pytest.mark.asyncio
async def test_user_flow_creates_entry_with_account_unique_id(hass) -> None:
    """A successful user flow should create an entry with a stable unique ID."""
    email = "person@example.com"
    id_token = _encode_id_token("account-subject")
    petsafe_module = _build_petsafe_module(id_token=id_token)

    with patch(
        "custom_components.petsafe_extended.config_flow._async_import_petsafe",
        AsyncMock(return_value=petsafe_module),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_EMAIL: email})
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "code"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "123456"})
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "devices"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "feeders": ["feeder-1"],
                "litterboxes": ["litter-1"],
                "smartdoors": ["door-1"],
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.unique_id == build_account_unique_id(email, id_token)
    assert entry.data[CONF_EMAIL] == email
    assert entry.data[CONF_TOKEN] == id_token
    assert entry.data[CONF_ACCESS_TOKEN] == "new-access-token"
    assert entry.data[CONF_REFRESH_TOKEN] == "new-refresh-token"


@pytest.mark.asyncio
async def test_user_flow_aborts_when_account_is_already_configured(hass) -> None:
    """A duplicate account should abort during the code exchange step."""
    email = "person@example.com"
    id_token = _encode_id_token("duplicate-subject")
    petsafe_module = _build_petsafe_module(id_token=id_token)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: email,
            CONF_TOKEN: "existing-id-token",
            CONF_ACCESS_TOKEN: "existing-access-token",
            CONF_REFRESH_TOKEN: "existing-refresh-token",
        },
        unique_id=build_account_unique_id(email, id_token),
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.petsafe_extended.config_flow._async_import_petsafe",
        AsyncMock(return_value=petsafe_module),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_EMAIL: email})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "123456"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_user_flow_shows_invalid_code_error(hass) -> None:
    """An invalid confirmation code should stay on the code step."""
    petsafe_module = _build_petsafe_module(
        id_token=_encode_id_token("invalid-code-subject"),
        invalid_code=True,
    )

    with patch(
        "custom_components.petsafe_extended.config_flow._async_import_petsafe",
        AsyncMock(return_value=petsafe_module),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_EMAIL: "person@example.com"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "000000"})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "code"
    assert result["errors"] == {CONF_CODE: "invalid_code"}


@pytest.mark.asyncio
async def test_reauth_flow_updates_existing_entry_tokens(hass) -> None:
    """A successful reauth flow should update the existing entry in place."""
    email = "person@example.com"
    old_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: email,
            CONF_TOKEN: "old-id-token",
            CONF_ACCESS_TOKEN: "old-access-token",
            CONF_REFRESH_TOKEN: "old-refresh-token",
            "feeders": ["feeder-1"],
            "smartdoors": ["door-1"],
        },
        unique_id=None,
        title=email,
    )
    old_entry.add_to_hass(hass)

    id_token = _encode_id_token("reauth-subject")
    petsafe_module = _build_petsafe_module(id_token=id_token)

    with (
        patch(
            "custom_components.petsafe_extended.config_flow._async_import_petsafe",
            AsyncMock(return_value=petsafe_module),
        ),
        patch.object(hass.config_entries, "async_schedule_reload") as mock_reload,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": old_entry.entry_id, "unique_id": old_entry.unique_id},
            data=old_entry.data,
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "654321"})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    updated_entry = hass.config_entries.async_get_entry(old_entry.entry_id)
    assert updated_entry is not None
    assert updated_entry.unique_id == build_account_unique_id(email, id_token)
    assert updated_entry.data[CONF_TOKEN] == id_token
    assert updated_entry.data[CONF_ACCESS_TOKEN] == "new-access-token"
    assert updated_entry.data[CONF_REFRESH_TOKEN] == "new-refresh-token"
    assert updated_entry.data["feeders"] == ["feeder-1"]
    assert updated_entry.data["smartdoors"] == ["door-1"]
    mock_reload.assert_called_once_with(old_entry.entry_id)
