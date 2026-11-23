"""Airflow, bypass and filter settings for the Brink Flair integration."""

from dataclasses import dataclass

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

from .const import DOMAIN, UNIT_AIRFLOW
from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .entity import BrinkFlairEntity
from .flair import (
    BYPASS_HYSTERESIS,
    BYPASS_TEMP_INDOOR,
    BYPASS_TEMP_OUTDOOR,
    EXHAUST_IMBALANCE,
    FILTER_INTERVAL,
    FLOW_PRESETS,
    GEO_MAX_TEMP,
    GEO_MIN_TEMP,
    SUPPLY_IMBALANCE,
    Setting,
    VentilationLevel,
    setting_value,
)
from .helpers import option_name

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class BrinkFlairNumberDescription(NumberEntityDescription):
    """Describes a Brink Flair setting."""

    setting: Setting


SETTINGS: tuple[BrinkFlairNumberDescription, ...] = (
    BrinkFlairNumberDescription(
        key="bypass_temp_indoor",
        translation_key="bypass_temp_indoor",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=15,
        native_max_value=35,
        native_step=0.5,
        setting=BYPASS_TEMP_INDOOR,
    ),
    BrinkFlairNumberDescription(
        key="bypass_temp_outdoor",
        translation_key="bypass_temp_outdoor",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=7,
        native_max_value=15,
        native_step=0.5,
        setting=BYPASS_TEMP_OUTDOOR,
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
        setting=BYPASS_HYSTERESIS,
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
        setting=FILTER_INTERVAL,
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
        setting=SUPPLY_IMBALANCE,
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
        setting=EXHAUST_IMBALANCE,
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
        setting=GEO_MIN_TEMP,
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
        setting=GEO_MAX_TEMP,
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

    def _has_value(self) -> bool:
        return (
            setting_value(self.coordinator.data, self.entity_description.setting)
            is not None
        )

    @property
    def native_value(self) -> float | None:
        """The current value."""
        return setting_value(self.coordinator.data, self.entity_description.setting)

    async def async_set_native_value(self, value: float) -> None:
        """Change the setting."""
        await self._async_write(
            self.coordinator.device.async_set_setting(
                self.entity_description.setting, value
            )
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
        key = f"flow_preset_{option_name(level)}"
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
        lower, upper = self.coordinator.data.flow_preset_bounds(
            self._level, self.coordinator.device.model.max_flow
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
        await self._async_write(
            self.coordinator.device.async_set_setting(
                FLOW_PRESETS, flow, offset=self._level
            )
        )
