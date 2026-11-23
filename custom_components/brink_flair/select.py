"""Bypass mode for the Brink Flair integration."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import BypassMode

PARALLEL_UPDATES = 1

OPTIONS = {mode.name.lower(): mode for mode in BypassMode}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrinkFlairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the bypass mode select."""
    async_add_entities([BrinkFlairBypassModeSelect(entry.runtime_data)])


class BrinkFlairBypassModeSelect(BrinkFlairEntity, SelectEntity):
    """Whether the bypass follows its temperature limits or is forced."""

    _attr_translation_key = "bypass_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(OPTIONS)

    def __init__(self, coordinator: BrinkFlairCoordinator) -> None:
        """Initialize the select."""
        super().__init__(coordinator, "bypass_mode")

    @property
    def current_option(self) -> str | None:
        """The current bypass mode."""
        mode = self.coordinator.data.bypass_mode
        return BypassMode(mode).name.lower() if mode in iter(BypassMode) else None

    async def async_select_option(self, option: str) -> None:
        """Set the bypass mode."""
        mode = OPTIONS[option]
        await self._async_write(
            self.coordinator.device.async_set_bypass_mode(mode),
            bypass_mode=int(mode),
        )
