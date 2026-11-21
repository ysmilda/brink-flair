"""Dump every documented Brink Flair register, to check the register map.

Usage:
    python scripts/dump_registers.py HOST [PORT] [UNIT_ID] [OFFSET]

OFFSET is added to every address (try -1 if all reads fail with an illegal
address error). Needs `pip install "modbus-connection[tmodbus]"`.
"""

import asyncio
import sys

from modbus_connection import ModbusError, ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

INPUT_BLOCKS = [
    (4000, 6),
    (4010, 3),
    (4020, 5),
    (4030, 8),
    (4040, 8),
    (4050, 2),
    (4060, 2),
    (4070, 3),
    (4080, 4),
    (4090, 1),
    (4100, 20),
    (4150, 1),
    (4200, 8),
]
HOLDING_BLOCKS = [
    (6000, 4),
    (6030, 7),
    (6100, 6),
    (6110, 2),
    (6120, 1),
    (6130, 2),
    (6140, 2),
    (6150, 1),
    (6170, 2),
    (7990, 3),
    (8000, 4),
    (8010, 2),
]


async def main() -> None:
    """Read and print every register block."""
    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 502
    unit_id = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    offset = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    connection = ModbusConnection(ModbusTcpParams(host=host, port=port))
    unit = connection.for_unit(unit_id)
    try:
        for kind, blocks, read in (
            ("input", INPUT_BLOCKS, unit.read_input_registers),
            ("holding", HOLDING_BLOCKS, unit.read_holding_registers),
        ):
            for address, count in blocks:
                try:
                    values = await read(address + offset, count)
                except ModbusError as err:
                    print(f"{kind} {address}: {type(err).__name__}: {err}")
                    continue
                for index, value in enumerate(values):
                    print(f"{kind} {address + index}: {value} (0x{value:04X})")
    finally:
        await connection.close()


asyncio.run(main())
