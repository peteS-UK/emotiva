import asyncio
import logging
import socket
import sys
import time

import asyncio_datagram
from lxml import etree
from asyncping3 import ping

from .const import CONF_PING_INTERVAL, CONF_PING_ENABLED

_LOGGER = logging.getLogger(__name__)


class Error(Exception):
    pass


class InvalidTransponderResponseError(Error):
    pass


class InvalidSourceError(Error):
    pass


class InvalidModeError(Error):
    pass


class PingWatcherService:
    def __init__(self, hass, config_entry, host):
        self._hass = hass
        self._config_entry = config_entry
        self._host = host
        self._stop = False

    async def start(self):
        """Monitor connectivity and manage automatic reloads."""
        try:
            # --- PHASE 1: Standard Polling ---
            while not self._stop:
                # 1. Check the explicit toggle
                is_enabled = self._config_entry.options.get(CONF_PING_ENABLED, True)
                if not is_enabled:
                    _LOGGER.info("Ping Watcher is disabled via configuration.")
                    self._stop = True
                    break

                interval = int(self._config_entry.options.get(CONF_PING_INTERVAL, 60))

                # Ping the AVR
                _ping = await ping(self._host, timeout=4)
                if not _ping:
                    await asyncio.sleep(2)
                    _ping = await ping(self._host, timeout=4)

                if _ping:
                    await asyncio.sleep(interval)
                else:
                    break

            # --- PHASE 2: Recovery Polling ---
            if not self._stop:
                _LOGGER.error(
                    "Connectivity lost to %s. Waiting for availability.", self._host
                )

            while not self._stop:
                is_enabled = self._config_entry.options.get(CONF_PING_ENABLED, True)
                if not is_enabled:
                    _LOGGER.info("Ping Watcher disabled during recovery.")
                    self._stop = True
                    break

                interval = int(self._config_entry.options.get(CONF_PING_INTERVAL, 60))

                # Quick ping to check if it's back
                if await ping(self._host, timeout=1):
                    _LOGGER.warning(
                        "Connectivity re-established with %s. Reloading configuration in 30s.",
                        self._host,
                    )
                    await asyncio.sleep(30)

                    self._hass.config_entries.async_schedule_reload(
                        self._config_entry.entry_id
                    )
                    return

                # Safety net: Ensure we wait at least 5 seconds between recovery pings
                await asyncio.sleep(max(interval, 5))

        except asyncio.CancelledError:
            _LOGGER.debug("Ping watcher task cancelled for %s", self._host)
        except Exception as err:
            _LOGGER.exception(
                "Unexpected error in Ping Watcher for %s: %s", self._host, err
            )

    async def stop(self):
        """Signal the watcher loop to stop."""
        self._stop = True


class EmotivaNotifier(object):
    def __init__(self, notifier_name=""):
        self._devs = {}
        self._notifier_name = notifier_name
        # runtime control
        self._running = False
        self._stream = None
        self.task: asyncio.Task | None = None

    async def async_start(self, local_ip, local_port):
        self._running = True
        stream: asyncio_datagram.DatagramServer = None
        _LOGGER.debug("Starting Listener on %s:%d", local_ip, local_port)
        try:
            stream = await asyncio_datagram.bind((local_ip, local_port))
        except IOError as e:
            _LOGGER.critical(
                "Cannot bind to local socket (%s:%s) %d: %s for listener %s",
                local_ip,
                local_port,
                e.errno,
                e.strerror,
                self._notifier_name,
            )
        except Exception:
            _LOGGER.critical(
                "Unknown error on binding to local socket %s for listener %s: %s",
                local_ip,
                self._notifier_name,
                sys.exc_info()[0],
            )

        self._stream = stream

        try:
            while self._running and self._stream is not None:
                try:
                    data, remote_addr = await self._stream.recv()
                except OSError as exc:
                    _LOGGER.debug("Listener %s exception: %s", self._notifier_name, exc)
                    break

                if not data or not remote_addr:
                    await asyncio.sleep(0.1)
                    continue

                host = remote_addr[0]
                _LOGGER.debug(
                    "Received notification for listener %s from %s\n%s",
                    self._notifier_name,
                    host,
                    data.decode() if isinstance(data, bytes) else data,
                )

                cb = self._devs.get(host)
                if cb:
                    try:
                        cb(data)
                    except Exception:
                        _LOGGER.exception("Error in notification callback for %s", host)
                else:
                    _LOGGER.debug("No callback registered for %s", host)

                await asyncio.sleep(0.1)
        finally:
            try:
                if self._stream is not None:
                    _LOGGER.debug(
                        "Closing stream for listener %s",
                        self._notifier_name,
                    )
                    self._stream.close()
            except Exception:
                _LOGGER.debug(
                    "Error closing stream: %s for listener %s",
                    sys.exc_info()[0],
                    self._notifier_name,
                )
            self._stream = None
            self._running = False
            _LOGGER.debug("Listener %s stream stopped", self._notifier_name)

    async def _async_register(self, callback, remote_ip):
        _LOGGER.debug("Registering %s with listener %s", remote_ip, self._notifier_name)

        if remote_ip not in self._devs:
            self._devs[remote_ip] = callback

    def stop(self):
        _LOGGER.debug("Stopping listener %s", self._notifier_name)
        self._running = False

    async def _async_unregister(self, remote_ip):
        if remote_ip in self._devs:
            del self._devs[remote_ip]
            _LOGGER.debug(
                "Unregistered %s from listener %s", remote_ip, self._notifier_name
            )
        else:
            _LOGGER.debug("Attempted to unregister %s but not found", remote_ip)


class EmotivaNotifiers(object):
    subscription: EmotivaNotifier
    subscription_task: asyncio.Task
    command: EmotivaNotifier
    command_task: asyncio.Task


class Emotiva(object):
    XML_HEADER = '<?xml version="1.0" encoding="utf-8"?>'.encode("utf-8")
    DISCOVER_REQ_PORT = 7000
    DISCOVER_RESP_PORT = 7001

    NOTIFY_EVENTS = set(
        [
            "power",
            "zone2_power",
            "source",
            "mode",
            "volume",
            "audio_input",
            "audio_bits",
            "audio_bitstream",
            "video_input",
            "video_format",
            "video_space",
        ]
    ).union(set(["input_%d" % d for d in range(1, 9)]))

    def __init__(
        self,
        hass,
        config_entry,
        ip,
        transp_xml="",
        _ctrl_port=None,
        _notify_port=None,
        _name="Unknown_name",
        _model="Unknown_model",
        _proto_ver=2.0,
        _info_port=None,
        _setup_port=None,
        events=NOTIFY_EVENTS,
    ):
        self._hass = hass
        self._config_entry = config_entry
        self._ip = ip
        self._name = _name
        self._model = _model
        self._proto_ver = float(_proto_ver)
        self._ctrl_port = _ctrl_port
        self._notify_port = _notify_port
        self._info_port = _info_port
        self._setup_port_tcp = _setup_port
        self._volume_max = 11
        self._volume_min = -96
        self._volume_range = self._volume_max - self._volume_min
        self._udp_stream: asyncio_datagram.DatagramClient | None = None
        self._update_cb = None
        self._remote_update_cb = None
        self._select_update_cb = None
        self._sensor_update_cb = {}
        self._all_events = set(
            [
                "power",
                "source",
                "dim",
                "mode",
                "speaker_preset",
                "center",
                "subwoofer",
                "surround",
                "back",
                "volume",
                "loudness",
                "treble",
                "bass",
                "zone2_power",
                "zone2_volume",
                "zone2_input",
                "tuner_band",
                "tuner_channel",
                "tuner_signal",
                "tuner_program",
                "tuner_RDS",
                "audio_input",
                "audio_bitstream",
                "audio_bits",
                "video_input",
                "video_format",
                "video_space",
                "input_1",
                "input_2",
                "input_3",
                "input_4",
                "input_5",
                "input_6",
                "input_7",
                "input_8",
            ]
        )
        self.ping_watcher = PingWatcherService(self._hass, self._config_entry, ip)

        if not self._ctrl_port or not self._notify_port:
            self.__parse_transponder(transp_xml)

        if not self._ctrl_port or not self._notify_port:
            raise InvalidTransponderResponseError("Couldn't find ctrl/notify ports")

        self._stripped_model = (
            self._model.replace(" ", "").replace("-", "").replace("_", "").upper()[:4]
        )
        _LOGGER.debug("Stripped Model %s", self._stripped_model)
        match self._stripped_model:
            # mode : command,mode_name_string, visible
            case "XMC1":
                _LOGGER.debug("Sound Modes for XMC-1")
                self._modes = {
                    "Stereo": ["stereo", "mode_stereo", False],
                    "Direct": ["direct", "mode_direct", False],
                    "Dolby": ["dolby", "mode_dolby", False],
                    "DTS": ["dts", "mode_dts", False],
                    "All Stereo": ["all_stereo", "mode_all_stereo", False],
                    "Auto": ["auto", "mode_auto", False],
                    "Reference Stereo": ["reference_stereo", "mode_ref_stereo", False],
                    "Surround": ["surround_mode", "mode_surround", False],
                    "PLIIx Music": ["dolby", "mode_dolby", False],
                    "PLIIx Movie": ["dolby", "mode_dolby", False],
                    "dts Neo:6 Cinema": ["dts", "mode_dts", False],
                    "dts Neo:6 Music": ["dts", "mode_dts", False],
                }
            case "XMC2":
                _LOGGER.debug("Sound Modes for XMC-2")
                self._modes = {
                    "Stereo": ["stereo", "mode_stereo", False],
                    "Direct": ["direct", "mode_direct", False],
                    "Dolby": ["dolby", "mode_dolby", False],
                    "DTS": ["dts", "mode_dts", False],
                    "All Stereo": ["all_stereo", "mode_all_stereo", False],
                    "Auto": ["auto", "mode_auto", False],
                    "Reference Stereo": ["reference_stereo", "mode_ref_stereo", False],
                    "Surround": ["surround_mode", "mode_surround", False],
                    "Dolby ATMOS": ["dolby", "mode_dolby", False],
                    "dts Neural:X": ["dts", "mode_dts", False],
                    "Dolby Surround": ["dolby", "mode_dolby", False],
                }
            case "RMC1":
                _LOGGER.debug("Sound Modes for RMC-1")
                self._modes = {
                    "Stereo": ["stereo", "mode_stereo", False],
                    "Direct": ["direct", "mode_direct", False],
                    "Dolby": ["dolby", "mode_dolby", False],
                    "DTS": ["dts", "mode_dts", False],
                    "All Stereo": ["all_stereo", "mode_all_stereo", False],
                    "Auto": ["auto", "mode_auto", False],
                    "Reference Stereo": ["reference_stereo", "mode_ref_stereo", False],
                    "Surround": ["surround_mode", "mode_surround", False],
                    "Dolby Surround": ["dolby", "mode_dolby", False],
                    "Dolby ATMOS": ["dolby", "mode_dolby", False],
                    "dts Neural:X": ["dts", "mode_dts", False],
                }
            case "RMC1l":
                _LOGGER.debug("Sound Modes for RMC-1l")
                self._modes = {
                    "Stereo": ["stereo", "mode_stereo", False],
                    "Direct": ["direct", "mode_direct", False],
                    "Dolby": ["dolby", "mode_dolby", False],
                    "DTS": ["dts", "mode_dts", False],
                    "All Stereo": ["all_stereo", "mode_all_stereo", False],
                    "Auto": ["auto", "mode_auto", False],
                    "Reference Stereo": ["reference_stereo", "mode_ref_stereo", False],
                    "Surround": ["surround_mode", "mode_surround", False],
                    "Dolby Surround": ["dolby", "mode_dolby", False],
                    "Dolby ATMOS": ["dolby", "mode_dolby", False],
                    "dts Neural:X": ["dts", "mode_dts", False],
                }
            case _:
                _LOGGER.debug("Sound Modes Default")
                self._modes = {
                    "Stereo": ["stereo", "mode_stereo", False],
                    "Direct": ["direct", "mode_direct", False],
                    "Dolby": ["dolby", "mode_dolby", False],
                    "DTS": ["dts", "mode_dts", False],
                    "All Stereo": ["all_stereo", "mode_all_stereo", False],
                    "Auto": ["auto", "mode_auto", False],
                    "Reference Stereo": ["reference_stereo", "mode_ref_stereo", False],
                    "Surround": ["surround_mode", "mode_surround", False],
                    "PLIIx Music": ["dolby", "mode_dolby", False],
                    "PLIIx Movie": ["dolby", "mode_dolby", False],
                    "dts Neo:6 Cinema": ["dts", "mode_dts", False],
                    "dts Neo:6 Music": ["dts", "mode_dts", False],
                }

        self._events = events

        # current state
        self._current_state: dict[str, str | None] = dict(
            ((ev, None) for ev in self._events)
        )
        self._current_state.update(dict(((m[1], None) for m in self._modes.values())))
        # Add states for the initial music modes
        self._current_state.update(
            {
                "selected_movie_music": "Music",
                "mode_music": "Music",
                "mode_movie": "Movie",
                "mode_dolby": "Dolby",
                "mode_dts": "DTS",
                "mode_auto": "Auto",
                "mode_direct": "Direct",
                "mode_surround": "Surround",
                "mode_stereo": "Stereo",
                "mode_all_stereo": "All Stereo",
                "mode_ref_stereo": "Reference Stereo",
            }
        )
        self._sources = {
            "source_1": "Input 1",
            "source_2": "Input 2",
            "source_3": "Input 3",
            "source_4": "Input 4",
            "source_5": "Input 5",
            "source_6": "Input 6",
            "source_7": "Input 7",
            "source_8": "Input 8",
            "analog1": "Analog 1",
            "analog2": "Analog 2",
            "analog3": "Analog 3",
            "analog4": "Record In",
            "analog5": "Analog 5",
            "analog71": "Analog 7.1",
            "ARC": "HDMI ARC",
            "coax1": "Coax 1",
            "coax2": "Coax 2",
            "coax3": "Coax 3",
            "coax4": "AES/EBU",
            "hdmi1": "HDMI 1",
            "hdmi2": "HDMI 2",
            "hdmi3": "HDMI 3",
            "hdmi4": "HDMI 4",
            "hdmi5": "HDMI 5",
            "hdmi6": "HDMI 6",
            "hdmi7": "HDMI 7",
            "hdmi8": "HDMI 8",
            "optical1": "Optical 1",
            "optical2": "Optical 2",
            "optical3": "Optical 3",
            "optical4": "Optical 4",
            "source_tuner": "Tuner",
            "usb_stream": "USB Stream",
        }

        self._muted = False

        self._local_ip = self._get_local_ip()

    def _get_local_ip(self):
        _LOGGER.debug("Local IP: %s", self._hass.config.api.local_ip)
        return self._hass.config.api.local_ip

    async def register_with_notifier(self):
        await self._notifiers.subscription._async_register(
            self._notify_handler, self._ip
        )
        await self._notifiers.command._async_register(self._notify_handler, self._ip)

    async def unregister_from_notifier(self):
        _LOGGER.debug("Removing %s from Listeners", self._ip)
        await self._notifiers.subscription._async_unregister(self._ip)
        await self._notifiers.command._async_unregister(self._ip)

    async def async_subscribe_events(self):
        _LOGGER.debug("Subscribing to %s", self._events)
        await self._subscribe_events(self._events)

    async def async_unsubscribe_events(self):
        _LOGGER.debug("Unsubscribing from %s", self._events)
        await self._unsubscribe_events(self._all_events)
        await asyncio.sleep(0.5)

    def _notify_handler(self, data):
        _LOGGER.debug("Notify Handler called.")
        _decoded_data = (
            data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
        )
        if "emotivaUnsubscribe" not in _decoded_data:
            resp = self._parse_response(data)
            self._handle_status(resp)

        async def _update_sensors():
            # await asyncio.sleep(1.0)
            await self._update_sensor_values()

        if "emotivaUpdate" not in _decoded_data and "audio_input" not in _decoded_data:
            _LOGGER.debug("Sensor Update Scheduled")
            self._hass.async_create_task(_update_sensors())

    async def _subscribe_events(self, events):
        msg = self.format_request(
            "emotivaSubscription",
            [(ev, None) for ev in events],
            {"protocol": "3.0"} if self._proto_ver == 3.0 else None,
        )
        await self._async_send_request(msg, ack=True)

    async def _unsubscribe_events(self, events):
        msg = self.format_request(
            "emotivaUnsubscribe",
            [(ev, None) for ev in events],
            {"protocol": "3.0"} if self._proto_ver == 3.0 else None,
        )
        await self._async_send_request(msg, ack=True)

    async def _update_events(self, events):
        msg = self.format_request(
            "emotivaUpdate",
            [(ev, {}) for ev in events],
            {"protocol": "3.0"} if self._proto_ver == 3.0 else None,
        )
        await self._async_send_request(msg, ack=True)

    async def _update_sensor_values(self):
        events = [
            "audio_input",
            "audio_bitstream",
            "video_input",
            "video_format",
            "video_space",
        ]
        await self._update_events(events)

    async def async_update_status(self, events):
        await self._update_events(events)

    async def udp_connect(self):
        try:
            _LOGGER.debug(
                "Connecting to control socket at %s:%d", self._ip, self._ctrl_port
            )
            self._udp_stream = await asyncio_datagram.connect(
                (self._ip, self._ctrl_port)
            )

        except IOError as e:
            _LOGGER.critical(
                "Cannot connect control socket %d: %s", e.errno, e.strerror
            )
            self._udp_stream = None

        except Exception:
            _LOGGER.critical(
                "Unknown error on control socket connection %s",
                sys.exc_info()[0],
            )
            # Ensure no half-open stream
            self._udp_stream = None

    async def udp_disconnect(self):
        try:
            if self._udp_stream is not None:
                _LOGGER.debug("Disconnecting from control socket")
                self._udp_stream.close()
        except IOError as e:
            _LOGGER.critical(
                "Cannot disconnect from control socket %d: %s",
                e.errno,
                e.strerror,
            )
        except Exception:
            _LOGGER.critical(
                "Unknown error on control socket disconnection %s",
                sys.exc_info()[0],
            )

    async def _udp_client(self, req):
        # Ensure we have a connected udp stream; try to connect if missing
        if self._udp_stream is None:
            _LOGGER.debug("UDP stream not connected, attempting to connect")
            try:
                await self.udp_connect()
            except Exception:
                _LOGGER.exception("Error while attempting initial UDP connect")

        if self._udp_stream is None:
            _LOGGER.error("UDP stream unavailable, dropping request")
            self._resp = None
            return

        try:
            await self._udp_stream.send(req)
        except Exception:
            try:
                _LOGGER.debug("Connection lost. Attempting to reconnect")
                await self.udp_connect()
                if self._udp_stream is None:
                    _LOGGER.error("Reconnect failed, dropping request")
                    self._resp = None
                    return
                await self._udp_stream.send(req)
            except Exception:
                _LOGGER.critical(
                    "Error while attempting to resend after exception %s",
                    sys.exc_info()[0],
                )

        # Response handling currently disabled; leave placeholder
        self._resp = None

    async def _async_send_request(self, req, ack=False, process_response=True):
        await self._udp_client(req)

        # Used to take an ack and process response if needed, but currently not implemented as responses are not being sent by the AVR

    async def _async_send_emotivacontrol(self, command, value):
        msg = self.format_request(
            "emotivaControl",
            [(command, {"value": str(value), "ack": "no"})],
            {"protocol": "3.0"} if self._proto_ver == 3.0 else None,
        )
        await self._async_send_request(msg, ack=True, process_response=False)

    def __parse_transponder(self, transp_xml):
        # _LOGGER.debug("transp_xml %s", transp_xml)
        if transp_xml is None or len(transp_xml) == 0:
            _LOGGER.error("No transponder XML provided")
            return

        try:
            elem = transp_xml.find("name")
        except Exception:
            elem = None
        if elem is not None and elem.text:
            self._name = elem.text.strip()

        try:
            elem = transp_xml.find("model")
        except Exception:
            elem = None
        if elem is not None and elem.text:
            self._model = elem.text.strip()

        try:
            ctrl = transp_xml.find("control")
        except Exception:
            ctrl = None

        if ctrl is None:
            _LOGGER.error(
                "Transponder response missing <control> element; cannot parse ports/version"
            )
            return

        try:
            elem = ctrl.find("version")
            if elem is not None and elem.text:
                try:
                    self._proto_ver = float(elem.text)
                except Exception:
                    _LOGGER.debug(
                        "Invalid protocol version in transponder: %s", elem.text
                    )
        except Exception:
            _LOGGER.debug("Error reading version from transponder")

        def _safe_int_from_ctrl(tag_name):
            try:
                el = ctrl.find(tag_name)
                if el is not None and el.text:
                    return int(el.text)
            except Exception:
                _LOGGER.debug("Invalid integer for %s in transponder", tag_name)
            return None

        _val = _safe_int_from_ctrl("controlPort")
        if _val is not None:
            self._ctrl_port = _val
        _val = _safe_int_from_ctrl("notifyPort")
        if _val is not None:
            self._notify_port = _val
        _val = _safe_int_from_ctrl("infoPort")
        if _val is not None:
            self._info_port = _val
        _val = _safe_int_from_ctrl("setupPortTCP")
        if _val is not None:
            self._setup_port_tcp = _val

    def _handle_status(self, resp):
        _LOGGER.debug("_handle_status called")
        for elem in resp:
            if elem.tag == "property":
                # v3 protocol style response, convert it to v2 style
                # _LOGGER.debug("Handling Protocol V3 xml")
                elem.tag = elem.get("name")
            if elem.tag not in self._current_state:
                _LOGGER.debug("Unknown element: %s" % elem.tag)
                continue
            val = (elem.get("value") or "").strip()
            visible = (elem.get("visible") or "").strip()
            # update mode status
            if elem.tag.startswith("mode_"):
                for v in self._modes.items():
                    if v[1][1] == elem.tag and v[1][2] != visible:
                        v[1][2] = True if visible == "true" else False
                        _LOGGER.debug(
                            " Changing visibility of %s to %s", elem.tag, visible
                        )
                        self._modes.update({v[0]: v[1]})
            # do not
            if elem.tag.startswith("input_") and visible != "true":
                continue
            if elem.tag == "volume":
                if val == "Mute":
                    self._muted = True
                    continue
                self._muted = False
                # fall through
            if val:
                self._current_state[elem.tag] = val
            if elem.tag.startswith("input_"):
                num = elem.tag[6:]
                self._sources["source_" + num] = val

        if self._update_cb:
            self._update_cb()
        if self._remote_update_cb:
            self._remote_update_cb()
        if self._select_update_cb:
            self._select_update_cb()
        if self._sensor_update_cb:
            for cb in self._sensor_update_cb.values():
                cb()

    def set_remote_update_cb(self, cb):
        self._remote_update_cb = cb

    def set_select_update_cb(self, cb):
        self._select_update_cb = cb

    def set_sensor_update_cb(self, sensor_name, cb):
        self._sensor_update_cb[sensor_name] = cb

    def remove_sensor_update_cb(self, sensor_name):
        del self._sensor_update_cb[sensor_name]

    def set_update_cb(self, cb):
        self._update_cb = cb

    async def run_ping_watcher(self):
        _LOGGER.debug("Setting up Ping Watcher")
        await self.ping_watcher.start()

    async def stop_ping_watcher(self):
        _LOGGER.debug("Stopping Ping Watcher")
        await self.ping_watcher.stop()

    @classmethod
    def discover(cls, version=2):
        resp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            resp_sock.bind(("", cls.DISCOVER_RESP_PORT))
        except Exception:
            time.sleep(1)
            try:
                resp_sock.bind(("", cls.DISCOVER_RESP_PORT))
            except Exception:
                _LOGGER.error("Cannot bind to discovery port")
                return []

        resp_sock.settimeout(0.5)

        req_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        req_sock.bind(("", 0))
        req_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # use empty list for no elements (don't pass a mutable default)
        req = cls.format_request(
            "emotivaPing",
            [],
            {"protocol": "3.0"} if version == 3.0 else None,
        )

        _LOGGER.debug("discover Broadcast Req: %s", req)
        req_sock.sendto(req, ("<broadcast>", cls.DISCOVER_REQ_PORT))

        devices = []
        while True:
            try:
                _resp_data, (ip, port) = resp_sock.recvfrom(4096)

                resp = cls._parse_response(_resp_data)
                if resp is None:
                    _LOGGER.debug("Skipping malformed discovery response from %s", ip)
                    continue
                _LOGGER.debug("Parsed ping response %s", resp)
                devices.append((ip, resp))
            except socket.timeout:
                break
        # Always return a list of discovered devices. If none were found
        # `devices` will be an empty list which callers can iterate safely.
        return devices

    @classmethod
    def _parse_response(cls, data):
        # Parse XML discovery responses; return None on failure so callers
        # can skip malformed responses safely.
        try:
            parser = etree.XMLParser(ns_clean=True, recover=True)
            root = etree.XML(data, parser)
            return root
        except etree.ParseError:
            _LOGGER.error("Malformed XML in discovery response")
            _LOGGER.debug("Response data: %s", data)
            return None
        except Exception:
            _LOGGER.exception("Unexpected error parsing discovery response")
            return None

    @classmethod
    def format_request(cls, pkt_type, req=None, pkt_attrs=None):
        """
        Build an XML request packet.

        - `req` should be a list/tuple of 2-element tuples: (command, params_dict).
          If `None`, it becomes an empty list. If a mapping is passed, it's
          converted to list(mapping.items()). Empty mapping becomes an empty
          request list.
        - `pkt_attrs` should be a dict of attributes for the root element; if
          `None` it's treated as an empty dict.
        """
        if req is None:
            req = []
        elif isinstance(req, dict):
            # convert mapping->list of (cmd, params) if non-empty, else empty
            req = list(req.items()) if req else []
        elif not isinstance(req, (list, tuple)):
            raise TypeError("req must be a list/tuple of (cmd, params) or None")

        if pkt_attrs is None:
            pkt_attrs = {}
        elif not isinstance(pkt_attrs, dict):
            raise TypeError("pkt_attrs must be a dict or None")

        output = cls.XML_HEADER
        builder = etree.TreeBuilder()
        builder.start(pkt_type, pkt_attrs)
        for item in req:
            try:
                cmd, params = item
            except Exception:
                raise TypeError("each req item must be a (cmd, params) pair")
            if params is None:
                params = {}
            elif not isinstance(params, dict):
                # coerce simple values to string param
                params = {"value": str(params)}
            builder.start(cmd, params)
            builder.end(cmd)
        builder.end(pkt_type)
        pkt = builder.close()
        return output + etree.tostring(pkt)

    @property
    def name(self):
        return self._name

    @property
    def model(self):
        return self._model

    @property
    def address(self):
        return self._ip

    @property
    def power(self):
        if self._current_state["power"] == "On":
            return True
        return False

    # @power.setter
    # def power(self, onoff):
    # 	cmd = {True: 'power_on', False: 'power_off'}[onoff]
    # 	self._send_emotivacontrol(cmd,0)

    @property
    def volume_level(self):
        if self._current_state["volume"] is not None:
            _vol = float(self._current_state["volume"].replace(" ", ""))
            return (_vol - self._volume_min) / self._volume_range
        return None

    @property
    def volume(self):
        if self._current_state["volume"] is not None:
            return float(self._current_state["volume"].replace(" ", ""))
        return None

    def set_notifiers(self, notifiers):
        self._notifiers: EmotivaNotifiers = notifiers

    # @volume.setter
    # def volume(self, value):
    # 	self._send_emotivacontrol('set_volume',value)

    async def _async_volume_step(self, incr):
        await self._async_send_emotivacontrol("volume", incr)

    async def async_volume_set(self, vol):
        await self._async_send_emotivacontrol("set_volume", vol)

    async def async_volume_up(self):
        await self._async_volume_step(1)

    async def async_volume_down(self):
        await self._async_volume_step(-1)

    async def async_mute_toggle(self):
        await self._async_send_emotivacontrol("mute", "0")

    async def async_set_mute(self, enable):
        mute_cmd = {True: "mute_on", False: "mute_off"}[enable]
        await self._async_send_emotivacontrol(mute_cmd, "0")

    async def async_turn_off(self):
        await self._async_send_emotivacontrol("power_off", "0")

    async def async_turn_on(self):
        await self._async_send_emotivacontrol("power_on", "0")

    async def async_send_command(self, command, value):
        await self._async_send_emotivacontrol(command, value)

    @property
    def mute(self):
        return self._muted

    # @mute.setter
    # def mute(self, enable):
    # 	mute_cmd = {True: 'mute_on', False: 'mute_off'}[enable]
    # 	self._send_emotivacontrol(mute_cmd,0)

    @property
    def sources(self):
        return tuple(self._sources.values())

    @property
    def source(self):
        return self._current_state["source"]

    async def async_set_source(self, val):
        _source_key = list(self._sources.keys())[
            list(self._sources.values()).index(val)
        ]

        if val not in self._sources.values():
            raise InvalidSourceError('Source "%s" is not a valid input' % val)

        await self._async_send_emotivacontrol(_source_key, "0")

    @property
    def modes(self):
        # we return only the modes that are active
        return tuple(dict(filter(lambda elem: elem[1][2], self._modes.items())).keys())

    @property
    def mode(self):
        try:
            return self._current_state["mode"]
        except Exception:
            _LOGGER.error("Unknown sound mode %s", self._current_state["mode"])
            return ""

    async def async_set_mode(self, val):
        if val not in self._modes:
            raise InvalidModeError('Mode "%s" does not exist' % val)
        elif self._modes[val][0] is None:
            raise InvalidModeError(
                'Mode "%s" has bad command value (%s)' % (val, self._modes[val][0])
            )
        await self._async_send_emotivacontrol(self._modes[val][0], "0")

        if self._current_state["mode_music"] in val:
            _LOGGER.debug(
                "Sound Mode Music.  mode_music %s", self._current_state["mode_music"]
            )
            await asyncio.sleep(0.25)
            await self._async_send_emotivacontrol("music", "0")
        elif self._current_state["mode_movie"] in val or "cinema" in val:
            _LOGGER.debug(
                "Sound Mode Movie.  mode_movie %s", self._current_state["mode_movie"]
            )
            await asyncio.sleep(0.25)
            await self._async_send_emotivacontrol("movie", "0")
