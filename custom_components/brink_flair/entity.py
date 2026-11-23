"""Base entity for the Brink Flair integration."""

from collections.abc import Awaitable

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from modbus_connection import ModbusError

from .const import DOMAIN, MANUFACTURER
from .coordinator import BrinkFlairCoordinator


def _device_info(coordinator: BrinkFlairCoordinator) -> DeviceInfo:
    """Describe the unit for the device registry."""
    identity = coordinator.device.identity
    info = DeviceInfo(
        identifiers={(DOMAIN, coordinator.serial_number)},
        manufacturer=MANUFACTURER,
        model=coordinator.device.model.name,
        serial_number=coordinator.serial_number,
    )
    if identity is not None:
        info["sw_version"] = identity.software_version
        info["hw_version"] = identity.hardware_version
    return info


class BrinkFlairEntity(CoordinatorEntity[BrinkFlairCoordinator]):
    """An entity of a Brink Flair unit."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BrinkFlairCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial_number}_{key}"
        self._attr_device_info = _device_info(coordinator)

    @property
    def available(self) -> bool:
        """Unavailable when the unit does not serve this entity's value."""
        return super().available and self._has_value()

    def _has_value(self) -> bool:
        """Whether the unit serves this entity's value."""
        return True

    async def _async_write(self, action: Awaitable[None]) -> None:
        """Send a change to the unit, then ask for a fresh reading."""
        try:
            await action
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
