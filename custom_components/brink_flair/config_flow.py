"""Config flow for the Brink Flair integration."""

from collections.abc import Mapping
from typing import Any, override

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigEntryState, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SerialPortSelector,
    TextSelector,
)
from modbus_connection import ModbusError
import probatio

from .const import (
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_STOPBITS,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DOMAIN,
    PARITY_OPTIONS,
    TYPE_SERIAL,
    TYPE_TCP,
)
from .flair import (
    DEFAULT_BAUDRATE,
    DEFAULT_STOPBITS,
    DEFAULT_UNIT_ID,
    FlairDevice,
    FlairIdentity,
)
from .helpers import create_modbus_params

STEP_RECONFIGURE_TCP = "reconfigure_tcp"
STEP_RECONFIGURE_SERIAL = "reconfigure_serial"

BAUDRATES = ["1200", "2400", "4800", "9600", "19200", "38400", "56000", "115200"]

UNIT_ID_SELECTOR = probatio.All(
    NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=247)),
    probatio.Coerce(int),
)

STEP_TCP_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): TextSelector(),
        probatio.Required(CONF_PORT, default=DEFAULT_PORT): probatio.All(
            NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
            ),
            probatio.Coerce(int),
        ),
        probatio.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): UNIT_ID_SELECTOR,
    }
)

STEP_SERIAL_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_DEVICE): SerialPortSelector(),
        probatio.Required(CONF_BAUDRATE, default=str(DEFAULT_BAUDRATE)): probatio.All(
            SelectSelector(
                SelectSelectorConfig(
                    options=BAUDRATES, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            probatio.Coerce(int),
        ),
        probatio.Required(CONF_PARITY, default="even"): SelectSelector(
            SelectSelectorConfig(
                options=list(PARITY_OPTIONS),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_PARITY,
            )
        ),
        probatio.Required(CONF_STOPBITS, default=str(DEFAULT_STOPBITS)): probatio.All(
            SelectSelector(
                SelectSelectorConfig(options=["1", "2"], mode=SelectSelectorMode.LIST)
            ),
            probatio.Coerce(int),
        ),
        probatio.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): UNIT_ID_SELECTOR,
    }
)


def _as_form_values(data: Mapping[str, Any]) -> dict[str, Any]:
    """Turn stored settings into the values the form's selectors expect."""
    return {
        key: str(value) if key in (CONF_BAUDRATE, CONF_STOPBITS) else value
        for key, value in data.items()
    }


async def _async_probe(hass: HomeAssistant, data: Mapping[str, Any]) -> FlairIdentity:
    """Connect to the unit and identify it, or raise."""
    params = create_modbus_params(data)
    async with async_get_temporary_unit(hass, params, data[CONF_UNIT_ID]) as unit:
        return await FlairDevice(unit).async_read_identity()


class BrinkFlairConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Brink Flair config flow."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick how the unit is reached."""
        return self.async_show_menu(
            step_id="user", menu_options=[TYPE_TCP, TYPE_SERIAL]
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a unit reached through a Modbus TCP gateway."""
        return await self._async_step_link(TYPE_TCP, STEP_TCP_DATA_SCHEMA, user_input)

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a unit reached through a serial RS-485 adapter."""
        return await self._async_step_link(
            TYPE_SERIAL, STEP_SERIAL_DATA_SCHEMA, user_input
        )

    async def _async_step_link(
        self,
        connection_type: str,
        schema: probatio.Schema,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Ask for the link settings, then probe the unit behind them."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_TYPE: connection_type, **user_input}
            identity, errors, placeholders = await self._async_validate(data)
            if identity is not None:
                await self.async_set_unique_id(identity.serial_number)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=identity.model_name, data=data)

        return self.async_show_form(
            step_id=connection_type,
            data_schema=self.add_suggested_values_to_schema(
                schema, _as_form_values(user_input or {})
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick how the unit is reached from now on."""
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=[STEP_RECONFIGURE_TCP, STEP_RECONFIGURE_SERIAL],
        )

    async def async_step_reconfigure_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reach the unit through a Modbus TCP gateway from now on."""
        return await self._async_step_reconfigure_link(
            STEP_RECONFIGURE_TCP, TYPE_TCP, STEP_TCP_DATA_SCHEMA, user_input
        )

    async def async_step_reconfigure_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reach the unit through a serial RS-485 adapter from now on."""
        return await self._async_step_reconfigure_link(
            STEP_RECONFIGURE_SERIAL, TYPE_SERIAL, STEP_SERIAL_DATA_SCHEMA, user_input
        )

    async def _async_step_reconfigure_link(
        self,
        step_id: str,
        connection_type: str,
        schema: probatio.Schema,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Ask for new link settings, then check they reach the same unit."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_TYPE: connection_type, **user_input}

            # The shared connection refuses a second set of settings for the
            # same device, so free it before probing the new settings.
            relinking = False
            if entry.state in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_RETRY):
                current = create_modbus_params(entry.data)
                new = create_modbus_params(data)
                if new.endpoint == current.endpoint and new != current:
                    relinking = await self.hass.config_entries.async_unload(
                        entry.entry_id
                    )

            identity, errors, placeholders = await self._async_validate(data)
            probed = identity.serial_number if identity is not None else None

            if relinking and probed != entry.unique_id:
                await self.hass.config_entries.async_setup(entry.entry_id)

            if identity is not None:
                await self.async_set_unique_id(probed)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data=data)

        suggested = user_input or (
            entry.data
            if entry.data[CONF_TYPE] == connection_type
            else {CONF_UNIT_ID: entry.data[CONF_UNIT_ID]}
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                schema, _as_form_values(suggested)
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _async_validate(
        self, data: dict[str, Any]
    ) -> tuple[FlairIdentity | None, dict[str, str], dict[str, str]]:
        """Probe the unit, returning its identity or the errors to show."""
        try:
            identity = await _async_probe(self.hass, data)
        except (ModbusError, HomeAssistantError) as err:
            return None, {"base": "cannot_connect"}, {"error": str(err)}
        return identity, {}, {}
