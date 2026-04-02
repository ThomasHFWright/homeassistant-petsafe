"""Runtime and coordinator data models for petsafe_extended."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .coordinator import PetSafeExtendedDataUpdateCoordinator


type PetSafeExtendedConfigEntry = ConfigEntry["PetSafeExtendedRuntimeData"]


@dataclass(slots=True)
class PetSafeExtendedFeederDetails:
    """Supplemental feeder state fetched outside the base device list call."""

    last_feeding: datetime | None = None
    next_feeding: datetime | None = None


@dataclass(slots=True)
class PetSafeExtendedLitterboxDetails:
    """Supplemental litterbox state fetched from activity history."""

    last_cleaning: datetime | None = None
    rake_status: str | None = None


@dataclass(slots=True, frozen=True)
class PetSafeExtendedPetProductLink:
    """A normalized association between a pet and a PetSafe product."""

    pet_id: str
    product_id: str
    product_type: str | None = None


@dataclass(slots=True)
class PetSafeExtendedPetProfile:
    """Sanitized pet metadata kept for future entity creation."""

    pet_id: str
    name: str | None = None
    pet_type: str | None = None
    breed: str | None = None
    gender: str | None = None
    weight: float | None = None
    weight_unit: str | None = None
    technology: str | None = None


@dataclass(slots=True)
class PetSafeExtendedPetLinkData:
    """Generic pet-to-product linkage shared across product types."""

    links: tuple[PetSafeExtendedPetProductLink, ...] = ()
    pets_by_id: dict[str, PetSafeExtendedPetProfile] = field(default_factory=dict)
    product_ids_by_pet_id: dict[str, tuple[str, ...]] = field(default_factory=dict)
    pet_ids_by_product_id: dict[str, tuple[str, ...]] = field(default_factory=dict)
    product_type_by_product_id: dict[str, str] = field(default_factory=dict)
    last_update: datetime | None = None

    def copy(self) -> PetSafeExtendedPetLinkData:
        """Return a detached copy safe for coordinator snapshots."""
        return PetSafeExtendedPetLinkData(
            links=tuple(self.links),
            pets_by_id=dict(self.pets_by_id),
            product_ids_by_pet_id={
                pet_id: tuple(product_ids) for pet_id, product_ids in self.product_ids_by_pet_id.items()
            },
            pet_ids_by_product_id={
                product_id: tuple(pet_ids) for product_id, pet_ids in self.pet_ids_by_product_id.items()
            },
            product_type_by_product_id=dict(self.product_type_by_product_id),
            last_update=self.last_update,
        )


@dataclass(slots=True)
class PetSafeExtendedCoordinatorData:
    """Snapshot of PetSafe device state held by the coordinator."""

    feeders: list[Any] = field(default_factory=list)
    litterboxes: list[Any] = field(default_factory=list)
    smartdoors: list[Any] = field(default_factory=list)
    feeder_details: dict[str, PetSafeExtendedFeederDetails] = field(default_factory=dict)
    litterbox_details: dict[str, PetSafeExtendedLitterboxDetails] = field(default_factory=dict)
    pet_links: PetSafeExtendedPetLinkData = field(default_factory=PetSafeExtendedPetLinkData)


@dataclass(slots=True)
class PetSafeExtendedRuntimeData:
    """Runtime objects attached to a loaded config entry."""

    client: Any
    coordinator: PetSafeExtendedDataUpdateCoordinator
    integration: Integration
