"""Check every setting write of the integration against a real Flair.

Each setting is changed through the integration's own protocol code, read
back, and restored to its original value. The filter reset is left out,
because it cannot be undone remotely.

Usage:
    python scripts/verify_writes.py HOST [PORT] [UNIT_ID]

Needs `pip install "modbus-connection[tmodbus]"`.
"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
import sys
from typing import Any

from modbus_connection import ModbusError, ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "brink_flair"))

from flair import FlairDevice, FlairState
from flair.registers import BypassMode, VentilationLevel

SETTLE = 3  # seconds before reading back


def _step(value: float, step: float, low: float, high: float) -> float:
    """Return a different value within the range."""
    return value + step if value + step <= high else value - step


async def _check(
    device: FlairDevice,
    name: str,
    read: Callable[[FlairState], Any],
    write: Callable[[Any], Awaitable[None]],
    new: Any,
) -> bool:
    original = read(await device.async_update())
    if original is None:
        print(f"SKIP {name}: not served by this unit")
        return True
    ok = True
    try:
        await write(new)
        await asyncio.sleep(SETTLE)
        after = read(await device.async_update())
        ok = after == new
        print(
            f"{'OK  ' if ok else 'FAIL'} {name}: {original} -> {new}, read back {after}"
        )
    except ModbusError as err:
        ok = False
        print(f"FAIL {name}: {original} -> {new}: {type(err).__name__}: {err}")
    finally:
        try:
            await write(original)
            await asyncio.sleep(SETTLE)
            restored = read(await device.async_update())
            if restored != original:
                ok = False
                print(f"     {name}: NOT RESTORED, now {restored}, was {original}")
        except ModbusError as err:
            ok = False
            print(f"     {name}: RESTORE FAILED: {type(err).__name__}: {err}")
    return ok


async def main() -> None:
    """Run every write check."""
    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 502
    unit_id = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    connection = ModbusConnection(ModbusTcpParams(host=host, port=port))
    device = FlairDevice(connection.for_unit(unit_id))
    try:
        await device.async_read_identity()
        state = await device.async_update()
        results: list[bool] = []

        async def check(name, read, write, new) -> None:
            results.append(await _check(device, name, read, write, new))

        other = (
            VentilationLevel.LOW
            if state.ventilation_mode != VentilationLevel.LOW
            else VentilationLevel.NORMAL
        )
        await check(
            "ventilation level",
            lambda s: (
                VentilationLevel(s.ventilation_mode)
                if s.ventilation_mode in iter(VentilationLevel)
                else s.ventilation_mode
            ),
            device.async_set_level,
            other,
        )
        await check(
            "standby", lambda s: s.standby, device.async_set_standby, not state.standby
        )
        for lvl in VentilationLevel:
            presets = state.flow_presets
            low = presets[lvl - 1] if lvl > 0 else 0
            high = (
                presets[lvl + 1]
                if lvl < VentilationLevel.HIGH
                else device.model.max_flow
            )
            await check(
                f"flow preset {lvl.name.lower()}",
                lambda s, lvl=lvl: s.flow_presets[lvl],
                lambda v, lvl=lvl: device.async_set_flow_preset(lvl, v),
                int(_step(presets[lvl], 5, low, high)),
            )
        await check(
            "bypass mode",
            lambda s: BypassMode(s.bypass_mode),
            device.async_set_bypass_mode,
            BypassMode.CLOSED
            if state.bypass_mode != BypassMode.CLOSED
            else BypassMode.AUTOMATIC,
        )
        await check(
            "bypass indoor temperature",
            lambda s: s.bypass_temp_indoor,
            device.async_set_bypass_temp_indoor,
            _step(state.bypass_temp_indoor, 0.5, 15, 35),
        )
        await check(
            "bypass outdoor temperature",
            lambda s: s.bypass_temp_outdoor,
            device.async_set_bypass_temp_outdoor,
            _step(state.bypass_temp_outdoor, 0.5, 7, 15),
        )
        await check(
            "bypass hysteresis",
            lambda s: s.bypass_hysteresis,
            device.async_set_bypass_hysteresis,
            _step(state.bypass_hysteresis, 0.5, 0, 5),
        )
        await check(
            "filter interval",
            lambda s: s.filter_interval_days,
            device.async_set_filter_interval,
            int(_step(state.filter_interval_days, 1, 1, 365)),
        )
        await check(
            "imbalance allowed",
            lambda s: s.imbalance_allowed,
            device.async_set_imbalance_allowed,
            not state.imbalance_allowed,
        )
        for name, attr, setter in (
            ("supply imbalance", "supply_imbalance", device.async_set_supply_imbalance),
            (
                "exhaust imbalance",
                "exhaust_imbalance",
                device.async_set_exhaust_imbalance,
            ),
        ):
            value = getattr(state, attr)
            await check(
                name,
                lambda s, attr=attr: getattr(s, attr),
                setter,
                None if value is None else int(_step(value, 1, -15, 15)),
            )
        await check(
            "geo heat exchanger",
            lambda s: s.geo_heat_exchanger,
            device.async_set_geo_heat_exchanger,
            not state.geo_heat_exchanger,
        )
        await check(
            "geo minimum temperature",
            lambda s: s.geo_min_temp,
            device.async_set_geo_min_temp,
            None
            if state.geo_min_temp is None
            else _step(state.geo_min_temp, 0.5, 0, 10),
        )
        await check(
            "geo maximum temperature",
            lambda s: s.geo_max_temp,
            device.async_set_geo_max_temp,
            None
            if state.geo_max_temp is None
            else _step(state.geo_max_temp, 0.5, 15, 40),
        )
        print(f"\n{sum(results)} of {len(results)} writes verified and restored")
    finally:
        await connection.close()


asyncio.run(main())
