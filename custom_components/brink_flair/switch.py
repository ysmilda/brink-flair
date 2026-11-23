"""Installer switches for the Brink Flair integration."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import GEO_HEAT_EXCHANGER, IMBALANCE_ALLOWED, Setting, setting_value

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class BrinkFlairSwitchDescription(SwitchEntityDescription):
    """Describes a Brink Flair switch."""

    setting: Setting


# Installer settings, so they start disabled.
SWITCHES: tuple[BrinkFlairSwitchDescription, ...] = (
    BrinkFlairSwitchDescription(
        key="imbalance_allowed",
        translation_key="imbalance_allowed",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        setting=IMBALANCE_ALLOWED,
    ),
    BrinkFlairSwitchDescription(
        key="geo_heat_exchanger",
        translation_key="geo_heat_exchanger",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        setting=GEO_HEAT_EXCHANGER,
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

    def _has_value(self) -> bool:
        return (
            setting_value(self.coordinator.data, self.entity_description.setting)
            is not None
        )

    @property
    def is_on(self) -> bool | None:
        """The current state."""
        return setting_value(self.coordinator.data, self.entity_description.setting)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        await self._async_write(
            self.coordinator.device.async_set_setting(
                self.entity_description.setting, on
            )
        )
