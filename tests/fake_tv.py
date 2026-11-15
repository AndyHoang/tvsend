"""A fake DLNA TV for the tests: runs inside the test process on 127.0.0.1.

It serves a device description and answers the AVTransport commands tvsend uses.
Playback is simulated: a clip has `duration` seconds and its position advances `speed`
times faster than real time, so a 10-second clip can end in a fraction of a second.
"""

import html
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE = "urn:schemas-upnp-org:service:AVTransport:1"
UDN = "uuid:00000000-test-0000-0000-000000000001"
NAME = "Test TV"

DESCRIPTION = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
    <friendlyName>%s</friendlyName>
    <modelName>Fake 50</modelName>
    <UDN>%s</UDN>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
        <controlURL>ctl/RenderingControl</controlURL>
      </service>
      <service>
        <serviceType>%s</serviceType>
        <serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>
        <controlURL>ctl/AVTransport</controlURL>
      </service>
    </serviceList>
  </device>
</root>
""" % (NAME, UDN, SERVICE)

# A device that is on the network but cannot play video (a router, say).
OTHER_DESCRIPTION = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <friendlyName>Test Router</friendlyName>
    <UDN>uuid:00000000-test-0000-0000-000000000002</UDN>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
        <controlURL>ctl/wan</controlURL>
      </service>
    </serviceList>
  </device>
</root>
"""


def _clock(sec):
    sec = max(0.0, sec)
    return "%d:%02d:%05.2f" % (int(sec) // 3600, int(sec) % 3600 // 60, sec % 60)


class FakeTV:
    def __init__(self, duration=10.0, speed=12.5, load_delay=0.03):
        self.duration = duration  # seconds every clip claims to last
        self.speed = speed  # clip seconds per real second
        self.load_delay = load_delay  # real seconds spent on "loading" after Play
        self.refuse = set()  # SetAVTransportURI fails (HTTP 500) for URLs containing any of these
        self.never_start = set()  # Play does nothing for URLs containing any of these
        self.loaded = []  # every URL the TV accepted, in order
        self.attempts = []  # every URL it was asked to load, accepted or not
        self.actions = []  # every SOAP action received, in order
        self._lock = threading.Lock()
        self._uri = ""
        self._mode = "NO_MEDIA_PRESENT"  # NO_MEDIA_PRESENT, STOPPED, LOADING, PLAYING, PAUSED_PLAYBACK
        self._base = 0.0  # position when playing last (re)started
        self._since = 0.0  # real time of that moment
        self._ready = 0.0  # real time when loading turns into playing
        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._srv.daemon_threads = True
        self._srv.tv = self
        self.port = self._srv.server_address[1]
        threading.Thread(target=self._srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    # ---- addresses
    @property
    def base(self):
        return "http://127.0.0.1:%d/" % self.port

    @property
    def location(self):
        return self.base + "desc.xml"

    @property
    def other_location(self):
        return self.base + "other.xml"

    @property
    def control_url(self):
        return self.base + "ctl/AVTransport"

    def close(self):
        self._srv.shutdown()
        self._srv.server_close()

    # ---- the simulated player (call with the lock held)
    def _settle(self):
        now = time.time()
        if self._mode == "LOADING" and now >= self._ready:
            self._mode, self._base, self._since = "PLAYING", self._base, self._ready
        if self._mode == "PLAYING" and self._base + (now - self._since) * self.speed >= self.duration:
            self._mode, self._base = "STOPPED", 0.0  # reached the end

    def _position(self):
        if self._mode == "PLAYING":
            return min(self._base + (time.time() - self._since) * self.speed, self.duration)
        if self._mode == "PAUSED_PLAYBACK":
            return self._base
        return 0.0

    # ---- what a test can read or do
    def snapshot(self):
        """(state, position, uri) as the TV would report it right now."""
        with self._lock:
            self._settle()
            state = "TRANSITIONING" if self._mode == "LOADING" else self._mode
            return state, self._position(), self._uri

    def press_stop(self):
        """The viewer presses Stop on the remote."""
        with self._lock:
            self._settle()
            self._mode, self._base = "STOPPED", 0.0

    def play_other(self, uri="http://192.0.2.9/other.mp4"):
        """Somebody else starts a different video on the TV."""
        with self._lock:
            self._uri, self._mode, self._base, self._since = uri, "PLAYING", 0.0, time.time()

    # ---- SOAP
    def handle(self, action, body):
        """Returns (http status, inner XML of the reply)."""
        with self._lock:
            self.actions.append(action)
            self._settle()
            if action == "SetAVTransportURI":
                m = re.search(r"<CurrentURI>([^<]*)", body)
                uri = html.unescape(m[1]) if m else ""
                self.attempts.append(uri)
                if any(x in uri for x in self.refuse):
                    return 500, ""
                self.loaded.append(uri)
                self._uri, self._mode, self._base = uri, "STOPPED", 0.0
            elif action == "Play":
                if not self._uri:
                    return 500, ""
                if any(x in self._uri for x in self.never_start):
                    return 200, ""
                if self._mode == "PAUSED_PLAYBACK":
                    self._mode, self._since = "PLAYING", time.time()
                elif self._mode != "PLAYING":
                    self._mode, self._ready = "LOADING", time.time() + self.load_delay
            elif action == "Pause":
                if self._mode != "PLAYING":
                    return 500, ""
                self._base, self._mode = self._position(), "PAUSED_PLAYBACK"
            elif action == "Stop":
                if self._mode == "NO_MEDIA_PRESENT":
                    return 500, ""
                self._mode, self._base = "STOPPED", 0.0
            elif action == "Seek":
                m = re.search(r"<Target>(\d+):(\d+):(\d+(?:\.\d+)?)", body)
                if not m or self._mode not in ("PLAYING", "PAUSED_PLAYBACK"):
                    return 500, ""
                self._base, self._since = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), time.time()
            elif action == "GetTransportInfo":
                state = "TRANSITIONING" if self._mode == "LOADING" else self._mode
                return 200, (
                    "<CurrentTransportState>%s</CurrentTransportState>"
                    "<CurrentTransportStatus>OK</CurrentTransportStatus>"
                    "<CurrentSpeed>1</CurrentSpeed>" % state
                )
            elif action == "GetPositionInfo":
                dur = self.duration if self._uri else 0.0
                return 200, (
                    "<Track>1</Track><TrackDuration>%s</TrackDuration><TrackURI>%s</TrackURI>"
                    "<RelTime>%s</RelTime>" % (_clock(dur), html.escape(self._uri), _clock(self._position()))
                )
            else:
                return 500, ""
            return 200, ""


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, text, kind="text/xml"):
        data = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/desc.xml":
            self._send(200, DESCRIPTION)
        elif self.path == "/other.xml":
            self._send(200, OTHER_DESCRIPTION)
        elif self.path == "/garbage.xml":
            self._send(200, "<root><device>this is not closed")
        else:
            self._send(404, "")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
        if self.path != "/ctl/AVTransport":
            return self._send(404, "")
        m = re.search(r"#(\w+)", self.headers.get("SOAPAction", ""))
        action = m[1] if m else ""
        code, inner = self.server.tv.handle(action, body)
        if code != 200:
            return self._send(code, "<s:Envelope><s:Body><s:Fault>UPnPError</s:Fault></s:Body></s:Envelope>")
        self._send(
            200,
            '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            '<s:Body><u:%sResponse xmlns:u="%s">%s</u:%sResponse></s:Body></s:Envelope>'
            % (action, SERVICE, inner, action),
        )

    def log_message(self, fmt, *args):
        pass
