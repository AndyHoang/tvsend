"""Finding TVs on the home network and reading what they say about themselves.

Two ways, in this order:

1. SSDP: one question sent to the whole network; TVs answer with the address of their
   description. A firewall on this computer often drops those answers (ufw does by
   default), which is why the question is sent from a fixed port (the tvsend port) that
   one firewall rule can open, and why there is a second way.
2. Asking directly: the description addresses that common TV brands use are tried on
   every address of the home network (or on the one address the user typed). This needs
   no answers to get through the firewall, but only finds the brands listed below.
"""

import ipaddress
import socket
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from .config import DEFAULT_PORT, TV

SSDP_GROUP = "239.255.255.250"
SSDP_PORT = 1900
SEARCH_TARGETS = (
    "urn:schemas-upnp-org:service:AVTransport:1",
    "urn:schemas-upnp-org:device:MediaRenderer:1",
)
MAX_DESCRIPTION = 1_000_000  # bytes; a device description is a few kB

# Where some brands publish their description (port, path). Samsung is confirmed on a
# real TV; the others are the commonly documented ones and still need confirming.
KNOWN_DESCRIPTIONS = (
    (9197, "/dmr"),  # Samsung
    (52323, "/dmr.xml"),  # Sony
    (55000, "/dmr/ddd.xml"),  # Panasonic
)
PROBE_TIMEOUT = 0.4  # seconds to wait for one address to accept a connection


def local_ip_for(address: str) -> str:
    """This computer's own address on the network that reaches `address` (never 0.0.0.0)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((address, 9))  # UDP: nothing is sent, the system only picks the route
        return s.getsockname()[0]
    finally:
        s.close()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el, name: str):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el, name: str) -> str:
    c = _child(el, name) if el is not None else None
    return (c.text or "").strip() if c is not None else ""


def describe(location: str, timeout: float = 4.0) -> TV | None:
    """Read a device description and return the TV it describes, or None if it cannot play video."""
    if urllib.parse.urlsplit(location).scheme != "http":
        return None
    try:
        with urllib.request.urlopen(location, timeout=timeout) as r:
            root = ET.fromstring(r.read(MAX_DESCRIPTION))
    except Exception:
        return None
    base = _text(root, "URLBase") or location
    for dev in root.iter():
        if _local(dev.tag) != "device":
            continue
        services = _child(dev, "serviceList")
        for svc in services if services is not None else ():
            kind = _text(svc, "serviceType")
            control = _text(svc, "controlURL")
            if kind.startswith("urn:schemas-upnp-org:service:AVTransport:") and control:
                host = urllib.parse.urlsplit(location).hostname or ""
                return TV(
                    id=_text(dev, "UDN") or location,
                    name=_text(dev, "friendlyName") or _text(dev, "modelName") or host,
                    address=host,
                    control_url=urllib.parse.urljoin(base, control),
                    location=location,
                    service=kind,
                    model=_text(dev, "modelName"),
                )
    return None


# ---------------------------------------------------------------- way 1: SSDP
def _locations(timeout: float, address: str | None, source_port: int = 0) -> list[str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    found: list[str] = []
    try:
        if source_port:
            try:  # this computer's one LAN address, and the port a firewall rule can name
                sock.bind((local_ip_for(address or SSDP_GROUP), source_port))
            except OSError:
                pass  # port busy: an automatic port still works where no firewall is in the way
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        dest = (address or SSDP_GROUP, SSDP_PORT)
        mx = max(1, min(int(timeout) - 1, 3))
        for _ in range(2):  # UDP may lose a packet: ask twice
            for st in SEARCH_TARGETS:
                msg = (
                    'M-SEARCH * HTTP/1.1\r\nHOST: %s:%d\r\nMAN: "ssdp:discover"\r\nMX: %d\r\nST: %s\r\n\r\n'
                    % (SSDP_GROUP, SSDP_PORT, mx, st)
                )
                try:
                    sock.sendto(msg.encode(), dest)
                except OSError:
                    pass
        deadline = time.time() + timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                break
            sock.settimeout(left)
            try:
                data, _ = sock.recvfrom(65507)
            except OSError:
                break
            for line in data.decode("utf-8", "replace").split("\r\n"):
                key, _, value = line.partition(":")
                if key.strip().lower() == "location" and value.strip() not in found:
                    found.append(value.strip())
    finally:
        sock.close()
    return found


# ---------------------------------------------------------------- way 2: asking directly
def _answers(ip: str, port: int) -> bool:
    try:
        socket.create_connection((ip, port), timeout=PROBE_TIMEOUT).close()
        return True
    except OSError:
        return False


def probe_address(ip: str) -> TV | None:
    """Try the known description addresses on one device."""
    for port, path in KNOWN_DESCRIPTIONS:
        if _answers(ip, port):
            tv = describe("http://%s:%d%s" % (ip, port, path))
            if tv:
                return tv
    return None


def probe_network(local_ip: str) -> list[TV]:
    """Try the known description addresses on every address of this computer's home network
    (the 254 neighbours of its own address)."""
    try:
        net = ipaddress.ip_network(local_ip + "/24", strict=False)
    except ValueError:
        return []
    if not net.is_private:
        return []  # only ever look around a home network
    hosts = [str(h) for h in net.hosts() if str(h) != local_ip]
    with ThreadPoolExecutor(max_workers=64) as pool:
        return [tv for tv in pool.map(probe_address, hosts) if tv]


# ---------------------------------------------------------------- the search
def _unique(tvs) -> list[TV]:
    unique: dict[str, TV] = {}
    for tv in tvs:
        unique.setdefault(tv.id, tv)
    return sorted(unique.values(), key=lambda t: (t.name.casefold(), t.address))


def search(
    timeout: float = 3.0, address: str | None = None, source_port: int = DEFAULT_PORT, deep: bool = True
) -> list[TV]:
    """Look for TVs that accept video. `address` asks one device only. With `deep`, when
    SSDP finds nothing the known description addresses are tried as well."""
    locations = _locations(timeout, address, source_port)
    tvs: list[TV] = []
    if locations:
        with ThreadPoolExecutor(max_workers=8) as pool:
            tvs = [tv for tv in pool.map(describe, locations) if tv]
    if not tvs and deep:
        try:
            if address:
                tv = probe_address(socket.gethostbyname(address))
                tvs = [tv] if tv else []
            else:
                tvs = probe_network(local_ip_for(SSDP_GROUP))
        except OSError:
            pass
    return _unique(tvs)


def from_user_input(text: str) -> TV | None:
    """What the user typed by hand: an IP address / host name, or the URL of a device description."""
    text = text.strip()
    if text.startswith("http://"):
        return describe(text)
    found = search(timeout=2.0, address=text)
    return found[0] if found else None
