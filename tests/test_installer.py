"""Tests for the imbalance and geo heat exchanger settings."""

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from modbus_connection import IllegalDataAddressError
from modbus_connection.mock import MockModbusUnit
import pytest

INSTALLER_ENTITIES = (
    "switch.flair_imbalance_allowed",
    "switch.flair_geo_heat_exchanger",
    "number.flair_supply_imbalance",
    "number.flair_exhaust_imbalance",
    "number.flair_geo_heat_exchanger_minimum_temperature",
    "number.flair_geo_heat_exchanger_maximum_temperature",
)


@pytest.mark.usefixtures("init_integration")
async def test_hidden_by_default(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """The installer settings exist, but start disabled."""
    for entity_id in INSTALLER_ENTITIES:
        entry = entity_registry.async_get(entity_id)
        assert entry is not None, entity_id
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_values_and_writes(
    hass: HomeAssistant, patch_modbus: MockModbusUnit
) -> None:
    """The settings show the unit's values and write back."""
    assert hass.states.get("switch.flair_imbalance_allowed").state == STATE_ON
    assert hass.states.get("switch.flair_geo_heat_exchanger").state == STATE_OFF
    assert hass.states.get("number.flair_supply_imbalance").state == "0"
    assert (
        hass.states.get("number.flair_geo_heat_exchanger_minimum_temperature").state
        == "5.0"
    )
    assert (
        hass.states.get("number.flair_geo_heat_exchanger_maximum_temperature").state
        == "25.0"
    )

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.flair_geo_heat_exchanger"},
        blocking=True,
    )
    assert patch_modbus.holding[6240] == 1

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.flair_supply_imbalance", ATTR_VALUE: -5},
        blocking=True,
    )
    assert patch_modbus.holding[6035] == 0xFFFB


@pytest.fixture
def mock_unit(
    mock_unit: MockModbusUnit, request: pytest.FixtureRequest
) -> MockModbusUnit:
    """Optionally a unit that does not serve the geo heat exchanger registers."""
    if getattr(request, "param", False):
        mock_unit.fail_read(6240, IllegalDataAddressError(), register_type="holding")
    return mock_unit


@pytest.mark.parametrize("mock_unit", [True], indirect=True)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_unserved_setting(hass: HomeAssistant) -> None:
    """A setting the unit does not serve is unavailable, the rest still works."""
    assert hass.states.get("switch.flair_geo_heat_exchanger").state == STATE_UNAVAILABLE
    assert hass.states.get("switch.flair_imbalance_allowed").state == STATE_ON
