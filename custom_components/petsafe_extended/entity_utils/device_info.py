"""Device info utilities for petsafe_extended."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from custom_components.petsafe_extended.const import DOMAIN, FEEDER_MODEL_GEN1, MANUFACTURER
from homeassistant.helpers.device_registry import DeviceInfo


def create_device_info_from_device(device: Any, *, default_model: str | None = None) -> DeviceInfo:
    """Create DeviceInfo for a PetSafe device object."""
    data = getattr(device, "data", {})
    api_name = cast(str, device.api_name)
    model = (
        getattr(device, "product_name", None) or _get_string(data, "productName") or default_model or FEEDER_MODEL_GEN1
    )
    return DeviceInfo(
        identifiers={(DOMAIN, api_name)},
        manufacturer=MANUFACTURER,
        name=getattr(device, "friendly_name", None) or _get_string(data, "friendlyName") or api_name,
        model=model,
        sw_version=getattr(device, "firmware", None),
    )


def _get_string(data: Any, key: str) -> str | None:
    """Return a non-empty string value from a mapping."""
    if not isinstance(data, Mapping):
        return None
    value = data.get(key)
    return value if isinstance(value, str) and value else None
