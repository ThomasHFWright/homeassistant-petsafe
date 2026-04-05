"""Feeder switch entities for petsafe_extended."""

from __future__ import annotations

from typing import Any

from custom_components.petsafe_extended.const import FEEDER_MODEL_GEN1
from custom_components.petsafe_extended.entity import PetSafeExtendedEntity
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory

FEEDER_SWITCH_DESCRIPTIONS: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="feeding_paused",
        name="Feeding Paused",
        icon="mdi:pause",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="child_lock",
        name="Child Lock",
        icon="mdi:lock-open",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="slow_feed",
        name="Slow Feed",
        icon="mdi:tortoise",
        entity_category=EntityCategory.CONFIG,
    ),
)


class PetSafeExtendedFeederSwitch(SwitchEntity, PetSafeExtendedEntity):
    """Representation of a feeder switch."""

    def __init__(self, coordinator: Any, feeder: Any, description: SwitchEntityDescription) -> None:
        """Initialize the feeder switch."""
        super().__init__(
            coordinator,
            feeder.api_name,
            description,
            feeder,
            default_model=FEEDER_MODEL_GEN1,
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether the switch is enabled."""
        feeder = self._get_feeder()
        if feeder is None:
            return None
        if self.entity_description.key == "child_lock":
            return feeder.is_locked
        if self.entity_description.key == "feeding_paused":
            return feeder.is_paused
        if self.entity_description.key == "slow_feed":
            return feeder.is_slow_feed
        return None

    @property
    def icon(self) -> str | None:
        """Return the icon for the current switch state."""
        if self.entity_description.key == "child_lock":
            return "mdi:lock" if self.is_on else "mdi:lock-open"
        return self.entity_description.icon

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return super().available and self._get_feeder() is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        del kwargs
        if self.entity_description.key == "child_lock":
            await self.coordinator.async_set_feeder_child_lock(self._api_name, True)
        elif self.entity_description.key == "feeding_paused":
            await self.coordinator.async_set_feeder_paused(self._api_name, True)
        else:
            await self.coordinator.async_set_feeder_slow_feed(self._api_name, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        del kwargs
        if self.entity_description.key == "child_lock":
            await self.coordinator.async_set_feeder_child_lock(self._api_name, False)
        elif self.entity_description.key == "feeding_paused":
            await self.coordinator.async_set_feeder_paused(self._api_name, False)
        else:
            await self.coordinator.async_set_feeder_slow_feed(self._api_name, False)

    def _get_feeder(self) -> Any | None:
        """Return the current feeder object from coordinator data."""
        if self.coordinator.data is None:
            return None
        return next((feeder for feeder in self.coordinator.data.feeders if feeder.api_name == self._api_name), None)
