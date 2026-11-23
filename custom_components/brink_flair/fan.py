"""Ventilation control for the Brink Flair integration."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import ActiveFunction, ControlMode, FlairModel, VentilationLevel
from .helpers import option_name

PARALLEL_UPDATES = 1

PRESET_LEVELS = {option_name(level): level for level in VentilationLevel}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrinkFlairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ventilation fan."""
    async_add_entities([BrinkFlairFan(entry.runtime_data)])


def flow_to_percentage(model: FlairModel, flow: int) -> int:
    """Map an airflow onto 1 to 100%, from the model's min to max flow. No flow is 0."""
    if flow <= 0:
        return 0
    span = model.max_flow - model.min_flow
    percentage = 1 + round((flow - model.min_flow) * 99 / span)
    return min(100, max(1, percentage))


def percentage_to_flow(model: FlairModel, percentage: int) -> int:
    """Map 1 to 100% onto the model's min to max flow, in m3/h."""
    span = model.max_flow - model.min_flow
    return model.min_flow + round((percentage - 1) * span / 99)


class BrinkFlairFan(BrinkFlairEntity, FanEntity):
    """The unit's ventilation: an airflow as a percentage, or one of its levels."""

    _attr_name = None
    _attr_translation_key = "ventilation"
    _attr_preset_modes = list(PRESET_LEVELS)
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
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
        """The airflow as a percentage, where 0 is off."""
        data = self.coordinator.data
        if data.standby:
            return 0
        # While Modbus sets the ventilation, show what was asked for: the
        # unit's own setpoint (4031) lags behind a change by several seconds.
        if data.control_mode == ControlMode.FLOW:
            flow = data.control_flow
        elif data.control_mode == ControlMode.SWITCH and data.control_level in iter(
            VentilationLevel
        ):
            flow = data.flow_presets[data.control_level]
        else:
            flow = data.supply_flow_setpoint
        return flow_to_percentage(self.coordinator.device.model, flow)

    @property
    def preset_mode(self) -> str | None:
        """The level Modbus set, or None for a set airflow or the unit's own control."""
        data = self.coordinator.data
        if (
            data.standby
            or data.control_mode != ControlMode.SWITCH
            or data.control_level not in iter(VentilationLevel)
        ):
            return None
        return option_name(VentilationLevel(data.control_level))

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """The airflow the unit measures, on the same scale as the percentage."""
        model = self.coordinator.device.model
        return {
            "actual_percentage": flow_to_percentage(
                model, self.coordinator.data.supply_flow
            )
        }

    async def async_set_percentage(self, percentage: int) -> None:
        """Set an airflow. Zero puts the unit in standby."""
        if percentage == 0:
            await self.async_turn_off()
            return
        device = self.coordinator.device
        flow = percentage_to_flow(device.model, percentage)
        await self._async_write(self._async_wake_and(device.async_set_flow, flow))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set one of the unit's ventilation levels."""
        level = PRESET_LEVELS[preset_mode]
        device = self.coordinator.device
        await self._async_write(self._async_wake_and(device.async_set_level, level))

    async def _async_wake_and[T](
        self, write: Callable[[T], Awaitable[None]], value: T
    ) -> None:
        """Wake the unit if it is in standby, then make the write, as one change."""
        device = self.coordinator.device
        if self.coordinator.data.standby:
            await device.async_set_standby(False)
        await write(value)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Wake the unit, optionally at an airflow or level."""
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None and percentage > 0:
            await self.async_set_percentage(percentage)
        else:
            await self._async_write(self.coordinator.device.async_set_standby(False))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Put the unit in standby."""
        await self._async_write(self.coordinator.device.async_set_standby(True))
