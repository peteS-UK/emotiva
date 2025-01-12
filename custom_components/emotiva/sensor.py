from __future__ import annotations

import logging

from .const import DOMAIN

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass

from homeassistant import config_entries, core

from homeassistant.core import callback

from homeassistant.helpers.device_registry import DeviceInfo

_LOGGER = logging.getLogger(__name__)

SENSORS = [
    {
        "name": "volume",
        "display_name": "Volume",
        "icon": "mdi:volume-off",
        "class": SensorDeviceClass.SOUND_PRESSURE,
        "uom": "dB",
        "state": "volume",
    },
    {
        "name": "audio_input",
        "display_name": "Audio Input",
        "icon": "mdi:volume-source",
        "class": None,
        "uom": None,
        "state": "audio_input",
    },
    {
        "name": "audio_bitstream",
        "display_name": "Audio Bitstream",
        "icon": "mdi:volume-equal",
        "class": None,
        "uom": None,
        "state": "audio_bitstream",
    },
    {
        "name": "video_input",
        "display_name": "Video Input",
        "icon": "mdi:video-switch-outline",
        "class": None,
        "uom": None,
        "state": "video_input",
    },
    {
        "name": "video_format",
        "display_name": "Video Format",
        "icon": "mdi:video-image",
        "class": None,
        "uom": None,
        "state": "video_format",
    },
    {
        "name": "video_space",
        "display_name": "Video Space",
        "icon": "mdi:video-outline",
        "class": None,
        "uom": None,
        "state": "video_space",
    },
]


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
        for sensor in SENSORS:
            async_add_entities([EmotivaDevice(emotiva, hass, sensor)])


class EmotivaDevice(SensorEntity):
    # Representation of a Emotiva Processor

    def __init__(self, device, hass, sensor):
        self._device = device
        self._hass = hass
        self._entity_id = "sensor.emotivaprocessor_" + sensor["name"]
        self._device_id = "emotiva_" + self._device.name.replace(" ", "_").replace(
            "-", "_"
        ).replace(":", "_")
        if sensor["name"] == "volume":
            # Keep the original name without sensor name for volume to prevent breaking change
            self._unique_id = self._device_id
        else:
            self._unique_id = self._device_id + sensor["name"]
        self._sensor = sensor

    async def async_added_to_hass(self):
        """Handle being added to hass."""
        self._device.set_sensor_update_cb(
            self._sensor["name"], self.async_update_callback
        )

    async def async_will_remove_from_hass(self) -> None:
        self._device.remove_sensor_update_cb(self._sensor["name"])

    @callback
    def async_update_callback(self, reason=False):
        """Update the device's state."""
        self.async_schedule_update_ha_state()

    @property
    def name(self):
        return self._device.name + " " + self._sensor["display_name"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._device_id)
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
        if self._sensor["name"] == "volume":
            if self._device.mute:
                return "mdi:volume-off"
            else:
                return "mdi:volume-high"
        else:
            return self._sensor["icon"]

    @entity_id.setter
    def entity_id(self, entity_id):
        self._entity_id = entity_id

    @property
    def device_class(self):
        return self._sensor["class"]

    @property
    def native_unit_of_measurement(self):
        return self._sensor["uom"]

    @property
    def native_value(self):
        return eval("self._device._current_state['" + self._sensor["state"] + "']")
