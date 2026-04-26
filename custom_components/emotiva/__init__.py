"""The emotiva component."""

import logging
import asyncio


from homeassistant import config_entries, core
from homeassistant.components.network import async_get_source_ip
from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_NAME, Platform
from homeassistant.exceptions import ConfigEntryError

from .const import (
    CONF_CTRL_PORT,
    CONF_NOTIFICATIONS,
    CONF_NOTIFY_PORT,
    CONF_PROTO_VER,
    CONF_DISCOVER,
    CONF_TYPE,
    DEFAULT_CTRL_PORT,
    DEFAULT_NOTIFY_PORT,
    DOMAIN,
)
from .emotiva import Emotiva, EmotivaNotifiers, EmotivaNotifier

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.REMOTE, Platform.SELECT, Platform.SENSOR]


async def async_migrate_entry(hass, config_entry):
    """Migrate old entry."""
    _LOGGER.critical("Migrating from version %s", config_entry.version)

    _LOGGER.critical("Migrating data %s", config_entry.data)

    if config_entry.version < 2:
        new_data = dict(config_entry.data)
        host = new_data.get(CONF_HOST, "")

        if new_data.get(CONF_TYPE) == "Discover" or new_data.get(CONF_DISCOVER, None):
            receivers = await hass.async_add_executor_job(Emotiva.discover, 3)

            _LOGGER.critical("Receivers %s", receivers)

            if receivers:
                _ip, _xml = receivers[0]

                device = Emotiva(hass, None, host, _xml)

                new_data = {
                    CONF_HOST: device.address,
                    CONF_NAME: device.name,
                    CONF_MODEL: device.model,
                    CONF_PROTO_VER: device._proto_ver,
                }

                _LOGGER.critical("New Data %s", new_data)

                hass.config_entries.async_update_entry(
                    config_entry,
                    title=device.name,
                    data=new_data,
                    unique_id=f"emotiva_{device.address.replace('.', '_')}",
                    version=2,
                )

            else:
                _LOGGER.error(
                    "No Emotiva devices found during migration.  Please ensure your device is powered on and connected to the network, then reload the integration and try again."
                )
                return False

        else:
            new_data.pop(CONF_TYPE, None)
            hass.config_entries.async_update_entry(
                config_entry,
                data=new_data,
                unique_id=f"emotiva_{host.replace('.', '_')}",
                version=2,
            )

        _LOGGER.info("Migration to version %s successful", config_entry.version)

    return True


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up platform from a ConfigEntry."""
    hass.data.setdefault(DOMAIN, {})
    hass_data = dict(entry.data)

    device = Emotiva(
        hass,
        entry,
        hass_data[CONF_HOST],
        transp_xml="",
        _ctrl_port=hass_data.get(CONF_CTRL_PORT, DEFAULT_CTRL_PORT),
        _notify_port=hass_data.get(CONF_NOTIFY_PORT, DEFAULT_NOTIFY_PORT),
        _proto_ver=hass_data[CONF_PROTO_VER],
        _name=hass_data[CONF_NAME],
        _model=hass_data[CONF_MODEL],
    )

    hass_data["emotiva"] = [device]

    if CONF_NOTIFICATIONS in entry.options:
        _update_extra_notifications(device, entry.options[CONF_NOTIFICATIONS])

    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    hass_data["unsub_options_update_listener"] = unsub_options_update_listener

    hass.data[DOMAIN][entry.entry_id] = hass_data

    if "notifiers" not in hass.data[DOMAIN]:
        # There are no current configs, so we create the listener
        notifiers = EmotivaNotifiers()
        notifiers.subscription = EmotivaNotifier("Subscription")
        notifiers.command = EmotivaNotifier("Command")

        _local_ip = await async_get_source_ip(hass)
        _notify_port = device._notify_port
        _control_port = device._ctrl_port

        if _notify_port and _control_port:
            notifiers.subscription.task = hass.async_create_background_task(
                notifiers.subscription.async_start(_local_ip, _notify_port),
                name="emotiva subscription notifier task",
            )
            notifiers.command.task = hass.async_create_background_task(
                notifiers.command.async_start(_local_ip, _control_port),
                name="emotiva command notifier task",
            )
            hass.data[DOMAIN]["notifiers"] = notifiers
        else:
            _LOGGER.error(
                "Could not determine notifier ports. Notifications will not work."
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _update_extra_notifications(device, notifications):
    if notifications is not None:
        _LOGGER.debug("Adding %s to %s", notifications, device.name)
        _notify_set = set(notifications.replace(" ", "").split(","))
    else:
        _notify_set = set()

    device._events = device._events.union(_notify_set)
    device._current_state.update(dict((m, None) for m in _notify_set))


async def options_update_listener(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
):
    """Handle options update."""
    device = hass.data[DOMAIN][config_entry.entry_id]["emotiva"][0]
    _update_extra_notifications(
        device,
        config_entry.options.get(CONF_NOTIFICATIONS),
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

        other_loaded_entries = [
            _entry
            for _entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if _entry.entry_id != entry.entry_id
        ]
        if not other_loaded_entries:
            _LOGGER.debug("Unloading Listeners")
            _notifiers = hass.data[DOMAIN].get("notifiers")
            if _notifiers is not None:
                for notifier_name in ("subscription", "command"):
                    notifier = getattr(_notifiers, notifier_name, None)
                    if notifier is None:
                        continue
                    try:
                        notifier.stop()
                        _LOGGER.debug("Cancelling task %s", notifier_name)
                        if notifier.task is not None:
                            notifier.task.cancel()
                            try:
                                await notifier.task
                            except asyncio.CancelledError:
                                _LOGGER.debug("Task %s cancelled", notifier_name)
                            notifier.task = None
                    except Exception:
                        _LOGGER.exception("Error stopping notifier %s", notifier_name)

            del hass.data[DOMAIN]["notifiers"]

    return unload_ok
