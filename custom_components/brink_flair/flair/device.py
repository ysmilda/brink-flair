"""Talk to a Brink Flair over Modbus, independent of Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from modbus_connection import IllegalDataAddressError, ModbusUnit

from . import registers as r
from .models import UNKNOWN_MODEL, FlairModel, model_for_appliance_type

_LOGGER = logging.getLogger(__name__)


def _signed(value: int) -> int:
    """Interpret a 16-bit register as a signed number."""
    return value - 0x10000 if value & 0x8000 else value


def _bcd(value: int) -> str:
    """Decode four BCD digits, high nibble first."""
    return "".join(str((value >> shift) & 0xF) for shift in (12, 8, 4, 0))


# Brink reports a temperature sensor that is not fitted as 999.9 degC.
_NOT_FITTED = 9999


def _temperature(value: int) -> float | None:
    """Decode a temperature in tenths of a degree, or None if not fitted."""
    return None if value == _NOT_FITTED else _signed(value) / 10


def _u32(high: int, low: int) -> int:
    """Combine two registers into a 32-bit number, high word first."""
    return (high << 16) | low


@dataclass(frozen=True, kw_only=True)
class FlairIdentity:
    """What a Flair says about itself."""

    serial_number: str
    appliance_type: int
    software_version: str
    hardware_version: str
    model: FlairModel | None
    """None when the appliance type is not in the model table."""

    @property
    def model_name(self) -> str:
        """The model name, or a generic name for an unknown type."""
        return (self.model or UNKNOWN_MODEL).name


@dataclass(frozen=True, kw_only=True)
class FlairState:
    """One poll of a Flair's readings and settings."""

    active_function: int
    fan_control_type: int
    ventilation_mode: int
    switch_position: int
    control_mode: int
    standby: bool

    supply_fan_status: int
    supply_flow_setpoint: int
    supply_flow: int
    supply_fan_speed: int
    supply_temperature: float | None
    supply_humidity: float
    supply_pressure: float

    exhaust_fan_status: int
    exhaust_flow_setpoint: int
    exhaust_flow: int
    exhaust_fan_speed: int
    exhaust_temperature: float | None
    exhaust_humidity: float
    exhaust_pressure: float

    bypass_status: int
    frost_status: int
    frost_heater_power: int
    ntc1_temperature: float | None
    ntc2_temperature: float | None

    filter_dirty: bool
    filter_hours: int | None
    """None when the unit does not report it."""
    filter_interval_days: int
    operating_hours: int | None
    """None when the unit does not report it."""

    flow_presets: tuple[int, int, int, int]
    bypass_mode: int
    bypass_temp_indoor: float
    bypass_temp_outdoor: float
    bypass_hysteresis: float

    rht_humidity: float | None = None
    """Only when a humidity sensor is enabled."""
    preheater_status: int | None = None
    preheater_capacity: int | None = None
    co2: dict[int, int] = field(default_factory=dict)
    """CO2 level in ppm by sensor number (1 to 4), for running sensors."""

    @property
    def bypass_state(self) -> r.BypassState:
        """The bypass position, simplified to open, closed or initializing."""
        return r.BYPASS_STATUS_MAP.get(self.bypass_status, r.BypassState.INITIALIZING)

    @property
    def has_error(self) -> bool:
        """Whether the unit reports a fault."""
        return (
            self.active_function
            in (r.ActiveFunction.NON_BLOCKING_ERROR, r.ActiveFunction.BLOCKING_ERROR)
            or self.fan_control_type == r.FanControlType.ERROR
            or r.FanStatus.ERROR in (self.supply_fan_status, self.exhaust_fan_status)
            or self.frost_status == r.FrostStatus.ERROR
            or self.bypass_state == r.BypassState.ERROR
        )

    @property
    def frost_protection_active(self) -> bool:
        """Whether frost protection is acting on the airflow or the heater."""
        return self.frost_status in r.FROST_ACTIVE_STATES

    @property
    def filter_days_remaining(self) -> int | None:
        """Days until the filter warning, never below zero."""
        if self.filter_hours is None:
            return None
        return max(0, self.filter_interval_days - self.filter_hours // 24)


class FlairDevice:
    """A Brink Flair reached through a Modbus unit."""

    def __init__(self, unit: ModbusUnit) -> None:
        """Wrap a Modbus unit."""
        self._unit = unit
        self.identity: FlairIdentity | None = None
        self.has_rht_sensor = False
        self.has_co2_sensors = False
        self.has_preheater = False
        self._requested_level: r.VentilationLevel | None = None
        self._unsupported: set[int] = set()

    @property
    def connected(self) -> bool:
        """Whether the Modbus link is up."""
        return self._unit.connected

    @property
    def model(self) -> FlairModel:
        """The model, or a generic one before identification or when unknown."""
        if self.identity is None or self.identity.model is None:
            return UNKNOWN_MODEL
        return self.identity.model

    async def _read_input(self, address: int, count: int) -> list[int]:
        return await self._unit.read_input_registers(address + r.ADDRESS_OFFSET, count)

    async def _read_optional_input(self, address: int, count: int) -> list[int] | None:
        """Read input registers that not every unit or firmware serves."""
        if address in self._unsupported:
            return None
        try:
            return await self._read_input(address, count)
        except IllegalDataAddressError:
            _LOGGER.debug("Input register %s is not served by this unit", address)
            self._unsupported.add(address)
            return None

    async def _read_holding(self, address: int, count: int) -> list[int]:
        return await self._unit.read_holding_registers(
            address + r.ADDRESS_OFFSET, count
        )

    async def _write(self, address: int, value: int) -> None:
        await self._unit.write_register(address + r.ADDRESS_OFFSET, value)

    async def async_read_identity(self) -> FlairIdentity:
        """Read the serial number, versions and appliance type."""
        # 4006 to 4009 are not served, so these are two reads.
        versions = await self._read_input(r.IR_SOFTWARE_VERSION, 5)
        serial_regs = await self._read_input(r.IR_SERIAL_NUMBER, 3)
        sw_type_major, sw_minor_fix, sw_build, hardware, appliance_type = versions
        serial = "".join(_bcd(value) for value in serial_regs)
        software = (
            f"{sw_type_major & 0xFF}.{sw_minor_fix >> 8}.{sw_minor_fix & 0xFF}"
            f".{sw_build}"
        )
        self.identity = FlairIdentity(
            serial_number=serial,
            appliance_type=appliance_type,
            software_version=software,
            hardware_version=f"{hardware >> 8}.{hardware & 0xFF}",
            model=model_for_appliance_type(appliance_type),
        )
        await self._detect_options()
        return self.identity

    async def _detect_options(self) -> None:
        """Find out which optional parts are enabled."""
        (heater_mode,) = await self._read_holding(r.HR_EXTERNAL_HEATER_MODE, 1)
        (rht_mode,) = await self._read_holding(r.HR_RHT_SENSOR_MODE, 1)
        (co2_mode,) = await self._read_holding(r.HR_CO2_SENSOR_MODE, 1)
        self.has_preheater = heater_mode == 1
        self.has_rht_sensor = rht_mode == 1
        self.has_co2_sensors = co2_mode == 1

    async def async_update(self) -> FlairState:
        """Read all readings and settings."""
        status = await self._read_input(r.IR_ACTIVE_FUNCTION, 5)
        supply = await self._read_input(r.IR_SUPPLY_FAN_STATUS, 8)
        exhaust = await self._read_input(r.IR_EXHAUST_FAN_STATUS, 8)
        (bypass_status,) = await self._read_input(r.IR_BYPASS_STATUS, 1)
        frost = await self._read_input(r.IR_FROST_STATUS, 2)
        sensors = await self._read_input(r.IR_SWITCH_POSITION, 4)
        (filter_status,) = await self._read_input(r.IR_FILTER_STATUS, 1)
        operating = await self._read_optional_input(r.IR_OPERATING_HOURS, 2)
        filter_hours = await self._read_optional_input(r.IR_FILTER_HOURS, 1)
        presets = await self._read_holding(r.HR_FLOW_PRESETS, 4)
        bypass = await self._read_holding(r.HR_BYPASS_MODE, 4)
        (filter_days,) = await self._read_holding(r.HR_FILTER_DAYS, 1)
        control = await self._read_holding(r.RC_CONTROL, 4)

        control_mode = control[0]
        if (
            self._requested_level is None
            and control_mode == r.ControlMode.SWITCH
            and control[1] in iter(r.VentilationLevel)
        ):
            # Pick up a level set before Home Assistant restarted.
            self._requested_level = r.VentilationLevel(control[1])
        if self._requested_level is not None and control_mode == r.ControlMode.OFF:
            # The remote control registers reset after a power cut.
            _LOGGER.info(
                "Modbus control was reset, sending the ventilation level again"
            )
            await self._apply_level(self._requested_level)
            control_mode = r.ControlMode.SWITCH

        state = FlairState(
            active_function=status[0],
            fan_control_type=status[1],
            ventilation_mode=status[2],
            switch_position=sensors[0],
            control_mode=control_mode,
            standby=control[3] == 1,
            supply_pressure=_signed(status[3]) / 10,
            exhaust_pressure=_signed(status[4]) / 10,
            supply_fan_status=supply[0],
            supply_flow_setpoint=supply[1],
            supply_flow=supply[2],
            supply_fan_speed=supply[4],
            supply_temperature=_temperature(supply[6]),
            supply_humidity=supply[7],
            exhaust_fan_status=exhaust[0],
            exhaust_flow_setpoint=exhaust[1],
            exhaust_flow=exhaust[2],
            exhaust_fan_speed=exhaust[4],
            exhaust_temperature=_temperature(exhaust[6]),
            exhaust_humidity=exhaust[7],
            bypass_status=bypass_status,
            frost_status=frost[0],
            frost_heater_power=frost[1],
            ntc1_temperature=_temperature(sensors[1]),
            ntc2_temperature=_temperature(sensors[2]),
            filter_dirty=filter_status == 1,
            operating_hours=_u32(*operating) if operating else None,
            filter_hours=filter_hours[0] if filter_hours else None,
            filter_interval_days=filter_days,
            flow_presets=(presets[0], presets[1], presets[2], presets[3]),
            bypass_mode=bypass[0],
            bypass_temp_indoor=bypass[1] / 10,
            bypass_temp_outdoor=bypass[2] / 10,
            bypass_hysteresis=bypass[3] / 10,
            rht_humidity=sensors[3] if self.has_rht_sensor else None,
            **await self._read_options(),
        )
        return state

    async def _read_options(self) -> dict:
        """Read the registers of optional parts that are present."""
        values: dict = {}
        if self.has_preheater:
            try:
                heater = await self._read_input(r.IR_PREHEATER_STATUS, 2)
            except IllegalDataAddressError:
                self.has_preheater = False
            else:
                values["preheater_status"] = heater[0]
                values["preheater_capacity"] = heater[1]
        if self.has_co2_sensors:
            co2 = await self._read_input(r.IR_CO2_SENSORS, 8)
            # Only a running sensor has a valid reading. An absent sensor
            # reports an error status.
            values["co2"] = {
                number + 1: co2[number * 2 + 1]
                for number in range(4)
                if co2[number * 2] == r.CO2SensorStatus.RUNNING
            }
        return values

    async def _apply_level(self, level: r.VentilationLevel) -> None:
        await self._write(r.RC_CONTROL, r.ControlMode.SWITCH)
        await self._write(r.RC_SWITCH_POSITION, level)

    async def async_set_level(self, level: r.VentilationLevel) -> None:
        """Take over control and set the ventilation level."""
        await self._apply_level(level)
        self._requested_level = level

    async def async_release_control(self) -> None:
        """Hand control back to the unit's display and wall switch."""
        await self._write(r.RC_CONTROL, r.ControlMode.OFF)
        self._requested_level = None

    async def async_set_standby(self, standby: bool) -> None:
        """Put the unit in standby, or wake it."""
        await self._write(r.RC_STANDBY, 1 if standby else 2)

    async def async_set_flow_preset(self, level: r.VentilationLevel, flow: int) -> None:
        """Set the airflow in m3/h for a ventilation level."""
        await self._write(r.HR_FLOW_PRESETS + level, flow)

    async def async_set_bypass_mode(self, mode: r.BypassMode) -> None:
        """Set the bypass to automatic, closed or open."""
        await self._write(r.HR_BYPASS_MODE, mode)

    async def async_set_bypass_temp_indoor(self, value: float) -> None:
        """Set the indoor temperature above which the bypass may open."""
        await self._write(r.HR_BYPASS_TEMP_INDOOR, round(value * 10))

    async def async_set_bypass_temp_outdoor(self, value: float) -> None:
        """Set the outdoor temperature above which the bypass may open."""
        await self._write(r.HR_BYPASS_TEMP_OUTDOOR, round(value * 10))

    async def async_set_bypass_hysteresis(self, value: float) -> None:
        """Set the bypass hysteresis."""
        await self._write(r.HR_BYPASS_HYSTERESIS, round(value * 10))

    async def async_set_filter_interval(self, days: int) -> None:
        """Set the number of days between filter warnings."""
        await self._write(r.HR_FILTER_DAYS, days)

    async def async_reset_filter(self) -> None:
        """Reset the filter counter after a filter change."""
        await self._write(r.RC_FILTER_RESET, 1)
