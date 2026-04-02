"""Service registration for petsafe_extended."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, cast

from custom_components.petsafe_extended.const import (
    ATTR_AMOUNT,
    ATTR_SLOW_FEED,
    ATTR_TIME,
    DOMAIN,
    LOGGER,
    SERVICE_ADD_SCHEDULE,
    SERVICE_DELETE_ALL_SCHEDULES,
    SERVICE_DELETE_SCHEDULE,
    SERVICE_FEED,
    SERVICE_MODIFY_SCHEDULE,
    SERVICE_PRIME,
)
from custom_components.petsafe_extended.coordinator import PetSafeExtendedDataUpdateCoordinator
from custom_components.petsafe_extended.utils import get_feeders_for_service
from homeassistant.const import ATTR_AREA_ID, ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import ServiceCall

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _service_targets(call: ServiceCall) -> tuple[list[str] | None, list[str] | None, list[str] | None]:
    """Extract Home Assistant service target selectors."""
    return (
        cast(list[str] | None, call.data.get(ATTR_AREA_ID)),
        cast(list[str] | None, call.data.get(ATTR_DEVICE_ID)),
        cast(list[str] | None, call.data.get(ATTR_ENTITY_ID)),
    )


async def _resolve_targeted_feeders(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[PetSafeExtendedDataUpdateCoordinator, list[str]]:
    """Resolve service targets to loaded feeder API names grouped by coordinator."""
    area_ids, device_ids, entity_ids = _service_targets(call)
    matched_api_names = get_feeders_for_service(hass, area_ids, device_ids, entity_ids)
    coordinators: dict[PetSafeExtendedDataUpdateCoordinator, list[str]] = defaultdict(list)

    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime_data = getattr(entry, "runtime_data", None)
        if runtime_data is None:
            continue

        coordinator = runtime_data.coordinator
        feeders = await coordinator.get_feeders()
        for feeder in feeders:
            if feeder.api_name in matched_api_names:
                coordinators[coordinator].append(feeder.api_name)

    return coordinators


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register feeder services at component level."""

    async def handle_add_schedule(call: ServiceCall) -> None:
        """Add a schedule to each targeted feeder."""
        coordinators = await _resolve_targeted_feeders(hass, call)
        feed_time = cast(str, call.data[ATTR_TIME])
        amount = cast(int, call.data[ATTR_AMOUNT])
        for coordinator, api_names in coordinators.items():
            for api_name in api_names:
                await coordinator.async_add_feeding_schedule(api_name, feed_time, amount, refresh=False)
            await coordinator.async_request_refresh()

    async def handle_delete_schedule(call: ServiceCall) -> None:
        """Delete a schedule from each targeted feeder."""
        coordinators = await _resolve_targeted_feeders(hass, call)
        feed_time = cast(str, call.data[ATTR_TIME])
        for coordinator, api_names in coordinators.items():
            for api_name in api_names:
                await coordinator.async_delete_feeding_schedule(api_name, feed_time, refresh=False)
            await coordinator.async_request_refresh()

    async def handle_delete_all_schedules(call: ServiceCall) -> None:
        """Delete all schedules from each targeted feeder."""
        coordinators = await _resolve_targeted_feeders(hass, call)
        for coordinator, api_names in coordinators.items():
            for api_name in api_names:
                await coordinator.async_delete_all_feeding_schedules(api_name, refresh=False)
            await coordinator.async_request_refresh()

    async def handle_modify_schedule(call: ServiceCall) -> None:
        """Modify a schedule on each targeted feeder."""
        coordinators = await _resolve_targeted_feeders(hass, call)
        feed_time = cast(str, call.data[ATTR_TIME])
        amount = cast(int, call.data[ATTR_AMOUNT])
        for coordinator, api_names in coordinators.items():
            for api_name in api_names:
                await coordinator.async_modify_feeding_schedule(api_name, feed_time, amount, refresh=False)
            await coordinator.async_request_refresh()

    async def handle_feed(call: ServiceCall) -> None:
        """Trigger a manual feed on each targeted feeder."""
        coordinators = await _resolve_targeted_feeders(hass, call)
        amount = cast(int, call.data[ATTR_AMOUNT])
        slow_feed = cast(bool | None, call.data.get(ATTR_SLOW_FEED))
        for coordinator, api_names in coordinators.items():
            for api_name in api_names:
                await coordinator.async_feed_feeder(api_name, amount, slow_feed, refresh=False)
            await coordinator.async_request_refresh()

    async def handle_prime(call: ServiceCall) -> None:
        """Prime each targeted feeder."""
        coordinators = await _resolve_targeted_feeders(hass, call)
        for coordinator, api_names in coordinators.items():
            for api_name in api_names:
                await coordinator.async_prime_feeder(api_name, refresh=False)
            await coordinator.async_request_refresh()

    services: dict[str, Any] = {
        SERVICE_ADD_SCHEDULE: handle_add_schedule,
        SERVICE_DELETE_SCHEDULE: handle_delete_schedule,
        SERVICE_DELETE_ALL_SCHEDULES: handle_delete_all_schedules,
        SERVICE_MODIFY_SCHEDULE: handle_modify_schedule,
        SERVICE_FEED: handle_feed,
        SERVICE_PRIME: handle_prime,
    }

    for service_name, handler in services.items():
        if hass.services.has_service(DOMAIN, service_name):
            continue
        hass.services.async_register(DOMAIN, service_name, handler)

    LOGGER.debug("Registered PetSafe services")
