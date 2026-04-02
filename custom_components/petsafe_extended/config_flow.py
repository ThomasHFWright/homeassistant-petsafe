"""Config flow for PetSafe Extended."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
import logging
from typing import Any

from botocore.exceptions import ParamValidationError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_BASE, CONF_CODE, CONF_EMAIL, CONF_TOKEN
import homeassistant.helpers.config_validation as cv
from homeassistant.requirements import RequirementsNotFound

from . import _async_import_petsafe
from .const import CONF_REFRESH_TOKEN, DOMAIN
from .utils.auth import build_account_unique_id

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str})
STEP_CODE_DATA_SCHEMA = vol.Schema({vol.Required(CONF_CODE): str})


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PetSafe Extended."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow state."""
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

    async def _async_exchange_code(self, code: str, *, step_id: str) -> str | None:
        """Exchange a confirmation code for tokens and device metadata."""
        try:
            petsafe = await self._async_get_petsafe()
        except ModuleNotFoundError, RequirementsNotFound:
            _LOGGER.exception("Unable to load the petsafe dependency during the %s step", step_id)
            return "cannot_connect"

        try:
            await self._async_load_devices(code)
        except ParamValidationError:
            return "invalid_code"
        except petsafe.client.InvalidCodeException:
            return "invalid_code"
        except Exception:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
            return "unknown_error"

        return None

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication for an existing PetSafe entry."""
        del entry_data
        self.data = dict(self._get_reauth_entry().data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the confirmation code step during reauthentication."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        email = reauth_entry.data[CONF_EMAIL]

        if user_input is None:
            try:
                petsafe = await self._async_get_petsafe()
                await self._async_request_email_code(petsafe, email)
            except ModuleNotFoundError, RequirementsNotFound:
                _LOGGER.exception("Unable to load the petsafe dependency during the reauth step")
                errors[CONF_BASE] = "cannot_connect"
            except Exception:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
                errors[CONF_BASE] = "cannot_connect"

            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_CODE_DATA_SCHEMA,
                errors=errors,
                description_placeholders={CONF_EMAIL: email},
            )

        if error := await self._async_exchange_code(user_input[CONF_CODE], step_id="reauth_confirm"):
            errors[CONF_CODE if error == "invalid_code" else CONF_BASE] = error
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_CODE_DATA_SCHEMA,
                errors=errors,
                description_placeholders={CONF_EMAIL: email},
            )

        return self.async_update_reload_and_abort(
            reauth_entry,
            title=email,
            unique_id=build_account_unique_id(email, self._id_token),
            data_updates={
                CONF_TOKEN: self._id_token,
                CONF_ACCESS_TOKEN: self._access_token,
                CONF_REFRESH_TOKEN: self._refresh_token,
            },
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
            await self._async_request_email_code(petsafe, user_input[CONF_EMAIL])
            self.data = {CONF_EMAIL: user_input[CONF_EMAIL]}
            return await self.async_step_code()
        except petsafe.client.InvalidUserException:
            errors[CONF_EMAIL] = "invalid_user"
        except Exception:  # noqa: BLE001 - petsafe-api raises broad runtime exceptions here.
            errors[CONF_BASE] = "cannot_connect"

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the confirmation code step."""
        errors: dict[str, str] = {}

        if user_input is None:
            return self.async_show_form(step_id="code", data_schema=STEP_CODE_DATA_SCHEMA)

        if error := await self._async_exchange_code(user_input[CONF_CODE], step_id="code"):
            errors[CONF_CODE if error == "invalid_code" else CONF_BASE] = error
            return self.async_show_form(step_id="code", data_schema=STEP_CODE_DATA_SCHEMA, errors=errors)

        await self.async_set_unique_id(build_account_unique_id(self.data[CONF_EMAIL], self._id_token))
        self._abort_if_unique_id_configured()
        return await self.async_step_devices()

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle device selection after authentication succeeds."""
        if user_input is None:
            return self.async_show_form(
                step_id="devices",
                data_schema=vol.Schema(
                    {
                        vol.Required("feeders", default=list(self._feeders or {})): cv.multi_select(
                            self._feeders or {}
                        ),
                        vol.Required("litterboxes", default=list(self._litterboxes or {})): cv.multi_select(
                            self._litterboxes or {}
                        ),
                        vol.Required("smartdoors", default=list(self._smartdoors or {})): cv.multi_select(
                            self._smartdoors or {}
                        ),
                    }
                ),
            )

        self.data.update(user_input)
        self.data[CONF_TOKEN] = self._id_token
        self.data[CONF_ACCESS_TOKEN] = self._access_token
        self.data[CONF_REFRESH_TOKEN] = self._refresh_token
        return self.async_create_entry(title=self.data[CONF_EMAIL], data=self.data)

    async def _async_request_email_code(self, petsafe: Any, email: str) -> None:
        """Request a one-time email code from the PetSafe API."""
        self._client = await self.hass.async_add_executor_job(partial(petsafe.PetSafeClient, email=email))
        if self._client is None:
            raise RuntimeError("PetSafe client was not initialized")
        await self._client.request_code()

    async def _async_load_devices(self, code: str) -> None:
        """Exchange the code for tokens and load the user's devices."""
        if self._client is None:
            raise RuntimeError("PetSafe client was not initialized")

        await self._client.request_tokens_from_code(code)
        self._id_token = self._client.id_token
        self._access_token = self._client.access_token
        self._refresh_token = self._client.refresh_token

        self._feeders = {device.api_name: device.friendly_name for device in await self._client.get_feeders()}
        self._litterboxes = {device.api_name: device.friendly_name for device in await self._client.get_litterboxes()}
        self._smartdoors = {device.api_name: device.friendly_name for device in await self._client.get_smartdoors()}


__all__ = ["ConfigFlow"]
