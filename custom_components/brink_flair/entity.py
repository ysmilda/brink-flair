"""Base entity for the Brink Flair integration."""

from collections.abc import Awaitable

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from modbus_connection import ModbusError

from .const import DOMAIN
from .coordinator import BrinkFlairCoordinator


class BrinkFlairEntity(CoordinatorEntity[BrinkFlairCoordinator]):
    """An entity of a Brink Flair unit."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BrinkFlairCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial_number}_{key}"
        self._attr_device_info = coordinator.device_info

    async def _async_write(self, action: Awaitable[None]) -> None:
        """Send a change to the unit, then refresh its state."""
        try:
            await action
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
