

from __future__ import annotations

import logging

DOMAIN = "emotiva"

from .emotiva import Emotiva

import voluptuous as vol

from homeassistant.components.media_player import (
	PLATFORM_SCHEMA,
	MediaPlayerEntity,
	MediaPlayerEntityFeature,
	MediaPlayerState
)

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

DEFAULT_NAME = "Emotiva Processor - Media Player"
SERVICE_SEND_COMMAND = "send_command"

from .const import (
	CONF_NOTIFICATIONS,
	CONF_NOTIFY_PORT,
	CONF_CTRL_PORT
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
	{
		vol.Required(CONF_HOST): cv.string,
		vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
		vol.Optional(CONF_NOTIFICATIONS, default=None): cv.string,
		vol.Optional(CONF_CTRL_PORT, default=7002): vol.Coerce(int),
		vol.Optional(CONF_NOTIFY_PORT, default=7003): vol.Coerce(int)
	}
)

SUPPORT_EMOTIVA = (
	MediaPlayerEntityFeature.VOLUME_STEP
	| MediaPlayerEntityFeature.VOLUME_MUTE
	| MediaPlayerEntityFeature.TURN_ON
	| MediaPlayerEntityFeature.TURN_OFF
	| MediaPlayerEntityFeature.SELECT_SOURCE
	| MediaPlayerEntityFeature.VOLUME_SET
	| MediaPlayerEntityFeature.SELECT_SOUND_MODE 
)

#import asyncio

#def setup_platform(
#async
async def async_setup_platform(
				hass: HomeAssistant,
				config: ConfigType,
				#add_entities: AddEntitiesCallback,
				#async
				async_add_entities: AddEntitiesCallback,
				discovery_info: DiscoveryInfoType | None = None,
			) -> None:

	from datetime import timedelta

	SCAN_INTERVAL = timedelta(seconds=20)

	receivers = await hass.async_add_executor_job(Emotiva.discover,3)
	#receivers = Emotiva.discover(version=3)
	
	for receiver in receivers:

		_ip, _xml = receiver

		#emotiva = Emotiva(config[CONF_HOST], _ctrl_port = 7002, _notify_port = 7003)
		emotiva = Emotiva(_ip, _xml)

		#Get additional notify
		_notify_set = set(config[CONF_NOTIFICATIONS].split(","))

		emotiva._events = emotiva._events.union(_notify_set)
		emotiva._current_state.update(dict((m, None) for m in _notify_set))

		async_add_entities([EmotivaDevice(emotiva)])

	# Register entity services
	platform = entity_platform.async_get_current_platform()
	platform.async_register_entity_service(
		SERVICE_SEND_COMMAND,
		{
			vol.Required("Command"): cv.string,
			vol.Required("Value"): cv.string,
		},
		EmotivaDevice.send_command.__name__,
	)

class EmotivaDevice(MediaPlayerEntity):
	# Representation of a Emotiva Processor

	def __init__(self, device):

		self._device = device
		self._entity_id = "media_player.emotivaprocessor"
		self._unique_id = "emotiva_"+self._device.name.replace(" ","_").replace("-","_").replace(":","_")
		self._device_class = "receiver"
		
		self._device.connect()
	
	@property
	def icon(self):
		return "mdi:audio-video"

	@property
	def name(self):
		return self._device.name

	@property
	def device_info(self) -> DeviceInfo:
		return ({
				"identifiers":"{("+DOMAIN+", '11223344')}",
				"manufacturer":"Emotiva",
				"model":"XMC1",
				"name":"XMC"})

	@property
	def friendly_name(self):
		return self._device.name + " Processor"

	@property
	def has_entity_name(self):
		return True

	@property
	def unique_id(self):
		return self._unique_id
		
	@property
	def entity_id(self):
		return self._entity_id
	
	@property
	def device_class(self):
		return self._device_class

	@entity_id.setter
	def entity_id(self, entity_id):
		self._entity_id = entity_id

	@property
	def state(self) -> MediaPlayerState | None:
			if self._device.power == False:
				return MediaPlayerState.OFF
			if self._device.power == True:
				return MediaPlayerState.ON

			return None

	@property
	def source_list(self):
		return self._device.sources
	
	@property
	def source(self):
		return self._device.source

	@property
	def sound_mode_list(self):
		return self._device.modes	

	@property
	def sound_mode(self):
		return self._device.mode

	@property
	def supported_features(self) -> MediaPlayerEntityFeature:
			return SUPPORT_EMOTIVA

	@property
	def is_volume_muted(self):
		return self._device.mute
	
	@property 
	def extra_state_attributes(self):

		_attributes = {}

		for ev in self._device._events:
			if ev.startswith("input_") == False and  ev.startswith("power") == False:
				_attributes[ev] = self._device._current_state[ev]
		
		return _attributes
	
	@property
	def volume_level(self):
		if self._device.volume is None:
			# device is muted
			return 0.0
		else:
			return float("%.2f" % ((self._device.volume-self._device._volume_min)/self._device._volume_range))

	def set_volume_level(self, volume: float) -> None:
		_vol = ((volume * self._device._volume_range)+self._device._volume_min)
		self._device.volume = str(_vol)

	def turn_off(self) -> None:
		self._device.power = False

	def turn_on(self) -> None:
		self._device.power = True

	def mute_volume(self, mute: bool) -> None:
		self._device.mute = mute

	def volume_up(self):
		self._device.volume_up()

	def volume_down(self):
		self._device.volume_down()

	def update(self):
		self._device._update_status(self._device._events, float(self._device._proto_ver))		

	def select_source(self, source: str) -> None:
		self._device.source = source

	def select_sound_mode(self, mode: str) -> None:
		self._device.mode = mode

	def send_command(self, Command, Value):
		self._device.send_command(Command,Value)