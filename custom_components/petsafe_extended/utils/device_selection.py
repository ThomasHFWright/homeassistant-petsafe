"""Helpers for selecting configured PetSafe devices."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from custom_components.petsafe_extended.const import DOMAIN, FEEDER_MODEL_GEN1, FEEDER_MODEL_GEN2
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry

_T = TypeVar("_T")


def filter_selected_devices(devices: Iterable[_T], selected_ids: list[str] | None) -> list[_T]:
    """Filter devices by selected API names."""
    device_list = list(devices)
    if selected_ids is None:
        return device_list

    selected = set(selected_ids)
    return [device for device in device_list if getattr(device, "api_name", None) in selected]


def get_feeders_for_service(
    hass: HomeAssistant,
    area_ids: list[str] | None,
    device_ids: list[str] | None,
    entity_ids: list[str] | None,
) -> list[str]:
    """Return feeder API names matched from service targeting fields."""
    matched_devices: list[str] = []
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    if area_ids is not None:
        matched_devices = get_feeders_by_area_id(hass, device_reg, entity_reg, area_ids, matched_devices)
    if device_ids is not None:
        matched_devices = get_feeders_by_device_id(hass, device_reg, device_ids, matched_devices)
    if entity_ids is not None:
        matched_devices = get_feeders_by_entity_id(hass, device_reg, entity_reg, entity_ids, matched_devices)

    return matched_devices


def get_feeders_by_area_id(
    hass: HomeAssistant,
    device_reg: DeviceRegistry,
    entity_reg: er.EntityRegistry,
    area_ids: list[str],
    matched_devices: list[str] | None = None,
) -> list[str]:
    """Return feeder API names matched from Home Assistant area IDs."""
    matched = [] if matched_devices is None else matched_devices

    for area_id in area_ids:
        device_ids = [device.id for device in dr.async_entries_for_area(device_reg, area_id)]
        entity_ids = [entity.id for entity in er.async_entries_for_area(entity_reg, area_id)]

        for api_name in get_feeders_by_device_id(hass, device_reg, device_ids):
            if api_name not in matched:
                matched.append(api_name)

        for api_name in get_feeders_by_entity_id(hass, device_reg, entity_reg, entity_ids):
            if api_name not in matched:
                matched.append(api_name)

    return matched


def get_feeders_by_device_id(
    hass: HomeAssistant,
    device_reg: DeviceRegistry,
    device_ids: list[str],
    matched_devices: list[str] | None = None,
) -> list[str]:
    """Return feeder API names matched from Home Assistant device IDs."""
    matched = [] if matched_devices is None else matched_devices

    for device_id in device_ids:
        device_entry = device_reg.async_get(device_id)
        if not is_device_feeder(hass, device_entry):
            continue
        if device_entry is None:
            continue

        for identifier_domain, identifier_value in device_entry.identifiers:
            if identifier_domain == DOMAIN and identifier_value not in matched:
                matched.append(identifier_value)

    return matched


def get_feeders_by_entity_id(
    hass: HomeAssistant,
    device_reg: DeviceRegistry,
    entity_reg: er.EntityRegistry,
    entity_ids: list[str],
    matched_devices: list[str] | None = None,
) -> list[str]:
    """Return feeder API names matched from Home Assistant entity IDs."""
    matched = [] if matched_devices is None else matched_devices

    for entity_id in entity_ids:
        entity_entry = entity_reg.async_get(entity_id)
        if entity_entry is None or entity_entry.device_id is None:
            continue

        for api_name in get_feeders_by_device_id(hass, device_reg, [entity_entry.device_id]):
            if api_name not in matched:
                matched.append(api_name)

    return matched


def is_device_feeder(hass: HomeAssistant, device: DeviceEntry | None) -> bool:
    """Return whether a Home Assistant device entry represents a loaded feeder."""
    if device is None or device.model not in {FEEDER_MODEL_GEN1, FEEDER_MODEL_GEN2}:
        return False

    for config_entry in hass.config_entries.async_entries(DOMAIN):
        if config_entry.entry_id not in device.config_entries:
            continue
        if getattr(config_entry, "runtime_data", None) is None:
            return False
        return True

    return False
