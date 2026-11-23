"""Tests for the Brink Flair entities."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PRESET_MODE,
    DOMAIN as FAN_DOMAIN,
    SERVICE_SET_PERCENTAGE,
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
from custom_components.brink_flair.flair import FlairDevice, FlairState

pytestmark = pytest.mark.usefixtures("init_integration")

FAN = "fan.flair"


@pytest.fixture
def mock_unit(
    mock_unit: MockModbusUnit, request: pytest.FixtureRequest
) -> MockModbusUnit:
    """The mock Flair, starting with the control registers 8000 to 8003 given."""
    if (control := getattr(request, "param", None)) is not None:
        mock_unit.holding[8000] = control
    return mock_unit


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
    """The fan shows the level's airflow: normal is 200 of 50 to 300 m3/h."""
    state = hass.states.get(FAN)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 60
    assert state.attributes[ATTR_PRESET_MODE] == "normal"
    # The unit measures 148 m3/h of supply air, on the same scale.
    assert state.attributes["actual_percentage"] == 40


@pytest.mark.parametrize(("percentage", "flow"), [(1, 50), (50, 174), (100, 300)])
async def test_fan_speed_sets_flow(
    hass: HomeAssistant, patch_modbus: MockModbusUnit, percentage: int, flow: int
) -> None:
    """1 to 100% is the model's min to max flow, set in flow mode."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: percentage},
    )
    assert patch_modbus.holding[8000] == 2
    assert patch_modbus.holding[8002] == flow
    state = hass.states.get(FAN)
    assert state.attributes[ATTR_PERCENTAGE] == percentage
    assert state.attributes[ATTR_PRESET_MODE] is None


async def test_fan_speed_reads_back_at_once(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """A new airflow shows right away, before the unit's own setpoint catches up."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 100},
    )
    # Register 4031 still reports 140 m3/h.
    assert hass.states.get(FAN).attributes[ATTR_PERCENTAGE] == 100


@pytest.mark.parametrize("mock_unit", [[0, 0, 0, 0]], indirect=True)
async def test_fan_follows_unit_without_modbus_control(hass: HomeAssistant) -> None:
    """When the unit runs itself, the fan shows the unit's own setpoint."""
    state = hass.states.get(FAN)
    # 140 m3/h of 50 to 300 m3/h.
    assert state.attributes[ATTR_PERCENTAGE] == 37
    assert state.attributes[ATTR_PRESET_MODE] is None


async def test_fan_percentage_zero_turns_off(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """Zero on the speed buttons puts the unit in standby."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 0},
    )
    assert patch_modbus.holding[8003] == 1


@pytest.mark.parametrize("mock_unit", [[2, 0, 150, 0]], indirect=True)
async def test_fan_picks_up_flow_mode(hass: HomeAssistant) -> None:
    """An airflow set before a restart shows as a percentage, with no preset."""
    state = hass.states.get(FAN)
    # 150 m3/h of 50 to 300 m3/h.
    assert state.attributes[ATTR_PERCENTAGE] == 41
    assert state.attributes[ATTR_PRESET_MODE] is None


@pytest.mark.parametrize("mock_unit", [[2, 0, 150, 0]], indirect=True)
@pytest.mark.parametrize(
    ("preset", "level"), [("away", 0), ("low", 1), ("normal", 2), ("high", 3)]
)
async def test_fan_preset_sets_level(
    hass: HomeAssistant, patch_modbus: MockModbusUnit, preset: str, level: int
) -> None:
    """A preset is one of the unit's levels, and leaves flow mode."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: preset},
    )
    assert patch_modbus.holding[8000] == 1
    assert patch_modbus.holding[8001] == level
    assert hass.states.get(FAN).attributes[ATTR_PRESET_MODE] == preset


async def test_preset_when_already_in_control(
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


async def test_unit_read_back_straight_after_write(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """A change is read back from the unit at once, not at the next poll."""
    release = asyncio.Event()
    send = FlairDevice._write
    update = FlairDevice.async_update
    reads = 0

    async def held_write(self: FlairDevice, address: int, value: int) -> None:
        await release.wait()
        await send(self, address, value)

    async def counted_update(self: FlairDevice) -> FlairState:
        nonlocal reads
        reads += 1
        return await update(self)

    with (
        patch.object(FlairDevice, "_write", held_write),
        patch.object(FlairDevice, "async_update", counted_update),
    ):
        call = asyncio.create_task(
            _call(
                hass,
                FAN_DOMAIN,
                SERVICE_SET_PERCENTAGE,
                {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 100},
            )
        )
        await asyncio.sleep(0.05)
        # Nothing is shown before the unit has confirmed the write.
        assert hass.states.get(FAN).attributes[ATTR_PERCENTAGE] == 60
        assert reads == 0
        assert 8002 not in patch_modbus.holding

        release.set()
        await call
    assert patch_modbus.holding[8002] == 300
    assert reads == 1


async def test_failed_write_restores_shown_state(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """A change the unit rejects leaves the state as it was."""
    patch_modbus.fail_write(8002, ModbusTimeoutError("no answer"))
    with pytest.raises(HomeAssistantError):
        await _call(
            hass,
            FAN_DOMAIN,
            SERVICE_SET_PERCENTAGE,
            {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 100},
        )
    assert hass.states.get(FAN).attributes[ATTR_PERCENTAGE] == 60


@pytest.mark.parametrize("mock_unit", [[1, 2, 0, 1]], indirect=True)
async def test_fan_turn_on_with_speed(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """Turning on with a speed wakes the unit at that airflow."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 50},
    )
    assert patch_modbus.holding[8003] == 2
    assert patch_modbus.holding[8002] == 174


@pytest.mark.parametrize("mock_unit", [[1, 2, 0, 1]], indirect=True)
async def test_fan_turn_on_with_preset(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """Turning on with a preset wakes the unit at that level."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: "high"},
    )
    assert patch_modbus.holding[8003] == 2
    assert patch_modbus.holding[8001] == 3


async def test_fan_off_and_on(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """Turning off puts the unit in standby, and turning on wakes it."""
    await _call(hass, FAN_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: FAN})
    assert patch_modbus.holding[8003] == 1
    await hass.async_block_till_done()
    state = hass.states.get(FAN)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_PRESET_MODE] is None

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
    assert hass.states.get(FAN).attributes[ATTR_PRESET_MODE] == "low"


async def test_flow_restored_after_power_cut(
    hass: HomeAssistant,
    patch_modbus: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An airflow set from Home Assistant is sent again when the unit forgets it."""
    await _call(
        hass,
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 50},
    )
    patch_modbus.holding[8000] = 0
    patch_modbus.holding[8002] = 0

    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert patch_modbus.holding[8000] == 2
    assert patch_modbus.holding[8002] == 174
    assert hass.states.get(FAN).attributes[ATTR_PERCENTAGE] == 50


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
