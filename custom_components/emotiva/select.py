from __future__ import annotations

import logging

from homeassistant import config_entries, core
from homeassistant.components.select import (
    SelectEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

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


class EmotivaDevice(SelectEntity):
    # Representation of a Emotiva Processor

    def __init__(self, device, hass):
        self._device = device
        self._hass = hass
        self._entity_id = "select.emotivaprocessor_source"
        self._unique_id = "emotiva_" + self._device.name.replace(" ", "_").replace(
            "-", "_"
        ).replace(":", "_")

    async def async_added_to_hass(self):
        """Handle being added to hass."""
        self._device.set_select_update_cb(self.async_update_callback)

    async def async_will_remove_from_hass(self) -> None:
        self._device.set_select_update_cb(None)

    @callback
    def async_update_callback(self, reason=False):
        """Update the device's state."""
        _LOGGER.debug("Calling async_schedule_update_ha_state")
        self.async_schedule_update_ha_state()

    @property
    def name(self):
        return self._device.name + " Source"

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

    @property
    def should_poll(self):
        return False

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def entity_id(self):
        return self._entity_id

    @property
    def icon(self):
        return "mdi:hdmi-port"

    @entity_id.setter
    def entity_id(self, entity_id):
        self._entity_id = entity_id

    async def async_select_option(self, source: str) -> None:
        await self._device.async_set_source(source)

    @property
    def options(self):
        return self._device.sources

    @property
    def current_option(self):
        return self._device.source
