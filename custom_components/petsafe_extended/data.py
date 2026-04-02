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


@dataclass(slots=True)
class PetSafeExtendedCoordinatorData:
    """Snapshot of PetSafe device state held by the coordinator."""

    feeders: list[Any] = field(default_factory=list)
    litterboxes: list[Any] = field(default_factory=list)
    smartdoors: list[Any] = field(default_factory=list)
    feeder_details: dict[str, PetSafeExtendedFeederDetails] = field(default_factory=dict)
    litterbox_details: dict[str, PetSafeExtendedLitterboxDetails] = field(default_factory=dict)


@dataclass(slots=True)
class PetSafeExtendedRuntimeData:
    """Runtime objects attached to a loaded config entry."""

    client: Any
    coordinator: PetSafeExtendedDataUpdateCoordinator
    integration: Integration
