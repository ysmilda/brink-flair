"""Data update coordinator for the Brink Flair integration."""

import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection import ModbusError

from .const import DOMAIN, MANUFACTURER, SCAN_INTERVAL
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
        assert self.config_entry.unique_id is not None
        return self.config_entry.unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Describe the unit for the device registry."""
        identity = self.device.identity
        info = DeviceInfo(
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer=MANUFACTURER,
            model=self.device.model.name,
            serial_number=self.serial_number,
        )
        if identity is not None:
            info["sw_version"] = identity.software_version
            info["hw_version"] = identity.hardware_version
        return info

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
