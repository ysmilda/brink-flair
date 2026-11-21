"""Diagnostics for the Brink Flair integration."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import BrinkFlairConfigEntry

TO_REDACT = {CONF_HOST, "serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BrinkFlairConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    device = coordinator.device
    identity = device.identity
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "identity": async_redact_data(asdict(identity), TO_REDACT)
        if identity
        else None,
        "model": asdict(device.model),
        "unsupported_registers": device.unsupported_registers,
        "state": asdict(coordinator.data) if coordinator.data else None,
    }
