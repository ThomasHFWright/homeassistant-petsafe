"""Helper utilities for targeting PetSafe feeder devices."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry

from .const import DOMAIN, FEEDER_MODEL_GEN1, FEEDER_MODEL_GEN2

_T = TypeVar("_T")


def filter_selected_devices(devices: Iterable[_T], selected_ids: list[str] | None) -> list[_T]:
    """Filter devices by selected API names.

    A missing selection means all devices for backward compatibility.
    An empty list means the user explicitly selected none.
    """
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
        matched_devices = get_feeders_by_area_id(
            hass,
            device_reg,
            entity_reg,
            area_ids,
            matched_devices,
        )
    if device_ids is not None:
        matched_devices = get_feeders_by_device_id(
            hass,
            device_reg,
            device_ids,
            matched_devices,
        )
    if entity_ids is not None:
        matched_devices = get_feeders_by_entity_id(
            hass,
            device_reg,
            entity_reg,
            entity_ids,
            matched_devices,
        )

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
        devices = dr.async_entries_for_area(device_reg, area_id)
        device_ids: list[str] = []
        for device in devices:
            if device.id not in device_ids:
                device_ids.append(device.id)

        entities = er.async_entries_for_area(entity_reg, area_id)
        entity_ids: list[str] = []
        for entity in entities:
            if entity.id not in entity_ids:
                entity_ids.append(entity.id)

        devices_from_registry = get_feeders_by_device_id(hass, device_reg, device_ids)
        for api_name in devices_from_registry:
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

        api_name = next(iter(device_entry.identifiers))[1]
        if api_name not in matched:
            matched.append(api_name)

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
        if entity_entry is None:
            continue

        for api_name in get_feeders_by_device_id(hass, device_reg, [entity_entry.device_id]):
            if api_name not in matched:
                matched.append(api_name)

    return matched


def is_device_feeder(hass: HomeAssistant, device: DeviceEntry | None) -> bool:
    """Return whether a Home Assistant device entry represents a loaded feeder."""
    if device is None or device.model not in [FEEDER_MODEL_GEN1, FEEDER_MODEL_GEN2]:
        return False

    config_entry_ids = device.config_entries
    entry = next(
        (
            config_entry
            for config_entry in hass.config_entries.async_entries(DOMAIN)
            if config_entry.entry_id in config_entry_ids
        ),
        None,
    )
    if entry and entry.state != ConfigEntryState.LOADED:
        return False
    if entry is None or DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        return False

    return True
