"""DLNA / UPnP AVTransport: the protocol most smart TVs accept video over."""

import html
import re
import urllib.request

from ..config import TV
from .base import State

DLNA_FLAGS = "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"


def seconds(text: str) -> float:
    m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", text or "")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def clock_time(sec: float) -> str:
    sec = max(0, int(sec))
    return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def _tag(name: str, xml: str) -> str:
    m = re.search("<%s>([^<]*)" % name, xml)
    return m[1] if m else ""


class DlnaTV:
    def __init__(self, tv: TV):
        self.tv = tv
        self.name = tv.name

    def soap(self, action: str, args: str = "", timeout: float = 8) -> tuple[bool, str]:
        """Send one AVTransport command. Returns (ok, reply text or error)."""
        service = self.tv.service
        body = (
            '<?xml version="1.0" encoding="utf-8"?><s:Envelope '
            'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            '<u:%s xmlns:u="%s"><InstanceID>0</InstanceID>%s</u:%s></s:Body></s:Envelope>'
            % (action, service, args, action)
        )
        req = urllib.request.Request(
            self.tv.control_url,
            body.encode(),
            {"Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": '"%s#%s"' % (service, action)},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return True, r.read().decode(errors="replace")
        except Exception as e:
            return False, str(e)

    def state(self) -> State:
        ok, t = self.soap("GetTransportInfo", timeout=4)
        if not ok:
            return State("", 0.0, 0.0, "")
        ok, p = self.soap("GetPositionInfo", timeout=4)
        if not ok:
            p = ""
        return State(
            _tag("CurrentTransportState", t),
            seconds(_tag("RelTime", p)),
            seconds(_tag("TrackDuration", p)),
            html.unescape(_tag("TrackURI", p)),
        )

    def load(self, url: str, title: str, mime: str) -> tuple[bool, str]:
        meta = (
            '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
            '<item id="1" parentID="0" restricted="1"><dc:title>%s</dc:title>'
            "<upnp:class>object.item.videoItem</upnp:class>"
            '<res protocolInfo="http-get:*:%s:%s">%s</res></item></DIDL-Lite>'
            % (html.escape(title), mime, DLNA_FLAGS, html.escape(url))
        )
        return self.soap(
            "SetAVTransportURI",
            "<CurrentURI>%s</CurrentURI><CurrentURIMetaData>%s</CurrentURIMetaData>"
            % (html.escape(url), html.escape(meta)),
            timeout=30,
        )

    def play(self) -> tuple[bool, str]:
        return self.soap("Play", "<Speed>1</Speed>")

    def pause(self) -> tuple[bool, str]:
        return self.soap("Pause")

    def stop(self) -> tuple[bool, str]:
        return self.soap("Stop")

    def seek(self, sec: float) -> tuple[bool, str]:
        return self.soap("Seek", "<Unit>REL_TIME</Unit><Target>%s</Target>" % clock_time(sec))
