"""Ventilation control for the Brink Flair integration."""

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import ActiveFunction, VentilationLevel

PARALLEL_UPDATES = 1

LEVELS = [
    VentilationLevel.AWAY,
    VentilationLevel.LOW,
    VentilationLevel.NORMAL,
    VentilationLevel.HIGH,
]
PRESET_FOR_LEVEL = {level: level.name.lower() for level in LEVELS}
LEVEL_FOR_PRESET = {preset: level for level, preset in PRESET_FOR_LEVEL.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrinkFlairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ventilation fan."""
    async_add_entities([BrinkFlairFan(entry.runtime_data)])


class BrinkFlairFan(BrinkFlairEntity, FanEntity):
    """The unit's ventilation, as a fan with a preset per level."""

    _attr_name = None
    _attr_translation_key = "ventilation"
    _attr_preset_modes = list(PRESET_FOR_LEVEL.values())
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: BrinkFlairCoordinator) -> None:
        """Initialize the fan."""
        super().__init__(coordinator, "ventilation")

    def _level(self) -> VentilationLevel | None:
        mode = self.coordinator.data.ventilation_mode
        return VentilationLevel(mode) if mode in iter(VentilationLevel) else None

    @property
    def is_on(self) -> bool:
        """Whether the unit is ventilating."""
        data = self.coordinator.data
        return not data.standby and data.active_function != ActiveFunction.STANDBY

    @property
    def preset_mode(self) -> str | None:
        """The current level."""
        if (level := self._level()) is None:
            return None
        return PRESET_FOR_LEVEL[level]

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set a level, taking over control from the display and wall switch."""
        await self._async_set_level(LEVEL_FOR_PRESET[preset_mode])

    async def _async_set_level(self, level: VentilationLevel) -> None:
        device = self.coordinator.device
        if self.coordinator.data.standby:
            await self._async_write(device.async_set_standby(False))
        await self._async_write(device.async_set_level(level))

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Wake the unit, optionally at a level."""
        if preset_mode is not None:
            await self._async_write(self.coordinator.device.async_set_standby(False))
            await self.async_set_preset_mode(preset_mode)
        else:
            await self._async_write(self.coordinator.device.async_set_standby(False))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Put the unit in standby."""
        await self._async_write(self.coordinator.device.async_set_standby(True))
