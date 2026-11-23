"""Airflow, bypass and filter settings for the Brink Flair integration."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import FlairDevice, FlairState, VentilationLevel

PARALLEL_UPDATES = 1

UNIT_AIRFLOW = "m³/h"


@dataclass(frozen=True, kw_only=True)
class BrinkFlairNumberDescription(NumberEntityDescription):
    """Describes a Brink Flair setting."""

    value_fn: Callable[[FlairState], float | None]
    set_fn: Callable[[FlairDevice, float], Coroutine[Any, Any, None]]
    state_field: str
    """The FlairState field that value_fn reads."""


SETTINGS: tuple[BrinkFlairNumberDescription, ...] = (
    BrinkFlairNumberDescription(
        key="bypass_temp_indoor",
        translation_key="bypass_temp_indoor",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=15,
        native_max_value=35,
        native_step=0.5,
        value_fn=lambda state: state.bypass_temp_indoor,
        set_fn=lambda device, value: device.async_set_bypass_temp_indoor(value),
        state_field="bypass_temp_indoor",
    ),
    BrinkFlairNumberDescription(
        key="bypass_temp_outdoor",
        translation_key="bypass_temp_outdoor",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=7,
        native_max_value=15,
        native_step=0.5,
        value_fn=lambda state: state.bypass_temp_outdoor,
        set_fn=lambda device, value: device.async_set_bypass_temp_outdoor(value),
        state_field="bypass_temp_outdoor",
    ),
    BrinkFlairNumberDescription(
        key="bypass_hysteresis",
        translation_key="bypass_hysteresis",
        device_class=NumberDeviceClass.TEMPERATURE_DELTA,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=5,
        native_step=0.5,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.bypass_hysteresis,
        set_fn=lambda device, value: device.async_set_bypass_hysteresis(value),
        state_field="bypass_hysteresis",
    ),
    BrinkFlairNumberDescription(
        key="filter_interval",
        translation_key="filter_interval",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        native_min_value=1,
        native_max_value=365,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda state: state.filter_interval_days,
        set_fn=lambda device, value: device.async_set_filter_interval(int(value)),
        state_field="filter_interval_days",
    ),
    # Installer settings, so they start disabled.
    BrinkFlairNumberDescription(
        key="supply_imbalance",
        translation_key="supply_imbalance",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=-15,
        native_max_value=15,
        native_step=1,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.supply_imbalance,
        set_fn=lambda device, value: device.async_set_supply_imbalance(int(value)),
        state_field="supply_imbalance",
    ),
    BrinkFlairNumberDescription(
        key="exhaust_imbalance",
        translation_key="exhaust_imbalance",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=-15,
        native_max_value=15,
        native_step=1,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.exhaust_imbalance,
        set_fn=lambda device, value: device.async_set_exhaust_imbalance(int(value)),
        state_field="exhaust_imbalance",
    ),
    BrinkFlairNumberDescription(
        key="geo_min_temp",
        translation_key="geo_min_temp",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=10,
        native_step=0.5,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.geo_min_temp,
        set_fn=lambda device, value: device.async_set_geo_min_temp(value),
        state_field="geo_min_temp",
    ),
    BrinkFlairNumberDescription(
        key="geo_max_temp",
        translation_key="geo_max_temp",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=15,
        native_max_value=40,
        native_step=0.5,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.geo_max_temp,
        set_fn=lambda device, value: device.async_set_geo_max_temp(value),
        state_field="geo_max_temp",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrinkFlairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the settings."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [
        BrinkFlairFlowPresetNumber(coordinator, level) for level in VentilationLevel
    ]
    entities.extend(
        BrinkFlairSettingNumber(coordinator, description) for description in SETTINGS
    )
    async_add_entities(entities)


class BrinkFlairSettingNumber(BrinkFlairEntity, NumberEntity):
    """A setting of the unit."""

    _attr_entity_category = EntityCategory.CONFIG
    entity_description: BrinkFlairNumberDescription

    def __init__(
        self,
        coordinator: BrinkFlairCoordinator,
        description: BrinkFlairNumberDescription,
    ) -> None:
        """Initialize the setting."""
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
    def native_value(self) -> float | None:
        """The current value."""
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        """Change the setting."""
        field = self.entity_description.state_field
        # Keep the field's type: whole-number settings are stored as int.
        current = getattr(self.coordinator.data, field)
        await self._async_write(
            self.entity_description.set_fn(self.coordinator.device, value),
            **{field: type(current)(value)},
        )


class BrinkFlairFlowPresetNumber(BrinkFlairEntity, NumberEntity):
    """The airflow behind one ventilation level."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UNIT_AIRFLOW
    _attr_device_class = NumberDeviceClass.VOLUME_FLOW_RATE

    def __init__(
        self, coordinator: BrinkFlairCoordinator, level: VentilationLevel
    ) -> None:
        """Initialize the preset."""
        key = f"flow_preset_{level.name.lower()}"
        super().__init__(coordinator, key)
        self._level = level
        self._attr_translation_key = key
        model = coordinator.device.model
        # Level 0 (away) may be switched off entirely.
        self._attr_native_min_value = (
            0 if level == VentilationLevel.AWAY else model.min_flow
        )
        self._attr_native_max_value = model.max_flow

    @property
    def native_value(self) -> int:
        """The airflow for this level, in m3/h."""
        return self.coordinator.data.flow_presets[self._level]

    async def async_set_native_value(self, value: float) -> None:
        """Set the airflow for this level, keeping the levels in order."""
        flow = int(value)
        presets = self.coordinator.data.flow_presets
        lower = presets[self._level - 1] if self._level > 0 else 0
        upper = (
            presets[self._level + 1]
            if self._level < VentilationLevel.HIGH
            else self.native_max_value
        )
        if not lower <= flow <= upper:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="flow_out_of_order",
                translation_placeholders={
                    "flow": str(flow),
                    "lower": str(lower),
                    "upper": str(upper),
                },
            )
        presets = list(presets)
        presets[self._level] = flow
        await self._async_write(
            self.coordinator.device.async_set_flow_preset(self._level, flow),
            flow_presets=tuple(presets),
        )
