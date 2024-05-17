"""The emotiva component."""

import logging

from homeassistant import config_entries, core
from homeassistant.const import Platform
from homeassistant.const import CONF_HOST, CONF_NAME

from .emotiva import Emotiva

from .const import (
	DOMAIN,
	CONF_NOTIFICATIONS,
	CONF_NOTIFY_PORT,
	CONF_CTRL_PORT,
	CONF_PROTO_VER,
	CONF_DISCOVER,
	CONF_MANUAL,
	SERVICE_SEND_COMMAND,
	DEFAULT_NAME
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.REMOTE]


async def async_setup_entry(
	hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
	"""Set up platform from a ConfigEntry."""
	hass.data.setdefault(DOMAIN, {})
	hass_data = dict(entry.data)


	receivers = []
	emotiva = []

	if hass_data[CONF_DISCOVER]:
		receivers = await hass.async_add_executor_job(Emotiva.discover,3)
		_configdiscovered = False

		for receiver in receivers:

			_ip, _xml = receiver
				
			emotiva.append(Emotiva(_ip, _xml))
		
			_LOGGER.debug("Adding %s from discovery", _ip)

	if hass_data[CONF_MANUAL] and not any([hass_data[CONF_HOST] in tup for tup in receivers]):
		_LOGGER.debug("Adding %s:%s from config", hass_data[CONF_HOST]
				, hass_data[CONF_NAME])

		emotiva.append(Emotiva(hass_data[CONF_HOST], transp_xml = "", 
					_ctrl_port = hass_data[CONF_CTRL_PORT], _notify_port = hass_data[CONF_NOTIFY_PORT],
					_proto_ver = hass_data[CONF_PROTO_VER], _name = hass_data[CONF_NAME]))

		#Get additional notify

	if CONF_NOTIFICATIONS in entry.options:
		_update_extra_notifications(emotiva,entry.options[CONF_NOTIFICATIONS])

	hass_data["emotiva"] = emotiva

	# Registers update listener to update config entry when options are updated.
	unsub_options_update_listener = entry.add_update_listener(options_update_listener)
	# Store a reference to the unsubscribe function to cleanup if an entry is unloaded.
	hass_data["unsub_options_update_listener"] = unsub_options_update_listener

	hass.data[DOMAIN][entry.entry_id] = hass_data

	await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

	return True

def _update_extra_notifications(emotiva, notifications):
	if notifications is not None:
		_LOGGER.debug("Adding %s",notifications)
		_notify_set = set(notifications.replace(" ","").split(","))
	else:
		_notify_set = set()

	emotiva[len(emotiva)-1]._events = emotiva[len(emotiva)-1]._events.union(_notify_set)
	emotiva[len(emotiva)-1]._current_state.update(dict((m, None) for m in _notify_set))

async def options_update_listener(
	hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
):
	"""Handle options update."""
	_update_extra_notifications(hass.data[DOMAIN][config_entry.entry_id]["emotiva"],config_entry.options[CONF_NOTIFICATIONS])

	await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(
	hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
	"""Unload a config entry."""
	if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
		# Remove config entry from domain.
		entry_data = hass.data[DOMAIN].pop(entry.entry_id)
		# Remove options_update_listener.
		entry_data["unsub_options_update_listener"]()

	return unload_ok

