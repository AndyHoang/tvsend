import socket

import fake_tv as fake

from tvsend import discovery


def test_describe_reads_the_tv(fake_tv):
    tv = discovery.describe(fake_tv.location)
    assert tv is not None
    assert tv.name == "Test TV"
    assert tv.id == fake.UDN
    assert tv.model == "Fake 50"
    assert tv.address == "127.0.0.1"
    assert tv.control_url == fake_tv.control_url  # the relative controlURL is resolved against the location
    assert tv.location == fake_tv.location
    assert tv.service == "urn:schemas-upnp-org:service:AVTransport:1"
    assert tv.backend == "dlna"


def test_describe_device_that_cannot_play_video(fake_tv):
    assert discovery.describe(fake_tv.other_location) is None


def test_describe_bad_answers(fake_tv):
    assert discovery.describe(fake_tv.base + "garbage.xml") is None
    assert discovery.describe(fake_tv.base + "missing.xml") is None
    assert discovery.describe("https://127.0.0.1:%d/desc.xml" % fake_tv.port) is None  # http only
    assert discovery.describe("file:///etc/passwd") is None
    assert discovery.describe("") is None


def test_describe_nobody_listening():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert discovery.describe("http://127.0.0.1:%d/desc.xml" % port, timeout=1) is None


def test_local_ip_for():
    assert discovery.local_ip_for("127.0.0.1") == "127.0.0.1"


def test_typed_description_url(fake_tv):
    tv = discovery.from_user_input("  " + fake_tv.location + " ")
    assert tv is not None and tv.id == fake.UDN


def test_search_describes_and_dedups(fake_tv, monkeypatch):
    # No SSDP packets in tests: pretend the network answered with these locations.
    found = [
        fake_tv.location,
        fake_tv.other_location,
        fake_tv.location + "?again",
        fake_tv.base + "missing.xml",
    ]
    monkeypatch.setattr(discovery, "_locations", lambda *a, **k: found)
    tvs = discovery.search(timeout=0.1, deep=False)
    assert [t.id for t in tvs] == [fake.UDN]  # the same TV announced twice is listed once


def test_search_nothing_found(monkeypatch):
    monkeypatch.setattr(discovery, "_locations", lambda *a, **k: [])
    assert discovery.search(timeout=0.1, deep=False) == []


def test_deep_search_asks_the_typed_address_directly(fake_tv, monkeypatch):
    # SSDP silent: the known description addresses are tried on that one device.
    monkeypatch.setattr(discovery, "_locations", lambda *a, **k: [])
    monkeypatch.setattr(discovery, "KNOWN_DESCRIPTIONS", [(fake_tv.port, "/desc.xml")])
    assert discovery.probe_address("127.0.0.1").id == fake.UDN
    assert [t.id for t in discovery.search(timeout=0.1, address="127.0.0.1")] == [fake.UDN]
    assert discovery.from_user_input("127.0.0.1").id == fake.UDN
    monkeypatch.setattr(discovery, "KNOWN_DESCRIPTIONS", [(fake_tv.port, "/other.xml")])
    assert discovery.probe_address("127.0.0.1") is None


def test_probe_network_only_looks_around_a_home_network(monkeypatch):
    asked = []
    monkeypatch.setattr(discovery, "probe_address", lambda ip: asked.append(ip))
    assert discovery.probe_network("203.0.114.7") == [] and asked == []  # a public address: never
    assert discovery.probe_network("not an address") == []
    assert discovery.probe_network("192.168.7.20") == []
    assert len(asked) == 253 and "192.168.7.20" not in asked and "192.168.7.1" in asked
