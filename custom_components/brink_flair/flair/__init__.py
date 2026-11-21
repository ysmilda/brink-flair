"""Brink Flair Modbus protocol.

Nothing in this package imports Home Assistant, so it can move to its own
PyPI library when the integration goes into Home Assistant core.
"""

from .device import FlairDevice, FlairIdentity, FlairState
from .models import APPLIANCE_TYPES, UNKNOWN_MODEL, FlairModel
from .registers import (
    DEFAULT_BAUDRATE,
    DEFAULT_PARITY,
    DEFAULT_STOPBITS,
    DEFAULT_UNIT_ID,
    ActiveFunction,
    BypassMode,
    BypassState,
    ControlMode,
    FrostStatus,
    VentilationLevel,
)

__all__ = [
    "APPLIANCE_TYPES",
    "DEFAULT_BAUDRATE",
    "DEFAULT_PARITY",
    "DEFAULT_STOPBITS",
    "DEFAULT_UNIT_ID",
    "UNKNOWN_MODEL",
    "ActiveFunction",
    "BypassMode",
    "BypassState",
    "ControlMode",
    "FlairDevice",
    "FlairIdentity",
    "FlairModel",
    "FlairState",
    "FrostStatus",
    "VentilationLevel",
]
