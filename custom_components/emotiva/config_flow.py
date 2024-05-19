import logging

from typing import Any, Dict, Optional

import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_CTRL_PORT,
    CONF_NOTIFICATIONS,
    CONF_DISCOVER,
    CONF_MANUAL,
    CONF_NOTIFY_PORT,
    CONF_PROTO_VER,
)

from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_MODEL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get,
)


_LOGGER = logging.getLogger(__name__)

EMO_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DISCOVER, default=True): cv.boolean,
        vol.Optional(CONF_MANUAL, default=False): cv.boolean,
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_MODEL): cv.string,
        vol.Optional(CONF_CTRL_PORT, default=7002): vol.Coerce(int),
        vol.Optional(CONF_NOTIFY_PORT, default=7003): vol.Coerce(int),
        vol.Optional(CONF_PROTO_VER, default=3.0): vol.Coerce(float),
    }
)

EMO_OPTIONS_SCHEMA = vol.Schema({vol.Optional(CONF_NOTIFICATIONS): cv.string})


class SelectError(exceptions.HomeAssistantError):
    """Error"""

    pass


async def validate_auth(hass: core.HomeAssistant, data: dict) -> None:

    _models = ["XMC-1", "XMC-2", "RMC-1", "RMC-1l"]

    if "host" not in data.keys():
        data["host"] = ""
    if "name" not in data.keys():
        data["name"] = ""
    if "model" not in data.keys():
        data["model"] = ""
    if "manual" not in data.keys():
        data["manual"] = False
    if "discover" not in data.keys():
        data["discover"] = False

    if data["manual"] and (len(data["host"]) < 3 or len(data["name"]) < 1):
        # Manual entry requires host and name and model
        raise ValueError
    if data["manual"] == False and data["discover"] == False:
        raise SelectError

    if data["manual"] and (len(data["model"]) < 1 or data["model"] not in _models):
        raise ValueError


class EmotivaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Invoked when a user initiates a flow via the user interface."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_auth(self.hass, user_input)
            except ValueError:
                errors["base"] = "data"
            except SelectError:
                errors["base"] = "select"

            if not errors:
                # Input is valid, set data.
                self.data = user_input
                return self.async_create_entry(
                    title="Emotiva Processor", data=self.data
                )

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(
            step_id="user", data_schema=EMO_CONFIG_SCHEMA, errors=errors
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
                del user_input["notifications"]
            _LOGGER.debug("Returning %s", user_input)
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "notifications",
                        default=self.config_entry.options.get("notifications"),
                    ): cv.string,
                    vol.Optional(
                        "delete_existing",
                        default=False,
                    ): cv.boolean,
                }
            ),
        )
