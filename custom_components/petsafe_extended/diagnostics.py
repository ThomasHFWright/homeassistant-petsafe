"""Diagnostics support for petsafe_extended."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_ACCESS_TOKEN, CONF_EMAIL, CONF_TOKEN
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_REFRESH_TOKEN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import PetSafeExtendedConfigEntry

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: PetSafeExtendedConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    integration = entry.runtime_data.integration

    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_reg, entry.entry_id)

    device_info = []
    for device in devices:
        entities = er.async_entries_for_device(entity_reg, device.id)
        device_info.append(
            {
                "id": device.id,
                "name": device.name,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "sw_version": device.sw_version,
                "entity_count": len(entities),
                "entities": [
                    {
                        "entity_id": entity.entity_id,
                        "platform": entity.platform,
                        "original_name": entity.original_name,
                        "disabled": entity.disabled,
                        "disabled_by": entity.disabled_by.value if entity.disabled_by else None,
                    }
                    for entity in entities
                ],
            }
        )

    data_summary = {
        "feeders": len(coordinator.data.feeders) if coordinator.data else 0,
        "litterboxes": len(coordinator.data.litterboxes) if coordinator.data else 0,
        "smartdoors": len(coordinator.data.smartdoors) if coordinator.data else 0,
        "feeder_details": len(coordinator.data.feeder_details) if coordinator.data else 0,
        "litterbox_details": len(coordinator.data.litterbox_details) if coordinator.data else 0,
        "pet_profiles": len(coordinator.data.pet_links.pets_by_id) if coordinator.data else 0,
        "pet_product_links": len(coordinator.data.pet_links.links) if coordinator.data else 0,
        "linked_products": len(coordinator.data.pet_links.pet_ids_by_product_id) if coordinator.data else 0,
        "smartdoor_activity_doors": len(coordinator.data.smartdoor_activity_records) if coordinator.data else 0,
        "smartdoor_pet_states": (
            sum(len(states) for states in coordinator.data.smartdoor_pet_states.values()) if coordinator.data else 0
        ),
        "smartdoor_schedule_doors": len(coordinator.data.smartdoor_schedule_rules) if coordinator.data else 0,
        "smartdoor_schedule_rules": (
            sum(len(rules) for rules in coordinator.data.smartdoor_schedule_rules.values()) if coordinator.data else 0
        ),
        "smartdoor_scheduled_pets": (
            sum(summary.scheduled_pet_count for summary in coordinator.data.smartdoor_schedule_summaries.values())
            if coordinator.data
            else 0
        ),
        "smartdoor_schedule_summaries": len(coordinator.data.smartdoor_schedule_summaries) if coordinator.data else 0,
        "smartdoor_pet_schedule_states": (
            sum(len(states) for states in coordinator.data.smartdoor_pet_schedule_states.values())
            if coordinator.data
            else 0
        ),
        "pet_links_last_update": (
            coordinator.data.pet_links.last_update.isoformat()
            if coordinator.data and coordinator.data.pet_links.last_update
            else None
        ),
    }

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "domain": entry.domain,
            "title": entry.title,
            "state": str(entry.state),
            "unique_id": entry.unique_id,
            "disabled_by": entry.disabled_by.value if entry.disabled_by else None,
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "integration": {
            "name": integration.name,
            "version": integration.version,
            "domain": integration.domain,
            "documentation": integration.documentation,
            "issue_tracker": integration.issue_tracker,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "last_exception": type(coordinator.last_exception).__name__ if coordinator.last_exception else None,
        },
        "devices": device_info,
        "data_summary": data_summary,
    }
