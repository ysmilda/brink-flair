"""Data update coordinator for the Brink Flair integration."""

import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection import ModbusError

from .const import DOMAIN, SCAN_INTERVAL
from .flair import FlairDevice, FlairState

_LOGGER = logging.getLogger(__name__)

type BrinkFlairConfigEntry = ConfigEntry[BrinkFlairCoordinator]


class BrinkFlairCoordinator(DataUpdateCoordinator[FlairState]):
    """Poll a Brink Flair."""

    config_entry: BrinkFlairConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: BrinkFlairConfigEntry, device: FlairDevice
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=SCAN_INTERVAL,
        )
        self.device = device

    @property
    def serial_number(self) -> str:
        """The unit's serial number, which is the config entry's unique ID."""
        if self.config_entry.unique_id is None:
            msg = "The config entry has no unique ID"
            raise RuntimeError(msg)
        return self.config_entry.unique_id

    @override
    async def _async_setup(self) -> None:
        try:
            await self.device.async_read_identity()
        except ModbusError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err

    @override
    async def _async_update_data(self) -> FlairState:
        try:
            return await self.device.async_update()
        except ModbusError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
