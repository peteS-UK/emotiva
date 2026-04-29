from __future__ import annotations

import logging

from collections.abc import Iterable
from typing import Any

from .const import DOMAIN

from homeassistant.components.remote import (
    RemoteEntity,
)

from homeassistant import config_entries, core

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
        self._device.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._device.remove_callback(self.async_write_ha_state)

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
        if not self._device.power:
            return "off"
        elif self._device.power:
            return "on"
        else:
            return None

    @property
    def should_poll(self):
        return False

    @property
    def available(self) -> bool:
        """Return True if the device is currently online and available."""
        # We will add an 'is_online' flag to your device class
        return self._device.is_online

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

    async def async_send_command(
        self, command: Iterable[str], **kwargs: Any
    ) -> None | bool:
        """Send commands to the device."""
        for cmd in command:
            try:
                # Clean the string and split it
                parts = cmd.replace(" ", "").split(",")

                # Ensure we actually have two parts (command and value) before assigning
                if len(parts) < 2 or len(parts[0]) == 0 or len(parts[1]) == 0:
                    _LOGGER.error(
                        "Invalid remote command format: '%s'. Must be 'command,value'",
                        cmd,
                    )
                    continue

                emo_command = parts[0]
                value = parts[1]

                await self._device.async_send_command(emo_command, value)

            except Exception as err:
                _LOGGER.error("Unexpected error sending command '%s': %s", cmd, err)
