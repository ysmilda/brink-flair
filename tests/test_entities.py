"""Tests for the Brink Flair entities."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PRESET_MODE,
    DOMAIN as FAN_DOMAIN,
    SERVICE_SET_PRESET_MODE,
)
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from modbus_connection import (
    IllegalDataAddressError,
    IllegalDataValueError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusUnit
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.brink_flair.diagnostics import (
    async_get_config_entry_diagnostics,
)

pytestmark = pytest.mark.usefixtures("init_integration")

FAN = "fan.flair"


async def _call(hass: HomeAssistant, domain: str, service: str, data: dict) -> None:
    await hass.services.async_call(domain, service, data, blocking=True)


async def test_sensors(hass: HomeAssistant) -> None:
    """Readings are decoded with the right scale and sign."""
    assert hass.states.get("sensor.flair_supply_airflow").state == "148"
    assert hass.states.get("sensor.flair_exhaust_airflow").state == "151"
    assert hass.states.get("sensor.flair_supply_air_temperature").state == "19.1"
    assert hass.states.get("sensor.flair_outdoor_air_temperature").state == "12.5"
    assert hass.states.get("sensor.flair_supply_air_humidity").state == "43"
    assert hass.states.get("sensor.flair_exhaust_air_humidity").state == "94"
    assert hass.states.get("sensor.flair_bypass").state == "open"
    assert hass.states.get("sensor.flair_operating_mode").state == "auto_modbus"
    # 90 day interval, 48 days since the last reset.
    assert hass.states.get("sensor.flair_filter_days_remaining").state == "42"
    assert hass.states.get("binary_sensor.flair_filter").state == STATE_OFF
    assert hass.states.get("binary_sensor.flair_fault").state == STATE_OFF
    assert hass.states.get("binary_sensor.flair_frost_protection").state == STATE_OFF


async def test_optional_parts_absent(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Entities for parts the unit lacks exist, but start disabled."""
    for entity_id in (
        "sensor.flair_humidity",
        "binary_sensor.flair_preheater",
        "sensor.flair_preheater_capacity",
        "sensor.flair_co2_sensor_1",
    ):
        entry = entity_registry.async_get(entity_id)
        assert entry is not None, entity_id
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None


async def test_fan_state(hass: HomeAssistant) -> None:
    """The fan shows the current level."""
    state = hass.states.get(FAN)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PRESET_MODE] == "normal"
    assert ATTR_PERCENTAGE not in state.attributes


async def test_fan_preset(hass: HomeAssistant, patch_modbus: MockModbusUnit) -> None:
    """A preset takes over control and sets the level."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: "high"},
    )
    assert patch_modbus.holding[8001] == 3


async def test_fan_preset_when_already_in_control(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """A Flair 300 rejects rewriting 8000, so it is left alone when already set."""
    patch_modbus.fail_write(8000, IllegalDataValueError())
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: "low"},
    )
    assert patch_modbus.holding[8001] == 1


async def test_fan_turn_on_with_preset(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """Turning on with a preset wakes the unit at that level."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: "low"},
    )
    assert patch_modbus.holding[8003] == 2
    assert patch_modbus.holding[8001] == 1


async def test_fan_off_and_on(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """Turning off puts the unit in standby, and turning on wakes it."""
    await _call(hass, FAN_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: FAN})
    assert patch_modbus.holding[8003] == 1
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == STATE_OFF

    await _call(hass, FAN_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: FAN})
    assert patch_modbus.holding[8003] == 2


async def test_level_restored_after_power_cut(
    hass: HomeAssistant,
    patch_modbus: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A level set from Home Assistant is sent again when the unit forgets it."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: "low"},
    )
    patch_modbus.holding[8000] = 0
    patch_modbus.holding[8001] = 0

    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert patch_modbus.holding[8000] == 1
    assert patch_modbus.holding[8001] == 1


async def test_bypass_mode(hass: HomeAssistant, patch_modbus: MockModbusUnit) -> None:
    """The bypass can be forced open."""
    assert hass.states.get("select.flair_bypass_mode").state == "automatic"
    await _call(
        hass,
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.flair_bypass_mode", ATTR_OPTION: "open"},
    )
    assert patch_modbus.holding[6100] == 2


async def test_bypass_temperature(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """Temperatures are written in tenths of a degree."""
    entity_id = "number.flair_bypass_indoor_temperature"
    assert hass.states.get(entity_id).state == "24.0"
    await _call(
        hass,
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 25.5},
    )
    assert patch_modbus.holding[6101] == 255


async def test_flow_preset(hass: HomeAssistant, patch_modbus: MockModbusUnit) -> None:
    """A level's airflow can change within its neighbours."""
    entity_id = "number.flair_airflow_normal"
    assert hass.states.get(entity_id).state == "200"
    assert hass.states.get(entity_id).attributes["max"] == 300
    await _call(
        hass,
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 225},
    )
    assert patch_modbus.holding[6002] == 225


async def test_flow_preset_out_of_order(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """A level's airflow cannot pass the level above it."""
    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: "number.flair_airflow_low", ATTR_VALUE: 205},
        )
    assert 6001 not in patch_modbus.holding


async def test_reset_filter(hass: HomeAssistant, patch_modbus: MockModbusUnit) -> None:
    """The reset button writes the filter reset register."""
    await _call(
        hass,
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.flair_reset_filter"},
    )
    assert patch_modbus.holding[8010] == 1


async def test_write_failure(hass: HomeAssistant, patch_modbus: MockModbusUnit) -> None:
    """A failed write is reported to the user."""
    patch_modbus.fail_write(6100, ModbusTimeoutError("no answer"))
    with pytest.raises(HomeAssistantError):
        await _call(
            hass,
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: "select.flair_bypass_mode", ATTR_OPTION: "closed"},
        )


async def test_unavailable_when_unreachable(
    hass: HomeAssistant,
    patch_modbus: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Entities go unavailable when the unit stops answering, and come back."""
    patch_modbus.fail_requests(ModbusTimeoutError("no answer"))
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == STATE_UNAVAILABLE

    patch_modbus.fail_requests(None)
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == STATE_ON


async def test_diagnostics_redacts(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Diagnostics leave out the host and serial number."""
    result = await async_get_config_entry_diagnostics(hass, init_integration)
    assert result["entry_data"]["host"] == "**REDACTED**"
    assert result["identity"]["serial_number"] == "**REDACTED**"
    assert result["state"]["supply_flow"] == 148


async def test_counters_not_served(
    hass: HomeAssistant,
    patch_modbus: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Counters a unit refuses leave their sensors unknown, not unavailable."""
    patch_modbus.fail_read(4113, IllegalDataAddressError(), register_type="input")
    patch_modbus.fail_read(4115, IllegalDataAddressError(), register_type="input")
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == STATE_ON
    assert hass.states.get("sensor.flair_filter_days_remaining").state == "unknown"
