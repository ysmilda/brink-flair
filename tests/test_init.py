"""Tests for setting up the Brink Flair integration."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.brink_flair.const import DOMAIN

from .conftest import SERIAL


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry loads, registers the device, and unloads."""
    assert init_integration.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, SERIAL), init_integration.entry_id
    )
    assert device is not None
    assert device.manufacturer == "Brink Climate Systems"
    assert device.serial_number == SERIAL
    assert device.sw_version == "1.2.3.1234"
    assert device.hw_version == "1.2"

    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_unknown_model_issue(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """An appliance type outside the model table raises a repair issue."""
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"unknown_model_{init_integration.entry_id}"
    )
    assert issue is not None
    assert issue.translation_placeholders["appliance_type"] == "7"


async def test_setup_retry_when_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patch_modbus: MockModbusUnit,
) -> None:
    """A unit that does not answer is retried later."""
    patch_modbus.fail_requests(ModbusTimeoutError("no answer"))
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
