"""Helpers for PetSafe pet directory endpoints."""

from __future__ import annotations

import importlib
from typing import Any, cast

from homeassistant.core import HomeAssistant


async def _async_import_pets_module(hass: HomeAssistant) -> Any:
    """Import the optional petsafe.pets module on demand."""
    return await hass.async_add_executor_job(importlib.import_module, "petsafe.pets")


async def async_list_pets(hass: HomeAssistant, client: Any) -> list[Any]:
    """Return the pets visible to the authenticated account."""
    pets_module = await _async_import_pets_module(hass)
    return await cast(Any, pets_module.list_pets)(client)


async def async_list_pet_products(hass: HomeAssistant, client: Any, pet_id: str) -> list[Any]:
    """Return the products linked to a PetSafe pet."""
    pets_module = await _async_import_pets_module(hass)
    return await cast(Any, pets_module.list_pet_products)(client, pet_id)
