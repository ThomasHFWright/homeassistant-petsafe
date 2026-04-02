"""Pet/product link helpers for the coordinator."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import httpx

from custom_components.petsafe_extended.api import async_list_pet_products, async_list_pets
from custom_components.petsafe_extended.const import LOGGER
from custom_components.petsafe_extended.data import (
    PetSafeExtendedPetLinkData,
    PetSafeExtendedPetProductLink,
    PetSafeExtendedPetProfile,
)
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PET_LINK_REFRESH_INTERVAL = timedelta(hours=6)

_PET_ID_KEYS = ("petId", "petID", "id")
_PET_ID_ATTRS = ("pet_id", "id")
_PRODUCT_ID_KEYS = ("productId", "productID", "thingName", "thing_name", "id")
_PRODUCT_ID_ATTRS = ("api_name", "product_id", "thing_name", "id")

_PRODUCT_TYPE_FEEDER = "feeder"
_PRODUCT_TYPE_LITTERBOX = "litterbox"
_PRODUCT_TYPE_SMARTDOOR = "smartdoor"


def copy_pet_link_data(data: PetSafeExtendedPetLinkData | None) -> PetSafeExtendedPetLinkData:
    """Return a detached copy of pet link data."""
    if data is None:
        return PetSafeExtendedPetLinkData()
    return data.copy()


async def async_build_pet_link_data(
    hass: HomeAssistant,
    client: Any,
    feeders: list[Any],
    litterboxes: list[Any],
    smartdoors: list[Any],
    previous: PetSafeExtendedPetLinkData | None = None,
) -> PetSafeExtendedPetLinkData:
    """Build a generic pet-to-product linkage graph."""
    previous_data = copy_pet_link_data(previous)
    alias_to_canonical, product_type_by_product_id = _build_product_aliases(feeders, litterboxes, smartdoors)

    try:
        pets = _as_sequence(await async_list_pets(hass, client))
    except Exception as err:
        if _is_http_auth_error(err):
            raise
        LOGGER.debug("Failed to refresh PetSafe pet directory: %s", err)
        return previous_data

    pets_by_id: dict[str, PetSafeExtendedPetProfile] = {}
    pet_ids: list[str] = []
    for pet in pets:
        pet_id = _extract_identifier(pet, _PET_ID_KEYS, _PET_ID_ATTRS)
        if pet_id is None:
            continue
        pets_by_id[pet_id] = _build_pet_profile(pet, pet_id)
        pet_ids.append(pet_id)

    if not pet_ids:
        return PetSafeExtendedPetLinkData(
            pets_by_id=pets_by_id,
            product_type_by_product_id=dict(product_type_by_product_id),
            last_update=dt_util.utcnow(),
        )

    results = await asyncio.gather(
        *(async_list_pet_products(hass, client, pet_id) for pet_id in pet_ids),
        return_exceptions=True,
    )

    links: list[PetSafeExtendedPetProductLink] = []
    product_ids_by_pet_id: dict[str, tuple[str, ...]] = {}
    pet_ids_by_product_id: dict[str, set[str]] = defaultdict(set)

    for pet_id, result in zip(pet_ids, results, strict=True):
        if isinstance(result, Exception):
            if _is_http_auth_error(result):
                raise result
            LOGGER.debug("Failed to refresh PetSafe product links for pet %s: %s", pet_id, result)
            _restore_previous_links(
                pet_id,
                previous_data,
                links,
                product_ids_by_pet_id,
                pet_ids_by_product_id,
                product_type_by_product_id,
            )
            continue

        linked_product_ids: set[str] = set()
        for raw_product in _as_sequence(result):
            product_id = _resolve_product_id(raw_product, alias_to_canonical)
            if product_id is None:
                continue

            linked_product_ids.add(product_id)
            product_type = product_type_by_product_id.get(product_id) or _normalize_product_type(
                _get_first_text(raw_product, ("productType", "product_type", "type", "productName", "product_name"))
            )
            if product_type is not None:
                product_type_by_product_id.setdefault(product_id, product_type)

            links.append(
                PetSafeExtendedPetProductLink(
                    pet_id=pet_id,
                    product_id=product_id,
                    product_type=product_type_by_product_id.get(product_id),
                )
            )
            pet_ids_by_product_id[product_id].add(pet_id)

        product_ids_by_pet_id[pet_id] = tuple(sorted(linked_product_ids))

    return PetSafeExtendedPetLinkData(
        links=tuple(sorted(links, key=lambda link: (link.pet_id, link.product_id))),
        pets_by_id=pets_by_id,
        product_ids_by_pet_id={pet_id: tuple(product_ids) for pet_id, product_ids in product_ids_by_pet_id.items()},
        pet_ids_by_product_id={
            product_id: tuple(sorted(pet_ids)) for product_id, pet_ids in pet_ids_by_product_id.items()
        },
        product_type_by_product_id=dict(sorted(product_type_by_product_id.items())),
        last_update=dt_util.utcnow(),
    )


def _restore_previous_links(
    pet_id: str,
    previous: PetSafeExtendedPetLinkData,
    links: list[PetSafeExtendedPetProductLink],
    product_ids_by_pet_id: dict[str, tuple[str, ...]],
    pet_ids_by_product_id: dict[str, set[str]],
    product_type_by_product_id: dict[str, str],
) -> None:
    """Restore previously known links for a pet after a partial refresh failure."""
    product_ids = previous.product_ids_by_pet_id.get(pet_id, ())
    product_ids_by_pet_id[pet_id] = tuple(product_ids)
    for product_id in product_ids:
        product_type = previous.product_type_by_product_id.get(product_id)
        if product_type is not None:
            product_type_by_product_id.setdefault(product_id, product_type)
        links.append(
            PetSafeExtendedPetProductLink(
                pet_id=pet_id,
                product_id=product_id,
                product_type=product_type_by_product_id.get(product_id),
            )
        )
        pet_ids_by_product_id[product_id].add(pet_id)


def _build_product_aliases(
    feeders: list[Any],
    litterboxes: list[Any],
    smartdoors: list[Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build alias mappings so pet products resolve to known device keys."""
    alias_to_canonical: dict[str, str] = {}
    product_type_by_product_id: dict[str, str] = {}

    for product_type, devices in (
        (_PRODUCT_TYPE_FEEDER, feeders),
        (_PRODUCT_TYPE_LITTERBOX, litterboxes),
        (_PRODUCT_TYPE_SMARTDOOR, smartdoors),
    ):
        for device in devices:
            canonical = _get_device_canonical_id(device)
            if canonical is None:
                continue

            product_type_by_product_id[canonical] = product_type
            for alias in _collect_identifiers(device, _PRODUCT_ID_KEYS, _PRODUCT_ID_ATTRS):
                alias_to_canonical.setdefault(alias, canonical)

    return alias_to_canonical, product_type_by_product_id


def _resolve_product_id(raw_product: Any, alias_to_canonical: dict[str, str]) -> str | None:
    """Resolve a pet-product payload to the integration's canonical product key."""
    for candidate in _collect_identifiers(raw_product, _PRODUCT_ID_KEYS, _PRODUCT_ID_ATTRS):
        return alias_to_canonical.get(candidate, candidate)
    return None


def _get_device_canonical_id(device: Any) -> str | None:
    """Return the product identifier used by the integration for a device."""
    api_name = getattr(device, "api_name", None)
    if isinstance(api_name, str) and api_name.strip():
        return api_name.strip()
    return _extract_identifier(device, _PRODUCT_ID_KEYS, _PRODUCT_ID_ATTRS)


def _build_pet_profile(pet: Any, pet_id: str) -> PetSafeExtendedPetProfile:
    """Build a sanitized pet profile from a petsafe-api payload."""
    weight_value = _get_first_numeric(pet, ("weight", "weightValue", "weight_value"))
    return PetSafeExtendedPetProfile(
        pet_id=pet_id,
        name=_get_first_text(pet, ("name", "petName", "friendlyName")),
        pet_type=_get_first_text(pet, ("petType", "type", "species")),
        breed=_get_first_text(pet, ("breed",)),
        gender=_get_first_text(pet, ("gender", "sex")),
        weight=weight_value,
        weight_unit=_get_first_text(pet, ("weightUnit", "weight_unit")),
        technology=_get_first_text(pet, ("technology", "tagType", "tag_type")),
    )


def _collect_identifiers(value: Any, mapping_keys: Sequence[str], attr_keys: Sequence[str]) -> tuple[str, ...]:
    """Collect identifier aliases from a mapping-like payload or device object."""
    candidates: list[str] = []
    for source in (value, getattr(value, "data", None)):
        if not isinstance(source, Mapping):
            continue
        for key in mapping_keys:
            _append_identifier(candidates, source.get(key))

    for attr in attr_keys:
        _append_identifier(candidates, getattr(value, attr, None))

    return tuple(candidates)


def _extract_identifier(value: Any, mapping_keys: Sequence[str], attr_keys: Sequence[str]) -> str | None:
    """Extract the first identifier alias from an object."""
    identifiers = _collect_identifiers(value, mapping_keys, attr_keys)
    return identifiers[0] if identifiers else None


def _append_identifier(candidates: list[str], value: Any) -> None:
    """Append a stringified identifier if it is present and unique."""
    if value is None:
        return
    if isinstance(value, str):
        identifier = value.strip()
    elif isinstance(value, int | float):
        identifier = str(value)
    else:
        return

    if identifier and identifier not in candidates:
        candidates.append(identifier)


def _get_first_text(value: Any, keys: Sequence[str]) -> str | None:
    """Return the first non-empty text field from a payload."""
    for source in (value, getattr(value, "data", None)):
        if not isinstance(source, Mapping):
            continue
        for key in keys:
            candidate = source.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def _get_first_numeric(value: Any, keys: Sequence[str]) -> float | None:
    """Return the first numeric field from a payload."""
    for source in (value, getattr(value, "data", None)):
        if not isinstance(source, Mapping):
            continue
        for key in keys:
            candidate = source.get(key)
            if isinstance(candidate, int | float):
                return float(candidate)
    return None


def _normalize_product_type(value: str | None) -> str | None:
    """Normalize PetSafe product labels into stable internal types."""
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "").replace(" ", "")
    if not normalized:
        return None
    if "door" in normalized:
        return _PRODUCT_TYPE_SMARTDOOR
    if "feed" in normalized:
        return _PRODUCT_TYPE_FEEDER
    if "scoop" in normalized or "litter" in normalized:
        return _PRODUCT_TYPE_LITTERBOX
    if "track" in normalized:
        return "tracker"
    return value.strip().lower()


def _as_sequence(value: Any) -> list[Any]:
    """Coerce a petsafe-api response into a list of payload items."""
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _is_http_auth_error(error: Exception) -> bool:
    """Return whether an exception is an HTTP auth failure."""
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {401, 403}
