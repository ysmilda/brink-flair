"""Installer switches for the Brink Flair integration."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import FlairDevice, FlairState

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class BrinkFlairSwitchDescription(SwitchEntityDescription):
    """Describes a Brink Flair switch."""

    value_fn: Callable[[FlairState], bool | None]
    set_fn: Callable[[FlairDevice, bool], Coroutine[Any, Any, None]]


# Installer settings, so they start disabled.
SWITCHES: tuple[BrinkFlairSwitchDescription, ...] = (
    BrinkFlairSwitchDescription(
        key="imbalance_allowed",
        translation_key="imbalance_allowed",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.imbalance_allowed,
        set_fn=lambda device, on: device.async_set_imbalance_allowed(on),
    ),
    BrinkFlairSwitchDescription(
        key="geo_heat_exchanger",
        translation_key="geo_heat_exchanger",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.geo_heat_exchanger,
        set_fn=lambda device, on: device.async_set_geo_heat_exchanger(on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrinkFlairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        BrinkFlairSwitch(coordinator, description) for description in SWITCHES
    )


class BrinkFlairSwitch(BrinkFlairEntity, SwitchEntity):
    """An on/off setting of the unit."""

    entity_description: BrinkFlairSwitchDescription

    def __init__(
        self,
        coordinator: BrinkFlairCoordinator,
        description: BrinkFlairSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Unavailable when the unit does not serve the setting."""
        return (
            super().available
            and self.entity_description.value_fn(self.coordinator.data) is not None
        )

    @property
    def is_on(self) -> bool | None:
        """The current state."""
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await self._async_write(
            self.entity_description.set_fn(self.coordinator.device, True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await self._async_write(
            self.entity_description.set_fn(self.coordinator.device, False)
        )
