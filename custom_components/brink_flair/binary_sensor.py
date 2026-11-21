"""Binary sensors for the Brink Flair integration."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import FlairState

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BrinkFlairBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Brink Flair binary sensor."""

    value_fn: Callable[[FlairState], bool | None]


BINARY_SENSORS: tuple[BrinkFlairBinarySensorDescription, ...] = (
    BrinkFlairBinarySensorDescription(
        key="filter_dirty",
        translation_key="filter_dirty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda state: state.filter_dirty,
    ),
    BrinkFlairBinarySensorDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.has_error,
    ),
    BrinkFlairBinarySensorDescription(
        key="frost_protection",
        translation_key="frost_protection",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda state: state.frost_protection_active,
    ),
    BrinkFlairBinarySensorDescription(
        key="preheater",
        translation_key="preheater",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda state: (
            state.preheater_status == 2 if state.preheater_status is not None else None
        ),
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrinkFlairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        BrinkFlairBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class BrinkFlairBinarySensor(BrinkFlairEntity, BinarySensorEntity):
    """A binary sensor of the unit."""

    entity_description: BrinkFlairBinarySensorDescription

    def __init__(
        self,
        coordinator: BrinkFlairCoordinator,
        description: BrinkFlairBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """The current state."""
        return self.entity_description.value_fn(self.coordinator.data)
