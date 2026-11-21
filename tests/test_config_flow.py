"""Tests for the Brink Flair config flow."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.brink_flair.const import (
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_STOPBITS,
    CONF_UNIT_ID,
    DOMAIN,
    TYPE_SERIAL,
    TYPE_TCP,
)

from .conftest import SERIAL, TCP_DATA

pytestmark = pytest.mark.usefixtures("patch_modbus")

TCP_INPUT = {CONF_HOST: "192.0.2.10", CONF_PORT: 502, CONF_UNIT_ID: 20}
SERIAL_INPUT = {
    CONF_DEVICE: "/dev/ttyUSB0",
    CONF_BAUDRATE: "19200",
    CONF_PARITY: "E",
    CONF_STOPBITS: "1",
    CONF_UNIT_ID: 20,
}


async def _start(hass: HomeAssistant, menu_option: str) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": menu_option}
    )


async def test_tcp(hass: HomeAssistant) -> None:
    """A unit behind a TCP gateway is added."""
    result = await _start(hass, TYPE_TCP)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Flair"
    assert result["data"] == {CONF_TYPE: TYPE_TCP, **TCP_INPUT}
    assert result["result"].unique_id == SERIAL


async def test_serial(hass: HomeAssistant) -> None:
    """A unit on a serial adapter is added, with numbers stored as numbers."""
    result = await _start(hass, TYPE_SERIAL)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], SERIAL_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_TYPE: TYPE_SERIAL,
        CONF_DEVICE: "/dev/ttyUSB0",
        CONF_BAUDRATE: 19200,
        CONF_PARITY: "E",
        CONF_STOPBITS: 1,
        CONF_UNIT_ID: 20,
    }


async def test_cannot_connect_then_recover(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """An unreachable unit shows an error, and the flow can be retried."""
    patch_modbus.fail_requests(ModbusTimeoutError("no answer"))
    result = await _start(hass, TYPE_TCP)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    patch_modbus.fail_requests(None)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The same unit cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await _start(hass, TYPE_TCP)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def _start_reconfigure(
    hass: HomeAssistant, entry: MockConfigEntry, menu_option: str
) -> dict:
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": menu_option}
    )


async def test_reconfigure_to_serial(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The connection can move from TCP to serial."""
    result = await _start_reconfigure(hass, init_integration, "reconfigure_serial")
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], SERIAL_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.data[CONF_TYPE] == TYPE_SERIAL
    assert init_integration.data[CONF_BAUDRATE] == 19200


async def test_reconfigure_tcp_new_host(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The gateway address can change."""
    result = await _start_reconfigure(hass, init_integration, "reconfigure_tcp")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**TCP_INPUT, CONF_HOST: "192.0.2.20"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.data == {**TCP_DATA, CONF_HOST: "192.0.2.20"}


async def test_reconfigure_other_unit(
    hass: HomeAssistant, init_integration: MockConfigEntry, patch_modbus: MockModbusUnit
) -> None:
    """Settings that reach another unit are refused."""
    patch_modbus.input[4010] = [0x1111, 0x2222, 0x3333]
    result = await _start_reconfigure(hass, init_integration, "reconfigure_tcp")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, init_integration: MockConfigEntry, patch_modbus: MockModbusUnit
) -> None:
    """An unreachable unit keeps the reconfigure form open."""
    patch_modbus.fail_requests(ModbusTimeoutError("no answer"))
    result = await _start_reconfigure(hass, init_integration, "reconfigure_tcp")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TCP_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
