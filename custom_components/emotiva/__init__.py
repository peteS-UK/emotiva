"""The emotiva component."""

import logging

from homeassistant import config_entries, core
from homeassistant.const import Platform
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_MODEL

from .emotiva import Emotiva, EmotivaNotifier

from homeassistant.components.network import async_get_source_ip

from .const import (
    DOMAIN,
    CONF_NOTIFICATIONS,
    CONF_NOTIFY_PORT,
    CONF_CTRL_PORT,
    CONF_PROTO_VER,
    CONF_DISCOVER,
    CONF_MANUAL,
    CONF_TYPE,
)


class EmotivaNotifiers(object):
    subscription: object
    subscription_task: object
    command: object
    command_task: object


_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.REMOTE, Platform.SELECT, Platform.SENSOR]


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up platform from a ConfigEntry."""
    hass.data.setdefault(DOMAIN, {})
    hass_data = dict(entry.data)

    emotiva = []
    _control_port = None
    _notify_port = None

    if hass_data.get(CONF_TYPE, None) == "Discover" or hass_data.get(
        CONF_DISCOVER, None
    ):
        receivers = await hass.async_add_executor_job(Emotiva.discover, 3)

        for receiver in receivers:
            # Server was discovered
            _ip, _xml = receiver

            if not _control_port or not _notify_port:
                ctrl = _xml.find("control")
                elem = ctrl.find("controlPort")
                if elem is not None:
                    _control_port = int(elem.text)
                elem = ctrl.find("notifyPort")
                if elem is not None:
                    _notify_port = int(elem.text)

            emotiva.append(Emotiva(hass, _ip, _xml))
            _LOGGER.debug("Adding %s from Discovery", _ip)

    elif hass_data.get(CONF_TYPE, None) == "Manual" or hass_data.get(CONF_MANUAL, None):
        _LOGGER.debug(
            "Adding %s Name: %s Model: %s from Manual Config",
            hass_data[CONF_HOST],
            hass_data[CONF_NAME],
            hass_data[CONF_MODEL],
        )

        if not _control_port or not _notify_port:
            _control_port = hass_data[CONF_CTRL_PORT]
            _notify_port = hass_data[CONF_NOTIFY_PORT]

        emotiva.append(
            Emotiva(
                hass,
                hass_data[CONF_HOST],
                transp_xml="",
                _ctrl_port=hass_data[CONF_CTRL_PORT],
                _notify_port=hass_data[CONF_NOTIFY_PORT],
                _proto_ver=hass_data[CONF_PROTO_VER],
                _name=hass_data[CONF_NAME],
                _model=hass_data[CONF_MODEL],
            )
        )

    if len(emotiva) == 0:
        _LOGGER.critical("No processor discovered, and no manual processor info")
        return False

    if not _control_port or not _notify_port:
        _LOGGER.critical("Cannot discover control and/or notify ports")
        return False

    # Get additional notify

    if CONF_NOTIFICATIONS in entry.options:
        _update_extra_notifications(emotiva, entry.options[CONF_NOTIFICATIONS])

    hass_data["emotiva"] = emotiva

    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    # Store a reference to the unsubscribe function to cleanup if an entry is unloaded.
    hass_data["unsub_options_update_listener"] = unsub_options_update_listener

    hass.data[DOMAIN][entry.entry_id] = hass_data

    _LOGGER.debug(
        "Adding new Config Entry.  %d total configurations",
        len(hass.config_entries.async_entries(DOMAIN)),
    )

    # if len(hass.config_entries.async_entries(DOMAIN)) == 1:
    if "notifiers" not in hass.data[DOMAIN]:
        # There are no current configs, so we create the listener
        notifiers = EmotivaNotifiers()
        notifiers.subscription = EmotivaNotifier()
        notifiers.command = EmotivaNotifier()

        _local_ip = await async_get_source_ip(hass)

        notifiers.subscription_task = hass.async_create_background_task(
            notifiers.subscription._async_start(_local_ip, _notify_port),
            name="emotiva subscription notifier task",
        )

        notifiers.command_task = hass.async_create_background_task(
            notifiers.command._async_start(_local_ip, _control_port),
            name="emotiva command notifier task",
        )

        hass.data[DOMAIN]["notifiers"] = notifiers

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _update_extra_notifications(emotiva, notifications):
    if notifications is not None:
        _LOGGER.debug("Adding %s", notifications)
        _notify_set = set(notifications.replace(" ", "").split(","))
    else:
        _notify_set = set()

    emotiva[len(emotiva) - 1]._events = emotiva[len(emotiva) - 1]._events.union(
        _notify_set
    )
    emotiva[len(emotiva) - 1]._current_state.update(
        dict((m, None) for m in _notify_set)
    )


async def options_update_listener(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
):
    """Handle options update."""
    _update_extra_notifications(
        hass.data[DOMAIN][config_entry.entry_id]["emotiva"],
        config_entry.options.get(CONF_NOTIFICATIONS, None),
    )

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

        _LOGGER.debug(
            "Unloading Entry.  %d configurations remaining",
            len(hass.config_entries.async_loaded_entries(DOMAIN)) - 1,
        )

        if len(hass.config_entries.async_loaded_entries(DOMAIN)) == 1:
            _LOGGER.debug("Unloading Listeners")
            _notifiers = hass.data[DOMAIN]["notifiers"]
            await _notifiers.subscription._async_stop()
            await _notifiers.command._async_stop()
            _notifiers.subscription_task.cancel()
            _notifiers.command_task.cancel()
            del hass.data[DOMAIN]["notifiers"]

    return unload_ok
