import logging

from typing import Any

import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_CTRL_PORT,
    CONF_NOTIFICATIONS,
    CONF_NOTIFY_PORT,
    CONF_PROTO_VER,
    CONF_TYPE,
    CONF_PING_INTERVAL,
)

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_MODEL
from homeassistant.core import callback

import homeassistant.helpers.config_validation as cv

from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

_LOGGER = logging.getLogger(__name__)

EMO_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TYPE, default=True): SelectSelector(
            SelectSelectorConfig(
                mode=SelectSelectorMode.LIST,
                options=[
                    "Discover",
                    "Manual",
                ],
            )
        ),
    }
)

EMO_MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_MODEL): SelectSelector(
            SelectSelectorConfig(
                mode=SelectSelectorMode.DROPDOWN,
                options=["XMC-1", "XMC-2", "RMC-1", "RMC-1l"],
            )
        ),
        vol.Required(CONF_CTRL_PORT, default=7002): vol.Coerce(int),
        vol.Required(CONF_NOTIFY_PORT, default=7003): vol.Coerce(int),
        vol.Required(CONF_PROTO_VER, default="3.0"): vol.All(
            SelectSelector(
                SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=["3.0", "2.0"],
                )
            ),
            vol.Coerce(float),
        ),
    }
)

EMO_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NOTIFICATIONS): cv.string,
        vol.Optional(
            "delete_existing",
            default=False,
        ): cv.boolean,
        vol.Optional(CONF_PING_INTERVAL): vol.All(
            NumberSelector(
                NumberSelectorConfig(min=0, max=600, mode=NumberSelectorMode.SLIDER)
            ),
            vol.Coerce(int),
        ),
    }
)


class EmotivaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Invoked when a user initiates a flow via the user interface."""
        if user_input is not None:
            if user_input[CONF_TYPE] == "Discover":
                # Input is valid, set data.
                self.data = user_input
                return self.async_create_entry(
                    title="Emotiva Processor", data=self.data
                )
            else:
                return self.async_show_form(
                    step_id="manual", data_schema=EMO_MANUAL_SCHEMA
                )

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(step_id="user", data_schema=EMO_CONFIG_SCHEMA)

    async def async_step_manual(self, user_input=None):
        """Invoked when a user initiates a flow via the user interface."""
        if user_input is not None:
            # Input is valid, set data.
            self.data = user_input
            self.data[CONF_TYPE] = "Manual"
            return self.async_create_entry(title="Emotiva Processor", data=self.data)

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(
            step_id="manual",
            data_schema=EMO_MANUAL_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        _LOGGER.debug("1 user_input %s", user_input)
        """Manage the options."""

        if user_input is not None:
            if user_input["delete_existing"]:
                _LOGGER.debug("Deleting existing notification entry")
                del user_input[CONF_NOTIFICATIONS]
            _LOGGER.debug("Returning %s", user_input)
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                EMO_OPTIONS_SCHEMA,
                {
                    CONF_NOTIFICATIONS: self.config_entry.options.get(
                        CONF_NOTIFICATIONS
                    ),
                    CONF_PING_INTERVAL: self.config_entry.options.get(
                        CONF_PING_INTERVAL, 60
                    ),
                    "delete_existing": False,
                },
            ),
        )
