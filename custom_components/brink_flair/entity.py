"""Base entity for the Brink Flair integration."""

from collections.abc import Awaitable
from dataclasses import replace
from typing import Any

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

    async def _async_write(self, action: Awaitable[None], **changes: Any) -> None:
        """Show a change, send it to the unit, then refresh its state.

        ``changes`` are the state fields the write sets. They are shown before
        the unit confirms, and restored if the unit rejects the write.
        """
        previous = self.coordinator.data
        if changes:
            self.coordinator.async_set_updated_data(replace(previous, **changes))
        try:
            await action
        except ModbusError as err:
            if changes:
                self.coordinator.async_set_updated_data(previous)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
