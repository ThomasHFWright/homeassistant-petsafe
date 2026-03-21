"""Config flow for PetSafe Integration."""

from __future__ import annotations

from functools import partial
import logging
from typing import Any

from botocore.exceptions import ParamValidationError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_BASE, CONF_CODE, CONF_EMAIL, CONF_TOKEN
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.requirements import RequirementsNotFound

from . import _async_import_petsafe
from .const import CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str})
STEP_CODE_DATA_SCHEMA = vol.Schema({vol.Required(CONF_CODE): str})


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PetSafe Integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the PetSafe config flow state."""
        self.data: dict[str, Any] = {}
        self._petsafe: Any | None = None
        self._client: Any | None = None
        self._id_token: str | None = None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._feeders: dict[str, str] | None = None
        self._litterboxes: dict[str, str] | None = None
        self._smartdoors: dict[str, str] | None = None

    async def _async_get_petsafe(self) -> Any:
        """Ensure the petsafe dependency is installed before importing it."""
        if self._petsafe is None:
            self._petsafe = await _async_import_petsafe(self.hass)

        return self._petsafe

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle reauthentication by restarting the user step."""
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the email entry step."""
        errors: dict[str, str] = {}

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

        try:
            petsafe = await self._async_get_petsafe()
        except ModuleNotFoundError, RequirementsNotFound:
            _LOGGER.exception("Unable to load the petsafe dependency during the user step")
            errors[CONF_BASE] = "cannot_connect"
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

        try:
            await self.get_email_code(petsafe, user_input[CONF_EMAIL])
            self.data = user_input
            return await self.async_step_code()
        except petsafe.client.InvalidUserException:
            errors[CONF_EMAIL] = "invalid_user"
        except Exception:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
            errors[CONF_BASE] = "cannot_connect"

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the confirmation code step."""
        errors: dict[str, str] = {}

        if user_input is None:
            return self.async_show_form(step_id="code", data_schema=STEP_CODE_DATA_SCHEMA)

        try:
            petsafe = await self._async_get_petsafe()
        except ModuleNotFoundError, RequirementsNotFound:
            _LOGGER.exception("Unable to load the petsafe dependency during the code step")
            errors[CONF_BASE] = "cannot_connect"
            return self.async_show_form(step_id="code", data_schema=STEP_CODE_DATA_SCHEMA, errors=errors)

        try:
            await self.get_devices(self.data[CONF_EMAIL], user_input[CONF_CODE])
            return await self.async_step_devices()
        except ParamValidationError:
            errors[CONF_CODE] = "invalid_code"
        except petsafe.client.InvalidCodeException:
            errors[CONF_CODE] = "invalid_code"
        except Exception:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
            errors[CONF_BASE] = "unknown_error"

        return self.async_show_form(step_id="code", data_schema=STEP_CODE_DATA_SCHEMA, errors=errors)

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle device selection after authentication succeeds."""
        if user_input is None:
            return self.async_show_form(
                step_id="devices",
                data_schema=vol.Schema(
                    {
                        vol.Required("feeders", default=list(self._feeders)): cv.multi_select(self._feeders),
                        vol.Required("litterboxes", default=list(self._litterboxes)): cv.multi_select(
                            self._litterboxes
                        ),
                        vol.Required("smartdoors", default=list(self._smartdoors)): cv.multi_select(self._smartdoors),
                    }
                ),
            )

        self.data.update(user_input)
        self.data[CONF_TOKEN] = self._id_token
        self.data[CONF_ACCESS_TOKEN] = self._access_token
        self.data[CONF_REFRESH_TOKEN] = self._refresh_token
        return self.async_create_entry(title=self.data[CONF_EMAIL], data=self.data)

    async def get_email_code(self, petsafe: Any, email: str) -> bool:
        """Request a one-time email code from the PetSafe API."""
        self._client = await self.hass.async_add_executor_job(partial(petsafe.PetSafeClient, email=email))
        await self._client.request_code()
        return True

    async def get_devices(self, _email: str, code: str) -> bool:
        """Exchange the code for tokens and load the user's devices."""
        await self._client.request_tokens_from_code(code)
        self._id_token = self._client.id_token
        self._access_token = self._client.access_token
        self._refresh_token = self._client.refresh_token

        self._feeders = {device.api_name: device.friendly_name for device in await self._client.get_feeders()}
        self._litterboxes = {device.api_name: device.friendly_name for device in await self._client.get_litterboxes()}
        self._smartdoors = {device.api_name: device.friendly_name for device in await self._client.get_smartdoors()}
        return True
