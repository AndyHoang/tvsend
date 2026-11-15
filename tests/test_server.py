import http.client
import os
import urllib.parse

import pytest
from conftest import make_video

from tvsend.server import FileServer, mime_for, parse_range


def ask(server, path, method="GET", headers=None):
    """One request; returns (status, headers dict with lowercase names, body)."""
    conn = http.client.HTTPConnection(server.host, server.port, timeout=5)
    try:
        conn.request(method, path, headers=headers or {})
        r = conn.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        conn.close()


def url_path(url):
    return urllib.parse.urlsplit(url).path


@pytest.fixture
def clip(tmp_path):
    return make_video(tmp_path / "my clip é.mp4", 1000)


def test_listens_on_one_address_only(server):
    assert server.host == "127.0.0.1" and server.port > 0
    assert server.base == "http://127.0.0.1:%d/" % server.port


@pytest.mark.parametrize("host", ["0.0.0.0", "", "::", "*"])
def test_refuses_all_interfaces(host):
    with pytest.raises(ValueError):
        FileServer(host, 0)


def test_token_url_serves_the_file(server, clip):
    url = server.add(clip)
    assert url.startswith(server.base) and url.endswith("/my%20clip%20%C3%A9.mp4")
    assert server.owns(url) and not server.owns("http://192.0.2.5/x.mp4") and not server.owns("")
    status, headers, body = ask(server, url_path(url))
    assert status == 200
    assert body == open(clip, "rb").read()
    assert headers["content-type"] == "video/mp4"
    assert headers["content-length"] == "1000"
    assert headers["accept-ranges"] == "bytes"
    assert "DLNA.ORG_OP=01" in headers["contentfeatures.dlna.org"]


def test_same_file_gets_the_same_url_and_others_differ(server, clip, tmp_path):
    other = make_video(tmp_path / "other.mkv", 10)
    assert server.add(clip) == server.add(clip)
    assert server.add(other) != server.add(clip)
    assert ask(server, url_path(server.add(other)))[1]["content-type"] == "video/x-matroska"


def test_add_missing_file_raises(server, tmp_path):
    with pytest.raises(OSError):
        server.add(str(tmp_path / "nope.mp4"))
    with pytest.raises(OSError):
        server.add(str(tmp_path))


def test_head(server, clip):
    status, headers, body = ask(server, url_path(server.add(clip)), "HEAD")
    assert status == 200 and body == b"" and headers["content-length"] == "1000"


def test_range_requests(server, clip):
    path, data = url_path(server.add(clip)), open(clip, "rb").read()
    status, headers, body = ask(server, path, headers={"Range": "bytes=10-19"})
    assert (status, body, headers["content-range"]) == (206, data[10:20], "bytes 10-19/1000")
    status, headers, body = ask(server, path, headers={"Range": "bytes=990-"})
    assert (status, body, headers["content-range"]) == (206, data[990:], "bytes 990-999/1000")
    status, headers, body = ask(server, path, headers={"Range": "bytes=-5"})
    assert (status, body, headers["content-range"]) == (206, data[-5:], "bytes 995-999/1000")
    status, headers, body = ask(server, path, headers={"Range": "bytes=500-99999"})
    assert (status, body) == (206, data[500:])
    status, headers, body = ask(server, path, headers={"Range": "bytes=0-0"})
    assert (status, body) == (206, data[:1])


def test_range_outside_the_file(server, clip):
    path = url_path(server.add(clip))
    for rng in ("bytes=1000-", "bytes=5000-6000", "bytes=20-10", "bytes=-0"):
        status, headers, body = ask(server, path, headers={"Range": rng})
        assert (status, body, headers["content-range"]) == (416, b"", "bytes */1000"), rng


def test_unusable_range_sends_everything(server, clip):
    for rng in ("lines=1-2", "bytes=-", "bytes=1-2,5-6", "nonsense"):
        status, _, body = ask(server, url_path(server.add(clip)), headers={"Range": rng})
        assert status == 200 and len(body) == 1000, rng


def test_parse_range():
    assert parse_range(None, 100) is None
    assert parse_range("bytes=0-", 100) == (0, 99)
    assert parse_range(" bytes = 5 - 9 ", 100) == (5, 9)
    assert parse_range("bytes=-10", 100) == (90, 99)
    assert parse_range("bytes=-500", 100) == (0, 99)
    assert parse_range("bytes=100-", 100) == "bad"
    assert parse_range("bytes=0-", 0) == "bad"


def test_unknown_token_is_404(server, clip):
    server.add(clip)
    status, _, body = ask(server, "/not-a-real-token/" + urllib.parse.quote(os.path.basename(clip)))
    assert (status, body) == (404, b"")


def test_path_tricks_get_nothing(server, clip, tmp_path):
    secret = make_video(tmp_path / "secret.mp4", 10)
    token = url_path(server.add(clip)).split("/")[1]
    name = urllib.parse.quote(os.path.basename(clip))
    tricks = [
        "/",
        "/" + name,
        "/" + token,
        "//" + name,
        "/%s/sub/%s" % (token, name),
        "/../" + name,
        "/%s/../secret.mp4/x" % token,
        "/%2e%2e/secret.mp4",
        "/%s%%2f%s" % (token, name),
        secret,
        "/" + urllib.parse.quote(secret, safe=""),
        "/x/" + urllib.parse.quote(secret, safe=""),
        "/etc/passwd",
        "/x/..%2f..%2f..%2fetc%2fpasswd",
        "http://192.0.2.1/" + name,
    ]
    for path in tricks:
        status, _, body = ask(server, path)
        assert status == 404 and body == b"", path


def test_no_folder_listing(server, clip):
    token = url_path(server.add(clip)).split("/")[1]
    assert ask(server, "/%s/" % token)[2] in (b"", open(clip, "rb").read())  # never a listing
    assert b"<" not in ask(server, "/")[2]


def test_other_methods_are_refused(server, clip):
    path = url_path(server.add(clip))
    for method in ("POST", "PUT", "DELETE"):
        status, _, body = ask(server, path, method)
        assert status >= 400 and body == b"", method


def test_file_removed_after_queueing_is_404(server, clip):
    path = url_path(server.add(clip))
    os.unlink(clip)
    assert ask(server, path)[0] == 404


def test_log_callback_gets_one_line_per_request(clip):
    lines = []
    srv = FileServer("127.0.0.1", 0, log=lines.append)
    srv.start()
    try:
        ask(srv, url_path(srv.add(clip)))
        ask(srv, "/nope/x.mp4")
    finally:
        srv.stop()
    assert len(lines) == 2 and "-> 200" in lines[0] and "-> 404" in lines[1]


def test_stop_frees_the_port_and_start_twice_is_harmless(clip):
    srv = FileServer("127.0.0.1", 0)
    srv.start()
    srv.start()
    port = srv.port
    srv.stop()
    srv.stop()
    again = FileServer("127.0.0.1", port)
    again.start()
    try:
        assert ask(again, url_path(again.add(clip)))[0] == 200
    finally:
        again.stop()


def test_port_in_use_raises(server):
    with pytest.raises(OSError):
        FileServer("127.0.0.1", server.port).start()


def test_mime_for():
    assert mime_for("a.MP4") == "video/mp4" and mime_for("a.m4v") == "video/mp4"
    assert mime_for("a.mov") == "video/quicktime" and mime_for("a.webm") == "video/webm"
    assert mime_for("a.avi") == "video/x-msvideo" and mime_for("a.ts") == "video/mp2t"
    assert mime_for("a.unknown") == "video/mp4"
