from __future__ import annotations

import logging
import asyncio

from collections.abc import Iterable
from typing import Any

from .const import DOMAIN

from .emotiva import Emotiva

import voluptuous as vol

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
)

from homeassistant import config_entries, core

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    discovery_flow,
    entity_platform,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.device_registry import DeviceInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
) -> None:

    config = hass.data[DOMAIN][config_entry.entry_id]

    if config_entry.options:
        config.update(config_entry.options)

    emotiva_list = config["emotiva"]

    for emotiva in emotiva_list:
        async_add_entities([EmotivaDevice(emotiva, hass)])


class EmotivaDevice(RemoteEntity):
    # Representation of a Emotiva Processor

    def __init__(self, device, hass):

        self._device = device
        self._hass = hass
        self._entity_id = "remote.emotivaprocessor"
        self._unique_id = "emotiva_" + self._device.name.replace(" ", "_").replace(
            "-", "_"
        ).replace(":", "_")

    async def async_added_to_hass(self):
        """Handle being added to hass."""
        #        await super().async_added_to_hass()
        self._device.set_remote_update_cb(self.async_update_callback)

    async def async_will_remove_from_hass(self) -> None:
        self._device.set_remote_update_cb(None)

    def async_update_callback(self, reason=False):
        """Update the device's state."""
        _LOGGER.debug("Calling async_schedule_update_ha_state")
        self.async_schedule_update_ha_state()

    @property
    def name(self):
        return "Remote"

    @property
    def has_entity_name(self):
        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._unique_id)
            },
            name=self._device.name,
            manufacturer="Emotiva",
            model=self._device.model,
        )

    async def async_update(self):
        pass

    @property
    def state(self):
        if self._device.power == False:
            return "off"
        elif self._device.power == True:
            return "on"
        else:
            return None

    should_poll = False

    @property
    def should_poll(self):
        return False

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def entity_id(self):
        return self._entity_id

    @entity_id.setter
    def entity_id(self, entity_id):
        self._entity_id = entity_id

    async def async_turn_off(self) -> None:
        await self._device.async_turn_off()

    async def async_turn_on(self) -> None:
        await self._device.async_turn_on()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        try:
            emo_Command = command[0].replace(" ", "").split(",")[0]
            Value = command[0].replace(" ", "").split(",")[1]
            if len(emo_Command) == 0 or len(Value) == 0:
                _LOGGER.error("Invalid remote command format.  Must be command,value")
                return False
            else:
                await self._device.async_send_command(emo_Command, Value)
        except:
            _LOGGER.error("Invalid remote command format.  Must be command,value")
            return False
