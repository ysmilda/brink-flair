"""Write settings and controls to a Flair. FlairDevice builds on this."""

from typing import Any

from modbus_connection import ModbusUnit

from . import registers as r
from .settings import Setting


class FlairWrites:
    """Write settings to a Flair over Modbus."""

    _unit: ModbusUnit

    async def _write(self, address: int, value: int) -> None:
        await self._unit.write_register(address + r.ADDRESS_OFFSET, int(value))

    async def async_set_setting(
        self, setting: Setting, value: Any, offset: int = 0
    ) -> None:
        """Write a setting. offset picks one register of a run, such as a flow level."""
        await self._write(setting.address + offset, setting.encode(value))

    async def async_set_standby(self, standby: bool) -> None:
        """Put the unit in standby, or wake it."""
        await self._write(r.RC_STANDBY, 1 if standby else 2)

    async def async_reset_filter(self) -> None:
        """Reset the filter counter after a filter change."""
        await self._write(r.RC_FILTER_RESET, 1)
