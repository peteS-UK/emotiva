import logging

from typing import Any

import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_NOTIFICATIONS,
    CONF_PROTO_VER,
    CONF_TYPE,
    CONF_PING_INTERVAL,
)

from asyncping3 import ping


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

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)

import asyncio

_LOGGER = logging.getLogger(__name__)

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


from .emotiva import Emotiva


@config_entries.HANDLERS.register(DOMAIN)
class EmotivaConfigFlow(ConfigFlow):
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the config flow."""
        self.discovered_devices = []
        self.discovery_task: asyncio.Task | None = None

    async def _discover(self):
        """Discover Emotiva devices."""
        receivers = await self.hass.async_add_executor_job(Emotiva.discover, 3)
        if receivers:
            for ip, xml in receivers:
                device = Emotiva(self.hass, None, ip, xml)
                if device.name not in [d.name for d in self.discovered_devices]:
                    self.discovered_devices.append(device)
        await asyncio.sleep(2)

    async def async_step_start_discovery(self, user_input=None):
        """Start discovery."""
        _LOGGER.debug("Starting discovery task")
        if not self.discovery_task:
            self.discovery_task = self.hass.async_create_task(self._discover())

        if self.discovery_task is not None and self.discovery_task.done():

            if self.discovery_task is not None:
                self.discovery_task.cancel()
                try:
                    await self.discovery_task
                except asyncio.CancelledError:
                    _LOGGER.debug("Discovery cancelled")
                self.discovery_task = None

            return self.async_show_progress_done(
                next_step_id=(
                    "choose_device" if self.discovered_devices else "discovery_failed"
                )
            )

        return self.async_show_progress(
            step_id="start_discovery",
            progress_action="start_discovery",
            progress_task=self.discovery_task,
        )

    async def async_step_discovery_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a failed discovery."""

        return self.async_show_menu(step_id="discovery_failed", menu_options=["manual"])

    async def async_step_choose_device(self, user_input=None):
        """Handle multiple devices found."""
        if not self.discovered_devices:
            return self.async_show_form(
                step_id="choose_device",
                data_schema=None,
                description_placeholders={
                    "not_found": "No devices found. Please use manual configuration."
                },
            )

        if user_input is not None:
            for device in self.discovered_devices:
                if device.name == user_input["device"]:
                    await self.async_set_unique_id(
                        f"emotiva_{device.address.replace('.', '_')}"
                    )
                    self._abort_if_unique_id_configured()
                    data = {
                        CONF_HOST: device.address,
                        CONF_NAME: device.name,
                        CONF_MODEL: device.model,
                        CONF_PROTO_VER: device._proto_ver,
                    }
                    return self.async_create_entry(title=device.name, data=data)

        device_names = [device.name for device in self.discovered_devices]
        return self.async_show_form(
            step_id="choose_device",
            data_schema=vol.Schema({vol.Required("device"): vol.In(device_names)}),
        )

    async def async_step_user(self, user_input=None):
        """Invoked when a user initiates a flow via the user interface."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["start_discovery", "manual"],
        )

    async def async_step_manual(self, user_input=None):
        """Invoked when a user initiates a flow via the user interface."""
        errors = {}
        if user_input is not None:
            try:
                ping_result = await ping(user_input[CONF_HOST], timeout=1)
                if ping_result is None:
                    raise Exception(TimeoutError)
                await self.async_set_unique_id(
                    f"emotiva_{user_input[CONF_HOST].replace('.', '_')}"
                )
                self._abort_if_unique_id_configured()
            except Exception:
                errors[CONF_HOST] = "cannot_connect"

            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                EMO_MANUAL_SCHEMA, user_input
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlow):
    def __init__(self) -> None:
        """Initialize options flow."""
        # self.config_entry = config_entry

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
