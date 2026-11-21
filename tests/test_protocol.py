"""Tests for the Home Assistant independent protocol module."""

from modbus_connection.mock import MockModbusConnection

from custom_components.brink_flair.flair import BypassState, FlairDevice
from custom_components.brink_flair.flair.device import _bcd, _signed, _temperature, _u32

from .conftest import flair_300_registers


def test_decoding() -> None:
    """Register values decode as Brink documents them."""
    assert _signed(0xFF9C) == -100
    assert _signed(215) == 215
    assert _bcd(0x4290) == "4290"
    assert _u32(1, 2) == 65538


def test_temperature_not_fitted() -> None:
    """A sensor that is not fitted reads 9999 and decodes as None."""
    assert _temperature(9999) is None
    assert _temperature(125) == 12.5
    assert _temperature(0xFFE2) == -3.0


async def test_fault_sources() -> None:
    """A fan control error or a bypass error counts as a fault."""
    unit = MockModbusConnection().for_unit(20)
    unit.input, unit.holding = flair_300_registers()
    device = FlairDevice(unit)
    await device.async_read_identity()

    state = await device.async_update()
    assert not state.has_error

    unit.input[4020] = [12, 4, 2, 37, 42]
    assert (await device.async_update()).has_error

    unit.input[4020] = [12, 1, 2, 37, 42]
    unit.input[4050] = [255, 920]
    state = await device.async_update()
    assert state.bypass_state == BypassState.ERROR
    assert state.has_error
