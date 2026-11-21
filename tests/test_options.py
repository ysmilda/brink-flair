"""Tests for a Flair with optional parts fitted."""

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from modbus_connection.mock import MockModbusUnit
import pytest


@pytest.fixture
def mock_unit(mock_unit: MockModbusUnit) -> MockModbusUnit:
    """A Flair with a preheater, humidity sensor and two CO2 sensors."""
    mock_unit.holding.update({6130: 1, 6140: 1, 6150: 1})
    mock_unit.input[4060] = [2, 40]
    mock_unit.input[4080] = [2, 125, 9999, 61]
    mock_unit.input[4200] = [4, 650, 4, 820, 3, 400, 0, 0]
    return mock_unit


@pytest.mark.usefixtures("init_integration")
async def test_optional_parts(hass: HomeAssistant) -> None:
    """Optional parts get their own entities."""
    assert hass.states.get("sensor.flair_humidity").state == "61"
    assert hass.states.get("binary_sensor.flair_preheater").state == STATE_ON
    assert hass.states.get("sensor.flair_preheater_capacity").state == "40"
    assert hass.states.get("sensor.flair_co2_sensor_1").state == "650"
    assert hass.states.get("sensor.flair_co2_sensor_2").state == "820"
    assert hass.states.get("sensor.flair_co2_sensor_3").state == "unknown"
