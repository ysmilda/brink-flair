"""Helpers for the Brink Flair integration."""

from collections.abc import Mapping
from enum import Enum
from typing import Any

from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from modbus_connection import ModbusSerialParams, ModbusTcpParams

from .const import (
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_STOPBITS,
    PARITY_OPTIONS,
    TYPE_SERIAL,
)


def create_modbus_params(
    data: Mapping[str, Any],
) -> ModbusSerialParams | ModbusTcpParams:
    """Build the Modbus link parameters from config entry data."""
    if data[CONF_TYPE] == TYPE_SERIAL:
        return ModbusSerialParams(
            device=data[CONF_DEVICE],
            baudrate=data[CONF_BAUDRATE],
            parity=PARITY_OPTIONS[data[CONF_PARITY]],
            stopbits=data[CONF_STOPBITS],
        )
    return ModbusTcpParams(host=data[CONF_HOST], port=data[CONF_PORT])


def option_name(member: Enum) -> str:
    """Return the option string for an enum member, such as "away"."""
    return member.name.lower()
