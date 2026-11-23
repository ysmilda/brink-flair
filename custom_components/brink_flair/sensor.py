"""Sensors for the Brink Flair integration."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import UNIT_AIRFLOW
from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import ActiveFunction, BypassState, FlairState, FrostStatus
from .helpers import option_name

PARALLEL_UPDATES = 0


def _enum_options(enum: type[IntEnum]) -> list[str]:
    return [option_name(member) for member in enum]


def _enum_value(enum: type[IntEnum], value: int) -> str | None:
    return option_name(enum(value)) if value in iter(enum) else None


@dataclass(frozen=True, kw_only=True)
class BrinkFlairSensorDescription(SensorEntityDescription):
    """Describes a Brink Flair sensor."""

    value_fn: Callable[[FlairState], float | int | str | None]


def _airflow(
    key: str, value_fn: Callable[[FlairState], int], **kwargs
) -> BrinkFlairSensorDescription:
    return BrinkFlairSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UNIT_AIRFLOW,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
        **kwargs,
    )


def _temperature(
    key: str, value_fn: Callable[[FlairState], float], **kwargs
) -> BrinkFlairSensorDescription:
    return BrinkFlairSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=value_fn,
        **kwargs,
    )


def _humidity(
    key: str, value_fn: Callable[[FlairState], float | None], **kwargs
) -> BrinkFlairSensorDescription:
    return BrinkFlairSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=value_fn,
        **kwargs,
    )


def _fan_speed(
    key: str, value_fn: Callable[[FlairState], int]
) -> BrinkFlairSensorDescription:
    return BrinkFlairSensorDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=value_fn,
    )


def _pressure(
    key: str, value_fn: Callable[[FlairState], float]
) -> BrinkFlairSensorDescription:
    return BrinkFlairSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PA,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=value_fn,
    )


def _co2(number: int) -> BrinkFlairSensorDescription:
    return BrinkFlairSensorDescription(
        key=f"co2_{number}",
        translation_key="co2",
        translation_placeholders={"number": str(number)},
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.co2.get(number),
        entity_registry_enabled_default=False,
    )


SENSORS: tuple[BrinkFlairSensorDescription, ...] = (
    _airflow("supply_flow", lambda state: state.supply_flow),
    _airflow("exhaust_flow", lambda state: state.exhaust_flow),
    _airflow(
        "supply_flow_setpoint",
        lambda state: state.supply_flow_setpoint,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    _airflow(
        "exhaust_flow_setpoint",
        lambda state: state.exhaust_flow_setpoint,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    _temperature("supply_temperature", lambda state: state.supply_temperature),
    _temperature("exhaust_temperature", lambda state: state.exhaust_temperature),
    _temperature("ntc1_temperature", lambda state: state.ntc1_temperature),
    _temperature(
        "ntc2_temperature",
        lambda state: state.ntc2_temperature,
        entity_registry_enabled_default=False,
    ),
    _humidity("supply_humidity", lambda state: state.supply_humidity),
    _humidity("exhaust_humidity", lambda state: state.exhaust_humidity),
    _humidity(
        "rht_humidity",
        lambda state: state.rht_humidity,
        entity_registry_enabled_default=False,
    ),
    _fan_speed("supply_fan_speed", lambda state: state.supply_fan_speed),
    _fan_speed("exhaust_fan_speed", lambda state: state.exhaust_fan_speed),
    _pressure("supply_pressure", lambda state: state.supply_pressure),
    _pressure("exhaust_pressure", lambda state: state.exhaust_pressure),
    BrinkFlairSensorDescription(
        key="bypass",
        translation_key="bypass",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(BypassState),
        value_fn=lambda state: option_name(state.bypass_state),
    ),
    BrinkFlairSensorDescription(
        key="active_function",
        translation_key="active_function",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(ActiveFunction),
        value_fn=lambda state: _enum_value(ActiveFunction, state.active_function),
    ),
    BrinkFlairSensorDescription(
        key="frost_status",
        translation_key="frost_status",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(FrostStatus),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda state: _enum_value(FrostStatus, state.frost_status),
    ),
    BrinkFlairSensorDescription(
        key="filter_days_remaining",
        translation_key="filter_days_remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda state: state.filter_days_remaining,
    ),
    BrinkFlairSensorDescription(
        key="operating_hours",
        translation_key="operating_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.operating_hours,
    ),
    BrinkFlairSensorDescription(
        key="preheater_capacity",
        translation_key="preheater_capacity",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.preheater_capacity,
        entity_registry_enabled_default=False,
    ),
    *(_co2(number) for number in range(1, 5)),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrinkFlairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        BrinkFlairSensor(coordinator, description) for description in SENSORS
    )


class BrinkFlairSensor(BrinkFlairEntity, SensorEntity):
    """A sensor of the unit."""

    entity_description: BrinkFlairSensorDescription

    def __init__(
        self,
        coordinator: BrinkFlairCoordinator,
        description: BrinkFlairSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | None:
        """The current value."""
        return self.entity_description.value_fn(self.coordinator.data)
