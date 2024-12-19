import asyncio
import logging
import socket
import sys
import time

import asyncio_datagram
from lxml import etree

_LOGGER = logging.getLogger(__name__)


class Error(Exception):
    pass


class InvalidTransponderResponseError(Error):
    pass


class InvalidSourceError(Error):
    pass


class InvalidModeError(Error):
    pass


class EmotivaNotifiers(object):
    subscription: object
    subscription_task: object
    command: object
    command_task: object


class EmotivaNotifier(object):
    def __init__(self):
        self._devs = {}

    async def _async_start(self, local_ip, local_port):
        _LOGGER.debug("Starting Listener on %s:%d", local_ip, local_port)
        try:
            stream = await asyncio_datagram.bind((local_ip, local_port))
        except IOError as e:
            _LOGGER.critical("Cannot bind to local socket %d: %s", e.errno, e.strerror)
        except Exception:
            _LOGGER.critical(
                "Unknown error on binding to local socket %s", sys.exc_info()[0]
            )

        self._stream = stream

        while True and stream is not None:
            data, remote_addr = await stream.recv()

            _LOGGER.debug(
                "Received notification from %s\n%s",
                remote_addr[0],
                data.decode() if isinstance(data, bytes) else data,
            )

            cb = self._devs[remote_addr[0]]

            cb(data)

            await asyncio.sleep(0.1)

    async def _async_register(self, callback, remote_ip):
        _LOGGER.debug("Registering %s with listener", remote_ip)

        if remote_ip not in self._devs:
            self._devs[remote_ip] = callback

    async def _async_stop(self):
        self._stream.close()

    async def _async_unregister(self, remote_ip):
        del self._devs[remote_ip]


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
            "audio_bitstream",
            "video_input",
            "video_format",
        ]
    ).union(set(["input_%d" % d for d in range(1, 9)]))

    def __init__(
        self,
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
        self._ctrl_sock = None
        self._udp_stream = None
        self._update_cb = None
        self._remote_update_cb = None

        if not self._ctrl_port or not self._notify_port:
            self.__parse_transponder(transp_xml)

        if not self._ctrl_port or not self._notify_port:
            raise InvalidTransponderResponseError("Coulnd't find ctrl/notify ports")

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
        self._current_state = dict(((ev, None) for ev in self._events))
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
        self._sources = {}

        self._muted = False

        self._local_ip = self._get_local_ip()

    def _get_local_ip(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((self._ip, self._ctrl_port))
        _local_ip = sock.getsockname()[0]
        sock.close()
        _LOGGER.debug("Local IP: ", _local_ip)
        return _local_ip

    def connect(self):
        self._ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._ctrl_sock.bind(("", self._ctrl_port))
        self._ctrl_sock.settimeout(0.5)

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
        await self._unsubscribe_events(self._events)

    def _notify_handler(self, data):
        _LOGGER.debug("Notify Handler called")
        resp = self._parse_response(data)
        self._handle_status(resp)

    async def _subscribe_events(self, events):
        msg = self.format_request(
            "emotivaSubscription",
            [(ev, None) for ev in events],
            {"protocol": "3.0"} if self._proto_ver == 3.0 else {},
        )
        await self._async_send_request(msg, ack=True)

    async def _unsubscribe_events(self, events):
        msg = self.format_request(
            "emotivaUnsubscribe",
            [(ev, None) for ev in events],
            {"protocol": "3.0"} if self._proto_ver == 3.0 else {},
        )
        await self._async_send_request(msg, ack=True)

    def disconnect(self):
        self._ctrl_sock.close()

    async def async_update_status(self, events):
        msg = self.format_request(
            "emotivaUpdate",
            [(ev, {}) for ev in events],
            {"protocol": "3.0"} if self._proto_ver == 3 else {},
        )
        await self._async_send_request(msg, ack=True)

    async def udp_connect(self):
        try:
            #            self._udp_stream = await asyncio_datagram.connect(
            #                (self._ip, self._ctrl_port), (self._local_ip, self._ctrl_port)
            #            )
            self._udp_stream = await asyncio_datagram.connect(
                (self._ip, self._ctrl_port)
            )
        except IOError as e:
            _LOGGER.critical(
                "Cannot connect control listener socket %d: %s", e.errno, e.strerror
            )
        except Exception:
            _LOGGER.critical(
                "Unknown error on control listener socket connection %s",
                sys.exc_info()[0],
            )

    async def udp_disconnect(self):
        try:
            self._udp_stream.close()
        except IOError as e:
            _LOGGER.critical(
                "Cannot disconnect from control listener socket %d: %s",
                e.errno,
                e.strerror,
            )
        except Exception:
            _LOGGER.critical(
                "Unknown error on control listener socket disconnection %s",
                sys.exc_info()[0],
            )

    async def _udp_client(self, req, ack):
        try:
            await self._udp_stream.send(req)
        except Exception:
            try:
                _LOGGER.debug("Connection lost.  Attepting to reconnect")
                self.udp_connect()
                await self._udp_stream.send(req)

            except IOError as e:
                _LOGGER.critical(
                    "Cannot reconnect to command socket %d: %s", e.errno, e.strerror
                )
            except Exception:
                _LOGGER.critical(
                    "Unknown error on command socket reconnection %s", sys.exc_info()[0]
                )

        # await _stream.send(command, (self._ip, self._ctrl_port))
        # if ack:
        #    resp, remote_addr = await self._udp_stream.recv()
        #    _LOGGER.debug(
        #        "_udp_client received: \n%s",
        #        resp.decode() if isinstance(resp, bytes) else resp,
        #    )
        # else:
        #    resp = None

        # _stream.close()

        resp = None
        self._resp = resp

    async def _async_send_request(self, req, ack=False, process_response=True):
        await self._udp_client(req, ack)

        # _LOGGER.debug("_async_send_request received %s", self._resp)

        # if ack and process_response:
        #    resp = self._parse_response(self._resp)
        #    self._handle_status(resp)

    async def _async_send_emotivacontrol(self, command, value):
        msg = self.format_request(
            "emotivaControl",
            [(command, {"value": str(value), "ack": "no"})],
            {"protocol": "3.0"} if self._proto_ver == 3 else {},
        )
        await self._async_send_request(msg, ack=True, process_response=False)

    def __parse_transponder(self, transp_xml):
        # _LOGGER.debug("transp_xml %s", transp_xml)
        elem = transp_xml.find("name")
        if elem is not None:
            self._name = elem.text.strip()
        elem = transp_xml.find("model")
        if elem is not None:
            self._model = elem.text.strip()

        ctrl = transp_xml.find("control")
        elem = ctrl.find("version")
        if elem is not None:
            self._proto_ver = float(elem.text)
        elem = ctrl.find("controlPort")
        if elem is not None:
            self._ctrl_port = int(elem.text)
        elem = ctrl.find("notifyPort")
        if elem is not None:
            self._notify_port = int(elem.text)
        elem = ctrl.find("infoPort")
        if elem is not None:
            self._info_port = int(elem.text)
        elem = ctrl.find("setupPortTCP")
        if elem is not None:
            self._setup_port_tcp = int(elem.text)

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
                self._sources[val] = int(num)

        if self._update_cb:
            self._update_cb()
        if self._remote_update_cb:
            self._remote_update_cb()
        if self._select_update_cb:
            self._select_update_cb()
        if self._sensor_update_cb:
            self._sensor_update_cb()

    def set_remote_update_cb(self, cb):
        self._remote_update_cb = cb

    def set_select_update_cb(self, cb):
        self._select_update_cb = cb

    def set_sensor_update_cb(self, cb):
        self._sensor_update_cb = cb

    def set_update_cb(self, cb):
        self._update_cb = cb

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

        req = cls.format_request(
            "emotivaPing",
            {},
            {"protocol": "3.0"} if version == 3.0 else {},
        )

        _LOGGER.debug("discover Broadcast Req: %s", req)
        req_sock.sendto(req, ("<broadcast>", cls.DISCOVER_REQ_PORT))

        devices = []
        while True:
            try:
                _resp_data, (ip, port) = resp_sock.recvfrom(4096)

                resp = cls._parse_response(_resp_data)
                _LOGGER.debug("Parsed ping response %s", resp)
                devices.append((ip, resp))
            except socket.timeout:
                break
        if len(devices) > 0:
            # return devices[0]
            return devices
        else:
            return None

    @classmethod
    def _parse_response(cls, data):
        # _LOGGER.debug("parse_response: %s", data)
        try:
            parser = etree.XMLParser(ns_clean=True, recover=True)
            root = etree.XML(data, parser)
        except etree.ParseError:
            _LOGGER.error("Malformed XML")
            _LOGGER.error(data)
            root = ""
        return root

    @classmethod
    def format_request(cls, pkt_type, req={}, pkt_attrs={}):
        """
        req is a list of 2-element tuples with first element being the command,
        and second being a dict of parameters. E.g.
        ('power_on', {'value': "0"})

        pkt_attrs is a dictionary containing element attributes. E.g.
        {'protocol': "3.0"}
        """
        output = cls.XML_HEADER
        builder = etree.TreeBuilder()
        builder.start(pkt_type, pkt_attrs)
        for cmd, params in req:
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
        return tuple(self._sources.keys())

    @property
    def source(self):
        return self._current_state["source"]

    async def async_set_source(self, val):
        if val not in self._sources:
            raise InvalidSourceError('Source "%s" is not a valid input' % val)
        elif self._sources[val] is None:
            raise InvalidSourceError(
                'Source "%s" has bad value (%s)' % (val, self._sources[val])
            )
        await self._async_send_emotivacontrol("source_%d" % self._sources[val], "0")

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
