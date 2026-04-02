"""Litterbox select entities for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory

LITTERBOX_SELECT_DESCRIPTIONS: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(
        key="rake_timer",
        name="Rake Timer",
        options=["5", "10", "15", "20", "25", "30"],
        entity_category=EntityCategory.CONFIG,
    ),
)


class PetSafeExtendedLitterboxSelect(SelectEntity, PetSafeExtendedEntity):
    """Representation of a litterbox rake-timer select."""

    def __init__(self, coordinator: Any, litterbox: Any, description: SelectEntityDescription) -> None:
        """Initialize the litterbox select."""
        super().__init__(coordinator, litterbox.api_name, description, litterbox)

    @property
    def current_option(self) -> str | None:
        """Return the current option."""
        litterbox = self._get_litterbox()
        if litterbox is None:
            return None
        reported_state = litterbox.data.get("shadow", {}).get("state", {}).get("reported", {})
        delay = reported_state.get("rakeDelayTime")
        return str(delay) if delay is not None else None

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return super().available and self._get_litterbox() is not None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.coordinator.async_set_litterbox_rake_timer(self._api_name, int(option))

    def _get_litterbox(self) -> Any | None:
        """Return the current litterbox object from coordinator data."""
        if self.coordinator.data is None:
            return None
        return next(
            (litterbox for litterbox in self.coordinator.data.litterboxes if litterbox.api_name == self._api_name),
            None,
        )
