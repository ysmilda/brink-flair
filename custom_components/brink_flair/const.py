"""Constants for the Brink Flair integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "brink_flair"
MANUFACTURER: Final = "Brink Climate Systems"

CONF_BAUDRATE: Final = "baudrate"
CONF_PARITY: Final = "parity"
CONF_STOPBITS: Final = "stopbits"
CONF_UNIT_ID: Final = "unit_id"

TYPE_TCP: Final = "tcp"
TYPE_SERIAL: Final = "serial"

DEFAULT_PORT: Final = 502

SCAN_INTERVAL: Final = timedelta(seconds=30)
