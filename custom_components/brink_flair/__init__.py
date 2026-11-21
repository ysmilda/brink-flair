"""The Brink Flair integration."""

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import CONF_UNIT_ID, DOMAIN
from .coordinator import BrinkFlairConfigEntry, BrinkFlairCoordinator
from .flair import FlairDevice
from .helpers import create_modbus_params

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: BrinkFlairConfigEntry) -> bool:
    """Set up a Brink Flair from a config entry."""
    unit = async_get_unit(
        hass, entry, create_modbus_params(entry.data), entry.data[CONF_UNIT_ID]
    )
    coordinator = BrinkFlairCoordinator(hass, entry, FlairDevice(unit))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    identity = coordinator.device.identity
    issue_id = f"unknown_model_{entry.entry_id}"
    if identity is not None and identity.model is None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="unknown_model",
            translation_placeholders={
                "appliance_type": str(identity.appliance_type),
                "title": entry.title,
            },
            learn_more_url="https://github.com/ysmilda/brink-flair/issues",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BrinkFlairConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: BrinkFlairConfigEntry) -> None:
    """Clean up when a config entry is removed."""
    ir.async_delete_issue(hass, DOMAIN, f"unknown_model_{entry.entry_id}")
