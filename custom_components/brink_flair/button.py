"""Filter reset for the Brink Flair integration."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrinkFlairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the filter reset button."""
    async_add_entities([BrinkFlairFilterResetButton(entry.runtime_data)])


class BrinkFlairFilterResetButton(BrinkFlairEntity, ButtonEntity):
    """Reset the filter counter after a filter change."""

    _attr_translation_key = "reset_filter"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BrinkFlairCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "reset_filter")

    async def async_press(self) -> None:
        """Reset the filter counter."""
        await self._async_write(self.coordinator.device.async_reset_filter())
