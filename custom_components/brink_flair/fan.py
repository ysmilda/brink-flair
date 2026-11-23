"""Ventilation control for the Brink Flair integration."""

import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import ActiveFunction, VentilationLevel

PARALLEL_UPDATES = 1

# Speeds 1 to 4 are the ventilation levels from away up to high. Off is standby.
SPEED_RANGE = (1, 4)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrinkFlairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ventilation fan."""
    async_add_entities([BrinkFlairFan(entry.runtime_data)])


class BrinkFlairFan(BrinkFlairEntity, FanEntity):
    """The unit's ventilation, as four speeds and off."""

    _attr_name = None
    _attr_translation_key = "ventilation"
    _attr_speed_count = SPEED_RANGE[1]
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: BrinkFlairCoordinator) -> None:
        """Initialize the fan."""
        super().__init__(coordinator, "ventilation")

    @property
    def is_on(self) -> bool:
        """Whether the unit is ventilating."""
        data = self.coordinator.data
        return not data.standby and data.active_function != ActiveFunction.STANDBY

    @property
    def percentage(self) -> int:
        """The speed as a percentage, where 0 is off."""
        data = self.coordinator.data
        if data.standby or data.ventilation_mode not in iter(VentilationLevel):
            return 0
        speed = VentilationLevel(data.ventilation_mode) + 1
        return ranged_value_to_percentage(SPEED_RANGE, speed)

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """The airflow the unit measures, as a percentage of its max flow."""
        data = self.coordinator.data
        max_flow = self.coordinator.device.model.max_flow
        actual = round(data.supply_flow * 100 / max_flow)
        return {"actual_percentage": min(100, max(0, actual))}

    async def async_set_percentage(self, percentage: int) -> None:
        """Set a speed. Zero puts the unit in standby."""
        if percentage == 0:
            await self.async_turn_off()
            return
        # Round up, so the lowest percentage is speed 1 and not off.
        speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
        await self._async_set_level(VentilationLevel(speed - 1))

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
        """Wake the unit, optionally at a speed."""
        if percentage is not None and percentage > 0:
            await self.async_set_percentage(percentage)
        else:
            await self._async_write(self.coordinator.device.async_set_standby(False))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Put the unit in standby."""
        await self._async_write(self.coordinator.device.async_set_standby(True))
